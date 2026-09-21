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


def test_a_later_document_without_a_value_does_not_erase_an_earlier_one(session, tmp_path):
    store = LocalRawStore(tmp_path)
    rich = {"promoters": [{"ref": "P1", "name": "Shree Realty LLP", "pan": "AAAPA0001A", "registered_address": "12 MG Road"}]}
    thin = {"promoters": [{"ref": "P1", "name": "Shree Realty LLP"}]}
    run_ingest(FakeAdapter({"u1": rich}), session, store)
    run_ingest(FakeAdapter({"u2": thin}), session, store)
    promoter = session.scalar(select(Promoter))
    assert promoter.pan == "AAAPA0001A" and promoter.registered_address == "12 MG Road"


def test_complaint_without_a_promoter_ref_uses_its_projects_promoter(session, tmp_path):
    doc = {
        "promoters": [{"ref": "P1", "name": "Shree Realty LLP"}],
        "projects": [{"reg_no": "R1", "promoter_ref": "P1", "name": "Heights"}],
        "complaints": [{"ref": "C1", "promoter_ref": None, "status": "Order Approved", "project_reg_no": "R1"}],
    }
    run_ingest(FakeAdapter({"u1": doc}), session, LocalRawStore(tmp_path))
    assert session.scalar(select(Complaint.promoter_id)) == session.scalar(select(Promoter.id))


def test_complaint_with_no_promoter_and_no_known_project_fails_its_document(session, tmp_path):
    doc = {"complaints": [{"ref": "C1", "promoter_ref": None, "status": "Order Approved", "project_reg_no": "NOPE"}]}
    summary = run_ingest(FakeAdapter({"u1": doc}), session, LocalRawStore(tmp_path), max_failure_rate=1.0)
    assert summary.failed == 1
    assert "no promoter ref" in session.scalar(select(SourceDocument.parse_error))


def test_a_thin_project_update_adds_dates_and_keeps_the_name_and_promoter(session, tmp_path):
    from datetime import date
    store = LocalRawStore(tmp_path)
    intro = {"promoters": [{"ref": "P1", "name": "Shree Realty LLP"}],
             "projects": [{"reg_no": "R1", "promoter_ref": "P1", "name": "Heights", "registration_end": "2022-01-01"}]}
    thin = {"projects": [{"reg_no": "R1", "promoter_ref": None, "name": None, "extended_end": "2023-01-01"}]}
    run_ingest(FakeAdapter({"u1": intro}), session, store)
    run_ingest(FakeAdapter({"u2": thin}), session, store)
    project = session.scalar(select(Project))
    assert (project.name, project.registration_end_date, project.extended_end_date) == ("Heights", date(2022, 1, 1), date(2023, 1, 1))
    assert project.promoter_id == session.scalar(select(Promoter.id))


def test_a_thin_project_update_for_an_unknown_project_fails_its_document(session, tmp_path):
    thin = {"projects": [{"reg_no": "R9", "promoter_ref": None, "name": None, "registration_end": "2022-01-01"}]}
    summary = run_ingest(FakeAdapter({"u1": thin}), session, LocalRawStore(tmp_path), max_failure_rate=1.0)
    assert summary.failed == 1
    assert "not introduced" in session.scalar(select(SourceDocument.parse_error))


def test_declared_past_projects_are_stored_once_however_many_applications_repeat_them(session, tmp_path):
    from datetime import date
    from sahighar.db.models import PastProject
    row = {"promoter_ref": "P1", "name": "Willow Court", "project_type": "Residential",
           "original_proposed": "2013-11-30", "actual": "2015-04-27"}
    first = {"promoters": [{"ref": "P1", "name": "Shree Realty LLP"}], "past_projects": [row]}
    second = {"past_projects": [row, {**row, "name": "Eco Tower", "original_proposed": "2014-08-20", "actual": "2016-11-29"}]}
    store = LocalRawStore(tmp_path)
    run_ingest(FakeAdapter({"u1": first, "u2": second}), session, store)
    rows = session.scalars(select(PastProject).order_by(PastProject.name)).all()
    assert [(r.name, r.original_proposed_date, r.actual_completion_date) for r in rows] == [
        ("Eco Tower", date(2014, 8, 20), date(2016, 11, 29)), ("Willow Court", date(2013, 11, 30), date(2015, 4, 27))]
    assert all(r.promoter_id and r.source_document_id for r in rows)
