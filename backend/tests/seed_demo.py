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
