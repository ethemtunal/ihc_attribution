# IHC Attribution Pipeline

Airflow pipeline that reads conversions and sessions from a SQLite database, scores customer journeys via the [IHC Attribution API](https://ihc-attribution.com/marketing-attribution-api/), persists per-session attribution, aggregates per-channel reporting, and exports a CSV with CPO and ROAS.

## Stack

Python 3.13 (managed by `uv`), Airflow 3.2.2 (TaskFlow API), SQLAlchemy 2.x against SQLite, Pydantic 2.x, `requests`. Linted with `ruff`, type-checked with `mypy --strict`, tested with `pytest` + `factory-boy` (66 tests).

## Running it

```bash
export AIRFLOW_HOME=$(pwd)/.airflow
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export PYTHONPATH=$(pwd)
export IHC_API_KEY=<your-key>
export IHC_CONV_TYPE_ID=<your-conv-type-id>
export IHC_TEST_MODE=true        # caps chunks at 200 sessions (free tier); drop on paid plans

uv run airflow db migrate         # one-time
uv run airflow standalone
```

Visit `http://localhost:8080` (admin password printed to stdout on first launch), find `ihc_attribution_pipeline`, trigger with config:

```json
{"start_date": "2023-09-01", "end_date": "2023-09-07"}
```

Both dates are optional (null = unbounded). Outputs land in `data/runs/<run_id>/`:

- `journeys.jsonl` — one `CustomerJourneyEntity` per line
- `attribution_success.jsonl`, `attribution_failed.jsonl` — IHC API outcomes split by HTTP status
- `channel_reporting.csv` — the final report

## Tests

```bash
uv run pytest
```

66 tests covering the repository layer, services, the IHC HTTP client, and the export shape. Each test uses **GIVEN / WHEN / THEN** docstrings so the intent reads as a sentence — useful for understanding what each behavior guarantee actually is without having to parse the test body:

```python
def test_recompute_does_not_multi_count_cost_across_conversions(ihc_db):
    """
    GIVEN one session with cost=50 attributed to TWO different conversions
    WHEN recompute runs
    THEN that session's cost contributes ONCE (not twice) to the (channel, date) row.
         This is the bug guard for the multi-attribution case in real data.
    """
```

Test setup uses in-memory SQLite (function-scoped fixture in `tests/conftest.py`) and `factory-boy` factories under `common/datagen/` so test data reads as declarative rather than imperative SQL.

## Project layout

```
adapters/
  database/
    models/         SQLAlchemy ORM models
    repositories/   one method per operation; write methods commit themselves
  ihc/              HTTP client + Pydantic request/response models
common/datagen/     factory-boy factories (test setup only)
dags/               Airflow DAG (single TaskFlow file, 5 tasks)
data/
  challenge.db      provided SQLite source
  runs/<run_id>/    per-run output dir
domain/entities/    Pydantic entities — DB shapes + file-handoff shapes
services/           one module per pipeline step (build / attribute / write / aggregate / export)
tests/              66 tests, mirrors src tree
dependencies.py     engine + `db_session()` context manager
```

## Pipeline

```
build_journeys ─► attribute ─► write_scores ─► aggregate ─► export
   (read DB)      (IHC API)      (write DB)      (DB)         (read DB → CSV)
```

Each task receives a `Session` via the `db_session()` context manager (close-on-exit; write repos commit themselves). All inter-task data crosses Airflow XCom as paths or counts; the actual payloads live on disk under the per-run directory. Files are written via `.tmp + Path.replace()` so a crash mid-write never leaves a half-file downstream consumers can read.

| Step | Input | Output | DB ops |
|---|---|---|---|
| `build_journeys` | conv_date range | `journeys.jsonl` | reads source via SQL JOIN |
| `attribute` | journeys.jsonl | success.jsonl + failed.jsonl | none (HTTP only) |
| `write_scores` | success.jsonl | row count | INSERT into `attribution_customer_journey` |
| `aggregate` | — | row count | DELETE + INSERT `channel_reporting` |
| `export` | conv_date range | `channel_reporting.csv` | SELECT from `channel_reporting` |

## Design notes

**Layered architecture.** Repositories own SQL. Services own pipeline-step logic. The DAG just wires services together. Each layer is independently testable — the 60+ unit tests don't import Airflow.

**Pydantic at every boundary.** Files, HTTP, and the export CSV are all driven by Pydantic models so the contract is enforced on read AND write. The export entity uses `serialization_alias` for `CPO`/`ROAS` so the CSV header is derived from the model — adding a column means adding a field, nothing else.

**Aggregation as one SQL pass.** `DBChannelReportingRepo.recompute()` does `DELETE FROM channel_reporting` then `INSERT … SELECT …` with two CTEs (`cost_per_pair` and `ihc_per_pair`). Two CTEs — not one query — because cost must be summed per **unique session** and ihc must be summed **per attribution row**. A naive single JOIN `FROM session_sources LEFT JOIN attribution_customer_journey` multi-counts cost for sessions attributed to more than one conversion (we verified 18 such sessions in the challenge data).

**CPO and ROAS computed in SQL.** `get_for_export` uses `CASE WHEN ihc != 0 THEN cost/ihc ELSE NULL END`. Python just streams the Pydantic rows to CSV via `csv.DictWriter`. NULL values become blank cells automatically.

**Chunking respects two limits.** `attribute_journeys` enforces both `max_journeys_per_chunk` (100) AND `max_sessions_per_chunk` (3000 in prod / 200 in test). The `is_test` flag (wired from `IHC_TEST_MODE` env var) flips the session cap for free-tier `conv_type_id`s.

**Repo-layer commits.** Write repos call `self.session.commit()` themselves. Services pass a session but don't manage transactions. Per-chunk durability falls out naturally — each repo call is one atomic unit.

## Assumptions

| Decision | Rationale |
|---|---|
| Conversions with no prior sessions are dropped | They cannot be attributed (the INNER JOIN in the journey builder yields no rows). 54 of 2000 in challenge data. |
| No synthetic `conversion=1` session is added to journeys | Tested empirically against the IHC API: without an explicit marker the algorithm treats the last real session as the closer, and total ihc per conversion sums cleanly to 1.0. Sending a synthetic session means ~14% of credit goes to the purchase moment itself, which we'd then discard before DB write. |
| `channel_reporting.date` is `event_date` | Per the spec note. |
| `cost` is summed per unique session; `ihc` and `ihc_revenue` are summed per attribution row | A session shared across N conversions contributes its cost once but accrues ihc credit for each conversion it helped. Total ihc in `channel_reporting` equals the count of attributed conversions — verified at 1946.0 for the full week. |
| Sessions on a channel/day that were never attributed are still included | Per the spec wording for `cost`. They produce rows with `cost > 0, ihc = 0` (CPO blank, ROAS = 0). |
| `attribution_writer` uses plain INSERT | Chosen explicitly for simplicity. Re-running the writer requires a manual `DELETE FROM attribution_customer_journey` first. |
| `channel_reporting` is fully recomputed each run | Idempotent by construction. No incremental / stale-row gymnastics. |
| File handoff between Airflow tasks | XCom carries paths and counts; actual payloads are files. Survives task restarts. |
| Env vars for secrets and the test flag | Simplest. Airflow Connections + Variables would be the production-grade alternative. |

## End-to-end verification

A full-week run (`{"start_date": "2023-09-01", "end_date": "2023-09-07"}`) produces:

- 1946 distinct `conv_id`s in `attribution_customer_journey` (= 2000 − 54 with no priors)
- `SUM(ihc) = 1946.0` across both `attribution_customer_journey` and `channel_reporting` (each conv contributes ihc = 1.0)
- 150 rows in `channel_reporting` (sparse over 15 channels × 10 event_dates, since not every channel ran every day)
- `attribution_failed.jsonl` empty

## What could be improved

**Pandas vs SQLAlchemy.** The brief says the team writes data engineering code in Pandas. This codebase uses SQLAlchemy + a repository pattern, chosen for typed contracts and per-layer testability. A Pandas equivalent (`pd.read_sql_query` → DataFrame transform → `df.to_sql`) would be ~30% shorter and would match the team's stated convention; happy to refactor.

**Airflow-native plumbing.** Airflow Hooks + Connections (managed in the UI) instead of `dependencies.py` + env vars, and Airflow Variables for tunables like `IHC_TEST_MODE` and the chunk caps. Lets ops edit without redeploying.

**Re-run safety on `attribution_writer`.** Plain INSERT means an Airflow retry will fail with `IntegrityError` on the (`conv_id`, `session_id`) PK. Either reinstate `ON CONFLICT DO UPDATE` (idempotent at the cost of allowing silent overwrites) or wrap the writer with a "delete by conv_ids" step.

**No automatic retry of failed chunks.** `attribution_failed.jsonl` is the audit trail but nothing re-feeds it into a follow-up run. A "retry failed" task that converts that file back into a journeys.jsonl shape would close the loop.

**Reporting recompute scales with table size.** `recompute()` is fine for ~150 rows over a few thousand sessions, but at millions of (channel, day) pairs you'd want partitioned writes or incremental aggregation by date.

**The 54 unattributable conversions are dropped silently.** They appear in the gap between `COUNT(conversions)` and `COUNT(DISTINCT conv_id IN attribution_customer_journey)` but there's no positive signal. A short summary task ("X conversions had no prior sessions; Y went to attribution_failed") would help operators.

**Observability is minimal.** Airflow captures stdout; we don't emit structured metrics (chunk count, p95 latency, partial-failure rate). For a production deployment, instrument the IHC client and emit to whatever monitoring stack the team uses.

**No real-IHC integration test.** The client is fully unit-tested with mocked HTTP; the only true end-to-end validation is the smoke run documented above. A nightly CI smoke against a sandbox `conv_type_id` would catch real API-contract drift.
