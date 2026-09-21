import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def _sessionmaker() -> sessionmaker:
    return sessionmaker(create_engine(os.environ["DATABASE_URL"]))


def get_session():
    with _sessionmaker()() as session:
        yield session
