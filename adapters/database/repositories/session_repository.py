from sqlalchemy import and_, or_, select

from adapters.database.models.conversion import Conversion
from adapters.database.models.session_source import SessionSource
from adapters.database.repositories.base_repository import BaseRepo
from domain.entities.journey_row import JourneyRowEntity


class DBSessionsRepo(BaseRepo):
    def get_journey_rows_for_range(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[JourneyRowEntity]:
        stmt = (
            select(
                Conversion.conv_id,
                Conversion.user_id.label("conv_user_id"),
                Conversion.conv_date,
                Conversion.conv_time,
                Conversion.revenue,
                SessionSource.session_id,
                SessionSource.event_date,
                SessionSource.event_time,
                SessionSource.channel_name,
                SessionSource.holder_engagement,
                SessionSource.closer_engagement,
                SessionSource.impression_interaction,
            )
            .select_from(Conversion)
            .join(
                SessionSource,
                and_(
                    SessionSource.user_id == Conversion.user_id,
                    or_(
                        SessionSource.event_date < Conversion.conv_date,
                        and_(
                            SessionSource.event_date == Conversion.conv_date,
                            SessionSource.event_time <= Conversion.conv_time,
                        ),
                    ),
                ),
            )
            .order_by(
                Conversion.conv_id,
                SessionSource.event_date,
                SessionSource.event_time,
            )
        )
        if start_date is not None:
            stmt = stmt.where(Conversion.conv_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(Conversion.conv_date <= end_date)

        rows = self.session.execute(stmt).all()
        return [
            JourneyRowEntity(
                conv_id=row.conv_id,
                conv_user_id=row.conv_user_id,
                conv_date=row.conv_date,
                conv_time=row.conv_time,
                revenue=row.revenue,
                session_id=row.session_id,
                event_date=row.event_date,
                event_time=row.event_time,
                channel_name=row.channel_name,
                holder_engagement=row.holder_engagement,
                closer_engagement=row.closer_engagement,
                impression_interaction=row.impression_interaction,
            )
            for row in rows
        ]
