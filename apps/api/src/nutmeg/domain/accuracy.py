from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from nutmeg.domain.settlement import OneXTwoOutcome

BacktestMode = Literal["walk_forward", "as_of_time"]
AsOfTimeLabel = Literal["T-24h", "T-6h", "T-1h", "closing"]


class ActualMatchResult(BaseModel):
    fixture_id: str
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    settled_at: datetime | None = None

    @property
    def result_1x2(self) -> OneXTwoOutcome:
        if self.home_goals > self.away_goals:
            return OneXTwoOutcome.HOME_WIN
        if self.home_goals == self.away_goals:
            return OneXTwoOutcome.DRAW
        return OneXTwoOutcome.AWAY_WIN


class PredictionEvaluation(BaseModel):
    fixture_id: str
    prediction_snapshot_id: str | None = None
    prediction_time_utc: datetime
    model_version: str
    feature_version: str
    calibration_version: str
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    actual_result_1x2: OneXTwoOutcome
    predicted_result_1x2: OneXTwoOutcome
    actual_result_probability: float = Field(ge=0.0, le=1.0)
    log_loss_1x2: float = Field(ge=0.0)
    brier_score_1x2: float = Field(ge=0.0)
    actual_score_probability: float = Field(ge=0.0, le=1.0)
    actual_score_rank: int | None = Field(default=None, ge=1)
    market_comparison_json: dict[str, object] = Field(default_factory=dict)
    error_tags: list[str] = Field(default_factory=list)
    created_at: datetime


class StoredPredictionEvaluation(BaseModel):
    evaluation_id: int = Field(gt=0)
    evaluation: PredictionEvaluation


class CalibrationBucketKey(BaseModel):
    model_version: str
    market_type: str
    outcome: str
    bucket_start: float = Field(ge=0.0, le=1.0)
    bucket_end: float = Field(ge=0.0, le=1.0)
    competition_id: str | None = None

    @property
    def stable_id(self) -> str:
        competition = self.competition_id or "all"
        return "|".join(
            [
                self.model_version,
                self.market_type,
                self.outcome,
                competition,
                f"{self.bucket_start:.2f}",
                f"{self.bucket_end:.2f}",
            ]
        )


class CalibrationBucket(BaseModel):
    key: CalibrationBucketKey
    sample_size: int = Field(default=0, ge=0)
    predicted_probability_sum: float = Field(default=0.0, ge=0.0)
    actual_count: int = Field(default=0, ge=0)

    @property
    def average_predicted_probability(self) -> float:
        if self.sample_size == 0:
            return 0.0
        return self.predicted_probability_sum / self.sample_size

    @property
    def actual_frequency(self) -> float:
        if self.sample_size == 0:
            return 0.0
        return self.actual_count / self.sample_size


class ModelVersionMetrics(BaseModel):
    model_version: str
    sample_size: int = Field(ge=0)
    log_loss: float = Field(ge=0.0)
    brier_score: float = Field(ge=0.0)
    ece: float | None = Field(default=None, ge=0.0)
    metrics_json: dict[str, object] = Field(default_factory=dict)


class ModelComparisonStub(BaseModel):
    candidate_model_version: str
    baseline_model_version: str
    candidate_metrics: ModelVersionMetrics
    baseline_metrics: ModelVersionMetrics
    decision_stub: Literal["promote_candidate", "keep_baseline", "needs_review"]
    reasons: list[str] = Field(default_factory=list)


class DateWindow(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("date window end_date must be on or after start_date")
        return self


class BacktestRunSchema(BaseModel):
    mode: BacktestMode
    model_version: str
    train_window: DateWindow | None = None
    validation_window: DateWindow | None = None
    test_window: DateWindow
    competitions: list[str] = Field(default_factory=list)
    as_of_time: AsOfTimeLabel | None = None
    notes_json: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> Self:
        if (
            self.mode == "walk_forward"
            and (self.train_window is None or self.validation_window is None)
        ):
            raise ValueError("walk_forward backtests require train and validation windows")
        if self.mode == "as_of_time" and self.as_of_time is None:
            raise ValueError("as_of_time backtests require an as_of_time label")
        return self


class StoredBacktestRun(BaseModel):
    backtest_run_id: int = Field(gt=0)
    backtest_run: BacktestRunSchema
    metrics_json: dict[str, object]
    calibration_json: dict[str, object] = Field(default_factory=dict)
    report_uri: str | None = None
    created_at: datetime


class StoredModelComparisonReport(BaseModel):
    comparison_report_id: int = Field(gt=0)
    comparison: ModelComparisonStub
    created_at: datetime
