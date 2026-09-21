from datetime import date, datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (UniqueConstraint("url", "sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str]  # adapter origin label, e.g. "maharera-web", "file-import"
    kind: Mapped[str]  # "project" | "promoter" | "complaints"
    url: Mapped[str]  # for file imports use a "file:<name>" label
    fetched_at: Mapped[datetime]
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str]
    store_key: Mapped[str]
    parse_status: Mapped[str] = mapped_column(default="pending")  # pending | ok | failed
    parse_error: Mapped[str | None]


class Promoter(Base):
    __tablename__ = "promoter"
    __table_args__ = (UniqueConstraint("state", "rera_promoter_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2))  # MH | KA | TG
    rera_promoter_ref: Mapped[str]
    name: Mapped[str]
    pan: Mapped[str | None]
    registered_address: Mapped[str | None]
    partners_or_directors: Mapped[list | None] = mapped_column(Json)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class PromoterGroup(Base):
    __tablename__ = "promoter_group"

    id: Mapped[int] = mapped_column(primary_key=True)


class GroupMembership(Base):
    __tablename__ = "group_membership"

    group_id: Mapped[int] = mapped_column(ForeignKey("promoter_group.id"), primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"), primary_key=True)
    link_type: Mapped[str]  # filing_confirmed | possible
    evidence: Mapped[dict] = mapped_column(Json)


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("state", "rera_reg_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2))
    rera_reg_no: Mapped[str]
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    name: Mapped[str]
    city: Mapped[str | None]
    locality: Mapped[str | None]
    configurations: Mapped[list | None] = mapped_column(Json)
    carpet_area_range: Mapped[str | None]
    registration_end_date: Mapped[date | None]  # end of the original registration validity
    extended_end_date: Mapped[date | None]  # only when an extension certificate exists
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class PastProject(Base):
    """A completed project the promoter declared in its registration application: the promoter's own account of
    proposed versus actual completion. Not verified by this system."""
    __tablename__ = "past_project"
    __table_args__ = (UniqueConstraint("promoter_id", "name", "original_proposed_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    name: Mapped[str]
    project_type: Mapped[str | None]
    original_proposed_date: Mapped[date]
    actual_completion_date: Mapped[date]
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class Complaint(Base):
    __tablename__ = "complaint"
    __table_args__ = (UniqueConstraint("promoter_id", "complaint_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"))
    complaint_ref: Mapped[str]
    status: Mapped[str]  # raw text as published
    stage: Mapped[str]  # order_issued | pending | other
    non_execution_applied: Mapped[bool] = mapped_column(default=False)
    filed_year: Mapped[int | None]
    filed_month: Mapped[int | None]
    order_url: Mapped[str | None]
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class Coverage(Base):
    """Whether a kind of data was actually collected, so that "none found" is never confused with "not looked".

    key "complaints": complete = the complaint records of every builder were collected (a full crawl of the
    complaint index, or a complaints table from an authority). Without it, a builder with no complaint rows
    has unknown complaints, not clean ones.
    """
    __tablename__ = "coverage"

    key: Mapped[str] = mapped_column(primary_key=True)
    complete: Mapped[bool]
    updated_at: Mapped[datetime]


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("promoter_group.id"))
    computed_at: Mapped[datetime]
    breakdown: Mapped[dict] = mapped_column(Json)
    input_source_document_ids: Mapped[list] = mapped_column(Json)
