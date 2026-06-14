from sqlalchemy import insert

from adapters.database.models.attribution_customer_journey import (
    AttributionCustomerJourney,
)
from adapters.database.repositories.base_repository import BaseRepo
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)


class DBAttributionRepo(BaseRepo):
    def insert_many(self, entries: list[AttributionCustomerJourneyEntity]) -> None:
        if not entries:
            return
        stmt = insert(AttributionCustomerJourney).values(
            [e.model_dump() for e in entries]
        )
        self.session.execute(stmt)
        self.session.commit()
