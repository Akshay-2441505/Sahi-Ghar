from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sahighar.api.main import app
from sahighar.db.models import Project
from sahighar.db.session import get_session
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh
from tests.fakes import FakeAdapter
from tests.sample_data import DOC_1, DOC_2

@pytest.fixture
def client(session, tmp_path):
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _project_id(session, reg_no):
    return session.scalar(select(Project.id).where(Project.rera_reg_no == reg_no))


def test_trust_page_payload(client, session):
    r = client.get(f"/projects/{_project_id(session, 'MH-1')}")
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["name"] == "Shree Heights"
    assert {p["name"] for p in body["group_promoters"]} == {"Shree Realty LLP", "Shree Homes LLP"}
    assert body["score"]["schedule"]["score"] == 50
    assert body["score"]["complaints"]["score"] == 50
    assert body["score"]["overall"] == 50
    assert [p["name"] for p in body["possibly_related"]] == ["Shree Realty Phase 2 LLP"]
    assert body["possibly_related"][0]["evidence"]["same_address"] is True
    assert len(body["schedule"]) == 2  # possibly-related project is NOT counted
    assert body["group_basis"] == "same PAN"  # P1 and P2 are one group because the filings show the same PAN
    assert body["data_as_of"] and body["score_computed_at"]


def test_every_record_links_to_a_source(client, session):
    body = client.get(f"/projects/{_project_id(session, 'MH-1')}").json()
    records = body["schedule"] + body["complaints"] + body["possibly_related"] + body["group_promoters"]
    assert records
    for record in records:
        assert str(record["source_document_id"]) in body["sources"]
    assert body["complaints"][1]["order_url"] == "https://example.test/order/C2.pdf"


def test_declared_history_is_listed_once_with_its_source(client, session, tmp_path):
    past = [{"promoter_ref": "P1", "name": "Shree Old", "original_proposed": "2015-01-01", "actual": "2016-07-01"},
            {"promoter_ref": "P1", "name": "Shree Older", "original_proposed": "2012-01-01", "actual": "2012-01-01"}]
    run_ingest(FakeAdapter({"app1": {"past_projects": past}, "app2": {"past_projects": [{**past[0], "promoter_ref": "P2"}]}}),
               session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    body = client.get(f"/projects/{_project_id(session, 'MH-1')}").json()
    assert [d["name"] for d in body["declared_history"]] == ["Shree Older", "Shree Old"]  # oldest first; same project via P2 counted once
    assert body["declared_history"][1]["actual_completion_date"] == "2016-07-01"
    assert str(body["declared_history"][0]["source_document_id"]) in body["sources"]
    assert body["score"]["declared"]["total"] == 2


def test_regulator_notices_are_listed_for_the_groups_projects_only_with_their_source(client, session, tmp_path):
    notices = [{"reg_no": "MH-1", "kind": "abeyance", "promoter_ref": "P9"},  # our project: matched by its number
               {"reg_no": "MH-2", "kind": "nclt", "detail": {"status": "Lapsed", "status_as_of": "2025-01-31"}},
               {"reg_no": "MH-3", "kind": "abeyance", "promoter_ref": "P3"},  # a possibly-related builder: not this group's
               {"reg_no": "MH-800", "kind": "abeyance", "promoter_ref": "P2",  # this group's builder, project never in our search results
                "detail": {"project_name": "Shree Hidden", "district": "Pune"}},
               {"reg_no": "MH-999", "kind": "abeyance", "promoter_ref": "P9"}]
    run_ingest(FakeAdapter({"n1": {"project_flags": notices}}), session, LocalRawStore(tmp_path))
    body = client.get(f"/projects/{_project_id(session, 'MH-1')}").json()
    assert [(n["rera_reg_no"], n["project_name"], n["kind"], n["in_our_project_list"]) for n in body["status_notices"]] == [
        ("MH-1", "Shree Heights", "abeyance", True), ("MH-2", "Shree Gardens", "nclt", True), ("MH-800", "Shree Hidden", "abeyance", False)]
    assert body["status_notices"][1]["detail"]["status"] == "Lapsed"
    assert all(str(n["source_document_id"]) in body["sources"] for n in body["status_notices"])
    assert body["score"]["overall"] == 50  # notices are shown beside the score, never folded into it
    assert body["status_lists_as_of"] is None  # these test documents are not the regulator's lists, so "none listed" is never claimed


def test_notice_lists_as_of_is_the_older_of_the_two_lists_and_only_when_both_were_collected(client, session):
    from datetime import datetime
    from sahighar.db.models import SourceDocument

    def doc(kind, day):
        session.add(SourceDocument(origin="maharera-web", kind=kind, url=f"https://x.test/{kind}", fetched_at=datetime(2026, 9, day),
                                   sha256="0" * 64, content_type="text/html", store_key=kind, parse_status="ok"))
        session.commit()
    pid = _project_id(session, "MH-1")
    doc("status_abeyance", 20)
    assert client.get(f"/projects/{pid}").json()["status_lists_as_of"] is None  # only one of the two lists
    doc("status_nclt", 18)
    assert client.get(f"/projects/{pid}").json()["status_lists_as_of"].startswith("2026-09-18")


def test_search_matches_project_promoter_and_reg_no(client):
    def names(q):
        return {p["name"] for p in client.get("/search", params={"q": q}).json()["projects"]}

    assert names("shree") == {"Shree Heights", "Shree Gardens", "Shree Towers"}
    assert names("phase 2") == {"Shree Towers"}  # matched via promoter name
    assert names("mh-4") == {"Zenith One"}  # matched via RERA number
    assert names("50%") == set()  # % is literal, not a wildcard
    assert client.get("/search", params={"q": "a"}).status_code == 422


def test_promoter_endpoint_and_404s(client, session):
    promoter_id = session.scalar(select(Project.promoter_id).where(Project.rera_reg_no == "MH-1"))
    body = client.get(f"/promoters/{promoter_id}").json()
    assert body["score"]["overall"] == 50 and body["promoter"]["name"] == "Shree Realty LLP"
    assert client.get("/projects/9999").status_code == 404
    assert client.get("/promoters/9999").status_code == 404
