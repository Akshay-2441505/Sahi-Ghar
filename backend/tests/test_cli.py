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
