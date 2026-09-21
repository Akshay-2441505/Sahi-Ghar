from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from sahighar.adapters.maharera_pages import promoter_ref
from sahighar.adapters.maharera_web import MahaReraWebAdapter
from sahighar.adapters.polite import BlockedError, BudgetExhausted, FetchError, Fetched
from sahighar.db.models import Complaint, Project, Promoter
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore

FIXTURES = Path(__file__).parent / "fixtures" / "maharera"
LIST_PAGE = (FIXTURES / "list_page1.html").read_bytes()  # real page: 10 projects, 10 different promoters
CERTS = {("5", "DocProjectCert"): (FIXTURES / "cert_reg_5.html").read_bytes(),
         ("5", "DocProjectExtCert"): (FIXTURES / "cert_ext_5.html").read_bytes()}
NO_RECORD = b"<div>No Record Found</div>"
COMPLAINANT = "GREEN SPACE INFRA VENTURES"  # the promoter of the first card


def complaint_list_html(name: str) -> bytes:
    if promoter_ref(name) != promoter_ref(COMPLAINANT):
        return b"<html>Showing Final <span class='colorBlue'>0</span> Result</html>"
    return (f'<html>Showing Final <span class="colorBlue">1</span> Result<table><tr><th>Sr</th></tr>'
            f'<tr><td class="center"> 1</td><td>{COMPLAINANT}</td><td>2</td><td class="center">'
            f'<a href="https://x.test/promoter-complaint-view-data?promoter_id=777">v</a></td></tr></table></html>').encode()


def complaint_detail_html() -> bytes:
    def row(n, no, project, status, flag):
        return (f'<tr><td> {n}</td><td>{COMPLAINANT}</td><td>{project}</td><td>Nagpur</td><td>{no}</td>'
                f'<td>2024</td><td>March</td><td>{status}</td><td>{flag}</td><td>N</td></tr>')
    return ("<table><tr><th>Sr</th></tr>" + row(1, "CC1", "P50500000005", "Hearing Scheduled", "N")
            + row(2, "CC2", "P99999999999", "Order Approved", "Y") + "</table>").encode()


def site(url: str) -> bytes:
    u, q = urlparse(url), parse_qs(urlparse(url).query)
    if u.path in ("/projects-search-result", "/promoters-search-result"):
        return LIST_PAGE
    if u.path == "/project-document":
        return CERTS.get((q["id"][0], q["type"][0]), NO_RECORD)
    if u.path == "/promoter-complaint-report":
        return complaint_list_html(q["promoter_complaint_name"][0])
    if u.path == "/promoter-complaint-view-data":
        return complaint_detail_html()
    raise AssertionError(f"unexpected url {url}")


class FakeFetcher:
    def __init__(self, route=site, limit=None, fail=None):
        self.route, self.limit, self.fail, self.requested = route, limit, fail or (lambda url: None), []

    def get(self, url):
        if self.limit is not None and len(self.requested) >= self.limit:
            raise BudgetExhausted("limit")
        self.requested.append(url)
        error = self.fail(url)
        if error:
            raise error
        return Fetched(url, self.route(url), "text/html")


def adapter(fetcher, **kwargs):
    return MahaReraWebAdapter(fetcher, pincodes=["411001"], max_list_pages=1, max_promoter_pages=1, **kwargs)


def kinds(fetcher_docs):
    return [d.kind for d in fetcher_docs]


def test_discover_seeds_by_pincode_then_completes_each_builder_then_certificates_then_complaints():
    fetcher = FakeFetcher()
    docs = list(adapter(fetcher).discover())
    order = kinds(docs)
    assert order[0] == "project_list" and order.count("promoter_list") == 10
    assert order.count("registration_certificate") == 10 and order.count("extension_certificate") == 2
    assert order.count("complaint_list") == 10 and order.count("complaints") == 1
    assert order.index("promoter_list") > 0 and order.index("registration_certificate") > order.index("promoter_list")
    assert order.index("complaint_list") > order.index("extension_certificate")
    assert "project_location=411001" in docs[0].url and all(d.origin == "maharera-web" for d in docs)
    assert len(fetcher.requested) == 34


def test_full_import_builds_projects_dates_and_complaints(session, tmp_path):
    summary = run_ingest(adapter(FakeFetcher()), session, LocalRawStore(tmp_path))
    assert summary.failed == 0
    assert session.scalar(select(Project.name).where(Project.rera_reg_no == "P50500000005")) == "GREEN CITY 3"
    meridian = session.scalar(select(Project).where(Project.rera_reg_no == "P51700002065"))
    assert (meridian.registration_end_date, meridian.extended_end_date) == (date(2018, 12, 31), date(2019, 12, 31))
    assert session.scalar(select(Project.registration_end_date).where(Project.rera_reg_no == "P50500000005")) is None  # "No Record Found"
    assert len(session.scalars(select(Promoter)).all()) == 10
    complaints = {c.complaint_ref: c for c in session.scalars(select(Complaint))}
    assert set(complaints) == {"CC1", "CC2"}
    assert complaints["CC1"].stage == "pending" and complaints["CC1"].filed_month == 3 and complaints["CC1"].project_id is not None
    assert complaints["CC2"].stage == "order_issued" and complaints["CC2"].non_execution_applied is True
    assert complaints["CC2"].project_id is None  # a project outside this crawl; still attached to its promoter
    promoter_name = session.scalar(select(Promoter.name).join(Complaint, Complaint.promoter_id == Promoter.id).limit(1))
    assert promoter_name == COMPLAINANT


def test_a_second_run_skips_certificates_and_complaint_pages_it_already_has():
    first = FakeFetcher()
    list(adapter(first).discover())
    have = {u for u in first.requested if "project-document" in u or "view-data" in u}
    second = FakeFetcher()
    list(adapter(second, is_fresh=lambda url: url in have).discover())
    assert len(second.requested) == 34 - len(have) == 21
    assert not any("project-document" in u for u in second.requested)


def test_the_request_budget_stops_the_crawl_and_keeps_what_was_fetched(session, tmp_path):
    with pytest.raises(BudgetExhausted):
        run_ingest(adapter(FakeFetcher(limit=5)), session, LocalRawStore(tmp_path))
    assert len(session.scalars(select(Project)).all()) == 10  # the first list page was already ingested


def test_a_block_stops_the_crawl_for_good():
    def fail(url):
        return BlockedError("HTTP 403") if "project-document" in url else None

    fetcher = FakeFetcher(fail=fail)
    with pytest.raises(BlockedError):
        list(adapter(fetcher).discover())
    assert sum("project-document" in u for u in fetcher.requested) == 1  # it did not carry on to the next certificate


def test_one_missing_certificate_is_skipped_not_fatal():
    def fail(url):
        return FetchError("404") if "id=3&" in url else None

    fetcher = FakeFetcher(fail=fail)
    docs = list(adapter(fetcher).discover())
    assert kinds(docs).count("registration_certificate") == 9


def test_a_promoter_list_only_yields_that_promoters_projects():
    doc = next(d for d in adapter(FakeFetcher()).discover() if d.kind == "promoter_list")
    parsed = adapter(FakeFetcher()).parse(doc)
    assert len(parsed.projects) == 1 and len(parsed.promoters) == 1
    assert parsed.projects[0].promoter_ref == parsed.promoters[0].ref
