from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.dixon_coles_job import (
    DixonColesTrainingBacktestJobOptions,
    DixonColesTrainingDatabaseExecutor,
    run_dixon_coles_training_backtest_job,
)
from nutmeg.accuracy.job_repository import (
    AccuracyJobRunRecord,
    AccuracyJobType,
    PostgresAccuracyJobRunRepository,
)
from nutmeg.accuracy.local_postgres_runner import (
    LocalAccuracyDatabase,
    run_mock_accuracy_postgres_e2e,
)
from nutmeg.accuracy.weekly_training import (
    WeeklyDixonColesTrainingPipelineOptions,
    build_weekly_training_pipeline_plan,
    run_weekly_dixon_coles_training_pipeline,
    weekly_training_plan_metadata,
)
from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor

type AccuracyJobStatus = Literal["completed"]


class AccuracyJobRunAuditRepository(Protocol):
    def start_job(
        self,
        *,
        job_type: AccuracyJobType,
        reset_requested: bool,
        requested_by: str | None,
        metadata_json: dict[str, object] | None = None,
    ) -> AccuracyJobRunRecord:
        """Create a running audit record."""

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
        """Mark a running audit record completed."""

    def fail_job(
        self,
        *,
        accuracy_job_run_id: int,
        error_message: str,
    ) -> AccuracyJobRunRecord:
        """Mark a running audit record failed."""


class AccuracyJobResult(BaseModel):
    accuracy_job_run_id: int | None = Field(default=None, gt=0)
    job_type: AccuracyJobType
    status: AccuracyJobStatus = "completed"
    reset: bool
    dry_run: bool = False
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    prediction_snapshot_ids: dict[str, int]
    evaluation_ids: list[int]
    calibration_observation_count: int = Field(ge=0)
    model_comparison_report_id: int | None = None
    backtest_run_id: int | None = Field(default=None, gt=0)
    model_promotion_review_id: int | None = Field(default=None, gt=0)
    candidate_model_version: str | None = None
    baseline_model_version: str | None = None
    selected_rho: float | None = None
    train_sample_size: int | None = Field(default=None, ge=0)
    validation_sample_size: int | None = Field(default=None, ge=0)
    candidate_brier_score: float | None = Field(default=None, ge=0.0)
    candidate_ece: float | None = Field(default=None, ge=0.0)
    baseline_ece: float | None = Field(default=None, ge=0.0)
    baseline_calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    promotion_evidence_json: dict[str, object] = Field(default_factory=dict)
    model_comparison_decision: str | None = None
    model_promotion_decision: str | None = None
    model_promotion_next_status: str | None = None
    model_promotion_reasons: list[str] = Field(default_factory=list)
    rollback_should_rollback: bool = False
    report_uri: str | None = None
    weekly_training_plan: dict[str, object] = Field(default_factory=dict)
    weekly_training_status: str | None = None
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


def run_accuracy_job(
    settings: Settings,
    *,
    job_type: AccuracyJobType = "mock_postgres_e2e",
    reset: bool = True,
    database: LocalAccuracyDatabase | None = None,
    dixon_coles_options: DixonColesTrainingBacktestJobOptions | None = None,
    weekly_training_options: WeeklyDixonColesTrainingPipelineOptions | None = None,
) -> AccuracyJobResult:
    target_database = database or PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    if job_type == "weekly_dixon_coles_training_pipeline":
        if weekly_training_options is None:
            raise ValueError("weekly_training_options are required for weekly training job")
        pipeline_run = run_weekly_dixon_coles_training_pipeline(
            cast(DixonColesTrainingDatabaseExecutor, target_database),
            options=weekly_training_options,
        )
        training_run = pipeline_run.training_result
        return AccuracyJobResult(
            job_type=job_type,
            reset=reset,
            dry_run=training_run.dry_run,
            fixture_count=training_run.fixture_count,
            prediction_snapshot_ids={},
            evaluation_ids=[],
            calibration_observation_count=0,
            model_comparison_report_id=training_run.model_comparison_report_id,
            backtest_run_id=training_run.backtest_run_id,
            model_promotion_review_id=training_run.model_promotion_review_id,
            candidate_model_version=training_run.candidate_model_version,
            baseline_model_version=training_run.baseline_model_version,
            selected_rho=training_run.selected_rho,
            train_sample_size=training_run.train_sample_size,
            validation_sample_size=training_run.validation_sample_size,
            candidate_brier_score=training_run.candidate_brier_score,
            candidate_ece=training_run.candidate_ece,
            baseline_ece=training_run.baseline_ece,
            baseline_calibration_evidence_json=(
                training_run.baseline_calibration_evidence_json
            ),
            calibration_evidence_json=training_run.calibration_evidence_json,
            promotion_evidence_json=training_run.promotion_evidence_json,
            model_comparison_decision=training_run.model_comparison_decision,
            model_promotion_decision=training_run.model_promotion_decision,
            model_promotion_next_status=training_run.model_promotion_next_status,
            model_promotion_reasons=training_run.model_promotion_reasons,
            rollback_should_rollback=training_run.rollback_should_rollback,
            report_uri=training_run.report_uri,
            weekly_training_plan=pipeline_run.plan.model_dump(mode="json"),
            weekly_training_status=pipeline_run.status,
            warnings=training_run.warnings,
        )
    if job_type == "dixon_coles_training_backtest":
        if dixon_coles_options is None:
            raise ValueError("dixon_coles_options are required for Dixon-Coles job")
        training_run = run_dixon_coles_training_backtest_job(
            cast(DixonColesTrainingDatabaseExecutor, target_database),
            options=dixon_coles_options,
        )
        return AccuracyJobResult(
            job_type=job_type,
            reset=reset,
            dry_run=training_run.dry_run,
            fixture_count=training_run.fixture_count,
            prediction_snapshot_ids={},
            evaluation_ids=[],
            calibration_observation_count=0,
            model_comparison_report_id=training_run.model_comparison_report_id,
            backtest_run_id=training_run.backtest_run_id,
            model_promotion_review_id=training_run.model_promotion_review_id,
            candidate_model_version=training_run.candidate_model_version,
            baseline_model_version=training_run.baseline_model_version,
            selected_rho=training_run.selected_rho,
            train_sample_size=training_run.train_sample_size,
            validation_sample_size=training_run.validation_sample_size,
            candidate_brier_score=training_run.candidate_brier_score,
            candidate_ece=training_run.candidate_ece,
            baseline_ece=training_run.baseline_ece,
            baseline_calibration_evidence_json=(
                training_run.baseline_calibration_evidence_json
            ),
            calibration_evidence_json=training_run.calibration_evidence_json,
            promotion_evidence_json=training_run.promotion_evidence_json,
            model_comparison_decision=training_run.model_comparison_decision,
            model_promotion_decision=training_run.model_promotion_decision,
            model_promotion_next_status=training_run.model_promotion_next_status,
            model_promotion_reasons=training_run.model_promotion_reasons,
            rollback_should_rollback=training_run.rollback_should_rollback,
            report_uri=training_run.report_uri,
            warnings=training_run.warnings,
        )
    if job_type != "mock_postgres_e2e":
        raise ValueError(f"unsupported accuracy job type: {job_type}")

    loop_run = run_mock_accuracy_postgres_e2e(target_database, reset=reset)
    return AccuracyJobResult(
        job_type=job_type,
        reset=reset,
        fixture_count=loop_run.fixture_count,
        prediction_snapshot_ids=loop_run.prediction_snapshot_ids,
        evaluation_ids=loop_run.evaluation_ids,
        calibration_observation_count=loop_run.calibration_observation_count,
        model_comparison_report_id=loop_run.model_comparison_report_id,
    )


def run_audited_accuracy_job(
    settings: Settings,
    *,
    job_type: AccuracyJobType = "mock_postgres_e2e",
    reset: bool = True,
    requested_by: str | None = None,
    database: LocalAccuracyDatabase | None = None,
    audit_repository: AccuracyJobRunAuditRepository | None = None,
    dixon_coles_options: DixonColesTrainingBacktestJobOptions | None = None,
    weekly_training_options: WeeklyDixonColesTrainingPipelineOptions | None = None,
) -> AccuracyJobResult:
    if database is None:
        postgres_database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        target_database: LocalAccuracyDatabase = postgres_database
    else:
        target_database = database
    if audit_repository is None:
        if database is not None:
            raise ValueError("audit_repository is required when injecting a database")
        target_audit_repository: AccuracyJobRunAuditRepository = (
            PostgresAccuracyJobRunRepository(postgres_database)
        )
    else:
        target_audit_repository = audit_repository
    started = target_audit_repository.start_job(
        job_type=job_type,
        reset_requested=reset,
        requested_by=requested_by,
        metadata_json=_accuracy_job_metadata(
            settings,
            dixon_coles_options=dixon_coles_options,
            weekly_training_options=weekly_training_options,
        ),
    )

    try:
        result = run_accuracy_job(
            settings,
            job_type=job_type,
            reset=reset,
            database=target_database,
            dixon_coles_options=dixon_coles_options,
            weekly_training_options=weekly_training_options,
        )
    except Exception as exc:
        target_audit_repository.fail_job(
            accuracy_job_run_id=started.accuracy_job_run_id,
            error_message=str(exc),
        )
        raise

    completed = target_audit_repository.complete_job(
        accuracy_job_run_id=started.accuracy_job_run_id,
        fixture_count=result.fixture_count,
        prediction_snapshot_ids=result.prediction_snapshot_ids,
        evaluation_ids=result.evaluation_ids,
        calibration_observation_count=result.calibration_observation_count,
        model_comparison_report_id=result.model_comparison_report_id,
    )
    return result.model_copy(
        update={
            "accuracy_job_run_id": completed.accuracy_job_run_id,
            "requested_by": completed.requested_by,
            "started_at_utc": completed.started_at,
            "completed_at_utc": completed.completed_at,
            "duration_ms": completed.duration_ms,
        }
    )


def _accuracy_job_metadata(
    settings: Settings,
    *,
    dixon_coles_options: DixonColesTrainingBacktestJobOptions | None,
    weekly_training_options: WeeklyDixonColesTrainingPipelineOptions | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "api",
        "repository_mode": settings.accuracy_repository,
        "dry_run": False,
    }
    if dixon_coles_options is not None:
        metadata["dry_run"] = dixon_coles_options.dry_run
    if weekly_training_options is not None:
        metadata["dry_run"] = weekly_training_options.training_options.dry_run
        metadata.update(weekly_training_plan_metadata(weekly_training_options))
        metadata["weekly_training_plan_preview"] = build_weekly_training_pipeline_plan(
            weekly_training_options
        ).run_label
    return metadata
