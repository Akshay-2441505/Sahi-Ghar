import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.adapters.base import Adapter, ParsedRecords, RawDoc
from sahighar.db.models import Complaint, Project, Promoter, SourceDocument
from sahighar.rawstore import RawStore


@dataclass
class IngestSummary:
    total: int = 0
    ok: int = 0
    failed: int = 0


class IngestFailureRateExceeded(Exception):
    def __init__(self, summary: IngestSummary):
        super().__init__(f"{summary.failed} of {summary.total} documents failed to parse")
        self.summary = summary


def _upsert(session: Session, model, keys: dict, values: dict, keep_existing_if_none: bool = False):
    row = session.scalar(select(model).filter_by(**keys))
    if row is None:
        row = model(**keys)
        session.add(row)
    for name, value in values.items():
        if value is None and keep_existing_if_none:
            continue
        setattr(row, name, value)
    return row


def _promoter_id(session: Session, state: str, ref: str) -> int:
    pid = session.scalar(select(Promoter.id).where(Promoter.state == state, Promoter.rera_promoter_ref == ref))
    if pid is None:
        raise ValueError(f"unknown promoter ref {ref!r} (adapter must introduce promoters first)")
    return pid


def _apply(session: Session, state: str, sd_id: int, parsed: ParsedRecords) -> None:
    for p in parsed.promoters:
        _upsert(
            session, Promoter, {"state": state, "rera_promoter_ref": p.ref},
            {"name": p.name, "pan": p.pan, "registered_address": p.registered_address,
             "partners_or_directors": p.partners_or_directors, "source_document_id": sd_id},
            keep_existing_if_none=True,  # a thinner later document (e.g. a project list) must not erase PAN or address
        )
    for j in parsed.projects:
        _upsert(
            session, Project, {"state": state, "rera_reg_no": j.reg_no},
            {"promoter_id": _promoter_id(session, state, j.promoter_ref), "name": j.name,
             "city": j.city, "locality": j.locality, "configurations": j.configurations,
             "carpet_area_range": j.carpet_area_range, "registration_end_date": j.registration_end,
             "extended_end_date": j.extended_end, "source_document_id": sd_id},
        )
    for c in parsed.complaints:
        project = None
        if c.project_reg_no:
            project = session.scalar(
                select(Project).where(Project.state == state, Project.rera_reg_no == c.project_reg_no)
            )
        if c.promoter_ref:
            promoter_id = _promoter_id(session, state, c.promoter_ref)
        elif project is not None:  # the public complaint table gives a project number, not a promoter ID
            promoter_id = project.promoter_id
        else:
            raise ValueError(f"complaint {c.ref!r} has no promoter ref and no known project registration number")
        _upsert(
            session, Complaint, {"promoter_id": promoter_id, "complaint_ref": c.ref},
            {"project_id": project.id if project else None, "status": c.status, "stage": c.stage,
             "non_execution_applied": c.non_execution_applied, "filed_year": c.filed_year,
             "filed_month": c.filed_month, "order_url": c.order_url, "source_document_id": sd_id},
        )


def _process(session: Session, adapter: Adapter, sd_id: int, doc: RawDoc) -> bool:
    """Parse one stored document. A failure marks that document failed and never stops the run."""
    try:
        _apply(session, adapter.state, sd_id, adapter.parse(doc))
        sd = session.get(SourceDocument, sd_id)
        sd.parse_status, sd.parse_error = "ok", None
        session.commit()
        return True
    except Exception as exc:  # deliberate: per-document failure isolation
        session.rollback()
        sd = session.get(SourceDocument, sd_id)
        sd.parse_status, sd.parse_error = "failed", f"{type(exc).__name__}: {exc}"[:1000]
        session.commit()
        return False


def _record_doc(session: Session, doc: RawDoc, store: RawStore) -> tuple[int, bool]:
    """Store the raw bytes and upsert the source_document row. Returns (id, already_parsed_ok)."""
    sha = hashlib.sha256(doc.data).hexdigest()
    sd = session.scalar(select(SourceDocument).where(SourceDocument.url == doc.url, SourceDocument.sha256 == sha))
    if sd is None:
        sd = SourceDocument(
            origin=doc.origin, kind=doc.kind, url=doc.url, sha256=sha,
            content_type=doc.content_type, store_key=store.put(doc.data), fetched_at=doc.fetched_at,
        )
        session.add(sd)
    else:
        sd.fetched_at = doc.fetched_at  # re-fetched unchanged content: freshness moves, data does not
    session.commit()
    return sd.id, sd.parse_status == "ok"


def _check(summary: IngestSummary, max_failure_rate: float) -> IngestSummary:
    if summary.total and summary.failed / summary.total > max_failure_rate:
        raise IngestFailureRateExceeded(summary)
    return summary


def run_ingest(adapter: Adapter, session: Session, store: RawStore, max_failure_rate: float = 0.05) -> IngestSummary:
    summary = IngestSummary()
    for doc in adapter.discover():
        summary.total += 1
        sd_id, parsed_ok = _record_doc(session, doc, store)
        if parsed_ok or _process(session, adapter, sd_id, doc):
            summary.ok += 1
        else:
            summary.failed += 1
    return _check(summary, max_failure_rate)


def reparse_all(adapter: Adapter, session: Session, store: RawStore, max_failure_rate: float = 0.05) -> IngestSummary:
    """Re-run the parser over stored raw documents (after a parser fix). No network."""
    summary = IngestSummary()
    rows = session.scalars(
        select(SourceDocument).where(SourceDocument.origin == adapter.origin).order_by(SourceDocument.id)
    ).all()
    for sd in rows:
        doc = RawDoc(sd.origin, sd.kind, sd.url, sd.fetched_at, sd.content_type, store.get(sd.store_key))
        summary.total += 1
        if _process(session, adapter, sd.id, doc):
            summary.ok += 1
        else:
            summary.failed += 1
    return _check(summary, max_failure_rate)
