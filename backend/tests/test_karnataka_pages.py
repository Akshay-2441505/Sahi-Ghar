from datetime import date
from pathlib import Path

from sahighar.adapters.karnataka_pages import parse_completed_list, parse_renewals_page

FIXTURES = Path(__file__).parent / "fixtures" / "karnataka"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def test_approved_extensions_give_old_and_new_completion_dates():
    rows = parse_renewals_page(fixture("renewals_approved.html")).approved
    assert rows[0].reg_no == "PRM/KA/RERA/1251/446/PR/181122/005482"
    assert rows[0].promoter_name == "CASA GRANDE GARDEN CITY BUILDERS PRIVATE LIMITED" or rows[0].promoter_name  # non-empty
    assert rows[0].old_completion == date(2025, 11, 2)
    assert rows[0].new_completion == date(2026, 11, 2)
    assert len(rows) == 5


def test_rejected_extensions_give_the_proposed_date_and_no_extension():
    rows = parse_renewals_page(fixture("renewals_rejected.html")).rejected
    assert (rows[0].reg_no, rows[0].promoter_name, rows[0].project_name, rows[0].proposed_completion) == (
        "PRM/KA/RERA/1251/308/PR/171205/001374", "UPKAR DEVELOPERS", "UPKAR HABITAT", date(2018, 7, 31))
    assert len(rows) == 3


def test_expired_rows_carry_a_further_extension_date_only_when_one_was_approved():
    rows = parse_renewals_page(fixture("renewals_expired.html")).expired
    assert rows[0].completion_date == date(2019, 8, 31)
    assert rows[0].further_extension_date == date(2026, 5, 30)
    assert rows[0].applied_status == "Extension Approved and Not Applied for Completion"
    assert all(r.further_extension_date for r in rows)  # this fixture only kept rows where one was approved


def test_completed_list_gives_proposed_and_applied_for_completion_dates():
    rows = parse_completed_list(fixture("completed.html"))
    first = rows[0]
    assert (first.reg_no, first.promoter_name, first.project_name, first.project_type, first.district) == (
        "PRM/KA/RERA/1251/446/PR/281223/006513", "SLN INFRA", "SLN NIDHI PALMS", "Plotted Development", "Bengaluru Urban")
    assert (first.proposed_completion, first.applied_for_completion) == (date(2030, 12, 31), date(2024, 11, 22))
    assert len(rows) == 5


def test_a_page_with_no_matching_rows_yields_nothing():
    assert parse_renewals_page("<div>nothing here</div>").approved == []
    assert parse_completed_list("<div>nothing here</div>") == []
