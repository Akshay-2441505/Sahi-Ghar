import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, Coverage, GroupMembership, PastProject, Project, Promoter, ScoreSnapshot
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
    members: dict[int, list[int]] = defaultdict(list)
    for m in session.scalars(select(GroupMembership).where(GroupMembership.link_type == "filing_confirmed")):
        members[m.group_id].append(m.promoter_id)

    complaints_collected = bool(session.scalar(select(Coverage.complete).where(Coverage.key == "complaints")))
    now = utcnow()
    for group_id, promoter_ids in members.items():
        ps = [p for pid in promoter_ids for p in projects[pid]]
        cs = [c for pid in promoter_ids for c in complaints[pid]]
        ds = distinct_declared([d for pid in promoter_ids for d in declared[pid]])
        breakdown = score(
            [project_facts(p) for p in ps],
            [ComplaintFacts(c.stage, c.non_execution_applied) for c in cs], today,
            complaints_known=complaints_collected or bool(cs),  # complaint rows exist only if that builder's page was fetched
            declared=[DeclaredFacts(d.original_proposed_date, d.actual_completion_date) for d in ds],
        )
        sources = {promoter_doc[pid] for pid in promoter_ids} | {r.source_document_id for r in (*ps, *cs, *ds)}
        session.add(ScoreSnapshot(group_id=group_id, computed_at=now, breakdown=breakdown,
                                  input_source_document_ids=sorted(sources)))
    session.commit()
    return len(members)


def refresh(session: Session, today: date | None = None) -> int:
    """Rebuild promoter groups, then score every group. Run after each ingest."""
    rebuild_groups(session)
    return compute_scores(session, today or date.today())
