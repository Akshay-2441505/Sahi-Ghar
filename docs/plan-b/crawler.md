# Reading MahaRERA's public pages (the crawler)

Decision history: first "official data only", then (2026-09-21, later the same day) the owner approved reading MahaRERA's **open** pages politely, in bounded runs, trial first. The RTI request (`data-request-maharera.md`) stays as an optional second source for what these pages do not show.

## The rules (fixed in code, `sahighar/adapters/polite.py`)

- One request at a time, at least **3 seconds** apart. Do not lower `--delay`.
- An honest User-Agent naming the project and **your contact**, so a site operator can reach you (`--contact`).
- **Any 401/403/429, any CAPTCHA, or a redirect to another host stops the crawl for good.** Nothing retries, waits out or works around it. If it happens: do not run again for at least a day.
- **Never** touches the CAPTCHA-gated project detail app (`maharerait.maharashtra.gov.in`). It only reads `maharera.maharashtra.gov.in`.
- Every run has a **request budget** (`--max-requests`, default 300). A budget stop is normal: everything fetched is saved, and running the same command again continues.
- Server errors are retried with backoff, a few times. A missing page is skipped and reported, not fatal.
- Every page is stored raw before it is parsed, so any number can be traced to the page it came from, and a parser fix can be applied to stored pages with no network (`reparse`).

## Run it

    cd backend
    DATABASE_URL=... uv run python -m sahighar.cli crawl --contact you@example.com --pincode 411001

| Flag | Meaning |
|---|---|
| `--pincode P` (repeatable) | Seed with the projects in this pincode (the site's own search filter). Required unless `--all-maharashtra`. |
| `--all-maharashtra` | Seed with every project (about 49,000: thousands of requests, many hours; run it on a server, not a laptop). |
| `--max-requests N` | Stop after N requests (default 300). |
| `--max-list-pages N` | Trial cap on pages read per pincode (10 projects per page). |
| `--max-promoter-pages N` | Cap on pages per builder's portfolio (default 20). A capped portfolio gives a partial record for that builder. |
| `--max-complaint-pages N` | Trial cap on the complaint index (about 540 pages exist). Without it, the whole index is read once and reused. |
| `--refresh-after-days N` | Certificates, applications, complaint pages **and list pages** fetched within N days (default 90) are reused, not fetched again. This is what makes a resumed run skip the ~1,000 list pages it already has. Use a small N for a full refresh. |
| `--raw-store DIR` | Where fetched pages are kept (default `./raw_store`). |

After a crawl: `uv run python -m sahighar.cli reparse --origin maharera-web` re-runs the parsers over stored pages (no network).

Exit code: 0 finished or stopped at its budget, 1 some page failed to parse (named in the output), 2 bad usage, 3 blocked.

## What a crawl does, in order

0. **Two notice lists** MahaRERA publishes, one request each: projects **kept in abeyance** ("Due to Lapse of Completion Date": bank accounts frozen, promoter barred from selling until compliant; about 4,200 projects) and **NCLT projects** (about 330, with registration status). Fetched every run because they change.
1. **Project lists** for your pincodes (10 projects per page). Gives registration number, name, promoter name, district.
2. **Each builder's whole portfolio**, through the promoter search, because a builder's record only means something with all their projects.
3. **The complaint index** (about 540 pages, once; free when already stored).
4. **Builder by builder, largest portfolio first**, everything about each builder before the next:
   - the **certificates** of each of its projects: the registration certificate, and the extension certificate only when the project has one and the first document does not already carry the extension history. They supply the original and the extended end dates;
   - its **registration application** (its **oldest** project first: newer applications show PANs masked, so up to three are tried until one has a usable PAN). From it: the organization or individual, the organization's PAN, the members' PANs (directors, partners, signatories; LLP partner lists are in a second table), the business address, and the declared past projects. The document is about 1.6 MB and also contains bank accounts, phone numbers, emails and Aadhaar numbers, so **the raw PDF is never stored**: it is reduced at once to a whitelisted extract of about 0.5 KB (see Privacy);
   - its **complaint page**.

   A run that stops early (budget, laptop closed) therefore leaves whole builders finished, not every builder half done.

Rough cost at 3 s per request: a pincode of about 100 projects with their builders' portfolios is a few hundred requests (tens of minutes). The complaint index is about 540 requests (about 27 minutes) once. All of Maharashtra is about 4,900 list pages plus about 49,000 certificate requests: about two days of fetching.

## Block on 2026-09-22

Run 2 of the central Pune crawl was blocked (HTTP 403 on a certificate request) after 89 requests, following yesterday's roughly 2,600 requests. The crawler stopped for good, as designed; nothing was retried. Everything fetched before the block is saved (about 25 more certificates, 40 extensions, 2 applications, 17 complaint pages). **Do not run the MahaRERA crawl again before 2026-09-23**, and even then start with a small `--max-requests` to check the site answers normally before resuming the full run.

## Manual cross-check against the live site (2026-09-22)

Three spot-checks, by hand in a browser (not the crawler -- ordinary page loads, unaffected by the block):
- **Gagan Uno** (P52100001400): registration number, project name, promoter, original completion date
  (31/12/2019), extended completion date (31/12/2027), and the full five-step extension history (including the
  four steps labelled "Covid Extension") all matched the stored `project` row and `extension_history` exactly.
- **Windermere Phase 1** (P52100003865): registration number, project, promoter, and completion date
  (31/12/2018) matched; the site's own "Extension Certificate: N/A" confirms our null `extended_end_date`.
- **11 Mayur** (P52100009083, abeyance notice): confirmed on the live "Due to Lapse of Completion Date" list,
  same promoter and project name as stored in `project_flag`.

Also confirms the block on 2026-09-22 is specific to the crawler's request pattern, not a blanket IP ban:
ordinary browsing of the same site worked normally throughout.

## Continuing the central Pune crawl (next run)

State after runs 1-2 (2026-09-22, run 2 stopped by the block above): 2,002 projects from 778 builders; 1,247 registration + 355 extension certificates stored; 25 applications, 23 complaint pages; complaint index complete. Roughly 2,100 requests remain (certificates for the rest of the projects, applications and complaint pages for the rest of the builders). Run 3 continues central Pune (2 to 2.5 hours, laptop on and plugged in) -- not before 2026-09-23, and start with a small `--max-requests` first:

    cd backend
    set -a && . ./.env && set +a
    export DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5433/sahighar"
    uv run python -m sahighar.cli crawl --contact you@example.com --max-requests 3500       --pincode 411001 --pincode 411002 --pincode 411004 --pincode 411005 --pincode 411009       --pincode 411011 --pincode 411030 --pincode 411037 --pincode 411042 --pincode 411044

It resumes where run 1 stopped (list pages, certificates and complaint pages already stored are reused) and completes the largest builders first. Safe to interrupt and rerun. Do not run two crawls against MahaRERA at once.

If the laptop was restarted, start the database first: `docker start sahighar-pg` (it is not set to start by itself). A backup of the trial database is in `backend/backups/` (gitignored); restore with `docker exec -i sahighar-pg pg_restore -U postgres -d sahighar --clean < backend/backups/<file>.dump`. The raw pages in `backend/raw_store/` can rebuild everything with `reparse` (no network), so keep that folder and `.env` (the PII key) together and backed up.

Pincode sizes for all 62 Pune city pincodes are in `pune-pincode-sizes.json` (project counts, one request each, measured 2026-09-21).

## What you get, and what you do not

Gets: project registration number, name, promoter name, district; original registration end date; extended end date; complaints with status, project number, year and month, and the "applied for non-execution" flag.

Also gets, from the registration application (as tokens, never displayed): the organization's PAN, its members' PANs, and the business address (organizations only). That is what lets the pages say two companies are one builder ("same PAN") or share members.

Also gets, from the application: each builder's **declared past projects** (original proposed and actual completion dates). These are stored, shown as the "Declared delivery record" (every row links to its source) and scored as "Declared delivery" (needs at least 2 completed projects; a group's repeated listings are counted once). They are the promoter's own declarations, labelled "not verified", and the declared score does not separate blanket extensions (e.g. COVID) from the promoter's own delays. The project's declared status, revised completion date and litigation flag are read but not yet stored or shown.

Also gets, from newer certificates, the **extension history** (each extension labelled as published, e.g. "Covid Extension -2"). Days granted under COVID-19 relief are shown apart and are not counted against the builder in the schedule score: a project extended only under COVID-19 relief counts with those that needed no extension of their own. Older certificates carry no history, so for those nothing can be separated.

Also gets, from the two notice lists, **regulator notices** about projects (kept in abeyance; NCLT). They carry a registration number and a promoter **name** (no promoter id), so a builder's notices are found by project number or by name. They are shown on the trust page beside the score with a source link, are never averaged into it, and **the overall score is withheld while any notice exists**.

**Survivorship bias found (2026-09-21):** projects on the abeyance list appear to be **missing from the site's public project search** (two listed projects returned nothing when searched by name, while a known project was found by the same query). In the trial data 53 of 67 notices named projects our search-based crawl never returned. So schedule figures leave out a builder's worst projects; the notices are how they are recovered. Names are matched only by normalised text, so a common builder name can pick up another company's notice: the page says "matched to this builder by name only".

Still **not** available from open pages: quarterly progress reports. The list of projects whose registration was **revoked or void ab initio** (`/projects-registration-revoked-initio-void`, about 90 projects, paged, order PDFs) has no registration number, only names, and is not read yet.

## Privacy

- PAN and personal names become **one-way tokens** (HMAC with `SAHIGHAR_PII_KEY`) before they reach any record. They can be matched, never shown, never recovered. Loading refuses to start without the key.
- **Keep the key** in `backend/.env` (gitignored) and back it up privately. Changing or losing it means every token must be regenerated by fetching the applications again.
- An individual's **home address** is never kept. Bank details, phone numbers, emails and Aadhaar numbers are never read into the extract.
- The stored application is a small JSON **extract**, versioned (`EXTRACT_VERSION`). Because the raw PDF is not kept, improving the extractor cannot re-parse old extracts: bump the version and the crawler fetches those applications again.
- Masked PANs (`xxxxxx1234`, as newer applications show) identify nobody and are never tokenised.
- Personal samples are gitignored (`spike/samples/hsm-application-*`); do not commit them.

## Things the live trial taught us (kept because they explain the code)

- The promoter search filter is named `promoters_name` (plural). The `promoter_name` in the site's own paging links is ignored and returns all promoters.
- The complaint report's name filter only works through a form POST, so the crawler reads the whole (unfiltered) complaint index instead and matches builders by name.
- **Certificates come in three shapes**, from either certificate endpoint: an old registration certificate (original end date), an old extension certificate (new end date only), and a **newer certificate** that states the *original completion date*, the current validity end, and a full extension history in one document (including entries the site labels "Covid Extension"). The parser reads them by content. The extension history is parsed only for its dates; the "Covid" labels are not stored or shown yet, but they are exactly the context the trust page's caution about extensions is for, and are the obvious next improvement.
- Some certificate requests return a small JSON error instead of a PDF ("can not fetch the object from repository"). That is treated as "no certificate", not a failure.
- The PDF text uses non-breaking spaces; the parser normalises them.
- Counts drift while you crawl (the complaint index went from 5,382 to 5,384 promoters during the day).

- **A partial crawl must never look clean.** The first trial showed "Complaints 100/100, none on record" for a builder whose complaints had simply never been collected (the complaint index was capped). Now complaints count as *collected* only after the **whole** complaint index has been read (or a complaints table was imported); a builder whose own complaint page was fetched is also known. Otherwise the complaint section says "Not collected for this data set yet", gives no score, and the overall number ignores it. This is recorded in the `coverage` table.

## Trial results (2026-09-21, pincode 411001, Pune)

About 140 requests over three capped runs, 3 seconds apart, no blocks or errors from the site. Result: 42 projects from 16 builders (the pincode itself has 103 projects; builders' other projects were pulled in by the portfolio phase), 41 with an original end date, 10 with an extension. Values were checked against the certificates by hand (for example GAGAN UNO: original 31/12/2019, current 31/12/2027). Complaints were **not** collected in the trial (index capped at 5 of about 540 pages), and the pages say so. Not yet run: the full complaint index scan (about 27 minutes, one-off), and anything larger than one pincode.

## Trial results, continued (pincode 411001, Pune; all 16 builders; complaint index scanned in full)

Complaints are now collected (560 requests, 27 minutes). All 16 builders have a PAN token and a business address, 9 have members (Cedrus Assets lists 27 partners, Canrich Builders 4). One confirmed link: **RIBERA PROJECTS LLP and VVV REALTORS AND DEVELOPERS PRIVATE LIMITED share a PAN**, i.e. one legal entity under two names, and the page groups them and says why. No two builders in this small sample share a member, so no "possibly related" links appeared. **Scores are not calibrated:** a builder with two extended projects and several complaints scores 0/100 overall, and the registration extension does not distinguish the site's "Covid Extension" entries. Do not publish scores until that is reviewed.

## Known limits

- **Promoter identity is the promoter's name** (case, spacing and punctuation ignored) because the public list gives no promoter id. "Pvt Ltd" and "Private Limited" are different promoters here on purpose; merging is grouping's job, and it says "possibly related". Two unrelated promoters with the same name would be merged.
- A capped portfolio or a trial scope gives **partial data for some builders**. Do not read scores from a trial as real.
- Complaints are matched by promoter name; a name spelled differently on the complaint pages will not match.
- Not scheduled: a run happens when you run it, on your machine. A weekly job needs somewhere to run (a small server, or a GitHub Actions runner once you give a repository; GitHub's servers might be blocked, which is untested).
- The site can change. When it does, the parser tests fail first; fix the parser and run `reparse`.

## If the crawler is blocked

It stops, prints `BLOCKED` with the reason, and exits with code 3. Do not retry for at least a day, do not lower the delay, and do not look for a way around it. Consider the RTI route for that data instead.
