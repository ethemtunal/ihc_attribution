from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session

from adapters.database.repositories.attribution_repository import DBAttributionRepo
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)

WRITE_CHUNK_SIZE = 1000


def write_attribution_scores(
    session: Session,
    success_path: Path,
    chunk_size: int = WRITE_CHUNK_SIZE,
) -> int:
    """Stream-read attribution_success.jsonl and insert in chunks; return total rows.

    The repo commits per call, so each chunk is durable independently — a
    mid-task crash only loses the in-flight chunk. Plain INSERT semantics:
    rerunning with overlapping (conv_id, session_id) will raise
    IntegrityError. Callers responsible for ensuring the target rows don't
    already exist (e.g. truncate upstream, or run on a fresh pipeline scope).
    """
    repo = DBAttributionRepo(session)
    total = 0
    for chunk in _iter_chunks(success_path, chunk_size):
        repo.insert_many(chunk)
        total += len(chunk)
    return total


def _iter_chunks(
    success_path: Path,
    chunk_size: int,
) -> Iterator[list[AttributionCustomerJourneyEntity]]:
    chunk: list[AttributionCustomerJourneyEntity] = []
    with success_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk.append(AttributionCustomerJourneyEntity.model_validate_json(line))
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
