# Sahi Ghar

2026-09-20 · @Someone

A free tool, starting with Maharashtra, Karnataka, and Telangana, that lets homebuyers check a builder's real track record before booking, and matches them to RERA-verified projects that fit their requirements — positioned against paid, NCR-only tools like ReraTracker and pre-launch pan-India attempts like Cubeyards, rather than duplicating either.

## Problem & why now

Millions of Indian homebuyers commit lakhs of rupees to a flat without ever checking the builder's actual delivery record, even though that record is legally public. A homebuyer advocacy body reports [27.6 lakh buyers currently stuck](https://www.etvbharat.com/en/business/homebuyers-body-fpce-says-27-dot-6-lakh-customers-stuck-with-delayed-rera-registered-projects-enn26090904794) in delayed RERA-registered projects, and the government's own [September 2025 launch of a "Unified RERA Portal"](https://www.newsonair.gov.in/union-minister-manohar-lal-launches-unified-rera-portal-to-boost-transparency-in-real-estate) shows it knows state-by-state RERA data is too fragmented to use as-is.

A funded competitor, [ReraTracker](https://reratracker.com/) (launched 2025, Gurugram), already aggregates RERA data — but only for NCR (Haryana, UP, Delhi RERA), as a paid (₹799–1,999/month) tool aimed at investors and brokers, not first-time buyers. Its own [live progress-tracking feature](https://reratracker.com/tracking) is still an unbuilt placeholder, and nothing in its materials resolves a builder's history across the separate legal entities (SPVs) it commonly registers per project.

There's also [Cubeyards](https://cubeyards.com/rera), pitched as free, consumer-facing RERA verification across all 32 states and union territories — but as of this writing its live database shows zero projects and zero registered realtors, suggesting the vision is staked out but not yet delivered. That's the actual opportunity: ship something real, even in two states, before a pan-India attempt gets its data pipeline working.

This product's opening move: go where ReraTracker doesn't (Maharashtra, via MahaRERA's own public search tools), stay free and buyer-first, and build the two things nobody's shipped yet — real progress-vs-promise tracking, and entity resolution across a builder's SPVs.

## Users & MVP scope

Primary user: a first-time homebuyer in Maharashtra, Karnataka, or Telangana (Mumbai/Pune/Bengaluru/Hyderabad-heavy) evaluating a specific project or shortlisting a few, who currently has no easy way to check a builder's real track record before paying a booking amount.

MVP features:

1. **Verify** — search a project or builder, see a plain-language track record: projects delivered on time vs. late (and by how much), open and resolved complaints, summarized from official RERA filings with a link back to the source for every claim.
2. **Match** — enter city/locality, configuration (1/2/3BHK), and a rough budget; get back only RERA-registered projects that fit, ranked by trust score first and fit second (budget is a soft filter — see Data Sources for why).
3. **Compare** — view 2–3 shortlisted projects side by side on track record, complaints, and progress.
4. **Track & alert** — for a project a user is watching, show reported construction progress against the promised timeline (from quarterly filings), and notify them if a new complaint appears or the promised date changes.

## Out of scope for v1

- Live unit-level listings with real market pricing — that needs a scraped-listings pipeline, a different and much heavier build than government filings. Revisit post-MVP.
- Any state beyond Maharashtra, Karnataka, and Telangana — these three have confirmed, comparably rich public RERA data (project search, promoter-level complaints or litigation history, and QPR-style progress filings). Tamil Nadu and Gujarat have solid project search and status tracking but unconfirmed public complaint/QPR visibility — worth verifying before committing engineering time, not assumed equally workable.
- User-generated reviews of builders — real value, but needs a moderation system before it's safe to ship. A v2 feature, not v1.
- Legal/title verification — a genuinely different, harder problem; RERA data doesn't resolve land-title issues.

## Success metrics

- Number of unique builders/projects with a complete, source-linked track record.
- Number of buyers who search before booking — the core behavior this product exists to create.
- Accuracy of the delay-risk score against actual outcomes, checked quarterly as projects complete or slip.

## Risks

- **Scraping fragility** — MahaRERA's site can change layout or add anti-bot friction; budget real maintenance time, not a one-time script.
- **Reputational/legal exposure** — never assert anything beyond what official RERA data says, always link the source, timestamp every claim. This is a due-diligence mirror of government data, not an independent verdict.
- **Fast-follow risk** — ReraTracker is funded and could add Maharashtra coverage or ship its own progress tracker before this does. The real moat is the entity-resolution feature, which needs real data-engineering effort to fast-follow.
