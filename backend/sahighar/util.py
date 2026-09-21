from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC. All DateTime columns store naive UTC so SQLite and Postgres agree."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
