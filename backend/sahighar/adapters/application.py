"""Read a promoter's registration application (the "View Original Application" document) into a small, safe extract.

The real document also holds bank account numbers, phone numbers, emails, Aadhaar numbers and, for individuals, a
home address. None of that is kept: this is a WHITELIST. Only these fields leave this module, and every personal
identifier is already a one-way token (see sahighar.privacy):
  organization or individual, organization name and type, PAN token, members' PAN tokens (directors, partners,
  signatories), the business address (organizations only, never a home address), the promoter's declared past
  projects (name, type, original proposed and actual completion dates) and this project's declared status,
  proposed and revised completion dates and litigation flag.
Because the raw PDF is never stored, the stored document is this extract (a deliberate exception to "store the raw page").
"""
import base64
import io
import re
from datetime import date, datetime

from pypdf import PdfReader

from sahighar.adapters.base import ParsedRecords, PastProjectRec, PromoterRec
from sahighar.privacy import tokenize

# Bump when extract_application changes what it reads. Stored extracts carry the version they were made with; the raw
# PDF is not kept, so an older extract cannot be re-parsed, only fetched again.
EXTRACT_VERSION = 2
CONTENT_TYPE = f"application/json; extract={EXTRACT_VERSION}"

_PAN = r"[A-Z]{5}\d{4}[A-Z]"
_ISO = r"\d{4}-\d{2}-\d{2}"
_DMY = r"\d{2}/\d{2}/\d{4}"
_TYPES = r"(Residential|Commercial|Mixed|Industrial|Plotted|Others|Other)"


def _dmy(text: str) -> str:
    return datetime.strptime(text, "%d/%m/%Y").date().isoformat()


def _between(flat: str, start: str, end: str) -> str:
    m = re.search(rf"{start}\s+(.*?)\s+{end}", flat)
    return m.group(1).strip() if m else ""


def _address(flat: str) -> str | None:
    block = re.search(r"Block Number.*?Pin Code (\d{6})", flat)
    if not block:
        return None
    seg = block.group(0)
    parts = [_between(seg, "Block Number", "Building Name"), _between(seg, "Building Name", "Street Name"),
             _between(seg, "Street Name", "Locality"), _between(seg, "Locality", r"Land ?mark"),
             _between(seg, "Division", "District"), _between(seg, "District", "Taluka"), block.group(1)]
    return ", ".join(p for p in parts if p) or None


def _past_projects(flat: str) -> list[dict]:
    header = flat.find("Actual Date of Completion")
    if header < 0:
        return []
    region = flat[header + len("Actual Date of Completion"):]
    ends = [i for i in (region.find(m) for m in (" Sr.No.", " Project FSI", " Project Details")) if i >= 0]
    region = region[:min(ends)] if ends else region
    rows, position = [], 0
    for pair in re.finditer(rf"({_ISO}) ({_ISO})", region):
        row, position = region[position:pair.end()], pair.end()
        named = re.match(rf"\s*\d+\s+(.*?)\s+{_TYPES}\b", row)
        if named:
            rows.append({"name": named.group(1).strip(), "type": named.group(2),
                         "original_proposed": pair.group(1), "actual": pair.group(2)})
    return rows


def extract_application(text: str) -> dict:
    flat = re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("\xad", "-"))
    info = re.search(r"Information Type (Other Than Individual|Individual)", flat)
    if not info:
        raise ValueError("not a registration application (no 'Information Type')")
    individual = info.group(1) == "Individual"
    pan = re.search(rf"PAN Number ({_PAN})", flat)
    org = re.search(r"Total Amount Paid by User [\d.,]+ Name (.+?) PAN Number", flat)
    org_type = re.search(r"PAN Number \S+ Organization Type (.+?) (?:Description|Do you)", flat)  # not the menu label of the same name
    # Members appear in rows ending "<PAN> View"; LLPs list their partners in a second table further down. Some older
    # applications end the row with "<PAN>" alone inside the first table, so that table is read too.
    first_table = re.search(r"Member Name Designation PAN No\. VIEW (.*?) Information Type", flat)
    member_pans = list(dict.fromkeys(re.findall(rf"({_PAN}) View", flat) + (re.findall(_PAN, first_table.group(1)) if first_table else [])))
    status = re.search(rf"Project Status (.+?) Proposed Date of Completion ({_DMY})(?: Revised Proposed Date of Completion ({_DMY}))?", flat)
    litigation = re.search(r"Litigations related to the project \? (Yes|No)", flat)
    return {
        "info_type": "individual" if individual else "organization",
        "org_name": None if individual or not org else org.group(1).strip(),
        "org_type": None if individual or not org_type else org_type.group(1).strip(),
        "pan": tokenize("pan", pan.group(1)) if pan else None,
        "members": [] if individual else [tokenize("pan", p) for p in member_pans],  # masked PANs (xxxxxx1234) never match _PAN
        "address": None if individual else _address(flat),  # an individual's address is a home address: never kept
        "past_projects": _past_projects(flat),
        "project_status": status.group(1).strip() if status else None,
        "proposed_completion": _dmy(status.group(2)) if status else None,
        "revised_completion": _dmy(status.group(3)) if status and status.group(3) else None,
        "litigation": {"Yes": True, "No": False}[litigation.group(1)] if litigation else None,
    }


def extract_application_from_html(html: str) -> dict | None:
    """The document endpoint returns HTML wrapping a PDF. None if the site has no document (or answers with an error)."""
    m = re.search(r"data:application/pdf;base64,([A-Za-z0-9+/=]+)", html)
    if not m:
        return None
    blob = base64.b64decode(m.group(1))
    if not blob.startswith(b"%PDF"):
        return None
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(blob)).pages)
    return extract_application(text)


def parse_application(extract: dict) -> ParsedRecords:
    """Turn a stored extract (plus the promoter_ref and promoter_name the crawler added) into records: tokens only."""
    return ParsedRecords(
        promoters=[PromoterRec(extract["promoter_ref"], extract["promoter_name"], pan=extract.get("pan"),
                               registered_address=extract.get("address"),
                               partners_or_directors=extract.get("members") or None)],
        past_projects=[PastProjectRec(extract["promoter_ref"], p["name"], date.fromisoformat(p["original_proposed"]),
                                      date.fromisoformat(p["actual"]), p.get("type"))
                       for p in extract.get("past_projects", [])])
