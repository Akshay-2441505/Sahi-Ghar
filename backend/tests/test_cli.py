from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from sahighar.cli import main
from sahighar.db.models import Base, Project, ScoreSnapshot
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
    assert "25 requests" in capsys.readouterr().out
    assert main([*CRAWL, "--max-requests", "100", "--raw-store", str(tmp_path / "raw")]) == 0
    assert "11 requests" in capsys.readouterr().out  # certificates, complaint pages and the complaint index are all reused
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
    assert "25 requests" in capsys.readouterr().out


# ---- complaint coverage ------------------------------------------------------------------------------------

from sahighar.db.models import Coverage


def complaints_collected(engine):
    with Session(engine) as session:
        row = session.get(Coverage, "complaints")
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
