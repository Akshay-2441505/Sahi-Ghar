"""Load data and re-score everything.

  Files from an authority (CSV/Excel):
    DATABASE_URL=... uv run python -m sahighar.cli import <folder> --obtained-on 2026-11-05
  MahaRERA's public pages, politely and in bounded runs:
    DATABASE_URL=... uv run python -m sahighar.cli crawl --contact you@example.com --pincode 411001

Exit code: 0 finished (or stopped at its request budget: run again to continue), 1 some document failed to parse,
2 bad usage, 3 the site blocked the crawler (stop; do not retry for a while).
"""
import argparse
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

from sahighar.adapters.file_import import FileImportAdapter
from sahighar.adapters.maharera_web import MahaReraWebAdapter
from sahighar.adapters.polite import BlockedError, BudgetExhausted, PoliteFetcher
from sahighar.db.models import SourceDocument
from sahighar.db.session import session_scope
from sahighar.ingest.coverage import set_coverage
from sahighar.ingest.runner import reparse_all, run_ingest
from sahighar.privacy import PrivacyKeyMissing, tokenize
from sahighar.rawstore import LocalRawStore
from sahighar.scoring.service import refresh
from sahighar.util import utcnow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sahighar")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="load a folder of CSV/Excel files")
    imp.add_argument("folder")
    imp.add_argument("--obtained-on", type=date.fromisoformat, help="date you received the files, YYYY-MM-DD (default: file dates)")
    imp.add_argument("--state", default="MH", choices=["MH", "KA", "TG"])
    imp.add_argument("--raw-store", default="raw_store", help="where original files are kept (default: ./raw_store)")
    crawl = sub.add_parser("crawl", help="read MahaRERA's public pages politely (bounded, resumable)")
    crawl.add_argument("--contact", default=os.environ.get("SAHIGHAR_CONTACT"),
                       help="email or URL put in the User-Agent so the site can reach you (or set SAHIGHAR_CONTACT)")
    crawl.add_argument("--pincode", action="append", default=[], help="seed the crawl with this pincode (repeatable)")
    crawl.add_argument("--all-maharashtra", action="store_true", help="seed with every project in Maharashtra (thousands of requests)")
    crawl.add_argument("--max-requests", type=int, default=300, help="stop after this many requests (default 300)")
    crawl.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3, do not go lower)")
    crawl.add_argument("--max-list-pages", type=int, help="cap list pages per pincode (trial runs)")
    crawl.add_argument("--max-promoter-pages", type=int, default=20, help="cap pages per builder's portfolio (default 20)")
    crawl.add_argument("--max-complaint-pages", type=int, help="cap pages of the complaint index (about 540 exist; trial runs)")
    crawl.add_argument("--refresh-after-days", type=int, default=90, help="skip certificates and complaint pages fetched within this many days")
    crawl.add_argument("--raw-store", default="raw_store", help="where fetched pages are kept (default: ./raw_store)")
    reparse = sub.add_parser("reparse", help="re-run the parsers over stored pages (no network), e.g. after a parser fix")
    reparse.add_argument("--origin", choices=["maharera-web", "file-import"], required=True)
    reparse.add_argument("--raw-store", default="raw_store")
    args = parser.parse_args(argv)
    if args.command == "crawl":
        return _crawl(args)
    if args.command == "reparse":
        return _reparse(args)

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"{folder} is not a folder")
        return 2
    if not _privacy_key_ok():
        return 2
    adapter = FileImportAdapter(folder, args.state, args.obtained_on)
    with session_scope() as session:
        summary = run_ingest(adapter, session, LocalRawStore(Path(args.raw_store)), max_failure_rate=1.0)
        if session.scalar(select(func.count()).select_from(SourceDocument).where(
                SourceDocument.origin == adapter.origin, SourceDocument.kind == "complaints", SourceDocument.parse_status == "ok")):
            set_coverage(session, "complaints", True)  # a complaints table means complaints were collected for everyone in it
        print(f"{summary.ok} files imported, {summary.failed} failed")
        for doc in session.scalars(select(SourceDocument).where(
                SourceDocument.origin == adapter.origin, SourceDocument.parse_status == "failed")):
            print(f"  FAILED {doc.url.removeprefix('file:')}: {doc.parse_error}")
        print(f"{refresh(session)} promoter groups scored")
    return 1 if summary.failed else 0


def _privacy_key_ok() -> bool:
    """Loading refuses to start without the key, so a personal identifier can never be stored untokenised."""
    try:
        tokenize("pan", "AAAAA0000A")
    except PrivacyKeyMissing as error:
        print(error)
        return False
    return True


def _crawl(args) -> int:
    if not args.pincode and not args.all_maharashtra:
        print("choose a scope: --pincode <code> (repeatable) or --all-maharashtra")
        return 2
    if not args.contact:
        print("a contact is required (--contact you@example.com or SAHIGHAR_CONTACT), so the site can reach you if needed")
        return 2
    if not _privacy_key_ok():
        return 2
    fetcher = PoliteFetcher(args.contact, args.delay, args.max_requests)
    with session_scope() as session:
        cutoff = utcnow() - timedelta(days=args.refresh_after_days)
        fresh = set(session.scalars(select(SourceDocument.url).where(
            SourceDocument.origin == MahaReraWebAdapter.origin, SourceDocument.parse_status == "ok",
            SourceDocument.fetched_at >= cutoff,
            SourceDocument.kind.in_(["registration_certificate", "extension_certificate", "complaints", "application"]))))
        store = LocalRawStore(Path(args.raw_store))
        index_pages = dict(session.execute(select(SourceDocument.url, SourceDocument.store_key).where(
            SourceDocument.origin == MahaReraWebAdapter.origin, SourceDocument.parse_status == "ok",
            SourceDocument.kind == "complaint_list", SourceDocument.fetched_at >= cutoff).order_by(SourceDocument.id)).all())
        adapter = MahaReraWebAdapter(fetcher, args.pincode or None, fresh.__contains__, args.max_list_pages,
                                     args.max_promoter_pages, args.max_complaint_pages,
                                     stored=lambda url: store.get(index_pages[url]) if url in index_pages else None)
        stopped = None
        try:
            run_ingest(adapter, session, store, max_failure_rate=1.0)
        except BudgetExhausted:
            stopped = "budget"
        except BlockedError as error:
            stopped = f"blocked: {error}"
        if adapter.complaint_index_complete:  # only a complete scan lets "no complaints found" mean anything
            set_coverage(session, "complaints", True)
        print(f"{fetcher.requests} requests")
        if stopped == "budget":
            print(f"stopped at the request budget ({args.max_requests}). Everything fetched is saved; run the same command again to continue.")
        elif stopped:
            print(f"BLOCKED: {stopped.removeprefix('blocked: ')}. Stopped for good. Do not retry for at least a day, and do not try to get around it.")
        for note in adapter.skipped:
            print(f"  skipped {note}")
        failed = session.scalars(select(SourceDocument).where(
            SourceDocument.origin == adapter.origin, SourceDocument.parse_status == "failed")).all()
        for doc in failed:
            print(f"  FAILED {doc.url}: {doc.parse_error}")
        print(f"{refresh(session)} promoter groups scored")
    return 3 if stopped and stopped != "budget" else (1 if failed else 0)


def _reparse(args) -> int:
    adapter = MahaReraWebAdapter(None) if args.origin == "maharera-web" else FileImportAdapter(Path("."))
    with session_scope() as session:
        summary = reparse_all(adapter, session, LocalRawStore(Path(args.raw_store)), max_failure_rate=1.0)
        print(f"{summary.total} documents re-parsed, {summary.failed} failed")
        for doc in session.scalars(select(SourceDocument).where(
                SourceDocument.origin == adapter.origin, SourceDocument.parse_status == "failed")):
            print(f"  FAILED {doc.url}: {doc.parse_error}")
        print(f"{refresh(session)} promoter groups scored")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
