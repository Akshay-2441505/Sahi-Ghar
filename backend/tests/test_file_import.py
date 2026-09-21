from datetime import date, datetime

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from sahighar.adapters.file_import import FileImportAdapter
from sahighar.db.models import Complaint, Project, Promoter, ScoreSnapshot, SourceDocument
from sahighar.ingest.runner import run_ingest
from sahighar.privacy import tokenize
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh

PROJECTS = """Project Registration Number,Project Name,Promoter ID,Promoter Name,District,Registration Valid Up To,Extended Up To
P51700000001,Shree Heights,PR1,Shree Realty LLP,Pune,31/12/2018,
P51700000002,Shree Gardens,PR2,Shree Homes LLP,Pune,31/12/2018,31/12/2019
P51700000002,Shree Gardens,PR2,Shree Homes LLP,Pune,31/12/2018,30/06/2020
P51700000003,Shree Towers,PR3,Shree Realty Phase 2 LLP,Pune,31/12/2030,
"""
PROMOTERS = """Promoter ID,Promoter Name,Registered Office Address,PAN,Directors
PR1,Shree Realty LLP,"12 MG Road, Pune",AAAPA0001A,Ramesh Shah; Anil Mehta
PR2,Shree Homes LLP,,AAAPA0001A,
PR3,Shree Realty Phase 2 LLP,12 MG ROAD PUNE,BBBPB0002B,ramesh shah
"""
# shaped like MahaRERA's public complaint table: a project number, but no promoter ID
COMPLAINTS = """Complaint No.,Name of Promoter,Project No.,District,Year of Complaint Filing,Month of Complaint Filing,Complaint Status,Applied For Non-Execution (Y/N)
CC001,Shree Realty LLP,P51700000001,Pune,2024,March,Hearing Scheduled,N
CC002,Shree Homes LLP,P51700000002,Pune,2023,11,Order Approved,Y
"""


def write(folder, name, text):
    (folder / name).write_text(text, encoding="utf-8")


@pytest.fixture
def folder(tmp_path):
    for name, text in (("projects.csv", PROJECTS), ("promoters.csv", PROMOTERS), ("complaints.csv", COMPLAINTS)):
        write(tmp_path, name, text)
    return tmp_path


def parse_one(adapter, kind):
    return adapter.parse(next(d for d in adapter.discover() if d.kind == kind))


def test_discover_classifies_files_by_their_columns_and_orders_them(folder):
    write(folder, "zz_notes.csv", "Something,Else\n1,2\n")
    (folder / "readme.txt").write_text("ignored: not a table")
    docs = list(FileImportAdapter(folder).discover())
    assert [(d.kind, d.url) for d in docs] == [
        ("projects", "file:projects.csv"), ("promoters", "file:promoters.csv"),
        ("complaints", "file:complaints.csv"), ("unknown", "file:zz_notes.csv"),
    ]
    assert all(d.origin == "file-import" for d in docs)


def test_projects_use_the_latest_extension_and_derive_a_promoter_from_each_row(folder):
    parsed = parse_one(FileImportAdapter(folder), "projects")
    by_no = {p.reg_no: p for p in parsed.projects}
    assert by_no["P51700000001"].registration_end == date(2018, 12, 31) and by_no["P51700000001"].extended_end is None
    assert by_no["P51700000002"].extended_end == date(2020, 6, 30)  # two extension rows: the latest wins
    assert len(parsed.projects) == 3 and by_no["P51700000001"].city == "Pune"
    assert {(p.ref, p.name) for p in parsed.promoters} == {
        ("PR1", "Shree Realty LLP"), ("PR2", "Shree Homes LLP"), ("PR3", "Shree Realty Phase 2 LLP")}


def test_promoters_carry_pan_address_and_directors(folder):
    parsed = parse_one(FileImportAdapter(folder), "promoters")
    p1 = next(p for p in parsed.promoters if p.ref == "PR1")
    assert (p1.pan, p1.registered_address, p1.partners_or_directors) == (
        tokenize("pan", "AAAPA0001A"), "12 MG Road, Pune", [tokenize("name", "Ramesh Shah"), tokenize("name", "Anil Mehta")])
    assert "AAAPA0001A" not in str(p1) and "Ramesh" not in str(p1)  # raw identifiers never reach the records
    assert next(p for p in parsed.promoters if p.ref == "PR2").partners_or_directors is None


def test_complaints_map_status_to_stage_and_keep_only_month_and_year(folder):
    parsed = parse_one(FileImportAdapter(folder), "complaints")
    c1, c2 = parsed.complaints
    assert (c1.ref, c1.promoter_ref, c1.project_reg_no, c1.status, c1.stage) == (
        "CC001", None, "P51700000001", "Hearing Scheduled", "pending")
    assert (c1.filed_year, c1.filed_month, c1.non_execution_applied) == (2024, 3, False)
    assert (c2.stage, c2.filed_month, c2.non_execution_applied) == ("order_issued", 11, True)


def test_a_full_date_column_is_accepted_too(tmp_path):
    write(tmp_path, "c.csv", "Complaint No,Project No,Complaint Status,Date of Filing\nCC1,P1,Order Approved,05/03/2024\n")
    complaint = parse_one(FileImportAdapter(tmp_path), "complaints").complaints[0]
    assert (complaint.filed_year, complaint.filed_month) == (2024, 3)


def test_bad_values_fail_the_document_with_line_numbers_and_never_guess(tmp_path):
    write(tmp_path, "projects.csv", "Project Registration Number,Project Name,Promoter ID,Registration Valid Up To\n"
                                    "P1,A,PR1,31/12/2018\nP2,B,PR1,12/31/2018\nP3,C,PR1,soon\n")
    with pytest.raises(ValueError) as error:
        parse_one(FileImportAdapter(tmp_path), "projects")
    message = str(error.value)
    assert "projects.csv" in message and "line 3" in message and "line 4" in message and "12/31/2018" in message


def test_missing_required_columns_are_named(tmp_path):
    write(tmp_path, "projects.csv", "Project Registration Number,Project Name\nP1,A\n")
    with pytest.raises(ValueError, match=r"missing columns \['promoter_ref'\]"):
        parse_one(FileImportAdapter(tmp_path), "projects")


def test_an_unrecognised_file_is_reported_with_the_columns_it_has(tmp_path):
    write(tmp_path, "other.csv", "Foo,Bar\n1,2\n")
    with pytest.raises(ValueError, match="not recognised"):
        parse_one(FileImportAdapter(tmp_path), "unknown")


def test_fetched_at_is_the_date_the_owner_obtained_the_files(folder):
    docs = list(FileImportAdapter(folder, obtained_on=date(2026, 11, 5)).discover())
    assert {d.fetched_at for d in docs} == {datetime(2026, 11, 5)}


def test_reads_excel_files_with_real_date_cells(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Project Registration Number", "Project Name", "Promoter ID", "Registration Valid Up To", "Extended Up To"])
    sheet.append(["P1", "Heights", "PR1", datetime(2018, 12, 31), datetime(2019, 12, 31)])
    workbook.save(tmp_path / "projects.xlsx")
    project = parse_one(FileImportAdapter(tmp_path), "projects").projects[0]
    assert (project.registration_end, project.extended_end) == (date(2018, 12, 31), date(2019, 12, 31))


def test_end_to_end_import_scores_and_reports_the_bad_file_without_stopping(session, folder, tmp_path):
    write(folder, "zz_notes.csv", "Something,Else\n1,2\n")
    adapter = FileImportAdapter(folder, obtained_on=date(2026, 9, 1))
    summary = run_ingest(adapter, session, LocalRawStore(tmp_path / "raw"), max_failure_rate=0.5)
    assert (summary.total, summary.ok, summary.failed) == (4, 3, 1)
    assert session.scalar(select(SourceDocument.parse_error).where(SourceDocument.kind == "unknown")).startswith("ValueError")

    assert session.scalar(select(Promoter.pan).where(Promoter.rera_promoter_ref == "PR1")) == tokenize("pan", "AAAPA0001A")  # enriched, not erased
    assert session.scalar(select(Project.extended_end_date).where(Project.rera_reg_no == "P51700000002")) == date(2020, 6, 30)
    stages = dict(session.execute(select(Complaint.complaint_ref, Complaint.stage)).all())
    assert stages == {"CC001": "pending", "CC002": "order_issued"}
    # the complaint table had no promoter ID: each complaint took its project's promoter
    assert session.scalar(select(Promoter.name).join(Complaint, Complaint.promoter_id == Promoter.id)
                          .where(Complaint.complaint_ref == "CC002")) == "Shree Homes LLP"

    refresh(session, today=date(2026, 9, 1))
    snapshots = session.scalars(select(ScoreSnapshot)).all()
    pan_group = next(s.breakdown for s in snapshots if s.breakdown["schedule"]["extended"] == 1)
    assert pan_group["schedule"]["score"] == 50 and pan_group["schedule"]["median_months_extended"] == 18.0  # 547 days
    assert (pan_group["complaints"]["unresolved"], pan_group["overall"]) == (2, 25)


def test_a_projects_only_reply_still_imports(session, tmp_path):
    write(tmp_path, "projects.csv", PROJECTS)
    summary = run_ingest(FileImportAdapter(tmp_path), session, LocalRawStore(tmp_path / "raw"))
    assert summary.ok == 1 and session.scalar(select(Promoter.name).where(Promoter.rera_promoter_ref == "PR1")) == "Shree Realty LLP"
