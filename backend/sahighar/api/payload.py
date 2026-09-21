from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, GroupMembership, PastProject, Project, ProjectFlag, Promoter, ScoreSnapshot, SourceDocument
from sahighar.scoring.service import distinct_declared, project_facts
from sahighar.scoring.v1 import DAYS_PER_MONTH, classify


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
        facts = project_facts(p)
        outcome, months_extended = classify(facts, scored_on)
        schedule.append({
            "project_id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no,
            "registration_end_date": p.registration_end_date, "extended_end_date": p.extended_end_date,
            "outcome": outcome, "months_extended": months_extended,
            "covid_months": round(facts.covid_days / DAYS_PER_MONTH, 1) or None,  # COVID-19 relief inside the extension
            "source_document_id": p.source_document_id,
        })
    complaints = [
        {"complaint_ref": c.complaint_ref, "project_id": c.project_id, "status": c.status, "stage": c.stage,
         "non_execution_applied": c.non_execution_applied, "filed_year": c.filed_year, "filed_month": c.filed_month,
         "order_url": c.order_url, "source_document_id": c.source_document_id}
        for c in session.scalars(select(Complaint).where(Complaint.promoter_id.in_(confirmed_ids)).order_by(Complaint.id))
    ]
    declared_history = [
        {"name": d.name, "project_type": d.project_type, "original_proposed_date": d.original_proposed_date,
         "actual_completion_date": d.actual_completion_date, "source_document_id": d.source_document_id}
        for d in sorted(distinct_declared(list(session.scalars(select(PastProject).where(PastProject.promoter_id.in_(confirmed_ids))))),
                        key=lambda d: (d.original_proposed_date, d.name))
    ]
    names = {p["rera_reg_no"]: p["name"] for p in schedule}
    # A notice belongs to this group if it names one of its projects, or (the lists carry no promoter id) one of its
    # promoters by name. Projects kept in abeyance can be absent from the site's project search, so the second route
    # is how they are found at all; `in_our_project_list` says which is which.
    refs = [promoters[pid].rera_promoter_ref for pid in confirmed_ids]
    status_notices = [
        {"rera_reg_no": f.rera_reg_no, "project_name": names.get(f.rera_reg_no) or (f.detail or {}).get("project_name") or f.rera_reg_no,
         "kind": f.kind, "detail": f.detail, "in_our_project_list": f.rera_reg_no in names, "source_document_id": f.source_document_id}
        for f in session.scalars(select(ProjectFlag).where(
            ProjectFlag.state == promoter.state, or_(ProjectFlag.rera_reg_no.in_(names), ProjectFlag.promoter_ref.in_(refs)))
            .order_by(ProjectFlag.rera_reg_no, ProjectFlag.kind))
    ]
    listed = dict(session.execute(select(SourceDocument.kind, func.max(SourceDocument.fetched_at)).where(
        SourceDocument.kind.in_(["status_abeyance", "status_nclt"]), SourceDocument.parse_status == "ok").group_by(SourceDocument.kind)).all())
    possibly_related = [
        {"promoter_id": m.promoter_id, "name": promoters[m.promoter_id].name, "evidence": m.evidence,
         "source_document_id": promoters[m.promoter_id].source_document_id}
        for m in memberships if m.link_type == "possible"
    ]
    group_promoters = [
        {"promoter_id": pid, "name": promoters[pid].name, "source_document_id": promoters[pid].source_document_id}
        for pid in confirmed_ids
    ]

    source_ids = {r["source_document_id"] for r in (*schedule, *complaints, *declared_history, *status_notices, *possibly_related, *group_promoters)}
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
        "status_lists_as_of": min(listed.values()) if len(listed) == 2 else None,  # None: the lists were not collected
        "status_notices": status_notices,  # notices the regulator itself publishes about these projects
        "declared_history": declared_history,  # the promoter's own account from its registration applications
        "possibly_related": possibly_related,
        "sources": {str(d.id): {"url": d.url, "origin": d.origin, "fetched_at": d.fetched_at} for d in docs},
    }
