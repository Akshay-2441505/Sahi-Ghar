import pytest
from sqlalchemy.exc import IntegrityError

from sahighar.db.models import Project, Promoter, SourceDocument
from sahighar.util import utcnow


def _doc(session):
    sd = SourceDocument(origin="t", kind="project", url="u", fetched_at=utcnow(), sha256="a" * 64,
                        content_type="text/html", store_key="a" * 64)
    session.add(sd)
    session.flush()
    return sd


def test_natural_keys_are_unique(session):
    sd = _doc(session)
    pr = Promoter(state="MH", rera_promoter_ref="P1", name="X", source_document_id=sd.id)
    session.add(pr)
    session.flush()
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="A", source_document_id=sd.id))
    session.flush()
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="B", source_document_id=sd.id))
    with pytest.raises(IntegrityError):
        session.flush()
