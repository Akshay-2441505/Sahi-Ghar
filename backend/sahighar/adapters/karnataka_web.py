"""Adapter for Karnataka RERA's two bulk public pages (rera.karnataka.gov.in).

No PDFs, no per-project or per-builder requests: two page fetches give a builder-level delivery record straight
from published tables (see adapters/karnataka_pages.py for what each table holds). All network access goes
through a PoliteFetcher, same rules as MahaRERA: it stops the crawl for good on any refusal or CAPTCHA.
"""
from typing import Callable, Iterable

from sahighar.adapters.base import ComplaintRec, ParsedRecords, PastProjectRec, ProjectRec, PromoterRec, RawDoc
from sahighar.adapters.karnataka_pages import (
    karnataka_complaint_stage, parse_complaint_detail, parse_complaint_index, parse_completed_list, parse_renewals_page,
)
from sahighar.adapters.maharera_pages import promoter_ref  # state-agnostic: name -> stable ref, no MH-specific logic
from sahighar.adapters.polite import FetchError
from sahighar.util import utcnow

BASE = "https://rera.karnataka.gov.in"
RENEWALS_URL = f"{BASE}/viewRenewalProjects"
COMPLETED_URL = f"{BASE}/viewAllCompletedProjects"
COMPLAINT_INDEX_URL = f"{BASE}/promoterComplaintReport"


def complaint_detail_url(token: str) -> str:
    return f"{BASE}/complaintReportWiseList?pName={token}"


def _text(doc: RawDoc) -> str:
    return doc.data.decode("utf-8", errors="replace")


class KarnatakaWebAdapter:
    state = "KA"
    origin = "karnataka-web"

    def __init__(self, fetcher, include_complaints: bool = False, is_fresh: Callable[[str], bool] = lambda url: False,
                 max_complaint_promoters: int | None = None):
        """include_complaints: also read the complaint index and every promoter's own complaint list (about 2,000
        more requests). is_fresh(url): True if that promoter's complaint page is already stored and recent (not
        re-fetched). max_complaint_promoters: cap, for trial runs."""
        self.fetcher = fetcher
        self.include_complaints = include_complaints
        self.is_fresh = is_fresh
        self.max_complaint_promoters = max_complaint_promoters
        self.skipped: list[str] = []  # promoter complaint pages that could not be fetched (not fatal)
        self.complaint_scan_complete = False  # True only once every promoter's page was attempted without a stop

    def _doc(self, url: str, kind: str) -> RawDoc:
        fetched = self.fetcher.get(url)
        return RawDoc(self.origin, kind, url, utcnow(), fetched.content_type or "text/html", fetched.data)

    def _optional_doc(self, url: str, kind: str) -> RawDoc | None:
        try:
            return self._doc(url, kind)
        except FetchError as error:
            self.skipped.append(f"{url}: {error}")
            return None

    def discover(self) -> Iterable[RawDoc]:
        yield self._doc(RENEWALS_URL, "ka_renewals")
        yield self._doc(COMPLETED_URL, "ka_completed")
        if self.include_complaints:
            index_doc = self._doc(COMPLAINT_INDEX_URL, "ka_complaint_index")
            yield index_doc
            all_rows = parse_complaint_index(_text(index_doc))
            rows = all_rows[:self.max_complaint_promoters] if self.max_complaint_promoters else all_rows
            for row in rows:
                url = complaint_detail_url(row.token)
                if self.is_fresh(url):
                    continue
                doc = self._optional_doc(url, "ka_complaint_detail")
                if doc:
                    yield doc
            # reached only if nothing (budget, block) stopped the loop above, and it was not artificially capped
            self.complaint_scan_complete = rows is all_rows

    def parse(self, doc: RawDoc) -> ParsedRecords:
        text = _text(doc)
        if doc.kind == "ka_renewals":
            page = parse_renewals_page(text)
            promoters: dict[str, str] = {}
            projects: dict[str, ProjectRec] = {}  # keyed by reg_no: approved > rejected > expired (see below)
            # The "expired" table's single completion_date is often just the CURRENT (already-extended) deadline
            # for a project also listed in "approved extensions" -- letting it win would silently hide a real
            # extension, exactly what this score exists to surface. Only the approved table gives a genuine
            # original/extended pair, so a reg_no already placed by a more authoritative table is never replaced.
            for r in page.approved:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.setdefault(r.reg_no, ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name,
                                                         city=r.district, registration_end=r.old_completion, extended_end=r.new_completion))
            for r in page.rejected:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.setdefault(r.reg_no, ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name,
                                                         city=r.district, registration_end=r.proposed_completion))
            for r in page.expired:
                promoters[promoter_ref(r.promoter_name)] = r.promoter_name
                projects.setdefault(r.reg_no, ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name,
                                                         city=r.district, registration_end=r.completion_date, extended_end=r.further_extension_date))
            return ParsedRecords(promoters=[PromoterRec(ref, name) for ref, name in promoters.items()],
                                 projects=list(projects.values()))
        if doc.kind == "ka_completed":
            rows = parse_completed_list(text)
            promoters = {promoter_ref(r.promoter_name): r.promoter_name for r in rows}
            return ParsedRecords(
                promoters=[PromoterRec(ref, name) for ref, name in promoters.items()],
                # No registration_end here: "proposed completion" may already be an already-extended date, not
                # the original -- unlike the renewals tables, this list alone cannot tell the two apart, and
                # guessing risks the same silently-hidden-extension mistake as above. It still introduces the
                # project (a name/city, in case this is its only source) even though the schedule stays unknown.
                projects=[ProjectRec(r.reg_no, promoter_ref(r.promoter_name), r.project_name, city=r.district) for r in rows],
                # "applied for completion" is the promoter's own request to close the project out, not a verified
                # finish -- the same honesty level as MahaRERA's self-declared past projects, so it feeds the same field.
                past_projects=[PastProjectRec(promoter_ref(r.promoter_name), r.project_name, r.proposed_completion,
                                              r.applied_for_completion, r.project_type)
                               for r in rows if r.proposed_completion and r.applied_for_completion],
            )
        if doc.kind == "ka_complaint_index":
            return ParsedRecords()  # kept raw as evidence of the crawl; counts alone cannot feed the score honestly
        if doc.kind == "ka_complaint_detail":
            rows = parse_complaint_detail(text)
            if not rows:
                return ParsedRecords()
            # a detail page is scoped to one promoter, introduced here (it may have no schedule data at all)
            name = rows[0].promoter_name
            ref = promoter_ref(name)
            return ParsedRecords(
                promoters=[PromoterRec(ref, name)],
                complaints=[ComplaintRec(
                    ref=r.complaint_no, promoter_ref=ref, status=r.status, stage=karnataka_complaint_stage(r.status),
                    filed_year=r.complaint_date.year if r.complaint_date else None,
                    filed_month=r.complaint_date.month if r.complaint_date else None,
                    order_url=f"{BASE}{r.order_url}" if r.order_url else None,
                ) for r in rows],
            )
        raise ValueError(f"unknown document kind {doc.kind!r}")
