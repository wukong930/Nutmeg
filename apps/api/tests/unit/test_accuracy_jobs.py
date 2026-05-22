from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.accuracy.dixon_coles_job import DixonColesTrainingBacktestJobOptions
from nutmeg.accuracy.job_repository import AccuracyJobRunRecord
from nutmeg.accuracy.jobs import run_accuracy_job, run_audited_accuracy_job
from nutmeg.accuracy.local_postgres_runner import LocalAccuracyLoopRun
from nutmeg.accuracy.weekly_training import (
    WeeklyDixonColesTrainingPipelineOptions,
    WeeklyTrainingPipelinePlan,
)
from nutmeg.config import Settings
from nutmeg.database import DatabaseRow, QueryParams


class FakeAccuracyDatabase:
    def execute(self, query: str, params: QueryParams) -> None:
        raise AssertionError("runner should be monkeypatched in this test")


class FakeAuditRepository:
    def __init__(self) -> None:
        self.started: list[tuple[str, bool, str | None, dict[str, object] | None]] = []
        self.completed: list[tuple[int, int, dict[str, int], list[int], int, int | None]] = []
        self.failed: list[tuple[int, str]] = []

    def start_job(
        self,
        *,
        job_type: str,
        reset_requested: bool,
        requested_by: str | None,
        metadata_json: dict[str, object] | None = None,
    ) -> AccuracyJobRunRecord:
        self.started.append((job_type, reset_requested, requested_by, metadata_json))
        return _job_run_record(status="running", completed_at=None)

    def complete_job(
        self,
        *,
        accuracy_job_run_id: int,
        fixture_count: int,
        prediction_snapshot_ids: dict[str, int],
        evaluation_ids: list[int],
        calibration_observation_count: int,
        model_comparison_report_id: int | None,
    ) -> AccuracyJobRunRecord:
        self.completed.append(
            (
                accuracy_job_run_id,
                fixture_count,
                prediction_snapshot_ids,
                evaluation_ids,
                calibration_observation_count,
                model_comparison_report_id,
            )
        )
        return _job_run_record(
            status="completed",
            completed_at=datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
            duration_ms=75,
            fixture_count=fixture_count,
            prediction_snapshot_ids=prediction_snapshot_ids,
            evaluation_ids=evaluation_ids,
            calibration_observation_count=calibration_observation_count,
            model_comparison_report_id=model_comparison_report_id,
        )

    def fail_job(
        self,
        *,
        accuracy_job_run_id: int,
        error_message: str,
    ) -> AccuracyJobRunRecord:
        self.failed.append((accuracy_job_run_id, error_message))
        return _job_run_record(
            status="failed",
            completed_at=datetime(2026, 5, 8, 1, 6, tzinfo=UTC),
            error_message=error_message,
        )

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError("runner should be monkeypatched in this test")


def test_run_accuracy_job_maps_mock_postgres_loop_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeAccuracyDatabase()
    calls: list[tuple[object, bool]] = []

    def fake_runner(
        target_database: object,
        *,
        reset: bool,
    ) -> LocalAccuracyLoopRun:
        calls.append((target_database, reset))
        return LocalAccuracyLoopRun(
            fixture_count=2,
            prediction_snapshot_ids={"fix_a": 11, "fix_b": 12},
            evaluation_ids=[101, 102],
            calibration_observation_count=6,
            model_comparison_report_id=501,
        )

    monkeypatch.setattr("nutmeg.accuracy.jobs.run_mock_accuracy_postgres_e2e", fake_runner)

    result = run_accuracy_job(
        Settings(accuracy_repository="postgres"),
        reset=False,
        database=database,
    )

    assert calls == [(database, False)]
    assert result.job_type == "mock_postgres_e2e"
    assert result.status == "completed"
    assert result.reset is False
    assert result.fixture_count == 2
    assert result.prediction_snapshot_ids == {"fix_a": 11, "fix_b": 12}
    assert result.evaluation_ids == [101, 102]
    assert result.calibration_observation_count == 6
    assert result.model_comparison_report_id == 501
    assert result.stale is False
    assert result.fallback_used is False


def test_run_accuracy_job_uses_settings_database_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor_args: list[tuple[str, int]] = []
    runner_databases: list[object] = []

    class FakeExecutor:
        def __init__(self, database_url: str, *, connect_timeout_seconds: int) -> None:
            executor_args.append((database_url, connect_timeout_seconds))

    def fake_runner(
        target_database: object,
        *,
        reset: bool,
    ) -> LocalAccuracyLoopRun:
        runner_databases.append(target_database)
        return LocalAccuracyLoopRun(
            fixture_count=0,
            prediction_snapshot_ids={},
            evaluation_ids=[],
            calibration_observation_count=0,
            model_comparison_report_id=None,
        )

    monkeypatch.setattr("nutmeg.accuracy.jobs.PsycopgSyncDatabaseExecutor", FakeExecutor)
    monkeypatch.setattr("nutmeg.accuracy.jobs.run_mock_accuracy_postgres_e2e", fake_runner)

    run_accuracy_job(
        Settings(
            accuracy_repository="postgres",
            database_url="postgresql://nutmeg:nutmeg@localhost:55433/nutmeg",
            database_connect_timeout_seconds=7,
        )
    )

    assert executor_args == [("postgresql://nutmeg:nutmeg@localhost:55433/nutmeg", 7)]
    assert len(runner_databases) == 1


def test_run_accuracy_job_dispatches_dixon_coles_training_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeAccuracyDatabase()
    options = DixonColesTrainingBacktestJobOptions(
        as_of_time_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        dry_run=True,
    )
    calls: list[tuple[object, DixonColesTrainingBacktestJobOptions]] = []

    class FakeTrainingRun:
        dry_run = True
        fixture_count = 8
        prediction_snapshot_ids: dict[str, int] = {}
        evaluation_ids: list[int] = []
        calibration_observation_count = 0
        model_comparison_report_id = None
        backtest_run_id = None
        model_promotion_review_id = None
        candidate_model_version = "dc-v1.5-candidate"
        baseline_model_version = "poisson-m1.1.0"
        selected_rho = -0.05
        train_sample_size = 6
        validation_sample_size = 2
        candidate_brier_score = 0.21
        candidate_ece = 0.06
        baseline_ece = 0.08
        baseline_calibration_evidence_json = {"ece_source": "stored_calibration_buckets"}
        calibration_evidence_json = {"calibration_status": "validation_evidence_only"}
        promotion_evidence_json = {"candidate_upset_precision": {"sample_size": 3}}
        model_comparison_decision = "needs_review"
        model_promotion_decision = "keep_experiment"
        model_promotion_next_status = "experiment"
        model_promotion_reasons = ["candidate_brier_unavailable"]
        rollback_should_rollback = False
        report_uri = None
        warnings = ["candidate_brier_unavailable"]

    def fake_training_job(
        target_database: object,
        *,
        options: DixonColesTrainingBacktestJobOptions,
    ) -> FakeTrainingRun:
        calls.append((target_database, options))
        return FakeTrainingRun()

    monkeypatch.setattr(
        "nutmeg.accuracy.jobs.run_dixon_coles_training_backtest_job",
        fake_training_job,
    )

    result = run_accuracy_job(
        Settings(accuracy_repository="postgres"),
        job_type="dixon_coles_training_backtest",
        reset=False,
        database=database,
        dixon_coles_options=options,
    )

    assert calls == [(database, options)]
    assert result.job_type == "dixon_coles_training_backtest"
    assert result.dry_run is True
    assert result.fixture_count == 8
    assert result.candidate_model_version == "dc-v1.5-candidate"
    assert result.selected_rho == -0.05
    assert result.candidate_brier_score == 0.21
    assert result.candidate_ece == 0.06
    assert result.baseline_ece == 0.08
    assert result.baseline_calibration_evidence_json["ece_source"] == (
        "stored_calibration_buckets"
    )
    assert result.calibration_evidence_json["calibration_status"] == (
        "validation_evidence_only"
    )
    assert result.model_comparison_decision == "needs_review"
    assert result.model_promotion_decision == "keep_experiment"
    assert result.model_promotion_reasons == ["candidate_brier_unavailable"]
    assert result.warnings == ["candidate_brier_unavailable"]


def test_run_accuracy_job_dispatches_weekly_training_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeAccuracyDatabase()
    training_options = DixonColesTrainingBacktestJobOptions(
        as_of_time_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        dry_run=True,
    )
    options = WeeklyDixonColesTrainingPipelineOptions(
        training_options=training_options,
        scheduled_for_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        run_label="weekly-epl-dc",
    )
    calls: list[tuple[object, WeeklyDixonColesTrainingPipelineOptions]] = []

    class FakeTrainingRun:
        dry_run = True
        fixture_count = 8
        model_comparison_report_id = None
        backtest_run_id = None
        model_promotion_review_id = None
        candidate_model_version = "dc-v1.5-candidate"
        baseline_model_version = "poisson-m1.1.0"
        selected_rho = -0.05
        train_sample_size = 6
        validation_sample_size = 2
        candidate_brier_score = 0.21
        candidate_ece = 0.06
        baseline_ece = 0.08
        baseline_calibration_evidence_json = {"ece_source": "stored_calibration_buckets"}
        calibration_evidence_json = {"calibration_status": "validation_evidence_only"}
        promotion_evidence_json = {"candidate_upset_precision": {"sample_size": 3}}
        model_comparison_decision = "needs_review"
        model_promotion_decision = "keep_experiment"
        model_promotion_next_status = "experiment"
        model_promotion_reasons = ["candidate_brier_unavailable"]
        rollback_should_rollback = False
        report_uri = None
        warnings = ["candidate_brier_unavailable"]

    class FakePipelineRun:
        plan = WeeklyTrainingPipelinePlan(
            run_label="weekly-epl-dc",
            scheduled_for_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            freeze_as_of_time_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
            train_start_utc=datetime(2025, 5, 8, 1, 0, tzinfo=UTC),
            validation_start_utc=datetime(2026, 2, 7, 1, 0, tzinfo=UTC),
            validation_end_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
            candidate_model_version="dc-v1.5-candidate",
            baseline_model_version="poisson-m1.1.0",
            dry_run=True,
        )
        training_result = FakeTrainingRun()
        status = "completed_with_review_artifacts"

    def fake_pipeline(
        target_database: object,
        *,
        options: WeeklyDixonColesTrainingPipelineOptions,
    ) -> FakePipelineRun:
        calls.append((target_database, options))
        return FakePipelineRun()

    monkeypatch.setattr(
        "nutmeg.accuracy.jobs.run_weekly_dixon_coles_training_pipeline",
        fake_pipeline,
    )

    result = run_accuracy_job(
        Settings(accuracy_repository="postgres"),
        job_type="weekly_dixon_coles_training_pipeline",
        reset=False,
        database=database,
        weekly_training_options=options,
    )

    assert calls == [(database, options)]
    assert result.job_type == "weekly_dixon_coles_training_pipeline"
    assert result.weekly_training_plan["run_label"] == "weekly-epl-dc"
    assert result.weekly_training_status == "completed_with_review_artifacts"
    assert result.candidate_model_version == "dc-v1.5-candidate"


def test_run_audited_accuracy_job_records_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeAccuracyDatabase()
    audit_repository = FakeAuditRepository()

    def fake_runner(
        target_database: object,
        *,
        reset: bool,
    ) -> LocalAccuracyLoopRun:
        assert target_database is database
        assert reset is False
        return LocalAccuracyLoopRun(
            fixture_count=3,
            prediction_snapshot_ids={"fix_epl_001": 201},
            evaluation_ids=[301, 302, 303],
            calibration_observation_count=9,
            model_comparison_report_id=401,
        )

    monkeypatch.setattr("nutmeg.accuracy.jobs.run_mock_accuracy_postgres_e2e", fake_runner)

    result = run_audited_accuracy_job(
        Settings(accuracy_repository="postgres"),
        reset=False,
        requested_by="admin_api",
        database=database,
        audit_repository=audit_repository,
    )

    assert audit_repository.started == [
        (
            "mock_postgres_e2e",
            False,
            "admin_api",
            {"source": "api", "repository_mode": "postgres", "dry_run": False},
        )
    ]
    assert audit_repository.completed == [
        (9, 3, {"fix_epl_001": 201}, [301, 302, 303], 9, 401)
    ]
    assert audit_repository.failed == []
    assert result.accuracy_job_run_id == 9
    assert result.requested_by == "admin_api"
    assert result.duration_ms == 75


def test_run_audited_accuracy_job_marks_failed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeAccuracyDatabase()
    audit_repository = FakeAuditRepository()

    def fake_runner(target_database: object, *, reset: bool) -> LocalAccuracyLoopRun:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("nutmeg.accuracy.jobs.run_mock_accuracy_postgres_e2e", fake_runner)

    with pytest.raises(RuntimeError, match="database unavailable"):
        run_audited_accuracy_job(
            Settings(accuracy_repository="postgres"),
            database=database,
            audit_repository=audit_repository,
        )

    assert audit_repository.completed == []
    assert audit_repository.failed == [(9, "database unavailable")]


def _job_run_record(
    *,
    status: str,
    completed_at: datetime | None,
    duration_ms: int | None = None,
    fixture_count: int = 0,
    prediction_snapshot_ids: dict[str, int] | None = None,
    evaluation_ids: list[int] | None = None,
    calibration_observation_count: int = 0,
    model_comparison_report_id: int | None = None,
    error_message: str | None = None,
) -> AccuracyJobRunRecord:
    return AccuracyJobRunRecord(
        accuracy_job_run_id=9,
        job_type="mock_postgres_e2e",
        status=status,
        reset_requested=True,
        requested_by="admin_api",
        started_at=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        completed_at=completed_at,
        duration_ms=duration_ms,
        fixture_count=fixture_count,
        evaluation_count=len(evaluation_ids or []),
        calibration_observation_count=calibration_observation_count,
        model_comparison_report_id=model_comparison_report_id,
        prediction_snapshot_ids=prediction_snapshot_ids or {},
        evaluation_ids=evaluation_ids or [],
        error_message=error_message,
        metadata_json={"source": "api"},
    )
