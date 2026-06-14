import csv
from pathlib import Path

from sqlalchemy.orm import Session

from adapters.database.repositories.channel_reporting_repository import (
    DBChannelReportingRepo,
)
from domain.entities.channel_reporting_export_row import ChannelReportingExportRow

CSV_HEADER = [
    field.serialization_alias or name
    for name, field in ChannelReportingExportRow.model_fields.items()
]


def export_channel_reporting(
    session: Session,
    start_date: str | None,
    end_date: str | None,
    output_dir: Path,
) -> Path:
    """Read channel_reporting (optionally filtered by date), write CSV.

    CPO and ROAS are computed by the repo's SQL. Header and column order are
    derived from `ChannelReportingExportRow`'s field names + aliases — adding
    a field there flows through to the CSV automatically. Atomic via
    `.tmp + Path.replace()`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "channel_reporting.csv"
    tmp_path = output_dir / "channel_reporting.csv.tmp"

    rows = DBChannelReportingRepo(session).get_for_export(start_date, end_date)

    with tmp_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump(by_alias=True))

    tmp_path.replace(final_path)
    return final_path
