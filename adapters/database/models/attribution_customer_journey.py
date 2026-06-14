from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from adapters.database.models.base import Base
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)


class AttributionCustomerJourney(Base):
    __tablename__ = "attribution_customer_journey"

    conv_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    ihc: Mapped[float] = mapped_column(Float, nullable=False)

    def to_entity(self) -> AttributionCustomerJourneyEntity:
        return AttributionCustomerJourneyEntity(
            conv_id=self.conv_id,
            session_id=self.session_id,
            ihc=self.ihc,
        )

    @classmethod
    def from_entity(
        cls, entity: AttributionCustomerJourneyEntity
    ) -> "AttributionCustomerJourney":
        return cls(
            conv_id=entity.conv_id,
            session_id=entity.session_id,
            ihc=entity.ihc,
        )
