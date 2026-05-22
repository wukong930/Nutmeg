from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from math import floor, log, sqrt
from pathlib import Path
from re import sub
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver import resolve_1x2
from nutmeg.modeling import (
    HistoricalFixtureResult,
    build_competition_historical_strength_snapshot,
    build_dixon_coles_score_grid,
    build_poisson_score_grid_from_estimate,
    estimate_goal_lambdas_from_team_strength,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPoissonWalkForwardStatus = Literal["generated"]
type HistoricalPoissonWalkForwardGroupType = Literal[
    "overall",
    "competition",
    "season",
    "competition_season",
]
type HistoricalPoissonLambdaMethod = Literal[
    "rolling_strength",
    "enhanced_weighted_home_away",
    "shrunken_weighted_home_away",
    "hierarchical_weighted_home_away",
    "reliability_weighted_home_away",
    "season_weighted_home_away",
    "ema_form_adjusted",
    "form_rest_adjusted",
    "prematch_feature_adjusted",
]
type HistoricalWalkForwardScoreGridFamily = Literal["poisson", "dixon_coles_low_score"]
type HistoricalPrematchFeatureAsianHandicapLineMovementTransform = Literal[
    "linear",
    "signed_sqrt",
    "quarter_step",
]
ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS: tuple[
    HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
    ...,
] = ("linear", "signed_sqrt", "quarter_step")

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
DEFAULT_POISSON_WALK_FORWARD_MODEL_VERSION = "poisson-walk-forward-team-strength-v3.1"
DEFAULT_POISSON_WALK_FORWARD_FEATURE_VERSION = "rolling-results-team-strength-v1"
DEFAULT_POISSON_WALK_FORWARD_CALIBRATION_VERSION = "uncalibrated-walk-forward-v3.1"
DEFAULT_LOG_LOSS_EPSILON = 1e-12
MIN_ENHANCED_LAMBDA = 0.2
MAX_ENHANCED_LAMBDA = 3.5
MIN_STRENGTH = 0.45
MAX_STRENGTH = 1.9
MIN_DRAW_RATE_REFERENCE = 0.05
MAX_DRAW_RATE_REFERENCE = 0.45
DEFAULT_FORM_WINDOW_MATCHES = 6
DEFAULT_EMA_FORM_HALF_LIFE_MATCHES = 3.0
DEFAULT_REST_REFERENCE_DAYS = 6.0
DEFAULT_MAX_LAMBDA_ADJUSTMENT = 0.25
DEFAULT_STRENGTH_SHRINKAGE_MATCHES = 8.0
DEFAULT_PRIOR_SEASON_WEIGHT = 0.35
DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT = 0.12


class HistoricalPoissonWalkForwardOptions(BaseModel):
    lambda_method: HistoricalPoissonLambdaMethod = "rolling_strength"
    score_grid_family: HistoricalWalkForwardScoreGridFamily = "poisson"
    dixon_coles_rho: float = Field(default=-0.05, ge=-0.5, le=0.5)
    min_prior_matches: int = Field(default=30, ge=0)
    min_team_matches: int = Field(default=5, ge=1)
    max_training_results: int = Field(default=380, ge=1)
    max_goals: int = Field(default=8, ge=1, le=20)
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=30, ge=1)
    recency_half_life_days: float | None = Field(default=None, gt=0.0)
    home_away_split_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    strength_shrinkage_matches: float = Field(
        default=DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
        ge=0.0,
        le=80.0,
    )
    prior_season_weight: float = Field(
        default=DEFAULT_PRIOR_SEASON_WEIGHT,
        ge=0.0,
        le=1.0,
    )
    draw_correction_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    market_anchor_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    form_window_matches: int = Field(default=DEFAULT_FORM_WINDOW_MATCHES, ge=1)
    ema_form_half_life_matches: float = Field(
        default=DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
        gt=0.0,
        le=20.0,
    )
    form_adjustment_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    rest_adjustment_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    rest_reference_days: float = Field(default=DEFAULT_REST_REFERENCE_DAYS, gt=0.0)
    max_lambda_adjustment: float = Field(
        default=DEFAULT_MAX_LAMBDA_ADJUSTMENT,
        ge=0.0,
        le=1.0,
    )
    min_prematch_feature_data_quality_score: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
    )
    prematch_feature_odds_movement_weight: float = Field(
        default=0.50,
        ge=0.0,
        le=2.0,
    )
    prematch_feature_asian_handicap_movement_weight: float = Field(
        default=0.50,
        ge=0.0,
        le=2.0,
    )
    prematch_feature_min_asian_handicap_probability_delta: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_asian_handicap_line_movement_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
    )
    prematch_feature_min_asian_handicap_line_delta: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
    )
    prematch_feature_asian_handicap_line_movement_scale: float = Field(
        default=2.0,
        gt=0.0,
        le=10.0,
    )
    prematch_feature_asian_handicap_line_movement_transform: (
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform
    ) = "linear"
    prematch_feature_lineup_strength_weight: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_availability_risk_weight: float = Field(
        default=0.06,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_draw_risk_weight: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_semantic_risk_weight: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
    )
    max_prematch_feature_lambda_adjustment: float = Field(
        default=DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
        ge=0.0,
        le=0.50,
    )
    allow_missing_prematch_feature_fallback: bool = False
    require_feature_not_after_prediction: bool = True
    require_feature_before_kickoff: bool = True
    model_version: str = DEFAULT_POISSON_WALK_FORWARD_MODEL_VERSION
    feature_version: str = DEFAULT_POISSON_WALK_FORWARD_FEATURE_VERSION
    calibration_version: str = DEFAULT_POISSON_WALK_FORWARD_CALIBRATION_VERSION
    prediction_sample_limit: int = Field(default=20, ge=0)


class HistoricalPoissonWalkForwardMetricSet(BaseModel):
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    average_actual_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_calibration_error: float | None = Field(default=None, ge=0.0)
    calibration_observation_count: int = Field(default=0, ge=0)
    included_calibration_bucket_count: int = Field(default=0, ge=0)
    skipped_small_calibration_bucket_count: int = Field(default=0, ge=0)


class HistoricalPoissonWalkForwardFixtureSample(BaseModel):
    fixture_id: str
    slice_id: str
    competition_id: str
    season: str | None = None
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_outcome: str
    training_match_count: int = Field(ge=0)
    home_sample_matches: int | None = Field(default=None, ge=0)
    away_sample_matches: int | None = Field(default=None, ge=0)
    strength_shrinkage_matches: float = Field(default=0.0, ge=0.0)
    home_strength_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    away_strength_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_home_away_split_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    current_season_match_count: int | None = Field(default=None, ge=0)
    prior_season_match_count: int | None = Field(default=None, ge=0)
    prior_season_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    lambda_method: HistoricalPoissonLambdaMethod = "rolling_strength"
    score_grid_family: HistoricalWalkForwardScoreGridFamily = "poisson"
    dixon_coles_rho: float | None = Field(default=None, ge=-0.5, le=0.5)
    lambda_home: float = Field(gt=0.0)
    lambda_away: float = Field(gt=0.0)
    draw_rate_reference: float | None = Field(default=None, ge=0.0, le=1.0)
    home_form_sample_matches: int | None = Field(default=None, ge=0)
    away_form_sample_matches: int | None = Field(default=None, ge=0)
    home_form_points_per_match: float | None = Field(default=None, ge=0.0, le=3.0)
    away_form_points_per_match: float | None = Field(default=None, ge=0.0, le=3.0)
    home_form_goal_difference_per_match: float | None = None
    away_form_goal_difference_per_match: float | None = None
    ema_form_half_life_matches: float | None = Field(default=None, gt=0.0)
    home_rest_days: float | None = Field(default=None, ge=0.0)
    away_rest_days: float | None = Field(default=None, ge=0.0)
    form_adjustment_factor: float = Field(default=0.0, ge=-1.0, le=1.0)
    rest_adjustment_factor: float = Field(default=0.0, ge=-1.0, le=1.0)
    total_lambda_adjustment_factor: float = Field(default=0.0, ge=-1.0, le=1.0)
    lambda_home_before_prematch_feature_adjustment: float | None = Field(
        default=None,
        gt=0.0,
    )
    lambda_away_before_prematch_feature_adjustment: float | None = Field(
        default=None,
        gt=0.0,
    )
    prematch_feature_data_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    prematch_feature_adjustment_factor: float = Field(default=0.0, ge=-1.0, le=1.0)
    prematch_feature_total_goals_adjustment_factor: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
    )
    prematch_feature_reason_codes: list[str] = Field(default_factory=list)
    prematch_feature_readout_json: dict[str, object] = Field(default_factory=dict)
    candidate_probabilities_before_draw_correction: dict[str, float] = Field(
        default_factory=dict
    )
    candidate_probabilities_before_market_anchor: dict[str, float] = Field(
        default_factory=dict
    )
    market_anchor_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    model_signal_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    candidate_probabilities: dict[str, float] = Field(default_factory=dict)
    baseline_probabilities: dict[str, float] = Field(default_factory=dict)
    candidate_actual_probability: float = Field(ge=0.0, le=1.0)
    baseline_actual_probability: float = Field(ge=0.0, le=1.0)
    candidate_brier_score: float = Field(ge=0.0)
    baseline_brier_score: float = Field(ge=0.0)
    candidate_log_loss: float = Field(ge=0.0)
    baseline_log_loss: float = Field(ge=0.0)
    brier_score_delta_vs_baseline: float
    log_loss_delta_vs_baseline: float
    actual_probability_delta_vs_baseline: float


class HistoricalPoissonWalkForwardComparisonGroup(BaseModel):
    group_key: str
    group_type: HistoricalPoissonWalkForwardGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate: HistoricalPoissonWalkForwardMetricSet
    baseline: HistoricalPoissonWalkForwardMetricSet
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPoissonWalkForwardReport(BaseModel):
    report_key: str
    status: HistoricalPoissonWalkForwardStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    overall: HistoricalPoissonWalkForwardComparisonGroup
    by_competition: list[HistoricalPoissonWalkForwardComparisonGroup] = Field(
        default_factory=list
    )
    by_season: list[HistoricalPoissonWalkForwardComparisonGroup] = Field(
        default_factory=list
    )
    by_competition_season: list[HistoricalPoissonWalkForwardComparisonGroup] = Field(
        default_factory=list
    )
    sampled_predictions: list[HistoricalPoissonWalkForwardFixtureSample] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _FixtureContext:
    slice_id: str
    season: str | None
    fixture: HistoricalFixture


@dataclass(frozen=True)
class _SkippedFixture:
    fixture_id: str
    competition_id: str
    season: str | None
    reason: str


@dataclass(frozen=True)
class _WalkForwardLambdaEstimate:
    lambda_home: float
    lambda_away: float
    training_match_count: int
    home_sample_matches: int | None
    away_sample_matches: int | None
    strength_shrinkage_matches: float = 0.0
    home_strength_reliability: float | None = None
    away_strength_reliability: float | None = None
    effective_home_away_split_weight: float | None = None
    current_season_match_count: int | None = None
    prior_season_match_count: int | None = None
    prior_season_weight: float = 1.0
    draw_rate_reference: float | None = None
    home_form_sample_matches: int | None = None
    away_form_sample_matches: int | None = None
    home_form_points_per_match: float | None = None
    away_form_points_per_match: float | None = None
    home_form_goal_difference_per_match: float | None = None
    away_form_goal_difference_per_match: float | None = None
    ema_form_half_life_matches: float | None = None
    home_rest_days: float | None = None
    away_rest_days: float | None = None
    form_adjustment_factor: float = 0.0
    rest_adjustment_factor: float = 0.0
    total_lambda_adjustment_factor: float = 0.0
    lambda_home_before_prematch_feature_adjustment: float | None = None
    lambda_away_before_prematch_feature_adjustment: float | None = None
    prematch_feature_data_quality_score: float | None = None
    prematch_feature_adjustment_factor: float = 0.0
    prematch_feature_total_goals_adjustment_factor: float = 0.0
    prematch_feature_reason_codes: tuple[str, ...] = ()
    prematch_feature_readout_json: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _RecentTeamForm:
    sample_matches: int
    points_per_match: float | None
    goal_difference_per_match: float | None
    rest_days: float | None


@dataclass(frozen=True)
class _PrematchFeatureLambdaReadout:
    feature_data_quality_score: float
    tracked_outcome: str
    odds_movement_home_advantage_signal: float
    odds_movement_probability_delta: float | None
    lineup_strength_score: float
    lineup_schedule_risk: float
    key_player_absence_score: float
    draw_risk_score: float
    market_volatility_score: float
    semantic_risk_score: float
    source_ref_count: int
    reason_codes: tuple[str, ...]
    readout_json: dict[str, object]


@dataclass
class _WeightedTeamTotals:
    matches: int = 0
    weighted_matches: float = 0.0
    home_matches: int = 0
    weighted_home_matches: float = 0.0
    away_matches: int = 0
    weighted_away_matches: float = 0.0
    goals_for: float = 0.0
    goals_against: float = 0.0
    home_goals_for: float = 0.0
    home_goals_against: float = 0.0
    away_goals_for: float = 0.0
    away_goals_against: float = 0.0


@dataclass
class _CalibrationBucketAccumulator:
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0

    def observe(self, *, predicted_probability: float, actual_occurred: bool) -> None:
        self.sample_size += 1
        self.predicted_probability_sum += predicted_probability
        self.actual_count += 1 if actual_occurred else 0


@dataclass
class _MetricAccumulator:
    sample_size: int = 0
    hit_count: int = 0
    brier_score_sum: float = 0.0
    log_loss_sum: float = 0.0
    actual_probability_sum: float = 0.0
    calibration_buckets: dict[tuple[str, float, float], _CalibrationBucketAccumulator] = (
        field(default_factory=dict)
    )

    def observe(
        self,
        *,
        probabilities: dict[str, float],
        actual_outcome: str,
        bucket_size: float,
    ) -> None:
        self.sample_size += 1
        predicted_outcome = _predicted_outcome(probabilities)
        if predicted_outcome == actual_outcome:
            self.hit_count += 1
        actual_probability = probabilities[actual_outcome]
        self.actual_probability_sum += actual_probability
        self.brier_score_sum += _brier_score(probabilities, actual_outcome)
        self.log_loss_sum += _log_loss(actual_probability)
        for outcome in ONE_X_TWO_OUTCOMES:
            probability = probabilities[outcome]
            bucket_start, bucket_end = _bucket_bounds(probability, bucket_size)
            key = (outcome, bucket_start, bucket_end)
            bucket = self.calibration_buckets.setdefault(
                key,
                _CalibrationBucketAccumulator(),
            )
            bucket.observe(
                predicted_probability=probability,
                actual_occurred=outcome == actual_outcome,
            )


def build_historical_poisson_walk_forward_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPoissonWalkForwardOptions | None = None,
) -> HistoricalPoissonWalkForwardReport:
    resolved_options = options or HistoricalPoissonWalkForwardOptions()
    fixture_contexts = _fixture_contexts(historical_slices)
    evaluations, skipped = _walk_forward_fixture_evaluations(
        fixture_contexts,
        options=resolved_options,
    )
    overall = _comparison_group(
        "overall",
        group_type="overall",
        label="Overall",
        evaluations=evaluations,
        skipped=skipped,
        options=resolved_options,
    )
    by_competition = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="competition",
        key_fn=lambda item: item.competition_id,
        skipped_key_fn=lambda item: item.competition_id,
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_season = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="season",
        key_fn=lambda item: item.season or "unknown",
        skipped_key_fn=lambda item: item.season or "unknown",
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_competition_season = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="competition_season",
        key_fn=lambda item: "|".join(
            [item.competition_id, item.season or "unknown"]
        ),
        skipped_key_fn=lambda item: "|".join(
            [item.competition_id, item.season or "unknown"]
        ),
        label_fn=lambda key: key.replace("|", " "),
        options=resolved_options,
    )
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    warnings = _report_warnings(evaluations, skipped)
    report_key = _report_key(
        historical_slices,
        options=resolved_options,
        validation_count=len(evaluations),
        skipped_reason_counts=skipped_reason_counts,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_walk_forward_v3_1",
        "report_key": report_key,
        "model_version": resolved_options.model_version,
        "feature_version": resolved_options.feature_version,
        "calibration_version": resolved_options.calibration_version,
        "lambda_method": resolved_options.lambda_method,
        "score_grid_family": resolved_options.score_grid_family,
        "dixon_coles_rho": resolved_options.dixon_coles_rho,
        "recency_half_life_days": resolved_options.recency_half_life_days,
        "home_away_split_weight": resolved_options.home_away_split_weight,
        "strength_shrinkage_matches": resolved_options.strength_shrinkage_matches,
        "prior_season_weight": resolved_options.prior_season_weight,
        "draw_correction_weight": resolved_options.draw_correction_weight,
        "market_anchor_weight": resolved_options.market_anchor_weight,
        "form_window_matches": resolved_options.form_window_matches,
        "ema_form_half_life_matches": resolved_options.ema_form_half_life_matches,
        "form_adjustment_weight": resolved_options.form_adjustment_weight,
        "rest_adjustment_weight": resolved_options.rest_adjustment_weight,
        "rest_reference_days": resolved_options.rest_reference_days,
        "max_lambda_adjustment": resolved_options.max_lambda_adjustment,
        "min_prematch_feature_data_quality_score": (
            resolved_options.min_prematch_feature_data_quality_score
        ),
        "prematch_feature_odds_movement_weight": (
            resolved_options.prematch_feature_odds_movement_weight
        ),
        "prematch_feature_asian_handicap_movement_weight": (
            resolved_options.prematch_feature_asian_handicap_movement_weight
        ),
        "prematch_feature_min_asian_handicap_probability_delta": (
            resolved_options.prematch_feature_min_asian_handicap_probability_delta
        ),
        "prematch_feature_asian_handicap_line_movement_weight": (
            resolved_options.prematch_feature_asian_handicap_line_movement_weight
        ),
        "prematch_feature_min_asian_handicap_line_delta": (
            resolved_options.prematch_feature_min_asian_handicap_line_delta
        ),
        "prematch_feature_asian_handicap_line_movement_scale": (
            resolved_options.prematch_feature_asian_handicap_line_movement_scale
        ),
        "prematch_feature_asian_handicap_line_movement_transform": (
            resolved_options.prematch_feature_asian_handicap_line_movement_transform
        ),
        "prematch_feature_lineup_strength_weight": (
            resolved_options.prematch_feature_lineup_strength_weight
        ),
        "prematch_feature_availability_risk_weight": (
            resolved_options.prematch_feature_availability_risk_weight
        ),
        "prematch_feature_draw_risk_weight": (
            resolved_options.prematch_feature_draw_risk_weight
        ),
        "prematch_feature_semantic_risk_weight": (
            resolved_options.prematch_feature_semantic_risk_weight
        ),
        "max_prematch_feature_lambda_adjustment": (
            resolved_options.max_prematch_feature_lambda_adjustment
        ),
        "prematch_feature_lambda_adjustment_shadow_only": (
            resolved_options.lambda_method == "prematch_feature_adjusted"
        ),
        "market_anchor_calibration_shadow_only": (
            resolved_options.market_anchor_weight > 0
        ),
        "sample_shrinkage_shadow_only": (
            resolved_options.lambda_method == "shrunken_weighted_home_away"
        ),
        "hierarchical_strength_shadow_only": (
            resolved_options.lambda_method == "hierarchical_weighted_home_away"
        ),
        "reliability_weighted_home_away_shadow_only": (
            resolved_options.lambda_method == "reliability_weighted_home_away"
        ),
        "season_weighted_shadow_only": (
            resolved_options.lambda_method == "season_weighted_home_away"
        ),
        "ema_form_adjustment_shadow_only": (
            resolved_options.lambda_method == "ema_form_adjusted"
        ),
        "dixon_coles_v15_compatible": True,
        "baseline_source": "historical_slice_1x2_probability",
        "slice_count": len(historical_slices),
        "fixture_count": len(fixture_contexts),
        "validation_count": len(evaluations),
        "skipped_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "candidate_brier_score": overall.candidate.brier_score,
        "baseline_brier_score": overall.baseline.brier_score,
        "candidate_log_loss": overall.candidate.log_loss,
        "baseline_log_loss": overall.baseline.log_loss,
        "candidate_hit_rate": overall.candidate.hit_rate,
        "baseline_hit_rate": overall.baseline.hit_rate,
        "candidate_expected_calibration_error": (
            overall.candidate.expected_calibration_error
        ),
        "baseline_expected_calibration_error": (
            overall.baseline.expected_calibration_error
        ),
        "deltas_json": overall.deltas_json,
        "warnings": warnings,
    }
    return HistoricalPoissonWalkForwardReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=len(fixture_contexts),
        validation_count=len(evaluations),
        skipped_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        overall=overall,
        by_competition=by_competition,
        by_season=by_season,
        by_competition_season=by_competition_season,
        sampled_predictions=evaluations[: resolved_options.prediction_sample_limit],
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_poisson_walk_forward_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _walk_forward_fixture_evaluations(
    fixture_contexts: Sequence[_FixtureContext],
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> tuple[list[HistoricalPoissonWalkForwardFixtureSample], list[_SkippedFixture]]:
    evaluations: list[HistoricalPoissonWalkForwardFixtureSample] = []
    skipped: list[_SkippedFixture] = []
    for competition_id, competition_contexts in _contexts_by_competition(
        fixture_contexts
    ).items():
        prior_results: list[HistoricalFixtureResult] = []
        for context in sorted(
            competition_contexts,
            key=lambda item: (
                _aware_utc(item.fixture.kickoff_time_utc),
                item.fixture.fixture_id,
            ),
        ):
            fixture = context.fixture
            baseline_probabilities = _baseline_probabilities(fixture)
            if baseline_probabilities is None:
                skipped.append(_skipped(context, "missing_complete_1x2_baseline"))
                prior_results.append(
                    _historical_result(fixture, season=context.season)
                )
                continue
            if len(prior_results) < options.min_prior_matches:
                skipped.append(_skipped(context, "insufficient_prior_matches"))
                prior_results.append(
                    _historical_result(fixture, season=context.season)
                )
                continue
            estimate, estimate_skip_reason = _estimate_walk_forward_lambdas_with_skip_reason(
                prior_results,
                competition_id=competition_id,
                fixture=fixture,
                season=context.season,
                options=options,
            )
            if estimate is None:
                skipped.append(
                    _skipped(
                        context,
                        estimate_skip_reason or "insufficient_team_samples",
                    )
                )
                prior_results.append(
                    _historical_result(fixture, season=context.season)
                )
                continue
            score_grid = _build_walk_forward_score_grid(
                fixture.fixture_id,
                estimate,
                options=options,
            )
            raw_candidate_probabilities = resolve_1x2(score_grid).as_market_map()
            candidate_probabilities = _apply_draw_rate_correction(
                raw_candidate_probabilities,
                draw_rate_reference=estimate.draw_rate_reference,
                correction_weight=options.draw_correction_weight,
            )
            candidate_probabilities_before_market_anchor = candidate_probabilities
            candidate_probabilities = _apply_market_anchor(
                candidate_probabilities_before_market_anchor,
                baseline_probabilities=baseline_probabilities,
                anchor_weight=options.market_anchor_weight,
            )
            actual_outcome = fixture.actual_1x2_outcome
            evaluations.append(
                _fixture_sample(
                    context,
                    training_match_count=estimate.training_match_count,
                    home_sample_matches=estimate.home_sample_matches,
                    away_sample_matches=estimate.away_sample_matches,
                    strength_shrinkage_matches=estimate.strength_shrinkage_matches,
                    home_strength_reliability=estimate.home_strength_reliability,
                    away_strength_reliability=estimate.away_strength_reliability,
                    effective_home_away_split_weight=(
                        estimate.effective_home_away_split_weight
                    ),
                    current_season_match_count=estimate.current_season_match_count,
                    prior_season_match_count=estimate.prior_season_match_count,
                    prior_season_weight=estimate.prior_season_weight,
                    lambda_method=options.lambda_method,
                    score_grid_family=options.score_grid_family,
                    dixon_coles_rho=(
                        options.dixon_coles_rho
                        if options.score_grid_family == "dixon_coles_low_score"
                        else None
                    ),
                    lambda_home=estimate.lambda_home,
                    lambda_away=estimate.lambda_away,
                    draw_rate_reference=estimate.draw_rate_reference,
                    home_form_sample_matches=estimate.home_form_sample_matches,
                    away_form_sample_matches=estimate.away_form_sample_matches,
                    home_form_points_per_match=estimate.home_form_points_per_match,
                    away_form_points_per_match=estimate.away_form_points_per_match,
                    home_form_goal_difference_per_match=(
                        estimate.home_form_goal_difference_per_match
                    ),
                    away_form_goal_difference_per_match=(
                        estimate.away_form_goal_difference_per_match
                    ),
                    ema_form_half_life_matches=estimate.ema_form_half_life_matches,
                    home_rest_days=estimate.home_rest_days,
                    away_rest_days=estimate.away_rest_days,
                    form_adjustment_factor=estimate.form_adjustment_factor,
                    rest_adjustment_factor=estimate.rest_adjustment_factor,
                    total_lambda_adjustment_factor=(
                        estimate.total_lambda_adjustment_factor
                    ),
                    lambda_home_before_prematch_feature_adjustment=(
                        estimate.lambda_home_before_prematch_feature_adjustment
                    ),
                    lambda_away_before_prematch_feature_adjustment=(
                        estimate.lambda_away_before_prematch_feature_adjustment
                    ),
                    prematch_feature_data_quality_score=(
                        estimate.prematch_feature_data_quality_score
                    ),
                    prematch_feature_adjustment_factor=(
                        estimate.prematch_feature_adjustment_factor
                    ),
                    prematch_feature_total_goals_adjustment_factor=(
                        estimate.prematch_feature_total_goals_adjustment_factor
                    ),
                    prematch_feature_reason_codes=list(
                        estimate.prematch_feature_reason_codes
                    ),
                    prematch_feature_readout_json=(
                        estimate.prematch_feature_readout_json
                    ),
                    candidate_probabilities_before_draw_correction=(
                        raw_candidate_probabilities
                    ),
                    candidate_probabilities_before_market_anchor=(
                        candidate_probabilities_before_market_anchor
                    ),
                    market_anchor_weight=options.market_anchor_weight,
                    candidate_probabilities=candidate_probabilities,
                    baseline_probabilities=baseline_probabilities,
                    actual_outcome=actual_outcome,
                )
            )
            prior_results.append(_historical_result(fixture, season=context.season))
    return evaluations, skipped


def _fixture_sample(
    context: _FixtureContext,
    *,
    training_match_count: int,
    home_sample_matches: int | None,
    away_sample_matches: int | None,
    strength_shrinkage_matches: float,
    home_strength_reliability: float | None,
    away_strength_reliability: float | None,
    effective_home_away_split_weight: float | None,
    current_season_match_count: int | None,
    prior_season_match_count: int | None,
    prior_season_weight: float,
    lambda_method: HistoricalPoissonLambdaMethod,
    score_grid_family: HistoricalWalkForwardScoreGridFamily,
    dixon_coles_rho: float | None,
    lambda_home: float,
    lambda_away: float,
    draw_rate_reference: float | None,
    home_form_sample_matches: int | None,
    away_form_sample_matches: int | None,
    home_form_points_per_match: float | None,
    away_form_points_per_match: float | None,
    home_form_goal_difference_per_match: float | None,
    away_form_goal_difference_per_match: float | None,
    ema_form_half_life_matches: float | None,
    home_rest_days: float | None,
    away_rest_days: float | None,
    form_adjustment_factor: float,
    rest_adjustment_factor: float,
    total_lambda_adjustment_factor: float,
    lambda_home_before_prematch_feature_adjustment: float | None,
    lambda_away_before_prematch_feature_adjustment: float | None,
    prematch_feature_data_quality_score: float | None,
    prematch_feature_adjustment_factor: float,
    prematch_feature_total_goals_adjustment_factor: float,
    prematch_feature_reason_codes: list[str],
    prematch_feature_readout_json: dict[str, object],
    candidate_probabilities_before_draw_correction: dict[str, float],
    candidate_probabilities_before_market_anchor: dict[str, float],
    market_anchor_weight: float,
    candidate_probabilities: dict[str, float],
    baseline_probabilities: dict[str, float],
    actual_outcome: str,
) -> HistoricalPoissonWalkForwardFixtureSample:
    candidate_actual_probability = candidate_probabilities[actual_outcome]
    baseline_actual_probability = baseline_probabilities[actual_outcome]
    candidate_brier_score = _brier_score(candidate_probabilities, actual_outcome)
    baseline_brier_score = _brier_score(baseline_probabilities, actual_outcome)
    candidate_log_loss = _log_loss(candidate_actual_probability)
    baseline_log_loss = _log_loss(baseline_actual_probability)
    fixture = context.fixture
    return HistoricalPoissonWalkForwardFixtureSample(
        fixture_id=fixture.fixture_id,
        slice_id=context.slice_id,
        competition_id=fixture.competition_id,
        season=context.season,
        kickoff_time_utc=fixture.kickoff_time_utc,
        home_team_name=fixture.home_team_name,
        away_team_name=fixture.away_team_name,
        actual_outcome=actual_outcome,
        training_match_count=training_match_count,
        home_sample_matches=home_sample_matches,
        away_sample_matches=away_sample_matches,
        strength_shrinkage_matches=strength_shrinkage_matches,
        home_strength_reliability=home_strength_reliability,
        away_strength_reliability=away_strength_reliability,
        effective_home_away_split_weight=effective_home_away_split_weight,
        current_season_match_count=current_season_match_count,
        prior_season_match_count=prior_season_match_count,
        prior_season_weight=prior_season_weight,
        lambda_method=lambda_method,
        score_grid_family=score_grid_family,
        dixon_coles_rho=dixon_coles_rho,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        draw_rate_reference=draw_rate_reference,
        home_form_sample_matches=home_form_sample_matches,
        away_form_sample_matches=away_form_sample_matches,
        home_form_points_per_match=home_form_points_per_match,
        away_form_points_per_match=away_form_points_per_match,
        home_form_goal_difference_per_match=home_form_goal_difference_per_match,
        away_form_goal_difference_per_match=away_form_goal_difference_per_match,
        ema_form_half_life_matches=ema_form_half_life_matches,
        home_rest_days=home_rest_days,
        away_rest_days=away_rest_days,
        form_adjustment_factor=form_adjustment_factor,
        rest_adjustment_factor=rest_adjustment_factor,
        total_lambda_adjustment_factor=total_lambda_adjustment_factor,
        lambda_home_before_prematch_feature_adjustment=(
            lambda_home_before_prematch_feature_adjustment
        ),
        lambda_away_before_prematch_feature_adjustment=(
            lambda_away_before_prematch_feature_adjustment
        ),
        prematch_feature_data_quality_score=prematch_feature_data_quality_score,
        prematch_feature_adjustment_factor=prematch_feature_adjustment_factor,
        prematch_feature_total_goals_adjustment_factor=(
            prematch_feature_total_goals_adjustment_factor
        ),
        prematch_feature_reason_codes=prematch_feature_reason_codes,
        prematch_feature_readout_json=prematch_feature_readout_json,
        candidate_probabilities_before_draw_correction=(
            candidate_probabilities_before_draw_correction
        ),
        candidate_probabilities_before_market_anchor=(
            candidate_probabilities_before_market_anchor
        ),
        market_anchor_weight=market_anchor_weight,
        model_signal_weight=1.0 - market_anchor_weight,
        candidate_probabilities=candidate_probabilities,
        baseline_probabilities=baseline_probabilities,
        candidate_actual_probability=candidate_actual_probability,
        baseline_actual_probability=baseline_actual_probability,
        candidate_brier_score=candidate_brier_score,
        baseline_brier_score=baseline_brier_score,
        candidate_log_loss=candidate_log_loss,
        baseline_log_loss=baseline_log_loss,
        brier_score_delta_vs_baseline=candidate_brier_score - baseline_brier_score,
        log_loss_delta_vs_baseline=candidate_log_loss - baseline_log_loss,
        actual_probability_delta_vs_baseline=(
            candidate_actual_probability - baseline_actual_probability
        ),
    )


def _estimate_walk_forward_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    season: str | None = None,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    estimate, _skip_reason = _estimate_walk_forward_lambdas_with_skip_reason(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        season=season,
        options=options,
    )
    return estimate


def _estimate_walk_forward_lambdas_with_skip_reason(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    season: str | None = None,
    options: HistoricalPoissonWalkForwardOptions,
) -> tuple[_WalkForwardLambdaEstimate | None, str | None]:
    if options.lambda_method == "prematch_feature_adjusted":
        return _estimate_prematch_feature_adjusted_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
    if options.lambda_method == "form_rest_adjusted":
        estimate = _estimate_form_rest_adjusted_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "ema_form_adjusted":
        estimate = _estimate_ema_form_adjusted_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "shrunken_weighted_home_away":
        estimate = _estimate_shrunken_weighted_home_away_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "hierarchical_weighted_home_away":
        estimate = _estimate_hierarchical_weighted_home_away_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "reliability_weighted_home_away":
        estimate = _estimate_reliability_weighted_home_away_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "season_weighted_home_away":
        estimate = _estimate_season_weighted_home_away_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            season=season,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    if options.lambda_method == "enhanced_weighted_home_away":
        estimate = _estimate_enhanced_weighted_home_away_lambdas(
            prior_results,
            competition_id=competition_id,
            fixture=fixture,
            options=options,
        )
        return estimate, None if estimate is not None else "insufficient_team_samples"
    estimate = _estimate_rolling_strength_lambdas(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        options=options,
    )
    return estimate, None if estimate is not None else "insufficient_team_samples"


def _estimate_rolling_strength_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    snapshot = build_competition_historical_strength_snapshot(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        min_team_matches=options.min_team_matches,
        max_results=options.max_training_results,
    )
    estimate = estimate_goal_lambdas_from_team_strength(
        snapshot,
        fixture_id=fixture.fixture_id,
        home_team_id=_team_key(fixture.home_team_name),
        away_team_id=_team_key(fixture.away_team_name),
        model_version=options.model_version,
        feature_version=options.feature_version,
        calibration_version=options.calibration_version,
    )
    if estimate is None:
        return None
    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    return _WalkForwardLambdaEstimate(
        lambda_home=estimate.lambda_home,
        lambda_away=estimate.lambda_away,
        training_match_count=snapshot.match_count,
        home_sample_matches=_optional_int(
            estimate.metadata_json.get("home_sample_matches")
        ),
        away_sample_matches=_optional_int(
            estimate.metadata_json.get("away_sample_matches")
        ),
        draw_rate_reference=_draw_rate_reference(
            selected_results,
            as_of_time_utc=fixture.kickoff_time_utc,
            recency_half_life_days=options.recency_half_life_days,
        ),
    )


def _estimate_enhanced_weighted_home_away_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=fixture.kickoff_time_utc,
                recency_half_life_days=options.recency_half_life_days,
            ),
        )
        for result in selected_results
    ]
    return _estimate_weighted_home_away_lambdas_from_weighted_results(
        weighted_results,
        fixture=fixture,
        options=options,
    )


def _estimate_hierarchical_weighted_home_away_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=fixture.kickoff_time_utc,
                recency_half_life_days=options.recency_half_life_days,
            ),
        )
        for result in selected_results
    ]
    return _estimate_weighted_home_away_lambdas_from_weighted_results(
        weighted_results,
        fixture=fixture,
        options=options,
        shrink_attack_defense_strengths=True,
    )


def _estimate_reliability_weighted_home_away_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=fixture.kickoff_time_utc,
                recency_half_life_days=options.recency_half_life_days,
            ),
        )
        for result in selected_results
    ]
    return _estimate_weighted_home_away_lambdas_from_weighted_results(
        weighted_results,
        fixture=fixture,
        options=options,
        shrink_attack_defense_strengths=True,
        dynamic_home_away_split=True,
    )


def _estimate_season_weighted_home_away_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    season: str | None,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    use_season_weight = season is not None
    current_season_count = (
        sum(1 for result in selected_results if result.season == season)
        if use_season_weight
        else None
    )
    prior_season_count = (
        sum(1 for result in selected_results if result.season != season)
        if use_season_weight
        else None
    )
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=fixture.kickoff_time_utc,
                recency_half_life_days=options.recency_half_life_days,
            )
            * _season_weight(
                result,
                current_season=season,
                prior_season_weight=options.prior_season_weight,
            ),
        )
        for result in selected_results
    ]
    return _estimate_weighted_home_away_lambdas_from_weighted_results(
        weighted_results,
        fixture=fixture,
        options=options,
        current_season_match_count=current_season_count,
        prior_season_match_count=prior_season_count,
        prior_season_weight=(
            options.prior_season_weight if use_season_weight else 1.0
        ),
    )


def _estimate_weighted_home_away_lambdas_from_weighted_results(
    weighted_results: Sequence[tuple[HistoricalFixtureResult, float]],
    *,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
    current_season_match_count: int | None = None,
    prior_season_match_count: int | None = None,
    prior_season_weight: float = 1.0,
    shrink_attack_defense_strengths: bool = False,
    dynamic_home_away_split: bool = False,
) -> _WalkForwardLambdaEstimate | None:
    total_weight = sum(weight for _result, weight in weighted_results)
    if total_weight <= 0:
        return None
    avg_home_goals = max(
        0.1,
        sum(result.home_goals * weight for result, weight in weighted_results)
        / total_weight,
    )
    avg_away_goals = max(
        0.1,
        sum(result.away_goals * weight for result, weight in weighted_results)
        / total_weight,
    )
    league_goals_per_team_match = max(
        0.1,
        (
            sum(
                (result.home_goals + result.away_goals) * weight
                for result, weight in weighted_results
            )
            / (2 * total_weight)
        ),
    )
    team_totals: dict[str, _WeightedTeamTotals] = {}
    for result, weight in weighted_results:
        _add_weighted_team_result(
            team_totals,
            team_id=result.home_team_id,
            goals_for=result.home_goals,
            goals_against=result.away_goals,
            weight=weight,
            home_match=True,
        )
        _add_weighted_team_result(
            team_totals,
            team_id=result.away_team_id,
            goals_for=result.away_goals,
            goals_against=result.home_goals,
            weight=weight,
            home_match=False,
        )
    home_totals = team_totals.get(_team_key(fixture.home_team_name))
    away_totals = team_totals.get(_team_key(fixture.away_team_name))
    if home_totals is None or away_totals is None:
        return None
    if (
        home_totals.matches < options.min_team_matches
        or away_totals.matches < options.min_team_matches
    ):
        return None

    strength_shrinkage_matches = (
        options.strength_shrinkage_matches
        if shrink_attack_defense_strengths or dynamic_home_away_split
        else 0.0
    )
    home_reliability: float | None = None
    away_reliability: float | None = None
    if strength_shrinkage_matches > 0:
        home_reliability = _sample_reliability(
            home_totals.matches,
            shrinkage_matches=strength_shrinkage_matches,
        )
        away_reliability = _sample_reliability(
            away_totals.matches,
            shrinkage_matches=strength_shrinkage_matches,
        )
    split_weight = options.home_away_split_weight
    if dynamic_home_away_split:
        home_venue_reliability = _sample_reliability(
            home_totals.home_matches,
            shrinkage_matches=strength_shrinkage_matches,
        )
        away_venue_reliability = _sample_reliability(
            away_totals.away_matches,
            shrinkage_matches=strength_shrinkage_matches,
        )
        split_weight *= min(home_venue_reliability, away_venue_reliability)
    home_attack = _blend_strength(
        _overall_attack_strength(home_totals, league_goals_per_team_match),
        _venue_attack_strength(
            home_totals.home_goals_for,
            home_totals.weighted_home_matches,
            avg_home_goals,
        ),
        split_weight,
    )
    away_defense = _blend_strength(
        _overall_defense_weakness(away_totals, league_goals_per_team_match),
        _venue_defense_weakness(
            away_totals.away_goals_against,
            away_totals.weighted_away_matches,
            avg_home_goals,
        ),
        split_weight,
    )
    away_attack = _blend_strength(
        _overall_attack_strength(away_totals, league_goals_per_team_match),
        _venue_attack_strength(
            away_totals.away_goals_for,
            away_totals.weighted_away_matches,
            avg_away_goals,
        ),
        split_weight,
    )
    home_defense = _blend_strength(
        _overall_defense_weakness(home_totals, league_goals_per_team_match),
        _venue_defense_weakness(
            home_totals.home_goals_against,
            home_totals.weighted_home_matches,
            avg_away_goals,
        ),
        split_weight,
    )
    if shrink_attack_defense_strengths:
        home_reliability = home_reliability if home_reliability is not None else 1.0
        away_reliability = away_reliability if away_reliability is not None else 1.0
        home_attack = _shrink_strength_to_baseline(
            home_attack,
            reliability=home_reliability,
        )
        home_defense = _shrink_strength_to_baseline(
            home_defense,
            reliability=home_reliability,
        )
        away_attack = _shrink_strength_to_baseline(
            away_attack,
            reliability=away_reliability,
        )
        away_defense = _shrink_strength_to_baseline(
            away_defense,
            reliability=away_reliability,
        )
    return _WalkForwardLambdaEstimate(
        lambda_home=_clamp(
            avg_home_goals * home_attack * away_defense,
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_away=_clamp(
            avg_away_goals * away_attack * home_defense,
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        training_match_count=len(weighted_results),
        home_sample_matches=home_totals.matches,
        away_sample_matches=away_totals.matches,
        strength_shrinkage_matches=strength_shrinkage_matches,
        home_strength_reliability=home_reliability,
        away_strength_reliability=away_reliability,
        effective_home_away_split_weight=split_weight,
        current_season_match_count=current_season_match_count,
        prior_season_match_count=prior_season_match_count,
        prior_season_weight=prior_season_weight,
        draw_rate_reference=_draw_rate_reference_from_weighted_results(
            weighted_results
        ),
    )


def _estimate_shrunken_weighted_home_away_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    base_estimate = _estimate_enhanced_weighted_home_away_lambdas(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        options=options,
    )
    if base_estimate is None:
        return None

    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    league_baseline = _weighted_league_goal_baselines(
        selected_results,
        as_of_time_utc=fixture.kickoff_time_utc,
        recency_half_life_days=options.recency_half_life_days,
    )
    if league_baseline is None:
        return base_estimate

    home_reliability = _sample_reliability(
        base_estimate.home_sample_matches,
        shrinkage_matches=options.strength_shrinkage_matches,
    )
    away_reliability = _sample_reliability(
        base_estimate.away_sample_matches,
        shrinkage_matches=options.strength_shrinkage_matches,
    )
    matchup_reliability = min(home_reliability, away_reliability)
    baseline_home_goals, baseline_away_goals = league_baseline
    return replace(
        base_estimate,
        lambda_home=_clamp(
            baseline_home_goals
            + (base_estimate.lambda_home - baseline_home_goals)
            * matchup_reliability,
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_away=_clamp(
            baseline_away_goals
            + (base_estimate.lambda_away - baseline_away_goals)
            * matchup_reliability,
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        strength_shrinkage_matches=options.strength_shrinkage_matches,
        home_strength_reliability=home_reliability,
        away_strength_reliability=away_reliability,
    )


def _estimate_ema_form_adjusted_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    base_estimate = _estimate_enhanced_weighted_home_away_lambdas(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        options=options,
    )
    if base_estimate is None:
        return None

    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    home_form = _ema_team_form(
        selected_results,
        team_id=_team_key(fixture.home_team_name),
        as_of_time_utc=fixture.kickoff_time_utc,
        window_matches=options.form_window_matches,
        half_life_matches=options.ema_form_half_life_matches,
    )
    away_form = _ema_team_form(
        selected_results,
        team_id=_team_key(fixture.away_team_name),
        as_of_time_utc=fixture.kickoff_time_utc,
        window_matches=options.form_window_matches,
        half_life_matches=options.ema_form_half_life_matches,
    )
    form_adjustment = _form_adjustment_factor(home_form, away_form, options=options)
    return replace(
        base_estimate,
        lambda_home=_clamp(
            base_estimate.lambda_home * (1.0 + form_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_away=_clamp(
            base_estimate.lambda_away * (1.0 - form_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        home_form_sample_matches=home_form.sample_matches,
        away_form_sample_matches=away_form.sample_matches,
        home_form_points_per_match=home_form.points_per_match,
        away_form_points_per_match=away_form.points_per_match,
        home_form_goal_difference_per_match=home_form.goal_difference_per_match,
        away_form_goal_difference_per_match=away_form.goal_difference_per_match,
        ema_form_half_life_matches=options.ema_form_half_life_matches,
        form_adjustment_factor=form_adjustment,
        total_lambda_adjustment_factor=form_adjustment,
    )


def _estimate_form_rest_adjusted_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate | None:
    base_estimate = _estimate_enhanced_weighted_home_away_lambdas(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        options=options,
    )
    if base_estimate is None:
        return None

    selected_results = _selected_prior_results(
        prior_results,
        competition_id=competition_id,
        as_of_time_utc=fixture.kickoff_time_utc,
        max_results=options.max_training_results,
    )
    home_form = _recent_team_form(
        selected_results,
        team_id=_team_key(fixture.home_team_name),
        as_of_time_utc=fixture.kickoff_time_utc,
        window_matches=options.form_window_matches,
    )
    away_form = _recent_team_form(
        selected_results,
        team_id=_team_key(fixture.away_team_name),
        as_of_time_utc=fixture.kickoff_time_utc,
        window_matches=options.form_window_matches,
    )
    form_adjustment = _form_adjustment_factor(home_form, away_form, options=options)
    rest_adjustment = _rest_adjustment_factor(home_form, away_form, options=options)
    total_adjustment = _clamp(
        form_adjustment + rest_adjustment,
        -options.max_lambda_adjustment,
        options.max_lambda_adjustment,
    )
    return _WalkForwardLambdaEstimate(
        lambda_home=_clamp(
            base_estimate.lambda_home * (1.0 + total_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_away=_clamp(
            base_estimate.lambda_away * (1.0 - total_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        training_match_count=base_estimate.training_match_count,
        home_sample_matches=base_estimate.home_sample_matches,
        away_sample_matches=base_estimate.away_sample_matches,
        draw_rate_reference=base_estimate.draw_rate_reference,
        home_form_sample_matches=home_form.sample_matches,
        away_form_sample_matches=away_form.sample_matches,
        home_form_points_per_match=home_form.points_per_match,
        away_form_points_per_match=away_form.points_per_match,
        home_form_goal_difference_per_match=home_form.goal_difference_per_match,
        away_form_goal_difference_per_match=away_form.goal_difference_per_match,
        home_rest_days=home_form.rest_days,
        away_rest_days=away_form.rest_days,
        form_adjustment_factor=form_adjustment,
        rest_adjustment_factor=rest_adjustment,
        total_lambda_adjustment_factor=total_adjustment,
    )


def _estimate_prematch_feature_adjusted_lambdas(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    fixture: HistoricalFixture,
    options: HistoricalPoissonWalkForwardOptions,
) -> tuple[_WalkForwardLambdaEstimate | None, str | None]:
    base_estimate = _estimate_form_rest_adjusted_lambdas(
        prior_results,
        competition_id=competition_id,
        fixture=fixture,
        options=options,
    )
    if base_estimate is None:
        return None, "insufficient_team_samples"

    readout, skip_reason = _prematch_feature_lambda_readout(fixture, options=options)
    if readout is None:
        if options.allow_missing_prematch_feature_fallback:
            return (
                replace(
                    base_estimate,
                    lambda_home_before_prematch_feature_adjustment=(
                        base_estimate.lambda_home
                    ),
                    lambda_away_before_prematch_feature_adjustment=(
                        base_estimate.lambda_away
                    ),
                    prematch_feature_reason_codes=(
                        "prematch_feature_missing_fallback",
                        skip_reason or "missing_prematch_feature_readout",
                    ),
                    prematch_feature_readout_json={
                        "calculation_basis": "prematch_feature_lambda_readout_v3_1",
                        "applied": False,
                        "skip_reason": skip_reason,
                    },
                ),
                None,
            )
        return None, skip_reason or "missing_prematch_feature_readout"

    return (
        _apply_prematch_feature_lambda_adjustment(
            base_estimate,
            readout=readout,
            options=options,
        ),
        None,
    )


def _prematch_feature_lambda_readout(
    fixture: HistoricalFixture,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> tuple[_PrematchFeatureLambdaReadout | None, str | None]:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return None, "missing_prematch_feature_snapshot"
    if snapshot.data_quality_score < options.min_prematch_feature_data_quality_score:
        return None, "prematch_feature_data_quality_below_threshold"
    if (
        options.require_feature_not_after_prediction
        and _aware_utc(snapshot.feature_time_utc) > _aware_utc(fixture.prediction_time_utc)
    ):
        return None, "prematch_feature_after_prediction_time"
    if (
        options.require_feature_before_kickoff
        and _aware_utc(snapshot.feature_time_utc) >= _aware_utc(fixture.kickoff_time_utc)
    ):
        return None, "prematch_feature_not_before_kickoff"

    prematch_context = _feature_mapping(snapshot.features_json.get("prematch_context"))
    if prematch_context is None:
        return None, "missing_prematch_context"

    baseline_probabilities = _baseline_probabilities(fixture)
    if baseline_probabilities is None:
        return None, "missing_complete_1x2_baseline"

    raw_lineup = _feature_mapping(prematch_context.get("lineup"))
    raw_availability = _feature_mapping(prematch_context.get("availability"))
    lineup = raw_lineup or {}
    availability = raw_availability or {}
    risk_signals = _feature_mapping(prematch_context.get("risk_signals")) or {}
    odds_movements = _feature_list_of_mappings(prematch_context.get("odds_movement"))
    semantic_signals = _feature_list_of_mappings(
        prematch_context.get("semantic_signals")
    )
    tracked_outcome = _prematch_tracked_outcome(
        odds_movements,
        baseline_probabilities=baseline_probabilities,
    )
    tracked_movement = _prematch_movement_for_outcome(
        odds_movements,
        tracked_outcome,
    )
    odds_delta = (
        _feature_optional_float(tracked_movement.get("probability_delta"))
        if tracked_movement
        else None
    )
    lineup_risk = _prematch_lineup_risk(lineup)
    availability_risk = _prematch_availability_risk(availability)
    semantic_risk = _prematch_semantic_risk(semantic_signals)
    bookmaker_disagreement = (
        _feature_optional_float(tracked_movement.get("bookmaker_disagreement")) or 0.0
        if tracked_movement
        else 0.0
    )
    market_volatility = _clamp(
        max(
            _feature_float(risk_signals.get("market_volatility_score")),
            abs(odds_delta or 0.0),
            bookmaker_disagreement,
        ),
        0.0,
        1.0,
    )
    lineup_schedule_risk = _clamp(
        max(
            _feature_float(risk_signals.get("lineup_schedule_risk")),
            lineup_risk,
            availability_risk,
        ),
        0.0,
        1.0,
    )
    lineup_strength = _prematch_lineup_strength(
        lineup,
        availability_risk=availability_risk,
    )
    draw_risk = _prematch_draw_risk(
        baseline_probabilities,
        semantic_signals=semantic_signals,
        lineup_schedule_risk=lineup_schedule_risk,
        market_volatility_score=market_volatility,
    )
    home_advantage_signal = _prematch_odds_home_advantage_signal(
        odds_movements,
        asian_handicap_movement_weight=(
            options.prematch_feature_asian_handicap_movement_weight
        ),
        min_asian_handicap_probability_delta=(
            options.prematch_feature_min_asian_handicap_probability_delta
        ),
        asian_handicap_line_movement_weight=(
            options.prematch_feature_asian_handicap_line_movement_weight
        ),
        min_asian_handicap_line_delta=(
            options.prematch_feature_min_asian_handicap_line_delta
        ),
        asian_handicap_line_movement_scale=(
            options.prematch_feature_asian_handicap_line_movement_scale
        ),
        asian_handicap_line_movement_transform=(
            options.prematch_feature_asian_handicap_line_movement_transform
        ),
    )
    signal_family_presence = {
        "lineup": raw_lineup is not None,
        "availability": raw_availability is not None,
        "odds_movement": bool(odds_movements),
        "semantic": bool(semantic_signals),
    }
    reason_codes = _prematch_lambda_reason_codes(
        tracked_outcome=tracked_outcome,
        odds_home_advantage_signal=home_advantage_signal,
        lineup_strength=lineup_strength,
        availability_risk=availability_risk,
        draw_risk=draw_risk,
        semantic_risk=semantic_risk,
        signal_family_presence=signal_family_presence,
    )
    source_ref_count = _prematch_source_ref_count(snapshot.source_snapshot_refs)
    readout_json: dict[str, object] = {
        "calculation_basis": "prematch_feature_lambda_readout_v3_1",
        "tracked_outcome": tracked_outcome,
        "odds_movement_home_advantage_signal": home_advantage_signal,
        "odds_movement_probability_delta": odds_delta,
        "asian_handicap_movement_weight": (
            options.prematch_feature_asian_handicap_movement_weight
        ),
        "min_asian_handicap_probability_delta": (
            options.prematch_feature_min_asian_handicap_probability_delta
        ),
        "asian_handicap_line_movement_weight": (
            options.prematch_feature_asian_handicap_line_movement_weight
        ),
        "min_asian_handicap_line_delta": (
            options.prematch_feature_min_asian_handicap_line_delta
        ),
        "asian_handicap_line_movement_scale": (
            options.prematch_feature_asian_handicap_line_movement_scale
        ),
        "asian_handicap_line_movement_transform": (
            options.prematch_feature_asian_handicap_line_movement_transform
        ),
        "lineup_strength_score": lineup_strength,
        "lineup_schedule_risk": lineup_schedule_risk,
        "key_player_absence_score": _feature_float(
            availability.get("key_player_absence_score")
        ),
        "draw_risk_score": draw_risk,
        "market_volatility_score": market_volatility,
        "semantic_risk_score": semantic_risk,
        "source_ref_count": source_ref_count,
        "signal_family_presence": signal_family_presence,
        "reason_codes": reason_codes,
    }
    return (
        _PrematchFeatureLambdaReadout(
            feature_data_quality_score=snapshot.data_quality_score,
            tracked_outcome=tracked_outcome,
            odds_movement_home_advantage_signal=home_advantage_signal,
            odds_movement_probability_delta=odds_delta,
            lineup_strength_score=lineup_strength,
            lineup_schedule_risk=lineup_schedule_risk,
            key_player_absence_score=_feature_float(
                availability.get("key_player_absence_score")
            ),
            draw_risk_score=draw_risk,
            market_volatility_score=market_volatility,
            semantic_risk_score=semantic_risk,
            source_ref_count=source_ref_count,
            reason_codes=tuple(reason_codes),
            readout_json=readout_json,
        ),
        None,
    )


def _apply_prematch_feature_lambda_adjustment(
    base_estimate: _WalkForwardLambdaEstimate,
    *,
    readout: _PrematchFeatureLambdaReadout,
    options: HistoricalPoissonWalkForwardOptions,
) -> _WalkForwardLambdaEstimate:
    tracked_side = _prematch_outcome_side(readout.tracked_outcome)
    odds_signal = (
        readout.odds_movement_home_advantage_signal
        * options.prematch_feature_odds_movement_weight
    )
    lineup_signal = (
        tracked_side
        * readout.lineup_strength_score
        * options.prematch_feature_lineup_strength_weight
    )
    availability_signal = (
        -tracked_side
        * readout.key_player_absence_score
        * options.prematch_feature_availability_risk_weight
    )
    semantic_signal = (
        -tracked_side
        * readout.semantic_risk_score
        * options.prematch_feature_semantic_risk_weight
        * 0.50
    )
    raw_advantage_signal = (
        odds_signal + lineup_signal + availability_signal + semantic_signal
    )
    advantage_adjustment = _clamp(
        raw_advantage_signal,
        -options.max_prematch_feature_lambda_adjustment,
        options.max_prematch_feature_lambda_adjustment,
    )
    raw_total_goals_adjustment = -(
        readout.draw_risk_score * options.prematch_feature_draw_risk_weight
        + readout.lineup_schedule_risk
        * options.prematch_feature_semantic_risk_weight
        * 0.50
    )
    total_goals_adjustment = _clamp(
        raw_total_goals_adjustment,
        -options.max_prematch_feature_lambda_adjustment,
        0.0,
    )
    readout_json = {
        **readout.readout_json,
        "shadow_only": True,
        "applied": True,
        "raw_advantage_signal": raw_advantage_signal,
        "advantage_adjustment_factor": advantage_adjustment,
        "raw_total_goals_adjustment": raw_total_goals_adjustment,
        "total_goals_adjustment_factor": total_goals_adjustment,
        "component_signals": {
            "odds_signal": odds_signal,
            "lineup_signal": lineup_signal,
            "availability_signal": availability_signal,
            "semantic_signal": semantic_signal,
        },
    }
    return replace(
        base_estimate,
        lambda_home=_clamp(
            base_estimate.lambda_home
            * (1.0 + advantage_adjustment + total_goals_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_away=_clamp(
            base_estimate.lambda_away
            * (1.0 - advantage_adjustment + total_goals_adjustment),
            MIN_ENHANCED_LAMBDA,
            MAX_ENHANCED_LAMBDA,
        ),
        lambda_home_before_prematch_feature_adjustment=base_estimate.lambda_home,
        lambda_away_before_prematch_feature_adjustment=base_estimate.lambda_away,
        prematch_feature_data_quality_score=readout.feature_data_quality_score,
        prematch_feature_adjustment_factor=advantage_adjustment,
        prematch_feature_total_goals_adjustment_factor=total_goals_adjustment,
        prematch_feature_reason_codes=readout.reason_codes,
        prematch_feature_readout_json=readout_json,
    )


def _goal_lambda_estimate(
    fixture_id: str,
    estimate: _WalkForwardLambdaEstimate,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> GoalLambdaEstimate:
    return GoalLambdaEstimate(
        fixture_id=fixture_id,
        lambda_home=estimate.lambda_home,
        lambda_away=estimate.lambda_away,
        model_family="poisson",
        model_version=options.model_version,
        feature_version=options.feature_version,
        calibration_version=options.calibration_version,
        metadata_json={
            "lambda_method": options.lambda_method,
            "score_grid_family": options.score_grid_family,
            "dixon_coles_rho": options.dixon_coles_rho,
            "recency_half_life_days": options.recency_half_life_days,
            "home_away_split_weight": options.home_away_split_weight,
            "strength_shrinkage_matches": options.strength_shrinkage_matches,
            "prior_season_weight": options.prior_season_weight,
            "draw_correction_weight": options.draw_correction_weight,
            "form_window_matches": options.form_window_matches,
            "ema_form_half_life_matches": options.ema_form_half_life_matches,
            "form_adjustment_weight": options.form_adjustment_weight,
            "rest_adjustment_weight": options.rest_adjustment_weight,
            "rest_reference_days": options.rest_reference_days,
            "max_lambda_adjustment": options.max_lambda_adjustment,
            "training_match_count": estimate.training_match_count,
            "home_sample_matches": estimate.home_sample_matches,
            "away_sample_matches": estimate.away_sample_matches,
            "home_strength_reliability": estimate.home_strength_reliability,
            "away_strength_reliability": estimate.away_strength_reliability,
            "current_season_match_count": estimate.current_season_match_count,
            "prior_season_match_count": estimate.prior_season_match_count,
            "estimate_prior_season_weight": estimate.prior_season_weight,
            "draw_rate_reference": estimate.draw_rate_reference,
            "home_form_sample_matches": estimate.home_form_sample_matches,
            "away_form_sample_matches": estimate.away_form_sample_matches,
            "home_form_points_per_match": estimate.home_form_points_per_match,
            "away_form_points_per_match": estimate.away_form_points_per_match,
            "home_form_goal_difference_per_match": (
                estimate.home_form_goal_difference_per_match
            ),
            "away_form_goal_difference_per_match": (
                estimate.away_form_goal_difference_per_match
            ),
            "home_rest_days": estimate.home_rest_days,
            "away_rest_days": estimate.away_rest_days,
            "form_adjustment_factor": estimate.form_adjustment_factor,
            "rest_adjustment_factor": estimate.rest_adjustment_factor,
            "total_lambda_adjustment_factor": estimate.total_lambda_adjustment_factor,
            "lambda_home_before_prematch_feature_adjustment": (
                estimate.lambda_home_before_prematch_feature_adjustment
            ),
            "lambda_away_before_prematch_feature_adjustment": (
                estimate.lambda_away_before_prematch_feature_adjustment
            ),
            "prematch_feature_data_quality_score": (
                estimate.prematch_feature_data_quality_score
            ),
            "prematch_feature_adjustment_factor": (
                estimate.prematch_feature_adjustment_factor
            ),
            "prematch_feature_total_goals_adjustment_factor": (
                estimate.prematch_feature_total_goals_adjustment_factor
            ),
            "prematch_feature_reason_codes": list(
                estimate.prematch_feature_reason_codes
            ),
            "prematch_feature_readout_json": estimate.prematch_feature_readout_json,
            "dixon_coles_v15_compatible": True,
        },
    )


def _build_walk_forward_score_grid(
    fixture_id: str,
    estimate: _WalkForwardLambdaEstimate,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> ScoreProbabilityGrid:
    if options.score_grid_family == "dixon_coles_low_score":
        return build_dixon_coles_score_grid(
            fixture_id=fixture_id,
            lambda_home=estimate.lambda_home,
            lambda_away=estimate.lambda_away,
            rho=options.dixon_coles_rho,
            max_goals=options.max_goals,
            model_version=options.model_version,
            calibration_version=options.calibration_version,
        )
    return build_poisson_score_grid_from_estimate(
        _goal_lambda_estimate(fixture_id, estimate, options=options),
        max_goals=options.max_goals,
    )


def _selected_prior_results(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    as_of_time_utc: datetime,
    max_results: int,
) -> list[HistoricalFixtureResult]:
    normalized_as_of = _aware_utc(as_of_time_utc)
    return sorted(
        [
            result
            for result in prior_results
            if result.competition_id == competition_id
            and _aware_utc(result.kickoff_time_utc) < normalized_as_of
        ],
        key=lambda result: (_aware_utc(result.kickoff_time_utc), result.fixture_id),
        reverse=True,
    )[:max_results]


def _recent_team_form(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    team_id: str,
    as_of_time_utc: datetime,
    window_matches: int,
) -> _RecentTeamForm:
    normalized_as_of = _aware_utc(as_of_time_utc)
    team_results = sorted(
        [
            result
            for result in prior_results
            if _team_match_values(result, team_id) is not None
            and _aware_utc(result.kickoff_time_utc) < normalized_as_of
        ],
        key=lambda result: (_aware_utc(result.kickoff_time_utc), result.fixture_id),
        reverse=True,
    )[: max(1, window_matches)]
    if not team_results:
        return _RecentTeamForm(
            sample_matches=0,
            points_per_match=None,
            goal_difference_per_match=None,
            rest_days=None,
        )

    points = 0
    goal_difference = 0
    for result in team_results:
        values = _team_match_values(result, team_id)
        if values is None:
            continue
        goals_for, goals_against = values
        goal_difference += goals_for - goals_against
        if goals_for > goals_against:
            points += 3
        elif goals_for == goals_against:
            points += 1
    sample_matches = len(team_results)
    most_recent_match_time = _aware_utc(team_results[0].kickoff_time_utc)
    rest_days = max(
        0.0,
        (normalized_as_of - most_recent_match_time).total_seconds() / 86_400,
    )
    return _RecentTeamForm(
        sample_matches=sample_matches,
        points_per_match=points / sample_matches,
        goal_difference_per_match=goal_difference / sample_matches,
        rest_days=rest_days,
    )


def _ema_team_form(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    team_id: str,
    as_of_time_utc: datetime,
    window_matches: int,
    half_life_matches: float,
) -> _RecentTeamForm:
    normalized_as_of = _aware_utc(as_of_time_utc)
    team_results = sorted(
        [
            result
            for result in prior_results
            if _team_match_values(result, team_id) is not None
            and _aware_utc(result.kickoff_time_utc) < normalized_as_of
        ],
        key=lambda result: (_aware_utc(result.kickoff_time_utc), result.fixture_id),
        reverse=True,
    )[: max(1, window_matches)]
    if not team_results:
        return _RecentTeamForm(
            sample_matches=0,
            points_per_match=None,
            goal_difference_per_match=None,
            rest_days=None,
        )

    weighted_points = 0.0
    weighted_goal_difference = 0.0
    total_weight = 0.0
    for index, result in enumerate(team_results):
        values = _team_match_values(result, team_id)
        if values is None:
            continue
        goals_for, goals_against = values
        weight = float(0.5 ** (index / half_life_matches))
        total_weight += weight
        weighted_goal_difference += (goals_for - goals_against) * weight
        if goals_for > goals_against:
            weighted_points += 3.0 * weight
        elif goals_for == goals_against:
            weighted_points += 1.0 * weight
    most_recent_match_time = _aware_utc(team_results[0].kickoff_time_utc)
    rest_days = max(
        0.0,
        (normalized_as_of - most_recent_match_time).total_seconds() / 86_400,
    )
    if total_weight <= 0:
        return _RecentTeamForm(
            sample_matches=len(team_results),
            points_per_match=None,
            goal_difference_per_match=None,
            rest_days=rest_days,
        )
    return _RecentTeamForm(
        sample_matches=len(team_results),
        points_per_match=_clamp(weighted_points / total_weight, 0.0, 3.0),
        goal_difference_per_match=weighted_goal_difference / total_weight,
        rest_days=rest_days,
    )


def _team_match_values(
    result: HistoricalFixtureResult,
    team_id: str,
) -> tuple[int, int] | None:
    if result.home_team_id == team_id:
        return result.home_goals, result.away_goals
    if result.away_team_id == team_id:
        return result.away_goals, result.home_goals
    return None


def _form_adjustment_factor(
    home_form: _RecentTeamForm,
    away_form: _RecentTeamForm,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> float:
    if options.form_adjustment_weight <= 0:
        return 0.0
    home_score = _team_form_score(home_form)
    away_score = _team_form_score(away_form)
    if home_score is None or away_score is None:
        return 0.0
    raw_edge = (home_score - away_score) * 0.5
    return _clamp(
        raw_edge * options.form_adjustment_weight,
        -options.max_lambda_adjustment,
        options.max_lambda_adjustment,
    )


def _team_form_score(team_form: _RecentTeamForm) -> float | None:
    if (
        team_form.points_per_match is None
        or team_form.goal_difference_per_match is None
    ):
        return None
    points_component = _clamp((team_form.points_per_match - 1.5) / 1.5, -1.0, 1.0)
    goal_difference_component = _clamp(
        team_form.goal_difference_per_match / 2.0,
        -1.0,
        1.0,
    )
    return 0.7 * points_component + 0.3 * goal_difference_component


def _rest_adjustment_factor(
    home_form: _RecentTeamForm,
    away_form: _RecentTeamForm,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> float:
    if options.rest_adjustment_weight <= 0:
        return 0.0
    home_score = _rest_score(home_form.rest_days, options=options)
    away_score = _rest_score(away_form.rest_days, options=options)
    raw_edge = (home_score - away_score) * 0.5
    return _clamp(
        raw_edge * options.rest_adjustment_weight,
        -options.max_lambda_adjustment,
        options.max_lambda_adjustment,
    )


def _rest_score(
    rest_days: float | None,
    *,
    options: HistoricalPoissonWalkForwardOptions,
) -> float:
    if rest_days is None:
        return 0.0
    return _clamp(
        (rest_days - options.rest_reference_days) / options.rest_reference_days,
        -1.0,
        1.0,
    )


def _prematch_odds_home_advantage_signal(
    odds_movements: Sequence[Mapping[str, object]],
    *,
    asian_handicap_movement_weight: float = 0.50,
    min_asian_handicap_probability_delta: float = 0.0,
    asian_handicap_line_movement_weight: float = 0.0,
    min_asian_handicap_line_delta: float = 0.0,
    asian_handicap_line_movement_scale: float = 2.0,
    asian_handicap_line_movement_transform: (
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform
    ) = "linear",
) -> float:
    signal = 0.0
    seen_asian_handicap_lines: set[tuple[float | None, float | None]] = set()
    for movement in odds_movements:
        outcome = movement.get("outcome")
        probability_delta = _feature_optional_float(movement.get("probability_delta"))
        if probability_delta is None:
            continue
        if outcome == "home_win":
            signal += probability_delta
        elif outcome == "away_win":
            signal -= probability_delta
        elif (
            outcome == "home_cover"
            and abs(probability_delta) >= min_asian_handicap_probability_delta
        ):
            signal += probability_delta * asian_handicap_movement_weight
        elif (
            outcome == "away_cover"
            and abs(probability_delta) >= min_asian_handicap_probability_delta
        ):
            signal -= probability_delta * asian_handicap_movement_weight
        if outcome in {"home_cover", "away_cover"}:
            line_key = _asian_handicap_line_key(movement)
            if line_key in seen_asian_handicap_lines:
                continue
            seen_asian_handicap_lines.add(line_key)
            line_signal = _asian_handicap_line_home_advantage_signal(
                movement,
                min_line_delta=min_asian_handicap_line_delta,
                line_movement_scale=asian_handicap_line_movement_scale,
                line_movement_transform=asian_handicap_line_movement_transform,
            )
            if line_signal is not None:
                signal += line_signal * asian_handicap_line_movement_weight
    return _clamp(signal, -1.0, 1.0)


def _asian_handicap_line_home_advantage_signal(
    movement: Mapping[str, object],
    *,
    min_line_delta: float,
    line_movement_scale: float,
    line_movement_transform: HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
) -> float | None:
    metadata = _feature_mapping(movement.get("metadata_json"))
    if metadata is None:
        return None
    line_delta = _feature_optional_float(metadata.get("line_delta"))
    if line_delta is None:
        opening_line = _feature_optional_float(metadata.get("opening_line"))
        closing_line = _feature_optional_float(metadata.get("closing_line"))
        if opening_line is None or closing_line is None:
            return None
        line_delta = closing_line - opening_line
    if abs(line_delta) < min_line_delta:
        return None
    return _asian_handicap_line_delta_home_advantage_signal(
        line_delta,
        line_movement_scale=line_movement_scale,
        line_movement_transform=line_movement_transform,
    )


def _asian_handicap_line_delta_home_advantage_signal(
    line_delta: float,
    *,
    line_movement_scale: float,
    line_movement_transform: HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
) -> float:
    magnitude = abs(line_delta)
    if magnitude <= 0.0:
        return 0.0
    direction = -1.0 if line_delta > 0 else 1.0
    if line_movement_transform == "linear":
        normalized = magnitude / line_movement_scale
    elif line_movement_transform == "signed_sqrt":
        normalized = sqrt(magnitude / line_movement_scale)
    elif line_movement_transform == "quarter_step":
        normalized = max(1.0, magnitude / 0.25) / line_movement_scale
    else:
        raise ValueError(f"Unsupported line movement transform: {line_movement_transform}")
    return _clamp(direction * normalized, -1.0, 1.0)


def _asian_handicap_line_key(
    movement: Mapping[str, object],
) -> tuple[float | None, float | None]:
    metadata = _feature_mapping(movement.get("metadata_json"))
    if metadata is None:
        return None, None
    return (
        _feature_optional_float(metadata.get("opening_line")),
        _feature_optional_float(metadata.get("closing_line")),
    )


def _prematch_tracked_outcome(
    odds_movements: Sequence[Mapping[str, object]],
    *,
    baseline_probabilities: dict[str, float],
) -> str:
    movement_candidates: list[tuple[float, str]] = []
    for movement in odds_movements:
        outcome = movement.get("outcome")
        probability_delta = _feature_optional_float(movement.get("probability_delta"))
        if (
            isinstance(outcome, str)
            and outcome in ONE_X_TWO_OUTCOMES
            and probability_delta is not None
        ):
            movement_candidates.append((abs(probability_delta), outcome))
    if movement_candidates:
        return max(movement_candidates, key=lambda item: item[0])[1]
    for movement in odds_movements:
        outcome = movement.get("outcome")
        if isinstance(outcome, str) and outcome in ONE_X_TWO_OUTCOMES:
            return outcome
    return _predicted_outcome(baseline_probabilities)


def _prematch_movement_for_outcome(
    odds_movements: Sequence[Mapping[str, object]],
    outcome: str,
) -> Mapping[str, object]:
    for movement in odds_movements:
        if movement.get("outcome") == outcome:
            return movement
    return {}


def _prematch_lineup_risk(lineup: Mapping[str, object]) -> float:
    confidence = _feature_optional_float(lineup.get("expected_lineup_confidence"))
    strength = _feature_optional_float(lineup.get("starting_xi_strength"))
    bench_dropoff = _feature_float(lineup.get("bench_dropoff_score"))
    confidence_risk = 0.0 if confidence is None else max(0.0, 0.78 - confidence) / 0.78
    strength_risk = 0.0 if strength is None else max(0.0, 0.78 - strength) / 0.78
    return _clamp(
        0.40 * confidence_risk + 0.40 * strength_risk + 0.20 * bench_dropoff,
        0.0,
        1.0,
    )


def _prematch_availability_risk(availability: Mapping[str, object]) -> float:
    return _clamp(
        0.45 * _feature_float(availability.get("key_player_absence_score"))
        + 0.20 * _feature_float(availability.get("striker_absence_score"))
        + 0.18 * _feature_float(availability.get("defender_absence_score"))
        + 0.17 * _feature_float(availability.get("goalkeeper_absence_score")),
        0.0,
        1.0,
    )


def _prematch_lineup_strength(
    lineup: Mapping[str, object],
    *,
    availability_risk: float,
) -> float:
    confidence = _feature_optional_float(lineup.get("expected_lineup_confidence"))
    strength = _feature_optional_float(lineup.get("starting_xi_strength"))
    bench_dropoff = _feature_float(lineup.get("bench_dropoff_score"))
    confidence_edge = 0.0 if confidence is None else max(0.0, confidence - 0.80) / 0.20
    strength_edge = 0.0 if strength is None else max(0.0, strength - 0.78) / 0.22
    return _clamp(
        0.45 * confidence_edge
        + 0.45 * strength_edge
        - 0.35 * availability_risk
        - 0.20 * bench_dropoff,
        0.0,
        1.0,
    )


def _prematch_semantic_risk(
    semantic_signals: Sequence[Mapping[str, object]],
) -> float:
    risk_scores = [
        _feature_float(signal.get("confidence"))
        for signal in semantic_signals
        if _prematch_semantic_signal_name(signal)
        in {
            "rotation_hint",
            "press_conference_injury_hint",
            "manager_change_recently",
            "relegation_pressure",
        }
    ]
    return max(risk_scores, default=0.0)


def _prematch_draw_risk(
    baseline_probabilities: dict[str, float],
    *,
    semantic_signals: Sequence[Mapping[str, object]],
    lineup_schedule_risk: float,
    market_volatility_score: float,
) -> float:
    draw_signal = max(
        (
            _feature_float(signal.get("confidence"))
            for signal in semantic_signals
            if _prematch_semantic_signal_name(signal)
            in {"manager_change_recently", "rotation_hint", "relegation_pressure"}
        ),
        default=0.0,
    )
    baseline_draw_pressure = _clamp(
        (baseline_probabilities["draw"] - 0.25) / 0.20,
        0.0,
        1.0,
    )
    return _clamp(
        0.40 * draw_signal
        + 0.30 * baseline_draw_pressure
        + 0.20 * lineup_schedule_risk
        + 0.10 * market_volatility_score,
        0.0,
        1.0,
    )


def _prematch_lambda_reason_codes(
    *,
    tracked_outcome: str,
    odds_home_advantage_signal: float,
    lineup_strength: float,
    availability_risk: float,
    draw_risk: float,
    semantic_risk: float,
    signal_family_presence: Mapping[str, bool],
) -> list[str]:
    reason_codes = ["prematch_feature_lambda_adjustment", f"tracked_outcome:{tracked_outcome}"]
    if signal_family_presence.get("lineup"):
        reason_codes.append("lineup_signal_present")
    if signal_family_presence.get("availability"):
        reason_codes.append("availability_signal_present")
    if signal_family_presence.get("odds_movement"):
        reason_codes.append("odds_movement_signal_present")
    else:
        reason_codes.append("context_only_no_odds_movement")
    if signal_family_presence.get("semantic"):
        reason_codes.append("semantic_signal_present")
    if odds_home_advantage_signal > 0:
        reason_codes.append("home_advantage_odds_shortened")
    if odds_home_advantage_signal < 0:
        reason_codes.append("away_advantage_odds_shortened")
    if lineup_strength >= 0.25:
        reason_codes.append("lineup_strength_confirmed")
    if availability_risk >= 0.25:
        reason_codes.append("availability_risk_detected")
    if draw_risk >= 0.35:
        reason_codes.append("draw_risk_detected")
    if semantic_risk >= 0.50:
        reason_codes.append("semantic_prematch_risk_detected")
    return reason_codes


def _prematch_outcome_side(outcome: str) -> int:
    if outcome == "home_win":
        return 1
    if outcome == "away_win":
        return -1
    return 0


def _add_weighted_team_result(
    team_totals: dict[str, _WeightedTeamTotals],
    *,
    team_id: str,
    goals_for: int,
    goals_against: int,
    weight: float,
    home_match: bool,
) -> None:
    totals = team_totals.setdefault(team_id, _WeightedTeamTotals())
    totals.matches += 1
    totals.weighted_matches += weight
    totals.goals_for += goals_for * weight
    totals.goals_against += goals_against * weight
    if home_match:
        totals.home_matches += 1
        totals.weighted_home_matches += weight
        totals.home_goals_for += goals_for * weight
        totals.home_goals_against += goals_against * weight
    else:
        totals.away_matches += 1
        totals.weighted_away_matches += weight
        totals.away_goals_for += goals_for * weight
        totals.away_goals_against += goals_against * weight


def _overall_attack_strength(
    totals: _WeightedTeamTotals,
    league_goals_per_team_match: float,
) -> float | None:
    return _strength(
        _safe_divide(totals.goals_for, totals.weighted_matches),
        league_goals_per_team_match,
    )


def _overall_defense_weakness(
    totals: _WeightedTeamTotals,
    league_goals_per_team_match: float,
) -> float | None:
    return _strength(
        _safe_divide(totals.goals_against, totals.weighted_matches),
        league_goals_per_team_match,
    )


def _venue_attack_strength(
    weighted_goals_for: float,
    weighted_matches: float,
    league_venue_goals: float,
) -> float | None:
    return _strength(
        _safe_divide(weighted_goals_for, weighted_matches),
        league_venue_goals,
    )


def _venue_defense_weakness(
    weighted_goals_against: float,
    weighted_matches: float,
    league_venue_goals: float,
) -> float | None:
    return _strength(
        _safe_divide(weighted_goals_against, weighted_matches),
        league_venue_goals,
    )


def _strength(value: float | None, denominator: float) -> float | None:
    if value is None or denominator <= 0:
        return None
    return _clamp(value / denominator, MIN_STRENGTH, MAX_STRENGTH)


def _blend_strength(
    overall_strength: float | None,
    venue_strength: float | None,
    venue_weight: float,
) -> float:
    resolved_overall = overall_strength or 1.0
    if venue_strength is None:
        return resolved_overall
    return _clamp(
        (1.0 - venue_weight) * resolved_overall + venue_weight * venue_strength,
        MIN_STRENGTH,
        MAX_STRENGTH,
    )


def _draw_rate_reference(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    as_of_time_utc: datetime,
    recency_half_life_days: float | None,
) -> float | None:
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=as_of_time_utc,
                recency_half_life_days=recency_half_life_days,
            ),
        )
        for result in prior_results
    ]
    total_weight = sum(weight for _result, weight in weighted_results)
    if total_weight <= 0:
        return None
    draw_weight = sum(
        weight
        for result, weight in weighted_results
        if result.home_goals == result.away_goals
    )
    return draw_weight / total_weight


def _draw_rate_reference_from_weighted_results(
    weighted_results: Sequence[tuple[HistoricalFixtureResult, float]],
) -> float | None:
    total_weight = sum(weight for _result, weight in weighted_results)
    if total_weight <= 0:
        return None
    draw_weight = sum(
        weight
        for result, weight in weighted_results
        if result.home_goals == result.away_goals
    )
    return draw_weight / total_weight


def _season_weight(
    result: HistoricalFixtureResult,
    *,
    current_season: str | None,
    prior_season_weight: float,
) -> float:
    if current_season is None or result.season == current_season:
        return 1.0
    return prior_season_weight


def _recency_weight(
    result: HistoricalFixtureResult,
    *,
    as_of_time_utc: datetime,
    recency_half_life_days: float | None,
) -> float:
    if recency_half_life_days is None:
        return 1.0
    days_since_match = max(
        0.0,
        (
            _aware_utc(as_of_time_utc) - _aware_utc(result.kickoff_time_utc)
        ).total_seconds()
        / 86_400,
    )
    return float(0.5 ** (days_since_match / recency_half_life_days))


def _weighted_league_goal_baselines(
    prior_results: Sequence[HistoricalFixtureResult],
    *,
    as_of_time_utc: datetime,
    recency_half_life_days: float | None,
) -> tuple[float, float] | None:
    weighted_results = [
        (
            result,
            _recency_weight(
                result,
                as_of_time_utc=as_of_time_utc,
                recency_half_life_days=recency_half_life_days,
            ),
        )
        for result in prior_results
    ]
    total_weight = sum(weight for _result, weight in weighted_results)
    if total_weight <= 0:
        return None
    return (
        max(
            0.1,
            sum(result.home_goals * weight for result, weight in weighted_results)
            / total_weight,
        ),
        max(
            0.1,
            sum(result.away_goals * weight for result, weight in weighted_results)
            / total_weight,
        ),
    )


def _sample_reliability(
    sample_matches: int | None,
    *,
    shrinkage_matches: float,
) -> float:
    if shrinkage_matches <= 0:
        return 1.0
    resolved_matches = max(0.0, float(sample_matches or 0))
    return _clamp(
        resolved_matches / (resolved_matches + shrinkage_matches),
        0.0,
        1.0,
    )


def _shrink_strength_to_baseline(strength: float, *, reliability: float) -> float:
    return _clamp(
        1.0 + (strength - 1.0) * reliability,
        MIN_STRENGTH,
        MAX_STRENGTH,
    )


def _apply_draw_rate_correction(
    probabilities: dict[str, float],
    *,
    draw_rate_reference: float | None,
    correction_weight: float,
) -> dict[str, float]:
    normalized_probabilities = _normalize_probabilities(probabilities)
    if (
        normalized_probabilities is None
        or draw_rate_reference is None
        or correction_weight <= 0
    ):
        return probabilities
    target_draw = _clamp(
        draw_rate_reference,
        MIN_DRAW_RATE_REFERENCE,
        MAX_DRAW_RATE_REFERENCE,
    )
    adjusted_draw = (
        (1.0 - correction_weight) * normalized_probabilities["draw"]
        + correction_weight * target_draw
    )
    non_draw_total = (
        normalized_probabilities["home_win"] + normalized_probabilities["away_win"]
    )
    if non_draw_total <= 0:
        return normalized_probabilities
    remaining_probability = max(0.0, 1.0 - adjusted_draw)
    return {
        "home_win": remaining_probability
        * normalized_probabilities["home_win"]
        / non_draw_total,
        "draw": adjusted_draw,
        "away_win": remaining_probability
        * normalized_probabilities["away_win"]
        / non_draw_total,
    }


def _apply_market_anchor(
    probabilities: dict[str, float],
    *,
    baseline_probabilities: dict[str, float],
    anchor_weight: float,
) -> dict[str, float]:
    normalized_probabilities = _normalize_probabilities(probabilities)
    normalized_baseline = _normalize_probabilities(baseline_probabilities)
    if normalized_probabilities is None:
        return probabilities
    if normalized_baseline is None or anchor_weight <= 0:
        return normalized_probabilities
    if anchor_weight >= 1:
        return normalized_baseline
    anchored_probabilities = {
        outcome: (1.0 - anchor_weight) * normalized_probabilities[outcome]
        + anchor_weight * normalized_baseline[outcome]
        for outcome in ONE_X_TWO_OUTCOMES
    }
    return _normalize_probabilities(anchored_probabilities) or normalized_probabilities


def _comparison_group(
    group_key: str,
    *,
    group_type: HistoricalPoissonWalkForwardGroupType,
    label: str,
    evaluations: Sequence[HistoricalPoissonWalkForwardFixtureSample],
    skipped: Sequence[_SkippedFixture],
    options: HistoricalPoissonWalkForwardOptions,
    competition_id: str | None = None,
    season: str | None = None,
) -> HistoricalPoissonWalkForwardComparisonGroup:
    candidate = _metric_set(
        evaluations,
        probability_fn=lambda item: item.candidate_probabilities,
        options=options,
    )
    baseline = _metric_set(
        evaluations,
        probability_fn=lambda item: item.baseline_probabilities,
        options=options,
    )
    deltas = _metric_deltas(candidate, baseline)
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_walk_forward_group_v3_1",
        "group_key": group_key,
        "group_type": group_type,
        "label": label,
        "validation_count": len(evaluations),
        "skipped_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "candidate": candidate.model_dump(mode="json"),
        "baseline": baseline.model_dump(mode="json"),
        "deltas_json": deltas,
    }
    return HistoricalPoissonWalkForwardComparisonGroup(
        group_key=group_key,
        group_type=group_type,
        label=label,
        competition_id=competition_id,
        season=season,
        validation_count=len(evaluations),
        skipped_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        candidate=candidate,
        baseline=baseline,
        deltas_json=deltas,
        summary_json=summary,
    )


def _grouped_comparisons(
    evaluations: Sequence[HistoricalPoissonWalkForwardFixtureSample],
    skipped: Sequence[_SkippedFixture],
    *,
    group_type: HistoricalPoissonWalkForwardGroupType,
    key_fn: Callable[[HistoricalPoissonWalkForwardFixtureSample], str],
    skipped_key_fn: Callable[[_SkippedFixture], str],
    label_fn: Callable[[str], str],
    options: HistoricalPoissonWalkForwardOptions,
) -> list[HistoricalPoissonWalkForwardComparisonGroup]:
    evaluation_groups: dict[str, list[HistoricalPoissonWalkForwardFixtureSample]] = {}
    skipped_groups: dict[str, list[_SkippedFixture]] = {}
    for evaluation in evaluations:
        key = key_fn(evaluation)
        evaluation_groups.setdefault(key, []).append(evaluation)
    for skipped_fixture in skipped:
        key = skipped_key_fn(skipped_fixture)
        skipped_groups.setdefault(key, []).append(skipped_fixture)
    groups: list[HistoricalPoissonWalkForwardComparisonGroup] = []
    for key in sorted(set(evaluation_groups) | set(skipped_groups)):
        competition_id: str | None = None
        season: str | None = None
        if group_type == "competition":
            competition_id = key
        elif group_type == "season":
            season = None if key == "unknown" else key
        elif group_type == "competition_season":
            competition_id, raw_season = key.split("|", maxsplit=1)
            season = None if raw_season == "unknown" else raw_season
        groups.append(
            _comparison_group(
                key,
                group_type=group_type,
                label=label_fn(key),
                evaluations=evaluation_groups.get(key, []),
                skipped=skipped_groups.get(key, []),
                options=options,
                competition_id=competition_id,
                season=season,
            )
        )
    return groups


def _metric_set(
    evaluations: Sequence[HistoricalPoissonWalkForwardFixtureSample],
    *,
    probability_fn: Callable[[HistoricalPoissonWalkForwardFixtureSample], dict[str, float]],
    options: HistoricalPoissonWalkForwardOptions,
) -> HistoricalPoissonWalkForwardMetricSet:
    accumulator = _MetricAccumulator()
    for evaluation in evaluations:
        probabilities = probability_fn(evaluation)
        accumulator.observe(
            probabilities=probabilities,
            actual_outcome=evaluation.actual_outcome,
            bucket_size=options.bucket_size,
        )
    expected_calibration_error, included_bucket_count, skipped_bucket_count = (
        _expected_calibration_error(
            accumulator.calibration_buckets,
            min_bucket_sample_size=options.min_bucket_sample_size,
        )
    )
    return HistoricalPoissonWalkForwardMetricSet(
        sample_size=accumulator.sample_size,
        hit_count=accumulator.hit_count,
        hit_rate=_safe_divide(accumulator.hit_count, accumulator.sample_size),
        brier_score=_safe_divide(
            accumulator.brier_score_sum,
            accumulator.sample_size,
        ),
        log_loss=_safe_divide(accumulator.log_loss_sum, accumulator.sample_size),
        average_actual_probability=_safe_divide(
            accumulator.actual_probability_sum,
            accumulator.sample_size,
        ),
        expected_calibration_error=expected_calibration_error,
        calibration_observation_count=sum(
            bucket.sample_size for bucket in accumulator.calibration_buckets.values()
        ),
        included_calibration_bucket_count=included_bucket_count,
        skipped_small_calibration_bucket_count=skipped_bucket_count,
    )


def _expected_calibration_error(
    buckets: dict[tuple[str, float, float], _CalibrationBucketAccumulator],
    *,
    min_bucket_sample_size: int,
) -> tuple[float | None, int, int]:
    numerator = 0.0
    denominator = 0
    included_bucket_count = 0
    skipped_bucket_count = 0
    for bucket in buckets.values():
        if bucket.sample_size < min_bucket_sample_size:
            skipped_bucket_count += 1
            continue
        average_predicted = bucket.predicted_probability_sum / bucket.sample_size
        actual_frequency = bucket.actual_count / bucket.sample_size
        numerator += bucket.sample_size * abs(average_predicted - actual_frequency)
        denominator += bucket.sample_size
        included_bucket_count += 1
    return _safe_divide(numerator, denominator), included_bucket_count, skipped_bucket_count


def _metric_deltas(
    candidate: HistoricalPoissonWalkForwardMetricSet,
    baseline: HistoricalPoissonWalkForwardMetricSet,
) -> dict[str, object]:
    return {
        "hit_rate_delta": _optional_delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _optional_delta(
            candidate.brier_score,
            baseline.brier_score,
        ),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "average_actual_probability_delta": _optional_delta(
            candidate.average_actual_probability,
            baseline.average_actual_probability,
        ),
        "expected_calibration_error_delta": _optional_delta(
            candidate.expected_calibration_error,
            baseline.expected_calibration_error,
        ),
    }


def _contexts_by_competition(
    fixture_contexts: Sequence[_FixtureContext],
) -> dict[str, list[_FixtureContext]]:
    contexts_by_competition: dict[str, list[_FixtureContext]] = {}
    for context in fixture_contexts:
        contexts_by_competition.setdefault(
            context.fixture.competition_id,
            [],
        ).append(context)
    return contexts_by_competition


def _fixture_contexts(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> list[_FixtureContext]:
    contexts: list[_FixtureContext] = []
    for historical_slice in historical_slices:
        contexts.extend(
            _FixtureContext(
                slice_id=historical_slice.metadata.slice_id,
                season=historical_slice.metadata.season,
                fixture=fixture,
            )
            for fixture in historical_slice.fixtures
        )
    return contexts


def _baseline_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    raw_probabilities = {
        prediction.outcome: prediction.probability
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
    }
    if any(outcome not in raw_probabilities for outcome in ONE_X_TWO_OUTCOMES):
        return None
    return _normalize_probabilities(
        {outcome: raw_probabilities[outcome] for outcome in ONE_X_TWO_OUTCOMES}
    )


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, float] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {outcome: value / total for outcome, value in probabilities.items()}


def _historical_result(
    fixture: HistoricalFixture,
    *,
    season: str | None = None,
) -> HistoricalFixtureResult:
    return HistoricalFixtureResult(
        fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        season=season,
        kickoff_time_utc=fixture.kickoff_time_utc,
        home_team_id=_team_key(fixture.home_team_name),
        away_team_id=_team_key(fixture.away_team_name),
        home_goals=fixture.actual_home_goals,
        away_goals=fixture.actual_away_goals,
    )


def _team_key(team_name: str) -> str:
    slug = sub(r"[^a-z0-9]+", "_", team_name.strip().casefold()).strip("_")
    return slug or "unknown_team"


def _brier_score(probabilities: dict[str, float], actual_outcome: str) -> float:
    return sum(
        (probabilities[outcome] - (1.0 if outcome == actual_outcome else 0.0)) ** 2
        for outcome in ONE_X_TWO_OUTCOMES
    )


def _log_loss(probability: float) -> float:
    bounded_probability = min(
        max(probability, DEFAULT_LOG_LOSS_EPSILON),
        1.0 - DEFAULT_LOG_LOSS_EPSILON,
    )
    return -log(bounded_probability)


def _predicted_outcome(probabilities: dict[str, float]) -> str:
    return max(ONE_X_TWO_OUTCOMES, key=lambda outcome: probabilities[outcome])


def _bucket_bounds(probability: float, bucket_size: float) -> tuple[float, float]:
    if probability == 1.0:
        bucket_start = max(0.0, 1.0 - bucket_size)
    else:
        bucket_start = floor(probability / bucket_size) * bucket_size
    bucket_end = min(1.0, bucket_start + bucket_size)
    return round(bucket_start, 10), round(bucket_end, 10)


def _skipped(context: _FixtureContext, reason: str) -> _SkippedFixture:
    return _SkippedFixture(
        fixture_id=context.fixture.fixture_id,
        competition_id=context.fixture.competition_id,
        season=context.season,
        reason=reason,
    )


def _report_warnings(
    evaluations: Sequence[HistoricalPoissonWalkForwardFixtureSample],
    skipped: Sequence[_SkippedFixture],
) -> list[str]:
    warnings: list[str] = []
    if not evaluations:
        warnings.append("historical_poisson_walk_forward:no_validation_fixtures")
    if skipped:
        warnings.append("historical_poisson_walk_forward:skipped_fixtures")
    return warnings


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPoissonWalkForwardOptions,
    validation_count: int,
    skipped_reason_counts: dict[str, int],
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "as_of_times": [
            historical_slice.as_of_time_utc.isoformat()
            for historical_slice in historical_slices
        ],
        "slice_content_digests": [
            _slice_content_digest(historical_slice)
            for historical_slice in historical_slices
        ],
        "validation_count": validation_count,
        "skipped_reason_counts": skipped_reason_counts,
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_poisson_walk_forward:{digest}"


def _slice_content_digest(historical_slice: HistoricalRecommendationSlice) -> str:
    payload = historical_slice.model_dump(mode="json")
    return sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run a walk-forward Poisson score-grid benchmark on historical slices."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--lambda-method",
        choices=[
            "rolling_strength",
            "enhanced_weighted_home_away",
            "shrunken_weighted_home_away",
            "hierarchical_weighted_home_away",
            "reliability_weighted_home_away",
            "season_weighted_home_away",
            "ema_form_adjusted",
            "form_rest_adjusted",
            "prematch_feature_adjusted",
        ],
        default="rolling_strength",
    )
    parser.add_argument(
        "--score-grid-family",
        choices=["poisson", "dixon_coles_low_score"],
        default="poisson",
    )
    parser.add_argument("--dixon-coles-rho", type=float, default=-0.05)
    parser.add_argument("--min-prior-matches", type=int, default=30)
    parser.add_argument("--min-team-matches", type=int, default=5)
    parser.add_argument("--max-training-results", type=int, default=380)
    parser.add_argument("--max-goals", type=int, default=8)
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=30)
    parser.add_argument("--recency-half-life-days", type=float)
    parser.add_argument("--home-away-split-weight", type=float, default=0.0)
    parser.add_argument(
        "--strength-shrinkage-matches",
        type=float,
        default=DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
    )
    parser.add_argument(
        "--prior-season-weight",
        type=float,
        default=DEFAULT_PRIOR_SEASON_WEIGHT,
    )
    parser.add_argument("--draw-correction-weight", type=float, default=0.0)
    parser.add_argument("--market-anchor-weight", type=float, default=0.0)
    parser.add_argument("--form-window-matches", type=int, default=6)
    parser.add_argument(
        "--ema-form-half-life-matches",
        type=float,
        default=DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
    )
    parser.add_argument("--form-adjustment-weight", type=float, default=0.0)
    parser.add_argument("--rest-adjustment-weight", type=float, default=0.0)
    parser.add_argument("--rest-reference-days", type=float, default=6.0)
    parser.add_argument("--max-lambda-adjustment", type=float, default=0.25)
    parser.add_argument("--min-prematch-feature-data-quality-score", type=float, default=80.0)
    parser.add_argument("--prematch-feature-odds-movement-weight", type=float, default=0.50)
    parser.add_argument(
        "--prematch-feature-asian-handicap-movement-weight",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--prematch-feature-min-asian-handicap-probability-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-weight",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-min-asian-handicap-line-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-scale",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-transform",
        choices=ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS,
        default="linear",
    )
    parser.add_argument("--prematch-feature-lineup-strength-weight", type=float, default=0.08)
    parser.add_argument("--prematch-feature-availability-risk-weight", type=float, default=0.06)
    parser.add_argument("--prematch-feature-draw-risk-weight", type=float, default=0.05)
    parser.add_argument("--prematch-feature-semantic-risk-weight", type=float, default=0.04)
    parser.add_argument("--max-prematch-feature-lambda-adjustment", type=float, default=0.12)
    parser.add_argument(
        "--allow-missing-prematch-feature-fallback",
        action="store_true",
    )
    parser.add_argument(
        "--allow-feature-after-prediction",
        action="store_true",
    )
    parser.add_argument(
        "--allow-feature-not-before-kickoff",
        action="store_true",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_POISSON_WALK_FORWARD_MODEL_VERSION,
    )
    parser.add_argument(
        "--feature-version",
        default=DEFAULT_POISSON_WALK_FORWARD_FEATURE_VERSION,
    )
    parser.add_argument(
        "--calibration-version",
        default=DEFAULT_POISSON_WALK_FORWARD_CALIBRATION_VERSION,
    )
    parser.add_argument("--prediction-sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalPoissonWalkForwardOptions:
    return HistoricalPoissonWalkForwardOptions(
        lambda_method=args.lambda_method,
        score_grid_family=args.score_grid_family,
        dixon_coles_rho=args.dixon_coles_rho,
        min_prior_matches=args.min_prior_matches,
        min_team_matches=args.min_team_matches,
        max_training_results=args.max_training_results,
        max_goals=args.max_goals,
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        recency_half_life_days=args.recency_half_life_days,
        home_away_split_weight=args.home_away_split_weight,
        strength_shrinkage_matches=args.strength_shrinkage_matches,
        prior_season_weight=args.prior_season_weight,
        draw_correction_weight=args.draw_correction_weight,
        market_anchor_weight=args.market_anchor_weight,
        form_window_matches=args.form_window_matches,
        ema_form_half_life_matches=args.ema_form_half_life_matches,
        form_adjustment_weight=args.form_adjustment_weight,
        rest_adjustment_weight=args.rest_adjustment_weight,
        rest_reference_days=args.rest_reference_days,
        max_lambda_adjustment=args.max_lambda_adjustment,
        min_prematch_feature_data_quality_score=(
            args.min_prematch_feature_data_quality_score
        ),
        prematch_feature_odds_movement_weight=(
            args.prematch_feature_odds_movement_weight
        ),
        prematch_feature_asian_handicap_movement_weight=(
            args.prematch_feature_asian_handicap_movement_weight
        ),
        prematch_feature_min_asian_handicap_probability_delta=(
            args.prematch_feature_min_asian_handicap_probability_delta
        ),
        prematch_feature_asian_handicap_line_movement_weight=(
            args.prematch_feature_asian_handicap_line_movement_weight
        ),
        prematch_feature_min_asian_handicap_line_delta=(
            args.prematch_feature_min_asian_handicap_line_delta
        ),
        prematch_feature_asian_handicap_line_movement_scale=(
            args.prematch_feature_asian_handicap_line_movement_scale
        ),
        prematch_feature_asian_handicap_line_movement_transform=(
            args.prematch_feature_asian_handicap_line_movement_transform
        ),
        prematch_feature_lineup_strength_weight=(
            args.prematch_feature_lineup_strength_weight
        ),
        prematch_feature_availability_risk_weight=(
            args.prematch_feature_availability_risk_weight
        ),
        prematch_feature_draw_risk_weight=args.prematch_feature_draw_risk_weight,
        prematch_feature_semantic_risk_weight=(
            args.prematch_feature_semantic_risk_weight
        ),
        max_prematch_feature_lambda_adjustment=(
            args.max_prematch_feature_lambda_adjustment
        ),
        allow_missing_prematch_feature_fallback=(
            args.allow_missing_prematch_feature_fallback
        ),
        require_feature_not_after_prediction=not args.allow_feature_after_prediction,
        require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
        model_version=args.model_version,
        feature_version=args.feature_version,
        calibration_version=args.calibration_version,
        prediction_sample_limit=args.prediction_sample_limit,
    )


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _feature_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _feature_list_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _feature_optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _feature_float(value: object) -> float:
    return _feature_optional_float(value) or 0.0


def _prematch_semantic_signal_name(signal: Mapping[str, object]) -> str:
    value = signal.get("signal_name")
    return value if isinstance(value, str) else ""


def _prematch_source_ref_count(source_refs: Mapping[str, object]) -> int:
    prematch_refs = _feature_mapping(source_refs.get("prematch"))
    if prematch_refs is None:
        return len(source_refs)
    count = 0
    for value in prematch_refs.values():
        if isinstance(value, list):
            count += len(value)
        elif value:
            count += 1
    return count


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline
