from datetime import date
from pathlib import Path

from sahighar.adapters.karnataka_pages import karnataka_complaint_stage, parse_complaint_detail, parse_complaint_index

FIXTURES = Path(__file__).parent / "fixtures" / "karnataka"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def test_complaint_index_gives_each_promoters_count_and_detail_page_token():
    rows = parse_complaint_index(fixture("complaint_index.html"))
    assert len(rows) == 6
    first = rows[0]
    assert (first.promoter_name, first.count) == ("SHRIRAM PROPERTIES PRIVATE LIMITED", 1)
    assert first.token == "okNvPWxTQ8l5UxjN066RAi61dZ51bfPfpZqiSd7McAInfGDPntG1oBc1ZHGnNelo"
    encoded = next(r for r in rows if r.promoter_name == "B.G. Ajaya Kumr Late B.G. Jayanna")
    assert encoded.token == "PawTu6noUQRTnbe1jdiED2dk1396RW%2BkJJZpA1J2opYQdonm5YXoK%2BvAv5EDMllf"  # kept percent-encoded, ready to reuse in a URL


def test_complaint_detail_rows_and_the_order_pdf_link_only_when_disposed():
    rows = parse_complaint_detail(fixture("complaint_detail_ishtika.html"))
    assert len(rows) == 3
    first = rows[0]
    assert (first.complaint_no, first.promoter_name, first.project_name, first.status) == (
        "00978/2023", "ISHTIKA HOMES PRIVATE LIMITED", "AGASTYA", "DISPOSED AUTHORITY FULLBENCH")
    assert (first.complaint_date, first.disposed_date) == (date(2023, 6, 27), date(2025, 7, 21))
    assert first.order_url == "/download_jc?DOC_ID=D0%2FTqCMP6lSd1eg8DCNsBQ%3D%3D"


def test_a_complaint_not_yet_disposed_has_no_order_link_and_no_disposed_date():
    rows = parse_complaint_detail(fixture("complaint_detail_lavanya.html"))
    posted = next(r for r in rows if r.status.startswith("POSTED"))
    assert posted.disposed_date is None and posted.order_url is None
    disposed = next(r for r in rows if r.status.startswith("DISPOSED"))
    assert disposed.order_url is not None


def test_under_enquiry_also_has_no_order_link():
    rows = parse_complaint_detail(fixture("complaint_detail_single.html"))
    assert len(rows) == 1 and rows[0].status == "UNDER ENQUIRY AUTHORITY FULLBENCH"
    assert rows[0].order_url is None and rows[0].disposed_date is None


def test_stage_mapping_is_conservative_unknown_statuses_are_other_never_guessed():
    assert karnataka_complaint_stage("DISPOSED AUTHORITY FULLBENCH") == "order_issued"
    assert karnataka_complaint_stage("DISPOSED AUTHORITY BENCH4") == "order_issued"
    assert karnataka_complaint_stage("DISPOSED AO") == "order_issued"
    assert karnataka_complaint_stage("UNDER ENQUIRY AUTHORITY FULLBENCH") == "pending"
    assert karnataka_complaint_stage("POSTED FOR ORDERS AUTHORITY BENCH4") == "pending"
    assert karnataka_complaint_stage("SOME NEW STATUS NEVER SEEN BEFORE") == "other"


def test_a_page_with_no_matching_rows_yields_nothing():
    assert parse_complaint_index("<div>nothing here</div>") == []
    assert parse_complaint_detail("<div>nothing here</div>") == []
