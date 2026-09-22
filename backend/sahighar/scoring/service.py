import re
from collections import defaultdict
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, Coverage, GroupMembership, PastProject, Project, ProjectFlag, Promoter, ScoreSnapshot
from sahighar.resolve.grouping import rebuild_groups
from sahighar.scoring.v1 import ComplaintFacts, DeclaredFacts, ProjectFacts, covid_days, score
from sahighar.util import utcnow


def project_facts(p: Project) -> ProjectFacts:
    return ProjectFacts(p.registration_end_date, p.extended_end_date, covid_days(p.extension_history, p.registration_end_date))


def distinct_declared(rows: list[PastProject]) -> list[PastProject]:
    """A group's companies (and each of their applications) can list the same completed project again: count it once."""
    seen: dict[tuple, PastProject] = {}
    for d in sorted(rows, key=lambda r: r.id):
        key = (re.sub(r"[^a-z0-9]+", " ", d.name.lower()).strip(), d.original_proposed_date, d.actual_completion_date)
        seen.setdefault(key, d)
    return list(seen.values())


def group_notices(session: Session, state: str, refs: list[str], reg_nos: list[str]) -> list[ProjectFlag]:
    """Regulator notices about a group: those naming one of its projects, or (the lists carry no promoter id) one of
    its promoters by name. Also used by the trust page, so the score and the page can never disagree."""
    return list(session.scalars(select(ProjectFlag).where(
        ProjectFlag.state == state, or_(ProjectFlag.rera_reg_no.in_(reg_nos), ProjectFlag.promoter_ref.in_(refs)))
        .order_by(ProjectFlag.rera_reg_no, ProjectFlag.kind)))


def compute_scores(session: Session, today: date) -> int:
    """One ScoreSnapshot per group, from the group's filing_confirmed promoters only."""
    projects: dict[int, list[Project]] = defaultdict(list)
    for p in session.scalars(select(Project)):
        projects[p.promoter_id].append(p)
    complaints: dict[int, list[Complaint]] = defaultdict(list)
    for c in session.scalars(select(Complaint)):
        complaints[c.promoter_id].append(c)
    declared: dict[int, list[PastProject]] = defaultdict(list)
    for d in session.scalars(select(PastProject)):
        declared[d.promoter_id].append(d)
    promoter_doc = dict(session.execute(select(Promoter.id, Promoter.source_document_id)).all())
    promoter_key = {pid: (state, ref) for pid, state, ref in session.execute(select(Promoter.id, Promoter.state, Promoter.rera_promoter_ref))}
    members: dict[int, list[int]] = defaultdict(list)
    for m in session.scalars(select(GroupMembership).where(GroupMembership.link_type == "filing_confirmed")):
        members[m.group_id].append(m.promoter_id)

    # Coverage is per state ("complaints:MH", "complaints:KA", ...): a full scan in one state must never make
    # another state's missing complaint data look like a clean record.
    coverage_by_state = {key.removeprefix("complaints:"): complete for key, complete in session.execute(
        select(Coverage.key, Coverage.complete)).all() if key.startswith("complaints:")}
    now = utcnow()
    for group_id, promoter_ids in members.items():
        ps = [p for pid in promoter_ids for p in projects[pid]]
        cs = [c for pid in promoter_ids for c in complaints[pid]]
        ds = distinct_declared([d for pid in promoter_ids for d in declared[pid]])
        group_state = promoter_key[promoter_ids[0]][0]
        notices = group_notices(session, group_state, [promoter_key[pid][1] for pid in promoter_ids], [p.rera_reg_no for p in ps])
        breakdown = score(
            [project_facts(p) for p in ps],
            [ComplaintFacts(c.stage, c.non_execution_applied) for c in cs], today,
            complaints_known=coverage_by_state.get(group_state, False) or bool(cs),  # or complaint rows exist for this builder
            declared=[DeclaredFacts(d.original_proposed_date, d.actual_completion_date) for d in ds], notices=len(notices),
        )
        sources = {promoter_doc[pid] for pid in promoter_ids} | {r.source_document_id for r in (*ps, *cs, *ds, *notices)}
        session.add(ScoreSnapshot(group_id=group_id, computed_at=now, breakdown=breakdown,
                                  input_source_document_ids=sorted(sources)))
    session.commit()
    return len(members)


def refresh(session: Session, today: date | None = None) -> int:
    """Rebuild promoter groups, then score every group. Run after each ingest."""
    rebuild_groups(session)
    return compute_scores(session, today or date.today())
