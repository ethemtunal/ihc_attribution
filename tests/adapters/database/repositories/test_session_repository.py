from adapters.database.repositories.session_repository import DBSessionsRepo
from common.datagen.conversion_factory import ConversionFactory
from common.datagen.session_source_factory import SessionSourceFactory


def test_returns_empty_when_no_data(ihc_db):
    """
    GIVEN an empty database
    WHEN get_journey_rows_for_range is called
    THEN it returns an empty list.
    """
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert result == []


def test_returns_session_before_conversion_for_same_user(ihc_db):
    """
    GIVEN a conversion and an earlier session that share the same user_id
    WHEN get_journey_rows_for_range is called with no date filter
    THEN the (conversion, session) pair is returned.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert len(result) == 1
    assert result[0].conv_id == "c1"
    assert result[0].session_id == "s1"


def test_excludes_sessions_after_the_conversion_time(ihc_db):
    """
    GIVEN a conversion and a session for the same user that occurred AFTER the conversion
    WHEN get_journey_rows_for_range is called
    THEN that later session is not included in the result.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_after",
        user_id="u1",
        event_date="2024-01-11",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert result == []


def test_includes_session_at_exact_conversion_timestamp(ihc_db):
    """
    GIVEN a conversion and a session at the exact same (date, time) for the same user
    WHEN get_journey_rows_for_range is called
    THEN the boundary session is included (the predicate is inclusive: <=).
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_exact",
        user_id="u1",
        event_date="2024-01-10",
        event_time="12:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert len(result) == 1
    assert result[0].session_id == "s_exact"


def test_excludes_sessions_from_other_users(ihc_db):
    """
    GIVEN a conversion for user A and a session for user B
    WHEN get_journey_rows_for_range is called
    THEN the cross-user session is not joined to the conversion.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="userA",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_other",
        user_id="userB",
        event_date="2024-01-05",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert result == []


def test_orders_rows_by_conv_then_session_time(ihc_db):
    """
    GIVEN one conversion and multiple prior sessions
    WHEN get_journey_rows_for_range is called
    THEN the rows are ordered by (conv_id, event_date, event_time) ascending.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_late",
        user_id="u1",
        event_date="2024-01-08",
        event_time="09:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_early",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
    )
    SessionSourceFactory.create(
        session_id="s_mid",
        user_id="u1",
        event_date="2024-01-05",
        event_time="18:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert [r.session_id for r in result] == ["s_early", "s_mid", "s_late"]


def test_same_session_appears_under_each_matching_conversion(ihc_db):
    """
    GIVEN a single user with two conversions and one earlier session
    WHEN get_journey_rows_for_range is called
    THEN the session row appears once per conversion (the JOIN produces both pairs).
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
    )
    ConversionFactory.create(
        conv_id="c2",
        user_id="u1",
        conv_date="2024-01-20",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, None)

    assert sorted((r.conv_id, r.session_id) for r in result) == [
        ("c1", "s1"),
        ("c2", "s1"),
    ]


def test_start_date_filter_excludes_earlier_conversions(ihc_db):
    """
    GIVEN two conversions on different dates and matching prior sessions
    WHEN get_journey_rows_for_range is called with start_date after the first conversion
    THEN only the later conversion's rows are returned.
    """
    ConversionFactory.create(
        conv_id="c_old",
        user_id="u1",
        conv_date="2024-01-05",
        conv_time="12:00:00",
    )
    ConversionFactory.create(
        conv_id="c_new",
        user_id="u2",
        conv_date="2024-02-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="09:00:00",
    )
    SessionSourceFactory.create(
        session_id="s2",
        user_id="u2",
        event_date="2024-02-01",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range("2024-02-01", None)

    assert [r.conv_id for r in result] == ["c_new"]


def test_end_date_filter_excludes_later_conversions(ihc_db):
    """
    GIVEN two conversions on different dates and matching prior sessions
    WHEN get_journey_rows_for_range is called with end_date before the second conversion
    THEN only the earlier conversion's rows are returned.
    """
    ConversionFactory.create(
        conv_id="c_in",
        user_id="u1",
        conv_date="2024-01-05",
        conv_time="12:00:00",
    )
    ConversionFactory.create(
        conv_id="c_out",
        user_id="u2",
        conv_date="2024-02-10",
        conv_time="12:00:00",
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-01",
        event_time="09:00:00",
    )
    SessionSourceFactory.create(
        session_id="s2",
        user_id="u2",
        event_date="2024-02-01",
        event_time="09:00:00",
    )
    repo = DBSessionsRepo(ihc_db)

    result = repo.get_journey_rows_for_range(None, "2024-01-31")

    assert [r.conv_id for r in result] == ["c_in"]
