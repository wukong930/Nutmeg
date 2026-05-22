from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PromotionDecision = Literal["shadow_candidate", "keep_experiment"]


class ModelPromotionInput(BaseModel):
    candidate_model_version: str
    baseline_model_version: str
    sample_size: int = Field(ge=0)
    overall_log_loss_delta: float
    overall_brier_delta: float
    calibration_error_delta: float
    core_market_improvement: bool
    upset_precision_at_k_delta: float
    handicap_performance_delta: float
    parlay_simulation_delta: float | None = None
    low_sample_competition_drift: bool = False


class ModelPromotionReview(BaseModel):
    candidate_model_version: str
    baseline_model_version: str
    decision: PromotionDecision
    next_status: Literal["shadow", "experiment"]
    reasons: list[str]


class ModelRollbackSignal(BaseModel):
    active_model_version: str
    previous_stable_model_version: str
    online_log_loss_delta: float = 0.0
    calibration_drift: float = 0.0
    score_grid_normalization_error_count: int = Field(default=0, ge=0)
    provider_incident_active: bool = False
    api_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    log_loss_threshold: float = 0.05
    calibration_drift_threshold: float = 0.05
    api_error_rate_threshold: float = 0.02


class ModelRollbackPlan(BaseModel):
    should_rollback: bool
    target_model_version: str | None = None
    reasons: list[str]
    steps: list[str]


def evaluate_model_promotion(
    payload: ModelPromotionInput,
    *,
    minimum_sample_size: int = 300,
    tolerated_precision_drop: float = 0.02,
    tolerated_handicap_drop: float = 0.02,
) -> ModelPromotionReview:
    reasons: list[str] = []
    if payload.sample_size < minimum_sample_size:
        reasons.append("sample_size_below_minimum")
    if payload.overall_log_loss_delta > 0:
        reasons.append("overall_log_loss_worse")
    if payload.overall_brier_delta > 0:
        reasons.append("overall_brier_worse")
    if payload.calibration_error_delta > 0:
        reasons.append("calibration_error_worse")
    if not payload.core_market_improvement:
        reasons.append("no_core_market_improvement")
    if payload.upset_precision_at_k_delta < -tolerated_precision_drop:
        reasons.append("upset_precision_drop_too_large")
    if payload.handicap_performance_delta < -tolerated_handicap_drop:
        reasons.append("handicap_performance_drop_too_large")
    if payload.low_sample_competition_drift:
        reasons.append("low_sample_competition_drift")

    if reasons:
        return ModelPromotionReview(
            candidate_model_version=payload.candidate_model_version,
            baseline_model_version=payload.baseline_model_version,
            decision="keep_experiment",
            next_status="experiment",
            reasons=reasons,
        )
    return ModelPromotionReview(
        candidate_model_version=payload.candidate_model_version,
        baseline_model_version=payload.baseline_model_version,
        decision="shadow_candidate",
        next_status="shadow",
        reasons=["candidate_passed_first_promotion_gate"],
    )


def evaluate_model_rollback(payload: ModelRollbackSignal) -> ModelRollbackPlan:
    reasons: list[str] = []
    if payload.online_log_loss_delta > payload.log_loss_threshold:
        reasons.append("online_log_loss_exceeded_threshold")
    if payload.calibration_drift > payload.calibration_drift_threshold:
        reasons.append("calibration_drift_exceeded_threshold")
    if payload.score_grid_normalization_error_count > 0:
        reasons.append("score_grid_normalization_errors")
    if payload.provider_incident_active:
        reasons.append("provider_incident_active")
    if payload.api_error_rate > payload.api_error_rate_threshold:
        reasons.append("api_error_rate_exceeded_threshold")

    if not reasons:
        return ModelRollbackPlan(should_rollback=False, reasons=[], steps=[])

    return ModelRollbackPlan(
        should_rollback=True,
        target_model_version=payload.previous_stable_model_version,
        reasons=reasons,
        steps=[
            "point_active_model_version_to_previous_stable",
            "pause_candidate_publication",
            "mark_impacted_predictions",
            "generate_incident_report",
        ],
    )
