from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from adapters.database.models.base import Base
from domain.entities.session_cost import SessionCostEntity


class SessionCost(Base):
    __tablename__ = "session_costs"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_entity(self) -> SessionCostEntity:
        return SessionCostEntity(
            session_id=self.session_id,
            cost=self.cost,
        )

    @classmethod
    def from_entity(cls, entity: SessionCostEntity) -> "SessionCost":
        return cls(
            session_id=entity.session_id,
            cost=entity.cost,
        )
