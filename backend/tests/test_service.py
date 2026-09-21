from datetime import date

from sqlalchemy import func, select

from sahighar.db.models import GroupMembership, Promoter, PromoterGroup, ScoreSnapshot
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh
from tests.fakes import FakeAdapter
from sahighar.util import utcnow
from tests.sample_data import DOC_1, DOC_2


def test_refresh_scores_each_group_from_confirmed_members_only(session, tmp_path):
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    assert refresh(session, today=date(2026, 9, 1)) == 3  # {P1,P2}, {P3}, {P4}

    p1 = session.scalar(select(Promoter).where(Promoter.rera_promoter_ref == "P1"))
    group_id = session.scalar(select(GroupMembership.group_id).where(
        GroupMembership.promoter_id == p1.id, GroupMembership.link_type == "filing_confirmed"))
    snapshot = session.scalar(select(ScoreSnapshot).where(ScoreSnapshot.group_id == group_id))
    assert snapshot.breakdown["schedule"]["score"] == 50  # P3's project (a possible link) is not counted
    assert snapshot.breakdown["overall"] == 50
    assert p1.source_document_id in snapshot.input_source_document_ids


def test_refresh_twice_does_not_pile_up_groups_or_snapshots(session, tmp_path):
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    refresh(session, today=date(2026, 9, 1))
    assert session.scalar(select(func.count()).select_from(PromoterGroup)) == 3
    assert session.scalar(select(func.count()).select_from(ScoreSnapshot)) == 3


def _complaints_reason(session, promoter_ref):
    p = session.scalar(select(Promoter).where(Promoter.rera_promoter_ref == promoter_ref))
    group_id = session.scalar(select(GroupMembership.group_id).where(
        GroupMembership.promoter_id == p.id, GroupMembership.link_type == "filing_confirmed"))
    return session.scalar(select(ScoreSnapshot).where(ScoreSnapshot.group_id == group_id)).breakdown["complaints"]


def test_a_builder_with_no_complaint_rows_is_unknown_until_complaints_were_collected(session, tmp_path):
    from sahighar.db.models import Coverage
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    assert _complaints_reason(session, "P4")["reason"] == "not_collected"  # P4 has no complaint rows and nothing says we looked
    assert _complaints_reason(session, "P1")["available"] is True  # P1's complaints were fetched, so they are known

    session.add(Coverage(key="complaints", complete=True, updated_at=utcnow()))
    session.commit()
    refresh(session, today=date(2026, 9, 1))
    p4 = _complaints_reason(session, "P4")
    assert p4["available"] is True and p4["score"] == 100  # now "no complaints" is a real finding


def test_declared_past_projects_are_deduplicated_across_a_groups_applications(session, tmp_path):
    past = lambda ref, name, o, a: {"promoter_ref": ref, "name": name, "original_proposed": o, "actual": a}
    doc = {"past_projects": [
        past("P1", "Willow Court", "2013-11-30", "2015-04-27"), past("P1", "Eco Tower", "2014-08-20", "2014-08-01"),
        past("P2", "Willow Court", "2013-11-30", "2015-04-27"),  # the same project, listed again by the group's other company
        past("P2", "Sky Villas", "2016-01-01", "2016-06-30")]}
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2, "u3": doc}), session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    declared = _group_breakdown(session, "P1")["declared"]
    assert (declared["total"], declared["on_or_before"], declared["later"]) == (3, 1, 2)  # 4 rows, 3 distinct projects


def _group_breakdown(session, promoter_ref):
    p = session.scalar(select(Promoter).where(Promoter.rera_promoter_ref == promoter_ref))
    group_id = session.scalar(select(GroupMembership.group_id).where(
        GroupMembership.promoter_id == p.id, GroupMembership.link_type == "filing_confirmed"))
    return session.scalar(select(ScoreSnapshot).where(ScoreSnapshot.group_id == group_id)).breakdown
