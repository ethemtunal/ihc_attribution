from pathlib import Path
from unittest.mock import patch

from adapters.database.models.attribution_customer_journey import (
    AttributionCustomerJourney,
)
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)
from services.attribution_writer import write_attribution_scores


def _write_success_file(
    path: Path, entries: list[AttributionCustomerJourneyEntity]
) -> None:
    path.write_text("".join(e.model_dump_json() + "\n" for e in entries))


def test_writes_nothing_when_input_is_empty(ihc_db, tmp_path):
    """
    GIVEN an empty attribution_success.jsonl
    WHEN write_attribution_scores runs
    THEN 0 is returned, no rows are written, and no commit is issued.
    """
    success_path = tmp_path / "attribution_success.jsonl"
    success_path.write_text("")

    with patch.object(ihc_db, "commit", wraps=ihc_db.commit) as commit_spy:
        total = write_attribution_scores(ihc_db, success_path)

    assert total == 0
    assert ihc_db.query(AttributionCustomerJourney).count() == 0
    assert commit_spy.call_count == 0


def test_inserts_all_rows_in_a_single_chunk(ihc_db, tmp_path):
    """
    GIVEN three entries and a chunk_size large enough to hold them all
    WHEN write_attribution_scores runs
    THEN all three rows land in attribution_customer_journey with their ihc values.
    """
    success_path = tmp_path / "attribution_success.jsonl"
    entries = [
        AttributionCustomerJourneyEntity(conv_id="c1", session_id="s1", ihc=0.3),
        AttributionCustomerJourneyEntity(conv_id="c1", session_id="s2", ihc=0.7),
        AttributionCustomerJourneyEntity(conv_id="c2", session_id="s3", ihc=1.0),
    ]
    _write_success_file(success_path, entries)

    total = write_attribution_scores(ihc_db, success_path, chunk_size=1000)

    assert total == 3
    rows = {
        (r.conv_id, r.session_id): r.ihc
        for r in ihc_db.query(AttributionCustomerJourney).all()
    }
    assert rows == {("c1", "s1"): 0.3, ("c1", "s2"): 0.7, ("c2", "s3"): 1.0}


def test_commits_once_per_chunk_when_chunk_size_is_smaller_than_input(ihc_db, tmp_path):
    """
    GIVEN five entries and chunk_size=2
    WHEN write_attribution_scores runs
    THEN session.commit is called exactly 3 times (chunks of 2, 2, 1) — per-chunk
         commit bounds the loss on a mid-task crash.
    """
    success_path = tmp_path / "attribution_success.jsonl"
    entries = [
        AttributionCustomerJourneyEntity(conv_id=f"c{i}", session_id=f"s{i}", ihc=0.5)
        for i in range(5)
    ]
    _write_success_file(success_path, entries)

    with patch.object(ihc_db, "commit", wraps=ihc_db.commit) as commit_spy:
        total = write_attribution_scores(ihc_db, success_path, chunk_size=2)

    assert total == 5
    assert commit_spy.call_count == 3
    assert ihc_db.query(AttributionCustomerJourney).count() == 5


def test_skips_blank_lines_in_success_file(ihc_db, tmp_path):
    """
    GIVEN a success file with a stray blank line between entries
    WHEN write_attribution_scores runs
    THEN blank lines are ignored — only the real entries get persisted.
    """
    success_path = tmp_path / "attribution_success.jsonl"
    success_path.write_text(
        AttributionCustomerJourneyEntity(
            conv_id="c1", session_id="s1", ihc=0.5
        ).model_dump_json()
        + "\n\n"
        + AttributionCustomerJourneyEntity(
            conv_id="c1", session_id="s2", ihc=0.5
        ).model_dump_json()
        + "\n"
    )

    total = write_attribution_scores(ihc_db, success_path)

    assert total == 2
    assert ihc_db.query(AttributionCustomerJourney).count() == 2
