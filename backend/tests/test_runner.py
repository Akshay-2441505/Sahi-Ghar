import pytest
from sqlalchemy import delete, select

from sahighar.db.models import Complaint, Project, Promoter, SourceDocument
from sahighar.ingest.runner import IngestFailureRateExceeded, reparse_all, run_ingest
from sahighar.rawstore import LocalRawStore
from tests.fakes import FakeAdapter

GOOD = {
    "promoters": [{"ref": "P1", "name": "Shree Realty LLP"}],
    "projects": [{"reg_no": "R1", "promoter_ref": "P1", "name": "Heights", "registration_end": "2022-01-01"}],
    "complaints": [{"ref": "C1", "promoter_ref": "P1", "status": "Hearing Scheduled", "project_reg_no": "R1"}],
}
ORPHAN = {"projects": [{"reg_no": "R9", "promoter_ref": "NOPE", "name": "Ghost"}]}


def test_ingest_stores_raw_and_tags_every_row_with_its_source(session, tmp_path):
    store = LocalRawStore(tmp_path)
    summary = run_ingest(FakeAdapter({"u1": GOOD}), session, store)
    assert (summary.total, summary.ok, summary.failed) == (1, 1, 0)
    sd = session.scalar(select(SourceDocument))
    assert sd.parse_status == "ok" and store.get(sd.store_key)
    for model in (Promoter, Project, Complaint):
        assert session.scalar(select(model)).source_document_id == sd.id
    assert session.scalar(select(Complaint)).project_id == session.scalar(select(Project.id))


def test_ingest_is_idempotent(session, tmp_path):
    store = LocalRawStore(tmp_path)
    for _ in range(2):
        run_ingest(FakeAdapter({"u1": GOOD}), session, store)
    assert len(session.scalars(select(SourceDocument)).all()) == 1
    assert len(session.scalars(select(Project)).all()) == 1


def test_one_bad_document_does_not_stop_the_run(session, tmp_path):
    adapter = FakeAdapter({"u1": GOOD, "u2": ORPHAN})
    summary = run_ingest(adapter, session, LocalRawStore(tmp_path), max_failure_rate=1.0)
    assert (summary.ok, summary.failed) == (1, 1)
    bad = session.scalar(select(SourceDocument).where(SourceDocument.url == "u2"))
    assert bad.parse_status == "failed" and "unknown promoter" in bad.parse_error
    assert session.scalar(select(Project.rera_reg_no)) == "R1"


def test_failure_rate_over_threshold_raises(session, tmp_path):
    with pytest.raises(IngestFailureRateExceeded):
        run_ingest(FakeAdapter({"u1": GOOD, "u2": ORPHAN}), session, LocalRawStore(tmp_path))


def test_reparse_rebuilds_records_from_stored_raw_without_network(session, tmp_path):
    store = LocalRawStore(tmp_path)
    adapter = FakeAdapter({"u1": GOOD})
    run_ingest(adapter, session, store)
    for model in (Complaint, Project, Promoter):
        session.execute(delete(model))
    session.commit()
    adapter.payloads = {}  # nothing to discover: parsing must use the stored bytes
    summary = reparse_all(adapter, session, store)
    assert summary.ok == 1
    assert session.scalar(select(Project.rera_reg_no)) == "R1"
