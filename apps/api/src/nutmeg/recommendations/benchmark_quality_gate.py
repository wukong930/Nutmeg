from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.benchmark_runner import (
    PostgresRecommendationBenchmarkRunRepository,
    RecommendationBenchmarkDatabaseExecutor,
    StoredRecommendationBenchmarkRun,
)
from nutmeg.recommendations.global_planner_short_odds_adapter_gate import (
    HistoricalGlobalPlannerShortOddsAdapterGateReport,
    load_global_planner_short_odds_adapter_gate_report,
)
from nutmeg.recommendations.global_planner_short_odds_adapter_sample_expansion import (
    HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport,
    load_global_planner_short_odds_adapter_sample_expansion_report,
)
from nutmeg.recommendations.historical_budget_stability_audit import (
    HistoricalBudgetStabilityAuditReport,
    load_historical_budget_stability_audit_report,
)
from nutmeg.recommendations.historical_correct_score_admission import (
    HistoricalCorrectScoreAdmissionReport,
    load_historical_correct_score_admission_report,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditReport,
    load_historical_final_answer_market_concentration_audit_report,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_runtime_replay import (
    HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    HistoricalMarketMovementRiskFilterRuntimeActivationReport,
    load_historical_market_movement_risk_filter_runtime_activation_report,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_sample_expansion import (
    HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
    load_historical_market_movement_runtime_activation_sample_expansion_report,
)
from nutmeg.recommendations.models import RecommendationStrategy
from nutmeg.recommendations.recommendation_strategy_default_path_isolation import (
    RecommendationStrategyDefaultPathIsolationReport,
    load_recommendation_strategy_default_path_isolation_report,
)
from nutmeg.recommendations.recommendation_strategy_promotion_gate import (
    RecommendationStrategyPromotionGateReport,
    load_recommendation_strategy_promotion_gate_report,
)
from nutmeg.recommendations.recommendation_strategy_staged_activation_smoke import (
    RecommendationStrategyStagedActivationSmokeReport,
    load_recommendation_strategy_staged_activation_smoke_report,
)
from nutmeg.recommendations.replacement_reranker_shadow_admission import (
    HistoricalReplacementRerankerShadowAdmissionReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_profile_switch import (
    HistoricalShortOddsRuntimeProfileSwitchReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

if TYPE_CHECKING:
    from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segmented_governance_review import (  # noqa: E501
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport,
    )

    from .historical_market_movement_runtime_activation_segment_replay_batch_gate import (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport,
    )
    from .historical_prematch_feature_quality_cycle import (
        HistoricalPrematchFeatureQualityCycleResult,
    )
    from .historical_prematch_feature_rolling_admission import (
        HistoricalPrematchFeatureRollingAdmissionReport,
    )
    from .historical_prematch_feature_sample_readiness import (
        HistoricalPrematchFeatureSampleReadinessReport,
    )
    from .historical_probability_calibration_profile_model_quality_gate import (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport,
    )
    from .historical_probability_calibration_profile_rolling_admission import (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    )

type RecommendationBenchmarkQualityGateCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type RecommendationBenchmarkQualityGateStatus = Literal[
    "passed",
    "failed",
    "insufficient_history",
]

RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1 = "short_odds_candidate_v1"
RUNTIME_PROFILE_SWITCH_PRESETS = (RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1,)
FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1 = (
    "final_answer_segment_penalty_ger_regime_holdout_v1"
)
FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESETS = (
    FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1,
)
RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1 = (
    "probability_preserving_13change_v1"
)
RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1 = (
    "probability_preserving_quality_score_v1"
)
RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS = (
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
)
UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1 = (
    "v3_2_unified_candidate_pool_guard_v1"
)
UNIFIED_CANDIDATE_POOL_GUARD_PRESETS = (
    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
)
SHORT_ODDS_RUNTIME_PROFILE_SWITCH_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_"
    "runtime_profile_switch_v1.json"
)
SHORT_ODDS_RUNTIME_PROFILE_SWITCH_REPLAY_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_"
    "runtime_shadow_replay_switch_staged_v1.json"
)
FINAL_ANSWER_SEGMENT_PENALTY_GER_REGIME_RUNTIME_REPLAY_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_"
    "penalty_ger_regime_original_harm_guard_runtime_replay_v1.json"
)
PROBABILITY_PRESERVING_13CHANGE_STRATEGY_PROMOTION_GATE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_adjacent_threshold_13plus_strategy_promotion_gate_v1.json"
)
PROBABILITY_PRESERVING_13CHANGE_STAGED_ACTIVATION_SMOKE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_adjacent_threshold_13plus_staged_activation_smoke_v1.json"
)
PROBABILITY_PRESERVING_13CHANGE_DEFAULT_PATH_ISOLATION_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_adjacent_threshold_13plus_default_path_isolation_v1.json"
)
PROBABILITY_PRESERVING_QUALITY_SCORE_STRATEGY_PROMOTION_GATE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_quality_score_strategy_promotion_gate_v1.json"
)
PROBABILITY_PRESERVING_QUALITY_SCORE_STAGED_ACTIVATION_SMOKE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_quality_score_staged_activation_smoke_v1.json"
)
PROBABILITY_PRESERVING_QUALITY_SCORE_DEFAULT_PATH_ISOLATION_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_"
    "probability_preserving_quality_score_default_path_isolation_v1.json"
)


class RecommendationBenchmarkQualityGateRepository(Protocol):
    def list_history(
        self,
        *,
        benchmark_key: str | None = None,
        strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkRun]:
        """Read persisted recommendation benchmark runs for quality checks."""


class RecommendationBenchmarkQualityGateOptions(BaseModel):
    benchmark_key: str | None = Field(default=None, min_length=1)
    strategy: RecommendationStrategy | None = None
    history_limit: int = Field(default=2, ge=1, le=200)
    allow_missing_history: bool = False
    min_scenario_count: int = Field(default=1, ge=0)
    min_completed_ratio: float | None = Field(default=1.0, ge=0.0, le=1.0)
    max_failed_count: int | None = Field(default=0, ge=0)
    max_warning_count: int | None = Field(default=None, ge=0)
    min_global_best_selected_count: int = Field(default=0, ge=0)
    min_global_best_candidate_count: int = Field(default=0, ge=0)
    min_global_best_generated_option_count: int = Field(default=0, ge=0)
    min_core_replay_ready_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    min_chain_integrity_ready_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    max_chain_integrity_critical_issue_count: int | None = Field(default=0, ge=0)
    min_successor_chain_evaluation_passed_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_successor_chain_effective_leaf_count: int = Field(default=0, ge=0)
    max_successor_chain_critical_issue_count: int | None = Field(default=0, ge=0)
    max_successor_chain_ambiguous_source_count: int | None = Field(default=0, ge=0)
    max_successor_chain_source_status_sync_required_count: int | None = Field(
        default=None,
        ge=0,
    )
    max_ambiguous_successor_source_count: int | None = Field(default=0, ge=0)
    max_stale_recommendation_count: int | None = Field(default=0, ge=0)
    max_successor_recompute_required_count: int | None = Field(default=0, ge=0)
    min_final_hit_sample_size: int = Field(default=0, ge=0)
    min_final_hit_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    min_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_average_core_replay_roi: float | None = None
    min_upset_capture_sample_size: int = Field(default=0, ge=0)
    min_upset_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    historical_suite_quality_gate_report_path: Path | None = None
    require_historical_suite_quality_gate: bool = False
    require_historical_suite_lifecycle_evidence: bool = True
    require_historical_suite_lifecycle_source_status_synced: bool = True
    require_historical_suite_successor_chain_evaluation: bool = False
    min_historical_suite_slice_count: int = Field(default=0, ge=0)
    min_historical_suite_comparison_count: int = Field(default=0, ge=0)
    min_historical_suite_candidate_final_hit_sample_size: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_candidate_final_hit_coverage_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_historical_suite_candidate_dynamic_mixed_final_answer_count: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_candidate_dynamic_mixed_final_answer_rate: float | None = (
        Field(default=None, ge=0.0, le=1.0)
    )
    min_historical_suite_candidate_handicap_final_answer_count: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_candidate_correct_score_final_answer_count: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_candidate_multiple_choice_final_answer_count: int = Field(
        default=0,
        ge=0,
    )
    max_historical_suite_failed_check_count: int | None = Field(default=0, ge=0)
    min_historical_suite_lifecycle_effective_leaf_count: int = Field(default=0, ge=0)
    min_historical_suite_lifecycle_active_edge_count: int = Field(default=0, ge=0)
    max_historical_suite_lifecycle_critical_issue_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_historical_suite_lifecycle_source_status_sync_required_count: int | None = (
        Field(default=0, ge=0)
    )
    min_historical_suite_successor_effective_leaf_count: int = Field(default=0, ge=0)
    min_historical_suite_successor_active_edge_count: int = Field(default=0, ge=0)
    max_historical_suite_successor_critical_issue_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_historical_suite_successor_ambiguous_source_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_historical_suite_successor_source_status_sync_required_count: int | None = (
        Field(default=0, ge=0)
    )
    require_historical_suite_market_movement_runtime_replay: bool = False
    require_historical_suite_market_movement_runtime_replay_allowed: bool = True
    require_historical_suite_market_movement_runtime_replay_passed_status: bool = True
    min_historical_suite_market_movement_runtime_replay_rule_count: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_market_movement_runtime_replay_selected_rule_count: int = (
        Field(default=0, ge=0)
    )
    min_historical_suite_market_movement_runtime_replay_accepted_count: int = Field(
        default=0,
        ge=0,
    )
    min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count: int = (
        Field(default=0, ge=0)
    )
    min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count: int = (
        Field(default=0, ge=0)
    )
    min_historical_suite_market_movement_runtime_replay_final_hit_rate_delta: (
        float | None
    ) = 0.0
    min_historical_suite_market_movement_runtime_replay_roi_delta: float | None = 0.0
    min_historical_suite_market_movement_runtime_replay_profit_loss_delta: (
        float | None
    ) = 0.0
    max_historical_suite_market_movement_runtime_replay_brier_score_delta: (
        float | None
    ) = 0.0
    max_historical_suite_market_movement_runtime_replay_log_loss_delta: float | None = (
        0.0
    )
    max_historical_suite_market_movement_runtime_replay_mean_calibration_error_delta: (
        float | None
    ) = 0.0
    require_historical_suite_market_movement_runtime_replay_production_unchanged: bool = (
        True
    )
    require_historical_suite_market_movement_runtime_replay_public_response_unchanged: bool = (
        True
    )
    market_movement_runtime_activation_report_path: Path | None = None
    require_market_movement_runtime_activation: bool = False
    require_market_movement_runtime_activation_ready: bool = True
    min_market_movement_runtime_activation_rule_count: int = Field(default=0, ge=0)
    min_market_movement_runtime_activation_selected_rule_count: int = Field(
        default=0,
        ge=0,
    )
    max_market_movement_runtime_activation_selected_rule_count: int | None = Field(
        default=1,
        ge=0,
    )
    min_market_movement_runtime_activation_adjusted_fixture_count: int = Field(
        default=0,
        ge=0,
    )
    min_market_movement_runtime_activation_adjusted_prediction_count: int = Field(
        default=0,
        ge=0,
    )
    min_market_movement_runtime_activation_final_hit_rate_delta: float | None = 0.0
    min_market_movement_runtime_activation_roi_delta: float | None = 0.0
    min_market_movement_runtime_activation_profit_loss_delta: float | None = 0.0
    max_market_movement_runtime_activation_brier_score_delta: float | None = 0.0
    max_market_movement_runtime_activation_log_loss_delta: float | None = 0.0
    max_market_movement_runtime_activation_mean_calibration_error_delta: (
        float | None
    ) = 0.0
    require_market_movement_runtime_activation_no_default_profile_write: bool = True
    require_market_movement_runtime_activation_no_default_path_change: bool = True
    require_market_movement_runtime_activation_no_production_change: bool = True
    require_market_movement_runtime_activation_no_public_response_change: bool = True
    market_movement_runtime_activation_sample_expansion_report_path: Path | None = None
    require_market_movement_runtime_activation_sample_expansion: bool = False
    require_market_movement_runtime_activation_sample_expansion_promotion_ready: bool = (
        False
    )
    market_movement_runtime_activation_segment_replay_batch_gate_report_path: (
        Path | None
    ) = None
    require_market_movement_runtime_activation_segment_replay_batch_gate: bool = False
    require_market_movement_runtime_activation_segment_replay_batch_ready: bool = True
    require_market_movement_runtime_activation_segment_replay_batch_promotion_ready: bool = (
        False
    )
    min_market_movement_runtime_activation_segment_replay_batch_report_count: int = (
        Field(default=0, ge=0)
    )
    min_market_movement_runtime_activation_segment_replay_batch_passed_count: int = (
        Field(default=0, ge=0)
    )
    min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count: int = Field(
        default=0,
        ge=0,
    )
    min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count: int = Field(  # noqa: E501
        default=0,
        ge=0,
    )
    budget_stability_audit_report_path: Path | None = None
    require_budget_stability_audit: bool = False
    min_budget_stability_slice_count: int = Field(default=0, ge=0)
    min_budget_stability_comparable_count: int = Field(default=0, ge=0)
    max_budget_stability_signature_change_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    max_budget_stability_harmful_change_count: int | None = Field(default=None, ge=0)
    min_budget_stability_hit_delta_count: int | None = None
    min_budget_stability_profit_loss_delta: float | None = None
    min_budget_stability_roi_delta: float | None = None
    max_budget_stability_warning_count: int | None = Field(default=0, ge=0)
    final_answer_market_concentration_audit_report_path: Path | None = None
    require_final_answer_market_concentration_audit: bool = False
    min_final_answer_market_concentration_slice_count: int = Field(default=0, ge=0)
    min_final_answer_market_concentration_dynamic_mixed_final_answer_count: int = (
        Field(default=0, ge=0)
    )
    min_final_answer_market_concentration_effective_constraint_profile_count: int = (
        Field(default=0, ge=0)
    )
    max_final_answer_market_concentration_failed_check_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_final_answer_market_concentration_warning_count: int | None = Field(
        default=0,
        ge=0,
    )
    correct_score_admission_report_path: Path | None = None
    require_correct_score_admission: bool = False
    require_correct_score_admission_holdout_allowed: bool = True
    require_correct_score_admission_production_allowed: bool = False
    min_correct_score_admission_slice_count: int = Field(default=0, ge=0)
    min_correct_score_admission_comparison_count: int = Field(default=0, ge=0)
    min_correct_score_admission_candidate_final_hit_sample_size: int = Field(
        default=0,
        ge=0,
    )
    min_correct_score_admission_candidate_final_hit_coverage_ratio: (
        float | None
    ) = Field(default=None, ge=0.0, le=1.0)
    min_correct_score_admission_candidate_final_hit_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_correct_score_admission_candidate_roi: float | None = None
    min_correct_score_admission_candidate_correct_score_final_answer_count: int = (
        Field(default=0, ge=0)
    )
    min_correct_score_admission_candidate_correct_score_final_answer_rate: (
        float | None
    ) = Field(default=None, ge=0.0, le=1.0)
    min_correct_score_admission_final_hit_rate_delta: float | None = 0.0
    min_correct_score_admission_roi_delta: float | None = 0.0
    min_correct_score_admission_profit_loss_delta: float | None = 0.0
    max_correct_score_admission_brier_score_delta: float | None = 0.0
    max_correct_score_admission_log_loss_delta: float | None = 0.0
    max_correct_score_admission_mean_calibration_error_delta: float | None = 0.0
    max_correct_score_admission_failed_check_count: int | None = Field(
        default=None,
        ge=0,
    )
    max_correct_score_admission_warning_count: int | None = Field(default=None, ge=0)
    require_unified_candidate_pool: bool = False
    min_unified_candidate_pool_present_count: int = Field(default=0, ge=0)
    min_unified_candidate_pool_valid_candidate_count: int = Field(default=0, ge=0)
    min_unified_candidate_pool_unique_family_count: int = Field(default=0, ge=0)
    max_unified_candidate_pool_selection_mismatch_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_unified_candidate_pool_selected_2x1_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    require_unified_candidate_pool_multiple_value_admission: bool = False
    min_unified_candidate_pool_multiple_value_candidate_count: int = Field(
        default=0,
        ge=0,
    )
    min_unified_candidate_pool_multiple_value_admitted_candidate_count: int = Field(
        default=0,
        ge=0,
    )
    min_unified_candidate_pool_multiple_value_extra_option_count: int = Field(
        default=0,
        ge=0,
    )
    max_unified_candidate_pool_multiple_value_rejected_candidate_count: (
        int | None
    ) = Field(default=None, ge=0)
    max_unified_candidate_pool_selected_multiple_value_rejected_count: (
        int | None
    ) = Field(default=0, ge=0)
    unified_candidate_pool_guard_preset: str | None = Field(default=None, min_length=1)
    runtime_profile_switch_preset: str | None = Field(default=None, min_length=1)
    runtime_profile_switch_report_path: Path | None = None
    runtime_profile_switch_replay_report_path: Path | None = None
    require_runtime_profile_switch_gate: bool = False
    require_runtime_profile_switch_replay: bool = True
    require_runtime_profile_switch_staged_only: bool = True
    min_runtime_profile_switch_rule_count: int = Field(default=1, ge=0)
    min_runtime_profile_switch_allowed_competition_count: int = Field(default=4, ge=0)
    min_runtime_profile_switch_final_answer_count: int = Field(default=30, ge=0)
    min_runtime_profile_switch_changed_final_answer_count: int = Field(default=5, ge=0)
    min_runtime_profile_switch_final_answer_hit_rate_delta: float = 0.0
    min_runtime_profile_switch_roi_delta: float = 0.0
    min_runtime_profile_switch_profit_loss_delta: float = 0.0
    max_runtime_profile_switch_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    max_runtime_profile_switch_final_hit_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    max_runtime_profile_switch_profit_loss_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    min_runtime_profile_switch_average_hit_probability_delta: float = -0.02
    final_answer_segment_penalty_runtime_replay_preset: str | None = Field(
        default=None,
        min_length=1,
    )
    final_answer_segment_penalty_runtime_replay_report_path: Path | None = None
    require_final_answer_segment_penalty_runtime_replay: bool = False
    require_final_answer_segment_penalty_runtime_replay_holdout_allowed: bool = True
    require_final_answer_segment_penalty_runtime_replay_runtime_allowed: bool = False
    min_final_answer_segment_penalty_runtime_replay_rule_count: int = Field(
        default=1,
        ge=0,
    )
    min_final_answer_segment_penalty_runtime_replay_selected_rule_count: int = Field(
        default=1,
        ge=0,
    )
    max_final_answer_segment_penalty_runtime_replay_selected_rule_count: int | None = (
        Field(default=1, ge=0)
    )
    min_final_answer_segment_penalty_runtime_replay_final_answer_count: int = Field(
        default=30,
        ge=0,
    )
    min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count: int = (
        Field(default=1, ge=0)
    )
    min_final_answer_segment_penalty_runtime_replay_penalty_option_count: int = Field(
        default=1,
        ge=0,
    )
    min_final_answer_segment_penalty_runtime_replay_hit_count_delta: int = 0
    min_final_answer_segment_penalty_runtime_replay_hit_rate_delta: float = 0.0
    min_final_answer_segment_penalty_runtime_replay_roi_delta: float = 0.0
    min_final_answer_segment_penalty_runtime_replay_profit_loss_delta: float = 0.0
    min_final_answer_segment_penalty_runtime_replay_candidate_roi: float | None = None
    max_final_answer_segment_penalty_runtime_replay_brier_score_delta: float | None = (
        0.0
    )
    max_final_answer_segment_penalty_runtime_replay_log_loss_delta: float | None = 0.0
    max_final_answer_segment_penalty_runtime_replay_calibration_error_delta: (
        float | None
    ) = 0.0
    max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline: (
        int | None
    ) = Field(default=0, ge=0)
    max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline: (
        int | None
    ) = Field(default=0, ge=0)
    max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline: (
        int | None
    ) = Field(default=0, ge=0)
    require_final_answer_segment_penalty_runtime_replay_no_production_change: bool = True
    require_final_answer_segment_penalty_runtime_replay_no_public_response_change: (
        bool
    ) = True
    replacement_reranker_shadow_admission_report_path: Path | None = None
    require_replacement_reranker_shadow_admission: bool = False
    require_replacement_reranker_runtime_candidate_allowed: bool = True
    require_replacement_reranker_scoped_evidence: bool = False
    require_replacement_reranker_prematch_source_surface: bool = False
    min_replacement_reranker_scope_final_answer_count: int = Field(default=0, ge=0)
    min_replacement_reranker_shadow_final_answer_count: int = Field(default=0, ge=0)
    min_replacement_reranker_changed_from_model_top_count: int = Field(default=0, ge=0)
    min_replacement_reranker_hit_delta_vs_model_top: int = 0
    min_replacement_reranker_profit_loss_delta_vs_model_top: float = 0.0
    min_replacement_reranker_roi_delta_vs_model_top: float = 0.0
    max_replacement_reranker_harm_count_vs_model_top: int | None = Field(
        default=0,
        ge=0,
    )
    max_replacement_reranker_final_hit_harm_count_vs_model_top: int | None = Field(
        default=0,
        ge=0,
    )
    max_replacement_reranker_profit_loss_harm_count_vs_model_top: int | None = Field(
        default=0,
        ge=0,
    )
    max_replacement_reranker_failed_fold_count: int | None = Field(default=0, ge=0)
    min_replacement_reranker_active_competition_fold_count: int = Field(default=0, ge=0)
    min_replacement_reranker_active_season_fold_count: int = Field(default=0, ge=0)
    min_replacement_reranker_active_rolling_fold_count: int = Field(default=0, ge=0)
    global_planner_short_odds_adapter_gate_report_path: Path | None = None
    require_global_planner_short_odds_adapter_gate: bool = False
    require_global_planner_short_odds_adapter_default_path_unchanged: bool = True
    require_global_planner_short_odds_adapter_shadow_path_unchanged: bool = True
    require_global_planner_short_odds_adapter_explicit_opt_in_changed: bool = True
    min_global_planner_short_odds_adapter_runtime_final_answer_count: int = Field(
        default=30,
        ge=0,
    )
    min_global_planner_short_odds_adapter_runtime_changed_final_answer_count: int = (
        Field(default=5, ge=0)
    )
    min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta: float = (
        0.0
    )
    min_global_planner_short_odds_adapter_runtime_roi_delta: float = 0.0
    min_global_planner_short_odds_adapter_runtime_profit_loss_delta: float = 0.0
    max_global_planner_short_odds_adapter_runtime_harm_count_vs_original: (
        int | None
    ) = Field(default=0, ge=0)
    max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original: (
        int | None
    ) = Field(default=0, ge=0)
    max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original: (
        int | None
    ) = Field(default=0, ge=0)
    min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta: (
        float
    ) = -0.02
    require_global_planner_short_odds_adapter_runtime_public_unchanged: bool = True
    require_global_planner_short_odds_adapter_runtime_production_unchanged: bool = True
    global_planner_short_odds_adapter_sample_expansion_report_path: Path | None = None
    require_global_planner_short_odds_adapter_sample_expansion: bool = False
    require_global_planner_short_odds_adapter_sample_expansion_promotion_ready: (
        bool
    ) = False
    recommendation_strategy_governance_preset: str | None = Field(
        default=None,
        min_length=1,
    )
    recommendation_strategy_promotion_gate_report_path: Path | None = None
    require_recommendation_strategy_promotion_gate: bool = False
    require_recommendation_strategy_gate_ready: bool = True
    min_recommendation_strategy_gate_final_answer_count: int = Field(
        default=30,
        ge=0,
    )
    min_recommendation_strategy_gate_changed_final_answer_count: int = Field(
        default=1,
        ge=0,
    )
    min_recommendation_strategy_gate_hit_delta_count: int = 0
    min_recommendation_strategy_gate_profit_loss_delta: float = 0.0
    min_recommendation_strategy_gate_minimum_roi_delta: float | None = 0.0
    max_recommendation_strategy_gate_harm_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_recommendation_strategy_gate_final_hit_harm_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_recommendation_strategy_gate_profit_loss_harm_count: int | None = Field(
        default=0,
        ge=0,
    )
    require_recommendation_strategy_gate_no_production_change: bool = True
    require_recommendation_strategy_gate_no_public_response_change: bool = True
    recommendation_strategy_staged_activation_smoke_report_path: Path | None = None
    require_recommendation_strategy_staged_activation_smoke: bool = False
    require_recommendation_strategy_staged_activation_ready: bool = True
    require_recommendation_strategy_staged_no_default_write: bool = True
    require_recommendation_strategy_staged_no_production_change: bool = True
    require_recommendation_strategy_staged_no_public_response_change: bool = True
    min_recommendation_strategy_staged_rule_count: int = Field(default=1, ge=0)
    min_recommendation_strategy_staged_allowed_competition_count: int = Field(
        default=1,
        ge=0,
    )
    recommendation_strategy_default_path_isolation_report_path: Path | None = None
    require_recommendation_strategy_default_path_isolation: bool = False
    require_recommendation_strategy_default_path_isolated: bool = True
    require_recommendation_strategy_default_adapter_disabled: bool = True
    require_recommendation_strategy_default_adapter_unchanged: bool = True
    require_recommendation_strategy_explicit_opt_in_applied: bool = True
    require_recommendation_strategy_isolation_no_default_write: bool = True
    require_recommendation_strategy_isolation_no_production_change: bool = True
    require_recommendation_strategy_isolation_no_public_response_change: bool = True
    probability_calibration_profile_rolling_admission_report_path: Path | None = None
    require_probability_calibration_profile_rolling_admission: bool = False
    require_probability_calibration_profile_candidate_allowed: bool = True
    require_probability_calibration_profile_active_profile: bool = True
    min_probability_calibration_profile_overall_adjusted_fixture_count: int = Field(
        default=1,
        ge=0,
    )
    min_probability_calibration_profile_overall_bucket_count: int = Field(
        default=1,
        ge=0,
    )
    max_probability_calibration_profile_failed_fold_count: int | None = Field(
        default=0,
        ge=0,
    )
    min_probability_calibration_profile_active_competition_fold_count: int = Field(
        default=1,
        ge=0,
    )
    min_probability_calibration_profile_active_season_cutoff_fold_count: int = Field(
        default=1,
        ge=0,
    )
    min_probability_calibration_profile_active_rolling_fold_count: int = Field(
        default=1,
        ge=0,
    )
    probability_calibration_profile_model_quality_gate_report_path: Path | None = None
    require_probability_calibration_profile_model_quality_gate: bool = False
    require_probability_calibration_profile_model_quality_ready: bool = True
    min_probability_calibration_profile_model_quality_selected_competition_count: int = (
        Field(default=1, ge=0)
    )
    min_probability_calibration_profile_model_quality_adjusted_slice_count: int = Field(
        default=1,
        ge=0,
    )
    min_probability_calibration_profile_model_quality_adjusted_fixture_count: int = (
        Field(default=1, ge=0)
    )
    max_probability_calibration_profile_model_quality_skipped_fixture_count: (
        int | None
    ) = Field(default=0, ge=0)
    max_probability_calibration_profile_model_quality_final_answer_changed_count: (
        int | None
    ) = Field(default=0, ge=0)
    min_probability_calibration_profile_model_quality_final_answer_hit_count_delta: (
        int
    ) = 0
    min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta: (
        float | None
    ) = 0.0
    min_probability_calibration_profile_model_quality_roi_delta: float | None = 0.0
    min_probability_calibration_profile_model_quality_profit_loss_delta: float = 0.0
    max_probability_calibration_profile_model_quality_brier_score_delta: (
        float | None
    ) = 0.0
    max_probability_calibration_profile_model_quality_log_loss_delta: (
        float | None
    ) = 0.0
    max_probability_calibration_profile_model_quality_calibration_error_delta: (
        float | None
    ) = 0.0
    asian_handicap_segmented_model_quality_governance_report_path: Path | None = None
    require_asian_handicap_segmented_model_quality_governance: bool = False
    require_asian_handicap_segmented_model_quality_ready: bool = True
    require_asian_handicap_segmented_model_quality_internal_only: bool = True
    require_asian_handicap_segmented_model_quality_default_path_isolated: bool = True
    require_asian_handicap_segmented_model_quality_no_production_change: bool = True
    require_asian_handicap_segmented_model_quality_no_public_response_change: bool = True
    min_asian_handicap_segmented_model_quality_accepted_segment_count: int = Field(
        default=0,
        ge=0,
    )
    max_asian_handicap_segmented_model_quality_shadow_segment_count: int | None = (
        Field(default=None, ge=0)
    )
    max_asian_handicap_segmented_model_quality_fallback_segment_count: int | None = (
        Field(default=None, ge=0)
    )
    max_asian_handicap_segmented_model_quality_rejected_segment_count: int | None = (
        Field(default=0, ge=0)
    )
    min_asian_handicap_segmented_model_quality_accepted_validation_count: int = Field(
        default=0,
        ge=0,
    )
    min_asian_handicap_segmented_model_quality_calibration_applied_count: int = Field(
        default=0,
        ge=0,
    )
    min_asian_handicap_segmented_model_quality_hit_rate_delta: float | None = 0.0
    max_asian_handicap_segmented_model_quality_brier_score_delta: float | None = 0.0
    max_asian_handicap_segmented_model_quality_log_loss_delta: float | None = 0.0
    max_asian_handicap_segmented_model_quality_calibration_error_delta: (
        float | None
    ) = 0.0
    min_asian_handicap_segmented_model_quality_actual_probability_delta: (
        float | None
    ) = 0.0
    prematch_feature_quality_cycle_report_path: Path | None = None
    require_prematch_feature_quality_cycle: bool = False
    require_prematch_feature_quality_cycle_passed: bool = True
    min_prematch_feature_quality_cycle_slice_count: int = Field(default=1, ge=0)
    min_prematch_feature_quality_cycle_fixture_count: int = Field(default=1, ge=0)
    min_prematch_feature_quality_cycle_evaluated_candidate_count: int = Field(
        default=1,
        ge=0,
    )
    min_prematch_feature_quality_cycle_passing_candidate_count: int = Field(
        default=1,
        ge=0,
    )
    max_prematch_feature_quality_cycle_warning_count: int | None = Field(
        default=0,
        ge=0,
    )
    require_prematch_feature_quality_cycle_best_gate_passed: bool = True
    max_prematch_feature_quality_cycle_best_brier_score_delta: float | None = 0.0
    max_prematch_feature_quality_cycle_best_log_loss_delta: float | None = 0.0
    max_prematch_feature_quality_cycle_best_calibration_error_delta: (
        float | None
    ) = 0.0
    prematch_feature_rolling_admission_report_path: Path | None = None
    require_prematch_feature_rolling_admission: bool = False
    require_prematch_feature_rolling_admission_candidate_allowed: bool = True
    min_prematch_feature_rolling_admission_overall_evaluated_candidate_count: (
        int
    ) = Field(default=1, ge=0)
    min_prematch_feature_rolling_admission_overall_passing_candidate_count: int = Field(
        default=1,
        ge=0,
    )
    max_prematch_feature_rolling_admission_failed_fold_count: int | None = Field(
        default=0,
        ge=0,
    )
    min_prematch_feature_rolling_admission_active_competition_fold_count: int = Field(
        default=1,
        ge=0,
    )
    min_prematch_feature_rolling_admission_active_season_cutoff_fold_count: int = Field(
        default=1,
        ge=0,
    )
    min_prematch_feature_rolling_admission_active_rolling_fold_count: int = Field(
        default=1,
        ge=0,
    )
    max_prematch_feature_rolling_admission_overall_brier_score_delta: (
        float | None
    ) = 0.0
    max_prematch_feature_rolling_admission_overall_log_loss_delta: (
        float | None
    ) = 0.0
    max_prematch_feature_rolling_admission_overall_calibration_error_delta: (
        float | None
    ) = 0.0
    prematch_feature_sample_readiness_report_path: Path | None = None
    require_prematch_feature_sample_readiness: bool = False
    require_prematch_feature_sample_ready_allowed: bool = True
    min_prematch_feature_sample_ready_source_count: int = Field(default=1, ge=0)
    min_prematch_feature_sample_ready_fixture_count: int = Field(default=100, ge=0)
    min_prematch_feature_sample_ready_competition_count: int = Field(
        default=1,
        ge=0,
    )
    min_prematch_feature_sample_ready_season_count: int = Field(default=1, ge=0)
    min_prematch_feature_sample_ready_competition_season_count: int = Field(
        default=1,
        ge=0,
    )
    max_prematch_feature_sample_readiness_warning_count: int | None = Field(
        default=0,
        ge=0,
    )
    fail_on_history_statuses: tuple[str, ...] = ("regressed",)


def apply_runtime_profile_switch_preset(
    options: RecommendationBenchmarkQualityGateOptions,
    preset: str | None,
) -> RecommendationBenchmarkQualityGateOptions:
    if preset is None:
        return options
    if preset != RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1:
        raise ValueError(f"unknown runtime profile switch preset: {preset}")
    return options.model_copy(
        update={
            "runtime_profile_switch_preset": preset,
            "runtime_profile_switch_report_path": (
                options.runtime_profile_switch_report_path
                or SHORT_ODDS_RUNTIME_PROFILE_SWITCH_REPORT_PATH
            ),
            "runtime_profile_switch_replay_report_path": (
                options.runtime_profile_switch_replay_report_path
                or SHORT_ODDS_RUNTIME_PROFILE_SWITCH_REPLAY_REPORT_PATH
            ),
            "require_runtime_profile_switch_gate": True,
            "require_runtime_profile_switch_replay": True,
            "require_runtime_profile_switch_staged_only": True,
            "min_runtime_profile_switch_rule_count": 1,
            "min_runtime_profile_switch_allowed_competition_count": 4,
            "min_runtime_profile_switch_final_answer_count": 30,
            "min_runtime_profile_switch_changed_final_answer_count": 5,
            "min_runtime_profile_switch_final_answer_hit_rate_delta": 0.0,
            "min_runtime_profile_switch_roi_delta": 0.0,
            "min_runtime_profile_switch_profit_loss_delta": 0.0,
            "max_runtime_profile_switch_harm_count_vs_original": 0,
            "max_runtime_profile_switch_final_hit_harm_count_vs_original": 0,
            "max_runtime_profile_switch_profit_loss_harm_count_vs_original": 0,
            "min_runtime_profile_switch_average_hit_probability_delta": -0.02,
        }
    )


def apply_final_answer_segment_penalty_runtime_replay_preset(
    options: RecommendationBenchmarkQualityGateOptions,
    preset: str | None,
) -> RecommendationBenchmarkQualityGateOptions:
    if preset is None:
        return options
    if (
        preset
        != FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
    ):
        raise ValueError(
            f"unknown final-answer segment penalty runtime replay preset: {preset}"
        )
    return options.model_copy(
        update={
            "final_answer_segment_penalty_runtime_replay_preset": preset,
            "final_answer_segment_penalty_runtime_replay_report_path": (
                options.final_answer_segment_penalty_runtime_replay_report_path
                or FINAL_ANSWER_SEGMENT_PENALTY_GER_REGIME_RUNTIME_REPLAY_REPORT_PATH
            ),
            "require_final_answer_segment_penalty_runtime_replay": True,
            "require_final_answer_segment_penalty_runtime_replay_holdout_allowed": True,
            "require_final_answer_segment_penalty_runtime_replay_runtime_allowed": False,
            "min_final_answer_segment_penalty_runtime_replay_rule_count": 1,
            "min_final_answer_segment_penalty_runtime_replay_selected_rule_count": 1,
            "max_final_answer_segment_penalty_runtime_replay_selected_rule_count": 1,
            "min_final_answer_segment_penalty_runtime_replay_final_answer_count": 30,
            "min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count": 2,
            "min_final_answer_segment_penalty_runtime_replay_penalty_option_count": 2,
            "min_final_answer_segment_penalty_runtime_replay_hit_count_delta": 0,
            "min_final_answer_segment_penalty_runtime_replay_hit_rate_delta": 0.0,
            "min_final_answer_segment_penalty_runtime_replay_roi_delta": 0.0,
            "min_final_answer_segment_penalty_runtime_replay_profit_loss_delta": 0.0,
            "min_final_answer_segment_penalty_runtime_replay_candidate_roi": None,
            "max_final_answer_segment_penalty_runtime_replay_brier_score_delta": 0.0,
            "max_final_answer_segment_penalty_runtime_replay_log_loss_delta": 0.0,
            "max_final_answer_segment_penalty_runtime_replay_calibration_error_delta": 0.0,
            "max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline": 0,
            "max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline": 0,
            "max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline": 0,
            "require_final_answer_segment_penalty_runtime_replay_no_production_change": True,
            "require_final_answer_segment_penalty_runtime_replay_no_public_response_change": True,
        }
    )


def apply_recommendation_strategy_governance_preset(
    options: RecommendationBenchmarkQualityGateOptions,
    preset: str | None,
) -> RecommendationBenchmarkQualityGateOptions:
    if preset is None:
        return options
    if preset == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1:
        return _apply_recommendation_strategy_governance_preset(
            options,
            preset=preset,
            promotion_gate_report_path=(
                PROBABILITY_PRESERVING_13CHANGE_STRATEGY_PROMOTION_GATE_REPORT_PATH
            ),
            staged_activation_smoke_report_path=(
                PROBABILITY_PRESERVING_13CHANGE_STAGED_ACTIVATION_SMOKE_REPORT_PATH
            ),
            default_path_isolation_report_path=(
                PROBABILITY_PRESERVING_13CHANGE_DEFAULT_PATH_ISOLATION_REPORT_PATH
            ),
            min_final_answer_count=90,
            min_changed_final_answer_count=13,
            min_hit_delta_count=4,
            min_profit_loss_delta=15.0,
            min_minimum_roi_delta=0.04,
        )
    if (
        preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1
    ):
        return _apply_recommendation_strategy_governance_preset(
            options,
            preset=preset,
            promotion_gate_report_path=(
                PROBABILITY_PRESERVING_QUALITY_SCORE_STRATEGY_PROMOTION_GATE_REPORT_PATH
            ),
            staged_activation_smoke_report_path=(
                PROBABILITY_PRESERVING_QUALITY_SCORE_STAGED_ACTIVATION_SMOKE_REPORT_PATH
            ),
            default_path_isolation_report_path=(
                PROBABILITY_PRESERVING_QUALITY_SCORE_DEFAULT_PATH_ISOLATION_REPORT_PATH
            ),
            min_final_answer_count=99,
            min_changed_final_answer_count=14,
            min_hit_delta_count=4,
            min_profit_loss_delta=15.0,
            min_minimum_roi_delta=0.04,
        )
    raise ValueError(f"unknown recommendation strategy governance preset: {preset}")


def _apply_recommendation_strategy_governance_preset(
    options: RecommendationBenchmarkQualityGateOptions,
    *,
    preset: str,
    promotion_gate_report_path: Path,
    staged_activation_smoke_report_path: Path,
    default_path_isolation_report_path: Path,
    min_final_answer_count: int,
    min_changed_final_answer_count: int,
    min_hit_delta_count: int,
    min_profit_loss_delta: float,
    min_minimum_roi_delta: float,
) -> RecommendationBenchmarkQualityGateOptions:
    if preset not in RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS:
        raise ValueError(f"unknown recommendation strategy governance preset: {preset}")
    return options.model_copy(
        update={
            "recommendation_strategy_governance_preset": preset,
            "recommendation_strategy_promotion_gate_report_path": (
                options.recommendation_strategy_promotion_gate_report_path
                or promotion_gate_report_path
            ),
            "recommendation_strategy_staged_activation_smoke_report_path": (
                options.recommendation_strategy_staged_activation_smoke_report_path
                or staged_activation_smoke_report_path
            ),
            "recommendation_strategy_default_path_isolation_report_path": (
                options.recommendation_strategy_default_path_isolation_report_path
                or default_path_isolation_report_path
            ),
            "require_recommendation_strategy_promotion_gate": True,
            "require_recommendation_strategy_gate_ready": True,
            "min_recommendation_strategy_gate_final_answer_count": min_final_answer_count,
            "min_recommendation_strategy_gate_changed_final_answer_count": (
                min_changed_final_answer_count
            ),
            "min_recommendation_strategy_gate_hit_delta_count": min_hit_delta_count,
            "min_recommendation_strategy_gate_profit_loss_delta": min_profit_loss_delta,
            "min_recommendation_strategy_gate_minimum_roi_delta": min_minimum_roi_delta,
            "max_recommendation_strategy_gate_harm_count": 0,
            "max_recommendation_strategy_gate_final_hit_harm_count": 0,
            "max_recommendation_strategy_gate_profit_loss_harm_count": 0,
            "require_recommendation_strategy_gate_no_production_change": True,
            "require_recommendation_strategy_gate_no_public_response_change": True,
            "require_recommendation_strategy_staged_activation_smoke": True,
            "require_recommendation_strategy_staged_activation_ready": True,
            "require_recommendation_strategy_staged_no_default_write": True,
            "require_recommendation_strategy_staged_no_production_change": True,
            "require_recommendation_strategy_staged_no_public_response_change": True,
            "min_recommendation_strategy_staged_rule_count": 1,
            "min_recommendation_strategy_staged_allowed_competition_count": 5,
            "require_recommendation_strategy_default_path_isolation": True,
            "require_recommendation_strategy_default_path_isolated": True,
            "require_recommendation_strategy_default_adapter_disabled": True,
            "require_recommendation_strategy_default_adapter_unchanged": True,
            "require_recommendation_strategy_explicit_opt_in_applied": True,
            "require_recommendation_strategy_isolation_no_default_write": True,
            "require_recommendation_strategy_isolation_no_production_change": True,
            "require_recommendation_strategy_isolation_no_public_response_change": True,
        }
    )


def apply_unified_candidate_pool_guard_preset(
    options: RecommendationBenchmarkQualityGateOptions,
    preset: str | None,
) -> RecommendationBenchmarkQualityGateOptions:
    if preset is None:
        return options
    if preset != UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1:
        raise ValueError(f"unknown unified candidate pool guard preset: {preset}")
    return options.model_copy(
        update={
            "unified_candidate_pool_guard_preset": preset,
            "require_unified_candidate_pool": True,
            "min_unified_candidate_pool_present_count": max(
                options.min_unified_candidate_pool_present_count,
                1,
            ),
            "min_unified_candidate_pool_valid_candidate_count": max(
                options.min_unified_candidate_pool_valid_candidate_count,
                1,
            ),
            "min_unified_candidate_pool_unique_family_count": max(
                options.min_unified_candidate_pool_unique_family_count,
                2,
            ),
            "max_unified_candidate_pool_selection_mismatch_count": min(
                options.max_unified_candidate_pool_selection_mismatch_count
                if options.max_unified_candidate_pool_selection_mismatch_count
                is not None
                else 0,
                0,
            ),
            "max_unified_candidate_pool_selected_2x1_rate": min(
                options.max_unified_candidate_pool_selected_2x1_rate
                if options.max_unified_candidate_pool_selected_2x1_rate is not None
                else 0.80,
                0.80,
            ),
            "max_unified_candidate_pool_selected_multiple_value_rejected_count": min(
                (
                    options.max_unified_candidate_pool_selected_multiple_value_rejected_count
                    if (
                        options.max_unified_candidate_pool_selected_multiple_value_rejected_count
                        is not None
                    )
                    else 0
                ),
                0,
            ),
        }
    )


class RecommendationBenchmarkQualityGateCheck(BaseModel):
    name: str
    status: RecommendationBenchmarkQualityGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class RecommendationHistoricalSuiteQualityGateEvidence(BaseModel):
    gate_key: str
    passed: bool
    status: str | None = None
    suite_key: str | None = None
    suite_status: str | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class RecommendationBenchmarkQualityGateResult(BaseModel):
    gate_key: str
    status: RecommendationBenchmarkQualityGateStatus
    passed: bool
    latest_run: StoredRecommendationBenchmarkRun | None = None
    previous_run: StoredRecommendationBenchmarkRun | None = None
    checks: list[RecommendationBenchmarkQualityGateCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    historical_suite_quality_gate_report_path: Path | None = None
    historical_suite_quality_gate_present: bool = False
    historical_suite_quality_gate_passed: bool | None = None
    historical_suite_quality_gate_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    budget_stability_audit_report_path: Path | None = None
    budget_stability_audit_present: bool = False
    budget_stability_audit_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    final_answer_market_concentration_audit_report_path: Path | None = None
    final_answer_market_concentration_audit_present: bool = False
    final_answer_market_concentration_audit_passed: bool | None = None
    final_answer_market_concentration_audit_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    correct_score_admission_report_path: Path | None = None
    correct_score_admission_present: bool = False
    correct_score_admission_status: str | None = None
    correct_score_admission_holdout_allowed: bool | None = None
    correct_score_admission_production_allowed: bool | None = None
    correct_score_admission_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    runtime_profile_switch_report_path: Path | None = None
    runtime_profile_switch_gate_present: bool = False
    runtime_profile_switch_gate_switch_ready: bool | None = None
    runtime_profile_switch_summary_json: dict[str, object] = Field(default_factory=dict)
    runtime_profile_switch_replay_report_path: Path | None = None
    runtime_profile_switch_replay_present: bool = False
    runtime_profile_switch_replay_passed: bool | None = None
    runtime_profile_switch_replay_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    final_answer_segment_penalty_runtime_replay_report_path: Path | None = None
    final_answer_segment_penalty_runtime_replay_present: bool = False
    final_answer_segment_penalty_runtime_replay_holdout_allowed: bool | None = None
    final_answer_segment_penalty_runtime_replay_runtime_allowed: bool | None = None
    final_answer_segment_penalty_runtime_replay_summary_json: dict[str, object] = (
        Field(default_factory=dict)
    )
    market_movement_runtime_activation_report_path: Path | None = None
    market_movement_runtime_activation_present: bool = False
    market_movement_runtime_activation_ready: bool | None = None
    market_movement_runtime_activation_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    market_movement_runtime_activation_sample_expansion_report_path: Path | None = None
    market_movement_runtime_activation_sample_expansion_present: bool = False
    market_movement_runtime_activation_sample_expansion_passed: bool | None = None
    market_movement_runtime_activation_sample_expansion_promotion_ready: (
        bool | None
    ) = None
    market_movement_runtime_activation_sample_expansion_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    market_movement_runtime_activation_segment_replay_batch_gate_report_path: (
        Path | None
    ) = None
    market_movement_runtime_activation_segment_replay_batch_gate_present: bool = False
    market_movement_runtime_activation_segment_replay_batch_ready: bool | None = None
    market_movement_runtime_activation_segment_replay_batch_promotion_ready: (
        bool | None
    ) = None
    market_movement_runtime_activation_segment_replay_batch_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    replacement_reranker_shadow_admission_report_path: Path | None = None
    replacement_reranker_shadow_admission_present: bool = False
    replacement_reranker_shadow_admission_runtime_candidate_allowed: bool | None = None
    replacement_reranker_shadow_admission_shadow_allowed: bool | None = None
    replacement_reranker_shadow_admission_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    global_planner_short_odds_adapter_gate_report_path: Path | None = None
    global_planner_short_odds_adapter_gate_present: bool = False
    global_planner_short_odds_adapter_gate_passed: bool | None = None
    global_planner_short_odds_adapter_gate_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    global_planner_short_odds_adapter_sample_expansion_report_path: Path | None = None
    global_planner_short_odds_adapter_sample_expansion_present: bool = False
    global_planner_short_odds_adapter_sample_expansion_passed: bool | None = None
    global_planner_short_odds_adapter_sample_expansion_promotion_ready: bool | None = (
        None
    )
    global_planner_short_odds_adapter_sample_expansion_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    recommendation_strategy_promotion_gate_report_path: Path | None = None
    recommendation_strategy_promotion_gate_present: bool = False
    recommendation_strategy_promotion_gate_ready: bool | None = None
    recommendation_strategy_promotion_gate_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    recommendation_strategy_staged_activation_smoke_report_path: Path | None = None
    recommendation_strategy_staged_activation_smoke_present: bool = False
    recommendation_strategy_staged_activation_ready: bool | None = None
    recommendation_strategy_staged_activation_smoke_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    recommendation_strategy_default_path_isolation_report_path: Path | None = None
    recommendation_strategy_default_path_isolation_present: bool = False
    recommendation_strategy_default_path_isolated: bool | None = None
    recommendation_strategy_default_path_isolation_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    probability_calibration_profile_rolling_admission_report_path: Path | None = None
    probability_calibration_profile_rolling_admission_present: bool = False
    probability_calibration_profile_rolling_admission_candidate_allowed: (
        bool | None
    ) = None
    probability_calibration_profile_rolling_admission_shadow_allowed: bool | None = None
    probability_calibration_profile_rolling_admission_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    probability_calibration_profile_model_quality_gate_report_path: Path | None = None
    probability_calibration_profile_model_quality_gate_present: bool = False
    probability_calibration_profile_model_quality_gate_ready: bool | None = None
    probability_calibration_profile_model_quality_gate_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    asian_handicap_segmented_model_quality_governance_report_path: Path | None = None
    asian_handicap_segmented_model_quality_governance_present: bool = False
    asian_handicap_segmented_model_quality_governance_ready: bool | None = None
    asian_handicap_segmented_model_quality_governance_summary_json: dict[
        str, object
    ] = Field(default_factory=dict)
    prematch_feature_quality_cycle_report_path: Path | None = None
    prematch_feature_quality_cycle_present: bool = False
    prematch_feature_quality_cycle_passed: bool | None = None
    prematch_feature_quality_cycle_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    prematch_feature_rolling_admission_report_path: Path | None = None
    prematch_feature_rolling_admission_present: bool = False
    prematch_feature_rolling_admission_candidate_allowed: bool | None = None
    prematch_feature_rolling_admission_shadow_allowed: bool | None = None
    prematch_feature_rolling_admission_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    prematch_feature_sample_readiness_report_path: Path | None = None
    prematch_feature_sample_readiness_present: bool = False
    prematch_feature_sample_readiness_sample_ready_allowed: bool | None = None
    prematch_feature_sample_readiness_shadow_allowed: bool | None = None
    prematch_feature_sample_readiness_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_benchmark_quality_gate(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
    repository: RecommendationBenchmarkQualityGateRepository | None = None,
    historical_suite_quality_gate: (
        RecommendationHistoricalSuiteQualityGateEvidence | None
    ) = None,
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None = None,
    final_answer_market_concentration_audit: (
        HistoricalFinalAnswerMarketConcentrationAuditReport | None
    ) = None,
    correct_score_admission: HistoricalCorrectScoreAdmissionReport | None = None,
    runtime_profile_switch_gate: (
        HistoricalShortOddsRuntimeProfileSwitchReport | None
    ) = None,
    runtime_profile_switch_replay: (
        HistoricalShortOddsRuntimeShadowReplayReport | None
    ) = None,
    final_answer_segment_penalty_runtime_replay: (
        HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None
    ) = None,
    market_movement_runtime_activation: (
        HistoricalMarketMovementRiskFilterRuntimeActivationReport | None
    ) = None,
    market_movement_runtime_activation_sample_expansion: (
        HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None
    ) = None,
    market_movement_runtime_activation_segment_replay_batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ) = None,
    replacement_reranker_shadow_admission: (
        HistoricalReplacementRerankerShadowAdmissionReport | None
    ) = None,
    global_planner_short_odds_adapter_gate: (
        HistoricalGlobalPlannerShortOddsAdapterGateReport | None
    ) = None,
    global_planner_short_odds_adapter_sample_expansion: (
        HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None
    ) = None,
    recommendation_strategy_promotion_gate: (
        RecommendationStrategyPromotionGateReport | None
    ) = None,
    recommendation_strategy_staged_activation_smoke: (
        RecommendationStrategyStagedActivationSmokeReport | None
    ) = None,
    recommendation_strategy_default_path_isolation: (
        RecommendationStrategyDefaultPathIsolationReport | None
    ) = None,
    probability_calibration_profile_rolling_admission: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None
    ) = None,
    probability_calibration_profile_model_quality_gate: (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport | None
    ) = None,
    asian_handicap_segmented_model_quality_governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ) = None,
    prematch_feature_quality_cycle: (
        HistoricalPrematchFeatureQualityCycleResult | None
    ) = None,
    prematch_feature_rolling_admission: (
        HistoricalPrematchFeatureRollingAdmissionReport | None
    ) = None,
    prematch_feature_sample_readiness: (
        HistoricalPrematchFeatureSampleReadinessReport | None
    ) = None,
) -> RecommendationBenchmarkQualityGateResult:
    resolved_historical_suite_quality_gate = (
        historical_suite_quality_gate
        or _load_historical_suite_quality_gate(
            options.historical_suite_quality_gate_report_path
        )
    )
    resolved_budget_stability_audit = (
        budget_stability_audit
        or _load_budget_stability_audit(options.budget_stability_audit_report_path)
    )
    resolved_final_answer_market_concentration_audit = (
        final_answer_market_concentration_audit
        or _load_final_answer_market_concentration_audit(
            options.final_answer_market_concentration_audit_report_path
        )
    )
    resolved_correct_score_admission = (
        correct_score_admission
        or _load_correct_score_admission(options.correct_score_admission_report_path)
    )
    resolved_runtime_profile_switch_gate = (
        runtime_profile_switch_gate
        or _load_runtime_profile_switch_gate(options.runtime_profile_switch_report_path)
    )
    resolved_runtime_profile_switch_replay = (
        runtime_profile_switch_replay
        or _load_runtime_profile_switch_replay(
            options.runtime_profile_switch_replay_report_path
        )
    )
    resolved_final_answer_segment_penalty_runtime_replay = (
        final_answer_segment_penalty_runtime_replay
        or _load_final_answer_segment_penalty_runtime_replay(
            options.final_answer_segment_penalty_runtime_replay_report_path
        )
    )
    resolved_market_movement_runtime_activation = (
        market_movement_runtime_activation
        or _load_market_movement_runtime_activation(
            options.market_movement_runtime_activation_report_path
        )
    )
    resolved_market_movement_runtime_activation_sample_expansion = (
        market_movement_runtime_activation_sample_expansion
        or _load_market_movement_runtime_activation_sample_expansion(
            options.market_movement_runtime_activation_sample_expansion_report_path
        )
    )
    resolved_market_movement_runtime_activation_segment_replay_batch_gate = (
        market_movement_runtime_activation_segment_replay_batch_gate
        or _load_market_movement_runtime_activation_segment_replay_batch_gate(
            options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        )
    )
    resolved_replacement_reranker_shadow_admission = (
        replacement_reranker_shadow_admission
        or _load_replacement_reranker_shadow_admission(
            options.replacement_reranker_shadow_admission_report_path
        )
    )
    resolved_global_planner_short_odds_adapter_gate = (
        global_planner_short_odds_adapter_gate
        or _load_global_planner_short_odds_adapter_gate(
            options.global_planner_short_odds_adapter_gate_report_path
        )
    )
    resolved_global_planner_short_odds_adapter_sample_expansion = (
        global_planner_short_odds_adapter_sample_expansion
        or _load_global_planner_short_odds_adapter_sample_expansion(
            options.global_planner_short_odds_adapter_sample_expansion_report_path
        )
    )
    resolved_recommendation_strategy_promotion_gate = (
        recommendation_strategy_promotion_gate
        or _load_recommendation_strategy_promotion_gate(
            options.recommendation_strategy_promotion_gate_report_path
        )
    )
    resolved_recommendation_strategy_staged_activation_smoke = (
        recommendation_strategy_staged_activation_smoke
        or _load_recommendation_strategy_staged_activation_smoke(
            options.recommendation_strategy_staged_activation_smoke_report_path
        )
    )
    resolved_recommendation_strategy_default_path_isolation = (
        recommendation_strategy_default_path_isolation
        or _load_recommendation_strategy_default_path_isolation(
            options.recommendation_strategy_default_path_isolation_report_path
        )
    )
    resolved_probability_calibration_profile_rolling_admission = (
        probability_calibration_profile_rolling_admission
        or _load_probability_calibration_profile_rolling_admission(
            options.probability_calibration_profile_rolling_admission_report_path
        )
    )
    resolved_probability_calibration_profile_model_quality_gate = (
        probability_calibration_profile_model_quality_gate
        or _load_probability_calibration_profile_model_quality_gate(
            options.probability_calibration_profile_model_quality_gate_report_path
        )
    )
    resolved_asian_handicap_segmented_model_quality_governance = (
        asian_handicap_segmented_model_quality_governance
        or _load_asian_handicap_segmented_model_quality_governance(
            options.asian_handicap_segmented_model_quality_governance_report_path
        )
    )
    resolved_prematch_feature_quality_cycle = (
        prematch_feature_quality_cycle
        or _load_prematch_feature_quality_cycle(
            options.prematch_feature_quality_cycle_report_path
        )
    )
    resolved_prematch_feature_rolling_admission = (
        prematch_feature_rolling_admission
        or _load_prematch_feature_rolling_admission(
            options.prematch_feature_rolling_admission_report_path
        )
    )
    resolved_prematch_feature_sample_readiness = (
        prematch_feature_sample_readiness
        or _load_prematch_feature_sample_readiness(
            options.prematch_feature_sample_readiness_report_path
        )
    )
    gate_repository = repository or PostgresRecommendationBenchmarkRunRepository(database)
    history = gate_repository.list_history(
        benchmark_key=options.benchmark_key,
        strategy=options.strategy,
        limit=options.history_limit,
    )
    gate_key = _gate_key(options)
    if not history:
        checks = _historical_suite_quality_gate_checks(
            resolved_historical_suite_quality_gate,
            options=options,
        )
        checks.extend(
            _budget_stability_audit_checks(
                resolved_budget_stability_audit,
                options=options,
            )
        )
        checks.extend(
            _final_answer_market_concentration_audit_checks(
                resolved_final_answer_market_concentration_audit,
                options=options,
            )
        )
        checks.extend(
            _correct_score_admission_checks(
                resolved_correct_score_admission,
                options=options,
            )
        )
        checks.extend(_unified_candidate_pool_checks({}, options=options))
        checks.extend(
            _runtime_profile_switch_gate_checks(
                resolved_runtime_profile_switch_gate,
                resolved_runtime_profile_switch_replay,
                options=options,
            )
        )
        checks.extend(
            _final_answer_segment_penalty_runtime_replay_checks(
                resolved_final_answer_segment_penalty_runtime_replay,
                options=options,
            )
        )
        checks.extend(
            _market_movement_runtime_activation_checks(
                resolved_market_movement_runtime_activation,
                options=options,
            )
        )
        checks.extend(
            _market_movement_runtime_activation_sample_expansion_checks(
                resolved_market_movement_runtime_activation_sample_expansion,
                options=options,
            )
        )
        checks.extend(
            _market_movement_runtime_activation_segment_replay_batch_gate_checks(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate,
                options=options,
            )
        )
        checks.extend(
            _replacement_reranker_shadow_admission_checks(
                resolved_replacement_reranker_shadow_admission,
                options=options,
            )
        )
        checks.extend(
            _global_planner_short_odds_adapter_gate_checks(
                resolved_global_planner_short_odds_adapter_gate,
                options=options,
            )
        )
        checks.extend(
            _global_planner_short_odds_adapter_sample_expansion_checks(
                resolved_global_planner_short_odds_adapter_sample_expansion,
                options=options,
            )
        )
        checks.extend(
            _recommendation_strategy_promotion_gate_checks(
                resolved_recommendation_strategy_promotion_gate,
                options=options,
            )
        )
        checks.extend(
            _recommendation_strategy_staged_activation_smoke_checks(
                resolved_recommendation_strategy_staged_activation_smoke,
                options=options,
            )
        )
        checks.extend(
            _recommendation_strategy_default_path_isolation_checks(
                resolved_recommendation_strategy_default_path_isolation,
                options=options,
            )
        )
        checks.extend(
            _probability_calibration_profile_rolling_admission_checks(
                resolved_probability_calibration_profile_rolling_admission,
                options=options,
            )
        )
        checks.extend(
            _probability_calibration_profile_model_quality_gate_checks(
                resolved_probability_calibration_profile_model_quality_gate,
                options=options,
            )
        )
        checks.extend(
            _asian_handicap_segmented_model_quality_governance_checks(
                resolved_asian_handicap_segmented_model_quality_governance,
                options=options,
            )
        )
        checks.extend(
            _prematch_feature_quality_cycle_checks(
                resolved_prematch_feature_quality_cycle,
                options=options,
            )
        )
        checks.extend(
            _prematch_feature_rolling_admission_checks(
                resolved_prematch_feature_rolling_admission,
                options=options,
            )
        )
        checks.extend(
            _prematch_feature_sample_readiness_checks(
                resolved_prematch_feature_sample_readiness,
                options=options,
            )
        )
        failed_checks = [check for check in checks if check.status == "failed"]
        warnings = [
            "benchmark_quality_gate:no_persisted_benchmark_history",
            *[
                f"benchmark_quality_gate:failed_check:{check.name}"
                for check in failed_checks
            ],
        ]
        passed = options.allow_missing_history and not failed_checks
        missing_history_status: RecommendationBenchmarkQualityGateStatus = (
            "passed"
            if passed
            else "failed"
            if failed_checks
            else "insufficient_history"
        )
        summary: dict[str, object] = {
            "gate_key": gate_key,
            "status": missing_history_status,
            "passed": passed,
            "history_count": 0,
            "allow_missing_history": options.allow_missing_history,
            "failed_checks": [check.name for check in failed_checks],
            "warnings": warnings,
            "calculation_basis": "recommendation_benchmark_quality_gate_v3_1",
            "runtime_profile_switch_preset": options.runtime_profile_switch_preset,
            "final_answer_segment_penalty_runtime_replay_preset": (
                options.final_answer_segment_penalty_runtime_replay_preset
            ),
            "recommendation_strategy_governance_preset": (
                options.recommendation_strategy_governance_preset
            ),
            "unified_candidate_pool_guard_preset": (
                options.unified_candidate_pool_guard_preset
            ),
        }
        summary.update(
            _historical_suite_quality_gate_summary_fields(
                resolved_historical_suite_quality_gate,
                report_path=options.historical_suite_quality_gate_report_path,
            )
        )
        summary.update(
            _budget_stability_audit_summary_fields(
                resolved_budget_stability_audit,
                report_path=options.budget_stability_audit_report_path,
            )
        )
        summary.update(
            _final_answer_market_concentration_audit_summary_fields(
                resolved_final_answer_market_concentration_audit,
                report_path=(
                    options.final_answer_market_concentration_audit_report_path
                ),
            )
        )
        summary.update(
            _correct_score_admission_summary_fields(
                resolved_correct_score_admission,
                report_path=options.correct_score_admission_report_path,
            )
        )
        summary.update(
            _runtime_profile_switch_summary_fields(
                resolved_runtime_profile_switch_gate,
                resolved_runtime_profile_switch_replay,
                switch_report_path=options.runtime_profile_switch_report_path,
                replay_report_path=options.runtime_profile_switch_replay_report_path,
            )
        )
        summary.update(
            _final_answer_segment_penalty_runtime_replay_summary_fields(
                resolved_final_answer_segment_penalty_runtime_replay,
                report_path=(
                    options.final_answer_segment_penalty_runtime_replay_report_path
                ),
            )
        )
        summary.update(
            _market_movement_runtime_activation_summary_fields(
                resolved_market_movement_runtime_activation,
                report_path=options.market_movement_runtime_activation_report_path,
            )
        )
        summary.update(
            _market_movement_runtime_activation_sample_expansion_summary_fields(
                resolved_market_movement_runtime_activation_sample_expansion,
                report_path=(
                    options.market_movement_runtime_activation_sample_expansion_report_path
                ),
            )
        )
        summary.update(
            _market_movement_runtime_activation_segment_replay_batch_gate_summary_fields(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate,
                report_path=(
                    options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
                ),
            )
        )
        summary.update(
            _replacement_reranker_shadow_admission_summary_fields(
                resolved_replacement_reranker_shadow_admission,
                report_path=options.replacement_reranker_shadow_admission_report_path,
            )
        )
        summary.update(
            _global_planner_short_odds_adapter_gate_summary_fields(
                resolved_global_planner_short_odds_adapter_gate,
                report_path=(
                    options.global_planner_short_odds_adapter_gate_report_path
                ),
            )
        )
        summary.update(
            _global_planner_short_odds_adapter_sample_expansion_summary_fields(
                resolved_global_planner_short_odds_adapter_sample_expansion,
                report_path=(
                    options.global_planner_short_odds_adapter_sample_expansion_report_path
                ),
            )
        )
        summary.update(
            _recommendation_strategy_promotion_gate_summary_fields(
                resolved_recommendation_strategy_promotion_gate,
                report_path=options.recommendation_strategy_promotion_gate_report_path,
            )
        )
        summary.update(
            _recommendation_strategy_staged_activation_smoke_summary_fields(
                resolved_recommendation_strategy_staged_activation_smoke,
                report_path=(
                    options.recommendation_strategy_staged_activation_smoke_report_path
                ),
            )
        )
        summary.update(
            _recommendation_strategy_default_path_isolation_summary_fields(
                resolved_recommendation_strategy_default_path_isolation,
                report_path=(
                    options.recommendation_strategy_default_path_isolation_report_path
                ),
            )
        )
        summary.update(
            _probability_calibration_profile_rolling_admission_summary_fields(
                resolved_probability_calibration_profile_rolling_admission,
                report_path=(
                    options.probability_calibration_profile_rolling_admission_report_path
                ),
            )
        )
        summary.update(
            _probability_calibration_profile_model_quality_gate_summary_fields(
                resolved_probability_calibration_profile_model_quality_gate,
                report_path=(
                    options.probability_calibration_profile_model_quality_gate_report_path
                ),
            )
        )
        summary.update(
            _asian_handicap_segmented_model_quality_governance_summary_fields(
                resolved_asian_handicap_segmented_model_quality_governance,
                report_path=(
                    options.asian_handicap_segmented_model_quality_governance_report_path
                ),
            )
        )
        summary.update(
            _prematch_feature_quality_cycle_summary_fields(
                resolved_prematch_feature_quality_cycle,
                report_path=options.prematch_feature_quality_cycle_report_path,
            )
        )
        summary.update(
            _prematch_feature_rolling_admission_summary_fields(
                resolved_prematch_feature_rolling_admission,
                report_path=options.prematch_feature_rolling_admission_report_path,
            )
        )
        summary.update(
            _prematch_feature_sample_readiness_summary_fields(
                resolved_prematch_feature_sample_readiness,
                report_path=options.prematch_feature_sample_readiness_report_path,
            )
        )
        return RecommendationBenchmarkQualityGateResult(
            gate_key=gate_key,
            status=missing_history_status,
            passed=passed,
            checks=checks,
            warnings=warnings,
            historical_suite_quality_gate_report_path=(
                options.historical_suite_quality_gate_report_path
            ),
            historical_suite_quality_gate_present=(
                resolved_historical_suite_quality_gate is not None
            ),
            historical_suite_quality_gate_passed=(
                resolved_historical_suite_quality_gate.passed
                if resolved_historical_suite_quality_gate is not None
                else None
            ),
            historical_suite_quality_gate_summary_json=(
                resolved_historical_suite_quality_gate.summary_json
                if resolved_historical_suite_quality_gate is not None
                else {}
            ),
            budget_stability_audit_report_path=(
                options.budget_stability_audit_report_path
            ),
            budget_stability_audit_present=(
                resolved_budget_stability_audit is not None
            ),
            budget_stability_audit_summary_json=(
                resolved_budget_stability_audit.summary_json
                if resolved_budget_stability_audit is not None
                else {}
            ),
            final_answer_market_concentration_audit_report_path=(
                options.final_answer_market_concentration_audit_report_path
            ),
            final_answer_market_concentration_audit_present=(
                resolved_final_answer_market_concentration_audit is not None
            ),
            final_answer_market_concentration_audit_passed=(
                resolved_final_answer_market_concentration_audit.passed
                if resolved_final_answer_market_concentration_audit is not None
                else None
            ),
            final_answer_market_concentration_audit_summary_json=(
                resolved_final_answer_market_concentration_audit.summary_json
                if resolved_final_answer_market_concentration_audit is not None
                else {}
            ),
            correct_score_admission_report_path=(
                options.correct_score_admission_report_path
            ),
            correct_score_admission_present=(
                resolved_correct_score_admission is not None
            ),
            correct_score_admission_status=(
                resolved_correct_score_admission.status
                if resolved_correct_score_admission is not None
                else None
            ),
            correct_score_admission_holdout_allowed=(
                resolved_correct_score_admission.holdout_allowed
                if resolved_correct_score_admission is not None
                else None
            ),
            correct_score_admission_production_allowed=(
                resolved_correct_score_admission.production_recommendation_allowed
                if resolved_correct_score_admission is not None
                else None
            ),
            correct_score_admission_summary_json=(
                resolved_correct_score_admission.summary_json
                if resolved_correct_score_admission is not None
                else {}
            ),
            runtime_profile_switch_report_path=options.runtime_profile_switch_report_path,
            runtime_profile_switch_gate_present=(
                resolved_runtime_profile_switch_gate is not None
            ),
            runtime_profile_switch_gate_switch_ready=(
                resolved_runtime_profile_switch_gate.switch_ready
                if resolved_runtime_profile_switch_gate is not None
                else None
            ),
            runtime_profile_switch_summary_json=(
                resolved_runtime_profile_switch_gate.summary_json
                if resolved_runtime_profile_switch_gate is not None
                else {}
            ),
            runtime_profile_switch_replay_report_path=(
                options.runtime_profile_switch_replay_report_path
            ),
            runtime_profile_switch_replay_present=(
                resolved_runtime_profile_switch_replay is not None
            ),
            runtime_profile_switch_replay_passed=(
                resolved_runtime_profile_switch_replay.passed
                if resolved_runtime_profile_switch_replay is not None
                else None
            ),
            runtime_profile_switch_replay_summary_json=(
                resolved_runtime_profile_switch_replay.summary_json
                if resolved_runtime_profile_switch_replay is not None
                else {}
            ),
            final_answer_segment_penalty_runtime_replay_report_path=(
                options.final_answer_segment_penalty_runtime_replay_report_path
            ),
            final_answer_segment_penalty_runtime_replay_present=(
                resolved_final_answer_segment_penalty_runtime_replay is not None
            ),
            final_answer_segment_penalty_runtime_replay_holdout_allowed=(
                resolved_final_answer_segment_penalty_runtime_replay.holdout_replay_allowed
                if resolved_final_answer_segment_penalty_runtime_replay is not None
                else None
            ),
            final_answer_segment_penalty_runtime_replay_runtime_allowed=(
                resolved_final_answer_segment_penalty_runtime_replay.runtime_replay_allowed
                if resolved_final_answer_segment_penalty_runtime_replay is not None
                else None
            ),
            final_answer_segment_penalty_runtime_replay_summary_json=(
                resolved_final_answer_segment_penalty_runtime_replay.summary_json
                if resolved_final_answer_segment_penalty_runtime_replay is not None
                else {}
            ),
            market_movement_runtime_activation_report_path=(
                options.market_movement_runtime_activation_report_path
            ),
            market_movement_runtime_activation_present=(
                resolved_market_movement_runtime_activation is not None
            ),
            market_movement_runtime_activation_ready=(
                resolved_market_movement_runtime_activation.staged_activation_ready
                if resolved_market_movement_runtime_activation is not None
                else None
            ),
            market_movement_runtime_activation_summary_json=(
                resolved_market_movement_runtime_activation.summary_json
                if resolved_market_movement_runtime_activation is not None
                else {}
            ),
            market_movement_runtime_activation_sample_expansion_report_path=(
                options.market_movement_runtime_activation_sample_expansion_report_path
            ),
            market_movement_runtime_activation_sample_expansion_present=(
                resolved_market_movement_runtime_activation_sample_expansion is not None
            ),
            market_movement_runtime_activation_sample_expansion_passed=(
                resolved_market_movement_runtime_activation_sample_expansion.passed
                if resolved_market_movement_runtime_activation_sample_expansion
                is not None
                else None
            ),
            market_movement_runtime_activation_sample_expansion_promotion_ready=(
                resolved_market_movement_runtime_activation_sample_expansion.promotion_ready
                if resolved_market_movement_runtime_activation_sample_expansion
                is not None
                else None
            ),
            market_movement_runtime_activation_sample_expansion_summary_json=(
                resolved_market_movement_runtime_activation_sample_expansion.summary_json
                if resolved_market_movement_runtime_activation_sample_expansion
                is not None
                else {}
            ),
            market_movement_runtime_activation_segment_replay_batch_gate_report_path=(
                options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
            ),
            market_movement_runtime_activation_segment_replay_batch_gate_present=(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate
                is not None
            ),
            market_movement_runtime_activation_segment_replay_batch_ready=(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate.runtime_replay_batch_ready
                if resolved_market_movement_runtime_activation_segment_replay_batch_gate
                is not None
                else None
            ),
            market_movement_runtime_activation_segment_replay_batch_promotion_ready=(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate.production_promotion_ready
                if resolved_market_movement_runtime_activation_segment_replay_batch_gate
                is not None
                else None
            ),
            market_movement_runtime_activation_segment_replay_batch_summary_json=(
                resolved_market_movement_runtime_activation_segment_replay_batch_gate.summary_json
                if resolved_market_movement_runtime_activation_segment_replay_batch_gate
                is not None
                else {}
            ),
            replacement_reranker_shadow_admission_report_path=(
                options.replacement_reranker_shadow_admission_report_path
            ),
            replacement_reranker_shadow_admission_present=(
                resolved_replacement_reranker_shadow_admission is not None
            ),
            replacement_reranker_shadow_admission_runtime_candidate_allowed=(
                resolved_replacement_reranker_shadow_admission.runtime_profile_candidate_allowed
                if resolved_replacement_reranker_shadow_admission is not None
                else None
            ),
            replacement_reranker_shadow_admission_shadow_allowed=(
                resolved_replacement_reranker_shadow_admission.shadow_allowed
                if resolved_replacement_reranker_shadow_admission is not None
                else None
            ),
            replacement_reranker_shadow_admission_summary_json=(
                resolved_replacement_reranker_shadow_admission.summary_json
                if resolved_replacement_reranker_shadow_admission is not None
                else {}
            ),
            global_planner_short_odds_adapter_gate_report_path=(
                options.global_planner_short_odds_adapter_gate_report_path
            ),
            global_planner_short_odds_adapter_gate_present=(
                resolved_global_planner_short_odds_adapter_gate is not None
            ),
            global_planner_short_odds_adapter_gate_passed=(
                resolved_global_planner_short_odds_adapter_gate.passed
                if resolved_global_planner_short_odds_adapter_gate is not None
                else None
            ),
            global_planner_short_odds_adapter_gate_summary_json=(
                resolved_global_planner_short_odds_adapter_gate.summary_json
                if resolved_global_planner_short_odds_adapter_gate is not None
                else {}
            ),
            global_planner_short_odds_adapter_sample_expansion_report_path=(
                options.global_planner_short_odds_adapter_sample_expansion_report_path
            ),
            global_planner_short_odds_adapter_sample_expansion_present=(
                resolved_global_planner_short_odds_adapter_sample_expansion is not None
            ),
            global_planner_short_odds_adapter_sample_expansion_passed=(
                resolved_global_planner_short_odds_adapter_sample_expansion.passed
                if resolved_global_planner_short_odds_adapter_sample_expansion
                is not None
                else None
            ),
            global_planner_short_odds_adapter_sample_expansion_promotion_ready=(
                resolved_global_planner_short_odds_adapter_sample_expansion.promotion_ready
                if resolved_global_planner_short_odds_adapter_sample_expansion
                is not None
                else None
            ),
            global_planner_short_odds_adapter_sample_expansion_summary_json=(
                resolved_global_planner_short_odds_adapter_sample_expansion.summary_json
                if resolved_global_planner_short_odds_adapter_sample_expansion
                is not None
                else {}
            ),
            recommendation_strategy_promotion_gate_report_path=(
                options.recommendation_strategy_promotion_gate_report_path
            ),
            recommendation_strategy_promotion_gate_present=(
                resolved_recommendation_strategy_promotion_gate is not None
            ),
            recommendation_strategy_promotion_gate_ready=(
                resolved_recommendation_strategy_promotion_gate.strategy_gate_ready
                if resolved_recommendation_strategy_promotion_gate is not None
                else None
            ),
            recommendation_strategy_promotion_gate_summary_json=(
                resolved_recommendation_strategy_promotion_gate.summary_json
                if resolved_recommendation_strategy_promotion_gate is not None
                else {}
            ),
            recommendation_strategy_staged_activation_smoke_report_path=(
                options.recommendation_strategy_staged_activation_smoke_report_path
            ),
            recommendation_strategy_staged_activation_smoke_present=(
                resolved_recommendation_strategy_staged_activation_smoke is not None
            ),
            recommendation_strategy_staged_activation_ready=(
                resolved_recommendation_strategy_staged_activation_smoke.staged_activation_ready
                if resolved_recommendation_strategy_staged_activation_smoke
                is not None
                else None
            ),
            recommendation_strategy_staged_activation_smoke_summary_json=(
                resolved_recommendation_strategy_staged_activation_smoke.summary_json
                if resolved_recommendation_strategy_staged_activation_smoke
                is not None
                else {}
            ),
            recommendation_strategy_default_path_isolation_report_path=(
                options.recommendation_strategy_default_path_isolation_report_path
            ),
            recommendation_strategy_default_path_isolation_present=(
                resolved_recommendation_strategy_default_path_isolation is not None
            ),
            recommendation_strategy_default_path_isolated=(
                resolved_recommendation_strategy_default_path_isolation.default_path_isolated
                if resolved_recommendation_strategy_default_path_isolation
                is not None
                else None
            ),
            recommendation_strategy_default_path_isolation_summary_json=(
                resolved_recommendation_strategy_default_path_isolation.summary_json
                if resolved_recommendation_strategy_default_path_isolation
                is not None
                else {}
            ),
            probability_calibration_profile_rolling_admission_report_path=(
                options.probability_calibration_profile_rolling_admission_report_path
            ),
            probability_calibration_profile_rolling_admission_present=(
                resolved_probability_calibration_profile_rolling_admission is not None
            ),
            probability_calibration_profile_rolling_admission_candidate_allowed=(
                resolved_probability_calibration_profile_rolling_admission.candidate_profile_allowed
                if resolved_probability_calibration_profile_rolling_admission
                is not None
                else None
            ),
            probability_calibration_profile_rolling_admission_shadow_allowed=(
                resolved_probability_calibration_profile_rolling_admission.shadow_allowed
                if resolved_probability_calibration_profile_rolling_admission
                is not None
                else None
            ),
            probability_calibration_profile_rolling_admission_summary_json=(
                resolved_probability_calibration_profile_rolling_admission.summary_json
                if resolved_probability_calibration_profile_rolling_admission
                is not None
                else {}
            ),
            probability_calibration_profile_model_quality_gate_report_path=(
                options.probability_calibration_profile_model_quality_gate_report_path
            ),
            probability_calibration_profile_model_quality_gate_present=(
                resolved_probability_calibration_profile_model_quality_gate is not None
            ),
            probability_calibration_profile_model_quality_gate_ready=(
                resolved_probability_calibration_profile_model_quality_gate.model_quality_gate_passed
                if resolved_probability_calibration_profile_model_quality_gate
                is not None
                else None
            ),
            probability_calibration_profile_model_quality_gate_summary_json=(
                resolved_probability_calibration_profile_model_quality_gate.summary_json
                if resolved_probability_calibration_profile_model_quality_gate
                is not None
                else {}
            ),
            asian_handicap_segmented_model_quality_governance_report_path=(
                options.asian_handicap_segmented_model_quality_governance_report_path
            ),
            asian_handicap_segmented_model_quality_governance_present=(
                resolved_asian_handicap_segmented_model_quality_governance is not None
            ),
            asian_handicap_segmented_model_quality_governance_ready=(
                resolved_asian_handicap_segmented_model_quality_governance.governance_review_ready
                if resolved_asian_handicap_segmented_model_quality_governance
                is not None
                else None
            ),
            asian_handicap_segmented_model_quality_governance_summary_json=(
                resolved_asian_handicap_segmented_model_quality_governance.summary_json
                if resolved_asian_handicap_segmented_model_quality_governance
                is not None
                else {}
            ),
            prematch_feature_quality_cycle_report_path=(
                options.prematch_feature_quality_cycle_report_path
            ),
            prematch_feature_quality_cycle_present=(
                resolved_prematch_feature_quality_cycle is not None
            ),
            prematch_feature_quality_cycle_passed=(
                resolved_prematch_feature_quality_cycle.passed
                if resolved_prematch_feature_quality_cycle is not None
                else None
            ),
            prematch_feature_quality_cycle_summary_json=(
                resolved_prematch_feature_quality_cycle.summary_json
                if resolved_prematch_feature_quality_cycle is not None
                else {}
            ),
            prematch_feature_rolling_admission_report_path=(
                options.prematch_feature_rolling_admission_report_path
            ),
            prematch_feature_rolling_admission_present=(
                resolved_prematch_feature_rolling_admission is not None
            ),
            prematch_feature_rolling_admission_candidate_allowed=(
                resolved_prematch_feature_rolling_admission.candidate_feature_allowed
                if resolved_prematch_feature_rolling_admission is not None
                else None
            ),
            prematch_feature_rolling_admission_shadow_allowed=(
                resolved_prematch_feature_rolling_admission.shadow_allowed
                if resolved_prematch_feature_rolling_admission is not None
                else None
            ),
            prematch_feature_rolling_admission_summary_json=(
                resolved_prematch_feature_rolling_admission.summary_json
                if resolved_prematch_feature_rolling_admission is not None
                else {}
            ),
            prematch_feature_sample_readiness_report_path=(
                options.prematch_feature_sample_readiness_report_path
            ),
            prematch_feature_sample_readiness_present=(
                resolved_prematch_feature_sample_readiness is not None
            ),
            prematch_feature_sample_readiness_sample_ready_allowed=(
                resolved_prematch_feature_sample_readiness.sample_ready_allowed
                if resolved_prematch_feature_sample_readiness is not None
                else None
            ),
            prematch_feature_sample_readiness_shadow_allowed=(
                resolved_prematch_feature_sample_readiness.shadow_allowed
                if resolved_prematch_feature_sample_readiness is not None
                else None
            ),
            prematch_feature_sample_readiness_summary_json=(
                resolved_prematch_feature_sample_readiness.summary_json
                if resolved_prematch_feature_sample_readiness is not None
                else {}
            ),
            summary_json=summary,
        )

    latest = history[0]
    previous = history[1] if len(history) > 1 else None
    checks = _quality_gate_checks(
        latest,
        options=options,
        historical_suite_quality_gate=resolved_historical_suite_quality_gate,
        budget_stability_audit=resolved_budget_stability_audit,
        final_answer_market_concentration_audit=(
            resolved_final_answer_market_concentration_audit
        ),
        correct_score_admission=resolved_correct_score_admission,
        runtime_profile_switch_gate=resolved_runtime_profile_switch_gate,
        runtime_profile_switch_replay=resolved_runtime_profile_switch_replay,
        final_answer_segment_penalty_runtime_replay=(
            resolved_final_answer_segment_penalty_runtime_replay
        ),
        market_movement_runtime_activation=(
            resolved_market_movement_runtime_activation
        ),
        market_movement_runtime_activation_sample_expansion=(
            resolved_market_movement_runtime_activation_sample_expansion
        ),
        market_movement_runtime_activation_segment_replay_batch_gate=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate
        ),
        replacement_reranker_shadow_admission=(
            resolved_replacement_reranker_shadow_admission
        ),
        global_planner_short_odds_adapter_gate=(
            resolved_global_planner_short_odds_adapter_gate
        ),
        global_planner_short_odds_adapter_sample_expansion=(
            resolved_global_planner_short_odds_adapter_sample_expansion
        ),
        recommendation_strategy_promotion_gate=(
            resolved_recommendation_strategy_promotion_gate
        ),
        recommendation_strategy_staged_activation_smoke=(
            resolved_recommendation_strategy_staged_activation_smoke
        ),
        recommendation_strategy_default_path_isolation=(
            resolved_recommendation_strategy_default_path_isolation
        ),
        probability_calibration_profile_rolling_admission=(
            resolved_probability_calibration_profile_rolling_admission
        ),
        probability_calibration_profile_model_quality_gate=(
            resolved_probability_calibration_profile_model_quality_gate
        ),
        asian_handicap_segmented_model_quality_governance=(
            resolved_asian_handicap_segmented_model_quality_governance
        ),
        prematch_feature_quality_cycle=resolved_prematch_feature_quality_cycle,
        prematch_feature_rolling_admission=(
            resolved_prematch_feature_rolling_admission
        ),
        prematch_feature_sample_readiness=(
            resolved_prematch_feature_sample_readiness
        ),
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: RecommendationBenchmarkQualityGateStatus = "passed" if passed else "failed"
    warnings = [
        f"benchmark_quality_gate:failed_check:{check.name}" for check in failed_checks
    ]
    summary = _quality_gate_summary(
        gate_key=gate_key,
        latest=latest,
        previous=previous,
        checks=checks,
        passed=passed,
        warnings=warnings,
        historical_suite_quality_gate=resolved_historical_suite_quality_gate,
        historical_suite_quality_gate_report_path=(
            options.historical_suite_quality_gate_report_path
        ),
        budget_stability_audit=resolved_budget_stability_audit,
        budget_stability_audit_report_path=options.budget_stability_audit_report_path,
        final_answer_market_concentration_audit=(
            resolved_final_answer_market_concentration_audit
        ),
        final_answer_market_concentration_audit_report_path=(
            options.final_answer_market_concentration_audit_report_path
        ),
        correct_score_admission=resolved_correct_score_admission,
        correct_score_admission_report_path=(
            options.correct_score_admission_report_path
        ),
        runtime_profile_switch_gate=resolved_runtime_profile_switch_gate,
        runtime_profile_switch_replay=resolved_runtime_profile_switch_replay,
        runtime_profile_switch_report_path=options.runtime_profile_switch_report_path,
        runtime_profile_switch_replay_report_path=(
            options.runtime_profile_switch_replay_report_path
        ),
        runtime_profile_switch_preset=options.runtime_profile_switch_preset,
        final_answer_segment_penalty_runtime_replay=(
            resolved_final_answer_segment_penalty_runtime_replay
        ),
        final_answer_segment_penalty_runtime_replay_report_path=(
            options.final_answer_segment_penalty_runtime_replay_report_path
        ),
        final_answer_segment_penalty_runtime_replay_preset=(
            options.final_answer_segment_penalty_runtime_replay_preset
        ),
        market_movement_runtime_activation=(
            resolved_market_movement_runtime_activation
        ),
        market_movement_runtime_activation_report_path=(
            options.market_movement_runtime_activation_report_path
        ),
        market_movement_runtime_activation_sample_expansion=(
            resolved_market_movement_runtime_activation_sample_expansion
        ),
        market_movement_runtime_activation_sample_expansion_report_path=(
            options.market_movement_runtime_activation_sample_expansion_report_path
        ),
        market_movement_runtime_activation_segment_replay_batch_gate=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate
        ),
        market_movement_runtime_activation_segment_replay_batch_gate_report_path=(
            options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        ),
        recommendation_strategy_governance_preset=(
            options.recommendation_strategy_governance_preset
        ),
        unified_candidate_pool_guard_preset=(
            options.unified_candidate_pool_guard_preset
        ),
        replacement_reranker_shadow_admission=(
            resolved_replacement_reranker_shadow_admission
        ),
        replacement_reranker_shadow_admission_report_path=(
            options.replacement_reranker_shadow_admission_report_path
        ),
        global_planner_short_odds_adapter_gate=(
            resolved_global_planner_short_odds_adapter_gate
        ),
        global_planner_short_odds_adapter_gate_report_path=(
            options.global_planner_short_odds_adapter_gate_report_path
        ),
        global_planner_short_odds_adapter_sample_expansion=(
            resolved_global_planner_short_odds_adapter_sample_expansion
        ),
        global_planner_short_odds_adapter_sample_expansion_report_path=(
            options.global_planner_short_odds_adapter_sample_expansion_report_path
        ),
        recommendation_strategy_promotion_gate=(
            resolved_recommendation_strategy_promotion_gate
        ),
        recommendation_strategy_promotion_gate_report_path=(
            options.recommendation_strategy_promotion_gate_report_path
        ),
        recommendation_strategy_staged_activation_smoke=(
            resolved_recommendation_strategy_staged_activation_smoke
        ),
        recommendation_strategy_staged_activation_smoke_report_path=(
            options.recommendation_strategy_staged_activation_smoke_report_path
        ),
        recommendation_strategy_default_path_isolation=(
            resolved_recommendation_strategy_default_path_isolation
        ),
        recommendation_strategy_default_path_isolation_report_path=(
            options.recommendation_strategy_default_path_isolation_report_path
        ),
        probability_calibration_profile_rolling_admission=(
            resolved_probability_calibration_profile_rolling_admission
        ),
        probability_calibration_profile_rolling_admission_report_path=(
            options.probability_calibration_profile_rolling_admission_report_path
        ),
        probability_calibration_profile_model_quality_gate=(
            resolved_probability_calibration_profile_model_quality_gate
        ),
        probability_calibration_profile_model_quality_gate_report_path=(
            options.probability_calibration_profile_model_quality_gate_report_path
        ),
        asian_handicap_segmented_model_quality_governance=(
            resolved_asian_handicap_segmented_model_quality_governance
        ),
        asian_handicap_segmented_model_quality_governance_report_path=(
            options.asian_handicap_segmented_model_quality_governance_report_path
        ),
        prematch_feature_quality_cycle=resolved_prematch_feature_quality_cycle,
        prematch_feature_quality_cycle_report_path=(
            options.prematch_feature_quality_cycle_report_path
        ),
        prematch_feature_rolling_admission=(
            resolved_prematch_feature_rolling_admission
        ),
        prematch_feature_rolling_admission_report_path=(
            options.prematch_feature_rolling_admission_report_path
        ),
        prematch_feature_sample_readiness=(
            resolved_prematch_feature_sample_readiness
        ),
        prematch_feature_sample_readiness_report_path=(
            options.prematch_feature_sample_readiness_report_path
        ),
    )
    return RecommendationBenchmarkQualityGateResult(
        gate_key=gate_key,
        status=status,
        passed=passed,
        latest_run=latest,
        previous_run=previous,
        checks=checks,
        warnings=warnings,
        historical_suite_quality_gate_report_path=(
            options.historical_suite_quality_gate_report_path
        ),
        historical_suite_quality_gate_present=(
            resolved_historical_suite_quality_gate is not None
        ),
        historical_suite_quality_gate_passed=(
            resolved_historical_suite_quality_gate.passed
            if resolved_historical_suite_quality_gate is not None
            else None
        ),
        historical_suite_quality_gate_summary_json=(
            resolved_historical_suite_quality_gate.summary_json
            if resolved_historical_suite_quality_gate is not None
            else {}
        ),
        budget_stability_audit_report_path=options.budget_stability_audit_report_path,
        budget_stability_audit_present=resolved_budget_stability_audit is not None,
        budget_stability_audit_summary_json=(
            resolved_budget_stability_audit.summary_json
            if resolved_budget_stability_audit is not None
            else {}
        ),
        final_answer_market_concentration_audit_report_path=(
            options.final_answer_market_concentration_audit_report_path
        ),
        final_answer_market_concentration_audit_present=(
            resolved_final_answer_market_concentration_audit is not None
        ),
        final_answer_market_concentration_audit_passed=(
            resolved_final_answer_market_concentration_audit.passed
            if resolved_final_answer_market_concentration_audit is not None
            else None
        ),
        final_answer_market_concentration_audit_summary_json=(
            resolved_final_answer_market_concentration_audit.summary_json
            if resolved_final_answer_market_concentration_audit is not None
            else {}
        ),
        correct_score_admission_report_path=options.correct_score_admission_report_path,
        correct_score_admission_present=resolved_correct_score_admission is not None,
        correct_score_admission_status=(
            resolved_correct_score_admission.status
            if resolved_correct_score_admission is not None
            else None
        ),
        correct_score_admission_holdout_allowed=(
            resolved_correct_score_admission.holdout_allowed
            if resolved_correct_score_admission is not None
            else None
        ),
        correct_score_admission_production_allowed=(
            resolved_correct_score_admission.production_recommendation_allowed
            if resolved_correct_score_admission is not None
            else None
        ),
        correct_score_admission_summary_json=(
            resolved_correct_score_admission.summary_json
            if resolved_correct_score_admission is not None
            else {}
        ),
        runtime_profile_switch_report_path=options.runtime_profile_switch_report_path,
        runtime_profile_switch_gate_present=(
            resolved_runtime_profile_switch_gate is not None
        ),
        runtime_profile_switch_gate_switch_ready=(
            resolved_runtime_profile_switch_gate.switch_ready
            if resolved_runtime_profile_switch_gate is not None
            else None
        ),
        runtime_profile_switch_summary_json=(
            resolved_runtime_profile_switch_gate.summary_json
            if resolved_runtime_profile_switch_gate is not None
            else {}
        ),
        runtime_profile_switch_replay_report_path=(
            options.runtime_profile_switch_replay_report_path
        ),
        runtime_profile_switch_replay_present=(
            resolved_runtime_profile_switch_replay is not None
        ),
        runtime_profile_switch_replay_passed=(
            resolved_runtime_profile_switch_replay.passed
            if resolved_runtime_profile_switch_replay is not None
            else None
        ),
        runtime_profile_switch_replay_summary_json=(
            resolved_runtime_profile_switch_replay.summary_json
            if resolved_runtime_profile_switch_replay is not None
            else {}
        ),
        final_answer_segment_penalty_runtime_replay_report_path=(
            options.final_answer_segment_penalty_runtime_replay_report_path
        ),
        final_answer_segment_penalty_runtime_replay_present=(
            resolved_final_answer_segment_penalty_runtime_replay is not None
        ),
        final_answer_segment_penalty_runtime_replay_holdout_allowed=(
            resolved_final_answer_segment_penalty_runtime_replay.holdout_replay_allowed
            if resolved_final_answer_segment_penalty_runtime_replay is not None
            else None
        ),
        final_answer_segment_penalty_runtime_replay_runtime_allowed=(
            resolved_final_answer_segment_penalty_runtime_replay.runtime_replay_allowed
            if resolved_final_answer_segment_penalty_runtime_replay is not None
            else None
        ),
        final_answer_segment_penalty_runtime_replay_summary_json=(
            resolved_final_answer_segment_penalty_runtime_replay.summary_json
            if resolved_final_answer_segment_penalty_runtime_replay is not None
            else {}
        ),
        market_movement_runtime_activation_report_path=(
            options.market_movement_runtime_activation_report_path
        ),
        market_movement_runtime_activation_present=(
            resolved_market_movement_runtime_activation is not None
        ),
        market_movement_runtime_activation_ready=(
            resolved_market_movement_runtime_activation.staged_activation_ready
            if resolved_market_movement_runtime_activation is not None
            else None
        ),
        market_movement_runtime_activation_summary_json=(
            resolved_market_movement_runtime_activation.summary_json
            if resolved_market_movement_runtime_activation is not None
            else {}
        ),
        market_movement_runtime_activation_sample_expansion_report_path=(
            options.market_movement_runtime_activation_sample_expansion_report_path
        ),
        market_movement_runtime_activation_sample_expansion_present=(
            resolved_market_movement_runtime_activation_sample_expansion is not None
        ),
        market_movement_runtime_activation_sample_expansion_passed=(
            resolved_market_movement_runtime_activation_sample_expansion.passed
            if resolved_market_movement_runtime_activation_sample_expansion is not None
            else None
        ),
        market_movement_runtime_activation_sample_expansion_promotion_ready=(
            resolved_market_movement_runtime_activation_sample_expansion.promotion_ready
            if resolved_market_movement_runtime_activation_sample_expansion is not None
            else None
        ),
        market_movement_runtime_activation_sample_expansion_summary_json=(
            resolved_market_movement_runtime_activation_sample_expansion.summary_json
            if resolved_market_movement_runtime_activation_sample_expansion is not None
            else {}
        ),
        market_movement_runtime_activation_segment_replay_batch_gate_report_path=(
            options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        ),
        market_movement_runtime_activation_segment_replay_batch_gate_present=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate
            is not None
        ),
        market_movement_runtime_activation_segment_replay_batch_ready=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate.runtime_replay_batch_ready
            if resolved_market_movement_runtime_activation_segment_replay_batch_gate
            is not None
            else None
        ),
        market_movement_runtime_activation_segment_replay_batch_promotion_ready=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate.production_promotion_ready
            if resolved_market_movement_runtime_activation_segment_replay_batch_gate
            is not None
            else None
        ),
        market_movement_runtime_activation_segment_replay_batch_summary_json=(
            resolved_market_movement_runtime_activation_segment_replay_batch_gate.summary_json
            if resolved_market_movement_runtime_activation_segment_replay_batch_gate
            is not None
            else {}
        ),
        replacement_reranker_shadow_admission_report_path=(
            options.replacement_reranker_shadow_admission_report_path
        ),
        replacement_reranker_shadow_admission_present=(
            resolved_replacement_reranker_shadow_admission is not None
        ),
        replacement_reranker_shadow_admission_runtime_candidate_allowed=(
            resolved_replacement_reranker_shadow_admission.runtime_profile_candidate_allowed
            if resolved_replacement_reranker_shadow_admission is not None
            else None
        ),
        replacement_reranker_shadow_admission_shadow_allowed=(
            resolved_replacement_reranker_shadow_admission.shadow_allowed
            if resolved_replacement_reranker_shadow_admission is not None
            else None
        ),
        replacement_reranker_shadow_admission_summary_json=(
            resolved_replacement_reranker_shadow_admission.summary_json
            if resolved_replacement_reranker_shadow_admission is not None
            else {}
        ),
        global_planner_short_odds_adapter_gate_report_path=(
            options.global_planner_short_odds_adapter_gate_report_path
        ),
        global_planner_short_odds_adapter_gate_present=(
            resolved_global_planner_short_odds_adapter_gate is not None
        ),
        global_planner_short_odds_adapter_gate_passed=(
            resolved_global_planner_short_odds_adapter_gate.passed
            if resolved_global_planner_short_odds_adapter_gate is not None
            else None
        ),
        global_planner_short_odds_adapter_gate_summary_json=(
            resolved_global_planner_short_odds_adapter_gate.summary_json
            if resolved_global_planner_short_odds_adapter_gate is not None
            else {}
        ),
        global_planner_short_odds_adapter_sample_expansion_report_path=(
            options.global_planner_short_odds_adapter_sample_expansion_report_path
        ),
        global_planner_short_odds_adapter_sample_expansion_present=(
            resolved_global_planner_short_odds_adapter_sample_expansion is not None
        ),
        global_planner_short_odds_adapter_sample_expansion_passed=(
            resolved_global_planner_short_odds_adapter_sample_expansion.passed
            if resolved_global_planner_short_odds_adapter_sample_expansion is not None
            else None
        ),
        global_planner_short_odds_adapter_sample_expansion_promotion_ready=(
            resolved_global_planner_short_odds_adapter_sample_expansion.promotion_ready
            if resolved_global_planner_short_odds_adapter_sample_expansion is not None
            else None
        ),
        global_planner_short_odds_adapter_sample_expansion_summary_json=(
            resolved_global_planner_short_odds_adapter_sample_expansion.summary_json
            if resolved_global_planner_short_odds_adapter_sample_expansion is not None
            else {}
        ),
        recommendation_strategy_promotion_gate_report_path=(
            options.recommendation_strategy_promotion_gate_report_path
        ),
        recommendation_strategy_promotion_gate_present=(
            resolved_recommendation_strategy_promotion_gate is not None
        ),
        recommendation_strategy_promotion_gate_ready=(
            resolved_recommendation_strategy_promotion_gate.strategy_gate_ready
            if resolved_recommendation_strategy_promotion_gate is not None
            else None
        ),
        recommendation_strategy_promotion_gate_summary_json=(
            resolved_recommendation_strategy_promotion_gate.summary_json
            if resolved_recommendation_strategy_promotion_gate is not None
            else {}
        ),
        recommendation_strategy_staged_activation_smoke_report_path=(
            options.recommendation_strategy_staged_activation_smoke_report_path
        ),
        recommendation_strategy_staged_activation_smoke_present=(
            resolved_recommendation_strategy_staged_activation_smoke is not None
        ),
        recommendation_strategy_staged_activation_ready=(
            resolved_recommendation_strategy_staged_activation_smoke.staged_activation_ready
            if resolved_recommendation_strategy_staged_activation_smoke is not None
            else None
        ),
        recommendation_strategy_staged_activation_smoke_summary_json=(
            resolved_recommendation_strategy_staged_activation_smoke.summary_json
            if resolved_recommendation_strategy_staged_activation_smoke is not None
            else {}
        ),
        recommendation_strategy_default_path_isolation_report_path=(
            options.recommendation_strategy_default_path_isolation_report_path
        ),
        recommendation_strategy_default_path_isolation_present=(
            resolved_recommendation_strategy_default_path_isolation is not None
        ),
        recommendation_strategy_default_path_isolated=(
            resolved_recommendation_strategy_default_path_isolation.default_path_isolated
            if resolved_recommendation_strategy_default_path_isolation is not None
            else None
        ),
        recommendation_strategy_default_path_isolation_summary_json=(
            resolved_recommendation_strategy_default_path_isolation.summary_json
            if resolved_recommendation_strategy_default_path_isolation is not None
            else {}
        ),
        probability_calibration_profile_rolling_admission_report_path=(
            options.probability_calibration_profile_rolling_admission_report_path
        ),
        probability_calibration_profile_rolling_admission_present=(
            resolved_probability_calibration_profile_rolling_admission is not None
        ),
        probability_calibration_profile_rolling_admission_candidate_allowed=(
            resolved_probability_calibration_profile_rolling_admission.candidate_profile_allowed
            if resolved_probability_calibration_profile_rolling_admission is not None
            else None
        ),
        probability_calibration_profile_rolling_admission_shadow_allowed=(
            resolved_probability_calibration_profile_rolling_admission.shadow_allowed
            if resolved_probability_calibration_profile_rolling_admission is not None
            else None
        ),
        probability_calibration_profile_rolling_admission_summary_json=(
            resolved_probability_calibration_profile_rolling_admission.summary_json
            if resolved_probability_calibration_profile_rolling_admission is not None
            else {}
        ),
        probability_calibration_profile_model_quality_gate_report_path=(
            options.probability_calibration_profile_model_quality_gate_report_path
        ),
        probability_calibration_profile_model_quality_gate_present=(
            resolved_probability_calibration_profile_model_quality_gate is not None
        ),
        probability_calibration_profile_model_quality_gate_ready=(
            resolved_probability_calibration_profile_model_quality_gate.model_quality_gate_passed
            if resolved_probability_calibration_profile_model_quality_gate is not None
            else None
        ),
        probability_calibration_profile_model_quality_gate_summary_json=(
            resolved_probability_calibration_profile_model_quality_gate.summary_json
            if resolved_probability_calibration_profile_model_quality_gate is not None
            else {}
        ),
        asian_handicap_segmented_model_quality_governance_report_path=(
            options.asian_handicap_segmented_model_quality_governance_report_path
        ),
        asian_handicap_segmented_model_quality_governance_present=(
            resolved_asian_handicap_segmented_model_quality_governance is not None
        ),
        asian_handicap_segmented_model_quality_governance_ready=(
            resolved_asian_handicap_segmented_model_quality_governance.governance_review_ready
            if resolved_asian_handicap_segmented_model_quality_governance is not None
            else None
        ),
        asian_handicap_segmented_model_quality_governance_summary_json=(
            resolved_asian_handicap_segmented_model_quality_governance.summary_json
            if resolved_asian_handicap_segmented_model_quality_governance is not None
            else {}
        ),
        prematch_feature_quality_cycle_report_path=(
            options.prematch_feature_quality_cycle_report_path
        ),
        prematch_feature_quality_cycle_present=(
            resolved_prematch_feature_quality_cycle is not None
        ),
        prematch_feature_quality_cycle_passed=(
            resolved_prematch_feature_quality_cycle.passed
            if resolved_prematch_feature_quality_cycle is not None
            else None
        ),
        prematch_feature_quality_cycle_summary_json=(
            resolved_prematch_feature_quality_cycle.summary_json
            if resolved_prematch_feature_quality_cycle is not None
            else {}
        ),
        prematch_feature_rolling_admission_report_path=(
            options.prematch_feature_rolling_admission_report_path
        ),
        prematch_feature_rolling_admission_present=(
            resolved_prematch_feature_rolling_admission is not None
        ),
        prematch_feature_rolling_admission_candidate_allowed=(
            resolved_prematch_feature_rolling_admission.candidate_feature_allowed
            if resolved_prematch_feature_rolling_admission is not None
            else None
        ),
        prematch_feature_rolling_admission_shadow_allowed=(
            resolved_prematch_feature_rolling_admission.shadow_allowed
            if resolved_prematch_feature_rolling_admission is not None
            else None
        ),
        prematch_feature_rolling_admission_summary_json=(
            resolved_prematch_feature_rolling_admission.summary_json
            if resolved_prematch_feature_rolling_admission is not None
            else {}
        ),
        prematch_feature_sample_readiness_report_path=(
            options.prematch_feature_sample_readiness_report_path
        ),
        prematch_feature_sample_readiness_present=(
            resolved_prematch_feature_sample_readiness is not None
        ),
        prematch_feature_sample_readiness_sample_ready_allowed=(
            resolved_prematch_feature_sample_readiness.sample_ready_allowed
            if resolved_prematch_feature_sample_readiness is not None
            else None
        ),
        prematch_feature_sample_readiness_shadow_allowed=(
            resolved_prematch_feature_sample_readiness.shadow_allowed
            if resolved_prematch_feature_sample_readiness is not None
            else None
        ),
        prematch_feature_sample_readiness_summary_json=(
            resolved_prematch_feature_sample_readiness.summary_json
            if resolved_prematch_feature_sample_readiness is not None
            else {}
        ),
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_benchmark_quality_gate(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _quality_gate_checks(
    latest: StoredRecommendationBenchmarkRun,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
    historical_suite_quality_gate: (
        RecommendationHistoricalSuiteQualityGateEvidence | None
    ) = None,
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None = None,
    final_answer_market_concentration_audit: (
        HistoricalFinalAnswerMarketConcentrationAuditReport | None
    ) = None,
    correct_score_admission: HistoricalCorrectScoreAdmissionReport | None = None,
    runtime_profile_switch_gate: (
        HistoricalShortOddsRuntimeProfileSwitchReport | None
    ) = None,
    runtime_profile_switch_replay: (
        HistoricalShortOddsRuntimeShadowReplayReport | None
    ) = None,
    final_answer_segment_penalty_runtime_replay: (
        HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None
    ) = None,
    market_movement_runtime_activation: (
        HistoricalMarketMovementRiskFilterRuntimeActivationReport | None
    ) = None,
    market_movement_runtime_activation_sample_expansion: (
        HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None
    ) = None,
    market_movement_runtime_activation_segment_replay_batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ) = None,
    replacement_reranker_shadow_admission: (
        HistoricalReplacementRerankerShadowAdmissionReport | None
    ) = None,
    global_planner_short_odds_adapter_gate: (
        HistoricalGlobalPlannerShortOddsAdapterGateReport | None
    ) = None,
    global_planner_short_odds_adapter_sample_expansion: (
        HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None
    ) = None,
    recommendation_strategy_promotion_gate: (
        RecommendationStrategyPromotionGateReport | None
    ) = None,
    recommendation_strategy_staged_activation_smoke: (
        RecommendationStrategyStagedActivationSmokeReport | None
    ) = None,
    recommendation_strategy_default_path_isolation: (
        RecommendationStrategyDefaultPathIsolationReport | None
    ) = None,
    probability_calibration_profile_rolling_admission: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None
    ) = None,
    probability_calibration_profile_model_quality_gate: (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport | None
    ) = None,
    asian_handicap_segmented_model_quality_governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ) = None,
    prematch_feature_quality_cycle: (
        HistoricalPrematchFeatureQualityCycleResult | None
    ) = None,
    prematch_feature_rolling_admission: (
        HistoricalPrematchFeatureRollingAdmissionReport | None
    ) = None,
    prematch_feature_sample_readiness: (
        HistoricalPrematchFeatureSampleReadinessReport | None
    ) = None,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _check_minimum(
            name="scenario_count",
            actual=latest.scenario_count,
            threshold=options.min_scenario_count,
            detail="latest benchmark should cover enough scenarios",
        ),
        _check_optional_minimum(
            name="completed_ratio",
            actual=_ratio(latest.completed_count, latest.scenario_count),
            threshold=options.min_completed_ratio,
            detail="completed benchmark scenarios should meet the configured ratio",
        ),
        _check_optional_maximum(
            name="failed_count",
            actual=latest.failed_count,
            threshold=options.max_failed_count,
            detail="failed benchmark scenarios should stay within the configured limit",
        ),
        _check_optional_maximum(
            name="warning_count",
            actual=latest.warning_count,
            threshold=options.max_warning_count,
            detail="benchmark warnings should stay within the configured limit",
        ),
        _check_minimum(
            name="global_best_selected_count",
            actual=latest.global_best_selected_count,
            threshold=options.min_global_best_selected_count,
            detail="latest benchmark should select enough global best answers",
        ),
        _check_minimum(
            name="global_best_candidate_count",
            actual=_summary_int(latest.summary_json, "global_best_candidate_count"),
            threshold=options.min_global_best_candidate_count,
            detail="latest benchmark should evaluate enough recommendation candidates",
        ),
        _check_minimum(
            name="global_best_generated_option_count",
            actual=_summary_int(
                latest.summary_json,
                "global_best_generated_option_count",
            ),
            threshold=options.min_global_best_generated_option_count,
            detail="latest benchmark should generate enough recommendation options",
        ),
        _check_optional_minimum(
            name="core_replay_ready_ratio",
            actual=_ratio(latest.core_replay_ready_count, latest.completed_count),
            threshold=options.min_core_replay_ready_ratio,
            detail="core replay ready scenarios should meet the configured ratio",
        ),
        _check_optional_minimum(
            name="chain_integrity_ready_ratio",
            actual=_ratio(
                _summary_int(latest.summary_json, "chain_integrity_ready_count"),
                latest.completed_count,
            ),
            threshold=options.min_chain_integrity_ready_ratio,
            detail="chain integrity ready scenarios should meet the configured ratio",
        ),
        _check_optional_maximum(
            name="chain_integrity_critical_issue_count",
            actual=_summary_int(
                latest.summary_json,
                "chain_integrity_total_critical_issue_count",
            ),
            threshold=options.max_chain_integrity_critical_issue_count,
            detail="chain integrity critical issues should stay within the configured limit",
        ),
        _check_optional_minimum(
            name="successor_chain_evaluation_passed_ratio",
            actual=_ratio(
                _summary_int(
                    latest.summary_json,
                    "successor_chain_evaluation_passed_count",
                ),
                latest.completed_count,
            ),
            threshold=options.min_successor_chain_evaluation_passed_ratio,
            detail=(
                "successor chain evaluation passed scenarios should meet the "
                "configured ratio"
            ),
        ),
        _check_minimum(
            name="successor_chain_effective_leaf_count",
            actual=_summary_int(
                latest.summary_json,
                "successor_chain_effective_leaf_count",
            ),
            threshold=options.min_successor_chain_effective_leaf_count,
            detail="successor chain evaluation should observe enough effective leaf runs",
        ),
        _check_optional_maximum(
            name="successor_chain_critical_issue_count",
            actual=_summary_int(
                latest.summary_json,
                "successor_chain_critical_issue_count",
            ),
            threshold=options.max_successor_chain_critical_issue_count,
            detail="successor chain critical issues should stay within the configured limit",
        ),
        _check_optional_maximum(
            name="successor_chain_ambiguous_source_count",
            actual=_summary_int(
                latest.summary_json,
                "successor_chain_ambiguous_source_count",
            ),
            threshold=options.max_successor_chain_ambiguous_source_count,
            detail="ambiguous successor chain sources should stay within the configured limit",
        ),
        _check_optional_maximum(
            name="successor_chain_source_status_sync_required_count",
            actual=_summary_int(
                latest.summary_json,
                "successor_chain_source_status_sync_required_count",
            ),
            threshold=options.max_successor_chain_source_status_sync_required_count,
            detail=(
                "successor sources requiring status sync should stay within "
                "the configured limit"
            ),
        ),
        _check_optional_maximum(
            name="ambiguous_successor_source_count",
            actual=_summary_count(
                latest.summary_json,
                count_key="ambiguous_successor_source_count",
                ids_key="ambiguous_successor_source_recommendation_run_ids",
            ),
            threshold=options.max_ambiguous_successor_source_count,
            detail="ambiguous successor sources should stay within the configured limit",
        ),
        _check_optional_maximum(
            name="stale_recommendation_count",
            actual=_summary_count(
                latest.summary_json,
                count_key="stale_recommendation_count",
                ids_key="stale_recommendation_run_ids",
            ),
            threshold=options.max_stale_recommendation_count,
            detail="stale recommendations should stay within the configured limit",
        ),
        _check_optional_maximum(
            name="successor_recompute_required_count",
            actual=_summary_count(
                latest.summary_json,
                count_key="successor_recompute_required_count",
                ids_key="successor_recompute_required_recommendation_run_ids",
            ),
            threshold=options.max_successor_recompute_required_count,
            detail=(
                "recommendations requiring successor recompute should stay within "
                "the configured limit"
            ),
        ),
        _check_minimum(
            name="final_hit_sample_size",
            actual=latest.final_hit_sample_size,
            threshold=options.min_final_hit_sample_size,
            detail="settled final-hit sample size should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="final_hit_coverage_ratio",
            actual=_ratio(latest.final_hit_sample_size, latest.completed_count),
            threshold=options.min_final_hit_coverage_ratio,
            detail=(
                "settled final-answer replay samples should cover enough completed "
                "benchmark scenarios"
            ),
        ),
        _check_optional_minimum(
            name="final_hit_rate",
            actual=_ratio(latest.final_hit_count, latest.final_hit_sample_size),
            threshold=options.min_final_hit_rate,
            detail="final hit rate should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="average_core_replay_roi",
            actual=latest.average_core_replay_roi,
            threshold=options.min_average_core_replay_roi,
            detail="average core replay ROI should meet the configured minimum",
        ),
        _check_minimum(
            name="upset_capture_sample_size",
            actual=_upset_capture_sample_size(latest.summary_json),
            threshold=options.min_upset_capture_sample_size,
            detail="settled upset opportunity sample size should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="upset_capture_rate",
            actual=_upset_capture_rate(latest.summary_json),
            threshold=options.min_upset_capture_rate,
            detail="upset capture rate should meet the configured minimum",
        ),
    ]
    checks.extend(
        _historical_suite_quality_gate_checks(
            historical_suite_quality_gate,
            options=options,
        )
    )
    checks.extend(
        _budget_stability_audit_checks(
            budget_stability_audit,
            options=options,
        )
    )
    checks.extend(
        _final_answer_market_concentration_audit_checks(
            final_answer_market_concentration_audit,
            options=options,
        )
    )
    checks.extend(
        _correct_score_admission_checks(
            correct_score_admission,
            options=options,
        )
    )
    checks.extend(_unified_candidate_pool_checks(latest.summary_json, options=options))
    checks.extend(
        _runtime_profile_switch_gate_checks(
            runtime_profile_switch_gate,
            runtime_profile_switch_replay,
            options=options,
        )
    )
    checks.extend(
        _final_answer_segment_penalty_runtime_replay_checks(
            final_answer_segment_penalty_runtime_replay,
            options=options,
        )
    )
    checks.extend(
        _market_movement_runtime_activation_checks(
            market_movement_runtime_activation,
            options=options,
        )
    )
    checks.extend(
        _market_movement_runtime_activation_sample_expansion_checks(
            market_movement_runtime_activation_sample_expansion,
            options=options,
        )
    )
    checks.extend(
        _market_movement_runtime_activation_segment_replay_batch_gate_checks(
            market_movement_runtime_activation_segment_replay_batch_gate,
            options=options,
        )
    )
    checks.extend(
        _replacement_reranker_shadow_admission_checks(
            replacement_reranker_shadow_admission,
            options=options,
        )
    )
    checks.extend(
        _global_planner_short_odds_adapter_gate_checks(
            global_planner_short_odds_adapter_gate,
            options=options,
        )
    )
    checks.extend(
        _global_planner_short_odds_adapter_sample_expansion_checks(
            global_planner_short_odds_adapter_sample_expansion,
            options=options,
        )
    )
    checks.extend(
        _recommendation_strategy_promotion_gate_checks(
            recommendation_strategy_promotion_gate,
            options=options,
        )
    )
    checks.extend(
        _recommendation_strategy_staged_activation_smoke_checks(
            recommendation_strategy_staged_activation_smoke,
            options=options,
        )
    )
    checks.extend(
        _recommendation_strategy_default_path_isolation_checks(
            recommendation_strategy_default_path_isolation,
            options=options,
        )
    )
    checks.extend(
        _probability_calibration_profile_rolling_admission_checks(
            probability_calibration_profile_rolling_admission,
            options=options,
        )
    )
    checks.extend(
        _probability_calibration_profile_model_quality_gate_checks(
            probability_calibration_profile_model_quality_gate,
            options=options,
        )
    )
    checks.extend(
        _asian_handicap_segmented_model_quality_governance_checks(
            asian_handicap_segmented_model_quality_governance,
            options=options,
        )
    )
    checks.extend(
        _prematch_feature_quality_cycle_checks(
            prematch_feature_quality_cycle,
            options=options,
        )
    )
    checks.extend(
        _prematch_feature_rolling_admission_checks(
            prematch_feature_rolling_admission,
            options=options,
        )
    )
    checks.extend(
        _prematch_feature_sample_readiness_checks(
            prematch_feature_sample_readiness,
            options=options,
        )
    )
    checks.append(_check_history_status(latest, options=options))
    return checks


def _quality_gate_summary(
    *,
    gate_key: str,
    latest: StoredRecommendationBenchmarkRun,
    previous: StoredRecommendationBenchmarkRun | None,
    checks: Sequence[RecommendationBenchmarkQualityGateCheck],
    passed: bool,
    warnings: Sequence[str],
    historical_suite_quality_gate: (
        RecommendationHistoricalSuiteQualityGateEvidence | None
    ),
    historical_suite_quality_gate_report_path: Path | None,
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None,
    budget_stability_audit_report_path: Path | None,
    final_answer_market_concentration_audit: (
        HistoricalFinalAnswerMarketConcentrationAuditReport | None
    ),
    final_answer_market_concentration_audit_report_path: Path | None,
    correct_score_admission: HistoricalCorrectScoreAdmissionReport | None,
    correct_score_admission_report_path: Path | None,
    runtime_profile_switch_gate: HistoricalShortOddsRuntimeProfileSwitchReport | None,
    runtime_profile_switch_replay: HistoricalShortOddsRuntimeShadowReplayReport | None,
    runtime_profile_switch_report_path: Path | None,
    runtime_profile_switch_replay_report_path: Path | None,
    runtime_profile_switch_preset: str | None,
    final_answer_segment_penalty_runtime_replay: (
        HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None
    ),
    final_answer_segment_penalty_runtime_replay_report_path: Path | None,
    final_answer_segment_penalty_runtime_replay_preset: str | None,
    market_movement_runtime_activation: (
        HistoricalMarketMovementRiskFilterRuntimeActivationReport | None
    ),
    market_movement_runtime_activation_report_path: Path | None,
    market_movement_runtime_activation_sample_expansion: (
        HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None
    ),
    market_movement_runtime_activation_sample_expansion_report_path: Path | None,
    market_movement_runtime_activation_segment_replay_batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ),
    market_movement_runtime_activation_segment_replay_batch_gate_report_path: (
        Path | None
    ),
    recommendation_strategy_governance_preset: str | None,
    unified_candidate_pool_guard_preset: str | None,
    replacement_reranker_shadow_admission: (
        HistoricalReplacementRerankerShadowAdmissionReport | None
    ),
    replacement_reranker_shadow_admission_report_path: Path | None,
    global_planner_short_odds_adapter_gate: (
        HistoricalGlobalPlannerShortOddsAdapterGateReport | None
    ),
    global_planner_short_odds_adapter_gate_report_path: Path | None,
    global_planner_short_odds_adapter_sample_expansion: (
        HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None
    ),
    global_planner_short_odds_adapter_sample_expansion_report_path: Path | None,
    recommendation_strategy_promotion_gate: (
        RecommendationStrategyPromotionGateReport | None
    ),
    recommendation_strategy_promotion_gate_report_path: Path | None,
    recommendation_strategy_staged_activation_smoke: (
        RecommendationStrategyStagedActivationSmokeReport | None
    ),
    recommendation_strategy_staged_activation_smoke_report_path: Path | None,
    recommendation_strategy_default_path_isolation: (
        RecommendationStrategyDefaultPathIsolationReport | None
    ),
    recommendation_strategy_default_path_isolation_report_path: Path | None,
    probability_calibration_profile_rolling_admission: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None
    ),
    probability_calibration_profile_rolling_admission_report_path: Path | None,
    probability_calibration_profile_model_quality_gate: (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport | None
    ),
    probability_calibration_profile_model_quality_gate_report_path: Path | None,
    asian_handicap_segmented_model_quality_governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ),
    asian_handicap_segmented_model_quality_governance_report_path: Path | None,
    prematch_feature_quality_cycle: HistoricalPrematchFeatureQualityCycleResult | None,
    prematch_feature_quality_cycle_report_path: Path | None,
    prematch_feature_rolling_admission: (
        HistoricalPrematchFeatureRollingAdmissionReport | None
    ),
    prematch_feature_rolling_admission_report_path: Path | None,
    prematch_feature_sample_readiness: (
        HistoricalPrematchFeatureSampleReadinessReport | None
    ),
    prematch_feature_sample_readiness_report_path: Path | None,
) -> dict[str, object]:
    failed_checks = [check.name for check in checks if check.status == "failed"]
    summary: dict[str, object] = {
        "gate_key": gate_key,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "latest_benchmark_run_id": latest.recommendation_benchmark_run_id,
        "latest_benchmark_key": latest.benchmark_key,
        "latest_created_at": latest.created_at.isoformat(),
        "previous_benchmark_run_id": (
            previous.recommendation_benchmark_run_id if previous is not None else None
        ),
        "history_status": _history_status(latest),
        "scenario_count": latest.scenario_count,
        "completed_ratio": _ratio(latest.completed_count, latest.scenario_count),
        "failed_count": latest.failed_count,
        "warning_count": latest.warning_count,
        "global_best_selected_count": latest.global_best_selected_count,
        "global_best_candidate_count": _summary_int(
            latest.summary_json,
            "global_best_candidate_count",
        ),
        "global_best_generated_option_count": _summary_int(
            latest.summary_json,
            "global_best_generated_option_count",
        ),
        "unified_candidate_pool_present_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_present_count",
        ),
        "unified_candidate_pool_valid_candidate_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_valid_candidate_count",
        ),
        "unified_candidate_pool_unique_family_count": len(
            _summary_list(
                latest.summary_json,
                "unified_candidate_pool_unique_family_keys",
            )
        ),
        "unified_candidate_pool_unique_family_keys": _summary_list(
            latest.summary_json,
            "unified_candidate_pool_unique_family_keys",
        ),
        "unified_candidate_pool_selection_mismatch_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_selection_mismatch_count",
        ),
        "unified_candidate_pool_selected_2x1_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_selected_2x1_count",
        ),
        "unified_candidate_pool_selected_2x1_rate": _summary_float(
            latest.summary_json,
            "unified_candidate_pool_selected_2x1_rate",
        ),
        "unified_candidate_pool_multiple_value_candidate_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_multiple_value_candidate_count",
        ),
        "unified_candidate_pool_multiple_value_admitted_candidate_count": (
            _summary_int(
                latest.summary_json,
                "unified_candidate_pool_multiple_value_admitted_candidate_count",
            )
        ),
        "unified_candidate_pool_multiple_value_rejected_candidate_count": (
            _summary_int(
                latest.summary_json,
                "unified_candidate_pool_multiple_value_rejected_candidate_count",
            )
        ),
        "unified_candidate_pool_multiple_value_extra_option_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_multiple_value_extra_option_count",
        ),
        "unified_candidate_pool_selected_multiple_value_statuses": _summary_list(
            latest.summary_json,
            "unified_candidate_pool_selected_multiple_value_statuses",
        ),
        "unified_candidate_pool_selected_multiple_value_admitted_count": (
            _summary_int(
                latest.summary_json,
                "unified_candidate_pool_selected_multiple_value_admitted_count",
            )
        ),
        "unified_candidate_pool_selected_multiple_value_rejected_count": (
            _summary_int(
                latest.summary_json,
                "unified_candidate_pool_selected_multiple_value_rejected_count",
            )
        ),
        "unified_candidate_pool_selected_multiple_extra_option_count": _summary_int(
            latest.summary_json,
            "unified_candidate_pool_selected_multiple_extra_option_count",
        ),
        "unified_candidate_pool_multiple_value_rejection_reason_counts": (
            _summary_mapping(
                latest.summary_json,
                "unified_candidate_pool_multiple_value_rejection_reason_counts",
            )
        ),
        "core_replay_ready_ratio": _ratio(
            latest.core_replay_ready_count,
            latest.completed_count,
        ),
        "chain_integrity_ready_ratio": _ratio(
            _summary_int(latest.summary_json, "chain_integrity_ready_count"),
            latest.completed_count,
        ),
        "chain_integrity_critical_issue_count": _summary_int(
            latest.summary_json,
            "chain_integrity_total_critical_issue_count",
        ),
        "successor_chain_evaluation_passed_ratio": _ratio(
            _summary_int(
                latest.summary_json,
                "successor_chain_evaluation_passed_count",
            ),
            latest.completed_count,
        ),
        "successor_chain_effective_leaf_count": _summary_int(
            latest.summary_json,
            "successor_chain_effective_leaf_count",
        ),
        "successor_chain_critical_issue_count": _summary_int(
            latest.summary_json,
            "successor_chain_critical_issue_count",
        ),
        "successor_chain_ambiguous_source_count": _summary_int(
            latest.summary_json,
            "successor_chain_ambiguous_source_count",
        ),
        "successor_chain_source_status_sync_required_count": _summary_int(
            latest.summary_json,
            "successor_chain_source_status_sync_required_count",
        ),
        "ambiguous_successor_source_count": _summary_count(
            latest.summary_json,
            count_key="ambiguous_successor_source_count",
            ids_key="ambiguous_successor_source_recommendation_run_ids",
        ),
        "stale_recommendation_count": _summary_count(
            latest.summary_json,
            count_key="stale_recommendation_count",
            ids_key="stale_recommendation_run_ids",
        ),
        "successor_recompute_required_count": _summary_count(
            latest.summary_json,
            count_key="successor_recompute_required_count",
            ids_key="successor_recompute_required_recommendation_run_ids",
        ),
        "final_hit_sample_size": latest.final_hit_sample_size,
        "final_hit_coverage_ratio": _ratio(
            latest.final_hit_sample_size,
            latest.completed_count,
        ),
        "final_hit_rate": _ratio(
            latest.final_hit_count,
            latest.final_hit_sample_size,
        ),
        "average_core_replay_roi": latest.average_core_replay_roi,
        "upset_capture_sample_size": _upset_capture_sample_size(latest.summary_json),
        "upset_capture_count": _summary_int(latest.summary_json, "upset_capture_count"),
        "upset_capture_rate": _upset_capture_rate(latest.summary_json),
        "failed_checks": failed_checks,
        "warnings": list(warnings),
        "calculation_basis": "recommendation_benchmark_quality_gate_v3_1",
        "runtime_profile_switch_preset": runtime_profile_switch_preset,
        "final_answer_segment_penalty_runtime_replay_preset": (
            final_answer_segment_penalty_runtime_replay_preset
        ),
        "recommendation_strategy_governance_preset": (
            recommendation_strategy_governance_preset
        ),
        "unified_candidate_pool_guard_preset": unified_candidate_pool_guard_preset,
    }
    summary.update(
        _historical_suite_quality_gate_summary_fields(
            historical_suite_quality_gate,
            report_path=historical_suite_quality_gate_report_path,
        )
    )
    summary.update(
        _budget_stability_audit_summary_fields(
            budget_stability_audit,
            report_path=budget_stability_audit_report_path,
        )
    )
    summary.update(
        _final_answer_market_concentration_audit_summary_fields(
            final_answer_market_concentration_audit,
            report_path=final_answer_market_concentration_audit_report_path,
        )
    )
    summary.update(
        _correct_score_admission_summary_fields(
            correct_score_admission,
            report_path=correct_score_admission_report_path,
        )
    )
    summary.update(
        _runtime_profile_switch_summary_fields(
            runtime_profile_switch_gate,
            runtime_profile_switch_replay,
            switch_report_path=runtime_profile_switch_report_path,
            replay_report_path=runtime_profile_switch_replay_report_path,
        )
    )
    summary.update(
        _final_answer_segment_penalty_runtime_replay_summary_fields(
            final_answer_segment_penalty_runtime_replay,
            report_path=final_answer_segment_penalty_runtime_replay_report_path,
        )
    )
    summary.update(
        _market_movement_runtime_activation_summary_fields(
            market_movement_runtime_activation,
            report_path=market_movement_runtime_activation_report_path,
        )
    )
    summary.update(
        _market_movement_runtime_activation_sample_expansion_summary_fields(
            market_movement_runtime_activation_sample_expansion,
            report_path=market_movement_runtime_activation_sample_expansion_report_path,
        )
    )
    summary.update(
        _market_movement_runtime_activation_segment_replay_batch_gate_summary_fields(
            market_movement_runtime_activation_segment_replay_batch_gate,
            report_path=(
                market_movement_runtime_activation_segment_replay_batch_gate_report_path
            ),
        )
    )
    summary.update(
        _replacement_reranker_shadow_admission_summary_fields(
            replacement_reranker_shadow_admission,
            report_path=replacement_reranker_shadow_admission_report_path,
        )
    )
    summary.update(
        _global_planner_short_odds_adapter_gate_summary_fields(
            global_planner_short_odds_adapter_gate,
            report_path=global_planner_short_odds_adapter_gate_report_path,
        )
    )
    summary.update(
        _global_planner_short_odds_adapter_sample_expansion_summary_fields(
            global_planner_short_odds_adapter_sample_expansion,
            report_path=global_planner_short_odds_adapter_sample_expansion_report_path,
        )
    )
    summary.update(
        _recommendation_strategy_promotion_gate_summary_fields(
            recommendation_strategy_promotion_gate,
            report_path=recommendation_strategy_promotion_gate_report_path,
        )
    )
    summary.update(
        _recommendation_strategy_staged_activation_smoke_summary_fields(
            recommendation_strategy_staged_activation_smoke,
            report_path=recommendation_strategy_staged_activation_smoke_report_path,
        )
    )
    summary.update(
        _recommendation_strategy_default_path_isolation_summary_fields(
            recommendation_strategy_default_path_isolation,
            report_path=recommendation_strategy_default_path_isolation_report_path,
        )
    )
    summary.update(
        _probability_calibration_profile_rolling_admission_summary_fields(
            probability_calibration_profile_rolling_admission,
            report_path=probability_calibration_profile_rolling_admission_report_path,
        )
    )
    summary.update(
        _probability_calibration_profile_model_quality_gate_summary_fields(
            probability_calibration_profile_model_quality_gate,
            report_path=probability_calibration_profile_model_quality_gate_report_path,
        )
    )
    summary.update(
        _asian_handicap_segmented_model_quality_governance_summary_fields(
            asian_handicap_segmented_model_quality_governance,
            report_path=(
                asian_handicap_segmented_model_quality_governance_report_path
            ),
        )
    )
    summary.update(
        _prematch_feature_quality_cycle_summary_fields(
            prematch_feature_quality_cycle,
            report_path=prematch_feature_quality_cycle_report_path,
        )
    )
    summary.update(
        _prematch_feature_rolling_admission_summary_fields(
            prematch_feature_rolling_admission,
            report_path=prematch_feature_rolling_admission_report_path,
        )
    )
    summary.update(
        _prematch_feature_sample_readiness_summary_fields(
            prematch_feature_sample_readiness,
            report_path=prematch_feature_sample_readiness_report_path,
        )
    )
    return summary


def _historical_suite_quality_gate_checks(
    historical_suite_quality_gate: RecommendationHistoricalSuiteQualityGateEvidence
    | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _historical_suite_quality_gate_present_check(
            historical_suite_quality_gate,
            options=options,
        )
    ]
    if historical_suite_quality_gate is None:
        return checks

    summary = historical_suite_quality_gate.summary_json
    checks.extend(
        [
            RecommendationBenchmarkQualityGateCheck(
                name="historical_suite_quality_gate_passed",
                status="passed" if historical_suite_quality_gate.passed else "failed",
                actual=historical_suite_quality_gate.passed,
                threshold=True,
                detail="attached historical suite quality gate should pass",
            ),
            _check_minimum(
                name="historical_suite_slice_count",
                actual=_summary_int(summary, "slice_count"),
                threshold=options.min_historical_suite_slice_count,
                detail="attached historical suite should cover enough frozen slices",
            ),
            _check_minimum(
                name="historical_suite_comparison_count",
                actual=_summary_int(summary, "comparison_count"),
                threshold=options.min_historical_suite_comparison_count,
                detail=(
                    "attached historical suite should contain enough optimizer "
                    "comparisons"
                ),
            ),
            _check_minimum(
                name="historical_suite_candidate_final_hit_sample_size",
                actual=_summary_int(summary, "candidate_final_hit_sample_size"),
                threshold=(
                    options.min_historical_suite_candidate_final_hit_sample_size
                ),
                detail=(
                    "attached historical suite should contain enough settled "
                    "candidate final-answer samples"
                ),
            ),
            _check_optional_minimum(
                name="historical_suite_candidate_final_hit_coverage_ratio",
                actual=_optional_float(summary.get("candidate_final_hit_coverage_ratio")),
                threshold=(
                    options.min_historical_suite_candidate_final_hit_coverage_ratio
                ),
                detail=(
                    "attached historical suite final-hit samples should cover "
                    "enough optimizer comparisons"
                ),
            ),
            _check_minimum(
                name="historical_suite_candidate_dynamic_mixed_final_answer_count",
                actual=_summary_int(
                    summary,
                    "candidate_dynamic_mixed_final_answer_count",
                ),
                threshold=(
                    options.min_historical_suite_candidate_dynamic_mixed_final_answer_count
                ),
                detail=(
                    "attached historical suite should include enough dynamic "
                    "mixed-market final answers when explicitly required"
                ),
            ),
            _check_optional_minimum(
                name="historical_suite_candidate_dynamic_mixed_final_answer_rate",
                actual=_optional_float(
                    summary.get("candidate_dynamic_mixed_final_answer_rate")
                ),
                threshold=(
                    options.min_historical_suite_candidate_dynamic_mixed_final_answer_rate
                ),
                detail=(
                    "attached historical suite should keep enough dynamic "
                    "mixed-market final-answer coverage"
                ),
            ),
            _check_minimum(
                name="historical_suite_candidate_handicap_final_answer_count",
                actual=_summary_int(
                    summary,
                    "candidate_handicap_final_answer_count",
                ),
                threshold=(
                    options.min_historical_suite_candidate_handicap_final_answer_count
                ),
                detail=(
                    "attached historical suite should include enough handicap "
                    "final answers when explicitly required"
                ),
            ),
            _check_minimum(
                name="historical_suite_candidate_correct_score_final_answer_count",
                actual=_summary_int(
                    summary,
                    "candidate_correct_score_final_answer_count",
                ),
                threshold=(
                    options.min_historical_suite_candidate_correct_score_final_answer_count
                ),
                detail=(
                    "attached historical suite should include enough correct-score "
                    "final answers when explicitly required"
                ),
            ),
            _check_minimum(
                name="historical_suite_candidate_multiple_choice_final_answer_count",
                actual=_summary_int(
                    summary,
                    "candidate_multiple_choice_final_answer_count",
                ),
                threshold=(
                    options.min_historical_suite_candidate_multiple_choice_final_answer_count
                ),
                detail=(
                    "attached historical suite should include enough multiple-choice "
                    "final answers when explicitly required"
                ),
            ),
            _check_optional_maximum(
                name="historical_suite_failed_check_count",
                actual=_summary_failed_check_count(summary),
                threshold=options.max_historical_suite_failed_check_count,
                detail=(
                    "attached historical suite failed checks should stay within "
                    "the configured limit"
                ),
            ),
            _required_bool_check(
                name="historical_suite_lifecycle_quality_cycle_present",
                actual=_summary_bool(summary, "lifecycle_quality_cycle_present"),
                required=options.require_historical_suite_lifecycle_evidence,
                detail=(
                    "attached historical suite should include lifecycle quality-cycle "
                    "evidence"
                ),
            ),
            _required_bool_check(
                name="historical_suite_lifecycle_quality_cycle_passed",
                actual=_summary_bool(summary, "lifecycle_quality_cycle_passed"),
                required=options.require_historical_suite_lifecycle_evidence,
                detail="attached lifecycle quality cycle should pass",
            ),
            _required_bool_check(
                name="historical_suite_lifecycle_persisted_smoke_present",
                actual=_summary_bool(summary, "lifecycle_persisted_smoke_present"),
                required=options.require_historical_suite_lifecycle_evidence,
                detail=(
                    "attached historical suite lifecycle evidence should include "
                    "persisted smoke"
                ),
            ),
            _required_bool_check(
                name="historical_suite_lifecycle_persisted_smoke_passed",
                actual=_summary_bool(summary, "lifecycle_persisted_smoke_passed"),
                required=options.require_historical_suite_lifecycle_evidence,
                detail="attached persisted lifecycle smoke should pass",
            ),
            _required_bool_check(
                name="historical_suite_lifecycle_source_status_synced",
                actual=_summary_bool(summary, "lifecycle_source_status_synced"),
                required=(
                    options.require_historical_suite_lifecycle_source_status_synced
                ),
                detail=(
                    "attached lifecycle evidence should show superseded source "
                    "status synced"
                ),
            ),
            _check_minimum(
                name="historical_suite_lifecycle_effective_leaf_count",
                actual=_summary_int(summary, "lifecycle_effective_leaf_count"),
                threshold=options.min_historical_suite_lifecycle_effective_leaf_count,
                detail=(
                    "attached lifecycle evidence should observe enough effective "
                    "leaf runs"
                ),
            ),
            _check_minimum(
                name="historical_suite_lifecycle_active_edge_count",
                actual=_summary_int(summary, "lifecycle_active_edge_count"),
                threshold=options.min_historical_suite_lifecycle_active_edge_count,
                detail=(
                    "attached lifecycle evidence should observe enough active "
                    "successor edges"
                ),
            ),
            _check_optional_maximum(
                name="historical_suite_lifecycle_critical_issue_count",
                actual=_summary_int(summary, "lifecycle_critical_issue_count"),
                threshold=(
                    options.max_historical_suite_lifecycle_critical_issue_count
                ),
                detail=(
                    "attached lifecycle critical issues should stay within the "
                    "configured limit"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "historical_suite_lifecycle_source_status_sync_required_count"
                ),
                actual=_summary_int(
                    summary,
                    "lifecycle_source_status_sync_required_count",
                ),
                threshold=(
                    options.max_historical_suite_lifecycle_source_status_sync_required_count
                ),
                detail=(
                    "attached lifecycle source status sync-required count should "
                    "stay within the configured limit"
                ),
            ),
            _required_bool_check(
                name="historical_suite_successor_chain_evaluation_present",
                actual=_summary_bool(summary, "successor_chain_evaluation_present"),
                required=(
                    options.require_historical_suite_successor_chain_evaluation
                ),
                detail=(
                    "attached historical suite should include successor-chain "
                    "evaluation evidence"
                ),
            ),
            _required_bool_check(
                name="historical_suite_successor_chain_evaluation_passed",
                actual=_summary_bool(summary, "successor_chain_evaluation_passed"),
                required=(
                    options.require_historical_suite_successor_chain_evaluation
                ),
                detail="attached successor-chain evaluation should pass",
            ),
            _required_bool_check(
                name="historical_suite_successor_effective_final_only_ready",
                actual=_summary_bool(summary, "successor_effective_final_only_ready"),
                required=(
                    options.require_historical_suite_successor_chain_evaluation
                ),
                detail=(
                    "attached successor-chain evidence should identify final "
                    "effective leaf runs"
                ),
            ),
            _check_minimum(
                name="historical_suite_successor_effective_leaf_count",
                actual=_summary_int(summary, "successor_effective_leaf_count"),
                threshold=(
                    options.min_historical_suite_successor_effective_leaf_count
                ),
                detail=(
                    "attached successor-chain evidence should include enough "
                    "effective leaf runs"
                ),
            ),
            _check_minimum(
                name="historical_suite_successor_active_edge_count",
                actual=_summary_int(summary, "successor_active_edge_count"),
                threshold=options.min_historical_suite_successor_active_edge_count,
                detail=(
                    "attached successor-chain evidence should include enough "
                    "active source->successor edges"
                ),
            ),
            _check_optional_maximum(
                name="historical_suite_successor_critical_issue_count",
                actual=_summary_int(summary, "successor_critical_issue_count"),
                threshold=(
                    options.max_historical_suite_successor_critical_issue_count
                ),
                detail=(
                    "attached successor-chain critical issues should stay within "
                    "the configured limit"
                ),
            ),
            _check_optional_maximum(
                name="historical_suite_successor_ambiguous_source_count",
                actual=_summary_int(summary, "successor_ambiguous_source_count"),
                threshold=(
                    options.max_historical_suite_successor_ambiguous_source_count
                ),
                detail=(
                    "attached successor-chain ambiguous sources should stay "
                    "within the configured limit"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "historical_suite_successor_source_status_sync_required_count"
                ),
                actual=_summary_int(
                    summary,
                    "successor_source_status_sync_required_count",
                ),
                threshold=(
                    options.max_historical_suite_successor_source_status_sync_required_count
                ),
                detail=(
                    "attached successor-chain source status sync debt should stay "
                    "within the configured limit"
                ),
            ),
            _required_bool_check(
                name="historical_suite_market_movement_runtime_replay_present",
                actual=_summary_bool(
                    summary,
                    "market_movement_runtime_replay_present",
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                ),
                detail=(
                    "attached historical suite should include market-movement "
                    "runtime replay evidence"
                ),
            ),
            _required_bool_check(
                name="historical_suite_market_movement_runtime_replay_passed",
                actual=_summary_bool(
                    summary,
                    "market_movement_runtime_replay_passed",
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                ),
                detail="attached market-movement runtime replay should pass",
            ),
            _required_bool_check(
                name="historical_suite_market_movement_runtime_replay_allowed",
                actual=_summary_bool(
                    summary,
                    "market_movement_runtime_replay_allowed",
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                    and options.require_historical_suite_market_movement_runtime_replay_allowed
                ),
                detail=(
                    "attached market-movement runtime replay should be "
                    "shadow-allowed"
                ),
            ),
            _required_bool_check(
                name="historical_suite_market_movement_runtime_replay_passed_status",
                actual=(
                    _summary_str(
                        summary,
                        "market_movement_runtime_replay_status",
                    )
                    == "runtime_shadow_replay_passed"
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                    and (
                        options.require_historical_suite_market_movement_runtime_replay_passed_status
                    )
                ),
                detail=(
                    "attached market-movement runtime replay should have the "
                    "runtime pass status"
                ),
            ),
            _check_minimum(
                name="historical_suite_market_movement_runtime_replay_rule_count",
                actual=_summary_int(
                    summary,
                    "market_movement_runtime_replay_rule_count",
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_rule_count
                ),
                detail="attached market-movement runtime replay should load rules",
            ),
            _check_minimum(
                name=(
                    "historical_suite_market_movement_runtime_replay_selected_rule_count"
                ),
                actual=_summary_int(
                    summary,
                    "market_movement_runtime_replay_selected_rule_count",
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_selected_rule_count
                ),
                detail="attached market-movement runtime replay should select rules",
            ),
            _check_minimum(
                name="historical_suite_market_movement_runtime_replay_accepted_count",
                actual=_summary_int(
                    summary,
                    "market_movement_runtime_replay_accepted_count",
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_accepted_count
                ),
                detail="attached market-movement runtime replay should accept segments",
            ),
            _check_minimum(
                name=(
                    "historical_suite_market_movement_runtime_replay_adjusted_fixture_count"
                ),
                actual=_summary_int(
                    summary,
                    "market_movement_runtime_replay_adjusted_fixture_count",
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count
                ),
                detail="attached market-movement runtime replay should adjust fixtures",
            ),
            _check_minimum(
                name=(
                    "historical_suite_market_movement_runtime_replay_adjusted_prediction_count"
                ),
                actual=_summary_int(
                    summary,
                    "market_movement_runtime_replay_adjusted_prediction_count",
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count
                ),
                detail="attached market-movement runtime replay should adjust predictions",
            ),
            _check_optional_minimum(
                name=(
                    "historical_suite_market_movement_runtime_replay_final_hit_rate_delta"
                ),
                actual=_optional_float(
                    summary.get("market_movement_runtime_replay_final_hit_rate_delta")
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_final_hit_rate_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail=(
                    "attached market-movement runtime replay final-hit rate "
                    "should not regress"
                ),
            ),
            _check_optional_minimum(
                name="historical_suite_market_movement_runtime_replay_roi_delta",
                actual=_optional_float(
                    summary.get("market_movement_runtime_replay_roi_delta")
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_roi_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail="attached market-movement runtime replay ROI should not regress",
            ),
            _check_optional_minimum(
                name=(
                    "historical_suite_market_movement_runtime_replay_profit_loss_delta"
                ),
                actual=_optional_float(
                    summary.get("market_movement_runtime_replay_profit_loss_delta")
                ),
                threshold=(
                    options.min_historical_suite_market_movement_runtime_replay_profit_loss_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail=(
                    "attached market-movement runtime replay profit/loss should "
                    "not regress"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "historical_suite_market_movement_runtime_replay_brier_score_delta"
                ),
                actual=_optional_float(
                    summary.get("market_movement_runtime_replay_brier_score_delta")
                ),
                threshold=(
                    options.max_historical_suite_market_movement_runtime_replay_brier_score_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail=(
                    "attached market-movement runtime replay Brier score should "
                    "not regress"
                ),
            ),
            _check_optional_maximum(
                name="historical_suite_market_movement_runtime_replay_log_loss_delta",
                actual=_optional_float(
                    summary.get("market_movement_runtime_replay_log_loss_delta")
                ),
                threshold=(
                    options.max_historical_suite_market_movement_runtime_replay_log_loss_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail=(
                    "attached market-movement runtime replay log loss should not "
                    "regress"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "historical_suite_market_movement_runtime_replay_calibration_delta"
                ),
                actual=_optional_float(
                    summary.get(
                        "market_movement_runtime_replay_mean_calibration_error_delta"
                    )
                ),
                threshold=(
                    options.max_historical_suite_market_movement_runtime_replay_mean_calibration_error_delta
                    if options.require_historical_suite_market_movement_runtime_replay
                    else None
                ),
                detail=(
                    "attached market-movement runtime replay calibration should "
                    "not regress"
                ),
            ),
            _required_bool_check(
                name=(
                    "historical_suite_market_movement_runtime_replay_production_unchanged"
                ),
                actual=not _summary_bool(
                    summary,
                    "market_movement_runtime_replay_production_changed",
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                    and (
                        options.require_historical_suite_market_movement_runtime_replay_production_unchanged
                    )
                ),
                detail=(
                    "attached market-movement runtime replay should not change "
                    "production"
                ),
            ),
            _required_bool_check(
                name="historical_suite_market_movement_runtime_replay_public_unchanged",
                actual=not _summary_bool(
                    summary,
                    "market_movement_runtime_replay_public_changed",
                ),
                required=(
                    options.require_historical_suite_market_movement_runtime_replay
                    and (
                        options.require_historical_suite_market_movement_runtime_replay_public_response_unchanged
                    )
                ),
                detail=(
                    "attached market-movement runtime replay should not change "
                    "public output"
                ),
            ),
        ]
    )
    return checks


def _historical_suite_quality_gate_present_check(
    historical_suite_quality_gate: RecommendationHistoricalSuiteQualityGateEvidence
    | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_historical_suite_quality_gate:
        return _skipped_check(
            name="historical_suite_quality_gate_present",
            actual=historical_suite_quality_gate is not None,
            detail="historical suite quality-gate evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="historical_suite_quality_gate_present",
        status="passed" if historical_suite_quality_gate is not None else "failed",
        actual=historical_suite_quality_gate is not None,
        threshold=True,
        detail=(
            "historical suite quality-gate evidence must be attached before this "
            "benchmark gate can pass"
        ),
    )


def _historical_suite_quality_gate_summary_fields(
    historical_suite_quality_gate: RecommendationHistoricalSuiteQualityGateEvidence
    | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if historical_suite_quality_gate is None:
        return {
            "historical_suite_quality_gate_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "historical_suite_quality_gate_present": False,
            "historical_suite_quality_gate_passed": None,
            "historical_suite_quality_gate_key": None,
            "historical_suite_quality_gate_status": None,
            "historical_suite_quality_gate_suite_key": None,
            "historical_suite_quality_gate_suite_status": None,
            "historical_suite_slice_count": 0,
            "historical_suite_comparison_count": 0,
            "historical_suite_candidate_final_hit_sample_size": 0,
            "historical_suite_candidate_final_hit_coverage_ratio": None,
            "historical_suite_candidate_final_hit_rate": None,
            "historical_suite_candidate_roi": None,
            "historical_suite_baseline_dynamic_mixed_final_answer_count": 0,
            "historical_suite_candidate_dynamic_mixed_final_answer_count": 0,
            "historical_suite_baseline_dynamic_mixed_final_answer_rate": None,
            "historical_suite_candidate_dynamic_mixed_final_answer_rate": None,
            "historical_suite_baseline_final_answer_market_type_counts": {},
            "historical_suite_candidate_final_answer_market_type_counts": {},
            "historical_suite_baseline_handicap_final_answer_count": 0,
            "historical_suite_candidate_handicap_final_answer_count": 0,
            "historical_suite_baseline_handicap_final_answer_rate": None,
            "historical_suite_candidate_handicap_final_answer_rate": None,
            "historical_suite_baseline_correct_score_final_answer_count": 0,
            "historical_suite_candidate_correct_score_final_answer_count": 0,
            "historical_suite_baseline_multiple_choice_final_answer_count": 0,
            "historical_suite_candidate_multiple_choice_final_answer_count": 0,
            "historical_suite_baseline_final_answer_selected_candidate_count": 0,
            "historical_suite_candidate_final_answer_selected_candidate_count": 0,
            "historical_suite_baseline_final_answer_multiple_choice_fixture_count": 0,
            "historical_suite_candidate_final_answer_multiple_choice_fixture_count": 0,
            "historical_suite_failed_check_count": 0,
            "historical_suite_lifecycle_quality_cycle_present": False,
            "historical_suite_lifecycle_quality_cycle_passed": None,
            "historical_suite_lifecycle_persisted_smoke_present": False,
            "historical_suite_lifecycle_persisted_smoke_passed": None,
            "historical_suite_lifecycle_source_status_synced": None,
            "historical_suite_lifecycle_effective_leaf_count": 0,
            "historical_suite_lifecycle_active_edge_count": 0,
            "historical_suite_lifecycle_critical_issue_count": 0,
            "historical_suite_lifecycle_source_status_sync_required_count": 0,
            "historical_suite_successor_chain_evaluation_present": False,
            "historical_suite_successor_chain_evaluation_passed": None,
            "historical_suite_successor_effective_final_only_ready": False,
            "historical_suite_successor_effective_leaf_count": 0,
            "historical_suite_successor_active_edge_count": 0,
            "historical_suite_successor_critical_issue_count": 0,
            "historical_suite_successor_ambiguous_source_count": 0,
            "historical_suite_successor_source_status_sync_required_count": 0,
            "historical_suite_market_movement_runtime_replay_present": False,
            "historical_suite_market_movement_runtime_replay_passed": None,
            "historical_suite_market_movement_runtime_replay_status": None,
            "historical_suite_market_movement_runtime_replay_allowed": False,
            "historical_suite_market_movement_runtime_replay_holdout_allowed": False,
            "historical_suite_market_movement_runtime_replay_rule_count": 0,
            "historical_suite_market_movement_runtime_replay_selected_rule_count": 0,
            "historical_suite_market_movement_runtime_replay_candidate_count": 0,
            "historical_suite_market_movement_runtime_replay_accepted_count": 0,
            "historical_suite_market_movement_runtime_replay_adjusted_fixture_count": 0,
            "historical_suite_market_movement_runtime_replay_adjusted_prediction_count": 0,
            "historical_suite_market_movement_runtime_replay_final_hit_rate_delta": None,
            "historical_suite_market_movement_runtime_replay_roi_delta": None,
            "historical_suite_market_movement_runtime_replay_profit_loss_delta": None,
            "historical_suite_market_movement_runtime_replay_brier_score_delta": None,
            "historical_suite_market_movement_runtime_replay_log_loss_delta": None,
            "historical_suite_market_movement_runtime_replay_calibration_delta": None,
            "historical_suite_market_movement_runtime_replay_production_changed": None,
            "historical_suite_market_movement_runtime_replay_public_changed": None,
        }

    summary = historical_suite_quality_gate.summary_json
    return {
        "historical_suite_quality_gate_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "historical_suite_quality_gate_present": True,
        "historical_suite_quality_gate_passed": historical_suite_quality_gate.passed,
        "historical_suite_quality_gate_key": historical_suite_quality_gate.gate_key,
        "historical_suite_quality_gate_status": historical_suite_quality_gate.status,
        "historical_suite_quality_gate_suite_key": (
            historical_suite_quality_gate.suite_key
            or _summary_str(summary, "suite_key")
        ),
        "historical_suite_quality_gate_suite_status": (
            historical_suite_quality_gate.suite_status
            or _summary_str(summary, "suite_status")
        ),
        "historical_suite_slice_count": _summary_int(summary, "slice_count"),
        "historical_suite_comparison_count": _summary_int(
            summary,
            "comparison_count",
        ),
        "historical_suite_candidate_final_hit_sample_size": _summary_int(
            summary,
            "candidate_final_hit_sample_size",
        ),
        "historical_suite_candidate_final_hit_coverage_ratio": _optional_float(
            summary.get("candidate_final_hit_coverage_ratio")
        ),
        "historical_suite_candidate_final_hit_rate": _optional_float(
            summary.get("candidate_final_hit_rate")
        ),
        "historical_suite_candidate_roi": _optional_float(
            summary.get("candidate_roi")
        ),
        "historical_suite_baseline_dynamic_mixed_final_answer_count": (
            _summary_int(summary, "baseline_dynamic_mixed_final_answer_count")
        ),
        "historical_suite_candidate_dynamic_mixed_final_answer_count": (
            _summary_int(summary, "candidate_dynamic_mixed_final_answer_count")
        ),
        "historical_suite_baseline_dynamic_mixed_final_answer_rate": (
            _optional_float(summary.get("baseline_dynamic_mixed_final_answer_rate"))
        ),
        "historical_suite_candidate_dynamic_mixed_final_answer_rate": (
            _optional_float(summary.get("candidate_dynamic_mixed_final_answer_rate"))
        ),
        "historical_suite_baseline_final_answer_market_type_counts": (
            _summary_mapping(summary, "baseline_final_answer_market_type_counts")
        ),
        "historical_suite_candidate_final_answer_market_type_counts": (
            _summary_mapping(summary, "candidate_final_answer_market_type_counts")
        ),
        "historical_suite_baseline_handicap_final_answer_count": _summary_int(
            summary,
            "baseline_handicap_final_answer_count",
        ),
        "historical_suite_candidate_handicap_final_answer_count": _summary_int(
            summary,
            "candidate_handicap_final_answer_count",
        ),
        "historical_suite_baseline_handicap_final_answer_rate": _optional_float(
            summary.get("baseline_handicap_final_answer_rate")
        ),
        "historical_suite_candidate_handicap_final_answer_rate": _optional_float(
            summary.get("candidate_handicap_final_answer_rate")
        ),
        "historical_suite_baseline_correct_score_final_answer_count": (
            _summary_int(summary, "baseline_correct_score_final_answer_count")
        ),
        "historical_suite_candidate_correct_score_final_answer_count": (
            _summary_int(summary, "candidate_correct_score_final_answer_count")
        ),
        "historical_suite_baseline_multiple_choice_final_answer_count": (
            _summary_int(summary, "baseline_multiple_choice_final_answer_count")
        ),
        "historical_suite_candidate_multiple_choice_final_answer_count": (
            _summary_int(summary, "candidate_multiple_choice_final_answer_count")
        ),
        "historical_suite_baseline_final_answer_selected_candidate_count": (
            _summary_int(summary, "baseline_final_answer_selected_candidate_count")
        ),
        "historical_suite_candidate_final_answer_selected_candidate_count": (
            _summary_int(summary, "candidate_final_answer_selected_candidate_count")
        ),
        "historical_suite_baseline_final_answer_multiple_choice_fixture_count": (
            _summary_int(
                summary,
                "baseline_final_answer_multiple_choice_fixture_count",
            )
        ),
        "historical_suite_candidate_final_answer_multiple_choice_fixture_count": (
            _summary_int(
                summary,
                "candidate_final_answer_multiple_choice_fixture_count",
            )
        ),
        "historical_suite_failed_check_count": _summary_failed_check_count(summary),
        "historical_suite_lifecycle_quality_cycle_present": _summary_bool(
            summary,
            "lifecycle_quality_cycle_present",
        ),
        "historical_suite_lifecycle_quality_cycle_passed": _summary_optional_bool(
            summary,
            "lifecycle_quality_cycle_passed",
        ),
        "historical_suite_lifecycle_persisted_smoke_present": _summary_bool(
            summary,
            "lifecycle_persisted_smoke_present",
        ),
        "historical_suite_lifecycle_persisted_smoke_passed": _summary_optional_bool(
            summary,
            "lifecycle_persisted_smoke_passed",
        ),
        "historical_suite_lifecycle_source_status_synced": _summary_optional_bool(
            summary,
            "lifecycle_source_status_synced",
        ),
        "historical_suite_lifecycle_effective_leaf_count": _summary_int(
            summary,
            "lifecycle_effective_leaf_count",
        ),
        "historical_suite_lifecycle_active_edge_count": _summary_int(
            summary,
            "lifecycle_active_edge_count",
        ),
        "historical_suite_lifecycle_critical_issue_count": _summary_int(
            summary,
            "lifecycle_critical_issue_count",
        ),
        "historical_suite_lifecycle_source_status_sync_required_count": (
            _summary_int(summary, "lifecycle_source_status_sync_required_count")
        ),
        "historical_suite_successor_chain_evaluation_present": _summary_bool(
            summary,
            "successor_chain_evaluation_present",
        ),
        "historical_suite_successor_chain_evaluation_passed": (
            _summary_optional_bool(summary, "successor_chain_evaluation_passed")
        ),
        "historical_suite_successor_effective_final_only_ready": _summary_bool(
            summary,
            "successor_effective_final_only_ready",
        ),
        "historical_suite_successor_effective_leaf_count": _summary_int(
            summary,
            "successor_effective_leaf_count",
        ),
        "historical_suite_successor_active_edge_count": _summary_int(
            summary,
            "successor_active_edge_count",
        ),
        "historical_suite_successor_critical_issue_count": _summary_int(
            summary,
            "successor_critical_issue_count",
        ),
        "historical_suite_successor_ambiguous_source_count": _summary_int(
            summary,
            "successor_ambiguous_source_count",
        ),
        "historical_suite_successor_source_status_sync_required_count": _summary_int(
            summary,
            "successor_source_status_sync_required_count",
        ),
        "historical_suite_market_movement_runtime_replay_present": _summary_bool(
            summary,
            "market_movement_runtime_replay_present",
        ),
        "historical_suite_market_movement_runtime_replay_passed": _summary_optional_bool(
            summary,
            "market_movement_runtime_replay_passed",
        ),
        "historical_suite_market_movement_runtime_replay_status": _summary_str(
            summary,
            "market_movement_runtime_replay_status",
        ),
        "historical_suite_market_movement_runtime_replay_allowed": _summary_bool(
            summary,
            "market_movement_runtime_replay_allowed",
        ),
        "historical_suite_market_movement_runtime_replay_holdout_allowed": _summary_bool(
            summary,
            "market_movement_runtime_replay_holdout_allowed",
        ),
        "historical_suite_market_movement_runtime_replay_rule_count": _summary_int(
            summary,
            "market_movement_runtime_replay_rule_count",
        ),
        "historical_suite_market_movement_runtime_replay_selected_rule_count": (
            _summary_int(summary, "market_movement_runtime_replay_selected_rule_count")
        ),
        "historical_suite_market_movement_runtime_replay_candidate_count": (
            _summary_int(summary, "market_movement_runtime_replay_candidate_count")
        ),
        "historical_suite_market_movement_runtime_replay_accepted_count": (
            _summary_int(summary, "market_movement_runtime_replay_accepted_count")
        ),
        "historical_suite_market_movement_runtime_replay_adjusted_fixture_count": (
            _summary_int(summary, "market_movement_runtime_replay_adjusted_fixture_count")
        ),
        "historical_suite_market_movement_runtime_replay_adjusted_prediction_count": (
            _summary_int(
                summary,
                "market_movement_runtime_replay_adjusted_prediction_count",
            )
        ),
        "historical_suite_market_movement_runtime_replay_final_hit_rate_delta": (
            _optional_float(
                summary.get("market_movement_runtime_replay_final_hit_rate_delta")
            )
        ),
        "historical_suite_market_movement_runtime_replay_roi_delta": _optional_float(
            summary.get("market_movement_runtime_replay_roi_delta")
        ),
        "historical_suite_market_movement_runtime_replay_profit_loss_delta": (
            _optional_float(summary.get("market_movement_runtime_replay_profit_loss_delta"))
        ),
        "historical_suite_market_movement_runtime_replay_brier_score_delta": (
            _optional_float(summary.get("market_movement_runtime_replay_brier_score_delta"))
        ),
        "historical_suite_market_movement_runtime_replay_log_loss_delta": (
            _optional_float(summary.get("market_movement_runtime_replay_log_loss_delta"))
        ),
        "historical_suite_market_movement_runtime_replay_calibration_delta": (
            _optional_float(
                summary.get(
                    "market_movement_runtime_replay_mean_calibration_error_delta"
                )
            )
        ),
        "historical_suite_market_movement_runtime_replay_production_changed": (
            _summary_optional_bool(
                summary,
                "market_movement_runtime_replay_production_changed",
            )
        ),
        "historical_suite_market_movement_runtime_replay_public_changed": (
            _summary_optional_bool(summary, "market_movement_runtime_replay_public_changed")
        ),
    }


def _budget_stability_audit_checks(
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _budget_stability_audit_present_check(
            budget_stability_audit,
            options=options,
        )
    ]
    if budget_stability_audit is None:
        return checks
    aggregate = _budget_stability_aggregate(budget_stability_audit)
    checks.extend(
        [
            RecommendationBenchmarkQualityGateCheck(
                name="budget_stability_audit_status",
                status=(
                    "passed"
                    if budget_stability_audit.status == "generated"
                    else "failed"
                ),
                actual=budget_stability_audit.status,
                threshold="generated",
                detail="budget stability audit report should be generated",
            ),
            _check_minimum(
                name="budget_stability_slice_count",
                actual=budget_stability_audit.slice_count,
                threshold=options.min_budget_stability_slice_count,
                detail=(
                    "budget stability audit should cover enough historical slices"
                ),
            ),
            _check_minimum(
                name="budget_stability_comparable_count",
                actual=_summary_int(aggregate, "comparable_count"),
                threshold=options.min_budget_stability_comparable_count,
                detail=(
                    "budget stability audit should compare enough slice/budget pairs"
                ),
            ),
            _check_optional_maximum(
                name="budget_stability_signature_change_rate",
                actual=_summary_float(aggregate, "signature_change_rate"),
                threshold=options.max_budget_stability_signature_change_rate,
                detail=(
                    "budget-tier final-answer signature changes should stay "
                    "within the configured rate"
                ),
            ),
            _check_optional_maximum(
                name="budget_stability_harmful_change_count",
                actual=budget_stability_audit.harmful_change_count,
                threshold=options.max_budget_stability_harmful_change_count,
                detail=(
                    "budget-tier harmful final-answer changes should stay within "
                    "the configured limit"
                ),
            ),
            _check_optional_minimum(
                name="budget_stability_hit_delta_count",
                actual=_summary_int(aggregate, "hit_delta_count"),
                threshold=options.min_budget_stability_hit_delta_count,
                detail=(
                    "budget-tier hit delta should not fall below the configured "
                    "minimum"
                ),
            ),
            _check_optional_minimum(
                name="budget_stability_profit_loss_delta",
                actual=_summary_float(aggregate, "profit_loss_delta"),
                threshold=options.min_budget_stability_profit_loss_delta,
                detail=(
                    "budget-tier profit/loss delta should not fall below the "
                    "configured minimum"
                ),
            ),
            _check_optional_minimum(
                name="budget_stability_roi_delta",
                actual=_summary_float(aggregate, "roi_delta"),
                threshold=options.min_budget_stability_roi_delta,
                detail=(
                    "budget-tier ROI delta should not fall below the configured "
                    "minimum"
                ),
            ),
            _check_optional_maximum(
                name="budget_stability_warning_count",
                actual=len(budget_stability_audit.warnings),
                threshold=options.max_budget_stability_warning_count,
                detail=(
                    "budget stability audit warnings should stay within the "
                    "configured limit"
                ),
            ),
        ]
    )
    return checks


def _budget_stability_audit_present_check(
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_budget_stability_audit:
        return _skipped_check(
            name="budget_stability_audit_present",
            actual=budget_stability_audit is not None,
            detail="budget stability audit evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="budget_stability_audit_present",
        status="passed" if budget_stability_audit is not None else "failed",
        actual=budget_stability_audit is not None,
        threshold=True,
        detail=(
            "budget stability audit evidence must be attached before this "
            "benchmark gate can pass"
        ),
    )


def _budget_stability_audit_summary_fields(
    budget_stability_audit: HistoricalBudgetStabilityAuditReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if budget_stability_audit is None:
        return {
            "budget_stability_audit_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "budget_stability_audit_present": False,
            "budget_stability_audit_key": None,
            "budget_stability_audit_status": None,
            "budget_stability_slice_count": 0,
            "budget_stability_budgets": [],
            "budget_stability_reference_budget": None,
            "budget_stability_comparable_count": 0,
            "budget_stability_signature_changed_count": 0,
            "budget_stability_signature_change_rate": None,
            "budget_stability_harmful_change_count": 0,
            "budget_stability_beneficial_change_count": 0,
            "budget_stability_hit_delta_count": 0,
            "budget_stability_profit_loss_delta": None,
            "budget_stability_roi_delta": None,
            "budget_stability_warning_count": 0,
        }
    aggregate = _budget_stability_aggregate(budget_stability_audit)
    return {
        "budget_stability_audit_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "budget_stability_audit_present": True,
        "budget_stability_audit_key": budget_stability_audit.report_key,
        "budget_stability_audit_status": budget_stability_audit.status,
        "budget_stability_slice_count": budget_stability_audit.slice_count,
        "budget_stability_budgets": list(budget_stability_audit.budgets),
        "budget_stability_reference_budget": budget_stability_audit.reference_budget,
        "budget_stability_comparable_count": _summary_int(
            aggregate,
            "comparable_count",
        ),
        "budget_stability_signature_changed_count": _summary_int(
            aggregate,
            "signature_changed_count",
        ),
        "budget_stability_signature_change_rate": _summary_float(
            aggregate,
            "signature_change_rate",
        ),
        "budget_stability_harmful_change_count": (
            budget_stability_audit.harmful_change_count
        ),
        "budget_stability_beneficial_change_count": (
            budget_stability_audit.beneficial_change_count
        ),
        "budget_stability_hit_delta_count": _summary_int(
            aggregate,
            "hit_delta_count",
        ),
        "budget_stability_profit_loss_delta": _summary_float(
            aggregate,
            "profit_loss_delta",
        ),
        "budget_stability_roi_delta": _summary_float(aggregate, "roi_delta"),
        "budget_stability_warning_count": len(budget_stability_audit.warnings),
    }


def _budget_stability_aggregate(
    budget_stability_audit: HistoricalBudgetStabilityAuditReport,
) -> dict[str, object]:
    summaries = budget_stability_audit.comparison_summaries
    if not summaries:
        return {
            "comparable_count": 0,
            "signature_changed_count": 0,
            "signature_change_rate": None,
            "hit_delta_count": 0,
            "profit_loss_delta": None,
            "roi_delta": None,
        }
    signature_rates = [
        summary.signature_change_rate
        for summary in summaries
        if summary.signature_change_rate is not None
    ]
    roi_deltas = [
        summary.roi_delta for summary in summaries if summary.roi_delta is not None
    ]
    return {
        "comparable_count": max(summary.comparable_count for summary in summaries),
        "signature_changed_count": sum(
            summary.signature_changed_count for summary in summaries
        ),
        "signature_change_rate": max(signature_rates) if signature_rates else None,
        "hit_delta_count": min(summary.hit_delta_count for summary in summaries),
        "profit_loss_delta": min(summary.profit_loss_delta for summary in summaries),
        "roi_delta": min(roi_deltas) if roi_deltas else None,
    }


def _final_answer_market_concentration_audit_checks(
    audit: HistoricalFinalAnswerMarketConcentrationAuditReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _final_answer_market_concentration_audit_present_check(
            audit,
            options=options,
        )
    ]
    if audit is None:
        return checks

    checks.extend(
        [
            RecommendationBenchmarkQualityGateCheck(
                name="final_answer_market_concentration_audit_passed",
                status="passed" if audit.passed else "failed",
                actual=audit.passed,
                threshold=True,
                detail="attached final-answer market concentration audit should pass",
            ),
            RecommendationBenchmarkQualityGateCheck(
                name="final_answer_market_concentration_audit_status",
                status="passed" if audit.status == "passed" else "failed",
                actual=audit.status,
                threshold="passed",
                detail=(
                    "attached final-answer market concentration audit status "
                    "should pass"
                ),
            ),
            _check_minimum(
                name="final_answer_market_concentration_slice_count",
                actual=audit.slice_count,
                threshold=options.min_final_answer_market_concentration_slice_count,
                detail=(
                    "final-answer market concentration audit should cover enough "
                    "frozen slices"
                ),
            ),
            _check_minimum(
                name=(
                    "final_answer_market_concentration_"
                    "dynamic_mixed_final_answer_count"
                ),
                actual=audit.dynamic_mixed_final_answer_count,
                threshold=(
                    options.min_final_answer_market_concentration_dynamic_mixed_final_answer_count
                ),
                detail=(
                    "final-answer market concentration audit should observe enough "
                    "dynamic mixed-market final answers"
                ),
            ),
            _check_minimum(
                name=(
                    "final_answer_market_concentration_"
                    "effective_constraint_profile_count"
                ),
                actual=_final_answer_market_concentration_effective_constraint_profile_count(
                    audit
                ),
                threshold=(
                    options.min_final_answer_market_concentration_effective_constraint_profile_count
                ),
                detail=(
                    "final-answer market concentration audit should include enough "
                    "effective constraint-profile runtime evidence"
                ),
            ),
            _check_optional_maximum(
                name="final_answer_market_concentration_failed_check_count",
                actual=_final_answer_market_concentration_failed_check_count(audit),
                threshold=(
                    options.max_final_answer_market_concentration_failed_check_count
                ),
                detail=(
                    "final-answer market concentration audit failed checks should "
                    "stay within the configured limit"
                ),
            ),
            _check_optional_maximum(
                name="final_answer_market_concentration_warning_count",
                actual=len(audit.warnings),
                threshold=options.max_final_answer_market_concentration_warning_count,
                detail=(
                    "final-answer market concentration audit warnings should stay "
                    "within the configured limit"
                ),
            ),
        ]
    )
    return checks


def _final_answer_market_concentration_audit_present_check(
    audit: HistoricalFinalAnswerMarketConcentrationAuditReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_final_answer_market_concentration_audit:
        return _skipped_check(
            name="final_answer_market_concentration_audit_present",
            actual=audit is not None,
            detail="final-answer market concentration audit evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="final_answer_market_concentration_audit_present",
        status="passed" if audit is not None else "failed",
        actual=audit is not None,
        threshold=True,
        detail=(
            "final-answer market concentration audit evidence must be attached "
            "before this benchmark gate can pass"
        ),
    )


def _final_answer_market_concentration_audit_summary_fields(
    audit: HistoricalFinalAnswerMarketConcentrationAuditReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if audit is None:
        return {
            "final_answer_market_concentration_audit_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "final_answer_market_concentration_audit_present": False,
            "final_answer_market_concentration_audit_key": None,
            "final_answer_market_concentration_audit_status": None,
            "final_answer_market_concentration_audit_passed": None,
            "final_answer_market_concentration_slice_count": 0,
            "final_answer_market_concentration_final_answer_count": 0,
            "final_answer_market_concentration_dynamic_mixed_final_answer_count": 0,
            "final_answer_market_concentration_dynamic_mixed_final_answer_rate": None,
            "final_answer_market_concentration_effective_pass_types": [],
            "final_answer_market_concentration_effective_constraint_profiles": [],
            "final_answer_market_concentration_effective_constraint_profile_count": 0,
            (
                "final_answer_market_concentration_"
                "candidate_completed_dynamic_mix_lane_count"
            ): 0,
            (
                "final_answer_market_concentration_"
                "candidate_final_answer_dynamic_mix_lane_count"
            ): 0,
            "final_answer_market_concentration_failed_check_count": 0,
            "final_answer_market_concentration_warning_count": 0,
        }

    summary = audit.summary_json
    effective_constraint_profiles = _summary_list(
        summary,
        "dynamic_mix_final_answer_lane_effective_constraint_profiles",
    )
    return {
        "final_answer_market_concentration_audit_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "final_answer_market_concentration_audit_present": True,
        "final_answer_market_concentration_audit_key": audit.report_key,
        "final_answer_market_concentration_audit_status": audit.status,
        "final_answer_market_concentration_audit_passed": audit.passed,
        "final_answer_market_concentration_slice_count": audit.slice_count,
        "final_answer_market_concentration_final_answer_count": audit.final_answer_count,
        "final_answer_market_concentration_dynamic_mixed_final_answer_count": (
            audit.dynamic_mixed_final_answer_count
        ),
        "final_answer_market_concentration_dynamic_mixed_final_answer_rate": (
            audit.dynamic_mixed_final_answer_rate
        ),
        "final_answer_market_concentration_effective_pass_types": _summary_list(
            summary,
            "dynamic_mix_final_answer_lane_effective_pass_types",
        ),
        "final_answer_market_concentration_effective_constraint_profiles": (
            effective_constraint_profiles
        ),
        "final_answer_market_concentration_effective_constraint_profile_count": len(
            effective_constraint_profiles
        ),
        (
            "final_answer_market_concentration_"
            "candidate_completed_dynamic_mix_lane_count"
        ): _summary_int(
            summary,
            "candidate_completed_dynamic_mix_final_answer_lane_count",
        ),
        (
            "final_answer_market_concentration_"
            "candidate_final_answer_dynamic_mix_lane_count"
        ): _summary_int(
            summary,
            "candidate_final_answer_dynamic_mix_final_answer_lane_count",
        ),
        "final_answer_market_concentration_failed_check_count": (
            _final_answer_market_concentration_failed_check_count(audit)
        ),
        "final_answer_market_concentration_warning_count": len(audit.warnings),
    }


def _final_answer_market_concentration_failed_check_count(
    audit: HistoricalFinalAnswerMarketConcentrationAuditReport,
) -> int:
    summary_failed_check_count = _summary_failed_check_count(audit.summary_json)
    if summary_failed_check_count:
        return summary_failed_check_count
    return len([check for check in audit.checks if check.status == "failed"])


def _final_answer_market_concentration_effective_constraint_profile_count(
    audit: HistoricalFinalAnswerMarketConcentrationAuditReport,
) -> int:
    return len(
        _summary_list(
            audit.summary_json,
            "dynamic_mix_final_answer_lane_effective_constraint_profiles",
        )
    )


def _correct_score_admission_checks(
    admission: HistoricalCorrectScoreAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _correct_score_admission_present_check(
            admission,
            options=options,
        )
    ]
    if admission is None:
        return checks

    checks.extend(
        [
            _required_bool_check(
                name="correct_score_admission_holdout_allowed",
                actual=admission.holdout_allowed,
                required=(
                    options.require_correct_score_admission
                    and options.require_correct_score_admission_holdout_allowed
                ),
                detail=(
                    "correct-score admission should be holdout-allowed before "
                    "periodic evidence can pass"
                ),
            ),
            _required_bool_check(
                name="correct_score_admission_production_allowed",
                actual=admission.production_recommendation_allowed,
                required=(
                    options.require_correct_score_admission
                    and options.require_correct_score_admission_production_allowed
                ),
                detail=(
                    "correct-score admission should be production-allowed only "
                    "when promotion is explicitly required"
                ),
            ),
            _check_minimum(
                name="correct_score_admission_slice_count",
                actual=admission.slice_count,
                threshold=options.min_correct_score_admission_slice_count,
                detail="correct-score admission should cover enough slices",
            ),
            _check_minimum(
                name="correct_score_admission_comparison_count",
                actual=admission.comparison_count,
                threshold=options.min_correct_score_admission_comparison_count,
                detail="correct-score admission should cover enough comparisons",
            ),
            _check_minimum(
                name="correct_score_admission_candidate_final_hit_sample_size",
                actual=admission.candidate_final_hit_sample_size,
                threshold=(
                    options.min_correct_score_admission_candidate_final_hit_sample_size
                ),
                detail="correct-score admission should cover enough final-hit samples",
            ),
            _check_optional_minimum(
                name="correct_score_admission_candidate_final_hit_coverage_ratio",
                actual=admission.candidate_final_hit_coverage_ratio,
                threshold=(
                    options.min_correct_score_admission_candidate_final_hit_coverage_ratio
                ),
                detail="correct-score admission should cover final answers",
            ),
            _check_optional_minimum(
                name="correct_score_admission_candidate_final_hit_rate",
                actual=admission.candidate_final_hit_rate,
                threshold=options.min_correct_score_admission_candidate_final_hit_rate,
                detail="correct-score admission should retain hit-rate quality",
            ),
            _check_optional_minimum(
                name="correct_score_admission_candidate_roi",
                actual=admission.candidate_roi,
                threshold=options.min_correct_score_admission_candidate_roi,
                detail="correct-score admission should retain ROI quality",
            ),
            _check_minimum(
                name=(
                    "correct_score_admission_"
                    "candidate_correct_score_final_answer_count"
                ),
                actual=admission.candidate_correct_score_final_answer_count,
                threshold=(
                    options.min_correct_score_admission_candidate_correct_score_final_answer_count
                ),
                detail=(
                    "correct-score admission should observe enough correct-score "
                    "final answers before promotion"
                ),
            ),
            _check_optional_minimum(
                name=(
                    "correct_score_admission_"
                    "candidate_correct_score_final_answer_rate"
                ),
                actual=admission.candidate_correct_score_final_answer_rate,
                threshold=(
                    options.min_correct_score_admission_candidate_correct_score_final_answer_rate
                ),
                detail="correct-score final-answer rate should meet the configured floor",
            ),
            _check_optional_minimum(
                name="correct_score_admission_final_hit_rate_delta",
                actual=admission.final_hit_rate_delta,
                threshold=options.min_correct_score_admission_final_hit_rate_delta,
                detail="correct-score admission should not reduce final hit rate",
            ),
            _check_optional_minimum(
                name="correct_score_admission_roi_delta",
                actual=admission.roi_delta,
                threshold=options.min_correct_score_admission_roi_delta,
                detail="correct-score admission should not reduce ROI",
            ),
            _check_optional_minimum(
                name="correct_score_admission_profit_loss_delta",
                actual=admission.profit_loss_delta,
                threshold=options.min_correct_score_admission_profit_loss_delta,
                detail="correct-score admission should not reduce profit/loss",
            ),
            _check_optional_maximum(
                name="correct_score_admission_brier_score_delta",
                actual=admission.brier_score_delta,
                threshold=options.max_correct_score_admission_brier_score_delta,
                detail="correct-score admission should not worsen Brier score",
            ),
            _check_optional_maximum(
                name="correct_score_admission_log_loss_delta",
                actual=admission.log_loss_delta,
                threshold=options.max_correct_score_admission_log_loss_delta,
                detail="correct-score admission should not worsen log loss",
            ),
            _check_optional_maximum(
                name="correct_score_admission_mean_calibration_error_delta",
                actual=admission.mean_calibration_error_delta,
                threshold=(
                    options.max_correct_score_admission_mean_calibration_error_delta
                ),
                detail="correct-score admission should not worsen calibration error",
            ),
            _check_optional_maximum(
                name="correct_score_admission_failed_check_count",
                actual=_correct_score_admission_failed_check_count(admission),
                threshold=options.max_correct_score_admission_failed_check_count,
                detail=(
                    "correct-score admission source checks should stay within the "
                    "configured limit"
                ),
            ),
            _check_optional_maximum(
                name="correct_score_admission_warning_count",
                actual=len(admission.warnings),
                threshold=options.max_correct_score_admission_warning_count,
                detail="correct-score admission warnings should stay bounded",
            ),
        ]
    )
    return checks


def _correct_score_admission_present_check(
    admission: HistoricalCorrectScoreAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_correct_score_admission:
        return _skipped_check(
            name="correct_score_admission_present",
            actual=admission is not None,
            detail="correct-score admission evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="correct_score_admission_present",
        status="passed" if admission is not None else "failed",
        actual=admission is not None,
        threshold=True,
        detail=(
            "correct-score admission evidence must be attached before this "
            "benchmark gate can pass"
        ),
    )


def _correct_score_admission_summary_fields(
    admission: HistoricalCorrectScoreAdmissionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if admission is None:
        return {
            "correct_score_admission_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "correct_score_admission_present": False,
            "correct_score_admission_key": None,
            "correct_score_admission_status": None,
            "correct_score_admission_production_allowed": None,
            "correct_score_admission_holdout_allowed": None,
            "correct_score_admission_source_gate_key": None,
            "correct_score_admission_source_gate_status": None,
            "correct_score_admission_source_suite_status": None,
            "correct_score_admission_slice_count": 0,
            "correct_score_admission_comparison_count": 0,
            "correct_score_admission_candidate_final_hit_sample_size": 0,
            "correct_score_admission_candidate_final_hit_coverage_ratio": None,
            "correct_score_admission_candidate_final_hit_rate": None,
            "correct_score_admission_candidate_roi": None,
            "correct_score_admission_candidate_correct_score_final_answer_count": 0,
            "correct_score_admission_candidate_correct_score_final_answer_rate": None,
            "correct_score_admission_final_hit_rate_delta": None,
            "correct_score_admission_roi_delta": None,
            "correct_score_admission_profit_loss_delta": None,
            "correct_score_admission_brier_score_delta": None,
            "correct_score_admission_log_loss_delta": None,
            "correct_score_admission_mean_calibration_error_delta": None,
            "correct_score_admission_production_recommendation_changed": None,
            "correct_score_admission_public_response_changed": None,
            "correct_score_admission_failed_checks": [],
            "correct_score_admission_failed_check_count": 0,
            "correct_score_admission_warning_count": 0,
            "correct_score_admission_warnings": [],
        }

    return {
        "correct_score_admission_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "correct_score_admission_present": True,
        "correct_score_admission_key": admission.report_key,
        "correct_score_admission_status": admission.status,
        "correct_score_admission_production_allowed": (
            admission.production_recommendation_allowed
        ),
        "correct_score_admission_holdout_allowed": admission.holdout_allowed,
        "correct_score_admission_source_gate_key": admission.source_gate_key,
        "correct_score_admission_source_gate_status": admission.source_gate_status,
        "correct_score_admission_source_suite_status": admission.source_suite_status,
        "correct_score_admission_slice_count": admission.slice_count,
        "correct_score_admission_comparison_count": admission.comparison_count,
        "correct_score_admission_candidate_final_hit_sample_size": (
            admission.candidate_final_hit_sample_size
        ),
        "correct_score_admission_candidate_final_hit_coverage_ratio": (
            admission.candidate_final_hit_coverage_ratio
        ),
        "correct_score_admission_candidate_final_hit_rate": (
            admission.candidate_final_hit_rate
        ),
        "correct_score_admission_candidate_roi": admission.candidate_roi,
        "correct_score_admission_candidate_correct_score_final_answer_count": (
            admission.candidate_correct_score_final_answer_count
        ),
        "correct_score_admission_candidate_correct_score_final_answer_rate": (
            admission.candidate_correct_score_final_answer_rate
        ),
        "correct_score_admission_final_hit_rate_delta": (
            admission.final_hit_rate_delta
        ),
        "correct_score_admission_roi_delta": admission.roi_delta,
        "correct_score_admission_profit_loss_delta": admission.profit_loss_delta,
        "correct_score_admission_brier_score_delta": admission.brier_score_delta,
        "correct_score_admission_log_loss_delta": admission.log_loss_delta,
        "correct_score_admission_mean_calibration_error_delta": (
            admission.mean_calibration_error_delta
        ),
        "correct_score_admission_production_recommendation_changed": (
            admission.production_recommendation_changed
        ),
        "correct_score_admission_public_response_changed": (
            admission.public_response_changed
        ),
        "correct_score_admission_failed_checks": [
            check.name for check in admission.checks if check.status == "failed"
        ],
        "correct_score_admission_failed_check_count": (
            _correct_score_admission_failed_check_count(admission)
        ),
        "correct_score_admission_warning_count": len(admission.warnings),
        "correct_score_admission_warnings": admission.warnings,
    }


def _correct_score_admission_failed_check_count(
    admission: HistoricalCorrectScoreAdmissionReport,
) -> int:
    summary_failed_check_count = _summary_failed_check_count(admission.summary_json)
    if summary_failed_check_count:
        return summary_failed_check_count
    return len([check for check in admission.checks if check.status == "failed"])


def _unified_candidate_pool_checks(
    summary: dict[str, object],
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    present_count = _summary_int(summary, "unified_candidate_pool_present_count")
    unique_family_keys = _summary_list(summary, "unified_candidate_pool_unique_family_keys")
    multiple_value_admitted_count = _summary_int(
        summary,
        "unified_candidate_pool_multiple_value_admitted_candidate_count",
    )
    return [
        _required_bool_check(
            name="unified_candidate_pool_present",
            actual=present_count > 0,
            required=options.require_unified_candidate_pool,
            detail=(
                "benchmark should include unified final-answer candidate-pool "
                "evidence when required"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_present_count",
            actual=present_count,
            threshold=options.min_unified_candidate_pool_present_count,
            detail=(
                "benchmark should include enough scenarios with unified "
                "candidate-pool evidence"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_valid_candidate_count",
            actual=_summary_int(summary, "unified_candidate_pool_valid_candidate_count"),
            threshold=options.min_unified_candidate_pool_valid_candidate_count,
            detail=(
                "unified candidate pools should retain enough valid final-answer "
                "options"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_unique_family_count",
            actual=len(unique_family_keys),
            threshold=options.min_unified_candidate_pool_unique_family_count,
            detail=(
                "unified candidate pool should cover enough final-answer families "
                "instead of collapsing onto one play type"
            ),
        ),
        _check_optional_maximum(
            name="unified_candidate_pool_selection_mismatch_count",
            actual=_summary_int(
                summary,
                "unified_candidate_pool_selection_mismatch_count",
            ),
            threshold=options.max_unified_candidate_pool_selection_mismatch_count,
            detail=(
                "selected final-answer families must be present in the unified "
                "candidate pool"
            ),
        ),
        _check_optional_maximum(
            name="unified_candidate_pool_selected_2x1_rate",
            actual=_summary_float(summary, "unified_candidate_pool_selected_2x1_rate"),
            threshold=options.max_unified_candidate_pool_selected_2x1_rate,
            detail=(
                "2x1 should remain one candidate family rather than dominating "
                "the final answer surface"
            ),
        ),
        _required_bool_check(
            name="unified_candidate_pool_multiple_value_admission",
            actual=multiple_value_admitted_count > 0,
            required=options.require_unified_candidate_pool_multiple_value_admission,
            detail=(
                "multiple-choice expansion should provide at least one admitted "
                "marginal-value candidate when admission evidence is required"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_multiple_value_candidate_count",
            actual=_summary_int(
                summary,
                "unified_candidate_pool_multiple_value_candidate_count",
            ),
            threshold=options.min_unified_candidate_pool_multiple_value_candidate_count,
            detail=(
                "benchmark should contain enough multiple-choice candidates for "
                "marginal-value admission evidence"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_multiple_value_admitted_candidate_count",
            actual=multiple_value_admitted_count,
            threshold=(
                options.min_unified_candidate_pool_multiple_value_admitted_candidate_count
            ),
            detail=(
                "multiple-choice candidates should be admitted only when their "
                "extra outcomes add measurable marginal value"
            ),
        ),
        _check_minimum(
            name="unified_candidate_pool_multiple_value_extra_option_count",
            actual=_summary_int(
                summary,
                "unified_candidate_pool_multiple_value_extra_option_count",
            ),
            threshold=options.min_unified_candidate_pool_multiple_value_extra_option_count,
            detail=(
                "multiple-choice admission evidence should cover enough extra "
                "selected outcomes"
            ),
        ),
        _check_optional_maximum(
            name="unified_candidate_pool_multiple_value_rejected_candidate_count",
            actual=_summary_int(
                summary,
                "unified_candidate_pool_multiple_value_rejected_candidate_count",
            ),
            threshold=(
                options.max_unified_candidate_pool_multiple_value_rejected_candidate_count
            ),
            detail=(
                "total rejected multiple-choice candidates must stay within the "
                "configured diagnostic tolerance"
            ),
        ),
        _check_optional_maximum(
            name="unified_candidate_pool_selected_multiple_value_rejected_count",
            actual=_summary_int(
                summary,
                "unified_candidate_pool_selected_multiple_value_rejected_count",
            ),
            threshold=(
                options.max_unified_candidate_pool_selected_multiple_value_rejected_count
            ),
            detail=(
                "the selected final answer must not use a multiple-choice "
                "expansion rejected by marginal-value admission"
            ),
        ),
    ]


def _runtime_profile_switch_gate_checks(
    runtime_profile_switch_gate: HistoricalShortOddsRuntimeProfileSwitchReport | None,
    runtime_profile_switch_replay: HistoricalShortOddsRuntimeShadowReplayReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _runtime_profile_switch_present_check(
            runtime_profile_switch_gate,
            options=options,
        )
    ]
    if runtime_profile_switch_gate is None:
        return checks
    replay_required = (
        options.require_runtime_profile_switch_gate
        and options.require_runtime_profile_switch_replay
    )
    checks.extend(
        [
            _required_bool_check(
                name="runtime_profile_switch_ready",
                actual=runtime_profile_switch_gate.switch_ready,
                required=options.require_runtime_profile_switch_gate,
                detail="attached runtime profile switch gate should be switch-ready",
            ),
            _required_bool_check(
                name="runtime_profile_switch_status_ready",
                actual=runtime_profile_switch_gate.status == "switch_ready",
                required=options.require_runtime_profile_switch_staged_only,
                detail="attached runtime profile switch gate should remain staged-only",
            ),
            _required_bool_check(
                name="runtime_profile_switch_default_profile_not_requested",
                actual=not runtime_profile_switch_gate.default_profile_write_requested,
                required=options.require_runtime_profile_switch_staged_only,
                detail="runtime profile switch evidence should not request default writes",
            ),
            _required_bool_check(
                name="runtime_profile_switch_default_profile_not_written",
                actual=not runtime_profile_switch_gate.default_profile_written,
                required=options.require_runtime_profile_switch_staged_only,
                detail="runtime profile switch evidence should not write the default profile",
            ),
            _check_minimum(
                name="runtime_profile_switch_rule_count",
                actual=runtime_profile_switch_gate.candidate_rule_count,
                threshold=options.min_runtime_profile_switch_rule_count,
                detail="runtime profile switch should include enough short-odds rules",
            ),
            _check_minimum(
                name="runtime_profile_switch_allowed_competition_count",
                actual=len(runtime_profile_switch_gate.allowed_competition_ids),
                threshold=options.min_runtime_profile_switch_allowed_competition_count,
                detail="runtime profile switch should cover enough competitions",
            ),
            _runtime_profile_switch_replay_present_check(
                runtime_profile_switch_replay,
                required=replay_required,
            ),
        ]
    )
    if runtime_profile_switch_replay is None:
        return checks
    checks.extend(
        [
            _required_bool_check(
                name="runtime_profile_switch_replay_passed",
                actual=runtime_profile_switch_replay.passed,
                required=replay_required,
                detail="runtime profile switch staged replay should pass",
            ),
            _required_bool_check(
                name="runtime_profile_switch_replay_status_passed",
                actual=runtime_profile_switch_replay.status == "shadow_replay_passed",
                required=replay_required,
                detail="runtime profile switch staged replay status should be passed",
            ),
            _required_bool_check(
                name="runtime_profile_switch_replay_profile_matches",
                actual=(
                    runtime_profile_switch_replay.source_rule_profile_version
                    == runtime_profile_switch_gate.activated_profile_version
                ),
                required=True,
                detail="runtime profile switch replay should use the staged profile",
            ),
            _check_minimum(
                name="runtime_profile_switch_replay_final_answer_count",
                actual=runtime_profile_switch_replay.final_answer_count,
                threshold=options.min_runtime_profile_switch_final_answer_count,
                detail="runtime profile switch replay should cover enough final answers",
            ),
            _check_minimum(
                name="runtime_profile_switch_replay_changed_final_answer_count",
                actual=runtime_profile_switch_replay.changed_final_answer_count,
                threshold=(
                    options.min_runtime_profile_switch_changed_final_answer_count
                ),
                detail="runtime profile switch replay should affect enough final answers",
            ),
            _check_optional_minimum(
                name="runtime_profile_switch_replay_final_answer_hit_rate_delta",
                actual=runtime_profile_switch_replay.final_answer_hit_rate_delta,
                threshold=(
                    options.min_runtime_profile_switch_final_answer_hit_rate_delta
                ),
                detail="runtime profile switch replay hit rate should not regress",
            ),
            _check_optional_minimum(
                name="runtime_profile_switch_replay_roi_delta",
                actual=runtime_profile_switch_replay.roi_delta,
                threshold=options.min_runtime_profile_switch_roi_delta,
                detail="runtime profile switch replay ROI should not regress",
            ),
            _check_optional_minimum(
                name="runtime_profile_switch_replay_profit_loss_delta",
                actual=runtime_profile_switch_replay.profit_loss_delta,
                threshold=options.min_runtime_profile_switch_profit_loss_delta,
                detail="runtime profile switch replay profit/loss should not regress",
            ),
            _check_optional_maximum(
                name="runtime_profile_switch_replay_harm_count_vs_original",
                actual=runtime_profile_switch_replay.harm_count_vs_original,
                threshold=options.max_runtime_profile_switch_harm_count_vs_original,
                detail=(
                    "runtime profile switch replay should pass compatibility "
                    "no-harm"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "runtime_profile_switch_replay_final_hit_harm_count_vs_original"
                ),
                actual=(
                    runtime_profile_switch_replay.final_hit_harm_count_vs_original
                ),
                threshold=(
                    options.max_runtime_profile_switch_final_hit_harm_count_vs_original
                ),
                detail=(
                    "runtime profile switch replay should not turn original hits "
                    "into misses"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "runtime_profile_switch_replay_profit_loss_harm_count_vs_original"
                ),
                actual=(
                    runtime_profile_switch_replay.profit_loss_harm_count_vs_original
                ),
                threshold=(
                    options.max_runtime_profile_switch_profit_loss_harm_count_vs_original
                ),
                detail=(
                    "runtime profile switch replay should not reduce original "
                    "final-answer profit/loss"
                ),
            ),
            _check_optional_minimum(
                name="runtime_profile_switch_replay_average_hit_probability_delta",
                actual=(
                    runtime_profile_switch_replay.average_hit_probability_delta_vs_original
                ),
                threshold=(
                    options.min_runtime_profile_switch_average_hit_probability_delta
                ),
                detail=(
                    "runtime profile switch replay hit-probability loss should stay "
                    "inside tolerance"
                ),
            ),
            _required_bool_check(
                name="runtime_profile_switch_replay_public_response_unchanged",
                actual=not runtime_profile_switch_replay.public_response_changed,
                required=options.require_runtime_profile_switch_gate,
                detail="runtime profile switch replay should not change public responses",
            ),
            _required_bool_check(
                name="runtime_profile_switch_replay_production_unchanged",
                actual=not runtime_profile_switch_replay.production_recommendation_changed,
                required=options.require_runtime_profile_switch_gate,
                detail=(
                    "runtime profile switch replay should not change production "
                    "recommendations"
                ),
            ),
        ]
    )
    return checks


def _runtime_profile_switch_present_check(
    runtime_profile_switch_gate: HistoricalShortOddsRuntimeProfileSwitchReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_runtime_profile_switch_gate:
        return _skipped_check(
            name="runtime_profile_switch_gate_present",
            actual=runtime_profile_switch_gate is not None,
            detail="runtime profile switch evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="runtime_profile_switch_gate_present",
        status="passed" if runtime_profile_switch_gate is not None else "failed",
        actual=runtime_profile_switch_gate is not None,
        threshold=True,
        detail=(
            "runtime profile switch evidence must be attached before this benchmark "
            "gate can pass"
        ),
    )


def _runtime_profile_switch_replay_present_check(
    runtime_profile_switch_replay: HistoricalShortOddsRuntimeShadowReplayReport | None,
    *,
    required: bool,
) -> RecommendationBenchmarkQualityGateCheck:
    if not required:
        return _skipped_check(
            name="runtime_profile_switch_replay_present",
            actual=runtime_profile_switch_replay is not None,
            detail="runtime profile switch replay evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="runtime_profile_switch_replay_present",
        status="passed" if runtime_profile_switch_replay is not None else "failed",
        actual=runtime_profile_switch_replay is not None,
        threshold=True,
        detail="runtime profile switch staged replay evidence must be attached",
    )


def _runtime_profile_switch_summary_fields(
    runtime_profile_switch_gate: HistoricalShortOddsRuntimeProfileSwitchReport | None,
    runtime_profile_switch_replay: HistoricalShortOddsRuntimeShadowReplayReport | None,
    *,
    switch_report_path: Path | None,
    replay_report_path: Path | None,
) -> dict[str, object]:
    if runtime_profile_switch_gate is None:
        switch_fields: dict[str, object] = {
            "runtime_profile_switch_report_path": (
                str(switch_report_path) if switch_report_path is not None else None
            ),
            "runtime_profile_switch_gate_present": False,
            "runtime_profile_switch_key": None,
            "runtime_profile_switch_status": None,
            "runtime_profile_switch_ready": None,
            "runtime_profile_switch_activated_profile_version": None,
            "runtime_profile_switch_rule_count": 0,
            "runtime_profile_switch_allowed_competition_count": 0,
            "runtime_profile_switch_default_profile_write_requested": None,
            "runtime_profile_switch_default_profile_written": None,
        }
    else:
        switch_fields = {
            "runtime_profile_switch_report_path": (
                str(switch_report_path) if switch_report_path is not None else None
            ),
            "runtime_profile_switch_gate_present": True,
            "runtime_profile_switch_key": runtime_profile_switch_gate.report_key,
            "runtime_profile_switch_status": runtime_profile_switch_gate.status,
            "runtime_profile_switch_ready": runtime_profile_switch_gate.switch_ready,
            "runtime_profile_switch_activated_profile_version": (
                runtime_profile_switch_gate.activated_profile_version
            ),
            "runtime_profile_switch_rule_count": (
                runtime_profile_switch_gate.candidate_rule_count
            ),
            "runtime_profile_switch_allowed_competition_count": len(
                runtime_profile_switch_gate.allowed_competition_ids
            ),
            "runtime_profile_switch_default_profile_write_requested": (
                runtime_profile_switch_gate.default_profile_write_requested
            ),
            "runtime_profile_switch_default_profile_written": (
                runtime_profile_switch_gate.default_profile_written
            ),
        }
    if runtime_profile_switch_replay is None:
        return {
            **switch_fields,
            "runtime_profile_switch_replay_report_path": (
                str(replay_report_path) if replay_report_path is not None else None
            ),
            "runtime_profile_switch_replay_present": False,
            "runtime_profile_switch_replay_key": None,
            "runtime_profile_switch_replay_status": None,
            "runtime_profile_switch_replay_passed": None,
            "runtime_profile_switch_replay_final_answer_count": 0,
            "runtime_profile_switch_replay_changed_final_answer_count": 0,
            "runtime_profile_switch_replay_final_answer_hit_rate_delta": None,
            "runtime_profile_switch_replay_roi_delta": None,
            "runtime_profile_switch_replay_profit_loss_delta": None,
            "runtime_profile_switch_replay_harm_count_vs_original": 0,
            "runtime_profile_switch_replay_final_hit_harm_count_vs_original": 0,
            "runtime_profile_switch_replay_profit_loss_harm_count_vs_original": 0,
            "runtime_profile_switch_replay_average_hit_probability_delta": None,
            "runtime_profile_switch_replay_public_response_changed": None,
            "runtime_profile_switch_replay_production_recommendation_changed": None,
        }
    return {
        **switch_fields,
        "runtime_profile_switch_replay_report_path": (
            str(replay_report_path) if replay_report_path is not None else None
        ),
        "runtime_profile_switch_replay_present": True,
        "runtime_profile_switch_replay_key": runtime_profile_switch_replay.report_key,
        "runtime_profile_switch_replay_status": runtime_profile_switch_replay.status,
        "runtime_profile_switch_replay_passed": runtime_profile_switch_replay.passed,
        "runtime_profile_switch_replay_final_answer_count": (
            runtime_profile_switch_replay.final_answer_count
        ),
        "runtime_profile_switch_replay_changed_final_answer_count": (
            runtime_profile_switch_replay.changed_final_answer_count
        ),
        "runtime_profile_switch_replay_final_answer_hit_rate_delta": (
            runtime_profile_switch_replay.final_answer_hit_rate_delta
        ),
        "runtime_profile_switch_replay_roi_delta": runtime_profile_switch_replay.roi_delta,
        "runtime_profile_switch_replay_profit_loss_delta": (
            runtime_profile_switch_replay.profit_loss_delta
        ),
        "runtime_profile_switch_replay_harm_count_vs_original": (
            runtime_profile_switch_replay.harm_count_vs_original
        ),
        "runtime_profile_switch_replay_final_hit_harm_count_vs_original": (
            runtime_profile_switch_replay.final_hit_harm_count_vs_original
        ),
        "runtime_profile_switch_replay_profit_loss_harm_count_vs_original": (
            runtime_profile_switch_replay.profit_loss_harm_count_vs_original
        ),
        "runtime_profile_switch_replay_average_hit_probability_delta": (
            runtime_profile_switch_replay.average_hit_probability_delta_vs_original
        ),
        "runtime_profile_switch_replay_public_response_changed": (
            runtime_profile_switch_replay.public_response_changed
        ),
        "runtime_profile_switch_replay_production_recommendation_changed": (
            runtime_profile_switch_replay.production_recommendation_changed
        ),
    }


def _final_answer_segment_penalty_runtime_replay_checks(
    replay: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _final_answer_segment_penalty_runtime_replay_present_check(
            replay,
            options=options,
        )
    ]
    if replay is None:
        return checks
    checks.extend(
        [
            _required_bool_check(
                name="final_answer_segment_penalty_runtime_replay_holdout_allowed",
                actual=replay.holdout_replay_allowed,
                required=(
                    options.require_final_answer_segment_penalty_runtime_replay
                    and options.require_final_answer_segment_penalty_runtime_replay_holdout_allowed
                ),
                detail="segment penalty runtime replay should be holdout-allowed",
            ),
            _required_bool_check(
                name="final_answer_segment_penalty_runtime_replay_runtime_allowed",
                actual=replay.runtime_replay_allowed,
                required=(
                    options.require_final_answer_segment_penalty_runtime_replay
                    and options.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
                ),
                detail="segment penalty runtime replay should be runtime-allowed",
            ),
            _check_minimum(
                name="final_answer_segment_penalty_runtime_replay_rule_count",
                actual=replay.rule_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_rule_count
                ),
                detail="segment penalty runtime replay should load enough rules",
            ),
            _check_minimum(
                name="final_answer_segment_penalty_runtime_replay_selected_rule_count",
                actual=replay.selected_rule_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_selected_rule_count
                ),
                detail="segment penalty runtime replay should select enough rules",
            ),
            _check_optional_maximum(
                name="final_answer_segment_penalty_runtime_replay_selected_rule_count_max",
                actual=replay.selected_rule_count,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_selected_rule_count
                ),
                detail="segment penalty runtime replay should stay within rule limits",
            ),
            _check_minimum(
                name="final_answer_segment_penalty_runtime_replay_final_answer_count",
                actual=replay.final_answer_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_final_answer_count
                ),
                detail="segment penalty runtime replay should cover enough final answers",
            ),
            _check_minimum(
                name=(
                    "final_answer_segment_penalty_runtime_replay_changed_final_answer_count"
                ),
                actual=replay.changed_final_answer_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
                ),
                detail="segment penalty runtime replay should affect enough answers",
            ),
            _check_minimum(
                name="final_answer_segment_penalty_runtime_replay_penalty_option_count",
                actual=replay.penalty_option_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
                ),
                detail="segment penalty runtime replay should exercise penalty options",
            ),
            _check_minimum(
                name="final_answer_segment_penalty_runtime_replay_hit_count_delta",
                actual=replay.final_answer_hit_delta_count,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_hit_count_delta
                ),
                detail="segment penalty runtime replay hit count should not regress",
            ),
            _check_optional_minimum(
                name="final_answer_segment_penalty_runtime_replay_hit_rate_delta",
                actual=replay.final_answer_hit_rate_delta,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_hit_rate_delta
                ),
                detail="segment penalty runtime replay hit rate should not regress",
            ),
            _check_optional_minimum(
                name="final_answer_segment_penalty_runtime_replay_roi_delta",
                actual=replay.roi_delta,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_roi_delta
                ),
                detail="segment penalty runtime replay ROI should not regress",
            ),
            _check_optional_minimum(
                name="final_answer_segment_penalty_runtime_replay_profit_loss_delta",
                actual=replay.profit_loss_delta,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_profit_loss_delta
                ),
                detail="segment penalty runtime replay profit/loss should not regress",
            ),
            _check_optional_minimum(
                name="final_answer_segment_penalty_runtime_replay_candidate_roi",
                actual=replay.candidate_roi,
                threshold=(
                    options.min_final_answer_segment_penalty_runtime_replay_candidate_roi
                ),
                detail="segment penalty runtime replay absolute ROI should meet floor",
            ),
            _check_optional_maximum(
                name="final_answer_segment_penalty_runtime_replay_brier_score_delta",
                actual=replay.brier_score_delta,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_brier_score_delta
                ),
                detail="segment penalty runtime replay Brier score should not regress",
            ),
            _check_optional_maximum(
                name="final_answer_segment_penalty_runtime_replay_log_loss_delta",
                actual=replay.log_loss_delta,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_log_loss_delta
                ),
                detail="segment penalty runtime replay log loss should not regress",
            ),
            _check_optional_maximum(
                name=(
                    "final_answer_segment_penalty_runtime_replay_calibration_error_delta"
                ),
                actual=replay.mean_calibration_error_delta,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_calibration_error_delta
                ),
                detail="segment penalty runtime replay calibration should not regress",
            ),
            _check_optional_maximum(
                name="final_answer_segment_penalty_runtime_replay_harm_count",
                actual=replay.harm_count_vs_baseline,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
                ),
                detail="segment penalty runtime replay should not harm final answers",
            ),
            _check_optional_maximum(
                name=(
                    "final_answer_segment_penalty_runtime_replay_final_hit_harm_count"
                ),
                actual=replay.final_hit_harm_count_vs_baseline,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
                ),
                detail=(
                    "segment penalty runtime replay should not reduce original "
                    "final-answer hit counts"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count"
                ),
                actual=replay.profit_loss_harm_count_vs_baseline,
                threshold=(
                    options.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
                ),
                detail=(
                    "segment penalty runtime replay should not reduce original "
                    "final-answer profit/loss"
                ),
            ),
            _required_bool_check(
                name=(
                    "final_answer_segment_penalty_runtime_replay_production_unchanged"
                ),
                actual=not replay.production_recommendation_changed,
                required=_segment_penalty_runtime_replay_required(
                    options,
                    options.require_final_answer_segment_penalty_runtime_replay_no_production_change,
                ),
                detail="segment penalty runtime replay should not change production",
            ),
            _required_bool_check(
                name="final_answer_segment_penalty_runtime_replay_public_unchanged",
                actual=not replay.public_response_changed,
                required=_segment_penalty_runtime_replay_required(
                    options,
                    options.require_final_answer_segment_penalty_runtime_replay_no_public_response_change,
                ),
                detail="segment penalty runtime replay should not change public output",
            ),
        ]
    )
    return checks


def _segment_penalty_runtime_replay_required(
    options: RecommendationBenchmarkQualityGateOptions,
    enabled: bool,
) -> bool:
    return options.require_final_answer_segment_penalty_runtime_replay and enabled


def _final_answer_segment_penalty_runtime_replay_present_check(
    replay: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_final_answer_segment_penalty_runtime_replay:
        return _skipped_check(
            name="final_answer_segment_penalty_runtime_replay_present",
            actual=replay is not None,
            detail="segment penalty runtime replay evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="final_answer_segment_penalty_runtime_replay_present",
        status="passed" if replay is not None else "failed",
        actual=replay is not None,
        threshold=True,
        detail="segment penalty runtime replay evidence must be attached",
    )


def _final_answer_segment_penalty_runtime_replay_summary_fields(
    replay: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if replay is None:
        return {
            "final_answer_segment_penalty_runtime_replay_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "final_answer_segment_penalty_runtime_replay_present": False,
            "final_answer_segment_penalty_runtime_replay_key": None,
            "final_answer_segment_penalty_runtime_replay_status": None,
            "final_answer_segment_penalty_runtime_replay_runtime_allowed": None,
            "final_answer_segment_penalty_runtime_replay_holdout_allowed": None,
            "final_answer_segment_penalty_runtime_replay_profile_version": None,
            "final_answer_segment_penalty_runtime_replay_rule_count": 0,
            "final_answer_segment_penalty_runtime_replay_selected_rule_count": 0,
            "final_answer_segment_penalty_runtime_replay_final_answer_count": 0,
            "final_answer_segment_penalty_runtime_replay_changed_final_answer_count": 0,
            "final_answer_segment_penalty_runtime_replay_penalty_option_count": 0,
            "final_answer_segment_penalty_runtime_replay_hit_count_delta": 0,
            "final_answer_segment_penalty_runtime_replay_hit_rate_delta": None,
            "final_answer_segment_penalty_runtime_replay_candidate_roi": None,
            "final_answer_segment_penalty_runtime_replay_roi_delta": None,
            "final_answer_segment_penalty_runtime_replay_profit_loss_delta": None,
            "final_answer_segment_penalty_runtime_replay_harm_count": 0,
            "final_answer_segment_penalty_runtime_replay_final_hit_harm_count": 0,
            "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count": 0,
            "final_answer_segment_penalty_runtime_replay_failed_checks": [],
            "final_answer_segment_penalty_runtime_replay_production_changed": None,
            "final_answer_segment_penalty_runtime_replay_public_changed": None,
        }
    return {
        "final_answer_segment_penalty_runtime_replay_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "final_answer_segment_penalty_runtime_replay_present": True,
        "final_answer_segment_penalty_runtime_replay_key": replay.report_key,
        "final_answer_segment_penalty_runtime_replay_status": replay.status,
        "final_answer_segment_penalty_runtime_replay_runtime_allowed": (
            replay.runtime_replay_allowed
        ),
        "final_answer_segment_penalty_runtime_replay_holdout_allowed": (
            replay.holdout_replay_allowed
        ),
        "final_answer_segment_penalty_runtime_replay_profile_version": (
            replay.source_rule_profile_version
        ),
        "final_answer_segment_penalty_runtime_replay_rule_count": replay.rule_count,
        "final_answer_segment_penalty_runtime_replay_selected_rule_count": (
            replay.selected_rule_count
        ),
        "final_answer_segment_penalty_runtime_replay_final_answer_count": (
            replay.final_answer_count
        ),
        "final_answer_segment_penalty_runtime_replay_changed_final_answer_count": (
            replay.changed_final_answer_count
        ),
        "final_answer_segment_penalty_runtime_replay_penalty_option_count": (
            replay.penalty_option_count
        ),
        "final_answer_segment_penalty_runtime_replay_hit_count_delta": (
            replay.final_answer_hit_delta_count
        ),
        "final_answer_segment_penalty_runtime_replay_hit_rate_delta": (
            replay.final_answer_hit_rate_delta
        ),
        "final_answer_segment_penalty_runtime_replay_candidate_roi": (
            replay.candidate_roi
        ),
        "final_answer_segment_penalty_runtime_replay_roi_delta": replay.roi_delta,
        "final_answer_segment_penalty_runtime_replay_profit_loss_delta": (
            replay.profit_loss_delta
        ),
        "final_answer_segment_penalty_runtime_replay_harm_count": (
            replay.harm_count_vs_baseline
        ),
        "final_answer_segment_penalty_runtime_replay_final_hit_harm_count": (
            replay.final_hit_harm_count_vs_baseline
        ),
        "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count": (
            replay.profit_loss_harm_count_vs_baseline
        ),
        "final_answer_segment_penalty_runtime_replay_failed_checks": [
            check.name for check in replay.checks if check.status == "failed"
        ],
        "final_answer_segment_penalty_runtime_replay_production_changed": (
            replay.production_recommendation_changed
        ),
        "final_answer_segment_penalty_runtime_replay_public_changed": (
            replay.public_response_changed
        ),
    }


def _market_movement_runtime_activation_checks(
    activation: HistoricalMarketMovementRiskFilterRuntimeActivationReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _market_movement_runtime_activation_present_check(
            activation,
            options=options,
        )
    ]
    if activation is None:
        return checks
    required = (
        options.require_market_movement_runtime_activation
        or activation.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="market_movement_runtime_activation_ready",
                actual=activation.staged_activation_ready,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_ready
                ),
                detail="market-movement runtime activation should be staged-ready",
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_status_ready",
                actual=activation.status == "staged_activation_ready",
                required=(
                    required
                    and options.require_market_movement_runtime_activation_ready
                ),
                detail=(
                    "market-movement runtime activation status should be "
                    "staged-ready"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_no_blockers",
                actual=not activation.blockers,
                required=required,
                detail="market-movement runtime activation should have no blockers",
            ),
            _check_minimum(
                name="market_movement_runtime_activation_rule_count",
                actual=activation.rule_count,
                threshold=(
                    options.min_market_movement_runtime_activation_rule_count
                    if required
                    else 0
                ),
                detail="market-movement runtime activation should load enough rules",
            ),
            _check_minimum(
                name="market_movement_runtime_activation_selected_rule_count",
                actual=activation.selected_rule_count,
                threshold=(
                    options.min_market_movement_runtime_activation_selected_rule_count
                    if required
                    else 0
                ),
                detail="market-movement runtime activation should select enough rules",
            ),
            _check_optional_maximum(
                name="market_movement_runtime_activation_selected_rule_count_max",
                actual=activation.selected_rule_count,
                threshold=(
                    options.max_market_movement_runtime_activation_selected_rule_count
                    if required
                    else None
                ),
                detail=(
                    "market-movement runtime activation should stay within the "
                    "selected-rule limit"
                ),
            ),
            _check_minimum(
                name="market_movement_runtime_activation_adjusted_fixture_count",
                actual=activation.adjusted_fixture_count,
                threshold=(
                    options.min_market_movement_runtime_activation_adjusted_fixture_count
                    if required
                    else 0
                ),
                detail=(
                    "market-movement runtime activation should cover adjusted fixtures"
                ),
            ),
            _check_minimum(
                name="market_movement_runtime_activation_adjusted_prediction_count",
                actual=activation.adjusted_prediction_count,
                threshold=(
                    options.min_market_movement_runtime_activation_adjusted_prediction_count
                    if required
                    else 0
                ),
                detail=(
                    "market-movement runtime activation should cover adjusted "
                    "predictions"
                ),
            ),
            _check_optional_minimum(
                name="market_movement_runtime_activation_final_hit_rate_delta",
                actual=activation.final_hit_rate_delta,
                threshold=(
                    options.min_market_movement_runtime_activation_final_hit_rate_delta
                    if required
                    else None
                ),
                detail=(
                    "market-movement runtime activation final hit rate should not "
                    "regress"
                ),
            ),
            _check_optional_minimum(
                name="market_movement_runtime_activation_roi_delta",
                actual=activation.roi_delta,
                threshold=(
                    options.min_market_movement_runtime_activation_roi_delta
                    if required
                    else None
                ),
                detail="market-movement runtime activation ROI should not regress",
            ),
            _check_optional_minimum(
                name="market_movement_runtime_activation_profit_loss_delta",
                actual=activation.profit_loss_delta,
                threshold=(
                    options.min_market_movement_runtime_activation_profit_loss_delta
                    if required
                    else None
                ),
                detail=(
                    "market-movement runtime activation profit/loss should not "
                    "regress"
                ),
            ),
            _check_optional_maximum(
                name="market_movement_runtime_activation_brier_score_delta",
                actual=activation.brier_score_delta,
                threshold=(
                    options.max_market_movement_runtime_activation_brier_score_delta
                    if required
                    else None
                ),
                detail=(
                    "market-movement runtime activation Brier score should not regress"
                ),
            ),
            _check_optional_maximum(
                name="market_movement_runtime_activation_log_loss_delta",
                actual=activation.log_loss_delta,
                threshold=(
                    options.max_market_movement_runtime_activation_log_loss_delta
                    if required
                    else None
                ),
                detail="market-movement runtime activation log loss should not regress",
            ),
            _check_optional_maximum(
                name="market_movement_runtime_activation_calibration_delta",
                actual=activation.mean_calibration_error_delta,
                threshold=(
                    options.max_market_movement_runtime_activation_mean_calibration_error_delta
                    if required
                    else None
                ),
                detail=(
                    "market-movement runtime activation calibration should not regress"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_default_profile_not_written",
                actual=not activation.default_profile_written,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_no_default_profile_write
                ),
                detail=(
                    "market-movement runtime activation should not write the "
                    "default profile"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_default_path_unchanged",
                actual=not activation.default_recommendation_path_changed,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_no_default_path_change
                ),
                detail=(
                    "market-movement runtime activation should not change the "
                    "default recommendation path"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_production_unchanged",
                actual=not activation.production_recommendation_changed,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_no_production_change
                ),
                detail=(
                    "market-movement runtime activation should not change production"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_activation_public_unchanged",
                actual=not activation.public_response_changed,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_no_public_response_change
                ),
                detail=(
                    "market-movement runtime activation should not change public output"
                ),
            ),
        ]
    )
    return checks


def _market_movement_runtime_activation_present_check(
    activation: HistoricalMarketMovementRiskFilterRuntimeActivationReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_market_movement_runtime_activation:
        return _skipped_check(
            name="market_movement_runtime_activation_present",
            actual=activation is not None,
            detail="market-movement runtime activation evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="market_movement_runtime_activation_present",
        status="passed" if activation is not None else "failed",
        actual=activation is not None,
        threshold=True,
        detail="market-movement runtime activation evidence must be attached",
    )


def _market_movement_runtime_activation_summary_fields(
    activation: HistoricalMarketMovementRiskFilterRuntimeActivationReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if activation is None:
        return {
            "market_movement_runtime_activation_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "market_movement_runtime_activation_present": False,
            "market_movement_runtime_activation_key": None,
            "market_movement_runtime_activation_status": None,
            "market_movement_runtime_activation_ready": None,
            "market_movement_runtime_activation_staged_profile_version": None,
            "market_movement_runtime_activation_source_suite_gate_key": None,
            "market_movement_runtime_activation_source_runtime_replay_report_key": (
                None
            ),
            "market_movement_runtime_activation_source_runtime_profile_version": (
                None
            ),
            "market_movement_runtime_activation_rule_count": 0,
            "market_movement_runtime_activation_selected_rule_count": 0,
            "market_movement_runtime_activation_selected_rule_ids": [],
            "market_movement_runtime_activation_selected_segment_group_keys": [],
            "market_movement_runtime_activation_adjusted_fixture_count": 0,
            "market_movement_runtime_activation_adjusted_prediction_count": 0,
            "market_movement_runtime_activation_final_hit_rate_delta": None,
            "market_movement_runtime_activation_roi_delta": None,
            "market_movement_runtime_activation_profit_loss_delta": None,
            "market_movement_runtime_activation_brier_score_delta": None,
            "market_movement_runtime_activation_log_loss_delta": None,
            "market_movement_runtime_activation_calibration_delta": None,
            "market_movement_runtime_activation_default_profile_written": None,
            "market_movement_runtime_activation_default_path_changed": None,
            "market_movement_runtime_activation_production_changed": None,
            "market_movement_runtime_activation_public_changed": None,
            "market_movement_runtime_activation_blockers": [],
            "market_movement_runtime_activation_failed_checks": [],
        }
    return {
        "market_movement_runtime_activation_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "market_movement_runtime_activation_present": True,
        "market_movement_runtime_activation_key": activation.report_key,
        "market_movement_runtime_activation_status": activation.status,
        "market_movement_runtime_activation_ready": (
            activation.staged_activation_ready
        ),
        "market_movement_runtime_activation_staged_profile_version": (
            activation.staged_profile_version
        ),
        "market_movement_runtime_activation_source_suite_gate_key": (
            activation.source_suite_gate_key
        ),
        "market_movement_runtime_activation_source_runtime_replay_report_key": (
            activation.source_runtime_replay_report_key
        ),
        "market_movement_runtime_activation_source_runtime_profile_version": (
            activation.source_runtime_profile_version
        ),
        "market_movement_runtime_activation_rule_count": activation.rule_count,
        "market_movement_runtime_activation_selected_rule_count": (
            activation.selected_rule_count
        ),
        "market_movement_runtime_activation_selected_rule_ids": (
            activation.selected_rule_ids
        ),
        "market_movement_runtime_activation_selected_segment_group_keys": (
            activation.selected_segment_group_keys
        ),
        "market_movement_runtime_activation_adjusted_fixture_count": (
            activation.adjusted_fixture_count
        ),
        "market_movement_runtime_activation_adjusted_prediction_count": (
            activation.adjusted_prediction_count
        ),
        "market_movement_runtime_activation_final_hit_rate_delta": (
            activation.final_hit_rate_delta
        ),
        "market_movement_runtime_activation_roi_delta": activation.roi_delta,
        "market_movement_runtime_activation_profit_loss_delta": (
            activation.profit_loss_delta
        ),
        "market_movement_runtime_activation_brier_score_delta": (
            activation.brier_score_delta
        ),
        "market_movement_runtime_activation_log_loss_delta": (
            activation.log_loss_delta
        ),
        "market_movement_runtime_activation_calibration_delta": (
            activation.mean_calibration_error_delta
        ),
        "market_movement_runtime_activation_default_profile_written": (
            activation.default_profile_written
        ),
        "market_movement_runtime_activation_default_path_changed": (
            activation.default_recommendation_path_changed
        ),
        "market_movement_runtime_activation_production_changed": (
            activation.production_recommendation_changed
        ),
        "market_movement_runtime_activation_public_changed": (
            activation.public_response_changed
        ),
        "market_movement_runtime_activation_blockers": activation.blockers,
        "market_movement_runtime_activation_failed_checks": [
            check.name for check in activation.checks if check.status == "failed"
        ],
    }


def _market_movement_runtime_activation_sample_expansion_checks(
    expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _market_movement_runtime_activation_sample_expansion_present_check(
            expansion,
            options=options,
        )
    ]
    if expansion is None:
        return checks
    required = (
        options.require_market_movement_runtime_activation_sample_expansion
        or expansion.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="market_movement_activation_sample_expansion_passed",
                actual=expansion.passed,
                required=required,
                detail="market-movement activation sample expansion should pass",
            ),
            _required_bool_check(
                name="market_movement_activation_sample_expansion_not_blocked",
                actual=expansion.status != "blocked",
                required=required,
                detail="sample expansion evidence should not be blocked",
            ),
            _required_bool_check(
                name="market_movement_activation_sample_expansion_promotion_ready",
                actual=expansion.promotion_ready,
                required=(
                    options.require_market_movement_runtime_activation_sample_expansion_promotion_ready
                ),
                detail=(
                    "sample expansion should be promotion-ready when explicitly "
                    "required"
                ),
            ),
        ]
    )
    return checks


def _market_movement_runtime_activation_sample_expansion_present_check(
    expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_market_movement_runtime_activation_sample_expansion:
        return _skipped_check(
            name="market_movement_activation_sample_expansion_present",
            actual=expansion is not None,
            detail=(
                "market-movement activation sample expansion evidence is optional"
            ),
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="market_movement_activation_sample_expansion_present",
        status="passed" if expansion is not None else "failed",
        actual=expansion is not None,
        threshold=True,
        detail=(
            "market-movement activation sample expansion evidence must be attached"
        ),
    )


def _market_movement_runtime_activation_sample_expansion_summary_fields(
    expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if expansion is None:
        return {
            "market_movement_activation_sample_expansion_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "market_movement_activation_sample_expansion_present": False,
            "market_movement_activation_sample_expansion_key": None,
            "market_movement_activation_sample_expansion_status": None,
            "market_movement_activation_sample_expansion_passed": None,
            "market_movement_activation_sample_expansion_promotion_ready": None,
            "market_movement_activation_sample_expansion_ready_fixture_count": 0,
            "market_movement_activation_sample_expansion_supplemental_fixture_count": 0,
            "market_movement_activation_sample_expansion_combined_fixture_count": 0,
            "market_movement_activation_sample_expansion_combined_competition_count": 0,
            "market_movement_activation_sample_expansion_adjusted_fixture_count": 0,
            "market_movement_activation_sample_expansion_adjusted_ratio": None,
            "market_movement_activation_sample_expansion_segment_replay_batch_gate_count": 0,
            "market_movement_activation_sample_expansion_segment_replay_batch_ready_count": 0,
            (
                "market_movement_activation_sample_expansion_"
                "segment_replay_batch_adjusted_fixture_count"
            ): 0,
            "market_movement_activation_sample_expansion_effective_segment_count": 0,
            "market_movement_activation_sample_expansion_effective_adjusted_fixture_count": 0,
            "market_movement_activation_sample_expansion_effective_adjusted_ratio": None,
            "market_movement_activation_sample_expansion_watchlist": [],
            "market_movement_activation_sample_expansion_failed_checks": [],
        }
    return {
        "market_movement_activation_sample_expansion_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "market_movement_activation_sample_expansion_present": True,
        "market_movement_activation_sample_expansion_key": expansion.report_key,
        "market_movement_activation_sample_expansion_status": expansion.status,
        "market_movement_activation_sample_expansion_passed": expansion.passed,
        "market_movement_activation_sample_expansion_promotion_ready": (
            expansion.promotion_ready
        ),
        "market_movement_activation_sample_expansion_source_activation_key": (
            expansion.source_activation_report_key
        ),
        "market_movement_activation_sample_expansion_selected_segment_keys": (
            expansion.selected_segment_group_keys
        ),
        "market_movement_activation_sample_expansion_selected_competition_ids": (
            expansion.selected_segment_competition_ids
        ),
        "market_movement_activation_sample_expansion_ready_fixture_count": (
            expansion.ready_fixture_count
        ),
        "market_movement_activation_sample_expansion_supplemental_fixture_count": (
            expansion.supplemental_fixture_count
        ),
        "market_movement_activation_sample_expansion_combined_fixture_count": (
            expansion.combined_fixture_count
        ),
        "market_movement_activation_sample_expansion_combined_competition_count": (
            expansion.combined_competition_count
        ),
        "market_movement_activation_sample_expansion_combined_competition_season_count": (
            expansion.combined_competition_season_count
        ),
        "market_movement_activation_sample_expansion_adjusted_fixture_count": (
            expansion.adjusted_fixture_count
        ),
        "market_movement_activation_sample_expansion_adjusted_ratio": (
            expansion.adjusted_to_combined_fixture_ratio
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_gate_count": (
            expansion.segment_replay_batch_gate_count
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_ready_count": (
            expansion.segment_replay_batch_ready_count
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_adjusted_fixture_count": (
            expansion.segment_replay_batch_adjusted_fixture_count
        ),
        "market_movement_activation_sample_expansion_effective_segment_keys": (
            expansion.effective_segment_group_keys
        ),
        "market_movement_activation_sample_expansion_effective_segment_count": (
            expansion.effective_segment_count
        ),
        "market_movement_activation_sample_expansion_effective_adjusted_fixture_count": (
            expansion.effective_adjusted_fixture_count
        ),
        "market_movement_activation_sample_expansion_effective_adjusted_ratio": (
            expansion.effective_adjusted_to_combined_fixture_ratio
        ),
        "market_movement_activation_sample_expansion_watchlist": expansion.watchlist,
        "market_movement_activation_sample_expansion_blockers": expansion.blockers,
        "market_movement_activation_sample_expansion_failed_checks": [
            check.name for check in expansion.checks if check.status == "failed"
        ],
    }


def _market_movement_runtime_activation_segment_replay_batch_gate_checks(
    batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ),
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _market_movement_runtime_activation_segment_replay_batch_gate_present_check(
            batch_gate,
            options=options,
        )
    ]
    if batch_gate is None:
        return checks
    required = (
        options.require_market_movement_runtime_activation_segment_replay_batch_gate
        or batch_gate.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="market_movement_segment_replay_batch_passed",
                actual=batch_gate.passed,
                required=required,
                detail="market-movement segment replay batch gate should pass",
            ),
            _required_bool_check(
                name="market_movement_segment_replay_batch_ready",
                actual=batch_gate.runtime_replay_batch_ready,
                required=(
                    required
                    and options.require_market_movement_runtime_activation_segment_replay_batch_ready  # noqa: E501
                ),
                detail="market-movement segment replay batch should be runtime-ready",
            ),
            _required_bool_check(
                name="market_movement_segment_replay_batch_promotion_ready",
                actual=batch_gate.production_promotion_ready,
                required=(
                    options.require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
                ),
                detail=(
                    "market-movement segment replay batch should be promotion-ready "
                    "when explicitly required"
                ),
            ),
            _check_minimum(
                name="market_movement_segment_replay_batch_report_count",
                actual=batch_gate.replay_report_count,
                threshold=(
                    options.min_market_movement_runtime_activation_segment_replay_batch_report_count
                ),
                detail="market-movement segment replay batch should include enough reports",
            ),
            _check_minimum(
                name="market_movement_segment_replay_batch_passed_count",
                actual=batch_gate.passed_replay_count,
                threshold=(
                    options.min_market_movement_runtime_activation_segment_replay_batch_passed_count
                ),
                detail="market-movement segment replay batch should pass enough reports",
            ),
            _check_minimum(
                name="market_movement_segment_replay_batch_adjusted_fixture_count",
                actual=batch_gate.total_adjusted_fixture_count,
                threshold=(
                    options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
                ),
                detail=(
                    "market-movement segment replay batch should cover enough "
                    "adjusted fixtures"
                ),
            ),
            _check_minimum(
                name="market_movement_segment_replay_batch_adjusted_prediction_count",
                actual=batch_gate.total_adjusted_prediction_count,
                threshold=(
                    options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
                ),
                detail=(
                    "market-movement segment replay batch should cover enough "
                    "adjusted predictions"
                ),
            ),
            _required_bool_check(
                name="market_movement_segment_replay_batch_production_unchanged",
                actual=not batch_gate.production_recommendation_changed,
                required=required,
                detail=(
                    "market-movement segment replay batch should not change production"
                ),
            ),
            _required_bool_check(
                name="market_movement_segment_replay_batch_public_unchanged",
                actual=not batch_gate.public_response_changed,
                required=required,
                detail=(
                    "market-movement segment replay batch should not change public output"
                ),
            ),
        ]
    )
    return checks


def _market_movement_runtime_activation_segment_replay_batch_gate_present_check(
    batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ),
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_market_movement_runtime_activation_segment_replay_batch_gate:
        return _skipped_check(
            name="market_movement_segment_replay_batch_present",
            actual=batch_gate is not None,
            detail=(
                "market-movement segment replay batch gate evidence is optional"
            ),
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="market_movement_segment_replay_batch_present",
        status="passed" if batch_gate is not None else "failed",
        actual=batch_gate is not None,
        threshold=True,
        detail=(
            "market-movement segment replay batch gate evidence must be attached"
        ),
    )


def _market_movement_runtime_activation_segment_replay_batch_gate_summary_fields(
    batch_gate: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None
    ),
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if batch_gate is None:
        return {
            "market_movement_segment_replay_batch_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "market_movement_segment_replay_batch_present": False,
            "market_movement_segment_replay_batch_key": None,
            "market_movement_segment_replay_batch_status": None,
            "market_movement_segment_replay_batch_passed": None,
            "market_movement_segment_replay_batch_ready": None,
            "market_movement_segment_replay_batch_promotion_ready": None,
            "market_movement_segment_replay_batch_report_count": 0,
            "market_movement_segment_replay_batch_passed_count": 0,
            "market_movement_segment_replay_batch_failed_count": 0,
            "market_movement_segment_replay_batch_adjusted_fixture_count": 0,
            "market_movement_segment_replay_batch_adjusted_prediction_count": 0,
            "market_movement_segment_replay_batch_weighted_brier_delta": None,
            "market_movement_segment_replay_batch_weighted_log_loss_delta": None,
            "market_movement_segment_replay_batch_weighted_calibration_delta": None,
            "market_movement_segment_replay_batch_watchlist": [],
            "market_movement_segment_replay_batch_blockers": [],
        }
    return {
        "market_movement_segment_replay_batch_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "market_movement_segment_replay_batch_present": True,
        "market_movement_segment_replay_batch_key": batch_gate.report_key,
        "market_movement_segment_replay_batch_status": batch_gate.status,
        "market_movement_segment_replay_batch_passed": batch_gate.passed,
        "market_movement_segment_replay_batch_ready": (
            batch_gate.runtime_replay_batch_ready
        ),
        "market_movement_segment_replay_batch_promotion_ready": (
            batch_gate.production_promotion_ready
        ),
        "market_movement_segment_replay_batch_source_segment_expansion_key": (
            batch_gate.source_segment_expansion_report_key
        ),
        "market_movement_segment_replay_batch_replayed_rule_ids": (
            batch_gate.replayed_rule_ids
        ),
        "market_movement_segment_replay_batch_replayed_segment_keys": (
            batch_gate.replayed_segment_group_keys
        ),
        "market_movement_segment_replay_batch_missing_segment_keys": (
            batch_gate.missing_selected_segment_group_keys
        ),
        "market_movement_segment_replay_batch_report_count": (
            batch_gate.replay_report_count
        ),
        "market_movement_segment_replay_batch_passed_count": (
            batch_gate.passed_replay_count
        ),
        "market_movement_segment_replay_batch_failed_count": (
            batch_gate.failed_replay_count
        ),
        "market_movement_segment_replay_batch_adjusted_fixture_count": (
            batch_gate.total_adjusted_fixture_count
        ),
        "market_movement_segment_replay_batch_adjusted_prediction_count": (
            batch_gate.total_adjusted_prediction_count
        ),
        "market_movement_segment_replay_batch_weighted_final_hit_delta": (
            batch_gate.weighted_final_hit_rate_delta
        ),
        "market_movement_segment_replay_batch_weighted_roi_delta": (
            batch_gate.weighted_roi_delta
        ),
        "market_movement_segment_replay_batch_total_profit_loss_delta": (
            batch_gate.total_profit_loss_delta
        ),
        "market_movement_segment_replay_batch_weighted_brier_delta": (
            batch_gate.weighted_brier_score_delta
        ),
        "market_movement_segment_replay_batch_weighted_log_loss_delta": (
            batch_gate.weighted_log_loss_delta
        ),
        "market_movement_segment_replay_batch_weighted_calibration_delta": (
            batch_gate.weighted_mean_calibration_error_delta
        ),
        "market_movement_segment_replay_batch_production_changed": (
            batch_gate.production_recommendation_changed
        ),
        "market_movement_segment_replay_batch_public_changed": (
            batch_gate.public_response_changed
        ),
        "market_movement_segment_replay_batch_watchlist": batch_gate.watchlist,
        "market_movement_segment_replay_batch_blockers": batch_gate.blockers,
    }


def _replacement_reranker_shadow_admission_checks(
    admission: HistoricalReplacementRerankerShadowAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _replacement_reranker_shadow_admission_present_check(
            admission,
            options=options,
        )
    ]
    if admission is None:
        return checks

    summary = admission.summary_json
    scope = _replacement_reranker_scope_summary(admission)
    source_surface = _replacement_reranker_source_surface_summary(admission)
    required = options.require_replacement_reranker_shadow_admission
    checks.extend(
        [
            _required_bool_check(
                name="replacement_reranker_shadow_admission_accepted",
                actual=admission.status == "accepted",
                required=required,
                detail="replacement reranker scoped admission should be accepted",
            ),
            _required_bool_check(
                name="replacement_reranker_shadow_admission_runtime_candidate_allowed",
                actual=admission.runtime_profile_candidate_allowed,
                required=(
                    required
                    and options.require_replacement_reranker_runtime_candidate_allowed
                ),
                detail=(
                    "replacement reranker admission should allow runtime candidate "
                    "review without changing production"
                ),
            ),
            _required_bool_check(
                name="replacement_reranker_shadow_admission_shadow_allowed",
                actual=admission.shadow_allowed,
                required=required,
                detail="replacement reranker admission should remain shadow-allowed",
            ),
            _required_bool_check(
                name="replacement_reranker_shadow_admission_scoped",
                actual=_scope_bool(scope, "enabled"),
                required=required and options.require_replacement_reranker_scoped_evidence,
                detail="replacement reranker admission should include scoped evidence",
            ),
            _required_bool_check(
                name="replacement_reranker_prematch_source_surface",
                actual=(
                    source_surface.get("kind") == "prematch_replacement_surface"
                ),
                required=(
                    required
                    and options.require_replacement_reranker_prematch_source_surface
                ),
                detail=(
                    "replacement reranker admission should be backed by a full "
                    "pre-match eligible source surface"
                ),
            ),
            _check_minimum(
                name="replacement_reranker_scope_final_answer_count",
                actual=_scope_int(scope, "scoped_final_answer_count"),
                threshold=options.min_replacement_reranker_scope_final_answer_count,
                detail="replacement reranker scope should cover enough final answers",
            ),
            _check_minimum(
                name="replacement_reranker_shadow_final_answer_count",
                actual=_summary_int(summary, "overall_shadow_final_answer_count"),
                threshold=options.min_replacement_reranker_shadow_final_answer_count,
                detail="replacement reranker shadow should cover enough final answers",
            ),
            _check_minimum(
                name="replacement_reranker_changed_from_model_top_count",
                actual=_summary_int(summary, "overall_changed_from_model_top_count"),
                threshold=(
                    options.min_replacement_reranker_changed_from_model_top_count
                ),
                detail="replacement reranker should rerank enough model-top choices",
            ),
            _check_minimum(
                name="replacement_reranker_hit_delta_vs_model_top",
                actual=_summary_int(summary, "overall_hit_delta_vs_model_top_count"),
                threshold=options.min_replacement_reranker_hit_delta_vs_model_top,
                detail="replacement reranker final-answer hits should not regress",
            ),
            _check_optional_minimum(
                name="replacement_reranker_profit_loss_delta_vs_model_top",
                actual=_summary_float(
                    summary,
                    "overall_profit_loss_delta_vs_model_top",
                ),
                threshold=(
                    options.min_replacement_reranker_profit_loss_delta_vs_model_top
                ),
                detail="replacement reranker profit/loss should not regress",
            ),
            _check_optional_minimum(
                name="replacement_reranker_roi_delta_vs_model_top",
                actual=_summary_float(summary, "overall_roi_delta_vs_model_top"),
                threshold=options.min_replacement_reranker_roi_delta_vs_model_top,
                detail="replacement reranker ROI should not regress",
            ),
            _check_optional_maximum(
                name="replacement_reranker_harm_count_vs_model_top",
                actual=_summary_int(summary, "overall_harm_count_vs_model_top"),
                threshold=options.max_replacement_reranker_harm_count_vs_model_top,
                detail="replacement reranker should not harm model-top replacements",
            ),
            _check_optional_maximum(
                name="replacement_reranker_final_hit_harm_count_vs_model_top",
                actual=_summary_int(
                    summary,
                    "overall_final_hit_harm_count_vs_model_top",
                ),
                threshold=(
                    options.max_replacement_reranker_final_hit_harm_count_vs_model_top
                ),
                detail=(
                    "replacement reranker should not turn model-top final-answer "
                    "hits into misses"
                ),
            ),
            _check_optional_maximum(
                name="replacement_reranker_profit_loss_harm_count_vs_model_top",
                actual=_summary_int(
                    summary,
                    "overall_profit_loss_harm_count_vs_model_top",
                ),
                threshold=(
                    options.max_replacement_reranker_profit_loss_harm_count_vs_model_top
                ),
                detail=(
                    "replacement reranker should not reduce model-top final-answer "
                    "profit/loss"
                ),
            ),
            _check_optional_maximum(
                name="replacement_reranker_failed_fold_count",
                actual=admission.failed_fold_count,
                threshold=options.max_replacement_reranker_failed_fold_count,
                detail="replacement reranker admission should not fail active folds",
            ),
            _check_minimum(
                name="replacement_reranker_active_competition_fold_count",
                actual=admission.active_competition_fold_count,
                threshold=(
                    options.min_replacement_reranker_active_competition_fold_count
                ),
                detail="replacement reranker should validate competition folds",
            ),
            _check_minimum(
                name="replacement_reranker_active_season_fold_count",
                actual=admission.active_season_fold_count,
                threshold=options.min_replacement_reranker_active_season_fold_count,
                detail="replacement reranker should validate season folds",
            ),
            _check_minimum(
                name="replacement_reranker_active_rolling_fold_count",
                actual=admission.active_rolling_fold_count,
                threshold=options.min_replacement_reranker_active_rolling_fold_count,
                detail="replacement reranker should validate rolling folds",
            ),
        ]
    )
    return checks


def _replacement_reranker_shadow_admission_present_check(
    admission: HistoricalReplacementRerankerShadowAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_replacement_reranker_shadow_admission:
        return _skipped_check(
            name="replacement_reranker_shadow_admission_present",
            actual=admission is not None,
            detail="replacement reranker shadow admission evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="replacement_reranker_shadow_admission_present",
        status="passed" if admission is not None else "failed",
        actual=admission is not None,
        threshold=True,
        detail="replacement reranker shadow admission evidence must be attached",
    )


def _replacement_reranker_shadow_admission_summary_fields(
    admission: HistoricalReplacementRerankerShadowAdmissionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if admission is None:
        return {
            "replacement_reranker_shadow_admission_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "replacement_reranker_shadow_admission_present": False,
            "replacement_reranker_shadow_admission_key": None,
            "replacement_reranker_shadow_admission_status": None,
            "replacement_reranker_shadow_admission_runtime_candidate_allowed": None,
            "replacement_reranker_shadow_admission_shadow_allowed": None,
            "replacement_reranker_shadow_admission_profile_id": None,
            "replacement_reranker_source_surface_kind": None,
            "replacement_reranker_source_surface_missed_legs_only": None,
            "replacement_reranker_source_surface_selected_leg_count": 0,
            "replacement_reranker_source_surface_final_answer_count": 0,
            "replacement_reranker_shadow_admission_scope_enabled": False,
            "replacement_reranker_shadow_admission_scope_final_answer_count": 0,
            "replacement_reranker_shadow_final_answer_count": 0,
            "replacement_reranker_changed_from_model_top_count": 0,
            "replacement_reranker_hit_delta_vs_model_top": 0,
            "replacement_reranker_profit_loss_delta_vs_model_top": None,
            "replacement_reranker_roi_delta_vs_model_top": None,
            "replacement_reranker_harm_count_vs_model_top": 0,
            "replacement_reranker_final_hit_harm_count_vs_model_top": 0,
            "replacement_reranker_profit_loss_harm_count_vs_model_top": 0,
            "replacement_reranker_failed_fold_count": 0,
            "replacement_reranker_active_competition_fold_count": 0,
            "replacement_reranker_active_season_fold_count": 0,
            "replacement_reranker_active_rolling_fold_count": 0,
        }
    summary = admission.summary_json
    scope = _replacement_reranker_scope_summary(admission)
    source_surface = _replacement_reranker_source_surface_summary(admission)
    return {
        "replacement_reranker_shadow_admission_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "replacement_reranker_shadow_admission_present": True,
        "replacement_reranker_shadow_admission_key": admission.report_key,
        "replacement_reranker_shadow_admission_status": admission.status,
        "replacement_reranker_shadow_admission_runtime_candidate_allowed": (
            admission.runtime_profile_candidate_allowed
        ),
        "replacement_reranker_shadow_admission_shadow_allowed": (
            admission.shadow_allowed
        ),
        "replacement_reranker_shadow_admission_profile_id": admission.profile_id,
        "replacement_reranker_source_surface_kind": _summary_str(
            source_surface,
            "kind",
        ),
        "replacement_reranker_source_surface_missed_legs_only": _summary_optional_bool(
            source_surface,
            "missed_legs_only",
        ),
        "replacement_reranker_source_surface_selected_leg_count": _scope_int(
            source_surface,
            "selected_leg_count",
        ),
        "replacement_reranker_source_surface_final_answer_count": _scope_int(
            source_surface,
            "final_answer_count",
        ),
        "replacement_reranker_shadow_admission_scope_enabled": _scope_bool(
            scope,
            "enabled",
        ),
        "replacement_reranker_shadow_admission_scope_competition_ids": (
            _scope_list(scope, "scoped_competition_ids")
        ),
        "replacement_reranker_shadow_admission_scope_season_ids": (
            _scope_list(scope, "scoped_season_ids")
        ),
        "replacement_reranker_shadow_admission_scope_final_answer_count": (
            _scope_int(scope, "scoped_final_answer_count")
        ),
        "replacement_reranker_shadow_final_answer_count": _summary_int(
            summary,
            "overall_shadow_final_answer_count",
        ),
        "replacement_reranker_changed_from_model_top_count": _summary_int(
            summary,
            "overall_changed_from_model_top_count",
        ),
        "replacement_reranker_hit_delta_vs_model_top": _summary_int(
            summary,
            "overall_hit_delta_vs_model_top_count",
        ),
        "replacement_reranker_profit_loss_delta_vs_model_top": _summary_float(
            summary,
            "overall_profit_loss_delta_vs_model_top",
        ),
        "replacement_reranker_roi_delta_vs_model_top": _summary_float(
            summary,
            "overall_roi_delta_vs_model_top",
        ),
        "replacement_reranker_harm_count_vs_model_top": _summary_int(
            summary,
            "overall_harm_count_vs_model_top",
        ),
        "replacement_reranker_final_hit_harm_count_vs_model_top": _summary_int(
            summary,
            "overall_final_hit_harm_count_vs_model_top",
        ),
        "replacement_reranker_profit_loss_harm_count_vs_model_top": _summary_int(
            summary,
            "overall_profit_loss_harm_count_vs_model_top",
        ),
        "replacement_reranker_failed_fold_count": admission.failed_fold_count,
        "replacement_reranker_active_competition_fold_count": (
            admission.active_competition_fold_count
        ),
        "replacement_reranker_active_season_fold_count": (
            admission.active_season_fold_count
        ),
        "replacement_reranker_active_rolling_fold_count": (
            admission.active_rolling_fold_count
        ),
    }


def _replacement_reranker_scope_summary(
    admission: HistoricalReplacementRerankerShadowAdmissionReport,
) -> dict[str, object]:
    scope = admission.summary_json.get("scope")
    return scope if isinstance(scope, dict) else {}


def _replacement_reranker_source_surface_summary(
    admission: HistoricalReplacementRerankerShadowAdmissionReport,
) -> dict[str, object]:
    source_surface = admission.summary_json.get("source_surface")
    return source_surface if isinstance(source_surface, dict) else {}


def _global_planner_short_odds_adapter_gate_checks(
    gate: HistoricalGlobalPlannerShortOddsAdapterGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _global_planner_short_odds_adapter_gate_present_check(
            gate,
            options=options,
        )
    ]
    if gate is None:
        return checks
    required = options.require_global_planner_short_odds_adapter_gate
    checks.extend(
        [
            _required_bool_check(
                name="global_planner_short_odds_adapter_gate_passed",
                actual=gate.passed,
                required=required,
                detail="global planner short-odds adapter gate should pass",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_gate_status_passed",
                actual=gate.status == "passed",
                required=required,
                detail="global planner short-odds adapter gate status should pass",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_default_path_unchanged",
                actual=gate.planner_default_path_changed is False,
                required=(
                    required
                    and options.require_global_planner_short_odds_adapter_default_path_unchanged
                ),
                detail="default-disabled planner branch should not change answers",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_shadow_path_unchanged",
                actual=gate.planner_shadow_path_changed is False,
                required=(
                    required
                    and options.require_global_planner_short_odds_adapter_shadow_path_unchanged
                ),
                detail="shadow-only planner branch should not change answers",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_explicit_opt_in_changed",
                actual=gate.planner_explicit_opt_in_changed is True,
                required=(
                    required
                    and options.require_global_planner_short_odds_adapter_explicit_opt_in_changed
                ),
                detail="explicit opt-in planner branch should exercise replacement",
            ),
            _check_minimum(
                name="global_planner_short_odds_adapter_runtime_final_answer_count",
                actual=gate.runtime_final_answer_count,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_final_answer_count
                ),
                detail="source real-history replay should cover enough final answers",
            ),
            _check_minimum(
                name="global_planner_short_odds_adapter_runtime_changed_final_answer_count",
                actual=gate.runtime_changed_final_answer_count,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_changed_final_answer_count
                ),
                detail="source real-history replay should affect enough final answers",
            ),
            _check_optional_minimum(
                name="global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta",
                actual=gate.runtime_final_answer_hit_rate_delta,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta
                ),
                detail="source real-history replay hit rate should not regress",
            ),
            _check_optional_minimum(
                name="global_planner_short_odds_adapter_runtime_roi_delta",
                actual=gate.runtime_roi_delta,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_roi_delta
                ),
                detail="source real-history replay ROI should not regress",
            ),
            _check_minimum(
                name="global_planner_short_odds_adapter_runtime_profit_loss_delta",
                actual=gate.runtime_profit_loss_delta,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_profit_loss_delta
                ),
                detail="source real-history replay profit/loss should not regress",
            ),
            _check_optional_maximum(
                name="global_planner_short_odds_adapter_runtime_harm_count",
                actual=gate.runtime_harm_count_vs_original,
                threshold=(
                    options.max_global_planner_short_odds_adapter_runtime_harm_count_vs_original
                ),
                detail="source real-history replay should not harm original answers",
            ),
            _check_optional_maximum(
                name="global_planner_short_odds_adapter_runtime_final_hit_harm_count",
                actual=gate.runtime_final_hit_harm_count_vs_original,
                threshold=(
                    options.max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original
                ),
                detail="source replay should not turn original hits into misses",
            ),
            _check_optional_maximum(
                name="global_planner_short_odds_adapter_runtime_profit_loss_harm_count",
                actual=gate.runtime_profit_loss_harm_count_vs_original,
                threshold=(
                    options.max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original
                ),
                detail="source replay should not reduce original final-answer profit/loss",
            ),
            _check_optional_minimum(
                name="global_planner_short_odds_adapter_runtime_average_hit_probability_delta",
                actual=gate.runtime_average_hit_probability_delta,
                threshold=(
                    options.min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta
                ),
                detail="source replay hit-probability loss should stay inside tolerance",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_runtime_public_unchanged",
                actual=not gate.runtime_public_response_changed,
                required=(
                    required
                    and options.require_global_planner_short_odds_adapter_runtime_public_unchanged
                ),
                detail="source replay should not change public responses",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_runtime_production_unchanged",
                actual=not gate.runtime_production_recommendation_changed,
                required=required
                and _requires_global_planner_adapter_runtime_production_unchanged(
                    options
                ),
                detail="source replay should not change production recommendations",
            ),
        ]
    )
    return checks


def _global_planner_short_odds_adapter_gate_present_check(
    gate: HistoricalGlobalPlannerShortOddsAdapterGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_global_planner_short_odds_adapter_gate:
        return _skipped_check(
            name="global_planner_short_odds_adapter_gate_present",
            actual=gate is not None,
            detail="global planner short-odds adapter evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="global_planner_short_odds_adapter_gate_present",
        status="passed" if gate is not None else "failed",
        actual=gate is not None,
        threshold=True,
        detail="global planner short-odds adapter evidence must be attached",
    )


def _requires_global_planner_adapter_runtime_production_unchanged(
    options: RecommendationBenchmarkQualityGateOptions,
) -> bool:
    return (
        options.require_global_planner_short_odds_adapter_runtime_production_unchanged
    )


def _global_planner_short_odds_adapter_gate_summary_fields(
    gate: HistoricalGlobalPlannerShortOddsAdapterGateReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if gate is None:
        return {
            "global_planner_short_odds_adapter_gate_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "global_planner_short_odds_adapter_gate_present": False,
            "global_planner_short_odds_adapter_gate_key": None,
            "global_planner_short_odds_adapter_gate_status": None,
            "global_planner_short_odds_adapter_gate_passed": None,
            "global_planner_short_odds_adapter_default_path_changed": None,
            "global_planner_short_odds_adapter_shadow_path_changed": None,
            "global_planner_short_odds_adapter_explicit_opt_in_changed": None,
            "global_planner_short_odds_adapter_runtime_final_answer_count": 0,
            "global_planner_short_odds_adapter_runtime_changed_final_answer_count": 0,
            "global_planner_short_odds_adapter_runtime_roi_delta": None,
            "global_planner_short_odds_adapter_runtime_profit_loss_delta": None,
            "global_planner_short_odds_adapter_runtime_harm_count": 0,
            "global_planner_short_odds_adapter_runtime_final_hit_harm_count": 0,
            "global_planner_short_odds_adapter_runtime_profit_loss_harm_count": 0,
        }
    return {
        "global_planner_short_odds_adapter_gate_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "global_planner_short_odds_adapter_gate_present": True,
        "global_planner_short_odds_adapter_gate_key": gate.report_key,
        "global_planner_short_odds_adapter_gate_status": gate.status,
        "global_planner_short_odds_adapter_gate_passed": gate.passed,
        "global_planner_short_odds_adapter_source_planner_branch_report_key": (
            gate.source_planner_branch_report_key
        ),
        "global_planner_short_odds_adapter_source_runtime_shadow_replay_report_key": (
            gate.source_runtime_shadow_replay_report_key
        ),
        "global_planner_short_odds_adapter_source_rule_profile_version": (
            gate.source_rule_profile_version
        ),
        "global_planner_short_odds_adapter_default_path_changed": (
            gate.planner_default_path_changed
        ),
        "global_planner_short_odds_adapter_shadow_path_changed": (
            gate.planner_shadow_path_changed
        ),
        "global_planner_short_odds_adapter_explicit_opt_in_changed": (
            gate.planner_explicit_opt_in_changed
        ),
        "global_planner_short_odds_adapter_shadow_adapter_status": (
            gate.planner_shadow_adapter_status
        ),
        "global_planner_short_odds_adapter_opt_in_adapter_status": (
            gate.planner_opt_in_adapter_status
        ),
        "global_planner_short_odds_adapter_runtime_replay_passed": (
            gate.runtime_replay_passed
        ),
        "global_planner_short_odds_adapter_runtime_replay_status": (
            gate.runtime_replay_status
        ),
        "global_planner_short_odds_adapter_runtime_final_answer_count": (
            gate.runtime_final_answer_count
        ),
        "global_planner_short_odds_adapter_runtime_changed_final_answer_count": (
            gate.runtime_changed_final_answer_count
        ),
        "global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta": (
            gate.runtime_final_answer_hit_rate_delta
        ),
        "global_planner_short_odds_adapter_runtime_roi_delta": (
            gate.runtime_roi_delta
        ),
        "global_planner_short_odds_adapter_runtime_profit_loss_delta": (
            gate.runtime_profit_loss_delta
        ),
        "global_planner_short_odds_adapter_runtime_harm_count": (
            gate.runtime_harm_count_vs_original
        ),
        "global_planner_short_odds_adapter_runtime_final_hit_harm_count": (
            gate.runtime_final_hit_harm_count_vs_original
        ),
        "global_planner_short_odds_adapter_runtime_profit_loss_harm_count": (
            gate.runtime_profit_loss_harm_count_vs_original
        ),
        "global_planner_short_odds_adapter_runtime_average_hit_probability_delta": (
            gate.runtime_average_hit_probability_delta
        ),
        "global_planner_short_odds_adapter_runtime_public_response_changed": (
            gate.runtime_public_response_changed
        ),
        "global_planner_short_odds_adapter_runtime_production_recommendation_changed": (
            gate.runtime_production_recommendation_changed
        ),
        "global_planner_short_odds_adapter_failed_checks": [
            check.name for check in gate.checks if check.status == "failed"
        ],
    }


def _global_planner_short_odds_adapter_sample_expansion_checks(
    expansion: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _global_planner_short_odds_adapter_sample_expansion_present_check(
            expansion,
            options=options,
        )
    ]
    if expansion is None:
        return checks
    required = (
        options.require_global_planner_short_odds_adapter_sample_expansion
        or expansion.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="global_planner_short_odds_adapter_sample_expansion_passed",
                actual=expansion.passed,
                required=required,
                detail="global planner short-odds adapter sample expansion should pass",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_sample_expansion_not_blocked",
                actual=expansion.status != "blocked",
                required=required,
                detail="sample expansion evidence should not be blocked",
            ),
            _required_bool_check(
                name="global_planner_short_odds_adapter_sample_expansion_promotion_ready",
                actual=expansion.promotion_ready,
                required=(
                    options.require_global_planner_short_odds_adapter_sample_expansion_promotion_ready
                ),
                detail="sample expansion should be promotion-ready when explicitly required",
            ),
        ]
    )
    return checks


def _global_planner_short_odds_adapter_sample_expansion_present_check(
    expansion: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_global_planner_short_odds_adapter_sample_expansion:
        return _skipped_check(
            name="global_planner_short_odds_adapter_sample_expansion_present",
            actual=expansion is not None,
            detail="global planner short-odds adapter sample expansion is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="global_planner_short_odds_adapter_sample_expansion_present",
        status="passed" if expansion is not None else "failed",
        actual=expansion is not None,
        threshold=True,
        detail="global planner short-odds adapter sample expansion evidence must be attached",
    )


def _global_planner_short_odds_adapter_sample_expansion_summary_fields(
    expansion: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if expansion is None:
        return {
            "global_planner_short_odds_adapter_sample_expansion_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "global_planner_short_odds_adapter_sample_expansion_present": False,
            "global_planner_short_odds_adapter_sample_expansion_key": None,
            "global_planner_short_odds_adapter_sample_expansion_status": None,
            "global_planner_short_odds_adapter_sample_expansion_passed": None,
            "global_planner_short_odds_adapter_sample_expansion_promotion_ready": None,
            "global_planner_short_odds_adapter_sample_expansion_supplemental_final_answer_count": 0,
            (
                "global_planner_short_odds_adapter_sample_expansion_"
                "supplemental_changed_final_answer_count"
            ): 0,
            "global_planner_short_odds_adapter_sample_expansion_combined_final_answer_count": 0,
            (
                "global_planner_short_odds_adapter_sample_expansion_"
                "combined_changed_final_answer_count"
            ): 0,
            "global_planner_short_odds_adapter_sample_expansion_combined_roi_delta": None,
            "global_planner_short_odds_adapter_sample_expansion_combined_harm_count": 0,
            "global_planner_short_odds_adapter_sample_expansion_watchlist_checks": [],
        }
    watchlist_checks = expansion.summary_json.get("watchlist_checks", [])
    if not isinstance(watchlist_checks, list):
        watchlist_checks = []
    return {
        "global_planner_short_odds_adapter_sample_expansion_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "global_planner_short_odds_adapter_sample_expansion_present": True,
        "global_planner_short_odds_adapter_sample_expansion_key": expansion.report_key,
        "global_planner_short_odds_adapter_sample_expansion_status": expansion.status,
        "global_planner_short_odds_adapter_sample_expansion_passed": expansion.passed,
        "global_planner_short_odds_adapter_sample_expansion_promotion_ready": (
            expansion.promotion_ready
        ),
        "global_planner_short_odds_adapter_sample_expansion_base_gate_key": (
            expansion.base_gate_report_key
        ),
        "global_planner_short_odds_adapter_sample_expansion_supplemental_report_count": (
            expansion.supplemental_report_count
        ),
        "global_planner_short_odds_adapter_sample_expansion_supplemental_final_answer_count": (
            expansion.supplemental_final_answer_count
        ),
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "supplemental_changed_final_answer_count"
        ): (
            expansion.supplemental_changed_final_answer_count
        ),
        "global_planner_short_odds_adapter_sample_expansion_supplemental_activation_rate": (
            expansion.supplemental_activation_rate
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_final_answer_count": (
            expansion.combined_final_answer_count
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_changed_final_answer_count": (
            expansion.combined_changed_final_answer_count
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_activation_rate": (
            expansion.combined_activation_rate
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_hit_rate_delta": (
            expansion.combined_final_answer_hit_rate_delta
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_roi_delta": (
            expansion.combined_roi_delta
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_profit_loss_delta": (
            expansion.combined_profit_loss_delta
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_harm_count": (
            expansion.combined_harm_count_vs_original
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_final_hit_harm_count": (
            expansion.combined_final_hit_harm_count_vs_original
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_profit_loss_harm_count": (
            expansion.combined_profit_loss_harm_count_vs_original
        ),
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "combined_average_hit_probability_delta"
        ): (
            expansion.combined_average_hit_probability_delta
        ),
        "global_planner_short_odds_adapter_sample_expansion_watchlist_checks": (
            watchlist_checks
        ),
        "global_planner_short_odds_adapter_sample_expansion_failed_checks": [
            check.name for check in expansion.checks if check.status == "failed"
        ],
    }


def _recommendation_strategy_promotion_gate_checks(
    gate: RecommendationStrategyPromotionGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _recommendation_strategy_promotion_gate_present_check(
            gate,
            options=options,
        )
    ]
    if gate is None:
        return checks
    required = (
        options.require_recommendation_strategy_promotion_gate
        or gate.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="recommendation_strategy_promotion_gate_ready",
                actual=gate.strategy_gate_ready,
                required=(
                    required and options.require_recommendation_strategy_gate_ready
                ),
                detail="strategy promotion gate should be ready when required",
            ),
            _required_bool_check(
                name="recommendation_strategy_promotion_gate_status_ready",
                actual=gate.status == "ready",
                required=(
                    required and options.require_recommendation_strategy_gate_ready
                ),
                detail="strategy promotion gate status should be ready",
            ),
            _required_bool_check(
                name="recommendation_strategy_promotion_gate_no_blockers",
                actual=not gate.blockers,
                required=required,
                detail="strategy promotion gate should not contain blockers",
            ),
            _check_minimum(
                name="recommendation_strategy_promotion_gate_final_answer_count",
                actual=gate.total_final_answer_count,
                threshold=options.min_recommendation_strategy_gate_final_answer_count,
                detail="strategy gate should cover enough final answers",
            ),
            _check_minimum(
                name=(
                    "recommendation_strategy_promotion_gate_changed_final_answer_count"
                ),
                actual=gate.total_changed_final_answer_count,
                threshold=(
                    options.min_recommendation_strategy_gate_changed_final_answer_count
                ),
                detail="strategy gate should change enough final answers",
            ),
            _check_minimum(
                name="recommendation_strategy_promotion_gate_hit_delta_count",
                actual=gate.total_final_answer_hit_delta_count,
                threshold=options.min_recommendation_strategy_gate_hit_delta_count,
                detail="strategy gate final-hit delta should not regress",
            ),
            _check_minimum(
                name="recommendation_strategy_promotion_gate_profit_loss_delta",
                actual=gate.total_profit_loss_delta,
                threshold=options.min_recommendation_strategy_gate_profit_loss_delta,
                detail="strategy gate profit/loss delta should not regress",
            ),
            _check_optional_minimum(
                name="recommendation_strategy_promotion_gate_minimum_roi_delta",
                actual=gate.minimum_roi_delta,
                threshold=options.min_recommendation_strategy_gate_minimum_roi_delta,
                detail="strategy gate minimum ROI delta should not regress",
            ),
            _check_optional_maximum(
                name="recommendation_strategy_promotion_gate_harm_count",
                actual=gate.total_harm_count_vs_original,
                threshold=options.max_recommendation_strategy_gate_harm_count,
                detail="strategy gate should not harm original answers",
            ),
            _check_optional_maximum(
                name="recommendation_strategy_promotion_gate_final_hit_harm_count",
                actual=gate.total_final_hit_harm_count_vs_original,
                threshold=options.max_recommendation_strategy_gate_final_hit_harm_count,
                detail="strategy gate should not turn original hits into misses",
            ),
            _check_optional_maximum(
                name="recommendation_strategy_promotion_gate_profit_loss_harm_count",
                actual=gate.total_profit_loss_harm_count_vs_original,
                threshold=(
                    options.max_recommendation_strategy_gate_profit_loss_harm_count
                ),
                detail="strategy gate should not reduce original profit/loss",
            ),
            _required_bool_check(
                name="recommendation_strategy_promotion_gate_production_unchanged",
                actual=not gate.production_recommendation_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_gate_no_production_change
                ),
                detail="strategy gate should not change production recommendations",
            ),
            _required_bool_check(
                name="recommendation_strategy_promotion_gate_public_unchanged",
                actual=not gate.public_response_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_gate_no_public_response_change
                ),
                detail="strategy gate should not change public responses",
            ),
        ]
    )
    return checks


def _recommendation_strategy_promotion_gate_present_check(
    gate: RecommendationStrategyPromotionGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_recommendation_strategy_promotion_gate:
        return _skipped_check(
            name="recommendation_strategy_promotion_gate_present",
            actual=gate is not None,
            detail="recommendation strategy promotion gate evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="recommendation_strategy_promotion_gate_present",
        status="passed" if gate is not None else "failed",
        actual=gate is not None,
        threshold=True,
        detail="recommendation strategy promotion gate evidence must be attached",
    )


def _recommendation_strategy_promotion_gate_summary_fields(
    gate: RecommendationStrategyPromotionGateReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if gate is None:
        return {
            "recommendation_strategy_promotion_gate_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "recommendation_strategy_promotion_gate_present": False,
            "recommendation_strategy_promotion_gate_key": None,
            "recommendation_strategy_promotion_gate_status": None,
            "recommendation_strategy_promotion_gate_ready": None,
            "recommendation_strategy_promotion_gate_final_answer_count": 0,
            "recommendation_strategy_promotion_gate_changed_final_answer_count": 0,
            "recommendation_strategy_promotion_gate_hit_delta_count": 0,
            "recommendation_strategy_promotion_gate_profit_loss_delta": None,
            "recommendation_strategy_promotion_gate_minimum_roi_delta": None,
            "recommendation_strategy_promotion_gate_harm_count": 0,
            "recommendation_strategy_promotion_gate_final_hit_harm_count": 0,
            "recommendation_strategy_promotion_gate_profit_loss_harm_count": 0,
            "recommendation_strategy_promotion_gate_production_changed": None,
            "recommendation_strategy_promotion_gate_public_response_changed": None,
            "recommendation_strategy_promotion_gate_failed_checks": [],
        }
    return {
        "recommendation_strategy_promotion_gate_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "recommendation_strategy_promotion_gate_present": True,
        "recommendation_strategy_promotion_gate_key": gate.gate_key,
        "recommendation_strategy_promotion_gate_status": gate.status,
        "recommendation_strategy_promotion_gate_ready": gate.strategy_gate_ready,
        "recommendation_strategy_key": gate.strategy_key,
        "recommendation_strategy_gate_id": gate.gate_id,
        "recommendation_strategy_promotion_gate_evidence_count": gate.evidence_count,
        "recommendation_strategy_promotion_gate_ready_evidence_count": (
            gate.ready_evidence_count
        ),
        "recommendation_strategy_promotion_gate_selected_candidate_keys": (
            gate.selected_candidate_keys
        ),
        "recommendation_strategy_promotion_gate_allowed_competition_ids": (
            gate.allowed_competition_ids
        ),
        "recommendation_strategy_promotion_gate_final_answer_count": (
            gate.total_final_answer_count
        ),
        "recommendation_strategy_promotion_gate_changed_final_answer_count": (
            gate.total_changed_final_answer_count
        ),
        "recommendation_strategy_promotion_gate_hit_delta_count": (
            gate.total_final_answer_hit_delta_count
        ),
        "recommendation_strategy_promotion_gate_profit_loss_delta": (
            gate.total_profit_loss_delta
        ),
        "recommendation_strategy_promotion_gate_minimum_roi_delta": (
            gate.minimum_roi_delta
        ),
        "recommendation_strategy_promotion_gate_harm_count": (
            gate.total_harm_count_vs_original
        ),
        "recommendation_strategy_promotion_gate_final_hit_harm_count": (
            gate.total_final_hit_harm_count_vs_original
        ),
        "recommendation_strategy_promotion_gate_profit_loss_harm_count": (
            gate.total_profit_loss_harm_count_vs_original
        ),
        "recommendation_strategy_promotion_gate_production_changed": (
            gate.production_recommendation_changed
        ),
        "recommendation_strategy_promotion_gate_public_response_changed": (
            gate.public_response_changed
        ),
        "recommendation_strategy_promotion_gate_blockers": gate.blockers,
        "recommendation_strategy_promotion_gate_failed_checks": [
            check.name for check in gate.checks if check.status == "failed"
        ],
    }


def _recommendation_strategy_staged_activation_smoke_checks(
    smoke: RecommendationStrategyStagedActivationSmokeReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _recommendation_strategy_staged_activation_smoke_present_check(
            smoke,
            options=options,
        )
    ]
    if smoke is None:
        return checks
    required = (
        options.require_recommendation_strategy_staged_activation_smoke
        or smoke.status == "blocked"
    )
    checks.extend(
        [
            _required_bool_check(
                name="recommendation_strategy_staged_activation_ready",
                actual=smoke.staged_activation_ready,
                required=(
                    required
                    and options.require_recommendation_strategy_staged_activation_ready
                ),
                detail="staged activation smoke should be ready when required",
            ),
            _required_bool_check(
                name="recommendation_strategy_staged_activation_status_ready",
                actual=smoke.status == "staged_activation_ready",
                required=(
                    required
                    and options.require_recommendation_strategy_staged_activation_ready
                ),
                detail="staged activation smoke status should be ready",
            ),
            _required_bool_check(
                name="recommendation_strategy_staged_activation_no_blockers",
                actual=not smoke.blockers,
                required=required,
                detail="staged activation smoke should not contain blockers",
            ),
            _check_minimum(
                name="recommendation_strategy_staged_rule_count",
                actual=smoke.selected_rule_count,
                threshold=options.min_recommendation_strategy_staged_rule_count,
                detail="staged activation should select enough rules",
            ),
            _check_minimum(
                name="recommendation_strategy_staged_allowed_competition_count",
                actual=len(smoke.allowed_competition_ids),
                threshold=(
                    options.min_recommendation_strategy_staged_allowed_competition_count
                ),
                detail="staged activation should cover enough competitions",
            ),
            _required_bool_check(
                name="recommendation_strategy_staged_default_profile_not_written",
                actual=not smoke.default_profile_written,
                required=(
                    required
                    and options.require_recommendation_strategy_staged_no_default_write
                ),
                detail="staged activation should not write the default profile",
            ),
            _required_bool_check(
                name="recommendation_strategy_staged_production_unchanged",
                actual=not smoke.production_recommendation_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_staged_no_production_change
                ),
                detail="staged activation should not change production recommendations",
            ),
            _required_bool_check(
                name="recommendation_strategy_staged_public_unchanged",
                actual=not smoke.public_response_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_staged_no_public_response_change
                ),
                detail="staged activation should not change public responses",
            ),
        ]
    )
    return checks


def _recommendation_strategy_staged_activation_smoke_present_check(
    smoke: RecommendationStrategyStagedActivationSmokeReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_recommendation_strategy_staged_activation_smoke:
        return _skipped_check(
            name="recommendation_strategy_staged_activation_smoke_present",
            actual=smoke is not None,
            detail="recommendation strategy staged activation smoke is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="recommendation_strategy_staged_activation_smoke_present",
        status="passed" if smoke is not None else "failed",
        actual=smoke is not None,
        threshold=True,
        detail="recommendation strategy staged activation smoke must be attached",
    )


def _recommendation_strategy_staged_activation_smoke_summary_fields(
    smoke: RecommendationStrategyStagedActivationSmokeReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if smoke is None:
        return {
            "recommendation_strategy_staged_activation_smoke_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "recommendation_strategy_staged_activation_smoke_present": False,
            "recommendation_strategy_staged_activation_smoke_key": None,
            "recommendation_strategy_staged_activation_smoke_status": None,
            "recommendation_strategy_staged_activation_ready": None,
            "recommendation_strategy_staged_rule_count": 0,
            "recommendation_strategy_staged_allowed_competition_count": 0,
            "recommendation_strategy_staged_default_profile_written": None,
            "recommendation_strategy_staged_production_changed": None,
            "recommendation_strategy_staged_public_response_changed": None,
            "recommendation_strategy_staged_activation_failed_checks": [],
        }
    return {
        "recommendation_strategy_staged_activation_smoke_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "recommendation_strategy_staged_activation_smoke_present": True,
        "recommendation_strategy_staged_activation_smoke_key": smoke.report_key,
        "recommendation_strategy_staged_activation_smoke_status": smoke.status,
        "recommendation_strategy_staged_activation_ready": (
            smoke.staged_activation_ready
        ),
        "recommendation_strategy_staged_profile_version": (
            smoke.staged_profile_version
        ),
        "recommendation_strategy_staged_source_strategy_gate_key": (
            smoke.source_strategy_gate_key
        ),
        "recommendation_strategy_staged_rule_profile_version": (
            smoke.rule_profile_version
        ),
        "recommendation_strategy_staged_rule_count": smoke.selected_rule_count,
        "recommendation_strategy_staged_allowed_competition_count": len(
            smoke.allowed_competition_ids
        ),
        "recommendation_strategy_staged_allowed_competition_ids": (
            smoke.allowed_competition_ids
        ),
        "recommendation_strategy_staged_default_profile_written": (
            smoke.default_profile_written
        ),
        "recommendation_strategy_staged_production_changed": (
            smoke.production_recommendation_changed
        ),
        "recommendation_strategy_staged_public_response_changed": (
            smoke.public_response_changed
        ),
        "recommendation_strategy_staged_blockers": smoke.blockers,
        "recommendation_strategy_staged_activation_failed_checks": [
            check.name for check in smoke.checks if check.status == "failed"
        ],
    }


def _recommendation_strategy_default_path_isolation_checks(
    isolation: RecommendationStrategyDefaultPathIsolationReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _recommendation_strategy_default_path_isolation_present_check(
            isolation,
            options=options,
        )
    ]
    if isolation is None:
        return checks
    required = (
        options.require_recommendation_strategy_default_path_isolation
        or isolation.status == "blocked"
    )
    default_adapter_unchanged_required = (
        required and options.require_recommendation_strategy_default_adapter_unchanged
    )
    checks.extend(
        [
            _required_bool_check(
                name="recommendation_strategy_default_path_isolated",
                actual=isolation.default_path_isolated,
                required=(
                    required
                    and options.require_recommendation_strategy_default_path_isolated
                ),
                detail="default recommendation path should remain isolated",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_path_isolation_status_isolated",
                actual=isolation.status == "isolated",
                required=(
                    required
                    and options.require_recommendation_strategy_default_path_isolated
                ),
                detail="default path isolation status should be isolated",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_path_isolation_no_blockers",
                actual=not isolation.blockers,
                required=required,
                detail="default path isolation should not contain blockers",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_adapter_disabled",
                actual=isolation.default_adapter_status == "disabled",
                required=(
                    required
                    and options.require_recommendation_strategy_default_adapter_disabled
                ),
                detail="default adapter branch should remain disabled",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_adapter_selection_unchanged",
                actual=not isolation.default_adapter_selection_changed,
                required=default_adapter_unchanged_required,
                detail="default adapter branch should not change selections",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_adapter_path_unchanged",
                actual=not isolation.default_adapter_default_path_changed,
                required=default_adapter_unchanged_required,
                detail="default adapter branch should not change the default path",
            ),
            _required_bool_check(
                name="recommendation_strategy_default_adapter_public_unchanged",
                actual=not isolation.default_adapter_public_response_changed,
                required=default_adapter_unchanged_required,
                detail="default adapter branch should not change public responses",
            ),
            _required_bool_check(
                name="recommendation_strategy_explicit_opt_in_applied",
                actual=isolation.explicit_opt_in_adapter_status == "applied",
                required=(
                    required
                    and options.require_recommendation_strategy_explicit_opt_in_applied
                ),
                detail="explicit internal opt-in branch should exercise the strategy",
            ),
            _required_bool_check(
                name="recommendation_strategy_explicit_opt_in_selection_changed",
                actual=isolation.explicit_opt_in_selection_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_explicit_opt_in_applied
                ),
                detail="explicit opt-in should change selections for smoke coverage",
            ),
            _required_bool_check(
                name="recommendation_strategy_explicit_opt_in_path_unchanged",
                actual=not isolation.explicit_opt_in_default_path_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_explicit_opt_in_applied
                ),
                detail="explicit opt-in should not change default-path metadata",
            ),
            _required_bool_check(
                name="recommendation_strategy_explicit_opt_in_public_unchanged",
                actual=not isolation.explicit_opt_in_public_response_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_explicit_opt_in_applied
                ),
                detail="explicit opt-in should not change public responses",
            ),
            _required_bool_check(
                name="recommendation_strategy_isolation_default_profile_not_written",
                actual=not isolation.default_profile_written,
                required=(
                    required
                    and options.require_recommendation_strategy_isolation_no_default_write
                ),
                detail="default path isolation should not write the default profile",
            ),
            _required_bool_check(
                name="recommendation_strategy_isolation_production_unchanged",
                actual=not isolation.production_recommendation_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_isolation_no_production_change
                ),
                detail="default path isolation should not change production recommendations",
            ),
            _required_bool_check(
                name="recommendation_strategy_isolation_public_unchanged",
                actual=not isolation.public_response_changed,
                required=(
                    required
                    and options.require_recommendation_strategy_isolation_no_public_response_change
                ),
                detail="default path isolation should not change public responses",
            ),
        ]
    )
    return checks


def _recommendation_strategy_default_path_isolation_present_check(
    isolation: RecommendationStrategyDefaultPathIsolationReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_recommendation_strategy_default_path_isolation:
        return _skipped_check(
            name="recommendation_strategy_default_path_isolation_present",
            actual=isolation is not None,
            detail="recommendation strategy default-path isolation is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="recommendation_strategy_default_path_isolation_present",
        status="passed" if isolation is not None else "failed",
        actual=isolation is not None,
        threshold=True,
        detail="recommendation strategy default-path isolation must be attached",
    )


def _recommendation_strategy_default_path_isolation_summary_fields(
    isolation: RecommendationStrategyDefaultPathIsolationReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if isolation is None:
        return {
            "recommendation_strategy_default_path_isolation_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "recommendation_strategy_default_path_isolation_present": False,
            "recommendation_strategy_default_path_isolation_key": None,
            "recommendation_strategy_default_path_isolation_status": None,
            "recommendation_strategy_default_path_isolated": None,
            "recommendation_strategy_default_adapter_status": None,
            "recommendation_strategy_default_adapter_selection_changed": None,
            "recommendation_strategy_explicit_opt_in_adapter_status": None,
            "recommendation_strategy_explicit_opt_in_selection_changed": None,
            "recommendation_strategy_isolation_default_profile_written": None,
            "recommendation_strategy_isolation_production_changed": None,
            "recommendation_strategy_isolation_public_response_changed": None,
            "recommendation_strategy_default_path_isolation_failed_checks": [],
        }
    return {
        "recommendation_strategy_default_path_isolation_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "recommendation_strategy_default_path_isolation_present": True,
        "recommendation_strategy_default_path_isolation_key": isolation.report_key,
        "recommendation_strategy_default_path_isolation_status": isolation.status,
        "recommendation_strategy_default_path_isolated": (
            isolation.default_path_isolated
        ),
        "recommendation_strategy_default_profile_path": isolation.default_profile_path,
        "recommendation_strategy_default_profile_version": (
            isolation.default_profile_version
        ),
        "recommendation_strategy_staged_profile_path": isolation.staged_profile_path,
        "recommendation_strategy_staged_profile_version_for_isolation": (
            isolation.staged_profile_version
        ),
        "recommendation_strategy_default_adapter_status": (
            isolation.default_adapter_status
        ),
        "recommendation_strategy_default_adapter_selection_changed": (
            isolation.default_adapter_selection_changed
        ),
        "recommendation_strategy_default_adapter_path_changed": (
            isolation.default_adapter_default_path_changed
        ),
        "recommendation_strategy_default_adapter_public_response_changed": (
            isolation.default_adapter_public_response_changed
        ),
        "recommendation_strategy_explicit_opt_in_adapter_status": (
            isolation.explicit_opt_in_adapter_status
        ),
        "recommendation_strategy_explicit_opt_in_selection_changed": (
            isolation.explicit_opt_in_selection_changed
        ),
        "recommendation_strategy_explicit_opt_in_path_changed": (
            isolation.explicit_opt_in_default_path_changed
        ),
        "recommendation_strategy_explicit_opt_in_public_response_changed": (
            isolation.explicit_opt_in_public_response_changed
        ),
        "recommendation_strategy_isolation_default_profile_written": (
            isolation.default_profile_written
        ),
        "recommendation_strategy_isolation_production_changed": (
            isolation.production_recommendation_changed
        ),
        "recommendation_strategy_isolation_public_response_changed": (
            isolation.public_response_changed
        ),
        "recommendation_strategy_default_path_isolation_blockers": isolation.blockers,
        "recommendation_strategy_default_path_isolation_failed_checks": [
            check.name for check in isolation.checks if check.status == "failed"
        ],
    }


def _probability_calibration_profile_rolling_admission_checks(
    admission: HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _probability_calibration_profile_rolling_admission_present_check(
            admission,
            options=options,
        )
    ]
    if admission is None:
        return checks
    required = options.require_probability_calibration_profile_rolling_admission
    profile_mode = admission.profile.mode if admission.profile is not None else None
    checks.extend(
        [
            _required_bool_check(
                name="probability_calibration_profile_rolling_admission_accepted",
                actual=admission.status == "accepted",
                required=required,
                detail="probability calibration rolling admission should be accepted",
            ),
            _required_bool_check(
                name=(
                    "probability_calibration_profile_rolling_admission_candidate_allowed"
                ),
                actual=admission.candidate_profile_allowed,
                required=(
                    required
                    and options.require_probability_calibration_profile_candidate_allowed
                ),
                detail=(
                    "probability calibration admission should allow a staged "
                    "runtime profile"
                ),
            ),
            _required_bool_check(
                name="probability_calibration_profile_rolling_admission_shadow_allowed",
                actual=admission.shadow_allowed,
                required=required,
                detail="probability calibration admission should remain shadow-allowed",
            ),
            _required_bool_check(
                name="probability_calibration_profile_rolling_admission_active_profile",
                actual=profile_mode == "active",
                required=(
                    required
                    and options.require_probability_calibration_profile_active_profile
                ),
                detail=(
                    "probability calibration admission should emit an active staged "
                    "profile when promotion is required"
                ),
            ),
            _required_bool_check(
                name=(
                    "probability_calibration_profile_rolling_admission_overall_gate"
                ),
                actual=admission.overall_fold.passed_final_answer_gate,
                required=required,
                detail="overall probability calibration final-answer gate should pass",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_rolling_admission_overall_adjusted_fixture_count"
                ),
                actual=admission.overall_fold.adjusted_fixture_count,
                threshold=(
                    options.min_probability_calibration_profile_overall_adjusted_fixture_count
                ),
                detail="overall calibration admission should adjust enough fixtures",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_rolling_admission_overall_bucket_count"
                ),
                actual=admission.overall_fold.bucket_count,
                threshold=(
                    options.min_probability_calibration_profile_overall_bucket_count
                ),
                detail="overall calibration admission should emit enough buckets",
            ),
            _check_optional_maximum(
                name="probability_calibration_profile_rolling_admission_failed_fold_count",
                actual=admission.failed_fold_count,
                threshold=options.max_probability_calibration_profile_failed_fold_count,
                detail="probability calibration admission should not fail active folds",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_rolling_admission_active_competition_fold_count"
                ),
                actual=admission.active_competition_fold_count,
                threshold=(
                    options.min_probability_calibration_profile_active_competition_fold_count
                ),
                detail="probability calibration admission should validate competition folds",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_rolling_admission_active_season_cutoff_fold_count"
                ),
                actual=admission.active_season_cutoff_fold_count,
                threshold=(
                    options.min_probability_calibration_profile_active_season_cutoff_fold_count
                ),
                detail="probability calibration admission should validate season cutoffs",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_rolling_admission_active_rolling_fold_count"
                ),
                actual=admission.active_rolling_fold_count,
                threshold=(
                    options.min_probability_calibration_profile_active_rolling_fold_count
                ),
                detail="probability calibration admission should validate rolling folds",
            ),
        ]
    )
    return checks


def _probability_calibration_profile_rolling_admission_present_check(
    admission: HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_probability_calibration_profile_rolling_admission:
        return _skipped_check(
            name="probability_calibration_profile_rolling_admission_present",
            actual=admission is not None,
            detail="probability calibration rolling admission evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="probability_calibration_profile_rolling_admission_present",
        status="passed" if admission is not None else "failed",
        actual=admission is not None,
        threshold=True,
        detail=(
            "probability calibration rolling admission evidence must be attached "
            "before this benchmark gate can pass"
        ),
    )


def _probability_calibration_profile_rolling_admission_summary_fields(
    admission: HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if admission is None:
        return {
            "probability_calibration_profile_rolling_admission_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "probability_calibration_profile_rolling_admission_present": False,
            "probability_calibration_profile_rolling_admission_key": None,
            "probability_calibration_profile_rolling_admission_status": None,
            "probability_calibration_profile_candidate_allowed": None,
            "probability_calibration_profile_shadow_allowed": None,
            "probability_calibration_profile_mode": None,
            "probability_calibration_profile_key": None,
            "probability_calibration_profile_source_artifact_report_key": None,
            "probability_calibration_profile_source_gate_report_key": None,
            "probability_calibration_profile_overall_gate_passed": None,
            "probability_calibration_profile_overall_adjusted_fixture_count": 0,
            "probability_calibration_profile_overall_bucket_count": 0,
            "probability_calibration_profile_failed_fold_count": 0,
            "probability_calibration_profile_active_competition_fold_count": 0,
            "probability_calibration_profile_active_season_cutoff_fold_count": 0,
            "probability_calibration_profile_active_rolling_fold_count": 0,
            "probability_calibration_profile_selected_competition_ids": [],
            "probability_calibration_profile_failed_checks": [],
        }
    profile_mode = admission.profile.mode if admission.profile is not None else None
    profile_key = admission.profile.profile_key if admission.profile is not None else None
    return {
        "probability_calibration_profile_rolling_admission_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "probability_calibration_profile_rolling_admission_present": True,
        "probability_calibration_profile_rolling_admission_key": admission.report_key,
        "probability_calibration_profile_rolling_admission_status": admission.status,
        "probability_calibration_profile_candidate_allowed": (
            admission.candidate_profile_allowed
        ),
        "probability_calibration_profile_shadow_allowed": admission.shadow_allowed,
        "probability_calibration_profile_mode": profile_mode,
        "probability_calibration_profile_key": profile_key,
        "probability_calibration_profile_source_artifact_report_key": (
            admission.source_artifact_report_key
        ),
        "probability_calibration_profile_source_gate_report_key": (
            admission.source_gate_report_key
        ),
        "probability_calibration_profile_overall_gate_passed": (
            admission.overall_fold.passed_final_answer_gate
        ),
        "probability_calibration_profile_overall_adjusted_fixture_count": (
            admission.overall_fold.adjusted_fixture_count
        ),
        "probability_calibration_profile_overall_bucket_count": (
            admission.overall_fold.bucket_count
        ),
        "probability_calibration_profile_failed_fold_count": (
            admission.failed_fold_count
        ),
        "probability_calibration_profile_active_competition_fold_count": (
            admission.active_competition_fold_count
        ),
        "probability_calibration_profile_active_season_cutoff_fold_count": (
            admission.active_season_cutoff_fold_count
        ),
        "probability_calibration_profile_active_rolling_fold_count": (
            admission.active_rolling_fold_count
        ),
        "probability_calibration_profile_selected_competition_ids": (
            admission.overall_fold.selected_competition_ids
        ),
        "probability_calibration_profile_overall_final_hit_rate_delta": (
            admission.overall_fold.final_hit_rate_delta
        ),
        "probability_calibration_profile_overall_roi_delta": (
            admission.overall_fold.roi_delta
        ),
        "probability_calibration_profile_overall_profit_loss_delta": (
            admission.overall_fold.profit_loss_delta
        ),
        "probability_calibration_profile_overall_brier_score_delta": (
            admission.overall_fold.brier_score_delta
        ),
        "probability_calibration_profile_overall_log_loss_delta": (
            admission.overall_fold.log_loss_delta
        ),
        "probability_calibration_profile_overall_mean_calibration_error_delta": (
            admission.overall_fold.mean_calibration_error_delta
        ),
        "probability_calibration_profile_failed_checks": [
            check.name for check in admission.checks if check.status == "failed"
        ],
    }


def _probability_calibration_profile_model_quality_gate_checks(
    gate: HistoricalProbabilityCalibrationProfileModelQualityGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _probability_calibration_profile_model_quality_gate_present_check(
            gate,
            options=options,
        )
    ]
    if gate is None:
        return checks
    required = options.require_probability_calibration_profile_model_quality_gate
    checks.extend(
        [
            _required_bool_check(
                name="probability_calibration_profile_model_quality_gate_ready",
                actual=gate.model_quality_gate_passed
                and gate.status == "model_quality_ready",
                required=(
                    required
                    and options.require_probability_calibration_profile_model_quality_ready
                ),
                detail="probability calibration model-quality evidence should be ready",
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_model_quality_selected_competition_count"
                ),
                actual=len(gate.selected_competition_ids),
                threshold=(
                    options.min_probability_calibration_profile_model_quality_selected_competition_count
                ),
                detail=(
                    "probability calibration model-quality evidence should cover "
                    "enough competitions"
                ),
            ),
            _check_minimum(
                name="probability_calibration_profile_model_quality_adjusted_slice_count",
                actual=gate.adjusted_slice_count,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_adjusted_slice_count
                ),
                detail=(
                    "probability calibration model-quality evidence should cover "
                    "enough adjusted slices"
                ),
            ),
            _check_minimum(
                name="probability_calibration_profile_model_quality_adjusted_fixture_count",
                actual=gate.adjusted_fixture_count,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_adjusted_fixture_count
                ),
                detail=(
                    "probability calibration model-quality evidence should cover "
                    "enough adjusted fixtures"
                ),
            ),
            _check_optional_maximum(
                name="probability_calibration_profile_model_quality_skipped_fixture_count",
                actual=gate.skipped_fixture_count,
                threshold=(
                    options.max_probability_calibration_profile_model_quality_skipped_fixture_count
                ),
                detail=(
                    "probability calibration model-quality evidence should not "
                    "skip too many fixtures"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "probability_calibration_profile_model_quality_final_answer_changed_count"
                ),
                actual=gate.final_answer_changed_count,
                threshold=(
                    options.max_probability_calibration_profile_model_quality_final_answer_changed_count
                ),
                detail=(
                    "probability calibration model-quality evidence should keep "
                    "final answers unchanged by default"
                ),
            ),
            _check_minimum(
                name=(
                    "probability_calibration_profile_model_quality_final_answer_hit_count_delta"
                ),
                actual=gate.final_answer_hit_count_delta,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_final_answer_hit_count_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should not "
                    "reduce final-answer hits"
                ),
            ),
            _check_optional_minimum(
                name=(
                    "probability_calibration_profile_model_quality_final_answer_hit_rate_delta"
                ),
                actual=gate.final_answer_hit_rate_delta,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should not "
                    "reduce final-answer hit rate"
                ),
            ),
            _check_optional_minimum(
                name="probability_calibration_profile_model_quality_roi_delta",
                actual=gate.roi_delta,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_roi_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should not "
                    "reduce ROI"
                ),
            ),
            _check_minimum(
                name="probability_calibration_profile_model_quality_profit_loss_delta",
                actual=gate.profit_loss_delta,
                threshold=(
                    options.min_probability_calibration_profile_model_quality_profit_loss_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should not "
                    "reduce profit/loss"
                ),
            ),
            _check_optional_maximum(
                name="probability_calibration_profile_model_quality_brier_score_delta",
                actual=gate.brier_score_delta,
                threshold=(
                    options.max_probability_calibration_profile_model_quality_brier_score_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should improve "
                    "or preserve Brier score"
                ),
            ),
            _check_optional_maximum(
                name="probability_calibration_profile_model_quality_log_loss_delta",
                actual=gate.log_loss_delta,
                threshold=(
                    options.max_probability_calibration_profile_model_quality_log_loss_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should improve "
                    "or preserve log loss"
                ),
            ),
            _check_optional_maximum(
                name=(
                    "probability_calibration_profile_model_quality_calibration_error_delta"
                ),
                actual=gate.mean_calibration_error_delta,
                threshold=(
                    options.max_probability_calibration_profile_model_quality_calibration_error_delta
                ),
                detail=(
                    "probability calibration model-quality evidence should improve "
                    "or preserve calibration error"
                ),
            ),
        ]
    )
    return checks


def _probability_calibration_profile_model_quality_gate_present_check(
    gate: HistoricalProbabilityCalibrationProfileModelQualityGateReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_probability_calibration_profile_model_quality_gate:
        return _skipped_check(
            name="probability_calibration_profile_model_quality_gate_present",
            actual=gate is not None,
            detail="probability calibration model-quality evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="probability_calibration_profile_model_quality_gate_present",
        status="passed" if gate is not None else "failed",
        actual=gate is not None,
        threshold=True,
        detail=(
            "probability calibration model-quality evidence must be attached "
            "before this benchmark gate can pass"
        ),
    )


def _probability_calibration_profile_model_quality_gate_summary_fields(
    gate: HistoricalProbabilityCalibrationProfileModelQualityGateReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if gate is None:
        return {
            "probability_calibration_profile_model_quality_gate_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "probability_calibration_profile_model_quality_gate_present": False,
            "probability_calibration_profile_model_quality_gate_key": None,
            "probability_calibration_profile_model_quality_gate_status": None,
            "probability_calibration_profile_model_quality_gate_ready": None,
            "probability_calibration_profile_model_quality_profile_gate_report_key": None,
            "probability_calibration_profile_model_quality_selected_competition_count": 0,
            "probability_calibration_profile_model_quality_selected_competition_ids": [],
            "probability_calibration_profile_model_quality_adjusted_slice_count": 0,
            "probability_calibration_profile_model_quality_adjusted_fixture_count": 0,
            "probability_calibration_profile_model_quality_skipped_fixture_count": 0,
            "probability_calibration_profile_model_quality_final_answer_changed_count": 0,
            "probability_calibration_profile_model_quality_final_answer_hit_count_delta": 0,
            "probability_calibration_profile_model_quality_final_answer_hit_rate_delta": None,
            "probability_calibration_profile_model_quality_roi_delta": None,
            "probability_calibration_profile_model_quality_profit_loss_delta": 0.0,
            "probability_calibration_profile_model_quality_brier_score_delta": None,
            "probability_calibration_profile_model_quality_log_loss_delta": None,
            "probability_calibration_profile_model_quality_mean_calibration_error_delta": None,
            "probability_calibration_profile_model_quality_failed_checks": [],
            "probability_calibration_profile_model_quality_warning_count": 0,
        }
    return {
        "probability_calibration_profile_model_quality_gate_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "probability_calibration_profile_model_quality_gate_present": True,
        "probability_calibration_profile_model_quality_gate_key": gate.report_key,
        "probability_calibration_profile_model_quality_gate_status": gate.status,
        "probability_calibration_profile_model_quality_gate_ready": (
            gate.model_quality_gate_passed
        ),
        "probability_calibration_profile_model_quality_profile_gate_report_key": (
            gate.profile_gate_report_key
        ),
        "probability_calibration_profile_model_quality_selected_competition_count": (
            len(gate.selected_competition_ids)
        ),
        "probability_calibration_profile_model_quality_selected_competition_ids": (
            gate.selected_competition_ids
        ),
        "probability_calibration_profile_model_quality_adjusted_slice_count": (
            gate.adjusted_slice_count
        ),
        "probability_calibration_profile_model_quality_adjusted_fixture_count": (
            gate.adjusted_fixture_count
        ),
        "probability_calibration_profile_model_quality_skipped_fixture_count": (
            gate.skipped_fixture_count
        ),
        "probability_calibration_profile_model_quality_final_answer_changed_count": (
            gate.final_answer_changed_count
        ),
        "probability_calibration_profile_model_quality_final_answer_hit_count_delta": (
            gate.final_answer_hit_count_delta
        ),
        "probability_calibration_profile_model_quality_final_answer_hit_rate_delta": (
            gate.final_answer_hit_rate_delta
        ),
        "probability_calibration_profile_model_quality_roi_delta": gate.roi_delta,
        "probability_calibration_profile_model_quality_profit_loss_delta": (
            gate.profit_loss_delta
        ),
        "probability_calibration_profile_model_quality_brier_score_delta": (
            gate.brier_score_delta
        ),
        "probability_calibration_profile_model_quality_log_loss_delta": gate.log_loss_delta,
        "probability_calibration_profile_model_quality_mean_calibration_error_delta": (
            gate.mean_calibration_error_delta
        ),
        "probability_calibration_profile_model_quality_failed_checks": [
            check.name for check in gate.checks if check.status == "failed"
        ],
        "probability_calibration_profile_model_quality_warning_count": len(
            gate.warnings
        ),
    }


def _asian_handicap_segmented_model_quality_governance_checks(
    governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ),
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _asian_handicap_segmented_model_quality_governance_present_check(
            governance,
            options=options,
        )
    ]
    if governance is None:
        return checks
    required = options.require_asian_handicap_segmented_model_quality_governance
    staged_profile = governance.staged_profile_json
    checks.extend(
        [
            _required_bool_check(
                name="asian_handicap_segmented_model_quality_governance_ready",
                actual=(
                    governance.governance_review_ready
                    and governance.status == "governance_ready"
                ),
                required=(
                    required
                    and options.require_asian_handicap_segmented_model_quality_ready
                ),
                detail=(
                    "Asian-handicap segmented model-quality governance should be ready"
                ),
            ),
            _required_bool_check(
                name="asian_handicap_segmented_model_quality_internal_only",
                actual=governance.internal_review_only
                and _mapping_bool(staged_profile, "internal_review_only")
                and _mapping_bool(staged_profile, "dry_run_only"),
                required=(
                    required
                    and options.require_asian_handicap_segmented_model_quality_internal_only
                ),
                detail=(
                    "Asian-handicap model-quality evidence must stay internal-only "
                    "and dry-run-only"
                ),
            ),
            _required_bool_check(
                name="asian_handicap_segmented_model_quality_default_path_isolated",
                actual=governance.default_path_isolated
                and _mapping_bool(staged_profile, "default_path_isolated"),
                required=(
                    required
                    and options.require_asian_handicap_segmented_model_quality_default_path_isolated
                ),
                detail=(
                    "Asian-handicap governance must not alter the default prediction path"
                ),
            ),
            _required_bool_check(
                name="asian_handicap_segmented_model_quality_production_unchanged",
                actual=(
                    not governance.production_recommendation_allowed
                    and not governance.production_recommendation_changed
                    and not _mapping_bool(
                        staged_profile,
                        "production_recommendation_allowed",
                    )
                    and not _mapping_bool(
                        staged_profile,
                        "production_recommendation_changed",
                    )
                ),
                required=(
                    required
                    and options.require_asian_handicap_segmented_model_quality_no_production_change
                ),
                detail=(
                    "Asian-handicap governance must not enable or change production recommendations"
                ),
            ),
            _required_bool_check(
                name="asian_handicap_segmented_model_quality_public_response_unchanged",
                actual=(
                    not governance.public_response_changed
                    and not _mapping_bool(staged_profile, "public_response_changed")
                ),
                required=(
                    required
                    and (
                        options.require_asian_handicap_segmented_model_quality_no_public_response_change
                    )
                ),
                detail="Asian-handicap governance must not change public responses",
            ),
            _check_minimum(
                name="asian_handicap_segmented_model_quality_accepted_segment_count",
                actual=governance.accepted_segment_count,
                threshold=(
                    options.min_asian_handicap_segmented_model_quality_accepted_segment_count
                ),
                detail=(
                    "Asian-handicap governance should have enough accepted segments"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_shadow_segment_count",
                actual=governance.shadow_segment_count,
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_shadow_segment_count
                ),
                detail=(
                    "Asian-handicap governance should keep shadow segments bounded"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_fallback_segment_count",
                actual=governance.fallback_segment_count,
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_fallback_segment_count
                ),
                detail=(
                    "Asian-handicap governance should keep baseline fallback segments bounded"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_rejected_segment_count",
                actual=governance.rejected_segment_count,
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_rejected_segment_count
                ),
                detail=(
                    "Asian-handicap governance should not contain rejected segments"
                ),
            ),
            _check_minimum(
                name=(
                    "asian_handicap_segmented_model_quality_accepted_validation_count"
                ),
                actual=governance.accepted_validation_count,
                threshold=(
                    options.min_asian_handicap_segmented_model_quality_accepted_validation_count
                ),
                detail=(
                    "Asian-handicap governance should have enough accepted validation samples"
                ),
            ),
            _check_minimum(
                name=(
                    "asian_handicap_segmented_model_quality_calibration_applied_count"
                ),
                actual=governance.calibration_sample_expansion_applied_count,
                threshold=(
                    options.min_asian_handicap_segmented_model_quality_calibration_applied_count
                ),
                detail=(
                    "Asian-handicap governance should include calibration measurement support"
                ),
            ),
            _check_optional_minimum(
                name="asian_handicap_segmented_model_quality_hit_rate_delta",
                actual=_governance_delta(governance, "hit_rate_delta"),
                threshold=options.min_asian_handicap_segmented_model_quality_hit_rate_delta,
                detail=(
                    "Asian-handicap governance should preserve accepted hit rate"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_brier_score_delta",
                actual=_governance_delta(governance, "brier_score_delta"),
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_brier_score_delta
                ),
                detail=(
                    "Asian-handicap governance should preserve or improve Brier score"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_log_loss_delta",
                actual=_governance_delta(governance, "log_loss_delta"),
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_log_loss_delta
                ),
                detail=(
                    "Asian-handicap governance should preserve or improve log loss"
                ),
            ),
            _check_optional_maximum(
                name="asian_handicap_segmented_model_quality_calibration_error_delta",
                actual=_governance_delta(
                    governance,
                    "expected_calibration_error_delta",
                ),
                threshold=(
                    options.max_asian_handicap_segmented_model_quality_calibration_error_delta
                ),
                detail=(
                    "Asian-handicap governance should preserve or improve calibration error"
                ),
            ),
            _check_optional_minimum(
                name="asian_handicap_segmented_model_quality_actual_probability_delta",
                actual=_governance_delta(
                    governance,
                    "average_actual_probability_delta",
                ),
                threshold=(
                    options.min_asian_handicap_segmented_model_quality_actual_probability_delta
                ),
                detail=(
                    "Asian-handicap governance should preserve actual-outcome probability"
                ),
            ),
        ]
    )
    return checks


def _asian_handicap_segmented_model_quality_governance_present_check(
    governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ),
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_asian_handicap_segmented_model_quality_governance:
        return _skipped_check(
            name="asian_handicap_segmented_model_quality_governance_present",
            actual=governance is not None,
            detail=(
                "Asian-handicap segmented model-quality governance evidence is optional"
            ),
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="asian_handicap_segmented_model_quality_governance_present",
        status="passed" if governance is not None else "failed",
        actual=governance is not None,
        threshold=True,
        detail=(
            "Asian-handicap segmented model-quality governance evidence must be "
            "attached before this benchmark gate can pass"
        ),
    )


def _asian_handicap_segmented_model_quality_governance_summary_fields(
    governance: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None
    ),
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if governance is None:
        return {
            "asian_handicap_segmented_model_quality_governance_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "asian_handicap_segmented_model_quality_governance_present": False,
            "asian_handicap_segmented_model_quality_governance_key": None,
            "asian_handicap_segmented_model_quality_governance_status": None,
            "asian_handicap_segmented_model_quality_governance_ready": None,
            "asian_handicap_segmented_model_quality_internal_only": None,
            "asian_handicap_segmented_model_quality_default_path_isolated": None,
            "asian_handicap_segmented_model_quality_production_allowed": None,
            "asian_handicap_segmented_model_quality_production_changed": None,
            "asian_handicap_segmented_model_quality_public_response_changed": None,
            "asian_handicap_segmented_model_quality_accepted_segment_count": 0,
            "asian_handicap_segmented_model_quality_shadow_segment_count": 0,
            "asian_handicap_segmented_model_quality_fallback_segment_count": 0,
            "asian_handicap_segmented_model_quality_rejected_segment_count": 0,
            "asian_handicap_segmented_model_quality_accepted_validation_count": 0,
            "asian_handicap_segmented_model_quality_calibration_applied_count": 0,
            "asian_handicap_segmented_model_quality_accepted_segment_ids": [],
            "asian_handicap_segmented_model_quality_fallback_segment_ids": [],
            "asian_handicap_segmented_model_quality_hit_rate_delta": None,
            "asian_handicap_segmented_model_quality_brier_score_delta": None,
            "asian_handicap_segmented_model_quality_log_loss_delta": None,
            "asian_handicap_segmented_model_quality_calibration_error_delta": None,
            "asian_handicap_segmented_model_quality_actual_probability_delta": None,
            "asian_handicap_segmented_model_quality_blockers": [],
            "asian_handicap_segmented_model_quality_warning_count": 0,
        }
    return {
        "asian_handicap_segmented_model_quality_governance_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "asian_handicap_segmented_model_quality_governance_present": True,
        "asian_handicap_segmented_model_quality_governance_key": governance.report_key,
        "asian_handicap_segmented_model_quality_governance_status": governance.status,
        "asian_handicap_segmented_model_quality_governance_ready": (
            governance.governance_review_ready
        ),
        "asian_handicap_segmented_model_quality_internal_only": (
            governance.internal_review_only
        ),
        "asian_handicap_segmented_model_quality_default_path_isolated": (
            governance.default_path_isolated
        ),
        "asian_handicap_segmented_model_quality_production_allowed": (
            governance.production_recommendation_allowed
        ),
        "asian_handicap_segmented_model_quality_production_changed": (
            governance.production_recommendation_changed
        ),
        "asian_handicap_segmented_model_quality_public_response_changed": (
            governance.public_response_changed
        ),
        "asian_handicap_segmented_model_quality_accepted_segment_count": (
            governance.accepted_segment_count
        ),
        "asian_handicap_segmented_model_quality_shadow_segment_count": (
            governance.shadow_segment_count
        ),
        "asian_handicap_segmented_model_quality_fallback_segment_count": (
            governance.fallback_segment_count
        ),
        "asian_handicap_segmented_model_quality_rejected_segment_count": (
            governance.rejected_segment_count
        ),
        "asian_handicap_segmented_model_quality_accepted_validation_count": (
            governance.accepted_validation_count
        ),
        "asian_handicap_segmented_model_quality_calibration_applied_count": (
            governance.calibration_sample_expansion_applied_count
        ),
        "asian_handicap_segmented_model_quality_accepted_segment_ids": (
            governance.accepted_segment_ids
        ),
        "asian_handicap_segmented_model_quality_fallback_segment_ids": (
            governance.fallback_segment_ids
        ),
        "asian_handicap_segmented_model_quality_hit_rate_delta": (
            _governance_delta(governance, "hit_rate_delta")
        ),
        "asian_handicap_segmented_model_quality_brier_score_delta": (
            _governance_delta(governance, "brier_score_delta")
        ),
        "asian_handicap_segmented_model_quality_log_loss_delta": (
            _governance_delta(governance, "log_loss_delta")
        ),
        "asian_handicap_segmented_model_quality_calibration_error_delta": (
            _governance_delta(governance, "expected_calibration_error_delta")
        ),
        "asian_handicap_segmented_model_quality_actual_probability_delta": (
            _governance_delta(governance, "average_actual_probability_delta")
        ),
        "asian_handicap_segmented_model_quality_blockers": governance.blockers,
        "asian_handicap_segmented_model_quality_warning_count": len(
            governance.warnings
        ),
    }


def _governance_delta(
    governance: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport,
    metric_name: str,
) -> float | None:
    value = governance.accepted_segment_deltas_json.get(metric_name)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _mapping_bool(mapping: dict[str, object], key: str) -> bool:
    return mapping.get(key) is True


def _prematch_feature_quality_cycle_checks(
    cycle: HistoricalPrematchFeatureQualityCycleResult | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _prematch_feature_quality_cycle_present_check(
            cycle,
            options=options,
        )
    ]
    if cycle is None:
        return checks
    required = options.require_prematch_feature_quality_cycle or not cycle.passed
    checks.extend(
        [
            _required_bool_check(
                name="prematch_feature_quality_cycle_passed",
                actual=cycle.passed,
                required=(
                    required
                    and options.require_prematch_feature_quality_cycle_passed
                ),
                detail="prematch feature quality cycle should pass",
            ),
            _required_bool_check(
                name="prematch_feature_quality_cycle_best_gate_passed",
                actual=cycle.best_quality_gate_passed,
                required=(
                    required
                    and options.require_prematch_feature_quality_cycle_best_gate_passed
                ),
                detail="best prematch feature final-answer candidate gate should pass",
            ),
            _check_minimum(
                name="prematch_feature_quality_cycle_slice_count",
                actual=cycle.slice_count,
                threshold=options.min_prematch_feature_quality_cycle_slice_count,
                detail="prematch feature quality cycle should cover enough slices",
            ),
            _check_minimum(
                name="prematch_feature_quality_cycle_fixture_count",
                actual=cycle.fixture_count,
                threshold=options.min_prematch_feature_quality_cycle_fixture_count,
                detail="prematch feature quality cycle should cover enough fixtures",
            ),
            _check_minimum(
                name="prematch_feature_quality_cycle_evaluated_candidate_count",
                actual=cycle.evaluated_candidate_count,
                threshold=(
                    options.min_prematch_feature_quality_cycle_evaluated_candidate_count
                ),
                detail="prematch feature quality cycle should evaluate candidates",
            ),
            _check_minimum(
                name="prematch_feature_quality_cycle_passing_candidate_count",
                actual=cycle.passing_candidate_count,
                threshold=(
                    options.min_prematch_feature_quality_cycle_passing_candidate_count
                ),
                detail="prematch feature quality cycle should keep passing candidates",
            ),
            _check_optional_maximum(
                name="prematch_feature_quality_cycle_warning_count",
                actual=len(cycle.warnings),
                threshold=options.max_prematch_feature_quality_cycle_warning_count,
                detail="prematch feature quality cycle warnings should stay bounded",
            ),
            _check_optional_maximum(
                name="prematch_feature_quality_cycle_best_brier_score_delta",
                actual=_summary_float(cycle.best_deltas_json, "brier_score_delta"),
                threshold=(
                    options.max_prematch_feature_quality_cycle_best_brier_score_delta
                ),
                detail="best prematch feature candidate should not regress Brier",
            ),
            _check_optional_maximum(
                name="prematch_feature_quality_cycle_best_log_loss_delta",
                actual=_summary_float(cycle.best_deltas_json, "log_loss_delta"),
                threshold=(
                    options.max_prematch_feature_quality_cycle_best_log_loss_delta
                ),
                detail="best prematch feature candidate should not regress log loss",
            ),
            _check_optional_maximum(
                name="prematch_feature_quality_cycle_best_calibration_error_delta",
                actual=_summary_float(
                    cycle.best_deltas_json,
                    "mean_calibration_error_delta",
                ),
                threshold=(
                    options.max_prematch_feature_quality_cycle_best_calibration_error_delta
                ),
                detail=(
                    "best prematch feature candidate should not regress "
                    "calibration error"
                ),
            ),
        ]
    )
    return checks


def _prematch_feature_quality_cycle_present_check(
    cycle: HistoricalPrematchFeatureQualityCycleResult | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_prematch_feature_quality_cycle:
        return _skipped_check(
            name="prematch_feature_quality_cycle_present",
            actual=cycle is not None,
            detail="prematch feature quality-cycle evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="prematch_feature_quality_cycle_present",
        status="passed" if cycle is not None else "failed",
        actual=cycle is not None,
        threshold=True,
        detail=(
            "prematch feature quality-cycle evidence must be attached before "
            "this benchmark gate can pass"
        ),
    )


def _prematch_feature_quality_cycle_summary_fields(
    cycle: HistoricalPrematchFeatureQualityCycleResult | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if cycle is None:
        return {
            "prematch_feature_quality_cycle_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "prematch_feature_quality_cycle_present": False,
            "prematch_feature_quality_cycle_key": None,
            "prematch_feature_quality_cycle_status": None,
            "prematch_feature_quality_cycle_passed": None,
            "prematch_feature_quality_cycle_final_answer_gate_key": None,
            "prematch_feature_quality_cycle_grid_key": None,
            "prematch_feature_quality_cycle_slice_count": 0,
            "prematch_feature_quality_cycle_fixture_count": 0,
            "prematch_feature_quality_cycle_evaluated_candidate_count": 0,
            "prematch_feature_quality_cycle_passing_candidate_count": 0,
            "prematch_feature_quality_cycle_best_feature_grid_candidate_id": None,
            "prematch_feature_quality_cycle_best_feature_grid_rank": 0,
            "prematch_feature_quality_cycle_best_gate_passed": None,
            "prematch_feature_quality_cycle_best_suite_status": None,
            "prematch_feature_quality_cycle_best_brier_score_delta": None,
            "prematch_feature_quality_cycle_best_log_loss_delta": None,
            "prematch_feature_quality_cycle_best_calibration_error_delta": None,
            "prematch_feature_quality_cycle_best_failed_quality_check_names": [],
            "prematch_feature_quality_cycle_warning_count": 0,
            "prematch_feature_quality_cycle_warnings": [],
        }
    return {
        "prematch_feature_quality_cycle_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "prematch_feature_quality_cycle_present": True,
        "prematch_feature_quality_cycle_key": cycle.cycle_key,
        "prematch_feature_quality_cycle_status": cycle.status,
        "prematch_feature_quality_cycle_passed": cycle.passed,
        "prematch_feature_quality_cycle_final_answer_gate_key": (
            cycle.final_answer_gate_report_key
        ),
        "prematch_feature_quality_cycle_final_answer_gate_report_path": (
            str(cycle.final_answer_gate_report_path)
            if cycle.final_answer_gate_report_path is not None
            else None
        ),
        "prematch_feature_quality_cycle_grid_key": cycle.grid_report_key,
        "prematch_feature_quality_cycle_slice_count": cycle.slice_count,
        "prematch_feature_quality_cycle_fixture_count": cycle.fixture_count,
        "prematch_feature_quality_cycle_evaluated_candidate_count": (
            cycle.evaluated_candidate_count
        ),
        "prematch_feature_quality_cycle_passing_candidate_count": (
            cycle.passing_candidate_count
        ),
        "prematch_feature_quality_cycle_best_feature_grid_candidate_id": (
            cycle.best_feature_grid_candidate_id
        ),
        "prematch_feature_quality_cycle_best_feature_grid_rank": (
            cycle.best_feature_grid_rank
        ),
        "prematch_feature_quality_cycle_best_gate_passed": (
            cycle.best_quality_gate_passed
        ),
        "prematch_feature_quality_cycle_best_suite_status": cycle.best_suite_status,
        "prematch_feature_quality_cycle_best_brier_score_delta": _summary_float(
            cycle.best_deltas_json,
            "brier_score_delta",
        ),
        "prematch_feature_quality_cycle_best_log_loss_delta": _summary_float(
            cycle.best_deltas_json,
            "log_loss_delta",
        ),
        "prematch_feature_quality_cycle_best_calibration_error_delta": _summary_float(
            cycle.best_deltas_json,
            "mean_calibration_error_delta",
        ),
        "prematch_feature_quality_cycle_best_failed_quality_check_names": (
            cycle.best_failed_quality_check_names
        ),
        "prematch_feature_quality_cycle_warning_count": len(cycle.warnings),
        "prematch_feature_quality_cycle_warnings": cycle.warnings,
    }


def _prematch_feature_rolling_admission_checks(
    admission: HistoricalPrematchFeatureRollingAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _prematch_feature_rolling_admission_present_check(
            admission,
            options=options,
        )
    ]
    if admission is None:
        return checks
    required = (
        options.require_prematch_feature_rolling_admission
        or admission.status != "accepted"
    )
    checks.extend(
        [
            _required_bool_check(
                name="prematch_feature_rolling_admission_accepted",
                actual=admission.status == "accepted",
                required=required,
                detail="prematch feature rolling admission should be accepted",
            ),
            _required_bool_check(
                name="prematch_feature_rolling_admission_candidate_allowed",
                actual=admission.candidate_feature_allowed,
                required=(
                    required
                    and options.require_prematch_feature_rolling_admission_candidate_allowed
                ),
                detail=(
                    "prematch feature admission should allow a staged feature "
                    "candidate"
                ),
            ),
            _required_bool_check(
                name="prematch_feature_rolling_admission_shadow_allowed",
                actual=admission.shadow_allowed,
                required=required,
                detail="prematch feature admission should remain shadow-allowed",
            ),
            _required_bool_check(
                name="prematch_feature_rolling_admission_overall_gate_passed",
                actual=admission.overall_fold.passed_final_answer_gate,
                required=required,
                detail="overall prematch feature final-answer gate should pass",
            ),
            _check_minimum(
                name=(
                    "prematch_feature_rolling_admission_overall_evaluated_candidate_count"
                ),
                actual=admission.overall_fold.evaluated_candidate_count,
                threshold=(
                    options.min_prematch_feature_rolling_admission_overall_evaluated_candidate_count
                ),
                detail="overall prematch feature admission should evaluate candidates",
            ),
            _check_minimum(
                name=(
                    "prematch_feature_rolling_admission_overall_passing_candidate_count"
                ),
                actual=admission.overall_fold.passing_candidate_count,
                threshold=(
                    options.min_prematch_feature_rolling_admission_overall_passing_candidate_count
                ),
                detail="overall prematch feature admission should keep passing candidates",
            ),
            _check_optional_maximum(
                name="prematch_feature_rolling_admission_failed_fold_count",
                actual=admission.failed_fold_count,
                threshold=(
                    options.max_prematch_feature_rolling_admission_failed_fold_count
                ),
                detail="prematch feature admission should not fail active folds",
            ),
            _check_minimum(
                name="prematch_feature_rolling_admission_active_competition_fold_count",
                actual=admission.active_competition_fold_count,
                threshold=(
                    options.min_prematch_feature_rolling_admission_active_competition_fold_count
                ),
                detail="prematch feature admission should validate competition folds",
            ),
            _check_minimum(
                name=(
                    "prematch_feature_rolling_admission_active_season_cutoff_fold_count"
                ),
                actual=admission.active_season_cutoff_fold_count,
                threshold=(
                    options.min_prematch_feature_rolling_admission_active_season_cutoff_fold_count
                ),
                detail="prematch feature admission should validate season cutoffs",
            ),
            _check_minimum(
                name="prematch_feature_rolling_admission_active_rolling_fold_count",
                actual=admission.active_rolling_fold_count,
                threshold=(
                    options.min_prematch_feature_rolling_admission_active_rolling_fold_count
                ),
                detail="prematch feature admission should validate rolling folds",
            ),
            _check_optional_maximum(
                name="prematch_feature_rolling_admission_overall_brier_score_delta",
                actual=admission.overall_fold.brier_score_delta,
                threshold=(
                    options.max_prematch_feature_rolling_admission_overall_brier_score_delta
                ),
                detail="overall prematch feature admission should not regress Brier",
            ),
            _check_optional_maximum(
                name="prematch_feature_rolling_admission_overall_log_loss_delta",
                actual=admission.overall_fold.log_loss_delta,
                threshold=(
                    options.max_prematch_feature_rolling_admission_overall_log_loss_delta
                ),
                detail="overall prematch feature admission should not regress log loss",
            ),
            _check_optional_maximum(
                name="prematch_feature_rolling_admission_overall_calibration_error_delta",
                actual=admission.overall_fold.mean_calibration_error_delta,
                threshold=(
                    options.max_prematch_feature_rolling_admission_overall_calibration_error_delta
                ),
                detail=(
                    "overall prematch feature admission should not regress "
                    "calibration error"
                ),
            ),
        ]
    )
    return checks


def _prematch_feature_rolling_admission_present_check(
    admission: HistoricalPrematchFeatureRollingAdmissionReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_prematch_feature_rolling_admission:
        return _skipped_check(
            name="prematch_feature_rolling_admission_present",
            actual=admission is not None,
            detail="prematch feature rolling-admission evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="prematch_feature_rolling_admission_present",
        status="passed" if admission is not None else "failed",
        actual=admission is not None,
        threshold=True,
        detail=(
            "prematch feature rolling-admission evidence must be attached before "
            "this benchmark gate can pass"
        ),
    )


def _prematch_feature_rolling_admission_summary_fields(
    admission: HistoricalPrematchFeatureRollingAdmissionReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if admission is None:
        return {
            "prematch_feature_rolling_admission_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "prematch_feature_rolling_admission_present": False,
            "prematch_feature_rolling_admission_key": None,
            "prematch_feature_rolling_admission_status": None,
            "prematch_feature_rolling_admission_candidate_allowed": None,
            "prematch_feature_rolling_admission_shadow_allowed": None,
            "prematch_feature_rolling_admission_source_grid_key": None,
            "prematch_feature_rolling_admission_overall_gate_key": None,
            "prematch_feature_rolling_admission_overall_gate_passed": None,
            "prematch_feature_rolling_admission_overall_evaluated_candidate_count": 0,
            "prematch_feature_rolling_admission_overall_passing_candidate_count": 0,
            "prematch_feature_rolling_admission_overall_adjusted_fixture_count": 0,
            "prematch_feature_rolling_admission_best_feature_grid_candidate_id": None,
            "prematch_feature_rolling_admission_best_feature_grid_rank": 0,
            "prematch_feature_rolling_admission_best_gate_passed": None,
            "prematch_feature_rolling_admission_best_suite_status": None,
            "prematch_feature_rolling_admission_failed_fold_count": 0,
            "prematch_feature_rolling_admission_active_competition_fold_count": 0,
            "prematch_feature_rolling_admission_active_season_cutoff_fold_count": 0,
            "prematch_feature_rolling_admission_active_rolling_fold_count": 0,
            "prematch_feature_rolling_admission_overall_final_hit_rate_delta": None,
            "prematch_feature_rolling_admission_overall_roi_delta": None,
            "prematch_feature_rolling_admission_overall_profit_loss_delta": None,
            "prematch_feature_rolling_admission_overall_brier_score_delta": None,
            "prematch_feature_rolling_admission_overall_log_loss_delta": None,
            "prematch_feature_rolling_admission_overall_calibration_error_delta": None,
            "prematch_feature_rolling_admission_failed_checks": [],
            "prematch_feature_rolling_admission_warning_count": 0,
            "prematch_feature_rolling_admission_warnings": [],
        }
    return {
        "prematch_feature_rolling_admission_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "prematch_feature_rolling_admission_present": True,
        "prematch_feature_rolling_admission_key": admission.report_key,
        "prematch_feature_rolling_admission_status": admission.status,
        "prematch_feature_rolling_admission_candidate_allowed": (
            admission.candidate_feature_allowed
        ),
        "prematch_feature_rolling_admission_shadow_allowed": admission.shadow_allowed,
        "prematch_feature_rolling_admission_source_grid_key": (
            admission.source_grid_report_key
        ),
        "prematch_feature_rolling_admission_overall_gate_key": (
            admission.overall_gate_report_key
        ),
        "prematch_feature_rolling_admission_overall_gate_passed": (
            admission.overall_fold.passed_final_answer_gate
        ),
        "prematch_feature_rolling_admission_overall_evaluated_candidate_count": (
            admission.overall_fold.evaluated_candidate_count
        ),
        "prematch_feature_rolling_admission_overall_passing_candidate_count": (
            admission.overall_fold.passing_candidate_count
        ),
        "prematch_feature_rolling_admission_overall_adjusted_fixture_count": (
            admission.overall_fold.adjusted_fixture_count
        ),
        "prematch_feature_rolling_admission_best_feature_grid_candidate_id": (
            admission.overall_fold.best_feature_grid_candidate_id
        ),
        "prematch_feature_rolling_admission_best_feature_grid_rank": (
            admission.overall_fold.best_feature_grid_rank or 0
        ),
        "prematch_feature_rolling_admission_best_gate_passed": (
            admission.overall_fold.best_quality_gate_passed
        ),
        "prematch_feature_rolling_admission_best_suite_status": (
            admission.overall_fold.best_suite_status
        ),
        "prematch_feature_rolling_admission_failed_fold_count": (
            admission.failed_fold_count
        ),
        "prematch_feature_rolling_admission_active_competition_fold_count": (
            admission.active_competition_fold_count
        ),
        "prematch_feature_rolling_admission_active_season_cutoff_fold_count": (
            admission.active_season_cutoff_fold_count
        ),
        "prematch_feature_rolling_admission_active_rolling_fold_count": (
            admission.active_rolling_fold_count
        ),
        "prematch_feature_rolling_admission_overall_final_hit_rate_delta": (
            admission.overall_fold.final_hit_rate_delta
        ),
        "prematch_feature_rolling_admission_overall_roi_delta": (
            admission.overall_fold.roi_delta
        ),
        "prematch_feature_rolling_admission_overall_profit_loss_delta": (
            admission.overall_fold.profit_loss_delta
        ),
        "prematch_feature_rolling_admission_overall_brier_score_delta": (
            admission.overall_fold.brier_score_delta
        ),
        "prematch_feature_rolling_admission_overall_log_loss_delta": (
            admission.overall_fold.log_loss_delta
        ),
        "prematch_feature_rolling_admission_overall_calibration_error_delta": (
            admission.overall_fold.mean_calibration_error_delta
        ),
        "prematch_feature_rolling_admission_failed_checks": [
            check.name for check in admission.checks if check.status == "failed"
        ],
        "prematch_feature_rolling_admission_warning_count": len(admission.warnings),
        "prematch_feature_rolling_admission_warnings": admission.warnings,
    }


def _prematch_feature_sample_readiness_checks(
    readiness: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> list[RecommendationBenchmarkQualityGateCheck]:
    checks = [
        _prematch_feature_sample_readiness_present_check(
            readiness,
            options=options,
        )
    ]
    if readiness is None:
        return checks
    required = (
        options.require_prematch_feature_sample_readiness
        or readiness.status != "accepted"
    )
    checks.extend(
        [
            _required_bool_check(
                name="prematch_feature_sample_readiness_accepted",
                actual=readiness.status == "accepted",
                required=required,
                detail="prematch feature sample readiness should be accepted",
            ),
            _required_bool_check(
                name="prematch_feature_sample_ready_allowed",
                actual=readiness.sample_ready_allowed,
                required=(
                    required
                    and options.require_prematch_feature_sample_ready_allowed
                ),
                detail="prematch feature sample readiness should allow learning",
            ),
            _required_bool_check(
                name="prematch_feature_sample_readiness_shadow_allowed",
                actual=readiness.shadow_allowed,
                required=required,
                detail="prematch feature sample readiness should remain shadow-allowed",
            ),
            _check_minimum(
                name="prematch_feature_sample_ready_source_count",
                actual=readiness.accepted_source_count,
                threshold=options.min_prematch_feature_sample_ready_source_count,
                detail="sample readiness should have enough accepted sources",
            ),
            _check_minimum(
                name="prematch_feature_sample_ready_fixture_count",
                actual=readiness.ready_fixture_count,
                threshold=options.min_prematch_feature_sample_ready_fixture_count,
                detail="sample readiness should have enough accepted fixtures",
            ),
            _check_minimum(
                name="prematch_feature_sample_ready_competition_count",
                actual=readiness.ready_competition_count,
                threshold=options.min_prematch_feature_sample_ready_competition_count,
                detail="sample readiness should cover enough competitions",
            ),
            _check_minimum(
                name="prematch_feature_sample_ready_season_count",
                actual=readiness.ready_season_count,
                threshold=options.min_prematch_feature_sample_ready_season_count,
                detail="sample readiness should cover enough seasons",
            ),
            _check_minimum(
                name="prematch_feature_sample_ready_competition_season_count",
                actual=readiness.ready_competition_season_count,
                threshold=(
                    options.min_prematch_feature_sample_ready_competition_season_count
                ),
                detail="sample readiness should cover enough competition-season cells",
            ),
            _check_optional_maximum(
                name="prematch_feature_sample_readiness_warning_count",
                actual=len(readiness.warnings),
                threshold=options.max_prematch_feature_sample_readiness_warning_count,
                detail="sample readiness warning count should stay bounded",
            ),
        ]
    )
    return checks


def _prematch_feature_sample_readiness_present_check(
    readiness: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    if not options.require_prematch_feature_sample_readiness:
        return _skipped_check(
            name="prematch_feature_sample_readiness_present",
            actual=readiness is not None,
            detail="prematch feature sample-readiness evidence is optional",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="prematch_feature_sample_readiness_present",
        status="passed" if readiness is not None else "failed",
        actual=readiness is not None,
        threshold=True,
        detail=(
            "prematch feature sample-readiness evidence must be attached before "
            "this benchmark gate can pass"
        ),
    )


def _prematch_feature_sample_readiness_summary_fields(
    readiness: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    report_path: Path | None,
) -> dict[str, object]:
    if readiness is None:
        return {
            "prematch_feature_sample_readiness_report_path": (
                str(report_path) if report_path is not None else None
            ),
            "prematch_feature_sample_readiness_present": False,
            "prematch_feature_sample_readiness_key": None,
            "prematch_feature_sample_readiness_status": None,
            "prematch_feature_sample_readiness_target_profile": None,
            "prematch_feature_sample_ready_allowed": None,
            "prematch_feature_sample_readiness_shadow_allowed": None,
            "prematch_feature_sample_readiness_coverage_audit_key": None,
            "prematch_feature_sample_ready_source_count": 0,
            "prematch_feature_sample_ready_fixture_count": 0,
            "prematch_feature_sample_ready_slice_count": 0,
            "prematch_feature_sample_ready_competition_count": 0,
            "prematch_feature_sample_ready_season_count": 0,
            "prematch_feature_sample_ready_competition_season_count": 0,
            "prematch_feature_sample_readiness_failed_checks": [],
            "prematch_feature_sample_readiness_warning_count": 0,
            "prematch_feature_sample_readiness_warnings": [],
        }
    return {
        "prematch_feature_sample_readiness_report_path": (
            str(report_path) if report_path is not None else None
        ),
        "prematch_feature_sample_readiness_present": True,
        "prematch_feature_sample_readiness_key": readiness.readiness_key,
        "prematch_feature_sample_readiness_status": readiness.status,
        "prematch_feature_sample_readiness_target_profile": readiness.target_profile,
        "prematch_feature_sample_ready_allowed": readiness.sample_ready_allowed,
        "prematch_feature_sample_readiness_shadow_allowed": readiness.shadow_allowed,
        "prematch_feature_sample_readiness_coverage_audit_key": (
            readiness.coverage_audit_key
        ),
        "prematch_feature_sample_ready_source_count": readiness.accepted_source_count,
        "prematch_feature_sample_ready_fixture_count": readiness.ready_fixture_count,
        "prematch_feature_sample_ready_slice_count": readiness.ready_slice_count,
        "prematch_feature_sample_ready_competition_count": (
            readiness.ready_competition_count
        ),
        "prematch_feature_sample_ready_season_count": readiness.ready_season_count,
        "prematch_feature_sample_ready_competition_season_count": (
            readiness.ready_competition_season_count
        ),
        "prematch_feature_sample_readiness_failed_checks": [
            check.name for check in readiness.checks if check.status == "failed"
        ],
        "prematch_feature_sample_readiness_warning_count": len(readiness.warnings),
        "prematch_feature_sample_readiness_warnings": readiness.warnings,
    }


def _scope_int(scope: dict[str, object], key: str) -> int:
    value = scope.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _scope_bool(scope: dict[str, object], key: str) -> bool:
    value = scope.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "passed"}
    return False


def _scope_list(scope: dict[str, object], key: str) -> list[object]:
    value = scope.get(key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return []


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Evaluate persisted Nutmeg recommendation benchmark quality gates."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--benchmark-key", default=None)
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default=None,
    )
    parser.add_argument("--history-limit", type=int, default=2)
    parser.add_argument("--allow-missing-history", action="store_true")
    parser.add_argument("--min-scenario-count", type=int, default=1)
    parser.add_argument("--min-completed-ratio", type=float, default=1.0)
    parser.add_argument("--max-failed-count", type=int, default=0)
    parser.add_argument("--max-warning-count", type=int, default=None)
    parser.add_argument("--min-global-best-selected-count", type=int, default=0)
    parser.add_argument("--min-global-best-candidate-count", type=int, default=0)
    parser.add_argument(
        "--min-global-best-generated-option-count",
        type=int,
        default=0,
    )
    parser.add_argument("--min-core-replay-ready-ratio", type=float, default=None)
    parser.add_argument("--min-chain-integrity-ready-ratio", type=float, default=None)
    parser.add_argument(
        "--max-chain-integrity-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-successor-chain-evaluation-passed-ratio",
        type=float,
        default=None,
    )
    parser.add_argument("--min-successor-chain-effective-leaf-count", type=int, default=0)
    parser.add_argument("--max-successor-chain-critical-issue-count", type=int, default=0)
    parser.add_argument("--max-successor-chain-ambiguous-source-count", type=int, default=0)
    parser.add_argument(
        "--max-successor-chain-source-status-sync-required-count",
        type=int,
        default=None,
    )
    parser.add_argument("--max-ambiguous-successor-source-count", type=int, default=0)
    parser.add_argument("--max-stale-recommendation-count", type=int, default=0)
    parser.add_argument("--max-successor-recompute-required-count", type=int, default=0)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=0)
    parser.add_argument("--min-final-hit-coverage-ratio", type=float, default=None)
    parser.add_argument("--min-final-hit-rate", type=float, default=None)
    parser.add_argument("--min-average-core-replay-roi", type=float, default=None)
    parser.add_argument("--min-upset-capture-sample-size", type=int, default=0)
    parser.add_argument("--min-upset-capture-rate", type=float, default=None)
    parser.add_argument(
        "--historical-suite-quality-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument("--require-historical-suite-quality-gate", action="store_true")
    parser.add_argument(
        "--allow-missing-historical-suite-lifecycle-evidence",
        action="store_true",
    )
    parser.add_argument(
        "--allow-unsynced-historical-suite-lifecycle-source-status",
        action="store_true",
    )
    parser.add_argument(
        "--require-historical-suite-successor-chain-evaluation",
        action="store_true",
    )
    parser.add_argument("--min-historical-suite-slice-count", type=int, default=0)
    parser.add_argument("--min-historical-suite-comparison-count", type=int, default=0)
    parser.add_argument(
        "--min-historical-suite-candidate-final-hit-sample-size",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-final-hit-coverage-ratio",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-dynamic-mixed-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-handicap-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-correct-score-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-candidate-multiple-choice-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument("--max-historical-suite-failed-check-count", type=int, default=0)
    parser.add_argument(
        "--min-historical-suite-lifecycle-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-lifecycle-active-edge-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-historical-suite-lifecycle-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-historical-suite-lifecycle-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-successor-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-successor-active-edge-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-historical-suite-successor-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-historical-suite-successor-ambiguous-source-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-historical-suite-successor-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--require-historical-suite-market-movement-runtime-replay",
        action="store_true",
    )
    parser.add_argument(
        "--allow-historical-suite-market-movement-runtime-replay-not-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--allow-historical-suite-market-movement-runtime-replay-non-passed-status",
        action="store_true",
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-selected-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-accepted-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-historical-suite-market-movement-runtime-replay-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-historical-suite-market-movement-runtime-replay-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-historical-suite-market-movement-runtime-replay-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-historical-suite-market-movement-runtime-replay-calibration-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--allow-historical-suite-market-movement-runtime-replay-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-historical-suite-market-movement-runtime-replay-public-change",
        action="store_true",
    )
    parser.add_argument("--budget-stability-audit-report-path", type=Path, default=None)
    parser.add_argument("--require-budget-stability-audit", action="store_true")
    parser.add_argument("--min-budget-stability-slice-count", type=int, default=0)
    parser.add_argument("--min-budget-stability-comparable-count", type=int, default=0)
    parser.add_argument(
        "--max-budget-stability-signature-change-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--max-budget-stability-harmful-change-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--min-budget-stability-hit-delta-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--min-budget-stability-profit-loss-delta",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-budget-stability-roi-delta",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--max-budget-stability-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--final-answer-market-concentration-audit-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-final-answer-market-concentration-audit",
        action="store_true",
    )
    parser.add_argument(
        "--min-final-answer-market-concentration-slice-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-final-answer-market-concentration-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-final-answer-market-concentration-effective-constraint-profile-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-final-answer-market-concentration-failed-check-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-final-answer-market-concentration-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--correct-score-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument("--require-correct-score-admission", action="store_true")
    parser.add_argument(
        "--allow-correct-score-admission-holdout-not-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--require-correct-score-admission-production-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--min-correct-score-admission-slice-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-correct-score-admission-comparison-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-final-hit-sample-size",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-final-hit-coverage-ratio",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-final-hit-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-roi",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-correct-score-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-correct-score-admission-candidate-correct-score-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-correct-score-admission-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-correct-score-admission-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-correct-score-admission-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-correct-score-admission-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-correct-score-admission-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-correct-score-admission-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-correct-score-admission-failed-check-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-correct-score-admission-warning-count",
        type=int,
        default=None,
    )
    parser.add_argument("--require-unified-candidate-pool", action="store_true")
    parser.add_argument(
        "--min-unified-candidate-pool-present-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-unified-candidate-pool-valid-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-unified-candidate-pool-unique-family-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-unified-candidate-pool-selection-mismatch-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-unified-candidate-pool-selected-2x1-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--require-unified-candidate-pool-multiple-value-admission",
        action="store_true",
    )
    parser.add_argument(
        "--min-unified-candidate-pool-multiple-value-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-unified-candidate-pool-multiple-value-admitted-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-unified-candidate-pool-multiple-value-extra-option-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-unified-candidate-pool-multiple-value-rejected-candidate-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-unified-candidate-pool-selected-multiple-value-rejected-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--unified-candidate-pool-guard-preset",
        choices=UNIFIED_CANDIDATE_POOL_GUARD_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--runtime-profile-switch-preset",
        choices=RUNTIME_PROFILE_SWITCH_PRESETS,
        default=None,
    )
    parser.add_argument("--runtime-profile-switch-report-path", type=Path, default=None)
    parser.add_argument(
        "--runtime-profile-switch-replay-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument("--require-runtime-profile-switch-gate", action="store_true")
    parser.add_argument(
        "--allow-missing-runtime-profile-switch-replay",
        action="store_true",
    )
    parser.add_argument("--allow-runtime-profile-switch-applied", action="store_true")
    parser.add_argument("--min-runtime-profile-switch-rule-count", type=int, default=1)
    parser.add_argument(
        "--min-runtime-profile-switch-allowed-competition-count",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--min-runtime-profile-switch-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--min-runtime-profile-switch-changed-final-answer-count",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--min-runtime-profile-switch-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-runtime-profile-switch-roi-delta", type=float, default=0.0)
    parser.add_argument(
        "--min-runtime-profile-switch-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-runtime-profile-switch-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-runtime-profile-switch-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-runtime-profile-switch-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-runtime-profile-switch-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--final-answer-segment-penalty-runtime-replay-preset",
        choices=FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--final-answer-segment-penalty-runtime-replay-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-final-answer-segment-penalty-runtime-replay",
        action="store_true",
    )
    parser.add_argument(
        "--allow-missing-final-answer-segment-penalty-runtime-replay-holdout",
        action="store_true",
    )
    parser.add_argument(
        "--require-final-answer-segment-penalty-runtime-replay-runtime-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-changed-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-penalty-option-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-hit-count-delta",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-final-answer-segment-penalty-runtime-replay-candidate-roi",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-final-hit-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-final-answer-segment-penalty-runtime-replay-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--allow-final-answer-segment-penalty-runtime-replay-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-final-answer-segment-penalty-runtime-replay-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--market-movement-runtime-activation-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-market-movement-runtime-activation",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-selected-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-activation-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-activation-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-activation-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-activation-calibration-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-default-profile-write",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-default-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--market-movement-runtime-activation-sample-expansion-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-market-movement-runtime-activation-sample-expansion",
        action="store_true",
    )
    parser.add_argument(
        "--require-market-movement-runtime-activation-sample-expansion-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--market-movement-runtime-activation-segment-replay-batch-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-market-movement-runtime-activation-segment-replay-batch-gate",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-activation-segment-replay-batch-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--require-market-movement-runtime-activation-segment-replay-batch-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-segment-replay-batch-report-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-segment-replay-batch-passed-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-segment-replay-batch-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-activation-segment-replay-batch-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--replacement-reranker-shadow-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-replacement-reranker-shadow-admission",
        action="store_true",
    )
    parser.add_argument(
        "--allow-replacement-reranker-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--require-replacement-reranker-scoped-evidence",
        action="store_true",
    )
    parser.add_argument(
        "--require-replacement-reranker-prematch-source-surface",
        action="store_true",
    )
    parser.add_argument(
        "--min-replacement-reranker-scope-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-shadow-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-changed-from-model-top-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-replacement-reranker-roi-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-replacement-reranker-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-replacement-reranker-final-hit-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-replacement-reranker-profit-loss-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-replacement-reranker-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-active-competition-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-active-season-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-reranker-active-rolling-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--global-planner-short-odds-adapter-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-global-planner-short-odds-adapter-gate",
        action="store_true",
    )
    parser.add_argument(
        "--allow-global-planner-short-odds-adapter-default-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-global-planner-short-odds-adapter-shadow-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-global-planner-short-odds-adapter-missing-explicit-opt-in-change",
        action="store_true",
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-changed-final-answer-count",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-global-planner-short-odds-adapter-runtime-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-global-planner-short-odds-adapter-runtime-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-global-planner-short-odds-adapter-runtime-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-global-planner-short-odds-adapter-runtime-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--allow-global-planner-short-odds-adapter-runtime-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-global-planner-short-odds-adapter-runtime-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--global-planner-short-odds-adapter-sample-expansion-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-global-planner-short-odds-adapter-sample-expansion",
        action="store_true",
    )
    parser.add_argument(
        "--require-global-planner-short-odds-adapter-sample-expansion-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--recommendation-strategy-governance-preset",
        choices=RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--recommendation-strategy-promotion-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-recommendation-strategy-promotion-gate",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-gate-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--min-recommendation-strategy-gate-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--min-recommendation-strategy-gate-changed-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-recommendation-strategy-gate-hit-delta-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-recommendation-strategy-gate-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-recommendation-strategy-gate-minimum-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-recommendation-strategy-gate-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-recommendation-strategy-gate-final-hit-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-recommendation-strategy-gate-profit-loss-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--allow-recommendation-strategy-gate-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-gate-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--recommendation-strategy-staged-activation-smoke-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-recommendation-strategy-staged-activation-smoke",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-staged-activation-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-staged-default-write",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-staged-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-staged-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--min-recommendation-strategy-staged-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-recommendation-strategy-staged-allowed-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--recommendation-strategy-default-path-isolation-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-recommendation-strategy-default-path-isolation",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-default-path-not-isolated",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-default-adapter-enabled",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-default-adapter-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-missing-explicit-opt-in",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-isolation-default-write",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-isolation-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-recommendation-strategy-isolation-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--probability-calibration-profile-rolling-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-probability-calibration-profile-rolling-admission",
        action="store_true",
    )
    parser.add_argument(
        "--allow-probability-calibration-profile-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--allow-probability-calibration-profile-non-active-profile",
        action="store_true",
    )
    parser.add_argument(
        "--min-probability-calibration-profile-overall-adjusted-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-overall-bucket-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-active-season-cutoff-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-active-rolling-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--probability-calibration-profile-model-quality-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-probability-calibration-profile-model-quality-gate",
        action="store_true",
    )
    parser.add_argument(
        "--allow-probability-calibration-profile-model-quality-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-selected-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-adjusted-slice-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-adjusted-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-model-quality-skipped-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-model-quality-final-answer-changed-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-final-answer-hit-count-delta",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-probability-calibration-profile-model-quality-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-model-quality-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-model-quality-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-probability-calibration-profile-model-quality-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--asian-handicap-segmented-model-quality-governance-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-asian-handicap-segmented-model-quality-governance",
        action="store_true",
    )
    parser.add_argument(
        "--allow-asian-handicap-segmented-model-quality-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--allow-asian-handicap-segmented-model-quality-non-internal",
        action="store_true",
    )
    parser.add_argument(
        "--allow-asian-handicap-segmented-model-quality-default-path-not-isolated",
        action="store_true",
    )
    parser.add_argument(
        "--allow-asian-handicap-segmented-model-quality-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-asian-handicap-segmented-model-quality-public-response-change",
        action="store_true",
    )
    parser.add_argument(
        "--min-asian-handicap-segmented-model-quality-accepted-segment-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-shadow-segment-count",
        type=int,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-fallback-segment-count",
        type=int,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-rejected-segment-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-asian-handicap-segmented-model-quality-accepted-validation-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-asian-handicap-segmented-model-quality-calibration-applied-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-asian-handicap-segmented-model-quality-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-asian-handicap-segmented-model-quality-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-asian-handicap-segmented-model-quality-actual-probability-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-quality-cycle-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-prematch-feature-quality-cycle",
        action="store_true",
    )
    parser.add_argument(
        "--allow-failed-prematch-feature-quality-cycle",
        action="store_true",
    )
    parser.add_argument(
        "--allow-prematch-feature-quality-cycle-best-gate-failed",
        action="store_true",
    )
    parser.add_argument(
        "--min-prematch-feature-quality-cycle-slice-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-quality-cycle-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-quality-cycle-evaluated-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-quality-cycle-passing-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-prematch-feature-quality-cycle-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-prematch-feature-quality-cycle-best-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-prematch-feature-quality-cycle-best-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-prematch-feature-quality-cycle-best-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-rolling-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-prematch-feature-rolling-admission",
        action="store_true",
    )
    parser.add_argument(
        "--allow-prematch-feature-rolling-admission-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--min-prematch-feature-rolling-admission-overall-evaluated-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-rolling-admission-overall-passing-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-prematch-feature-rolling-admission-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-prematch-feature-rolling-admission-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-rolling-admission-active-season-cutoff-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-rolling-admission-active-rolling-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-prematch-feature-rolling-admission-overall-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-prematch-feature-rolling-admission-overall-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-prematch-feature-rolling-admission-overall-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-sample-readiness-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-prematch-feature-sample-readiness",
        action="store_true",
    )
    parser.add_argument(
        "--allow-prematch-feature-sample-readiness-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--min-prematch-feature-sample-ready-source-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-sample-ready-fixture-count",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--min-prematch-feature-sample-ready-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-sample-ready-season-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-prematch-feature-sample-ready-competition-season-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-prematch-feature-sample-readiness-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument("--fail-on-history-statuses", default="regressed")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkQualityGateOptions:
    options = RecommendationBenchmarkQualityGateOptions(
        benchmark_key=args.benchmark_key,
        strategy=args.strategy,
        history_limit=args.history_limit,
        allow_missing_history=args.allow_missing_history,
        min_scenario_count=args.min_scenario_count,
        min_completed_ratio=args.min_completed_ratio,
        max_failed_count=args.max_failed_count,
        max_warning_count=args.max_warning_count,
        min_global_best_selected_count=args.min_global_best_selected_count,
        min_global_best_candidate_count=args.min_global_best_candidate_count,
        min_global_best_generated_option_count=(
            args.min_global_best_generated_option_count
        ),
        min_core_replay_ready_ratio=args.min_core_replay_ready_ratio,
        min_chain_integrity_ready_ratio=args.min_chain_integrity_ready_ratio,
        max_chain_integrity_critical_issue_count=(
            args.max_chain_integrity_critical_issue_count
        ),
        min_successor_chain_evaluation_passed_ratio=(
            args.min_successor_chain_evaluation_passed_ratio
        ),
        min_successor_chain_effective_leaf_count=(
            args.min_successor_chain_effective_leaf_count
        ),
        max_successor_chain_critical_issue_count=(
            args.max_successor_chain_critical_issue_count
        ),
        max_successor_chain_ambiguous_source_count=(
            args.max_successor_chain_ambiguous_source_count
        ),
        max_successor_chain_source_status_sync_required_count=(
            args.max_successor_chain_source_status_sync_required_count
        ),
        max_ambiguous_successor_source_count=args.max_ambiguous_successor_source_count,
        max_stale_recommendation_count=args.max_stale_recommendation_count,
        max_successor_recompute_required_count=(
            args.max_successor_recompute_required_count
        ),
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_final_hit_coverage_ratio=args.min_final_hit_coverage_ratio,
        min_final_hit_rate=args.min_final_hit_rate,
        min_average_core_replay_roi=args.min_average_core_replay_roi,
        min_upset_capture_sample_size=args.min_upset_capture_sample_size,
        min_upset_capture_rate=args.min_upset_capture_rate,
        historical_suite_quality_gate_report_path=(
            args.historical_suite_quality_gate_report_path
        ),
        require_historical_suite_quality_gate=(
            args.require_historical_suite_quality_gate
        ),
        require_historical_suite_lifecycle_evidence=(
            not args.allow_missing_historical_suite_lifecycle_evidence
        ),
        require_historical_suite_lifecycle_source_status_synced=(
            not args.allow_unsynced_historical_suite_lifecycle_source_status
        ),
        require_historical_suite_successor_chain_evaluation=(
            args.require_historical_suite_successor_chain_evaluation
        ),
        min_historical_suite_slice_count=args.min_historical_suite_slice_count,
        min_historical_suite_comparison_count=(
            args.min_historical_suite_comparison_count
        ),
        min_historical_suite_candidate_final_hit_sample_size=(
            args.min_historical_suite_candidate_final_hit_sample_size
        ),
        min_historical_suite_candidate_final_hit_coverage_ratio=(
            args.min_historical_suite_candidate_final_hit_coverage_ratio
        ),
        min_historical_suite_candidate_dynamic_mixed_final_answer_count=(
            args.min_historical_suite_candidate_dynamic_mixed_final_answer_count
        ),
        min_historical_suite_candidate_dynamic_mixed_final_answer_rate=(
            args.min_historical_suite_candidate_dynamic_mixed_final_answer_rate
        ),
        min_historical_suite_candidate_handicap_final_answer_count=(
            args.min_historical_suite_candidate_handicap_final_answer_count
        ),
        min_historical_suite_candidate_correct_score_final_answer_count=(
            args.min_historical_suite_candidate_correct_score_final_answer_count
        ),
        min_historical_suite_candidate_multiple_choice_final_answer_count=(
            args.min_historical_suite_candidate_multiple_choice_final_answer_count
        ),
        max_historical_suite_failed_check_count=(
            args.max_historical_suite_failed_check_count
        ),
        min_historical_suite_lifecycle_effective_leaf_count=(
            args.min_historical_suite_lifecycle_effective_leaf_count
        ),
        min_historical_suite_lifecycle_active_edge_count=(
            args.min_historical_suite_lifecycle_active_edge_count
        ),
        max_historical_suite_lifecycle_critical_issue_count=(
            args.max_historical_suite_lifecycle_critical_issue_count
        ),
        max_historical_suite_lifecycle_source_status_sync_required_count=(
            args.max_historical_suite_lifecycle_source_status_sync_required_count
        ),
        min_historical_suite_successor_effective_leaf_count=(
            args.min_historical_suite_successor_effective_leaf_count
        ),
        min_historical_suite_successor_active_edge_count=(
            args.min_historical_suite_successor_active_edge_count
        ),
        max_historical_suite_successor_critical_issue_count=(
            args.max_historical_suite_successor_critical_issue_count
        ),
        max_historical_suite_successor_ambiguous_source_count=(
            args.max_historical_suite_successor_ambiguous_source_count
        ),
        max_historical_suite_successor_source_status_sync_required_count=(
            args.max_historical_suite_successor_source_status_sync_required_count
        ),
        require_historical_suite_market_movement_runtime_replay=(
            args.require_historical_suite_market_movement_runtime_replay
        ),
        require_historical_suite_market_movement_runtime_replay_allowed=(
            not args.allow_historical_suite_market_movement_runtime_replay_not_allowed
        ),
        require_historical_suite_market_movement_runtime_replay_passed_status=(
            not args.allow_historical_suite_market_movement_runtime_replay_non_passed_status
        ),
        min_historical_suite_market_movement_runtime_replay_rule_count=(
            args.min_historical_suite_market_movement_runtime_replay_rule_count
        ),
        min_historical_suite_market_movement_runtime_replay_selected_rule_count=(
            args.min_historical_suite_market_movement_runtime_replay_selected_rule_count
        ),
        min_historical_suite_market_movement_runtime_replay_accepted_count=(
            args.min_historical_suite_market_movement_runtime_replay_accepted_count
        ),
        min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count=(
            args.min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count
        ),
        min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count=(
            args.min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count
        ),
        min_historical_suite_market_movement_runtime_replay_final_hit_rate_delta=(
            args.min_historical_suite_market_movement_runtime_replay_final_hit_rate_delta
        ),
        min_historical_suite_market_movement_runtime_replay_roi_delta=(
            args.min_historical_suite_market_movement_runtime_replay_roi_delta
        ),
        min_historical_suite_market_movement_runtime_replay_profit_loss_delta=(
            args.min_historical_suite_market_movement_runtime_replay_profit_loss_delta
        ),
        max_historical_suite_market_movement_runtime_replay_brier_score_delta=(
            args.max_historical_suite_market_movement_runtime_replay_brier_score_delta
        ),
        max_historical_suite_market_movement_runtime_replay_log_loss_delta=(
            args.max_historical_suite_market_movement_runtime_replay_log_loss_delta
        ),
        max_historical_suite_market_movement_runtime_replay_mean_calibration_error_delta=(
            args.max_historical_suite_market_movement_runtime_replay_calibration_delta
        ),
        require_historical_suite_market_movement_runtime_replay_production_unchanged=(
            not args.allow_historical_suite_market_movement_runtime_replay_production_change
        ),
        require_historical_suite_market_movement_runtime_replay_public_response_unchanged=(
            not args.allow_historical_suite_market_movement_runtime_replay_public_change
        ),
        budget_stability_audit_report_path=args.budget_stability_audit_report_path,
        require_budget_stability_audit=args.require_budget_stability_audit,
        min_budget_stability_slice_count=args.min_budget_stability_slice_count,
        min_budget_stability_comparable_count=args.min_budget_stability_comparable_count,
        max_budget_stability_signature_change_rate=(
            args.max_budget_stability_signature_change_rate
        ),
        max_budget_stability_harmful_change_count=(
            args.max_budget_stability_harmful_change_count
        ),
        min_budget_stability_hit_delta_count=(
            args.min_budget_stability_hit_delta_count
        ),
        min_budget_stability_profit_loss_delta=(
            args.min_budget_stability_profit_loss_delta
        ),
        min_budget_stability_roi_delta=args.min_budget_stability_roi_delta,
        max_budget_stability_warning_count=args.max_budget_stability_warning_count,
        final_answer_market_concentration_audit_report_path=(
            args.final_answer_market_concentration_audit_report_path
        ),
        require_final_answer_market_concentration_audit=(
            args.require_final_answer_market_concentration_audit
        ),
        min_final_answer_market_concentration_slice_count=(
            args.min_final_answer_market_concentration_slice_count
        ),
        min_final_answer_market_concentration_dynamic_mixed_final_answer_count=(
            args.min_final_answer_market_concentration_dynamic_mixed_final_answer_count
        ),
        min_final_answer_market_concentration_effective_constraint_profile_count=(
            args.min_final_answer_market_concentration_effective_constraint_profile_count
        ),
        max_final_answer_market_concentration_failed_check_count=(
            args.max_final_answer_market_concentration_failed_check_count
        ),
        max_final_answer_market_concentration_warning_count=(
            args.max_final_answer_market_concentration_warning_count
        ),
        correct_score_admission_report_path=args.correct_score_admission_report_path,
        require_correct_score_admission=args.require_correct_score_admission,
        require_correct_score_admission_holdout_allowed=(
            not args.allow_correct_score_admission_holdout_not_allowed
        ),
        require_correct_score_admission_production_allowed=(
            args.require_correct_score_admission_production_allowed
        ),
        min_correct_score_admission_slice_count=(
            args.min_correct_score_admission_slice_count
        ),
        min_correct_score_admission_comparison_count=(
            args.min_correct_score_admission_comparison_count
        ),
        min_correct_score_admission_candidate_final_hit_sample_size=(
            args.min_correct_score_admission_candidate_final_hit_sample_size
        ),
        min_correct_score_admission_candidate_final_hit_coverage_ratio=(
            args.min_correct_score_admission_candidate_final_hit_coverage_ratio
        ),
        min_correct_score_admission_candidate_final_hit_rate=(
            args.min_correct_score_admission_candidate_final_hit_rate
        ),
        min_correct_score_admission_candidate_roi=(
            args.min_correct_score_admission_candidate_roi
        ),
        min_correct_score_admission_candidate_correct_score_final_answer_count=(
            args.min_correct_score_admission_candidate_correct_score_final_answer_count
        ),
        min_correct_score_admission_candidate_correct_score_final_answer_rate=(
            args.min_correct_score_admission_candidate_correct_score_final_answer_rate
        ),
        min_correct_score_admission_final_hit_rate_delta=(
            args.min_correct_score_admission_final_hit_rate_delta
        ),
        min_correct_score_admission_roi_delta=(
            args.min_correct_score_admission_roi_delta
        ),
        min_correct_score_admission_profit_loss_delta=(
            args.min_correct_score_admission_profit_loss_delta
        ),
        max_correct_score_admission_brier_score_delta=(
            args.max_correct_score_admission_brier_score_delta
        ),
        max_correct_score_admission_log_loss_delta=(
            args.max_correct_score_admission_log_loss_delta
        ),
        max_correct_score_admission_mean_calibration_error_delta=(
            args.max_correct_score_admission_mean_calibration_error_delta
        ),
        max_correct_score_admission_failed_check_count=(
            args.max_correct_score_admission_failed_check_count
        ),
        max_correct_score_admission_warning_count=(
            args.max_correct_score_admission_warning_count
        ),
        require_unified_candidate_pool=args.require_unified_candidate_pool,
        min_unified_candidate_pool_present_count=(
            args.min_unified_candidate_pool_present_count
        ),
        min_unified_candidate_pool_valid_candidate_count=(
            args.min_unified_candidate_pool_valid_candidate_count
        ),
        min_unified_candidate_pool_unique_family_count=(
            args.min_unified_candidate_pool_unique_family_count
        ),
        max_unified_candidate_pool_selection_mismatch_count=(
            args.max_unified_candidate_pool_selection_mismatch_count
        ),
        max_unified_candidate_pool_selected_2x1_rate=(
            args.max_unified_candidate_pool_selected_2x1_rate
        ),
        require_unified_candidate_pool_multiple_value_admission=(
            args.require_unified_candidate_pool_multiple_value_admission
        ),
        min_unified_candidate_pool_multiple_value_candidate_count=(
            args.min_unified_candidate_pool_multiple_value_candidate_count
        ),
        min_unified_candidate_pool_multiple_value_admitted_candidate_count=(
            args.min_unified_candidate_pool_multiple_value_admitted_candidate_count
        ),
        min_unified_candidate_pool_multiple_value_extra_option_count=(
            args.min_unified_candidate_pool_multiple_value_extra_option_count
        ),
        max_unified_candidate_pool_multiple_value_rejected_candidate_count=(
            args.max_unified_candidate_pool_multiple_value_rejected_candidate_count
        ),
        max_unified_candidate_pool_selected_multiple_value_rejected_count=(
            args.max_unified_candidate_pool_selected_multiple_value_rejected_count
        ),
        runtime_profile_switch_report_path=args.runtime_profile_switch_report_path,
        runtime_profile_switch_replay_report_path=(
            args.runtime_profile_switch_replay_report_path
        ),
        require_runtime_profile_switch_gate=args.require_runtime_profile_switch_gate,
        require_runtime_profile_switch_replay=(
            not args.allow_missing_runtime_profile_switch_replay
        ),
        require_runtime_profile_switch_staged_only=(
            not args.allow_runtime_profile_switch_applied
        ),
        min_runtime_profile_switch_rule_count=(
            args.min_runtime_profile_switch_rule_count
        ),
        min_runtime_profile_switch_allowed_competition_count=(
            args.min_runtime_profile_switch_allowed_competition_count
        ),
        min_runtime_profile_switch_final_answer_count=(
            args.min_runtime_profile_switch_final_answer_count
        ),
        min_runtime_profile_switch_changed_final_answer_count=(
            args.min_runtime_profile_switch_changed_final_answer_count
        ),
        min_runtime_profile_switch_final_answer_hit_rate_delta=(
            args.min_runtime_profile_switch_final_answer_hit_rate_delta
        ),
        min_runtime_profile_switch_roi_delta=args.min_runtime_profile_switch_roi_delta,
        min_runtime_profile_switch_profit_loss_delta=(
            args.min_runtime_profile_switch_profit_loss_delta
        ),
        max_runtime_profile_switch_harm_count_vs_original=(
            args.max_runtime_profile_switch_harm_count_vs_original
        ),
        max_runtime_profile_switch_final_hit_harm_count_vs_original=(
            args.max_runtime_profile_switch_final_hit_harm_count_vs_original
        ),
        max_runtime_profile_switch_profit_loss_harm_count_vs_original=(
            args.max_runtime_profile_switch_profit_loss_harm_count_vs_original
        ),
        min_runtime_profile_switch_average_hit_probability_delta=(
            args.min_runtime_profile_switch_average_hit_probability_delta
        ),
        final_answer_segment_penalty_runtime_replay_report_path=(
            args.final_answer_segment_penalty_runtime_replay_report_path
        ),
        require_final_answer_segment_penalty_runtime_replay=(
            args.require_final_answer_segment_penalty_runtime_replay
        ),
        require_final_answer_segment_penalty_runtime_replay_holdout_allowed=(
            not args.allow_missing_final_answer_segment_penalty_runtime_replay_holdout
        ),
        require_final_answer_segment_penalty_runtime_replay_runtime_allowed=(
            args.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        ),
        min_final_answer_segment_penalty_runtime_replay_rule_count=(
            args.min_final_answer_segment_penalty_runtime_replay_rule_count
        ),
        min_final_answer_segment_penalty_runtime_replay_selected_rule_count=(
            args.min_final_answer_segment_penalty_runtime_replay_selected_rule_count
        ),
        max_final_answer_segment_penalty_runtime_replay_selected_rule_count=(
            args.max_final_answer_segment_penalty_runtime_replay_selected_rule_count
        ),
        min_final_answer_segment_penalty_runtime_replay_final_answer_count=(
            args.min_final_answer_segment_penalty_runtime_replay_final_answer_count
        ),
        min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count=(
            args.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        ),
        min_final_answer_segment_penalty_runtime_replay_penalty_option_count=(
            args.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        ),
        min_final_answer_segment_penalty_runtime_replay_hit_count_delta=(
            args.min_final_answer_segment_penalty_runtime_replay_hit_count_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_hit_rate_delta=(
            args.min_final_answer_segment_penalty_runtime_replay_hit_rate_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_roi_delta=(
            args.min_final_answer_segment_penalty_runtime_replay_roi_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_profit_loss_delta=(
            args.min_final_answer_segment_penalty_runtime_replay_profit_loss_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_candidate_roi=(
            args.min_final_answer_segment_penalty_runtime_replay_candidate_roi
        ),
        max_final_answer_segment_penalty_runtime_replay_brier_score_delta=(
            args.max_final_answer_segment_penalty_runtime_replay_brier_score_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_log_loss_delta=(
            args.max_final_answer_segment_penalty_runtime_replay_log_loss_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_calibration_error_delta=(
            args.max_final_answer_segment_penalty_runtime_replay_calibration_error_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline=(
            args.max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
        ),
        max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline=(
            args.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        ),
        max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline=(
            args.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        ),
        require_final_answer_segment_penalty_runtime_replay_no_production_change=(
            not args.allow_final_answer_segment_penalty_runtime_replay_production_change
        ),
        require_final_answer_segment_penalty_runtime_replay_no_public_response_change=(
            not args.allow_final_answer_segment_penalty_runtime_replay_public_change
        ),
        market_movement_runtime_activation_report_path=(
            args.market_movement_runtime_activation_report_path
        ),
        require_market_movement_runtime_activation=(
            args.require_market_movement_runtime_activation
        ),
        require_market_movement_runtime_activation_ready=(
            not args.allow_market_movement_runtime_activation_not_ready
        ),
        min_market_movement_runtime_activation_rule_count=(
            args.min_market_movement_runtime_activation_rule_count
        ),
        min_market_movement_runtime_activation_selected_rule_count=(
            args.min_market_movement_runtime_activation_selected_rule_count
        ),
        max_market_movement_runtime_activation_selected_rule_count=(
            args.max_market_movement_runtime_activation_selected_rule_count
        ),
        min_market_movement_runtime_activation_adjusted_fixture_count=(
            args.min_market_movement_runtime_activation_adjusted_fixture_count
        ),
        min_market_movement_runtime_activation_adjusted_prediction_count=(
            args.min_market_movement_runtime_activation_adjusted_prediction_count
        ),
        min_market_movement_runtime_activation_final_hit_rate_delta=(
            args.min_market_movement_runtime_activation_final_hit_rate_delta
        ),
        min_market_movement_runtime_activation_roi_delta=(
            args.min_market_movement_runtime_activation_roi_delta
        ),
        min_market_movement_runtime_activation_profit_loss_delta=(
            args.min_market_movement_runtime_activation_profit_loss_delta
        ),
        max_market_movement_runtime_activation_brier_score_delta=(
            args.max_market_movement_runtime_activation_brier_score_delta
        ),
        max_market_movement_runtime_activation_log_loss_delta=(
            args.max_market_movement_runtime_activation_log_loss_delta
        ),
        max_market_movement_runtime_activation_mean_calibration_error_delta=(
            args.max_market_movement_runtime_activation_calibration_delta
        ),
        require_market_movement_runtime_activation_no_default_profile_write=(
            not args.allow_market_movement_runtime_activation_default_profile_write
        ),
        require_market_movement_runtime_activation_no_default_path_change=(
            not args.allow_market_movement_runtime_activation_default_path_change
        ),
        require_market_movement_runtime_activation_no_production_change=(
            not args.allow_market_movement_runtime_activation_production_change
        ),
        require_market_movement_runtime_activation_no_public_response_change=(
            not args.allow_market_movement_runtime_activation_public_change
        ),
        market_movement_runtime_activation_sample_expansion_report_path=(
            args.market_movement_runtime_activation_sample_expansion_report_path
        ),
        require_market_movement_runtime_activation_sample_expansion=(
            args.require_market_movement_runtime_activation_sample_expansion
        ),
        require_market_movement_runtime_activation_sample_expansion_promotion_ready=(
            args.require_market_movement_runtime_activation_sample_expansion_promotion_ready
        ),
        market_movement_runtime_activation_segment_replay_batch_gate_report_path=(
            args.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        ),
        require_market_movement_runtime_activation_segment_replay_batch_gate=(
            args.require_market_movement_runtime_activation_segment_replay_batch_gate
        ),
        require_market_movement_runtime_activation_segment_replay_batch_ready=(
            not args.allow_market_movement_runtime_activation_segment_replay_batch_not_ready
        ),
        require_market_movement_runtime_activation_segment_replay_batch_promotion_ready=(
            args.require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
        ),
        min_market_movement_runtime_activation_segment_replay_batch_report_count=(
            args.min_market_movement_runtime_activation_segment_replay_batch_report_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_passed_count=(
            args.min_market_movement_runtime_activation_segment_replay_batch_passed_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count=(
            args.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count=(
            args.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
        ),
        replacement_reranker_shadow_admission_report_path=(
            args.replacement_reranker_shadow_admission_report_path
        ),
        require_replacement_reranker_shadow_admission=(
            args.require_replacement_reranker_shadow_admission
        ),
        require_replacement_reranker_runtime_candidate_allowed=(
            not args.allow_replacement_reranker_shadow_only
        ),
        require_replacement_reranker_scoped_evidence=(
            args.require_replacement_reranker_scoped_evidence
        ),
        require_replacement_reranker_prematch_source_surface=(
            args.require_replacement_reranker_prematch_source_surface
        ),
        min_replacement_reranker_scope_final_answer_count=(
            args.min_replacement_reranker_scope_final_answer_count
        ),
        min_replacement_reranker_shadow_final_answer_count=(
            args.min_replacement_reranker_shadow_final_answer_count
        ),
        min_replacement_reranker_changed_from_model_top_count=(
            args.min_replacement_reranker_changed_from_model_top_count
        ),
        min_replacement_reranker_hit_delta_vs_model_top=(
            args.min_replacement_reranker_hit_delta_vs_model_top
        ),
        min_replacement_reranker_profit_loss_delta_vs_model_top=(
            args.min_replacement_reranker_profit_loss_delta_vs_model_top
        ),
        min_replacement_reranker_roi_delta_vs_model_top=(
            args.min_replacement_reranker_roi_delta_vs_model_top
        ),
        max_replacement_reranker_harm_count_vs_model_top=(
            args.max_replacement_reranker_harm_count_vs_model_top
        ),
        max_replacement_reranker_final_hit_harm_count_vs_model_top=(
            args.max_replacement_reranker_final_hit_harm_count_vs_model_top
        ),
        max_replacement_reranker_profit_loss_harm_count_vs_model_top=(
            args.max_replacement_reranker_profit_loss_harm_count_vs_model_top
        ),
        max_replacement_reranker_failed_fold_count=(
            args.max_replacement_reranker_failed_fold_count
        ),
        min_replacement_reranker_active_competition_fold_count=(
            args.min_replacement_reranker_active_competition_fold_count
        ),
        min_replacement_reranker_active_season_fold_count=(
            args.min_replacement_reranker_active_season_fold_count
        ),
        min_replacement_reranker_active_rolling_fold_count=(
            args.min_replacement_reranker_active_rolling_fold_count
        ),
        global_planner_short_odds_adapter_gate_report_path=(
            args.global_planner_short_odds_adapter_gate_report_path
        ),
        require_global_planner_short_odds_adapter_gate=(
            args.require_global_planner_short_odds_adapter_gate
        ),
        require_global_planner_short_odds_adapter_default_path_unchanged=(
            not args.allow_global_planner_short_odds_adapter_default_path_change
        ),
        require_global_planner_short_odds_adapter_shadow_path_unchanged=(
            not args.allow_global_planner_short_odds_adapter_shadow_path_change
        ),
        require_global_planner_short_odds_adapter_explicit_opt_in_changed=(
            not args.allow_global_planner_short_odds_adapter_missing_explicit_opt_in_change
        ),
        min_global_planner_short_odds_adapter_runtime_final_answer_count=(
            args.min_global_planner_short_odds_adapter_runtime_final_answer_count
        ),
        min_global_planner_short_odds_adapter_runtime_changed_final_answer_count=(
            args.min_global_planner_short_odds_adapter_runtime_changed_final_answer_count
        ),
        min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta=(
            args.min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta
        ),
        min_global_planner_short_odds_adapter_runtime_roi_delta=(
            args.min_global_planner_short_odds_adapter_runtime_roi_delta
        ),
        min_global_planner_short_odds_adapter_runtime_profit_loss_delta=(
            args.min_global_planner_short_odds_adapter_runtime_profit_loss_delta
        ),
        max_global_planner_short_odds_adapter_runtime_harm_count_vs_original=(
            args.max_global_planner_short_odds_adapter_runtime_harm_count_vs_original
        ),
        max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original=(
            args.max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original
        ),
        max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original=(
            args.max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original
        ),
        min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta=(
            args.min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta
        ),
        require_global_planner_short_odds_adapter_runtime_public_unchanged=(
            not args.allow_global_planner_short_odds_adapter_runtime_public_change
        ),
        require_global_planner_short_odds_adapter_runtime_production_unchanged=(
            not args.allow_global_planner_short_odds_adapter_runtime_production_change
        ),
        global_planner_short_odds_adapter_sample_expansion_report_path=(
            args.global_planner_short_odds_adapter_sample_expansion_report_path
        ),
        require_global_planner_short_odds_adapter_sample_expansion=(
            args.require_global_planner_short_odds_adapter_sample_expansion
        ),
        require_global_planner_short_odds_adapter_sample_expansion_promotion_ready=(
            args.require_global_planner_short_odds_adapter_sample_expansion_promotion_ready
        ),
        recommendation_strategy_promotion_gate_report_path=(
            args.recommendation_strategy_promotion_gate_report_path
        ),
        require_recommendation_strategy_promotion_gate=(
            args.require_recommendation_strategy_promotion_gate
        ),
        require_recommendation_strategy_gate_ready=(
            not args.allow_recommendation_strategy_gate_not_ready
        ),
        min_recommendation_strategy_gate_final_answer_count=(
            args.min_recommendation_strategy_gate_final_answer_count
        ),
        min_recommendation_strategy_gate_changed_final_answer_count=(
            args.min_recommendation_strategy_gate_changed_final_answer_count
        ),
        min_recommendation_strategy_gate_hit_delta_count=(
            args.min_recommendation_strategy_gate_hit_delta_count
        ),
        min_recommendation_strategy_gate_profit_loss_delta=(
            args.min_recommendation_strategy_gate_profit_loss_delta
        ),
        min_recommendation_strategy_gate_minimum_roi_delta=(
            args.min_recommendation_strategy_gate_minimum_roi_delta
        ),
        max_recommendation_strategy_gate_harm_count=(
            args.max_recommendation_strategy_gate_harm_count
        ),
        max_recommendation_strategy_gate_final_hit_harm_count=(
            args.max_recommendation_strategy_gate_final_hit_harm_count
        ),
        max_recommendation_strategy_gate_profit_loss_harm_count=(
            args.max_recommendation_strategy_gate_profit_loss_harm_count
        ),
        require_recommendation_strategy_gate_no_production_change=(
            not args.allow_recommendation_strategy_gate_production_change
        ),
        require_recommendation_strategy_gate_no_public_response_change=(
            not args.allow_recommendation_strategy_gate_public_change
        ),
        recommendation_strategy_staged_activation_smoke_report_path=(
            args.recommendation_strategy_staged_activation_smoke_report_path
        ),
        require_recommendation_strategy_staged_activation_smoke=(
            args.require_recommendation_strategy_staged_activation_smoke
        ),
        require_recommendation_strategy_staged_activation_ready=(
            not args.allow_recommendation_strategy_staged_activation_not_ready
        ),
        require_recommendation_strategy_staged_no_default_write=(
            not args.allow_recommendation_strategy_staged_default_write
        ),
        require_recommendation_strategy_staged_no_production_change=(
            not args.allow_recommendation_strategy_staged_production_change
        ),
        require_recommendation_strategy_staged_no_public_response_change=(
            not args.allow_recommendation_strategy_staged_public_change
        ),
        min_recommendation_strategy_staged_rule_count=(
            args.min_recommendation_strategy_staged_rule_count
        ),
        min_recommendation_strategy_staged_allowed_competition_count=(
            args.min_recommendation_strategy_staged_allowed_competition_count
        ),
        recommendation_strategy_default_path_isolation_report_path=(
            args.recommendation_strategy_default_path_isolation_report_path
        ),
        require_recommendation_strategy_default_path_isolation=(
            args.require_recommendation_strategy_default_path_isolation
        ),
        require_recommendation_strategy_default_path_isolated=(
            not args.allow_recommendation_strategy_default_path_not_isolated
        ),
        require_recommendation_strategy_default_adapter_disabled=(
            not args.allow_recommendation_strategy_default_adapter_enabled
        ),
        require_recommendation_strategy_default_adapter_unchanged=(
            not args.allow_recommendation_strategy_default_adapter_change
        ),
        require_recommendation_strategy_explicit_opt_in_applied=(
            not args.allow_recommendation_strategy_missing_explicit_opt_in
        ),
        require_recommendation_strategy_isolation_no_default_write=(
            not args.allow_recommendation_strategy_isolation_default_write
        ),
        require_recommendation_strategy_isolation_no_production_change=(
            not args.allow_recommendation_strategy_isolation_production_change
        ),
        require_recommendation_strategy_isolation_no_public_response_change=(
            not args.allow_recommendation_strategy_isolation_public_change
        ),
        probability_calibration_profile_rolling_admission_report_path=(
            args.probability_calibration_profile_rolling_admission_report_path
        ),
        require_probability_calibration_profile_rolling_admission=(
            args.require_probability_calibration_profile_rolling_admission
        ),
        require_probability_calibration_profile_candidate_allowed=(
            not args.allow_probability_calibration_profile_shadow_only
        ),
        require_probability_calibration_profile_active_profile=(
            not args.allow_probability_calibration_profile_non_active_profile
        ),
        min_probability_calibration_profile_overall_adjusted_fixture_count=(
            args.min_probability_calibration_profile_overall_adjusted_fixture_count
        ),
        min_probability_calibration_profile_overall_bucket_count=(
            args.min_probability_calibration_profile_overall_bucket_count
        ),
        max_probability_calibration_profile_failed_fold_count=(
            args.max_probability_calibration_profile_failed_fold_count
        ),
        min_probability_calibration_profile_active_competition_fold_count=(
            args.min_probability_calibration_profile_active_competition_fold_count
        ),
        min_probability_calibration_profile_active_season_cutoff_fold_count=(
            args.min_probability_calibration_profile_active_season_cutoff_fold_count
        ),
        min_probability_calibration_profile_active_rolling_fold_count=(
            args.min_probability_calibration_profile_active_rolling_fold_count
        ),
        probability_calibration_profile_model_quality_gate_report_path=(
            args.probability_calibration_profile_model_quality_gate_report_path
        ),
        require_probability_calibration_profile_model_quality_gate=(
            args.require_probability_calibration_profile_model_quality_gate
        ),
        require_probability_calibration_profile_model_quality_ready=(
            not args.allow_probability_calibration_profile_model_quality_not_ready
        ),
        min_probability_calibration_profile_model_quality_selected_competition_count=(
            args.min_probability_calibration_profile_model_quality_selected_competition_count
        ),
        min_probability_calibration_profile_model_quality_adjusted_slice_count=(
            args.min_probability_calibration_profile_model_quality_adjusted_slice_count
        ),
        min_probability_calibration_profile_model_quality_adjusted_fixture_count=(
            args.min_probability_calibration_profile_model_quality_adjusted_fixture_count
        ),
        max_probability_calibration_profile_model_quality_skipped_fixture_count=(
            args.max_probability_calibration_profile_model_quality_skipped_fixture_count
        ),
        max_probability_calibration_profile_model_quality_final_answer_changed_count=(
            args.max_probability_calibration_profile_model_quality_final_answer_changed_count
        ),
        min_probability_calibration_profile_model_quality_final_answer_hit_count_delta=(
            args.min_probability_calibration_profile_model_quality_final_answer_hit_count_delta
        ),
        min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta=(
            args.min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta
        ),
        min_probability_calibration_profile_model_quality_roi_delta=(
            args.min_probability_calibration_profile_model_quality_roi_delta
        ),
        min_probability_calibration_profile_model_quality_profit_loss_delta=(
            args.min_probability_calibration_profile_model_quality_profit_loss_delta
        ),
        max_probability_calibration_profile_model_quality_brier_score_delta=(
            args.max_probability_calibration_profile_model_quality_brier_score_delta
        ),
        max_probability_calibration_profile_model_quality_log_loss_delta=(
            args.max_probability_calibration_profile_model_quality_log_loss_delta
        ),
        max_probability_calibration_profile_model_quality_calibration_error_delta=(
            args.max_probability_calibration_profile_model_quality_calibration_error_delta
        ),
        asian_handicap_segmented_model_quality_governance_report_path=(
            args.asian_handicap_segmented_model_quality_governance_report_path
        ),
        require_asian_handicap_segmented_model_quality_governance=(
            args.require_asian_handicap_segmented_model_quality_governance
        ),
        require_asian_handicap_segmented_model_quality_ready=(
            not args.allow_asian_handicap_segmented_model_quality_not_ready
        ),
        require_asian_handicap_segmented_model_quality_internal_only=(
            not args.allow_asian_handicap_segmented_model_quality_non_internal
        ),
        require_asian_handicap_segmented_model_quality_default_path_isolated=(
            not args.allow_asian_handicap_segmented_model_quality_default_path_not_isolated
        ),
        require_asian_handicap_segmented_model_quality_no_production_change=(
            not args.allow_asian_handicap_segmented_model_quality_production_change
        ),
        require_asian_handicap_segmented_model_quality_no_public_response_change=(
            not args.allow_asian_handicap_segmented_model_quality_public_response_change
        ),
        min_asian_handicap_segmented_model_quality_accepted_segment_count=(
            args.min_asian_handicap_segmented_model_quality_accepted_segment_count
        ),
        max_asian_handicap_segmented_model_quality_shadow_segment_count=(
            args.max_asian_handicap_segmented_model_quality_shadow_segment_count
        ),
        max_asian_handicap_segmented_model_quality_fallback_segment_count=(
            args.max_asian_handicap_segmented_model_quality_fallback_segment_count
        ),
        max_asian_handicap_segmented_model_quality_rejected_segment_count=(
            args.max_asian_handicap_segmented_model_quality_rejected_segment_count
        ),
        min_asian_handicap_segmented_model_quality_accepted_validation_count=(
            args.min_asian_handicap_segmented_model_quality_accepted_validation_count
        ),
        min_asian_handicap_segmented_model_quality_calibration_applied_count=(
            args.min_asian_handicap_segmented_model_quality_calibration_applied_count
        ),
        min_asian_handicap_segmented_model_quality_hit_rate_delta=(
            args.min_asian_handicap_segmented_model_quality_hit_rate_delta
        ),
        max_asian_handicap_segmented_model_quality_brier_score_delta=(
            args.max_asian_handicap_segmented_model_quality_brier_score_delta
        ),
        max_asian_handicap_segmented_model_quality_log_loss_delta=(
            args.max_asian_handicap_segmented_model_quality_log_loss_delta
        ),
        max_asian_handicap_segmented_model_quality_calibration_error_delta=(
            args.max_asian_handicap_segmented_model_quality_calibration_error_delta
        ),
        min_asian_handicap_segmented_model_quality_actual_probability_delta=(
            args.min_asian_handicap_segmented_model_quality_actual_probability_delta
        ),
        prematch_feature_quality_cycle_report_path=(
            args.prematch_feature_quality_cycle_report_path
        ),
        require_prematch_feature_quality_cycle=(
            args.require_prematch_feature_quality_cycle
        ),
        require_prematch_feature_quality_cycle_passed=(
            not args.allow_failed_prematch_feature_quality_cycle
        ),
        require_prematch_feature_quality_cycle_best_gate_passed=(
            not args.allow_prematch_feature_quality_cycle_best_gate_failed
        ),
        min_prematch_feature_quality_cycle_slice_count=(
            args.min_prematch_feature_quality_cycle_slice_count
        ),
        min_prematch_feature_quality_cycle_fixture_count=(
            args.min_prematch_feature_quality_cycle_fixture_count
        ),
        min_prematch_feature_quality_cycle_evaluated_candidate_count=(
            args.min_prematch_feature_quality_cycle_evaluated_candidate_count
        ),
        min_prematch_feature_quality_cycle_passing_candidate_count=(
            args.min_prematch_feature_quality_cycle_passing_candidate_count
        ),
        max_prematch_feature_quality_cycle_warning_count=(
            args.max_prematch_feature_quality_cycle_warning_count
        ),
        max_prematch_feature_quality_cycle_best_brier_score_delta=(
            args.max_prematch_feature_quality_cycle_best_brier_score_delta
        ),
        max_prematch_feature_quality_cycle_best_log_loss_delta=(
            args.max_prematch_feature_quality_cycle_best_log_loss_delta
        ),
        max_prematch_feature_quality_cycle_best_calibration_error_delta=(
            args.max_prematch_feature_quality_cycle_best_calibration_error_delta
        ),
        prematch_feature_rolling_admission_report_path=(
            args.prematch_feature_rolling_admission_report_path
        ),
        require_prematch_feature_rolling_admission=(
            args.require_prematch_feature_rolling_admission
        ),
        require_prematch_feature_rolling_admission_candidate_allowed=(
            not args.allow_prematch_feature_rolling_admission_shadow_only
        ),
        min_prematch_feature_rolling_admission_overall_evaluated_candidate_count=(
            args.min_prematch_feature_rolling_admission_overall_evaluated_candidate_count
        ),
        min_prematch_feature_rolling_admission_overall_passing_candidate_count=(
            args.min_prematch_feature_rolling_admission_overall_passing_candidate_count
        ),
        max_prematch_feature_rolling_admission_failed_fold_count=(
            args.max_prematch_feature_rolling_admission_failed_fold_count
        ),
        min_prematch_feature_rolling_admission_active_competition_fold_count=(
            args.min_prematch_feature_rolling_admission_active_competition_fold_count
        ),
        min_prematch_feature_rolling_admission_active_season_cutoff_fold_count=(
            args.min_prematch_feature_rolling_admission_active_season_cutoff_fold_count
        ),
        min_prematch_feature_rolling_admission_active_rolling_fold_count=(
            args.min_prematch_feature_rolling_admission_active_rolling_fold_count
        ),
        max_prematch_feature_rolling_admission_overall_brier_score_delta=(
            args.max_prematch_feature_rolling_admission_overall_brier_score_delta
        ),
        max_prematch_feature_rolling_admission_overall_log_loss_delta=(
            args.max_prematch_feature_rolling_admission_overall_log_loss_delta
        ),
        max_prematch_feature_rolling_admission_overall_calibration_error_delta=(
            args.max_prematch_feature_rolling_admission_overall_calibration_error_delta
        ),
        prematch_feature_sample_readiness_report_path=(
            args.prematch_feature_sample_readiness_report_path
        ),
        require_prematch_feature_sample_readiness=(
            args.require_prematch_feature_sample_readiness
        ),
        require_prematch_feature_sample_ready_allowed=(
            not args.allow_prematch_feature_sample_readiness_shadow_only
        ),
        min_prematch_feature_sample_ready_source_count=(
            args.min_prematch_feature_sample_ready_source_count
        ),
        min_prematch_feature_sample_ready_fixture_count=(
            args.min_prematch_feature_sample_ready_fixture_count
        ),
        min_prematch_feature_sample_ready_competition_count=(
            args.min_prematch_feature_sample_ready_competition_count
        ),
        min_prematch_feature_sample_ready_season_count=(
            args.min_prematch_feature_sample_ready_season_count
        ),
        min_prematch_feature_sample_ready_competition_season_count=(
            args.min_prematch_feature_sample_ready_competition_season_count
        ),
        max_prematch_feature_sample_readiness_warning_count=(
            args.max_prematch_feature_sample_readiness_warning_count
        ),
        fail_on_history_statuses=tuple(_csv(args.fail_on_history_statuses)),
    )
    options = apply_runtime_profile_switch_preset(
        options,
        args.runtime_profile_switch_preset,
    )
    options = apply_final_answer_segment_penalty_runtime_replay_preset(
        options,
        args.final_answer_segment_penalty_runtime_replay_preset,
    )
    options = apply_recommendation_strategy_governance_preset(
        options,
        args.recommendation_strategy_governance_preset,
    )
    return apply_unified_candidate_pool_guard_preset(
        options,
        args.unified_candidate_pool_guard_preset,
    )


def _check_minimum(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> RecommendationBenchmarkQualityGateCheck:
    return RecommendationBenchmarkQualityGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> RecommendationBenchmarkQualityGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return RecommendationBenchmarkQualityGateCheck(
        name=name,
        status=(
            "passed" if actual is not None and actual >= float(threshold) else "failed"
        ),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_maximum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> RecommendationBenchmarkQualityGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return RecommendationBenchmarkQualityGateCheck(
        name=name,
        status=(
            "passed" if actual is not None and actual <= float(threshold) else "failed"
        ),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> RecommendationBenchmarkQualityGateCheck:
    if not required:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return RecommendationBenchmarkQualityGateCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _check_history_status(
    latest: StoredRecommendationBenchmarkRun,
    *,
    options: RecommendationBenchmarkQualityGateOptions,
) -> RecommendationBenchmarkQualityGateCheck:
    status = _history_status(latest)
    if not options.fail_on_history_statuses:
        return _skipped_check(
            name="history_status",
            actual=status,
            detail="history status blocking is disabled",
        )
    return RecommendationBenchmarkQualityGateCheck(
        name="history_status",
        status=(
            "failed" if status in set(options.fail_on_history_statuses) else "passed"
        ),
        actual=status,
        threshold=",".join(options.fail_on_history_statuses),
        detail="benchmark history status should not be in the configured fail list",
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | None,
    detail: str,
) -> RecommendationBenchmarkQualityGateCheck:
    return RecommendationBenchmarkQualityGateCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _history_status(latest: StoredRecommendationBenchmarkRun) -> str | None:
    summary_status = latest.summary_json.get("history_status")
    if isinstance(summary_status, str):
        return summary_status
    comparison_status = latest.history_comparison_json.get("status")
    if isinstance(comparison_status, str):
        return comparison_status
    return None


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _summary_mapping(summary: dict[str, object], key: str) -> dict[str, object]:
    value = summary.get(key, {})
    if isinstance(value, dict):
        return dict(value)
    return {}


def _summary_list(summary: dict[str, object], key: str) -> list[object]:
    value = summary.get(key, [])
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return []


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _summary_str(summary: dict[str, object], key: str) -> str | None:
    value = summary.get(key)
    if isinstance(value, str):
        return value
    return None


def _summary_bool(summary: dict[str, object], key: str) -> bool:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "passed"}:
            return True
        if normalized in {"false", "0", "no", "failed", "none", "null"}:
            return False
    return False


def _summary_optional_bool(summary: dict[str, object], key: str) -> bool | None:
    if key not in summary:
        return None
    return _summary_bool(summary, key)


def _summary_failed_check_count(summary: dict[str, object]) -> int:
    value = summary.get("failed_checks")
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return _summary_int(summary, "failed_check_count")


def _summary_count(
    summary: dict[str, object],
    *,
    count_key: str,
    ids_key: str,
) -> int:
    if count_key in summary:
        return _summary_int(summary, count_key)
    value = summary.get(ids_key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return 0


def _summary_float(summary: dict[str, object], key: str) -> float | None:
    value = summary.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _upset_capture_sample_size(summary: dict[str, object]) -> int:
    value = _summary_int(summary, "upset_capture_sample_size")
    if value > 0:
        return value
    return _summary_int(summary, "upset_opportunity_count")


def _upset_capture_rate(summary: dict[str, object]) -> float | None:
    explicit = _summary_float(summary, "upset_capture_rate")
    if explicit is not None:
        return explicit
    sample_size = _upset_capture_sample_size(summary)
    if sample_size <= 0:
        return None
    return _summary_int(summary, "upset_capture_count") / sample_size


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _gate_key(options: RecommendationBenchmarkQualityGateOptions) -> str:
    benchmark_key = options.benchmark_key or "all"
    strategy = options.strategy or "any"
    return f"recommendation_benchmark_quality_gate:{benchmark_key}:{strategy}"


def _load_historical_suite_quality_gate(
    path: Path | None,
) -> RecommendationHistoricalSuiteQualityGateEvidence | None:
    if path is None:
        return None
    return RecommendationHistoricalSuiteQualityGateEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_budget_stability_audit(
    path: Path | None,
) -> HistoricalBudgetStabilityAuditReport | None:
    if path is None:
        return None
    return load_historical_budget_stability_audit_report(path)


def _load_final_answer_market_concentration_audit(
    path: Path | None,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport | None:
    if path is None:
        return None
    return load_historical_final_answer_market_concentration_audit_report(path)


def _load_correct_score_admission(
    path: Path | None,
) -> HistoricalCorrectScoreAdmissionReport | None:
    if path is None:
        return None
    return load_historical_correct_score_admission_report(path)


def _load_runtime_profile_switch_gate(
    path: Path | None,
) -> HistoricalShortOddsRuntimeProfileSwitchReport | None:
    if path is None:
        return None
    return HistoricalShortOddsRuntimeProfileSwitchReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_runtime_profile_switch_replay(
    path: Path | None,
) -> HistoricalShortOddsRuntimeShadowReplayReport | None:
    if path is None:
        return None
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_final_answer_segment_penalty_runtime_replay(
    path: Path | None,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport | None:
    if path is None:
        return None
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_market_movement_runtime_activation(
    path: Path | None,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationReport | None:
    if path is None:
        return None
    return load_historical_market_movement_risk_filter_runtime_activation_report(path)


def _load_market_movement_runtime_activation_sample_expansion(
    path: Path | None,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionReport | None:
    if path is None:
        return None
    return load_historical_market_movement_runtime_activation_sample_expansion_report(path)


def _load_market_movement_runtime_activation_segment_replay_batch_gate(
    path: Path | None,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport | None:
    if path is None:
        return None
    from .historical_market_movement_runtime_activation_segment_replay_batch_gate import (
        load_historical_market_movement_runtime_activation_segment_replay_batch_gate_report,
    )

    return (
        load_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
            path
        )
    )


def _load_replacement_reranker_shadow_admission(
    path: Path | None,
) -> HistoricalReplacementRerankerShadowAdmissionReport | None:
    if path is None:
        return None
    return HistoricalReplacementRerankerShadowAdmissionReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_probability_calibration_profile_rolling_admission(
    path: Path | None,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None:
    if path is None:
        return None
    from .historical_probability_calibration_profile_rolling_admission import (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    )

    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_probability_calibration_profile_model_quality_gate(
    path: Path | None,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateReport | None:
    if path is None:
        return None
    from .historical_probability_calibration_profile_model_quality_gate import (
        load_historical_probability_calibration_profile_model_quality_gate_report,
    )

    return load_historical_probability_calibration_profile_model_quality_gate_report(path)


def _load_asian_handicap_segmented_model_quality_governance(
    path: Path | None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport | None:
    if path is None:
        return None
    from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segmented_governance_review import (  # noqa: E501
        load_historical_prematch_feature_asian_handicap_segmented_governance_review_report,
    )

    return (
        load_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
            path
        )
    )


def _load_prematch_feature_quality_cycle(
    path: Path | None,
) -> HistoricalPrematchFeatureQualityCycleResult | None:
    if path is None:
        return None
    from .historical_prematch_feature_quality_cycle import (
        HistoricalPrematchFeatureQualityCycleResult,
    )

    return HistoricalPrematchFeatureQualityCycleResult.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_prematch_feature_rolling_admission(
    path: Path | None,
) -> HistoricalPrematchFeatureRollingAdmissionReport | None:
    if path is None:
        return None
    from .historical_prematch_feature_rolling_admission import (
        HistoricalPrematchFeatureRollingAdmissionReport,
    )

    return HistoricalPrematchFeatureRollingAdmissionReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_prematch_feature_sample_readiness(
    path: Path | None,
) -> HistoricalPrematchFeatureSampleReadinessReport | None:
    if path is None:
        return None
    from .historical_prematch_feature_sample_readiness import (
        HistoricalPrematchFeatureSampleReadinessReport,
    )

    return HistoricalPrematchFeatureSampleReadinessReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_global_planner_short_odds_adapter_gate(
    path: Path | None,
) -> HistoricalGlobalPlannerShortOddsAdapterGateReport | None:
    if path is None:
        return None
    return load_global_planner_short_odds_adapter_gate_report(path)


def _load_global_planner_short_odds_adapter_sample_expansion(
    path: Path | None,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport | None:
    if path is None:
        return None
    return load_global_planner_short_odds_adapter_sample_expansion_report(path)


def _load_recommendation_strategy_promotion_gate(
    path: Path | None,
) -> RecommendationStrategyPromotionGateReport | None:
    if path is None:
        return None
    return load_recommendation_strategy_promotion_gate_report(path)


def _load_recommendation_strategy_staged_activation_smoke(
    path: Path | None,
) -> RecommendationStrategyStagedActivationSmokeReport | None:
    if path is None:
        return None
    return load_recommendation_strategy_staged_activation_smoke_report(path)


def _load_recommendation_strategy_default_path_isolation(
    path: Path | None,
) -> RecommendationStrategyDefaultPathIsolationReport | None:
    if path is None:
        return None
    return load_recommendation_strategy_default_path_isolation_report(path)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
