# Score methodology and sign-off status

Written 2026-09-22, for the owner's sign-off decision before any score is shown to a real user. This is the one
place that states plainly what the score is, what has been checked, and what has not.

## What the score is

A scored checklist (`sahighar/scoring/v1.py`), not a model: four independent components, each shown with its own
inputs, never just a number. **The overall figure is a mean of whichever components have data**, and is withheld
entirely — not shown as a lower number — when either condition below holds:

- fewer than `MIN_SECTIONS_FOR_OVERALL` (2) components have data, or
- the regulator has published any notice about the builder's projects (kept in abeyance, NCLT, etc.) — an
  average cannot speak for that, so the sections stay visible but the overall is hidden with a stated reason.

| Component | What it measures | Needs at least | Source |
|---|---|---|---|
| **Schedule** | Share of evaluated projects that did **not** need an extension attributable to the builder (COVID-labelled relief days are subtracted from "own" extension time and counted with "not extended") | 2 evaluated projects (extended, covid-only or not-extended; "within registration" and "unknown" don't count) | Registration/extension certificates (MH); renewals-page tables (KA) |
| **Complaints** | `1 - unresolved / total`, where unresolved = pending or "non-execution" requested | at least 1 project, and the complaint list for that builder actually collected (tracked per state — see Coverage below) | Complaint index + per-builder detail (both states) |
| **Declared** | Share of the builder's own declared past projects finished on or before its own first-proposed date | 2 declared completed projects (a group's repeated listings of the same project are counted once) | Registration application PDF (MH); "applied for completion" list (KA) |
| **Progress vs promise** | Not built. Needs quarterly progress reports, which are not available from any open source found so far. | — | — |

Never says "late" — an extension is not necessarily the builder's fault, and a project past its date with no
extension on record may simply be finished. Complaints and notices are shown in the regulator's own words.

## Verified against the live site

- **Maharashtra**, 2026-09-22, three spot-checks by hand in a browser (not the crawler): Gagan Uno's full
  five-step extension history including four steps labelled "Covid Extension", Windermere Phase 1's plain
  registration (no extension), and the "11 Mayur" abeyance notice — all matched the stored data exactly.
  Details: `crawler.md`, "Manual cross-check against the live site".
- **Karnataka**: not yet spot-checked by eye against the live site (today's crawler is the only client allowed on
  that host at a time, and it was busy). Instead, verified by a pure data-quality audit of everything already
  ingested (no network) — see `karnataka.md`, "Data-quality audit". That audit **found and fixed a real bug**:
  769 of 6,501 Karnataka projects (12%) had a cruder source silently overwriting the precise original/extended
  date pair, hiding a real extension. After the fix, only 2 explainable edge cases remain out of 6,501. A live
  spot-check of a handful of Karnataka projects is the natural next step before trusting the schedule numbers
  as fully as Maharashtra's.
- **Cross-state correctness**: two bugs were found and fixed where a fact collected for one state was silently
  read as if it applied to another (complaint coverage, and the withheld-overall wording). Both were caught
  before they could affect real (published) numbers — Karnataka currently has no PAN data, so the cross-state
  group scenario that would trigger the second bug cannot happen yet with real data, but the fix is in place for
  when it can.

## Coverage: what is actually known vs assumed

Coverage is tracked per state (`Coverage` table, keys `complaints:MH` / `complaints:KA`) specifically so that one
state's complete scan can never make another's missing data look clean. As of this write-up:

- Maharashtra: complaint index fully scanned; 778 promoter groups scored, covering central Pune only (10 of
  Maharashtra's roughly 4,900 list pages so far — a small fraction of the state; see `crawler.md`).
- Karnataka: complaint index fetched; per-builder detail pages are still being fetched (a long-running crawl,
  progress tracked in `karnataka.md`) — **not yet complete**, so Karnataka's "complaints" component is not yet
  marked collected and stays "not_collected" until that finishes.
- 5,588 promoter groups scored in total (779 MH + 4,848 KA promoters); 621 currently show an overall figure
  (need ≥2 components and no notice); 36 have their overall withheld specifically because of a regulator notice.

## Known limitations, by design

- **Grouping is PAN-only for `filing_confirmed` links.** Karnataka's open pages carry no PAN, so every Karnataka
  promoter is currently its own island — sister companies of the same builder are never linked there, unlike
  Maharashtra where a shared PAN merges them. This is a real gap in Karnataka's picture, not a bug.
- **"Possibly related" (shared partner/address) evidence** also depends on data Karnataka's bulk pages don't
  carry (partners, registered address); so far it only ever fires for Maharashtra.
- **Karnataka's declared/schedule split**: the "applied for completion" list's date is the promoter's own
  request to close out, not a verified finish — worded the same as Maharashtra's self-declared past projects.
- **Progress vs promise** is not available for either state; always shown as "not yet available", never omitted
  silently.
- **A builder name is not a builder ID** anywhere in this system except MahaRERA's PAN. Two different companies
  with the same or a very similar name can be merged (Maharashtra's "possible" links) or have a notice
  misattributed (`in_our_project_list: false` rows, matched by name only) — both cases are labelled, never hidden.

## Sign-off checklist (not done until these are)

1. Karnataka's complaint crawl finishes (currently running).
2. A handful of Karnataka projects spot-checked by hand against the live site, the same way Maharashtra's were.
3. The pre-existing Maharashtra "equal original/extended date" pattern (16 of 2,002 projects, documented in
   `karnataka.md`) is understood well enough to say it's benign with confidence, not just by inference.
4. The owner has looked at real trust pages for builders they recognise and confirmed the numbers read sensibly.

**Until all four are done, no score from this system should be shown to a real user or claimed as reliable.**
This document should be updated (not just re-read) once they are.
