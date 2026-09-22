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

    session.add(Coverage(key="complaints:MH", complete=True, updated_at=utcnow()))
    session.commit()
    refresh(session, today=date(2026, 9, 1))
    p4 = _complaints_reason(session, "P4")
    assert p4["available"] is True and p4["score"] == 100  # now "no complaints" is a real finding


def test_complaint_coverage_is_scoped_per_state_never_leaks_across_states(session, tmp_path):
    """MH's complaint index being fully scanned must never make a KA builder's complaints look known."""
    from sahighar.adapters.base import RawDoc
    from sahighar.db.models import Coverage
    run_ingest(FakeAdapter({"u1": DOC_1}), session, LocalRawStore(tmp_path))  # FakeAdapter.state == "MH"

    class KaFakeAdapter(FakeAdapter):
        state = "KA"

    run_ingest(KaFakeAdapter({"u2": {"promoters": [{"ref": "K1", "name": "Karnataka Co"}],
                                     "projects": [{"reg_no": "KA-1", "promoter_ref": "K1", "name": "KA One"}]}}),
               session, LocalRawStore(tmp_path))
    session.add(Coverage(key="complaints:MH", complete=True, updated_at=utcnow()))
    session.commit()
    refresh(session, today=date(2026, 9, 1))
    assert _complaints_reason(session, "K1")["reason"] == "not_collected"  # MH's coverage must not leak to KA
    assert _complaints_reason(session, "P1")["available"] is True  # MH's own coverage still applies to MH


def test_a_pan_merged_group_spanning_two_states_needs_both_states_complaints_collected(session, tmp_path):
    """Same PAN across states is one legal entity and is meant to merge (see test_grouping.py) -- but the merged
    group's complaints can only be called known once EVERY state it spans has been collected, not just one."""
    from sahighar.db.models import Coverage

    class KaFakeAdapter(FakeAdapter):
        state = "KA"

    same_pan = {"promoters": [{"ref": "MH1", "name": "National Co MH", "pan": "SAMEPAN0001"}],
                "projects": [{"reg_no": "MHX-1", "promoter_ref": "MH1", "name": "MH Project", "registration_end": "2022-01-01"}]}
    same_pan_ka = {"promoters": [{"ref": "KA1", "name": "National Co KA", "pan": "SAMEPAN0001"}],
                   "projects": [{"reg_no": "KAX-1", "promoter_ref": "KA1", "name": "KA Project", "registration_end": "2022-01-01"}]}
    run_ingest(FakeAdapter({"u1": same_pan}), session, LocalRawStore(tmp_path))
    run_ingest(KaFakeAdapter({"u2": same_pan_ka}), session, LocalRawStore(tmp_path))
    session.add(Coverage(key="complaints:MH", complete=True, updated_at=utcnow()))  # only MH's side was collected
    session.commit()
    refresh(session, today=date(2026, 9, 1))
    reason = _complaints_reason(session, "MH1")
    assert _complaints_reason(session, "KA1") == reason  # same group, same snapshot
    assert reason["reason"] == "not_collected"  # KA's side of this merged entity is still unknown


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


def test_a_notice_naming_the_builder_withholds_the_groups_overall_score(session, tmp_path):
    store = LocalRawStore(tmp_path)
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, store)
    refresh(session, today=date(2026, 9, 1))
    assert _group_breakdown(session, "P1")["overall"] == 50 and _group_breakdown(session, "P1")["notices"] == {"count": 0}
    notice = {"project_flags": [{"reg_no": "MH-800", "kind": "abeyance", "promoter_ref": "P2"},  # named by builder only
                                {"reg_no": "MH-1", "kind": "nclt"}]}  # named by project number only
    run_ingest(FakeAdapter({"n1": notice}), session, store)
    refresh(session, today=date(2026, 9, 1))
    p1 = _group_breakdown(session, "P1")
    assert p1["notices"] == {"count": 2} and p1["overall"] is None and p1["schedule"]["score"] == 50
    assert _group_breakdown(session, "P4")["notices"] == {"count": 0}


def _group_breakdown(session, promoter_ref):
    p = session.scalar(select(Promoter).where(Promoter.rera_promoter_ref == promoter_ref))
    group_id = session.scalar(select(GroupMembership.group_id).where(
        GroupMembership.promoter_id == p.id, GroupMembership.link_type == "filing_confirmed"))
    return session.scalar(select(ScoreSnapshot).where(ScoreSnapshot.group_id == group_id)).breakdown
