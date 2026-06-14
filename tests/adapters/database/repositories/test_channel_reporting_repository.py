import pytest

from adapters.database.models.channel_reporting import ChannelReporting
from adapters.database.repositories.channel_reporting_repository import (
    DBChannelReportingRepo,
)
from common.datagen.attribution_factory import AttributionCustomerJourneyFactory
from common.datagen.conversion_factory import ConversionFactory
from common.datagen.session_cost_factory import SessionCostFactory
from common.datagen.session_source_factory import SessionSourceFactory

# ---------- recompute ----------


def test_recompute_writes_nothing_when_no_source_data(ihc_db):
    """
    GIVEN empty source tables
    WHEN recompute runs
    THEN channel_reporting stays empty.
    """
    DBChannelReportingRepo(ihc_db).recompute()

    assert ihc_db.query(ChannelReporting).count() == 0


def test_recompute_includes_sessions_with_no_attribution(ihc_db):
    """
    GIVEN a session with cost but no attribution
    WHEN recompute runs
    THEN the (channel, date) row appears with cost > 0 and ihc = 0.
    """
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="10:00:00",
        channel_name="FB & IG Ads",
    )
    SessionCostFactory.create(session_id="s1", cost=10.0)

    DBChannelReportingRepo(ihc_db).recompute()

    rows = ihc_db.query(ChannelReporting).all()
    assert len(rows) == 1
    assert rows[0].channel_name == "FB & IG Ads"
    assert rows[0].date == "2024-01-01"
    assert rows[0].cost == 10.0
    assert rows[0].ihc == 0.0
    assert rows[0].ihc_revenue == 0.0


def test_recompute_does_not_multi_count_cost_across_conversions(ihc_db):
    """
    GIVEN one session with cost=50 attributed to TWO different conversions
    WHEN recompute runs
    THEN that session's cost contributes ONCE (not twice) to the (channel, date) row.
         This is the bug guard for the multi-attribution case in real data.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-02",
        conv_time="12:00:00",
        revenue=100.0,
    )
    ConversionFactory.create(
        conv_id="c2",
        user_id="u1",
        conv_date="2024-01-03",
        conv_time="12:00:00",
        revenue=200.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="10:00:00",
        channel_name="SEA",
    )
    SessionCostFactory.create(session_id="s1", cost=50.0)
    AttributionCustomerJourneyFactory.create(conv_id="c1", session_id="s1", ihc=0.5)
    AttributionCustomerJourneyFactory.create(conv_id="c2", session_id="s1", ihc=0.5)

    DBChannelReportingRepo(ihc_db).recompute()

    rows = ihc_db.query(ChannelReporting).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.cost == 50.0  # not 100.0
    assert row.ihc == 1.0
    assert row.ihc_revenue == pytest.approx(0.5 * 100.0 + 0.5 * 200.0)


def test_recompute_sums_ihc_per_attribution_for_shared_session(ihc_db):
    """
    GIVEN session s1 on (FB & IG Ads, 2024-01-01) with cost=$5, attributed to:
            (c1, s1, ihc=0.5)  where c1.revenue = $100
            (c2, s1, ihc=0.4)  where c2.revenue = $200
    WHEN recompute runs
    THEN the (FB & IG Ads, 2024-01-01) row has:
            cost        = 5      (one session, counted once)
            ihc         = 0.9    (= 0.5 + 0.4 — each attribution summed independently)
            ihc_revenue = 130    (= 0.5 * 100 + 0.4 * 200)
         The asymmetry: cost is per-session, ihc is per-attribution-row.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-02",
        conv_time="12:00:00",
        revenue=100.0,
    )
    ConversionFactory.create(
        conv_id="c2",
        user_id="u1",
        conv_date="2024-01-03",
        conv_time="12:00:00",
        revenue=200.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="10:00:00",
        channel_name="FB & IG Ads",
    )
    SessionCostFactory.create(session_id="s1", cost=5.0)
    AttributionCustomerJourneyFactory.create(conv_id="c1", session_id="s1", ihc=0.5)
    AttributionCustomerJourneyFactory.create(conv_id="c2", session_id="s1", ihc=0.4)

    DBChannelReportingRepo(ihc_db).recompute()

    rows = ihc_db.query(ChannelReporting).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.channel_name == "FB & IG Ads"
    assert row.date == "2024-01-01"
    assert row.cost == 5.0
    assert row.ihc == pytest.approx(0.9)
    assert row.ihc_revenue == pytest.approx(130.0)


def test_recompute_treats_missing_session_cost_as_zero(ihc_db):
    """
    GIVEN a session with no row in session_costs (organic / direct)
    WHEN recompute runs
    THEN the row is included with cost=0; ihc/ihc_revenue come from attribution.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-02",
        conv_time="12:00:00",
        revenue=100.0,
    )
    SessionSourceFactory.create(
        session_id="s_organic",
        user_id="u1",
        event_date="2024-01-01",
        event_time="10:00:00",
        channel_name="Organic",
    )
    AttributionCustomerJourneyFactory.create(
        conv_id="c1", session_id="s_organic", ihc=1.0
    )

    DBChannelReportingRepo(ihc_db).recompute()

    rows = ihc_db.query(ChannelReporting).all()
    assert len(rows) == 1
    assert rows[0].cost == 0.0
    assert rows[0].ihc == 1.0
    assert rows[0].ihc_revenue == 100.0


def test_recompute_groups_separately_by_channel_and_date(ihc_db):
    """
    GIVEN sessions spread across two channels and two event_dates
    WHEN recompute runs
    THEN four (channel, date) rows are written.
    """
    for sid, channel, date in [
        ("s1", "SEA", "2024-01-01"),
        ("s2", "SEA", "2024-01-02"),
        ("s3", "Display", "2024-01-01"),
        ("s4", "Display", "2024-01-02"),
    ]:
        SessionSourceFactory.create(
            session_id=sid,
            user_id="u",
            event_date=date,
            event_time="10:00:00",
            channel_name=channel,
        )
        SessionCostFactory.create(session_id=sid, cost=5.0)

    DBChannelReportingRepo(ihc_db).recompute()

    rows = ihc_db.query(ChannelReporting).all()
    keys = sorted((r.channel_name, r.date) for r in rows)
    assert keys == [
        ("Display", "2024-01-01"),
        ("Display", "2024-01-02"),
        ("SEA", "2024-01-01"),
        ("SEA", "2024-01-02"),
    ]


def test_recompute_is_idempotent(ihc_db):
    """
    GIVEN recompute already ran
    WHEN it runs again with the same source data
    THEN channel_reporting has the same rows (DELETE wipes, INSERT recreates).
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-02",
        conv_time="12:00:00",
        revenue=100.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="10:00:00",
        channel_name="SEA",
    )
    SessionCostFactory.create(session_id="s1", cost=10.0)
    AttributionCustomerJourneyFactory.create(conv_id="c1", session_id="s1", ihc=1.0)
    repo = DBChannelReportingRepo(ihc_db)

    repo.recompute()
    first = sorted(
        (r.channel_name, r.date, r.cost, r.ihc, r.ihc_revenue)
        for r in ihc_db.query(ChannelReporting).all()
    )
    repo.recompute()
    second = sorted(
        (r.channel_name, r.date, r.cost, r.ihc, r.ihc_revenue)
        for r in ihc_db.query(ChannelReporting).all()
    )

    assert first == second


def test_recompute_wipes_stale_rows_not_present_in_source(ihc_db):
    """
    GIVEN channel_reporting has a row for a (channel, date) with no current source data
    WHEN recompute runs
    THEN that stale row is removed.
    """
    ihc_db.add(
        ChannelReporting(
            channel_name="OldChannel",
            date="2020-01-01",
            cost=99.0,
            ihc=99.0,
            ihc_revenue=99.0,
        )
    )
    ihc_db.commit()

    DBChannelReportingRepo(ihc_db).recompute()

    assert (
        ihc_db.query(ChannelReporting).filter_by(channel_name="OldChannel").count() == 0
    )


# ---------- get_for_export ----------


def test_get_for_export_returns_empty_when_no_rows(ihc_db):
    """
    GIVEN an empty channel_reporting table
    WHEN get_for_export is called
    THEN it returns an empty list.
    """
    assert DBChannelReportingRepo(ihc_db).get_for_export() == []


def test_get_for_export_returns_rows_ordered_by_date_then_channel(ihc_db):
    """
    GIVEN rows on multiple (channel, date) pairs
    WHEN get_for_export is called with no filter
    THEN rows are returned ordered by (date, channel_name) ascending.
    """
    for sid, channel, date in [
        ("s1", "SEA", "2024-01-02"),
        ("s2", "Direct", "2024-01-02"),
        ("s3", "SEA", "2024-01-01"),
    ]:
        SessionSourceFactory.create(
            session_id=sid,
            user_id="u",
            event_date=date,
            event_time="10:00:00",
            channel_name=channel,
        )
        SessionCostFactory.create(session_id=sid, cost=1.0)
    repo = DBChannelReportingRepo(ihc_db)
    repo.recompute()

    result = repo.get_for_export()

    assert [(r.date, r.channel_name) for r in result] == [
        ("2024-01-01", "SEA"),
        ("2024-01-02", "Direct"),
        ("2024-01-02", "SEA"),
    ]


def test_get_for_export_filters_by_inclusive_date_range(ihc_db):
    """
    GIVEN rows on 2024-01-01, 2024-01-15, and 2024-02-01
    WHEN get_for_export is called with start='2024-01-10' and end='2024-01-31'
    THEN only the 2024-01-15 row is returned.
    """
    for sid, date in [
        ("s_jan1", "2024-01-01"),
        ("s_jan15", "2024-01-15"),
        ("s_feb1", "2024-02-01"),
    ]:
        SessionSourceFactory.create(
            session_id=sid,
            user_id=f"u_{sid}",
            event_date=date,
            event_time="10:00:00",
            channel_name="SEA",
        )
        SessionCostFactory.create(session_id=sid, cost=1.0)
    repo = DBChannelReportingRepo(ihc_db)
    repo.recompute()

    result = repo.get_for_export("2024-01-10", "2024-01-31")

    assert [r.date for r in result] == ["2024-01-15"]


def test_get_for_export_computes_cpo_and_roas_in_sql(ihc_db):
    """
    GIVEN a row with cost=50, ihc=2.5, ihc_revenue=500
    WHEN get_for_export is called
    THEN cpo = 20.0 (cost/ihc) and roas = 10.0 (ihc_revenue/cost), computed in SQL.
    """
    ihc_db.add(
        ChannelReporting(
            channel_name="SEA",
            date="2024-01-01",
            cost=50.0,
            ihc=2.5,
            ihc_revenue=500.0,
        )
    )
    ihc_db.commit()

    result = DBChannelReportingRepo(ihc_db).get_for_export()

    assert len(result) == 1
    assert result[0].cpo == 20.0
    assert result[0].roas == 10.0


def test_get_for_export_returns_null_cpo_when_ihc_is_zero(ihc_db):
    """
    GIVEN a row with ihc=0 (e.g. cost spent but no attributed conversions)
    WHEN get_for_export is called
    THEN cpo is None (SQL CASE returns NULL); roas is still computed.
    """
    ihc_db.add(
        ChannelReporting(
            channel_name="Display",
            date="2024-01-01",
            cost=100.0,
            ihc=0.0,
            ihc_revenue=0.0,
        )
    )
    ihc_db.commit()

    result = DBChannelReportingRepo(ihc_db).get_for_export()

    assert result[0].cpo is None
    assert result[0].roas == 0.0


def test_get_for_export_returns_null_roas_when_cost_is_zero(ihc_db):
    """
    GIVEN a row with cost=0 (organic / direct)
    WHEN get_for_export is called
    THEN roas is None; cpo is still computed (0).
    """
    ihc_db.add(
        ChannelReporting(
            channel_name="Organic",
            date="2024-01-01",
            cost=0.0,
            ihc=2.0,
            ihc_revenue=200.0,
        )
    )
    ihc_db.commit()

    result = DBChannelReportingRepo(ihc_db).get_for_export()

    assert result[0].roas is None
    assert result[0].cpo == 0.0
