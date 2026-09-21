from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, GroupMembership, Project, Promoter, ScoreSnapshot, SourceDocument
from sahighar.scoring.v1 import ProjectFacts, classify


def trust_payload(session: Session, promoter: Promoter) -> dict:
    """Everything the trust page shows for a promoter's filing-confirmed group.

    Every record carries `source_document_id`, resolvable in `sources`.
    """
    own = session.scalar(
        select(GroupMembership).where(
            GroupMembership.promoter_id == promoter.id, GroupMembership.link_type == "filing_confirmed"
        )
    )
    memberships = session.scalars(select(GroupMembership).where(GroupMembership.group_id == own.group_id)).all()
    confirmed_ids = [m.promoter_id for m in memberships if m.link_type == "filing_confirmed"]
    promoters = {p.id: p for p in session.scalars(select(Promoter).where(Promoter.id.in_(
        [m.promoter_id for m in memberships])))}

    snapshot = session.scalar(
        select(ScoreSnapshot).where(ScoreSnapshot.group_id == own.group_id)
        .order_by(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc())
    )
    scored_on = snapshot.computed_at.date() if snapshot else date.today()

    schedule = []
    for p in session.scalars(select(Project).where(Project.promoter_id.in_(confirmed_ids)).order_by(Project.id)):
        outcome, months_extended = classify(ProjectFacts(p.registration_end_date, p.extended_end_date), scored_on)
        schedule.append({
            "project_id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no,
            "registration_end_date": p.registration_end_date, "extended_end_date": p.extended_end_date,
            "outcome": outcome, "months_extended": months_extended, "source_document_id": p.source_document_id,
        })
    complaints = [
        {"complaint_ref": c.complaint_ref, "project_id": c.project_id, "status": c.status, "stage": c.stage,
         "non_execution_applied": c.non_execution_applied, "filed_year": c.filed_year, "filed_month": c.filed_month,
         "order_url": c.order_url, "source_document_id": c.source_document_id}
        for c in session.scalars(select(Complaint).where(Complaint.promoter_id.in_(confirmed_ids)).order_by(Complaint.id))
    ]
    possibly_related = [
        {"promoter_id": m.promoter_id, "name": promoters[m.promoter_id].name, "evidence": m.evidence,
         "source_document_id": promoters[m.promoter_id].source_document_id}
        for m in memberships if m.link_type == "possible"
    ]
    group_promoters = [
        {"promoter_id": pid, "name": promoters[pid].name, "source_document_id": promoters[pid].source_document_id}
        for pid in confirmed_ids
    ]

    source_ids = {r["source_document_id"] for r in (*schedule, *complaints, *possibly_related, *group_promoters)}
    docs = session.scalars(select(SourceDocument).where(SourceDocument.id.in_(source_ids))).all()
    return {
        "data_as_of": max((d.fetched_at for d in docs), default=None),
        "score_computed_at": snapshot.computed_at if snapshot else None,
        "score": snapshot.breakdown if snapshot else None,
        "group_promoters": group_promoters,
        # why several promoters are one group; the evidence records only the kind of match, never the identifier
        "group_basis": "same PAN" if len(confirmed_ids) > 1 else None,
        "schedule": schedule,
        "complaints": complaints,
        "possibly_related": possibly_related,
        "sources": {str(d.id): {"url": d.url, "origin": d.origin, "fetched_at": d.fetched_at} for d in docs},
    }
