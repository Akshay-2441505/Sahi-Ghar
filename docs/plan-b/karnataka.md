# Karnataka: two bulk pages, no crawl needed

Unlike MahaRERA, Karnataka RERA (`rera.karnataka.gov.in`) publishes builder-level delivery data as two whole-dataset
HTML tables. No PDFs, no per-project or per-builder requests, no CAPTCHA on either page (checked 2026-09-21).

## Run it

    cd backend
    DATABASE_URL=... uv run python -m sahighar.cli crawl-karnataka --contact you@example.com

Two requests total, 3 s apart, same politeness rules as MahaRERA (own honest User-Agent, stops for good on any
block or CAPTCHA). After a parser fix: `reparse --origin karnataka-web` (no network).

## What the two pages give

- `/viewRenewalProjects`, three tables: **approved extensions** (old and new completion date), **rejected**
  extension applications (proposed date, no extension recorded), and projects whose **completion date has
  expired** (with a further-extension date only when one was approved). Together these fill `registration_end`
  and `extended_end` the same way MahaRERA's certificates do.
- `/viewAllCompletedProjects`: projects that have **applied to close out as complete**, with the date first
  proposed and the date applied. This feeds the "declared" score component, worded the same as MahaRERA's
  self-declared past projects (applying to close out is not the same as a verified finish).

## What it does not give (yet)

- **No PAN, no partners, no address** — Karnataka's bulk pages carry a promoter *name* only, no identifier.
  Every Karnataka promoter is therefore its own group ("single_entity"); two companies of the same builder are
  never linked, and a common name is never flagged as "possibly related" either (that needs the partner/address
  data MahaRERA's applications have; Karnataka has no open equivalent found so far).
- **No complaints.** `/promoterComplaintReport` (about 2,018 promoters, counts only) and the per-promoter detail
  behind it were found in the spike but not read; every Karnataka builder's complaint score reads "not
  collected" until that is built. Complaint coverage is tracked per state (`Coverage` key `complaints:KA`), so
  this can never be masked by MahaRERA's own complaint coverage.
- Projects still in progress and not yet past their completion date are on neither page, so the full register is
  not covered, only completed/expired/extended projects.

## Source of the field-mapping detail

`docs/spikes/2026-09-maharera-access.md`, "Follow-up probe, 2026-09-21" — exact table columns and row counts as
fetched that day (979 approved extensions, 69 rejected, 2,859 expired, 3,527 applied-for-completion).
