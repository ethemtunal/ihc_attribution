import factory
from factory.alchemy import SQLAlchemyModelFactory

from adapters.database.models.attribution_customer_journey import (
    AttributionCustomerJourney,
)
from tests.conftest import get_session_factory


class AttributionCustomerJourneyFactory(SQLAlchemyModelFactory):
    class Meta:
        model = AttributionCustomerJourney
        sqlalchemy_session_factory = get_session_factory
        sqlalchemy_session_persistence = "flush"

    conv_id = factory.Sequence(lambda n: f"conv-{n}")
    session_id = factory.Sequence(lambda n: f"session-{n}")
    ihc = 0.5
