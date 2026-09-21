import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from sahighar.adapters.tabular import parse_date, parse_month, parse_year, parse_yes_no, read_table, split_names


def test_reads_csv_with_a_bom_and_matches_headers_by_meaning():
    data = "﻿Project Registration Number,Project Name,Promoter ID,Ignored Column\nP1,Heights,PR1,x\n".encode("utf-8")
    table = read_table(data, "projects.csv")
    assert table.columns == ["reg_no", "name", "promoter_ref"]
    assert table.rows == [{"reg_no": "P1", "name": "Heights", "promoter_ref": "PR1"}]


def test_reads_windows_1252_csv_and_other_delimiters():
    data = "Promoter ID;Promoter Name\nPR1;Shree Réalty\n".encode("cp1252")
    assert read_table(data, "promoters.csv").rows == [{"promoter_ref": "PR1", "promoter_name": "Shree Réalty"}]


def test_a_complaints_project_no_is_not_a_project_registration_number():
    table = read_table(b"Complaint No.,Project No.,Complaint Status\nCC1,P1,Order Approved\n", "c.csv")
    assert table.columns == ["complaint_ref", "project_reg_no", "status"]
    projects = read_table(b"Project No.,Project Name,Promoter ID\nP1,Heights,PR1\n", "p.csv")
    assert projects.columns == ["reg_no", "name", "promoter_ref"]


def test_blank_rows_are_skipped_and_line_numbers_kept():
    table = read_table(b"Complaint No.,Complaint Status\nCC1,Order Approved\n,\nCC2,Hearing Scheduled\n", "c.csv")
    assert [r["complaint_ref"] for r in table.rows] == ["CC1", "CC2"]
    assert table.lines == [2, 4]


def test_reads_xlsx_and_keeps_date_cells_as_dates():
    wb = Workbook()
    ws = wb.active
    ws.append(["Project Registration Number", "Registration Valid Up To", "Year of Complaint Filing"])
    ws.append(["P1", datetime(2018, 12, 31), 2024.0])
    buffer = io.BytesIO()
    wb.save(buffer)
    table = read_table(buffer.getvalue(), "projects.xlsx")
    assert table.rows == [{"reg_no": "P1", "registration_end": date(2018, 12, 31), "filed_year": "2024"}]


def test_parse_date_is_day_first_and_never_guesses():
    assert parse_date("31/12/2018") == date(2018, 12, 31)
    assert parse_date("31-12-2018") == date(2018, 12, 31)
    assert parse_date("2018-12-31") == date(2018, 12, 31)
    assert parse_date(date(2018, 12, 31)) == date(2018, 12, 31)
    assert parse_date("") is None and parse_date(None) is None
    for bad in ("12/31/2018", "31/12/18", "soon", "31/13/2018"):
        with pytest.raises(ValueError):
            parse_date(bad)


def test_parse_month_year_and_yes_no():
    assert [parse_month(v) for v in ("March", "mar", "3", "03", "December")] == [3, 3, 3, 3, 12]
    assert parse_month("") is None
    with pytest.raises(ValueError):
        parse_month("13")
    assert parse_year("2024") == 2024 and parse_year("2024.0") == 2024 and parse_year("") is None
    with pytest.raises(ValueError):
        parse_year("24")
    assert [parse_yes_no(v) for v in ("Y", "yes", "N", "no", "", "1", "0")] == [True, True, False, False, False, True, False]
    with pytest.raises(ValueError):
        parse_yes_no("maybe")


def test_split_names_on_semicolon_bar_or_newline_but_not_comma():
    assert split_names("Ramesh Shah; Anil Mehta|Zed\nQ") == ["Ramesh Shah", "Anil Mehta", "Zed", "Q"]
    assert split_names("Shah, Ramesh") == ["Shah, Ramesh"]
    assert split_names("") == []
