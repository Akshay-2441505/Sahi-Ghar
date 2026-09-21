"""Import a folder of data files (CSV/Excel) from an authority and re-score everything.

    DATABASE_URL=... uv run python -m sahighar.cli import <folder> --obtained-on 2026-11-05

Exit code: 0 all files loaded, 1 some file failed (named below, with the reason; the rest still loaded), 2 bad usage.
"""
import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import select

from sahighar.adapters.file_import import FileImportAdapter
from sahighar.db.models import SourceDocument
from sahighar.db.session import session_scope
from sahighar.ingest.runner import run_ingest
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sahighar")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="load a folder of CSV/Excel files")
    imp.add_argument("folder")
    imp.add_argument("--obtained-on", type=date.fromisoformat, help="date you received the files, YYYY-MM-DD (default: file dates)")
    imp.add_argument("--state", default="MH", choices=["MH", "KA", "TG"])
    imp.add_argument("--raw-store", default="raw_store", help="where original files are kept (default: ./raw_store)")
    args = parser.parse_args(argv)

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"{folder} is not a folder")
        return 2
    adapter = FileImportAdapter(folder, args.state, args.obtained_on)
    with session_scope() as session:
        summary = run_ingest(adapter, session, LocalRawStore(Path(args.raw_store)), max_failure_rate=1.0)
        print(f"{summary.ok} files imported, {summary.failed} failed")
        for doc in session.scalars(select(SourceDocument).where(
                SourceDocument.origin == adapter.origin, SourceDocument.parse_status == "failed")):
            print(f"  FAILED {doc.url.removeprefix('file:')}: {doc.parse_error}")
        print(f"{refresh(session)} promoter groups scored")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
