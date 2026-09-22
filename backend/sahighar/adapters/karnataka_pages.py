"""Pure parsers for Karnataka RERA's bulk public pages (rera.karnataka.gov.in). No network here.

Two pages give a builder-level delivery record with no PDFs and no per-project requests:
  /viewRenewalProjects   -- three tables: approved extensions, rejected extension applications, and projects whose
                             completion date has passed (with or without an approved-but-unused extension).
  /viewAllCompletedProjects -- projects that have applied to close out as complete, with the date they applied.
"date" fields are DD/MM/YYYY, as published.
"""
import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import date, datetime


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _dmy(text: str) -> date | None:
    text = text.strip()
    return datetime.strptime(text, "%d/%m/%Y").date() if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text) else None


_REG_NO = re.compile(r"PRM/KA/RERA/\S+")


def _rows(html: str) -> list[list[str]]:
    return [[_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]


def _tables_by_header(html: str, *keywords: str) -> list[list[list[str]]]:
    """The renewals page holds three <table>s with the same column count in places; tell them apart by a header
    word unique to each, not by shape. Returns, for each keyword, the row lists of the (first) table whose header
    contains it -- [] if that table is not on this page (e.g. a fixture trimmed to one table)."""
    found = []
    for table in re.findall(r"<table.*?</table>", html, re.S):
        header = _text((re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S) or [""])[0])
        found.append((header, _rows(table)))
    return [next((rows for header, rows in found if keyword in header), []) for keyword in keywords]


@dataclass
class ApprovedExtension:
    reg_no: str
    promoter_name: str
    project_name: str
    district: str
    old_completion: date | None
    new_completion: date | None


@dataclass
class RejectedExtension:
    reg_no: str
    promoter_name: str
    project_name: str
    district: str
    proposed_completion: date | None


@dataclass
class ExpiredRow:
    reg_no: str
    promoter_name: str
    project_name: str
    district: str
    completion_date: date | None
    further_extension_date: date | None  # only when "Extension Approved and Not Applied for Completion"
    applied_status: str


@dataclass
class RenewalsPage:
    approved: list[ApprovedExtension] = field(default_factory=list)
    rejected: list[RejectedExtension] = field(default_factory=list)
    expired: list[ExpiredRow] = field(default_factory=list)


def parse_renewals_page(html: str) -> RenewalsPage:
    approved_rows, rejected_rows, expired_rows = _tables_by_header(
        html, "NEW REGISTRATION NO", "REJECTED ON", "FURTHER EXTENSION DATE")
    page = RenewalsPage()
    for row in approved_rows[1:]:
        if len(row) >= 11 and _REG_NO.fullmatch(row[1]):
            page.approved.append(ApprovedExtension(row[1], row[5], row[6], row[7], _dmy(row[9]), _dmy(row[10])))
    for row in rejected_rows[1:]:
        if len(row) >= 8 and _REG_NO.fullmatch(row[1]):
            page.rejected.append(RejectedExtension(row[1], row[2], row[3], row[4], _dmy(row[6])))
    for row in expired_rows[1:]:
        if len(row) >= 8 and _REG_NO.fullmatch(row[1]):
            page.expired.append(ExpiredRow(row[1], row[2], row[3], row[4], _dmy(row[5]), _dmy(row[6]), row[7]))
    return page


@dataclass
class CompletedRow:
    reg_no: str
    promoter_name: str
    project_name: str
    project_type: str
    district: str
    proposed_completion: date | None
    applied_for_completion: date | None


def parse_completed_list(html: str) -> list[CompletedRow]:
    return [CompletedRow(row[1], row[2], row[3], row[5], row[6], _dmy(row[8]), _dmy(row[9]))
            for row in _rows(html) if len(row) >= 10 and _REG_NO.fullmatch(row[1])]


@dataclass
class ComplaintIndexRow:
    promoter_name: str
    count: int
    token: str  # opaque "pName" value from the row's link, kept percent-encoded ready to paste into a URL


def parse_complaint_index(html: str) -> list[ComplaintIndexRow]:
    """/promoterComplaintReport: one page, every promoter with a complaint, its count, and a link to its own
    complaint list. No pagination, no promoter id -- the name is all there is."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 4:
            continue
        name, count_text = _text(cells[1]), _text(cells[2])
        token = re.search(r"pName=([^\"&]+)", cells[3])
        if name and count_text.isdigit() and token:
            rows.append(ComplaintIndexRow(name, int(count_text), token.group(1)))
    return rows


@dataclass
class ComplaintDetailRow:
    complaint_no: str
    promoter_name: str
    project_name: str
    status: str  # raw text exactly as published, e.g. "DISPOSED AUTHORITY FULLBENCH"
    complaint_date: date | None
    disposed_date: date | None  # only once disposed
    order_url: str | None  # the order PDF, only once disposed


def parse_complaint_detail(html: str) -> list[ComplaintDetailRow]:
    """A promoter's own complaint list (complaintReportWiseList). The ORDER column's PDF link (fa-file-pdf-o)
    appears only once a complaint is disposed; before that it is empty, matching the absent disposed date."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 9:
            continue
        complaint_no = _text(cells[1])
        if not complaint_no:
            continue
        order = re.search(r"href=['\"](/download_jc\?[^'\"]+)['\"]", cells[8])
        rows.append(ComplaintDetailRow(
            complaint_no, _text(cells[2]), _text(cells[3]), _text(cells[5]),
            _dmy(_text(cells[6])), _dmy(_text(cells[7])), order.group(1) if order else None))
    return rows


def karnataka_complaint_stage(status: str) -> str:
    """Map a published complaint status to a stage: order_issued | pending | other. Unknown statuses are
    "other", never guessed -- the same policy as MahaRERA's complaint_stage(). Confirmed by sample (2026-09-22):
    "DISPOSED ..." always carries a disposed date and an order PDF; "UNDER ENQUIRY ..." and "POSTED FOR ORDERS
    ..." never do, so they count as still open."""
    s = status.strip().upper()
    if s.startswith("DISPOSED"):
        return "order_issued"
    if s.startswith("UNDER ENQUIRY") or s.startswith("POSTED FOR ORDERS"):
        return "pending"
    return "other"
