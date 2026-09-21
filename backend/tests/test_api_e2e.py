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
    assert body["data_as_of"] and body["score_computed_at"]


def test_every_record_links_to_a_source(client, session):
    body = client.get(f"/projects/{_project_id(session, 'MH-1')}").json()
    records = body["schedule"] + body["complaints"] + body["possibly_related"] + body["group_promoters"]
    assert records
    for record in records:
        assert str(record["source_document_id"]) in body["sources"]
    assert body["complaints"][1]["order_url"] == "https://example.test/order/C2.pdf"


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
