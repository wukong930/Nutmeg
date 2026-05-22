from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.dixon_coles_job import (
    DixonColesTrainingBacktestJobOptions,
    DixonColesTrainingBacktestJobResult,
    DixonColesTrainingDatabaseExecutor,
    run_dixon_coles_training_backtest_job,
)

WeeklyTrainingSchedulerStatus = Literal["operator_controlled_stub"]
WeeklyTrainingPipelineStatus = Literal["completed_with_review_artifacts"]


class WeeklyDixonColesTrainingPipelineOptions(BaseModel):
    training_options: DixonColesTrainingBacktestJobOptions
    scheduled_for_utc: datetime | None = None
    run_label: str | None = Field(default=None, min_length=1)
    scheduler_status: WeeklyTrainingSchedulerStatus = "operator_controlled_stub"


class WeeklyTrainingPipelinePlan(BaseModel):
    cadence: Literal["weekly"] = "weekly"
    scheduler_status: WeeklyTrainingSchedulerStatus = "operator_controlled_stub"
    run_label: str
    scheduled_for_utc: datetime
    freeze_as_of_time_utc: datetime
    train_start_utc: datetime
    validation_start_utc: datetime
    validation_end_utc: datetime
    competition_id: str | None = None
    candidate_model_version: str
    baseline_model_version: str
    dry_run: bool
    stages: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class WeeklyDixonColesTrainingPipelineResult(BaseModel):
    plan: WeeklyTrainingPipelinePlan
    training_result: DixonColesTrainingBacktestJobResult
    status: WeeklyTrainingPipelineStatus = "completed_with_review_artifacts"


def build_weekly_training_pipeline_plan(
    options: WeeklyDixonColesTrainingPipelineOptions,
) -> WeeklyTrainingPipelinePlan:
    training_options = options.training_options
    freeze_as_of = training_options.normalized_as_of_time_utc
    scheduled_for = (
        _aware_utc(options.scheduled_for_utc)
        if options.scheduled_for_utc is not None
        else freeze_as_of
    )
    run_label = options.run_label or _default_run_label(
        freeze_as_of_time_utc=freeze_as_of,
        candidate_model_version=training_options.candidate_model_version,
    )
    return WeeklyTrainingPipelinePlan(
        scheduler_status=options.scheduler_status,
        run_label=run_label,
        scheduled_for_utc=scheduled_for,
        freeze_as_of_time_utc=freeze_as_of,
        train_start_utc=freeze_as_of - timedelta(days=training_options.train_window_days),
        validation_start_utc=freeze_as_of
        - timedelta(days=training_options.validation_window_days),
        validation_end_utc=freeze_as_of,
        competition_id=training_options.competition_id,
        candidate_model_version=training_options.candidate_model_version,
        baseline_model_version=training_options.baseline_model_version,
        dry_run=training_options.dry_run,
        stages=[
            "freeze_training_and_validation_windows",
            "train_candidate_model",
            "walk_forward_backtest",
            "probability_calibration_evidence_check",
            "model_comparison",
            "promotion_review_artifact",
        ],
        safety_notes=[
            "operator_controlled_entrypoint_only",
            "no_system_cron_installed_by_this_plan",
            "no_automatic_model_activation",
        ],
    )


def run_weekly_dixon_coles_training_pipeline(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    options: WeeklyDixonColesTrainingPipelineOptions,
) -> WeeklyDixonColesTrainingPipelineResult:
    plan = build_weekly_training_pipeline_plan(options)
    training_result = run_dixon_coles_training_backtest_job(
        database,
        options=options.training_options,
    )
    return WeeklyDixonColesTrainingPipelineResult(
        plan=plan,
        training_result=training_result,
    )


def weekly_training_plan_metadata(
    options: WeeklyDixonColesTrainingPipelineOptions,
) -> dict[str, object]:
    plan = build_weekly_training_pipeline_plan(options)
    return {
        "pipeline": "weekly_dixon_coles_training",
        "weekly_training_plan": plan.model_dump(mode="json"),
    }


def _default_run_label(
    *,
    freeze_as_of_time_utc: datetime,
    candidate_model_version: str,
) -> str:
    timestamp = freeze_as_of_time_utc.strftime("%Y%m%dT%H%M%SZ")
    safe_model = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "-"
        for character in candidate_model_version
    )
    return f"weekly-{timestamp}-{safe_model}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
