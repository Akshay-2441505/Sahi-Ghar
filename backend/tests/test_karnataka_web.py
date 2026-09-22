from datetime import date
from pathlib import Path

from sqlalchemy import select

from sahighar.adapters.karnataka_web import KarnatakaWebAdapter
from sahighar.adapters.polite import Fetched
from sahighar.db.models import Complaint, PastProject, Project, Promoter
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore

FIXTURES = Path(__file__).parent / "fixtures" / "karnataka"
RENEWALS = (
    "<html><body>"
    + (FIXTURES / "renewals_approved.html").read_text(encoding="utf-8")
    + (FIXTURES / "renewals_rejected.html").read_text(encoding="utf-8")
    + (FIXTURES / "renewals_expired.html").read_text(encoding="utf-8")
    + "</body></html>"
)
COMPLETED = (FIXTURES / "completed.html").read_text(encoding="utf-8")


class FakeFetcher:
    def __init__(self):
        self.requested: list[str] = []

    @property
    def requests(self):
        return len(self.requested)

    def get(self, url):
        self.requested.append(url)
        data = RENEWALS if "Renewal" in url else COMPLETED
        return Fetched(url, data.encode(), "text/html")


def test_discover_fetches_the_two_bulk_pages_once_each():
    fetcher = FakeFetcher()
    docs = list(KarnatakaWebAdapter(fetcher).discover())
    assert [d.kind for d in docs] == ["ka_renewals", "ka_completed"]
    assert fetcher.requests == 2
    assert all(d.origin == "karnataka-web" for d in docs)


def test_full_import_builds_projects_with_schedule_and_declared_dates(session, tmp_path):
    summary = run_ingest(KarnatakaWebAdapter(FakeFetcher()), session, LocalRawStore(tmp_path))
    assert summary.failed == 0

    extended = session.scalar(select(Project).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"))
    assert (extended.registration_end_date, extended.extended_end_date) == (date(2025, 11, 2), date(2026, 11, 2))

    rejected = session.scalar(select(Project).where(Project.rera_reg_no == "PRM/KA/RERA/1251/308/PR/171205/001374"))
    assert (rejected.registration_end_date, rejected.extended_end_date) == (date(2018, 7, 31), None)

    expired_with_extension = session.scalar(select(Project).where(Project.rera_reg_no == "PRM/KA/RERA/1251/310/PR/180120/001486"))
    assert (expired_with_extension.registration_end_date, expired_with_extension.extended_end_date) == (date(2019, 8, 31), date(2026, 5, 30))

    completed = session.scalar(select(Project).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/281223/006513"))
    assert completed.name == "SLN NIDHI PALMS" and completed.city == "Bengaluru Urban"
    assert completed.registration_end_date == date(2030, 12, 31)

    past = session.scalar(select(PastProject).where(PastProject.name == "SLN NIDHI PALMS"))
    assert (past.original_proposed_date, past.actual_completion_date, past.project_type) == (
        date(2030, 12, 31), date(2024, 11, 22), "Plotted Development")

    assert session.scalar(select(Promoter).where(Promoter.name == "SLN INFRA")) is not None
    assert len(session.scalars(select(Promoter)).all()) == 15  # every distinct promoter name across both pages


COMPLAINT_INDEX = (FIXTURES / "complaint_index.html").read_text(encoding="utf-8")
COMPLAINT_DETAILS = {
    "okNvPWxTQ8l5UxjN066RAi61dZ51bfPfpZqiSd7McAInfGDPntG1oBc1ZHGnNelo": (FIXTURES / "complaint_detail_single.html").read_text(encoding="utf-8"),
}


class ComplaintFakeFetcher(FakeFetcher):
    """Serves the complaint index and, for one known token, a detail page; any other token gets the ishtika fixture."""
    def get(self, url):
        self.requested.append(url)
        if "promoterComplaintReport" in url:
            return Fetched(url, COMPLAINT_INDEX.encode(), "text/html")
        if "complaintReportWiseList" in url:
            token = url.split("pName=")[1]
            data = COMPLAINT_DETAILS.get(token, (FIXTURES / "complaint_detail_ishtika.html").read_text(encoding="utf-8"))
            return Fetched(url, data.encode(), "text/html")
        data = RENEWALS if "Renewal" in url else COMPLETED
        return Fetched(url, data.encode(), "text/html")


def test_complaints_are_fetched_index_then_each_promoters_detail_when_enabled():
    fetcher = ComplaintFakeFetcher()
    docs = list(KarnatakaWebAdapter(fetcher, include_complaints=True).discover())
    assert [d.kind for d in docs] == ["ka_renewals", "ka_completed", "ka_complaint_index"] + ["ka_complaint_detail"] * 6
    assert fetcher.requests == 9  # 2 bulk pages + 1 index + 6 promoter detail pages


def test_complaints_are_off_by_default():
    docs = list(KarnatakaWebAdapter(ComplaintFakeFetcher()).discover())
    assert [d.kind for d in docs] == ["ka_renewals", "ka_completed"]


def test_a_capped_run_marks_the_complaint_scan_incomplete_a_full_run_marks_it_complete():
    capped = KarnatakaWebAdapter(ComplaintFakeFetcher(), include_complaints=True, max_complaint_promoters=2)
    list(capped.discover())
    assert capped.complaint_scan_complete is False

    full = KarnatakaWebAdapter(ComplaintFakeFetcher(), include_complaints=True)
    list(full.discover())
    assert full.complaint_scan_complete is True


def test_a_fresh_detail_page_is_not_fetched_again():
    fetcher = ComplaintFakeFetcher()
    fresh_url = "https://rera.karnataka.gov.in/complaintReportWiseList?pName=okNvPWxTQ8l5UxjN066RAi61dZ51bfPfpZqiSd7McAInfGDPntG1oBc1ZHGnNelo"
    docs = list(KarnatakaWebAdapter(fetcher, include_complaints=True, is_fresh=lambda u: u == fresh_url).discover())
    assert "ka_complaint_detail" in [d.kind for d in docs]  # the other 5 are still fetched
    assert not any(d.url == fresh_url for d in docs)
    assert fetcher.requests == 8  # one fewer than the full 9


def test_complaint_detail_introduces_its_own_promoter_and_stores_a_disposed_and_an_open_complaint(session, tmp_path):
    fetcher = ComplaintFakeFetcher()
    summary = run_ingest(KarnatakaWebAdapter(fetcher, include_complaints=True), session, LocalRawStore(tmp_path))
    assert summary.failed == 0
    single_promoter = session.scalar(select(Promoter).where(Promoter.name == "B.G. Ajaya Kumr Late B.G. Jayanna"))
    assert single_promoter is not None  # introduced purely from its complaint, with no schedule data at all
    open_complaint = session.scalar(select(Complaint).where(Complaint.promoter_id == single_promoter.id))
    assert (open_complaint.complaint_ref, open_complaint.stage, open_complaint.order_url) == ("00650/2026", "pending", None)

    ishtika = session.scalar(select(Promoter).where(Promoter.name == "ISHTIKA HOMES PRIVATE LIMITED"))
    disposed = session.scalar(select(Complaint).where(Complaint.promoter_id == ishtika.id, Complaint.complaint_ref == "00978/2023"))
    assert disposed.stage == "order_issued" and disposed.order_url == "https://rera.karnataka.gov.in/download_jc?DOC_ID=D0%2FTqCMP6lSd1eg8DCNsBQ%3D%3D"
    assert disposed.filed_year == 2023 and disposed.filed_month == 6


def test_reparse_rebuilds_the_same_records_with_no_network(session, tmp_path):
    store = LocalRawStore(tmp_path)
    run_ingest(KarnatakaWebAdapter(FakeFetcher()), session, store)
    before = session.scalar(select(Project.registration_end_date).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"))
    from sahighar.ingest.runner import reparse_all
    summary = reparse_all(KarnatakaWebAdapter(FakeFetcher()), session, store)
    assert summary.failed == 0
    after = session.scalar(select(Project.registration_end_date).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"))
    assert before == after
