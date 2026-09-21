"""Pure parsers for the pages on MahaRERA's public site (maharera.maharashtra.gov.in). No network here.

Written against real pages saved in docs/spikes (fixtures in tests/fixtures/maharera). When the site changes,
the parser tests fail first; fix the parser and re-parse the stored raw pages, no need to fetch again.
"""
import base64
import html as htmllib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

from pypdf import PdfReader

_CARD_MARK = 'class="row shadow p-3 mb-5 bg-body rounded"'


def promoter_ref(name: str) -> str:
    """Stable id for a promoter: its name, ignoring case, spacing and punctuation only.

    The public project list gives the promoter's name but no id. "Pvt Ltd" and "Private Limited" stay
    different on purpose: merging them by guessing is what grouping is for, and it says so on the page.
    """
    return "n:" + re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _total(page: str) -> int | None:
    m = re.search(r'Showing Final <span[^>]*>(\d+)</span>', page)
    return int(m.group(1)) if m else None


@dataclass
class ProjectCard:
    reg_no: str
    name: str
    promoter_name: str
    district: str
    pincode: str
    last_modified: date | None
    cert_id: str | None  # internal id used by the certificate endpoint
    ext_cert_id: str | None  # None when the site shows "N/A"


@dataclass
class ProjectListPage:
    total: int | None
    pages: int | None
    cards: list[ProjectCard]


def _field(block: str, label: str) -> str:
    m = re.search(rf'{label}</div>\s*<p>([^<]*)</p>', block)
    return _text(m.group(1)) if m else ""


def _cert_id(block: str, flag: str) -> str | None:
    for tag in re.findall(r"<a\b[^>]*>", block):
        if f'data-qstr-flag="{flag}"' in tag:
            m = re.search(r'data-qstr="(\d+)"', tag)
            if m:
                return m.group(1)
    return None


def parse_project_list(html: str) -> ProjectListPage:
    pages = re.search(r'data-current-data="(\d+)"', html)
    cards = []
    for block in html.split(_CARD_MARK)[1:]:
        reg = re.search(r"# (P\d+)", block)
        name = re.search(r"<strong>([^<]+)</strong>", block)
        promoter = re.search(r'<p class="darkBlue bold ">([^<]*)</p>', block)
        if not (reg and name and promoter):
            continue  # not a project card
        modified = _field(block, "Last Modified")
        cards.append(ProjectCard(
            reg_no=reg.group(1), name=_text(name.group(1)), promoter_name=_text(promoter.group(1)),
            district=_field(block, "District"), pincode=_field(block, "Pincode"),
            last_modified=datetime.strptime(modified, "%Y-%m-%d").date() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified) else None,
            cert_id=_cert_id(block, "DocProjectCert"), ext_cert_id=_cert_id(block, "DocProjectExtCert"),
        ))
    return ProjectListPage(_total(html), int(pages.group(1)) if pages else None, cards)


@dataclass
class ComplaintListRow:
    name: str
    count: int
    promoter_id: str


@dataclass
class ComplaintListPage:
    total: int | None
    rows: list[ComplaintListRow]


def parse_complaint_list(html: str) -> ComplaintListPage:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        link = re.search(r"promoter_id=(\d+)", tr)
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if link and len(cells) >= 3 and cells[2].isdigit():
            rows.append(ComplaintListRow(cells[1], int(cells[2]), link.group(1)))
    return ComplaintListPage(_total(html), rows)


@dataclass
class ComplaintRow:
    promoter_name: str
    project_no: str
    district: str
    complaint_no: str
    year: int | None
    month: str
    status: str
    non_execution_applied: bool


def parse_complaint_detail(html: str) -> list[ComplaintRow]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = [_text(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(c) >= 10 and c[4]:
            rows.append(ComplaintRow(c[1], c[2], c[3], c[4], int(c[5]) if c[5].isdigit() else None, c[6], c[7],
                                     c[8].strip().lower() == "y"))
    return rows


@dataclass
class Certificate:
    reg_no: str
    kind: str  # registration | extension
    valid_from: date | None
    valid_until: date


def _date(text: str) -> date:
    return datetime.strptime(text, "%d/%m/%Y").date()


def parse_certificate(html: str) -> Certificate | None:
    """The certificate endpoint returns HTML with the PDF embedded. None if the site says there is none."""
    m = re.search(r"data:application/pdf;base64,([A-Za-z0-9+/=]+)", html)
    if not m:
        return None
    reader = PdfReader(io.BytesIO(base64.b64decode(m.group(1))))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).replace("\xa0", " ")  # PDF text uses non-breaking spaces
    reg = re.search(r"\bP\d{11}\b", text)
    if not reg:
        raise ValueError("certificate has no project registration number")
    if "EXTENSION OF REGISTRATION" in text.upper():
        until = re.search(r"valid up to\s+(\d{2}/\d{2}/\d{4})", text)
        if not until:
            raise ValueError(f"extension certificate for {reg.group(0)} has no 'valid up to' date")
        return Certificate(reg.group(0), "extension", None, _date(until.group(1)))
    span = re.search(r"commencing from\s+(\d{2}/\d{2}/\d{4})\s+and ending with\s+(\d{2}/\d{2}/\d{4})", text)
    if not span:
        raise ValueError(f"registration certificate for {reg.group(0)} has no validity period")
    return Certificate(reg.group(0), "registration", _date(span.group(1)), _date(span.group(2)))
