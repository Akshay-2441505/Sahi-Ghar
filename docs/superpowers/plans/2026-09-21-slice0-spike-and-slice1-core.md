# Sahi Ghar — Slice 0 (Access Spike) + Slice 1 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything in slice 1 that does not depend on which files MahaRERA eventually provides (slice 0, the access spike, is already done and decided the data path): raw store, schema, ingest runner, promoter grouping, trust score v1, API, and the search + trust-page frontend, proven end to end on fixture data.

**Architecture:** Source-agnostic adapters yield raw documents; a runner stores them raw-first (content-addressed) and parses them into Postgres with every row tagged by its `source_document_id`. Grouping and scoring are pure functions over those rows; a FastAPI service serves a trust payload where every figure resolves to a stored source; a React page renders it. The MahaRERA adapter itself is deliberately **not** in this plan (see "Plan B").

**Tech Stack:** Python 3.11+ (uv), FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite for unit tests), rapidfuzz, httpx; React 19 + Vite + Tailwind 4 + React Router, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-21-sahi-ghar-design.md` (amended 2026-09-21; this plan implements the amended version: `discover()`/`parse()` adapter interface, official-data-only path, registration-end-date schedule, complaint stages, address+name grouping rule, projects-only `/search`).

## Global Constraints

Every task's requirements implicitly include these (copied from the spec).

- Stack: Python + FastAPI + PostgreSQL backend; React + Vite + Tailwind frontend.
- **No CAPTCHA solving or bypass, ever.** If a page is CAPTCHA-gated, the spike records it and stops on that page.
- **Official data only: no code in this repository fetches from any RERA website** (owner decision 2026-09-21). Data enters through the file-import adapter (Plan B) or test fixtures.
- Every parsed row carries `source_document_id`; every figure on the trust page links to its source document; every page states "data as of" a date.
- Adapters never touch the database; `parse()` is a pure function of the raw document (no network, no database).
- Fields a source does not publish stay nullable, and rules that depend on them degrade gracefully.
- Grouping: `filing_confirmed` (same PAN) links feed the registration schedule and the score; `possible` links (partner overlap plus address or name; or same address plus similar name) are shown separately, labelled "not counted in this score", and never counted.
- The registration schedule is measured against the **original** registration end date; an extension date is shown beside it, never used to hide it. Never call a project "late" or "delayed": open data has no completion status, an extension is not necessarily the promoter's fault, and a project past its end date may already be complete.
- Complaint statuses are stored exactly as published; the stage mapping (`complaint_stage`) is the only interpretation, unknown statuses map to `other`, and the source's year and month are never turned into a day.
- Trust score v1 is a scored checklist, not ML; every tunable number lives in `backend/sahighar/scoring/v1.py`. The overall number is never shown without its breakdown.
- Wording is neutral and stays within what RERA data says: no verdicts, no ads, no "featured" builders.
- All `DateTime` columns store naive UTC (`sahighar.util.utcnow`).
- Dev API port is **8010** (8000 is used by another project on this machine); the frontend calls `/api/...` and the Vite dev proxy strips `/api`.
- **No GitHub repo, remote or push is created by the agent.** The user supplies a repo at the end of the project; anything that needs GitHub (for example CI) is queued until then.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` when Claude makes the commit.

## Environment notes

- Repo root: `C:\Users\aakur\OneDrive\Desktop\Sahi Ghar`. Commands below are bash (Git Bash) from the repo root unless a step says `cd backend` or `cd frontend`.
- Verified available: Python 3.13, uv 0.10, Node 22, npm 10, Docker 29. `psql` is not installed; use `docker exec` when a psql prompt is needed.
- The repo sits inside OneDrive. `backend/.venv` and `frontend/node_modules` are large and churn; consider pausing OneDrive sync for this folder or moving the repo out of OneDrive before Task 6.
- Vitest's default forked workers time out on this machine; `pool: 'threads'` is set in `vite.config.ts` (Task 14).

## File structure

```
spike/                          THROWAWAY, already committed: probe.py, test_probe.py, samples/
docs/spikes/2026-09-maharera-access.md      the spike report and decision (done)
backend/
  pyproject.toml
  alembic.ini, alembic/                     migrations (Task 8)
  sahighar/
    util.py                                 utcnow()
    rawstore.py                             RawStore protocol + LocalRawStore
    db/models.py, db/session.py
    adapters/base.py                        RawDoc, *Rec, ParsedRecords, Adapter protocol
    ingest/runner.py                        run_ingest, reparse_all
    resolve/grouping.py                     resolve_groups (pure), rebuild_groups
    scoring/v1.py                           classify, score (pure)
    scoring/service.py                      compute_scores, refresh
    api/main.py, api/payload.py
  tests/                                    conftest, fakes, sample_data, test_*.py, seed_demo.py
frontend/
  src/api.ts, format.ts
  src/components/SourceLink.tsx, ScoreBreakdown.tsx
  src/pages/Search.tsx, TrustPage.tsx, TrustPage.test.tsx
```

## Plan B (written after the spike, NOT in this plan)

The file-import adapter for the data the owner obtains (parsers and fixtures modelled on the real formats in `spike/samples/`, plus a draft data request or RTI naming the fields the spike found), the S3-compatible `RawStore` that streams large bodies to disk, deployment (Neon/Render/Vercel/R2), and the three-builder manual cross-check. There is no scheduled scraper. They depend on what data actually arrives, so writing them now would target an unknown format.

---

## Part 1 — Slice 0: Access spike — COMPLETED 2026-09-21

Tasks 1-5 (probe tool, MahaRERA findings, runner check, Karnataka/Telangana/rera-india, decision) are done and committed on the local branch `slice0-spike-and-core`. **Do not redo them.** Read `docs/spikes/2026-09-maharera-access.md` first; the outcome that shapes everything below:

- **Path B, by the owner's decision: official data only. No code in this repository fetches from any RERA website.** The first real adapter is a file-import adapter for data the owner obtains by data request or RTI (Plan B).
- Maharashtra's open pages showed which fields exist (registration and extension end dates from certificates, complaints with status and non-execution flags, promoter name and registered office). The CAPTCHA-gated detail app (PAN, partners, completion status) is off-limits.
- **Delivery metric:** registration end dates (registered until; extended by N months or not extended), never "on time / late". **Complaints:** the site's stages (order issued, pending) plus non-execution requests. **Grouping:** PAN and partner rules stay (dormant without that data), plus a same-address and similar-name rule.
- Task 3 (GitHub runner reachability) is **obsolete**: there is no scheduled scrape.
- `spike/` (probe tool and `samples/`) stays in the repo as throwaway evidence. `spike/samples/` shows the real page formats and can seed test fixtures for Plan B's parsers.

---

## Part 2 — Slice 1 core (source-independent)

All tasks below run on fixture data and need nothing from MahaRERA. Backend commands run from `backend/`.

### Task 6: Backend scaffold and raw store

**Files:**
- Create: `backend/pyproject.toml`, `backend/sahighar/__init__.py`, `backend/sahighar/util.py`, `backend/sahighar/rawstore.py`, `backend/tests/__init__.py`
- Test: `backend/tests/test_rawstore.py`

**Interfaces:**
- Produces: `utcnow() -> datetime` (naive UTC); `RawStore` protocol (`put(data: bytes) -> str`, `get(key: str) -> bytes`); `LocalRawStore(root: Path)` where the key is the sha256 hex of the content.

- [ ] **Step 1: Scaffold the project**

Create `backend/pyproject.toml`:

```toml
[project]
name = "sahighar"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "httpx>=0.27",
    "rapidfuzz>=3.9",
    "uvicorn>=0.30",
    "psycopg[binary]>=3.2",
]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create empty files `backend/sahighar/__init__.py` and `backend/tests/__init__.py`. Create `backend/sahighar/util.py`:

```python
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC. All DateTime columns store naive UTC so SQLite and Postgres agree."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

The root `.gitignore` (already committed) covers `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `raw_store/` and `.env`; confirm with `cat .gitignore` and add any that are missing.

Run: `cd backend && uv sync`
Expected: dependencies resolve and install, creating `backend/uv.lock`.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_rawstore.py`:

```python
from sahighar.rawstore import LocalRawStore


def test_rawstore_roundtrip_and_dedupe(tmp_path):
    store = LocalRawStore(tmp_path)
    key = store.put(b"hello")
    assert store.put(b"hello") == key
    assert store.get(key) == b"hello"
    assert len(list(tmp_path.rglob("*.gz"))) == 1
    assert store.put(b"other") != key
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_rawstore.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.rawstore'`

- [ ] **Step 4: Write the raw store**

Create `backend/sahighar/rawstore.py`:

```python
import gzip
import hashlib
from pathlib import Path
from typing import Protocol


class RawStore(Protocol):
    def put(self, data: bytes) -> str:
        """Store bytes, return the key (content-addressed, so re-putting is a no-op)."""

    def get(self, key: str) -> bytes: ...


class LocalRawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.gz"

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(data))
        return key

    def get(self, key: str) -> bytes:
        return gzip.decompress(self._path(key).read_bytes())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_rawstore.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add backend .gitignore
git commit -m "backend: scaffold project and add content-addressed raw store"
```

### Task 7: Database models and test session

**Files:**
- Create: `backend/sahighar/db/__init__.py`, `backend/sahighar/db/models.py`, `backend/sahighar/db/session.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `sahighar.util.utcnow` (test only).
- Produces: ORM classes `Base`, `SourceDocument`, `Promoter`, `PromoterGroup`, `GroupMembership`, `Project`, `Complaint`, `ScoreSnapshot` with the columns shown below; `get_session()` FastAPI dependency reading `DATABASE_URL`; a pytest fixture `session` (in-memory SQLite, tables created).

Before writing: skim the field lists in `docs/spikes/2026-09-maharera-access.md` (rows 4-5). The models below already follow the owner's decisions recorded there; if a field the scoring or grouping rules need is missing from them, stop and raise it with the user rather than improvising.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sahighar.db.models import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        yield s
```

Create `backend/tests/test_models.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from sahighar.db.models import Project, Promoter, SourceDocument
from sahighar.util import utcnow


def _doc(session):
    sd = SourceDocument(origin="t", kind="project", url="u", fetched_at=utcnow(), sha256="a" * 64,
                        content_type="text/html", store_key="a" * 64)
    session.add(sd)
    session.flush()
    return sd


def test_natural_keys_are_unique(session):
    sd = _doc(session)
    pr = Promoter(state="MH", rera_promoter_ref="P1", name="X", source_document_id=sd.id)
    session.add(pr)
    session.flush()
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="A", source_document_id=sd.id))
    session.flush()
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="B", source_document_id=sd.id))
    with pytest.raises(IntegrityError):
        session.flush()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.db'`

- [ ] **Step 3: Write the models and session**

Create empty `backend/sahighar/db/__init__.py`. Create `backend/sahighar/db/models.py`:

```python
from datetime import date, datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (UniqueConstraint("url", "sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str]  # adapter origin label, e.g. "maharera-web", "file-import"
    kind: Mapped[str]  # "project" | "promoter" | "complaints"
    url: Mapped[str]  # for file imports use a "file:<name>" label
    fetched_at: Mapped[datetime]
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str]
    store_key: Mapped[str]
    parse_status: Mapped[str] = mapped_column(default="pending")  # pending | ok | failed
    parse_error: Mapped[str | None]


class Promoter(Base):
    __tablename__ = "promoter"
    __table_args__ = (UniqueConstraint("state", "rera_promoter_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2))  # MH | KA | TG
    rera_promoter_ref: Mapped[str]
    name: Mapped[str]
    pan: Mapped[str | None]
    registered_address: Mapped[str | None]
    partners_or_directors: Mapped[list | None] = mapped_column(Json)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class PromoterGroup(Base):
    __tablename__ = "promoter_group"

    id: Mapped[int] = mapped_column(primary_key=True)


class GroupMembership(Base):
    __tablename__ = "group_membership"

    group_id: Mapped[int] = mapped_column(ForeignKey("promoter_group.id"), primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"), primary_key=True)
    link_type: Mapped[str]  # filing_confirmed | possible
    evidence: Mapped[dict] = mapped_column(Json)


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("state", "rera_reg_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(2))
    rera_reg_no: Mapped[str]
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    name: Mapped[str]
    city: Mapped[str | None]
    locality: Mapped[str | None]
    configurations: Mapped[list | None] = mapped_column(Json)
    carpet_area_range: Mapped[str | None]
    registration_end_date: Mapped[date | None]  # end of the original registration validity
    extended_end_date: Mapped[date | None]  # only when an extension certificate exists
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class Complaint(Base):
    __tablename__ = "complaint"
    __table_args__ = (UniqueConstraint("promoter_id", "complaint_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"))
    complaint_ref: Mapped[str]
    status: Mapped[str]  # raw text as published
    stage: Mapped[str]  # order_issued | pending | other
    non_execution_applied: Mapped[bool] = mapped_column(default=False)
    filed_year: Mapped[int | None]
    filed_month: Mapped[int | None]
    order_url: Mapped[str | None]
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("promoter_group.id"))
    computed_at: Mapped[datetime]
    breakdown: Mapped[dict] = mapped_column(Json)
    input_source_document_ids: Mapped[list] = mapped_column(Json)
```

Create `backend/sahighar/db/session.py`:

```python
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def _sessionmaker() -> sessionmaker:
    return sessionmaker(create_engine(os.environ["DATABASE_URL"]))


def get_session():
    with _sessionmaker()() as session:
        yield session
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "backend: add schema models and test session fixture"
```

### Task 8: Alembic migration on real Postgres

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/` (generated), `backend/alembic/versions/<rev>_initial_schema.py` (generated)
- Modify: `backend/alembic/env.py`, `backend/pyproject.toml` (Postgres driver)

**Interfaces:**
- Consumes: `sahighar.db.models.Base`.
- Produces: `alembic upgrade head` creates the schema on Postgres; `DATABASE_URL` selects the database. Dev database: `postgresql+psycopg://postgres:dev@localhost:5433/sahighar`.

- [ ] **Step 1: Start a throwaway Postgres**

```bash
docker rm -f sahighar-pg >/dev/null 2>&1
docker run -d --name sahighar-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=sahighar -p 5433:5432 postgres:16
```

Wait ~5 seconds for it to accept connections.

- [ ] **Step 2: Add the driver and initialise Alembic**

```bash
cd backend
uv add "psycopg[binary]>=3.2"
uv run alembic init alembic
```

Edit `backend/alembic/env.py`: add `import os` as the first line, and replace the line `target_metadata = None` with:

```python
from sahighar.db.models import Base  # noqa: E402

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
```

- [ ] **Step 3: Generate the initial migration**

Shell environment variables do not persist between separate commands, so `DATABASE_URL` is set inline on every command below.

```bash
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run alembic revision --autogenerate -m "initial schema"
```

Expected: `Detected added table` lines for all 7 tables and a new file in `alembic/versions/`. Open it and confirm the JSON columns are `postgresql.JSONB`.

- [ ] **Step 4: Prove upgrade, downgrade and re-upgrade work**

```bash
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run alembic upgrade head \
  && DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run alembic downgrade base \
  && DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run alembic upgrade head
docker exec sahighar-pg psql -U postgres -d sahighar -c '\dt'
```

Expected: no errors; `\dt` lists `alembic_version, complaint, group_membership, project, promoter, promoter_group, score_snapshot, source_document`.

- [ ] **Step 5: Confirm the unit tests still pass, stop the container, commit**

```bash
uv run pytest -q
docker rm -f sahighar-pg
```

```bash
git add backend
git commit -m "backend: add Alembic with initial schema migration"
```

### Task 9: Adapter interface and ingest runner

**Files:**
- Create: `backend/sahighar/adapters/__init__.py`, `backend/sahighar/adapters/base.py`, `backend/sahighar/ingest/__init__.py`, `backend/sahighar/ingest/runner.py`, `backend/tests/fakes.py`
- Test: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: models from Task 7, `RawStore` from Task 6.
- Produces:
  - `RawDoc(origin, kind, url, fetched_at, content_type, data)`, `PromoterRec`, `ProjectRec` (with `registration_end`, `extended_end`), `ComplaintRec` (raw `status`, `stage`, `non_execution_applied`, `filed_year`, `filed_month`), `ParsedRecords`, `complaint_stage(status) -> str` ("Order Approved" is `order_issued`; "Hearing Scheduled" and "Roznama Approved" are `pending`; anything else `other`), `Adapter` protocol (`state`, `origin`, `discover() -> Iterable[RawDoc]`, `parse(doc) -> ParsedRecords`).
  - `run_ingest(adapter, session, store, max_failure_rate=0.05) -> IngestSummary(total, ok, failed)`; raises `IngestFailureRateExceeded`.
  - `reparse_all(adapter, session, store, max_failure_rate=0.05) -> IngestSummary`.
  - Test double `tests.fakes.FakeAdapter(payloads: dict[str, dict])`.

- [ ] **Step 1: Write the failing test and the test double**

Create `backend/tests/fakes.py`:

```python
import json
from datetime import date

from sahighar.adapters.base import ComplaintRec, ParsedRecords, ProjectRec, PromoterRec, RawDoc, complaint_stage
from sahighar.util import utcnow


def _d(value):
    return date.fromisoformat(value) if value else None


class FakeAdapter:
    """Test double. Each payload is a JSON document {promoters, projects, complaints} keyed by url."""

    state = "MH"
    origin = "fake"

    def __init__(self, payloads: dict[str, dict]):
        self.payloads = payloads

    def discover(self):
        for url, payload in self.payloads.items():
            yield RawDoc(self.origin, "project", url, utcnow(), "application/json", json.dumps(payload).encode())

    def parse(self, doc: RawDoc) -> ParsedRecords:
        d = json.loads(doc.data)
        return ParsedRecords(
            promoters=[PromoterRec(**x) for x in d.get("promoters", [])],
            projects=[
                ProjectRec(**{**x, "registration_end": _d(x.get("registration_end")), "extended_end": _d(x.get("extended_end"))})
                for x in d.get("projects", [])
            ],
            complaints=[ComplaintRec(**{**x, "stage": complaint_stage(x["status"])}) for x in d.get("complaints", [])],
        )
```

Create `backend/tests/test_runner.py`:

```python
import pytest
from sqlalchemy import delete, select

from sahighar.db.models import Complaint, Project, Promoter, SourceDocument
from sahighar.ingest.runner import IngestFailureRateExceeded, reparse_all, run_ingest
from sahighar.rawstore import LocalRawStore
from tests.fakes import FakeAdapter

GOOD = {
    "promoters": [{"ref": "P1", "name": "Shree Realty LLP"}],
    "projects": [{"reg_no": "R1", "promoter_ref": "P1", "name": "Heights", "registration_end": "2022-01-01"}],
    "complaints": [{"ref": "C1", "promoter_ref": "P1", "status": "Hearing Scheduled", "project_reg_no": "R1"}],
}
ORPHAN = {"projects": [{"reg_no": "R9", "promoter_ref": "NOPE", "name": "Ghost"}]}


def test_ingest_stores_raw_and_tags_every_row_with_its_source(session, tmp_path):
    store = LocalRawStore(tmp_path)
    summary = run_ingest(FakeAdapter({"u1": GOOD}), session, store)
    assert (summary.total, summary.ok, summary.failed) == (1, 1, 0)
    sd = session.scalar(select(SourceDocument))
    assert sd.parse_status == "ok" and store.get(sd.store_key)
    for model in (Promoter, Project, Complaint):
        assert session.scalar(select(model)).source_document_id == sd.id
    assert session.scalar(select(Complaint)).project_id == session.scalar(select(Project.id))


def test_ingest_is_idempotent(session, tmp_path):
    store = LocalRawStore(tmp_path)
    for _ in range(2):
        run_ingest(FakeAdapter({"u1": GOOD}), session, store)
    assert len(session.scalars(select(SourceDocument)).all()) == 1
    assert len(session.scalars(select(Project)).all()) == 1


def test_one_bad_document_does_not_stop_the_run(session, tmp_path):
    adapter = FakeAdapter({"u1": GOOD, "u2": ORPHAN})
    summary = run_ingest(adapter, session, LocalRawStore(tmp_path), max_failure_rate=1.0)
    assert (summary.ok, summary.failed) == (1, 1)
    bad = session.scalar(select(SourceDocument).where(SourceDocument.url == "u2"))
    assert bad.parse_status == "failed" and "unknown promoter" in bad.parse_error
    assert session.scalar(select(Project.rera_reg_no)) == "R1"


def test_failure_rate_over_threshold_raises(session, tmp_path):
    with pytest.raises(IngestFailureRateExceeded):
        run_ingest(FakeAdapter({"u1": GOOD, "u2": ORPHAN}), session, LocalRawStore(tmp_path))


def test_reparse_rebuilds_records_from_stored_raw_without_network(session, tmp_path):
    store = LocalRawStore(tmp_path)
    adapter = FakeAdapter({"u1": GOOD})
    run_ingest(adapter, session, store)
    for model in (Complaint, Project, Promoter):
        session.execute(delete(model))
    session.commit()
    adapter.payloads = {}  # nothing to discover: parsing must use the stored bytes
    summary = reparse_all(adapter, session, store)
    assert summary.ok == 1
    assert session.scalar(select(Project.rera_reg_no)) == "R1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.adapters'`

- [ ] **Step 3: Write the adapter interface**

Create empty `backend/sahighar/adapters/__init__.py` and `backend/sahighar/ingest/__init__.py`. Create `backend/sahighar/adapters/base.py`:

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Protocol


@dataclass(frozen=True)
class RawDoc:
    origin: str  # adapter origin label
    kind: str  # "project" | "promoter" | "complaints"
    url: str  # "file:<name>" for file imports
    fetched_at: datetime
    content_type: str
    data: bytes


@dataclass
class PromoterRec:
    ref: str
    name: str
    pan: str | None = None
    registered_address: str | None = None
    partners_or_directors: list[str] | None = None


@dataclass
class ProjectRec:
    reg_no: str
    promoter_ref: str
    name: str
    city: str | None = None
    locality: str | None = None
    configurations: list[str] | None = None
    carpet_area_range: str | None = None
    registration_end: date | None = None  # end of the original registration validity
    extended_end: date | None = None  # new end date, only if an extension certificate exists


@dataclass
class ComplaintRec:
    ref: str
    promoter_ref: str
    status: str  # raw text exactly as published, e.g. "Order Approved"
    stage: str  # order_issued | pending | other  (see complaint_stage)
    non_execution_applied: bool = False  # a buyer asked to enforce an order that was not complied with
    project_reg_no: str | None = None
    filed_year: int | None = None  # the source publishes year and month only
    filed_month: int | None = None
    order_url: str | None = None


@dataclass
class ParsedRecords:
    promoters: list[PromoterRec] = field(default_factory=list)
    projects: list[ProjectRec] = field(default_factory=list)
    complaints: list[ComplaintRec] = field(default_factory=list)


_STAGES = {"order approved": "order_issued", "hearing scheduled": "pending", "roznama approved": "pending"}


def complaint_stage(status: str) -> str:
    """Map a published complaint status to a stage. Unknown statuses are 'other', never guessed."""
    return _STAGES.get(status.strip().lower(), "other")


class Adapter(Protocol):
    """One implementation per (state, source path).

    Contract: `discover()` yields every raw document the source provides, and a
    promoter is always introduced (a PromoterRec in some earlier or the same
    document's `parse()` result) before any project or complaint that references it.
    `parse()` is a pure function of the document: no network, no database.
    """

    state: str  # "MH" | "KA" | "TG"
    origin: str

    def discover(self) -> Iterable[RawDoc]: ...

    def parse(self, doc: RawDoc) -> ParsedRecords: ...
```

- [ ] **Step 4: Write the runner**

Create `backend/sahighar/ingest/runner.py`:

```python
import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.adapters.base import Adapter, ParsedRecords, RawDoc
from sahighar.db.models import Complaint, Project, Promoter, SourceDocument
from sahighar.rawstore import RawStore


@dataclass
class IngestSummary:
    total: int = 0
    ok: int = 0
    failed: int = 0


class IngestFailureRateExceeded(Exception):
    def __init__(self, summary: IngestSummary):
        super().__init__(f"{summary.failed} of {summary.total} documents failed to parse")
        self.summary = summary


def _upsert(session: Session, model, keys: dict, values: dict):
    row = session.scalar(select(model).filter_by(**keys))
    if row is None:
        row = model(**keys)
        session.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    return row


def _promoter_id(session: Session, state: str, ref: str) -> int:
    pid = session.scalar(select(Promoter.id).where(Promoter.state == state, Promoter.rera_promoter_ref == ref))
    if pid is None:
        raise ValueError(f"unknown promoter ref {ref!r} (adapter must introduce promoters first)")
    return pid


def _apply(session: Session, state: str, sd_id: int, parsed: ParsedRecords) -> None:
    for p in parsed.promoters:
        _upsert(
            session, Promoter, {"state": state, "rera_promoter_ref": p.ref},
            {"name": p.name, "pan": p.pan, "registered_address": p.registered_address,
             "partners_or_directors": p.partners_or_directors, "source_document_id": sd_id},
        )
    for j in parsed.projects:
        _upsert(
            session, Project, {"state": state, "rera_reg_no": j.reg_no},
            {"promoter_id": _promoter_id(session, state, j.promoter_ref), "name": j.name,
             "city": j.city, "locality": j.locality, "configurations": j.configurations,
             "carpet_area_range": j.carpet_area_range, "registration_end_date": j.registration_end,
             "extended_end_date": j.extended_end, "source_document_id": sd_id},
        )
    for c in parsed.complaints:
        promoter_id = _promoter_id(session, state, c.promoter_ref)
        project_id = None
        if c.project_reg_no:
            project_id = session.scalar(
                select(Project.id).where(Project.state == state, Project.rera_reg_no == c.project_reg_no)
            )
        _upsert(
            session, Complaint, {"promoter_id": promoter_id, "complaint_ref": c.ref},
            {"project_id": project_id, "status": c.status, "stage": c.stage,
             "non_execution_applied": c.non_execution_applied, "filed_year": c.filed_year,
             "filed_month": c.filed_month, "order_url": c.order_url, "source_document_id": sd_id},
        )


def _process(session: Session, adapter: Adapter, sd_id: int, doc: RawDoc) -> bool:
    """Parse one stored document. A failure marks that document failed and never stops the run."""
    try:
        _apply(session, adapter.state, sd_id, adapter.parse(doc))
        sd = session.get(SourceDocument, sd_id)
        sd.parse_status, sd.parse_error = "ok", None
        session.commit()
        return True
    except Exception as exc:  # deliberate: per-document failure isolation
        session.rollback()
        sd = session.get(SourceDocument, sd_id)
        sd.parse_status, sd.parse_error = "failed", f"{type(exc).__name__}: {exc}"[:1000]
        session.commit()
        return False


def _record_doc(session: Session, doc: RawDoc, store: RawStore) -> tuple[int, bool]:
    """Store the raw bytes and upsert the source_document row. Returns (id, already_parsed_ok)."""
    sha = hashlib.sha256(doc.data).hexdigest()
    sd = session.scalar(select(SourceDocument).where(SourceDocument.url == doc.url, SourceDocument.sha256 == sha))
    if sd is None:
        sd = SourceDocument(
            origin=doc.origin, kind=doc.kind, url=doc.url, sha256=sha,
            content_type=doc.content_type, store_key=store.put(doc.data), fetched_at=doc.fetched_at,
        )
        session.add(sd)
    else:
        sd.fetched_at = doc.fetched_at  # re-fetched unchanged content: freshness moves, data does not
    session.commit()
    return sd.id, sd.parse_status == "ok"


def _check(summary: IngestSummary, max_failure_rate: float) -> IngestSummary:
    if summary.total and summary.failed / summary.total > max_failure_rate:
        raise IngestFailureRateExceeded(summary)
    return summary


def run_ingest(adapter: Adapter, session: Session, store: RawStore, max_failure_rate: float = 0.05) -> IngestSummary:
    summary = IngestSummary()
    for doc in adapter.discover():
        summary.total += 1
        sd_id, parsed_ok = _record_doc(session, doc, store)
        if parsed_ok or _process(session, adapter, sd_id, doc):
            summary.ok += 1
        else:
            summary.failed += 1
    return _check(summary, max_failure_rate)


def reparse_all(adapter: Adapter, session: Session, store: RawStore, max_failure_rate: float = 0.05) -> IngestSummary:
    """Re-run the parser over stored raw documents (after a parser fix). No network."""
    summary = IngestSummary()
    rows = session.scalars(
        select(SourceDocument).where(SourceDocument.origin == adapter.origin).order_by(SourceDocument.id)
    ).all()
    for sd in rows:
        doc = RawDoc(sd.origin, sd.kind, sd.url, sd.fetched_at, sd.content_type, store.get(sd.store_key))
        summary.total += 1
        if _process(session, adapter, sd.id, doc):
            summary.ok += 1
        else:
            summary.failed += 1
    return _check(summary, max_failure_rate)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: `7 passed` (1 rawstore, 1 models, 5 runner)

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "backend: add adapter interface and raw-first ingest runner"
```

### Task 10: Trust score v1

**Files:**
- Create: `backend/sahighar/scoring/__init__.py`, `backend/sahighar/scoring/v1.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Produces: `ProjectFacts(registration_end, extended_end)`; `ComplaintFacts(stage, non_execution_applied)`; `classify(p, today) -> (outcome, months_extended | None)` with outcome in `extended | not_extended | within_registration | unknown`; `score(projects, complaints, today) -> dict` with keys `schedule`, `complaints`, `progress`, `overall` (shapes visible in the code below and consumed verbatim by the frontend `Score` type in Task 14).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scoring.py`:

```python
from datetime import date

from sahighar.adapters.base import complaint_stage
from sahighar.scoring.v1 import ComplaintFacts as C
from sahighar.scoring.v1 import ProjectFacts as P
from sahighar.scoring.v1 import classify, score

TODAY = date(2026, 9, 1)


def test_classify_is_measured_against_the_original_end_date():
    assert classify(P(date(2022, 1, 1), date(2023, 1, 1)), TODAY) == ("extended", 12.0)
    assert classify(P(date(2022, 1, 1), None), TODAY) == ("not_extended", None)
    assert classify(P(date(2027, 1, 1), None), TODAY) == ("within_registration", None)


def test_extension_counts_even_if_the_original_date_has_not_passed():
    assert classify(P(date(2027, 1, 1), date(2027, 7, 1)), TODAY)[0] == "extended"


def test_unknown_when_data_missing_or_nonsensical():
    assert classify(P(None, None), TODAY) == ("unknown", None)
    assert classify(P(date(2022, 1, 1), date(2021, 1, 1)), TODAY)[0] == "not_extended"  # "extension" that moves earlier


def test_complaint_stage_maps_known_statuses_and_never_guesses():
    assert complaint_stage("Order Approved") == "order_issued"
    assert complaint_stage("  hearing scheduled ") == "pending"
    assert complaint_stage("Roznama Approved") == "pending"
    assert complaint_stage("Something New") == "other"


def test_score_with_history_and_complaints():
    projects = [P(date(2022, 1, 1), None), P(date(2022, 1, 1), None), P(date(2022, 1, 1), date(2023, 1, 1))]
    complaints = [C("pending", False), C("order_issued", False), C("order_issued", True)]
    s = score(projects, complaints, TODAY)
    assert s["schedule"]["score"] == 67 and s["schedule"]["extended"] == 1 and s["schedule"]["median_months_extended"] == 12.0
    assert s["complaints"]["unresolved"] == 2  # one pending, one order not executed
    assert (s["complaints"]["total"], s["complaints"]["pending"], s["complaints"]["order_issued"],
            s["complaints"]["order_not_executed"]) == (3, 1, 2, 1)
    assert s["complaints"]["score"] == 33  # 100 * (1 - 2/3)
    assert s["progress"]["available"] is False
    assert s["overall"] == 50


def test_pending_and_not_executed_on_one_complaint_count_once():
    s = score([P(date(2022, 1, 1), None)], [C("pending", True)], TODAY)
    assert s["complaints"]["unresolved"] == 1 and s["complaints"]["score"] == 0


def test_insufficient_history_still_scores_complaints():
    projects = [P(date(2022, 1, 1), None), P(date(2027, 1, 1), None)]
    s = score(projects, [], TODAY)
    assert s["schedule"]["available"] is False and s["schedule"]["reason"] == "insufficient_history"
    assert s["complaints"]["score"] == 100
    assert s["overall"] == 100


def test_no_projects_means_not_enough_data():
    s = score([], [], TODAY)
    assert s["overall"] is None and s["complaints"]["reason"] == "no_projects"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.scoring'`

- [ ] **Step 3: Write the scoring module**

Create empty `backend/sahighar/scoring/__init__.py`. Create `backend/sahighar/scoring/v1.py`:

```python
"""Trust score v1: a scored checklist, not ML. All tunable numbers live here.

Every sub-score is shown with its inputs; the overall number is never shown alone.
Wording is neutral: an extension is not necessarily the promoter's fault, and a project past
its end date without an extension may simply have been completed, so neither is called "late".
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

MIN_EVALUATED_PROJECTS = 2  # fewer evaluated projects -> "insufficient history"
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class ProjectFacts:
    registration_end: date | None  # end of the original registration validity
    extended_end: date | None  # new end date, only if an extension certificate exists


@dataclass(frozen=True)
class ComplaintFacts:
    stage: str  # order_issued | pending | other
    non_execution_applied: bool


def _months(days: int) -> float:
    return round(days / DAYS_PER_MONTH, 1)


def classify(p: ProjectFacts, today: date) -> tuple[str, float | None]:
    """Return (outcome, months_extended). Outcome: extended | not_extended | within_registration | unknown.

    Measured against the ORIGINAL registration end date: an extension never hides in the numbers.
    """
    if p.registration_end is None:
        return "unknown", None
    if p.extended_end is not None and p.extended_end > p.registration_end:
        return "extended", _months((p.extended_end - p.registration_end).days)
    if p.registration_end < today:
        return "not_extended", None
    return "within_registration", None


def score(projects: list[ProjectFacts], complaints: list[ComplaintFacts], today: date) -> dict:
    outcomes = [classify(p, today) for p in projects]
    counts = Counter(outcome for outcome, _ in outcomes)
    evaluated = counts["extended"] + counts["not_extended"]
    months = [m for outcome, m in outcomes if outcome == "extended"]
    schedule_ok = evaluated >= MIN_EVALUATED_PROJECTS
    schedule = {
        "available": schedule_ok,
        "reason": None if schedule_ok else "insufficient_history",
        "score": round(100 * counts["not_extended"] / evaluated) if schedule_ok else None,
        "extended": counts["extended"],
        "not_extended": counts["not_extended"],
        "within_registration": counts["within_registration"],
        "unknown": counts["unknown"],
        "median_months_extended": median(months) if months else None,
    }

    n = len(projects)
    unresolved = sum(c.stage == "pending" or c.non_execution_applied for c in complaints)
    complaint_summary = {
        "available": n > 0,
        "reason": None if n > 0 else "no_projects",
        "score": round(100 * max(0.0, 1 - unresolved / n)) if n > 0 else None,
        "total": len(complaints),
        "pending": sum(c.stage == "pending" for c in complaints),
        "order_issued": sum(c.stage == "order_issued" for c in complaints),
        "order_not_executed": sum(c.non_execution_applied for c in complaints),
        "unresolved": unresolved,
        "project_count": n,
    }

    available = [c["score"] for c in (schedule, complaint_summary) if c["available"]]
    return {
        "schedule": schedule,
        "complaints": complaint_summary,
        "progress": {"available": False, "reason": "not_yet_available", "score": None},
        "overall": round(mean(available)) if available else None,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_scoring.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "backend: add trust score v1 (scored checklist)"
```

### Task 11: Promoter grouping

**Files:**
- Create: `backend/sahighar/resolve/__init__.py`, `backend/sahighar/resolve/grouping.py`
- Test: `backend/tests/test_grouping.py`

**Interfaces:**
- Consumes: `Promoter`, `PromoterGroup`, `GroupMembership`, `ScoreSnapshot` models.
- Produces: `resolve_groups(promoters: list[Promoter]) -> list[GroupResult]` (pure; each `GroupResult.members` is a list of `Link(promoter_id, link_type, evidence)`); `rebuild_groups(session) -> int` (persists, returns group count).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_grouping.py`:

```python
from sahighar.db.models import Promoter
from sahighar.resolve.grouping import resolve_groups


def P(id, name, pan=None, address=None, partners=None):
    return Promoter(id=id, state="MH", rera_promoter_ref=f"P{id}", name=name, pan=pan,
                    registered_address=address, partners_or_directors=partners, source_document_id=1)


def types(group):
    return {(m.promoter_id, m.link_type) for m in group.members}


def test_same_pan_is_filing_confirmed_and_transitive():
    groups = resolve_groups([P(1, "A", pan="ABCDE1234F"), P(2, "B", pan="abcde1234f "), P(3, "C", pan="ZZZZZ9999Z")])
    assert types(groups[0]) == {(1, "filing_confirmed"), (2, "filing_confirmed")}
    assert types(groups[1]) == {(3, "filing_confirmed")}


def test_partner_overlap_plus_same_address_is_possible_only():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="12 MG Road, Pune", partners=["Ramesh Shah"]),
        P(2, "Different Name Pvt Ltd", address="12 MG ROAD PUNE", partners=["ramesh  shah"]),
    ])
    assert types(groups[0]) == {(1, "filing_confirmed"), (2, "possible")}
    assert types(groups[1]) == {(2, "filing_confirmed"), (1, "possible")}
    assert groups[0].members[1].evidence["same_address"] is True


def test_partner_overlap_plus_similar_name_is_possible():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="A", partners=["Ramesh Shah"]),
        P(2, "Shree Realty Phase 2 LLP", address="B", partners=["Ramesh Shah"]),
    ])
    assert (2, "possible") in types(groups[0])


def test_same_address_plus_similar_name_is_possible_without_any_partner_data():
    groups = resolve_groups([
        P(1, "Shree Realty LLP", address="12 MG Road, Pune"),
        P(2, "Shree Realty Phase 2 LLP", address="12 MG ROAD PUNE"),
        P(3, "Unrelated Builders", address="12 MG Road Pune"),
    ])
    assert (2, "possible") in types(groups[0])
    assert groups[0].members[1].evidence == {"shared_partners": [], "same_address": True, "name_similarity": 100}
    assert all(m.promoter_id != 3 for g in groups[:2] for m in g.members if m.link_type == "possible")


def test_single_weak_signal_creates_no_link():
    only_partner = resolve_groups([P(1, "Alpha", partners=["Ramesh Shah"]), P(2, "Beta", partners=["Ramesh Shah"])])
    assert all(len(g.members) == 1 for g in only_partner)
    only_address = resolve_groups([P(1, "Alpha", address="12 MG Road"), P(2, "Beta", address="12 MG Road")])
    assert all(len(g.members) == 1 for g in only_address)
    only_name = resolve_groups([P(1, "Shree Realty LLP"), P(2, "Shree Realty LLP")])
    assert all(len(g.members) == 1 for g in only_name)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_grouping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.resolve'`

- [ ] **Step 3: Write the grouping module**

Create empty `backend/sahighar/resolve/__init__.py`. Create `backend/sahighar/resolve/grouping.py`:

```python
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sahighar.db.models import GroupMembership, Promoter, PromoterGroup, ScoreSnapshot

NAME_SIMILARITY_THRESHOLD = 90


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


def _partners(p: Promoter) -> set[str]:
    return {_norm(n) for n in (p.partners_or_directors or [])} - {""}


@dataclass
class Link:
    promoter_id: int
    link_type: str  # filing_confirmed | possible
    evidence: dict


@dataclass
class GroupResult:
    members: list[Link] = field(default_factory=list)


def resolve_groups(promoters: list[Promoter]) -> list[GroupResult]:
    """Rule-based grouping. Pure: takes Promoter objects, returns groups; touches no database.

    filing_confirmed: same PAN (union-find, so links are transitive).
    possible: (overlapping named partner/director AND (same normalised address OR similar name))
              OR (same normalised address AND similar name).
    A single weak signal alone never links anything.
    """
    parent = {p.id: p.id for p in promoters}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_pan: dict[str, list[Promoter]] = {}
    for p in promoters:
        pan = (p.pan or "").strip().upper()
        if pan:
            by_pan.setdefault(pan, []).append(p)
    for same in by_pan.values():
        for other in same[1:]:
            parent[find(other.id)] = find(same[0].id)

    components: dict[int, list[Promoter]] = {}
    for p in promoters:
        components.setdefault(find(p.id), []).append(p)

    groups: dict[int, GroupResult] = {}
    for root, members in components.items():
        pan = (members[0].pan or "").strip().upper()
        evidence = {"basis": "pan", "pan": pan} if len(members) > 1 else {"basis": "single_entity"}
        groups[root] = GroupResult([Link(m.id, "filing_confirmed", dict(evidence)) for m in members])

    # Every `possible` rule needs a shared partner or a shared address, so candidate pairs are
    # built from those two indexes only. ponytail: a very common address (a co-working space) makes
    # O(k^2) pairs; cap or skip oversized buckets if that ever shows up in real data.
    by_partner: dict[str, list[Promoter]] = {}
    by_address: dict[str, list[Promoter]] = {}
    for p in promoters:
        for name in _partners(p):
            by_partner.setdefault(name, []).append(p)
        if _norm(p.registered_address):
            by_address.setdefault(_norm(p.registered_address), []).append(p)
    pairs: set[tuple[int, int]] = set()
    for index in (by_partner, by_address):
        for people in index.values():
            for i, a in enumerate(people):
                for b in people[i + 1:]:
                    if find(a.id) != find(b.id):
                        pairs.add((min(a.id, b.id), max(a.id, b.id)))

    by_id = {p.id: p for p in promoters}
    for a_id, b_id in pairs:
        a, b = by_id[a_id], by_id[b_id]
        shared = sorted(_partners(a) & _partners(b))
        same_address = bool(_norm(a.registered_address)) and _norm(a.registered_address) == _norm(b.registered_address)
        similarity = fuzz.token_set_ratio(_norm(a.name), _norm(b.name))
        similar_name = similarity >= NAME_SIMILARITY_THRESHOLD
        if not ((shared and (same_address or similar_name)) or (same_address and similar_name)):
            continue
        evidence = {"shared_partners": shared, "same_address": same_address, "name_similarity": round(similarity)}
        for host, guest in ((a, b), (b, a)):
            group = groups[find(host.id)]
            if all(m.promoter_id != guest.id for m in group.members):
                group.members.append(Link(guest.id, "possible", dict(evidence)))

    return sorted(groups.values(), key=lambda g: min(m.promoter_id for m in g.members))


def rebuild_groups(session: Session) -> int:
    # ponytail: full rebuild each run (also drops score snapshots, which reference group ids);
    # keep history / stable group ids only if it is ever needed.
    session.execute(delete(ScoreSnapshot))
    session.execute(delete(GroupMembership))
    session.execute(delete(PromoterGroup))
    groups = resolve_groups(list(session.scalars(select(Promoter))))
    for g in groups:
        row = PromoterGroup()
        session.add(row)
        session.flush()
        for m in g.members:
            session.add(GroupMembership(group_id=row.id, promoter_id=m.promoter_id, link_type=m.link_type, evidence=m.evidence))
    session.commit()
    return len(groups)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_grouping.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "backend: add rule-based promoter grouping"
```

### Task 12: Score service (refresh)

**Files:**
- Create: `backend/sahighar/scoring/service.py`, `backend/tests/sample_data.py`
- Test: `backend/tests/test_service.py`

**Interfaces:**
- Consumes: `rebuild_groups` (Task 11), `score`/`ProjectFacts` (Task 10), models, `run_ingest`/`FakeAdapter` (Task 9, test only).
- Produces: `compute_scores(session, today: date) -> int` and `refresh(session, today: date | None = None) -> int` (rebuild groups, then one `ScoreSnapshot` per group from its `filing_confirmed` promoters only; returns group count). `tests.sample_data.DOC_1`, `DOC_2` fixture documents.

- [ ] **Step 1: Write the fixture data and the failing test**

Create `backend/tests/sample_data.py`:

```python
# Two fixture documents shared by the service, API and demo-seed code.
# P1+P2 share a PAN (filing_confirmed); P3 shares partner + address with P1 (possible); P4 is unrelated.

DOC_1 = {
    "promoters": [
        {"ref": "P1", "name": "Shree Realty LLP", "pan": "AAAPA0001A", "registered_address": "12 MG Road, Pune",
         "partners_or_directors": ["Ramesh Shah"]},
        {"ref": "P2", "name": "Shree Homes LLP", "pan": "AAAPA0001A"},
    ],
    "projects": [
        {"reg_no": "MH-1", "promoter_ref": "P1", "name": "Shree Heights", "city": "Pune",
         "registration_end": "2022-01-01"},
        {"reg_no": "MH-2", "promoter_ref": "P2", "name": "Shree Gardens",
         "registration_end": "2022-01-01", "extended_end": "2023-01-01"},
    ],
    "complaints": [
        {"ref": "C1", "promoter_ref": "P1", "status": "Hearing Scheduled", "project_reg_no": "MH-1",
         "filed_year": 2024, "filed_month": 3},
        {"ref": "C2", "promoter_ref": "P2", "status": "Order Approved", "project_reg_no": "MH-2",
         "filed_year": 2023, "filed_month": 11, "order_url": "https://example.test/order/C2.pdf"},
    ],
}
DOC_2 = {
    "promoters": [
        {"ref": "P3", "name": "Shree Realty Phase 2 LLP", "pan": "BBBPB0002B", "registered_address": "12 MG ROAD PUNE",
         "partners_or_directors": ["ramesh shah"]},
        {"ref": "P4", "name": "Zenith Constructions", "pan": "CCCPC0003C"},
    ],
    "projects": [
        {"reg_no": "MH-3", "promoter_ref": "P3", "name": "Shree Towers", "registration_end": "2027-01-01"},
        {"reg_no": "MH-4", "promoter_ref": "P4", "name": "Zenith One", "registration_end": "2027-06-01"},
    ],
}
```

Create `backend/tests/test_service.py`:

```python
from datetime import date

from sqlalchemy import func, select

from sahighar.db.models import GroupMembership, Promoter, PromoterGroup, ScoreSnapshot
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh
from tests.fakes import FakeAdapter
from tests.sample_data import DOC_1, DOC_2


def test_refresh_scores_each_group_from_confirmed_members_only(session, tmp_path):
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    assert refresh(session, today=date(2026, 9, 1)) == 3  # {P1,P2}, {P3}, {P4}

    p1 = session.scalar(select(Promoter).where(Promoter.rera_promoter_ref == "P1"))
    group_id = session.scalar(select(GroupMembership.group_id).where(
        GroupMembership.promoter_id == p1.id, GroupMembership.link_type == "filing_confirmed"))
    snapshot = session.scalar(select(ScoreSnapshot).where(ScoreSnapshot.group_id == group_id))
    assert snapshot.breakdown["schedule"]["score"] == 50  # P3's project (a possible link) is not counted
    assert snapshot.breakdown["overall"] == 50
    assert p1.source_document_id in snapshot.input_source_document_ids


def test_refresh_twice_does_not_pile_up_groups_or_snapshots(session, tmp_path):
    run_ingest(FakeAdapter({"u1": DOC_1, "u2": DOC_2}), session, LocalRawStore(tmp_path))
    refresh(session, today=date(2026, 9, 1))
    refresh(session, today=date(2026, 9, 1))
    assert session.scalar(select(func.count()).select_from(PromoterGroup)) == 3
    assert session.scalar(select(func.count()).select_from(ScoreSnapshot)) == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.scoring.service'`

- [ ] **Step 3: Write the service**

Create `backend/sahighar/scoring/service.py`:

```python
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, GroupMembership, Project, Promoter, ScoreSnapshot
from sahighar.resolve.grouping import rebuild_groups
from sahighar.scoring.v1 import ComplaintFacts, ProjectFacts, score
from sahighar.util import utcnow


def compute_scores(session: Session, today: date) -> int:
    """One ScoreSnapshot per group, from the group's filing_confirmed promoters only."""
    projects: dict[int, list[Project]] = defaultdict(list)
    for p in session.scalars(select(Project)):
        projects[p.promoter_id].append(p)
    complaints: dict[int, list[Complaint]] = defaultdict(list)
    for c in session.scalars(select(Complaint)):
        complaints[c.promoter_id].append(c)
    promoter_doc = dict(session.execute(select(Promoter.id, Promoter.source_document_id)).all())
    members: dict[int, list[int]] = defaultdict(list)
    for m in session.scalars(select(GroupMembership).where(GroupMembership.link_type == "filing_confirmed")):
        members[m.group_id].append(m.promoter_id)

    now = utcnow()
    for group_id, promoter_ids in members.items():
        ps = [p for pid in promoter_ids for p in projects[pid]]
        cs = [c for pid in promoter_ids for c in complaints[pid]]
        breakdown = score(
            [ProjectFacts(p.registration_end_date, p.extended_end_date) for p in ps],
            [ComplaintFacts(c.stage, c.non_execution_applied) for c in cs], today,
        )
        sources = {promoter_doc[pid] for pid in promoter_ids} | {r.source_document_id for r in (*ps, *cs)}
        session.add(ScoreSnapshot(group_id=group_id, computed_at=now, breakdown=breakdown,
                                  input_source_document_ids=sorted(sources)))
    session.commit()
    return len(members)


def refresh(session: Session, today: date | None = None) -> int:
    """Rebuild promoter groups, then score every group. Run after each ingest."""
    rebuild_groups(session)
    return compute_scores(session, today or date.today())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: `22 passed`

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "backend: add refresh service (group then score)"
```

### Task 13: API

**Files:**
- Create: `backend/sahighar/api/__init__.py`, `backend/sahighar/api/payload.py`, `backend/sahighar/api/main.py`
- Test: `backend/tests/test_api_e2e.py`

**Interfaces:**
- Consumes: `refresh` (Task 12), `classify`/`ProjectFacts` (Task 10), `get_session` (Task 7).
- Produces: FastAPI `app` with `GET /search?q=` (projects only), `GET /projects/{id}`, `GET /promoters/{id}`. The trust payload keys are: `data_as_of`, `score_computed_at`, `score`, `group_promoters`, `schedule`, `complaints`, `possibly_related`, `sources` (keyed by stringified source document id); the project response adds `project`, the promoter response adds `promoter`. Every record carries `source_document_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_e2e.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_api_e2e.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.api'`

- [ ] **Step 3: Write the payload builder and the app**

Create empty `backend/sahighar/api/__init__.py`. Create `backend/sahighar/api/payload.py`:

```python
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sahighar.db.models import Complaint, GroupMembership, Project, Promoter, ScoreSnapshot, SourceDocument
from sahighar.scoring.v1 import ProjectFacts, classify


def trust_payload(session: Session, promoter: Promoter) -> dict:
    """Everything the trust page shows for a promoter's filing-confirmed group.

    Every record carries `source_document_id`, resolvable in `sources`.
    """
    own = session.scalar(
        select(GroupMembership).where(
            GroupMembership.promoter_id == promoter.id, GroupMembership.link_type == "filing_confirmed"
        )
    )
    memberships = session.scalars(select(GroupMembership).where(GroupMembership.group_id == own.group_id)).all()
    confirmed_ids = [m.promoter_id for m in memberships if m.link_type == "filing_confirmed"]
    promoters = {p.id: p for p in session.scalars(select(Promoter).where(Promoter.id.in_(
        [m.promoter_id for m in memberships])))}

    snapshot = session.scalar(
        select(ScoreSnapshot).where(ScoreSnapshot.group_id == own.group_id)
        .order_by(ScoreSnapshot.computed_at.desc(), ScoreSnapshot.id.desc())
    )
    scored_on = snapshot.computed_at.date() if snapshot else date.today()

    schedule = []
    for p in session.scalars(select(Project).where(Project.promoter_id.in_(confirmed_ids)).order_by(Project.id)):
        outcome, months_extended = classify(ProjectFacts(p.registration_end_date, p.extended_end_date), scored_on)
        schedule.append({
            "project_id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no,
            "registration_end_date": p.registration_end_date, "extended_end_date": p.extended_end_date,
            "outcome": outcome, "months_extended": months_extended, "source_document_id": p.source_document_id,
        })
    complaints = [
        {"complaint_ref": c.complaint_ref, "project_id": c.project_id, "status": c.status, "stage": c.stage,
         "non_execution_applied": c.non_execution_applied, "filed_year": c.filed_year, "filed_month": c.filed_month,
         "order_url": c.order_url, "source_document_id": c.source_document_id}
        for c in session.scalars(select(Complaint).where(Complaint.promoter_id.in_(confirmed_ids)).order_by(Complaint.id))
    ]
    possibly_related = [
        {"promoter_id": m.promoter_id, "name": promoters[m.promoter_id].name, "evidence": m.evidence,
         "source_document_id": promoters[m.promoter_id].source_document_id}
        for m in memberships if m.link_type == "possible"
    ]
    group_promoters = [
        {"promoter_id": pid, "name": promoters[pid].name, "source_document_id": promoters[pid].source_document_id}
        for pid in confirmed_ids
    ]

    source_ids = {r["source_document_id"] for r in (*schedule, *complaints, *possibly_related, *group_promoters)}
    docs = session.scalars(select(SourceDocument).where(SourceDocument.id.in_(source_ids))).all()
    return {
        "data_as_of": max((d.fetched_at for d in docs), default=None),
        "score_computed_at": snapshot.computed_at if snapshot else None,
        "score": snapshot.breakdown if snapshot else None,
        "group_promoters": group_promoters,
        "schedule": schedule,
        "complaints": complaints,
        "possibly_related": possibly_related,
        "sources": {str(d.id): {"url": d.url, "origin": d.origin, "fetched_at": d.fetched_at} for d in docs},
    }
```

Create `backend/sahighar/api/main.py`:

```python
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sahighar.api.payload import trust_payload
from sahighar.db.models import Project, Promoter
from sahighar.db.session import get_session

app = FastAPI(title="Sahi Ghar")


@app.get("/search")
def search(q: str = Query(min_length=2), session: Session = Depends(get_session)):
    """Projects whose name, promoter name or RERA registration number contains the query."""
    needle = q.lower()
    rows = session.execute(
        select(Project, Promoter.name).join(Promoter, Project.promoter_id == Promoter.id)
        .where(or_(func.lower(Project.name).contains(needle, autoescape=True),
                   func.lower(Project.rera_reg_no).contains(needle, autoescape=True),
                   func.lower(Promoter.name).contains(needle, autoescape=True)))
        .order_by(Project.name).limit(25)
    ).all()
    return {"projects": [{"id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no, "city": p.city,
                          "promoter_id": p.promoter_id, "promoter_name": name}
                         for p, name in rows]}


@app.get("/projects/{project_id}")
def project(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    promoter = session.get(Promoter, p.promoter_id)
    return {
        "project": {"id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no, "city": p.city, "locality": p.locality,
                    "configurations": p.configurations, "carpet_area_range": p.carpet_area_range,
                    "registration_end_date": p.registration_end_date, "extended_end_date": p.extended_end_date,
                    "promoter_id": promoter.id, "promoter_name": promoter.name,
                    "source_document_id": p.source_document_id},
        **trust_payload(session, promoter),
    }


@app.get("/promoters/{promoter_id}")
def promoter(promoter_id: int, session: Session = Depends(get_session)):
    p = session.get(Promoter, promoter_id)
    if p is None:
        raise HTTPException(404, "promoter not found")
    return {"promoter": {"id": p.id, "name": p.name, "rera_promoter_ref": p.rera_promoter_ref}, **trust_payload(session, p)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest -v`
Expected: `26 passed`. Two harmless deprecation warnings from Starlette's test client are expected.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "backend: add search and trust-payload API"
```

### Task 14: Frontend scaffold, API client and formatting

**Files:**
- Create: `frontend/` (Vite React-TS scaffold), `frontend/src/api.ts`, `frontend/src/format.ts`, `frontend/src/test-setup.ts`
- Modify: `frontend/vite.config.ts`, `frontend/package.json` (test script), `frontend/index.html` (title), `frontend/src/index.css`, `frontend/src/main.tsx`

**Interfaces:**
- Produces: TypeScript types `Score`, `ScheduleItem`, `ComplaintItem`, `RelatedItem`, `ProjectPayload`, `SearchResult`, `Source` mirroring the API; `searchProjects(q) -> Promise<SearchResult[]>`; `getProject(id) -> Promise<ProjectPayload>`; `formatDate(value: string | null): string`; `formatMonthYear(year, month): string` (never shows a day); `outcomeText(item): string`. `npm test` runs Vitest; the Vite dev server proxies `/api` to `http://localhost:8010`.

- [ ] **Step 1: Scaffold and install**

```bash
npm create vite@latest frontend -- --template react-ts --no-interactive
cd frontend
npm install
npm install react-router-dom tailwindcss @tailwindcss/vite
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
rm -f src/App.css && rm -rf src/assets
```

- [ ] **Step 2: Configure Vite, Tailwind, Vitest and the entry point**

Replace `frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': { target: 'http://localhost:8010', rewrite: (path) => path.replace(/^\/api/, '') } },
  },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', pool: 'threads' },
})
```

Create `frontend/src/test-setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
```

Replace `frontend/src/index.css` with:

```css
@import 'tailwindcss';
```

Replace `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

In `frontend/package.json` add `"test": "vitest run"` to `scripts`. In `frontend/index.html` change `<title>frontend</title>` to `<title>Sahi Ghar</title>`. The scaffold's `App.tsx` imports the `App.css` and assets deleted in Step 1, so replace `frontend/src/App.tsx` with this stub (Task 16 replaces it with the real routes):

```tsx
export default function App() {
  return <p>Sahi Ghar</p>
}
```

- [ ] **Step 3: Write the failing test for formatting**

Create `frontend/src/format.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatDate, formatMonthYear, outcomeText } from './format'

describe('formatDate', () => {
  it('reads naive API datetimes as UTC, not local time', () => {
    // 2026-09-01T00:00:00 must not become 31 Aug for viewers east of UTC (India is +05:30).
    expect(formatDate('2026-09-01T00:00:00')).toMatch(/^1 Sep(t)? 2026$/)
  })
  it('formats plain dates and handles null', () => {
    expect(formatDate('2022-01-01')).toMatch(/^1 Jan 2022$/)
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatMonthYear', () => {
  it('never invents a day when the source gives year and month only', () => {
    expect(formatMonthYear(2024, 3)).toBe('March 2024')
    expect(formatMonthYear(2024, null)).toBe('2024')
    expect(formatMonthYear(null, null)).toBe('—')
  })
})

describe('outcomeText', () => {
  it('states the schedule against the original end date in neutral words', () => {
    expect(outcomeText({ outcome: 'extended', months_extended: 12 })).toBe('Registration extended by 12 months')
    expect(outcomeText({ outcome: 'not_extended', months_extended: null })).toBe('Original end date passed; no extension on record')
    expect(outcomeText({ outcome: 'unknown', months_extended: null })).toBe('No end date in the filing')
  })
})
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL: cannot resolve `./format` (the module does not exist yet).

- [ ] **Step 5: Write the API client and formatters**

Create `frontend/src/api.ts`:

```ts
export type Source = { url: string; origin: string; fetched_at: string }

export type Score = {
  overall: number | null
  schedule: {
    available: boolean
    reason: string | null
    score: number | null
    extended: number
    not_extended: number
    within_registration: number
    unknown: number
    median_months_extended: number | null
  }
  complaints: {
    available: boolean
    reason: string | null
    score: number | null
    total: number
    pending: number
    order_issued: number
    order_not_executed: number
    unresolved: number
    project_count: number
  }
  progress: { available: boolean; reason: string | null; score: number | null }
}

export type ScheduleItem = {
  project_id: number
  name: string
  rera_reg_no: string
  registration_end_date: string | null
  extended_end_date: string | null
  outcome: 'extended' | 'not_extended' | 'within_registration' | 'unknown'
  months_extended: number | null
  source_document_id: number
}

export type ComplaintItem = {
  complaint_ref: string
  status: string
  stage: 'order_issued' | 'pending' | 'other'
  non_execution_applied: boolean
  filed_year: number | null
  filed_month: number | null
  order_url: string | null
  source_document_id: number
}

export type RelatedItem = {
  promoter_id: number
  name: string
  evidence: { shared_partners: string[]; same_address: boolean; name_similarity: number }
  source_document_id: number
}

export type ProjectPayload = {
  project: {
    id: number
    name: string
    rera_reg_no: string
    city: string | null
    locality: string | null
    registration_end_date: string | null
    extended_end_date: string | null
    promoter_name: string
    source_document_id: number
  }
  data_as_of: string | null
  score_computed_at: string | null
  score: Score | null
  group_promoters: { promoter_id: number; name: string; source_document_id: number }[]
  schedule: ScheduleItem[]
  complaints: ComplaintItem[]
  possibly_related: RelatedItem[]
  sources: Record<string, Source>
}

export type SearchResult = {
  id: number
  name: string
  rera_reg_no: string
  city: string | null
  promoter_name: string
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) throw new Error(response.status === 404 ? 'Not found' : `Request failed (${response.status})`)
  return response.json()
}

export const searchProjects = (q: string) =>
  get<{ projects: SearchResult[] }>(`/search?q=${encodeURIComponent(q)}`).then((r) => r.projects)

export const getProject = (id: string) => get<ProjectPayload>(`/projects/${encodeURIComponent(id)}`)
```

Create `frontend/src/format.ts`:

```ts
import type { ScheduleItem } from './api'

// The API sends naive UTC datetimes (no "Z"); without this the browser reads them as local time.
const asUtc = (value: string) => (/T[\d:.]+$/.test(value) ? `${value}Z` : value)

export function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(asUtc(value)).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** The source publishes year and month only, so never show a day. */
export function formatMonthYear(year: number | null, month: number | null): string {
  if (!year) return '—'
  return month ? `${MONTHS[month - 1]} ${year}` : String(year)
}

export function outcomeText(item: Pick<ScheduleItem, 'outcome' | 'months_extended'>): string {
  switch (item.outcome) {
    case 'extended':
      return `Registration extended by ${item.months_extended} months`
    case 'not_extended':
      return 'Original end date passed; no extension on record'
    case 'within_registration':
      return 'Within the registered period'
    default:
      return 'No end date in the filing'
  }
}
```

- [ ] **Step 6: Run the tests, then the build**

Run: `cd frontend && npm test`
Expected: `Tests  4 passed` (4 in format.test.ts)

Also run once with an eastern timezone to prove the UTC handling: `TZ=Asia/Kolkata npm test` — same result.

Run: `cd frontend && npm run build`
Expected: `built in ...` with no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "frontend: scaffold Vite app, API client and formatters"
```

### Task 15: Trust page components

**Files:**
- Create: `frontend/src/components/SourceLink.tsx`, `frontend/src/components/ScoreBreakdown.tsx`, `frontend/src/pages/TrustPage.tsx`
- Test: `frontend/src/pages/TrustPage.test.tsx`

**Interfaces:**
- Consumes: types and `getProject` from `api.ts`, `formatDate`/`outcomeText` from `format.ts`.
- Produces: `<SourceLink id sources />`, `<ScoreBreakdown score />`, `TrustPageView({ data })` (pure, testable) and the default-exported route component `TrustPage` (reads `:id`, fetches, renders `TrustPageView`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/TrustPage.test.tsx`:

```tsx
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ProjectPayload } from '../api'
import { TrustPageView } from './TrustPage'

const data: ProjectPayload = {
  project: { id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', city: 'Pune', locality: null,
    registration_end_date: '2022-01-01', extended_end_date: null, promoter_name: 'Shree Realty LLP', source_document_id: 1 },
  data_as_of: '2026-09-01T00:00:00',
  score_computed_at: '2026-09-01T00:00:00',
  score: {
    overall: 25,
    schedule: { available: true, reason: null, score: 50, extended: 1, not_extended: 1, within_registration: 0, unknown: 0, median_months_extended: 12 },
    complaints: { available: true, reason: null, score: 0, total: 2, pending: 1, order_issued: 1, order_not_executed: 1, unresolved: 2, project_count: 2 },
    progress: { available: false, reason: 'not_yet_available', score: null },
  },
  group_promoters: [{ promoter_id: 1, name: 'Shree Realty LLP', source_document_id: 1 }],
  schedule: [
    { project_id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', registration_end_date: '2022-01-01', extended_end_date: null,
      outcome: 'not_extended', months_extended: null, source_document_id: 1 },
    { project_id: 2, name: 'Shree Gardens', rera_reg_no: 'MH-2', registration_end_date: '2022-01-01', extended_end_date: '2023-01-01',
      outcome: 'extended', months_extended: 12, source_document_id: 2 },
  ],
  complaints: [
    { complaint_ref: 'C1', status: 'Hearing Scheduled', stage: 'pending', non_execution_applied: false,
      filed_year: 2024, filed_month: 3, order_url: null, source_document_id: 3 },
    { complaint_ref: 'C2', status: 'Order Approved', stage: 'order_issued', non_execution_applied: true,
      filed_year: 2023, filed_month: 11, order_url: 'https://example.test/C2.pdf', source_document_id: 3 },
  ],
  possibly_related: [
    { promoter_id: 3, name: 'Shree Realty Phase 2 LLP',
      evidence: { shared_partners: [], same_address: true, name_similarity: 100 }, source_document_id: 4 },
  ],
  sources: {
    '1': { url: 'https://maharera.example/p/1', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '2': { url: 'https://maharera.example/p/2', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '3': { url: 'https://maharera.example/c', origin: 'test', fetched_at: '2026-09-01T00:00:00' },
    '4': { url: 'file:import.csv', origin: 'file-import', fetched_at: '2026-09-01T00:00:00' },
  },
}

describe('TrustPageView', () => {
  it('shows the breakdown before the overall number, and never the overall alone', () => {
    render(<TrustPageView data={data} />)
    const breakdown = screen.getByRole('region', { name: 'Score breakdown' })
    expect(within(breakdown).getByText('Registration schedule')).toBeInTheDocument()
    expect(within(breakdown).getByText(/1 of 2 projects had their registration extended \(median 12 months\); 1 passed the original end date/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/1 hearing pending, 1 order issued; 1 with a request to enforce/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Progress vs promise/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Overall: 25\/100, the average of the sections above/)).toBeInTheDocument()
  })

  it('stamps the data date and states it is not a verdict', () => {
    render(<TrustPageView data={data} />)
    expect(screen.getByText(/Data as of 1 Sep(t)? 2026/)).toBeInTheDocument()
    expect(screen.getByText(/not an independent verdict/)).toBeInTheDocument()
  })

  it('never calls a project late, and says what the dates are', () => {
    render(<TrustPageView data={data} />)
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).getByText(/these are dates, not a verdict/)).toBeInTheDocument()
    expect(within(schedule).getByText('Registration extended by 12 months')).toBeInTheDocument()
    expect(within(schedule).getByText('Original end date passed; no extension on record')).toBeInTheDocument()
    expect(screen.queryByText(/\blate\b|delayed/i)).not.toBeInTheDocument()
  })

  it('shows complaints with the status exactly as published and only month and year', () => {
    render(<TrustPageView data={data} />)
    const complaints = screen.getByRole('region', { name: 'Complaints' })
    expect(within(complaints).getByText('Order Approved')).toBeInTheDocument()
    expect(within(complaints).getByText('March 2024')).toBeInTheDocument()
    expect(within(complaints).getByText('Yes, order not complied with')).toBeInTheDocument()
  })

  it('puts a source link beside every schedule and complaint row', () => {
    render(<TrustPageView data={data} />)
    for (const name of ['Registration schedule', 'Complaints']) {
      const rows = within(screen.getByRole('region', { name })).getAllByRole('row').slice(1)
      expect(rows.length).toBeGreaterThan(0)
      for (const row of rows) expect(within(row).getByText(/^Source, fetched/)).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: 'Original order' })).toHaveAttribute('href', 'https://example.test/C2.pdf')
  })

  it('keeps possibly related entities separate and labelled as not counted', () => {
    render(<TrustPageView data={data} />)
    const block = screen.getByRole('region', { name: 'Possibly related entities' })
    expect(within(block).getByText(/not counted in this score/)).toBeInTheDocument()
    expect(within(block).getByText(/Shree Realty Phase 2 LLP/)).toBeInTheDocument()
    expect(within(block).getByText(/same registered address/)).toBeInTheDocument()
    expect(within(block).getByText(/^Source, fetched/)).toBeInTheDocument()
    const schedule = screen.getByRole('region', { name: 'Registration schedule' })
    expect(within(schedule).queryByText(/Phase 2/)).not.toBeInTheDocument()
  })

  it('says so when there is not enough data instead of showing a number', () => {
    const empty = { ...data, score: { ...data.score!, overall: null,
      schedule: { ...data.score!.schedule, available: false, score: null, reason: 'insufficient_history' } } }
    render(<TrustPageView data={empty} />)
    expect(screen.getByText(/Not enough history to summarise/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL: cannot resolve `./TrustPage`.

- [ ] **Step 3: Write the components**

Create `frontend/src/components/SourceLink.tsx`:

```tsx
import type { Source } from '../api'
import { formatDate } from '../format'

/** Every figure on the trust page renders one of these next to it. */
export function SourceLink({ id, sources }: { id: number; sources: Record<string, Source> }) {
  const source = sources[String(id)]
  if (!source) return null
  const label = `Source, fetched ${formatDate(source.fetched_at)}`
  if (!source.url.startsWith('http')) {
    return <span className="text-xs text-stone-500">{label} ({source.origin})</span>
  }
  return (
    <a className="text-xs text-blue-800 underline" href={source.url} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  )
}
```

Create `frontend/src/components/ScoreBreakdown.tsx`:

```tsx
import type { Score } from '../api'

function Section({ title, score, children }: { title: string; score: number | null; children: React.ReactNode }) {
  return (
    <div className="rounded border border-stone-300 bg-white p-4">
      <h3 className="text-sm font-semibold text-stone-700">{title}</h3>
      <p className="mt-1 text-2xl font-semibold text-stone-900">{score === null ? '—' : `${score}/100`}</p>
      <p className="mt-1 text-sm text-stone-600">{children}</p>
    </div>
  )
}

/** The overall number is only ever rendered below, and as a summary of, the three sections. */
export function ScoreBreakdown({ score }: { score: Score }) {
  const { schedule, complaints, progress } = score
  const evaluated = schedule.extended + schedule.not_extended
  return (
    <section aria-label="Score breakdown">
      <div className="grid gap-3 sm:grid-cols-3">
        <Section title="Registration schedule" score={schedule.score}>
          {schedule.available
            ? `${schedule.extended} of ${evaluated} projects had their registration extended` +
              (schedule.median_months_extended !== null ? ` (median ${schedule.median_months_extended} months)` : '') +
              `; ${schedule.not_extended} passed the original end date with no extension on record.`
            : 'Not enough history to summarise (at least 2 projects past their original end date or extended are needed).'}
        </Section>
        <Section title="Complaints" score={complaints.score}>
          {complaints.available
            ? `${complaints.total} on record: ${complaints.pending} hearing pending, ${complaints.order_issued} order issued; ` +
              `${complaints.order_not_executed} with a request to enforce an order that was not complied with. ` +
              `${complaints.unresolved} unresolved across ${complaints.project_count} registered projects.`
            : 'No registered projects on record.'}
        </Section>
        <Section title="Progress vs promise" score={progress.score}>
          Not yet available. Quarterly progress reports are not included in this version.
        </Section>
      </div>
      <p className="mt-3 text-sm text-stone-700">
        {score.overall === null
          ? 'Overall: not enough data.'
          : `Overall: ${score.overall}/100, the average of the sections above that have data.`}
      </p>
    </section>
  )
}
```

Create `frontend/src/pages/TrustPage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProject, type ProjectPayload } from '../api'
import { ScoreBreakdown } from '../components/ScoreBreakdown'
import { SourceLink } from '../components/SourceLink'
import { formatDate, formatMonthYear, outcomeText } from '../format'

export function TrustPageView({ data }: { data: ProjectPayload }) {
  const { project, sources } = data
  return (
    <article className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-stone-900">{project.name}</h1>
        <p className="mt-1 text-sm text-stone-700">
          RERA registration <span className="font-mono">{project.rera_reg_no}</span> · Promoter: {project.promoter_name}
          {project.city ? ` · ${project.city}` : ''}
        </p>
        <p className="mt-2 text-sm text-stone-600">
          Data as of {formatDate(data.data_as_of)}. RERA filings are updated quarterly, not live. This page mirrors public
          records; it is not an independent verdict.
        </p>
      </header>

      {data.score ? <ScoreBreakdown score={data.score} /> : <p>No score has been computed for this promoter yet.</p>}

      <section aria-label="Registration schedule">
        <h2 className="text-lg font-semibold text-stone-900">Registration schedule</h2>
        <p className="text-sm text-stone-600">
          Projects registered by {data.group_promoters.map((p) => p.name).join(', ')}. Dates are the end of each
          registration, taken from the registration and extension certificates. An extension is not necessarily the
          promoter's fault, and a project past its end date may already be complete: these are dates, not a verdict.
        </p>
        <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-stone-600">
            <tr><th>Project</th><th>Registered until</th><th>Extended to</th><th>Outcome</th><th>Source</th></tr>
          </thead>
          <tbody>
            {data.schedule.map((h) => (
              <tr key={h.project_id} className="border-t border-stone-200 align-top">
                <td>{h.name} <span className="font-mono text-xs text-stone-500">{h.rera_reg_no}</span></td>
                <td>{formatDate(h.registration_end_date)}</td>
                <td>{formatDate(h.extended_end_date)}</td>
                <td>{outcomeText(h)}</td>
                <td><SourceLink id={h.source_document_id} sources={sources} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>

      <section aria-label="Complaints">
        <h2 className="text-lg font-semibold text-stone-900">Complaints</h2>
        {data.complaints.length === 0 ? (
          <p className="text-sm text-stone-600">No complaints on record for this promoter.</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-stone-600">
              <tr><th>Reference</th><th>Status as published</th><th>Filed</th><th>Enforcement requested</th><th>Order</th><th>Source</th></tr>
            </thead>
            <tbody>
              {data.complaints.map((c) => (
                <tr key={c.complaint_ref} className="border-t border-stone-200 align-top">
                  <td className="font-mono">{c.complaint_ref}</td>
                  <td>{c.status}</td>
                  <td>{formatMonthYear(c.filed_year, c.filed_month)}</td>
                  <td>{c.non_execution_applied ? 'Yes, order not complied with' : 'No'}</td>
                  <td>
                    {c.order_url ? (
                      <a className="text-blue-800 underline" href={c.order_url} target="_blank" rel="noopener noreferrer">
                        Original order
                      </a>
                    ) : '—'}
                  </td>
                  <td><SourceLink id={c.source_document_id} sources={sources} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </section>

      {data.possibly_related.length > 0 && (
        <section aria-label="Possibly related entities" className="rounded border border-dashed border-stone-400 p-4">
          <h2 className="text-lg font-semibold text-stone-900">Possibly related entities</h2>
          <p className="text-sm text-stone-600">
            Records of possibly related entities (not counted in this score). They are matched on details such as a shared
            registered address, similar name, or overlapping partners or directors; the filings do not confirm a link.
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {data.possibly_related.map((r) => (
              <li key={r.promoter_id}>
                {r.name}:{' '}
                {[
                  r.evidence.shared_partners.length ? `shares ${r.evidence.shared_partners.join(', ')}` : null,
                  r.evidence.same_address ? 'same registered address' : null,
                  `name similarity ${r.evidence.name_similarity}%`,
                ].filter(Boolean).join('; ')}{' '}
                <SourceLink id={r.source_document_id} sources={sources} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}

export default function TrustPage() {
  const { id = '' } = useParams()
  const [data, setData] = useState<ProjectPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getProject(id).then(setData).catch((e: Error) => setError(e.message))
  }, [id])

  if (error) return <p>{error}. <Link className="underline" to="/">Back to search</Link></p>
  if (!data) return <p>Loading…</p>
  return <TrustPageView data={data} />
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: `Tests  11 passed` (4 format + 7 trust page)

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "frontend: add trust page with score breakdown and source links"
```

### Task 16: Search page, routing and visual pass

**Files:**
- Create: `frontend/src/pages/Search.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `searchProjects`, `TrustPage`.
- Produces: routes `/` (search) and `/projects/:id` (trust page).

- [ ] **Step 1: Write the search page and routes**

Replace `frontend/src/App.tsx`:

```tsx
import { Link, Route, Routes } from 'react-router-dom'
import Search from './pages/Search'
import TrustPage from './pages/TrustPage'

export default function App() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-300 bg-white">
        <div className="mx-auto max-w-4xl px-4 py-3">
          <Link to="/" className="text-lg font-semibold">Sahi Ghar</Link>
          <span className="ml-3 text-sm text-stone-600">A public-record lookup of builders' RERA track records</span>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/projects/:id" element={<TrustPage />} />
        </Routes>
      </main>
    </div>
  )
}
```

Create `frontend/src/pages/Search.tsx`:

```tsx
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { searchProjects, type SearchResult } from '../api'

export default function Search() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      setResults(await searchProjects(q.trim()))
    } catch (e) {
      setResults(null)
      setError((e as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="flex gap-2">
        <label className="sr-only" htmlFor="q">Builder, project name or RERA number</label>
        <input
          id="q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          minLength={2}
          required
          placeholder="Builder, project name or RERA number"
          className="flex-1 rounded border border-stone-400 px-3 py-2"
        />
        <button className="rounded bg-stone-900 px-4 py-2 text-white">Search</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {results && results.length === 0 && <p>No registered projects match “{q}”.</p>}
      {results && results.length > 0 && (
        <ul className="divide-y divide-stone-200">
          {results.map((r) => (
            <li key={r.id} className="py-3">
              <Link className="font-medium text-blue-800 underline" to={`/projects/${r.id}`}>{r.name}</Link>
              <p className="text-sm text-stone-600">
                <span className="font-mono">{r.rera_reg_no}</span> · {r.promoter_name}
                {r.city ? ` · ${r.city}` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd frontend && npm run build && npm test`
Expected: build succeeds; `Tests  11 passed`.

- [ ] **Step 3: Commit the functional version**

```bash
git add frontend
git commit -m "frontend: add search page and routes"
```

- [ ] **Step 4: Visual design pass (after Task 17 Step 5 shows the real page)**

Run this step once the app is up in Task 17. Use the `frontend-design:frontend-design` (or `impeccable`) skill to raise the visual quality **within** `DESIGN.md`'s principles: it must read like a public-record lookup or a credit report, not a real-estate sales site. Acceptance criteria:
- No ads, "featured" builders, hero imagery, or sales copy.
- The breakdown stays above the overall number; every figure keeps its adjacent source link; "Data as of" and the not-a-verdict note stay visible near the top.
- The "Possibly related entities" block stays visibly separate and labelled "not counted in this score".
- Colour is never the only carrier of meaning; body text has readable contrast.
- No horizontal page scroll at 375px width (tables scroll inside their own wrapper).
- `cd frontend && npm test && npm run build` still pass unchanged.

Commit as `frontend: visual polish`.

### Task 17: Full-stack run-through and README

**Files:**
- Create: `backend/tests/seed_demo.py`, `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `uv run python -m tests.seed_demo` loads the fixture documents into `$DATABASE_URL` and scores them (dev only); a README with the run commands.

- [ ] **Step 1: Write the demo seed**

Create `backend/tests/seed_demo.py`:

```python
"""Dev only: load the sample documents into $DATABASE_URL and score them.

    DATABASE_URL=postgresql+psycopg://... uv run python -m tests.seed_demo
"""
from pathlib import Path

from sahighar.db.session import _sessionmaker
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh
from tests.fakes import FakeAdapter
from tests.sample_data import DOC_1, DOC_2


def main() -> None:
    adapter = FakeAdapter({"https://example.test/demo/doc-1": DOC_1, "https://example.test/demo/doc-2": DOC_2})
    with _sessionmaker()() as session:
        print(run_ingest(adapter, session, LocalRawStore(Path("raw_store"))))
        print(refresh(session), "groups scored")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Start Postgres, migrate, seed**

```bash
docker rm -f sahighar-pg >/dev/null 2>&1
docker run -d --name sahighar-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=sahighar -p 5433:5432 postgres:16
sleep 5
cd backend
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run alembic upgrade head
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run python -m tests.seed_demo
```

Expected output ends with `IngestSummary(total=2, ok=2, failed=0)` and `3 groups scored`.

- [ ] **Step 3: Start the API and the frontend**

Terminal 1: `cd backend && DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar" uv run uvicorn sahighar.api.main:app --port 8010`
Terminal 2: `cd frontend && npm run dev`  (prints a `http://localhost:5173` URL)

Sanity check: `curl -s "http://localhost:8010/search?q=shree"` returns JSON with three projects. If port 8010 is busy, pick another and change the proxy target in `vite.config.ts` to match.

- [ ] **Step 4: Write the README**

Create `README.md` at the repo root:

```markdown
# Sahi Ghar

Free tool that shows a homebuilder's RERA track record before you book. Docs: `PRD.md`, `DESIGN.md`, `TECH_STACK.md`, `DATA_SOURCES.md`; design spec in `docs/superpowers/specs/`; MahaRERA access findings in `docs/spikes/`.

## Run locally

    docker run -d --name sahighar-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=sahighar -p 5433:5432 postgres:16
    cd backend && uv sync
    export DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5433/sahighar
    uv run alembic upgrade head
    uv run python -m tests.seed_demo          # loads fixture data (dev only)
    uv run uvicorn sahighar.api.main:app --port 8010
    # in another terminal
    cd frontend && npm install && npm run dev

## Tests

    cd backend && uv run pytest
    cd frontend && npm test
```

- [ ] **Step 5: Check the real page in a browser**

Open `http://localhost:5173`. Search `shree`: three results. Open **Shree Heights** and confirm each of these:
- Header shows the RERA number, promoter name, and "Data as of <today's date>" with the not-a-verdict sentence.
- Breakdown shows Registration schedule 50/100 ("1 of 2 projects had their registration extended (median 12 months); 1 passed the original end date with no extension on record."), Complaints 50/100 ("2 on record: 1 hearing pending, 1 order issued; 0 with a request to enforce an order that was not complied with. 1 unresolved across 2 registered projects."), Progress vs promise "—", then "Overall: 50/100, the average of the sections above that have data."
- Registration schedule table lists Shree Heights ("Original end date passed; no extension on record") and Shree Gardens ("Registration extended by 12 months"); **Shree Towers is absent**. Each row has a "Source, fetched ..." link to `https://example.test/demo/doc-1`. The words "late" and "delayed" appear nowhere on the page.
- Complaints table shows C1 ("Hearing Scheduled", March 2024) and C2 ("Order Approved", November 2023) with an "Original order" link on C2; no day of the month is shown anywhere.
- "Possibly related entities" lists Shree Realty Phase 2 LLP, says "not counted in this score", and shows "same registered address".
- Search `zzz`: "No registered projects match" message, no crash. Visit `/projects/9999`: "Not found" with a back link.
- Resize to 375px wide: no horizontal page scroll (tables scroll inside their block).

Now do the visual pass from Task 16 Step 4, re-check these points, and stop both servers.

- [ ] **Step 6: Clean up and commit**

```bash
docker rm -f sahighar-pg
```

```bash
git add backend/tests/seed_demo.py README.md frontend
git commit -m "docs: add README and demo seed; visual pass"
```

---

## Self-review against the spec

**Spec coverage**

| Spec section | Covered by |
|---|---|
| §3 Slice 0 spike (questions 1-9, shallow K/T check, decision rule) | Done before this plan's Part 2; outcome recorded in the spike report (Path B); question 6 (runner) is moot because nothing is scraped |
| §4 adapter interface, raw store (local impl) | Tasks 6, 9 |
| §4 S3-compatible raw store | Plan B (deployment) |
| §5 data model, idempotent upserts, raw-first | Tasks 7, 8, 9 |
| §6 grouping (PAN / possible rules, presentation rule) | Tasks 11, 15 (UI separation) |
| §7 trust score v1 | Task 10, 12 |
| §8 API | Task 13 |
| §9 frontend | Tasks 14-16 |
| §11 failure handling (per-document isolation, threshold, re-parse) | Task 9 |
| §11 hosting (no weekly scrape: refresh = a new import) | Plan B |
| §12 testing (fixtures, unit, contract, e2e) | Tasks 9-13, 15; import-parser tests and the manual 3-builder check are Plan B |
| §13 success criteria: slice 0 | Done (spike report and decision) |
| §13 success criteria: slice 1 (real MahaRERA data, cross-check) | Plan B, once data arrives; the core is proven here on fixtures |

**Known limits carried in the code (each marked `ponytail:` where it is a deliberate corner):** grouping and snapshots are rebuilt from scratch on every `refresh` (no history, group ids unstable); `search` is a substring scan (fine at slice-1 volume, add a trigram index if it is not); a complaint whose project is not yet ingested is stored with `project_id = NULL`.
