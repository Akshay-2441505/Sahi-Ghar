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
