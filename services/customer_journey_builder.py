from itertools import groupby
from pathlib import Path

from sqlalchemy.orm import Session

from adapters.database.repositories.session_repository import DBSessionsRepo
from domain.entities.customer_journey import CustomerJourneyEntity
from domain.entities.journey_row import JourneyRowEntity
from domain.entities.journey_touchpoint import JourneyTouchpointEntity


def build_customer_journeys(
    session: Session,
    start_date: str | None,
    end_date: str | None,
    output_dir: Path,
) -> Path:
    """Build customer journeys for in-range conversions, write JSONL, return path.

    One CustomerJourneyEntity per line. Each journey is the ordered list of
    touchpoint sessions preceding the conversion. The IHC algorithm treats
    the last session as the closer when no explicit conversion=1 marker is
    sent, so per-conversion ihc sums to 1.0 on real sessions only.

    Conversions with no prior sessions are skipped (the JOIN yields no rows
    for them).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "journeys.jsonl"
    tmp_path = output_dir / "journeys.jsonl.tmp"

    rows = DBSessionsRepo(session).get_journey_rows_for_range(start_date, end_date)

    with tmp_path.open("w") as f:
        for conv_id, group in groupby(rows, key=lambda r: r.conv_id):
            journey = _build_journey(conv_id, list(group))
            f.write(journey.model_dump_json() + "\n")

    tmp_path.replace(final_path)
    return final_path


def _build_journey(
    conv_id: str, group: list[JourneyRowEntity]
) -> CustomerJourneyEntity:
    head = group[0]
    touchpoints = [
        JourneyTouchpointEntity(
            session_id=r.session_id,
            timestamp=f"{r.event_date}T{r.event_time}",
            channel=r.channel_name,
            holder_engagement=r.holder_engagement,
            closer_engagement=r.closer_engagement,
            impression_interaction=r.impression_interaction,
        )
        for r in group
    ]
    return CustomerJourneyEntity(
        conversion_id=conv_id,
        conv_date=head.conv_date,
        conv_time=head.conv_time,
        revenue=head.revenue,
        user_id=head.conv_user_id,
        sessions=touchpoints,
    )
