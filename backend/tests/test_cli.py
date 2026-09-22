from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from sahighar.cli import main
from sahighar.db.models import Base, Project, ScoreSnapshot, SourceDocument
from sahighar.db.session import _sessionmaker
from tests.test_file_import import COMPLAINTS, PROJECTS, PROMOTERS


def setup_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    Base.metadata.create_all(create_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    _sessionmaker.cache_clear()
    return create_engine(url)


def write_tables(folder, **extra):
    for name, text in {"projects.csv": PROJECTS, "promoters.csv": PROMOTERS, "complaints.csv": COMPLAINTS, **extra}.items():
        (folder / name).write_text(text, encoding="utf-8")


def test_import_loads_files_scores_and_reports(monkeypatch, tmp_path, capsys):
    engine = setup_db(monkeypatch, tmp_path)
    data = tmp_path / "reply"
    data.mkdir()
    write_tables(data)
    code = main(["import", str(data), "--obtained-on", "2026-11-05", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "3 files imported" in out and "0 failed" in out and "2 promoter groups scored" in out
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 3
        assert session.scalar(select(func.count()).select_from(ScoreSnapshot)) == 2  # PR1+PR2 share a PAN; PR3 is alone


def test_a_bad_file_is_named_with_its_reason_and_the_rest_still_loads(monkeypatch, tmp_path, capsys):
    engine = setup_db(monkeypatch, tmp_path)
    data = tmp_path / "reply"
    data.mkdir()
    write_tables(data, **{"extra.csv": "Foo,Bar\n1,2\n"})
    code = main(["import", str(data), "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 1 and "1 failed" in out and "extra.csv" in out and "not recognised" in out
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 3


def test_a_missing_folder_is_a_clear_error(monkeypatch, tmp_path, capsys):
    setup_db(monkeypatch, tmp_path)
    assert main(["import", str(tmp_path / "nope")]) == 2
    assert "not a folder" in capsys.readouterr().out


# ---- crawl -------------------------------------------------------------------------------------------------

import pytest

from sahighar.adapters.polite import BlockedError
from tests.test_maharera_web import FakeFetcher


@pytest.fixture
def fake_site(monkeypatch):
    """Replace the real fetcher with the fake site; returns the fetchers created so tests can inspect them."""
    made = []

    def factory(contact, delay, max_requests):
        made.append(FakeFetcher(limit=max_requests))
        made[-1].contact = contact
        return made[-1]

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", factory)
    return made


CRAWL = ["crawl", "--contact", "me@example.test", "--pincode", "411001", "--max-list-pages", "1", "--max-promoter-pages", "1"]


def test_crawl_needs_an_explicit_scope_and_a_contact(monkeypatch, tmp_path, capsys, fake_site):
    setup_db(monkeypatch, tmp_path)
    monkeypatch.delenv("SAHIGHAR_CONTACT", raising=False)
    assert main(["crawl", "--contact", "me@example.test"]) == 2
    assert "--pincode" in capsys.readouterr().out
    assert main(["crawl", "--pincode", "411001"]) == 2
    assert "contact" in capsys.readouterr().out
    assert fake_site == []  # nothing was fetched


def test_a_bounded_crawl_stops_cleanly_and_says_how_to_continue(monkeypatch, tmp_path, capsys, fake_site):
    engine = setup_db(monkeypatch, tmp_path)
    code = main([*CRAWL, "--max-requests", "5", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "request budget" in out and "run the same command again" in out
    assert fake_site[0].contact == "me@example.test"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 10


def test_a_full_small_crawl_then_a_second_run_skips_what_it_already_has(monkeypatch, tmp_path, capsys, fake_site):
    engine = setup_db(monkeypatch, tmp_path)
    assert main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")]) == 0
    assert "37 requests" in capsys.readouterr().out
    assert main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")]) == 0
    assert "2 requests" in capsys.readouterr().out  # only the two notice lists (they change often): list pages, certificates, complaint pages and the index are all reused
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 10


def test_a_block_ends_the_crawl_with_a_clear_message_and_exit_code_3(monkeypatch, tmp_path, capsys):
    engine = setup_db(monkeypatch, tmp_path)
    monkeypatch.setattr("sahighar.cli.PoliteFetcher", lambda contact, delay, max_requests: FakeFetcher(
        fail=lambda url: BlockedError("HTTP 429") if "project-document" in url else None))
    code = main([*CRAWL, "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 3 and "BLOCKED" in out and "do not retry" in out.lower() and "HTTP 429" in out
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 10  # what was fetched before is kept


def test_reparse_rebuilds_records_from_stored_pages_without_any_network(monkeypatch, tmp_path, capsys, fake_site):
    engine = setup_db(monkeypatch, tmp_path)
    assert main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")]) == 0
    with Session(engine) as session:  # simulate a parser bug fixed since: throw the parsed rows away
        session.query(ScoreSnapshot).delete()
        from sahighar.db.models import Complaint, GroupMembership, PromoterGroup
        for model in (GroupMembership, PromoterGroup, Complaint, Project):
            session.query(model).delete()
        session.commit()
    capsys.readouterr()
    code = main(["reparse", "--origin", "maharera-web", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "0 failed" in out and len(fake_site) == 1  # no second fetcher was created: nothing was fetched
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 10


def test_crawl_passes_the_complaint_page_cap_and_reuses_stored_index_pages(monkeypatch, tmp_path, capsys, fake_site):
    setup_db(monkeypatch, tmp_path)
    main([*CRAWL, "--max-requests", "100", "--max-complaint-pages", "1", "--raw-store", str(tmp_path / "raw")])
    assert "37 requests" in capsys.readouterr().out


# ---- complaint coverage ------------------------------------------------------------------------------------

from sahighar.db.models import Coverage


def complaints_collected(engine, state="MH"):
    with Session(engine) as session:
        row = session.get(Coverage, f"complaints:{state}")
        return bool(row and row.complete)


def test_a_full_crawl_marks_complaints_collected(monkeypatch, tmp_path, fake_site):
    engine = setup_db(monkeypatch, tmp_path)
    assert complaints_collected(engine) is False
    main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")])
    assert complaints_collected(engine) is True


def test_a_capped_crawl_does_not(monkeypatch, tmp_path, fake_site):
    engine = setup_db(monkeypatch, tmp_path)

    def live(url):
        from urllib.parse import urlparse
        from tests.test_maharera_web import FIXTURES, site
        return (FIXTURES / "complaint_list_live.html").read_bytes() if urlparse(url).path == "/promoter-complaint-report" else site(url)

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", lambda contact, delay, max_requests: FakeFetcher(route=live, limit=max_requests))
    main([*CRAWL, "--max-requests", "100", "--max-complaint-pages", "2", "--raw-store", str(tmp_path / "raw")])
    assert complaints_collected(engine) is False


def test_an_import_with_a_complaints_table_marks_them_collected_and_one_without_does_not(monkeypatch, tmp_path):
    engine = setup_db(monkeypatch, tmp_path)
    without = tmp_path / "without"
    without.mkdir()
    (without / "projects.csv").write_text(PROJECTS, encoding="utf-8")
    main(["import", str(without), "--raw-store", str(tmp_path / "raw")])
    assert complaints_collected(engine) is False
    full = tmp_path / "full"
    full.mkdir()
    write_tables(full)
    main(["import", str(full), "--raw-store", str(tmp_path / "raw")])
    assert complaints_collected(engine) is True


def test_crawl_and_import_refuse_to_run_without_the_privacy_key(monkeypatch, tmp_path, capsys, fake_site):
    setup_db(monkeypatch, tmp_path)
    monkeypatch.delenv("SAHIGHAR_PII_KEY", raising=False)
    assert main(CRAWL) == 2
    assert "SAHIGHAR_PII_KEY" in capsys.readouterr().out
    assert fake_site == []  # nothing was fetched
    data = tmp_path / "reply"
    data.mkdir()
    write_tables(data)
    assert main(["import", str(data)]) == 2
    assert "SAHIGHAR_PII_KEY" in capsys.readouterr().out


def test_applications_extracted_by_an_older_extractor_are_fetched_again(monkeypatch, tmp_path, capsys, fake_site):
    engine = setup_db(monkeypatch, tmp_path)
    assert main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")]) == 0
    capsys.readouterr()
    with Session(engine) as session:  # pretend those extracts came from an older version of the extractor
        session.query(SourceDocument).filter(SourceDocument.kind == "application").update({"content_type": "application/json; extract=0"})
        session.commit()
    main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")])
    assert "12 requests" in capsys.readouterr().out  # the 10 applications fetched again + the two notice lists, and nothing else


def test_crawl_karnataka_needs_a_contact_and_reports_a_block(monkeypatch, tmp_path, capsys):
    from sahighar.adapters.polite import BlockedError, Fetched

    engine = setup_db(monkeypatch, tmp_path)
    monkeypatch.delenv("SAHIGHAR_CONTACT", raising=False)
    assert main(["crawl-karnataka"]) == 2
    assert "contact" in capsys.readouterr().out

    class BlockedFetcher:
        def __init__(self, contact, delay, max_requests):
            self.requests = 0

        def get(self, url):
            self.requests += 1
            raise BlockedError("HTTP 403")

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", BlockedFetcher)
    code = main(["crawl-karnataka", "--contact", "me@example.test", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 3 and "BLOCKED" in out and "Do not retry" in out


def test_crawl_karnataka_loads_both_pages_and_scores(monkeypatch, tmp_path, capsys):
    from sahighar.adapters.polite import Fetched
    from tests.test_karnataka_web import COMPLETED, RENEWALS

    engine = setup_db(monkeypatch, tmp_path)

    class FakeFetcher:
        def __init__(self, contact, delay, max_requests):
            self.requests = 0
            self.contact = contact

        def get(self, url):
            self.requests += 1
            data = RENEWALS if "Renewal" in url else COMPLETED
            return Fetched(url, data.encode(), "text/html")

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", FakeFetcher)
    code = main(["crawl-karnataka", "--contact", "me@example.test", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "2 requests" in out and "promoter groups scored" in out
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project).where(Project.state == "KA")) > 0


def test_crawl_karnataka_complaints_reads_index_then_every_promoter_and_marks_coverage(monkeypatch, tmp_path, capsys):
    from sahighar.adapters.polite import Fetched
    from tests.test_karnataka_web import COMPLAINT_INDEX, COMPLETED, FIXTURES, RENEWALS

    engine = setup_db(monkeypatch, tmp_path)

    class FakeFetcher:
        def __init__(self, contact, delay, max_requests):
            self.requests = 0
            self.limit = max_requests

        def get(self, url):
            if self.limit is not None and self.requests >= self.limit:
                from sahighar.adapters.polite import BudgetExhausted
                raise BudgetExhausted("limit")
            self.requests += 1
            if "promoterComplaintReport" in url:
                return Fetched(url, COMPLAINT_INDEX.encode(), "text/html")
            if "complaintReportWiseList" in url:
                data = (FIXTURES / "complaint_detail_single.html").read_text(encoding="utf-8")
                return Fetched(url, data.encode(), "text/html")
            data = RENEWALS if "Renewal" in url else COMPLETED
            return Fetched(url, data.encode(), "text/html")

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", FakeFetcher)
    code = main(["crawl-karnataka", "--contact", "me@example.test", "--complaints",
                "--max-requests", "100", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "9 requests" in out  # 2 bulk pages + 1 index + 6 promoter details
    with Session(engine) as session:
        assert session.get(Coverage, "complaints:KA").complete is True
        assert session.scalar(select(func.count()).select_from(Project).where(Project.state == "KA")) > 0


def test_crawl_karnataka_complaints_can_be_capped_and_resumed(monkeypatch, tmp_path, capsys):
    from sahighar.adapters.polite import Fetched
    from tests.test_karnataka_web import COMPLAINT_INDEX, COMPLETED, FIXTURES, RENEWALS

    setup_db(monkeypatch, tmp_path)

    class FakeFetcher:
        def __init__(self, contact, delay, max_requests):
            self.requests = 0
            self.limit = max_requests

        def get(self, url):
            if self.requests >= self.limit:
                from sahighar.adapters.polite import BudgetExhausted
                raise BudgetExhausted("limit")
            self.requests += 1
            if "promoterComplaintReport" in url:
                return Fetched(url, COMPLAINT_INDEX.encode(), "text/html")
            if "complaintReportWiseList" in url:
                data = (FIXTURES / "complaint_detail_single.html").read_text(encoding="utf-8")
                return Fetched(url, data.encode(), "text/html")
            data = RENEWALS if "Renewal" in url else COMPLETED
            return Fetched(url, data.encode(), "text/html")

    monkeypatch.setattr("sahighar.cli.PoliteFetcher", FakeFetcher)
    code = main(["crawl-karnataka", "--contact", "me@example.test", "--complaints",
                "--max-requests", "5", "--raw-store", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert code == 0 and "request budget" in out and "run the same command again" in out
