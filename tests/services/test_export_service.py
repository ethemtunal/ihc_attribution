import csv
from pathlib import Path

from adapters.database.models.channel_reporting import ChannelReporting
from services.export_service import CSV_HEADER, export_channel_reporting


def _seed_channel_reporting(
    ihc_db, rows: list[tuple[str, str, float, float, float]]
) -> None:
    """Each row is (channel_name, date, cost, ihc, ihc_revenue)."""
    for channel_name, date, cost, ihc, ihc_revenue in rows:
        ihc_db.add(
            ChannelReporting(
                channel_name=channel_name,
                date=date,
                cost=cost,
                ihc=ihc,
                ihc_revenue=ihc_revenue,
            )
        )
    ihc_db.commit()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def test_writes_header_only_when_no_rows(ihc_db, tmp_path):
    """
    GIVEN an empty channel_reporting table
    WHEN export_channel_reporting runs
    THEN the CSV has exactly the header line and no data rows.
    """
    out = export_channel_reporting(ihc_db, None, None, tmp_path)

    assert out == tmp_path / "channel_reporting.csv"
    lines = out.read_text().splitlines()
    assert lines == [",".join(CSV_HEADER)]


def test_writes_one_csv_row_per_channel_reporting_row(ihc_db, tmp_path):
    """
    GIVEN one channel_reporting row with cost=50, ihc=2.5, ihc_revenue=500
    WHEN export_channel_reporting runs
    THEN the CSV has one data row with CPO=20.0 and ROAS=10.0.
    """
    _seed_channel_reporting(ihc_db, [("SEA", "2024-01-01", 50.0, 2.5, 500.0)])

    out = export_channel_reporting(ihc_db, None, None, tmp_path)

    rows = _read_csv(out)
    assert len(rows) == 1
    r = rows[0]
    assert r["channel_name"] == "SEA"
    assert r["date"] == "2024-01-01"
    assert float(r["cost"]) == 50.0
    assert float(r["ihc"]) == 2.5
    assert float(r["ihc_revenue"]) == 500.0
    assert float(r["CPO"]) == 20.0
    assert float(r["ROAS"]) == 10.0


def test_leaves_cpo_blank_when_ihc_is_zero(ihc_db, tmp_path):
    """
    GIVEN a (channel, date) with ihc=0 (e.g. cost spent but no attributed conversions)
    WHEN export_channel_reporting runs
    THEN CPO is left blank in the CSV; ROAS is still computed (0).
    """
    _seed_channel_reporting(ihc_db, [("Display", "2024-01-01", 100.0, 0.0, 0.0)])

    out = export_channel_reporting(ihc_db, None, None, tmp_path)

    rows = _read_csv(out)
    assert rows[0]["CPO"] == ""
    assert rows[0]["ROAS"] == "0.0"


def test_leaves_roas_blank_when_cost_is_zero(ihc_db, tmp_path):
    """
    GIVEN an organic-style row with cost=0 but ihc=2 and ihc_revenue=200
    WHEN export_channel_reporting runs
    THEN ROAS is left blank in the CSV; CPO is still computed (0).
    """
    _seed_channel_reporting(ihc_db, [("Organic", "2024-01-01", 0.0, 2.0, 200.0)])

    out = export_channel_reporting(ihc_db, None, None, tmp_path)

    rows = _read_csv(out)
    assert rows[0]["ROAS"] == ""
    assert float(rows[0]["CPO"]) == 0.0


def test_date_range_filter_passes_through_to_repo(ihc_db, tmp_path):
    """
    GIVEN three rows on 2024-01-01, 2024-01-15, 2024-02-01
    WHEN export_channel_reporting is called with start='2024-01-10' end='2024-01-31'
    THEN only the 2024-01-15 row appears in the CSV.
    """
    _seed_channel_reporting(
        ihc_db,
        [
            ("SEA", "2024-01-01", 1.0, 1.0, 1.0),
            ("SEA", "2024-01-15", 2.0, 2.0, 2.0),
            ("SEA", "2024-02-01", 3.0, 3.0, 3.0),
        ],
    )

    out = export_channel_reporting(ihc_db, "2024-01-10", "2024-01-31", tmp_path)

    rows = _read_csv(out)
    assert [r["date"] for r in rows] == ["2024-01-15"]


def test_uses_atomic_rename_leaves_no_tmp_file(ihc_db, tmp_path):
    """
    GIVEN a successful export
    WHEN export_channel_reporting finishes
    THEN the .tmp staging file is gone and only the final CSV remains.
    """
    _seed_channel_reporting(ihc_db, [("SEA", "2024-01-01", 1.0, 1.0, 1.0)])

    export_channel_reporting(ihc_db, None, None, tmp_path)

    assert (tmp_path / "channel_reporting.csv").exists()
    assert not (tmp_path / "channel_reporting.csv.tmp").exists()


def test_creates_output_dir_when_it_does_not_exist(ihc_db, tmp_path):
    """
    GIVEN an output_dir that does not yet exist
    WHEN export_channel_reporting runs
    THEN the directory is created and the CSV file lands inside it.
    """
    nested = tmp_path / "runs" / "run-123"
    assert not nested.exists()

    out = export_channel_reporting(ihc_db, None, None, nested)

    assert nested.is_dir()
    assert out == nested / "channel_reporting.csv"
