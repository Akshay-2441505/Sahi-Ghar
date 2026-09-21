# Sahi Ghar

Free tool that shows a homebuilder's RERA track record before you book. Docs: `PRD.md`, `DESIGN.md`, `TECH_STACK.md`, `DATA_SOURCES.md`; design spec in `docs/superpowers/specs/`; implementation plan in `docs/superpowers/plans/`; MahaRERA access findings and decisions in `docs/spikes/`.

Data path: official data only. Nothing in this repository fetches from a RERA website.

## Run locally

    docker run -d --name sahighar-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=sahighar -p 5433:5432 postgres:16
    cd backend && uv sync
    export DATABASE_URL=postgresql+psycopg://postgres:dev@localhost:5433/sahighar
    uv run alembic upgrade head
    uv run python -m tests.seed_demo          # loads fixture data (dev only)
    uv run uvicorn sahighar.api.main:app --port 8010
    # in another terminal
    cd frontend && npm install && npm run dev

## Import real data

When an authority's data files arrive (the RTI request draft is in `docs/plan-b/`), load them with:

    cd backend
    uv run python -m sahighar.cli import <folder> --obtained-on YYYY-MM-DD

See `docs/plan-b/file-import.md` for the expected tables and rules.

## Tests

    cd backend && uv run pytest
    cd frontend && npm test
