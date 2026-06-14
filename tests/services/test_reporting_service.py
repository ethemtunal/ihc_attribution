from adapters.database.models.channel_reporting import ChannelReporting
from common.datagen.attribution_factory import AttributionCustomerJourneyFactory
from common.datagen.conversion_factory import ConversionFactory
from common.datagen.session_cost_factory import SessionCostFactory
from common.datagen.session_source_factory import SessionSourceFactory
from services.reporting_service import recompute_channel_reporting


def _seed(
    *,
    conv_id: str,
    user_id: str,
    conv_date: str,
    revenue: float,
    session_id: str,
    event_date: str,
    channel_name: str,
    cost: float,
    ihc: float,
) -> None:
    ConversionFactory.create(
        conv_id=conv_id,
        user_id=user_id,
        conv_date=conv_date,
        conv_time="12:00:00",
        revenue=revenue,
    )
    SessionSourceFactory.create(
        session_id=session_id,
        user_id=user_id,
        event_date=event_date,
        event_time="10:00:00",
        channel_name=channel_name,
    )
    SessionCostFactory.create(session_id=session_id, cost=cost)
    AttributionCustomerJourneyFactory.create(
        conv_id=conv_id, session_id=session_id, ihc=ihc
    )


def test_returns_zero_and_writes_nothing_when_no_source_data(ihc_db):
    """
    GIVEN empty source tables
    WHEN recompute_channel_reporting runs
    THEN it returns 0 and channel_reporting stays empty.
    """
    total = recompute_channel_reporting(ihc_db)

    assert total == 0
    assert ihc_db.query(ChannelReporting).count() == 0


def test_writes_one_row_per_channel_event_date_pair(ihc_db):
    """
    GIVEN attribution rows spanning two channels and two event_dates
    WHEN recompute_channel_reporting runs
    THEN channel_reporting has 4 rows.
    """
    for sid, ch, date in [
        ("s1", "SEA", "2024-01-01"),
        ("s2", "SEA", "2024-01-02"),
        ("s3", "Display", "2024-01-01"),
        ("s4", "Display", "2024-01-02"),
    ]:
        _seed(
            conv_id=f"c_{sid}",
            user_id=f"u_{sid}",
            conv_date="2024-01-05",
            revenue=100.0,
            session_id=sid,
            event_date=date,
            channel_name=ch,
            cost=10.0,
            ihc=1.0,
        )

    total = recompute_channel_reporting(ihc_db)

    assert total == 4
    keys = sorted(
        (r.channel_name, r.date) for r in ihc_db.query(ChannelReporting).all()
    )
    assert keys == [
        ("Display", "2024-01-01"),
        ("Display", "2024-01-02"),
        ("SEA", "2024-01-01"),
        ("SEA", "2024-01-02"),
    ]


def test_rerunning_is_idempotent(ihc_db):
    """
    GIVEN recompute_channel_reporting was already run
    WHEN it runs again with the same source data
    THEN row count and values stay the same.
    """
    _seed(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-05",
        revenue=100.0,
        session_id="s1",
        event_date="2024-01-01",
        channel_name="SEA",
        cost=10.0,
        ihc=1.0,
    )

    recompute_channel_reporting(ihc_db)
    recompute_channel_reporting(ihc_db)

    rows = ihc_db.query(ChannelReporting).all()
    assert len(rows) == 1
    assert rows[0].cost == 10.0
    assert rows[0].ihc == 1.0
    assert rows[0].ihc_revenue == 100.0
