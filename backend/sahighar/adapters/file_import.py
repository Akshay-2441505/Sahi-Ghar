"""Adapter for data the owner obtains from an authority (RTI or data request): a folder of CSV/Excel files.

Nothing here fetches from a website. Each file becomes one RawDoc (the real file bytes), so every imported
number links back to "file <name>, obtained <date>". Files are recognised by their columns, not their names:
  complaints table: has a complaint number      projects table: has a project registration number
  promoters table:  has a promoter id
Load order is projects, promoters, complaints, so a promoters table enriches what the projects table introduced.
"""
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Iterable

from sahighar.adapters.base import ComplaintRec, ParsedRecords, ProjectRec, PromoterRec, RawDoc, complaint_stage
from sahighar.adapters.tabular import (
    Table, parse_date, parse_month, parse_year, parse_yes_no, read_table, split_names,
)

_ORDER = {"projects": 0, "promoters": 1, "complaints": 2, "unknown": 3}
_CONTENT_TYPES = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12"}


def _kind(columns: list[str]) -> str:
    if "complaint_ref" in columns:
        return "complaints"
    if "reg_no" in columns:
        return "projects"
    if "promoter_ref" in columns:
        return "promoters"
    return "unknown"


class FileImportAdapter:
    origin = "file-import"

    def __init__(self, folder: Path, state: str = "MH", obtained_on: date | None = None):
        """obtained_on: the date the owner received the files (default: each file's modified time)."""
        self.folder = Path(folder)
        self.state = state
        self.obtained_on = obtained_on

    def discover(self) -> Iterable[RawDoc]:
        docs = []
        for path in sorted(self.folder.iterdir()):
            if path.suffix.lower() not in _CONTENT_TYPES:
                continue
            data = path.read_bytes()
            try:
                kind = _kind(read_table(data, path.name).columns)
            except Exception:  # unreadable file: still yield it, so parse() records the real error against it
                kind = "unknown"
            if self.obtained_on is not None:
                fetched_at = datetime.combine(self.obtained_on, time())
            else:
                fetched_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(tzinfo=None)
            docs.append(RawDoc(self.origin, kind, f"file:{path.name}", fetched_at, _CONTENT_TYPES[path.suffix.lower()], data))
        return sorted(docs, key=lambda d: (_ORDER[d.kind], d.url))

    def parse(self, doc: RawDoc) -> ParsedRecords:
        name = doc.url.removeprefix("file:")
        table = read_table(doc.data, name)
        parser = {"projects": _projects, "promoters": _promoters, "complaints": _complaints}.get(doc.kind)
        if parser is None:
            raise ValueError(f"{name}: not recognised as a projects, promoters or complaints table; "
                             f"columns found: {table.columns or 'none'}")
        return parser(name, table)


def _require(name: str, table: Table, *columns: str) -> None:
    missing = [c for c in columns if c not in table.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}; columns found: {table.columns}")


def _each_row(name: str, table: Table, handle) -> None:
    """Run handle(row) on every row, collecting problems so one message lists the first few bad lines."""
    problems = []
    for line, row in zip(table.lines, table.rows):
        try:
            handle(row)
        except ValueError as error:
            problems.append(f"line {line}: {error}")
    if problems:
        more = f"; and {len(problems) - 10} more" if len(problems) > 10 else ""
        raise ValueError(f"{name}: " + "; ".join(problems[:10]) + more)


def _projects(name: str, table: Table) -> ParsedRecords:
    _require(name, table, "reg_no", "name", "promoter_ref")
    projects: dict[str, ProjectRec] = {}
    promoters: dict[str, PromoterRec] = {}

    def handle(row: dict) -> None:
        reg_no = row["reg_no"]
        end, extended = parse_date(row.get("registration_end")), parse_date(row.get("extended_end"))
        if not reg_no or not row["promoter_ref"]:
            raise ValueError("project registration number and promoter id are required")
        known = projects.get(reg_no)
        if known is None:  # several rows for one project = one row per extension
            projects[reg_no] = ProjectRec(reg_no, row["promoter_ref"], row["name"], city=row.get("city") or None,
                                          locality=row.get("locality") or None, registration_end=end, extended_end=extended)
        else:
            if end and known.registration_end and end != known.registration_end:
                raise ValueError(f"{reg_no} has two different registration end dates")
            known.registration_end = known.registration_end or end
            known.extended_end = max((d for d in (known.extended_end, extended) if d), default=None)
        if row.get("promoter_name"):  # lets a projects-only reply import; a promoters table enriches it later
            promoters.setdefault(row["promoter_ref"], PromoterRec(row["promoter_ref"], row["promoter_name"]))

    _each_row(name, table, handle)
    return ParsedRecords(promoters=list(promoters.values()), projects=list(projects.values()))


def _promoters(name: str, table: Table) -> ParsedRecords:
    _require(name, table, "promoter_ref")
    if "promoter_name" not in table.columns and "name" not in table.columns:
        raise ValueError(f"{name}: missing a promoter name column; columns found: {table.columns}")
    promoters = []

    def handle(row: dict) -> None:
        promoter_name = row.get("promoter_name") or row.get("name")
        if not row["promoter_ref"] or not promoter_name:
            raise ValueError("promoter id and promoter name are required")
        promoters.append(PromoterRec(
            row["promoter_ref"], promoter_name, pan=(row.get("pan") or "").upper() or None,
            registered_address=row.get("address") or None,
            partners_or_directors=split_names(row.get("partners")) or None))

    _each_row(name, table, handle)
    return ParsedRecords(promoters=promoters)


def _complaints(name: str, table: Table) -> ParsedRecords:
    _require(name, table, "complaint_ref", "status")
    if "promoter_ref" not in table.columns and "project_reg_no" not in table.columns:
        raise ValueError(f"{name}: needs a promoter id or a project number column; columns found: {table.columns}")
    complaints = []

    def handle(row: dict) -> None:
        if not row["complaint_ref"]:
            raise ValueError("complaint number is required")
        filed = parse_date(row.get("filed_date"))
        year = filed.year if filed else parse_year(row.get("filed_year"))
        month = filed.month if filed else parse_month(row.get("filed_month"))
        complaints.append(ComplaintRec(
            row["complaint_ref"], row.get("promoter_ref") or None, row["status"], complaint_stage(row["status"]),
            non_execution_applied=parse_yes_no(row.get("non_execution")),
            project_reg_no=row.get("project_reg_no") or None, filed_year=year, filed_month=month,
            order_url=row.get("order_url") or None))

    _each_row(name, table, handle)
    return ParsedRecords(complaints=complaints)
