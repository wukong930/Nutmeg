from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads

from nutmeg.accuracy.job_repository import (
    COMPLETE_ACCURACY_JOB_RUN_QUERY,
    FAIL_ACCURACY_JOB_RUN_QUERY,
    INSERT_ACCURACY_JOB_RUN_QUERY,
    LIST_ACCURACY_JOB_RUNS_QUERY,
    PostgresAccuracyJobRunRepository,
)
from nutmeg.database import DatabaseRow, QueryParams


class FakeJobRunDatabase:
    def __init__(
        self,
        *,
        returning_rows: Sequence[DatabaseRow] | None = None,
        list_rows: Sequence[DatabaseRow] | None = None,
    ) -> None:
        self.returning_rows = list(returning_rows or [])
        self.list_rows = list(list_rows or [])
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if not self.returning_rows:
            return None
        return self.returning_rows.pop(0)

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        return self.list_rows


def test_job_run_repository_starts_job_with_metadata() -> None:
    database = FakeJobRunDatabase(returning_rows=[_row(status="running")])
    repository = PostgresAccuracyJobRunRepository(database)

    record = repository.start_job(
        job_type="mock_postgres_e2e",
        reset_requested=False,
        requested_by="admin_api",
        metadata_json={"source": "api"},
    )

    query, params = database.fetch_one_calls[0]
    assert query == INSERT_ACCURACY_JOB_RUN_QUERY
    assert params["job_type"] == "mock_postgres_e2e"
    assert params["reset_requested"] is False
    assert params["requested_by"] == "admin_api"
    assert loads(str(params["metadata_json"])) == {"source": "api"}
    assert record.accuracy_job_run_id == 7
    assert record.status == "running"
    assert record.metadata_json == {"source": "api"}


def test_job_run_repository_completes_job_with_counts() -> None:
    database = FakeJobRunDatabase(
        returning_rows=[
            _row(
                status="completed",
                completed_at=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
                duration_ms=125,
                fixture_count=3,
                evaluation_count=3,
                calibration_observation_count=9,
                model_comparison_report_id=401,
                prediction_snapshot_ids_json={"fix_epl_001": 201},
                evaluation_ids_json=[301, 302, 303],
            )
        ]
    )
    repository = PostgresAccuracyJobRunRepository(database)

    record = repository.complete_job(
        accuracy_job_run_id=7,
        fixture_count=3,
        prediction_snapshot_ids={"fix_epl_001": 201},
        evaluation_ids=[301, 302, 303],
        calibration_observation_count=9,
        model_comparison_report_id=401,
    )

    query, params = database.fetch_one_calls[0]
    assert query == COMPLETE_ACCURACY_JOB_RUN_QUERY
    assert params["evaluation_count"] == 3
    assert loads(str(params["prediction_snapshot_ids_json"])) == {"fix_epl_001": 201}
    assert loads(str(params["evaluation_ids_json"])) == [301, 302, 303]
    assert record.status == "completed"
    assert record.duration_ms == 125
    assert record.evaluation_ids == [301, 302, 303]


def test_job_run_repository_marks_failed_job() -> None:
    database = FakeJobRunDatabase(
        returning_rows=[
            _row(
                status="failed",
                completed_at=datetime(2026, 5, 8, 1, 2, tzinfo=UTC),
                duration_ms=40,
                error_message="database statement failed",
            )
        ]
    )
    repository = PostgresAccuracyJobRunRepository(database)

    record = repository.fail_job(
        accuracy_job_run_id=7,
        error_message="database statement failed" * 100,
    )

    query, params = database.fetch_one_calls[0]
    assert query == FAIL_ACCURACY_JOB_RUN_QUERY
    assert len(str(params["error_message"])) == 500
    assert record.status == "failed"
    assert record.error_message == "database statement failed"


def test_job_run_repository_lists_latest_runs() -> None:
    database = FakeJobRunDatabase(
        list_rows=[
            _row(status="completed", prediction_snapshot_ids_json='{"fix_a":11}'),
            _row(
                accuracy_job_run_id=8,
                status="failed",
                evaluation_ids_json="[101]",
                error_message="boom",
            ),
        ]
    )
    repository = PostgresAccuracyJobRunRepository(database)

    records = repository.list_latest(limit=500)

    query, params = database.fetch_all_calls[0]
    assert query == LIST_ACCURACY_JOB_RUNS_QUERY
    assert params["limit"] == 100
    assert records[0].prediction_snapshot_ids == {"fix_a": 11}
    assert records[1].evaluation_ids == [101]
    assert records[1].error_message == "boom"


def test_job_run_repository_parses_dixon_coles_job_type() -> None:
    database = FakeJobRunDatabase(
        list_rows=[
            _row(
                status="completed",
                job_type="dixon_coles_training_backtest",
                fixture_count=8,
            )
        ]
    )
    repository = PostgresAccuracyJobRunRepository(database)

    records = repository.list_latest(limit=1)

    assert records[0].job_type == "dixon_coles_training_backtest"
    assert records[0].fixture_count == 8


def test_job_run_repository_parses_weekly_training_job_type() -> None:
    database = FakeJobRunDatabase(
        list_rows=[
            _row(
                status="completed",
                job_type="weekly_dixon_coles_training_pipeline",
                fixture_count=8,
            )
        ]
    )
    repository = PostgresAccuracyJobRunRepository(database)

    records = repository.list_latest(limit=1)

    assert records[0].job_type == "weekly_dixon_coles_training_pipeline"
    assert records[0].fixture_count == 8


def _row(
    *,
    accuracy_job_run_id: int = 7,
    job_type: str = "mock_postgres_e2e",
    status: str,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    fixture_count: int = 0,
    evaluation_count: int = 0,
    calibration_observation_count: int = 0,
    model_comparison_report_id: int | None = None,
    prediction_snapshot_ids_json: object | None = None,
    evaluation_ids_json: object | None = None,
    error_message: str | None = None,
) -> DatabaseRow:
    return {
        "accuracy_job_run_id": accuracy_job_run_id,
        "job_type": job_type,
        "status": status,
        "reset_requested": True,
        "requested_by": "admin_api",
        "started_at": datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "fixture_count": fixture_count,
        "evaluation_count": evaluation_count,
        "calibration_observation_count": calibration_observation_count,
        "model_comparison_report_id": model_comparison_report_id,
        "prediction_snapshot_ids_json": prediction_snapshot_ids_json or {},
        "evaluation_ids_json": evaluation_ids_json or [],
        "error_message": error_message,
        "metadata_json": {"source": "api"},
    }
