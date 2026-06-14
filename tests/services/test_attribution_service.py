from pathlib import Path
from unittest.mock import MagicMock

from adapters.ihc.client import (
    IhcApiError,
    IhcComputeResponse,
    IhcErrorTrigger,
    IhcPartialFailureError,
    IhcSessionResult,
)
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)
from domain.entities.attribution_failure import AttributionFailureEntity
from domain.entities.customer_journey import CustomerJourneyEntity
from domain.entities.journey_touchpoint import JourneyTouchpointEntity
from services.attribution_service import (
    MAX_SESSIONS_PER_CHUNK_PROD,
    MAX_SESSIONS_PER_CHUNK_TEST,
    attribute_journeys,
)


def _touchpoint(session_id: str = "s1") -> JourneyTouchpointEntity:
    return JourneyTouchpointEntity(
        session_id=session_id,
        timestamp="2024-01-05T09:00:00",
        channel="SEA",
        holder_engagement=1,
        closer_engagement=0,
        impression_interaction=0,
    )


def _journey(conv_id: str, n_sessions: int = 1) -> CustomerJourneyEntity:
    return CustomerJourneyEntity(
        conversion_id=conv_id,
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
        user_id=f"u_{conv_id}",
        sessions=[_touchpoint(f"{conv_id}_s{i}") for i in range(n_sessions)],
    )


def _write_journeys(path: Path, journeys: list[CustomerJourneyEntity]) -> None:
    path.write_text("".join(j.model_dump_json() + "\n" for j in journeys))


def _ok_response(*ihc_pairs: tuple[str, str, float]) -> IhcComputeResponse:
    return IhcComputeResponse(
        status_code=200,
        value=[
            IhcSessionResult(
                conversion_id=cid,
                session_id=sid,
                initializer=1.0,
                holder=0.0,
                closer=1.0,
                ihc=ihc,
            )
            for cid, sid, ihc in ihc_pairs
        ],
        partial_failure_errors=[],
    )


def _load_jsonl(path: Path, model):
    return [
        model.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line
    ]


def test_writes_empty_output_files_when_input_is_empty(tmp_path):
    """
    GIVEN an empty journeys.jsonl
    WHEN attribute_journeys runs
    THEN no API call is made, both output files exist and are empty, counts are 0.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    journeys_path.write_text("")
    client = MagicMock(spec=["compute"])

    result = attribute_journeys(client, journeys_path, tmp_path)

    assert not client.compute.called
    assert result.success_count == 0
    assert result.failed_count == 0
    assert result.success_path.read_text() == ""
    assert result.failed_path.read_text() == ""


def test_single_chunk_200_response_writes_all_to_success(tmp_path):
    """
    GIVEN one journey with two sessions and a 200 response
    WHEN attribute_journeys runs
    THEN both scored sessions appear in attribution_success.jsonl as
         AttributionCustomerJourneyEntity rows; failed file is empty.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(journeys_path, [_journey("c1", n_sessions=2)])
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response(
        ("c1", "c1_s0", 0.4), ("c1", "c1_s1", 0.6)
    )

    result = attribute_journeys(client, journeys_path, tmp_path)

    assert result.success_count == 2
    assert result.failed_count == 0
    successes = _load_jsonl(result.success_path, AttributionCustomerJourneyEntity)
    assert [(s.conv_id, s.session_id, s.ihc) for s in successes] == [
        ("c1", "c1_s0", 0.4),
        ("c1", "c1_s1", 0.6),
    ]


def test_chunks_by_max_journeys_limit(tmp_path):
    """
    GIVEN 250 single-session journeys and max_journeys_per_chunk=100
    WHEN attribute_journeys runs
    THEN client.compute is called 3 times with chunk sizes 100, 100, 50.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    journeys = [_journey(f"c{i}", n_sessions=1) for i in range(250)]
    _write_journeys(journeys_path, journeys)
    client = MagicMock(spec=["compute"])
    client.compute.side_effect = lambda chunk: _ok_response(
        *((j.conversion_id, j.sessions[0].session_id, 1.0) for j in chunk)
    )

    result = attribute_journeys(
        client, journeys_path, tmp_path, max_journeys_per_chunk=100
    )

    sizes = [len(call.args[0]) for call in client.compute.call_args_list]
    assert sizes == [100, 100, 50]
    assert result.success_count == 250


def test_chunks_by_max_sessions_limit_even_when_journey_count_is_low(tmp_path):
    """
    GIVEN three journeys with 1500, 1500, and 1500 sessions and max_sessions_per_chunk=3000
    WHEN attribute_journeys runs
    THEN the third journey lands in a second chunk to keep each chunk <=3000 sessions.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(
        journeys_path,
        [
            _journey("c1", n_sessions=1500),
            _journey("c2", n_sessions=1500),
            _journey("c3", n_sessions=1500),
        ],
    )
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response()

    attribute_journeys(
        client,
        journeys_path,
        tmp_path,
        max_journeys_per_chunk=100,
        max_sessions_per_chunk=3000,
    )

    sizes = [
        sum(len(j.sessions) for j in call.args[0])
        for call in client.compute.call_args_list
    ]
    assert sizes == [3000, 1500]


def test_206_partial_failure_splits_success_and_failed(tmp_path):
    """
    GIVEN a chunk where one session is scored and another reports a partial failure
    WHEN attribute_journeys runs
    THEN the scored session goes to success file, the failure goes to failed file
         with conv_id, session_id, reason, and status_code populated.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(
        journeys_path, [_journey("c1", n_sessions=1), _journey("c2", n_sessions=1)]
    )
    client = MagicMock(spec=["compute"])
    client.compute.return_value = IhcComputeResponse(
        status_code=206,
        value=[
            IhcSessionResult(
                conversion_id="c1",
                session_id="c1_s0",
                initializer=1.0,
                holder=0.0,
                closer=1.0,
                ihc=1.0,
            )
        ],
        partial_failure_errors=[
            IhcPartialFailureError(
                trigger=IhcErrorTrigger(conversion_id="c2", session_id="c2_s0"),
                reason="invalid timestamp",
                status_code=406,
            )
        ],
    )

    result = attribute_journeys(client, journeys_path, tmp_path)

    successes = _load_jsonl(result.success_path, AttributionCustomerJourneyEntity)
    failures = _load_jsonl(result.failed_path, AttributionFailureEntity)
    assert [s.conv_id for s in successes] == ["c1"]
    assert len(failures) == 1
    assert failures[0].conv_id == "c2"
    assert failures[0].session_id == "c2_s0"
    assert failures[0].reason == "invalid timestamp"
    assert failures[0].status_code == 406


def test_IhcApiError_routes_whole_chunk_to_failed_file(tmp_path):
    """
    GIVEN client.compute raises IhcApiError (e.g. 500 server error)
    WHEN attribute_journeys runs
    THEN every journey in the failing chunk gets one row in the failed file
         (session_id None — granularity unknown at the HTTP-error level).
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(
        journeys_path, [_journey("c1", n_sessions=1), _journey("c2", n_sessions=1)]
    )
    client = MagicMock(spec=["compute"])
    client.compute.side_effect = IhcApiError(500, "internal server error")

    result = attribute_journeys(client, journeys_path, tmp_path)

    assert result.success_count == 0
    assert result.failed_count == 2
    failures = _load_jsonl(result.failed_path, AttributionFailureEntity)
    assert {f.conv_id for f in failures} == {"c1", "c2"}
    assert all(f.session_id is None for f in failures)
    assert all(f.status_code == 500 for f in failures)
    assert all("internal server error" in f.reason for f in failures)


def test_continues_processing_subsequent_chunks_after_an_error(tmp_path):
    """
    GIVEN two chunks where chunk 1 raises IhcApiError and chunk 2 returns 200
    WHEN attribute_journeys runs (max_journeys_per_chunk=1)
    THEN chunk 1 is in the failed file, chunk 2 is in the success file — one
         chunk's failure does not abort the run.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(
        journeys_path,
        [_journey("c_bad", n_sessions=1), _journey("c_good", n_sessions=1)],
    )
    client = MagicMock(spec=["compute"])
    client.compute.side_effect = [
        IhcApiError(503, "service unavailable"),
        _ok_response(("c_good", "c_good_s0", 1.0)),
    ]

    result = attribute_journeys(
        client, journeys_path, tmp_path, max_journeys_per_chunk=1
    )

    assert result.success_count == 1
    assert result.failed_count == 1
    successes = _load_jsonl(result.success_path, AttributionCustomerJourneyEntity)
    failures = _load_jsonl(result.failed_path, AttributionFailureEntity)
    assert [s.conv_id for s in successes] == ["c_good"]
    assert [f.conv_id for f in failures] == ["c_bad"]


def test_uses_atomic_rename_leaves_no_tmp_files(tmp_path):
    """
    GIVEN a successful run
    WHEN attribute_journeys finishes
    THEN the .tmp staging files are gone and only the final files remain.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(journeys_path, [_journey("c1", n_sessions=1)])
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response(("c1", "c1_s0", 1.0))

    attribute_journeys(client, journeys_path, tmp_path)

    assert not (tmp_path / "attribution_success.jsonl.tmp").exists()
    assert not (tmp_path / "attribution_failed.jsonl.tmp").exists()
    assert (tmp_path / "attribution_success.jsonl").exists()
    assert (tmp_path / "attribution_failed.jsonl").exists()


def test_is_test_flag_caps_session_chunks_at_free_tier_limit(tmp_path):
    """
    GIVEN three journeys each with 100 sessions
    WHEN attribute_journeys runs with is_test=True
    THEN chunks are capped at 200 sessions (IHC free tier), so the three
         journeys split into two chunks (2 journeys = 200 sessions, then 1).
    """
    journeys_path = tmp_path / "journeys.jsonl"
    journeys = [_journey(f"c{i}", n_sessions=100) for i in range(3)]
    _write_journeys(journeys_path, journeys)
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response()

    attribute_journeys(client, journeys_path, tmp_path, is_test=True)

    sizes = [
        sum(len(j.sessions) for j in call.args[0])
        for call in client.compute.call_args_list
    ]
    assert sizes == [200, 100]


def test_default_uses_prod_session_cap(tmp_path):
    """
    GIVEN four journeys each with 1000 sessions (4000 total)
    WHEN attribute_journeys runs with default is_test=False
    THEN chunks are capped at 3000 sessions (IHC public docs default).
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(
        journeys_path, [_journey(f"c{i}", n_sessions=1000) for i in range(4)]
    )
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response()

    attribute_journeys(client, journeys_path, tmp_path)

    sizes = [
        sum(len(j.sessions) for j in call.args[0])
        for call in client.compute.call_args_list
    ]
    assert max(sizes) <= MAX_SESSIONS_PER_CHUNK_PROD
    assert MAX_SESSIONS_PER_CHUNK_PROD == 3000
    assert MAX_SESSIONS_PER_CHUNK_TEST == 200


def test_explicit_max_sessions_overrides_is_test(tmp_path):
    """
    GIVEN is_test=True (which would normally cap at 200)
    AND an explicit max_sessions_per_chunk=50
    WHEN attribute_journeys runs
    THEN the explicit value wins.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(journeys_path, [_journey(f"c{i}", n_sessions=40) for i in range(5)])
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response()

    attribute_journeys(
        client,
        journeys_path,
        tmp_path,
        is_test=True,
        max_sessions_per_chunk=50,
    )

    sizes = [
        sum(len(j.sessions) for j in call.args[0])
        for call in client.compute.call_args_list
    ]
    assert max(sizes) <= 50


def test_creates_output_dir_when_it_does_not_exist(tmp_path):
    """
    GIVEN an output_dir that does not yet exist
    WHEN attribute_journeys runs
    THEN the directory is created and both files land inside it.
    """
    journeys_path = tmp_path / "journeys.jsonl"
    _write_journeys(journeys_path, [_journey("c1", n_sessions=1)])
    nested = tmp_path / "runs" / "run-99"
    client = MagicMock(spec=["compute"])
    client.compute.return_value = _ok_response(("c1", "c1_s0", 1.0))

    result = attribute_journeys(client, journeys_path, nested)

    assert nested.is_dir()
    assert result.success_path == nested / "attribution_success.jsonl"
    assert result.failed_path == nested / "attribution_failed.jsonl"
