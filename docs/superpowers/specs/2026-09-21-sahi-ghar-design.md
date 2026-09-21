# Sahi Ghar — Design Spec: Slice 0 (Access Spike) + Slice 1 (Maharashtra Verify)

Date: 2026-09-21
Source docs: `PRD.md`, `DESIGN.md`, `TECH_STACK.md`, `DATA_SOURCES.md`
Approved plan: `~/.claude/plans/the-folder-contains-all-goofy-stardust.md`
Amended 2026-09-21 after the spike (`docs/spikes/2026-09-maharera-access.md`): data path is **open public pages, read politely by a bounded crawler (owner's later decision), with data requests as a second source** (first decided as official data only), the delivery metric is based on **registration end dates**, complaints use the site's stages, and grouping gains an address+name rule. Sections 3-8 reflect this.

## 1. Goal and scope

Sahi Ghar lets a homebuyer check a builder's real RERA track record before booking. The long-term scope is Maharashtra, Karnataka and Telangana, with four features (Verify, Match, Compare, Track & alert). This spec covers only the first two slices:

- **Slice 0 — Access spike:** find out how MahaRERA data can actually be obtained.
- **Slice 1 — Maharashtra Verify:** ingest MahaRERA data, group related promoters, compute a trust score, and serve a search page and a project trust page.

Out of scope for this spec (later slices, see §10): Karnataka and Telangana adapters, QPR ingestion, Track/watchlist/alerts, Match, Compare, MCA data, complaint-order summarisation, the delay-risk ML model, user accounts.

Fixed decisions:

1. All three states are the goal. The adapter interface is designed for three states now; only MahaRERA is implemented in slice 1.
2. The spike precedes any parser code. The adapter interface is source-agnostic. **Owner decision after the spike: first official data only, then (later the same day) crawling MahaRERA's open pages politely and in bounded runs is approved, trial first.** Two real adapters exist: a web adapter that reads the open pages (never the CAPTCHA-gated detail app; stops for good on any refusal or CAPTCHA) and a file-import adapter for data obtained by data request or RTI.
3. **No CAPTCHA solving or bypass, ever.** If a page is CAPTCHA-gated, use another route (§3).
4. Slice 1 builder grouping is rule-based and uses RERA data only. MCA data is added later as another evidence source.
5. Stack follows `TECH_STACK.md`: Python + FastAPI + PostgreSQL, React + Vite + Tailwind.

## 2. Principles

- Nothing is stated beyond what official RERA data says. Every figure links to the stored source document and is stamped "as of <date>".
- The product is a mirror of government records, not a verdict. Wording is neutral ("2 complaints open") never judgemental ("unreliable builder").
- Related-entity grouping is never asserted unless the filings themselves prove it.
- No ads, no "featured" builders, no sales tone (`DESIGN.md`).

## 3. Slice 0 — Access spike

**Purpose:** answer one question with evidence: *how do we get MahaRERA project, promoter and complaint data reliably, legitimately and cheaply?*

**Output:** `docs/spikes/2026-09-maharera-access.md`. Spike code lives in `spike/`, is labelled throwaway, and is never imported by `backend/`.

**Questions to answer (MahaRERA in depth):**

| # | Question | Evidence to record |
|---|----------|--------------------|
| 1 | Are project search, promoter search and the promoter complaint report reachable without a CAPTCHA? | Per page: yes/no, with a screenshot or response sample |
| 2 | How is data delivered (server-rendered HTML, XHR/JSON, PDF)? | Request/response samples, endpoint URLs |
| 3 | How does pagination and filtering work; can we enumerate all projects? | Query parameters, page counts, total results |
| 4 | Which fields exist per project, promoter and complaint? Is PAN, address, or director/partner data published? Do project pages carry a promoter past-experience / other-projects disclosure? | Field list per record type (drives the grouping rules in §6) |
| 5 | Are original and revised completion dates and completion status both present? | Sample records (drives the delay calculation in §7) |
| 6 | Are the pages reachable from a GitHub Actions runner, not just a laptop? | One workflow run's result |
| 7 | What request rate is tolerated without errors? | Observed at a deliberately low rate, never stress-tested |
| 8 | What do robots.txt and the site's terms of use say about automated access? | Quoted or linked text |
| 9 | What does `mukuldas77-web/rera-india` already cover? | Short review; reuse or discard |

**Shallow check (K-RERA and Telangana RERA):** for each state's project search and complaint pages: reachable, CAPTCHA yes/no, data format. One paragraph each. Purpose: make sure the adapter interface (§4) will not need reshaping for slice 2.

**Rules for the spike:**

- Low request rate, identifiable User-Agent, no parallel hammering.
- If a CAPTCHA appears, stop on that page and record it. Do not use OCR, solving services, or session tricks.
- Store sample responses under `spike/samples/` (they later become parser test fixtures if the path is a scrape).

**Decision rule (the spike ends by choosing one path per data type):**

- **Path A — direct automated fetch:** all of project, promoter and complaint data are reachable without CAPTCHA, terms do not prohibit it, and it works from a GH Actions runner (or a documented alternative runner).
- **Path B — official data or assisted import:** any needed page is CAPTCHA-gated or prohibited. Use official downloads, the Unified RERA Portal, an RTI or data request to MahaRERA, or a human-assisted import tool that ingests files the user obtains manually.
- **Mixed:** use Path A for open pages and Path B for gated ones. The adapter interface supports this (§4).

The choice is written into the spike report. **Outcome (2026-09-21): first Path B, then reversed by the owner to Path A for the open pages, trial first.** The open Maharashtra pages (project list, complaints, registration and extension certificates) were found to be CAPTCHA-free; the detail app that holds PAN, partners and completion status is CAPTCHA-gated and off-limits regardless. The findings remain the reference for which fields exist.

## 4. Slice 1 architecture

Monorepo layout:

```
backend/sahighar/
  adapters/   base.py (interface), maharera.py
  ingest/     runner: fetch -> store raw -> parse -> upsert
  resolve/    rule-based promoter grouping
  scoring/    trust score v1 (pure functions)
  api/        FastAPI routes
  db/         SQLAlchemy models, Alembic migrations
backend/tests/   fixtures/ per adapter
frontend/        React + Vite + Tailwind
.github/workflows/ingest.yml
```

Data flow:

```
source (site / file / manual) -> adapter -> raw store + source_document row
   -> parsed records (each tagged source_document_id) -> Postgres
   -> resolve (groups) -> scoring (score_snapshot) -> API -> frontend
```

**Adapter interface** (one per state, one implementation per source path):

- `state` (`MH` | `KA` | `TG`) and `origin` (label such as `maharera-web` or `file-import`).
- `discover() -> Iterable[RawDoc]` — yields every raw document the source provides. How it traverses (paging, per-promoter complaint lists, reading a folder of files) is the adapter's own business. Contract: a promoter is introduced (as a `PromoterRec` in that document or an earlier one) before any project or complaint that references it.
- `parse(raw_doc) -> ParsedRecords` — pure function of the raw document (no network, no database), so re-parsing stored raw pages needs no network. `ParsedRecords` holds `PromoterRec`, `ProjectRec` and `ComplaintRec` lists keyed by natural RERA references.

`RawDoc` = origin, kind (`project` | `promoter` | `complaints`), url (`file:<name>` for imports), fetched_at, content type, bytes. Adapters do not touch the database; the runner does. A file-import adapter and a scraper adapter implement the same interface, which is how Path B and mixed sources fit. (This refines the earlier four-method sketch: one `discover()` generator lets each adapter keep its own crawl state.)

**Raw store:** content-addressed (sha256), gzip-compressed, behind a small `RawStore` interface (`put(bytes) -> key`, `get(key) -> bytes`). The local-directory implementation is built in slice 1 core; the S3-compatible implementation (prod, e.g. Cloudflare R2, because free-tier Postgres at ~0.5 GB is too small for raw pages) is added in the deployment plan. `source_document` rows hold origin, kind, url, fetched_at, sha256, content type, store key, and parse status/error; `(url, sha256)` is unique, and re-fetching unchanged content only moves `fetched_at`.

## 5. Data model (PostgreSQL)

- `source_document(id, origin, url, fetched_at, sha256, content_type, store_key, parse_status, parse_error)`
- `promoter(id, state, rera_promoter_ref, name, pan, registered_address, partners_or_directors jsonb, source_document_id)`
- `promoter_group(id)` and `group_membership(group_id, promoter_id, link_type, evidence jsonb)` — `link_type` is `filing_confirmed` or `possible` (§6).
- `project(id, state, rera_reg_no, promoter_id, name, city, locality, configurations jsonb, carpet_area_range, registration_end_date, extended_end_date nullable, source_document_id)` — `registration_end_date` is the end of the original registration validity (tied to, but not the same as, the proposed completion date) and is always labelled as such; `extended_end_date` is set only when an extension certificate exists. There is no actual-completion column: open data does not publish one.
- `complaint(id, promoter_id, project_id nullable, complaint_ref, status (raw text as published), stage (order_issued | pending | other), non_execution_applied bool, filed_year, filed_month, order_url nullable, source_document_id)` — the site publishes year and month only, so no day is invented.
- `score_snapshot(id, group_id, computed_at, breakdown jsonb, input_source_document_ids)`

Exact column sets are finalised from the spike's field list (question 4 and 5); fields the source does not publish stay nullable and the rules that depend on them degrade gracefully (§6, §7). Every parsed row carries `source_document_id`; this is the mechanism behind "every number links to its source".

Ingestion is idempotent: upserts key on the natural RERA reference; unchanged raw content (same sha256) is not re-stored.

## 6. Promoter grouping (rule-based)

Signals, strongest first. Which are usable is decided by the spike (question 4):

1. **Same PAN** on two promoter records → `filing_confirmed`.
2. **Same normalised registered address AND overlapping named partners/directors** → `possible`.
3. **Fuzzy promoter-name match (token-set ratio ≥ 90) AND overlapping named partners/directors** → `possible`.
4. **Same normalised registered address AND fuzzy promoter-name match (token-set ratio ≥ 90)**, with no partner data needed → `possible`. (Added after the spike: open data has names and registered-office addresses but no PAN or partners.)

A single weak signal alone (name only, address only, or partners only) creates no link. Each link stores its evidence (which fields matched, both source document ids).

**Known limit of RERA-only grouping.** An SPV is a separate legal entity with its own PAN, so shared-PAN links will mostly catch duplicate registrations of one entity, not sister SPVs. Most cross-SPV links will therefore be `possible` (and excluded from the score) until MCA director evidence lands in slice 5. This is accepted for slice 1 because the alternative is overstating a link. The spike (§3, question 4) checks whether MahaRERA project pages publish a promoter's past-experience or other-projects disclosure, which could close part of the gap from RERA data alone.

Presentation rule: delivery history and the score use **`filing_confirmed` links only**. `possible` links are shown separately: "Records of possibly related entities (not counted in this score)", listing evidence. This keeps the score defensible and the grouping honest. If PAN is not published for Maharashtra, the score falls back to the single promoter entity and possible links still display.

## 7. Trust score v1 (scored checklist, not ML)

Computed per `filing_confirmed` group. All constants live in one file so they can be recalibrated against outcomes (PRD success metric). Wording stays neutral: an extension is not necessarily the promoter's fault (blanket extensions exist), and a project past its end date without an extension may simply have been completed, so neither is called "late".

- **Registration schedule** (the "delivery history" in the design docs, renamed so it does not overclaim). Per project, from `registration_end_date`, `extended_end_date` and the computation date: *extended* (an extension certificate moved the end date later; months extended recorded), *not extended* (the original end date has passed and no extension is on record), *within registration* (original end date not yet reached), *unknown* (no end date). Score input = `not_extended / (extended + not_extended)`. Fewer than 2 evaluated projects (`extended + not_extended`) → "insufficient history", no sub-score. Median months extended (over extended projects) is displayed alongside.
- **Complaints.** Per complaint: `stage` (order issued, pending, other) and `non_execution_applied` (a buyer asked to enforce an order that was not complied with). *Unresolved* = stage pending, or non-execution applied. rate = `unresolved / project_count`; sub-score = `100 × max(0, 1 − rate)`. The counts (total, pending, order issued, order not executed) are shown. Zero projects → not computed.
- **Progress vs promise.** Shown as "not yet available" until slice 3 (QPR).

Overall = mean of the available sub-scores, **always displayed with the breakdown**, never alone. If no sub-score is available: "Not enough data". Each sub-score lists its inputs and links to source documents. Everything is stamped with `computed_at` and the underlying data's `fetched_at` (for an imported file, the date the file was obtained).

## 8. API

- `GET /search?q=` (q of at least 2 characters) — returns projects whose name, promoter name or RERA registration number contains the query (case-insensitive, literal match, max 25), each with its promoter's name, so a builder search lands on that builder's projects.
- `GET /projects/{id}` — trust-page payload: project facts, score breakdown, registration schedule, complaints (with order links), grouping evidence (both link types, labelled), source document list, data freshness.
- `GET /promoters/{id}` — promoter view of the same.

Errors: unknown id → 404; every response includes `data_as_of`. No auth in slice 1 (read-only public data).

## 9. Frontend

React + Vite + Tailwind. Two screens: search results and project trust page per `DESIGN.md` (public-record look; score breakdown before headline; plain-language delivery history; complaints table; "as of" dates; a source link beside every figure; the "possibly related" block clearly separated). Match, Compare, Watchlist are not in slice 1. Visual design work uses the design skills at plan time.

## 10. Roadmap after slice 1

Slice 2 Karnataka + Telangana adapters. Slice 3 QPR ingestion, progress-vs-promise, watchlist and alerts (needs an accounts/notification decision). Slice 4 Match + Compare. Slice 5 MCA evidence for grouping, Claude complaint-order summaries, delay-risk model.

## 11. Hosting and operations

Neon (Postgres), Render (API), Vercel (frontend), Cloudflare R2 (raw store), GitHub Actions weekly cron for ingest. If the spike shows GH runners are blocked, the ingest job runs from an alternative runner chosen then. All free tier until the MVP proves out.

Failure handling: per-document failure isolation (one bad page marks its `source_document.parse_status = failed` with the error and the run continues); a failure summary is printed and fails the workflow if the failure rate exceeds a threshold; a parser fix is applied by re-parsing stored raw documents.

## 12. Testing

- Parser tests against saved fixtures per adapter (the regression net for site changes).
- Pure-function unit tests for grouping and scoring, including edge cases: insufficient history, missing PAN, zero projects, project past due date.
- One API contract test; one end-to-end test (ingest fixtures → query API → assert trust payload and source links).
- Manual check: three real Maharashtra builders, comparing the trust page to the live MahaRERA record.

## 13. Success criteria

- **Slice 0:** the spike report exists, answers questions 1–9, and states the chosen path.
- **Slice 1:** the ingest job populates Postgres from real MahaRERA data; searching a real builder returns a trust page where every figure links to a stored source document; the three-builder manual check matches; re-parsing stored raw pages reproduces the same records.
