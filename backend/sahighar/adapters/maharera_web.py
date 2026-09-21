"""Adapter that reads MahaRERA's public pages politely (maharera.maharashtra.gov.in).

Never touches the CAPTCHA-gated project detail app on the second host. All network access goes through a
PoliteFetcher, which stops the crawl on any refusal or CAPTCHA. A crawl runs in phases:
  1. project lists for the chosen pincodes (10 projects per page);
  2. each builder found in phase 1: their whole portfolio (a builder's record only means something if all their
     projects are in), via the promoter search;
  3. registration and extension certificates for every project (they hold the original and extended end dates);
  4. complaints: the complete complaint report index (the site's name filter needs a form POST, so the whole index
     is read once, about 540 pages, and reused), then the complaint page of each builder in scope.
Each fetched page is one RawDoc, so every number links to the stored page it came from.
"""
from math import ceil
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
    # the promoter search box is named promoters_name (plural); the promoter_name in the site's own paging links is ignored
    return f"{BASE}/promoters-search-result?promoters_name={quote(name, safe='')}&promoter_location=&page={page}&op="


def certificate_url(cert_id: str, flag: str) -> str:
    return f"{BASE}/project-document?id={cert_id}&type={flag}"


def complaint_list_page_url(page: int) -> str:
    return (f"{BASE}/promoter-complaint-report?promoter_complaint_division=0&promoter_complaint_district=0"
            f"&promoter_complaint_name=&page={page}&op=")


def complaint_detail_url(promoter_id: str) -> str:
    return f"{BASE}/promoter-complaint-view-data?promoter_id={promoter_id}"


def _text(doc: RawDoc) -> str:
    return doc.data.decode("utf-8", errors="replace")


class MahaReraWebAdapter:
    state = "MH"
    origin = "maharera-web"

    def __init__(self, fetcher, pincodes: list[str] | None = None, is_fresh: Callable[[str], bool] = lambda url: False,
                 max_list_pages: int | None = None, max_promoter_pages: int = 20, max_complaint_pages: int | None = None,
                 stored: Callable[[str], bytes | None] = lambda url: None):
        """pincodes: seed the crawl with these (None = all of Maharashtra, about 4,900 list pages).
        is_fresh(url): True if that certificate or complaint page is already stored and recent (it is then not fetched).
        stored(url): the stored bytes of a recent complaint report page, or None (used for planning, not re-fetched).
        max_list_pages / max_promoter_pages / max_complaint_pages: caps, for trial runs."""
        self.fetcher, self.pincodes, self.is_fresh, self.stored = fetcher, pincodes, is_fresh, stored
        self.max_list_pages, self.max_promoter_pages = max_list_pages, max_promoter_pages
        self.max_complaint_pages = max_complaint_pages
        self.skipped: list[str] = []  # pages that could not be fetched (not found, server error); reported by the CLI
        self._complaint_ids: dict[str, list[str]] = {}

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
        page, pages = 1, 1
        while page <= pages:
            doc = self._doc(url_for(page), kind)
            yield doc
            parsed = parse_project_list(_text(doc))
            for card in parsed.cards:
                ref = promoter_ref(card.promoter_name)
                if only is None or ref == only:
                    cards.setdefault(card.reg_no, card)
                    promoters.setdefault(ref, card.promoter_name)
            if page == 1:
                pages = min(parsed.pages or 1, cap) if cap else (parsed.pages or 1)
            page += 1

    def _certificate(self, cert_id: str | None, flag: str, kind: str) -> RawDoc | None:
        url = certificate_url(cert_id, flag) if cert_id else None
        if url is None or self.is_fresh(url):
            return None
        return self._optional_doc(url, kind)

    @staticmethod
    def _is_complete(doc: RawDoc) -> bool:
        try:
            cert = parse_certificate(_text(doc))
        except Exception:
            return False  # a broken certificate is reported when it is parsed, not here
        return bool(cert and cert.complete)

    def _complaint_index(self):
        """Yield the complaint report pages (from the site, or reused from storage) and remember each promoter's ids."""
        ids: dict[str, list[str]] = {}
        page, pages = 1, 1
        while page <= pages:
            url = complaint_list_page_url(page)
            data = self.stored(url)
            if data is None:
                doc = self._doc(url, "complaint_list")
                yield doc
                data = doc.data
            parsed = parse_complaint_list(data.decode("utf-8", errors="replace"))
            for row in parsed.rows:
                ids.setdefault(promoter_ref(row.name), []).append(row.promoter_id)
            if page == 1:
                pages = ceil(parsed.total / 10) if parsed.total else 1
                if self.max_complaint_pages:
                    pages = min(pages, self.max_complaint_pages)
            page += 1
        self._complaint_ids = ids

    def discover(self) -> Iterable[RawDoc]:
        cards: dict[str, ProjectCard] = {}
        promoters: dict[str, str] = {}
        for pincode in self.pincodes or [""]:
            yield from self._list_pages(lambda n: list_url(pincode, n), "project_list", self.max_list_pages, cards, promoters, None)
        for ref, name in list(promoters.items()):
            yield from self._list_pages(lambda n: promoter_list_url(name, n), "promoter_list", self.max_promoter_pages,
                                        cards, promoters, ref)
        for card in sorted(cards.values(), key=lambda c: c.reg_no):
            registration = self._certificate(card.cert_id, "DocProjectCert", "registration_certificate")
            if registration:
                yield registration
            if not (registration and self._is_complete(registration)):  # a newer certificate already holds the extension
                extension = self._certificate(card.ext_cert_id, "DocProjectExtCert", "extension_certificate")
                if extension:
                    yield extension
        yield from self._complaint_index()
        for ref in promoters:
            for promoter_id in self._complaint_ids.get(ref, []):
                url = complaint_detail_url(promoter_id)
                if not self.is_fresh(url) and (doc := self._optional_doc(url, "complaints")):
                    yield doc

    def parse(self, doc: RawDoc) -> ParsedRecords:
        text = _text(doc)
        if doc.kind in ("project_list", "promoter_list"):
            cards = parse_project_list(text).cards
            if doc.kind == "promoter_list":  # the search also returns similarly named builders: keep only the asked-for one
                target = promoter_ref(parse_qs(urlparse(doc.url).query)["promoters_name"][0])
                cards = [c for c in cards if promoter_ref(c.promoter_name) == target]
            return ParsedRecords(
                promoters=list({promoter_ref(c.promoter_name): PromoterRec(promoter_ref(c.promoter_name), c.promoter_name)
                                for c in cards}.values()),
                projects=[ProjectRec(c.reg_no, promoter_ref(c.promoter_name), c.name, city=c.district or None) for c in cards])
        if doc.kind in ("registration_certificate", "extension_certificate"):
            cert = parse_certificate(text)
            if cert is None:  # "No Record Found", or a JSON error where the PDF should be
                return ParsedRecords()
            extended = cert.current_end if cert.current_end and (cert.original_end is None or cert.current_end > cert.original_end) else None
            return ParsedRecords(projects=[ProjectRec(cert.reg_no, None, None, registration_end=cert.original_end, extended_end=extended)])
        if doc.kind == "complaint_list":
            return ParsedRecords()  # kept as evidence of which promoter page to fetch
        if doc.kind == "complaints":
            return ParsedRecords(complaints=[
                ComplaintRec(r.complaint_no, promoter_ref(r.promoter_name), r.status, complaint_stage(r.status),
                             non_execution_applied=r.non_execution_applied, project_reg_no=r.project_no,
                             filed_year=r.year, filed_month=parse_month(r.month))
                for r in parse_complaint_detail(text)])
        raise ValueError(f"unknown document kind {doc.kind!r}")
