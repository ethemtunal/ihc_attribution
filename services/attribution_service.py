from collections.abc import Iterator
from pathlib import Path

from adapters.ihc.client import IhcApiError, IhcClient
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)
from domain.entities.attribution_failure import AttributionFailureEntity
from domain.entities.attribution_run_result import AttributionRunResult
from domain.entities.customer_journey import CustomerJourneyEntity

MAX_JOURNEYS_PER_CHUNK = 100
MAX_SESSIONS_PER_CHUNK = 3000


def attribute_journeys(
    client: IhcClient,
    journeys_path: Path,
    output_dir: Path,
    max_journeys_per_chunk: int = MAX_JOURNEYS_PER_CHUNK,
    max_sessions_per_chunk: int = MAX_SESSIONS_PER_CHUNK,
) -> AttributionRunResult:
    """Stream-read journeys, chunk under IHC limits, POST each chunk.

    Writes scored entries to attribution_success.jsonl and failed entries
    (per-session 206 partial failures + whole-chunk non-2xx errors) to
    attribution_failed.jsonl. Both files are written via `.tmp + replace`
    so a successful run leaves only the final files; a crash leaves no
    partial output downstream consumers might pick up.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    success_final = output_dir / "attribution_success.jsonl"
    failed_final = output_dir / "attribution_failed.jsonl"
    success_tmp = output_dir / "attribution_success.jsonl.tmp"
    failed_tmp = output_dir / "attribution_failed.jsonl.tmp"

    success_count = 0
    failed_count = 0

    with success_tmp.open("w") as sf, failed_tmp.open("w") as ff:
        for chunk in _iter_chunks(
            journeys_path, max_journeys_per_chunk, max_sessions_per_chunk
        ):
            try:
                response = client.compute(chunk)
            except IhcApiError as exc:
                for journey in chunk:
                    failure = AttributionFailureEntity(
                        conv_id=journey.conversion_id,
                        reason=f"http_{exc.status_code}: {exc.body[:200]}",
                        status_code=exc.status_code,
                    )
                    ff.write(failure.model_dump_json() + "\n")
                    failed_count += 1
                continue

            for result in response.value:
                entry = AttributionCustomerJourneyEntity(
                    conv_id=result.conversion_id,
                    session_id=result.session_id,
                    ihc=result.ihc,
                )
                sf.write(entry.model_dump_json() + "\n")
                success_count += 1

            for err in response.partial_failure_errors:
                failure = AttributionFailureEntity(
                    conv_id=err.trigger.conversion_id,
                    session_id=err.trigger.session_id,
                    reason=err.reason,
                    status_code=err.status_code,
                )
                ff.write(failure.model_dump_json() + "\n")
                failed_count += 1

    success_tmp.replace(success_final)
    failed_tmp.replace(failed_final)

    return AttributionRunResult(
        success_path=success_final,
        failed_path=failed_final,
        success_count=success_count,
        failed_count=failed_count,
    )


def _iter_chunks(
    journeys_path: Path,
    max_journeys: int,
    max_sessions: int,
) -> Iterator[list[CustomerJourneyEntity]]:
    chunk: list[CustomerJourneyEntity] = []
    chunk_sessions = 0
    with journeys_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            journey = CustomerJourneyEntity.model_validate_json(line)
            n = len(journey.sessions)
            if chunk and (
                len(chunk) >= max_journeys or chunk_sessions + n > max_sessions
            ):
                yield chunk
                chunk = []
                chunk_sessions = 0
            chunk.append(journey)
            chunk_sessions += n
        if chunk:
            yield chunk
