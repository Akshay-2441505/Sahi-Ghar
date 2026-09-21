"""Pure parsers for the pages on MahaRERA's public site (maharera.maharashtra.gov.in). No network here.

Written against real pages saved in docs/spikes (fixtures in tests/fixtures/maharera). When the site changes,
the parser tests fail first; fix the parser and re-parse the stored raw pages, no need to fetch again.
"""
import base64
import html as htmllib
import io
import re
from dataclasses import dataclass, field
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
        view = re.search(r"/project/view/(\d+)", block)  # builder-search cards have no Certificate link; this id is the same
        cards.append(ProjectCard(
            reg_no=reg.group(1), name=_text(name.group(1)), promoter_name=_text(promoter.group(1)),
            district=_field(block, "District"), pincode=_field(block, "Pincode"),
            last_modified=datetime.strptime(modified, "%Y-%m-%d").date() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified) else None,
            cert_id=_cert_id(block, "DocProjectCert") or (view.group(1) if view else None),
            ext_cert_id=_cert_id(block, "DocProjectExtCert"),
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


def _table_rows(html: str) -> list[list[str]]:
    return [[_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)] for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]


@dataclass
class AbeyanceRow:
    reg_no: str
    promoter_name: str
    project_name: str
    district: str


def parse_abeyance_list(html: str) -> list[AbeyanceRow]:
    """The "Due to Lapse of Completion Date" list: projects MahaRERA keeps in abeyance."""
    return [AbeyanceRow(row[1], row[2], row[3], row[4]) for row in _table_rows(html)
            if len(row) >= 5 and re.fullmatch(r"P\d{11}", row[1])]


@dataclass
class NcltRow:
    reg_no: str
    promoter_name: str
    project_name: str
    district: str
    status: str  # registration status as published, e.g. "Lapsed" or "Active"
    status_as_of: date | None  # the date in the column heading "Project Status as on dd-mm-yyyy"
    proposed_completion: date | None
    form4_uploaded: bool


def _dmy(text: str) -> date | None:
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", text.strip())
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def parse_nclt_list(html: str) -> list[NcltRow]:
    """The NCLT projects list: one page, with each project's certificate number and registration status."""
    heading = re.search(r"Project Status as on (\d{2}-\d{2}-\d{4})", html)
    as_of = _dmy(heading.group(1)) if heading else None
    return [NcltRow(row[3], row[1], row[2], row[6], row[8], as_of, _dmy(row[4]), row[9].strip().upper() == "Y")
            for row in _table_rows(html) if len(row) >= 10 and re.fullmatch(r"P\d{11}", row[3])]


@dataclass
class Certificate:
    reg_no: str
    original_end: date | None  # end of the ORIGINAL registration validity, when the document says so
    current_end: date | None  # end of the registration as of this document (the extended date, if extended)
    complete: bool  # True for the newer format, which carries the whole extension history in one document
    extensions: list[tuple[str, date]] = field(default_factory=list)  # (label as published, revised end date), in order


def _date(text: str) -> date:
    return datetime.strptime(text, "%d/%m/%Y").date()


_D = r"(\d{2}/\d{2}/\d{4})"


def parse_certificate(html: str) -> Certificate | None:
    """The certificate endpoint returns HTML with the PDF embedded, in one of three shapes (read by content, not by
    which endpoint served it): an old registration certificate (original end date), an old extension certificate
    (new end date only), or a newer certificate that states the original date and the current end date together.
    None if the site has no certificate (\"No Record Found\", or a small JSON error where the PDF should be)."""
    m = re.search(r"data:application/pdf;base64,([A-Za-z0-9+/=]+)", html)
    if not m:
        return None
    blob = base64.b64decode(m.group(1))
    if not blob.startswith(b"%PDF"):
        return None
    pages = PdfReader(io.BytesIO(blob)).pages
    text = "\n".join(page.extract_text() or "" for page in pages).replace("\xa0", " ")  # the PDF text uses non-breaking spaces
    reg = re.search(r"\bP\d{11}\b", text)
    if not reg:
        raise ValueError("certificate has no project registration number")
    original = re.search(rf"Original Project Completion date:\s*{_D}", text)
    ending = re.search(rf"ending with\s+{_D}", text)
    until = re.search(rf"valid up to\s+{_D}", text)
    if original:
        if not ending:
            raise ValueError(f"certificate for {reg.group(0)} states an original date but no validity end")
        history = re.findall(rf"^\s*((?:[A-Za-z]+ )*Extension\s*-\s*\d+)\s+{_D}\s+{_D}", text, re.M)
        return Certificate(reg.group(0), _date(original.group(1)), _date(ending.group(1)), True,
                           [(label, _date(revised)) for label, _approved, revised in history])
    if "EXTENSION OF REGISTRATION" in text.upper() and until:
        return Certificate(reg.group(0), None, _date(until.group(1)), False)
    if ending:
        return Certificate(reg.group(0), _date(ending.group(1)), _date(ending.group(1)), False)
    raise ValueError(f"certificate for {reg.group(0)} has no validity period")
