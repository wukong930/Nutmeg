from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from itertools import chain
from json import dumps
from math import log
from pathlib import Path
from re import search
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.parlay import AtomicBet, ParlayEvaluation
from nutmeg.market_resolver.settlement import (
    settle_cn_handicap_1x2,
    settle_european_handicap_1x2,
)
from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.competition_profiles import (
    default_competition_recommendation_profile_version,
)
from nutmeg.recommendations.final_arbitrator import (
    build_final_answer_arbitration_payload,
    rank_final_answer_options,
    score_final_answer_option,
)
from nutmeg.recommendations.global_planner import (
    RecommendationGlobalPlanOption,
    RecommendationPlanOptionType,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationMode,
    RecommendationPolicyConfig,
    RecommendationSelection,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.optimizer import (
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)
from nutmeg.recommendations.policy import (
    build_recommendation_policy_config,
    build_upset_focus_policy_config,
    candidate_min_data_quality_score,
    parse_pass_type_leg_count,
    rank_candidates,
)
from nutmeg.recommendations.upset_policy import analyze_candidate_upset_signal
from nutmeg.recommendations.upset_signal_calibration import (
    assess_upset_signal_calibration,
)

type HistoricalOutcome = Literal["home_win", "draw", "away_win"]
type HistoricalScenarioStatus = Literal["completed", "failed"]
type HistoricalOptimizerProfile = Literal["heuristic", "solver"]
type HistoricalFinalAnswerStakeEfficiencyScope = Literal[
    "all",
    "quality_signal_affected",
]

DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES = ("1x1", "2x1", "3x1", "4x1")
DEFAULT_HISTORICAL_BACKTEST_MODES: tuple[RecommendationMode, ...] = ("single", "multiple")
DEFAULT_HISTORICAL_BACKTEST_REQUESTED_BY = "historical-backtest-cli"


class HistoricalDynamicMixFinalAnswerLaneConstraintProfile(BaseModel):
    profile_key: str = ""
    pass_type: str
    mode: RecommendationMode | None = None
    constraint_profile_id: str = "default"
    constraint_profile_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketPrediction(BaseModel):
    market_type: RecommendationMarketType = "1x2"
    outcome: str
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float = Field(gt=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    model_edge: float | None = None
    data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    model_confidence_score: float = Field(default=0.70, ge=0.0, le=1.0)
    calibration_score: float = Field(default=0.70, ge=0.0, le=1.0)
    upset_protection_score: float = Field(default=0.0, ge=0.0, le=1.0)
    odds_stability_score: float = Field(default=0.70, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    line: float | None = None
    side: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFixture(BaseModel):
    fixture_id: str
    competition_id: str
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    prediction_time_utc: datetime
    model_version: str
    feature_version: str | None = None
    calibration_version: str | None = None
    predictions: list[HistoricalMarketPrediction] = Field(min_length=1)
    feature_snapshot: FeatureSnapshot | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)

    @property
    def actual_1x2_outcome(self) -> HistoricalOutcome:
        if self.actual_home_goals > self.actual_away_goals:
            return "home_win"
        if self.actual_home_goals < self.actual_away_goals:
            return "away_win"
        return "draw"


class HistoricalRecommendationSliceMetadata(BaseModel):
    slice_id: str
    name: str
    competition_id: str
    season: str | None = None
    result_source: str
    odds_source: str
    prediction_source: str
    source_urls: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalRecommendationSlice(BaseModel):
    metadata: HistoricalRecommendationSliceMetadata
    as_of_time_utc: datetime
    fixtures: list[HistoricalFixture] = Field(min_length=1)


class HistoricalRecommendationBacktestOptions(BaseModel):
    pass_types: tuple[str, ...] = DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES
    modes: tuple[RecommendationMode, ...] = DEFAULT_HISTORICAL_BACKTEST_MODES
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float = Field(default=20.0, gt=0.0)
    min_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    min_data_quality_score_by_competition_id: dict[str, float] = Field(
        default_factory=dict
    )
    data_quality_beta_lane_enabled: bool = False
    data_quality_beta_lane_competition_ids: tuple[str, ...] = ()
    data_quality_beta_lane_season_ids: tuple[str, ...] = ()
    data_quality_beta_lane_min_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    data_quality_beta_lane_max_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    data_quality_beta_lane_min_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    data_quality_beta_lane_max_decimal_odds: float | None = Field(default=None, gt=1.0)
    data_quality_beta_lane_min_model_edge: float | None = None
    data_quality_beta_lane_min_model_confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_min_calibration_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_min_odds_stability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_max_volatility_penalty: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_enabled: bool = False
    data_quality_beta_lane_probability_repair_strength: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_max_delta: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_min_market_probability_delta: float = (
        Field(default=0.0, ge=0.0, le=1.0)
    )
    data_quality_beta_lane_probability_repair_extra_uplift: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_data_quality_gap_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_odds_stability_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_probability_repair_max_probability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    allowed_markets: tuple[RecommendationMarketType, ...] = ("1x2",)
    require_odds: bool = True
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    upset_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    requested_by: str | None = DEFAULT_HISTORICAL_BACKTEST_REQUESTED_BY
    candidate_fixture_limit: int | None = Field(default=None, ge=1)
    max_candidates_per_fixture: int = Field(default=3, ge=1, le=8)
    scenario_candidate_fixture_buffer: int | None = Field(default=None, ge=0)
    final_answer_scenario_variant_count: int = Field(default=1, ge=1, le=8)
    derive_market_context_signals: bool = False
    upset_exposure_reserve: bool = False
    upset_exposure_reserve_fixture_count: int = Field(default=0, ge=0)
    upset_exposure_reserve_max_candidates_per_fixture: int = Field(default=1, ge=1, le=3)
    upset_exposure_reserve_min_protection_score: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
    )
    upset_exposure_reserve_min_probability: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
    )
    upset_exposure_reserve_max_decimal_odds: float | None = Field(default=None, gt=1.0)
    upset_final_answer_lane: bool = False
    upset_final_answer_lane_pass_type: str = "1x1"
    upset_final_answer_lane_mode: RecommendationMode = "single"
    upset_final_answer_lane_candidate_limit: int = Field(default=24, ge=1, le=128)
    upset_final_answer_lane_min_protection_score: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_min_probability: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_min_decimal_odds: float | None = Field(default=None, gt=1.0)
    upset_final_answer_lane_max_decimal_odds: float | None = Field(default=None, gt=1.0)
    upset_final_answer_lane_min_model_edge: float | None = None
    upset_final_answer_lane_max_model_edge: float | None = None
    upset_final_answer_lane_competition_ids: tuple[str, ...] = ()
    upset_final_answer_lane_excluded_competition_ids: tuple[str, ...] = ()
    upset_final_answer_lane_min_calibration_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_min_model_confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_min_odds_stability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_max_volatility_penalty: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_max_hit_probability_deficit: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_max_signal_calibration_risk: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_min_signal_reliability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    upset_final_answer_lane_score_boost: float = Field(default=0.0, ge=0.0, le=1.0)
    short_price_negative_edge_guardrail: bool = False
    short_price_negative_edge_max_decimal_odds: float = Field(default=1.35, gt=1.0)
    short_price_negative_edge_min_probability: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
    )
    short_price_negative_edge_max_model_edge: float = 0.0
    short_price_negative_edge_soft_penalty: bool = False
    short_price_negative_edge_soft_penalty_strength: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
    )
    short_price_negative_edge_soft_penalty_competition_ids: tuple[str, ...] = ()
    marginal_loss_driver_candidate_guardrail: bool = False
    marginal_loss_driver_candidate_guardrail_probability_min: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    marginal_loss_driver_candidate_guardrail_probability_max: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )
    marginal_loss_driver_candidate_guardrail_max_decimal_odds: float = Field(
        default=1.50,
        gt=1.0,
    )
    marginal_loss_driver_candidate_guardrail_max_model_edge: float = -0.02
    marginal_loss_driver_candidate_guardrail_max_calibration_score: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    marginal_loss_driver_candidate_guardrail_max_model_confidence_score: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    marginal_loss_driver_candidate_guardrail_max_odds_stability_score: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    marginal_loss_driver_candidate_guardrail_competition_ids: tuple[str, ...] = ()
    marginal_loss_driver_candidate_soft_penalty: bool = False
    marginal_loss_driver_candidate_soft_penalty_strength: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_penalty: bool = False
    final_answer_quality_signal_penalty_strength: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_probability_min: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_probability_max: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_min_decimal_odds: float = Field(default=1.0, ge=1.0)
    final_answer_quality_signal_max_decimal_odds: float = Field(default=1.35, gt=1.0)
    final_answer_quality_signal_max_model_edge: float = 0.0
    final_answer_quality_signal_score_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_score_max: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_quality_signal_competition_ids: tuple[str, ...] = ()
    final_answer_selection_value_signal: bool = False
    final_answer_selection_value_signal_strength: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
    )
    final_answer_selection_value_signal_probability_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_selection_value_signal_probability_max: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_selection_value_signal_min_decimal_odds: float = Field(
        default=1.0,
        ge=1.0,
    )
    final_answer_selection_value_signal_max_decimal_odds: float = Field(
        default=10.0,
        gt=1.0,
    )
    final_answer_selection_value_signal_max_model_edge: float | None = None
    final_answer_selection_value_signal_score_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_selection_value_signal_score_max: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    final_answer_selection_value_signal_competition_ids: tuple[str, ...] = ()
    final_answer_selection_value_signal_outcomes: tuple[str, ...] = ()
    final_answer_selection_value_signal_max_hit_probability_deficit: float | None = (
        Field(default=None, ge=0.0, le=1.0)
    )
    final_answer_selection_value_signal_min_option_roi: float | None = None
    final_answer_selection_value_signal_max_option_risk_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    final_answer_segment_penalty: bool = False
    final_answer_segment_penalty_strength: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
    )
    final_answer_segment_pass_types: tuple[str, ...] = ()
    final_answer_segment_modes: tuple[RecommendationMode, ...] = ()
    final_answer_segment_competition_ids: tuple[str, ...] = ()
    final_answer_segment_season_ids: tuple[str, ...] = ()
    final_answer_segment_min_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    final_answer_segment_max_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    final_answer_segment_min_hit_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    final_answer_segment_max_hit_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    final_answer_segment_min_odds_product: float | None = Field(default=None, gt=1.0)
    final_answer_segment_max_odds_product: float | None = Field(default=None, gt=1.0)
    final_answer_segment_min_average_leg_decimal_odds: float | None = Field(
        default=None,
        gt=1.0,
    )
    final_answer_segment_max_average_leg_decimal_odds: float | None = Field(
        default=None,
        gt=1.0,
    )
    final_answer_stake_efficiency_guard: bool = False
    final_answer_stake_efficiency_penalty_strength: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )
    final_answer_stake_efficiency_max_stake_multiplier: float = Field(
        default=2.0,
        ge=1.0,
    )
    final_answer_stake_efficiency_min_roi: float = 0.0
    final_answer_stake_efficiency_modes: tuple[RecommendationMode, ...] = ("multiple",)
    final_answer_stake_efficiency_scope: HistoricalFinalAnswerStakeEfficiencyScope = (
        "all"
    )
    dynamic_mix_final_answer_lane: bool = False
    dynamic_mix_final_answer_lane_pass_types: tuple[str, ...] = ("2x1",)
    dynamic_mix_final_answer_lane_mode: RecommendationMode = "single"
    dynamic_mix_final_answer_lane_modes: tuple[RecommendationMode, ...] = ()
    dynamic_mix_final_answer_lane_admitted_pass_types: tuple[str, ...] = ()
    dynamic_mix_final_answer_lane_blocked_pass_types: tuple[str, ...] = ()
    dynamic_mix_final_answer_lane_constraint_profiles: tuple[
        HistoricalDynamicMixFinalAnswerLaneConstraintProfile, ...
    ] = ()
    dynamic_mix_final_answer_lane_min_market_count: int = Field(default=2, ge=2, le=4)
    dynamic_mix_final_answer_lane_candidate_limit: int = Field(default=96, ge=1, le=512)
    dynamic_mix_final_answer_lane_solver_search: bool = False
    dynamic_mix_final_answer_lane_min_probability: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_score_boost: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_max_hit_probability_deficit: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_min_roi_delta: float | None = None
    correct_score_final_answer_lane: bool = False
    correct_score_final_answer_lane_pass_types: tuple[str, ...] = ("2x1",)
    correct_score_final_answer_lane_mode: RecommendationMode = "single"
    correct_score_final_answer_lane_modes: tuple[RecommendationMode, ...] = ()
    correct_score_final_answer_lane_candidate_limit: int = Field(
        default=96,
        ge=1,
        le=512,
    )
    correct_score_final_answer_lane_min_probability: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_min_correct_score_probability: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_max_correct_score_per_selection: int = Field(
        default=1,
        ge=1,
        le=3,
    )
    correct_score_final_answer_lane_score_boost: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_max_hit_probability_deficit: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_min_roi_delta: float | None = None
    correct_score_final_answer_lane_outcomes: tuple[str, ...] = ()
    competition_season_index_by_slice_id: dict[str, int] = Field(default_factory=dict)


class HistoricalRecommendationScenario(BaseModel):
    scenario_key: str
    pass_type: str
    mode: RecommendationMode
    constraint_profile_key: str | None = None
    constraint_profile_id: str | None = None
    constraint_profile_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationScenarioResult(BaseModel):
    scenario: HistoricalRecommendationScenario
    status: HistoricalScenarioStatus
    selected_fixture_ids: list[str] = Field(default_factory=list)
    selected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    total_stake: float = Field(default=0.0, ge=0.0)
    actual_return: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float = 0.0
    expected_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    actual_hit: bool = False
    calibration_error: float | None = Field(default=None, ge=0.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    captured_upset_fixture_ids: list[str] = Field(default_factory=list)
    selection_diagnostics_json: dict[str, object] = Field(default_factory=dict)
    option: RecommendationGlobalPlanOption | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalRecommendationBacktestResult(BaseModel):
    backtest_key: str
    slice_id: str
    as_of_time_utc: datetime
    fixture_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    scenario_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    final_answer: HistoricalRecommendationScenarioResult | None = None
    scenarios: list[HistoricalRecommendationScenarioResult] = Field(default_factory=list)
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(ge=0.0)
    actual_return: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    upset_opportunity_count: int = Field(ge=0)
    upset_capture_count: int = Field(ge=0)
    upset_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationBacktestComparisonResult(BaseModel):
    comparison_key: str
    slice_id: str
    baseline_optimizer_profile: HistoricalOptimizerProfile
    candidate_optimizer_profile: HistoricalOptimizerProfile
    status: str
    baseline: HistoricalRecommendationBacktestResult
    candidate: HistoricalRecommendationBacktestResult
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationBacktestSuiteResult(BaseModel):
    suite_key: str
    status: str
    slice_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    baseline_optimizer_profile: HistoricalOptimizerProfile
    candidate_optimizer_profile: HistoricalOptimizerProfile
    comparisons: list[HistoricalRecommendationBacktestComparisonResult] = Field(
        default_factory=list
    )
    aggregate_deltas_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_recommendation_slice(path: Path | str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice.model_validate_json(Path(path).read_text(encoding="utf-8"))


def run_historical_recommendation_backtest(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
) -> HistoricalRecommendationBacktestResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    fixtures = _eligible_fixtures(historical_slice)
    competition_season_index = resolved_options.competition_season_index_by_slice_id.get(
        historical_slice.metadata.slice_id
    )
    all_candidates = _candidates_from_fixtures(
        fixtures,
        season_id=historical_slice.metadata.season,
        competition_season_index=competition_season_index,
        derive_market_context_signals=resolved_options.derive_market_context_signals,
        short_price_negative_edge_guardrail=(resolved_options.short_price_negative_edge_guardrail),
        short_price_negative_edge_max_decimal_odds=(
            resolved_options.short_price_negative_edge_max_decimal_odds
        ),
        short_price_negative_edge_min_probability=(
            resolved_options.short_price_negative_edge_min_probability
        ),
        short_price_negative_edge_max_model_edge=(
            resolved_options.short_price_negative_edge_max_model_edge
        ),
        short_price_negative_edge_soft_penalty=(
            resolved_options.short_price_negative_edge_soft_penalty
        ),
        short_price_negative_edge_soft_penalty_strength=(
            resolved_options.short_price_negative_edge_soft_penalty_strength
        ),
        short_price_negative_edge_soft_penalty_competition_ids=(
            resolved_options.short_price_negative_edge_soft_penalty_competition_ids
        ),
        marginal_loss_driver_candidate_guardrail=(
            resolved_options.marginal_loss_driver_candidate_guardrail
        ),
        marginal_loss_driver_candidate_guardrail_probability_min=(
            resolved_options.marginal_loss_driver_candidate_guardrail_probability_min
        ),
        marginal_loss_driver_candidate_guardrail_probability_max=(
            resolved_options.marginal_loss_driver_candidate_guardrail_probability_max
        ),
        marginal_loss_driver_candidate_guardrail_max_decimal_odds=(
            resolved_options.marginal_loss_driver_candidate_guardrail_max_decimal_odds
        ),
        marginal_loss_driver_candidate_guardrail_max_model_edge=(
            resolved_options.marginal_loss_driver_candidate_guardrail_max_model_edge
        ),
        marginal_loss_driver_candidate_guardrail_max_calibration_score=(
            resolved_options.marginal_loss_driver_candidate_guardrail_max_calibration_score
        ),
        marginal_loss_driver_candidate_guardrail_max_model_confidence_score=(
            resolved_options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score
        ),
        marginal_loss_driver_candidate_guardrail_max_odds_stability_score=(
            resolved_options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score
        ),
        marginal_loss_driver_candidate_guardrail_competition_ids=(
            resolved_options.marginal_loss_driver_candidate_guardrail_competition_ids
        ),
        marginal_loss_driver_candidate_soft_penalty=(
            resolved_options.marginal_loss_driver_candidate_soft_penalty
        ),
        marginal_loss_driver_candidate_soft_penalty_strength=(
            resolved_options.marginal_loss_driver_candidate_soft_penalty_strength
        ),
    )
    short_price_negative_edge_guardrail_excluded_candidate_count = (
        _short_price_negative_edge_guardrail_excluded_prediction_count(
            fixtures,
            options=resolved_options,
        )
    )
    short_price_negative_edge_soft_penalty_candidate_count = (
        _short_price_negative_edge_soft_penalty_prediction_count(
            fixtures,
            options=resolved_options,
        )
    )
    marginal_loss_driver_candidate_guardrail_excluded_candidate_count = (
        _marginal_loss_driver_candidate_guardrail_excluded_prediction_count(
            fixtures,
            options=resolved_options,
        )
    )
    marginal_loss_driver_candidate_soft_penalty_candidate_count = (
        _marginal_loss_driver_candidate_soft_penalty_prediction_count(
            fixtures,
            options=resolved_options,
        )
    )
    policy_config = build_recommendation_policy_config(
        strategy=resolved_options.strategy,
        allowed_markets=resolved_options.allowed_markets,
        min_probability=resolved_options.min_probability,
        min_model_edge=resolved_options.min_model_edge,
        min_data_quality_score=resolved_options.min_data_quality_score,
        min_data_quality_score_by_competition_id=(
            resolved_options.min_data_quality_score_by_competition_id
        ),
        require_odds=resolved_options.require_odds,
        data_quality_beta_lane_enabled=resolved_options.data_quality_beta_lane_enabled,
        data_quality_beta_lane_competition_ids=(
            resolved_options.data_quality_beta_lane_competition_ids
        ),
        data_quality_beta_lane_season_ids=(
            resolved_options.data_quality_beta_lane_season_ids
        ),
        data_quality_beta_lane_min_competition_season_index=(
            resolved_options.data_quality_beta_lane_min_competition_season_index
        ),
        data_quality_beta_lane_max_competition_season_index=(
            resolved_options.data_quality_beta_lane_max_competition_season_index
        ),
        data_quality_beta_lane_min_probability=(
            resolved_options.data_quality_beta_lane_min_probability
        ),
        data_quality_beta_lane_max_decimal_odds=(
            resolved_options.data_quality_beta_lane_max_decimal_odds
        ),
        data_quality_beta_lane_min_model_edge=(
            resolved_options.data_quality_beta_lane_min_model_edge
        ),
        data_quality_beta_lane_min_model_confidence_score=(
            resolved_options.data_quality_beta_lane_min_model_confidence_score
        ),
        data_quality_beta_lane_min_calibration_score=(
            resolved_options.data_quality_beta_lane_min_calibration_score
        ),
        data_quality_beta_lane_min_odds_stability_score=(
            resolved_options.data_quality_beta_lane_min_odds_stability_score
        ),
        data_quality_beta_lane_max_volatility_penalty=(
            resolved_options.data_quality_beta_lane_max_volatility_penalty
        ),
    )
    all_candidates = _apply_data_quality_beta_lane_probability_repair(
        all_candidates,
        options=resolved_options,
        policy_config=policy_config,
    )
    candidates = _compress_candidate_pool(
        all_candidates,
        options=resolved_options,
        policy_config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    fixture_by_id = {fixture.fixture_id: fixture for fixture in fixtures}
    scenarios = _historical_scenarios(resolved_options)
    scenario_results = _run_historical_scenarios(
        scenarios,
        candidates=candidates,
        fixture_by_id=fixture_by_id,
        options=resolved_options,
        policy_config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    upset_lane_result = _run_historical_upset_final_answer_lane(
        candidates=all_candidates,
        fixture_by_id=fixture_by_id,
        options=resolved_options,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    if upset_lane_result is not None:
        scenario_results.append(upset_lane_result)
    scenario_results.extend(
        _run_historical_dynamic_mix_final_answer_lanes(
            candidates=all_candidates,
            fixture_by_id=fixture_by_id,
            options=resolved_options,
            policy_config=policy_config,
            as_of_time_utc=historical_slice.as_of_time_utc,
        )
    )
    scenario_results.extend(
        _run_historical_correct_score_final_answer_lanes(
            candidates=all_candidates,
            fixture_by_id=fixture_by_id,
            options=resolved_options,
            policy_config=policy_config,
            as_of_time_utc=historical_slice.as_of_time_utc,
        )
    )
    completed = [result for result in scenario_results if result.status == "completed"]
    ranked_options = _rank_historical_final_answer_options(
        [result.option for result in completed if result.option is not None],
        backtest_options=resolved_options,
    )
    final_answer = (
        _scenario_result_for_option(ranked_options[0], completed) if ranked_options else None
    )
    upset_opportunities = _upset_opportunity_fixture_ids(
        fixtures,
        threshold=resolved_options.upset_threshold,
        derive_market_context_signals=resolved_options.derive_market_context_signals,
    )
    upset_capture_count = (
        len(set(final_answer.captured_upset_fixture_ids).intersection(upset_opportunities))
        if final_answer is not None
        else 0
    )
    final_hit_sample_size = 1 if final_answer is not None else 0
    final_hit_count = 1 if final_answer is not None and final_answer.actual_hit else 0
    total_stake = final_answer.total_stake if final_answer is not None else 0.0
    actual_return = final_answer.actual_return if final_answer is not None else 0.0
    profit_loss = actual_return - total_stake
    summary = _summary_json(
        historical_slice,
        options=resolved_options,
        completed=completed,
        final_answer=final_answer,
        upset_opportunities=upset_opportunities,
        upset_capture_count=upset_capture_count,
        policy_config=policy_config,
        eligible_candidate_count=len(all_candidates),
        eligible_candidates=all_candidates,
        candidate_pool_count=len(candidates),
        candidate_pool_fixture_count=len({candidate.fixture_id for candidate in candidates}),
        candidate_pool_candidates=candidates,
        short_price_negative_edge_guardrail_excluded_candidate_count=(
            short_price_negative_edge_guardrail_excluded_candidate_count
        ),
        short_price_negative_edge_soft_penalty_candidate_count=(
            short_price_negative_edge_soft_penalty_candidate_count
        ),
        marginal_loss_driver_candidate_guardrail_excluded_candidate_count=(
            marginal_loss_driver_candidate_guardrail_excluded_candidate_count
        ),
        marginal_loss_driver_candidate_soft_penalty_candidate_count=(
            marginal_loss_driver_candidate_soft_penalty_candidate_count
        ),
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=_backtest_key(historical_slice, options=resolved_options),
        slice_id=historical_slice.metadata.slice_id,
        as_of_time_utc=_aware_utc(historical_slice.as_of_time_utc),
        fixture_count=len(fixtures),
        candidate_count=len(candidates),
        scenario_count=len(scenario_results),
        completed_count=len(completed),
        failed_count=len(scenario_results) - len(completed),
        final_answer=final_answer,
        scenarios=scenario_results,
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        final_hit_rate=_ratio(final_hit_count, final_hit_sample_size),
        total_stake=total_stake,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=(profit_loss / total_stake if total_stake > 0 else None),
        mean_calibration_error=(
            final_answer.calibration_error if final_answer is not None else None
        ),
        brier_score=final_answer.brier_score if final_answer is not None else None,
        log_loss=final_answer.log_loss if final_answer is not None else None,
        upset_opportunity_count=len(upset_opportunities),
        upset_capture_count=upset_capture_count,
        upset_capture_rate=_ratio(upset_capture_count, len(upset_opportunities)),
        warnings=_backtest_warnings(scenario_results, final_answer=final_answer),
        summary_json=summary,
    )


def run_historical_recommendation_backtest_comparison(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestComparisonResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    baseline = run_historical_recommendation_backtest(
        historical_slice,
        options=resolved_options.model_copy(
            update={"optimizer_profile": baseline_optimizer_profile}
        ),
    )
    candidate = run_historical_recommendation_backtest(
        historical_slice,
        options=resolved_options.model_copy(
            update={"optimizer_profile": candidate_optimizer_profile}
        ),
    )
    deltas = _comparison_deltas(baseline, candidate)
    status = _comparison_status(deltas)
    summary: dict[str, object] = {
        "calculation_basis": "historical_recommendation_backtest_comparison_v3_1",
        "slice_id": historical_slice.metadata.slice_id,
        "baseline_optimizer_profile": baseline_optimizer_profile,
        "candidate_optimizer_profile": candidate_optimizer_profile,
        "status": status,
        "baseline_backtest_key": baseline.backtest_key,
        "candidate_backtest_key": candidate.backtest_key,
        "baseline_final_answer_scenario_key": (
            baseline.final_answer.scenario.scenario_key
            if baseline.final_answer is not None
            else None
        ),
        "candidate_final_answer_scenario_key": (
            candidate.final_answer.scenario.scenario_key
            if candidate.final_answer is not None
            else None
        ),
        "baseline_final_answer_market_types": baseline.summary_json.get(
            "final_answer_market_types",
            [],
        ),
        "candidate_final_answer_market_types": candidate.summary_json.get(
            "final_answer_market_types",
            [],
        ),
        "baseline_final_answer_dynamic_mixed_market": baseline.summary_json.get(
            "final_answer_dynamic_mixed_market",
            False,
        ),
        "candidate_final_answer_dynamic_mixed_market": candidate.summary_json.get(
            "final_answer_dynamic_mixed_market",
            False,
        ),
        "baseline_final_answer_multiple_choice_fixture_count": (
            baseline.summary_json.get("final_answer_multiple_choice_fixture_count", 0)
        ),
        "candidate_final_answer_multiple_choice_fixture_count": (
            candidate.summary_json.get("final_answer_multiple_choice_fixture_count", 0)
        ),
        "final_answer_changed": _final_answer_signature(baseline.final_answer)
        != _final_answer_signature(candidate.final_answer),
        "deltas": deltas,
    }
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=_comparison_key(
            historical_slice,
            options=resolved_options,
            baseline_optimizer_profile=baseline_optimizer_profile,
            candidate_optimizer_profile=candidate_optimizer_profile,
        ),
        slice_id=historical_slice.metadata.slice_id,
        baseline_optimizer_profile=baseline_optimizer_profile,
        candidate_optimizer_profile=candidate_optimizer_profile,
        status=status,
        baseline=baseline,
        candidate=candidate,
        deltas_json=deltas,
        summary_json=summary,
    )


def run_historical_recommendation_backtest_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    suite_options = _options_with_competition_season_context(
        resolved_options,
        historical_slices,
    )
    comparisons = [
        run_historical_recommendation_backtest_comparison(
            historical_slice,
            options=suite_options,
            baseline_optimizer_profile=baseline_optimizer_profile,
            candidate_optimizer_profile=candidate_optimizer_profile,
        )
        for historical_slice in historical_slices
    ]
    aggregate_deltas = _suite_aggregate_deltas(comparisons)
    status = _comparison_status(aggregate_deltas) if comparisons else "insufficient_samples"
    summary = _suite_summary_json(
        historical_slices,
        comparisons=comparisons,
        aggregate_deltas=aggregate_deltas,
        status=status,
        baseline_optimizer_profile=baseline_optimizer_profile,
        candidate_optimizer_profile=candidate_optimizer_profile,
    )
    warnings = _suite_warnings(comparisons=comparisons, status=status)
    if not historical_slices:
        warnings.append("historical_suite_no_slices")
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=_suite_key(
            historical_slices,
            options=suite_options,
            baseline_optimizer_profile=baseline_optimizer_profile,
            candidate_optimizer_profile=candidate_optimizer_profile,
        ),
        status=status,
        slice_count=len(historical_slices),
        comparison_count=len(comparisons),
        baseline_optimizer_profile=baseline_optimizer_profile,
        candidate_optimizer_profile=candidate_optimizer_profile,
        comparisons=comparisons,
        aggregate_deltas_json=aggregate_deltas,
        warnings=warnings,
        summary_json=summary,
    )


def _options_with_competition_season_context(
    options: HistoricalRecommendationBacktestOptions,
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> HistoricalRecommendationBacktestOptions:
    if options.competition_season_index_by_slice_id:
        return options
    return options.model_copy(
        update={
            "competition_season_index_by_slice_id": (
                build_historical_competition_season_index_by_slice_id(
                    historical_slices
                )
            )
        }
    )


def build_historical_competition_season_index_by_slice_id(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, int]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    index_by_slice_id: dict[str, int] = {}
    for slices in grouped.values():
        ordered = sorted(slices, key=_competition_season_sort_key)
        season_index_by_key: dict[str, int] = {}
        for historical_slice in ordered:
            season_key = _competition_season_index_key(historical_slice)
            if season_key not in season_index_by_key:
                season_index_by_key[season_key] = len(season_index_by_key) + 1
            index_by_slice_id[historical_slice.metadata.slice_id] = (
                season_index_by_key[season_key]
            )
    return index_by_slice_id


def _competition_season_index_key(
    historical_slice: HistoricalRecommendationSlice,
) -> str:
    season = historical_slice.metadata.season
    if season:
        return season
    return f"slice:{historical_slice.metadata.slice_id}"


def _competition_season_sort_key(
    historical_slice: HistoricalRecommendationSlice,
) -> tuple[int, str]:
    return (
        _season_start_year(historical_slice.metadata.season)
        or _aware_utc(historical_slice.as_of_time_utc).year,
        historical_slice.metadata.slice_id,
    )


def _run_historical_scenario(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> HistoricalRecommendationScenarioResult:
    try:
        scenario_candidates = _scenario_candidate_pool(
            candidates,
            scenario=scenario,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        selection = _select_historical_selection(
            scenario,
            candidates=scenario_candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        settlement = _settle_selection(selection, fixture_by_id=fixture_by_id)
        captured_upsets = _captured_upset_fixture_ids(
            selection,
            fixture_by_id=fixture_by_id,
            threshold=options.upset_threshold,
        )
        option = _historical_plan_option(selection, scenario=scenario)
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="completed",
            selected_fixture_ids=selection.fixture_ids,
            selected_outcomes=_selected_outcomes(selection),
            total_stake=selection.evaluation.total_stake,
            actual_return=settlement.actual_return,
            profit_loss=settlement.profit_loss,
            roi=settlement.roi,
            expected_hit_probability=selection.evaluation.hit_probability,
            actual_hit=settlement.actual_hit,
            calibration_error=abs(
                selection.evaluation.hit_probability - float(settlement.actual_hit)
            ),
            brier_score=(selection.evaluation.hit_probability - float(settlement.actual_hit)) ** 2,
            log_loss=_binary_log_loss(
                selection.evaluation.hit_probability,
                actual_hit=settlement.actual_hit,
            ),
            captured_upset_fixture_ids=captured_upsets,
            selection_diagnostics_json=_selection_diagnostics(
                selection,
                optimizer_profile=options.optimizer_profile,
            ),
            option=option,
        )
    except ValueError as exc:
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="failed",
            error_message=str(exc),
            warnings=[str(exc)],
        )


def _run_historical_scenarios(
    scenarios: Sequence[HistoricalRecommendationScenario],
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[HistoricalRecommendationScenarioResult]:
    results: list[HistoricalRecommendationScenarioResult] = []
    for scenario in scenarios:
        base_result = _run_historical_scenario(
            scenario,
            candidates=candidates,
            fixture_by_id=fixture_by_id,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        results.append(base_result)
        if options.final_answer_scenario_variant_count <= 1:
            continue
        if base_result.status != "completed":
            continue
        excluded_fixture_ids = set(base_result.selected_fixture_ids)
        for variant_index in range(1, options.final_answer_scenario_variant_count):
            variant_candidates = [
                candidate
                for candidate in candidates
                if candidate.fixture_id not in excluded_fixture_ids
            ]
            variant_result = _run_historical_scenario(
                _historical_scenario_variant(
                    scenario,
                    variant_index=variant_index,
                ),
                candidates=variant_candidates,
                fixture_by_id=fixture_by_id,
                options=options,
                policy_config=policy_config,
                as_of_time_utc=as_of_time_utc,
            )
            variant_result = _with_scenario_variant_diagnostics(
                variant_result,
                base_scenario=scenario,
                variant_index=variant_index,
                excluded_fixture_ids=excluded_fixture_ids,
            )
            if variant_result.status != "completed":
                break
            results.append(variant_result)
            excluded_fixture_ids.update(variant_result.selected_fixture_ids)
    return results


def _historical_scenario_variant(
    scenario: HistoricalRecommendationScenario,
    *,
    variant_index: int,
) -> HistoricalRecommendationScenario:
    return HistoricalRecommendationScenario(
        scenario_key=f"{scenario.scenario_key}#variant{variant_index}",
        pass_type=scenario.pass_type,
        mode=scenario.mode,
    )


def _with_scenario_variant_diagnostics(
    result: HistoricalRecommendationScenarioResult,
    *,
    base_scenario: HistoricalRecommendationScenario,
    variant_index: int,
    excluded_fixture_ids: set[str],
) -> HistoricalRecommendationScenarioResult:
    diagnostics = {
        **result.selection_diagnostics_json,
        "scenario_variant": True,
        "base_scenario_key": base_scenario.scenario_key,
        "variant_index": variant_index,
        "excluded_fixture_ids": sorted(excluded_fixture_ids),
    }
    return result.model_copy(update={"selection_diagnostics_json": diagnostics})


def _run_historical_upset_final_answer_lane(
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> HistoricalRecommendationScenarioResult | None:
    if not options.upset_final_answer_lane:
        return None
    scenario = HistoricalRecommendationScenario(
        scenario_key=(
            "upset_lane:"
            f"{options.upset_final_answer_lane_pass_type}:"
            f"{options.upset_final_answer_lane_mode}"
        ),
        pass_type=options.upset_final_answer_lane_pass_type,
        mode=options.upset_final_answer_lane_mode,
    )
    try:
        lane_candidates = _upset_final_answer_lane_candidates(
            candidates,
            options=options,
            as_of_time_utc=as_of_time_utc,
        )
        if not lane_candidates:
            raise ValueError("upset_final_answer_lane_no_candidates")
        policy_config = build_upset_focus_policy_config(
            strategy=options.strategy,
            allowed_markets=options.allowed_markets,
            min_probability=options.upset_final_answer_lane_min_probability,
            min_model_edge=options.min_model_edge,
            min_data_quality_score=options.min_data_quality_score,
            min_data_quality_score_by_competition_id=(
                options.min_data_quality_score_by_competition_id
            ),
            require_odds=options.require_odds,
            data_quality_beta_lane_enabled=options.data_quality_beta_lane_enabled,
            data_quality_beta_lane_competition_ids=(
                options.data_quality_beta_lane_competition_ids
            ),
            data_quality_beta_lane_season_ids=options.data_quality_beta_lane_season_ids,
            data_quality_beta_lane_min_competition_season_index=(
                options.data_quality_beta_lane_min_competition_season_index
            ),
            data_quality_beta_lane_max_competition_season_index=(
                options.data_quality_beta_lane_max_competition_season_index
            ),
            data_quality_beta_lane_min_probability=(
                options.data_quality_beta_lane_min_probability
            ),
            data_quality_beta_lane_max_decimal_odds=(
                options.data_quality_beta_lane_max_decimal_odds
            ),
            data_quality_beta_lane_min_model_edge=(
                options.data_quality_beta_lane_min_model_edge
            ),
            data_quality_beta_lane_min_model_confidence_score=(
                options.data_quality_beta_lane_min_model_confidence_score
            ),
            data_quality_beta_lane_min_calibration_score=(
                options.data_quality_beta_lane_min_calibration_score
            ),
            data_quality_beta_lane_min_odds_stability_score=(
                options.data_quality_beta_lane_min_odds_stability_score
            ),
            data_quality_beta_lane_max_volatility_penalty=(
                options.data_quality_beta_lane_max_volatility_penalty
            ),
        )
        selection = _select_historical_selection(
            scenario,
            candidates=lane_candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        settlement = _settle_selection(selection, fixture_by_id=fixture_by_id)
        captured_upsets = _captured_upset_fixture_ids(
            selection,
            fixture_by_id=fixture_by_id,
            threshold=options.upset_threshold,
        )
        option = _historical_upset_lane_plan_option(
            selection,
            scenario=scenario,
            options=options,
            lane_candidate_count=len(lane_candidates),
        )
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="completed",
            selected_fixture_ids=selection.fixture_ids,
            selected_outcomes=_selected_outcomes(selection),
            total_stake=selection.evaluation.total_stake,
            actual_return=settlement.actual_return,
            profit_loss=settlement.profit_loss,
            roi=settlement.roi,
            expected_hit_probability=selection.evaluation.hit_probability,
            actual_hit=settlement.actual_hit,
            calibration_error=abs(
                selection.evaluation.hit_probability - float(settlement.actual_hit)
            ),
            brier_score=(selection.evaluation.hit_probability - float(settlement.actual_hit)) ** 2,
            log_loss=_binary_log_loss(
                selection.evaluation.hit_probability,
                actual_hit=settlement.actual_hit,
            ),
            captured_upset_fixture_ids=captured_upsets,
            selection_diagnostics_json={
                **_selection_diagnostics(
                    selection,
                    optimizer_profile=options.optimizer_profile,
                ),
                "upset_final_answer_lane": True,
                "lane_candidate_count": len(lane_candidates),
                "score_boost": options.upset_final_answer_lane_score_boost,
            },
            option=option,
        )
    except ValueError as exc:
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="failed",
            error_message=str(exc),
            warnings=[str(exc)],
        )


def _run_historical_dynamic_mix_final_answer_lanes(
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[HistoricalRecommendationScenarioResult]:
    if not options.dynamic_mix_final_answer_lane:
        return []
    return [
        _run_historical_dynamic_mix_final_answer_lane(
            scenario,
            candidates=candidates,
            fixture_by_id=fixture_by_id,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        for scenario in _dynamic_mix_final_answer_lane_scenarios(options)
    ]


def _dynamic_mix_final_answer_lane_scenarios(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[HistoricalRecommendationScenario, ...]:
    profiles = _dynamic_mix_final_answer_lane_effective_constraint_profiles(options)
    if profiles:
        return tuple(
            HistoricalRecommendationScenario(
                scenario_key=_dynamic_mix_final_answer_lane_scenario_key(
                    profile.pass_type,
                    mode=profile.mode or options.dynamic_mix_final_answer_lane_mode,
                    constraint_profile_key=profile.profile_key,
                ),
                pass_type=profile.pass_type,
                mode=profile.mode or options.dynamic_mix_final_answer_lane_mode,
                constraint_profile_key=profile.profile_key,
                constraint_profile_id=profile.constraint_profile_id,
                constraint_profile_json=dict(profile.constraint_profile_json),
            )
            for profile in profiles
        )
    return tuple(
        HistoricalRecommendationScenario(
            scenario_key=_dynamic_mix_final_answer_lane_scenario_key(pass_type, mode=mode),
            pass_type=pass_type,
            mode=mode,
        )
        for pass_type in _dynamic_mix_final_answer_lane_pass_types(options)
        for mode in _dynamic_mix_final_answer_lane_modes(options)
    )


def _dynamic_mix_final_answer_lane_scenario_key(
    pass_type: str,
    *,
    mode: RecommendationMode,
    constraint_profile_key: str | None = None,
) -> str:
    key = f"dynamic_mix_lane:{pass_type}:{mode}"
    if constraint_profile_key:
        return f"{key}:profile:{constraint_profile_key}"
    return key


def _run_historical_dynamic_mix_final_answer_lane(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> HistoricalRecommendationScenarioResult:
    try:
        selection = _select_dynamic_mix_final_answer_lane_selection(
            scenario,
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        settlement = _settle_selection(selection, fixture_by_id=fixture_by_id)
        captured_upsets = _captured_upset_fixture_ids(
            selection,
            fixture_by_id=fixture_by_id,
            threshold=options.upset_threshold,
        )
        option = _historical_dynamic_mix_lane_plan_option(
            selection,
            scenario=scenario,
            options=options,
        )
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="completed",
            selected_fixture_ids=selection.fixture_ids,
            selected_outcomes=_selected_outcomes(selection),
            total_stake=selection.evaluation.total_stake,
            actual_return=settlement.actual_return,
            profit_loss=settlement.profit_loss,
            roi=settlement.roi,
            expected_hit_probability=selection.evaluation.hit_probability,
            actual_hit=settlement.actual_hit,
            calibration_error=abs(
                selection.evaluation.hit_probability - float(settlement.actual_hit)
            ),
            brier_score=(selection.evaluation.hit_probability - float(settlement.actual_hit)) ** 2,
            log_loss=_binary_log_loss(
                selection.evaluation.hit_probability,
                actual_hit=settlement.actual_hit,
            ),
            captured_upset_fixture_ids=captured_upsets,
            selection_diagnostics_json={
                **_selection_diagnostics(
                    selection,
                    optimizer_profile=options.optimizer_profile,
                ),
                "dynamic_mix_final_answer_lane": True,
                "score_boost": options.dynamic_mix_final_answer_lane_score_boost,
            },
            option=option,
        )
    except ValueError as exc:
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="failed",
            error_message=str(exc),
            warnings=[str(exc)],
        )


def _dynamic_mix_final_answer_lane_modes(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[RecommendationMode, ...]:
    if options.dynamic_mix_final_answer_lane_modes:
        return options.dynamic_mix_final_answer_lane_modes
    return (options.dynamic_mix_final_answer_lane_mode,)


def _dynamic_mix_final_answer_lane_pass_types(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[str, ...]:
    profiles = _dynamic_mix_final_answer_lane_effective_constraint_profiles(options)
    if profiles:
        return _dedupe_tuple(profile.pass_type for profile in profiles)
    admitted = set(options.dynamic_mix_final_answer_lane_admitted_pass_types)
    blocked = set(options.dynamic_mix_final_answer_lane_blocked_pass_types)
    return tuple(
        pass_type
        for pass_type in options.dynamic_mix_final_answer_lane_pass_types
        if pass_type not in blocked and (not admitted or pass_type in admitted)
    )


def _dynamic_mix_final_answer_lane_effective_constraint_profiles(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[HistoricalDynamicMixFinalAnswerLaneConstraintProfile, ...]:
    requested_pass_types = set(options.dynamic_mix_final_answer_lane_pass_types)
    requested_modes = set(_dynamic_mix_final_answer_lane_modes(options))
    admitted_pass_types = set(options.dynamic_mix_final_answer_lane_admitted_pass_types)
    profiles: list[HistoricalDynamicMixFinalAnswerLaneConstraintProfile] = []
    seen: set[str] = set()
    for profile in options.dynamic_mix_final_answer_lane_constraint_profiles:
        if requested_pass_types and profile.pass_type not in requested_pass_types:
            continue
        if admitted_pass_types and profile.pass_type not in admitted_pass_types:
            continue
        if profile.mode is not None and profile.mode not in requested_modes:
            continue
        profile_key = profile.profile_key or _constraint_profile_key(profile)
        if profile_key in seen:
            continue
        seen.add(profile_key)
        profiles.append(profile.model_copy(update={"profile_key": profile_key}))
    return tuple(profiles)


def _constraint_profile_key(
    profile: HistoricalDynamicMixFinalAnswerLaneConstraintProfile,
) -> str:
    return (
        f"{profile.pass_type}:{profile.mode or 'any'}:"
        f"{profile.constraint_profile_id}"
    )


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return tuple(deduped)


def _dynamic_mix_final_answer_lane_max_outcomes_per_fixture(
    scenario: HistoricalRecommendationScenario,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> int:
    value = _constraint_profile_int(scenario, "max_outcomes_per_fixture")
    if value is None:
        return options.max_outcomes_per_fixture
    return max(1, min(3, value))


def _dynamic_mix_final_answer_lane_min_marginal_quality_gain(
    scenario: HistoricalRecommendationScenario,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> float:
    value = _constraint_profile_float(scenario, "min_marginal_quality_gain")
    if value is None:
        return options.min_marginal_quality_gain
    return value


def _constraint_profile_int(
    scenario: HistoricalRecommendationScenario,
    key: str,
) -> int | None:
    value = scenario.constraint_profile_json.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _constraint_profile_float(
    scenario: HistoricalRecommendationScenario,
    key: str,
) -> float | None:
    value = scenario.constraint_profile_json.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _dynamic_mix_final_answer_lane_constraint_profile_signature(
    options: HistoricalRecommendationBacktestOptions,
) -> str:
    if not options.dynamic_mix_final_answer_lane_constraint_profiles:
        return ""
    payload = [
        profile.model_dump(mode="json")
        for profile in options.dynamic_mix_final_answer_lane_constraint_profiles
    ]
    return dumps(payload, ensure_ascii=False, sort_keys=True)


def _dynamic_mix_final_answer_lane_solver_search(
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    return (
        options.dynamic_mix_final_answer_lane_solver_search
        and options.optimizer_profile == "solver"
    )


class _SelectionSettlement(BaseModel):
    actual_hit: bool
    actual_return: float = Field(ge=0.0)
    profit_loss: float
    roi: float


def _select_historical_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    if scenario.mode == "multiple":
        return select_budget_constrained_multiple_parlay(
            candidates,
            pass_type=scenario.pass_type,
            unit_stake=options.unit_stake,
            max_budget=options.max_budget,
            config=policy_config,
            as_of_time_utc=as_of_time_utc,
            max_outcomes_per_fixture=options.max_outcomes_per_fixture,
            min_marginal_quality_gain=options.min_marginal_quality_gain,
            enable_solver_search=options.optimizer_profile == "solver",
        )
    return select_budget_constrained_single_parlay(
        candidates,
        pass_type=scenario.pass_type,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
        min_quality_gain=options.min_marginal_quality_gain,
        enable_solver_search=options.optimizer_profile == "solver",
    )


class _DynamicMixProjection(BaseModel):
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    quality: float
    replaced_fixture_id: str | None = None
    replaced_market_type: str | None = None
    replacement_market_type: str | None = None

    @property
    def sort_key(self) -> tuple[float, float, float, float, float, str]:
        average_score = (
            sum(item.score for item in self.selected_scored) / len(self.selected_scored)
            if self.selected_scored
            else 0.0
        )
        market_part = ",".join(
            sorted({item.candidate.market_type for item in self.selected_scored})
        )
        return (
            self.quality,
            self.evaluation.hit_probability,
            self.evaluation.roi,
            average_score,
            -self.evaluation.total_stake,
            market_part,
        )


def _select_dynamic_mix_final_answer_lane_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    if scenario.mode == "single":
        return _select_dynamic_mix_final_answer_lane_single_selection(
            scenario,
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
    if scenario.mode == "multiple":
        return _select_dynamic_mix_final_answer_lane_multiple_selection(
            scenario,
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
    raise ValueError("dynamic_mix_final_answer_lane_unsupported_mode")


def _select_dynamic_mix_final_answer_lane_single_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    leg_count = parse_pass_type_leg_count(scenario.pass_type)
    if leg_count < 2:
        raise ValueError("dynamic_mix_final_answer_lane_requires_parlay_pass_type")
    lane_candidates = _dynamic_mix_final_answer_lane_candidates(
        candidates,
        options=options,
        policy_config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    if not lane_candidates:
        raise ValueError("dynamic_mix_final_answer_lane_no_candidates")
    base_selection = select_budget_constrained_single_parlay(
        lane_candidates,
        pass_type=scenario.pass_type,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
        min_quality_gain=_dynamic_mix_final_answer_lane_min_marginal_quality_gain(
            scenario,
            options=options,
        ),
        enable_solver_search=_dynamic_mix_final_answer_lane_solver_search(options),
    )
    ranked = rank_candidates(
        lane_candidates,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    candidate_by_identity = {
        _candidate_identity(scored.candidate): scored for scored in ranked
    }
    selected_scored = [
        candidate_by_identity[_candidate_identity(item.candidate)]
        for item in base_selection.selected_candidates
        if _candidate_identity(item.candidate) in candidate_by_identity
    ]
    if len(selected_scored) != leg_count:
        raise ValueError("dynamic_mix_final_answer_lane_base_selection_unavailable")
    base_market_types = _selected_market_types(selected_scored)
    projections: list[_DynamicMixProjection] = []
    if len(base_market_types) >= options.dynamic_mix_final_answer_lane_min_market_count:
        projections.append(
            _dynamic_mix_projection_from_scored(
                selected_scored,
                pass_type=scenario.pass_type,
                unit_stake=options.unit_stake,
                max_budget=options.max_budget,
            )
        )
    scored_by_fixture: dict[str, list[ScoredRecommendationCandidate]] = {}
    for scored in ranked:
        scored_by_fixture.setdefault(scored.candidate.fixture_id, []).append(scored)
    selected_fixture_ids = {item.candidate.fixture_id for item in selected_scored}
    selected_keys = {_candidate_identity(item.candidate) for item in selected_scored}
    for index, selected in enumerate(selected_scored):
        for replacement in scored_by_fixture.get(selected.candidate.fixture_id, []):
            if _candidate_identity(replacement.candidate) in selected_keys:
                continue
            candidate_scored = list(selected_scored)
            candidate_scored[index] = replacement
            projection = _dynamic_mix_projection_from_scored(
                candidate_scored,
                pass_type=scenario.pass_type,
                unit_stake=options.unit_stake,
                max_budget=options.max_budget,
                replaced_fixture_id=selected.candidate.fixture_id,
                replaced_market_type=selected.candidate.market_type,
                replacement_market_type=replacement.candidate.market_type,
            )
            if (
                len(_selected_market_types(candidate_scored))
                >= options.dynamic_mix_final_answer_lane_min_market_count
            ):
                projections.append(projection)
    for replacement in ranked:
        if replacement.candidate.fixture_id in selected_fixture_ids:
            continue
        if replacement.candidate.market_type in base_market_types and len(base_market_types) == 1:
            continue
        for index, selected in enumerate(selected_scored):
            candidate_scored = list(selected_scored)
            candidate_scored[index] = replacement
            if len({item.candidate.fixture_id for item in candidate_scored}) != leg_count:
                continue
            if (
                len(_selected_market_types(candidate_scored))
                < options.dynamic_mix_final_answer_lane_min_market_count
            ):
                continue
            projections.append(
                _dynamic_mix_projection_from_scored(
                    candidate_scored,
                    pass_type=scenario.pass_type,
                    unit_stake=options.unit_stake,
                    max_budget=options.max_budget,
                    replaced_fixture_id=selected.candidate.fixture_id,
                    replaced_market_type=selected.candidate.market_type,
                    replacement_market_type=replacement.candidate.market_type,
                )
            )
    valid_projections = [
        projection
        for projection in projections
        if projection.evaluation.rule_valid
        and _within_budget(projection.evaluation)
        and len(_selected_market_types(projection.selected_scored))
        >= options.dynamic_mix_final_answer_lane_min_market_count
    ]
    if not valid_projections:
        raise ValueError("dynamic_mix_final_answer_lane_no_valid_mixed_projection")
    best_projection = max(valid_projections, key=lambda projection: projection.sort_key)
    total_score = sum(item.score for item in best_projection.selected_scored) / len(
        best_projection.selected_scored
    )
    return RecommendationSelection(
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        selected_candidates=best_projection.selected_scored,
        evaluation=best_projection.evaluation,
        total_score=total_score,
        locked_fixture_ids=[],
        candidate_count=len(lane_candidates),
        excluded_candidate_count=max(0, len(candidates) - len(lane_candidates)),
        explanation_json={
            **base_selection.explanation_json,
            "selection_basis": "v3_1_dynamic_mix_final_answer_lane",
            "dynamic_mix_final_answer_lane": {
                "enabled": True,
                "base_fixture_ids": base_selection.fixture_ids,
                "base_market_types": sorted(base_market_types),
                "selected_market_types": sorted(
                    _selected_market_types(best_projection.selected_scored)
                ),
                "candidate_count": len(lane_candidates),
                "evaluated_projection_count": len(valid_projections),
                "quality_score": best_projection.quality,
                "replaced_fixture_id": best_projection.replaced_fixture_id,
                "replaced_market_type": best_projection.replaced_market_type,
                "replacement_market_type": best_projection.replacement_market_type,
                "score_boost": options.dynamic_mix_final_answer_lane_score_boost,
                "max_hit_probability_deficit": (
                    options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
                ),
                "min_roi_delta": options.dynamic_mix_final_answer_lane_min_roi_delta,
                "constraint_profile_key": scenario.constraint_profile_key,
                "constraint_profile_id": scenario.constraint_profile_id,
                "constraint_profile_json": scenario.constraint_profile_json,
                "min_marginal_quality_gain": (
                    _dynamic_mix_final_answer_lane_min_marginal_quality_gain(
                        scenario,
                        options=options,
                    )
                ),
            },
        },
    )


def _select_dynamic_mix_final_answer_lane_multiple_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    leg_count = parse_pass_type_leg_count(scenario.pass_type)
    if leg_count < 2:
        raise ValueError("dynamic_mix_final_answer_lane_requires_parlay_pass_type")
    lane_candidates = _dynamic_mix_final_answer_lane_candidates(
        candidates,
        options=options,
        policy_config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    if not lane_candidates:
        raise ValueError("dynamic_mix_final_answer_lane_no_candidates")
    base_selection = select_budget_constrained_multiple_parlay(
        lane_candidates,
        pass_type=scenario.pass_type,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
        max_outcomes_per_fixture=(
            _dynamic_mix_final_answer_lane_max_outcomes_per_fixture(
                scenario,
                options=options,
            )
        ),
        min_marginal_quality_gain=(
            _dynamic_mix_final_answer_lane_min_marginal_quality_gain(
                scenario,
                options=options,
            )
        ),
        enable_solver_search=_dynamic_mix_final_answer_lane_solver_search(options),
    )
    base_market_types = _selected_market_types(base_selection.selected_candidates)
    if (
        len(base_market_types) >= options.dynamic_mix_final_answer_lane_min_market_count
        and _within_budget(base_selection.evaluation)
    ):
        return _with_dynamic_mix_multiple_lane_explanation(
            base_selection,
            base_selection=base_selection,
            lane_candidate_count=len(lane_candidates),
            seed_selection=None,
            scenario=scenario,
            options=options,
        )

    seed_selection = _select_dynamic_mix_final_answer_lane_single_selection(
        scenario.model_copy(update={"mode": "single"}),
        candidates=candidates,
        options=options,
        policy_config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    locked_candidates = [item.candidate for item in seed_selection.selected_candidates]
    expanded_selection = select_budget_constrained_multiple_parlay(
        lane_candidates,
        pass_type=scenario.pass_type,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=locked_candidates,
        max_outcomes_per_fixture=(
            _dynamic_mix_final_answer_lane_max_outcomes_per_fixture(
                scenario,
                options=options,
            )
        ),
        min_marginal_quality_gain=(
            _dynamic_mix_final_answer_lane_min_marginal_quality_gain(
                scenario,
                options=options,
            )
        ),
        enable_solver_search=_dynamic_mix_final_answer_lane_solver_search(options),
    )
    if not _within_budget(expanded_selection.evaluation):
        raise ValueError("dynamic_mix_final_answer_lane_multiple_over_budget")
    if (
        len(_selected_market_types(expanded_selection.selected_candidates))
        < options.dynamic_mix_final_answer_lane_min_market_count
    ):
        raise ValueError("dynamic_mix_final_answer_lane_no_valid_mixed_projection")
    return _with_dynamic_mix_multiple_lane_explanation(
        expanded_selection,
        base_selection=base_selection,
        lane_candidate_count=len(lane_candidates),
        seed_selection=seed_selection,
        scenario=scenario,
        options=options,
    )


def _with_dynamic_mix_multiple_lane_explanation(
    selection: RecommendationSelection,
    *,
    base_selection: RecommendationSelection,
    lane_candidate_count: int,
    seed_selection: RecommendationSelection | None,
    scenario: HistoricalRecommendationScenario,
    options: HistoricalRecommendationBacktestOptions,
) -> RecommendationSelection:
    selected_market_types = _selected_market_types(selection.selected_candidates)
    seed_payload: dict[str, object] | None = None
    if seed_selection is not None:
        seed_payload = {
            "fixture_ids": seed_selection.fixture_ids,
            "market_types": sorted(
                _selected_market_types(seed_selection.selected_candidates)
            ),
            "hit_probability": seed_selection.evaluation.hit_probability,
            "roi": seed_selection.evaluation.roi,
        }
    return selection.model_copy(
        update={
            "explanation_json": {
                **selection.explanation_json,
                "selection_basis": "v3_1_dynamic_mix_final_answer_lane",
                "dynamic_mix_final_answer_lane": {
                    "enabled": True,
                    "mode": "multiple",
                    "base_fixture_ids": base_selection.fixture_ids,
                    "base_market_types": sorted(
                        _selected_market_types(base_selection.selected_candidates)
                    ),
                    "selected_market_types": sorted(selected_market_types),
                    "candidate_count": lane_candidate_count,
                    "seed_selection": seed_payload,
                    "score_boost": options.dynamic_mix_final_answer_lane_score_boost,
                    "max_hit_probability_deficit": (
                        options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
                    ),
                    "min_roi_delta": options.dynamic_mix_final_answer_lane_min_roi_delta,
                    "max_outcomes_per_fixture": (
                        _dynamic_mix_final_answer_lane_max_outcomes_per_fixture(
                            scenario,
                            options=options,
                        )
                    ),
                    "min_marginal_quality_gain": (
                        _dynamic_mix_final_answer_lane_min_marginal_quality_gain(
                            scenario,
                            options=options,
                        )
                    ),
                    "constraint_profile_key": scenario.constraint_profile_key,
                    "constraint_profile_id": scenario.constraint_profile_id,
                    "constraint_profile_json": scenario.constraint_profile_json,
                },
            }
        }
    )


def _dynamic_mix_projection_from_scored(
    selected_scored: Sequence[ScoredRecommendationCandidate],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float | None,
    replaced_fixture_id: str | None = None,
    replaced_market_type: str | None = None,
    replacement_market_type: str | None = None,
) -> _DynamicMixProjection:
    legs = [item.candidate.to_leg_selection() for item in selected_scored]
    evaluation = evaluate_parlay(
        legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
    )
    return _DynamicMixProjection(
        selected_scored=list(selected_scored),
        evaluation=evaluation,
        quality=_dynamic_mix_parlay_quality(evaluation, selected_scored),
        replaced_fixture_id=replaced_fixture_id,
        replaced_market_type=replaced_market_type,
        replacement_market_type=replacement_market_type,
    )


def _dynamic_mix_parlay_quality(
    evaluation: ParlayEvaluation,
    selected_candidates: Sequence[ScoredRecommendationCandidate],
) -> float:
    average_candidate_score = (
        sum(item.score for item in selected_candidates) / len(selected_candidates)
        if selected_candidates
        else 0.0
    )
    roi_component = _clamp(0.50 + evaluation.roi / 2.0)
    ev_component = _clamp(
        0.50 + evaluation.expected_value / max(evaluation.total_stake, 1.0) / 2.0
    )
    risk_component = 1.0 - evaluation.risk_score
    return _clamp(
        0.40 * evaluation.hit_probability
        + 0.25 * ev_component
        + 0.25 * average_candidate_score
        + 0.10 * roi_component
        + 0.05 * risk_component
    )


def _dynamic_mix_final_answer_lane_candidates(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    ranked = rank_candidates(
        [
            candidate
            for candidate in candidates
            if candidate.market_type in options.allowed_markets
            and candidate.probability >= options.dynamic_mix_final_answer_lane_min_probability
            and candidate.data_quality_score
            >= _candidate_min_data_quality_score(candidate, options)
        ],
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    return [
        scored.candidate
        for scored in ranked[: options.dynamic_mix_final_answer_lane_candidate_limit]
    ]


def _run_historical_correct_score_final_answer_lanes(
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[HistoricalRecommendationScenarioResult]:
    if not options.correct_score_final_answer_lane:
        return []
    return [
        _run_historical_correct_score_final_answer_lane(
            scenario,
            candidates=candidates,
            fixture_by_id=fixture_by_id,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        for scenario in _correct_score_final_answer_lane_scenarios(options)
    ]


def _correct_score_final_answer_lane_scenarios(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[HistoricalRecommendationScenario, ...]:
    return tuple(
        HistoricalRecommendationScenario(
            scenario_key=_correct_score_final_answer_lane_scenario_key(
                pass_type,
                mode=mode,
            ),
            pass_type=pass_type,
            mode=mode,
        )
        for pass_type in options.correct_score_final_answer_lane_pass_types
        for mode in _correct_score_final_answer_lane_modes(options)
    )


def _correct_score_final_answer_lane_scenario_key(
    pass_type: str,
    *,
    mode: RecommendationMode,
) -> str:
    return f"correct_score_lane:{pass_type}:{mode}"


def _correct_score_final_answer_lane_modes(
    options: HistoricalRecommendationBacktestOptions,
) -> tuple[RecommendationMode, ...]:
    if options.correct_score_final_answer_lane_modes:
        return options.correct_score_final_answer_lane_modes
    return (options.correct_score_final_answer_lane_mode,)


def _run_historical_correct_score_final_answer_lane(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    fixture_by_id: dict[str, HistoricalFixture],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> HistoricalRecommendationScenarioResult:
    try:
        selection = _select_correct_score_final_answer_lane_selection(
            scenario,
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        settlement = _settle_selection(selection, fixture_by_id=fixture_by_id)
        captured_upsets = _captured_upset_fixture_ids(
            selection,
            fixture_by_id=fixture_by_id,
            threshold=options.upset_threshold,
        )
        option = _historical_correct_score_lane_plan_option(
            selection,
            scenario=scenario,
            options=options,
        )
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="completed",
            selected_fixture_ids=selection.fixture_ids,
            selected_outcomes=_selected_outcomes(selection),
            total_stake=selection.evaluation.total_stake,
            actual_return=settlement.actual_return,
            profit_loss=settlement.profit_loss,
            roi=settlement.roi,
            expected_hit_probability=selection.evaluation.hit_probability,
            actual_hit=settlement.actual_hit,
            calibration_error=abs(
                selection.evaluation.hit_probability - float(settlement.actual_hit)
            ),
            brier_score=(selection.evaluation.hit_probability - float(settlement.actual_hit)) ** 2,
            log_loss=_binary_log_loss(
                selection.evaluation.hit_probability,
                actual_hit=settlement.actual_hit,
            ),
            captured_upset_fixture_ids=captured_upsets,
            selection_diagnostics_json={
                **_selection_diagnostics(
                    selection,
                    optimizer_profile=options.optimizer_profile,
                ),
                "correct_score_final_answer_lane": True,
                "score_boost": options.correct_score_final_answer_lane_score_boost,
            },
            option=option,
        )
    except ValueError as exc:
        return HistoricalRecommendationScenarioResult(
            scenario=scenario,
            status="failed",
            error_message=str(exc),
            warnings=[str(exc)],
        )


def _select_correct_score_final_answer_lane_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    if scenario.mode == "single":
        return _select_correct_score_final_answer_lane_single_selection(
            scenario,
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
    if scenario.mode == "multiple":
        seed_selection = _select_correct_score_final_answer_lane_single_selection(
            scenario.model_copy(update={"mode": "single"}),
            candidates=candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=as_of_time_utc,
        )
        return seed_selection.model_copy(
            update={
                "mode": "multiple",
                "explanation_json": {
                    **seed_selection.explanation_json,
                    "selection_basis": "v3_2_correct_score_final_answer_lane_seed",
                    "correct_score_final_answer_lane": {
                        **_correct_score_lane_explanation_payload(
                            options=options,
                            scenario=scenario,
                            lane_candidate_count=seed_selection.candidate_count,
                            evaluated_projection_count=0,
                            selected_correct_score_count=(
                                _selected_correct_score_count(
                                    seed_selection.selected_candidates
                                )
                            ),
                        ),
                        "multiple_mode_seed_only": True,
                    },
                },
            }
        )
    raise ValueError("correct_score_final_answer_lane_unsupported_mode")


def _select_correct_score_final_answer_lane_single_selection(
    scenario: HistoricalRecommendationScenario,
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> RecommendationSelection:
    leg_count = parse_pass_type_leg_count(scenario.pass_type)
    if leg_count < 2:
        raise ValueError("correct_score_final_answer_lane_requires_parlay_pass_type")
    lane_candidates = _correct_score_final_answer_lane_candidates(
        candidates,
        options=options,
        policy_config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    if not lane_candidates:
        raise ValueError("correct_score_final_answer_lane_no_candidates")
    lane_policy_config = _correct_score_final_answer_lane_policy_config(
        policy_config,
        options=options,
    )
    ranked = rank_candidates(
        lane_candidates,
        config=lane_policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    correct_score_ranked = [
        scored
        for scored in ranked
        if scored.candidate.market_type == "correct_score"
        and scored.candidate.effective_probability()
        >= options.correct_score_final_answer_lane_min_correct_score_probability
    ]
    if not correct_score_ranked:
        raise ValueError("correct_score_final_answer_lane_no_correct_score_candidate")
    projections: list[_DynamicMixProjection] = []
    max_correct_score_count = min(
        options.correct_score_final_answer_lane_max_correct_score_per_selection,
        leg_count,
    )
    for correct_score_scored in correct_score_ranked:
        selected_scored: list[ScoredRecommendationCandidate] = [correct_score_scored]
        selected_identities = {_candidate_identity(correct_score_scored.candidate)}
        selected_fixture_ids = {correct_score_scored.candidate.fixture_id}
        for scored in ranked:
            identity = _candidate_identity(scored.candidate)
            if identity in selected_identities:
                continue
            if scored.candidate.fixture_id in selected_fixture_ids:
                continue
            if (
                scored.candidate.market_type == "correct_score"
                and _selected_correct_score_count(selected_scored)
                >= max_correct_score_count
            ):
                continue
            selected_scored.append(scored)
            selected_identities.add(identity)
            selected_fixture_ids.add(scored.candidate.fixture_id)
            if len(selected_scored) == leg_count:
                break
        if len(selected_scored) != leg_count:
            continue
        projection = _dynamic_mix_projection_from_scored(
            selected_scored,
            pass_type=scenario.pass_type,
            unit_stake=options.unit_stake,
            max_budget=options.max_budget,
        )
        if (
            projection.evaluation.rule_valid
            and _within_budget(projection.evaluation)
            and 1
            <= _selected_correct_score_count(projection.selected_scored)
            <= max_correct_score_count
        ):
            projections.append(projection)
    if not projections:
        raise ValueError("correct_score_final_answer_lane_no_valid_projection")
    best_projection = max(
        projections,
        key=lambda projection: projection.sort_key,
    )
    total_score = sum(item.score for item in best_projection.selected_scored) / len(
        best_projection.selected_scored
    )
    return RecommendationSelection(
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        selected_candidates=best_projection.selected_scored,
        evaluation=best_projection.evaluation,
        total_score=total_score,
        locked_fixture_ids=[],
        candidate_count=len(lane_candidates),
        excluded_candidate_count=max(0, len(candidates) - len(lane_candidates)),
        explanation_json={
            "selection_basis": "v3_2_correct_score_final_answer_lane",
            "correct_score_final_answer_lane": _correct_score_lane_explanation_payload(
                options=options,
                scenario=scenario,
                lane_candidate_count=len(lane_candidates),
                evaluated_projection_count=len(projections),
                selected_correct_score_count=(
                    _selected_correct_score_count(best_projection.selected_scored)
                ),
            ),
        },
    )


def _correct_score_final_answer_lane_candidates(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    if "correct_score" not in set(options.allowed_markets):
        return []
    allowed_outcomes = set(options.correct_score_final_answer_lane_outcomes)
    filtered_candidates = [
        candidate
        for candidate in candidates
        if candidate.market_type in options.allowed_markets
        and candidate.data_quality_score
        >= _candidate_min_data_quality_score(candidate, options)
        and _correct_score_final_answer_lane_candidate_probability_ok(
            candidate,
            options=options,
        )
        and (
            candidate.market_type != "correct_score"
            or not allowed_outcomes
            or candidate.outcome in allowed_outcomes
        )
    ]
    lane_policy_config = _correct_score_final_answer_lane_policy_config(
        policy_config,
        options=options,
    )
    ranked = rank_candidates(
        filtered_candidates,
        config=lane_policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    limit = options.correct_score_final_answer_lane_candidate_limit
    selected = ranked[:limit]
    selected_identities = {_candidate_identity(scored.candidate) for scored in selected}
    if not any(scored.candidate.market_type == "correct_score" for scored in selected):
        first_correct_score = next(
            (
                scored
                for scored in ranked
                if scored.candidate.market_type == "correct_score"
            ),
            None,
        )
        if first_correct_score is not None:
            if len(selected) >= limit:
                selected = selected[: max(limit - 1, 0)]
            if _candidate_identity(first_correct_score.candidate) not in selected_identities:
                selected = [*selected, first_correct_score]
    return [scored.candidate for scored in selected]


def _correct_score_final_answer_lane_candidate_probability_ok(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    threshold = (
        options.correct_score_final_answer_lane_min_correct_score_probability
        if candidate.market_type == "correct_score"
        else options.correct_score_final_answer_lane_min_probability
    )
    return candidate.effective_probability() >= threshold


def _correct_score_final_answer_lane_policy_config(
    policy_config: RecommendationPolicyConfig,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> RecommendationPolicyConfig:
    return policy_config.model_copy(
        update={
            "min_probability": min(
                policy_config.min_probability,
                options.correct_score_final_answer_lane_min_probability,
                options.correct_score_final_answer_lane_min_correct_score_probability,
            )
        }
    )


def _correct_score_lane_explanation_payload(
    *,
    options: HistoricalRecommendationBacktestOptions,
    scenario: HistoricalRecommendationScenario,
    lane_candidate_count: int,
    evaluated_projection_count: int,
    selected_correct_score_count: int,
) -> dict[str, object]:
    return {
        "enabled": True,
        "pass_type": scenario.pass_type,
        "mode": scenario.mode,
        "candidate_count": lane_candidate_count,
        "evaluated_projection_count": evaluated_projection_count,
        "selected_correct_score_count": selected_correct_score_count,
        "candidate_limit": options.correct_score_final_answer_lane_candidate_limit,
        "min_probability": options.correct_score_final_answer_lane_min_probability,
        "min_correct_score_probability": (
            options.correct_score_final_answer_lane_min_correct_score_probability
        ),
        "max_correct_score_per_selection": (
            options.correct_score_final_answer_lane_max_correct_score_per_selection
        ),
        "score_boost": options.correct_score_final_answer_lane_score_boost,
        "max_hit_probability_deficit": (
            options.correct_score_final_answer_lane_max_hit_probability_deficit
        ),
        "min_roi_delta": options.correct_score_final_answer_lane_min_roi_delta,
        "outcomes": list(options.correct_score_final_answer_lane_outcomes),
    }


def _selected_correct_score_count(
    selected_scored: Sequence[ScoredRecommendationCandidate],
) -> int:
    return sum(
        1
        for item in selected_scored
        if item.candidate.market_type == "correct_score"
    )


def _selected_market_types(
    selected_scored: Sequence[ScoredRecommendationCandidate],
) -> set[str]:
    return {item.candidate.market_type for item in selected_scored}


def _settle_selection(
    selection: RecommendationSelection,
    *,
    fixture_by_id: dict[str, HistoricalFixture],
) -> _SelectionSettlement:
    actual_return = sum(
        _actual_return_for_atomic_bet(atomic_bet, fixture_by_id=fixture_by_id)
        for atomic_bet in selection.evaluation.atomic_bets
    )
    profit_loss = actual_return - selection.evaluation.total_stake
    return _SelectionSettlement(
        actual_hit=actual_return > 0,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=profit_loss / selection.evaluation.total_stake
        if selection.evaluation.total_stake > 0
        else 0.0,
    )


def _actual_return_for_atomic_bet(
    atomic_bet: AtomicBet,
    *,
    fixture_by_id: dict[str, HistoricalFixture],
) -> float:
    if all(
        _leg_matches_actual_outcome(
            fixture_by_id[leg.fixture_id],
            outcome=leg.outcome,
            market_type=leg.market_type,
            line=leg.line,
        )
        for leg in atomic_bet.legs
    ):
        return atomic_bet.stake * atomic_bet.odds_product
    return 0.0


def _leg_matches_actual_outcome(
    fixture: HistoricalFixture,
    *,
    outcome: str,
    market_type: str,
    line: float | None = None,
) -> bool:
    if market_type == "1x2":
        return outcome == fixture.actual_1x2_outcome
    if market_type == "cn_handicap_1x2":
        handicap = _integer_handicap_line(line)
        if handicap is None:
            return False
        return (
            outcome
            == settle_cn_handicap_1x2(
                fixture.actual_home_goals,
                fixture.actual_away_goals,
                handicap=handicap,
            ).value
        )
    if market_type == "european_handicap_1x2":
        handicap = _integer_handicap_line(line)
        if handicap is None:
            return False
        return (
            outcome
            == settle_european_handicap_1x2(
                fixture.actual_home_goals,
                fixture.actual_away_goals,
                handicap=handicap,
            ).value
        )
    if market_type == "correct_score":
        return outcome == f"{fixture.actual_home_goals}-{fixture.actual_away_goals}"
    return False


def _integer_handicap_line(line: float | None) -> int | None:
    if line is None:
        return None
    rounded = round(line)
    if abs(line - rounded) > 1e-9:
        return None
    return int(rounded)


def _historical_plan_option(
    selection: RecommendationSelection,
    *,
    scenario: HistoricalRecommendationScenario,
) -> RecommendationGlobalPlanOption:
    option_type = _option_type(selection)
    variant_index = _scenario_variant_index(scenario)
    option_key = f"historical:{option_type}:{scenario.pass_type}:{scenario.mode}"
    reason_codes = ["historical_backtest_candidate"]
    explanation_json: dict[str, object] = {
        "calculation_basis": "historical_recommendation_backtest_v3_1",
        "scenario_key": scenario.scenario_key,
    }
    if variant_index is not None:
        option_key = f"{option_key}:variant:{variant_index}"
        reason_codes.append("historical_backtest_shadow_variant")
        explanation_json["scenario_variant"] = {
            "enabled": True,
            "variant_index": variant_index,
            "base_scenario_key": scenario.scenario_key.split("#variant", maxsplit=1)[0],
        }
    return RecommendationGlobalPlanOption(
        option_key=option_key,
        option_type=option_type,
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        planner_score=selection.total_score,
        within_budget=_within_budget(selection.evaluation),
        selection=selection,
        reason_codes=reason_codes,
        explanation_json=explanation_json,
    )


def _scenario_variant_index(
    scenario: HistoricalRecommendationScenario,
) -> int | None:
    match = search(r"#variant(?P<index>\d+)$", scenario.scenario_key)
    if match is None:
        return None
    return int(match.group("index"))


def _historical_upset_lane_plan_option(
    selection: RecommendationSelection,
    *,
    scenario: HistoricalRecommendationScenario,
    options: HistoricalRecommendationBacktestOptions,
    lane_candidate_count: int,
) -> RecommendationGlobalPlanOption:
    option_type = _option_type(selection)
    return RecommendationGlobalPlanOption(
        option_key=(f"historical:upset_lane:{option_type}:{scenario.pass_type}:{scenario.mode}"),
        option_type=option_type,
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        planner_score=selection.total_score,
        within_budget=_within_budget(selection.evaluation),
        selection=selection,
        reason_codes=["historical_backtest_candidate", "upset_final_answer_lane"],
        explanation_json={
            "calculation_basis": "historical_recommendation_backtest_v3_1",
            "scenario_key": scenario.scenario_key,
            "upset_final_answer_lane": {
                "enabled": True,
                "candidate_count": lane_candidate_count,
                "score_boost": options.upset_final_answer_lane_score_boost,
                "min_protection_score": (options.upset_final_answer_lane_min_protection_score),
                "min_probability": options.upset_final_answer_lane_min_probability,
                "min_decimal_odds": options.upset_final_answer_lane_min_decimal_odds,
                "max_decimal_odds": options.upset_final_answer_lane_max_decimal_odds,
                "min_model_edge": options.upset_final_answer_lane_min_model_edge,
                "max_model_edge": options.upset_final_answer_lane_max_model_edge,
                "competition_ids": list(options.upset_final_answer_lane_competition_ids),
                "excluded_competition_ids": list(
                    options.upset_final_answer_lane_excluded_competition_ids
                ),
                "min_calibration_score": (options.upset_final_answer_lane_min_calibration_score),
                "min_model_confidence_score": (
                    options.upset_final_answer_lane_min_model_confidence_score
                ),
                "min_odds_stability_score": (
                    options.upset_final_answer_lane_min_odds_stability_score
                ),
                "max_volatility_penalty": (options.upset_final_answer_lane_max_volatility_penalty),
                "max_hit_probability_deficit": (
                    options.upset_final_answer_lane_max_hit_probability_deficit
                ),
                "max_signal_calibration_risk": (
                    options.upset_final_answer_lane_max_signal_calibration_risk
                ),
                "min_signal_reliability_score": (
                    options.upset_final_answer_lane_min_signal_reliability_score
                ),
            },
        },
    )


def _historical_dynamic_mix_lane_plan_option(
    selection: RecommendationSelection,
    *,
    scenario: HistoricalRecommendationScenario,
    options: HistoricalRecommendationBacktestOptions,
) -> RecommendationGlobalPlanOption:
    option_type = _option_type(selection)
    return RecommendationGlobalPlanOption(
        option_key=(
            "historical:dynamic_mix_lane:"
            f"{option_type}:{scenario.pass_type}:{scenario.mode}"
        ),
        option_type=option_type,
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        planner_score=selection.total_score,
        within_budget=_within_budget(selection.evaluation),
        selection=selection,
        reason_codes=[
            "historical_backtest_candidate",
            "dynamic_mix_final_answer_lane",
        ],
        explanation_json={
            "calculation_basis": "historical_recommendation_backtest_v3_1",
            "scenario_key": scenario.scenario_key,
            "dynamic_mix_final_answer_lane": {
                "enabled": True,
                "score_boost": options.dynamic_mix_final_answer_lane_score_boost,
                "min_market_count": options.dynamic_mix_final_answer_lane_min_market_count,
                "constraint_profile_key": scenario.constraint_profile_key,
                "constraint_profile_id": scenario.constraint_profile_id,
                "constraint_profile_json": scenario.constraint_profile_json,
                "max_hit_probability_deficit": (
                    options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
                ),
                "min_roi_delta": options.dynamic_mix_final_answer_lane_min_roi_delta,
            },
        },
    )


def _historical_correct_score_lane_plan_option(
    selection: RecommendationSelection,
    *,
    scenario: HistoricalRecommendationScenario,
    options: HistoricalRecommendationBacktestOptions,
) -> RecommendationGlobalPlanOption:
    option_type = _option_type(selection)
    return RecommendationGlobalPlanOption(
        option_key=(
            "historical:correct_score_lane:"
            f"{option_type}:{scenario.pass_type}:{scenario.mode}"
        ),
        option_type=option_type,
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        planner_score=selection.total_score,
        within_budget=_within_budget(selection.evaluation),
        selection=selection,
        reason_codes=[
            "historical_backtest_candidate",
            "correct_score_final_answer_lane",
        ],
        explanation_json={
            "calculation_basis": "historical_recommendation_backtest_v3_2",
            "scenario_key": scenario.scenario_key,
            "correct_score_final_answer_lane": {
                "enabled": True,
                "score_boost": options.correct_score_final_answer_lane_score_boost,
                "max_hit_probability_deficit": (
                    options.correct_score_final_answer_lane_max_hit_probability_deficit
                ),
                "min_roi_delta": options.correct_score_final_answer_lane_min_roi_delta,
                "max_correct_score_per_selection": (
                    options.correct_score_final_answer_lane_max_correct_score_per_selection
                ),
            },
        },
    )


def _eligible_fixtures(
    historical_slice: HistoricalRecommendationSlice,
) -> list[HistoricalFixture]:
    as_of_time = _aware_utc(historical_slice.as_of_time_utc)
    return [
        fixture
        for fixture in historical_slice.fixtures
        if _aware_utc(fixture.prediction_time_utc) <= as_of_time
        and _aware_utc(fixture.kickoff_time_utc) > as_of_time
    ]


def _candidates_from_fixtures(
    fixtures: Sequence[HistoricalFixture],
    *,
    season_id: str | None = None,
    competition_season_index: int | None = None,
    derive_market_context_signals: bool = False,
    short_price_negative_edge_guardrail: bool = False,
    short_price_negative_edge_max_decimal_odds: float = 1.35,
    short_price_negative_edge_min_probability: float = 0.70,
    short_price_negative_edge_max_model_edge: float = 0.0,
    short_price_negative_edge_soft_penalty: bool = False,
    short_price_negative_edge_soft_penalty_strength: float = 0.50,
    short_price_negative_edge_soft_penalty_competition_ids: tuple[str, ...] = (),
    marginal_loss_driver_candidate_guardrail: bool = False,
    marginal_loss_driver_candidate_guardrail_probability_min: float = 0.65,
    marginal_loss_driver_candidate_guardrail_probability_max: float = 0.80,
    marginal_loss_driver_candidate_guardrail_max_decimal_odds: float = 1.50,
    marginal_loss_driver_candidate_guardrail_max_model_edge: float = -0.02,
    marginal_loss_driver_candidate_guardrail_max_calibration_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_max_model_confidence_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_max_odds_stability_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_competition_ids: tuple[str, ...] = (),
    marginal_loss_driver_candidate_soft_penalty: bool = False,
    marginal_loss_driver_candidate_soft_penalty_strength: float = 0.20,
) -> list[RecommendationCandidate]:
    return list(
        chain.from_iterable(
            _candidates_from_fixture(
                fixture,
                season_id=season_id,
                competition_season_index=competition_season_index,
                derive_market_context_signals=derive_market_context_signals,
                short_price_negative_edge_guardrail=(short_price_negative_edge_guardrail),
                short_price_negative_edge_max_decimal_odds=(
                    short_price_negative_edge_max_decimal_odds
                ),
                short_price_negative_edge_min_probability=(
                    short_price_negative_edge_min_probability
                ),
                short_price_negative_edge_max_model_edge=(short_price_negative_edge_max_model_edge),
                short_price_negative_edge_soft_penalty=(short_price_negative_edge_soft_penalty),
                short_price_negative_edge_soft_penalty_strength=(
                    short_price_negative_edge_soft_penalty_strength
                ),
                short_price_negative_edge_soft_penalty_competition_ids=(
                    short_price_negative_edge_soft_penalty_competition_ids
                ),
                marginal_loss_driver_candidate_guardrail=(marginal_loss_driver_candidate_guardrail),
                marginal_loss_driver_candidate_guardrail_probability_min=(
                    marginal_loss_driver_candidate_guardrail_probability_min
                ),
                marginal_loss_driver_candidate_guardrail_probability_max=(
                    marginal_loss_driver_candidate_guardrail_probability_max
                ),
                marginal_loss_driver_candidate_guardrail_max_decimal_odds=(
                    marginal_loss_driver_candidate_guardrail_max_decimal_odds
                ),
                marginal_loss_driver_candidate_guardrail_max_model_edge=(
                    marginal_loss_driver_candidate_guardrail_max_model_edge
                ),
                marginal_loss_driver_candidate_guardrail_max_calibration_score=(
                    marginal_loss_driver_candidate_guardrail_max_calibration_score
                ),
                marginal_loss_driver_candidate_guardrail_max_model_confidence_score=(
                    marginal_loss_driver_candidate_guardrail_max_model_confidence_score
                ),
                marginal_loss_driver_candidate_guardrail_max_odds_stability_score=(
                    marginal_loss_driver_candidate_guardrail_max_odds_stability_score
                ),
                marginal_loss_driver_candidate_guardrail_competition_ids=(
                    marginal_loss_driver_candidate_guardrail_competition_ids
                ),
                marginal_loss_driver_candidate_soft_penalty=(
                    marginal_loss_driver_candidate_soft_penalty
                ),
                marginal_loss_driver_candidate_soft_penalty_strength=(
                    marginal_loss_driver_candidate_soft_penalty_strength
                ),
            )
            for fixture in fixtures
        )
    )


def _candidates_from_fixture(
    fixture: HistoricalFixture,
    *,
    season_id: str | None = None,
    competition_season_index: int | None = None,
    derive_market_context_signals: bool = False,
    short_price_negative_edge_guardrail: bool = False,
    short_price_negative_edge_max_decimal_odds: float = 1.35,
    short_price_negative_edge_min_probability: float = 0.70,
    short_price_negative_edge_max_model_edge: float = 0.0,
    short_price_negative_edge_soft_penalty: bool = False,
    short_price_negative_edge_soft_penalty_strength: float = 0.50,
    short_price_negative_edge_soft_penalty_competition_ids: tuple[str, ...] = (),
    marginal_loss_driver_candidate_guardrail: bool = False,
    marginal_loss_driver_candidate_guardrail_probability_min: float = 0.65,
    marginal_loss_driver_candidate_guardrail_probability_max: float = 0.80,
    marginal_loss_driver_candidate_guardrail_max_decimal_odds: float = 1.50,
    marginal_loss_driver_candidate_guardrail_max_model_edge: float = -0.02,
    marginal_loss_driver_candidate_guardrail_max_calibration_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_max_model_confidence_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_max_odds_stability_score: float | None = None,
    marginal_loss_driver_candidate_guardrail_competition_ids: tuple[str, ...] = (),
    marginal_loss_driver_candidate_soft_penalty: bool = False,
    marginal_loss_driver_candidate_soft_penalty_strength: float = 0.20,
) -> list[RecommendationCandidate]:
    market_context_by_outcome = (
        _fixture_market_context_metadata(fixture) if derive_market_context_signals else {}
    )
    resolved_season_id = season_id or _fixture_season_id(fixture)
    season_metadata: dict[str, object] = (
        {"season_id": resolved_season_id} if resolved_season_id else {}
    )
    if competition_season_index is not None:
        season_metadata["competition_season_index"] = competition_season_index
        season_metadata["prior_competition_season_count"] = (
            competition_season_index - 1
        )
    season_start_year = _season_start_year(resolved_season_id)
    if season_start_year is not None:
        season_metadata["season_start_year"] = season_start_year
    candidates: list[RecommendationCandidate] = []
    for prediction in fixture.predictions:
        if _short_price_negative_edge_guardrail_applies(
            fixture,
            prediction=prediction,
            enabled=short_price_negative_edge_guardrail,
            max_decimal_odds=short_price_negative_edge_max_decimal_odds,
            min_probability=short_price_negative_edge_min_probability,
            max_model_edge=short_price_negative_edge_max_model_edge,
        ):
            continue
        if _marginal_loss_driver_candidate_guardrail_applies(
            fixture,
            prediction=prediction,
            enabled=marginal_loss_driver_candidate_guardrail,
            probability_min=marginal_loss_driver_candidate_guardrail_probability_min,
            probability_max=marginal_loss_driver_candidate_guardrail_probability_max,
            max_decimal_odds=marginal_loss_driver_candidate_guardrail_max_decimal_odds,
            max_model_edge=marginal_loss_driver_candidate_guardrail_max_model_edge,
            max_calibration_score=(marginal_loss_driver_candidate_guardrail_max_calibration_score),
            max_model_confidence_score=(
                marginal_loss_driver_candidate_guardrail_max_model_confidence_score
            ),
            max_odds_stability_score=(
                marginal_loss_driver_candidate_guardrail_max_odds_stability_score
            ),
            competition_ids=marginal_loss_driver_candidate_guardrail_competition_ids,
        ):
            continue
        context_metadata = market_context_by_outcome.get(prediction.outcome, {})
        candidate_metadata = {
            **prediction.metadata_json,
            **context_metadata,
        }
        soft_penalty_metadata = _short_price_negative_edge_soft_penalty_metadata(
            fixture,
            prediction=prediction,
            candidate_metadata=candidate_metadata,
            enabled=short_price_negative_edge_soft_penalty,
            max_decimal_odds=short_price_negative_edge_max_decimal_odds,
            min_probability=short_price_negative_edge_min_probability,
            max_model_edge=short_price_negative_edge_max_model_edge,
            strength=short_price_negative_edge_soft_penalty_strength,
            competition_ids=short_price_negative_edge_soft_penalty_competition_ids,
        )
        loss_driver_soft_penalty_metadata = _marginal_loss_driver_candidate_soft_penalty_metadata(
            fixture,
            prediction=prediction,
            candidate_metadata={
                **candidate_metadata,
                **soft_penalty_metadata,
            },
            enabled=marginal_loss_driver_candidate_soft_penalty,
            probability_min=(marginal_loss_driver_candidate_guardrail_probability_min),
            probability_max=(marginal_loss_driver_candidate_guardrail_probability_max),
            max_decimal_odds=(marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            max_model_edge=marginal_loss_driver_candidate_guardrail_max_model_edge,
            max_calibration_score=(marginal_loss_driver_candidate_guardrail_max_calibration_score),
            max_model_confidence_score=(
                marginal_loss_driver_candidate_guardrail_max_model_confidence_score
            ),
            max_odds_stability_score=(
                marginal_loss_driver_candidate_guardrail_max_odds_stability_score
            ),
            strength=marginal_loss_driver_candidate_soft_penalty_strength,
            competition_ids=marginal_loss_driver_candidate_guardrail_competition_ids,
        )
        candidates.append(
            RecommendationCandidate(
                fixture_id=fixture.fixture_id,
                market_type=prediction.market_type,
                outcome=prediction.outcome,
                probability=prediction.probability,
                decimal_odds=prediction.decimal_odds,
                market_probability=prediction.market_probability,
                model_edge=prediction.model_edge,
                data_quality_score=prediction.data_quality_score,
                model_confidence_score=prediction.model_confidence_score,
                calibration_score=prediction.calibration_score,
                upset_protection_score=prediction.upset_protection_score,
                odds_stability_score=prediction.odds_stability_score,
                volatility_penalty=prediction.volatility_penalty,
                line=prediction.line,
                side=prediction.side,
                candidate_id=(
                    f"{fixture.fixture_id}:{prediction.market_type}:"
                    f"{prediction.line}:{prediction.side}:{prediction.outcome}"
                ),
                model_version=fixture.model_version,
                prediction_time_utc=fixture.prediction_time_utc,
                kickoff_time_utc=fixture.kickoff_time_utc,
                correlation_key=_prediction_correlation_key(
                    fixture,
                    outcome=prediction.outcome,
                    market_type=prediction.market_type,
                ),
                metadata_json={
                    **candidate_metadata,
                    **soft_penalty_metadata,
                    **loss_driver_soft_penalty_metadata,
                    **season_metadata,
                    "source": "historical_recommendation_slice",
                    "competition_id": fixture.competition_id,
                    "home_team_name": fixture.home_team_name,
                    "away_team_name": fixture.away_team_name,
                    "actual_1x2_outcome": fixture.actual_1x2_outcome,
                },
            )
        )
    return candidates


def _short_price_negative_edge_guardrail_excluded_prediction_count(
    fixtures: Sequence[HistoricalFixture],
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> int:
    if not options.short_price_negative_edge_guardrail:
        return 0
    return sum(
        1
        for fixture in fixtures
        for prediction in fixture.predictions
        if _short_price_negative_edge_guardrail_applies(
            fixture,
            prediction=prediction,
            enabled=True,
            max_decimal_odds=options.short_price_negative_edge_max_decimal_odds,
            min_probability=options.short_price_negative_edge_min_probability,
            max_model_edge=options.short_price_negative_edge_max_model_edge,
        )
    )


def _short_price_negative_edge_soft_penalty_prediction_count(
    fixtures: Sequence[HistoricalFixture],
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> int:
    if not options.short_price_negative_edge_soft_penalty:
        return 0
    return sum(
        1
        for fixture in fixtures
        for prediction in fixture.predictions
        if _short_price_negative_edge_soft_penalty_applies(
            fixture,
            prediction=prediction,
            enabled=True,
            max_decimal_odds=options.short_price_negative_edge_max_decimal_odds,
            min_probability=options.short_price_negative_edge_min_probability,
            max_model_edge=options.short_price_negative_edge_max_model_edge,
            competition_ids=(options.short_price_negative_edge_soft_penalty_competition_ids),
        )
    )


def _marginal_loss_driver_candidate_guardrail_excluded_prediction_count(
    fixtures: Sequence[HistoricalFixture],
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> int:
    if not options.marginal_loss_driver_candidate_guardrail:
        return 0
    return sum(
        1
        for fixture in fixtures
        for prediction in fixture.predictions
        if _marginal_loss_driver_candidate_guardrail_applies(
            fixture,
            prediction=prediction,
            enabled=True,
            probability_min=(options.marginal_loss_driver_candidate_guardrail_probability_min),
            probability_max=(options.marginal_loss_driver_candidate_guardrail_probability_max),
            max_decimal_odds=(options.marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            max_model_edge=(options.marginal_loss_driver_candidate_guardrail_max_model_edge),
            max_calibration_score=(
                options.marginal_loss_driver_candidate_guardrail_max_calibration_score
            ),
            max_model_confidence_score=(
                options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score
            ),
            max_odds_stability_score=(
                options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score
            ),
            competition_ids=(options.marginal_loss_driver_candidate_guardrail_competition_ids),
        )
    )


def _marginal_loss_driver_candidate_soft_penalty_prediction_count(
    fixtures: Sequence[HistoricalFixture],
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> int:
    if not options.marginal_loss_driver_candidate_soft_penalty:
        return 0
    return sum(
        1
        for fixture in fixtures
        for prediction in fixture.predictions
        if _marginal_loss_driver_candidate_soft_penalty_applies(
            fixture,
            prediction=prediction,
            enabled=True,
            probability_min=(options.marginal_loss_driver_candidate_guardrail_probability_min),
            probability_max=(options.marginal_loss_driver_candidate_guardrail_probability_max),
            max_decimal_odds=(options.marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            max_model_edge=(options.marginal_loss_driver_candidate_guardrail_max_model_edge),
            max_calibration_score=(
                options.marginal_loss_driver_candidate_guardrail_max_calibration_score
            ),
            max_model_confidence_score=(
                options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score
            ),
            max_odds_stability_score=(
                options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score
            ),
            competition_ids=(options.marginal_loss_driver_candidate_guardrail_competition_ids),
        )
    )


def _short_price_negative_edge_guardrail_applies(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    enabled: bool,
    max_decimal_odds: float,
    min_probability: float,
    max_model_edge: float,
) -> bool:
    if not enabled:
        return False
    if prediction.market_type != "1x2":
        return False
    favorite = _fixture_market_favorite_prediction(fixture)
    if favorite is None or favorite.outcome != prediction.outcome:
        return False
    if prediction.decimal_odds > max_decimal_odds:
        return False
    if prediction.probability < min_probability:
        return False
    return _prediction_model_edge(prediction) < max_model_edge


def _short_price_negative_edge_soft_penalty_applies(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    enabled: bool,
    max_decimal_odds: float,
    min_probability: float,
    max_model_edge: float,
    competition_ids: tuple[str, ...],
) -> bool:
    if competition_ids and fixture.competition_id not in set(competition_ids):
        return False
    return _short_price_negative_edge_guardrail_applies(
        fixture,
        prediction=prediction,
        enabled=enabled,
        max_decimal_odds=max_decimal_odds,
        min_probability=min_probability,
        max_model_edge=max_model_edge,
    )


def _marginal_loss_driver_candidate_guardrail_applies(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    enabled: bool,
    probability_min: float,
    probability_max: float,
    max_decimal_odds: float,
    max_model_edge: float,
    max_calibration_score: float | None,
    max_model_confidence_score: float | None,
    max_odds_stability_score: float | None,
    competition_ids: tuple[str, ...],
) -> bool:
    if not enabled:
        return False
    if competition_ids and fixture.competition_id not in set(competition_ids):
        return False
    if prediction.market_type != "1x2":
        return False
    if prediction.decimal_odds > max_decimal_odds:
        return False
    if prediction.probability < probability_min:
        return False
    if prediction.probability >= probability_max:
        return False
    if max_calibration_score is not None and prediction.calibration_score > max_calibration_score:
        return False
    if (
        max_model_confidence_score is not None
        and prediction.model_confidence_score > max_model_confidence_score
    ):
        return False
    if (
        max_odds_stability_score is not None
        and prediction.odds_stability_score > max_odds_stability_score
    ):
        return False
    return _prediction_model_edge(prediction) < max_model_edge


def _marginal_loss_driver_candidate_soft_penalty_applies(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    enabled: bool,
    probability_min: float,
    probability_max: float,
    max_decimal_odds: float,
    max_model_edge: float,
    max_calibration_score: float | None,
    max_model_confidence_score: float | None,
    max_odds_stability_score: float | None,
    competition_ids: tuple[str, ...],
) -> bool:
    return _marginal_loss_driver_candidate_guardrail_applies(
        fixture,
        prediction=prediction,
        enabled=enabled,
        probability_min=probability_min,
        probability_max=probability_max,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        max_calibration_score=max_calibration_score,
        max_model_confidence_score=max_model_confidence_score,
        max_odds_stability_score=max_odds_stability_score,
        competition_ids=competition_ids,
    )


def _short_price_negative_edge_soft_penalty_metadata(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    candidate_metadata: dict[str, object],
    enabled: bool,
    max_decimal_odds: float,
    min_probability: float,
    max_model_edge: float,
    strength: float,
    competition_ids: tuple[str, ...],
) -> dict[str, object]:
    if not _short_price_negative_edge_soft_penalty_applies(
        fixture,
        prediction=prediction,
        enabled=enabled,
        max_decimal_odds=max_decimal_odds,
        min_probability=min_probability,
        max_model_edge=max_model_edge,
        competition_ids=competition_ids,
    ):
        return {}
    penalty_score = _short_price_negative_edge_soft_penalty_score(
        prediction,
        max_decimal_odds=max_decimal_odds,
        min_probability=min_probability,
        max_model_edge=max_model_edge,
        strength=strength,
    )
    existing_fragility = _metadata_score(candidate_metadata, "favorite_fragility_score")
    return {
        "short_price_negative_edge_soft_penalty_basis": (
            "historical_short_price_negative_edge_soft_penalty_v3_1"
        ),
        "short_price_negative_edge_soft_penalty_score": round(penalty_score, 4),
        "short_price_negative_edge_soft_penalty_strength": round(strength, 4),
        "favorite_fragility_score": max(existing_fragility, round(penalty_score, 4)),
    }


def _short_price_negative_edge_soft_penalty_score(
    prediction: HistoricalMarketPrediction,
    *,
    max_decimal_odds: float,
    min_probability: float,
    max_model_edge: float,
    strength: float,
) -> float:
    edge_pressure = _clamp((max_model_edge - _prediction_model_edge(prediction)) / 0.12)
    price_pressure = _clamp(
        (max_decimal_odds - prediction.decimal_odds) / max(max_decimal_odds - 1.0, 0.01)
    )
    probability_pressure = _clamp(
        (prediction.probability - min_probability) / max(1.0 - min_probability, 0.01)
    )
    return _clamp(
        strength * (0.50 * edge_pressure + 0.30 * price_pressure + 0.20 * probability_pressure)
    )


def _marginal_loss_driver_candidate_soft_penalty_metadata(
    fixture: HistoricalFixture,
    *,
    prediction: HistoricalMarketPrediction,
    candidate_metadata: dict[str, object],
    enabled: bool,
    probability_min: float,
    probability_max: float,
    max_decimal_odds: float,
    max_model_edge: float,
    max_calibration_score: float | None,
    max_model_confidence_score: float | None,
    max_odds_stability_score: float | None,
    strength: float,
    competition_ids: tuple[str, ...],
) -> dict[str, object]:
    if not _marginal_loss_driver_candidate_soft_penalty_applies(
        fixture,
        prediction=prediction,
        enabled=enabled,
        probability_min=probability_min,
        probability_max=probability_max,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        max_calibration_score=max_calibration_score,
        max_model_confidence_score=max_model_confidence_score,
        max_odds_stability_score=max_odds_stability_score,
        competition_ids=competition_ids,
    ):
        return {}
    penalty_score = _marginal_loss_driver_candidate_soft_penalty_score(
        prediction,
        probability_min=probability_min,
        probability_max=probability_max,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        strength=strength,
    )
    existing_fragility = _metadata_score(candidate_metadata, "favorite_fragility_score")
    existing_score_penalty = _metadata_score(
        candidate_metadata,
        "internal_candidate_score_penalty",
    )
    return {
        "marginal_loss_driver_candidate_soft_penalty_basis": (
            "historical_marginal_loss_driver_candidate_soft_penalty_v3_1"
        ),
        "marginal_loss_driver_candidate_soft_penalty_score": round(
            penalty_score,
            4,
        ),
        "marginal_loss_driver_candidate_soft_penalty_strength": round(strength, 4),
        "internal_candidate_score_penalty": max(
            existing_score_penalty,
            round(penalty_score, 4),
        ),
        "favorite_fragility_score": max(existing_fragility, round(penalty_score, 4)),
    }


def _marginal_loss_driver_candidate_soft_penalty_score(
    prediction: HistoricalMarketPrediction,
    *,
    probability_min: float,
    probability_max: float,
    max_decimal_odds: float,
    max_model_edge: float,
    strength: float,
) -> float:
    edge_pressure = _clamp((max_model_edge - _prediction_model_edge(prediction)) / 0.12)
    price_pressure = _clamp(
        (max_decimal_odds - prediction.decimal_odds) / max(max_decimal_odds - 1.0, 0.01)
    )
    probability_pressure = _clamp(
        (prediction.probability - probability_min) / max(probability_max - probability_min, 0.01)
    )
    return _clamp(
        strength * (0.50 * edge_pressure + 0.30 * price_pressure + 0.20 * probability_pressure)
    )


def _fixture_market_favorite_prediction(
    fixture: HistoricalFixture,
) -> HistoricalMarketPrediction | None:
    predictions = [
        prediction for prediction in fixture.predictions if prediction.market_type == "1x2"
    ]
    if not predictions:
        return None
    return max(predictions, key=lambda prediction: prediction.probability)


def _prediction_model_edge(prediction: HistoricalMarketPrediction) -> float:
    if prediction.model_edge is not None:
        return prediction.model_edge
    market_probability = (
        prediction.market_probability
        if prediction.market_probability is not None
        else 1.0 / prediction.decimal_odds
    )
    return prediction.probability - market_probability


def _fixture_market_context_metadata(
    fixture: HistoricalFixture,
) -> dict[str, dict[str, object]]:
    predictions = [
        prediction
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
        and prediction.outcome in {"home_win", "draw", "away_win"}
    ]
    prediction_by_outcome = {prediction.outcome: prediction for prediction in predictions}
    if {"home_win", "draw", "away_win"} - set(prediction_by_outcome):
        return {}

    favorite = max(predictions, key=lambda prediction: prediction.probability)
    favorite_probability = favorite.probability
    draw_probability = prediction_by_outcome["draw"].probability
    favorite_not_win_probability = 1.0 - favorite_probability
    fragility_score = _derived_market_context_favorite_fragility_score(
        favorite_probability=favorite_probability,
        favorite_decimal_odds=favorite.decimal_odds,
        draw_probability=draw_probability,
    )
    basis = {
        "market_context_signal_basis": "historical_1x2_market_context_v3_1",
        "market_context_favorite_outcome": favorite.outcome,
        "market_context_favorite_probability": round(favorite_probability, 6),
        "market_context_favorite_decimal_odds": round(favorite.decimal_odds, 6),
        "market_context_favorite_not_win_probability": round(
            favorite_not_win_probability,
            6,
        ),
        "market_context_draw_probability": round(draw_probability, 6),
        "market_context_favorite_fragility_score": round(fragility_score, 4),
    }
    metadata_by_outcome: dict[str, dict[str, object]] = {}
    for prediction in predictions:
        outcome_metadata: dict[str, object] = dict(basis)
        if prediction.outcome == favorite.outcome:
            outcome_metadata["is_market_favorite"] = True
            if fragility_score >= 0.28:
                outcome_metadata["favorite_fragility_score"] = max(
                    _metadata_score(prediction.metadata_json, "favorite_fragility_score"),
                    round(fragility_score, 4),
                )
        else:
            outcome_metadata["is_market_favorite"] = False
            protection_boost = _market_context_protection_boost(
                prediction.outcome,
                favorite_fragility_score=fragility_score,
                favorite_probability=favorite_probability,
            )
            if protection_boost >= 0.35:
                existing_upset_score = max(
                    prediction.upset_protection_score,
                    _metadata_score(prediction.metadata_json, "upset_score"),
                )
                outcome_metadata["target_outcome"] = prediction.outcome
                outcome_metadata["upset_score"] = max(
                    existing_upset_score,
                    round(protection_boost, 4),
                )
                outcome_metadata["upset_direction"] = (
                    "draw_overlooked" if prediction.outcome == "draw" else "underdog_protection"
                )
        metadata_by_outcome[prediction.outcome] = outcome_metadata
    return metadata_by_outcome


def _apply_data_quality_beta_lane_probability_repair(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
) -> list[RecommendationCandidate]:
    if (
        not options.data_quality_beta_lane_probability_repair_enabled
        or options.data_quality_beta_lane_probability_repair_max_delta <= 0
        or not _data_quality_beta_lane_probability_repair_has_signal(options)
    ):
        return list(candidates)
    return [
        _repair_data_quality_beta_lane_probability(
            candidate,
            options=options,
            policy_config=policy_config,
        )
        for candidate in candidates
    ]


def _repair_data_quality_beta_lane_probability(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
) -> RecommendationCandidate:
    if not _data_quality_beta_lane_probability_repair_applies(
        candidate,
        options=options,
        policy_config=policy_config,
    ):
        return candidate
    market_probability = candidate.effective_market_probability()
    if market_probability is None:
        return candidate
    repair_delta = _data_quality_beta_lane_probability_repair_delta(
        candidate,
        market_probability=market_probability,
        options=options,
        policy_config=policy_config,
    )
    if repair_delta <= 0:
        return candidate
    repaired_probability = min(
        _clamp(candidate.probability + repair_delta),
        options.data_quality_beta_lane_probability_repair_max_probability,
    )
    repair_delta = max(0.0, repaired_probability - candidate.probability)
    if repair_delta <= 0:
        return candidate
    repaired_model_edge = repaired_probability - market_probability
    return candidate.model_copy(
        update={
            "probability": repaired_probability,
            "model_edge": repaired_model_edge,
            "metadata_json": {
                **candidate.metadata_json,
                "data_quality_beta_lane_probability_repair_basis": (
                    "historical_data_quality_beta_lane_market_floor_v3_1"
                ),
                "data_quality_beta_lane_probability_repair_original_probability": round(
                    candidate.probability,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_market_probability": round(
                    market_probability,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_delta": round(
                    repair_delta,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_strength": round(
                    options.data_quality_beta_lane_probability_repair_strength,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_max_delta": round(
                    options.data_quality_beta_lane_probability_repair_max_delta,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_extra_uplift": round(
                    options.data_quality_beta_lane_probability_repair_extra_uplift,
                    6,
                ),
                (
                    "data_quality_beta_lane_probability_repair_"
                    "data_quality_gap_weight"
                ): round(
                    options.data_quality_beta_lane_probability_repair_data_quality_gap_weight,
                    6,
                ),
                (
                    "data_quality_beta_lane_probability_repair_"
                    "odds_stability_weight"
                ): round(
                    options.data_quality_beta_lane_probability_repair_odds_stability_weight,
                    6,
                ),
                "data_quality_beta_lane_probability_repair_max_probability": round(
                    options.data_quality_beta_lane_probability_repair_max_probability,
                    6,
                ),
            },
        }
    )


def _data_quality_beta_lane_probability_repair_delta(
    candidate: RecommendationCandidate,
    *,
    market_probability: float,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
) -> float:
    market_gap = max(0.0, market_probability - candidate.probability)
    effective_threshold = candidate_min_data_quality_score(candidate, policy_config)
    quality_gap = _clamp(
        (policy_config.min_data_quality_score - candidate.data_quality_score)
        / max(policy_config.min_data_quality_score - effective_threshold, 1.0)
    )
    stability_quality = _clamp(
        (
            candidate.odds_stability_score
            - options.data_quality_beta_lane_min_odds_stability_score
        )
        / max(1.0 - options.data_quality_beta_lane_min_odds_stability_score, 0.01)
    )
    raw_delta = (
        market_gap * options.data_quality_beta_lane_probability_repair_strength
        + options.data_quality_beta_lane_probability_repair_extra_uplift
        + quality_gap
        * options.data_quality_beta_lane_probability_repair_data_quality_gap_weight
        + stability_quality
        * options.data_quality_beta_lane_probability_repair_odds_stability_weight
    )
    return min(raw_delta, options.data_quality_beta_lane_probability_repair_max_delta)


def _data_quality_beta_lane_probability_repair_has_signal(
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    return any(
        value > 0
        for value in (
            options.data_quality_beta_lane_probability_repair_strength,
            options.data_quality_beta_lane_probability_repair_extra_uplift,
            options.data_quality_beta_lane_probability_repair_data_quality_gap_weight,
            options.data_quality_beta_lane_probability_repair_odds_stability_weight,
        )
    )


def _data_quality_beta_lane_probability_repair_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
) -> bool:
    if not options.data_quality_beta_lane_enabled:
        return False
    raw_competition_id = candidate.metadata_json.get("competition_id")
    if not isinstance(raw_competition_id, str):
        return False
    if (
        options.data_quality_beta_lane_competition_ids
        and raw_competition_id not in set(options.data_quality_beta_lane_competition_ids)
    ):
        return False
    if not _data_quality_beta_lane_regime_applies(candidate, options=options):
        return False
    effective_threshold = candidate_min_data_quality_score(candidate, policy_config)
    if effective_threshold >= policy_config.min_data_quality_score:
        return False
    if candidate.data_quality_score < effective_threshold:
        return False
    if candidate.data_quality_score >= policy_config.min_data_quality_score:
        return False
    if candidate.probability < options.data_quality_beta_lane_min_probability:
        return False
    if (
        options.data_quality_beta_lane_max_decimal_odds is not None
        and (
            candidate.decimal_odds is None
            or candidate.decimal_odds
            > options.data_quality_beta_lane_max_decimal_odds
        )
    ):
        return False
    if (
        options.data_quality_beta_lane_min_model_edge is not None
        and candidate.effective_model_edge()
        < options.data_quality_beta_lane_min_model_edge
    ):
        return False
    if (
        candidate.model_confidence_score
        < options.data_quality_beta_lane_min_model_confidence_score
    ):
        return False
    if candidate.calibration_score < options.data_quality_beta_lane_min_calibration_score:
        return False
    if (
        candidate.odds_stability_score
        < options.data_quality_beta_lane_min_odds_stability_score
    ):
        return False
    if (
        options.data_quality_beta_lane_max_volatility_penalty is not None
        and candidate.volatility_penalty
        > options.data_quality_beta_lane_max_volatility_penalty
    ):
        return False
    market_probability = candidate.effective_market_probability()
    return (
        market_probability is not None
        and market_probability - candidate.probability
        >= options.data_quality_beta_lane_probability_repair_min_market_probability_delta
    )


def _data_quality_beta_lane_regime_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if options.data_quality_beta_lane_season_ids:
        season_id = _candidate_season_id(candidate)
        if season_id not in set(options.data_quality_beta_lane_season_ids):
            return False
    if (
        options.data_quality_beta_lane_min_competition_season_index is None
        and options.data_quality_beta_lane_max_competition_season_index is None
    ):
        return True
    season_index = _candidate_competition_season_index(candidate)
    if season_index is None:
        return False
    if (
        options.data_quality_beta_lane_min_competition_season_index is not None
        and season_index
        < options.data_quality_beta_lane_min_competition_season_index
    ):
        return False
    return not (
        options.data_quality_beta_lane_max_competition_season_index is not None
        and season_index
        > options.data_quality_beta_lane_max_competition_season_index
    )


def _data_quality_beta_lane_probability_repair_candidates(
    candidates: Sequence[RecommendationCandidate],
) -> list[RecommendationCandidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.metadata_json.get("data_quality_beta_lane_probability_repair_basis")
        == "historical_data_quality_beta_lane_market_floor_v3_1"
    ]


def _derived_market_context_favorite_fragility_score(
    *,
    favorite_probability: float,
    favorite_decimal_odds: float,
    draw_probability: float,
) -> float:
    not_win_pressure = 1.0 - favorite_probability
    vulnerable_favorite_band = _clamp((favorite_probability - 0.44) / 0.18) * _clamp(
        (0.70 - favorite_probability) / 0.18
    )
    short_price_pressure = _clamp((2.05 - favorite_decimal_odds) / 0.80)
    raw_score = (
        0.44 * not_win_pressure
        + 0.25 * draw_probability
        + 0.16 * short_price_pressure
        + 0.15 * vulnerable_favorite_band
    )
    if favorite_probability >= 0.74:
        raw_score *= 0.70
    return round(_clamp(raw_score), 4)


def _market_context_protection_boost(
    outcome: str,
    *,
    favorite_fragility_score: float,
    favorite_probability: float,
) -> float:
    if favorite_fragility_score < 0.35 or favorite_probability > 0.66:
        return 0.0
    if outcome == "draw":
        return _clamp(favorite_fragility_score * 0.68)
    return _clamp(favorite_fragility_score * 0.56)


def _metadata_score(metadata_json: dict[str, object], key: str) -> float:
    raw = metadata_json.get(key)
    if isinstance(raw, int | float):
        return _clamp(float(raw))
    return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _prediction_correlation_key(
    fixture: HistoricalFixture,
    *,
    outcome: str,
    market_type: str,
) -> str | None:
    if outcome in {"home_win", "handicap_home_win"}:
        return f"{fixture.competition_id}:team:{_correlation_slug(fixture.home_team_name)}"
    if outcome in {"away_win", "handicap_away_win"}:
        return f"{fixture.competition_id}:team:{_correlation_slug(fixture.away_team_name)}"
    if market_type in {"cn_handicap_1x2", "european_handicap_1x2"}:
        return f"{fixture.competition_id}:handicap_draw"
    return None


def _correlation_slug(value: str) -> str:
    return "_".join(value.lower().split())


def _compress_candidate_pool(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    if options.candidate_fixture_limit is None:
        return list(candidates)
    ranked = rank_candidates(
        candidates,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    scored_by_fixture: dict[str, list[ScoredRecommendationCandidate]] = {}
    for scored in ranked:
        scored_by_fixture.setdefault(scored.candidate.fixture_id, []).append(scored)

    reserve_fixture_ids = set(
        _upset_exposure_reserve_fixture_ids(
            candidates,
            options=options,
            as_of_time_utc=as_of_time_utc,
            limit=options.upset_exposure_reserve_fixture_count,
        )
    )
    fixture_sort_keys = [
        (
            fixture_id,
            _candidate_fixture_pool_sort_key(scored_candidates),
        )
        for fixture_id, scored_candidates in scored_by_fixture.items()
    ]
    selected_fixture_ids = {
        fixture_id
        for fixture_id, _sort_key in sorted(
            fixture_sort_keys,
            key=lambda item: item[1],
            reverse=True,
        )[: options.candidate_fixture_limit]
    }
    selected_fixture_ids.update(reserve_fixture_ids)
    compressed: list[RecommendationCandidate] = []
    for fixture_id in selected_fixture_ids:
        selected_candidates = [
            scored.candidate
            for scored in scored_by_fixture.get(fixture_id, [])[
                : options.max_candidates_per_fixture
            ]
        ]
        if fixture_id in reserve_fixture_ids:
            selected_candidates = _with_upset_exposure_reserve_candidates(
                selected_candidates,
                candidates=[
                    candidate for candidate in candidates if candidate.fixture_id == fixture_id
                ],
                options=options,
                as_of_time_utc=as_of_time_utc,
            )
        compressed.extend(selected_candidates)
    return compressed


def _scenario_candidate_pool(
    candidates: Sequence[RecommendationCandidate],
    *,
    scenario: HistoricalRecommendationScenario,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    if options.scenario_candidate_fixture_buffer is None:
        return list(candidates)
    leg_count = parse_pass_type_leg_count(scenario.pass_type)
    fixture_limit = leg_count + options.scenario_candidate_fixture_buffer
    candidate_fixture_count = len({candidate.fixture_id for candidate in candidates})
    if fixture_limit >= candidate_fixture_count:
        return list(candidates)

    ranked = rank_candidates(
        candidates,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    scored_by_fixture: dict[str, list[ScoredRecommendationCandidate]] = {}
    for scored in ranked:
        scored_by_fixture.setdefault(scored.candidate.fixture_id, []).append(scored)
    reserve_fixture_ids = set(
        _upset_exposure_reserve_fixture_ids(
            candidates,
            options=options,
            as_of_time_utc=as_of_time_utc,
            limit=options.upset_exposure_reserve_fixture_count,
        )
    )
    selected_fixture_ids = {
        fixture_id
        for fixture_id, _sort_key in sorted(
            (
                (fixture_id, _candidate_fixture_pool_sort_key(scored_candidates))
                for fixture_id, scored_candidates in scored_by_fixture.items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:fixture_limit]
    }
    selected_fixture_ids.update(reserve_fixture_ids)
    return [candidate for candidate in candidates if candidate.fixture_id in selected_fixture_ids]


def _upset_exposure_reserve_fixture_ids(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
    limit: int,
) -> list[str]:
    if not options.upset_exposure_reserve or limit <= 0:
        return []
    best_by_fixture: dict[str, tuple[tuple[float, float, float, float, float, str], str]] = {}
    for candidate in candidates:
        if not _upset_exposure_reserve_candidate_applies(
            candidate,
            options=options,
            as_of_time_utc=as_of_time_utc,
        ):
            continue
        sort_key = _upset_exposure_reserve_candidate_sort_key(candidate)
        current = best_by_fixture.get(candidate.fixture_id)
        if current is None or sort_key > current[0]:
            best_by_fixture[candidate.fixture_id] = (sort_key, candidate.fixture_id)
    return [
        fixture_id
        for _sort_key, fixture_id in sorted(
            best_by_fixture.values(),
            key=lambda item: item[0],
            reverse=True,
        )[:limit]
    ]


def _with_upset_exposure_reserve_candidates(
    selected_candidates: Sequence[RecommendationCandidate],
    *,
    candidates: Sequence[RecommendationCandidate],
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    selected_by_key = {
        _candidate_identity(candidate): candidate for candidate in selected_candidates
    }
    reserve_candidates = sorted(
        (
            candidate
            for candidate in candidates
            if _upset_exposure_reserve_candidate_applies(
                candidate,
                options=options,
                as_of_time_utc=as_of_time_utc,
            )
        ),
        key=_upset_exposure_reserve_candidate_sort_key,
        reverse=True,
    )[: options.upset_exposure_reserve_max_candidates_per_fixture]
    for candidate in reserve_candidates:
        selected_by_key.setdefault(_candidate_identity(candidate), candidate)
    return list(selected_by_key.values())


def _upset_exposure_reserve_candidate_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> bool:
    if not options.upset_exposure_reserve:
        return False
    if candidate.market_type not in options.allowed_markets:
        return False
    if candidate.probability < options.upset_exposure_reserve_min_probability:
        return False
    if candidate.data_quality_score < _candidate_min_data_quality_score(candidate, options):
        return False
    if options.require_odds and candidate.decimal_odds is None:
        return False
    if (
        options.upset_exposure_reserve_max_decimal_odds is not None
        and candidate.decimal_odds is not None
        and candidate.decimal_odds > options.upset_exposure_reserve_max_decimal_odds
    ):
        return False
    if candidate.has_started(as_of_time_utc):
        return False
    signal = analyze_candidate_upset_signal(candidate)
    return signal.protection_score >= options.upset_exposure_reserve_min_protection_score


def _candidate_min_data_quality_score(
    candidate: RecommendationCandidate,
    options: HistoricalRecommendationBacktestOptions,
) -> float:
    raw_competition_id = candidate.metadata_json.get("competition_id")
    if isinstance(raw_competition_id, str):
        return options.min_data_quality_score_by_competition_id.get(
            raw_competition_id,
            options.min_data_quality_score,
        )
    return options.min_data_quality_score


def _upset_exposure_reserve_candidates(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    return [
        candidate
        for candidate in candidates
        if _upset_exposure_reserve_candidate_applies(
            candidate,
            options=options,
            as_of_time_utc=as_of_time_utc,
        )
    ]


def _upset_final_answer_lane_candidates(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> list[RecommendationCandidate]:
    lane_candidates = [
        candidate
        for candidate in candidates
        if _upset_final_answer_lane_candidate_applies(
            candidate,
            options=options,
            as_of_time_utc=as_of_time_utc,
        )
    ]
    return sorted(
        lane_candidates,
        key=_upset_exposure_reserve_candidate_sort_key,
        reverse=True,
    )[: options.upset_final_answer_lane_candidate_limit]


def _upset_final_answer_lane_candidate_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
    as_of_time_utc: datetime,
) -> bool:
    if not options.upset_final_answer_lane:
        return False
    if candidate.market_type not in options.allowed_markets:
        return False
    if not _upset_final_answer_lane_competition_applies(candidate, options=options):
        return False
    if candidate.probability < options.upset_final_answer_lane_min_probability:
        return False
    if candidate.data_quality_score < _candidate_min_data_quality_score(candidate, options):
        return False
    if options.require_odds and candidate.decimal_odds is None:
        return False
    if options.upset_final_answer_lane_min_decimal_odds is not None and (
        candidate.decimal_odds is None
        or candidate.decimal_odds < options.upset_final_answer_lane_min_decimal_odds
    ):
        return False
    if (
        options.upset_final_answer_lane_max_decimal_odds is not None
        and candidate.decimal_odds is not None
        and candidate.decimal_odds > options.upset_final_answer_lane_max_decimal_odds
    ):
        return False
    if candidate.has_started(as_of_time_utc):
        return False
    signal = analyze_candidate_upset_signal(candidate)
    if signal.protection_score < options.upset_final_answer_lane_min_protection_score:
        return False
    return _upset_final_answer_lane_quality_applies(candidate, options=options)


def _upset_final_answer_lane_quality_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if (
        options.upset_final_answer_lane_min_model_edge is not None
        and candidate.effective_model_edge() < options.upset_final_answer_lane_min_model_edge
    ):
        return False
    if (
        options.upset_final_answer_lane_max_model_edge is not None
        and candidate.effective_model_edge() > options.upset_final_answer_lane_max_model_edge
    ):
        return False
    if candidate.calibration_score < options.upset_final_answer_lane_min_calibration_score:
        return False
    if (
        candidate.model_confidence_score
        < options.upset_final_answer_lane_min_model_confidence_score
    ):
        return False
    if candidate.odds_stability_score < options.upset_final_answer_lane_min_odds_stability_score:
        return False
    if (
        options.upset_final_answer_lane_max_volatility_penalty is not None
        and candidate.volatility_penalty > options.upset_final_answer_lane_max_volatility_penalty
    ):
        return False
    calibration = assess_upset_signal_calibration(candidate)
    if (
        options.upset_final_answer_lane_max_signal_calibration_risk is not None
        and calibration.risk_score > options.upset_final_answer_lane_max_signal_calibration_risk
    ):
        return False
    return (
        calibration.reliability_score
        >= options.upset_final_answer_lane_min_signal_reliability_score
    )


def _upset_final_answer_lane_competition_applies(
    candidate: RecommendationCandidate,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    competition_id = _candidate_competition_id(candidate)
    allowed_competition_ids = set(options.upset_final_answer_lane_competition_ids)
    excluded_competition_ids = set(options.upset_final_answer_lane_excluded_competition_ids)
    if allowed_competition_ids and competition_id not in allowed_competition_ids:
        return False
    return competition_id not in excluded_competition_ids


def _candidate_competition_id(candidate: RecommendationCandidate) -> str | None:
    raw = candidate.metadata_json.get("competition_id")
    return raw if isinstance(raw, str) and raw else None


def _candidate_season_id(candidate: RecommendationCandidate) -> str | None:
    for key in ("season_id", "season", "source_season"):
        raw = candidate.metadata_json.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _candidate_competition_season_index(
    candidate: RecommendationCandidate,
) -> int | None:
    raw = candidate.metadata_json.get("competition_season_index")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _fixture_season_id(fixture: HistoricalFixture) -> str | None:
    for key in ("season_id", "season", "source_season"):
        raw = fixture.metadata_json.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _season_start_year(season_id: str | None) -> int | None:
    if not season_id:
        return None
    match = search(r"\d{4}", season_id)
    return int(match.group(0)) if match is not None else None


def _average_upset_signal_calibration_risk(
    candidates: Sequence[RecommendationCandidate],
) -> float | None:
    return _average(
        assess_upset_signal_calibration(candidate).risk_score for candidate in candidates
    )


def _average_upset_signal_reliability_score(
    candidates: Sequence[RecommendationCandidate],
) -> float | None:
    return _average(
        assess_upset_signal_calibration(candidate).reliability_score for candidate in candidates
    )


def _upset_exposure_reserve_candidate_sort_key(
    candidate: RecommendationCandidate,
) -> tuple[float, float, float, float, float, str]:
    signal = analyze_candidate_upset_signal(candidate)
    odds_discipline = -(candidate.decimal_odds or 99.0)
    return (
        signal.protection_score,
        candidate.probability,
        candidate.effective_model_edge(),
        candidate.data_quality_score / 100.0,
        odds_discipline,
        candidate.candidate_id or candidate.fixture_id,
    )


def _candidate_identity(
    candidate: RecommendationCandidate,
) -> tuple[
    str,
    str,
    str,
    float | None,
    str | None,
]:
    return (
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
        candidate.line,
        candidate.side,
    )


def _candidate_fixture_pool_sort_key(
    scored_candidates: Sequence[ScoredRecommendationCandidate],
) -> tuple[float, float, float, str]:
    top_score = max(scored.score for scored in scored_candidates)
    average_score = sum(scored.score for scored in scored_candidates) / len(scored_candidates)
    top_probability = max(scored.candidate.probability for scored in scored_candidates)
    fixture_id = scored_candidates[0].candidate.fixture_id
    return (top_score, average_score, top_probability, fixture_id)


def _historical_scenarios(
    options: HistoricalRecommendationBacktestOptions,
) -> list[HistoricalRecommendationScenario]:
    scenarios: list[HistoricalRecommendationScenario] = []
    for pass_type in options.pass_types:
        leg_count = parse_pass_type_leg_count(pass_type)
        for mode in options.modes:
            if leg_count == 1 and mode == "multiple":
                continue
            scenarios.append(
                HistoricalRecommendationScenario(
                    scenario_key=f"{pass_type}:{mode}",
                    pass_type=pass_type,
                    mode=mode,
                )
            )
    return scenarios


def _upset_opportunity_fixture_ids(
    fixtures: Sequence[HistoricalFixture],
    *,
    threshold: float,
    derive_market_context_signals: bool = False,
) -> set[str]:
    fixture_ids: set[str] = set()
    for fixture in fixtures:
        for candidate in _candidates_from_fixture(
            fixture,
            derive_market_context_signals=derive_market_context_signals,
        ):
            signal = analyze_candidate_upset_signal(candidate)
            if signal.protection_score >= threshold and _leg_matches_actual_outcome(
                fixture,
                outcome=candidate.outcome,
                market_type=candidate.market_type,
            ):
                fixture_ids.add(fixture.fixture_id)
    return fixture_ids


def _captured_upset_fixture_ids(
    selection: RecommendationSelection,
    *,
    fixture_by_id: dict[str, HistoricalFixture],
    threshold: float,
) -> list[str]:
    fixture_ids: list[str] = []
    for scored in selection.selected_candidates:
        candidate = scored.candidate
        fixture = fixture_by_id[candidate.fixture_id]
        signal = analyze_candidate_upset_signal(candidate)
        if (
            signal.protection_score >= threshold
            and _leg_matches_actual_outcome(
                fixture,
                outcome=candidate.outcome,
                market_type=candidate.market_type,
            )
            and candidate.fixture_id not in fixture_ids
        ):
            fixture_ids.append(candidate.fixture_id)
    return fixture_ids


def _summary_json(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
    completed: Sequence[HistoricalRecommendationScenarioResult],
    final_answer: HistoricalRecommendationScenarioResult | None,
    upset_opportunities: set[str],
    upset_capture_count: int,
    policy_config: RecommendationPolicyConfig,
    eligible_candidate_count: int,
    candidate_pool_count: int,
    candidate_pool_fixture_count: int,
    eligible_candidates: Sequence[RecommendationCandidate],
    candidate_pool_candidates: Sequence[RecommendationCandidate],
    short_price_negative_edge_guardrail_excluded_candidate_count: int,
    short_price_negative_edge_soft_penalty_candidate_count: int,
    marginal_loss_driver_candidate_guardrail_excluded_candidate_count: int,
    marginal_loss_driver_candidate_soft_penalty_candidate_count: int,
) -> dict[str, object]:
    final_answer_selected = (
        [item.candidate for item in final_answer.option.selection.selected_candidates]
        if final_answer is not None and final_answer.option is not None
        else []
    )
    completed_options = [result.option for result in completed if result.option is not None]
    candidate_pool_loss_driver_soft_penalty_candidates = (
        _marginal_loss_driver_candidate_soft_penalty_profile_candidates(
            candidate_pool_candidates
        )
    )
    completed_scenario_loss_driver_soft_penalty_selected_candidates = [
        item.candidate
        for option in completed_options
        for item in option.selection.selected_candidates
        if _is_marginal_loss_driver_candidate_soft_penalty_profile(item.candidate)
    ]
    final_answer_loss_driver_soft_penalty_candidates = (
        _marginal_loss_driver_candidate_soft_penalty_profile_candidates(
            final_answer_selected
        )
    )
    loss_driver_soft_penalty_fixture_exposure = (
        _marginal_loss_driver_candidate_soft_penalty_fixture_exposure(
            eligible_candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=historical_slice.as_of_time_utc,
        )
    )
    candidate_pool_upset_reserve_candidates = _upset_exposure_reserve_candidates(
        candidate_pool_candidates,
        options=options,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    final_answer_upset_reserve_candidates = _upset_exposure_reserve_candidates(
        final_answer_selected,
        options=options,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    eligible_upset_lane_candidates = _upset_final_answer_lane_candidates(
        eligible_candidates,
        options=options,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    candidate_pool_upset_lane_candidates = _upset_final_answer_lane_candidates(
        candidate_pool_candidates,
        options=options,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    final_answer_is_upset_lane = _is_upset_final_answer_lane_result(final_answer)
    final_answer_is_dynamic_mix_lane = _is_dynamic_mix_final_answer_lane_result(
        final_answer
    )
    final_answer_is_correct_score_lane = (
        _is_correct_score_final_answer_lane_result(final_answer)
    )
    final_answer_upset_lane_candidates = (
        _upset_final_answer_lane_candidates(
            final_answer_selected,
            options=options,
            as_of_time_utc=historical_slice.as_of_time_utc,
        )
        if final_answer_is_upset_lane
        else []
    )
    eligible_correct_score_lane_candidates = _correct_score_final_answer_lane_candidates(
        eligible_candidates,
        options=options,
        policy_config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    candidate_pool_correct_score_lane_candidates = (
        _correct_score_final_answer_lane_candidates(
            candidate_pool_candidates,
            options=options,
            policy_config=policy_config,
            as_of_time_utc=historical_slice.as_of_time_utc,
        )
    )
    final_answer_correct_score_lane_candidates = (
        [
            candidate
            for candidate in final_answer_selected
            if candidate.market_type == "correct_score"
        ]
        if final_answer_is_correct_score_lane
        else []
    )
    final_answer_market_summary = _final_answer_market_summary(
        final_answer,
        candidate_count=len(completed_options),
    )
    return {
        "calculation_basis": "historical_recommendation_backtest_v3_1",
        "slice_id": historical_slice.metadata.slice_id,
        "competition_id": historical_slice.metadata.competition_id,
        "fixture_count": len(historical_slice.fixtures),
        "eligible_candidate_count": eligible_candidate_count,
        "candidate_pool_count": candidate_pool_count,
        "candidate_pool_fixture_count": candidate_pool_fixture_count,
        "candidate_fixture_limit": options.candidate_fixture_limit,
        "max_candidates_per_fixture": options.max_candidates_per_fixture,
        "scenario_candidate_fixture_buffer": (options.scenario_candidate_fixture_buffer),
        "final_answer_scenario_variant_count": (
            options.final_answer_scenario_variant_count
        ),
        "completed_scenario_variant_count": sum(
            1
            for result in completed
            if result.selection_diagnostics_json.get("scenario_variant") is True
        ),
        "min_data_quality_score": options.min_data_quality_score,
        "min_data_quality_score_by_competition_id": dict(
            sorted(options.min_data_quality_score_by_competition_id.items())
        ),
        "data_quality_beta_lane_enabled": options.data_quality_beta_lane_enabled,
        "data_quality_beta_lane_competition_ids": list(
            options.data_quality_beta_lane_competition_ids
        ),
        "data_quality_beta_lane_season_ids": list(
            options.data_quality_beta_lane_season_ids
        ),
        "data_quality_beta_lane_min_competition_season_index": (
            options.data_quality_beta_lane_min_competition_season_index
        ),
        "data_quality_beta_lane_max_competition_season_index": (
            options.data_quality_beta_lane_max_competition_season_index
        ),
        "data_quality_beta_lane_min_probability": (
            options.data_quality_beta_lane_min_probability
        ),
        "data_quality_beta_lane_max_decimal_odds": (
            options.data_quality_beta_lane_max_decimal_odds
        ),
        "data_quality_beta_lane_min_model_edge": (
            options.data_quality_beta_lane_min_model_edge
        ),
        "data_quality_beta_lane_min_model_confidence_score": (
            options.data_quality_beta_lane_min_model_confidence_score
        ),
        "data_quality_beta_lane_min_calibration_score": (
            options.data_quality_beta_lane_min_calibration_score
        ),
        "data_quality_beta_lane_min_odds_stability_score": (
            options.data_quality_beta_lane_min_odds_stability_score
        ),
        "data_quality_beta_lane_max_volatility_penalty": (
            options.data_quality_beta_lane_max_volatility_penalty
        ),
        "data_quality_beta_lane_probability_repair_enabled": (
            options.data_quality_beta_lane_probability_repair_enabled
        ),
        "data_quality_beta_lane_probability_repair_strength": (
            options.data_quality_beta_lane_probability_repair_strength
        ),
        "data_quality_beta_lane_probability_repair_max_delta": (
            options.data_quality_beta_lane_probability_repair_max_delta
        ),
        "data_quality_beta_lane_probability_repair_min_market_probability_delta": (
            options.data_quality_beta_lane_probability_repair_min_market_probability_delta
        ),
        "data_quality_beta_lane_probability_repair_extra_uplift": (
            options.data_quality_beta_lane_probability_repair_extra_uplift
        ),
        "data_quality_beta_lane_probability_repair_data_quality_gap_weight": (
            options.data_quality_beta_lane_probability_repair_data_quality_gap_weight
        ),
        "data_quality_beta_lane_probability_repair_odds_stability_weight": (
            options.data_quality_beta_lane_probability_repair_odds_stability_weight
        ),
        "data_quality_beta_lane_probability_repair_max_probability": (
            options.data_quality_beta_lane_probability_repair_max_probability
        ),
        "data_quality_beta_lane_probability_repair_candidate_count": len(
            _data_quality_beta_lane_probability_repair_candidates(eligible_candidates)
        ),
        "data_quality_beta_lane_probability_repair_candidate_pool_count": len(
            _data_quality_beta_lane_probability_repair_candidates(candidate_pool_candidates)
        ),
        "data_quality_beta_lane_probability_repair_final_answer_selected_candidate_count": len(
            _data_quality_beta_lane_probability_repair_candidates(final_answer_selected)
        ),
        "data_quality_beta_lane_probability_repair_final_answer_selected_fixture_ids": sorted(
            {
                candidate.fixture_id
                for candidate in _data_quality_beta_lane_probability_repair_candidates(
                    final_answer_selected
                )
            }
        ),
        "derive_market_context_signals": options.derive_market_context_signals,
        "upset_exposure_reserve": options.upset_exposure_reserve,
        "upset_exposure_reserve_fixture_count": (options.upset_exposure_reserve_fixture_count),
        "upset_exposure_reserve_max_candidates_per_fixture": (
            options.upset_exposure_reserve_max_candidates_per_fixture
        ),
        "upset_exposure_reserve_min_protection_score": (
            options.upset_exposure_reserve_min_protection_score
        ),
        "upset_exposure_reserve_min_probability": (options.upset_exposure_reserve_min_probability),
        "upset_exposure_reserve_max_decimal_odds": (
            options.upset_exposure_reserve_max_decimal_odds
        ),
        "candidate_pool_upset_exposure_reserve_candidate_count": len(
            candidate_pool_upset_reserve_candidates
        ),
        "candidate_pool_upset_exposure_reserve_fixture_count": len(
            {candidate.fixture_id for candidate in candidate_pool_upset_reserve_candidates}
        ),
        "final_answer_upset_exposure_reserve_selected_candidate_count": len(
            final_answer_upset_reserve_candidates
        ),
        "final_answer_upset_exposure_reserve_selected_fixture_ids": sorted(
            {candidate.fixture_id for candidate in final_answer_upset_reserve_candidates}
        ),
        "upset_final_answer_lane": options.upset_final_answer_lane,
        "upset_final_answer_lane_pass_type": options.upset_final_answer_lane_pass_type,
        "upset_final_answer_lane_mode": options.upset_final_answer_lane_mode,
        "upset_final_answer_lane_candidate_limit": (
            options.upset_final_answer_lane_candidate_limit
        ),
        "upset_final_answer_lane_min_protection_score": (
            options.upset_final_answer_lane_min_protection_score
        ),
        "upset_final_answer_lane_min_probability": (
            options.upset_final_answer_lane_min_probability
        ),
        "upset_final_answer_lane_min_decimal_odds": (
            options.upset_final_answer_lane_min_decimal_odds
        ),
        "upset_final_answer_lane_max_decimal_odds": (
            options.upset_final_answer_lane_max_decimal_odds
        ),
        "upset_final_answer_lane_min_model_edge": (options.upset_final_answer_lane_min_model_edge),
        "upset_final_answer_lane_max_model_edge": (options.upset_final_answer_lane_max_model_edge),
        "upset_final_answer_lane_competition_ids": list(
            options.upset_final_answer_lane_competition_ids
        ),
        "upset_final_answer_lane_excluded_competition_ids": list(
            options.upset_final_answer_lane_excluded_competition_ids
        ),
        "upset_final_answer_lane_min_calibration_score": (
            options.upset_final_answer_lane_min_calibration_score
        ),
        "upset_final_answer_lane_min_model_confidence_score": (
            options.upset_final_answer_lane_min_model_confidence_score
        ),
        "upset_final_answer_lane_min_odds_stability_score": (
            options.upset_final_answer_lane_min_odds_stability_score
        ),
        "upset_final_answer_lane_max_volatility_penalty": (
            options.upset_final_answer_lane_max_volatility_penalty
        ),
        "upset_final_answer_lane_max_hit_probability_deficit": (
            options.upset_final_answer_lane_max_hit_probability_deficit
        ),
        "upset_final_answer_lane_max_signal_calibration_risk": (
            options.upset_final_answer_lane_max_signal_calibration_risk
        ),
        "upset_final_answer_lane_min_signal_reliability_score": (
            options.upset_final_answer_lane_min_signal_reliability_score
        ),
        "upset_final_answer_lane_score_boost": (options.upset_final_answer_lane_score_boost),
        "upset_final_answer_lane_candidate_count": len(eligible_upset_lane_candidates),
        "upset_final_answer_lane_fixture_count": len(
            {candidate.fixture_id for candidate in eligible_upset_lane_candidates}
        ),
        "candidate_pool_upset_final_answer_lane_candidate_count": len(
            candidate_pool_upset_lane_candidates
        ),
        "candidate_pool_upset_final_answer_lane_fixture_count": len(
            {candidate.fixture_id for candidate in candidate_pool_upset_lane_candidates}
        ),
        "completed_upset_final_answer_lane_count": sum(
            1 for result in completed if _is_upset_final_answer_lane_result(result)
        ),
        "upset_final_answer_lane_calibration_guard_blocked_option_count": (
            _upset_final_answer_lane_calibration_guard_blocked_option_count(
                completed_options,
                backtest_options=options,
            )
        ),
        "final_answer_upset_final_answer_lane": final_answer_is_upset_lane,
        "final_answer_upset_final_answer_lane_hit_probability_deficit": (
            _final_answer_upset_lane_hit_probability_deficit(
                final_answer,
                completed=completed,
                backtest_options=options,
            )
        ),
        "final_answer_upset_final_answer_lane_selected_candidate_count": len(
            final_answer_upset_lane_candidates
        ),
        "final_answer_upset_final_answer_lane_selected_fixture_ids": sorted(
            {candidate.fixture_id for candidate in final_answer_upset_lane_candidates}
        ),
        "final_answer_upset_final_answer_lane_signal_calibration_risk": (
            _average_upset_signal_calibration_risk(final_answer_upset_lane_candidates)
        ),
        "final_answer_upset_final_answer_lane_signal_reliability_score": (
            _average_upset_signal_reliability_score(final_answer_upset_lane_candidates)
        ),
        "short_price_negative_edge_guardrail": (options.short_price_negative_edge_guardrail),
        "short_price_negative_edge_max_decimal_odds": (
            options.short_price_negative_edge_max_decimal_odds
        ),
        "short_price_negative_edge_min_probability": (
            options.short_price_negative_edge_min_probability
        ),
        "short_price_negative_edge_max_model_edge": (
            options.short_price_negative_edge_max_model_edge
        ),
        "short_price_negative_edge_guardrail_excluded_candidate_count": (
            short_price_negative_edge_guardrail_excluded_candidate_count
        ),
        "short_price_negative_edge_soft_penalty": (options.short_price_negative_edge_soft_penalty),
        "short_price_negative_edge_soft_penalty_strength": (
            options.short_price_negative_edge_soft_penalty_strength
        ),
        "short_price_negative_edge_soft_penalty_competition_ids": list(
            options.short_price_negative_edge_soft_penalty_competition_ids
        ),
        "short_price_negative_edge_soft_penalty_candidate_count": (
            short_price_negative_edge_soft_penalty_candidate_count
        ),
        "marginal_loss_driver_candidate_guardrail": (
            options.marginal_loss_driver_candidate_guardrail
        ),
        "marginal_loss_driver_candidate_guardrail_probability_min": (
            options.marginal_loss_driver_candidate_guardrail_probability_min
        ),
        "marginal_loss_driver_candidate_guardrail_probability_max": (
            options.marginal_loss_driver_candidate_guardrail_probability_max
        ),
        "marginal_loss_driver_candidate_guardrail_max_decimal_odds": (
            options.marginal_loss_driver_candidate_guardrail_max_decimal_odds
        ),
        "marginal_loss_driver_candidate_guardrail_max_model_edge": (
            options.marginal_loss_driver_candidate_guardrail_max_model_edge
        ),
        "marginal_loss_driver_candidate_guardrail_max_calibration_score": (
            options.marginal_loss_driver_candidate_guardrail_max_calibration_score
        ),
        "marginal_loss_driver_candidate_guardrail_max_model_confidence_score": (
            options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score
        ),
        "marginal_loss_driver_candidate_guardrail_max_odds_stability_score": (
            options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score
        ),
        "marginal_loss_driver_candidate_guardrail_competition_ids": list(
            options.marginal_loss_driver_candidate_guardrail_competition_ids
        ),
        "marginal_loss_driver_candidate_guardrail_excluded_candidate_count": (
            marginal_loss_driver_candidate_guardrail_excluded_candidate_count
        ),
        "marginal_loss_driver_candidate_soft_penalty": (
            options.marginal_loss_driver_candidate_soft_penalty
        ),
        "marginal_loss_driver_candidate_soft_penalty_strength": (
            options.marginal_loss_driver_candidate_soft_penalty_strength
        ),
        "marginal_loss_driver_candidate_soft_penalty_candidate_count": (
            marginal_loss_driver_candidate_soft_penalty_candidate_count
        ),
        "marginal_loss_driver_candidate_soft_penalty_candidate_pool_candidate_count": len(
            candidate_pool_loss_driver_soft_penalty_candidates
        ),
        "marginal_loss_driver_candidate_soft_penalty_candidate_pool_fixture_count": len(
            {
                candidate.fixture_id
                for candidate in candidate_pool_loss_driver_soft_penalty_candidates
            }
        ),
        (
            "marginal_loss_driver_candidate_soft_penalty_"
            "completed_scenario_selected_candidate_count"
        ): len(completed_scenario_loss_driver_soft_penalty_selected_candidates),
        (
            "marginal_loss_driver_candidate_soft_penalty_"
            "completed_scenario_selected_option_count"
        ): sum(
            1
            for option in completed_options
            if any(
                _is_marginal_loss_driver_candidate_soft_penalty_profile(
                    item.candidate
                )
                for item in option.selection.selected_candidates
            )
        ),
        "marginal_loss_driver_candidate_soft_penalty_final_answer_selected_candidate_count": len(
            final_answer_loss_driver_soft_penalty_candidates
        ),
        "marginal_loss_driver_candidate_soft_penalty_final_answer_selected_fixture_ids": sorted(
            {
                candidate.fixture_id
                for candidate in final_answer_loss_driver_soft_penalty_candidates
            }
        ),
        **loss_driver_soft_penalty_fixture_exposure,
        "final_answer_quality_signal_penalty": (options.final_answer_quality_signal_penalty),
        "final_answer_quality_signal_penalty_strength": (
            options.final_answer_quality_signal_penalty_strength
        ),
        "final_answer_quality_signal_probability_min": (
            options.final_answer_quality_signal_probability_min
        ),
        "final_answer_quality_signal_probability_max": (
            options.final_answer_quality_signal_probability_max
        ),
        "final_answer_quality_signal_min_decimal_odds": (
            options.final_answer_quality_signal_min_decimal_odds
        ),
        "final_answer_quality_signal_max_decimal_odds": (
            options.final_answer_quality_signal_max_decimal_odds
        ),
        "final_answer_quality_signal_max_model_edge": (
            options.final_answer_quality_signal_max_model_edge
        ),
        "final_answer_quality_signal_score_min": (options.final_answer_quality_signal_score_min),
        "final_answer_quality_signal_score_max": (options.final_answer_quality_signal_score_max),
        "final_answer_quality_signal_competition_ids": list(
            options.final_answer_quality_signal_competition_ids
        ),
        "final_answer_quality_signal_penalty_score": (
            _final_answer_quality_signal_penalty_score(
                final_answer.option,
                backtest_options=options,
            )
            if final_answer is not None and final_answer.option is not None
            else 0.0
        ),
        "final_answer_quality_signal_affected_leg_count": (
            _final_answer_quality_signal_penalty_affected_leg_count(
                final_answer,
                backtest_options=options,
            )
        ),
        "final_answer_selection_value_signal": (
            options.final_answer_selection_value_signal
        ),
        "final_answer_selection_value_signal_strength": (
            options.final_answer_selection_value_signal_strength
        ),
        "final_answer_selection_value_signal_probability_min": (
            options.final_answer_selection_value_signal_probability_min
        ),
        "final_answer_selection_value_signal_probability_max": (
            options.final_answer_selection_value_signal_probability_max
        ),
        "final_answer_selection_value_signal_min_decimal_odds": (
            options.final_answer_selection_value_signal_min_decimal_odds
        ),
        "final_answer_selection_value_signal_max_decimal_odds": (
            options.final_answer_selection_value_signal_max_decimal_odds
        ),
        "final_answer_selection_value_signal_max_model_edge": (
            options.final_answer_selection_value_signal_max_model_edge
        ),
        "final_answer_selection_value_signal_score_min": (
            options.final_answer_selection_value_signal_score_min
        ),
        "final_answer_selection_value_signal_score_max": (
            options.final_answer_selection_value_signal_score_max
        ),
        "final_answer_selection_value_signal_competition_ids": list(
            options.final_answer_selection_value_signal_competition_ids
        ),
        "final_answer_selection_value_signal_outcomes": list(
            options.final_answer_selection_value_signal_outcomes
        ),
        "final_answer_selection_value_signal_max_hit_probability_deficit": (
            options.final_answer_selection_value_signal_max_hit_probability_deficit
        ),
        "final_answer_selection_value_signal_min_option_roi": (
            options.final_answer_selection_value_signal_min_option_roi
        ),
        "final_answer_selection_value_signal_max_option_risk_score": (
            options.final_answer_selection_value_signal_max_option_risk_score
        ),
        "final_answer_selection_value_signal_guard_blocked_option_count": (
            _final_answer_selection_value_signal_guard_blocked_option_count(
                completed_options,
                backtest_options=options,
            )
        ),
        "final_answer_selection_value_signal_score": (
            _final_answer_selection_value_signal_score(
                final_answer.option,
                backtest_options=options,
                reference_option=_best_non_upset_lane_reference_option(
                    completed_options,
                    backtest_options=options,
                    include_selection_value_signal=False,
                ),
            )
            if final_answer is not None and final_answer.option is not None
            else 0.0
        ),
        "final_answer_selection_value_signal_affected_leg_count": (
            _final_answer_selection_value_signal_affected_leg_count(
                final_answer,
                backtest_options=options,
            )
        ),
        "final_answer_segment_penalty": options.final_answer_segment_penalty,
        "final_answer_segment_penalty_strength": (
            options.final_answer_segment_penalty_strength
        ),
        "final_answer_segment_pass_types": list(options.final_answer_segment_pass_types),
        "final_answer_segment_modes": list(options.final_answer_segment_modes),
        "final_answer_segment_competition_ids": list(
            options.final_answer_segment_competition_ids
        ),
        "final_answer_segment_season_ids": list(
            options.final_answer_segment_season_ids
        ),
        "final_answer_segment_min_competition_season_index": (
            options.final_answer_segment_min_competition_season_index
        ),
        "final_answer_segment_max_competition_season_index": (
            options.final_answer_segment_max_competition_season_index
        ),
        "final_answer_segment_min_hit_probability": (
            options.final_answer_segment_min_hit_probability
        ),
        "final_answer_segment_max_hit_probability": (
            options.final_answer_segment_max_hit_probability
        ),
        "final_answer_segment_min_odds_product": (
            options.final_answer_segment_min_odds_product
        ),
        "final_answer_segment_max_odds_product": (
            options.final_answer_segment_max_odds_product
        ),
        "final_answer_segment_min_average_leg_decimal_odds": (
            options.final_answer_segment_min_average_leg_decimal_odds
        ),
        "final_answer_segment_max_average_leg_decimal_odds": (
            options.final_answer_segment_max_average_leg_decimal_odds
        ),
        "final_answer_segment_penalty_score": (
            _final_answer_segment_penalty_score(
                final_answer.option,
                backtest_options=options,
            )
            if final_answer is not None and final_answer.option is not None
            else 0.0
        ),
        "final_answer_segment_penalty_applied": (
            _final_answer_segment_penalty_score(
                final_answer.option,
                backtest_options=options,
            )
            > 0.0
            if final_answer is not None and final_answer.option is not None
            else False
        ),
        "final_answer_segment_penalty_option_count": sum(
            1
            for option in completed_options
            if _final_answer_segment_penalty_score(option, backtest_options=options)
            > 0.0
        ),
        "final_answer_stake_efficiency_guard": (
            options.final_answer_stake_efficiency_guard
        ),
        "final_answer_stake_efficiency_penalty_strength": (
            options.final_answer_stake_efficiency_penalty_strength
        ),
        "final_answer_stake_efficiency_max_stake_multiplier": (
            options.final_answer_stake_efficiency_max_stake_multiplier
        ),
        "final_answer_stake_efficiency_min_roi": (
            options.final_answer_stake_efficiency_min_roi
        ),
        "final_answer_stake_efficiency_modes": list(
            options.final_answer_stake_efficiency_modes
        ),
        "final_answer_stake_efficiency_scope": (
            options.final_answer_stake_efficiency_scope
        ),
        "final_answer_stake_efficiency_stake_multiplier": (
            _final_answer_stake_efficiency_stake_multiplier(
                final_answer.option
                if final_answer is not None and final_answer.option is not None
                else None
            )
        ),
        "final_answer_stake_efficiency_penalty_score": (
            _final_answer_stake_efficiency_penalty_score(
                final_answer.option,
                backtest_options=options,
            )
            if final_answer is not None and final_answer.option is not None
            else 0.0
        ),
        "final_answer_stake_efficiency_penalty_applied": (
            _final_answer_stake_efficiency_penalty_score(
                final_answer.option,
                backtest_options=options,
            )
            > 0.0
            if final_answer is not None and final_answer.option is not None
            else False
        ),
        "final_answer_stake_efficiency_penalty_option_count": sum(
            1
            for option in completed_options
            if _final_answer_stake_efficiency_penalty_score(
                option,
                backtest_options=options,
            )
            > 0.0
        ),
        "dynamic_mix_final_answer_lane": options.dynamic_mix_final_answer_lane,
        "dynamic_mix_final_answer_lane_pass_types": list(
            options.dynamic_mix_final_answer_lane_pass_types
        ),
        "dynamic_mix_final_answer_lane_effective_pass_types": list(
            _dynamic_mix_final_answer_lane_pass_types(options)
        ),
        "dynamic_mix_final_answer_lane_effective_constraint_profiles": [
            profile.model_dump(mode="json")
            for profile in _dynamic_mix_final_answer_lane_effective_constraint_profiles(
                options
            )
        ],
        "dynamic_mix_final_answer_lane_mode": (
            options.dynamic_mix_final_answer_lane_mode
        ),
        "dynamic_mix_final_answer_lane_modes": list(
            _dynamic_mix_final_answer_lane_modes(options)
        ),
        "dynamic_mix_final_answer_lane_admitted_pass_types": list(
            options.dynamic_mix_final_answer_lane_admitted_pass_types
        ),
        "dynamic_mix_final_answer_lane_blocked_pass_types": list(
            options.dynamic_mix_final_answer_lane_blocked_pass_types
        ),
        "dynamic_mix_final_answer_lane_constraint_profiles": [
            profile.model_dump(mode="json")
            for profile in options.dynamic_mix_final_answer_lane_constraint_profiles
        ],
        "dynamic_mix_final_answer_lane_min_market_count": (
            options.dynamic_mix_final_answer_lane_min_market_count
        ),
        "dynamic_mix_final_answer_lane_candidate_limit": (
            options.dynamic_mix_final_answer_lane_candidate_limit
        ),
        "dynamic_mix_final_answer_lane_solver_search": (
            options.dynamic_mix_final_answer_lane_solver_search
        ),
        "dynamic_mix_final_answer_lane_min_probability": (
            options.dynamic_mix_final_answer_lane_min_probability
        ),
        "dynamic_mix_final_answer_lane_score_boost": (
            options.dynamic_mix_final_answer_lane_score_boost
        ),
        "dynamic_mix_final_answer_lane_max_hit_probability_deficit": (
            options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
        ),
        "dynamic_mix_final_answer_lane_min_roi_delta": (
            options.dynamic_mix_final_answer_lane_min_roi_delta
        ),
        "completed_dynamic_mix_final_answer_lane_count": sum(
            1 for result in completed if _is_dynamic_mix_final_answer_lane_result(result)
        ),
        "dynamic_mix_final_answer_lane_quality_guard_blocked_option_count": (
            _dynamic_mix_final_answer_lane_quality_guard_blocked_option_count(
                completed_options,
                backtest_options=options,
            )
        ),
        "final_answer_dynamic_mix_final_answer_lane": (
            final_answer_is_dynamic_mix_lane
        ),
        "final_answer_dynamic_mix_final_answer_lane_hit_probability_deficit": (
            _final_answer_dynamic_mix_lane_hit_probability_deficit(
                final_answer,
                completed=completed,
                backtest_options=options,
            )
        ),
        "final_answer_dynamic_mix_final_answer_lane_selected_candidate_count": (
            len(final_answer_selected) if final_answer_is_dynamic_mix_lane else 0
        ),
        "final_answer_dynamic_mix_final_answer_lane_selected_fixture_ids": (
            sorted(candidate.fixture_id for candidate in final_answer_selected)
            if final_answer_is_dynamic_mix_lane
            else []
        ),
        "correct_score_final_answer_lane": options.correct_score_final_answer_lane,
        "correct_score_final_answer_lane_pass_types": list(
            options.correct_score_final_answer_lane_pass_types
        ),
        "correct_score_final_answer_lane_mode": (
            options.correct_score_final_answer_lane_mode
        ),
        "correct_score_final_answer_lane_modes": list(
            _correct_score_final_answer_lane_modes(options)
        ),
        "correct_score_final_answer_lane_candidate_limit": (
            options.correct_score_final_answer_lane_candidate_limit
        ),
        "correct_score_final_answer_lane_min_probability": (
            options.correct_score_final_answer_lane_min_probability
        ),
        "correct_score_final_answer_lane_min_correct_score_probability": (
            options.correct_score_final_answer_lane_min_correct_score_probability
        ),
        "correct_score_final_answer_lane_max_correct_score_per_selection": (
            options.correct_score_final_answer_lane_max_correct_score_per_selection
        ),
        "correct_score_final_answer_lane_score_boost": (
            options.correct_score_final_answer_lane_score_boost
        ),
        "correct_score_final_answer_lane_max_hit_probability_deficit": (
            options.correct_score_final_answer_lane_max_hit_probability_deficit
        ),
        "correct_score_final_answer_lane_min_roi_delta": (
            options.correct_score_final_answer_lane_min_roi_delta
        ),
        "correct_score_final_answer_lane_outcomes": list(
            options.correct_score_final_answer_lane_outcomes
        ),
        "correct_score_final_answer_lane_candidate_count": len(
            eligible_correct_score_lane_candidates
        ),
        "correct_score_final_answer_lane_fixture_count": len(
            {candidate.fixture_id for candidate in eligible_correct_score_lane_candidates}
        ),
        "candidate_pool_correct_score_final_answer_lane_candidate_count": len(
            candidate_pool_correct_score_lane_candidates
        ),
        "candidate_pool_correct_score_final_answer_lane_fixture_count": len(
            {
                candidate.fixture_id
                for candidate in candidate_pool_correct_score_lane_candidates
            }
        ),
        "completed_correct_score_final_answer_lane_count": sum(
            1
            for result in completed
            if _is_correct_score_final_answer_lane_result(result)
        ),
        "correct_score_final_answer_lane_quality_guard_blocked_option_count": (
            _correct_score_final_answer_lane_quality_guard_blocked_option_count(
                completed_options,
                backtest_options=options,
            )
        ),
        "final_answer_correct_score_final_answer_lane": (
            final_answer_is_correct_score_lane
        ),
        "final_answer_correct_score_final_answer_lane_hit_probability_deficit": (
            _final_answer_correct_score_lane_hit_probability_deficit(
                final_answer,
                completed=completed,
                backtest_options=options,
            )
        ),
        "final_answer_correct_score_final_answer_lane_selected_candidate_count": len(
            final_answer_correct_score_lane_candidates
        ),
        "final_answer_correct_score_final_answer_lane_selected_fixture_ids": sorted(
            {candidate.fixture_id for candidate in final_answer_correct_score_lane_candidates}
        ),
        "market_context_fragile_favorite_selection_count": (
            _market_context_fragile_favorite_selection_count(completed)
        ),
        "final_answer_competition_profile_version": (
            default_competition_recommendation_profile_version()
        ),
        "completed_count": len(completed),
        "scenario_hit_sample_size": len(completed),
        "scenario_hit_count": sum(1 for result in completed if result.actual_hit),
        "scenario_hit_rate": _ratio(
            sum(1 for result in completed if result.actual_hit),
            len(completed),
        ),
        "scenario_total_stake": sum(result.total_stake for result in completed),
        "scenario_actual_return": sum(result.actual_return for result in completed),
        "scenario_profit_loss": sum(result.profit_loss for result in completed),
        "scenario_roi": _float_ratio(
            sum(result.profit_loss for result in completed),
            sum(result.total_stake for result in completed),
        ),
        "pass_types": list(options.pass_types),
        "modes": list(options.modes),
        "unit_stake": options.unit_stake,
        "max_budget": options.max_budget,
        "strategy": options.strategy,
        "optimizer_profile": options.optimizer_profile,
        "solver_selected_scenario_count": sum(
            1
            for result in completed
            if result.selection_diagnostics_json.get("solver_selected") is True
        ),
        "final_answer_scenario_key": (
            final_answer.scenario.scenario_key if final_answer is not None else None
        ),
        "final_answer_selected_fixture_ids": (
            final_answer.selected_fixture_ids if final_answer is not None else []
        ),
        **final_answer_market_summary,
        "upset_opportunity_fixture_ids": sorted(upset_opportunities),
        "upset_capture_count": upset_capture_count,
        "result_source": historical_slice.metadata.result_source,
        "odds_source": historical_slice.metadata.odds_source,
        "prediction_source": historical_slice.metadata.prediction_source,
    }


def _marginal_loss_driver_candidate_soft_penalty_profile_candidates(
    candidates: Sequence[RecommendationCandidate],
) -> list[RecommendationCandidate]:
    return [
        candidate
        for candidate in candidates
        if _is_marginal_loss_driver_candidate_soft_penalty_profile(candidate)
    ]


def _final_answer_market_summary(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    candidate_count: int,
) -> dict[str, object]:
    if final_answer is None or final_answer.option is None:
        return {
            "final_answer_arbitration": None,
            "final_answer_market_types": [],
            "final_answer_market_count": 0,
            "final_answer_dynamic_mixed_market": False,
            "final_answer_selected_candidate_count": 0,
            "final_answer_multiple_choice_fixture_count": 0,
            "final_answer_has_handicap_market": False,
            "final_answer_has_correct_score_market": False,
        }

    payload = build_final_answer_arbitration_payload(
        final_answer.option,
        rank=1,
        candidate_count=candidate_count,
    )
    market_types = _payload_market_types(payload)
    return {
        "final_answer_arbitration": payload,
        "final_answer_market_types": market_types,
        "final_answer_market_count": len(market_types),
        "final_answer_dynamic_mixed_market": len(market_types) > 1,
        "final_answer_selected_candidate_count": _payload_int(
            payload,
            "selected_candidate_count",
        ),
        "final_answer_multiple_choice_fixture_count": _payload_int(
            payload,
            "multiple_choice_fixture_count",
        ),
        "final_answer_has_handicap_market": any(
            market_type in {"cn_handicap_1x2", "european_handicap_1x2"}
            for market_type in market_types
        ),
        "final_answer_has_correct_score_market": "correct_score" in market_types,
    }


def _payload_market_types(payload: Mapping[str, object]) -> list[str]:
    value = payload.get("market_types", [])
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if item is not None and str(item))


def _payload_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _is_marginal_loss_driver_candidate_soft_penalty_profile(
    candidate: RecommendationCandidate,
) -> bool:
    return candidate.metadata_json.get(
        "marginal_loss_driver_candidate_soft_penalty_basis"
    ) == "historical_marginal_loss_driver_candidate_soft_penalty_v3_1"


def _marginal_loss_driver_candidate_soft_penalty_fixture_exposure(
    candidates: Sequence[RecommendationCandidate],
    *,
    options: HistoricalRecommendationBacktestOptions,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> dict[str, object]:
    prefix = "marginal_loss_driver_candidate_soft_penalty_fixture_exposure"
    target_candidates = _marginal_loss_driver_candidate_soft_penalty_profile_candidates(
        candidates
    )
    target_candidate_identities = {
        _candidate_identity(candidate) for candidate in target_candidates
    }
    target_fixture_ids = {candidate.fixture_id for candidate in target_candidates}
    if not target_candidates:
        return _empty_fixture_exposure_summary(prefix)

    ranked = rank_candidates(
        candidates,
        config=policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    scored_by_fixture: dict[str, list[ScoredRecommendationCandidate]] = {}
    for scored in ranked:
        scored_by_fixture.setdefault(scored.candidate.fixture_id, []).append(scored)

    fixture_rows = [
        (fixture_id, _candidate_fixture_pool_sort_key(scored_candidates))
        for fixture_id, scored_candidates in scored_by_fixture.items()
    ]
    ordered_fixture_rows = sorted(
        fixture_rows,
        key=lambda item: item[1],
        reverse=True,
    )
    rank_by_fixture_id = {
        fixture_id: rank
        for rank, (fixture_id, _sort_key) in enumerate(ordered_fixture_rows, start=1)
    }
    rankable_target_fixture_ids = target_fixture_ids.intersection(rank_by_fixture_id)
    target_ranks = [
        rank_by_fixture_id[fixture_id]
        for fixture_id in rankable_target_fixture_ids
    ]
    candidate_fixture_limit = options.candidate_fixture_limit
    within_limit_fixture_ids = (
        {
            fixture_id
            for fixture_id in rankable_target_fixture_ids
            if rank_by_fixture_id[fixture_id] <= candidate_fixture_limit
        }
        if candidate_fixture_limit is not None
        else set(rankable_target_fixture_ids)
    )
    just_outside_fixture_ids = (
        {
            fixture_id
            for fixture_id in rankable_target_fixture_ids
            if candidate_fixture_limit
            < rank_by_fixture_id[fixture_id]
            <= candidate_fixture_limit
            + max(options.scenario_candidate_fixture_buffer or 0, 0)
        }
        if candidate_fixture_limit is not None
        else set()
    )
    best_target_fixture_id = _best_target_fixture_id(
        rankable_target_fixture_ids,
        rank_by_fixture_id=rank_by_fixture_id,
    )
    cutoff_sort_key = _cutoff_fixture_sort_key(
        ordered_fixture_rows,
        candidate_fixture_limit=candidate_fixture_limit,
    )
    best_target_sort_key = (
        _fixture_sort_key_by_fixture_id(ordered_fixture_rows).get(best_target_fixture_id)
        if best_target_fixture_id is not None
        else None
    )
    rankable_target_candidate_count = sum(
        1
        for scored in ranked
        if _candidate_identity(scored.candidate) in target_candidate_identities
    )
    exclusion_reason_counts = Counter(
        reason
        for candidate in target_candidates
        if (
            reason := _candidate_pool_policy_exclusion_reason(
                candidate,
                policy_config=policy_config,
                as_of_time_utc=as_of_time_utc,
            )
        )
        is not None
    )
    return {
        f"{prefix}_eligible_candidate_count": len(target_candidates),
        f"{prefix}_eligible_fixture_count": len(target_fixture_ids),
        f"{prefix}_rankable_candidate_count": rankable_target_candidate_count,
        f"{prefix}_excluded_candidate_count": sum(exclusion_reason_counts.values()),
        f"{prefix}_exclusion_reason_counts": dict(sorted(exclusion_reason_counts.items())),
        f"{prefix}_rankable_fixture_count": len(rankable_target_fixture_ids),
        f"{prefix}_within_candidate_fixture_limit_count": len(
            within_limit_fixture_ids
        ),
        f"{prefix}_just_outside_candidate_fixture_limit_count": len(
            just_outside_fixture_ids
        ),
        f"{prefix}_rank_min": min(target_ranks) if target_ranks else None,
        f"{prefix}_rank_average": _average_float(target_ranks),
        f"{prefix}_rank_max": max(target_ranks) if target_ranks else None,
        f"{prefix}_best_rank_gap_to_limit": _rank_gap_to_limit(
            target_ranks,
            candidate_fixture_limit=candidate_fixture_limit,
        ),
        f"{prefix}_best_fixture_id": best_target_fixture_id,
        f"{prefix}_best_fixture_top_score": (
            best_target_sort_key[0] if best_target_sort_key is not None else None
        ),
        f"{prefix}_cutoff_fixture_top_score": (
            cutoff_sort_key[0] if cutoff_sort_key is not None else None
        ),
        f"{prefix}_best_fixture_top_score_gap_to_cutoff": (
            best_target_sort_key[0] - cutoff_sort_key[0]
            if best_target_sort_key is not None and cutoff_sort_key is not None
            else None
        ),
    }


def _empty_fixture_exposure_summary(prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_eligible_candidate_count": 0,
        f"{prefix}_eligible_fixture_count": 0,
        f"{prefix}_rankable_candidate_count": 0,
        f"{prefix}_excluded_candidate_count": 0,
        f"{prefix}_exclusion_reason_counts": {},
        f"{prefix}_rankable_fixture_count": 0,
        f"{prefix}_within_candidate_fixture_limit_count": 0,
        f"{prefix}_just_outside_candidate_fixture_limit_count": 0,
        f"{prefix}_rank_min": None,
        f"{prefix}_rank_average": None,
        f"{prefix}_rank_max": None,
        f"{prefix}_best_rank_gap_to_limit": None,
        f"{prefix}_best_fixture_id": None,
        f"{prefix}_best_fixture_top_score": None,
        f"{prefix}_cutoff_fixture_top_score": None,
        f"{prefix}_best_fixture_top_score_gap_to_cutoff": None,
    }


def _best_target_fixture_id(
    fixture_ids: set[str],
    *,
    rank_by_fixture_id: Mapping[str, int],
) -> str | None:
    if not fixture_ids:
        return None
    return min(fixture_ids, key=lambda fixture_id: rank_by_fixture_id[fixture_id])


def _cutoff_fixture_sort_key(
    ordered_fixture_rows: Sequence[tuple[str, tuple[float, float, float, str]]],
    *,
    candidate_fixture_limit: int | None,
) -> tuple[float, float, float, str] | None:
    if candidate_fixture_limit is None or candidate_fixture_limit <= 0:
        return None
    if len(ordered_fixture_rows) < candidate_fixture_limit:
        return None
    return ordered_fixture_rows[candidate_fixture_limit - 1][1]


def _fixture_sort_key_by_fixture_id(
    ordered_fixture_rows: Sequence[tuple[str, tuple[float, float, float, str]]],
) -> dict[str, tuple[float, float, float, str]]:
    return {
        fixture_id: sort_key
        for fixture_id, sort_key in ordered_fixture_rows
    }


def _rank_gap_to_limit(
    ranks: Sequence[int],
    *,
    candidate_fixture_limit: int | None,
) -> int | None:
    if candidate_fixture_limit is None or not ranks:
        return None
    return min(ranks) - candidate_fixture_limit


def _average_float(values: Iterable[int | float]) -> float | None:
    collected = [float(value) for value in values]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _candidate_pool_policy_exclusion_reason(
    candidate: RecommendationCandidate,
    *,
    policy_config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
) -> str | None:
    if candidate.market_type not in policy_config.allowed_markets:
        return "market_not_allowed"
    if candidate.probability < policy_config.min_probability:
        return "probability_too_low"
    if candidate.data_quality_score < candidate_min_data_quality_score(
        candidate,
        policy_config,
    ):
        return "data_quality_too_low"
    if candidate.model_confidence_score < policy_config.min_model_confidence_score:
        return "model_confidence_too_low"
    if candidate.calibration_score < policy_config.min_calibration_score:
        return "calibration_too_low"
    if (
        policy_config.min_model_edge is not None
        and candidate.effective_model_edge() < policy_config.min_model_edge
    ):
        return "model_edge_too_low"
    if policy_config.require_odds_for_parlay and candidate.decimal_odds is None:
        return "odds_missing"
    if candidate.has_started(as_of_time_utc):
        return "fixture_already_started"
    return None


def _market_context_fragile_favorite_selection_count(
    completed: Sequence[HistoricalRecommendationScenarioResult],
) -> int:
    count = 0
    for result in completed:
        if result.option is None:
            continue
        for scored in result.option.selection.selected_candidates:
            metadata = scored.candidate.metadata_json
            if metadata.get("is_market_favorite") is not True:
                continue
            if _metadata_score(metadata, "market_context_favorite_fragility_score") >= 0.28:
                count += 1
    return count


def _backtest_warnings(
    scenario_results: Sequence[HistoricalRecommendationScenarioResult],
    *,
    final_answer: HistoricalRecommendationScenarioResult | None,
) -> list[str]:
    warnings = [
        f"scenario_failed:{result.scenario.scenario_key}:{result.error_message}"
        for result in scenario_results
        if result.status == "failed" and result.error_message is not None
    ]
    if final_answer is None:
        warnings.append("historical_backtest_no_final_answer")
    return warnings


def _scenario_result_for_option(
    option: RecommendationGlobalPlanOption,
    scenario_results: Sequence[HistoricalRecommendationScenarioResult],
) -> HistoricalRecommendationScenarioResult | None:
    for result in scenario_results:
        if result.option is not None and result.option.option_key == option.option_key:
            return result
    return None


def _rank_historical_final_answer_options(
    final_answer_options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> list[RecommendationGlobalPlanOption]:
    if (
        not backtest_options.final_answer_quality_signal_penalty
        and not backtest_options.final_answer_selection_value_signal
        and not backtest_options.final_answer_segment_penalty
        and not backtest_options.final_answer_stake_efficiency_guard
        and backtest_options.upset_final_answer_lane_score_boost == 0.0
        and backtest_options.upset_final_answer_lane_max_hit_probability_deficit is None
        and backtest_options.dynamic_mix_final_answer_lane_score_boost == 0.0
        and (
            backtest_options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
            is None
        )
        and backtest_options.dynamic_mix_final_answer_lane_min_roi_delta is None
        and backtest_options.correct_score_final_answer_lane_score_boost == 0.0
        and (
            backtest_options.correct_score_final_answer_lane_max_hit_probability_deficit
            is None
        )
        and backtest_options.correct_score_final_answer_lane_min_roi_delta is None
    ):
        return rank_final_answer_options(final_answer_options)
    reference_option = _best_non_upset_lane_reference_option(
        final_answer_options,
        backtest_options=backtest_options,
    )
    return sorted(
        final_answer_options,
        key=lambda option: _historical_adjusted_final_answer_sort_key(
            option,
            backtest_options=backtest_options,
            reference_option=reference_option,
        ),
        reverse=True,
    )


def _historical_adjusted_final_answer_sort_key(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    reference_option: RecommendationGlobalPlanOption | None = None,
) -> tuple[float, float, float, float, float, int]:
    evaluation = option.selection.evaluation
    base_score = score_final_answer_option(option).final_answer_score
    penalty = _final_answer_quality_signal_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    selection_value_adjustment = _final_answer_selection_value_signal_score(
        option,
        backtest_options=backtest_options,
        reference_option=reference_option,
    )
    segment_penalty = _final_answer_segment_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    stake_efficiency_penalty = _final_answer_stake_efficiency_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    boost = _upset_final_answer_lane_sort_boost(
        option,
        backtest_options=backtest_options,
        reference_option=reference_option,
    )
    dynamic_mix_boost = _dynamic_mix_final_answer_lane_sort_boost(
        option,
        backtest_options=backtest_options,
        reference_option=reference_option,
    )
    correct_score_boost = _correct_score_final_answer_lane_sort_boost(
        option,
        backtest_options=backtest_options,
        reference_option=reference_option,
    )
    data_quality = _average(
        item.candidate.data_quality_score for item in option.selection.selected_candidates
    )
    adjusted_score = _clamp(
        base_score
        - penalty
        - segment_penalty
        - stake_efficiency_penalty
        + boost
        + dynamic_mix_boost
        + correct_score_boost
        + selection_value_adjustment
    )
    if _dynamic_mix_final_answer_lane_quality_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        adjusted_score = -1.0
    if _correct_score_final_answer_lane_quality_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        adjusted_score = -1.0
    if _upset_final_answer_lane_calibration_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        adjusted_score = -1.0
    return (
        adjusted_score,
        evaluation.hit_probability,
        evaluation.roi,
        1.0 - evaluation.risk_score,
        data_quality / 100.0 if data_quality is not None else 0.0,
        len(option.selection.fixture_ids),
    )


def _upset_final_answer_lane_sort_boost(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    reference_option: RecommendationGlobalPlanOption | None = None,
) -> float:
    if backtest_options.upset_final_answer_lane_score_boost == 0.0:
        return 0.0
    if not _is_upset_final_answer_lane_option(option):
        return 0.0
    if _upset_final_answer_lane_calibration_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        return 0.0
    return backtest_options.upset_final_answer_lane_score_boost


def _dynamic_mix_final_answer_lane_sort_boost(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    reference_option: RecommendationGlobalPlanOption | None = None,
) -> float:
    if backtest_options.dynamic_mix_final_answer_lane_score_boost == 0.0:
        return 0.0
    if not _is_dynamic_mix_final_answer_lane_option(option):
        return 0.0
    if _dynamic_mix_final_answer_lane_quality_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        return 0.0
    return backtest_options.dynamic_mix_final_answer_lane_score_boost


def _correct_score_final_answer_lane_sort_boost(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    reference_option: RecommendationGlobalPlanOption | None = None,
) -> float:
    if backtest_options.correct_score_final_answer_lane_score_boost == 0.0:
        return 0.0
    if not _is_correct_score_final_answer_lane_option(option):
        return 0.0
    if _correct_score_final_answer_lane_quality_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        return 0.0
    return backtest_options.correct_score_final_answer_lane_score_boost


def _dynamic_mix_final_answer_lane_quality_guard_blocks(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption | None,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not _is_dynamic_mix_final_answer_lane_option(option):
        return False
    if reference_option is None:
        return False
    max_deficit = backtest_options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
    if (
        max_deficit is not None
        and _hit_probability_deficit(option, reference_option=reference_option) > max_deficit
    ):
        return True
    min_roi_delta = backtest_options.dynamic_mix_final_answer_lane_min_roi_delta
    if min_roi_delta is None:
        return False
    return (
        option.selection.evaluation.roi - reference_option.selection.evaluation.roi
        < min_roi_delta
    )


def _correct_score_final_answer_lane_quality_guard_blocks(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption | None,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not _is_correct_score_final_answer_lane_option(option):
        return False
    if reference_option is None:
        return False
    max_deficit = backtest_options.correct_score_final_answer_lane_max_hit_probability_deficit
    if (
        max_deficit is not None
        and _hit_probability_deficit(option, reference_option=reference_option) > max_deficit
    ):
        return True
    min_roi_delta = backtest_options.correct_score_final_answer_lane_min_roi_delta
    if min_roi_delta is None:
        return False
    return (
        option.selection.evaluation.roi - reference_option.selection.evaluation.roi
        < min_roi_delta
    )


def _hit_probability_deficit(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption,
) -> float:
    return max(
        0.0,
        reference_option.selection.evaluation.hit_probability
        - option.selection.evaluation.hit_probability,
    )


def _is_dynamic_mix_final_answer_lane_option(
    option: RecommendationGlobalPlanOption,
) -> bool:
    return "dynamic_mix_final_answer_lane" in option.reason_codes


def _is_correct_score_final_answer_lane_option(
    option: RecommendationGlobalPlanOption,
) -> bool:
    return "correct_score_final_answer_lane" in option.reason_codes


def _best_non_upset_lane_reference_option(
    final_answer_options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    include_selection_value_signal: bool = False,
) -> RecommendationGlobalPlanOption | None:
    non_lane_options = [
        option
        for option in final_answer_options
        if not _is_upset_final_answer_lane_option(option)
        and not _is_dynamic_mix_final_answer_lane_option(option)
        and not _is_correct_score_final_answer_lane_option(option)
    ]
    if not non_lane_options:
        return None
    return max(
        non_lane_options,
        key=lambda option: _historical_non_lane_reference_sort_key(
            option,
            backtest_options=backtest_options,
            include_selection_value_signal=include_selection_value_signal,
        ),
    )


def _historical_non_lane_reference_sort_key(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    include_selection_value_signal: bool = True,
) -> tuple[float, float, float, float, float, int]:
    evaluation = option.selection.evaluation
    base_score = score_final_answer_option(option).final_answer_score
    penalty = _final_answer_quality_signal_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    selection_value_adjustment = (
        _final_answer_selection_value_signal_score(
            option,
            backtest_options=backtest_options,
        )
        if include_selection_value_signal
        else 0.0
    )
    segment_penalty = _final_answer_segment_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    stake_efficiency_penalty = _final_answer_stake_efficiency_penalty_score(
        option,
        backtest_options=backtest_options,
    )
    data_quality = _average(
        item.candidate.data_quality_score for item in option.selection.selected_candidates
    )
    return (
        _clamp(
            base_score
            - penalty
            - segment_penalty
            - stake_efficiency_penalty
            + selection_value_adjustment
        ),
        evaluation.hit_probability,
        evaluation.roi,
        1.0 - evaluation.risk_score,
        data_quality / 100.0 if data_quality is not None else 0.0,
        len(option.selection.fixture_ids),
    )


def _upset_final_answer_lane_calibration_guard_blocks(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption | None,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    max_deficit = backtest_options.upset_final_answer_lane_max_hit_probability_deficit
    if max_deficit is None:
        return False
    if not _is_upset_final_answer_lane_option(option) or reference_option is None:
        return False
    return (
        _upset_final_answer_lane_hit_probability_deficit(
            option,
            reference_option=reference_option,
        )
        > max_deficit
    )


def _upset_final_answer_lane_hit_probability_deficit(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption,
) -> float:
    return max(
        0.0,
        reference_option.selection.evaluation.hit_probability
        - option.selection.evaluation.hit_probability,
    )


def _upset_final_answer_lane_calibration_guard_blocked_option_count(
    options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    reference_option = _best_non_upset_lane_reference_option(
        options,
        backtest_options=backtest_options,
    )
    return sum(
        1
        for option in options
        if _upset_final_answer_lane_calibration_guard_blocks(
            option,
            reference_option=reference_option,
            backtest_options=backtest_options,
        )
    )


def _dynamic_mix_final_answer_lane_quality_guard_blocked_option_count(
    options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    reference_option = _best_non_upset_lane_reference_option(
        options,
        backtest_options=backtest_options,
    )
    return sum(
        1
        for option in options
        if _dynamic_mix_final_answer_lane_quality_guard_blocks(
            option,
            reference_option=reference_option,
            backtest_options=backtest_options,
        )
    )


def _correct_score_final_answer_lane_quality_guard_blocked_option_count(
    options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    reference_option = _best_non_upset_lane_reference_option(
        options,
        backtest_options=backtest_options,
    )
    return sum(
        1
        for option in options
        if _correct_score_final_answer_lane_quality_guard_blocks(
            option,
            reference_option=reference_option,
            backtest_options=backtest_options,
        )
    )


def _final_answer_upset_lane_hit_probability_deficit(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    completed: Sequence[HistoricalRecommendationScenarioResult],
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float | None:
    if not _is_upset_final_answer_lane_result(final_answer):
        return None
    if final_answer is None or final_answer.option is None:
        return None
    reference_option = _best_non_upset_lane_reference_option(
        [result.option for result in completed if result.option is not None],
        backtest_options=backtest_options,
    )
    if reference_option is None:
        return None
    return _upset_final_answer_lane_hit_probability_deficit(
        final_answer.option,
        reference_option=reference_option,
    )


def _final_answer_dynamic_mix_lane_hit_probability_deficit(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    completed: Sequence[HistoricalRecommendationScenarioResult],
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float | None:
    if not _is_dynamic_mix_final_answer_lane_result(final_answer):
        return None
    if final_answer is None or final_answer.option is None:
        return None
    reference_option = _best_non_upset_lane_reference_option(
        [result.option for result in completed if result.option is not None],
        backtest_options=backtest_options,
    )
    if reference_option is None:
        return None
    return _hit_probability_deficit(
        final_answer.option,
        reference_option=reference_option,
    )


def _final_answer_correct_score_lane_hit_probability_deficit(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    completed: Sequence[HistoricalRecommendationScenarioResult],
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float | None:
    if not _is_correct_score_final_answer_lane_result(final_answer):
        return None
    if final_answer is None or final_answer.option is None:
        return None
    reference_option = _best_non_upset_lane_reference_option(
        [result.option for result in completed if result.option is not None],
        backtest_options=backtest_options,
    )
    if reference_option is None:
        return None
    return _hit_probability_deficit(
        final_answer.option,
        reference_option=reference_option,
    )


def _is_upset_final_answer_lane_result(
    result: HistoricalRecommendationScenarioResult | None,
) -> bool:
    return (
        result is not None
        and result.option is not None
        and _is_upset_final_answer_lane_option(result.option)
    )


def _is_upset_final_answer_lane_option(
    option: RecommendationGlobalPlanOption,
) -> bool:
    return option.explanation_json.get(
        "upset_final_answer_lane"
    ) is not None or option.option_key.startswith("historical:upset_lane:")


def _is_dynamic_mix_final_answer_lane_result(
    result: HistoricalRecommendationScenarioResult | None,
) -> bool:
    return (
        result is not None
        and result.option is not None
        and _is_dynamic_mix_final_answer_lane_option(result.option)
    )


def _is_correct_score_final_answer_lane_result(
    result: HistoricalRecommendationScenarioResult | None,
) -> bool:
    return (
        result is not None
        and result.option is not None
        and _is_correct_score_final_answer_lane_option(result.option)
    )


def _final_answer_quality_signal_penalty_score(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float:
    if not backtest_options.final_answer_quality_signal_penalty:
        return 0.0
    selected = option.selection.selected_candidates
    if not selected:
        return 0.0
    affected_count = sum(
        1
        for scored in selected
        if _final_answer_quality_signal_penalty_applies_to_scored(
            scored,
            backtest_options=backtest_options,
        )
    )
    if affected_count == 0:
        return 0.0
    exposure = affected_count / len(selected)
    return _clamp(backtest_options.final_answer_quality_signal_penalty_strength * exposure)


def _final_answer_quality_signal_penalty_applies(
    candidate: RecommendationCandidate,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    allowed_competition_ids = set(backtest_options.final_answer_quality_signal_competition_ids)
    if (
        allowed_competition_ids
        and _candidate_competition_id(candidate) not in allowed_competition_ids
    ):
        return False
    if candidate.decimal_odds is None:
        return False
    if candidate.decimal_odds < backtest_options.final_answer_quality_signal_min_decimal_odds:
        return False
    if candidate.decimal_odds > backtest_options.final_answer_quality_signal_max_decimal_odds:
        return False
    if candidate.probability < backtest_options.final_answer_quality_signal_probability_min:
        return False
    if candidate.probability >= backtest_options.final_answer_quality_signal_probability_max:
        return False
    return (
        candidate.effective_model_edge()
        < backtest_options.final_answer_quality_signal_max_model_edge
    )


def _final_answer_quality_signal_penalty_applies_to_scored(
    scored: ScoredRecommendationCandidate,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not _final_answer_quality_signal_penalty_applies(
        scored.candidate,
        backtest_options=backtest_options,
    ):
        return False
    if scored.score < backtest_options.final_answer_quality_signal_score_min:
        return False
    return scored.score <= backtest_options.final_answer_quality_signal_score_max


def _final_answer_quality_signal_penalty_affected_leg_count(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    if final_answer is None or final_answer.option is None:
        return 0
    return sum(
        1
        for scored in final_answer.option.selection.selected_candidates
        if _final_answer_quality_signal_penalty_applies_to_scored(
            scored,
            backtest_options=backtest_options,
        )
    )


def _final_answer_selection_value_signal_score(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
    reference_option: RecommendationGlobalPlanOption | None = None,
) -> float:
    if not backtest_options.final_answer_selection_value_signal:
        return 0.0
    if _final_answer_selection_value_signal_option_guard_blocks(
        option,
        reference_option=reference_option,
        backtest_options=backtest_options,
    ):
        return 0.0
    selected = option.selection.selected_candidates
    if not selected:
        return 0.0
    affected_count = sum(
        1
        for scored in selected
        if _final_answer_selection_value_signal_applies_to_scored(
            scored,
            backtest_options=backtest_options,
        )
    )
    if affected_count == 0:
        return 0.0
    exposure = affected_count / len(selected)
    return max(
        -1.0,
        min(1.0, backtest_options.final_answer_selection_value_signal_strength * exposure),
    )


def _final_answer_selection_value_signal_option_guard_blocks(
    option: RecommendationGlobalPlanOption,
    *,
    reference_option: RecommendationGlobalPlanOption | None = None,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not backtest_options.final_answer_selection_value_signal:
        return False
    min_roi = backtest_options.final_answer_selection_value_signal_min_option_roi
    if min_roi is not None and option.selection.evaluation.roi < min_roi:
        return True
    max_risk = backtest_options.final_answer_selection_value_signal_max_option_risk_score
    if max_risk is not None and option.selection.evaluation.risk_score > max_risk:
        return True
    max_deficit = (
        backtest_options.final_answer_selection_value_signal_max_hit_probability_deficit
    )
    if max_deficit is None or reference_option is None:
        return False
    deficit = max(
        0.0,
        reference_option.selection.evaluation.hit_probability
        - option.selection.evaluation.hit_probability,
    )
    return deficit > max_deficit


def _final_answer_selection_value_signal_guard_blocked_option_count(
    options: Sequence[RecommendationGlobalPlanOption],
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    if not backtest_options.final_answer_selection_value_signal:
        return 0
    reference_option = _best_non_upset_lane_reference_option(
        options,
        backtest_options=backtest_options,
        include_selection_value_signal=False,
    )
    return sum(
        1
        for option in options
        if _final_answer_selection_value_signal_option_guard_blocks(
            option,
            reference_option=reference_option,
            backtest_options=backtest_options,
        )
    )


def _final_answer_selection_value_signal_applies(
    candidate: RecommendationCandidate,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    allowed_competition_ids = set(
        backtest_options.final_answer_selection_value_signal_competition_ids
    )
    if (
        allowed_competition_ids
        and _candidate_competition_id(candidate) not in allowed_competition_ids
    ):
        return False
    allowed_outcomes = set(backtest_options.final_answer_selection_value_signal_outcomes)
    if allowed_outcomes and candidate.outcome not in allowed_outcomes:
        return False
    if candidate.decimal_odds is None:
        return False
    if (
        candidate.decimal_odds
        < backtest_options.final_answer_selection_value_signal_min_decimal_odds
    ):
        return False
    if (
        candidate.decimal_odds
        > backtest_options.final_answer_selection_value_signal_max_decimal_odds
    ):
        return False
    if (
        candidate.probability
        < backtest_options.final_answer_selection_value_signal_probability_min
    ):
        return False
    if (
        candidate.probability
        >= backtest_options.final_answer_selection_value_signal_probability_max
    ):
        return False
    max_model_edge = backtest_options.final_answer_selection_value_signal_max_model_edge
    return max_model_edge is None or candidate.effective_model_edge() < max_model_edge


def _final_answer_selection_value_signal_applies_to_scored(
    scored: ScoredRecommendationCandidate,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not _final_answer_selection_value_signal_applies(
        scored.candidate,
        backtest_options=backtest_options,
    ):
        return False
    if scored.score < backtest_options.final_answer_selection_value_signal_score_min:
        return False
    return scored.score <= backtest_options.final_answer_selection_value_signal_score_max


def _final_answer_selection_value_signal_affected_leg_count(
    final_answer: HistoricalRecommendationScenarioResult | None,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> int:
    if final_answer is None or final_answer.option is None:
        return 0
    return sum(
        1
        for scored in final_answer.option.selection.selected_candidates
        if _final_answer_selection_value_signal_applies_to_scored(
            scored,
            backtest_options=backtest_options,
        )
    )


def _final_answer_segment_penalty_score(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float:
    if not _final_answer_segment_penalty_applies(option, backtest_options=backtest_options):
        return 0.0
    return _clamp(backtest_options.final_answer_segment_penalty_strength)


def _final_answer_segment_penalty_applies(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not backtest_options.final_answer_segment_penalty:
        return False
    if (
        backtest_options.final_answer_segment_pass_types
        and option.pass_type not in backtest_options.final_answer_segment_pass_types
    ):
        return False
    if (
        backtest_options.final_answer_segment_modes
        and option.mode not in backtest_options.final_answer_segment_modes
    ):
        return False
    if not _option_competition_applies(
        option,
        competition_ids=backtest_options.final_answer_segment_competition_ids,
    ):
        return False
    if not _option_season_applies(
        option,
        season_ids=backtest_options.final_answer_segment_season_ids,
    ):
        return False
    if not _option_competition_season_index_applies(
        option,
        minimum=backtest_options.final_answer_segment_min_competition_season_index,
        maximum=backtest_options.final_answer_segment_max_competition_season_index,
    ):
        return False
    evaluation = option.selection.evaluation
    if (
        backtest_options.final_answer_segment_min_hit_probability is not None
        and evaluation.hit_probability
        < backtest_options.final_answer_segment_min_hit_probability
    ):
        return False
    if (
        backtest_options.final_answer_segment_max_hit_probability is not None
        and evaluation.hit_probability
        >= backtest_options.final_answer_segment_max_hit_probability
    ):
        return False
    odds_product = _option_odds_product(option)
    if (
        backtest_options.final_answer_segment_min_odds_product is not None
        and (
            odds_product is None
            or odds_product < backtest_options.final_answer_segment_min_odds_product
        )
    ):
        return False
    if (
        backtest_options.final_answer_segment_max_odds_product is not None
        and (
            odds_product is None
            or odds_product > backtest_options.final_answer_segment_max_odds_product
        )
    ):
        return False
    average_leg_odds = _option_average_leg_decimal_odds(option)
    if (
        backtest_options.final_answer_segment_min_average_leg_decimal_odds is not None
        and (
            average_leg_odds is None
            or average_leg_odds
            < backtest_options.final_answer_segment_min_average_leg_decimal_odds
        )
    ):
        return False
    if backtest_options.final_answer_segment_max_average_leg_decimal_odds is None:
        return True
    return (
        average_leg_odds is not None
        and average_leg_odds
        <= backtest_options.final_answer_segment_max_average_leg_decimal_odds
    )


def _final_answer_stake_efficiency_penalty_score(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> float:
    if not _final_answer_stake_efficiency_penalty_applies(
        option,
        backtest_options=backtest_options,
    ):
        return 0.0
    evaluation = option.selection.evaluation
    stake_multiplier = evaluation.total_stake / evaluation.unit_stake
    stake_excess = max(
        0.0,
        (
            stake_multiplier
            - backtest_options.final_answer_stake_efficiency_max_stake_multiplier
        )
        / backtest_options.final_answer_stake_efficiency_max_stake_multiplier,
    )
    roi_deficit = max(
        0.0,
        backtest_options.final_answer_stake_efficiency_min_roi - evaluation.roi,
    )
    exposure = _clamp(stake_excess + roi_deficit)
    return _clamp(
        backtest_options.final_answer_stake_efficiency_penalty_strength * exposure
    )


def _final_answer_stake_efficiency_penalty_applies(
    option: RecommendationGlobalPlanOption,
    *,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not backtest_options.final_answer_stake_efficiency_guard:
        return False
    if (
        backtest_options.final_answer_stake_efficiency_modes
        and option.mode not in backtest_options.final_answer_stake_efficiency_modes
    ):
        return False
    if (
        backtest_options.final_answer_stake_efficiency_scope
        == "quality_signal_affected"
        and (
            not backtest_options.final_answer_quality_signal_penalty
            or _final_answer_quality_signal_penalty_score(
                option,
                backtest_options=backtest_options,
            )
            <= 0.0
        )
    ):
        return False
    evaluation = option.selection.evaluation
    if evaluation.unit_stake <= 0.0 or evaluation.total_stake <= 0.0:
        return False
    stake_multiplier = evaluation.total_stake / evaluation.unit_stake
    if (
        stake_multiplier
        > backtest_options.final_answer_stake_efficiency_max_stake_multiplier
    ):
        return True
    return evaluation.roi < backtest_options.final_answer_stake_efficiency_min_roi


def _final_answer_stake_efficiency_stake_multiplier(
    option: RecommendationGlobalPlanOption | None,
) -> float | None:
    if option is None:
        return None
    evaluation = option.selection.evaluation
    if evaluation.unit_stake <= 0.0:
        return None
    return evaluation.total_stake / evaluation.unit_stake


def _option_competition_applies(
    option: RecommendationGlobalPlanOption,
    *,
    competition_ids: tuple[str, ...],
) -> bool:
    if not competition_ids:
        return True
    allowed = set(competition_ids)
    return any(
        _candidate_competition_id(scored.candidate) in allowed
        for scored in option.selection.selected_candidates
    )


def _option_season_applies(
    option: RecommendationGlobalPlanOption,
    *,
    season_ids: tuple[str, ...],
) -> bool:
    if not season_ids:
        return True
    allowed = set(season_ids)
    return any(
        _candidate_season_id(scored.candidate) in allowed
        for scored in option.selection.selected_candidates
    )


def _option_competition_season_index_applies(
    option: RecommendationGlobalPlanOption,
    *,
    minimum: int | None,
    maximum: int | None,
) -> bool:
    if minimum is None and maximum is None:
        return True
    for scored in option.selection.selected_candidates:
        index = _candidate_competition_season_index(scored.candidate)
        if index is None:
            continue
        if minimum is not None and index < minimum:
            continue
        if maximum is not None and index > maximum:
            continue
        return True
    return False


def _option_odds_product(option: RecommendationGlobalPlanOption) -> float | None:
    atomic_bets = option.selection.evaluation.atomic_bets
    if atomic_bets:
        return _average(atomic_bet.odds_product for atomic_bet in atomic_bets)
    product = 1.0
    for scored in option.selection.selected_candidates:
        if scored.candidate.decimal_odds is None:
            return None
        product *= scored.candidate.decimal_odds
    return product if product > 1.0 else None


def _option_average_leg_decimal_odds(
    option: RecommendationGlobalPlanOption,
) -> float | None:
    return _average(
        scored.candidate.decimal_odds
        for scored in option.selection.selected_candidates
        if scored.candidate.decimal_odds is not None
    )


def _selected_outcomes(selection: RecommendationSelection) -> dict[str, list[str]]:
    outcomes: dict[str, list[str]] = {}
    for scored in selection.selected_candidates:
        outcomes.setdefault(scored.candidate.fixture_id, []).append(scored.candidate.outcome)
    return outcomes


def _option_type(selection: RecommendationSelection) -> RecommendationPlanOptionType:
    if selection.pass_type == "1x1":
        return "standalone_single"
    if selection.mode == "multiple":
        return "multiple_parlay"
    return "single_parlay"


def _within_budget(evaluation: ParlayEvaluation) -> bool:
    budget_payload = evaluation.explanation_json.get("budget")
    if not isinstance(budget_payload, dict):
        return True
    return bool(budget_payload.get("within_budget", True))


def _binary_log_loss(probability: float, *, actual_hit: bool) -> float:
    clipped = max(1e-9, min(1.0 - 1e-9, probability))
    return -log(clipped if actual_hit else 1.0 - clipped)


def _backtest_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> str:
    payload = "|".join(
        [
            historical_slice.metadata.slice_id,
            historical_slice.as_of_time_utc.isoformat(),
            ",".join(options.pass_types),
            ",".join(options.modes),
            options.strategy,
            str(options.max_budget),
            str(options.min_data_quality_score),
            dumps(
                options.min_data_quality_score_by_competition_id,
                sort_keys=True,
            ),
            str(options.data_quality_beta_lane_enabled),
            ",".join(options.data_quality_beta_lane_competition_ids),
            ",".join(options.data_quality_beta_lane_season_ids),
            str(options.data_quality_beta_lane_min_competition_season_index),
            str(options.data_quality_beta_lane_max_competition_season_index),
            str(options.data_quality_beta_lane_min_probability),
            str(options.data_quality_beta_lane_max_decimal_odds),
            str(options.data_quality_beta_lane_min_model_edge),
            str(options.data_quality_beta_lane_min_model_confidence_score),
            str(options.data_quality_beta_lane_min_calibration_score),
            str(options.data_quality_beta_lane_min_odds_stability_score),
            str(options.data_quality_beta_lane_max_volatility_penalty),
            str(options.data_quality_beta_lane_probability_repair_enabled),
            str(options.data_quality_beta_lane_probability_repair_strength),
            str(options.data_quality_beta_lane_probability_repair_max_delta),
            str(
                options.data_quality_beta_lane_probability_repair_min_market_probability_delta
            ),
            str(options.data_quality_beta_lane_probability_repair_extra_uplift),
            str(
                options.data_quality_beta_lane_probability_repair_data_quality_gap_weight
            ),
            str(
                options.data_quality_beta_lane_probability_repair_odds_stability_weight
            ),
            str(options.data_quality_beta_lane_probability_repair_max_probability),
            options.optimizer_profile,
            str(options.candidate_fixture_limit),
            str(options.max_candidates_per_fixture),
            str(options.scenario_candidate_fixture_buffer),
            str(options.final_answer_scenario_variant_count),
            str(options.derive_market_context_signals),
            str(options.upset_exposure_reserve),
            str(options.upset_exposure_reserve_fixture_count),
            str(options.upset_exposure_reserve_max_candidates_per_fixture),
            str(options.upset_exposure_reserve_min_protection_score),
            str(options.upset_exposure_reserve_min_probability),
            str(options.upset_exposure_reserve_max_decimal_odds),
            str(options.upset_final_answer_lane),
            str(options.upset_final_answer_lane_pass_type),
            str(options.upset_final_answer_lane_mode),
            str(options.upset_final_answer_lane_candidate_limit),
            str(options.upset_final_answer_lane_min_protection_score),
            str(options.upset_final_answer_lane_min_probability),
            str(options.upset_final_answer_lane_min_decimal_odds),
            str(options.upset_final_answer_lane_max_decimal_odds),
            str(options.upset_final_answer_lane_min_model_edge),
            str(options.upset_final_answer_lane_max_model_edge),
            ",".join(options.upset_final_answer_lane_competition_ids),
            ",".join(options.upset_final_answer_lane_excluded_competition_ids),
            str(options.upset_final_answer_lane_min_calibration_score),
            str(options.upset_final_answer_lane_min_model_confidence_score),
            str(options.upset_final_answer_lane_min_odds_stability_score),
            str(options.upset_final_answer_lane_max_volatility_penalty),
            str(options.upset_final_answer_lane_max_hit_probability_deficit),
            str(options.upset_final_answer_lane_max_signal_calibration_risk),
            str(options.upset_final_answer_lane_min_signal_reliability_score),
            str(options.upset_final_answer_lane_score_boost),
            str(options.short_price_negative_edge_guardrail),
            str(options.short_price_negative_edge_max_decimal_odds),
            str(options.short_price_negative_edge_min_probability),
            str(options.short_price_negative_edge_max_model_edge),
            str(options.short_price_negative_edge_soft_penalty),
            str(options.short_price_negative_edge_soft_penalty_strength),
            ",".join(options.short_price_negative_edge_soft_penalty_competition_ids),
            str(options.marginal_loss_driver_candidate_guardrail),
            str(options.marginal_loss_driver_candidate_guardrail_probability_min),
            str(options.marginal_loss_driver_candidate_guardrail_probability_max),
            str(options.marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_edge),
            str(options.marginal_loss_driver_candidate_guardrail_max_calibration_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score),
            ",".join(options.marginal_loss_driver_candidate_guardrail_competition_ids),
            str(options.marginal_loss_driver_candidate_soft_penalty),
            str(options.marginal_loss_driver_candidate_soft_penalty_strength),
            str(options.final_answer_quality_signal_penalty),
            str(options.final_answer_quality_signal_penalty_strength),
            str(options.final_answer_quality_signal_probability_min),
            str(options.final_answer_quality_signal_probability_max),
            str(options.final_answer_quality_signal_min_decimal_odds),
            str(options.final_answer_quality_signal_max_decimal_odds),
            str(options.final_answer_quality_signal_max_model_edge),
            str(options.final_answer_quality_signal_score_min),
            str(options.final_answer_quality_signal_score_max),
            ",".join(options.final_answer_quality_signal_competition_ids),
            str(options.final_answer_selection_value_signal),
            str(options.final_answer_selection_value_signal_strength),
            str(options.final_answer_selection_value_signal_probability_min),
            str(options.final_answer_selection_value_signal_probability_max),
            str(options.final_answer_selection_value_signal_min_decimal_odds),
            str(options.final_answer_selection_value_signal_max_decimal_odds),
            str(options.final_answer_selection_value_signal_max_model_edge),
            str(options.final_answer_selection_value_signal_score_min),
            str(options.final_answer_selection_value_signal_score_max),
            ",".join(options.final_answer_selection_value_signal_competition_ids),
            ",".join(options.final_answer_selection_value_signal_outcomes),
            str(options.final_answer_selection_value_signal_max_hit_probability_deficit),
            str(options.final_answer_selection_value_signal_min_option_roi),
            str(options.final_answer_selection_value_signal_max_option_risk_score),
            str(options.final_answer_segment_penalty),
            str(options.final_answer_segment_penalty_strength),
            ",".join(options.final_answer_segment_pass_types),
            ",".join(options.final_answer_segment_modes),
            ",".join(options.final_answer_segment_competition_ids),
            ",".join(options.final_answer_segment_season_ids),
            str(options.final_answer_segment_min_competition_season_index),
            str(options.final_answer_segment_max_competition_season_index),
            str(options.final_answer_segment_min_hit_probability),
            str(options.final_answer_segment_max_hit_probability),
            str(options.final_answer_segment_min_odds_product),
            str(options.final_answer_segment_max_odds_product),
            str(options.final_answer_segment_min_average_leg_decimal_odds),
            str(options.final_answer_segment_max_average_leg_decimal_odds),
            str(options.final_answer_stake_efficiency_guard),
            str(options.final_answer_stake_efficiency_penalty_strength),
            str(options.final_answer_stake_efficiency_max_stake_multiplier),
            str(options.final_answer_stake_efficiency_min_roi),
            ",".join(options.final_answer_stake_efficiency_modes),
            options.final_answer_stake_efficiency_scope,
            str(options.dynamic_mix_final_answer_lane),
            ",".join(options.dynamic_mix_final_answer_lane_pass_types),
            str(options.dynamic_mix_final_answer_lane_mode),
            ",".join(options.dynamic_mix_final_answer_lane_modes),
            ",".join(options.dynamic_mix_final_answer_lane_admitted_pass_types),
            ",".join(options.dynamic_mix_final_answer_lane_blocked_pass_types),
            _dynamic_mix_final_answer_lane_constraint_profile_signature(options),
            str(options.dynamic_mix_final_answer_lane_min_market_count),
            str(options.dynamic_mix_final_answer_lane_candidate_limit),
            str(options.dynamic_mix_final_answer_lane_solver_search),
            str(options.dynamic_mix_final_answer_lane_min_probability),
            str(options.dynamic_mix_final_answer_lane_score_boost),
            str(options.dynamic_mix_final_answer_lane_max_hit_probability_deficit),
            str(options.dynamic_mix_final_answer_lane_min_roi_delta),
            str(options.correct_score_final_answer_lane),
            ",".join(options.correct_score_final_answer_lane_pass_types),
            str(options.correct_score_final_answer_lane_mode),
            ",".join(options.correct_score_final_answer_lane_modes),
            str(options.correct_score_final_answer_lane_candidate_limit),
            str(options.correct_score_final_answer_lane_min_probability),
            str(options.correct_score_final_answer_lane_min_correct_score_probability),
            str(options.correct_score_final_answer_lane_max_correct_score_per_selection),
            str(options.correct_score_final_answer_lane_score_boost),
            str(options.correct_score_final_answer_lane_max_hit_probability_deficit),
            str(options.correct_score_final_answer_lane_min_roi_delta),
            ",".join(options.correct_score_final_answer_lane_outcomes),
            default_competition_recommendation_profile_version(),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_recommendation_backtest:{historical_slice.metadata.slice_id}:{digest}"


def _selection_diagnostics(
    selection: RecommendationSelection,
    *,
    optimizer_profile: HistoricalOptimizerProfile,
) -> dict[str, object]:
    solver_search = selection.explanation_json.get("solver_search")
    return {
        "optimizer_profile": optimizer_profile,
        "solver_selected": isinstance(solver_search, dict)
        and solver_search.get("accepted") is True,
        "selection_basis": selection.explanation_json.get("selection_basis"),
        "solver_search": solver_search if isinstance(solver_search, dict) else None,
    }


def _comparison_deltas(
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
) -> dict[str, object]:
    return {
        "final_hit_rate_delta": _optional_delta(
            candidate.final_hit_rate,
            baseline.final_hit_rate,
        ),
        "final_hit_count_delta": candidate.final_hit_count - baseline.final_hit_count,
        "roi_delta": _optional_delta(candidate.roi, baseline.roi),
        "profit_loss_delta": candidate.profit_loss - baseline.profit_loss,
        "brier_score_delta": _optional_delta(candidate.brier_score, baseline.brier_score),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "mean_calibration_error_delta": _optional_delta(
            candidate.mean_calibration_error,
            baseline.mean_calibration_error,
        ),
        "upset_capture_rate_delta": _optional_delta(
            candidate.upset_capture_rate,
            baseline.upset_capture_rate,
        ),
        "upset_capture_count_delta": (candidate.upset_capture_count - baseline.upset_capture_count),
        "upset_exposure_reserve_selected_candidate_count_delta": (
            _summary_int(
                candidate.summary_json,
                "final_answer_upset_exposure_reserve_selected_candidate_count",
            )
            - _summary_int(
                baseline.summary_json,
                "final_answer_upset_exposure_reserve_selected_candidate_count",
            )
        ),
        "upset_final_answer_lane_selected_candidate_count_delta": (
            _summary_int(
                candidate.summary_json,
                "final_answer_upset_final_answer_lane_selected_candidate_count",
            )
            - _summary_int(
                baseline.summary_json,
                "final_answer_upset_final_answer_lane_selected_candidate_count",
            )
        ),
        "upset_final_answer_lane_calibration_guard_blocked_option_count_delta": (
            _summary_int(
                candidate.summary_json,
                "upset_final_answer_lane_calibration_guard_blocked_option_count",
            )
            - _summary_int(
                baseline.summary_json,
                "upset_final_answer_lane_calibration_guard_blocked_option_count",
            )
        ),
        "candidate_solver_selected_scenario_count": _summary_int(
            candidate.summary_json,
            "solver_selected_scenario_count",
        ),
    }


def _comparison_status(deltas: dict[str, object]) -> str:
    improvements = 0
    regressions = 0
    for key in (
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "upset_capture_rate_delta",
    ):
        delta = _optional_number(deltas.get(key))
        if delta is None:
            continue
        if delta > 0:
            improvements += 1
        elif delta < 0:
            regressions += 1
    for key in (
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    ):
        delta = _optional_number(deltas.get(key))
        if delta is None:
            continue
        if delta < 0:
            improvements += 1
        elif delta > 0:
            regressions += 1
    if improvements and regressions:
        return "mixed"
    if improvements:
        return "improved"
    if regressions:
        return "regressed"
    return "unchanged"


def _suite_aggregate_deltas(
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
) -> dict[str, object]:
    baseline_results = [comparison.baseline for comparison in comparisons]
    candidate_results = [comparison.candidate for comparison in comparisons]
    baseline_hit_sample_size = sum(result.final_hit_sample_size for result in baseline_results)
    candidate_hit_sample_size = sum(result.final_hit_sample_size for result in candidate_results)
    baseline_final_hit_count = sum(result.final_hit_count for result in baseline_results)
    candidate_final_hit_count = sum(result.final_hit_count for result in candidate_results)
    baseline_total_stake = sum(result.total_stake for result in baseline_results)
    candidate_total_stake = sum(result.total_stake for result in candidate_results)
    baseline_profit_loss = sum(result.profit_loss for result in baseline_results)
    candidate_profit_loss = sum(result.profit_loss for result in candidate_results)
    baseline_upset_opportunity_count = sum(
        result.upset_opportunity_count for result in baseline_results
    )
    candidate_upset_opportunity_count = sum(
        result.upset_opportunity_count for result in candidate_results
    )
    baseline_upset_capture_count = sum(result.upset_capture_count for result in baseline_results)
    candidate_upset_capture_count = sum(result.upset_capture_count for result in candidate_results)
    baseline_final_hit_rate = _ratio(baseline_final_hit_count, baseline_hit_sample_size)
    candidate_final_hit_rate = _ratio(candidate_final_hit_count, candidate_hit_sample_size)
    baseline_roi = baseline_profit_loss / baseline_total_stake if baseline_total_stake > 0 else None
    candidate_roi = (
        candidate_profit_loss / candidate_total_stake if candidate_total_stake > 0 else None
    )
    baseline_upset_capture_rate = _ratio(
        baseline_upset_capture_count,
        baseline_upset_opportunity_count,
    )
    candidate_upset_capture_rate = _ratio(
        candidate_upset_capture_count,
        candidate_upset_opportunity_count,
    )
    return {
        "final_hit_rate_delta": _optional_delta(
            candidate_final_hit_rate,
            baseline_final_hit_rate,
        ),
        "final_hit_count_delta": candidate_final_hit_count - baseline_final_hit_count,
        "roi_delta": _optional_delta(candidate_roi, baseline_roi),
        "profit_loss_delta": candidate_profit_loss - baseline_profit_loss,
        "brier_score_delta": _optional_delta(
            _weighted_result_average(candidate_results, "brier_score"),
            _weighted_result_average(baseline_results, "brier_score"),
        ),
        "log_loss_delta": _optional_delta(
            _weighted_result_average(candidate_results, "log_loss"),
            _weighted_result_average(baseline_results, "log_loss"),
        ),
        "mean_calibration_error_delta": _optional_delta(
            _weighted_result_average(candidate_results, "mean_calibration_error"),
            _weighted_result_average(baseline_results, "mean_calibration_error"),
        ),
        "upset_capture_rate_delta": _optional_delta(
            candidate_upset_capture_rate,
            baseline_upset_capture_rate,
        ),
        "upset_capture_count_delta": (candidate_upset_capture_count - baseline_upset_capture_count),
        "candidate_solver_selected_scenario_count": sum(
            _summary_int(
                comparison.candidate.summary_json,
                "solver_selected_scenario_count",
            )
            for comparison in comparisons
        ),
        "final_answer_changed_count": sum(
            1
            for comparison in comparisons
            if comparison.summary_json.get("final_answer_changed") is True
        ),
        "upset_final_answer_lane_calibration_guard_blocked_option_count_delta": (
            sum(
                _summary_int(
                    comparison.candidate.summary_json,
                    "upset_final_answer_lane_calibration_guard_blocked_option_count",
                )
                for comparison in comparisons
            )
            - sum(
                _summary_int(
                    comparison.baseline.summary_json,
                    "upset_final_answer_lane_calibration_guard_blocked_option_count",
                )
                for comparison in comparisons
            )
        ),
    }


def _suite_summary_json(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
    aggregate_deltas: dict[str, object],
    status: str,
    baseline_optimizer_profile: HistoricalOptimizerProfile,
    candidate_optimizer_profile: HistoricalOptimizerProfile,
) -> dict[str, object]:
    baseline_results = [comparison.baseline for comparison in comparisons]
    candidate_results = [comparison.candidate for comparison in comparisons]
    baseline_total_stake = sum(result.total_stake for result in baseline_results)
    candidate_total_stake = sum(result.total_stake for result in candidate_results)
    baseline_profit_loss = sum(result.profit_loss for result in baseline_results)
    candidate_profit_loss = sum(result.profit_loss for result in candidate_results)
    comparison_status_counts: dict[str, int] = {}
    for comparison in comparisons:
        comparison_status_counts[comparison.status] = (
            comparison_status_counts.get(comparison.status, 0) + 1
        )
    baseline_final_hit_sample_size = sum(
        result.final_hit_sample_size for result in baseline_results
    )
    candidate_final_hit_sample_size = sum(
        result.final_hit_sample_size for result in candidate_results
    )
    baseline_final_hit_count = sum(result.final_hit_count for result in baseline_results)
    candidate_final_hit_count = sum(result.final_hit_count for result in candidate_results)
    baseline_dynamic_mixed_final_answer_count = _summary_true_count(
        baseline_results,
        "final_answer_dynamic_mixed_market",
    )
    candidate_dynamic_mixed_final_answer_count = _summary_true_count(
        candidate_results,
        "final_answer_dynamic_mixed_market",
    )
    baseline_handicap_final_answer_count = _summary_true_count(
        baseline_results,
        "final_answer_has_handicap_market",
    )
    candidate_handicap_final_answer_count = _summary_true_count(
        candidate_results,
        "final_answer_has_handicap_market",
    )
    baseline_correct_score_final_answer_count = _summary_true_count(
        baseline_results,
        "final_answer_has_correct_score_market",
    )
    candidate_correct_score_final_answer_count = _summary_true_count(
        candidate_results,
        "final_answer_has_correct_score_market",
    )
    baseline_multiple_choice_final_answer_count = _summary_positive_count(
        baseline_results,
        "final_answer_multiple_choice_fixture_count",
    )
    candidate_multiple_choice_final_answer_count = _summary_positive_count(
        candidate_results,
        "final_answer_multiple_choice_fixture_count",
    )
    baseline_final_answer_selected_candidate_count = sum(
        _summary_int(result.summary_json, "final_answer_selected_candidate_count")
        for result in baseline_results
    )
    candidate_final_answer_selected_candidate_count = sum(
        _summary_int(result.summary_json, "final_answer_selected_candidate_count")
        for result in candidate_results
    )
    baseline_final_answer_multiple_choice_fixture_count = sum(
        _summary_int(result.summary_json, "final_answer_multiple_choice_fixture_count")
        for result in baseline_results
    )
    candidate_final_answer_multiple_choice_fixture_count = sum(
        _summary_int(result.summary_json, "final_answer_multiple_choice_fixture_count")
        for result in candidate_results
    )
    baseline_upset_opportunity_count = sum(
        result.upset_opportunity_count for result in baseline_results
    )
    candidate_upset_opportunity_count = sum(
        result.upset_opportunity_count for result in candidate_results
    )
    baseline_upset_capture_count = sum(result.upset_capture_count for result in baseline_results)
    candidate_upset_capture_count = sum(result.upset_capture_count for result in candidate_results)
    baseline_guardrail_excluded_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "short_price_negative_edge_guardrail_excluded_candidate_count",
        )
        for result in baseline_results
    )
    candidate_guardrail_excluded_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "short_price_negative_edge_guardrail_excluded_candidate_count",
        )
        for result in candidate_results
    )
    baseline_soft_penalty_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "short_price_negative_edge_soft_penalty_candidate_count",
        )
        for result in baseline_results
    )
    candidate_soft_penalty_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "short_price_negative_edge_soft_penalty_candidate_count",
        )
        for result in candidate_results
    )
    baseline_loss_driver_guardrail_excluded_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "marginal_loss_driver_candidate_guardrail_excluded_candidate_count",
        )
        for result in baseline_results
    )
    candidate_loss_driver_guardrail_excluded_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "marginal_loss_driver_candidate_guardrail_excluded_candidate_count",
        )
        for result in candidate_results
    )
    baseline_loss_driver_soft_penalty_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "marginal_loss_driver_candidate_soft_penalty_candidate_count",
        )
        for result in baseline_results
    )
    candidate_loss_driver_soft_penalty_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "marginal_loss_driver_candidate_soft_penalty_candidate_count",
        )
        for result in candidate_results
    )
    baseline_quality_signal_affected_leg_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_quality_signal_affected_leg_count",
        )
        for result in baseline_results
    )
    candidate_quality_signal_affected_leg_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_quality_signal_affected_leg_count",
        )
        for result in candidate_results
    )
    baseline_selection_value_signal_affected_leg_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_selection_value_signal_affected_leg_count",
        )
        for result in baseline_results
    )
    candidate_selection_value_signal_affected_leg_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_selection_value_signal_affected_leg_count",
        )
        for result in candidate_results
    )
    baseline_selection_value_signal_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_selection_value_signal_guard_blocked_option_count",
        )
        for result in baseline_results
    )
    candidate_selection_value_signal_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_selection_value_signal_guard_blocked_option_count",
        )
        for result in candidate_results
    )
    baseline_segment_penalty_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_segment_penalty_option_count",
        )
        for result in baseline_results
    )
    candidate_segment_penalty_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_segment_penalty_option_count",
        )
        for result in candidate_results
    )
    baseline_stake_efficiency_penalty_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_stake_efficiency_penalty_option_count",
        )
        for result in baseline_results
    )
    candidate_stake_efficiency_penalty_option_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_stake_efficiency_penalty_option_count",
        )
        for result in candidate_results
    )
    baseline_completed_dynamic_mix_lane_count = sum(
        _summary_int(
            result.summary_json,
            "completed_dynamic_mix_final_answer_lane_count",
        )
        for result in baseline_results
    )
    candidate_completed_dynamic_mix_lane_count = sum(
        _summary_int(
            result.summary_json,
            "completed_dynamic_mix_final_answer_lane_count",
        )
        for result in candidate_results
    )
    baseline_final_answer_dynamic_mix_lane_count = sum(
        1
        for result in baseline_results
        if result.summary_json.get("final_answer_dynamic_mix_final_answer_lane")
        is True
    )
    candidate_final_answer_dynamic_mix_lane_count = sum(
        1
        for result in candidate_results
        if result.summary_json.get("final_answer_dynamic_mix_final_answer_lane")
        is True
    )
    baseline_dynamic_mix_lane_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "dynamic_mix_final_answer_lane_quality_guard_blocked_option_count",
        )
        for result in baseline_results
    )
    candidate_dynamic_mix_lane_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "dynamic_mix_final_answer_lane_quality_guard_blocked_option_count",
        )
        for result in candidate_results
    )
    baseline_completed_correct_score_lane_count = sum(
        _summary_int(
            result.summary_json,
            "completed_correct_score_final_answer_lane_count",
        )
        for result in baseline_results
    )
    candidate_completed_correct_score_lane_count = sum(
        _summary_int(
            result.summary_json,
            "completed_correct_score_final_answer_lane_count",
        )
        for result in candidate_results
    )
    baseline_final_answer_correct_score_lane_count = sum(
        1
        for result in baseline_results
        if result.summary_json.get("final_answer_correct_score_final_answer_lane")
        is True
    )
    candidate_final_answer_correct_score_lane_count = sum(
        1
        for result in candidate_results
        if result.summary_json.get("final_answer_correct_score_final_answer_lane")
        is True
    )
    baseline_correct_score_lane_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "correct_score_final_answer_lane_quality_guard_blocked_option_count",
        )
        for result in baseline_results
    )
    candidate_correct_score_lane_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "correct_score_final_answer_lane_quality_guard_blocked_option_count",
        )
        for result in candidate_results
    )
    baseline_upset_reserve_pool_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "candidate_pool_upset_exposure_reserve_candidate_count",
        )
        for result in baseline_results
    )
    candidate_upset_reserve_pool_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "candidate_pool_upset_exposure_reserve_candidate_count",
        )
        for result in candidate_results
    )
    baseline_upset_reserve_selected_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_upset_exposure_reserve_selected_candidate_count",
        )
        for result in baseline_results
    )
    candidate_upset_reserve_selected_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_upset_exposure_reserve_selected_candidate_count",
        )
        for result in candidate_results
    )
    baseline_upset_lane_candidate_count = sum(
        _summary_int(result.summary_json, "upset_final_answer_lane_candidate_count")
        for result in baseline_results
    )
    candidate_upset_lane_candidate_count = sum(
        _summary_int(result.summary_json, "upset_final_answer_lane_candidate_count")
        for result in candidate_results
    )
    baseline_pool_upset_lane_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "candidate_pool_upset_final_answer_lane_candidate_count",
        )
        for result in baseline_results
    )
    candidate_pool_upset_lane_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "candidate_pool_upset_final_answer_lane_candidate_count",
        )
        for result in candidate_results
    )
    baseline_completed_upset_lane_count = sum(
        _summary_int(result.summary_json, "completed_upset_final_answer_lane_count")
        for result in baseline_results
    )
    candidate_completed_upset_lane_count = sum(
        _summary_int(result.summary_json, "completed_upset_final_answer_lane_count")
        for result in candidate_results
    )
    baseline_final_answer_upset_lane_count = sum(
        1
        for result in baseline_results
        if result.summary_json.get("final_answer_upset_final_answer_lane") is True
    )
    candidate_final_answer_upset_lane_count = sum(
        1
        for result in candidate_results
        if result.summary_json.get("final_answer_upset_final_answer_lane") is True
    )
    baseline_upset_lane_selected_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_upset_final_answer_lane_selected_candidate_count",
        )
        for result in baseline_results
    )
    candidate_upset_lane_selected_candidate_count = sum(
        _summary_int(
            result.summary_json,
            "final_answer_upset_final_answer_lane_selected_candidate_count",
        )
        for result in candidate_results
    )
    baseline_upset_lane_calibration_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "upset_final_answer_lane_calibration_guard_blocked_option_count",
        )
        for result in baseline_results
    )
    candidate_upset_lane_calibration_guard_blocked_option_count = sum(
        _summary_int(
            result.summary_json,
            "upset_final_answer_lane_calibration_guard_blocked_option_count",
        )
        for result in candidate_results
    )
    return {
        "calculation_basis": "historical_recommendation_backtest_suite_v3_1",
        "status": status,
        "slice_count": len(historical_slices),
        "comparison_count": len(comparisons),
        "slice_ids": [historical_slice.metadata.slice_id for historical_slice in historical_slices],
        "baseline_optimizer_profile": baseline_optimizer_profile,
        "candidate_optimizer_profile": candidate_optimizer_profile,
        "final_answer_competition_profile_version": (
            default_competition_recommendation_profile_version()
        ),
        "final_answer_scenario_variant_count": _first_summary_value(
            candidate_results,
            "final_answer_scenario_variant_count",
        ),
        "baseline_completed_scenario_variant_count": sum(
            _summary_int(result.summary_json, "completed_scenario_variant_count")
            for result in baseline_results
        ),
        "candidate_completed_scenario_variant_count": sum(
            _summary_int(result.summary_json, "completed_scenario_variant_count")
            for result in candidate_results
        ),
        "short_price_negative_edge_guardrail": any(
            result.summary_json.get("short_price_negative_edge_guardrail") is True
            for result in candidate_results
        ),
        "short_price_negative_edge_max_decimal_odds": _first_summary_value(
            candidate_results,
            "short_price_negative_edge_max_decimal_odds",
        ),
        "short_price_negative_edge_min_probability": _first_summary_value(
            candidate_results,
            "short_price_negative_edge_min_probability",
        ),
        "short_price_negative_edge_max_model_edge": _first_summary_value(
            candidate_results,
            "short_price_negative_edge_max_model_edge",
        ),
        "short_price_negative_edge_soft_penalty": any(
            result.summary_json.get("short_price_negative_edge_soft_penalty") is True
            for result in candidate_results
        ),
        "short_price_negative_edge_soft_penalty_strength": _first_summary_value(
            candidate_results,
            "short_price_negative_edge_soft_penalty_strength",
        ),
        "short_price_negative_edge_soft_penalty_competition_ids": _first_summary_value(
            candidate_results,
            "short_price_negative_edge_soft_penalty_competition_ids",
        ),
        "baseline_short_price_negative_edge_guardrail_excluded_candidate_count": (
            baseline_guardrail_excluded_candidate_count
        ),
        "candidate_short_price_negative_edge_guardrail_excluded_candidate_count": (
            candidate_guardrail_excluded_candidate_count
        ),
        "baseline_short_price_negative_edge_soft_penalty_candidate_count": (
            baseline_soft_penalty_candidate_count
        ),
        "candidate_short_price_negative_edge_soft_penalty_candidate_count": (
            candidate_soft_penalty_candidate_count
        ),
        "marginal_loss_driver_candidate_guardrail": any(
            result.summary_json.get("marginal_loss_driver_candidate_guardrail") is True
            for result in candidate_results
        ),
        "marginal_loss_driver_candidate_guardrail_probability_min": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_probability_min",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_probability_max": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_probability_max",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_max_decimal_odds": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_max_decimal_odds",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_max_model_edge": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_max_model_edge",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_max_calibration_score": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_max_calibration_score",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_max_model_confidence_score": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_max_model_confidence_score",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_max_odds_stability_score": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_max_odds_stability_score",
            )
        ),
        "marginal_loss_driver_candidate_guardrail_competition_ids": (
            _first_summary_value(
                candidate_results,
                "marginal_loss_driver_candidate_guardrail_competition_ids",
            )
        ),
        "baseline_marginal_loss_driver_candidate_guardrail_excluded_candidate_count": (
            baseline_loss_driver_guardrail_excluded_candidate_count
        ),
        "candidate_marginal_loss_driver_candidate_guardrail_excluded_candidate_count": (
            candidate_loss_driver_guardrail_excluded_candidate_count
        ),
        "marginal_loss_driver_candidate_soft_penalty": any(
            result.summary_json.get("marginal_loss_driver_candidate_soft_penalty") is True
            for result in candidate_results
        ),
        "marginal_loss_driver_candidate_soft_penalty_strength": _first_summary_value(
            candidate_results,
            "marginal_loss_driver_candidate_soft_penalty_strength",
        ),
        "baseline_marginal_loss_driver_candidate_soft_penalty_candidate_count": (
            baseline_loss_driver_soft_penalty_candidate_count
        ),
        "candidate_marginal_loss_driver_candidate_soft_penalty_candidate_count": (
            candidate_loss_driver_soft_penalty_candidate_count
        ),
        "final_answer_quality_signal_penalty": any(
            result.summary_json.get("final_answer_quality_signal_penalty") is True
            for result in candidate_results
        ),
        "final_answer_quality_signal_penalty_strength": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_penalty_strength",
        ),
        "final_answer_quality_signal_probability_min": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_probability_min",
        ),
        "final_answer_quality_signal_probability_max": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_probability_max",
        ),
        "final_answer_quality_signal_min_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_min_decimal_odds",
        ),
        "final_answer_quality_signal_max_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_max_decimal_odds",
        ),
        "final_answer_quality_signal_max_model_edge": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_max_model_edge",
        ),
        "final_answer_quality_signal_score_min": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_score_min",
        ),
        "final_answer_quality_signal_score_max": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_score_max",
        ),
        "final_answer_quality_signal_competition_ids": _first_summary_value(
            candidate_results,
            "final_answer_quality_signal_competition_ids",
        ),
        "baseline_final_answer_quality_signal_affected_leg_count": (
            baseline_quality_signal_affected_leg_count
        ),
        "candidate_final_answer_quality_signal_affected_leg_count": (
            candidate_quality_signal_affected_leg_count
        ),
        "final_answer_selection_value_signal": any(
            result.summary_json.get("final_answer_selection_value_signal") is True
            for result in candidate_results
        ),
        "final_answer_selection_value_signal_strength": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_strength",
        ),
        "final_answer_selection_value_signal_probability_min": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_probability_min",
        ),
        "final_answer_selection_value_signal_probability_max": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_probability_max",
        ),
        "final_answer_selection_value_signal_min_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_min_decimal_odds",
        ),
        "final_answer_selection_value_signal_max_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_max_decimal_odds",
        ),
        "final_answer_selection_value_signal_max_model_edge": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_max_model_edge",
        ),
        "final_answer_selection_value_signal_score_min": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_score_min",
        ),
        "final_answer_selection_value_signal_score_max": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_score_max",
        ),
        "final_answer_selection_value_signal_competition_ids": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_competition_ids",
        ),
        "final_answer_selection_value_signal_outcomes": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_outcomes",
        ),
        "final_answer_selection_value_signal_max_hit_probability_deficit": (
            _first_summary_value(
                candidate_results,
                "final_answer_selection_value_signal_max_hit_probability_deficit",
            )
        ),
        "final_answer_selection_value_signal_min_option_roi": _first_summary_value(
            candidate_results,
            "final_answer_selection_value_signal_min_option_roi",
        ),
        "final_answer_selection_value_signal_max_option_risk_score": (
            _first_summary_value(
                candidate_results,
                "final_answer_selection_value_signal_max_option_risk_score",
            )
        ),
        "baseline_final_answer_selection_value_signal_affected_leg_count": (
            baseline_selection_value_signal_affected_leg_count
        ),
        "candidate_final_answer_selection_value_signal_affected_leg_count": (
            candidate_selection_value_signal_affected_leg_count
        ),
        "baseline_final_answer_selection_value_signal_guard_blocked_option_count": (
            baseline_selection_value_signal_guard_blocked_option_count
        ),
        "candidate_final_answer_selection_value_signal_guard_blocked_option_count": (
            candidate_selection_value_signal_guard_blocked_option_count
        ),
        "final_answer_segment_penalty": any(
            result.summary_json.get("final_answer_segment_penalty") is True
            for result in candidate_results
        ),
        "final_answer_segment_penalty_strength": _first_summary_value(
            candidate_results,
            "final_answer_segment_penalty_strength",
        ),
        "final_answer_segment_pass_types": _first_summary_value(
            candidate_results,
            "final_answer_segment_pass_types",
        ),
        "final_answer_segment_modes": _first_summary_value(
            candidate_results,
            "final_answer_segment_modes",
        ),
        "final_answer_segment_competition_ids": _first_summary_value(
            candidate_results,
            "final_answer_segment_competition_ids",
        ),
        "final_answer_segment_season_ids": _first_summary_value(
            candidate_results,
            "final_answer_segment_season_ids",
        ),
        "final_answer_segment_min_competition_season_index": (
            _first_summary_value(
                candidate_results,
                "final_answer_segment_min_competition_season_index",
            )
        ),
        "final_answer_segment_max_competition_season_index": (
            _first_summary_value(
                candidate_results,
                "final_answer_segment_max_competition_season_index",
            )
        ),
        "final_answer_segment_min_hit_probability": _first_summary_value(
            candidate_results,
            "final_answer_segment_min_hit_probability",
        ),
        "final_answer_segment_max_hit_probability": _first_summary_value(
            candidate_results,
            "final_answer_segment_max_hit_probability",
        ),
        "final_answer_segment_min_odds_product": _first_summary_value(
            candidate_results,
            "final_answer_segment_min_odds_product",
        ),
        "final_answer_segment_max_odds_product": _first_summary_value(
            candidate_results,
            "final_answer_segment_max_odds_product",
        ),
        "final_answer_segment_min_average_leg_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_segment_min_average_leg_decimal_odds",
        ),
        "final_answer_segment_max_average_leg_decimal_odds": _first_summary_value(
            candidate_results,
            "final_answer_segment_max_average_leg_decimal_odds",
        ),
        "baseline_final_answer_segment_penalty_option_count": (
            baseline_segment_penalty_option_count
        ),
        "candidate_final_answer_segment_penalty_option_count": (
            candidate_segment_penalty_option_count
        ),
        "final_answer_stake_efficiency_guard": any(
            result.summary_json.get("final_answer_stake_efficiency_guard") is True
            for result in candidate_results
        ),
        "final_answer_stake_efficiency_penalty_strength": _first_summary_value(
            candidate_results,
            "final_answer_stake_efficiency_penalty_strength",
        ),
        "final_answer_stake_efficiency_max_stake_multiplier": _first_summary_value(
            candidate_results,
            "final_answer_stake_efficiency_max_stake_multiplier",
        ),
        "final_answer_stake_efficiency_min_roi": _first_summary_value(
            candidate_results,
            "final_answer_stake_efficiency_min_roi",
        ),
        "final_answer_stake_efficiency_modes": _first_summary_value(
            candidate_results,
            "final_answer_stake_efficiency_modes",
        ),
        "final_answer_stake_efficiency_scope": _first_summary_value(
            candidate_results,
            "final_answer_stake_efficiency_scope",
        ),
        "baseline_final_answer_stake_efficiency_penalty_option_count": (
            baseline_stake_efficiency_penalty_option_count
        ),
        "candidate_final_answer_stake_efficiency_penalty_option_count": (
            candidate_stake_efficiency_penalty_option_count
        ),
        "dynamic_mix_final_answer_lane": any(
            result.summary_json.get("dynamic_mix_final_answer_lane") is True
            for result in candidate_results
        ),
        "dynamic_mix_final_answer_lane_pass_types": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_pass_types",
        ),
        "dynamic_mix_final_answer_lane_effective_pass_types": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_effective_pass_types",
        ),
        "dynamic_mix_final_answer_lane_effective_constraint_profiles": (
            _first_summary_value(
                candidate_results,
                "dynamic_mix_final_answer_lane_effective_constraint_profiles",
            )
        ),
        "dynamic_mix_final_answer_lane_mode": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_mode",
        ),
        "dynamic_mix_final_answer_lane_modes": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_modes",
        ),
        "dynamic_mix_final_answer_lane_admitted_pass_types": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_admitted_pass_types",
        ),
        "dynamic_mix_final_answer_lane_blocked_pass_types": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_blocked_pass_types",
        ),
        "dynamic_mix_final_answer_lane_constraint_profiles": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_constraint_profiles",
        ),
        "dynamic_mix_final_answer_lane_min_market_count": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_min_market_count",
        ),
        "dynamic_mix_final_answer_lane_candidate_limit": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_candidate_limit",
        ),
        "dynamic_mix_final_answer_lane_solver_search": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_solver_search",
        ),
        "dynamic_mix_final_answer_lane_min_probability": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_min_probability",
        ),
        "dynamic_mix_final_answer_lane_score_boost": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_score_boost",
        ),
        "dynamic_mix_final_answer_lane_max_hit_probability_deficit": (
            _first_summary_value(
                candidate_results,
                "dynamic_mix_final_answer_lane_max_hit_probability_deficit",
            )
        ),
        "dynamic_mix_final_answer_lane_min_roi_delta": _first_summary_value(
            candidate_results,
            "dynamic_mix_final_answer_lane_min_roi_delta",
        ),
        "baseline_completed_dynamic_mix_final_answer_lane_count": (
            baseline_completed_dynamic_mix_lane_count
        ),
        "candidate_completed_dynamic_mix_final_answer_lane_count": (
            candidate_completed_dynamic_mix_lane_count
        ),
        "baseline_final_answer_dynamic_mix_final_answer_lane_count": (
            baseline_final_answer_dynamic_mix_lane_count
        ),
        "candidate_final_answer_dynamic_mix_final_answer_lane_count": (
            candidate_final_answer_dynamic_mix_lane_count
        ),
        "baseline_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count": (
            baseline_dynamic_mix_lane_guard_blocked_option_count
        ),
        "candidate_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count": (
            candidate_dynamic_mix_lane_guard_blocked_option_count
        ),
        "correct_score_final_answer_lane": any(
            result.summary_json.get("correct_score_final_answer_lane") is True
            for result in candidate_results
        ),
        "correct_score_final_answer_lane_pass_types": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_pass_types",
        ),
        "correct_score_final_answer_lane_mode": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_mode",
        ),
        "correct_score_final_answer_lane_modes": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_modes",
        ),
        "correct_score_final_answer_lane_candidate_limit": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_candidate_limit",
        ),
        "correct_score_final_answer_lane_min_probability": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_min_probability",
        ),
        "correct_score_final_answer_lane_min_correct_score_probability": (
            _first_summary_value(
                candidate_results,
                "correct_score_final_answer_lane_min_correct_score_probability",
            )
        ),
        "correct_score_final_answer_lane_max_correct_score_per_selection": (
            _first_summary_value(
                candidate_results,
                "correct_score_final_answer_lane_max_correct_score_per_selection",
            )
        ),
        "correct_score_final_answer_lane_score_boost": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_score_boost",
        ),
        "correct_score_final_answer_lane_max_hit_probability_deficit": (
            _first_summary_value(
                candidate_results,
                "correct_score_final_answer_lane_max_hit_probability_deficit",
            )
        ),
        "correct_score_final_answer_lane_min_roi_delta": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_min_roi_delta",
        ),
        "correct_score_final_answer_lane_outcomes": _first_summary_value(
            candidate_results,
            "correct_score_final_answer_lane_outcomes",
        ),
        "baseline_completed_correct_score_final_answer_lane_count": (
            baseline_completed_correct_score_lane_count
        ),
        "candidate_completed_correct_score_final_answer_lane_count": (
            candidate_completed_correct_score_lane_count
        ),
        "baseline_final_answer_correct_score_final_answer_lane_count": (
            baseline_final_answer_correct_score_lane_count
        ),
        "candidate_final_answer_correct_score_final_answer_lane_count": (
            candidate_final_answer_correct_score_lane_count
        ),
        "baseline_correct_score_final_answer_lane_quality_guard_blocked_option_count": (
            baseline_correct_score_lane_guard_blocked_option_count
        ),
        "candidate_correct_score_final_answer_lane_quality_guard_blocked_option_count": (
            candidate_correct_score_lane_guard_blocked_option_count
        ),
        "upset_exposure_reserve": any(
            result.summary_json.get("upset_exposure_reserve") is True
            for result in candidate_results
        ),
        "upset_exposure_reserve_fixture_count": _first_summary_value(
            candidate_results,
            "upset_exposure_reserve_fixture_count",
        ),
        "upset_exposure_reserve_min_protection_score": _first_summary_value(
            candidate_results,
            "upset_exposure_reserve_min_protection_score",
        ),
        "upset_exposure_reserve_min_probability": _first_summary_value(
            candidate_results,
            "upset_exposure_reserve_min_probability",
        ),
        "upset_exposure_reserve_max_decimal_odds": _first_summary_value(
            candidate_results,
            "upset_exposure_reserve_max_decimal_odds",
        ),
        "baseline_candidate_pool_upset_exposure_reserve_candidate_count": (
            baseline_upset_reserve_pool_candidate_count
        ),
        "candidate_candidate_pool_upset_exposure_reserve_candidate_count": (
            candidate_upset_reserve_pool_candidate_count
        ),
        "baseline_final_answer_upset_exposure_reserve_selected_candidate_count": (
            baseline_upset_reserve_selected_candidate_count
        ),
        "candidate_final_answer_upset_exposure_reserve_selected_candidate_count": (
            candidate_upset_reserve_selected_candidate_count
        ),
        "upset_final_answer_lane": any(
            result.summary_json.get("upset_final_answer_lane") is True
            for result in candidate_results
        ),
        "upset_final_answer_lane_pass_type": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_pass_type",
        ),
        "upset_final_answer_lane_mode": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_mode",
        ),
        "upset_final_answer_lane_candidate_limit": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_candidate_limit",
        ),
        "upset_final_answer_lane_min_protection_score": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_protection_score",
        ),
        "upset_final_answer_lane_min_probability": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_probability",
        ),
        "upset_final_answer_lane_min_decimal_odds": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_decimal_odds",
        ),
        "upset_final_answer_lane_max_decimal_odds": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_max_decimal_odds",
        ),
        "upset_final_answer_lane_min_model_edge": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_model_edge",
        ),
        "upset_final_answer_lane_max_model_edge": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_max_model_edge",
        ),
        "upset_final_answer_lane_competition_ids": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_competition_ids",
        ),
        "upset_final_answer_lane_excluded_competition_ids": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_excluded_competition_ids",
        ),
        "upset_final_answer_lane_min_calibration_score": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_calibration_score",
        ),
        "upset_final_answer_lane_min_model_confidence_score": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_model_confidence_score",
        ),
        "upset_final_answer_lane_min_odds_stability_score": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_odds_stability_score",
        ),
        "upset_final_answer_lane_max_volatility_penalty": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_max_volatility_penalty",
        ),
        "upset_final_answer_lane_max_hit_probability_deficit": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_max_hit_probability_deficit",
        ),
        "upset_final_answer_lane_max_signal_calibration_risk": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_max_signal_calibration_risk",
        ),
        "upset_final_answer_lane_min_signal_reliability_score": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_min_signal_reliability_score",
        ),
        "upset_final_answer_lane_score_boost": _first_summary_value(
            candidate_results,
            "upset_final_answer_lane_score_boost",
        ),
        "baseline_upset_final_answer_lane_candidate_count": (baseline_upset_lane_candidate_count),
        "candidate_upset_final_answer_lane_candidate_count": (candidate_upset_lane_candidate_count),
        "baseline_candidate_pool_upset_final_answer_lane_candidate_count": (
            baseline_pool_upset_lane_candidate_count
        ),
        "candidate_candidate_pool_upset_final_answer_lane_candidate_count": (
            candidate_pool_upset_lane_candidate_count
        ),
        "baseline_completed_upset_final_answer_lane_count": (baseline_completed_upset_lane_count),
        "candidate_completed_upset_final_answer_lane_count": (candidate_completed_upset_lane_count),
        "baseline_final_answer_upset_final_answer_lane_count": (
            baseline_final_answer_upset_lane_count
        ),
        "candidate_final_answer_upset_final_answer_lane_count": (
            candidate_final_answer_upset_lane_count
        ),
        "baseline_final_answer_upset_final_answer_lane_selected_candidate_count": (
            baseline_upset_lane_selected_candidate_count
        ),
        "candidate_final_answer_upset_final_answer_lane_selected_candidate_count": (
            candidate_upset_lane_selected_candidate_count
        ),
        "baseline_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            baseline_upset_lane_calibration_guard_blocked_option_count
        ),
        "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            candidate_upset_lane_calibration_guard_blocked_option_count
        ),
        "comparison_status_counts": comparison_status_counts,
        "baseline_final_hit_sample_size": baseline_final_hit_sample_size,
        "candidate_final_hit_sample_size": candidate_final_hit_sample_size,
        "baseline_final_hit_count": baseline_final_hit_count,
        "candidate_final_hit_count": candidate_final_hit_count,
        "baseline_final_hit_rate": _ratio(
            baseline_final_hit_count,
            baseline_final_hit_sample_size,
        ),
        "candidate_final_hit_rate": _ratio(
            candidate_final_hit_count,
            candidate_final_hit_sample_size,
        ),
        "baseline_dynamic_mixed_final_answer_count": (
            baseline_dynamic_mixed_final_answer_count
        ),
        "candidate_dynamic_mixed_final_answer_count": (
            candidate_dynamic_mixed_final_answer_count
        ),
        "baseline_dynamic_mixed_final_answer_rate": _ratio(
            baseline_dynamic_mixed_final_answer_count,
            baseline_final_hit_sample_size,
        ),
        "candidate_dynamic_mixed_final_answer_rate": _ratio(
            candidate_dynamic_mixed_final_answer_count,
            candidate_final_hit_sample_size,
        ),
        "baseline_final_answer_market_type_counts": _market_type_counts(
            baseline_results
        ),
        "candidate_final_answer_market_type_counts": _market_type_counts(
            candidate_results
        ),
        "baseline_handicap_final_answer_count": baseline_handicap_final_answer_count,
        "candidate_handicap_final_answer_count": candidate_handicap_final_answer_count,
        "baseline_handicap_final_answer_rate": _ratio(
            baseline_handicap_final_answer_count,
            baseline_final_hit_sample_size,
        ),
        "candidate_handicap_final_answer_rate": _ratio(
            candidate_handicap_final_answer_count,
            candidate_final_hit_sample_size,
        ),
        "baseline_correct_score_final_answer_count": (
            baseline_correct_score_final_answer_count
        ),
        "candidate_correct_score_final_answer_count": (
            candidate_correct_score_final_answer_count
        ),
        "baseline_multiple_choice_final_answer_count": (
            baseline_multiple_choice_final_answer_count
        ),
        "candidate_multiple_choice_final_answer_count": (
            candidate_multiple_choice_final_answer_count
        ),
        "baseline_final_answer_selected_candidate_count": (
            baseline_final_answer_selected_candidate_count
        ),
        "candidate_final_answer_selected_candidate_count": (
            candidate_final_answer_selected_candidate_count
        ),
        "baseline_final_answer_multiple_choice_fixture_count": (
            baseline_final_answer_multiple_choice_fixture_count
        ),
        "candidate_final_answer_multiple_choice_fixture_count": (
            candidate_final_answer_multiple_choice_fixture_count
        ),
        "baseline_total_stake": baseline_total_stake,
        "candidate_total_stake": candidate_total_stake,
        "baseline_profit_loss": baseline_profit_loss,
        "candidate_profit_loss": candidate_profit_loss,
        "baseline_roi": (
            baseline_profit_loss / baseline_total_stake if baseline_total_stake > 0 else None
        ),
        "candidate_roi": (
            candidate_profit_loss / candidate_total_stake if candidate_total_stake > 0 else None
        ),
        "baseline_brier_score": _weighted_result_average(
            baseline_results,
            "brier_score",
        ),
        "candidate_brier_score": _weighted_result_average(
            candidate_results,
            "brier_score",
        ),
        "baseline_log_loss": _weighted_result_average(baseline_results, "log_loss"),
        "candidate_log_loss": _weighted_result_average(candidate_results, "log_loss"),
        "baseline_mean_calibration_error": _weighted_result_average(
            baseline_results,
            "mean_calibration_error",
        ),
        "candidate_mean_calibration_error": _weighted_result_average(
            candidate_results,
            "mean_calibration_error",
        ),
        "baseline_upset_opportunity_count": baseline_upset_opportunity_count,
        "candidate_upset_opportunity_count": candidate_upset_opportunity_count,
        "baseline_upset_capture_count": baseline_upset_capture_count,
        "candidate_upset_capture_count": candidate_upset_capture_count,
        "baseline_upset_capture_rate": _ratio(
            baseline_upset_capture_count,
            baseline_upset_opportunity_count,
        ),
        "candidate_upset_capture_rate": _ratio(
            candidate_upset_capture_count,
            candidate_upset_opportunity_count,
        ),
        "candidate_solver_selected_scenario_count": aggregate_deltas.get(
            "candidate_solver_selected_scenario_count",
            0,
        ),
        "final_answer_changed_count": aggregate_deltas.get(
            "final_answer_changed_count",
            0,
        ),
        "aggregate_deltas": aggregate_deltas,
    }


def _suite_warnings(
    *,
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
    status: str,
) -> list[str]:
    warnings: list[str] = []
    if not comparisons:
        warnings.append("historical_suite_no_comparisons")
        return warnings
    if status == "regressed":
        warnings.append("historical_suite_regressed")
    elif status == "mixed":
        warnings.append("historical_suite_mixed")
    solver_selected_count = sum(
        _summary_int(
            comparison.candidate.summary_json,
            "solver_selected_scenario_count",
        )
        for comparison in comparisons
    )
    if solver_selected_count == 0:
        warnings.append("historical_suite_solver_did_not_change_any_scenario")
    return warnings


def _summary_true_count(
    results: Sequence[HistoricalRecommendationBacktestResult],
    key: str,
) -> int:
    return sum(1 for result in results if result.summary_json.get(key) is True)


def _summary_positive_count(
    results: Sequence[HistoricalRecommendationBacktestResult],
    key: str,
) -> int:
    return sum(1 for result in results if _summary_int(result.summary_json, key) > 0)


def _market_type_counts(
    results: Sequence[HistoricalRecommendationBacktestResult],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in results:
        market_types = result.summary_json.get("final_answer_market_types", [])
        if not isinstance(market_types, list):
            continue
        counts.update(str(market_type) for market_type in market_types if str(market_type))
    return dict(sorted(counts.items()))


def _weighted_result_average(
    results: Sequence[HistoricalRecommendationBacktestResult],
    field_name: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for result in results:
        value = getattr(result, field_name)
        if value is None:
            continue
        sample_size = result.final_hit_sample_size
        if sample_size <= 0:
            continue
        numerator += float(value) * sample_size
        denominator += sample_size
    if denominator <= 0:
        return None
    return numerator / denominator


def _first_summary_value(
    results: Sequence[HistoricalRecommendationBacktestResult],
    key: str,
) -> object | None:
    for result in results:
        if key in result.summary_json:
            return result.summary_json[key]
    return None


def _comparison_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
    baseline_optimizer_profile: HistoricalOptimizerProfile,
    candidate_optimizer_profile: HistoricalOptimizerProfile,
) -> str:
    payload = "|".join(
        [
            historical_slice.metadata.slice_id,
            historical_slice.as_of_time_utc.isoformat(),
            ",".join(options.pass_types),
            ",".join(options.modes),
            options.strategy,
            str(options.max_budget),
            str(options.candidate_fixture_limit),
            str(options.max_candidates_per_fixture),
            str(options.scenario_candidate_fixture_buffer),
            str(options.final_answer_scenario_variant_count),
            str(options.derive_market_context_signals),
            str(options.upset_exposure_reserve),
            str(options.upset_exposure_reserve_fixture_count),
            str(options.upset_exposure_reserve_max_candidates_per_fixture),
            str(options.upset_exposure_reserve_min_protection_score),
            str(options.upset_exposure_reserve_min_probability),
            str(options.upset_exposure_reserve_max_decimal_odds),
            str(options.upset_final_answer_lane),
            str(options.upset_final_answer_lane_pass_type),
            str(options.upset_final_answer_lane_mode),
            str(options.upset_final_answer_lane_candidate_limit),
            str(options.upset_final_answer_lane_min_protection_score),
            str(options.upset_final_answer_lane_min_probability),
            str(options.upset_final_answer_lane_min_decimal_odds),
            str(options.upset_final_answer_lane_max_decimal_odds),
            str(options.upset_final_answer_lane_min_model_edge),
            str(options.upset_final_answer_lane_max_model_edge),
            ",".join(options.upset_final_answer_lane_competition_ids),
            ",".join(options.upset_final_answer_lane_excluded_competition_ids),
            str(options.upset_final_answer_lane_min_calibration_score),
            str(options.upset_final_answer_lane_min_model_confidence_score),
            str(options.upset_final_answer_lane_min_odds_stability_score),
            str(options.upset_final_answer_lane_max_volatility_penalty),
            str(options.upset_final_answer_lane_max_hit_probability_deficit),
            str(options.upset_final_answer_lane_max_signal_calibration_risk),
            str(options.upset_final_answer_lane_min_signal_reliability_score),
            str(options.upset_final_answer_lane_score_boost),
            str(options.short_price_negative_edge_guardrail),
            str(options.short_price_negative_edge_max_decimal_odds),
            str(options.short_price_negative_edge_min_probability),
            str(options.short_price_negative_edge_max_model_edge),
            str(options.short_price_negative_edge_soft_penalty),
            str(options.short_price_negative_edge_soft_penalty_strength),
            ",".join(options.short_price_negative_edge_soft_penalty_competition_ids),
            str(options.marginal_loss_driver_candidate_guardrail),
            str(options.marginal_loss_driver_candidate_guardrail_probability_min),
            str(options.marginal_loss_driver_candidate_guardrail_probability_max),
            str(options.marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_edge),
            str(options.marginal_loss_driver_candidate_guardrail_max_calibration_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score),
            ",".join(options.marginal_loss_driver_candidate_guardrail_competition_ids),
            str(options.marginal_loss_driver_candidate_soft_penalty),
            str(options.marginal_loss_driver_candidate_soft_penalty_strength),
            str(options.final_answer_quality_signal_penalty),
            str(options.final_answer_quality_signal_penalty_strength),
            str(options.final_answer_quality_signal_probability_min),
            str(options.final_answer_quality_signal_probability_max),
            str(options.final_answer_quality_signal_min_decimal_odds),
            str(options.final_answer_quality_signal_max_decimal_odds),
            str(options.final_answer_quality_signal_max_model_edge),
            str(options.final_answer_quality_signal_score_min),
            str(options.final_answer_quality_signal_score_max),
            ",".join(options.final_answer_quality_signal_competition_ids),
            str(options.final_answer_selection_value_signal),
            str(options.final_answer_selection_value_signal_strength),
            str(options.final_answer_selection_value_signal_probability_min),
            str(options.final_answer_selection_value_signal_probability_max),
            str(options.final_answer_selection_value_signal_min_decimal_odds),
            str(options.final_answer_selection_value_signal_max_decimal_odds),
            str(options.final_answer_selection_value_signal_max_model_edge),
            str(options.final_answer_selection_value_signal_score_min),
            str(options.final_answer_selection_value_signal_score_max),
            ",".join(options.final_answer_selection_value_signal_competition_ids),
            ",".join(options.final_answer_selection_value_signal_outcomes),
            str(options.final_answer_selection_value_signal_max_hit_probability_deficit),
            str(options.final_answer_selection_value_signal_min_option_roi),
            str(options.final_answer_selection_value_signal_max_option_risk_score),
            str(options.final_answer_segment_penalty),
            str(options.final_answer_segment_penalty_strength),
            ",".join(options.final_answer_segment_pass_types),
            ",".join(options.final_answer_segment_modes),
            ",".join(options.final_answer_segment_competition_ids),
            ",".join(options.final_answer_segment_season_ids),
            str(options.final_answer_segment_min_competition_season_index),
            str(options.final_answer_segment_max_competition_season_index),
            str(options.final_answer_segment_min_hit_probability),
            str(options.final_answer_segment_max_hit_probability),
            str(options.final_answer_segment_min_odds_product),
            str(options.final_answer_segment_max_odds_product),
            str(options.final_answer_segment_min_average_leg_decimal_odds),
            str(options.final_answer_segment_max_average_leg_decimal_odds),
            str(options.final_answer_stake_efficiency_guard),
            str(options.final_answer_stake_efficiency_penalty_strength),
            str(options.final_answer_stake_efficiency_max_stake_multiplier),
            str(options.final_answer_stake_efficiency_min_roi),
            ",".join(options.final_answer_stake_efficiency_modes),
            options.final_answer_stake_efficiency_scope,
            str(options.dynamic_mix_final_answer_lane),
            ",".join(options.dynamic_mix_final_answer_lane_pass_types),
            str(options.dynamic_mix_final_answer_lane_mode),
            ",".join(options.dynamic_mix_final_answer_lane_modes),
            ",".join(options.dynamic_mix_final_answer_lane_admitted_pass_types),
            ",".join(options.dynamic_mix_final_answer_lane_blocked_pass_types),
            _dynamic_mix_final_answer_lane_constraint_profile_signature(options),
            str(options.dynamic_mix_final_answer_lane_min_market_count),
            str(options.dynamic_mix_final_answer_lane_candidate_limit),
            str(options.dynamic_mix_final_answer_lane_solver_search),
            str(options.dynamic_mix_final_answer_lane_min_probability),
            str(options.dynamic_mix_final_answer_lane_score_boost),
            str(options.dynamic_mix_final_answer_lane_max_hit_probability_deficit),
            str(options.dynamic_mix_final_answer_lane_min_roi_delta),
            str(options.correct_score_final_answer_lane),
            ",".join(options.correct_score_final_answer_lane_pass_types),
            str(options.correct_score_final_answer_lane_mode),
            ",".join(options.correct_score_final_answer_lane_modes),
            str(options.correct_score_final_answer_lane_candidate_limit),
            str(options.correct_score_final_answer_lane_min_probability),
            str(options.correct_score_final_answer_lane_min_correct_score_probability),
            str(options.correct_score_final_answer_lane_max_correct_score_per_selection),
            str(options.correct_score_final_answer_lane_score_boost),
            str(options.correct_score_final_answer_lane_max_hit_probability_deficit),
            str(options.correct_score_final_answer_lane_min_roi_delta),
            ",".join(options.correct_score_final_answer_lane_outcomes),
            default_competition_recommendation_profile_version(),
            baseline_optimizer_profile,
            candidate_optimizer_profile,
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return (
        "historical_recommendation_backtest_comparison:"
        f"{historical_slice.metadata.slice_id}:{digest}"
    )


def _suite_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions,
    baseline_optimizer_profile: HistoricalOptimizerProfile,
    candidate_optimizer_profile: HistoricalOptimizerProfile,
) -> str:
    slice_payload = ";".join(
        f"{historical_slice.metadata.slice_id}@{historical_slice.as_of_time_utc.isoformat()}"
        for historical_slice in historical_slices
    )
    payload = "|".join(
        [
            slice_payload,
            ",".join(options.pass_types),
            ",".join(options.modes),
            options.strategy,
            str(options.max_budget),
            str(options.candidate_fixture_limit),
            str(options.max_candidates_per_fixture),
            str(options.scenario_candidate_fixture_buffer),
            str(options.final_answer_scenario_variant_count),
            str(options.derive_market_context_signals),
            str(options.upset_exposure_reserve),
            str(options.upset_exposure_reserve_fixture_count),
            str(options.upset_exposure_reserve_max_candidates_per_fixture),
            str(options.upset_exposure_reserve_min_protection_score),
            str(options.upset_exposure_reserve_min_probability),
            str(options.upset_exposure_reserve_max_decimal_odds),
            str(options.upset_final_answer_lane),
            str(options.upset_final_answer_lane_pass_type),
            str(options.upset_final_answer_lane_mode),
            str(options.upset_final_answer_lane_candidate_limit),
            str(options.upset_final_answer_lane_min_protection_score),
            str(options.upset_final_answer_lane_min_probability),
            str(options.upset_final_answer_lane_min_decimal_odds),
            str(options.upset_final_answer_lane_max_decimal_odds),
            str(options.upset_final_answer_lane_min_model_edge),
            str(options.upset_final_answer_lane_max_model_edge),
            ",".join(options.upset_final_answer_lane_competition_ids),
            ",".join(options.upset_final_answer_lane_excluded_competition_ids),
            str(options.upset_final_answer_lane_min_calibration_score),
            str(options.upset_final_answer_lane_min_model_confidence_score),
            str(options.upset_final_answer_lane_min_odds_stability_score),
            str(options.upset_final_answer_lane_max_volatility_penalty),
            str(options.upset_final_answer_lane_max_hit_probability_deficit),
            str(options.upset_final_answer_lane_max_signal_calibration_risk),
            str(options.upset_final_answer_lane_min_signal_reliability_score),
            str(options.upset_final_answer_lane_score_boost),
            str(options.short_price_negative_edge_guardrail),
            str(options.short_price_negative_edge_max_decimal_odds),
            str(options.short_price_negative_edge_min_probability),
            str(options.short_price_negative_edge_max_model_edge),
            str(options.short_price_negative_edge_soft_penalty),
            str(options.short_price_negative_edge_soft_penalty_strength),
            ",".join(options.short_price_negative_edge_soft_penalty_competition_ids),
            str(options.marginal_loss_driver_candidate_guardrail),
            str(options.marginal_loss_driver_candidate_guardrail_probability_min),
            str(options.marginal_loss_driver_candidate_guardrail_probability_max),
            str(options.marginal_loss_driver_candidate_guardrail_max_decimal_odds),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_edge),
            str(options.marginal_loss_driver_candidate_guardrail_max_calibration_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_model_confidence_score),
            str(options.marginal_loss_driver_candidate_guardrail_max_odds_stability_score),
            ",".join(options.marginal_loss_driver_candidate_guardrail_competition_ids),
            str(options.marginal_loss_driver_candidate_soft_penalty),
            str(options.marginal_loss_driver_candidate_soft_penalty_strength),
            str(options.final_answer_quality_signal_penalty),
            str(options.final_answer_quality_signal_penalty_strength),
            str(options.final_answer_quality_signal_probability_min),
            str(options.final_answer_quality_signal_probability_max),
            str(options.final_answer_quality_signal_min_decimal_odds),
            str(options.final_answer_quality_signal_max_decimal_odds),
            str(options.final_answer_quality_signal_max_model_edge),
            str(options.final_answer_quality_signal_score_min),
            str(options.final_answer_quality_signal_score_max),
            ",".join(options.final_answer_quality_signal_competition_ids),
            str(options.final_answer_selection_value_signal),
            str(options.final_answer_selection_value_signal_strength),
            str(options.final_answer_selection_value_signal_probability_min),
            str(options.final_answer_selection_value_signal_probability_max),
            str(options.final_answer_selection_value_signal_min_decimal_odds),
            str(options.final_answer_selection_value_signal_max_decimal_odds),
            str(options.final_answer_selection_value_signal_max_model_edge),
            str(options.final_answer_selection_value_signal_score_min),
            str(options.final_answer_selection_value_signal_score_max),
            ",".join(options.final_answer_selection_value_signal_competition_ids),
            ",".join(options.final_answer_selection_value_signal_outcomes),
            str(options.final_answer_selection_value_signal_max_hit_probability_deficit),
            str(options.final_answer_selection_value_signal_min_option_roi),
            str(options.final_answer_selection_value_signal_max_option_risk_score),
            str(options.final_answer_segment_penalty),
            str(options.final_answer_segment_penalty_strength),
            ",".join(options.final_answer_segment_pass_types),
            ",".join(options.final_answer_segment_modes),
            ",".join(options.final_answer_segment_competition_ids),
            ",".join(options.final_answer_segment_season_ids),
            str(options.final_answer_segment_min_competition_season_index),
            str(options.final_answer_segment_max_competition_season_index),
            str(options.final_answer_segment_min_hit_probability),
            str(options.final_answer_segment_max_hit_probability),
            str(options.final_answer_segment_min_odds_product),
            str(options.final_answer_segment_max_odds_product),
            str(options.final_answer_segment_min_average_leg_decimal_odds),
            str(options.final_answer_segment_max_average_leg_decimal_odds),
            str(options.final_answer_stake_efficiency_guard),
            str(options.final_answer_stake_efficiency_penalty_strength),
            str(options.final_answer_stake_efficiency_max_stake_multiplier),
            str(options.final_answer_stake_efficiency_min_roi),
            ",".join(options.final_answer_stake_efficiency_modes),
            options.final_answer_stake_efficiency_scope,
            str(options.dynamic_mix_final_answer_lane),
            ",".join(options.dynamic_mix_final_answer_lane_pass_types),
            str(options.dynamic_mix_final_answer_lane_mode),
            ",".join(options.dynamic_mix_final_answer_lane_modes),
            ",".join(options.dynamic_mix_final_answer_lane_admitted_pass_types),
            ",".join(options.dynamic_mix_final_answer_lane_blocked_pass_types),
            _dynamic_mix_final_answer_lane_constraint_profile_signature(options),
            str(options.dynamic_mix_final_answer_lane_min_market_count),
            str(options.dynamic_mix_final_answer_lane_candidate_limit),
            str(options.dynamic_mix_final_answer_lane_solver_search),
            str(options.dynamic_mix_final_answer_lane_min_probability),
            str(options.dynamic_mix_final_answer_lane_score_boost),
            str(options.dynamic_mix_final_answer_lane_max_hit_probability_deficit),
            str(options.dynamic_mix_final_answer_lane_min_roi_delta),
            str(options.correct_score_final_answer_lane),
            ",".join(options.correct_score_final_answer_lane_pass_types),
            str(options.correct_score_final_answer_lane_mode),
            ",".join(options.correct_score_final_answer_lane_modes),
            str(options.correct_score_final_answer_lane_candidate_limit),
            str(options.correct_score_final_answer_lane_min_probability),
            str(options.correct_score_final_answer_lane_min_correct_score_probability),
            str(options.correct_score_final_answer_lane_max_correct_score_per_selection),
            str(options.correct_score_final_answer_lane_score_boost),
            str(options.correct_score_final_answer_lane_max_hit_probability_deficit),
            str(options.correct_score_final_answer_lane_min_roi_delta),
            ",".join(options.correct_score_final_answer_lane_outcomes),
            default_competition_recommendation_profile_version(),
            baseline_optimizer_profile,
            candidate_optimizer_profile,
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_recommendation_backtest_suite:{digest}"


def _final_answer_signature(
    final_answer: HistoricalRecommendationScenarioResult | None,
) -> tuple[str, tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]] | None:
    if final_answer is None:
        return None
    return (
        final_answer.scenario.scenario_key,
        tuple(final_answer.selected_fixture_ids),
        tuple(
            sorted(
                (fixture_id, tuple(outcomes))
                for fixture_id, outcomes in final_answer.selected_outcomes.items()
            )
        ),
    )


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _optional_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _float_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average(values: Iterable[float | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def main() -> None:
    args = _parse_args()
    historical_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    options = HistoricalRecommendationBacktestOptions(
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        strategy=cast(RecommendationStrategy, args.strategy),
        unit_stake=args.unit_stake,
        max_budget=args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        allowed_markets=tuple(
            cast(RecommendationMarketType, market)
            for market in _csv(args.allowed_markets)
        ),
        max_outcomes_per_fixture=args.max_outcomes_per_fixture,
        upset_threshold=args.upset_threshold,
        optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        candidate_fixture_limit=args.candidate_fixture_limit,
        max_candidates_per_fixture=args.max_candidates_per_fixture,
        scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
        final_answer_scenario_variant_count=(
            args.final_answer_scenario_variant_count
        ),
        derive_market_context_signals=args.derive_market_context_signals,
        upset_exposure_reserve=args.upset_exposure_reserve,
        upset_exposure_reserve_fixture_count=(args.upset_exposure_reserve_fixture_count),
        upset_exposure_reserve_max_candidates_per_fixture=(
            args.upset_exposure_reserve_max_candidates_per_fixture
        ),
        upset_exposure_reserve_min_protection_score=(
            args.upset_exposure_reserve_min_protection_score
        ),
        upset_exposure_reserve_min_probability=(args.upset_exposure_reserve_min_probability),
        upset_exposure_reserve_max_decimal_odds=(args.upset_exposure_reserve_max_decimal_odds),
        upset_final_answer_lane=args.upset_final_answer_lane,
        upset_final_answer_lane_pass_type=args.upset_final_answer_lane_pass_type,
        upset_final_answer_lane_mode=cast(
            RecommendationMode,
            args.upset_final_answer_lane_mode,
        ),
        upset_final_answer_lane_candidate_limit=(args.upset_final_answer_lane_candidate_limit),
        upset_final_answer_lane_min_protection_score=(
            args.upset_final_answer_lane_min_protection_score
        ),
        upset_final_answer_lane_min_probability=(args.upset_final_answer_lane_min_probability),
        upset_final_answer_lane_min_decimal_odds=(args.upset_final_answer_lane_min_decimal_odds),
        upset_final_answer_lane_max_decimal_odds=(args.upset_final_answer_lane_max_decimal_odds),
        upset_final_answer_lane_min_model_edge=(args.upset_final_answer_lane_min_model_edge),
        upset_final_answer_lane_max_model_edge=(args.upset_final_answer_lane_max_model_edge),
        upset_final_answer_lane_competition_ids=tuple(
            _csv(args.upset_final_answer_lane_competitions)
        ),
        upset_final_answer_lane_excluded_competition_ids=tuple(
            _csv(args.upset_final_answer_lane_excluded_competitions)
        ),
        upset_final_answer_lane_min_calibration_score=(
            args.upset_final_answer_lane_min_calibration_score
        ),
        upset_final_answer_lane_min_model_confidence_score=(
            args.upset_final_answer_lane_min_model_confidence_score
        ),
        upset_final_answer_lane_min_odds_stability_score=(
            args.upset_final_answer_lane_min_odds_stability_score
        ),
        upset_final_answer_lane_max_volatility_penalty=(
            args.upset_final_answer_lane_max_volatility_penalty
        ),
        upset_final_answer_lane_max_hit_probability_deficit=(
            args.upset_final_answer_lane_max_hit_probability_deficit
        ),
        upset_final_answer_lane_max_signal_calibration_risk=(
            args.upset_final_answer_lane_max_signal_calibration_risk
        ),
        upset_final_answer_lane_min_signal_reliability_score=(
            args.upset_final_answer_lane_min_signal_reliability_score
        ),
        upset_final_answer_lane_score_boost=args.upset_final_answer_lane_score_boost,
        short_price_negative_edge_guardrail=args.short_price_negative_edge_guardrail,
        short_price_negative_edge_max_decimal_odds=(
            args.short_price_negative_edge_max_decimal_odds
        ),
        short_price_negative_edge_min_probability=(args.short_price_negative_edge_min_probability),
        short_price_negative_edge_max_model_edge=(args.short_price_negative_edge_max_model_edge),
        short_price_negative_edge_soft_penalty=(args.short_price_negative_edge_soft_penalty),
        short_price_negative_edge_soft_penalty_strength=(
            args.short_price_negative_edge_soft_penalty_strength
        ),
        short_price_negative_edge_soft_penalty_competition_ids=tuple(
            _csv(args.short_price_negative_edge_soft_penalty_competitions)
        ),
        marginal_loss_driver_candidate_guardrail=(args.marginal_loss_driver_candidate_guardrail),
        marginal_loss_driver_candidate_guardrail_probability_min=(
            args.marginal_loss_driver_candidate_guardrail_probability_min
        ),
        marginal_loss_driver_candidate_guardrail_probability_max=(
            args.marginal_loss_driver_candidate_guardrail_probability_max
        ),
        marginal_loss_driver_candidate_guardrail_max_decimal_odds=(
            args.marginal_loss_driver_candidate_guardrail_max_decimal_odds
        ),
        marginal_loss_driver_candidate_guardrail_max_model_edge=(
            args.marginal_loss_driver_candidate_guardrail_max_model_edge
        ),
        marginal_loss_driver_candidate_guardrail_max_calibration_score=(
            args.marginal_loss_driver_candidate_guardrail_max_calibration_score
        ),
        marginal_loss_driver_candidate_guardrail_max_model_confidence_score=(
            args.marginal_loss_driver_candidate_guardrail_max_model_confidence_score
        ),
        marginal_loss_driver_candidate_guardrail_max_odds_stability_score=(
            args.marginal_loss_driver_candidate_guardrail_max_odds_stability_score
        ),
        marginal_loss_driver_candidate_guardrail_competition_ids=tuple(
            _csv(args.marginal_loss_driver_candidate_guardrail_competitions)
        ),
        marginal_loss_driver_candidate_soft_penalty=(
            args.marginal_loss_driver_candidate_soft_penalty
        ),
        marginal_loss_driver_candidate_soft_penalty_strength=(
            args.marginal_loss_driver_candidate_soft_penalty_strength
        ),
        final_answer_quality_signal_penalty=(args.final_answer_quality_signal_penalty),
        final_answer_quality_signal_penalty_strength=(
            args.final_answer_quality_signal_penalty_strength
        ),
        final_answer_quality_signal_probability_min=(
            args.final_answer_quality_signal_probability_min
        ),
        final_answer_quality_signal_probability_max=(
            args.final_answer_quality_signal_probability_max
        ),
        final_answer_quality_signal_min_decimal_odds=(
            args.final_answer_quality_signal_min_decimal_odds
        ),
        final_answer_quality_signal_max_decimal_odds=(
            args.final_answer_quality_signal_max_decimal_odds
        ),
        final_answer_quality_signal_max_model_edge=(
            args.final_answer_quality_signal_max_model_edge
        ),
        final_answer_quality_signal_score_min=(args.final_answer_quality_signal_score_min),
        final_answer_quality_signal_score_max=(args.final_answer_quality_signal_score_max),
        final_answer_quality_signal_competition_ids=tuple(
            _csv(args.final_answer_quality_signal_competitions)
        ),
        correct_score_final_answer_lane=args.correct_score_final_answer_lane,
        correct_score_final_answer_lane_pass_types=tuple(
            _csv(args.correct_score_final_answer_lane_pass_types)
        ),
        correct_score_final_answer_lane_mode=cast(
            RecommendationMode,
            args.correct_score_final_answer_lane_mode,
        ),
        correct_score_final_answer_lane_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.correct_score_final_answer_lane_modes)
        ),
        correct_score_final_answer_lane_candidate_limit=(
            args.correct_score_final_answer_lane_candidate_limit
        ),
        correct_score_final_answer_lane_min_probability=(
            args.correct_score_final_answer_lane_min_probability
        ),
        correct_score_final_answer_lane_min_correct_score_probability=(
            args.correct_score_final_answer_lane_min_correct_score_probability
        ),
        correct_score_final_answer_lane_max_correct_score_per_selection=(
            args.correct_score_final_answer_lane_max_correct_score_per_selection
        ),
        correct_score_final_answer_lane_score_boost=(
            args.correct_score_final_answer_lane_score_boost
        ),
        correct_score_final_answer_lane_max_hit_probability_deficit=(
            args.correct_score_final_answer_lane_max_hit_probability_deficit
        ),
        correct_score_final_answer_lane_min_roi_delta=(
            args.correct_score_final_answer_lane_min_roi_delta
        ),
        correct_score_final_answer_lane_outcomes=tuple(
            _csv(args.correct_score_final_answer_lane_outcomes)
        ),
        final_answer_selection_value_signal=(
            args.final_answer_selection_value_signal
        ),
        final_answer_selection_value_signal_strength=(
            args.final_answer_selection_value_signal_strength
        ),
        final_answer_selection_value_signal_probability_min=(
            args.final_answer_selection_value_signal_probability_min
        ),
        final_answer_selection_value_signal_probability_max=(
            args.final_answer_selection_value_signal_probability_max
        ),
        final_answer_selection_value_signal_min_decimal_odds=(
            args.final_answer_selection_value_signal_min_decimal_odds
        ),
        final_answer_selection_value_signal_max_decimal_odds=(
            args.final_answer_selection_value_signal_max_decimal_odds
        ),
        final_answer_selection_value_signal_max_model_edge=(
            args.final_answer_selection_value_signal_max_model_edge
        ),
        final_answer_selection_value_signal_score_min=(
            args.final_answer_selection_value_signal_score_min
        ),
        final_answer_selection_value_signal_score_max=(
            args.final_answer_selection_value_signal_score_max
        ),
        final_answer_selection_value_signal_competition_ids=tuple(
            _csv(args.final_answer_selection_value_signal_competitions)
        ),
        final_answer_selection_value_signal_outcomes=tuple(
            _csv(args.final_answer_selection_value_signal_outcomes)
        ),
        final_answer_selection_value_signal_max_hit_probability_deficit=(
            args.final_answer_selection_value_signal_max_hit_probability_deficit
        ),
        final_answer_selection_value_signal_min_option_roi=(
            args.final_answer_selection_value_signal_min_option_roi
        ),
        final_answer_selection_value_signal_max_option_risk_score=(
            args.final_answer_selection_value_signal_max_option_risk_score
        ),
        final_answer_segment_penalty=args.final_answer_segment_penalty,
        final_answer_segment_penalty_strength=(
            args.final_answer_segment_penalty_strength
        ),
        final_answer_segment_pass_types=tuple(
            _csv(args.final_answer_segment_pass_types)
        ),
        final_answer_segment_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.final_answer_segment_modes)
        ),
        final_answer_segment_competition_ids=tuple(
            _csv(args.final_answer_segment_competitions)
        ),
        final_answer_segment_season_ids=tuple(
            _csv(args.final_answer_segment_seasons)
        ),
        final_answer_segment_min_competition_season_index=(
            args.final_answer_segment_min_competition_season_index
        ),
        final_answer_segment_max_competition_season_index=(
            args.final_answer_segment_max_competition_season_index
        ),
        final_answer_segment_min_hit_probability=(
            args.final_answer_segment_min_hit_probability
        ),
        final_answer_segment_max_hit_probability=(
            args.final_answer_segment_max_hit_probability
        ),
        final_answer_segment_min_odds_product=(
            args.final_answer_segment_min_odds_product
        ),
        final_answer_segment_max_odds_product=(
            args.final_answer_segment_max_odds_product
        ),
        final_answer_segment_min_average_leg_decimal_odds=(
            args.final_answer_segment_min_average_leg_decimal_odds
        ),
        final_answer_segment_max_average_leg_decimal_odds=(
            args.final_answer_segment_max_average_leg_decimal_odds
        ),
        final_answer_stake_efficiency_guard=(
            args.final_answer_stake_efficiency_guard
        ),
        final_answer_stake_efficiency_penalty_strength=(
            args.final_answer_stake_efficiency_penalty_strength
        ),
        final_answer_stake_efficiency_max_stake_multiplier=(
            args.final_answer_stake_efficiency_max_stake_multiplier
        ),
        final_answer_stake_efficiency_min_roi=(
            args.final_answer_stake_efficiency_min_roi
        ),
        final_answer_stake_efficiency_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.final_answer_stake_efficiency_modes)
        ),
        final_answer_stake_efficiency_scope=cast(
            HistoricalFinalAnswerStakeEfficiencyScope,
            args.final_answer_stake_efficiency_scope,
        ),
    )
    result: (
        HistoricalRecommendationBacktestSuiteResult
        | HistoricalRecommendationBacktestComparisonResult
        | HistoricalRecommendationBacktestResult
    )
    exclude: Any
    if args.suite or len(historical_slices) > 1:
        result = run_historical_recommendation_backtest_suite(
            historical_slices,
            options=options,
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="solver",
        )
        exclude = {
            "comparisons": {
                "__all__": {
                    "baseline": {
                        "final_answer": {"option"},
                        "scenarios": {"__all__": {"option"}},
                    },
                    "candidate": {
                        "final_answer": {"option"},
                        "scenarios": {"__all__": {"option"}},
                    },
                }
            }
        }
    elif args.compare_solver:
        historical_slice = historical_slices[0]
        result = run_historical_recommendation_backtest_comparison(
            historical_slice,
            options=options,
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="solver",
        )
        exclude = {
            "baseline": {
                "final_answer": {"option"},
                "scenarios": {"__all__": {"option"}},
            },
            "candidate": {
                "final_answer": {"option"},
                "scenarios": {"__all__": {"option"}},
            },
        }
    else:
        historical_slice = historical_slices[0]
        result = run_historical_recommendation_backtest(
            historical_slice,
            options=options,
        )
        exclude = {
            "final_answer": {"option"},
            "scenarios": {"__all__": {"option"}},
        }
    print(
        dumps(
            result.model_dump(
                mode="json",
                exclude=exclude,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _parse_args() -> Namespace:
    parser = ArgumentParser(description="Run frozen historical recommendation backtest slices.")
    parser.add_argument("slice_paths", nargs="+", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--allowed-markets", default="1x2")
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--upset-exposure-reserve", action="store_true")
    parser.add_argument("--upset-exposure-reserve-fixture-count", type=int, default=0)
    parser.add_argument(
        "--upset-exposure-reserve-max-candidates-per-fixture",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-exposure-reserve-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane", action="store_true")
    parser.add_argument("--upset-final-answer-lane-pass-type", default="1x1")
    parser.add_argument(
        "--upset-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--upset-final-answer-lane-candidate-limit", type=int, default=24)
    parser.add_argument(
        "--upset-final-answer-lane-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-final-answer-lane-min-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-min-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-max-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-competitions", default="")
    parser.add_argument("--upset-final-answer-lane-excluded-competitions", default="")
    parser.add_argument(
        "--upset-final-answer-lane-min-calibration-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-model-confidence-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-odds-stability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-max-volatility-penalty", type=float)
    parser.add_argument(
        "--upset-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-max-signal-calibration-risk",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-signal-reliability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-score-boost", type=float, default=0.0)
    parser.add_argument("--short-price-negative-edge-guardrail", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--short-price-negative-edge-min-probability",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--short-price-negative-edge-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument("--short-price-negative-edge-soft-penalty", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-strength",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-competitions",
        default="",
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail",
        action="store_true",
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-probability-min",
        type=float,
        default=0.65,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-probability-max",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-max-decimal-odds",
        type=float,
        default=1.50,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-max-model-edge",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-max-calibration-score",
        type=float,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-max-model-confidence-score",
        type=float,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-max-odds-stability-score",
        type=float,
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-guardrail-competitions",
        default="",
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-soft-penalty",
        action="store_true",
    )
    parser.add_argument(
        "--marginal-loss-driver-candidate-soft-penalty-strength",
        type=float,
        default=0.20,
    )
    parser.add_argument("--final-answer-quality-signal-penalty", action="store_true")
    parser.add_argument(
        "--final-answer-quality-signal-penalty-strength",
        type=float,
        default=0.04,
    )
    parser.add_argument(
        "--final-answer-quality-signal-probability-min",
        type=float,
        default=0.65,
    )
    parser.add_argument(
        "--final-answer-quality-signal-probability-max",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--final-answer-quality-signal-min-decimal-odds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--final-answer-quality-signal-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-score-min",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-score-max",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-competitions",
        default="",
    )
    parser.add_argument("--correct-score-final-answer-lane", action="store_true")
    parser.add_argument("--correct-score-final-answer-lane-pass-types", default="2x1")
    parser.add_argument(
        "--correct-score-final-answer-lane-mode",
        default="single",
        choices=("single", "multiple"),
    )
    parser.add_argument("--correct-score-final-answer-lane-modes", default="")
    parser.add_argument(
        "--correct-score-final-answer-lane-candidate-limit",
        type=int,
        default=64,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-min-probability",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-min-correct-score-probability",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-max-correct-score-per-selection",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-score-boost",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument("--correct-score-final-answer-lane-min-roi-delta", type=float)
    parser.add_argument("--correct-score-final-answer-lane-outcomes", default="")
    parser.add_argument("--final-answer-selection-value-signal", action="store_true")
    parser.add_argument(
        "--final-answer-selection-value-signal-strength",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-probability-min",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-probability-max",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-min-decimal-odds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-max-decimal-odds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-max-model-edge",
        type=float,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-score-min",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-score-max",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-competitions",
        default="",
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-outcomes",
        default="",
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-min-option-roi",
        type=float,
    )
    parser.add_argument(
        "--final-answer-selection-value-signal-max-option-risk-score",
        type=float,
    )
    parser.add_argument("--final-answer-segment-penalty", action="store_true")
    parser.add_argument(
        "--final-answer-segment-penalty-strength",
        type=float,
        default=0.04,
    )
    parser.add_argument("--final-answer-segment-pass-types", default="")
    parser.add_argument("--final-answer-segment-modes", default="")
    parser.add_argument("--final-answer-segment-competitions", default="")
    parser.add_argument("--final-answer-segment-seasons", default="")
    parser.add_argument("--final-answer-segment-min-competition-season-index", type=int)
    parser.add_argument("--final-answer-segment-max-competition-season-index", type=int)
    parser.add_argument("--final-answer-segment-min-hit-probability", type=float)
    parser.add_argument("--final-answer-segment-max-hit-probability", type=float)
    parser.add_argument("--final-answer-segment-min-odds-product", type=float)
    parser.add_argument("--final-answer-segment-max-odds-product", type=float)
    parser.add_argument(
        "--final-answer-segment-min-average-leg-decimal-odds",
        type=float,
    )
    parser.add_argument(
        "--final-answer-segment-max-average-leg-decimal-odds",
        type=float,
    )
    parser.add_argument("--final-answer-stake-efficiency-guard", action="store_true")
    parser.add_argument(
        "--final-answer-stake-efficiency-penalty-strength",
        type=float,
        default=0.08,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-max-stake-multiplier",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-min-roi",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-modes",
        default="multiple",
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-scope",
        choices=["all", "quality_signal_affected"],
        default="all",
    )
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--compare-solver", action="store_true")
    parser.add_argument(
        "--suite",
        action="store_true",
        help="Run an aggregate heuristic-vs-solver comparison across all slice paths.",
    )
    return parser.parse_args()


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0
