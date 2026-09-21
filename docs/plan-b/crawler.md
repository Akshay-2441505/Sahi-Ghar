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
| `--refresh-after-days N` | Certificates and complaint pages fetched within N days (default 90) are reused, not fetched again. |
| `--raw-store DIR` | Where fetched pages are kept (default `./raw_store`). |

After a crawl: `uv run python -m sahighar.cli reparse --origin maharera-web` re-runs the parsers over stored pages (no network).

Exit code: 0 finished or stopped at its budget, 1 some page failed to parse (named in the output), 2 bad usage, 3 blocked.

## What a crawl does, in order

1. **Project lists** for your pincodes (10 projects per page). Gives registration number, name, promoter name, district.
2. **Each builder's whole portfolio**, through the promoter search, because a builder's record only means something with all their projects.
3. **Certificates** for every project: the registration certificate, and the extension certificate only when the project has one and the first document does not already carry the extension history. They supply the original and the extended end dates.
4. **Complaints:** the complete complaint index (once, reused), then the complaint page of every builder in scope.

Rough cost at 3 s per request: a pincode of about 100 projects with their builders' portfolios is a few hundred requests (tens of minutes). The complaint index is about 540 requests (about 27 minutes) once. All of Maharashtra is about 4,900 list pages plus about 49,000 certificate requests: about two days of fetching.

## What you get, and what you do not

Gets: project registration number, name, promoter name, district; original registration end date; extended end date; complaints with status, project number, year and month, and the "applied for non-execution" flag.

Does **not** get (these live behind the CAPTCHA, or are not published on open pages): promoter PAN, partners or directors, actual completion status or date, quarterly progress reports. Registered-office **addresses** are not read yet (they are in the certificate text but the wording differs for companies and individuals). Consequence: the grouping rules that need PAN, partners or addresses stay quiet, and every promoter is its own group until that data arrives (RTI, or later work).

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

## Known limits

- **Promoter identity is the promoter's name** (case, spacing and punctuation ignored) because the public list gives no promoter id. "Pvt Ltd" and "Private Limited" are different promoters here on purpose; merging is grouping's job, and it says "possibly related". Two unrelated promoters with the same name would be merged.
- A capped portfolio or a trial scope gives **partial data for some builders**. Do not read scores from a trial as real.
- Complaints are matched by promoter name; a name spelled differently on the complaint pages will not match.
- Not scheduled: a run happens when you run it, on your machine. A weekly job needs somewhere to run (a small server, or a GitHub Actions runner once you give a repository; GitHub's servers might be blocked, which is untested).
- The site can change. When it does, the parser tests fail first; fix the parser and run `reparse`.

## If the crawler is blocked

It stops, prints `BLOCKED` with the reason, and exits with code 3. Do not retry for at least a day, do not lower the delay, and do not look for a way around it. Consider the RTI route for that data instead.
