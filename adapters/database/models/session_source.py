from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from adapters.database.models.base import Base
from domain.entities.session_source import SessionSourceEntity


class SessionSource(Base):
    __tablename__ = "session_sources"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    event_date: Mapped[str] = mapped_column(String, nullable=False)
    event_time: Mapped[str] = mapped_column(String, nullable=False)
    channel_name: Mapped[str] = mapped_column(String, nullable=False)
    holder_engagement: Mapped[int] = mapped_column(Integer, nullable=False)
    closer_engagement: Mapped[int] = mapped_column(Integer, nullable=False)
    impression_interaction: Mapped[int] = mapped_column(Integer, nullable=False)

    def to_entity(self) -> SessionSourceEntity:
        return SessionSourceEntity(
            session_id=self.session_id,
            user_id=self.user_id,
            event_date=self.event_date,
            event_time=self.event_time,
            channel_name=self.channel_name,
            holder_engagement=self.holder_engagement,
            closer_engagement=self.closer_engagement,
            impression_interaction=self.impression_interaction,
        )

    @classmethod
    def from_entity(cls, entity: SessionSourceEntity) -> "SessionSource":
        return cls(
            session_id=entity.session_id,
            user_id=entity.user_id,
            event_date=entity.event_date,
            event_time=entity.event_time,
            channel_name=entity.channel_name,
            holder_engagement=entity.holder_engagement,
            closer_engagement=entity.closer_engagement,
            impression_interaction=entity.impression_interaction,
        )
