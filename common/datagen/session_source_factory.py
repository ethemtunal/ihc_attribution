import factory
from factory.alchemy import SQLAlchemyModelFactory

from adapters.database.models.session_source import SessionSource
from tests.conftest import get_session_factory


class SessionSourceFactory(SQLAlchemyModelFactory):
    class Meta:
        model = SessionSource
        sqlalchemy_session_factory = get_session_factory
        sqlalchemy_session_persistence = "flush"

    session_id = factory.Sequence(lambda n: f"session-{n}")
    user_id = factory.Sequence(lambda n: f"user-{n}")
    event_date = "2024-01-01"
    event_time = "12:00:00"
    channel_name = "Direct"
    holder_engagement = 1
    closer_engagement = 0
    impression_interaction = 0
