import os
from datetime import datetime
from pathlib import Path
from typing import Any

from airflow.sdk import Param, dag, task

from adapters.ihc.client import IhcClient
from dependencies import db_session
from services.attribution_service import attribute_journeys
from services.attribution_writer import write_attribution_scores
from services.customer_journey_builder import build_customer_journeys
from services.export_service import export_channel_reporting
from services.reporting_service import recompute_channel_reporting


@dag(
    dag_id="ihc_attribution_pipeline",
    description=(
        "Build customer journeys, score via IHC API, write attribution, "
        "aggregate channel reporting, export CSV."
    ),
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    params={
        "start_date": Param(
            None,
            type=["string", "null"],
            description="conv_date inclusive lower bound (YYYY-MM-DD); null = no lower bound",
        ),
        "end_date": Param(
            None,
            type=["string", "null"],
            description="conv_date inclusive upper bound (YYYY-MM-DD); null = no upper bound",
        ),
    },
    tags=["attribution", "ihc"],
)
def ihc_attribution_pipeline() -> None:
    @task
    def build_journeys(**context: Any) -> str:
        # Path returned, but XCom needs JSON-serializable; cast to str at the boundary.
        with db_session() as session:
            path = build_customer_journeys(
                session,
                context["params"]["start_date"],
                context["params"]["end_date"],
                _run_dir(context),
            )
        return str(path)

    @task
    def attribute(journeys_path: str, **context: Any) -> dict[str, Any]:
        client = IhcClient(
            api_key=_required_env("IHC_API_KEY"),
            conv_type_id=_required_env("IHC_CONV_TYPE_ID"),
        )
        is_test = os.environ.get("IHC_TEST_MODE", "").lower() in ("1", "true", "yes")
        result = attribute_journeys(
            client,
            Path(journeys_path),
            _run_dir(context),
            is_test=is_test,
        )
        return {
            "success_path": str(result.success_path),
            "failed_path": str(result.failed_path),
            "success_count": result.success_count,
            "failed_count": result.failed_count,
        }

    @task
    def write_scores(attr_result: dict[str, Any]) -> int:
        with db_session() as session:
            return write_attribution_scores(session, Path(attr_result["success_path"]))

    @task
    def aggregate(_written: int) -> int:
        with db_session() as session:
            return recompute_channel_reporting(session)

    @task
    def export(_aggregated: int, **context: Any) -> str:
        with db_session() as session:
            path = export_channel_reporting(
                session,
                context["params"]["start_date"],
                context["params"]["end_date"],
                _run_dir(context),
            )
        return str(path)

    journeys_path = build_journeys()
    attr_result = attribute(journeys_path)  # type: ignore[arg-type]
    written = write_scores(attr_result)  # type: ignore[arg-type]
    aggregated = aggregate(written)  # type: ignore[arg-type]
    export(aggregated)  # type: ignore[arg-type]


def _run_dir(context: dict[str, Any]) -> Path:
    return Path("data/runs") / str(context["dag_run"].run_id)


def _required_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"environment variable {key} must be set for this DAG")
    return value


attribution_dag = ihc_attribution_pipeline()
