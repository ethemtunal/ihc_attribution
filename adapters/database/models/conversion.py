from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from adapters.database.models.base import Base
from domain.entities.conversion import ConversionEntity


class Conversion(Base):
    __tablename__ = "conversions"

    conv_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    conv_date: Mapped[str] = mapped_column(String, nullable=False)
    conv_time: Mapped[str] = mapped_column(String, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, nullable=False)

    def to_entity(self) -> ConversionEntity:
        return ConversionEntity(
            conv_id=self.conv_id,
            user_id=self.user_id,
            conv_date=self.conv_date,
            conv_time=self.conv_time,
            revenue=self.revenue,
        )

    @classmethod
    def from_entity(cls, entity: ConversionEntity) -> "Conversion":
        return cls(
            conv_id=entity.conv_id,
            user_id=entity.user_id,
            conv_date=entity.conv_date,
            conv_time=entity.conv_time,
            revenue=entity.revenue,
        )
