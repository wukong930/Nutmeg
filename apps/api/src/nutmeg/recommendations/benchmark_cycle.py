from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.baseline_seed import (
    BASELINE_SEED_PROFILES,
    DEFAULT_BASELINE_SEED_PROFILE,
    RecommendationBaselineSeedProfile,
)
from nutmeg.recommendations.benchmark_core_replay_seed import (
    RecommendationBenchmarkCoreReplaySeedDatabase,
    RecommendationBenchmarkCoreReplaySeedOptions,
    RecommendationBenchmarkCoreReplaySeedResult,
    run_recommendation_benchmark_core_replay_seed,
)
from nutmeg.recommendations.benchmark_quality_gate import (
    FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESETS,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS,
    RUNTIME_PROFILE_SWITCH_PRESETS,
    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
    UNIFIED_CANDIDATE_POOL_GUARD_PRESETS,
    RecommendationBenchmarkQualityGateOptions,
    RecommendationBenchmarkQualityGateResult,
    apply_final_answer_segment_penalty_runtime_replay_preset,
    apply_recommendation_strategy_governance_preset,
    apply_runtime_profile_switch_preset,
    apply_unified_candidate_pool_guard_preset,
    run_recommendation_benchmark_quality_gate,
)
from nutmeg.recommendations.benchmark_runner import (
    DEFAULT_BENCHMARK_BUDGETS,
    DEFAULT_BENCHMARK_MODES,
    DEFAULT_BENCHMARK_PASS_TYPES,
    DEFAULT_BENCHMARK_REQUESTED_BY,
    RecommendationBenchmarkDatabaseExecutor,
)
from nutmeg.recommendations.benchmark_schedule import (
    RecommendationBenchmarkScheduleOptions,
    RecommendationBenchmarkScheduleRunResult,
    run_recommendation_benchmark_schedule,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type RecommendationBenchmarkCycleStatus = Literal[
    "passed",
    "failed",
    "gate_skipped",
]

RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1 = (
    "probability_preserving_13change_governance_v1"
)
RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1 = (
    "probability_preserving_quality_score_governance_v1"
)
RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1 = (
    "v3_2_unified_candidate_pool_guard_v1"
)
RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1 = (
    "v3_2_market_movement_segment_replay_batch_gate_v1"
)
RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1 = (
    "v3_2_core_accuracy_governance_v1"
)
RECOMMENDATION_BENCHMARK_CYCLE_PRESETS = (
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1,
)
CORE_PLUS_EXPANDED_A_LEAGUES_SUCCESSOR_EFFECTIVE_FINAL_ONLY_HISTORICAL_GATE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_"
    "successor_effective_final_only_gate_smoke_v1.json"
)
CORE_PLUS_EXPANDED_A_LEAGUES_BUDGET_STABILITY_AUDIT_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "local_core_plus_expanded_a_leagues_budget_stability_multiple_tie_breaker_smoke_v1.json"
)
CORE_PLUS_EXPANDED_A_LEAGUES_DYNAMIC_MIX_CONSTRAINT_RUNTIME_SMOKE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_expanded_a_leagues_rolling_window_"
    "dynamic_mix_final_answer_lane_constraint_profile_runtime_smoke_5slice_v1.json"
)
MARKET_MOVEMENT_RUNTIME_ACTIVATION_SAMPLE_EXPANSION_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_market_feature_market_movement_runtime_activation_"
    "sample_expansion_segment_replay_ready_v1.json"
)
MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_REPLAY_BATCH_GATE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_market_feature_market_movement_runtime_activation_"
    "segment_replay_batch_gate_sample_ready_v1.json"
)
ASIAN_HANDICAP_SEGMENTED_MODEL_QUALITY_GOVERNANCE_REPORT_PATH = Path(
    "configs/recommendations/historical_reports/"
    "football_data_co_uk_competition_segmented_asian_handicap_line_transform_"
    "enrichment_governance_review_v1.json"
)

INSERT_RECOMMENDATION_BENCHMARK_CYCLE_RUN_QUERY = """
INSERT INTO recommendation_benchmark_cycle_runs (
  cycle_key,
  status,
  passed,
  schedule_key,
  benchmark_key,
  benchmark_run_id,
  gate_key,
  gate_status,
  gate_passed,
  historical_suite_quality_gate_key,
  historical_suite_quality_gate_passed,
  historical_suite_lifecycle_source_status_synced,
  historical_suite_lifecycle_effective_leaf_count,
  historical_suite_lifecycle_active_edge_count,
  historical_suite_lifecycle_critical_issue_count,
  historical_suite_lifecycle_source_status_sync_required_count,
  failed_checks_json,
  summary_json,
  warnings_json,
  result_json,
  source
) VALUES (
  %(cycle_key)s,
  %(status)s,
  %(passed)s,
  %(schedule_key)s,
  %(benchmark_key)s,
  %(benchmark_run_id)s,
  %(gate_key)s,
  %(gate_status)s,
  %(gate_passed)s,
  %(historical_suite_quality_gate_key)s,
  %(historical_suite_quality_gate_passed)s,
  %(historical_suite_lifecycle_source_status_synced)s,
  %(historical_suite_lifecycle_effective_leaf_count)s,
  %(historical_suite_lifecycle_active_edge_count)s,
  %(historical_suite_lifecycle_critical_issue_count)s,
  %(historical_suite_lifecycle_source_status_sync_required_count)s,
  %(failed_checks_json)s::jsonb,
  %(summary_json)s::jsonb,
  %(warnings_json)s::jsonb,
  %(result_json)s::jsonb,
  %(source)s
)
RETURNING
  recommendation_benchmark_cycle_run_id,
  cycle_key,
  status,
  passed,
  schedule_key,
  benchmark_key,
  benchmark_run_id,
  gate_key,
  gate_status,
  gate_passed,
  historical_suite_quality_gate_key,
  historical_suite_quality_gate_passed,
  historical_suite_lifecycle_source_status_synced,
  historical_suite_lifecycle_effective_leaf_count,
  historical_suite_lifecycle_active_edge_count,
  historical_suite_lifecycle_critical_issue_count,
  historical_suite_lifecycle_source_status_sync_required_count,
  failed_checks_json,
  summary_json,
  warnings_json,
  created_at
"""

LIST_RECOMMENDATION_BENCHMARK_CYCLE_RUNS_QUERY = """
SELECT
  recommendation_benchmark_cycle_run_id,
  cycle_key,
  status,
  passed,
  schedule_key,
  benchmark_key,
  benchmark_run_id,
  gate_key,
  gate_status,
  gate_passed,
  historical_suite_quality_gate_key,
  historical_suite_quality_gate_passed,
  historical_suite_lifecycle_source_status_synced,
  historical_suite_lifecycle_effective_leaf_count,
  historical_suite_lifecycle_active_edge_count,
  historical_suite_lifecycle_critical_issue_count,
  historical_suite_lifecycle_source_status_sync_required_count,
  failed_checks_json,
  summary_json,
  warnings_json,
  created_at
FROM recommendation_benchmark_cycle_runs
WHERE (%(cycle_key)s::text IS NULL OR cycle_key = %(cycle_key)s::text)
  AND (%(benchmark_key)s::text IS NULL OR benchmark_key = %(benchmark_key)s::text)
ORDER BY created_at DESC, recommendation_benchmark_cycle_run_id DESC
LIMIT %(limit)s
"""


class RecommendationBenchmarkCycleScheduleRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkDatabaseExecutor,
        *,
        options: RecommendationBenchmarkScheduleOptions,
    ) -> RecommendationBenchmarkScheduleRunResult: ...


class RecommendationBenchmarkCycleGateRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkDatabaseExecutor,
        *,
        options: RecommendationBenchmarkQualityGateOptions,
    ) -> RecommendationBenchmarkQualityGateResult: ...


class RecommendationBenchmarkCycleCoreReplaySeedRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkCoreReplaySeedDatabase,
        *,
        options: RecommendationBenchmarkCoreReplaySeedOptions,
    ) -> RecommendationBenchmarkCoreReplaySeedResult: ...


class RecommendationBenchmarkCycleRunRepository(Protocol):
    def list_history(
        self,
        *,
        cycle_key: str | None = None,
        benchmark_key: str | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkCycleRun]:
        """Read persisted scheduled benchmark-cycle quality reports."""

    def save_run(
        self,
        result: RecommendationBenchmarkCycleRunResult,
        *,
        source: str = "recommendation_benchmark_cycle_v3_1",
    ) -> StoredRecommendationBenchmarkCycleRun:
        """Persist a scheduled benchmark-cycle quality report."""


class RecommendationBenchmarkCycleOptions(BaseModel):
    schedule_options: RecommendationBenchmarkScheduleOptions = Field(
        default_factory=RecommendationBenchmarkScheduleOptions
    )
    gate_options: RecommendationBenchmarkQualityGateOptions = Field(
        default_factory=RecommendationBenchmarkQualityGateOptions
    )
    cycle_preset: str | None = None
    run_gate: bool = True
    save_cycle_report: bool = False
    commit_core_replay_seed: bool = False
    core_replay_seed_profile: RecommendationBaselineSeedProfile = (
        DEFAULT_BASELINE_SEED_PROFILE
    )
    core_replay_seed_reset: bool = True


class StoredRecommendationBenchmarkCycleRun(BaseModel):
    recommendation_benchmark_cycle_run_id: int = Field(gt=0)
    cycle_key: str
    status: RecommendationBenchmarkCycleStatus
    passed: bool
    schedule_key: str
    benchmark_key: str
    benchmark_run_id: int | None = None
    gate_key: str | None = None
    gate_status: str | None = None
    gate_passed: bool | None = None
    historical_suite_quality_gate_key: str | None = None
    historical_suite_quality_gate_passed: bool | None = None
    historical_suite_lifecycle_source_status_synced: bool | None = None
    historical_suite_lifecycle_effective_leaf_count: int = Field(ge=0)
    historical_suite_lifecycle_active_edge_count: int = Field(ge=0)
    historical_suite_lifecycle_critical_issue_count: int = Field(ge=0)
    historical_suite_lifecycle_source_status_sync_required_count: int = Field(ge=0)
    failed_checks_json: list[object] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)
    warnings_json: list[object] = Field(default_factory=list)
    created_at: datetime


class RecommendationBenchmarkCycleRunResult(BaseModel):
    cycle_key: str
    status: RecommendationBenchmarkCycleStatus
    passed: bool
    schedule: RecommendationBenchmarkScheduleRunResult
    gate: RecommendationBenchmarkQualityGateResult | None = None
    stored_cycle_report: StoredRecommendationBenchmarkCycleRun | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class PostgresRecommendationBenchmarkCycleRunRepository:
    def __init__(self, database: RecommendationBenchmarkDatabaseExecutor) -> None:
        self.database = database

    def list_history(
        self,
        *,
        cycle_key: str | None = None,
        benchmark_key: str | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkCycleRun]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_BENCHMARK_CYCLE_RUNS_QUERY,
            {
                "cycle_key": cycle_key,
                "benchmark_key": benchmark_key,
                "limit": max(1, min(limit, 200)),
            },
        )
        return [_stored_cycle_run_from_row(row) for row in rows]

    def save_run(
        self,
        result: RecommendationBenchmarkCycleRunResult,
        *,
        source: str = "recommendation_benchmark_cycle_v3_1",
    ) -> StoredRecommendationBenchmarkCycleRun:
        summary = result.summary_json
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_BENCHMARK_CYCLE_RUN_QUERY,
                {
                    "cycle_key": result.cycle_key,
                    "status": result.status,
                    "passed": result.passed,
                    "schedule_key": _summary_str(summary, "schedule_key"),
                    "benchmark_key": _summary_str(summary, "benchmark_key"),
                    "benchmark_run_id": _optional_int(
                        summary.get("stored_report_id")
                    ),
                    "gate_key": _optional_str(summary.get("gate_key")),
                    "gate_status": _optional_str(summary.get("gate_status")),
                    "gate_passed": _optional_bool(summary.get("gate_passed")),
                    "historical_suite_quality_gate_key": _optional_str(
                        summary.get("historical_suite_quality_gate_key")
                    ),
                    "historical_suite_quality_gate_passed": _optional_bool(
                        summary.get("historical_suite_quality_gate_passed")
                    ),
                    "historical_suite_lifecycle_source_status_synced": (
                        _optional_bool(
                            summary.get(
                                "historical_suite_lifecycle_source_status_synced"
                            )
                        )
                    ),
                    "historical_suite_lifecycle_effective_leaf_count": _summary_int(
                        summary,
                        "historical_suite_lifecycle_effective_leaf_count",
                    ),
                    "historical_suite_lifecycle_active_edge_count": _summary_int(
                        summary,
                        "historical_suite_lifecycle_active_edge_count",
                    ),
                    "historical_suite_lifecycle_critical_issue_count": _summary_int(
                        summary,
                        "historical_suite_lifecycle_critical_issue_count",
                    ),
                    "historical_suite_lifecycle_source_status_sync_required_count": (
                        _summary_int(
                            summary,
                            "historical_suite_lifecycle_source_status_sync_required_count",
                        )
                    ),
                    "failed_checks_json": _json(
                        summary.get("gate_failed_checks", [])
                    ),
                    "summary_json": _json(summary),
                    "warnings_json": _json(result.warnings),
                    "result_json": _json(
                        result.model_dump(
                            mode="json",
                            exclude={"stored_cycle_report"},
                        )
                    ),
                    "source": source,
                },
            )
        )
        return _stored_cycle_run_from_row(row)


def apply_recommendation_benchmark_cycle_preset(
    options: RecommendationBenchmarkCycleOptions,
    preset: str | None,
) -> RecommendationBenchmarkCycleOptions:
    if preset is None:
        return options
    if preset == RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1:
        return _apply_core_accuracy_governance_cycle_preset(options, preset)
    if preset == RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1:
        return _apply_unified_candidate_pool_guard_cycle_preset(options, preset)
    if (
        preset
        == RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1
    ):
        return _apply_market_movement_segment_replay_batch_gate_cycle_preset(
            options,
            preset,
        )
    if (
        preset
        == RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
    ):
        schedule_name = "probability-preserving-13change-governance"
        strategy_governance_preset = (
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
        )
    elif (
        preset
        == RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1
    ):
        schedule_name = "probability-preserving-quality-score-governance"
        strategy_governance_preset = (
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1
        )
    else:
        raise ValueError(f"unknown recommendation benchmark cycle preset: {preset}")

    default_schedule = RecommendationBenchmarkScheduleOptions()
    default_historical_gate_path = (
        CORE_PLUS_EXPANDED_A_LEAGUES_SUCCESSOR_EFFECTIVE_FINAL_ONLY_HISTORICAL_GATE_REPORT_PATH
    )
    default_budget_stability_audit_path = (
        CORE_PLUS_EXPANDED_A_LEAGUES_BUDGET_STABILITY_AUDIT_REPORT_PATH
    )
    schedule = options.schedule_options
    schedule_options = schedule.model_copy(
        update={
            "schedule_name": (
                schedule_name
                if schedule.schedule_name == default_schedule.schedule_name
                else schedule.schedule_name
            ),
            "cadence": (
                "once"
                if schedule.cadence == default_schedule.cadence
                else schedule.cadence
            ),
            "run_core_replay": True,
            "run_chain_integrity": True,
            "run_successor_chain_evaluation": True,
            "run_prematch_pipeline": False,
            "dry_run": True,
        }
    )
    gate_options = apply_recommendation_strategy_governance_preset(
        options.gate_options,
        strategy_governance_preset,
    ).model_copy(
        update={
            "min_global_best_selected_count": 1,
            "min_global_best_candidate_count": 1,
            "min_global_best_generated_option_count": 1,
            "min_core_replay_ready_ratio": 1.0,
            "min_final_hit_sample_size": 1,
            "min_final_hit_coverage_ratio": 1.0,
            "historical_suite_quality_gate_report_path": (
                options.gate_options.historical_suite_quality_gate_report_path
                or default_historical_gate_path
            ),
            "require_historical_suite_quality_gate": True,
            "require_historical_suite_lifecycle_evidence": False,
            "require_historical_suite_lifecycle_source_status_synced": False,
            "min_historical_suite_slice_count": max(
                options.gate_options.min_historical_suite_slice_count,
                240,
            ),
            "min_historical_suite_comparison_count": max(
                options.gate_options.min_historical_suite_comparison_count,
                240,
            ),
            "min_historical_suite_candidate_final_hit_sample_size": max(
                options.gate_options.min_historical_suite_candidate_final_hit_sample_size,
                240,
            ),
            "min_historical_suite_candidate_final_hit_coverage_ratio": max(
                options.gate_options.min_historical_suite_candidate_final_hit_coverage_ratio
                or 0.0,
                1.0,
            ),
            "max_historical_suite_failed_check_count": 0,
            "require_historical_suite_successor_chain_evaluation": True,
            "min_historical_suite_successor_effective_leaf_count": max(
                options.gate_options.min_historical_suite_successor_effective_leaf_count,
                1,
            ),
            "min_historical_suite_successor_active_edge_count": max(
                options.gate_options.min_historical_suite_successor_active_edge_count,
                1,
            ),
            "max_historical_suite_successor_critical_issue_count": 0,
            "max_historical_suite_successor_ambiguous_source_count": 0,
            "max_historical_suite_successor_source_status_sync_required_count": 0,
            "budget_stability_audit_report_path": (
                options.gate_options.budget_stability_audit_report_path
                or default_budget_stability_audit_path
            ),
            "require_budget_stability_audit": True,
            "min_budget_stability_slice_count": max(
                options.gate_options.min_budget_stability_slice_count,
                240,
            ),
            "min_budget_stability_comparable_count": max(
                options.gate_options.min_budget_stability_comparable_count,
                240,
            ),
            "max_budget_stability_signature_change_rate": min(
                options.gate_options.max_budget_stability_signature_change_rate
                if options.gate_options.max_budget_stability_signature_change_rate
                is not None
                else 0.0,
                0.0,
            ),
            "max_budget_stability_harmful_change_count": min(
                options.gate_options.max_budget_stability_harmful_change_count
                if options.gate_options.max_budget_stability_harmful_change_count
                is not None
                else 0,
                0,
            ),
            "min_budget_stability_hit_delta_count": max(
                options.gate_options.min_budget_stability_hit_delta_count
                if options.gate_options.min_budget_stability_hit_delta_count
                is not None
                else 0,
                0,
            ),
            "min_budget_stability_profit_loss_delta": max(
                options.gate_options.min_budget_stability_profit_loss_delta
                if options.gate_options.min_budget_stability_profit_loss_delta
                is not None
                else 0.0,
                0.0,
            ),
            "min_budget_stability_roi_delta": max(
                options.gate_options.min_budget_stability_roi_delta
                if options.gate_options.min_budget_stability_roi_delta is not None
                else 0.0,
                0.0,
            ),
            "max_budget_stability_warning_count": 0,
        }
    )
    return options.model_copy(
        update={
            "schedule_options": schedule_options,
            "gate_options": gate_options,
            "cycle_preset": preset,
            "run_gate": True,
        }
    )


def _apply_core_accuracy_governance_cycle_preset(
    options: RecommendationBenchmarkCycleOptions,
    preset: str,
) -> RecommendationBenchmarkCycleOptions:
    base = apply_recommendation_benchmark_cycle_preset(
        options,
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1,
    )
    default_schedule = RecommendationBenchmarkScheduleOptions()
    schedule = options.schedule_options
    schedule_options = base.schedule_options.model_copy(
        update={
            "schedule_name": (
                "v3-2-core-accuracy-governance"
                if schedule.schedule_name == default_schedule.schedule_name
                else schedule.schedule_name
            ),
            "cadence": (
                "once"
                if schedule.cadence == default_schedule.cadence
                else schedule.cadence
            ),
            "run_global_best": True,
            "run_core_replay": True,
            "run_chain_integrity": True,
            "run_successor_chain_evaluation": True,
            "run_prematch_pipeline": False,
            "dry_run": True,
        }
    )
    gate_options = base.gate_options.model_copy(
        update={
            "final_answer_market_concentration_audit_report_path": (
                options.gate_options.final_answer_market_concentration_audit_report_path
                or CORE_PLUS_EXPANDED_A_LEAGUES_DYNAMIC_MIX_CONSTRAINT_RUNTIME_SMOKE_REPORT_PATH
            ),
            "require_final_answer_market_concentration_audit": True,
            "min_final_answer_market_concentration_slice_count": max(
                options.gate_options.min_final_answer_market_concentration_slice_count,
                5,
            ),
            "min_final_answer_market_concentration_dynamic_mixed_final_answer_count": max(
                options.gate_options.min_final_answer_market_concentration_dynamic_mixed_final_answer_count,
                5,
            ),
            "min_final_answer_market_concentration_effective_constraint_profile_count": max(
                options.gate_options.min_final_answer_market_concentration_effective_constraint_profile_count,
                2,
            ),
            "max_final_answer_market_concentration_failed_check_count": 0,
            "max_final_answer_market_concentration_warning_count": 0,
            "market_movement_runtime_activation_sample_expansion_report_path": (
                options.gate_options.market_movement_runtime_activation_sample_expansion_report_path
                or MARKET_MOVEMENT_RUNTIME_ACTIVATION_SAMPLE_EXPANSION_REPORT_PATH
            ),
            "require_market_movement_runtime_activation_sample_expansion": True,
            "require_market_movement_runtime_activation_sample_expansion_promotion_ready": True,
            "market_movement_runtime_activation_segment_replay_batch_gate_report_path": (
                options.gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
                or MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_REPLAY_BATCH_GATE_REPORT_PATH
            ),
            "require_market_movement_runtime_activation_segment_replay_batch_gate": True,
            "require_market_movement_runtime_activation_segment_replay_batch_ready": True,
            "require_market_movement_runtime_activation_segment_replay_batch_promotion_ready": True,
            "min_market_movement_runtime_activation_segment_replay_batch_report_count": max(
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_report_count,
                4,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_passed_count": max(
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_passed_count,
                4,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count": max(  # noqa: E501
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count,
                1200,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count": max(  # noqa: E501
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count,
                3600,
            ),
            "asian_handicap_segmented_model_quality_governance_report_path": (
                options.gate_options.asian_handicap_segmented_model_quality_governance_report_path
                or ASIAN_HANDICAP_SEGMENTED_MODEL_QUALITY_GOVERNANCE_REPORT_PATH
            ),
            "require_asian_handicap_segmented_model_quality_governance": True,
            "require_asian_handicap_segmented_model_quality_ready": True,
            "require_asian_handicap_segmented_model_quality_internal_only": True,
            "require_asian_handicap_segmented_model_quality_default_path_isolated": True,
            "require_asian_handicap_segmented_model_quality_no_production_change": True,
            "require_asian_handicap_segmented_model_quality_no_public_response_change": True,
            "min_asian_handicap_segmented_model_quality_accepted_segment_count": max(
                options.gate_options.min_asian_handicap_segmented_model_quality_accepted_segment_count,
                3,
            ),
            "max_asian_handicap_segmented_model_quality_shadow_segment_count": 0,
            "max_asian_handicap_segmented_model_quality_fallback_segment_count": 2,
            "max_asian_handicap_segmented_model_quality_rejected_segment_count": 0,
            "min_asian_handicap_segmented_model_quality_accepted_validation_count": max(
                options.gate_options.min_asian_handicap_segmented_model_quality_accepted_validation_count,
                100,
            ),
            "min_asian_handicap_segmented_model_quality_calibration_applied_count": max(
                options.gate_options.min_asian_handicap_segmented_model_quality_calibration_applied_count,
                2,
            ),
            "min_asian_handicap_segmented_model_quality_hit_rate_delta": 0.0,
            "max_asian_handicap_segmented_model_quality_brier_score_delta": 0.0,
            "max_asian_handicap_segmented_model_quality_log_loss_delta": 0.0,
            "max_asian_handicap_segmented_model_quality_calibration_error_delta": 0.0,
            "min_asian_handicap_segmented_model_quality_actual_probability_delta": 0.0,
        }
    )
    return base.model_copy(
        update={
            "schedule_options": schedule_options,
            "gate_options": gate_options,
            "cycle_preset": preset,
            "run_gate": True,
        }
    )


def _apply_market_movement_segment_replay_batch_gate_cycle_preset(
    options: RecommendationBenchmarkCycleOptions,
    preset: str,
) -> RecommendationBenchmarkCycleOptions:
    default_schedule = RecommendationBenchmarkScheduleOptions()
    schedule = options.schedule_options
    schedule_options = schedule.model_copy(
        update={
            "schedule_name": (
                "v3-2-market-movement-segment-replay-batch-gate"
                if schedule.schedule_name == default_schedule.schedule_name
                else schedule.schedule_name
            ),
            "cadence": (
                "once"
                if schedule.cadence == default_schedule.cadence
                else schedule.cadence
            ),
            "run_global_best": True,
            "run_core_replay": False,
            "run_chain_integrity": False,
            "run_successor_chain_evaluation": False,
            "run_prematch_pipeline": False,
            "dry_run": True,
            "save_report": True,
        }
    )
    gate_options = options.gate_options.model_copy(
        update={
            "market_movement_runtime_activation_sample_expansion_report_path": (
                options.gate_options.market_movement_runtime_activation_sample_expansion_report_path
                or MARKET_MOVEMENT_RUNTIME_ACTIVATION_SAMPLE_EXPANSION_REPORT_PATH
            ),
            "require_market_movement_runtime_activation_sample_expansion": True,
            "require_market_movement_runtime_activation_sample_expansion_promotion_ready": False,
            "market_movement_runtime_activation_segment_replay_batch_gate_report_path": (
                options.gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
                or MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_REPLAY_BATCH_GATE_REPORT_PATH
            ),
            "require_market_movement_runtime_activation_segment_replay_batch_gate": True,
            "require_market_movement_runtime_activation_segment_replay_batch_ready": True,
            "require_market_movement_runtime_activation_segment_replay_batch_promotion_ready": False,  # noqa: E501
            "min_market_movement_runtime_activation_segment_replay_batch_report_count": max(
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_report_count,
                4,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_passed_count": max(
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_passed_count,
                4,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count": max(  # noqa: E501
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count,
                1200,
            ),
            "min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count": max(  # noqa: E501
                options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count,
                3600,
            ),
        }
    )
    return options.model_copy(
        update={
            "schedule_options": schedule_options,
            "gate_options": gate_options,
            "cycle_preset": preset,
            "run_gate": True,
        }
    )


def _apply_unified_candidate_pool_guard_cycle_preset(
    options: RecommendationBenchmarkCycleOptions,
    preset: str,
) -> RecommendationBenchmarkCycleOptions:
    default_schedule = RecommendationBenchmarkScheduleOptions()
    schedule = options.schedule_options
    schedule_options = schedule.model_copy(
        update={
            "schedule_name": (
                "v3-2-unified-candidate-pool-guard"
                if schedule.schedule_name == default_schedule.schedule_name
                else schedule.schedule_name
            ),
            "cadence": (
                "once"
                if schedule.cadence == default_schedule.cadence
                else schedule.cadence
            ),
            "pass_types": (
                ("1x1", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1")
                if schedule.pass_types == default_schedule.pass_types
                else schedule.pass_types
            ),
            "run_global_best": True,
            "run_core_replay": False,
            "run_chain_integrity": False,
            "run_successor_chain_evaluation": False,
            "run_prematch_pipeline": False,
            "dry_run": True,
            "save_report": True,
        }
    )
    gate_options = apply_unified_candidate_pool_guard_preset(
        options.gate_options,
        UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
    ).model_copy(
        update={
            "history_limit": max(options.gate_options.history_limit, 2),
            "min_completed_ratio": 1.0,
            "max_failed_count": 0,
            "min_global_best_selected_count": max(
                options.gate_options.min_global_best_selected_count,
                1,
            ),
            "min_global_best_candidate_count": max(
                options.gate_options.min_global_best_candidate_count,
                1,
            ),
            "min_global_best_generated_option_count": max(
                options.gate_options.min_global_best_generated_option_count,
                1,
            ),
        }
    )
    return options.model_copy(
        update={
            "schedule_options": schedule_options,
            "gate_options": gate_options,
            "cycle_preset": preset,
            "run_gate": True,
        }
    )


def run_recommendation_benchmark_cycle(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkCycleOptions,
    schedule_runner: RecommendationBenchmarkCycleScheduleRunner | None = None,
    gate_runner: RecommendationBenchmarkCycleGateRunner | None = None,
    core_replay_seed_runner: (
        RecommendationBenchmarkCycleCoreReplaySeedRunner | None
    ) = None,
    cycle_repository: RecommendationBenchmarkCycleRunRepository | None = None,
) -> RecommendationBenchmarkCycleRunResult:
    core_replay_seed = None
    pre_schedule_warnings: list[str] = []
    if options.commit_core_replay_seed:
        core_replay_seed = (
            core_replay_seed_runner or run_recommendation_benchmark_core_replay_seed
        )(
            cast(RecommendationBenchmarkCoreReplaySeedDatabase, database),
            options=_core_replay_seed_options(options),
        )
        pre_schedule_warnings.extend(
            f"core_replay_seed:{item}" for item in core_replay_seed.warnings
        )
        if not core_replay_seed.passed:
            pre_schedule_warnings.append("benchmark_cycle:core_replay_seed_failed")

    schedule = (schedule_runner or run_recommendation_benchmark_schedule)(
        database,
        options=options.schedule_options,
    )
    cycle_key = _cycle_key(options)
    warnings = [*pre_schedule_warnings, *schedule.warnings]
    seed_passed = core_replay_seed is None or core_replay_seed.passed
    if not options.run_gate:
        warnings.append("benchmark_cycle:quality_gate_skipped")
        result = _cycle_result(
            cycle_key=cycle_key,
            cycle_preset=options.cycle_preset,
            status="gate_skipped" if seed_passed else "failed",
            passed=seed_passed,
            core_replay_seed=core_replay_seed,
            schedule=schedule,
            gate=None,
            warnings=warnings,
        )
        return _maybe_save_cycle_report(
            database,
            result=result,
            options=options,
            cycle_repository=cycle_repository,
        )

    if schedule.benchmark.stored_report is None:
        warnings.append(
            "benchmark_cycle:gate_reads_existing_history_without_current_saved_report"
        )
    gate_options = _gate_options_for_schedule(
        options.gate_options,
        schedule=schedule,
        strategy=options.schedule_options.strategy,
    )
    gate = (gate_runner or run_recommendation_benchmark_quality_gate)(
        database,
        options=gate_options,
    )
    warnings.extend(gate.warnings)
    result = _cycle_result(
        cycle_key=cycle_key,
        cycle_preset=options.cycle_preset,
        status="passed" if gate.passed and seed_passed else "failed",
        passed=gate.passed and seed_passed,
        core_replay_seed=core_replay_seed,
        schedule=schedule,
        gate=gate,
        warnings=_dedupe_strings(warnings),
    )
    return _maybe_save_cycle_report(
        database,
        result=result,
        options=options,
        cycle_repository=cycle_repository,
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
    result = run_recommendation_benchmark_cycle(
        database,
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        _write_cycle_output(result, args.output_path)
    print(result.model_dump_json(indent=2))
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _write_cycle_output(
    result: RecommendationBenchmarkCycleRunResult,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{result.model_dump_json(indent=2)}\n", encoding="utf-8")


def _maybe_save_cycle_report(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    result: RecommendationBenchmarkCycleRunResult,
    options: RecommendationBenchmarkCycleOptions,
    cycle_repository: RecommendationBenchmarkCycleRunRepository | None,
) -> RecommendationBenchmarkCycleRunResult:
    if not options.save_cycle_report:
        return result
    repository = cycle_repository or PostgresRecommendationBenchmarkCycleRunRepository(
        database
    )
    stored = repository.save_run(result)
    return result.model_copy(update={"stored_cycle_report": stored})


def _cycle_result(
    *,
    cycle_key: str,
    cycle_preset: str | None,
    status: RecommendationBenchmarkCycleStatus,
    passed: bool,
    core_replay_seed: RecommendationBenchmarkCoreReplaySeedResult | None,
    schedule: RecommendationBenchmarkScheduleRunResult,
    gate: RecommendationBenchmarkQualityGateResult | None,
    warnings: Sequence[str],
) -> RecommendationBenchmarkCycleRunResult:
    summary: dict[str, object] = {
        "cycle_key": cycle_key,
        "cycle_preset": cycle_preset,
        "status": status,
        "passed": passed,
        "schedule_key": schedule.schedule_key,
        "benchmark_key": schedule.benchmark.benchmark_key,
        "benchmark_scenario_count": schedule.benchmark.scenario_count,
        "benchmark_completed_count": schedule.benchmark.completed_count,
        "benchmark_failed_count": schedule.benchmark.failed_count,
        "stored_report_id": (
            schedule.benchmark.stored_report.recommendation_benchmark_run_id
            if schedule.benchmark.stored_report is not None
            else None
        ),
        "gate_key": gate.gate_key if gate is not None else None,
        "gate_status": gate.status if gate is not None else None,
        "gate_passed": gate.passed if gate is not None else None,
        "core_replay_seed_requested": core_replay_seed is not None,
        "core_replay_seed_passed": (
            core_replay_seed.passed if core_replay_seed is not None else None
        ),
        "core_replay_seed_profile": (
            core_replay_seed.profile if core_replay_seed is not None else None
        ),
        "core_replay_seed_reset": (
            core_replay_seed.reset_seed if core_replay_seed is not None else None
        ),
        "core_replay_seed_budget": (
            core_replay_seed.seed_budget if core_replay_seed is not None else None
        ),
        "core_replay_seed_benchmark_key": (
            core_replay_seed.benchmark.benchmark_key
            if core_replay_seed is not None
            else None
        ),
        "core_replay_seed_expected_scenario_count": (
            core_replay_seed.expected_scenario_count
            if core_replay_seed is not None
            else 0
        ),
        "core_replay_seed_stored_run_count": (
            core_replay_seed.stored_run_count if core_replay_seed is not None else 0
        ),
        "warnings": list(warnings),
        "calculation_basis": "recommendation_benchmark_cycle_v3_1",
    }
    summary.update(_cycle_gate_summary_fields(gate))
    return RecommendationBenchmarkCycleRunResult(
        cycle_key=cycle_key,
        status=status,
        passed=passed,
        schedule=schedule,
        gate=gate,
        warnings=list(warnings),
        summary_json=summary,
    )


def _cycle_gate_summary_fields(
    gate: RecommendationBenchmarkQualityGateResult | None,
) -> dict[str, object]:
    if gate is None:
        return {
            "gate_failed_checks": [],
            "global_best_selected_count": 0,
            "global_best_candidate_count": 0,
            "global_best_generated_option_count": 0,
            "core_replay_ready_ratio": None,
            "final_hit_sample_size": 0,
            "final_hit_coverage_ratio": None,
            "final_hit_rate": None,
            "average_core_replay_roi": None,
            "historical_suite_quality_gate_present": False,
            "historical_suite_quality_gate_passed": None,
            "historical_suite_quality_gate_key": None,
            "historical_suite_quality_gate_status": None,
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
            "unified_candidate_pool_present_count": 0,
            "unified_candidate_pool_valid_candidate_count": 0,
            "unified_candidate_pool_unique_family_count": 0,
            "unified_candidate_pool_unique_family_keys": [],
            "unified_candidate_pool_selection_mismatch_count": 0,
            "unified_candidate_pool_selected_2x1_count": 0,
            "unified_candidate_pool_selected_2x1_rate": None,
            "unified_candidate_pool_multiple_value_candidate_count": 0,
            "unified_candidate_pool_multiple_value_admitted_candidate_count": 0,
            "unified_candidate_pool_multiple_value_rejected_candidate_count": 0,
            "unified_candidate_pool_multiple_value_extra_option_count": 0,
            "unified_candidate_pool_selected_multiple_value_statuses": [],
            "unified_candidate_pool_selected_multiple_value_admitted_count": 0,
            "unified_candidate_pool_selected_multiple_value_rejected_count": 0,
            "unified_candidate_pool_selected_multiple_extra_option_count": 0,
            "unified_candidate_pool_multiple_value_rejection_reason_counts": {},
            "unified_candidate_pool_guard_preset": None,
            "runtime_profile_switch_preset": None,
            "runtime_profile_switch_gate_present": False,
            "runtime_profile_switch_ready": None,
            "runtime_profile_switch_key": None,
            "runtime_profile_switch_status": None,
            "runtime_profile_switch_rule_count": 0,
            "runtime_profile_switch_default_profile_written": None,
            "runtime_profile_switch_replay_present": False,
            "runtime_profile_switch_replay_passed": None,
            "runtime_profile_switch_replay_key": None,
            "runtime_profile_switch_replay_status": None,
            "runtime_profile_switch_replay_final_answer_count": 0,
            "runtime_profile_switch_replay_roi_delta": None,
            "runtime_profile_switch_replay_final_hit_harm_count_vs_original": 0,
            "runtime_profile_switch_replay_profit_loss_harm_count_vs_original": 0,
            "final_answer_segment_penalty_runtime_replay_preset": None,
            "final_answer_segment_penalty_runtime_replay_present": False,
            "final_answer_segment_penalty_runtime_replay_holdout_allowed": None,
            "final_answer_segment_penalty_runtime_replay_runtime_allowed": None,
            "final_answer_segment_penalty_runtime_replay_key": None,
            "final_answer_segment_penalty_runtime_replay_status": None,
            "final_answer_segment_penalty_runtime_replay_final_answer_count": 0,
            "final_answer_segment_penalty_runtime_replay_hit_count_delta": 0,
            "final_answer_segment_penalty_runtime_replay_roi_delta": None,
            "final_answer_segment_penalty_runtime_replay_harm_count": 0,
            "final_answer_segment_penalty_runtime_replay_final_hit_harm_count": 0,
            "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count": 0,
            "market_movement_runtime_activation_present": False,
            "market_movement_runtime_activation_key": None,
            "market_movement_runtime_activation_status": None,
            "market_movement_runtime_activation_ready": None,
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
            "market_movement_activation_sample_expansion_present": False,
            "market_movement_activation_sample_expansion_key": None,
            "market_movement_activation_sample_expansion_status": None,
            "market_movement_activation_sample_expansion_passed": None,
            "market_movement_activation_sample_expansion_promotion_ready": None,
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
            "market_movement_activation_sample_expansion_blockers": [],
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
            "replacement_reranker_shadow_admission_present": False,
            "replacement_reranker_shadow_admission_key": None,
            "replacement_reranker_shadow_admission_status": None,
            "replacement_reranker_shadow_admission_runtime_candidate_allowed": None,
            "replacement_reranker_shadow_admission_shadow_allowed": None,
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
            "global_planner_short_odds_adapter_runtime_final_hit_harm_count": 0,
            "global_planner_short_odds_adapter_runtime_profit_loss_harm_count": 0,
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
            "recommendation_strategy_promotion_gate_present": False,
            "recommendation_strategy_promotion_gate_key": None,
            "recommendation_strategy_promotion_gate_status": None,
            "recommendation_strategy_promotion_gate_ready": None,
            "recommendation_strategy_promotion_gate_final_answer_count": 0,
            "recommendation_strategy_promotion_gate_changed_final_answer_count": 0,
            "recommendation_strategy_promotion_gate_hit_delta_count": 0,
            "recommendation_strategy_promotion_gate_profit_loss_delta": None,
            "recommendation_strategy_promotion_gate_harm_count": 0,
            "recommendation_strategy_staged_activation_smoke_present": False,
            "recommendation_strategy_staged_activation_smoke_key": None,
            "recommendation_strategy_staged_activation_smoke_status": None,
            "recommendation_strategy_staged_activation_ready": None,
            "recommendation_strategy_staged_rule_count": 0,
            "recommendation_strategy_staged_allowed_competition_count": 0,
            "recommendation_strategy_staged_default_profile_written": None,
            "recommendation_strategy_default_path_isolation_present": False,
            "recommendation_strategy_default_path_isolation_key": None,
            "recommendation_strategy_default_path_isolation_status": None,
            "recommendation_strategy_default_path_isolated": None,
            "recommendation_strategy_default_adapter_status": None,
            "recommendation_strategy_default_adapter_selection_changed": None,
            "recommendation_strategy_explicit_opt_in_selection_changed": None,
            "recommendation_strategy_isolation_default_profile_written": None,
            "probability_calibration_profile_rolling_admission_present": False,
            "probability_calibration_profile_rolling_admission_key": None,
            "probability_calibration_profile_rolling_admission_status": None,
            "probability_calibration_profile_candidate_allowed": None,
            "probability_calibration_profile_shadow_allowed": None,
            "probability_calibration_profile_mode": None,
            "probability_calibration_profile_key": None,
            "probability_calibration_profile_overall_gate_passed": None,
            "probability_calibration_profile_overall_adjusted_fixture_count": 0,
            "probability_calibration_profile_overall_bucket_count": 0,
            "probability_calibration_profile_failed_fold_count": 0,
            "probability_calibration_profile_active_competition_fold_count": 0,
            "probability_calibration_profile_active_season_cutoff_fold_count": 0,
            "probability_calibration_profile_active_rolling_fold_count": 0,
            "probability_calibration_profile_model_quality_gate_present": False,
            "probability_calibration_profile_model_quality_gate_key": None,
            "probability_calibration_profile_model_quality_gate_status": None,
            "probability_calibration_profile_model_quality_gate_ready": None,
            "probability_calibration_profile_model_quality_selected_competition_count": 0,
            "probability_calibration_profile_model_quality_adjusted_slice_count": 0,
            "probability_calibration_profile_model_quality_adjusted_fixture_count": 0,
            "probability_calibration_profile_model_quality_skipped_fixture_count": 0,
            "probability_calibration_profile_model_quality_final_answer_changed_count": 0,
            "probability_calibration_profile_model_quality_brier_score_delta": None,
            "probability_calibration_profile_model_quality_log_loss_delta": None,
            "probability_calibration_profile_model_quality_mean_calibration_error_delta": None,
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
            "asian_handicap_segmented_model_quality_brier_score_delta": None,
            "asian_handicap_segmented_model_quality_log_loss_delta": None,
            "asian_handicap_segmented_model_quality_calibration_error_delta": None,
            "asian_handicap_segmented_model_quality_actual_probability_delta": None,
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
            "prematch_feature_rolling_admission_failed_fold_count": 0,
            "prematch_feature_rolling_admission_active_competition_fold_count": 0,
            "prematch_feature_rolling_admission_active_season_cutoff_fold_count": 0,
            "prematch_feature_rolling_admission_active_rolling_fold_count": 0,
            "prematch_feature_rolling_admission_best_feature_grid_candidate_id": None,
            "prematch_feature_rolling_admission_best_gate_passed": None,
            "prematch_feature_rolling_admission_best_suite_status": None,
            "prematch_feature_rolling_admission_overall_brier_score_delta": None,
            "prematch_feature_rolling_admission_overall_log_loss_delta": None,
            "prematch_feature_rolling_admission_overall_calibration_error_delta": None,
            "prematch_feature_rolling_admission_failed_checks": [],
            "prematch_feature_rolling_admission_warning_count": 0,
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
        }

    summary = gate.summary_json
    return {
        "gate_failed_checks": _summary_list(summary, "failed_checks"),
        "global_best_selected_count": _summary_int(
            summary,
            "global_best_selected_count",
        ),
        "global_best_candidate_count": _summary_int(
            summary,
            "global_best_candidate_count",
        ),
        "global_best_generated_option_count": _summary_int(
            summary,
            "global_best_generated_option_count",
        ),
        "core_replay_ready_ratio": _optional_float(
            summary.get("core_replay_ready_ratio")
        ),
        "final_hit_sample_size": _summary_int(summary, "final_hit_sample_size"),
        "final_hit_coverage_ratio": _optional_float(
            summary.get("final_hit_coverage_ratio")
        ),
        "final_hit_rate": _optional_float(summary.get("final_hit_rate")),
        "average_core_replay_roi": _optional_float(
            summary.get("average_core_replay_roi")
        ),
        "historical_suite_quality_gate_present": _summary_bool(
            summary,
            "historical_suite_quality_gate_present",
        ),
        "historical_suite_quality_gate_passed": _optional_bool(
            summary.get("historical_suite_quality_gate_passed")
        ),
        "historical_suite_quality_gate_key": _optional_str(
            summary.get("historical_suite_quality_gate_key")
        ),
        "historical_suite_quality_gate_status": _optional_str(
            summary.get("historical_suite_quality_gate_status")
        ),
        "historical_suite_quality_gate_suite_status": _optional_str(
            summary.get("historical_suite_quality_gate_suite_status")
        ),
        "historical_suite_slice_count": _summary_int(
            summary,
            "historical_suite_slice_count",
        ),
        "historical_suite_comparison_count": _summary_int(
            summary,
            "historical_suite_comparison_count",
        ),
        "historical_suite_candidate_final_hit_sample_size": _summary_int(
            summary,
            "historical_suite_candidate_final_hit_sample_size",
        ),
        "historical_suite_candidate_final_hit_coverage_ratio": _optional_float(
            summary.get("historical_suite_candidate_final_hit_coverage_ratio")
        ),
        "historical_suite_candidate_final_hit_rate": _optional_float(
            summary.get("historical_suite_candidate_final_hit_rate")
        ),
        "historical_suite_candidate_roi": _optional_float(
            summary.get("historical_suite_candidate_roi")
        ),
        "historical_suite_baseline_dynamic_mixed_final_answer_count": (
            _summary_int(
                summary,
                "historical_suite_baseline_dynamic_mixed_final_answer_count",
            )
        ),
        "historical_suite_candidate_dynamic_mixed_final_answer_count": (
            _summary_int(
                summary,
                "historical_suite_candidate_dynamic_mixed_final_answer_count",
            )
        ),
        "historical_suite_baseline_dynamic_mixed_final_answer_rate": (
            _optional_float(
                summary.get("historical_suite_baseline_dynamic_mixed_final_answer_rate")
            )
        ),
        "historical_suite_candidate_dynamic_mixed_final_answer_rate": (
            _optional_float(
                summary.get("historical_suite_candidate_dynamic_mixed_final_answer_rate")
            )
        ),
        "historical_suite_baseline_final_answer_market_type_counts": (
            _summary_mapping(
                summary,
                "historical_suite_baseline_final_answer_market_type_counts",
            )
        ),
        "historical_suite_candidate_final_answer_market_type_counts": (
            _summary_mapping(
                summary,
                "historical_suite_candidate_final_answer_market_type_counts",
            )
        ),
        "historical_suite_baseline_handicap_final_answer_count": _summary_int(
            summary,
            "historical_suite_baseline_handicap_final_answer_count",
        ),
        "historical_suite_candidate_handicap_final_answer_count": _summary_int(
            summary,
            "historical_suite_candidate_handicap_final_answer_count",
        ),
        "historical_suite_baseline_handicap_final_answer_rate": _optional_float(
            summary.get("historical_suite_baseline_handicap_final_answer_rate")
        ),
        "historical_suite_candidate_handicap_final_answer_rate": _optional_float(
            summary.get("historical_suite_candidate_handicap_final_answer_rate")
        ),
        "historical_suite_baseline_correct_score_final_answer_count": _summary_int(
            summary,
            "historical_suite_baseline_correct_score_final_answer_count",
        ),
        "historical_suite_candidate_correct_score_final_answer_count": _summary_int(
            summary,
            "historical_suite_candidate_correct_score_final_answer_count",
        ),
        "historical_suite_baseline_multiple_choice_final_answer_count": _summary_int(
            summary,
            "historical_suite_baseline_multiple_choice_final_answer_count",
        ),
        "historical_suite_candidate_multiple_choice_final_answer_count": _summary_int(
            summary,
            "historical_suite_candidate_multiple_choice_final_answer_count",
        ),
        "historical_suite_baseline_final_answer_selected_candidate_count": (
            _summary_int(
                summary,
                "historical_suite_baseline_final_answer_selected_candidate_count",
            )
        ),
        "historical_suite_candidate_final_answer_selected_candidate_count": (
            _summary_int(
                summary,
                "historical_suite_candidate_final_answer_selected_candidate_count",
            )
        ),
        "historical_suite_baseline_final_answer_multiple_choice_fixture_count": (
            _summary_int(
                summary,
                "historical_suite_baseline_final_answer_multiple_choice_fixture_count",
            )
        ),
        "historical_suite_candidate_final_answer_multiple_choice_fixture_count": (
            _summary_int(
                summary,
                "historical_suite_candidate_final_answer_multiple_choice_fixture_count",
            )
        ),
        "historical_suite_failed_check_count": _summary_int(
            summary,
            "historical_suite_failed_check_count",
        ),
        "historical_suite_lifecycle_quality_cycle_present": _summary_bool(
            summary,
            "historical_suite_lifecycle_quality_cycle_present",
        ),
        "historical_suite_lifecycle_quality_cycle_passed": _optional_bool(
            summary.get("historical_suite_lifecycle_quality_cycle_passed")
        ),
        "historical_suite_lifecycle_persisted_smoke_present": _summary_bool(
            summary,
            "historical_suite_lifecycle_persisted_smoke_present",
        ),
        "historical_suite_lifecycle_persisted_smoke_passed": _optional_bool(
            summary.get("historical_suite_lifecycle_persisted_smoke_passed")
        ),
        "historical_suite_lifecycle_source_status_synced": _optional_bool(
            summary.get("historical_suite_lifecycle_source_status_synced")
        ),
        "historical_suite_lifecycle_effective_leaf_count": _summary_int(
            summary,
            "historical_suite_lifecycle_effective_leaf_count",
        ),
        "historical_suite_lifecycle_active_edge_count": _summary_int(
            summary,
            "historical_suite_lifecycle_active_edge_count",
        ),
        "historical_suite_lifecycle_critical_issue_count": _summary_int(
            summary,
            "historical_suite_lifecycle_critical_issue_count",
        ),
        "historical_suite_lifecycle_source_status_sync_required_count": (
            _summary_int(
                summary,
                "historical_suite_lifecycle_source_status_sync_required_count",
            )
        ),
        "historical_suite_successor_chain_evaluation_present": _summary_bool(
            summary,
            "historical_suite_successor_chain_evaluation_present",
        ),
        "historical_suite_successor_chain_evaluation_passed": _optional_bool(
            summary.get("historical_suite_successor_chain_evaluation_passed")
        ),
        "historical_suite_successor_effective_final_only_ready": _summary_bool(
            summary,
            "historical_suite_successor_effective_final_only_ready",
        ),
        "historical_suite_successor_effective_leaf_count": _summary_int(
            summary,
            "historical_suite_successor_effective_leaf_count",
        ),
        "historical_suite_successor_active_edge_count": _summary_int(
            summary,
            "historical_suite_successor_active_edge_count",
        ),
        "historical_suite_successor_critical_issue_count": _summary_int(
            summary,
            "historical_suite_successor_critical_issue_count",
        ),
        "historical_suite_successor_ambiguous_source_count": _summary_int(
            summary,
            "historical_suite_successor_ambiguous_source_count",
        ),
        "historical_suite_successor_source_status_sync_required_count": _summary_int(
            summary,
            "historical_suite_successor_source_status_sync_required_count",
        ),
        "budget_stability_audit_present": _summary_bool(
            summary,
            "budget_stability_audit_present",
        ),
        "budget_stability_audit_key": _optional_str(
            summary.get("budget_stability_audit_key")
        ),
        "budget_stability_audit_status": _optional_str(
            summary.get("budget_stability_audit_status")
        ),
        "budget_stability_slice_count": _summary_int(
            summary,
            "budget_stability_slice_count",
        ),
        "budget_stability_budgets": _summary_list(
            summary,
            "budget_stability_budgets",
        ),
        "budget_stability_reference_budget": _optional_float(
            summary.get("budget_stability_reference_budget")
        ),
        "budget_stability_comparable_count": _summary_int(
            summary,
            "budget_stability_comparable_count",
        ),
        "budget_stability_signature_changed_count": _summary_int(
            summary,
            "budget_stability_signature_changed_count",
        ),
        "budget_stability_signature_change_rate": _optional_float(
            summary.get("budget_stability_signature_change_rate")
        ),
        "budget_stability_harmful_change_count": _summary_int(
            summary,
            "budget_stability_harmful_change_count",
        ),
        "budget_stability_beneficial_change_count": _summary_int(
            summary,
            "budget_stability_beneficial_change_count",
        ),
        "budget_stability_hit_delta_count": _summary_int(
            summary,
            "budget_stability_hit_delta_count",
        ),
        "budget_stability_profit_loss_delta": _optional_float(
            summary.get("budget_stability_profit_loss_delta")
        ),
        "budget_stability_roi_delta": _optional_float(
            summary.get("budget_stability_roi_delta")
        ),
        "budget_stability_warning_count": _summary_int(
            summary,
            "budget_stability_warning_count",
        ),
        "final_answer_market_concentration_audit_present": _summary_bool(
            summary,
            "final_answer_market_concentration_audit_present",
        ),
        "final_answer_market_concentration_audit_key": _optional_str(
            summary.get("final_answer_market_concentration_audit_key")
        ),
        "final_answer_market_concentration_audit_status": _optional_str(
            summary.get("final_answer_market_concentration_audit_status")
        ),
        "final_answer_market_concentration_audit_passed": _optional_bool(
            summary.get("final_answer_market_concentration_audit_passed")
        ),
        "final_answer_market_concentration_slice_count": _summary_int(
            summary,
            "final_answer_market_concentration_slice_count",
        ),
        "final_answer_market_concentration_final_answer_count": _summary_int(
            summary,
            "final_answer_market_concentration_final_answer_count",
        ),
        "final_answer_market_concentration_dynamic_mixed_final_answer_count": (
            _summary_int(
                summary,
                "final_answer_market_concentration_dynamic_mixed_final_answer_count",
            )
        ),
        "final_answer_market_concentration_dynamic_mixed_final_answer_rate": (
            _optional_float(
                summary.get(
                    "final_answer_market_concentration_dynamic_mixed_final_answer_rate"
                )
            )
        ),
        "final_answer_market_concentration_effective_pass_types": _summary_list(
            summary,
            "final_answer_market_concentration_effective_pass_types",
        ),
        "final_answer_market_concentration_effective_constraint_profiles": (
            _summary_list(
                summary,
                "final_answer_market_concentration_effective_constraint_profiles",
            )
        ),
        "final_answer_market_concentration_effective_constraint_profile_count": (
            _summary_int(
                summary,
                "final_answer_market_concentration_effective_constraint_profile_count",
            )
        ),
        (
            "final_answer_market_concentration_"
            "candidate_completed_dynamic_mix_lane_count"
        ): _summary_int(
            summary,
            (
                "final_answer_market_concentration_"
                "candidate_completed_dynamic_mix_lane_count"
            ),
        ),
        (
            "final_answer_market_concentration_"
            "candidate_final_answer_dynamic_mix_lane_count"
        ): _summary_int(
            summary,
            (
                "final_answer_market_concentration_"
                "candidate_final_answer_dynamic_mix_lane_count"
            ),
        ),
        "final_answer_market_concentration_failed_check_count": _summary_int(
            summary,
            "final_answer_market_concentration_failed_check_count",
        ),
        "final_answer_market_concentration_warning_count": _summary_int(
            summary,
            "final_answer_market_concentration_warning_count",
        ),
        "correct_score_admission_present": _summary_bool(
            summary,
            "correct_score_admission_present",
        ),
        "correct_score_admission_key": _optional_str(
            summary.get("correct_score_admission_key")
        ),
        "correct_score_admission_status": _optional_str(
            summary.get("correct_score_admission_status")
        ),
        "correct_score_admission_production_allowed": _optional_bool(
            summary.get("correct_score_admission_production_allowed")
        ),
        "correct_score_admission_holdout_allowed": _optional_bool(
            summary.get("correct_score_admission_holdout_allowed")
        ),
        "correct_score_admission_source_gate_key": _optional_str(
            summary.get("correct_score_admission_source_gate_key")
        ),
        "correct_score_admission_source_gate_status": _optional_str(
            summary.get("correct_score_admission_source_gate_status")
        ),
        "correct_score_admission_source_suite_status": _optional_str(
            summary.get("correct_score_admission_source_suite_status")
        ),
        "correct_score_admission_slice_count": _summary_int(
            summary,
            "correct_score_admission_slice_count",
        ),
        "correct_score_admission_comparison_count": _summary_int(
            summary,
            "correct_score_admission_comparison_count",
        ),
        "correct_score_admission_candidate_final_hit_sample_size": _summary_int(
            summary,
            "correct_score_admission_candidate_final_hit_sample_size",
        ),
        "correct_score_admission_candidate_final_hit_coverage_ratio": _optional_float(
            summary.get("correct_score_admission_candidate_final_hit_coverage_ratio")
        ),
        "correct_score_admission_candidate_final_hit_rate": _optional_float(
            summary.get("correct_score_admission_candidate_final_hit_rate")
        ),
        "correct_score_admission_candidate_roi": _optional_float(
            summary.get("correct_score_admission_candidate_roi")
        ),
        "correct_score_admission_candidate_correct_score_final_answer_count": (
            _summary_int(
                summary,
                "correct_score_admission_candidate_correct_score_final_answer_count",
            )
        ),
        "correct_score_admission_candidate_correct_score_final_answer_rate": (
            _optional_float(
                summary.get(
                    "correct_score_admission_candidate_correct_score_final_answer_rate"
                )
            )
        ),
        "correct_score_admission_final_hit_rate_delta": _optional_float(
            summary.get("correct_score_admission_final_hit_rate_delta")
        ),
        "correct_score_admission_roi_delta": _optional_float(
            summary.get("correct_score_admission_roi_delta")
        ),
        "correct_score_admission_profit_loss_delta": _optional_float(
            summary.get("correct_score_admission_profit_loss_delta")
        ),
        "correct_score_admission_brier_score_delta": _optional_float(
            summary.get("correct_score_admission_brier_score_delta")
        ),
        "correct_score_admission_log_loss_delta": _optional_float(
            summary.get("correct_score_admission_log_loss_delta")
        ),
        "correct_score_admission_mean_calibration_error_delta": _optional_float(
            summary.get("correct_score_admission_mean_calibration_error_delta")
        ),
        "correct_score_admission_production_recommendation_changed": _optional_bool(
            summary.get("correct_score_admission_production_recommendation_changed")
        ),
        "correct_score_admission_public_response_changed": _optional_bool(
            summary.get("correct_score_admission_public_response_changed")
        ),
        "correct_score_admission_failed_checks": _summary_list(
            summary,
            "correct_score_admission_failed_checks",
        ),
        "correct_score_admission_failed_check_count": _summary_int(
            summary,
            "correct_score_admission_failed_check_count",
        ),
        "correct_score_admission_warning_count": _summary_int(
            summary,
            "correct_score_admission_warning_count",
        ),
        "correct_score_admission_warnings": _summary_list(
            summary,
            "correct_score_admission_warnings",
        ),
        "unified_candidate_pool_present_count": _summary_int(
            summary,
            "unified_candidate_pool_present_count",
        ),
        "unified_candidate_pool_valid_candidate_count": _summary_int(
            summary,
            "unified_candidate_pool_valid_candidate_count",
        ),
        "unified_candidate_pool_unique_family_count": _summary_int(
            summary,
            "unified_candidate_pool_unique_family_count",
        ),
        "unified_candidate_pool_unique_family_keys": _summary_list(
            summary,
            "unified_candidate_pool_unique_family_keys",
        ),
        "unified_candidate_pool_selection_mismatch_count": _summary_int(
            summary,
            "unified_candidate_pool_selection_mismatch_count",
        ),
        "unified_candidate_pool_selected_2x1_count": _summary_int(
            summary,
            "unified_candidate_pool_selected_2x1_count",
        ),
        "unified_candidate_pool_selected_2x1_rate": _optional_float(
            summary.get("unified_candidate_pool_selected_2x1_rate")
        ),
        "unified_candidate_pool_multiple_value_candidate_count": _summary_int(
            summary,
            "unified_candidate_pool_multiple_value_candidate_count",
        ),
        "unified_candidate_pool_multiple_value_admitted_candidate_count": (
            _summary_int(
                summary,
                "unified_candidate_pool_multiple_value_admitted_candidate_count",
            )
        ),
        "unified_candidate_pool_multiple_value_rejected_candidate_count": (
            _summary_int(
                summary,
                "unified_candidate_pool_multiple_value_rejected_candidate_count",
            )
        ),
        "unified_candidate_pool_multiple_value_extra_option_count": _summary_int(
            summary,
            "unified_candidate_pool_multiple_value_extra_option_count",
        ),
        "unified_candidate_pool_selected_multiple_value_statuses": _summary_list(
            summary,
            "unified_candidate_pool_selected_multiple_value_statuses",
        ),
        "unified_candidate_pool_selected_multiple_value_admitted_count": _summary_int(
            summary,
            "unified_candidate_pool_selected_multiple_value_admitted_count",
        ),
        "unified_candidate_pool_selected_multiple_value_rejected_count": _summary_int(
            summary,
            "unified_candidate_pool_selected_multiple_value_rejected_count",
        ),
        "unified_candidate_pool_selected_multiple_extra_option_count": _summary_int(
            summary,
            "unified_candidate_pool_selected_multiple_extra_option_count",
        ),
        "unified_candidate_pool_multiple_value_rejection_reason_counts": _summary_mapping(
            summary,
            "unified_candidate_pool_multiple_value_rejection_reason_counts",
        ),
        "unified_candidate_pool_guard_preset": _optional_str(
            summary.get("unified_candidate_pool_guard_preset")
        ),
        "runtime_profile_switch_preset": _optional_str(
            summary.get("runtime_profile_switch_preset")
        ),
        "runtime_profile_switch_gate_present": _summary_bool(
            summary,
            "runtime_profile_switch_gate_present",
        ),
        "runtime_profile_switch_ready": _optional_bool(
            summary.get("runtime_profile_switch_ready")
        ),
        "runtime_profile_switch_key": _optional_str(
            summary.get("runtime_profile_switch_key")
        ),
        "runtime_profile_switch_status": _optional_str(
            summary.get("runtime_profile_switch_status")
        ),
        "runtime_profile_switch_rule_count": _summary_int(
            summary,
            "runtime_profile_switch_rule_count",
        ),
        "runtime_profile_switch_default_profile_written": _optional_bool(
            summary.get("runtime_profile_switch_default_profile_written")
        ),
        "runtime_profile_switch_replay_present": _summary_bool(
            summary,
            "runtime_profile_switch_replay_present",
        ),
        "runtime_profile_switch_replay_passed": _optional_bool(
            summary.get("runtime_profile_switch_replay_passed")
        ),
        "runtime_profile_switch_replay_key": _optional_str(
            summary.get("runtime_profile_switch_replay_key")
        ),
        "runtime_profile_switch_replay_status": _optional_str(
            summary.get("runtime_profile_switch_replay_status")
        ),
        "runtime_profile_switch_replay_final_answer_count": _summary_int(
            summary,
            "runtime_profile_switch_replay_final_answer_count",
        ),
        "runtime_profile_switch_replay_roi_delta": _optional_float(
            summary.get("runtime_profile_switch_replay_roi_delta")
        ),
        "runtime_profile_switch_replay_final_hit_harm_count_vs_original": (
            _summary_int(
                summary,
                "runtime_profile_switch_replay_final_hit_harm_count_vs_original",
            )
        ),
        "runtime_profile_switch_replay_profit_loss_harm_count_vs_original": (
            _summary_int(
                summary,
                "runtime_profile_switch_replay_profit_loss_harm_count_vs_original",
            )
        ),
        "final_answer_segment_penalty_runtime_replay_preset": _optional_str(
            summary.get("final_answer_segment_penalty_runtime_replay_preset")
        ),
        "final_answer_segment_penalty_runtime_replay_present": _summary_bool(
            summary,
            "final_answer_segment_penalty_runtime_replay_present",
        ),
        "final_answer_segment_penalty_runtime_replay_holdout_allowed": _optional_bool(
            summary.get("final_answer_segment_penalty_runtime_replay_holdout_allowed")
        ),
        "final_answer_segment_penalty_runtime_replay_runtime_allowed": _optional_bool(
            summary.get("final_answer_segment_penalty_runtime_replay_runtime_allowed")
        ),
        "final_answer_segment_penalty_runtime_replay_key": _optional_str(
            summary.get("final_answer_segment_penalty_runtime_replay_key")
        ),
        "final_answer_segment_penalty_runtime_replay_status": _optional_str(
            summary.get("final_answer_segment_penalty_runtime_replay_status")
        ),
        "final_answer_segment_penalty_runtime_replay_final_answer_count": _summary_int(
            summary,
            "final_answer_segment_penalty_runtime_replay_final_answer_count",
        ),
        "final_answer_segment_penalty_runtime_replay_hit_count_delta": _summary_int(
            summary,
            "final_answer_segment_penalty_runtime_replay_hit_count_delta",
        ),
        "final_answer_segment_penalty_runtime_replay_roi_delta": _optional_float(
            summary.get("final_answer_segment_penalty_runtime_replay_roi_delta")
        ),
        "final_answer_segment_penalty_runtime_replay_harm_count": _summary_int(
            summary,
            "final_answer_segment_penalty_runtime_replay_harm_count",
        ),
        "final_answer_segment_penalty_runtime_replay_final_hit_harm_count": (
            _summary_int(
                summary,
                "final_answer_segment_penalty_runtime_replay_final_hit_harm_count",
            )
        ),
        "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count": (
            _summary_int(
                summary,
                "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count",
            )
        ),
        "market_movement_runtime_activation_present": _summary_bool(
            summary,
            "market_movement_runtime_activation_present",
        ),
        "market_movement_runtime_activation_key": _optional_str(
            summary.get("market_movement_runtime_activation_key")
        ),
        "market_movement_runtime_activation_status": _optional_str(
            summary.get("market_movement_runtime_activation_status")
        ),
        "market_movement_runtime_activation_ready": _optional_bool(
            summary.get("market_movement_runtime_activation_ready")
        ),
        "market_movement_runtime_activation_rule_count": _summary_int(
            summary,
            "market_movement_runtime_activation_rule_count",
        ),
        "market_movement_runtime_activation_selected_rule_count": _summary_int(
            summary,
            "market_movement_runtime_activation_selected_rule_count",
        ),
        "market_movement_runtime_activation_selected_rule_ids": _summary_list(
            summary,
            "market_movement_runtime_activation_selected_rule_ids",
        ),
        "market_movement_runtime_activation_selected_segment_group_keys": (
            _summary_list(
                summary,
                "market_movement_runtime_activation_selected_segment_group_keys",
            )
        ),
        "market_movement_runtime_activation_adjusted_fixture_count": _summary_int(
            summary,
            "market_movement_runtime_activation_adjusted_fixture_count",
        ),
        "market_movement_runtime_activation_adjusted_prediction_count": _summary_int(
            summary,
            "market_movement_runtime_activation_adjusted_prediction_count",
        ),
        "market_movement_runtime_activation_final_hit_rate_delta": _optional_float(
            summary.get("market_movement_runtime_activation_final_hit_rate_delta")
        ),
        "market_movement_runtime_activation_roi_delta": _optional_float(
            summary.get("market_movement_runtime_activation_roi_delta")
        ),
        "market_movement_runtime_activation_profit_loss_delta": _optional_float(
            summary.get("market_movement_runtime_activation_profit_loss_delta")
        ),
        "market_movement_runtime_activation_brier_score_delta": _optional_float(
            summary.get("market_movement_runtime_activation_brier_score_delta")
        ),
        "market_movement_runtime_activation_log_loss_delta": _optional_float(
            summary.get("market_movement_runtime_activation_log_loss_delta")
        ),
        "market_movement_runtime_activation_calibration_delta": _optional_float(
            summary.get("market_movement_runtime_activation_calibration_delta")
        ),
        "market_movement_runtime_activation_default_profile_written": _optional_bool(
            summary.get("market_movement_runtime_activation_default_profile_written")
        ),
        "market_movement_runtime_activation_default_path_changed": _optional_bool(
            summary.get("market_movement_runtime_activation_default_path_changed")
        ),
        "market_movement_runtime_activation_production_changed": _optional_bool(
            summary.get("market_movement_runtime_activation_production_changed")
        ),
        "market_movement_runtime_activation_public_changed": _optional_bool(
            summary.get("market_movement_runtime_activation_public_changed")
        ),
        "market_movement_runtime_activation_blockers": _summary_list(
            summary,
            "market_movement_runtime_activation_blockers",
        ),
        "market_movement_runtime_activation_failed_checks": _summary_list(
            summary,
            "market_movement_runtime_activation_failed_checks",
        ),
        "market_movement_activation_sample_expansion_present": _summary_bool(
            summary,
            "market_movement_activation_sample_expansion_present",
        ),
        "market_movement_activation_sample_expansion_key": _optional_str(
            summary.get("market_movement_activation_sample_expansion_key")
        ),
        "market_movement_activation_sample_expansion_status": _optional_str(
            summary.get("market_movement_activation_sample_expansion_status")
        ),
        "market_movement_activation_sample_expansion_passed": _optional_bool(
            summary.get("market_movement_activation_sample_expansion_passed")
        ),
        "market_movement_activation_sample_expansion_promotion_ready": _optional_bool(
            summary.get(
                "market_movement_activation_sample_expansion_promotion_ready"
            )
        ),
        "market_movement_activation_sample_expansion_combined_fixture_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_combined_fixture_count",
            )
        ),
        "market_movement_activation_sample_expansion_combined_competition_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_combined_competition_count",
            )
        ),
        "market_movement_activation_sample_expansion_adjusted_fixture_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_adjusted_fixture_count",
            )
        ),
        "market_movement_activation_sample_expansion_adjusted_ratio": _optional_float(
            summary.get("market_movement_activation_sample_expansion_adjusted_ratio")
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_gate_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_segment_replay_batch_gate_count",
            )
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_ready_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_segment_replay_batch_ready_count",
            )
        ),
        "market_movement_activation_sample_expansion_segment_replay_batch_adjusted_fixture_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_segment_replay_batch_adjusted_fixture_count",
            )
        ),
        "market_movement_activation_sample_expansion_effective_segment_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_effective_segment_count",
            )
        ),
        "market_movement_activation_sample_expansion_effective_adjusted_fixture_count": (
            _summary_int(
                summary,
                "market_movement_activation_sample_expansion_effective_adjusted_fixture_count",
            )
        ),
        "market_movement_activation_sample_expansion_effective_adjusted_ratio": (
            _optional_float(
                summary.get(
                    "market_movement_activation_sample_expansion_effective_adjusted_ratio"
                )
            )
        ),
        "market_movement_activation_sample_expansion_watchlist": _summary_list(
            summary,
            "market_movement_activation_sample_expansion_watchlist",
        ),
        "market_movement_activation_sample_expansion_blockers": _summary_list(
            summary,
            "market_movement_activation_sample_expansion_blockers",
        ),
        "market_movement_segment_replay_batch_present": _summary_bool(
            summary,
            "market_movement_segment_replay_batch_present",
        ),
        "market_movement_segment_replay_batch_key": _optional_str(
            summary.get("market_movement_segment_replay_batch_key")
        ),
        "market_movement_segment_replay_batch_status": _optional_str(
            summary.get("market_movement_segment_replay_batch_status")
        ),
        "market_movement_segment_replay_batch_passed": _optional_bool(
            summary.get("market_movement_segment_replay_batch_passed")
        ),
        "market_movement_segment_replay_batch_ready": _optional_bool(
            summary.get("market_movement_segment_replay_batch_ready")
        ),
        "market_movement_segment_replay_batch_promotion_ready": _optional_bool(
            summary.get("market_movement_segment_replay_batch_promotion_ready")
        ),
        "market_movement_segment_replay_batch_report_count": _summary_int(
            summary,
            "market_movement_segment_replay_batch_report_count",
        ),
        "market_movement_segment_replay_batch_passed_count": _summary_int(
            summary,
            "market_movement_segment_replay_batch_passed_count",
        ),
        "market_movement_segment_replay_batch_failed_count": _summary_int(
            summary,
            "market_movement_segment_replay_batch_failed_count",
        ),
        "market_movement_segment_replay_batch_adjusted_fixture_count": _summary_int(
            summary,
            "market_movement_segment_replay_batch_adjusted_fixture_count",
        ),
        "market_movement_segment_replay_batch_adjusted_prediction_count": _summary_int(
            summary,
            "market_movement_segment_replay_batch_adjusted_prediction_count",
        ),
        "market_movement_segment_replay_batch_weighted_brier_delta": _optional_float(
            summary.get("market_movement_segment_replay_batch_weighted_brier_delta")
        ),
        "market_movement_segment_replay_batch_weighted_log_loss_delta": (
            _optional_float(
                summary.get(
                    "market_movement_segment_replay_batch_weighted_log_loss_delta"
                )
            )
        ),
        "market_movement_segment_replay_batch_weighted_calibration_delta": (
            _optional_float(
                summary.get(
                    "market_movement_segment_replay_batch_weighted_calibration_delta"
                )
            )
        ),
        "market_movement_segment_replay_batch_watchlist": _summary_list(
            summary,
            "market_movement_segment_replay_batch_watchlist",
        ),
        "market_movement_segment_replay_batch_blockers": _summary_list(
            summary,
            "market_movement_segment_replay_batch_blockers",
        ),
        "replacement_reranker_shadow_admission_present": _summary_bool(
            summary,
            "replacement_reranker_shadow_admission_present",
        ),
        "replacement_reranker_shadow_admission_key": _optional_str(
            summary.get("replacement_reranker_shadow_admission_key")
        ),
        "replacement_reranker_shadow_admission_status": _optional_str(
            summary.get("replacement_reranker_shadow_admission_status")
        ),
        "replacement_reranker_shadow_admission_runtime_candidate_allowed": (
            _optional_bool(
                summary.get(
                    "replacement_reranker_shadow_admission_runtime_candidate_allowed"
                )
            )
        ),
        "replacement_reranker_shadow_admission_shadow_allowed": _optional_bool(
            summary.get("replacement_reranker_shadow_admission_shadow_allowed")
        ),
        "replacement_reranker_source_surface_kind": _optional_str(
            summary.get("replacement_reranker_source_surface_kind")
        ),
        "replacement_reranker_source_surface_missed_legs_only": _optional_bool(
            summary.get("replacement_reranker_source_surface_missed_legs_only")
        ),
        "replacement_reranker_source_surface_selected_leg_count": _summary_int(
            summary,
            "replacement_reranker_source_surface_selected_leg_count",
        ),
        "replacement_reranker_source_surface_final_answer_count": _summary_int(
            summary,
            "replacement_reranker_source_surface_final_answer_count",
        ),
        "replacement_reranker_shadow_admission_scope_enabled": _summary_bool(
            summary,
            "replacement_reranker_shadow_admission_scope_enabled",
        ),
        "replacement_reranker_shadow_admission_scope_final_answer_count": (
            _summary_int(
                summary,
                "replacement_reranker_shadow_admission_scope_final_answer_count",
            )
        ),
        "replacement_reranker_shadow_final_answer_count": _summary_int(
            summary,
            "replacement_reranker_shadow_final_answer_count",
        ),
        "replacement_reranker_changed_from_model_top_count": _summary_int(
            summary,
            "replacement_reranker_changed_from_model_top_count",
        ),
        "replacement_reranker_hit_delta_vs_model_top": _summary_int(
            summary,
            "replacement_reranker_hit_delta_vs_model_top",
        ),
        "replacement_reranker_profit_loss_delta_vs_model_top": _optional_float(
            summary.get("replacement_reranker_profit_loss_delta_vs_model_top")
        ),
        "replacement_reranker_roi_delta_vs_model_top": _optional_float(
            summary.get("replacement_reranker_roi_delta_vs_model_top")
        ),
        "replacement_reranker_harm_count_vs_model_top": _summary_int(
            summary,
            "replacement_reranker_harm_count_vs_model_top",
        ),
        "replacement_reranker_final_hit_harm_count_vs_model_top": _summary_int(
            summary,
            "replacement_reranker_final_hit_harm_count_vs_model_top",
        ),
        "replacement_reranker_profit_loss_harm_count_vs_model_top": _summary_int(
            summary,
            "replacement_reranker_profit_loss_harm_count_vs_model_top",
        ),
        "replacement_reranker_failed_fold_count": _summary_int(
            summary,
            "replacement_reranker_failed_fold_count",
        ),
        "replacement_reranker_active_competition_fold_count": _summary_int(
            summary,
            "replacement_reranker_active_competition_fold_count",
        ),
        "replacement_reranker_active_season_fold_count": _summary_int(
            summary,
            "replacement_reranker_active_season_fold_count",
        ),
        "replacement_reranker_active_rolling_fold_count": _summary_int(
            summary,
            "replacement_reranker_active_rolling_fold_count",
        ),
        "global_planner_short_odds_adapter_gate_present": _summary_bool(
            summary,
            "global_planner_short_odds_adapter_gate_present",
        ),
        "global_planner_short_odds_adapter_gate_key": _optional_str(
            summary.get("global_planner_short_odds_adapter_gate_key")
        ),
        "global_planner_short_odds_adapter_gate_status": _optional_str(
            summary.get("global_planner_short_odds_adapter_gate_status")
        ),
        "global_planner_short_odds_adapter_gate_passed": _optional_bool(
            summary.get("global_planner_short_odds_adapter_gate_passed")
        ),
        "global_planner_short_odds_adapter_default_path_changed": _optional_bool(
            summary.get("global_planner_short_odds_adapter_default_path_changed")
        ),
        "global_planner_short_odds_adapter_shadow_path_changed": _optional_bool(
            summary.get("global_planner_short_odds_adapter_shadow_path_changed")
        ),
        "global_planner_short_odds_adapter_explicit_opt_in_changed": _optional_bool(
            summary.get("global_planner_short_odds_adapter_explicit_opt_in_changed")
        ),
        "global_planner_short_odds_adapter_runtime_final_answer_count": _summary_int(
            summary,
            "global_planner_short_odds_adapter_runtime_final_answer_count",
        ),
        "global_planner_short_odds_adapter_runtime_changed_final_answer_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_runtime_changed_final_answer_count",
            )
        ),
        "global_planner_short_odds_adapter_runtime_roi_delta": _optional_float(
            summary.get("global_planner_short_odds_adapter_runtime_roi_delta")
        ),
        "global_planner_short_odds_adapter_runtime_final_hit_harm_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_runtime_final_hit_harm_count",
            )
        ),
        "global_planner_short_odds_adapter_runtime_profit_loss_harm_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_runtime_profit_loss_harm_count",
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_present": _summary_bool(
            summary,
            "global_planner_short_odds_adapter_sample_expansion_present",
        ),
        "global_planner_short_odds_adapter_sample_expansion_key": _optional_str(
            summary.get("global_planner_short_odds_adapter_sample_expansion_key")
        ),
        "global_planner_short_odds_adapter_sample_expansion_status": _optional_str(
            summary.get("global_planner_short_odds_adapter_sample_expansion_status")
        ),
        "global_planner_short_odds_adapter_sample_expansion_passed": _optional_bool(
            summary.get("global_planner_short_odds_adapter_sample_expansion_passed")
        ),
        "global_planner_short_odds_adapter_sample_expansion_promotion_ready": (
            _optional_bool(
                summary.get(
                    "global_planner_short_odds_adapter_sample_expansion_promotion_ready"
                )
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_supplemental_final_answer_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_sample_expansion_supplemental_final_answer_count",
            )
        ),
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "supplemental_changed_final_answer_count"
        ): (
            _summary_int(
                summary,
                (
                    "global_planner_short_odds_adapter_sample_expansion_"
                    "supplemental_changed_final_answer_count"
                ),
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_final_answer_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_sample_expansion_combined_final_answer_count",
            )
        ),
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "combined_changed_final_answer_count"
        ): (
            _summary_int(
                summary,
                (
                    "global_planner_short_odds_adapter_sample_expansion_"
                    "combined_changed_final_answer_count"
                ),
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_roi_delta": (
            _optional_float(
                summary.get(
                    "global_planner_short_odds_adapter_sample_expansion_combined_roi_delta"
                )
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_combined_harm_count": (
            _summary_int(
                summary,
                "global_planner_short_odds_adapter_sample_expansion_combined_harm_count",
            )
        ),
        "global_planner_short_odds_adapter_sample_expansion_watchlist_checks": (
            _summary_list(
                summary,
                "global_planner_short_odds_adapter_sample_expansion_watchlist_checks",
            )
        ),
        "recommendation_strategy_promotion_gate_present": _summary_bool(
            summary,
            "recommendation_strategy_promotion_gate_present",
        ),
        "recommendation_strategy_promotion_gate_key": _optional_str(
            summary.get("recommendation_strategy_promotion_gate_key")
        ),
        "recommendation_strategy_promotion_gate_status": _optional_str(
            summary.get("recommendation_strategy_promotion_gate_status")
        ),
        "recommendation_strategy_promotion_gate_ready": _optional_bool(
            summary.get("recommendation_strategy_promotion_gate_ready")
        ),
        "recommendation_strategy_promotion_gate_final_answer_count": _summary_int(
            summary,
            "recommendation_strategy_promotion_gate_final_answer_count",
        ),
        (
            "recommendation_strategy_promotion_gate_changed_final_answer_count"
        ): _summary_int(
            summary,
            "recommendation_strategy_promotion_gate_changed_final_answer_count",
        ),
        "recommendation_strategy_promotion_gate_hit_delta_count": _summary_int(
            summary,
            "recommendation_strategy_promotion_gate_hit_delta_count",
        ),
        "recommendation_strategy_promotion_gate_profit_loss_delta": _optional_float(
            summary.get("recommendation_strategy_promotion_gate_profit_loss_delta")
        ),
        "recommendation_strategy_promotion_gate_harm_count": _summary_int(
            summary,
            "recommendation_strategy_promotion_gate_harm_count",
        ),
        "recommendation_strategy_staged_activation_smoke_present": _summary_bool(
            summary,
            "recommendation_strategy_staged_activation_smoke_present",
        ),
        "recommendation_strategy_staged_activation_smoke_key": _optional_str(
            summary.get("recommendation_strategy_staged_activation_smoke_key")
        ),
        "recommendation_strategy_staged_activation_smoke_status": _optional_str(
            summary.get("recommendation_strategy_staged_activation_smoke_status")
        ),
        "recommendation_strategy_staged_activation_ready": _optional_bool(
            summary.get("recommendation_strategy_staged_activation_ready")
        ),
        "recommendation_strategy_staged_rule_count": _summary_int(
            summary,
            "recommendation_strategy_staged_rule_count",
        ),
        "recommendation_strategy_staged_allowed_competition_count": _summary_int(
            summary,
            "recommendation_strategy_staged_allowed_competition_count",
        ),
        "recommendation_strategy_staged_default_profile_written": _optional_bool(
            summary.get("recommendation_strategy_staged_default_profile_written")
        ),
        "recommendation_strategy_default_path_isolation_present": _summary_bool(
            summary,
            "recommendation_strategy_default_path_isolation_present",
        ),
        "recommendation_strategy_default_path_isolation_key": _optional_str(
            summary.get("recommendation_strategy_default_path_isolation_key")
        ),
        "recommendation_strategy_default_path_isolation_status": _optional_str(
            summary.get("recommendation_strategy_default_path_isolation_status")
        ),
        "recommendation_strategy_default_path_isolated": _optional_bool(
            summary.get("recommendation_strategy_default_path_isolated")
        ),
        "recommendation_strategy_default_adapter_status": _optional_str(
            summary.get("recommendation_strategy_default_adapter_status")
        ),
        "recommendation_strategy_default_adapter_selection_changed": _optional_bool(
            summary.get("recommendation_strategy_default_adapter_selection_changed")
        ),
        "recommendation_strategy_explicit_opt_in_selection_changed": _optional_bool(
            summary.get("recommendation_strategy_explicit_opt_in_selection_changed")
        ),
        "recommendation_strategy_isolation_default_profile_written": _optional_bool(
            summary.get("recommendation_strategy_isolation_default_profile_written")
        ),
        "probability_calibration_profile_rolling_admission_present": _summary_bool(
            summary,
            "probability_calibration_profile_rolling_admission_present",
        ),
        "probability_calibration_profile_rolling_admission_key": _optional_str(
            summary.get("probability_calibration_profile_rolling_admission_key")
        ),
        "probability_calibration_profile_rolling_admission_status": _optional_str(
            summary.get("probability_calibration_profile_rolling_admission_status")
        ),
        "probability_calibration_profile_candidate_allowed": _optional_bool(
            summary.get("probability_calibration_profile_candidate_allowed")
        ),
        "probability_calibration_profile_shadow_allowed": _optional_bool(
            summary.get("probability_calibration_profile_shadow_allowed")
        ),
        "probability_calibration_profile_mode": _optional_str(
            summary.get("probability_calibration_profile_mode")
        ),
        "probability_calibration_profile_key": _optional_str(
            summary.get("probability_calibration_profile_key")
        ),
        "probability_calibration_profile_overall_gate_passed": _optional_bool(
            summary.get("probability_calibration_profile_overall_gate_passed")
        ),
        "probability_calibration_profile_overall_adjusted_fixture_count": _summary_int(
            summary,
            "probability_calibration_profile_overall_adjusted_fixture_count",
        ),
        "probability_calibration_profile_overall_bucket_count": _summary_int(
            summary,
            "probability_calibration_profile_overall_bucket_count",
        ),
        "probability_calibration_profile_failed_fold_count": _summary_int(
            summary,
            "probability_calibration_profile_failed_fold_count",
        ),
        "probability_calibration_profile_active_competition_fold_count": _summary_int(
            summary,
            "probability_calibration_profile_active_competition_fold_count",
        ),
        "probability_calibration_profile_active_season_cutoff_fold_count": _summary_int(
            summary,
            "probability_calibration_profile_active_season_cutoff_fold_count",
        ),
        "probability_calibration_profile_active_rolling_fold_count": _summary_int(
            summary,
            "probability_calibration_profile_active_rolling_fold_count",
        ),
        "probability_calibration_profile_model_quality_gate_present": _summary_bool(
            summary,
            "probability_calibration_profile_model_quality_gate_present",
        ),
        "probability_calibration_profile_model_quality_gate_key": _optional_str(
            summary.get("probability_calibration_profile_model_quality_gate_key")
        ),
        "probability_calibration_profile_model_quality_gate_status": _optional_str(
            summary.get("probability_calibration_profile_model_quality_gate_status")
        ),
        "probability_calibration_profile_model_quality_gate_ready": _optional_bool(
            summary.get("probability_calibration_profile_model_quality_gate_ready")
        ),
        "probability_calibration_profile_model_quality_selected_competition_count": (
            _summary_int(
                summary,
                "probability_calibration_profile_model_quality_selected_competition_count",
            )
        ),
        "probability_calibration_profile_model_quality_adjusted_slice_count": (
            _summary_int(
                summary,
                "probability_calibration_profile_model_quality_adjusted_slice_count",
            )
        ),
        "probability_calibration_profile_model_quality_adjusted_fixture_count": (
            _summary_int(
                summary,
                "probability_calibration_profile_model_quality_adjusted_fixture_count",
            )
        ),
        "probability_calibration_profile_model_quality_skipped_fixture_count": (
            _summary_int(
                summary,
                "probability_calibration_profile_model_quality_skipped_fixture_count",
            )
        ),
        "probability_calibration_profile_model_quality_final_answer_changed_count": (
            _summary_int(
                summary,
                "probability_calibration_profile_model_quality_final_answer_changed_count",
            )
        ),
        "probability_calibration_profile_model_quality_brier_score_delta": (
            _optional_float(
                summary.get("probability_calibration_profile_model_quality_brier_score_delta")
            )
        ),
        "probability_calibration_profile_model_quality_log_loss_delta": (
            _optional_float(
                summary.get("probability_calibration_profile_model_quality_log_loss_delta")
            )
        ),
        "probability_calibration_profile_model_quality_mean_calibration_error_delta": (
            _optional_float(
                summary.get(
                    "probability_calibration_profile_model_quality_mean_calibration_error_delta"
                )
            )
        ),
        "asian_handicap_segmented_model_quality_governance_present": _summary_bool(
            summary,
            "asian_handicap_segmented_model_quality_governance_present",
        ),
        "asian_handicap_segmented_model_quality_governance_key": _optional_str(
            summary.get("asian_handicap_segmented_model_quality_governance_key")
        ),
        "asian_handicap_segmented_model_quality_governance_status": _optional_str(
            summary.get("asian_handicap_segmented_model_quality_governance_status")
        ),
        "asian_handicap_segmented_model_quality_governance_ready": _optional_bool(
            summary.get("asian_handicap_segmented_model_quality_governance_ready")
        ),
        "asian_handicap_segmented_model_quality_internal_only": _optional_bool(
            summary.get("asian_handicap_segmented_model_quality_internal_only")
        ),
        "asian_handicap_segmented_model_quality_default_path_isolated": _optional_bool(
            summary.get(
                "asian_handicap_segmented_model_quality_default_path_isolated"
            )
        ),
        "asian_handicap_segmented_model_quality_production_allowed": _optional_bool(
            summary.get("asian_handicap_segmented_model_quality_production_allowed")
        ),
        "asian_handicap_segmented_model_quality_production_changed": _optional_bool(
            summary.get("asian_handicap_segmented_model_quality_production_changed")
        ),
        "asian_handicap_segmented_model_quality_public_response_changed": (
            _optional_bool(
                summary.get(
                    "asian_handicap_segmented_model_quality_public_response_changed"
                )
            )
        ),
        "asian_handicap_segmented_model_quality_accepted_segment_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_accepted_segment_count",
            )
        ),
        "asian_handicap_segmented_model_quality_shadow_segment_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_shadow_segment_count",
            )
        ),
        "asian_handicap_segmented_model_quality_fallback_segment_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_fallback_segment_count",
            )
        ),
        "asian_handicap_segmented_model_quality_rejected_segment_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_rejected_segment_count",
            )
        ),
        "asian_handicap_segmented_model_quality_accepted_validation_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_accepted_validation_count",
            )
        ),
        "asian_handicap_segmented_model_quality_calibration_applied_count": (
            _summary_int(
                summary,
                "asian_handicap_segmented_model_quality_calibration_applied_count",
            )
        ),
        "asian_handicap_segmented_model_quality_brier_score_delta": _optional_float(
            summary.get("asian_handicap_segmented_model_quality_brier_score_delta")
        ),
        "asian_handicap_segmented_model_quality_log_loss_delta": _optional_float(
            summary.get("asian_handicap_segmented_model_quality_log_loss_delta")
        ),
        "asian_handicap_segmented_model_quality_calibration_error_delta": (
            _optional_float(
                summary.get(
                    "asian_handicap_segmented_model_quality_calibration_error_delta"
                )
            )
        ),
        "asian_handicap_segmented_model_quality_actual_probability_delta": (
            _optional_float(
                summary.get(
                    "asian_handicap_segmented_model_quality_actual_probability_delta"
                )
            )
        ),
        "prematch_feature_quality_cycle_present": _summary_bool(
            summary,
            "prematch_feature_quality_cycle_present",
        ),
        "prematch_feature_quality_cycle_key": _optional_str(
            summary.get("prematch_feature_quality_cycle_key")
        ),
        "prematch_feature_quality_cycle_status": _optional_str(
            summary.get("prematch_feature_quality_cycle_status")
        ),
        "prematch_feature_quality_cycle_passed": _optional_bool(
            summary.get("prematch_feature_quality_cycle_passed")
        ),
        "prematch_feature_quality_cycle_final_answer_gate_key": _optional_str(
            summary.get("prematch_feature_quality_cycle_final_answer_gate_key")
        ),
        "prematch_feature_quality_cycle_grid_key": _optional_str(
            summary.get("prematch_feature_quality_cycle_grid_key")
        ),
        "prematch_feature_quality_cycle_slice_count": _summary_int(
            summary,
            "prematch_feature_quality_cycle_slice_count",
        ),
        "prematch_feature_quality_cycle_fixture_count": _summary_int(
            summary,
            "prematch_feature_quality_cycle_fixture_count",
        ),
        "prematch_feature_quality_cycle_evaluated_candidate_count": _summary_int(
            summary,
            "prematch_feature_quality_cycle_evaluated_candidate_count",
        ),
        "prematch_feature_quality_cycle_passing_candidate_count": _summary_int(
            summary,
            "prematch_feature_quality_cycle_passing_candidate_count",
        ),
        "prematch_feature_quality_cycle_best_feature_grid_candidate_id": _optional_str(
            summary.get("prematch_feature_quality_cycle_best_feature_grid_candidate_id")
        ),
        "prematch_feature_quality_cycle_best_feature_grid_rank": _summary_int(
            summary,
            "prematch_feature_quality_cycle_best_feature_grid_rank",
        ),
        "prematch_feature_quality_cycle_best_gate_passed": _optional_bool(
            summary.get("prematch_feature_quality_cycle_best_gate_passed")
        ),
        "prematch_feature_quality_cycle_best_suite_status": _optional_str(
            summary.get("prematch_feature_quality_cycle_best_suite_status")
        ),
        "prematch_feature_quality_cycle_best_brier_score_delta": _optional_float(
            summary.get("prematch_feature_quality_cycle_best_brier_score_delta")
        ),
        "prematch_feature_quality_cycle_best_log_loss_delta": _optional_float(
            summary.get("prematch_feature_quality_cycle_best_log_loss_delta")
        ),
        "prematch_feature_quality_cycle_best_calibration_error_delta": _optional_float(
            summary.get("prematch_feature_quality_cycle_best_calibration_error_delta")
        ),
        "prematch_feature_quality_cycle_best_failed_quality_check_names": _summary_list(
            summary,
            "prematch_feature_quality_cycle_best_failed_quality_check_names",
        ),
        "prematch_feature_quality_cycle_warning_count": _summary_int(
            summary,
            "prematch_feature_quality_cycle_warning_count",
        ),
        "prematch_feature_rolling_admission_present": _summary_bool(
            summary,
            "prematch_feature_rolling_admission_present",
        ),
        "prematch_feature_rolling_admission_key": _optional_str(
            summary.get("prematch_feature_rolling_admission_key")
        ),
        "prematch_feature_rolling_admission_status": _optional_str(
            summary.get("prematch_feature_rolling_admission_status")
        ),
        "prematch_feature_rolling_admission_candidate_allowed": _optional_bool(
            summary.get("prematch_feature_rolling_admission_candidate_allowed")
        ),
        "prematch_feature_rolling_admission_shadow_allowed": _optional_bool(
            summary.get("prematch_feature_rolling_admission_shadow_allowed")
        ),
        "prematch_feature_rolling_admission_source_grid_key": _optional_str(
            summary.get("prematch_feature_rolling_admission_source_grid_key")
        ),
        "prematch_feature_rolling_admission_overall_gate_key": _optional_str(
            summary.get("prematch_feature_rolling_admission_overall_gate_key")
        ),
        "prematch_feature_rolling_admission_overall_gate_passed": _optional_bool(
            summary.get("prematch_feature_rolling_admission_overall_gate_passed")
        ),
        "prematch_feature_rolling_admission_overall_evaluated_candidate_count": (
            _summary_int(
                summary,
                "prematch_feature_rolling_admission_overall_evaluated_candidate_count",
            )
        ),
        "prematch_feature_rolling_admission_overall_passing_candidate_count": (
            _summary_int(
                summary,
                "prematch_feature_rolling_admission_overall_passing_candidate_count",
            )
        ),
        "prematch_feature_rolling_admission_failed_fold_count": _summary_int(
            summary,
            "prematch_feature_rolling_admission_failed_fold_count",
        ),
        "prematch_feature_rolling_admission_active_competition_fold_count": (
            _summary_int(
                summary,
                "prematch_feature_rolling_admission_active_competition_fold_count",
            )
        ),
        "prematch_feature_rolling_admission_active_season_cutoff_fold_count": (
            _summary_int(
                summary,
                "prematch_feature_rolling_admission_active_season_cutoff_fold_count",
            )
        ),
        "prematch_feature_rolling_admission_active_rolling_fold_count": (
            _summary_int(
                summary,
                "prematch_feature_rolling_admission_active_rolling_fold_count",
            )
        ),
        "prematch_feature_rolling_admission_best_feature_grid_candidate_id": (
            _optional_str(
                summary.get(
                    "prematch_feature_rolling_admission_best_feature_grid_candidate_id"
                )
            )
        ),
        "prematch_feature_rolling_admission_best_gate_passed": _optional_bool(
            summary.get("prematch_feature_rolling_admission_best_gate_passed")
        ),
        "prematch_feature_rolling_admission_best_suite_status": _optional_str(
            summary.get("prematch_feature_rolling_admission_best_suite_status")
        ),
        "prematch_feature_rolling_admission_overall_brier_score_delta": (
            _optional_float(
                summary.get(
                    "prematch_feature_rolling_admission_overall_brier_score_delta"
                )
            )
        ),
        "prematch_feature_rolling_admission_overall_log_loss_delta": _optional_float(
            summary.get("prematch_feature_rolling_admission_overall_log_loss_delta")
        ),
        "prematch_feature_rolling_admission_overall_calibration_error_delta": (
            _optional_float(
                summary.get(
                    "prematch_feature_rolling_admission_overall_calibration_error_delta"
                )
            )
        ),
        "prematch_feature_rolling_admission_failed_checks": _summary_list(
            summary,
            "prematch_feature_rolling_admission_failed_checks",
        ),
        "prematch_feature_rolling_admission_warning_count": _summary_int(
            summary,
            "prematch_feature_rolling_admission_warning_count",
        ),
        "prematch_feature_sample_readiness_present": _summary_bool(
            summary,
            "prematch_feature_sample_readiness_present",
        ),
        "prematch_feature_sample_readiness_key": _optional_str(
            summary.get("prematch_feature_sample_readiness_key")
        ),
        "prematch_feature_sample_readiness_status": _optional_str(
            summary.get("prematch_feature_sample_readiness_status")
        ),
        "prematch_feature_sample_readiness_target_profile": _optional_str(
            summary.get("prematch_feature_sample_readiness_target_profile")
        ),
        "prematch_feature_sample_ready_allowed": _optional_bool(
            summary.get("prematch_feature_sample_ready_allowed")
        ),
        "prematch_feature_sample_readiness_shadow_allowed": _optional_bool(
            summary.get("prematch_feature_sample_readiness_shadow_allowed")
        ),
        "prematch_feature_sample_readiness_coverage_audit_key": _optional_str(
            summary.get("prematch_feature_sample_readiness_coverage_audit_key")
        ),
        "prematch_feature_sample_ready_source_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_source_count",
        ),
        "prematch_feature_sample_ready_fixture_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_fixture_count",
        ),
        "prematch_feature_sample_ready_slice_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_slice_count",
        ),
        "prematch_feature_sample_ready_competition_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_competition_count",
        ),
        "prematch_feature_sample_ready_season_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_season_count",
        ),
        "prematch_feature_sample_ready_competition_season_count": _summary_int(
            summary,
            "prematch_feature_sample_ready_competition_season_count",
        ),
        "prematch_feature_sample_readiness_failed_checks": _summary_list(
            summary,
            "prematch_feature_sample_readiness_failed_checks",
        ),
        "prematch_feature_sample_readiness_warning_count": _summary_int(
            summary,
            "prematch_feature_sample_readiness_warning_count",
        ),
    }


def _gate_options_for_schedule(
    options: RecommendationBenchmarkQualityGateOptions,
    *,
    schedule: RecommendationBenchmarkScheduleRunResult,
    strategy: RecommendationStrategy,
) -> RecommendationBenchmarkQualityGateOptions:
    return options.model_copy(
        update={
            "benchmark_key": options.benchmark_key or schedule.benchmark.benchmark_key,
            "strategy": options.strategy or strategy,
        }
    )


def _core_replay_seed_options(
    options: RecommendationBenchmarkCycleOptions,
) -> RecommendationBenchmarkCoreReplaySeedOptions:
    schedule = options.schedule_options
    seed_options = RecommendationBenchmarkCoreReplaySeedOptions(
        as_of_time_utc=schedule.normalized_run_at_utc,
        profile=options.core_replay_seed_profile,
        reset_seed=options.core_replay_seed_reset,
        lookback_hours=schedule.lookback_hours,
        pass_types=schedule.pass_types,
        modes=schedule.modes,
        max_budgets=schedule.max_budgets,
        strategy=schedule.strategy,
        unit_stake=schedule.unit_stake,
        min_probability=schedule.min_probability,
        min_data_quality_score=schedule.min_data_quality_score,
        require_odds=schedule.require_odds,
        candidate_limit=schedule.candidate_limit,
        requested_by=schedule.requested_by,
    )
    if schedule.competition_id is not None:
        seed_options = seed_options.model_copy(
            update={"competition_id": schedule.competition_id}
        )
    if schedule.model_version is not None:
        seed_options = seed_options.model_copy(
            update={"model_version": schedule.model_version}
        )
    return seed_options


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run a scheduled Nutmeg recommendation benchmark and quality gate."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument(
        "--cycle-preset",
        choices=RECOMMENDATION_BENCHMARK_CYCLE_PRESETS,
        default=None,
    )
    parser.add_argument("--schedule-name", default="default")
    parser.add_argument(
        "--cadence",
        choices=["once", "daily", "weekly"],
        default="daily",
    )
    parser.add_argument("--run-at-utc", default=None)
    parser.add_argument("--window-count", type=int, default=1)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_BENCHMARK_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_BENCHMARK_MODES))
    parser.add_argument(
        "--budgets",
        default=",".join(_budget_label(value) for value in DEFAULT_BENCHMARK_BUDGETS),
    )
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--min-probability", type=float, default=0.20)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--candidate-limit", type=int, default=300)
    parser.add_argument("--no-require-odds", action="store_true")
    parser.add_argument("--competition-id", default=None)
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--provider-name", default=None)
    parser.add_argument("--canonical-fixture-id", default=None)
    parser.add_argument("--requested-by", default=DEFAULT_BENCHMARK_REQUESTED_BY)
    parser.add_argument("--provider-observation-limit", type=int, default=2_000)
    parser.add_argument("--source-run-limit", type=int, default=100)
    parser.add_argument("--incident-limit", type=int, default=1_000)
    parser.add_argument("--report-limit", type=int, default=200)
    parser.add_argument("--replay-limit", type=int, default=200)
    parser.add_argument("--chain-integrity-limit", type=int, default=500)
    parser.add_argument("--include-prematch-pipeline", action="store_true")
    parser.add_argument("--skip-global-best", action="store_true")
    parser.add_argument("--skip-core-replay", action="store_true")
    parser.add_argument("--skip-chain-integrity", action="store_true")
    parser.add_argument("--skip-successor-chain-evaluation", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--save-cycle-report", action="store_true")
    parser.add_argument("--save-audit", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--commit-core-replay-seed", action="store_true")
    parser.add_argument(
        "--core-replay-seed-profile",
        choices=BASELINE_SEED_PROFILES,
        default=DEFAULT_BASELINE_SEED_PROFILE,
    )
    parser.add_argument("--no-core-replay-seed-reset", action="store_true")
    parser.add_argument("--gate-benchmark-key", default=None)
    parser.add_argument("--gate-history-limit", type=int, default=2)
    parser.add_argument("--allow-missing-history", action="store_true")
    parser.add_argument("--gate-min-scenario-count", type=int, default=1)
    parser.add_argument("--gate-min-completed-ratio", type=float, default=1.0)
    parser.add_argument("--gate-max-failed-count", type=int, default=0)
    parser.add_argument("--gate-max-warning-count", type=int, default=None)
    parser.add_argument("--gate-min-global-best-selected-count", type=int, default=0)
    parser.add_argument("--gate-min-global-best-candidate-count", type=int, default=0)
    parser.add_argument(
        "--gate-min-global-best-generated-option-count",
        type=int,
        default=0,
    )
    parser.add_argument("--gate-min-core-replay-ready-ratio", type=float, default=None)
    parser.add_argument("--gate-min-chain-integrity-ready-ratio", type=float, default=None)
    parser.add_argument(
        "--gate-max-chain-integrity-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-successor-chain-evaluation-passed-ratio",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-successor-chain-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-successor-chain-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-successor-chain-ambiguous-source-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-successor-chain-source-status-sync-required-count",
        type=int,
        default=None,
    )
    parser.add_argument("--gate-max-ambiguous-successor-source-count", type=int, default=0)
    parser.add_argument("--gate-max-stale-recommendation-count", type=int, default=0)
    parser.add_argument(
        "--gate-max-successor-recompute-required-count",
        type=int,
        default=0,
    )
    parser.add_argument("--gate-min-final-hit-sample-size", type=int, default=0)
    parser.add_argument("--gate-min-final-hit-coverage-ratio", type=float, default=None)
    parser.add_argument("--gate-min-final-hit-rate", type=float, default=None)
    parser.add_argument("--gate-min-average-core-replay-roi", type=float, default=None)
    parser.add_argument("--gate-min-upset-capture-sample-size", type=int, default=0)
    parser.add_argument("--gate-min-upset-capture-rate", type=float, default=None)
    parser.add_argument(
        "--gate-historical-suite-quality-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-historical-suite-quality-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-missing-historical-suite-lifecycle-evidence",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-unsynced-historical-suite-lifecycle-source-status",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-historical-suite-successor-chain-evaluation",
        action="store_true",
    )
    parser.add_argument("--gate-min-historical-suite-slice-count", type=int, default=0)
    parser.add_argument(
        "--gate-min-historical-suite-comparison-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-final-hit-sample-size",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-final-hit-coverage-ratio",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-dynamic-mixed-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-handicap-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-correct-score-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-candidate-multiple-choice-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-failed-check-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-lifecycle-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-lifecycle-active-edge-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-lifecycle-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-lifecycle-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-successor-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-historical-suite-successor-active-edge-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-successor-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-successor-ambiguous-source-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-historical-suite-successor-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-budget-stability-audit-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument("--gate-require-budget-stability-audit", action="store_true")
    parser.add_argument("--gate-min-budget-stability-slice-count", type=int, default=0)
    parser.add_argument(
        "--gate-min-budget-stability-comparable-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-budget-stability-signature-change-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-max-budget-stability-harmful-change-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--gate-min-budget-stability-hit-delta-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--gate-min-budget-stability-profit-loss-delta",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-budget-stability-roi-delta",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-max-budget-stability-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-final-answer-market-concentration-audit-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-final-answer-market-concentration-audit",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-final-answer-market-concentration-slice-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-final-answer-market-concentration-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-final-answer-market-concentration-effective-constraint-profile-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-final-answer-market-concentration-failed-check-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-final-answer-market-concentration-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-correct-score-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument("--gate-require-correct-score-admission", action="store_true")
    parser.add_argument(
        "--gate-allow-correct-score-admission-holdout-not-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-correct-score-admission-production-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-slice-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-comparison-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-final-hit-sample-size",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-final-hit-coverage-ratio",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-final-hit-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-roi",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-correct-score-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-candidate-correct-score-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-correct-score-admission-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-correct-score-admission-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-correct-score-admission-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-correct-score-admission-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-correct-score-admission-failed-check-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--gate-max-correct-score-admission-warning-count",
        type=int,
        default=None,
    )
    parser.add_argument("--gate-require-unified-candidate-pool", action="store_true")
    parser.add_argument(
        "--gate-min-unified-candidate-pool-present-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-unified-candidate-pool-valid-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-unified-candidate-pool-unique-family-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-unified-candidate-pool-selection-mismatch-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-unified-candidate-pool-selected-2x1-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-require-unified-candidate-pool-multiple-value-admission",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-unified-candidate-pool-multiple-value-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-unified-candidate-pool-multiple-value-admitted-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-unified-candidate-pool-multiple-value-extra-option-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-unified-candidate-pool-multiple-value-rejected-candidate-count",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--gate-max-unified-candidate-pool-selected-multiple-value-rejected-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-unified-candidate-pool-guard-preset",
        choices=UNIFIED_CANDIDATE_POOL_GUARD_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--gate-runtime-profile-switch-preset",
        choices=RUNTIME_PROFILE_SWITCH_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--gate-runtime-profile-switch-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-runtime-profile-switch-replay-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-runtime-profile-switch-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-missing-runtime-profile-switch-replay",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-runtime-profile-switch-applied",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-allowed-competition-count",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-changed-final-answer-count",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-runtime-profile-switch-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-runtime-profile-switch-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-runtime-profile-switch-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-runtime-profile-switch-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--gate-final-answer-segment-penalty-runtime-replay-preset",
        choices=FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--gate-final-answer-segment-penalty-runtime-replay-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-final-answer-segment-penalty-runtime-replay",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-missing-final-answer-segment-penalty-runtime-replay-holdout",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-final-answer-segment-penalty-runtime-replay-runtime-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-changed-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-penalty-option-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-hit-count-delta",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-final-answer-segment-penalty-runtime-replay-candidate-roi",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-final-hit-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-final-answer-segment-penalty-runtime-replay-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-allow-final-answer-segment-penalty-runtime-replay-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-final-answer-segment-penalty-runtime-replay-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-market-movement-runtime-activation-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-market-movement-runtime-activation",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-selected-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-market-movement-runtime-activation-selected-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-market-movement-runtime-activation-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-market-movement-runtime-activation-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-market-movement-runtime-activation-calibration-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-default-profile-write",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-default-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-market-movement-runtime-activation-sample-expansion-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-market-movement-runtime-activation-sample-expansion",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-market-movement-runtime-activation-sample-expansion-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-market-movement-runtime-activation-segment-replay-batch-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-market-movement-runtime-activation-segment-replay-batch-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-market-movement-runtime-activation-segment-replay-batch-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-market-movement-runtime-activation-segment-replay-batch-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-segment-replay-batch-report-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-segment-replay-batch-passed-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-replacement-reranker-shadow-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-replacement-reranker-shadow-admission",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-replacement-reranker-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-replacement-reranker-scoped-evidence",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-replacement-reranker-prematch-source-surface",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-scope-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-shadow-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-changed-from-model-top-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-roi-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-replacement-reranker-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-replacement-reranker-final-hit-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-replacement-reranker-profit-loss-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-replacement-reranker-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-active-competition-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-active-season-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-replacement-reranker-active-rolling-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-global-planner-short-odds-adapter-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-global-planner-short-odds-adapter-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-global-planner-short-odds-adapter-default-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-global-planner-short-odds-adapter-shadow-path-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-global-planner-short-odds-adapter-missing-explicit-opt-in-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-changed-final-answer-count",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-global-planner-short-odds-adapter-runtime-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-global-planner-short-odds-adapter-runtime-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-global-planner-short-odds-adapter-runtime-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-global-planner-short-odds-adapter-runtime-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--gate-allow-global-planner-short-odds-adapter-runtime-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-global-planner-short-odds-adapter-runtime-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-global-planner-short-odds-adapter-sample-expansion-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-global-planner-short-odds-adapter-sample-expansion",
        action="store_true",
    )
    parser.add_argument(
        "--gate-require-global-planner-short-odds-adapter-sample-expansion-promotion-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-recommendation-strategy-governance-preset",
        choices=RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS,
        default=None,
    )
    parser.add_argument(
        "--gate-recommendation-strategy-promotion-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-recommendation-strategy-promotion-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-gate-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-gate-final-answer-count",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-gate-changed-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-gate-hit-delta-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-gate-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-gate-minimum-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-recommendation-strategy-gate-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-recommendation-strategy-gate-final-hit-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-recommendation-strategy-gate-profit-loss-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-gate-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-gate-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-recommendation-strategy-staged-activation-smoke-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-recommendation-strategy-staged-activation-smoke",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-staged-activation-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-staged-default-write",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-staged-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-staged-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-staged-rule-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-recommendation-strategy-staged-allowed-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-recommendation-strategy-default-path-isolation-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-recommendation-strategy-default-path-isolation",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-default-path-not-isolated",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-default-adapter-enabled",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-default-adapter-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-missing-explicit-opt-in",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-isolation-default-write",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-isolation-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-recommendation-strategy-isolation-public-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-probability-calibration-profile-rolling-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-probability-calibration-profile-rolling-admission",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-probability-calibration-profile-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-probability-calibration-profile-non-active-profile",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-overall-adjusted-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-overall-bucket-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-active-season-cutoff-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-active-rolling-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-probability-calibration-profile-model-quality-gate-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-probability-calibration-profile-model-quality-gate",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-probability-calibration-profile-model-quality-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-selected-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-adjusted-slice-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-adjusted-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-model-quality-skipped-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-model-quality-final-answer-changed-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-final-answer-hit-count-delta",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-probability-calibration-profile-model-quality-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-model-quality-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-model-quality-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-probability-calibration-profile-model-quality-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-asian-handicap-segmented-model-quality-governance-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-asian-handicap-segmented-model-quality-governance",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-asian-handicap-segmented-model-quality-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-asian-handicap-segmented-model-quality-non-internal",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-asian-handicap-segmented-model-quality-default-path-not-isolated",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-asian-handicap-segmented-model-quality-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-asian-handicap-segmented-model-quality-public-response-change",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-asian-handicap-segmented-model-quality-accepted-segment-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-shadow-segment-count",
        type=int,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-fallback-segment-count",
        type=int,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-rejected-segment-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-asian-handicap-segmented-model-quality-accepted-validation-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-asian-handicap-segmented-model-quality-calibration-applied-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-asian-handicap-segmented-model-quality-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-asian-handicap-segmented-model-quality-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-min-asian-handicap-segmented-model-quality-actual-probability-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-prematch-feature-quality-cycle-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-prematch-feature-quality-cycle",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-failed-prematch-feature-quality-cycle",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-prematch-feature-quality-cycle-best-gate-failed",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-prematch-feature-quality-cycle-slice-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-quality-cycle-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-quality-cycle-evaluated-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-quality-cycle-passing-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-quality-cycle-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-quality-cycle-best-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-quality-cycle-best-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-quality-cycle-best-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-prematch-feature-rolling-admission-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-prematch-feature-rolling-admission",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-prematch-feature-rolling-admission-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-prematch-feature-rolling-admission-overall-evaluated-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-rolling-admission-overall-passing-candidate-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-rolling-admission-failed-fold-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-rolling-admission-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-rolling-admission-active-season-cutoff-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-rolling-admission-active-rolling-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-rolling-admission-overall-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-rolling-admission-overall-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-rolling-admission-overall-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--gate-prematch-feature-sample-readiness-report-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--gate-require-prematch-feature-sample-readiness",
        action="store_true",
    )
    parser.add_argument(
        "--gate-allow-prematch-feature-sample-readiness-shadow-only",
        action="store_true",
    )
    parser.add_argument(
        "--gate-min-prematch-feature-sample-ready-source-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-sample-ready-fixture-count",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-sample-ready-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-sample-ready-season-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-min-prematch-feature-sample-ready-competition-season-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--gate-max-prematch-feature-sample-readiness-warning-count",
        type=int,
        default=0,
    )
    parser.add_argument("--gate-fail-on-history-statuses", default="regressed")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkCycleOptions:
    schedule_options = RecommendationBenchmarkScheduleOptions(
        schedule_name=args.schedule_name,
        cadence=args.cadence,
        run_at_utc=_datetime(args.run_at_utc) if args.run_at_utc else None,
        window_count=args.window_count,
        lookback_hours=args.lookback_hours,
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(_mode(value) for value in _csv(args.modes)),
        max_budgets=tuple(_positive_float(value) for value in _csv(args.budgets)),
        strategy=args.strategy,
        unit_stake=args.unit_stake,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        require_odds=not args.no_require_odds,
        candidate_limit=args.candidate_limit,
        competition_id=args.competition_id,
        model_version=args.model_version,
        provider_name=args.provider_name,
        canonical_fixture_id=args.canonical_fixture_id,
        run_global_best=not args.skip_global_best,
        run_prematch_pipeline=args.include_prematch_pipeline,
        run_core_replay=not args.skip_core_replay,
        run_chain_integrity=not args.skip_chain_integrity,
        run_successor_chain_evaluation=(
            not args.skip_chain_integrity and not args.skip_successor_chain_evaluation
        ),
        dry_run=not args.commit,
        save_report=args.save_report,
        save_pipeline_audit=args.save_audit,
        requested_by=args.requested_by,
        provider_observation_limit=args.provider_observation_limit,
        source_run_limit=args.source_run_limit,
        incident_limit=args.incident_limit,
        report_limit=args.report_limit,
        replay_limit=args.replay_limit,
        chain_integrity_limit=args.chain_integrity_limit,
        continue_on_error=not args.stop_on_error,
    )
    gate_options = RecommendationBenchmarkQualityGateOptions(
        benchmark_key=args.gate_benchmark_key,
        strategy=args.strategy,
        history_limit=args.gate_history_limit,
        allow_missing_history=args.allow_missing_history,
        min_scenario_count=args.gate_min_scenario_count,
        min_completed_ratio=args.gate_min_completed_ratio,
        max_failed_count=args.gate_max_failed_count,
        max_warning_count=args.gate_max_warning_count,
        min_global_best_selected_count=args.gate_min_global_best_selected_count,
        min_global_best_candidate_count=args.gate_min_global_best_candidate_count,
        min_global_best_generated_option_count=(
            args.gate_min_global_best_generated_option_count
        ),
        min_core_replay_ready_ratio=args.gate_min_core_replay_ready_ratio,
        min_chain_integrity_ready_ratio=args.gate_min_chain_integrity_ready_ratio,
        max_chain_integrity_critical_issue_count=(
            args.gate_max_chain_integrity_critical_issue_count
        ),
        min_successor_chain_evaluation_passed_ratio=(
            args.gate_min_successor_chain_evaluation_passed_ratio
        ),
        min_successor_chain_effective_leaf_count=(
            args.gate_min_successor_chain_effective_leaf_count
        ),
        max_successor_chain_critical_issue_count=(
            args.gate_max_successor_chain_critical_issue_count
        ),
        max_successor_chain_ambiguous_source_count=(
            args.gate_max_successor_chain_ambiguous_source_count
        ),
        max_successor_chain_source_status_sync_required_count=(
            args.gate_max_successor_chain_source_status_sync_required_count
        ),
        max_ambiguous_successor_source_count=(
            args.gate_max_ambiguous_successor_source_count
        ),
        max_stale_recommendation_count=args.gate_max_stale_recommendation_count,
        max_successor_recompute_required_count=(
            args.gate_max_successor_recompute_required_count
        ),
        min_final_hit_sample_size=args.gate_min_final_hit_sample_size,
        min_final_hit_coverage_ratio=args.gate_min_final_hit_coverage_ratio,
        min_final_hit_rate=args.gate_min_final_hit_rate,
        min_average_core_replay_roi=args.gate_min_average_core_replay_roi,
        min_upset_capture_sample_size=args.gate_min_upset_capture_sample_size,
        min_upset_capture_rate=args.gate_min_upset_capture_rate,
        historical_suite_quality_gate_report_path=(
            args.gate_historical_suite_quality_gate_report_path
        ),
        require_historical_suite_quality_gate=(
            args.gate_require_historical_suite_quality_gate
        ),
        require_historical_suite_lifecycle_evidence=(
            not args.gate_allow_missing_historical_suite_lifecycle_evidence
        ),
        require_historical_suite_lifecycle_source_status_synced=(
            not args.gate_allow_unsynced_historical_suite_lifecycle_source_status
        ),
        require_historical_suite_successor_chain_evaluation=(
            args.gate_require_historical_suite_successor_chain_evaluation
        ),
        min_historical_suite_slice_count=args.gate_min_historical_suite_slice_count,
        min_historical_suite_comparison_count=(
            args.gate_min_historical_suite_comparison_count
        ),
        min_historical_suite_candidate_final_hit_sample_size=(
            args.gate_min_historical_suite_candidate_final_hit_sample_size
        ),
        min_historical_suite_candidate_final_hit_coverage_ratio=(
            args.gate_min_historical_suite_candidate_final_hit_coverage_ratio
        ),
        min_historical_suite_candidate_dynamic_mixed_final_answer_count=(
            args.gate_min_historical_suite_candidate_dynamic_mixed_final_answer_count
        ),
        min_historical_suite_candidate_dynamic_mixed_final_answer_rate=(
            args.gate_min_historical_suite_candidate_dynamic_mixed_final_answer_rate
        ),
        min_historical_suite_candidate_handicap_final_answer_count=(
            args.gate_min_historical_suite_candidate_handicap_final_answer_count
        ),
        min_historical_suite_candidate_correct_score_final_answer_count=(
            args.gate_min_historical_suite_candidate_correct_score_final_answer_count
        ),
        min_historical_suite_candidate_multiple_choice_final_answer_count=(
            args.gate_min_historical_suite_candidate_multiple_choice_final_answer_count
        ),
        max_historical_suite_failed_check_count=(
            args.gate_max_historical_suite_failed_check_count
        ),
        min_historical_suite_lifecycle_effective_leaf_count=(
            args.gate_min_historical_suite_lifecycle_effective_leaf_count
        ),
        min_historical_suite_lifecycle_active_edge_count=(
            args.gate_min_historical_suite_lifecycle_active_edge_count
        ),
        max_historical_suite_lifecycle_critical_issue_count=(
            args.gate_max_historical_suite_lifecycle_critical_issue_count
        ),
        max_historical_suite_lifecycle_source_status_sync_required_count=(
            args.gate_max_historical_suite_lifecycle_source_status_sync_required_count
        ),
        min_historical_suite_successor_effective_leaf_count=(
            args.gate_min_historical_suite_successor_effective_leaf_count
        ),
        min_historical_suite_successor_active_edge_count=(
            args.gate_min_historical_suite_successor_active_edge_count
        ),
        max_historical_suite_successor_critical_issue_count=(
            args.gate_max_historical_suite_successor_critical_issue_count
        ),
        max_historical_suite_successor_ambiguous_source_count=(
            args.gate_max_historical_suite_successor_ambiguous_source_count
        ),
        max_historical_suite_successor_source_status_sync_required_count=(
            args.gate_max_historical_suite_successor_source_status_sync_required_count
        ),
        budget_stability_audit_report_path=(
            args.gate_budget_stability_audit_report_path
        ),
        require_budget_stability_audit=args.gate_require_budget_stability_audit,
        min_budget_stability_slice_count=(
            args.gate_min_budget_stability_slice_count
        ),
        min_budget_stability_comparable_count=(
            args.gate_min_budget_stability_comparable_count
        ),
        max_budget_stability_signature_change_rate=(
            args.gate_max_budget_stability_signature_change_rate
        ),
        max_budget_stability_harmful_change_count=(
            args.gate_max_budget_stability_harmful_change_count
        ),
        min_budget_stability_hit_delta_count=(
            args.gate_min_budget_stability_hit_delta_count
        ),
        min_budget_stability_profit_loss_delta=(
            args.gate_min_budget_stability_profit_loss_delta
        ),
        min_budget_stability_roi_delta=args.gate_min_budget_stability_roi_delta,
        max_budget_stability_warning_count=(
            args.gate_max_budget_stability_warning_count
        ),
        final_answer_market_concentration_audit_report_path=(
            args.gate_final_answer_market_concentration_audit_report_path
        ),
        require_final_answer_market_concentration_audit=(
            args.gate_require_final_answer_market_concentration_audit
        ),
        min_final_answer_market_concentration_slice_count=(
            args.gate_min_final_answer_market_concentration_slice_count
        ),
        min_final_answer_market_concentration_dynamic_mixed_final_answer_count=(
            args.gate_min_final_answer_market_concentration_dynamic_mixed_final_answer_count
        ),
        min_final_answer_market_concentration_effective_constraint_profile_count=(
            args.gate_min_final_answer_market_concentration_effective_constraint_profile_count
        ),
        max_final_answer_market_concentration_failed_check_count=(
            args.gate_max_final_answer_market_concentration_failed_check_count
        ),
        max_final_answer_market_concentration_warning_count=(
            args.gate_max_final_answer_market_concentration_warning_count
        ),
        correct_score_admission_report_path=(
            args.gate_correct_score_admission_report_path
        ),
        require_correct_score_admission=args.gate_require_correct_score_admission,
        require_correct_score_admission_holdout_allowed=(
            not args.gate_allow_correct_score_admission_holdout_not_allowed
        ),
        require_correct_score_admission_production_allowed=(
            args.gate_require_correct_score_admission_production_allowed
        ),
        min_correct_score_admission_slice_count=(
            args.gate_min_correct_score_admission_slice_count
        ),
        min_correct_score_admission_comparison_count=(
            args.gate_min_correct_score_admission_comparison_count
        ),
        min_correct_score_admission_candidate_final_hit_sample_size=(
            args.gate_min_correct_score_admission_candidate_final_hit_sample_size
        ),
        min_correct_score_admission_candidate_final_hit_coverage_ratio=(
            args.gate_min_correct_score_admission_candidate_final_hit_coverage_ratio
        ),
        min_correct_score_admission_candidate_final_hit_rate=(
            args.gate_min_correct_score_admission_candidate_final_hit_rate
        ),
        min_correct_score_admission_candidate_roi=(
            args.gate_min_correct_score_admission_candidate_roi
        ),
        min_correct_score_admission_candidate_correct_score_final_answer_count=(
            args.gate_min_correct_score_admission_candidate_correct_score_final_answer_count
        ),
        min_correct_score_admission_candidate_correct_score_final_answer_rate=(
            args.gate_min_correct_score_admission_candidate_correct_score_final_answer_rate
        ),
        min_correct_score_admission_final_hit_rate_delta=(
            args.gate_min_correct_score_admission_final_hit_rate_delta
        ),
        min_correct_score_admission_roi_delta=(
            args.gate_min_correct_score_admission_roi_delta
        ),
        min_correct_score_admission_profit_loss_delta=(
            args.gate_min_correct_score_admission_profit_loss_delta
        ),
        max_correct_score_admission_brier_score_delta=(
            args.gate_max_correct_score_admission_brier_score_delta
        ),
        max_correct_score_admission_log_loss_delta=(
            args.gate_max_correct_score_admission_log_loss_delta
        ),
        max_correct_score_admission_mean_calibration_error_delta=(
            args.gate_max_correct_score_admission_mean_calibration_error_delta
        ),
        max_correct_score_admission_failed_check_count=(
            args.gate_max_correct_score_admission_failed_check_count
        ),
        max_correct_score_admission_warning_count=(
            args.gate_max_correct_score_admission_warning_count
        ),
        require_unified_candidate_pool=args.gate_require_unified_candidate_pool,
        min_unified_candidate_pool_present_count=(
            args.gate_min_unified_candidate_pool_present_count
        ),
        min_unified_candidate_pool_valid_candidate_count=(
            args.gate_min_unified_candidate_pool_valid_candidate_count
        ),
        min_unified_candidate_pool_unique_family_count=(
            args.gate_min_unified_candidate_pool_unique_family_count
        ),
        max_unified_candidate_pool_selection_mismatch_count=(
            args.gate_max_unified_candidate_pool_selection_mismatch_count
        ),
        max_unified_candidate_pool_selected_2x1_rate=(
            args.gate_max_unified_candidate_pool_selected_2x1_rate
        ),
        require_unified_candidate_pool_multiple_value_admission=(
            args.gate_require_unified_candidate_pool_multiple_value_admission
        ),
        min_unified_candidate_pool_multiple_value_candidate_count=(
            args.gate_min_unified_candidate_pool_multiple_value_candidate_count
        ),
        min_unified_candidate_pool_multiple_value_admitted_candidate_count=(
            args.gate_min_unified_candidate_pool_multiple_value_admitted_candidate_count
        ),
        min_unified_candidate_pool_multiple_value_extra_option_count=(
            args.gate_min_unified_candidate_pool_multiple_value_extra_option_count
        ),
        max_unified_candidate_pool_multiple_value_rejected_candidate_count=(
            args.gate_max_unified_candidate_pool_multiple_value_rejected_candidate_count
        ),
        max_unified_candidate_pool_selected_multiple_value_rejected_count=(
            args.gate_max_unified_candidate_pool_selected_multiple_value_rejected_count
        ),
        runtime_profile_switch_report_path=(
            args.gate_runtime_profile_switch_report_path
        ),
        runtime_profile_switch_replay_report_path=(
            args.gate_runtime_profile_switch_replay_report_path
        ),
        require_runtime_profile_switch_gate=(
            args.gate_require_runtime_profile_switch_gate
        ),
        require_runtime_profile_switch_replay=(
            not args.gate_allow_missing_runtime_profile_switch_replay
        ),
        require_runtime_profile_switch_staged_only=(
            not args.gate_allow_runtime_profile_switch_applied
        ),
        min_runtime_profile_switch_rule_count=(
            args.gate_min_runtime_profile_switch_rule_count
        ),
        min_runtime_profile_switch_allowed_competition_count=(
            args.gate_min_runtime_profile_switch_allowed_competition_count
        ),
        min_runtime_profile_switch_final_answer_count=(
            args.gate_min_runtime_profile_switch_final_answer_count
        ),
        min_runtime_profile_switch_changed_final_answer_count=(
            args.gate_min_runtime_profile_switch_changed_final_answer_count
        ),
        min_runtime_profile_switch_final_answer_hit_rate_delta=(
            args.gate_min_runtime_profile_switch_final_answer_hit_rate_delta
        ),
        min_runtime_profile_switch_roi_delta=(
            args.gate_min_runtime_profile_switch_roi_delta
        ),
        min_runtime_profile_switch_profit_loss_delta=(
            args.gate_min_runtime_profile_switch_profit_loss_delta
        ),
        max_runtime_profile_switch_harm_count_vs_original=(
            args.gate_max_runtime_profile_switch_harm_count_vs_original
        ),
        max_runtime_profile_switch_final_hit_harm_count_vs_original=(
            args.gate_max_runtime_profile_switch_final_hit_harm_count_vs_original
        ),
        max_runtime_profile_switch_profit_loss_harm_count_vs_original=(
            args.gate_max_runtime_profile_switch_profit_loss_harm_count_vs_original
        ),
        min_runtime_profile_switch_average_hit_probability_delta=(
            args.gate_min_runtime_profile_switch_average_hit_probability_delta
        ),
        final_answer_segment_penalty_runtime_replay_report_path=(
            args.gate_final_answer_segment_penalty_runtime_replay_report_path
        ),
        require_final_answer_segment_penalty_runtime_replay=(
            args.gate_require_final_answer_segment_penalty_runtime_replay
        ),
        require_final_answer_segment_penalty_runtime_replay_holdout_allowed=(
            not args.gate_allow_missing_final_answer_segment_penalty_runtime_replay_holdout
        ),
        require_final_answer_segment_penalty_runtime_replay_runtime_allowed=(
            args.gate_require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        ),
        min_final_answer_segment_penalty_runtime_replay_rule_count=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_rule_count
        ),
        min_final_answer_segment_penalty_runtime_replay_selected_rule_count=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_selected_rule_count
        ),
        max_final_answer_segment_penalty_runtime_replay_selected_rule_count=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_selected_rule_count
        ),
        min_final_answer_segment_penalty_runtime_replay_final_answer_count=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_final_answer_count
        ),
        min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        ),
        min_final_answer_segment_penalty_runtime_replay_penalty_option_count=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        ),
        min_final_answer_segment_penalty_runtime_replay_hit_count_delta=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_hit_count_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_hit_rate_delta=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_hit_rate_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_roi_delta=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_roi_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_profit_loss_delta=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_profit_loss_delta
        ),
        min_final_answer_segment_penalty_runtime_replay_candidate_roi=(
            args.gate_min_final_answer_segment_penalty_runtime_replay_candidate_roi
        ),
        max_final_answer_segment_penalty_runtime_replay_brier_score_delta=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_brier_score_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_log_loss_delta=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_log_loss_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_calibration_error_delta=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_calibration_error_delta
        ),
        max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
        ),
        max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        ),
        max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline=(
            args.gate_max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        ),
        require_final_answer_segment_penalty_runtime_replay_no_production_change=(
            not args.gate_allow_final_answer_segment_penalty_runtime_replay_production_change
        ),
        require_final_answer_segment_penalty_runtime_replay_no_public_response_change=(
            not args.gate_allow_final_answer_segment_penalty_runtime_replay_public_change
        ),
        market_movement_runtime_activation_report_path=(
            args.gate_market_movement_runtime_activation_report_path
        ),
        require_market_movement_runtime_activation=(
            args.gate_require_market_movement_runtime_activation
        ),
        require_market_movement_runtime_activation_ready=(
            not args.gate_allow_market_movement_runtime_activation_not_ready
        ),
        min_market_movement_runtime_activation_rule_count=(
            args.gate_min_market_movement_runtime_activation_rule_count
        ),
        min_market_movement_runtime_activation_selected_rule_count=(
            args.gate_min_market_movement_runtime_activation_selected_rule_count
        ),
        max_market_movement_runtime_activation_selected_rule_count=(
            args.gate_max_market_movement_runtime_activation_selected_rule_count
        ),
        min_market_movement_runtime_activation_adjusted_fixture_count=(
            args.gate_min_market_movement_runtime_activation_adjusted_fixture_count
        ),
        min_market_movement_runtime_activation_adjusted_prediction_count=(
            args.gate_min_market_movement_runtime_activation_adjusted_prediction_count
        ),
        min_market_movement_runtime_activation_final_hit_rate_delta=(
            args.gate_min_market_movement_runtime_activation_final_hit_rate_delta
        ),
        min_market_movement_runtime_activation_roi_delta=(
            args.gate_min_market_movement_runtime_activation_roi_delta
        ),
        min_market_movement_runtime_activation_profit_loss_delta=(
            args.gate_min_market_movement_runtime_activation_profit_loss_delta
        ),
        max_market_movement_runtime_activation_brier_score_delta=(
            args.gate_max_market_movement_runtime_activation_brier_score_delta
        ),
        max_market_movement_runtime_activation_log_loss_delta=(
            args.gate_max_market_movement_runtime_activation_log_loss_delta
        ),
        max_market_movement_runtime_activation_mean_calibration_error_delta=(
            args.gate_max_market_movement_runtime_activation_calibration_delta
        ),
        require_market_movement_runtime_activation_no_default_profile_write=(
            not args.gate_allow_market_movement_runtime_activation_default_profile_write
        ),
        require_market_movement_runtime_activation_no_default_path_change=(
            not args.gate_allow_market_movement_runtime_activation_default_path_change
        ),
        require_market_movement_runtime_activation_no_production_change=(
            not args.gate_allow_market_movement_runtime_activation_production_change
        ),
        require_market_movement_runtime_activation_no_public_response_change=(
            not args.gate_allow_market_movement_runtime_activation_public_change
        ),
        market_movement_runtime_activation_sample_expansion_report_path=(
            args.gate_market_movement_runtime_activation_sample_expansion_report_path
        ),
        require_market_movement_runtime_activation_sample_expansion=(
            args.gate_require_market_movement_runtime_activation_sample_expansion
        ),
        require_market_movement_runtime_activation_sample_expansion_promotion_ready=(
            args.gate_require_market_movement_runtime_activation_sample_expansion_promotion_ready
        ),
        market_movement_runtime_activation_segment_replay_batch_gate_report_path=(
            args.gate_market_movement_runtime_activation_segment_replay_batch_gate_report_path
        ),
        require_market_movement_runtime_activation_segment_replay_batch_gate=(
            args.gate_require_market_movement_runtime_activation_segment_replay_batch_gate
        ),
        require_market_movement_runtime_activation_segment_replay_batch_ready=(
            not args.gate_allow_market_movement_runtime_activation_segment_replay_batch_not_ready
        ),
        require_market_movement_runtime_activation_segment_replay_batch_promotion_ready=(
            args.gate_require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
        ),
        min_market_movement_runtime_activation_segment_replay_batch_report_count=(
            args.gate_min_market_movement_runtime_activation_segment_replay_batch_report_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_passed_count=(
            args.gate_min_market_movement_runtime_activation_segment_replay_batch_passed_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count=(
            args.gate_min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
        ),
        min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count=(
            args.gate_min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
        ),
        replacement_reranker_shadow_admission_report_path=(
            args.gate_replacement_reranker_shadow_admission_report_path
        ),
        require_replacement_reranker_shadow_admission=(
            args.gate_require_replacement_reranker_shadow_admission
        ),
        require_replacement_reranker_runtime_candidate_allowed=(
            not args.gate_allow_replacement_reranker_shadow_only
        ),
        require_replacement_reranker_scoped_evidence=(
            args.gate_require_replacement_reranker_scoped_evidence
        ),
        require_replacement_reranker_prematch_source_surface=(
            args.gate_require_replacement_reranker_prematch_source_surface
        ),
        min_replacement_reranker_scope_final_answer_count=(
            args.gate_min_replacement_reranker_scope_final_answer_count
        ),
        min_replacement_reranker_shadow_final_answer_count=(
            args.gate_min_replacement_reranker_shadow_final_answer_count
        ),
        min_replacement_reranker_changed_from_model_top_count=(
            args.gate_min_replacement_reranker_changed_from_model_top_count
        ),
        min_replacement_reranker_hit_delta_vs_model_top=(
            args.gate_min_replacement_reranker_hit_delta_vs_model_top
        ),
        min_replacement_reranker_profit_loss_delta_vs_model_top=(
            args.gate_min_replacement_reranker_profit_loss_delta_vs_model_top
        ),
        min_replacement_reranker_roi_delta_vs_model_top=(
            args.gate_min_replacement_reranker_roi_delta_vs_model_top
        ),
        max_replacement_reranker_harm_count_vs_model_top=(
            args.gate_max_replacement_reranker_harm_count_vs_model_top
        ),
        max_replacement_reranker_final_hit_harm_count_vs_model_top=(
            args.gate_max_replacement_reranker_final_hit_harm_count_vs_model_top
        ),
        max_replacement_reranker_profit_loss_harm_count_vs_model_top=(
            args.gate_max_replacement_reranker_profit_loss_harm_count_vs_model_top
        ),
        max_replacement_reranker_failed_fold_count=(
            args.gate_max_replacement_reranker_failed_fold_count
        ),
        min_replacement_reranker_active_competition_fold_count=(
            args.gate_min_replacement_reranker_active_competition_fold_count
        ),
        min_replacement_reranker_active_season_fold_count=(
            args.gate_min_replacement_reranker_active_season_fold_count
        ),
        min_replacement_reranker_active_rolling_fold_count=(
            args.gate_min_replacement_reranker_active_rolling_fold_count
        ),
        global_planner_short_odds_adapter_gate_report_path=(
            args.gate_global_planner_short_odds_adapter_gate_report_path
        ),
        require_global_planner_short_odds_adapter_gate=(
            args.gate_require_global_planner_short_odds_adapter_gate
        ),
        require_global_planner_short_odds_adapter_default_path_unchanged=(
            not args.gate_allow_global_planner_short_odds_adapter_default_path_change
        ),
        require_global_planner_short_odds_adapter_shadow_path_unchanged=(
            not args.gate_allow_global_planner_short_odds_adapter_shadow_path_change
        ),
        require_global_planner_short_odds_adapter_explicit_opt_in_changed=(
            not args.gate_allow_global_planner_short_odds_adapter_missing_explicit_opt_in_change
        ),
        min_global_planner_short_odds_adapter_runtime_final_answer_count=(
            args.gate_min_global_planner_short_odds_adapter_runtime_final_answer_count
        ),
        min_global_planner_short_odds_adapter_runtime_changed_final_answer_count=(
            args.gate_min_global_planner_short_odds_adapter_runtime_changed_final_answer_count
        ),
        min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta=(
            args.gate_min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta
        ),
        min_global_planner_short_odds_adapter_runtime_roi_delta=(
            args.gate_min_global_planner_short_odds_adapter_runtime_roi_delta
        ),
        min_global_planner_short_odds_adapter_runtime_profit_loss_delta=(
            args.gate_min_global_planner_short_odds_adapter_runtime_profit_loss_delta
        ),
        max_global_planner_short_odds_adapter_runtime_harm_count_vs_original=(
            args.gate_max_global_planner_short_odds_adapter_runtime_harm_count_vs_original
        ),
        max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original=(
            args.gate_max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original
        ),
        max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original=(
            args.gate_max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original
        ),
        min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta=(
            args.gate_min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta
        ),
        require_global_planner_short_odds_adapter_runtime_public_unchanged=(
            not args.gate_allow_global_planner_short_odds_adapter_runtime_public_change
        ),
        require_global_planner_short_odds_adapter_runtime_production_unchanged=(
            not args.gate_allow_global_planner_short_odds_adapter_runtime_production_change
        ),
        global_planner_short_odds_adapter_sample_expansion_report_path=(
            args.gate_global_planner_short_odds_adapter_sample_expansion_report_path
        ),
        require_global_planner_short_odds_adapter_sample_expansion=(
            args.gate_require_global_planner_short_odds_adapter_sample_expansion
        ),
        require_global_planner_short_odds_adapter_sample_expansion_promotion_ready=(
            args.gate_require_global_planner_short_odds_adapter_sample_expansion_promotion_ready
        ),
        recommendation_strategy_promotion_gate_report_path=(
            args.gate_recommendation_strategy_promotion_gate_report_path
        ),
        require_recommendation_strategy_promotion_gate=(
            args.gate_require_recommendation_strategy_promotion_gate
        ),
        require_recommendation_strategy_gate_ready=(
            not args.gate_allow_recommendation_strategy_gate_not_ready
        ),
        min_recommendation_strategy_gate_final_answer_count=(
            args.gate_min_recommendation_strategy_gate_final_answer_count
        ),
        min_recommendation_strategy_gate_changed_final_answer_count=(
            args.gate_min_recommendation_strategy_gate_changed_final_answer_count
        ),
        min_recommendation_strategy_gate_hit_delta_count=(
            args.gate_min_recommendation_strategy_gate_hit_delta_count
        ),
        min_recommendation_strategy_gate_profit_loss_delta=(
            args.gate_min_recommendation_strategy_gate_profit_loss_delta
        ),
        min_recommendation_strategy_gate_minimum_roi_delta=(
            args.gate_min_recommendation_strategy_gate_minimum_roi_delta
        ),
        max_recommendation_strategy_gate_harm_count=(
            args.gate_max_recommendation_strategy_gate_harm_count
        ),
        max_recommendation_strategy_gate_final_hit_harm_count=(
            args.gate_max_recommendation_strategy_gate_final_hit_harm_count
        ),
        max_recommendation_strategy_gate_profit_loss_harm_count=(
            args.gate_max_recommendation_strategy_gate_profit_loss_harm_count
        ),
        require_recommendation_strategy_gate_no_production_change=(
            not args.gate_allow_recommendation_strategy_gate_production_change
        ),
        require_recommendation_strategy_gate_no_public_response_change=(
            not args.gate_allow_recommendation_strategy_gate_public_change
        ),
        recommendation_strategy_staged_activation_smoke_report_path=(
            args.gate_recommendation_strategy_staged_activation_smoke_report_path
        ),
        require_recommendation_strategy_staged_activation_smoke=(
            args.gate_require_recommendation_strategy_staged_activation_smoke
        ),
        require_recommendation_strategy_staged_activation_ready=(
            not args.gate_allow_recommendation_strategy_staged_activation_not_ready
        ),
        require_recommendation_strategy_staged_no_default_write=(
            not args.gate_allow_recommendation_strategy_staged_default_write
        ),
        require_recommendation_strategy_staged_no_production_change=(
            not args.gate_allow_recommendation_strategy_staged_production_change
        ),
        require_recommendation_strategy_staged_no_public_response_change=(
            not args.gate_allow_recommendation_strategy_staged_public_change
        ),
        min_recommendation_strategy_staged_rule_count=(
            args.gate_min_recommendation_strategy_staged_rule_count
        ),
        min_recommendation_strategy_staged_allowed_competition_count=(
            args.gate_min_recommendation_strategy_staged_allowed_competition_count
        ),
        recommendation_strategy_default_path_isolation_report_path=(
            args.gate_recommendation_strategy_default_path_isolation_report_path
        ),
        require_recommendation_strategy_default_path_isolation=(
            args.gate_require_recommendation_strategy_default_path_isolation
        ),
        require_recommendation_strategy_default_path_isolated=(
            not args.gate_allow_recommendation_strategy_default_path_not_isolated
        ),
        require_recommendation_strategy_default_adapter_disabled=(
            not args.gate_allow_recommendation_strategy_default_adapter_enabled
        ),
        require_recommendation_strategy_default_adapter_unchanged=(
            not args.gate_allow_recommendation_strategy_default_adapter_change
        ),
        require_recommendation_strategy_explicit_opt_in_applied=(
            not args.gate_allow_recommendation_strategy_missing_explicit_opt_in
        ),
        require_recommendation_strategy_isolation_no_default_write=(
            not args.gate_allow_recommendation_strategy_isolation_default_write
        ),
        require_recommendation_strategy_isolation_no_production_change=(
            not args.gate_allow_recommendation_strategy_isolation_production_change
        ),
        require_recommendation_strategy_isolation_no_public_response_change=(
            not args.gate_allow_recommendation_strategy_isolation_public_change
        ),
        probability_calibration_profile_rolling_admission_report_path=(
            args.gate_probability_calibration_profile_rolling_admission_report_path
        ),
        require_probability_calibration_profile_rolling_admission=(
            args.gate_require_probability_calibration_profile_rolling_admission
        ),
        require_probability_calibration_profile_candidate_allowed=(
            not args.gate_allow_probability_calibration_profile_shadow_only
        ),
        require_probability_calibration_profile_active_profile=(
            not args.gate_allow_probability_calibration_profile_non_active_profile
        ),
        min_probability_calibration_profile_overall_adjusted_fixture_count=(
            args.gate_min_probability_calibration_profile_overall_adjusted_fixture_count
        ),
        min_probability_calibration_profile_overall_bucket_count=(
            args.gate_min_probability_calibration_profile_overall_bucket_count
        ),
        max_probability_calibration_profile_failed_fold_count=(
            args.gate_max_probability_calibration_profile_failed_fold_count
        ),
        min_probability_calibration_profile_active_competition_fold_count=(
            args.gate_min_probability_calibration_profile_active_competition_fold_count
        ),
        min_probability_calibration_profile_active_season_cutoff_fold_count=(
            args.gate_min_probability_calibration_profile_active_season_cutoff_fold_count
        ),
        min_probability_calibration_profile_active_rolling_fold_count=(
            args.gate_min_probability_calibration_profile_active_rolling_fold_count
        ),
        probability_calibration_profile_model_quality_gate_report_path=(
            args.gate_probability_calibration_profile_model_quality_gate_report_path
        ),
        require_probability_calibration_profile_model_quality_gate=(
            args.gate_require_probability_calibration_profile_model_quality_gate
        ),
        require_probability_calibration_profile_model_quality_ready=(
            not args.gate_allow_probability_calibration_profile_model_quality_not_ready
        ),
        min_probability_calibration_profile_model_quality_selected_competition_count=(
            args.gate_min_probability_calibration_profile_model_quality_selected_competition_count
        ),
        min_probability_calibration_profile_model_quality_adjusted_slice_count=(
            args.gate_min_probability_calibration_profile_model_quality_adjusted_slice_count
        ),
        min_probability_calibration_profile_model_quality_adjusted_fixture_count=(
            args.gate_min_probability_calibration_profile_model_quality_adjusted_fixture_count
        ),
        max_probability_calibration_profile_model_quality_skipped_fixture_count=(
            args.gate_max_probability_calibration_profile_model_quality_skipped_fixture_count
        ),
        max_probability_calibration_profile_model_quality_final_answer_changed_count=(
            args.gate_max_probability_calibration_profile_model_quality_final_answer_changed_count
        ),
        min_probability_calibration_profile_model_quality_final_answer_hit_count_delta=(
            args.gate_min_probability_calibration_profile_model_quality_final_answer_hit_count_delta
        ),
        min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta=(
            args.gate_min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta
        ),
        min_probability_calibration_profile_model_quality_roi_delta=(
            args.gate_min_probability_calibration_profile_model_quality_roi_delta
        ),
        min_probability_calibration_profile_model_quality_profit_loss_delta=(
            args.gate_min_probability_calibration_profile_model_quality_profit_loss_delta
        ),
        max_probability_calibration_profile_model_quality_brier_score_delta=(
            args.gate_max_probability_calibration_profile_model_quality_brier_score_delta
        ),
        max_probability_calibration_profile_model_quality_log_loss_delta=(
            args.gate_max_probability_calibration_profile_model_quality_log_loss_delta
        ),
        max_probability_calibration_profile_model_quality_calibration_error_delta=(
            args.gate_max_probability_calibration_profile_model_quality_calibration_error_delta
        ),
        asian_handicap_segmented_model_quality_governance_report_path=(
            args.gate_asian_handicap_segmented_model_quality_governance_report_path
        ),
        require_asian_handicap_segmented_model_quality_governance=(
            args.gate_require_asian_handicap_segmented_model_quality_governance
        ),
        require_asian_handicap_segmented_model_quality_ready=(
            not args.gate_allow_asian_handicap_segmented_model_quality_not_ready
        ),
        require_asian_handicap_segmented_model_quality_internal_only=(
            not args.gate_allow_asian_handicap_segmented_model_quality_non_internal
        ),
        require_asian_handicap_segmented_model_quality_default_path_isolated=(
            not args.gate_allow_asian_handicap_segmented_model_quality_default_path_not_isolated
        ),
        require_asian_handicap_segmented_model_quality_no_production_change=(
            not args.gate_allow_asian_handicap_segmented_model_quality_production_change
        ),
        require_asian_handicap_segmented_model_quality_no_public_response_change=(
            not args.gate_allow_asian_handicap_segmented_model_quality_public_response_change
        ),
        min_asian_handicap_segmented_model_quality_accepted_segment_count=(
            args.gate_min_asian_handicap_segmented_model_quality_accepted_segment_count
        ),
        max_asian_handicap_segmented_model_quality_shadow_segment_count=(
            args.gate_max_asian_handicap_segmented_model_quality_shadow_segment_count
        ),
        max_asian_handicap_segmented_model_quality_fallback_segment_count=(
            args.gate_max_asian_handicap_segmented_model_quality_fallback_segment_count
        ),
        max_asian_handicap_segmented_model_quality_rejected_segment_count=(
            args.gate_max_asian_handicap_segmented_model_quality_rejected_segment_count
        ),
        min_asian_handicap_segmented_model_quality_accepted_validation_count=(
            args.gate_min_asian_handicap_segmented_model_quality_accepted_validation_count
        ),
        min_asian_handicap_segmented_model_quality_calibration_applied_count=(
            args.gate_min_asian_handicap_segmented_model_quality_calibration_applied_count
        ),
        min_asian_handicap_segmented_model_quality_hit_rate_delta=(
            args.gate_min_asian_handicap_segmented_model_quality_hit_rate_delta
        ),
        max_asian_handicap_segmented_model_quality_brier_score_delta=(
            args.gate_max_asian_handicap_segmented_model_quality_brier_score_delta
        ),
        max_asian_handicap_segmented_model_quality_log_loss_delta=(
            args.gate_max_asian_handicap_segmented_model_quality_log_loss_delta
        ),
        max_asian_handicap_segmented_model_quality_calibration_error_delta=(
            args.gate_max_asian_handicap_segmented_model_quality_calibration_error_delta
        ),
        min_asian_handicap_segmented_model_quality_actual_probability_delta=(
            args.gate_min_asian_handicap_segmented_model_quality_actual_probability_delta
        ),
        prematch_feature_quality_cycle_report_path=(
            args.gate_prematch_feature_quality_cycle_report_path
        ),
        require_prematch_feature_quality_cycle=(
            args.gate_require_prematch_feature_quality_cycle
        ),
        require_prematch_feature_quality_cycle_passed=(
            not args.gate_allow_failed_prematch_feature_quality_cycle
        ),
        require_prematch_feature_quality_cycle_best_gate_passed=(
            not args.gate_allow_prematch_feature_quality_cycle_best_gate_failed
        ),
        min_prematch_feature_quality_cycle_slice_count=(
            args.gate_min_prematch_feature_quality_cycle_slice_count
        ),
        min_prematch_feature_quality_cycle_fixture_count=(
            args.gate_min_prematch_feature_quality_cycle_fixture_count
        ),
        min_prematch_feature_quality_cycle_evaluated_candidate_count=(
            args.gate_min_prematch_feature_quality_cycle_evaluated_candidate_count
        ),
        min_prematch_feature_quality_cycle_passing_candidate_count=(
            args.gate_min_prematch_feature_quality_cycle_passing_candidate_count
        ),
        max_prematch_feature_quality_cycle_warning_count=(
            args.gate_max_prematch_feature_quality_cycle_warning_count
        ),
        max_prematch_feature_quality_cycle_best_brier_score_delta=(
            args.gate_max_prematch_feature_quality_cycle_best_brier_score_delta
        ),
        max_prematch_feature_quality_cycle_best_log_loss_delta=(
            args.gate_max_prematch_feature_quality_cycle_best_log_loss_delta
        ),
        max_prematch_feature_quality_cycle_best_calibration_error_delta=(
            args.gate_max_prematch_feature_quality_cycle_best_calibration_error_delta
        ),
        prematch_feature_rolling_admission_report_path=(
            args.gate_prematch_feature_rolling_admission_report_path
        ),
        require_prematch_feature_rolling_admission=(
            args.gate_require_prematch_feature_rolling_admission
        ),
        require_prematch_feature_rolling_admission_candidate_allowed=(
            not args.gate_allow_prematch_feature_rolling_admission_shadow_only
        ),
        min_prematch_feature_rolling_admission_overall_evaluated_candidate_count=(
            args.gate_min_prematch_feature_rolling_admission_overall_evaluated_candidate_count
        ),
        min_prematch_feature_rolling_admission_overall_passing_candidate_count=(
            args.gate_min_prematch_feature_rolling_admission_overall_passing_candidate_count
        ),
        max_prematch_feature_rolling_admission_failed_fold_count=(
            args.gate_max_prematch_feature_rolling_admission_failed_fold_count
        ),
        min_prematch_feature_rolling_admission_active_competition_fold_count=(
            args.gate_min_prematch_feature_rolling_admission_active_competition_fold_count
        ),
        min_prematch_feature_rolling_admission_active_season_cutoff_fold_count=(
            args.gate_min_prematch_feature_rolling_admission_active_season_cutoff_fold_count
        ),
        min_prematch_feature_rolling_admission_active_rolling_fold_count=(
            args.gate_min_prematch_feature_rolling_admission_active_rolling_fold_count
        ),
        max_prematch_feature_rolling_admission_overall_brier_score_delta=(
            args.gate_max_prematch_feature_rolling_admission_overall_brier_score_delta
        ),
        max_prematch_feature_rolling_admission_overall_log_loss_delta=(
            args.gate_max_prematch_feature_rolling_admission_overall_log_loss_delta
        ),
        max_prematch_feature_rolling_admission_overall_calibration_error_delta=(
            args.gate_max_prematch_feature_rolling_admission_overall_calibration_error_delta
        ),
        prematch_feature_sample_readiness_report_path=(
            args.gate_prematch_feature_sample_readiness_report_path
        ),
        require_prematch_feature_sample_readiness=(
            args.gate_require_prematch_feature_sample_readiness
        ),
        require_prematch_feature_sample_ready_allowed=(
            not args.gate_allow_prematch_feature_sample_readiness_shadow_only
        ),
        min_prematch_feature_sample_ready_source_count=(
            args.gate_min_prematch_feature_sample_ready_source_count
        ),
        min_prematch_feature_sample_ready_fixture_count=(
            args.gate_min_prematch_feature_sample_ready_fixture_count
        ),
        min_prematch_feature_sample_ready_competition_count=(
            args.gate_min_prematch_feature_sample_ready_competition_count
        ),
        min_prematch_feature_sample_ready_season_count=(
            args.gate_min_prematch_feature_sample_ready_season_count
        ),
        min_prematch_feature_sample_ready_competition_season_count=(
            args.gate_min_prematch_feature_sample_ready_competition_season_count
        ),
        max_prematch_feature_sample_readiness_warning_count=(
            args.gate_max_prematch_feature_sample_readiness_warning_count
        ),
        fail_on_history_statuses=tuple(_csv(args.gate_fail_on_history_statuses)),
    )
    gate_options = apply_runtime_profile_switch_preset(
        gate_options,
        args.gate_runtime_profile_switch_preset,
    )
    gate_options = apply_final_answer_segment_penalty_runtime_replay_preset(
        gate_options,
        args.gate_final_answer_segment_penalty_runtime_replay_preset,
    )
    gate_options = apply_recommendation_strategy_governance_preset(
        gate_options,
        args.gate_recommendation_strategy_governance_preset,
    )
    gate_options = apply_unified_candidate_pool_guard_preset(
        gate_options,
        args.gate_unified_candidate_pool_guard_preset,
    )
    return apply_recommendation_benchmark_cycle_preset(
        RecommendationBenchmarkCycleOptions(
            schedule_options=schedule_options,
            gate_options=gate_options,
            run_gate=not args.skip_gate,
            save_cycle_report=args.save_cycle_report,
            commit_core_replay_seed=args.commit_core_replay_seed,
            core_replay_seed_profile=args.core_replay_seed_profile,
            core_replay_seed_reset=not args.no_core_replay_seed_reset,
        ),
        args.cycle_preset,
    )


def _cycle_key(options: RecommendationBenchmarkCycleOptions) -> str:
    schedule = options.schedule_options
    gate = "gate" if options.run_gate else "no_gate"
    runtime_profile_switch_preset = options.gate_options.runtime_profile_switch_preset
    preset_suffix = (
        f":runtime_profile_switch_preset:{runtime_profile_switch_preset}"
        if runtime_profile_switch_preset is not None
        else ""
    )
    segment_penalty_preset = (
        options.gate_options.final_answer_segment_penalty_runtime_replay_preset
    )
    segment_penalty_suffix = (
        ":final_answer_segment_penalty_runtime_replay_preset:"
        f"{segment_penalty_preset}"
        if segment_penalty_preset is not None
        else ""
    )
    strategy_governance_preset = (
        options.gate_options.recommendation_strategy_governance_preset
    )
    strategy_governance_suffix = (
        f":recommendation_strategy_governance_preset:{strategy_governance_preset}"
        if strategy_governance_preset is not None
        else ""
    )
    unified_candidate_pool_guard_preset = (
        options.gate_options.unified_candidate_pool_guard_preset
    )
    unified_candidate_pool_guard_suffix = (
        f":unified_candidate_pool_guard_preset:{unified_candidate_pool_guard_preset}"
        if unified_candidate_pool_guard_preset is not None
        else ""
    )
    cycle_preset_suffix = (
        f":cycle_preset:{options.cycle_preset}"
        if options.cycle_preset is not None
        else ""
    )
    core_replay_seed_suffix = (
        ":core_replay_seed:"
        f"{options.core_replay_seed_profile}:"
        f"{'reset' if options.core_replay_seed_reset else 'append'}"
        if options.commit_core_replay_seed
        else ""
    )
    return (
        f"recommendation_benchmark_cycle:{schedule.schedule_name}:"
        f"{schedule.cadence}:{gate}{preset_suffix}{segment_penalty_suffix}"
        f"{strategy_governance_suffix}{unified_candidate_pool_guard_suffix}"
        f"{cycle_preset_suffix}{core_replay_seed_suffix}"
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _mode(value: str) -> RecommendationMode:
    if value not in {"single", "multiple"}:
        raise ValueError(f"unknown benchmark mode: {value}")
    return value  # type: ignore[return-value]


def _positive_float(value: str) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError("benchmark budgets must be positive")
    return result


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _budget_label(value: float) -> str:
    return f"{value:g}"


def _stored_cycle_run_from_row(
    row: DatabaseRow,
) -> StoredRecommendationBenchmarkCycleRun:
    return StoredRecommendationBenchmarkCycleRun(
        recommendation_benchmark_cycle_run_id=_int(
            row["recommendation_benchmark_cycle_run_id"]
        ),
        cycle_key=str(row["cycle_key"]),
        status=_cycle_status(row["status"]),
        passed=_bool(row["passed"]),
        schedule_key=str(row["schedule_key"]),
        benchmark_key=str(row["benchmark_key"]),
        benchmark_run_id=_optional_int(row.get("benchmark_run_id")),
        gate_key=_optional_str(row.get("gate_key")),
        gate_status=_optional_str(row.get("gate_status")),
        gate_passed=_optional_bool(row.get("gate_passed")),
        historical_suite_quality_gate_key=_optional_str(
            row.get("historical_suite_quality_gate_key")
        ),
        historical_suite_quality_gate_passed=_optional_bool(
            row.get("historical_suite_quality_gate_passed")
        ),
        historical_suite_lifecycle_source_status_synced=_optional_bool(
            row.get("historical_suite_lifecycle_source_status_synced")
        ),
        historical_suite_lifecycle_effective_leaf_count=_int(
            row["historical_suite_lifecycle_effective_leaf_count"]
        ),
        historical_suite_lifecycle_active_edge_count=_int(
            row["historical_suite_lifecycle_active_edge_count"]
        ),
        historical_suite_lifecycle_critical_issue_count=_int(
            row["historical_suite_lifecycle_critical_issue_count"]
        ),
        historical_suite_lifecycle_source_status_sync_required_count=_int(
            row["historical_suite_lifecycle_source_status_sync_required_count"]
        ),
        failed_checks_json=_json_list(row.get("failed_checks_json")),
        summary_json=_json_mapping(row.get("summary_json")),
        warnings_json=_json_list(row.get("warnings_json")),
        created_at=_datetime_value(row["created_at"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_mapping(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        parsed = loads(value)
        if isinstance(parsed, dict):
            return {str(key): item for key, item in parsed.items()}
    return {}


def _json_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        parsed = loads(value)
        if isinstance(parsed, list):
            return parsed
    return []


def _summary_list(summary: dict[str, object], key: str) -> list[object]:
    return _json_list(summary.get(key))


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


def _summary_str(summary: dict[str, object], key: str) -> str:
    value = summary.get(key, "")
    if isinstance(value, str):
        return value
    return str(value)


def _summary_bool(summary: dict[str, object], key: str) -> bool:
    value = summary.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "passed"}
    return False


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "passed"}:
            return True
        if normalized in {"false", "0", "no", "failed"}:
            return False
    return None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    raise ValueError(f"expected int-like value, got {type(value).__name__}")


def _bool(value: object) -> bool:
    optional = _optional_bool(value)
    if optional is not None:
        return optional
    raise ValueError(f"expected bool-like value, got {type(value).__name__}")


def _datetime_value(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _datetime(value)
    raise ValueError(f"expected datetime-like value, got {type(value).__name__}")


def _cycle_status(value: object) -> RecommendationBenchmarkCycleStatus:
    if value in {"passed", "failed", "gate_skipped"}:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown benchmark cycle status: {value}")


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result
