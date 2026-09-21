import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from sahighar.adapters.maharera_pages import promoter_ref
from sahighar.adapters.maharera_web import MahaReraWebAdapter
from sahighar.adapters.polite import BlockedError, BudgetExhausted, FetchError, Fetched
from sahighar.db.models import Complaint, Project, Promoter
from sahighar.privacy import tokenize
from tests.application_samples import COMPANY, application_html
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore

FIXTURES = Path(__file__).parent / "fixtures" / "maharera"
LIST_PAGE = (FIXTURES / "list_page1.html").read_bytes()  # real page: 10 projects, 10 different promoters
CERTS = {("5", "DocProjectCert"): (FIXTURES / "cert_reg_5.html").read_bytes(),
         ("5", "DocProjectExtCert"): (FIXTURES / "cert_ext_5.html").read_bytes()}
NEW_FORMAT = (FIXTURES / "cert_new_format.html").read_bytes()
ERROR_JSON = (FIXTURES / "cert_error_json.html").read_bytes()
NO_RECORD = b"<div>No Record Found</div>"
COMPLAINANT = "GREEN SPACE INFRA VENTURES"  # the promoter of the first card


def complaint_list_html() -> bytes:
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
    if u.path == "/project-document" and q["type"] == ["DocProjectHSMViewCert"]:
        return application_html(COMPANY)
    if u.path == "/project-document":
        return CERTS.get((q["id"][0], q["type"][0]), NO_RECORD)
    if u.path == "/promoter-complaint-report":
        return complaint_list_html()
    if u.path == "/promoter-complaint-view-data":
        return complaint_detail_html()
    raise AssertionError(f"unexpected url {url}")


class FakeFetcher:
    def __init__(self, route=site, limit=None, fail=None):
        self.route, self.limit, self.fail, self.requested = route, limit, fail or (lambda url: None), []

    @property
    def requests(self):
        return len(self.requested)

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
    assert order.count("complaint_list") == 1 and order.count("complaints") == 1
    assert order.count("application") == 10  # one application per builder
    assert order.index("promoter_list") > 0 and order.index("registration_certificate") > order.index("promoter_list")
    assert order.index("complaint_list") > order.index("extension_certificate")
    assert "project_location=411001" in docs[0].url and all(d.origin == "maharera-web" for d in docs)
    assert len(fetcher.requested) == 35  # 1 + 10 builders + 10 + 2 certificates + 10 applications + 1 complaint page + 1 detail


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
    assert len(second.requested) == 35 - len(have) == 12
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


def test_builder_portfolios_use_the_real_filter_parameter_of_the_promoter_search():
    fetcher = FakeFetcher()
    list(adapter(fetcher).discover())
    portfolio_urls = [u for u in fetcher.requested if "promoters-search-result" in u]
    assert len(portfolio_urls) == 10 and all("promoters_name=" in u and "promoter_name=" not in u for u in portfolio_urls)


def test_a_complete_certificate_saves_the_extension_request():
    def route(url):
        q = parse_qs(urlparse(url).query)
        if urlparse(url).path == "/project-document" and q["id"] == ["15"] and q["type"] == ["DocProjectCert"]:
            return NEW_FORMAT  # already carries the extension history
        return site(url)

    fetcher = FakeFetcher(route=route)
    list(adapter(fetcher).discover())
    assert not any("type=DocProjectExtCert" in u and "id=15&" in u for u in fetcher.requested)
    assert any("id=5&type=DocProjectExtCert" in u for u in fetcher.requested)  # an old-format certificate still needs its extension


def test_a_certificate_endpoint_answering_with_a_json_error_is_not_a_failure(session, tmp_path):
    def route(url):
        q = parse_qs(urlparse(url).query)
        if urlparse(url).path == "/project-document" and q["id"] == ["3"]:
            return ERROR_JSON
        return site(url)

    summary = run_ingest(adapter(FakeFetcher(route=route)), session, LocalRawStore(tmp_path))
    assert summary.failed == 0


def test_a_new_format_certificate_sets_both_dates(session, tmp_path):
    from sahighar.adapters.base import RawDoc
    from sahighar.util import utcnow
    run_ingest(adapter(FakeFetcher()), session, LocalRawStore(tmp_path))
    card = session.scalar(select(Project).where(Project.rera_reg_no == "P51800002451"))  # any known project
    doc = RawDoc("maharera-web", "registration_certificate", "u", utcnow(), "text/html", NEW_FORMAT)
    parsed = adapter(FakeFetcher()).parse(doc)
    assert (parsed.projects[0].reg_no, parsed.projects[0].registration_end, parsed.projects[0].extended_end) == (
        "P52100001400", date(2019, 12, 31), date(2027, 12, 31))
    assert card is not None
    assert [(e["label"], e["revised_end"]) for e in parsed.projects[0].extension_history][1] == ("Covid Extension -2", "2021-03-30")


def test_stored_complaint_pages_are_reused_instead_of_fetched_again():
    fetcher = FakeFetcher()
    docs = list(adapter(fetcher, stored=lambda url: complaint_list_html() if "promoter-complaint-report" in url else None).discover())
    assert not any("promoter-complaint-report" in u for u in fetcher.requested)
    assert "complaint_list" not in kinds(docs) and kinds(docs).count("complaints") == 1


def test_the_complaint_index_is_capped_by_max_complaint_pages():
    def route(url):
        if urlparse(url).path == "/promoter-complaint-report":  # says there are 5384 promoters, i.e. 539 pages
            return (FIXTURES / "complaint_list_live.html").read_bytes()
        return site(url)

    fetcher = FakeFetcher(route=route)
    list(adapter(fetcher, max_complaint_pages=3).discover())
    assert sum("promoter-complaint-report" in u for u in fetcher.requested) == 3


def test_a_promoter_list_stored_under_the_old_parameter_name_still_parses():
    from sahighar.adapters.base import RawDoc
    from sahighar.util import utcnow
    old = "https://maharera.maharashtra.gov.in/promoters-search-result?promoter_name=Vascon%20Engineers%20Ltd&page=1&op="
    parsed = adapter(FakeFetcher()).parse(RawDoc("maharera-web", "promoter_list", old, utcnow(), "text/html", LIST_PAGE))
    assert parsed.projects == []  # that page was unfiltered, so none of its cards belong to the asked-for builder


def test_the_complaint_index_counts_as_collected_only_after_a_complete_scan():
    complete = adapter(FakeFetcher())
    list(complete.discover())
    assert complete.complaint_index_complete is True  # the fake index is one page, and it was read

    def live(url):
        return (FIXTURES / "complaint_list_live.html").read_bytes() if urlparse(url).path == "/promoter-complaint-report" else site(url)

    capped = adapter(FakeFetcher(route=live), max_complaint_pages=3)  # the real index has 539 pages
    list(capped.discover())
    assert capped.complaint_index_complete is False

    interrupted = adapter(FakeFetcher(limit=35 - 2))  # budget runs out before the last pages
    with pytest.raises(BudgetExhausted):
        list(interrupted.discover())
    assert interrupted.complaint_index_complete is False


def test_stored_index_pages_count_toward_a_complete_scan():
    reused = adapter(FakeFetcher(), stored=lambda url: complaint_list_html() if "promoter-complaint-report" in url else None)
    list(reused.discover())
    assert reused.complaint_index_complete is True


def test_applications_give_promoters_a_pan_token_members_and_a_business_address(session, tmp_path):
    summary = run_ingest(adapter(FakeFetcher()), session, LocalRawStore(tmp_path))
    assert summary.failed == 0
    promoters = session.scalars(select(Promoter)).all()
    assert {p.pan for p in promoters} == {tokenize("pan", "AAAPA1234A")}
    assert all(p.registered_address.endswith("411014") and len(p.partners_or_directors) == 2 for p in promoters)


def test_the_stored_application_holds_no_personal_identifier(session, tmp_path):
    from sahighar.db.models import SourceDocument
    from tests.application_samples import FORBIDDEN
    store = LocalRawStore(tmp_path)
    run_ingest(adapter(FakeFetcher()), session, store)
    stored = [store.get(d.store_key).decode() for d in session.scalars(select(SourceDocument).where(SourceDocument.kind == "application"))]
    assert len(stored) == 10 and all(len(s) < 5000 for s in stored)  # a small extract, not the 1.6 MB page
    assert not [s for s in stored for word in FORBIDDEN if word in s]


def test_each_builder_gets_one_application_from_its_latest_project():
    fetcher = FakeFetcher()
    list(adapter(fetcher).discover())
    applications = [u for u in fetcher.requested if "DocProjectHSMViewCert" in u]
    assert len(applications) == 10 and len(set(applications)) == 10


def test_an_application_that_cannot_be_read_is_skipped_and_reported_not_fatal():
    def route(url):
        return b"<div>No Record Found</div>" if "DocProjectHSMViewCert" in url else site(url)

    fetcher = FakeFetcher(route=route)
    docs = list(adapter(fetcher).discover())
    assert kinds(docs).count("application") == 0


def _cards(*cert_ids):
    from sahighar.adapters.maharera_pages import ProjectCard
    return [ProjectCard(f"P5{i}", "Proj", "ACME BUILDERS", "Pune", "411001", None, str(i), None) for i in cert_ids]


def test_the_oldest_application_is_tried_first_and_a_masked_pan_moves_on_to_the_next():
    from tests.application_samples import MASKED
    fetched = []

    def route(url):
        fetched.append(url)
        return application_html(MASKED if "id=3&" in url else COMPANY)  # the oldest project's application is masked

    adapter_ = adapter(FakeFetcher(route=route))
    doc = adapter_._application(sorted(_cards(30, 3, 11), key=lambda c: int(c.cert_id)), "n:acme builders", "ACME BUILDERS")
    assert [u.split("id=")[1].split("&")[0] for u in fetched] == ["3", "11"]  # oldest first; stops at the first usable PAN
    assert json.loads(doc.data)["pan"] == tokenize("pan", "AAAPA1234A") and "id=11&" in doc.url


def test_when_every_candidate_is_masked_the_last_readable_extract_is_kept():
    from tests.application_samples import MASKED
    adapter_ = adapter(FakeFetcher(route=lambda url: application_html(MASKED)))
    doc = adapter_._application(_cards(3, 11, 30, 40), "n:acme builders", "ACME BUILDERS")
    assert json.loads(doc.data)["pan"] is None and json.loads(doc.data)["address"]
    assert adapter_.fetcher.requests == 3  # at most three tries per builder


def test_a_builder_with_an_application_already_stored_is_not_fetched_again():
    fetcher = FakeFetcher()
    adapter_ = adapter(fetcher, is_fresh=lambda url: "id=3&" in url)
    assert adapter_._application(_cards(3, 11), "n:acme builders", "ACME BUILDERS") is None
    assert fetcher.requested == []
