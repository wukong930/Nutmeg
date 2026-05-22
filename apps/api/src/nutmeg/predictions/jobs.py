from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.predictions.job_repository import (
    PostgresPredictionJobRunRepository,
    PredictionJobRunRecord,
    PredictionJobType,
)
from nutmeg.predictions.pipeline import (
    PreMatchPredictionDatabase,
    PreMatchPredictionPipelineResult,
    run_postgres_canonical_prematch_prediction_pipeline,
    run_postgres_mock_prematch_prediction_pipeline,
)

type PredictionJobStatus = Literal["completed"]


class PredictionJobRunAuditRepository(Protocol):
    def start_job(
        self,
        *,
        job_type: PredictionJobType,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: dict[str, object] | None = None,
    ) -> PredictionJobRunRecord:
        """Create a running audit record."""

    def complete_job(
        self,
        *,
        prediction_job_run_id: int,
        fixture_count: int,
        generated_count: int,
        feature_snapshot_ids: dict[str, int],
        prediction_snapshot_ids: dict[str, int],
        score_grid_ids: dict[str, int],
        data_quality_scores: dict[str, float],
        skipped_fixture_ids: list[str],
        warnings: list[str],
    ) -> PredictionJobRunRecord:
        """Mark a running audit record completed."""

    def fail_job(
        self,
        *,
        prediction_job_run_id: int,
        error_message: str,
    ) -> PredictionJobRunRecord:
        """Mark a running audit record failed."""


class PredictionJobResult(BaseModel):
    prediction_job_run_id: int | None = Field(default=None, gt=0)
    job_type: PredictionJobType
    status: PredictionJobStatus = "completed"
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    prediction_time_utc: datetime
    fixture_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    score_grid_ids: dict[str, int] = Field(default_factory=dict)
    data_quality_scores: dict[str, float] = Field(default_factory=dict)
    skipped_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


def run_prediction_job(
    settings: Settings,
    *,
    job_type: PredictionJobType = "mock_prematch_predictions",
    fixture_ids: list[str] | None = None,
    competition_id: str | None = None,
    dry_run: bool = True,
    as_of_time_utc: datetime | None = None,
    window_hours: int = 72,
    max_snapshot_lag_hours: int = 24,
    limit: int = 100,
    enforce_odds_quality_gate: bool = True,
    database: PreMatchPredictionDatabase | None = None,
) -> PredictionJobResult:
    if job_type not in {"mock_prematch_predictions", "canonical_prematch_predictions"}:
        raise ValueError(f"unsupported prediction job type: {job_type}")

    target_database = database or PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    pipeline_result = (
        run_postgres_mock_prematch_prediction_pipeline(
            database=target_database,
            fixture_ids=fixture_ids,
            as_of_time_utc=as_of_time_utc,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
            dry_run=dry_run,
        )
        if job_type == "mock_prematch_predictions"
        else run_postgres_canonical_prematch_prediction_pipeline(
            database=target_database,
            fixture_ids=fixture_ids,
            competition_id=competition_id,
            as_of_time_utc=as_of_time_utc,
            window_hours=window_hours,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
            limit=limit,
            enforce_odds_quality_gate=enforce_odds_quality_gate,
            dry_run=dry_run,
        )
    )
    return _job_result_from_pipeline(
        job_type=job_type,
        dry_run=dry_run,
        pipeline_result=pipeline_result,
    )


def run_audited_prediction_job(
    settings: Settings,
    *,
    job_type: PredictionJobType = "mock_prematch_predictions",
    fixture_ids: list[str] | None = None,
    competition_id: str | None = None,
    dry_run: bool = True,
    as_of_time_utc: datetime | None = None,
    window_hours: int = 72,
    max_snapshot_lag_hours: int = 24,
    limit: int = 100,
    enforce_odds_quality_gate: bool = True,
    requested_by: str | None = None,
    database: PreMatchPredictionDatabase | None = None,
    audit_repository: PredictionJobRunAuditRepository | None = None,
) -> PredictionJobResult:
    if database is None:
        postgres_database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        target_database: PreMatchPredictionDatabase = postgres_database
    else:
        target_database = database
    if audit_repository is None:
        if database is not None:
            raise ValueError("audit_repository is required when injecting a database")
        target_audit_repository: PredictionJobRunAuditRepository = (
            PostgresPredictionJobRunRepository(postgres_database)
        )
    else:
        target_audit_repository = audit_repository

    started = target_audit_repository.start_job(
        job_type=job_type,
        dry_run=dry_run,
        requested_by=requested_by,
        metadata_json={
            "source": "api",
            "fixture_ids": fixture_ids or [],
            "competition_id": competition_id,
            "window_hours": window_hours,
            "max_snapshot_lag_hours": max_snapshot_lag_hours,
            "limit": limit,
            "enforce_odds_quality_gate": enforce_odds_quality_gate,
            "provider_governance_repository": settings.provider_governance_repository,
        },
    )

    try:
        result = run_prediction_job(
            settings,
            job_type=job_type,
            fixture_ids=fixture_ids,
            competition_id=competition_id,
            dry_run=dry_run,
            as_of_time_utc=as_of_time_utc,
            window_hours=window_hours,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
            limit=limit,
            enforce_odds_quality_gate=enforce_odds_quality_gate,
            database=target_database,
        )
    except Exception as exc:
        target_audit_repository.fail_job(
            prediction_job_run_id=started.prediction_job_run_id,
            error_message=str(exc),
        )
        raise

    completed = target_audit_repository.complete_job(
        prediction_job_run_id=started.prediction_job_run_id,
        fixture_count=result.fixture_count,
        generated_count=result.generated_count,
        feature_snapshot_ids=result.feature_snapshot_ids,
        prediction_snapshot_ids=result.prediction_snapshot_ids,
        score_grid_ids=result.score_grid_ids,
        data_quality_scores=result.data_quality_scores,
        skipped_fixture_ids=result.skipped_fixture_ids,
        warnings=result.warnings,
    )
    return result.model_copy(
        update={
            "prediction_job_run_id": completed.prediction_job_run_id,
            "requested_by": completed.requested_by,
            "started_at_utc": completed.started_at,
            "completed_at_utc": completed.completed_at,
            "duration_ms": completed.duration_ms,
        }
    )


def _job_result_from_pipeline(
    *,
    job_type: PredictionJobType,
    dry_run: bool,
    pipeline_result: PreMatchPredictionPipelineResult,
) -> PredictionJobResult:
    return PredictionJobResult(
        job_type=job_type,
        dry_run=dry_run,
        prediction_time_utc=pipeline_result.prediction_time_utc,
        fixture_count=pipeline_result.fixture_count,
        generated_count=pipeline_result.generated_count,
        feature_snapshot_ids=pipeline_result.feature_snapshot_ids,
        prediction_snapshot_ids=pipeline_result.prediction_snapshot_ids,
        score_grid_ids=pipeline_result.score_grid_ids,
        data_quality_scores=pipeline_result.data_quality_scores,
        skipped_fixture_ids=pipeline_result.skipped_fixture_ids,
        warnings=pipeline_result.warnings,
    )
