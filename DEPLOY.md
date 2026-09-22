# Deploying Sahi Ghar for free

Three accounts, no payment info needed: **Neon** (database), **Render** (API), **Vercel** (frontend).
Deploy in this order — each step needs something from the one before it.

## 1. Database: Neon

1. Sign up at [neon.tech](https://neon.tech) with your GitHub account.
2. Create a project (any region). Copy the connection string it gives you — it looks like
   `postgresql://user:password@host/dbname?sslmode=require`.
3. Change the scheme prefix from `postgresql://` to `postgresql+psycopg://` (the backend uses the `psycopg` v3
   driver, not `psycopg2`). Keep the rest, including `?sslmode=require`. That full string is your `DATABASE_URL`.
4. Load the schema and your existing data:
   ```bash
   cd backend
   DATABASE_URL="<your Neon URL>" uv run alembic upgrade head
   ```
   Then either re-run the crawl commands (see step 4) against Neon to populate it fresh, or restore your local
   `sahighar` database's data into Neon with `pg_dump`/`pg_restore` if you want to keep exactly what you have now.

## 2. Backend: Render

1. Sign up at [render.com](https://render.com) with GitHub, and give it access to `Akshay-2441505/Sahi-Ghar`.
2. New → Blueprint → pick this repo. Render reads `render.yaml` at the repo root and proposes one service,
   `sahighar-api`, with its root directory already set to `backend/`.
3. Before the first deploy, set the two env vars it asks for (marked `sync: false` in the blueprint, so Render
   prompts for them instead of reading them from the repo):
   - `DATABASE_URL` — the Neon connection string from step 1.
   - `SAHIGHAR_PII_KEY` — any long random string (e.g. `openssl rand -hex 32`). Keep it — losing it makes
     existing tokenized PAN/name matches unrecoverable, and it must stay the same value forever, including in CI.
4. Deploy. Once live, note the URL Render gives you, e.g. `https://sahighar-api.onrender.com`.
5. **Free-tier tradeoff**: this service sleeps after 15 minutes with no requests and takes ~30-60s to wake up on
   the next one. Fine for a low-traffic public tool; if that's annoying, Fly.io's free allowance avoids the
   sleep but wants a card on file.

## 3. Frontend: Vercel

1. Before deploying, edit `frontend/vercel.json` and replace `REPLACE-WITH-YOUR-RENDER-URL.onrender.com` with the
   actual Render URL from step 2. Commit and push that change.
2. Sign up at [vercel.com](https://vercel.com) with GitHub, then "Add New… → Project" → import
   `Akshay-2441505/Sahi-Ghar`.
3. **Root Directory**: set it to `frontend` in the import screen (Vercel can't read this from a config file
   before it knows where to look) — everything else (`npm run build`, output `dist`) is already in
   `frontend/vercel.json`.
4. Deploy. Vercel now serves the built React app and transparently proxies any `/api/*` request to your Render
   backend server-side — the browser only ever talks to your Vercel domain, so there's no CORS to configure.
5. Every push to your default branch redeploys automatically, on both Vercel and Render.

## 4. Scheduled data refresh: GitHub Actions

`.github/workflows/crawl.yml` runs the same weekly refresh job the project always intended (Maharashtra's 10
covered Pune pincodes + Karnataka statewide, complaints included), skipping anything already fetched within the
crawler's own 90-day freshness window — so most weeks are cheap, not a full re-crawl.

1. In the GitHub repo: Settings → Secrets and variables → Actions → New repository secret. Add:
   - `DATABASE_URL` — same Neon string as step 1.
   - `SAHIGHAR_PII_KEY` — the **exact same value** you set on Render. It must match, or newly tokenized PANs
     won't link up with ones already in the database.
   - `SAHIGHAR_CONTACT` — an email or URL the crawler puts in its User-Agent, so a site owner can reach you.
2. That's it — it runs Mondays at 03:00 UTC, and you can trigger it manually anytime from the Actions tab
   ("Run workflow").
3. If your repo is private, GitHub Actions gives 2,000 free minutes/month; this job's worst case is roughly
   3-4 hours a week, comfortably inside that. Public repos get unlimited free minutes.

## What doesn't need hosting

The 266 MB `raw_store/` (the crawler's raw-page cache, used for `reparse` after a parser fix without
re-fetching) is **not** read by the live API at all — only by the crawl/reparse CLI. It's fine for it to only
exist wherever you happen to run a crawl from; the GitHub Actions runner's copy is thrown away after each run,
which only costs you the ability to `reparse --origin X` without a live network re-fetch in CI specifically —
you can still do that locally anytime, since your own `raw_store/` keeps growing there.
