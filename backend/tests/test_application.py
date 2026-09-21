import json

import pytest

from sahighar.adapters.application import extract_application, parse_application
from sahighar.privacy import tokenize
from tests.application_samples import COMPANY, FORBIDDEN, INDIVIDUAL, application_html, make_pdf


def test_the_test_pdf_helper_really_has_a_text_layer():
    from pypdf import PdfReader
    import io
    text = PdfReader(io.BytesIO(make_pdf("Name Acme Builders Pvt Ltd PAN Number AAAPA1234A"))).pages[0].extract_text()
    assert "Acme Builders Pvt Ltd" in text


def test_company_application_gives_org_details_member_tokens_address_and_past_projects():
    a = extract_application(COMPANY)
    assert (a["info_type"], a["org_name"], a["org_type"]) == ("organization", "Acme Builders Pvt Ltd", "Company")
    assert a["pan"] == tokenize("pan", "AAAPA1234A")
    assert a["members"] == [tokenize("pan", "BBBPB1234B"), tokenize("pan", "CCCPC1234C")]
    assert a["address"] == "Acme House, Acme Tech Park, Ring Road, Vimannagar, Pune, Pune, 411014"
    assert a["past_projects"] == [
        {"name": "Willow Court", "type": "Residential", "original_proposed": "2013-11-30", "actual": "2015-04-27"},
        {"name": "Eco Tower", "type": "Commercial", "original_proposed": "2014-08-20", "actual": "2016-11-29"},
        {"name": "Forest County", "type": "Residential", "original_proposed": "2017-12-31", "actual": "2017-04-10"},
    ]
    assert (a["project_status"], a["proposed_completion"], a["revised_completion"], a["litigation"]) == (
        "On-Going Project", "2016-12-16", "2018-12-31", True)


def test_individual_application_keeps_no_home_address_and_no_name():
    a = extract_application(INDIVIDUAL)
    assert a["info_type"] == "individual" and a["pan"] == tokenize("pan", "DDDPD1234D")
    assert a["address"] is None and a["members"] == [] and a["org_name"] is None
    assert a["past_projects"] == [{"name": "Lotus Meadows", "type": "Residential", "original_proposed": "2015-03-10", "actual": "2015-01-10"}]
    assert (a["project_status"], a["litigation"]) == ("Completed", False)


@pytest.mark.parametrize("text", [COMPANY, INDIVIDUAL])
def test_no_personal_identifier_survives_extraction(text):
    dump = json.dumps(extract_application(text))
    leaked = [s for s in FORBIDDEN if s in dump]
    assert leaked == []
    assert "Bank" not in dump and "@" not in dump


def test_an_application_with_no_recognisable_content_is_an_error():
    with pytest.raises(ValueError, match="not a registration application"):
        extract_application("Something else entirely")


def test_extract_from_the_sites_html_response():
    from sahighar.adapters.application import extract_application_from_html
    extract = extract_application_from_html(application_html(COMPANY).decode())
    assert extract["org_name"] == "Acme Builders Pvt Ltd"
    assert extract_application_from_html("<div>No Record Found</div>") is None


def test_parse_builds_a_promoter_record_from_tokens_only():
    extract = extract_application(COMPANY) | {"promoter_ref": "n:acme builders pvt ltd", "promoter_name": "ACME BUILDERS PVT LTD"}
    parsed = parse_application(extract)
    promoter = parsed.promoters[0]
    assert (promoter.ref, promoter.name) == ("n:acme builders pvt ltd", "ACME BUILDERS PVT LTD")
    assert promoter.pan == tokenize("pan", "AAAPA1234A")
    assert promoter.partners_or_directors == [tokenize("pan", "BBBPB1234B"), tokenize("pan", "CCCPC1234C")]
    assert promoter.registered_address.endswith("411014")


def test_llp_application_reads_the_organization_type_and_every_partner_in_both_tables():
    from tests.application_samples import FORBIDDEN_LLP, LLP
    a = extract_application(LLP)
    assert a["org_type"] == "Others" and a["pan"] == tokenize("pan", "AAAPA1234A")
    assert a["members"] == [tokenize("pan", p) for p in ("BBBPB1234B", "CCCPC1234C", "EEEPE1234E")]  # de-duplicated, in order
    assert a["past_projects"] == [] and a["address"].endswith("411001")
    assert not [w for w in FORBIDDEN_LLP if w in json.dumps(a)]


def test_a_masked_pan_is_never_tokenised():
    from tests.application_samples import MASKED
    a = extract_application(MASKED)
    assert a["pan"] is None and a["members"] == []  # xxxxxx234A cannot identify anyone
    assert a["org_type"] == "Company" and a["address"] is not None  # the rest is still useful
