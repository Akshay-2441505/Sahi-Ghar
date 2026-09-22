from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sahighar.api.payload import trust_payload
from sahighar.db.models import Project, Promoter
from sahighar.db.session import get_session

app = FastAPI(title="Sahi Ghar")


@app.get("/search")
def search(q: str = Query(min_length=2), session: Session = Depends(get_session)):
    """Projects whose name, promoter name or RERA registration number contains the query."""
    needle = q.lower()
    rows = session.execute(
        select(Project, Promoter.name).join(Promoter, Project.promoter_id == Promoter.id)
        .where(or_(func.lower(Project.name).contains(needle, autoescape=True),
                   func.lower(Project.rera_reg_no).contains(needle, autoescape=True),
                   func.lower(Promoter.name).contains(needle, autoescape=True)))
        .order_by(Project.name).limit(25)
    ).all()
    return {"projects": [{"id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no, "city": p.city,
                          "promoter_id": p.promoter_id, "promoter_name": name}
                         for p, name in rows]}


@app.get("/projects/{project_id}")
def project(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    promoter = session.get(Promoter, p.promoter_id)
    return {
        "project": {"id": p.id, "state": p.state, "name": p.name, "rera_reg_no": p.rera_reg_no, "city": p.city, "locality": p.locality,
                    "configurations": p.configurations, "carpet_area_range": p.carpet_area_range,
                    "registration_end_date": p.registration_end_date, "extended_end_date": p.extended_end_date,
                    "promoter_id": promoter.id, "promoter_name": promoter.name,
                    "source_document_id": p.source_document_id},
        **trust_payload(session, promoter),
    }


@app.get("/promoters/{promoter_id}")
def promoter(promoter_id: int, session: Session = Depends(get_session)):
    p = session.get(Promoter, promoter_id)
    if p is None:
        raise HTTPException(404, "promoter not found")
    return {"promoter": {"id": p.id, "name": p.name, "rera_promoter_ref": p.rera_promoter_ref}, **trust_payload(session, p)}
