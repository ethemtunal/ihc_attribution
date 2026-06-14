from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from adapters.database.models.attribution_customer_journey import (  # noqa: F401
    AttributionCustomerJourney,
)
from adapters.database.models.base import Base
from adapters.database.models.channel_reporting import ChannelReporting  # noqa: F401
from adapters.database.models.conversion import Conversion  # noqa: F401
from adapters.database.models.session_cost import SessionCost  # noqa: F401
from adapters.database.models.session_source import SessionSource  # noqa: F401

TEST_SESSION: Session | None = None


@pytest.fixture(scope="function")
def ihc_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    global TEST_SESSION
    TEST_SESSION = session
    try:
        yield session
    finally:
        TEST_SESSION = None
        session.close()
        engine.dispose()


def get_session_factory() -> Session:
    if TEST_SESSION is None:
        raise RuntimeError(
            "TEST_SESSION not initialized; the ihc_db fixture must run first"
        )
    return TEST_SESSION
