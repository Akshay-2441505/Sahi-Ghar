from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Protocol


@dataclass(frozen=True)
class RawDoc:
    origin: str  # adapter origin label
    kind: str  # "project" | "promoter" | "complaints"
    url: str  # "file:<name>" for file imports
    fetched_at: datetime
    content_type: str
    data: bytes


@dataclass
class PromoterRec:
    ref: str
    name: str
    pan: str | None = None
    registered_address: str | None = None
    partners_or_directors: list[str] | None = None


@dataclass
class ProjectRec:
    reg_no: str
    promoter_ref: str | None  # None for a document that only adds dates to an already-introduced project
    name: str | None
    city: str | None = None
    locality: str | None = None
    configurations: list[str] | None = None
    carpet_area_range: str | None = None
    registration_end: date | None = None  # end of the original registration validity
    extended_end: date | None = None  # new end date, only if an extension certificate exists
    extension_history: list[dict] | None = None  # [{"label", "revised_end"}] as published, newer certificates only


@dataclass
class ComplaintRec:
    ref: str
    promoter_ref: str | None  # None when the source gives only a project number; the runner then uses the project's promoter
    status: str  # raw text exactly as published, e.g. "Order Approved"
    stage: str  # order_issued | pending | other  (see complaint_stage)
    non_execution_applied: bool = False  # a buyer asked to enforce an order that was not complied with
    project_reg_no: str | None = None
    filed_year: int | None = None  # the source publishes year and month only
    filed_month: int | None = None
    order_url: str | None = None


@dataclass
class PastProjectRec:
    """A project the promoter DECLARED as completed in its registration application (the promoter's own account)."""
    promoter_ref: str
    name: str
    original_proposed: date
    actual: date
    project_type: str | None = None


@dataclass
class ProjectFlagRec:
    """A notice the regulator itself publishes about a project (e.g. kept in abeyance, an NCLT project)."""
    reg_no: str
    kind: str  # abeyance | nclt
    detail: dict | None = None
    promoter_ref: str | None = None  # the promoter as named on the list (name only: these lists carry no promoter id)


@dataclass
class ParsedRecords:
    promoters: list[PromoterRec] = field(default_factory=list)
    projects: list[ProjectRec] = field(default_factory=list)
    complaints: list[ComplaintRec] = field(default_factory=list)
    past_projects: list[PastProjectRec] = field(default_factory=list)
    project_flags: list[ProjectFlagRec] = field(default_factory=list)


_STAGES = {"order approved": "order_issued", "hearing scheduled": "pending", "roznama approved": "pending"}


def complaint_stage(status: str) -> str:
    """Map a published complaint status to a stage. Unknown statuses are 'other', never guessed."""
    return _STAGES.get(status.strip().lower(), "other")


class Adapter(Protocol):
    """One implementation per (state, source path).

    Contract: `discover()` yields every raw document the source provides, and a
    promoter is always introduced (a PromoterRec in some earlier or the same
    document's `parse()` result) before any project or complaint that references it.
    `parse()` is a pure function of the document: no network, no database.
    """

    state: str  # "MH" | "KA" | "TG"
    origin: str

    def discover(self) -> Iterable[RawDoc]: ...

    def parse(self, doc: RawDoc) -> ParsedRecords: ...
