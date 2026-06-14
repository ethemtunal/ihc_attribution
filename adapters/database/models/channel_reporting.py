from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from adapters.database.models.base import Base
from domain.entities.channel_reporting import ChannelReportingEntity


class ChannelReporting(Base):
    __tablename__ = "channel_reporting"

    channel_name: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    ihc: Mapped[float] = mapped_column(Float, nullable=False)
    ihc_revenue: Mapped[float] = mapped_column(Float, nullable=False)

    def to_entity(self) -> ChannelReportingEntity:
        return ChannelReportingEntity(
            channel_name=self.channel_name,
            date=self.date,
            cost=self.cost,
            ihc=self.ihc,
            ihc_revenue=self.ihc_revenue,
        )

    @classmethod
    def from_entity(cls, entity: ChannelReportingEntity) -> "ChannelReporting":
        return cls(
            channel_name=entity.channel_name,
            date=entity.date,
            cost=entity.cost,
            ihc=entity.ihc,
            ihc_revenue=entity.ihc_revenue,
        )
