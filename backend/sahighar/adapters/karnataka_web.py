"""Adapter for Karnataka RERA's two bulk public pages (rera.karnataka.gov.in).

No PDFs, no per-project or per-builder requests: two page fetches give a builder-level delivery record straight
from published tables (see adapters/karnataka_pages.py for what each table holds). All network access goes
through a PoliteFetcher, same rules as MahaRERA: it stops the crawl for good on any refusal or CAPTCHA.
"""
from typing import Iterable

from sahighar.adapters.base import ParsedRecords, PastProjectRec, ProjectRec, PromoterRec, RawDoc
from sahighar.adapters.karnataka_pages import parse_completed_list, parse_renewals_page
from sahighar.adapters.maharera_pages import promoter_ref  # state-agnostic: name -> stable ref, no MH-specific logic
from sahighar.util import utcnow

BASE = "https://rera.karnataka.gov.in"
RENEWALS_URL = f"{BASE}/viewRenewalProjects"
COMPLETED_URL = f"{BASE}/viewAllCompletedProjects"


def _text(doc: RawDoc) -> str:
    return doc.data.decode("utf-8", errors="replace")


class KarnatakaWebAdapter:
    state = "KA"
    origin = "karnataka-web"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def _doc(self, url: str, kind: str) -> RawDoc:
        fetched = self.fetcher.get(url)
        return RawDoc(self.origin, kind, url, utcnow(), fetched.content_type or "text/html", fetched.data)

    def discover(self) -> Iterable[RawDoc]:
        yield self._doc(RENEWALS_URL, "ka_renewals")
        yield self._doc(COMPLETED_URL, "ka_completed")

    def parse(self, doc: RawDoc) -> ParsedRecords:
        text = _text(doc)
        if doc.kind == "ka_renewals":
            page = parse_renewals_page(text)
            promoters: dict[str, str] = {}
            projects = []
            for r in page.approved:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.append(ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name, city=r.district,
                                           registration_end=r.old_completion, extended_end=r.new_completion))
            for r in page.rejected:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.append(ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name, city=r.district,
                                           registration_end=r.proposed_completion))
            for r in page.expired:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.append(ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name, city=r.district,
                                           registration_end=r.completion_date, extended_end=r.further_extension_date))
            return ParsedRecords(promoters=[PromoterRec(ref, name) for ref, name in promoters.items()], projects=projects)
        if doc.kind == "ka_completed":
            rows = parse_completed_list(text)
            promoters = {promoter_ref(r.promoter_name): r.promoter_name for r in rows}
            return ParsedRecords(
                promoters=[PromoterRec(ref, name) for ref, name in promoters.items()],
                projects=[ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name, city=r.district,
                                     registration_end=r.proposed_completion) for r in rows],
                # "applied for completion" is the promoter's own request to close the project out, not a verified
                # finish -- the same honesty level as MahaRERA's self-declared past projects, so it feeds the same field.
                past_projects=[PastProjectRec(promoter_ref(r.promoter_name), r.project_name, r.proposed_completion,
                                              r.applied_for_completion, r.project_type)
                               for r in rows if r.proposed_completion and r.applied_for_completion],
            )
        raise ValueError(f"unknown document kind {doc.kind!r}")
