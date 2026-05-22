from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.providers.governance.quality import (
    DataQualityBreakdown,
    DataQualityInputs,
    score_data_quality,
)

OnboardingTargetStage = Literal["beta", "production"]
OnboardingDecision = Literal["beta_ready", "production_ready", "not_ready"]


class CompetitionOnboardingInput(BaseModel):
    competition_id: str
    competition_name: str
    target_stage: OnboardingTargetStage
    schedule_coverage: float = Field(ge=0.0, le=1.0)
    result_coverage: float = Field(ge=0.0, le=1.0)
    odds_coverage: float = Field(ge=0.0, le=1.0)
    handicap_coverage: float = Field(ge=0.0, le=1.0)
    lineup_injury_coverage: float = Field(ge=0.0, le=1.0)
    historical_stats_completeness: float = Field(ge=0.0, le=1.0)
    provider_consistency: float = Field(ge=0.0, le=1.0)
    data_freshness: float = Field(ge=0.0, le=1.0)
    historical_sample_size: int = Field(ge=0)
    complete_seasons: int = Field(default=0, ge=0)
    market_resolver_tests_passed: bool
    score_grid_generation_passed: bool
    log_loss_delta_vs_baseline: float | None = None
    brier_delta_vs_baseline: float | None = None
    calibration_shift: float | None = Field(default=None, ge=0.0)


class CompetitionOnboardingAssessment(BaseModel):
    competition_id: str
    competition_name: str
    target_stage: OnboardingTargetStage
    decision: OnboardingDecision
    data_quality: DataQualityBreakdown
    reasons: list[str]
    beta_ready: bool
    production_ready: bool


def assess_competition_onboarding(
    payload: CompetitionOnboardingInput,
) -> CompetitionOnboardingAssessment:
    data_quality = score_data_quality(
        DataQualityInputs(
            fixture_reliability=payload.schedule_coverage,
            odds_coverage=payload.odds_coverage,
            lineup_injury_coverage=payload.lineup_injury_coverage,
            historical_stats_completeness=payload.historical_stats_completeness,
            provider_consistency=payload.provider_consistency,
            data_freshness=payload.data_freshness,
        )
    )
    beta_reasons = _beta_blockers(payload)
    production_reasons = _production_blockers(payload)
    beta_ready = not beta_reasons
    production_ready = beta_ready and not production_reasons

    if payload.target_stage == "production" and production_ready:
        decision: OnboardingDecision = "production_ready"
        reasons: list[str] = []
    elif payload.target_stage == "beta" and beta_ready:
        decision = "beta_ready"
        reasons = []
    else:
        decision = "not_ready"
        reasons = (
            beta_reasons
            if payload.target_stage == "beta"
            else beta_reasons + production_reasons
        )

    return CompetitionOnboardingAssessment(
        competition_id=payload.competition_id,
        competition_name=payload.competition_name,
        target_stage=payload.target_stage,
        decision=decision,
        data_quality=data_quality,
        reasons=reasons,
        beta_ready=beta_ready,
        production_ready=production_ready,
    )


def _beta_blockers(payload: CompetitionOnboardingInput) -> list[str]:
    reasons: list[str] = []
    if payload.schedule_coverage < 0.98:
        reasons.append("schedule_coverage_below_98")
    if payload.result_coverage < 0.99:
        reasons.append("result_coverage_below_99")
    if payload.historical_sample_size < 300:
        reasons.append("historical_sample_below_300")
    if payload.odds_coverage < 0.60:
        reasons.append("odds_coverage_below_60")
    if not payload.score_grid_generation_passed:
        reasons.append("score_grid_generation_not_verified")
    if not payload.market_resolver_tests_passed:
        reasons.append("market_resolver_tests_not_verified")
    return reasons


def _production_blockers(payload: CompetitionOnboardingInput) -> list[str]:
    reasons: list[str] = []
    if payload.historical_sample_size < 500 and payload.complete_seasons < 2:
        reasons.append("production_needs_500_matches_or_2_complete_seasons")
    if payload.schedule_coverage < 0.99:
        reasons.append("schedule_coverage_below_99")
    if payload.result_coverage < 0.99:
        reasons.append("result_coverage_below_99")
    if payload.odds_coverage < 0.85:
        reasons.append("odds_coverage_below_85")
    if payload.handicap_coverage < 0.70:
        reasons.append("handicap_coverage_below_70")
    if payload.log_loss_delta_vs_baseline is None:
        reasons.append("log_loss_comparison_missing")
    elif payload.log_loss_delta_vs_baseline > 0:
        reasons.append("log_loss_worse_than_baseline")
    if payload.brier_delta_vs_baseline is None:
        reasons.append("brier_comparison_missing")
    elif payload.brier_delta_vs_baseline > 0:
        reasons.append("brier_worse_than_baseline")
    if payload.calibration_shift is None:
        reasons.append("calibration_comparison_missing")
    elif payload.calibration_shift > 0.05:
        reasons.append("calibration_serious_drift")
    return reasons
