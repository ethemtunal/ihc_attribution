import factory
from factory.alchemy import SQLAlchemyModelFactory

from adapters.database.models.conversion import Conversion
from tests.conftest import get_session_factory


class ConversionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Conversion
        sqlalchemy_session_factory = get_session_factory
        sqlalchemy_session_persistence = "flush"

    conv_id = factory.Sequence(lambda n: f"conv-{n}")
    user_id = factory.Sequence(lambda n: f"user-{n}")
    conv_date = "2024-01-02"
    conv_time = "12:00:00"
    revenue = 100.0
