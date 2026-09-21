# Sahi Ghar — Slice 0 (Access Spike) + Slice 1 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find out how MahaRERA data can legitimately be obtained (slice 0), and build everything in slice 1 that does not depend on MahaRERA's actual page format: raw store, schema, ingest runner, promoter grouping, trust score v1, API, and the search + trust-page frontend, proven end to end on fixture data.

**Architecture:** Source-agnostic adapters yield raw documents; a runner stores them raw-first (content-addressed) and parses them into Postgres with every row tagged by its `source_document_id`. Grouping and scoring are pure functions over those rows; a FastAPI service serves a trust payload where every figure resolves to a stored source; a React page renders it. The MahaRERA adapter itself is deliberately **not** in this plan (see "Plan B").

**Tech Stack:** Python 3.11+ (uv), FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite for unit tests), rapidfuzz, httpx; React 19 + Vite + Tailwind 4 + React Router, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-21-sahi-ghar-design.md` (amended 2026-09-21 with the refinements this plan implements: `discover()`/`parse()` adapter interface, `source_document.kind`, projects-only `/search`, PAN-grouping caveat).

## Global Constraints

Every task's requirements implicitly include these (copied from the spec).

- Stack: Python + FastAPI + PostgreSQL backend; React + Vite + Tailwind frontend.
- **No CAPTCHA solving or bypass, ever.** If a page is CAPTCHA-gated, the spike records it and stops on that page.
- Spike requests: one at a time, at least 3 seconds apart, identifiable User-Agent, never stress-tested.
- Every parsed row carries `source_document_id`; every figure on the trust page links to its source document; every page states "data as of" a date.
- Adapters never touch the database; `parse()` is a pure function of the raw document (no network, no database).
- Fields a source does not publish stay nullable, and rules that depend on them degrade gracefully.
- Grouping: `filing_confirmed` (same PAN) links feed delivery history and the score; `possible` links are shown separately, labelled "not counted in this score", and never counted.
- Lateness is measured against the **original** completion date; a revised date is shown beside it, never used to hide a delay.
- Trust score v1 is a scored checklist, not ML; every tunable number lives in `backend/sahighar/scoring/v1.py`. The overall number is never shown without its breakdown.
- Wording is neutral and stays within what RERA data says: no verdicts, no ads, no "featured" builders.
- All `DateTime` columns store naive UTC (`sahighar.util.utcnow`).
- Dev API port is **8010** (8000 is used by another project on this machine); the frontend calls `/api/...` and the Vite dev proxy strips `/api`.
- **No GitHub repo, remote or push is created by the agent.** The user supplies a repo at the end of the project; anything that needs GitHub (Actions runs, the weekly ingest workflow) is queued until then.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` when Claude makes the commit.

## Environment notes

- Repo root: `C:\Users\aakur\OneDrive\Desktop\Sahi Ghar`. Commands below are bash (Git Bash) from the repo root unless a step says `cd backend` or `cd frontend`.
- Verified available: Python 3.13, uv 0.10, Node 22, npm 10, Docker 29. `psql` is not installed; use `docker exec` when a psql prompt is needed.
- The repo sits inside OneDrive. `backend/.venv` and `frontend/node_modules` are large and churn; consider pausing OneDrive sync for this folder or moving the repo out of OneDrive before Task 6.
- Vitest's default forked workers time out on this machine; `pool: 'threads'` is set in `vite.config.ts` (Task 14).

## File structure

```
spike/                          THROWAWAY (Tasks 1-4): probe.py, test_probe.py, samples/
docs/spikes/2026-09-maharera-access.md      the spike report (Tasks 2-5)
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

The MahaRERA adapter (parsers + fixtures from `spike/samples/`), the weekly ingest workflow (written locally, activated only once the user supplies a GitHub repo), the runner-reachability check (Task 3 Step 3), the S3-compatible `RawStore`, deployment (Neon/Render/Vercel/R2), and the three-builder manual cross-check. They depend on the spike's chosen data-access path and field lists, so writing them now would target an unverified source.

---

## Part 1 — Slice 0: Access spike

Throwaway investigation. Output is a report and a decision, not shipped code. Tasks 2-4 are research tasks (evidence gathering; Task 3 only records a deferral), so their steps are commands and observations rather than red/green tests.

### Task 1: Spike probe tool

**Files:**
- Create: `spike/probe.py`
- Test: `spike/test_probe.py`

**Interfaces:**
- Produces: `python spike/probe.py URL [URL ...]` prints one dict per URL (`status`, `content_type`, `bytes`, `mentions_captcha`, `forms`, `saved`) and saves each response body under `spike/samples/`. `mentions_captcha(html: str) -> bool` is a hint, not a verdict.

- [ ] **Step 1: Write the failing test**

Create `spike/test_probe.py`:

```python
from probe import mentions_captcha


def test_detects_captcha_markers():
    assert mentions_captcha('<img src="/captcha.jpg">')
    assert mentions_captcha('<div class="g-recaptcha"></div>')
    assert not mentions_captcha("<form><input name='q'></form>")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with httpx --with pytest pytest spike/test_probe.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'probe'`

- [ ] **Step 3: Write the probe**

Create `spike/probe.py`:

```python
"""THROWAWAY spike tooling for docs/spikes/. Not imported by backend/.

Usage (from the repo root):
    SPIKE_CONTACT=<address-or-url> uv run --with httpx python spike/probe.py URL [URL ...]

Politeness: one request at a time, DELAY_SECONDS apart, identifiable User-Agent.
It only fetches and records. It never solves, works around or skips a CAPTCHA.
"""
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import httpx

DELAY_SECONDS = 3
SAMPLES = Path(__file__).parent / "samples"
CAPTCHA_HINTS = re.compile(r"captcha|g-recaptcha|hcaptcha|turnstile", re.I)


def mentions_captcha(html: str) -> bool:
    """A hint, not a verdict: a script bundle can mention 'captcha' without the page needing one."""
    return bool(CAPTCHA_HINTS.search(html))


def probe(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    SAMPLES.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:80]
    saved = SAMPLES / f"{slug}-{hashlib.sha256(response.content).hexdigest()[:8]}.html"
    saved.write_bytes(response.content)
    return {
        "url": url,
        "final_url": str(response.url),
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
        "mentions_captcha": mentions_captcha(response.text),
        "forms": len(re.findall(r"<form", response.text, re.I)),
        "saved": str(saved),
    }


def main(urls: list[str]) -> None:
    headers = {"User-Agent": f"SahiGharSpike/0.1 (research; {os.environ['SPIKE_CONTACT']})"}
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            if i:
                time.sleep(DELAY_SECONDS)
            try:
                print(probe(client, url), flush=True)
            except httpx.HTTPError as exc:
                print({"url": url, "error": f"{type(exc).__name__}: {exc}"}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Run the test, then smoke-test the tool on a harmless URL**

Run: `uv run --with httpx --with pytest pytest spike/test_probe.py -q -p no:cacheprovider`
Expected: `1 passed`

Run: `SPIKE_CONTACT=<a contact string you are comfortable putting in a User-Agent> uv run --with httpx python spike/probe.py https://example.com/`
Expected: one dict with `'status': 200`, `'mentions_captcha': False`. Then `rm -rf spike/samples`.
(`SPIKE_CONTACT` is the user's choice; ask them for it. Do not reuse their account email unprompted.)

- [ ] **Step 5: Commit**

```bash
git add spike/probe.py spike/test_probe.py
git commit -m "spike: add polite probe tool (throwaway)"
```

### Task 2: MahaRERA findings

**Files:**
- Create: `docs/spikes/2026-09-maharera-access.md`
- Create: `spike/samples/*` (generated by the probe; kept as evidence and later parser fixtures)

**Interfaces:**
- Consumes: `spike/probe.py` from Task 1.
- Produces: the report file with a filled findings table (questions 1-5, 7, 8 from the spec) that Tasks 3-5 extend and that Plan B is written from.

- [ ] **Step 1: Create the report skeleton**

Create `docs/spikes/2026-09-maharera-access.md` with exactly this content:

```markdown
# MahaRERA access spike

Run on: (fill: date)   By: (fill)   From: (fill: network/location)
Spec: docs/superpowers/specs/2026-09-21-sahi-ghar-design.md §3

## Findings (MahaRERA)

| # | Question | Finding | Evidence (file / URL / quote) |
|---|----------|---------|-------------------------------|
| 1 | Project search, promoter search, promoter complaint report reachable without a CAPTCHA? (one row per page) | (fill) | (fill) |
| 2 | How is data delivered (server-rendered HTML, XHR/JSON, PDF)? Endpoint URLs and methods | (fill) | (fill) |
| 3 | Pagination and filtering; can all projects be enumerated? | (fill) | (fill) |
| 4 | Fields per project / promoter / complaint. PAN? address? partners/directors? promoter past-experience or other-projects disclosure? | (fill) | (fill) |
| 5 | Original completion date, revised completion date, completion status present? | (fill) | (fill) |
| 6 | Reachable from a GitHub Actions runner? | (see Task 3) | |
| 7 | Request rate tolerated (at the polite rate used) | (fill) | (fill) |
| 8 | robots.txt and terms of use on automated access | (fill) | (fill) |
| 9 | rera-india review | (see Task 4) | |

## Karnataka and Telangana (shallow check)

(see Task 4)

## Decision

(see Task 5)
```

- [ ] **Step 2: Probe robots.txt, terms and the three data pages**

Run (from the repo root; one command so the 3-second spacing applies):

```bash
SPIKE_CONTACT=<contact> uv run --with httpx python spike/probe.py \
  https://maharera.maharashtra.gov.in/robots.txt \
  https://maharera.maharashtra.gov.in/ \
  https://maharera.maharashtra.gov.in/projects-search-result \
  https://maharera.maharashtra.gov.in/promoters-search-result \
  https://maharera.maharashtra.gov.in/promoter-complaint-report
```

Read the output. A row with `error` (e.g. socket closed, 403, timeout) is itself a finding: record it, and try once more later in a normal browser before concluding anything. Open `spike/samples/*robots*` and read what it permits. From the saved home page, find the site's terms / disclaimer / privacy links and read them for anything about automated access. Fill question 8.

- [ ] **Step 3: Inspect the three pages in a normal browser session**

Open each of the three pages in a normal browser (the in-app browser tools are fine), with DevTools Network open. For each, run **one** ordinary search or open one report, and record:
- Is a CAPTCHA presented before results appear? If yes: record it (screenshot or quoted text) and **stop on that page**. Do not attempt OCR, solving services, replaying tokens, or any other workaround.
- When results do load: is it a server-rendered page, or an XHR call? Copy the request URL, method, and a short sample of the response into `spike/samples/` (e.g. `maharera-projects-xhr-sample.json`).
- How does paging work (page number parameter, "next" link, total count)? Is there a way to filter by state district or registration number?
- What fields appear per result and on one project detail page: promoter name, promoter ID, PAN, registered address, partners/directors, original and revised completion dates, completion status, and any "past experience" / "other projects by promoter" section.

Do not click through more than a handful of records, and keep at least 3 seconds between page loads.

- [ ] **Step 4: Fill questions 1-5, 7, 8 in the report**

Replace each `(fill)` in those rows with the finding and its evidence pointer. Write "not determined" with a reason rather than guessing. Fill "Run on / By / From" at the top.

- [ ] **Step 5: Verify no cell in rows 1-5, 7, 8 was left blank**

Run: `grep -n "(fill" docs/spikes/2026-09-maharera-access.md`
Expected: only lines belonging to rows 6 and 9, the Karnataka/Telangana section and the Decision section remain (they are completed in Tasks 3-5).

- [ ] **Step 6: Commit**

```bash
git add docs/spikes spike/samples
git commit -m "spike: MahaRERA access findings"
```

### Task 3: Runner reachability (deferred until the user supplies a GitHub repo)

The user will provide the GitHub repo once the project is done. **Do not create a repo, add a remote, or push anything.** Until then question 6 cannot be answered, so this task only records that fact; the real check is queued for the end (Step 3).

**Files:**
- Modify: `docs/spikes/2026-09-maharera-access.md` (question 6)

**Interfaces:**
- Produces: question 6 recorded as deferred, so Task 5 can mark Path A "conditional on the runner check" and the scheduled runner as undecided.

- [ ] **Step 1: Record question 6 as deferred**

In the report, replace row 6's `(see Task 3)` with: `Not determined: deferred until the user supplies a GitHub repo (they will provide it at the end of the project). Risk: Indian government sites sometimes block cloud/datacenter IPs, so a laptop-reachable page may still fail from a GitHub runner.`

- [ ] **Step 2: Commit**

```bash
git add docs/spikes
git commit -m "spike: defer GitHub runner reachability until a repo exists"
```

- [ ] **Step 3: Queued for the end: run the check once the user provides the repo**

Not part of the spike now. When the user hands over a GitHub repo and asks to wire it up, add this workflow as `.github/workflows/spike-reachability.yml`, commit and push it to **their** repo (confirm with them first), set the repository variable `SPIKE_CONTACT` to the contact string from Task 1, then run it with `gh workflow run spike-reachability.yml`, `gh run watch`, `gh run view --log`:

```yaml
name: spike-reachability
on: workflow_dispatch
jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Probe the MahaRERA pages (polite, one at a time)
        env:
          SPIKE_CONTACT: ${{ vars.SPIKE_CONTACT }}
        run: >
          uv run --with httpx python spike/probe.py
          https://maharera.maharashtra.gov.in/projects-search-result
          https://maharera.maharashtra.gov.in/promoters-search-result
          https://maharera.maharashtra.gov.in/promoter-complaint-report
```

A `403`, timeout or connection error in the log means the runner is likely blocked. Then update row 6 and the Decision's scheduled-runner line, and weigh fallbacks: a self-hosted runner on this machine, a small always-on VM, or running the weekly job locally.

### Task 4: Karnataka, Telangana and rera-india

**Files:**
- Modify: `docs/spikes/2026-09-maharera-access.md` (question 9 and the shallow-check section)

**Interfaces:**
- Consumes: `spike/probe.py`.
- Produces: enough information to confirm the adapter interface will not need reshaping for slice 2, and a reuse/discard call on `rera-india`.

- [ ] **Step 1: Shallow-probe Karnataka and Telangana**

```bash
SPIKE_CONTACT=<contact> uv run --with httpx python spike/probe.py \
  https://rera.karnataka.gov.in/ \
  https://rera.karnataka.gov.in/promoterComplaintReport \
  https://rera.telangana.gov.in/
```

Open the project search and the complaints/litigation pages of each in a normal browser and, for each state, write one short paragraph in "Karnataka and Telangana (shallow check)": reachable? CAPTCHA before results (yes/no, stop if yes)? data format? are promoter PAN, complaints and quarterly progress reports visible? Does anything suggest `discover()` + `parse()` (spec §4) cannot express this source?

- [ ] **Step 2: Review rera-india**

Open `https://github.com/mukuldas77-web/rera-india`. Record in question 9: what states and data it covers, whether it ships data or scrapers, its licence, last activity, and a reuse / learn-from / discard call. Do not copy code without confirming the licence permits it.

- [ ] **Step 3: Verify and commit**

Run: `grep -n "(fill" docs/spikes/2026-09-maharera-access.md`
Expected: only the Decision section remains.

```bash
git add docs/spikes spike/samples
git commit -m "spike: Karnataka/Telangana shallow check and rera-india review"
```

### Task 5: Decision and review gate

**Files:**
- Modify: `docs/spikes/2026-09-maharera-access.md` (Decision section)

**Interfaces:**
- Produces: the recorded data-access path per data type (spec §3 decision rule), which Plan B is written from.

- [ ] **Step 1: Apply the spec's decision rule**

For each of project data, promoter data and complaint data choose exactly one:
- **Path A** — reachable without a CAPTCHA and terms do not prohibit automated access. Runner reachability (Task 3) is deferred, so mark Path A as "conditional on the runner check" and name the fallback runner (this machine, or a small VM) if that check later fails.
- **Path B** — official data or assisted import: official downloads, the Unified RERA Portal, an RTI or data request to MahaRERA, or a human-assisted import tool that ingests files the user obtains manually.
- **Mixed** — Path A for open pages, Path B for gated ones.

- [ ] **Step 2: Write the Decision section**

Replace the "Decision" placeholder with:

```markdown
## Decision

- Project data: Path A | Path B | Mixed  (pick one; cite the table row)
- Promoter data: (same)
- Complaint data: (same)
- Scheduled runner: undecided until the runner check runs (Task 3 Step 3) | (or the alternative chosen and why)
- Rationale: 2-3 sentences citing rows 1-8
- Consequences for the Plan B adapter: which fields exist for grouping (PAN, address, partners/directors, past-experience disclosure) and scoring (original/revised/actual dates, completion status), and which are missing
```

Replace the text in the parentheses and the choices with the actual decision. Run `grep -n "(fill\|(pick\|(same" docs/spikes/2026-09-maharera-access.md`; expected: no output.

- [ ] **Step 3: Commit, then STOP for the user**

```bash
git add docs/spikes
git commit -m "spike: record MahaRERA data-access decision"
```

Show the user the report's Decision section and the field list. **Do not start Part 2 or Plan B until they confirm.** If a field the grouping or scoring rules need (spec §6, §7) turns out not to exist at all, raise it with the user instead of improvising a substitute.

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

Before writing: open the spike report's field list (Task 5). If the source publishes something the grouping or scoring rules depend on that these models lack, stop and raise it with the user rather than improvising.

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
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="A", status="ongoing", source_document_id=sd.id))
    session.flush()
    session.add(Project(state="MH", rera_reg_no="R1", promoter_id=pr.id, name="B", status="ongoing", source_document_id=sd.id))
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
    original_completion_date: Mapped[date | None]
    revised_completion_date: Mapped[date | None]
    actual_completion_date: Mapped[date | None]
    status: Mapped[str]  # completed | ongoing | other
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))


class Complaint(Base):
    __tablename__ = "complaint"
    __table_args__ = (UniqueConstraint("promoter_id", "complaint_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    promoter_id: Mapped[int] = mapped_column(ForeignKey("promoter.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"))
    complaint_ref: Mapped[str]
    status: Mapped[str]  # open | resolved
    filed_on: Mapped[date | None]
    resolved_on: Mapped[date | None]
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
  - `RawDoc(origin, kind, url, fetched_at, content_type, data)`, `PromoterRec`, `ProjectRec`, `ComplaintRec`, `ParsedRecords`, `Adapter` protocol (`state`, `origin`, `discover() -> Iterable[RawDoc]`, `parse(doc) -> ParsedRecords`).
  - `run_ingest(adapter, session, store, max_failure_rate=0.05) -> IngestSummary(total, ok, failed)`; raises `IngestFailureRateExceeded`.
  - `reparse_all(adapter, session, store, max_failure_rate=0.05) -> IngestSummary`.
  - Test double `tests.fakes.FakeAdapter(payloads: dict[str, dict])`.

- [ ] **Step 1: Write the failing test and the test double**

Create `backend/tests/fakes.py`:

```python
import json
from datetime import date

from sahighar.adapters.base import ComplaintRec, ParsedRecords, ProjectRec, PromoterRec, RawDoc
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
                ProjectRec(**{**x, **{k: _d(x.get(k)) for k in ("original_completion", "revised_completion", "actual_completion")}})
                for x in d.get("projects", [])
            ],
            complaints=[
                ComplaintRec(**{**x, **{k: _d(x.get(k)) for k in ("filed_on", "resolved_on")}})
                for x in d.get("complaints", [])
            ],
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
    "projects": [{"reg_no": "R1", "promoter_ref": "P1", "name": "Heights", "status": "completed",
                  "original_completion": "2022-01-01", "actual_completion": "2021-12-01"}],
    "complaints": [{"ref": "C1", "promoter_ref": "P1", "status": "open", "project_reg_no": "R1"}],
}
ORPHAN = {"projects": [{"reg_no": "R9", "promoter_ref": "NOPE", "name": "Ghost", "status": "ongoing"}]}


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
    status: str  # completed | ongoing | other
    city: str | None = None
    locality: str | None = None
    configurations: list[str] | None = None
    carpet_area_range: str | None = None
    original_completion: date | None = None
    revised_completion: date | None = None
    actual_completion: date | None = None


@dataclass
class ComplaintRec:
    ref: str
    promoter_ref: str
    status: str  # open | resolved
    project_reg_no: str | None = None
    filed_on: date | None = None
    resolved_on: date | None = None
    order_url: str | None = None


@dataclass
class ParsedRecords:
    promoters: list[PromoterRec] = field(default_factory=list)
    projects: list[ProjectRec] = field(default_factory=list)
    complaints: list[ComplaintRec] = field(default_factory=list)


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
             "carpet_area_range": j.carpet_area_range, "status": j.status,
             "original_completion_date": j.original_completion,
             "revised_completion_date": j.revised_completion,
             "actual_completion_date": j.actual_completion, "source_document_id": sd_id},
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
            {"project_id": project_id, "status": c.status, "filed_on": c.filed_on,
             "resolved_on": c.resolved_on, "order_url": c.order_url, "source_document_id": sd_id},
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
- Produces: `ProjectFacts(status, original_completion, actual_completion)`; `classify(p, today) -> (outcome, months_late | None)` with outcome in `on_time | late | overdue | in_progress | unknown`; `score(projects, open_complaints, resolved_complaints, today) -> dict` with keys `delivery`, `complaints`, `progress`, `overall` (shapes visible in the code below and consumed verbatim by the frontend `Score` type in Task 14).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scoring.py`:

```python
from datetime import date

from sahighar.scoring.v1 import ProjectFacts as P
from sahighar.scoring.v1 import classify, score

TODAY = date(2026, 9, 1)


def test_classify_completed():
    assert classify(P("completed", date(2024, 1, 1), date(2023, 12, 1)), TODAY) == ("on_time", None)
    assert classify(P("completed", date(2024, 1, 1), date(2024, 1, 1)), TODAY) == ("on_time", None)
    assert classify(P("completed", date(2024, 1, 1), date(2025, 1, 1)), TODAY) == ("late", 12.0)


def test_classify_ongoing_uses_original_date():
    assert classify(P("ongoing", date(2026, 3, 1), None), TODAY) == ("overdue", 6.0)
    assert classify(P("ongoing", date(2027, 1, 1), None), TODAY) == ("in_progress", None)


def test_classify_unknown_when_data_missing():
    assert classify(P("completed", date(2024, 1, 1), None), TODAY)[0] == "unknown"
    assert classify(P("ongoing", None, None), TODAY)[0] == "unknown"
    assert classify(P("other", date(2020, 1, 1), None), TODAY)[0] == "unknown"


def test_score_with_history_and_complaints():
    projects = [
        P("completed", date(2024, 1, 1), date(2023, 12, 1)),
        P("completed", date(2024, 1, 1), date(2023, 12, 1)),
        P("completed", date(2024, 1, 1), date(2025, 1, 1)),
    ]
    s = score(projects, open_complaints=1, resolved_complaints=2, today=TODAY)
    assert s["delivery"]["score"] == 67 and s["delivery"]["late"] == 1
    assert s["complaints"]["score"] == 67 and s["complaints"]["resolved"] == 2
    assert s["progress"]["available"] is False
    assert s["overall"] == 67


def test_insufficient_history_still_scores_complaints():
    projects = [P("completed", date(2024, 1, 1), date(2023, 12, 1)), P("ongoing", date(2027, 1, 1), None)]
    s = score(projects, open_complaints=0, resolved_complaints=0, today=TODAY)
    assert s["delivery"]["available"] is False and s["delivery"]["reason"] == "insufficient_history"
    assert s["complaints"]["score"] == 100
    assert s["overall"] == 100


def test_no_projects_means_not_enough_data():
    s = score([], 0, 0, TODAY)
    assert s["overall"] is None and s["complaints"]["reason"] == "no_projects"


def test_median_months_late_includes_overdue():
    projects = [P("completed", date(2024, 1, 1), date(2025, 1, 1)), P("ongoing", date(2026, 3, 1), None)]
    assert score(projects, 0, 0, TODAY)["delivery"]["median_months_late"] == 9.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sahighar.scoring'`

- [ ] **Step 3: Write the scoring module**

Create empty `backend/sahighar/scoring/__init__.py`. Create `backend/sahighar/scoring/v1.py`:

```python
"""Trust score v1: a scored checklist, not ML. All tunable numbers live here.

Every sub-score is shown with its inputs; the overall number is never shown alone.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

MIN_KNOWN_OUTCOMES = 2  # fewer projects with a known outcome -> "insufficient history"
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class ProjectFacts:
    status: str  # completed | ongoing | other
    original_completion: date | None
    actual_completion: date | None


def _months(days: int) -> float:
    return round(days / DAYS_PER_MONTH, 1)


def classify(p: ProjectFacts, today: date) -> tuple[str, float | None]:
    """Return (outcome, months_late). Outcome is on_time | late | overdue | in_progress | unknown.

    Lateness is always measured against the ORIGINAL completion date; an approved revised
    date is shown next to it elsewhere but never hides the delay.
    """
    original = p.original_completion
    if p.status == "completed":
        if original is None or p.actual_completion is None:
            return "unknown", None
        if p.actual_completion <= original:
            return "on_time", None
        return "late", _months((p.actual_completion - original).days)
    if p.status == "ongoing" and original is not None:
        if original < today:
            return "overdue", _months((today - original).days)
        return "in_progress", None
    return "unknown", None


def score(projects: list[ProjectFacts], open_complaints: int, resolved_complaints: int, today: date) -> dict:
    outcomes = [classify(p, today) for p in projects]
    counts = Counter(outcome for outcome, _ in outcomes)
    known = counts["on_time"] + counts["late"] + counts["overdue"]
    delays = [months for _, months in outcomes if months is not None]
    delivery_ok = known >= MIN_KNOWN_OUTCOMES
    delivery = {
        "available": delivery_ok,
        "reason": None if delivery_ok else "insufficient_history",
        "score": round(100 * counts["on_time"] / known) if delivery_ok else None,
        "on_time": counts["on_time"],
        "late": counts["late"],
        "overdue": counts["overdue"],
        "in_progress": counts["in_progress"],
        "unknown": counts["unknown"],
        "median_months_late": median(delays) if delays else None,
    }

    n = len(projects)
    complaints = {
        "available": n > 0,
        "reason": None if n > 0 else "no_projects",
        "score": round(100 * max(0.0, 1 - open_complaints / n)) if n > 0 else None,
        "open": open_complaints,
        "resolved": resolved_complaints,
        "project_count": n,
    }

    available = [c["score"] for c in (delivery, complaints) if c["available"]]
    return {
        "delivery": delivery,
        "complaints": complaints,
        "progress": {"available": False, "reason": "not_yet_available", "score": None},
        "overall": round(mean(available)) if available else None,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_scoring.py -v`
Expected: `7 passed`

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
    possible: overlapping named partner/director AND (same normalised address OR similar name).
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

    # Candidate pairs come only from shared partner/director names (every `possible` rule needs one).
    by_partner: dict[str, list[Promoter]] = {}
    for p in promoters:
        for name in {_norm(n) for n in (p.partners_or_directors or [])} - {""}:
            by_partner.setdefault(name, []).append(p)
    shared: dict[tuple[int, int], set[str]] = {}
    for name, people in by_partner.items():
        for i, a in enumerate(people):
            for b in people[i + 1:]:
                if find(a.id) != find(b.id):
                    shared.setdefault((min(a.id, b.id), max(a.id, b.id)), set()).add(name)

    by_id = {p.id: p for p in promoters}
    for (a_id, b_id), names in shared.items():
        a, b = by_id[a_id], by_id[b_id]
        same_address = bool(_norm(a.registered_address)) and _norm(a.registered_address) == _norm(b.registered_address)
        similarity = fuzz.token_set_ratio(_norm(a.name), _norm(b.name))
        if not (same_address or similarity >= NAME_SIMILARITY_THRESHOLD):
            continue
        evidence = {"shared_partners": sorted(names), "same_address": same_address, "name_similarity": round(similarity)}
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
Expected: `4 passed`

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
        {"reg_no": "MH-1", "promoter_ref": "P1", "name": "Shree Heights", "status": "completed", "city": "Pune",
         "original_completion": "2022-01-01", "actual_completion": "2021-12-01"},
        {"reg_no": "MH-2", "promoter_ref": "P2", "name": "Shree Gardens", "status": "completed",
         "original_completion": "2022-01-01", "actual_completion": "2023-01-01"},
    ],
    "complaints": [
        {"ref": "C1", "promoter_ref": "P1", "status": "open", "project_reg_no": "MH-1"},
        {"ref": "C2", "promoter_ref": "P2", "status": "resolved", "project_reg_no": "MH-2",
         "order_url": "https://example.test/order/C2.pdf"},
    ],
}
DOC_2 = {
    "promoters": [
        {"ref": "P3", "name": "Shree Realty Phase 2 LLP", "pan": "BBBPB0002B", "registered_address": "12 MG ROAD PUNE",
         "partners_or_directors": ["ramesh shah"]},
        {"ref": "P4", "name": "Zenith Constructions", "pan": "CCCPC0003C"},
    ],
    "projects": [
        {"reg_no": "MH-3", "promoter_ref": "P3", "name": "Shree Towers", "status": "ongoing",
         "original_completion": "2027-01-01"},
        {"reg_no": "MH-4", "promoter_ref": "P4", "name": "Zenith One", "status": "ongoing", "original_completion": "2027-06-01"},
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
    assert snapshot.breakdown["delivery"]["score"] == 50  # P3's ongoing project is not counted
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
from sahighar.scoring.v1 import ProjectFacts, score
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
        open_count = sum(c.status == "open" for c in cs)
        breakdown = score(
            [ProjectFacts(p.status, p.original_completion_date, p.actual_completion_date) for p in ps],
            open_count, len(cs) - open_count, today,
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
Expected: `20 passed`

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
- Produces: FastAPI `app` with `GET /search?q=` (projects only), `GET /projects/{id}`, `GET /promoters/{id}`. The trust payload keys are: `data_as_of`, `score_computed_at`, `score`, `group_promoters`, `delivery_history`, `complaints`, `possibly_related`, `sources` (keyed by stringified source document id); the project response adds `project`, the promoter response adds `promoter`. Every record carries `source_document_id`.

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
    assert body["score"]["delivery"]["score"] == 50
    assert body["score"]["complaints"]["score"] == 50
    assert body["score"]["overall"] == 50
    assert [p["name"] for p in body["possibly_related"]] == ["Shree Realty Phase 2 LLP"]
    assert body["possibly_related"][0]["evidence"]["same_address"] is True
    assert len(body["delivery_history"]) == 2  # possibly-related project is NOT counted
    assert body["data_as_of"] and body["score_computed_at"]


def test_every_record_links_to_a_source(client, session):
    body = client.get(f"/projects/{_project_id(session, 'MH-1')}").json()
    records = body["delivery_history"] + body["complaints"] + body["possibly_related"] + body["group_promoters"]
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

    delivery_history = []
    for p in session.scalars(select(Project).where(Project.promoter_id.in_(confirmed_ids)).order_by(Project.id)):
        outcome, months_late = classify(
            ProjectFacts(p.status, p.original_completion_date, p.actual_completion_date), scored_on
        )
        delivery_history.append({
            "project_id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no, "status": p.status,
            "original_completion_date": p.original_completion_date, "revised_completion_date": p.revised_completion_date,
            "actual_completion_date": p.actual_completion_date, "outcome": outcome, "months_late": months_late,
            "source_document_id": p.source_document_id,
        })
    complaints = [
        {"complaint_ref": c.complaint_ref, "project_id": c.project_id, "status": c.status, "filed_on": c.filed_on,
         "resolved_on": c.resolved_on, "order_url": c.order_url, "source_document_id": c.source_document_id}
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

    source_ids = {r["source_document_id"] for r in (*delivery_history, *complaints, *possibly_related, *group_promoters)}
    docs = session.scalars(select(SourceDocument).where(SourceDocument.id.in_(source_ids))).all()
    return {
        "data_as_of": max((d.fetched_at for d in docs), default=None),
        "score_computed_at": snapshot.computed_at if snapshot else None,
        "score": snapshot.breakdown if snapshot else None,
        "group_promoters": group_promoters,
        "delivery_history": delivery_history,
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
                          "status": p.status, "promoter_id": p.promoter_id, "promoter_name": name}
                         for p, name in rows]}


@app.get("/projects/{project_id}")
def project(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    promoter = session.get(Promoter, p.promoter_id)
    return {
        "project": {"id": p.id, "name": p.name, "rera_reg_no": p.rera_reg_no, "city": p.city, "locality": p.locality,
                    "configurations": p.configurations, "carpet_area_range": p.carpet_area_range, "status": p.status,
                    "original_completion_date": p.original_completion_date,
                    "revised_completion_date": p.revised_completion_date,
                    "actual_completion_date": p.actual_completion_date,
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
Expected: `24 passed`. Two harmless deprecation warnings from Starlette's test client are expected.

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
- Produces: TypeScript types `Score`, `HistoryItem`, `ComplaintItem`, `RelatedItem`, `ProjectPayload`, `SearchResult`, `Source` mirroring the API; `searchProjects(q) -> Promise<SearchResult[]>`; `getProject(id) -> Promise<ProjectPayload>`; `formatDate(value: string | null): string`; `outcomeText(item): string`. `npm test` runs Vitest; the Vite dev server proxies `/api` to `http://localhost:8010`.

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
import { formatDate, outcomeText } from './format'

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

describe('outcomeText', () => {
  it('states lateness against the original date in plain words', () => {
    expect(outcomeText({ outcome: 'late', months_late: 12 })).toBe('Delivered 12 months after the original date')
    expect(outcomeText({ outcome: 'unknown', months_late: null })).toBe('Outcome not determinable from the filing')
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
  delivery: {
    available: boolean
    reason: string | null
    score: number | null
    on_time: number
    late: number
    overdue: number
    in_progress: number
    unknown: number
    median_months_late: number | null
  }
  complaints: {
    available: boolean
    reason: string | null
    score: number | null
    open: number
    resolved: number
    project_count: number
  }
  progress: { available: boolean; reason: string | null; score: number | null }
}

export type HistoryItem = {
  project_id: number
  name: string
  rera_reg_no: string
  status: string
  original_completion_date: string | null
  revised_completion_date: string | null
  actual_completion_date: string | null
  outcome: 'on_time' | 'late' | 'overdue' | 'in_progress' | 'unknown'
  months_late: number | null
  source_document_id: number
}

export type ComplaintItem = {
  complaint_ref: string
  status: 'open' | 'resolved'
  filed_on: string | null
  resolved_on: string | null
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
    status: string
    promoter_name: string
    source_document_id: number
  }
  data_as_of: string | null
  score_computed_at: string | null
  score: Score | null
  group_promoters: { promoter_id: number; name: string; source_document_id: number }[]
  delivery_history: HistoryItem[]
  complaints: ComplaintItem[]
  possibly_related: RelatedItem[]
  sources: Record<string, Source>
}

export type SearchResult = {
  id: number
  name: string
  rera_reg_no: string
  city: string | null
  status: string
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
import type { HistoryItem } from './api'

// The API sends naive UTC datetimes (no "Z"); without this the browser reads them as local time.
const asUtc = (value: string) => (/T[\d:.]+$/.test(value) ? `${value}Z` : value)

export function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(asUtc(value)).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

export function outcomeText(item: Pick<HistoryItem, 'outcome' | 'months_late'>): string {
  switch (item.outcome) {
    case 'on_time':
      return 'Delivered on time'
    case 'late':
      return `Delivered ${item.months_late} months after the original date`
    case 'overdue':
      return `${item.months_late} months past the original date, not yet completed`
    case 'in_progress':
      return 'In progress, original date not yet reached'
    default:
      return 'Outcome not determinable from the filing'
  }
}
```

- [ ] **Step 6: Run the tests, then the build**

Run: `cd frontend && npm test`
Expected: `Tests  3 passed` (3 in format.test.ts)

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
  project: { id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', city: 'Pune', locality: null, status: 'completed',
    promoter_name: 'Shree Realty LLP', source_document_id: 1 },
  data_as_of: '2026-09-01T00:00:00',
  score_computed_at: '2026-09-01T00:00:00',
  score: {
    overall: 50,
    delivery: { available: true, reason: null, score: 50, on_time: 1, late: 1, overdue: 0, in_progress: 0, unknown: 0, median_months_late: 12 },
    complaints: { available: true, reason: null, score: 50, open: 1, resolved: 1, project_count: 2 },
    progress: { available: false, reason: 'not_yet_available', score: null },
  },
  group_promoters: [{ promoter_id: 1, name: 'Shree Realty LLP', source_document_id: 1 }],
  delivery_history: [
    { project_id: 1, name: 'Shree Heights', rera_reg_no: 'MH-1', status: 'completed', original_completion_date: '2022-01-01',
      revised_completion_date: null, actual_completion_date: '2021-12-01', outcome: 'on_time', months_late: null, source_document_id: 1 },
    { project_id: 2, name: 'Shree Gardens', rera_reg_no: 'MH-2', status: 'completed', original_completion_date: '2022-01-01',
      revised_completion_date: '2022-06-01', actual_completion_date: '2023-01-01', outcome: 'late', months_late: 12, source_document_id: 2 },
  ],
  complaints: [
    { complaint_ref: 'C1', status: 'open', filed_on: null, resolved_on: null, order_url: null, source_document_id: 3 },
    { complaint_ref: 'C2', status: 'resolved', filed_on: null, resolved_on: null, order_url: 'https://example.test/C2.pdf', source_document_id: 3 },
  ],
  possibly_related: [
    { promoter_id: 3, name: 'Shree Realty Phase 2 LLP',
      evidence: { shared_partners: ['ramesh shah'], same_address: true, name_similarity: 85 }, source_document_id: 4 },
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
    expect(within(breakdown).getByText('Delivery history')).toBeInTheDocument()
    expect(within(breakdown).getByText(/1 of 2 past projects on time; 1 late \(median 12 months\)/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Progress vs promise/)).toBeInTheDocument()
    expect(within(breakdown).getByText(/Overall: 50\/100, the average of the sections above/)).toBeInTheDocument()
  })

  it('stamps the data date and states it is not a verdict', () => {
    render(<TrustPageView data={data} />)
    expect(screen.getByText(/Data as of 1 Sep(t)? 2026/)).toBeInTheDocument()
    expect(screen.getByText(/not an independent verdict/)).toBeInTheDocument()
  })

  it('puts a source link beside every delivery and complaint row', () => {
    render(<TrustPageView data={data} />)
    for (const name of ['Delivery history', 'Complaints']) {
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
    expect(within(block).getByText(/^Source, fetched/)).toBeInTheDocument()
    const history = screen.getByRole('region', { name: 'Delivery history' })
    expect(within(history).queryByText(/Phase 2/)).not.toBeInTheDocument()
  })

  it('says so when there is not enough data instead of showing a number', () => {
    const empty = { ...data, score: { ...data.score!, overall: null,
      delivery: { ...data.score!.delivery, available: false, score: null, reason: 'insufficient_history' } } }
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
  const { delivery, complaints, progress } = score
  const known = delivery.on_time + delivery.late + delivery.overdue
  return (
    <section aria-label="Score breakdown">
      <div className="grid gap-3 sm:grid-cols-3">
        <Section title="Delivery history" score={delivery.score}>
          {delivery.available
            ? `${delivery.on_time} of ${known} past projects on time; ${delivery.late + delivery.overdue} late` +
              (delivery.median_months_late !== null ? ` (median ${delivery.median_months_late} months).` : '.')
            : 'Not enough history to summarise (at least 2 completed or overdue projects are needed).'}
        </Section>
        <Section title="Complaints" score={complaints.score}>
          {complaints.available
            ? `${complaints.open} open, ${complaints.resolved} resolved, across ${complaints.project_count} registered projects.`
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
import { formatDate, outcomeText } from '../format'

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

      <section aria-label="Delivery history">
        <h2 className="text-lg font-semibold text-stone-900">Delivery history</h2>
        <p className="text-sm text-stone-600">
          Projects registered by {data.group_promoters.map((p) => p.name).join(', ')}. Lateness is measured against the
          original completion date; a revised date, if any, is shown beside it.
        </p>
        <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-stone-600">
            <tr><th>Project</th><th>Original date</th><th>Revised date</th><th>Actual</th><th>Outcome</th><th>Source</th></tr>
          </thead>
          <tbody>
            {data.delivery_history.map((h) => (
              <tr key={h.project_id} className="border-t border-stone-200 align-top">
                <td>{h.name} <span className="font-mono text-xs text-stone-500">{h.rera_reg_no}</span></td>
                <td>{formatDate(h.original_completion_date)}</td>
                <td>{formatDate(h.revised_completion_date)}</td>
                <td>{formatDate(h.actual_completion_date)}</td>
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
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="text-stone-600">
              <tr><th>Reference</th><th>Status</th><th>Filed</th><th>Resolved</th><th>Order</th><th>Source</th></tr>
            </thead>
            <tbody>
              {data.complaints.map((c) => (
                <tr key={c.complaint_ref} className="border-t border-stone-200 align-top">
                  <td className="font-mono">{c.complaint_ref}</td>
                  <td>{c.status === 'open' ? 'Open' : 'Resolved'}</td>
                  <td>{formatDate(c.filed_on)}</td>
                  <td>{formatDate(c.resolved_on)}</td>
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
            Records of possibly related entities (not counted in this score). These are matched on overlapping
            partners or directors plus a shared address or similar name; the filings do not confirm a link.
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {data.possibly_related.map((r) => (
              <li key={r.promoter_id}>
                {r.name}: shares {r.evidence.shared_partners.join(', ')}
                {r.evidence.same_address ? '; same registered address' : `; name similarity ${r.evidence.name_similarity}%`}{' '}
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
Expected: `Tests  8 passed` (3 format + 5 trust page)

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
Expected: build succeeds; `Tests  8 passed`.

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
- Breakdown shows Delivery history 50/100 ("1 of 2 past projects on time; 1 late (median 12 months)"), Complaints 50/100 ("1 open, 1 resolved, across 2 registered projects"), Progress vs promise "—", then "Overall: 50/100, the average of the sections above that have data."
- Delivery table lists Shree Heights and Shree Gardens; **Shree Towers is absent**. Each row has a "Source, fetched ..." link to `https://example.test/demo/doc-1`.
- Complaints table shows C1 (Open) and C2 (Resolved) with an "Original order" link on C2.
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
| §3 Slice 0 spike (questions 1-9, shallow K/T check, decision rule) | Tasks 1-5; question 6 (runner) deferred until a repo exists |
| §4 adapter interface, raw store (local impl) | Tasks 6, 9 |
| §4 S3-compatible raw store | Plan B (deployment) |
| §5 data model, idempotent upserts, raw-first | Tasks 7, 8, 9 |
| §6 grouping (PAN / possible rules, presentation rule) | Tasks 11, 15 (UI separation) |
| §7 trust score v1 | Task 10, 12 |
| §8 API | Task 13 |
| §9 frontend | Tasks 14-16 |
| §11 failure handling (per-document isolation, threshold, re-parse) | Task 9 |
| §11 weekly workflow, hosting | Plan B |
| §12 testing (fixtures, unit, contract, e2e) | Tasks 9-13, 15; parser fixture tests and the manual 3-builder check are Plan B |
| §13 success criteria: slice 0 | Task 5 |
| §13 success criteria: slice 1 (real MahaRERA data, live cross-check) | Plan B; the core is proven here on fixtures |

**Known limits carried in the code (each marked `ponytail:` where it is a deliberate corner):** grouping and snapshots are rebuilt from scratch on every `refresh` (no history, group ids unstable); `search` is a substring scan (fine at slice-1 volume, add a trigram index if it is not); a complaint whose project is not yet ingested is stored with `project_id = NULL`.
