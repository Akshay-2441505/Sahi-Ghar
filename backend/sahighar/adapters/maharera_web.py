"""Adapter that reads MahaRERA's public pages politely (maharera.maharashtra.gov.in).

Never touches the CAPTCHA-gated project detail app on the second host. All network access goes through a
PoliteFetcher, which stops the crawl on any refusal or CAPTCHA. A crawl runs in phases:
  1. project lists for the chosen pincodes (10 projects per page);
  2. each builder found in phase 1: their whole portfolio (a builder's record only means something if all their
     projects are in), via the promoter search;
  3. registration and extension certificates for every project (they hold the original and extended end dates);
  4. each builder's complaints (a name-filtered complaint list, then the promoter's complaint page).
Each fetched page is one RawDoc, so every number links to the stored page it came from.
"""
from typing import Callable, Iterable
from urllib.parse import parse_qs, quote, urlparse

from sahighar.adapters.base import ComplaintRec, ParsedRecords, ProjectRec, PromoterRec, RawDoc, complaint_stage
from sahighar.adapters.maharera_pages import (
    ProjectCard, parse_certificate, parse_complaint_detail, parse_complaint_list, parse_project_list, promoter_ref,
)
from sahighar.adapters.polite import FetchError
from sahighar.adapters.tabular import parse_month
from sahighar.util import utcnow

BASE = "https://maharera.maharashtra.gov.in"


def list_url(pincode: str, page: int) -> str:
    return (f"{BASE}/projects-search-result?project_name=&project_location={quote(pincode, safe='')}"
            f"&project_completion_date=&project_state=27&project_district=0&carpetAreas=&completionPercentages="
            f"&project_division=&page={page}&op=")


def promoter_list_url(name: str, page: int) -> str:
    return f"{BASE}/promoters-search-result?promoter_name={quote(name, safe='')}&promoter_location=&promoter_division=&page={page}&op="


def certificate_url(cert_id: str, flag: str) -> str:
    return f"{BASE}/project-document?id={cert_id}&type={flag}"


def complaint_list_url(name: str) -> str:
    return (f"{BASE}/promoter-complaint-report?promoter_complaint_division=0&promoter_complaint_district=0"
            f"&promoter_complaint_name={quote(name, safe='')}&page=1&op=")


def complaint_detail_url(promoter_id: str) -> str:
    return f"{BASE}/promoter-complaint-view-data?promoter_id={promoter_id}"


class MahaReraWebAdapter:
    state = "MH"
    origin = "maharera-web"

    def __init__(self, fetcher, pincodes: list[str] | None = None, is_fresh: Callable[[str], bool] = lambda url: False,
                 max_list_pages: int | None = None, max_promoter_pages: int = 20):
        """pincodes: seed the crawl with these (None = all of Maharashtra, about 4,900 list pages).
        is_fresh(url): True if that certificate or complaint page is already stored and recent (it is then not fetched).
        max_list_pages / max_promoter_pages: cap pages fetched per list, for trial runs."""
        self.fetcher, self.pincodes, self.is_fresh = fetcher, pincodes, is_fresh
        self.max_list_pages, self.max_promoter_pages = max_list_pages, max_promoter_pages
        self.skipped: list[str] = []  # pages that could not be fetched (not found, server error); reported by the CLI

    def _doc(self, url: str, kind: str) -> RawDoc:
        fetched = self.fetcher.get(url)
        return RawDoc(self.origin, kind, url, utcnow(), fetched.content_type or "text/html", fetched.data)

    def _optional_doc(self, url: str, kind: str) -> RawDoc | None:
        """A page whose absence is not fatal. A block or budget stop still propagates."""
        try:
            return self._doc(url, kind)
        except FetchError as error:
            self.skipped.append(f"{url}: {error}")
            return None

    def _list_pages(self, url_for, kind: str, cap: int | None, cards: dict, promoters: dict, only: str | None):
        page = 1
        pages = 1
        while page <= pages:
            doc = self._doc(url_for(page), kind)
            yield doc
            parsed = parse_project_list(doc.data.decode("utf-8", errors="replace"))
            for card in parsed.cards:
                ref = promoter_ref(card.promoter_name)
                if only is None or ref == only:
                    cards.setdefault(card.reg_no, card)
                    promoters.setdefault(ref, card.promoter_name)
            if page == 1:
                pages = parsed.pages or 1
                if cap:
                    pages = min(pages, cap)
            page += 1

    def discover(self) -> Iterable[RawDoc]:
        cards: dict[str, ProjectCard] = {}
        promoters: dict[str, str] = {}
        for pincode in self.pincodes or [""]:
            yield from self._list_pages(lambda n: list_url(pincode, n), "project_list", self.max_list_pages, cards, promoters, None)
        for ref, name in list(promoters.items()):
            yield from self._list_pages(lambda n: promoter_list_url(name, n), "promoter_list", self.max_promoter_pages,
                                        cards, promoters, ref)
        for card in sorted(cards.values(), key=lambda c: c.reg_no):
            for cert_id, flag, kind in ((card.cert_id, "DocProjectCert", "registration_certificate"),
                                        (card.ext_cert_id, "DocProjectExtCert", "extension_certificate")):
                url = certificate_url(cert_id, flag) if cert_id else None
                if url and not self.is_fresh(url) and (doc := self._optional_doc(url, kind)):
                    yield doc
        for ref, name in promoters.items():
            yield from self._complaints(ref, name)

    def _complaints(self, ref: str, name: str):
        listing = self._optional_doc(complaint_list_url(name), "complaint_list")
        if listing is None:
            return
        yield listing
        for row in parse_complaint_list(listing.data.decode("utf-8", errors="replace")).rows:
            url = complaint_detail_url(row.promoter_id)
            if promoter_ref(row.name) == ref and not self.is_fresh(url) and (doc := self._optional_doc(url, "complaints")):
                yield doc

    def parse(self, doc: RawDoc) -> ParsedRecords:
        text = doc.data.decode("utf-8", errors="replace")
        if doc.kind in ("project_list", "promoter_list"):
            cards = parse_project_list(text).cards
            if doc.kind == "promoter_list":  # the promoter search also returns similarly named builders: keep only the asked-for one
                target = promoter_ref(parse_qs(urlparse(doc.url).query)["promoter_name"][0])
                cards = [c for c in cards if promoter_ref(c.promoter_name) == target]
            return ParsedRecords(
                promoters=list({promoter_ref(c.promoter_name): PromoterRec(promoter_ref(c.promoter_name), c.promoter_name)
                                for c in cards}.values()),
                projects=[ProjectRec(c.reg_no, promoter_ref(c.promoter_name), c.name, city=c.district or None) for c in cards])
        if doc.kind in ("registration_certificate", "extension_certificate"):
            cert = parse_certificate(text)
            if cert is None:  # the site answered "No Record Found"
                return ParsedRecords()
            if cert.kind != doc.kind.removesuffix("_certificate"):
                raise ValueError(f"expected a {doc.kind} but the document is an {cert.kind} certificate")
            fields = {"registration_end": cert.valid_until} if cert.kind == "registration" else {"extended_end": cert.valid_until}
            return ParsedRecords(projects=[ProjectRec(cert.reg_no, None, None, **fields)])
        if doc.kind == "complaint_list":
            return ParsedRecords()  # kept as evidence of which promoter page to fetch
        if doc.kind == "complaints":
            return ParsedRecords(complaints=[
                ComplaintRec(r.complaint_no, promoter_ref(r.promoter_name), r.status, complaint_stage(r.status),
                             non_execution_applied=r.non_execution_applied, project_reg_no=r.project_no,
                             filed_year=r.year, filed_month=parse_month(r.month))
                for r in parse_complaint_detail(text)])
        raise ValueError(f"unknown document kind {doc.kind!r}")
