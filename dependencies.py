import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///data/challenge.db",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Open a SQLAlchemy session, ensure it's closed on exit.

    Repos commit on their own write methods, so this helper only manages the
    open/close lifecycle — no commit/rollback handling needed here.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
