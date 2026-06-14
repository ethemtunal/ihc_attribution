from pathlib import Path

from common.datagen.conversion_factory import ConversionFactory
from common.datagen.session_source_factory import SessionSourceFactory
from domain.entities.customer_journey import CustomerJourneyEntity
from services.customer_journey_builder import build_customer_journeys


def _load_journeys(path: Path) -> list[CustomerJourneyEntity]:
    return [
        CustomerJourneyEntity.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line
    ]


def test_writes_empty_file_when_no_conversions(ihc_db, tmp_path):
    """
    GIVEN an empty database
    WHEN build_customer_journeys is called
    THEN the output file exists and is empty.
    """
    out = build_customer_journeys(ihc_db, None, None, tmp_path)

    assert out == tmp_path / "journeys.jsonl"
    assert out.read_text() == ""


def test_skips_conversion_with_no_prior_sessions(ihc_db, tmp_path):
    """
    GIVEN a conversion with no sessions before it
    WHEN build_customer_journeys is called
    THEN no journey is emitted (the INNER JOIN drops the conversion).
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
    )

    out = build_customer_journeys(ihc_db, None, None, tmp_path)

    assert _load_journeys(out) == []


def test_emits_one_journey_with_only_real_touchpoints(ihc_db, tmp_path):
    """
    GIVEN a conversion with one prior session
    WHEN build_customer_journeys is called
    THEN one journey is written with exactly that one touchpoint — no synthetic
         conversion session is appended (IHC treats the last session as the closer).
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
        channel_name="SEA",
    )

    out = build_customer_journeys(ihc_db, None, None, tmp_path)

    journeys = _load_journeys(out)
    assert len(journeys) == 1
    j = journeys[0]
    assert j.conversion_id == "c1"
    assert j.revenue == 100.0
    assert j.user_id == "u1"
    assert len(j.sessions) == 1
    (real,) = j.sessions
    assert real.session_id == "s1"
    assert real.channel == "SEA"
    assert real.timestamp == "2024-01-05T09:00:00"


def test_touchpoints_are_ordered_chronologically(ihc_db, tmp_path):
    """
    GIVEN a conversion with three prior sessions in non-chronological insert order
    WHEN build_customer_journeys is called
    THEN the touchpoints are ordered by (event_date, event_time) ascending.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
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

    out = build_customer_journeys(ihc_db, None, None, tmp_path)

    journeys = _load_journeys(out)
    assert len(journeys) == 1
    sids = [t.session_id for t in journeys[0].sessions]
    assert sids == ["s_early", "s_mid", "s_late"]


def test_emits_one_journey_per_conversion(ihc_db, tmp_path):
    """
    GIVEN two conversions for the same user, each with their own prior session
    WHEN build_customer_journeys is called
    THEN two separate journeys are emitted with distinct conversion_ids.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
    )
    ConversionFactory.create(
        conv_id="c2",
        user_id="u1",
        conv_date="2024-01-20",
        conv_time="12:00:00",
        revenue=200.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
    )
    SessionSourceFactory.create(
        session_id="s2",
        user_id="u1",
        event_date="2024-01-15",
        event_time="09:00:00",
    )

    out = build_customer_journeys(ihc_db, None, None, tmp_path)

    journeys = _load_journeys(out)
    assert {j.conversion_id for j in journeys} == {"c1", "c2"}


def test_passes_date_range_filter_through_to_repo(ihc_db, tmp_path):
    """
    GIVEN two conversions on different dates, each with a prior session
    WHEN build_customer_journeys is called with a start_date excluding the older one
    THEN only the in-range conversion's journey is emitted.
    """
    ConversionFactory.create(
        conv_id="c_old",
        user_id="u1",
        conv_date="2024-01-05",
        conv_time="12:00:00",
        revenue=100.0,
    )
    ConversionFactory.create(
        conv_id="c_new",
        user_id="u2",
        conv_date="2024-02-10",
        conv_time="12:00:00",
        revenue=100.0,
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

    out = build_customer_journeys(ihc_db, "2024-02-01", None, tmp_path)

    journeys = _load_journeys(out)
    assert [j.conversion_id for j in journeys] == ["c_new"]


def test_uses_atomic_rename_leaves_no_tmp_file(ihc_db, tmp_path):
    """
    GIVEN a successful build
    WHEN build_customer_journeys finishes
    THEN the .tmp staging file is gone and only the final journeys.jsonl remains.
    """
    ConversionFactory.create(
        conv_id="c1",
        user_id="u1",
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
    )
    SessionSourceFactory.create(
        session_id="s1",
        user_id="u1",
        event_date="2024-01-05",
        event_time="09:00:00",
    )

    build_customer_journeys(ihc_db, None, None, tmp_path)

    assert (tmp_path / "journeys.jsonl").exists()
    assert not (tmp_path / "journeys.jsonl.tmp").exists()


def test_creates_output_dir_when_it_does_not_exist(ihc_db, tmp_path):
    """
    GIVEN an output_dir that does not yet exist
    WHEN build_customer_journeys is called
    THEN the directory is created and the file is written into it.
    """
    nested = tmp_path / "runs" / "run-42"
    assert not nested.exists()

    out = build_customer_journeys(ihc_db, None, None, nested)

    assert nested.is_dir()
    assert out == nested / "journeys.jsonl"
