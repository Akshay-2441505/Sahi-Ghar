from datetime import date
from pathlib import Path

import pytest

from sahighar.adapters.maharera_pages import (
    parse_certificate, parse_complaint_detail, parse_complaint_list, parse_project_list, promoter_ref,
)

FIXTURES = Path(__file__).parent / "fixtures" / "maharera"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def test_promoter_ref_ignores_case_spacing_and_punctuation_only():
    assert promoter_ref("GREEN SPACE INFRA VENTURES") == promoter_ref("  Green  Space Infra Ventures ")
    assert promoter_ref("Shree Realty LLP.") == promoter_ref("shree realty llp")
    assert promoter_ref("Shree Realty Pvt Ltd") != promoter_ref("Shree Realty Private Limited")  # never merged by guessing


def test_project_list_page_yields_cards_and_paging_info():
    page = parse_project_list(fixture("list_page1.html"))
    assert (page.total, page.pages) == (49450, 4945)
    assert len(page.cards) == 10
    first = page.cards[0]
    assert (first.reg_no, first.name, first.promoter_name, first.district, first.pincode) == (
        "P50500000005", "GREEN CITY 3", "GREEN SPACE INFRA VENTURES", "Nagpur", "441108")
    assert first.last_modified == date(2017, 5, 20) and first.cert_id == "1" and first.ext_cert_id is None


def test_cards_with_an_extension_certificate_carry_its_id():
    by_no = {c.reg_no: c for c in parse_project_list(fixture("list_page1.html")).cards}
    assert by_no["P51700002065"].ext_cert_id == "5" and by_no["P51700002065"].cert_id == "5"
    assert by_no["P51800002451"].ext_cert_id == "15"
    assert by_no["P50500000348"].ext_cert_id is None


def test_complaint_list_gives_promoter_ids_and_counts():
    page = parse_complaint_list(fixture("complaint_list.html"))
    assert page.total == 5382 and len(page.rows) == 10
    row = page.rows[2]
    assert (row.name, row.count, row.promoter_id) == ("ARJUN ANANT WAGHMARE", 4, "106973")


def test_complaint_detail_rows_keep_month_and_year_only():
    rows = parse_complaint_detail(fixture("complaint_detail.html"))
    assert len(rows) == 4
    first, last = rows[0], rows[-1]
    assert (first.promoter_name, first.project_no, first.district, first.complaint_no) == (
        "ARJUN ANANT WAGHMARE", "P51800004827", "Mumbai Suburban", "CC006000000057487")
    assert (first.year, first.month, first.status, first.non_execution_applied) == (2018, "December", "Order Approved", False)
    assert (last.complaint_no, last.year, last.month) == ("CC12400302", 2024, "October")


def test_old_format_registration_certificate_gives_the_original_end_date():
    cert = parse_certificate(fixture("cert_reg_5.html"))
    assert (cert.reg_no, cert.original_end, cert.current_end, cert.complete) == (
        "P51700002065", date(2018, 12, 31), date(2018, 12, 31), False)


def test_old_format_extension_certificate_gives_only_the_new_end_date():
    cert = parse_certificate(fixture("cert_ext_5.html"))
    assert (cert.reg_no, cert.original_end, cert.current_end, cert.complete) == (
        "P51700002065", None, date(2019, 12, 31), False)


def test_newer_format_certificate_has_the_original_and_current_dates_in_one_document():
    # the site serves this richer certificate (with the extension history) from either certificate endpoint
    cert = parse_certificate(fixture("cert_new_format.html"))
    assert (cert.reg_no, cert.original_end, cert.current_end, cert.complete) == (
        "P52100001400", date(2019, 12, 31), date(2027, 12, 31), True)


def test_newer_format_certificate_lists_each_extension_with_its_label():
    cert = parse_certificate(fixture("cert_new_format.html"))
    assert cert.extensions == [
        ("Extension-1", date(2020, 12, 30)), ("Covid Extension -2", date(2021, 3, 30)),
        ("Covid Extension -3", date(2021, 6, 30)), ("Covid Extension -4", date(2021, 12, 30)),
        ("Extension-5", date(2027, 12, 31))]
    assert parse_certificate(fixture("cert_reg_5.html")).extensions == []  # older formats carry no history


def test_abeyance_list_gives_the_certificate_numbers():
    from sahighar.adapters.maharera_pages import parse_abeyance_list
    assert parse_abeyance_list(fixture("status_abeyance.html")) == ["P52100005326", "P51900008342", "P52100009025", "P51800012235"]
    assert parse_abeyance_list("<div>nothing here</div>") == []


def test_nclt_list_gives_status_as_of_its_date_and_the_proposed_completion():
    from sahighar.adapters.maharera_pages import parse_nclt_list
    rows = parse_nclt_list(fixture("status_nclt.html"))
    assert (rows[0].reg_no, rows[0].status, rows[0].status_as_of, rows[0].proposed_completion, rows[0].form4_uploaded) == (
        "P51800008635", "Lapsed", date(2025, 1, 31), date(2021, 12, 30), False)
    assert len(rows) == 4


def test_a_response_without_a_certificate_is_not_an_error():
    assert parse_certificate("<div>No Record Found</div>") is None


def test_a_json_error_where_the_pdf_should_be_is_not_an_error_either():
    # the site sometimes answers {"status":"1","message":"can not fetch the object from repository"} instead of a PDF
    assert parse_certificate(fixture("cert_error_json.html")) is None


def test_a_pdf_that_does_not_look_like_a_certificate_is_an_error():
    import base64
    from pypdf import PdfWriter
    import io
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    html = f'<object data=data:application/pdf;base64,{base64.b64encode(buffer.getvalue()).decode()}>'
    with pytest.raises(ValueError, match="registration number"):
        parse_certificate(html)


def test_builder_search_cards_have_no_certificate_link_so_the_id_comes_from_the_view_link():
    # on the promoter search page the "Certificate" column is missing; the internal project id is in "View Details"
    cards = parse_project_list(fixture("promoter_list_page1.html")).cards
    assert len(cards) == 10 and all(c.cert_id for c in cards)
    assert [c.cert_id for c in cards][:4] == ["1", "3", "4", "5"]


def test_where_both_exist_the_certificate_id_equals_the_view_link_id():
    import re
    html = fixture("list_page1.html")
    blocks = html.split('class="row shadow p-3 mb-5 bg-body rounded"')[1:]
    first_view_ids = [re.search(r"/project/view/(\d+)", b).group(1) for b in blocks]  # each card links its view page twice
    cards = parse_project_list(html).cards
    assert [c.cert_id for c in cards] == first_view_ids
