import factory
from factory.alchemy import SQLAlchemyModelFactory

from adapters.database.models.session_cost import SessionCost
from tests.conftest import get_session_factory


class SessionCostFactory(SQLAlchemyModelFactory):
    class Meta:
        model = SessionCost
        sqlalchemy_session_factory = get_session_factory
        sqlalchemy_session_persistence = "flush"

    session_id = factory.Sequence(lambda n: f"session-{n}")
    cost = 10.0
