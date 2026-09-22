from datetime import date
from pathlib import Path

from sqlalchemy import select

from sahighar.adapters.karnataka_web import KarnatakaWebAdapter
from sahighar.adapters.polite import Fetched
from sahighar.db.models import PastProject, Project, Promoter
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


def test_reparse_rebuilds_the_same_records_with_no_network(session, tmp_path):
    store = LocalRawStore(tmp_path)
    run_ingest(KarnatakaWebAdapter(FakeFetcher()), session, store)
    before = session.scalar(select(Project.registration_end_date).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"))
    from sahighar.ingest.runner import reparse_all
    summary = reparse_all(KarnatakaWebAdapter(FakeFetcher()), session, store)
    assert summary.failed == 0
    after = session.scalar(select(Project.registration_end_date).where(Project.rera_reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"))
    assert before == after
