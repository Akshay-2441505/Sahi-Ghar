from sqlalchemy.orm import Session

from sahighar.db.models import Coverage
from sahighar.util import utcnow


def set_coverage(session: Session, key: str, complete: bool) -> None:
    """Record whether a kind of data was actually collected (see Coverage)."""
    row = session.get(Coverage, key) or Coverage(key=key)
    row.complete, row.updated_at = complete, utcnow()
    session.add(row)
    session.commit()
