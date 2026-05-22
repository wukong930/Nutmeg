from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads
from pathlib import Path

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PostgresRecommendationBenchmarkCycleRunRepository,
    RecommendationBaselineSeedResult,
    RecommendationBenchmarkCoreReplaySeedOptions,
    RecommendationBenchmarkCoreReplaySeedResult,
    RecommendationBenchmarkCycleOptions,
    RecommendationBenchmarkCycleRunResult,
    RecommendationBenchmarkQualityGateOptions,
    RecommendationBenchmarkQualityGateResult,
    RecommendationBenchmarkRunResult,
    RecommendationBenchmarkScheduleOptions,
    RecommendationBenchmarkScheduleRunResult,
    StoredRecommendationBenchmarkCycleRun,
    StoredRecommendationBenchmarkRun,
    run_recommendation_benchmark_cycle,
)
from nutmeg.recommendations.benchmark_cycle import (
    CORE_PLUS_EXPANDED_A_LEAGUES_BUDGET_STABILITY_AUDIT_REPORT_PATH,
    CORE_PLUS_EXPANDED_A_LEAGUES_DYNAMIC_MIX_CONSTRAINT_RUNTIME_SMOKE_REPORT_PATH,
    CORE_PLUS_EXPANDED_A_LEAGUES_SUCCESSOR_EFFECTIVE_FINAL_ONLY_HISTORICAL_GATE_REPORT_PATH,
    INSERT_RECOMMENDATION_BENCHMARK_CYCLE_RUN_QUERY,
    LIST_RECOMMENDATION_BENCHMARK_CYCLE_RUNS_QUERY,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1,
    RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1,
    _options_from_args,
    _parse_args,
    _write_cycle_output,
    apply_recommendation_benchmark_cycle_preset,
)
from nutmeg.recommendations.benchmark_quality_gate import (
    FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
    RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1,
    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
)


def test_cycle_runs_schedule_then_gate_with_current_benchmark_key() -> None:
    gate_calls: list[RecommendationBenchmarkQualityGateOptions] = []

    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                run_at_utc=_dt(2026, 5, 12, 0),
                save_report=True,
                strategy="accuracy_first",
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                min_completed_ratio=0.95,
                min_final_hit_rate=0.50,
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
            warnings=["schedule:minor_warning"],
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            calls=gate_calls,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.gate is not None
    assert result.summary_json["benchmark_key"] == "recommendation_benchmark:cycle"
    assert result.summary_json["gate_passed"] is True
    assert result.warnings == ["schedule:minor_warning"]
    assert gate_calls[0].benchmark_key == "recommendation_benchmark:cycle"
    assert gate_calls[0].strategy == "accuracy_first"
    assert gate_calls[0].min_completed_ratio == 0.95
    assert gate_calls[0].min_final_hit_rate == 0.50


def test_cycle_fails_when_quality_gate_fails() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=True,
            )
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=False,
            warnings=["benchmark_quality_gate:failed_check:final_hit_rate"],
        ),
    )

    assert result.passed is False
    assert result.status == "failed"
    assert result.summary_json["gate_status"] == "failed"
    assert result.warnings == ["benchmark_quality_gate:failed_check:final_hit_rate"]


def test_cycle_warns_when_gate_runs_without_current_saved_report() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=False,
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                benchmark_key="recommendation_benchmark:manual",
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=False,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.warnings == [
        "benchmark_cycle:gate_reads_existing_history_without_current_saved_report"
    ]
    assert result.summary_json["stored_report_id"] is None


def test_cycle_can_skip_quality_gate() -> None:
    gate_called = False

    def gate_runner(
        database: object,
        *,
        options: RecommendationBenchmarkQualityGateOptions,
    ) -> RecommendationBenchmarkQualityGateResult:
        nonlocal gate_called
        gate_called = True
        return _gate_result(options=options, passed=True)

    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
            ),
            run_gate=False,
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=False,
        ),
        gate_runner=gate_runner,
    )

    assert gate_called is False
    assert result.status == "gate_skipped"
    assert result.passed is True
    assert result.gate is None
    assert result.warnings == ["benchmark_cycle:quality_gate_skipped"]


def test_cycle_can_commit_core_replay_seed_before_schedule() -> None:
    seed_calls: list[RecommendationBenchmarkCoreReplaySeedOptions] = []

    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="once",
                run_at_utc=_dt(2026, 5, 12, 0),
                save_report=True,
            ),
            commit_core_replay_seed=True,
        ),
        core_replay_seed_runner=lambda database, *, options: _core_replay_seed_result(
            options=options,
            calls=seed_calls,
            stored_run_count=27,
            warnings=["seed_notice"],
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
        ),
    )

    assert result.passed is True
    assert seed_calls[0].as_of_time_utc == _dt(2026, 5, 12, 0)
    assert result.warnings == ["core_replay_seed:seed_notice"]
    assert result.summary_json["core_replay_seed_requested"] is True
    assert result.summary_json["core_replay_seed_passed"] is True
    assert result.summary_json["core_replay_seed_budget"] == 10.0
    assert result.summary_json["core_replay_seed_stored_run_count"] == 27


def test_cycle_fails_when_core_replay_seed_fails_even_if_gate_passes() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=True,
            ),
            commit_core_replay_seed=True,
        ),
        core_replay_seed_runner=lambda database, *, options: _core_replay_seed_result(
            options=options,
            passed=False,
            warnings=["benchmark_seed_missing_committed_recommendation_runs"],
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
        ),
    )

    assert result.passed is False
    assert result.status == "failed"
    assert result.warnings == [
        "core_replay_seed:benchmark_seed_missing_committed_recommendation_runs",
        "benchmark_cycle:core_replay_seed_failed",
    ]
    assert result.summary_json["core_replay_seed_passed"] is False


def test_cycle_summary_carries_historical_suite_lifecycle_gate_evidence() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=True,
            )
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    assert result.passed is True
    assert result.summary_json["gate_failed_checks"] == []
    assert result.summary_json["core_replay_ready_ratio"] == 1.0
    assert result.summary_json["final_hit_sample_size"] == 27
    assert result.summary_json["final_hit_coverage_ratio"] == 1.0
    assert result.summary_json["final_hit_rate"] == 2 / 3
    assert result.summary_json["average_core_replay_roi"] == 0.12
    assert result.summary_json["historical_suite_quality_gate_key"] == (
        "historical_recommendation_suite_quality_gate:core"
    )
    assert result.summary_json["historical_suite_quality_gate_passed"] is True
    assert result.summary_json["historical_suite_slice_count"] == 30
    assert result.summary_json["historical_suite_candidate_final_hit_sample_size"] == 30
    assert result.summary_json[
        "historical_suite_candidate_final_hit_coverage_ratio"
    ] == 1.0
    assert result.summary_json["historical_suite_candidate_final_hit_rate"] == 2 / 3
    assert result.summary_json["historical_suite_candidate_roi"] == 0.12
    assert (
        result.summary_json[
            "historical_suite_candidate_dynamic_mixed_final_answer_count"
        ]
        == 6
    )
    assert result.summary_json[
        "historical_suite_candidate_dynamic_mixed_final_answer_rate"
    ] == 0.60
    assert result.summary_json[
        "historical_suite_candidate_final_answer_market_type_counts"
    ] == {
        "1x2": 10,
        "cn_handicap_1x2": 6,
    }
    assert result.summary_json["historical_suite_candidate_handicap_final_answer_count"] == 6
    assert result.summary_json["historical_suite_lifecycle_source_status_synced"] is True
    assert result.summary_json["historical_suite_lifecycle_effective_leaf_count"] == 1
    assert result.summary_json["budget_stability_audit_present"] is True
    assert result.summary_json["budget_stability_slice_count"] == 240
    assert result.summary_json["budget_stability_signature_change_rate"] == 4 / 240
    assert result.summary_json["budget_stability_harmful_change_count"] == 2
    assert result.summary_json["budget_stability_roi_delta"] == -0.004
    assert result.summary_json["final_answer_market_concentration_audit_present"] is True
    assert result.summary_json["final_answer_market_concentration_audit_passed"] is True
    assert result.summary_json[
        "final_answer_market_concentration_dynamic_mixed_final_answer_count"
    ] == 5
    assert result.summary_json[
        "final_answer_market_concentration_effective_pass_types"
    ] == ["2x1", "3x1"]
    assert result.summary_json[
        "final_answer_market_concentration_effective_constraint_profile_count"
    ] == 2
    assert result.summary_json["correct_score_admission_present"] is True
    assert result.summary_json["correct_score_admission_status"] == "holdout_only"
    assert result.summary_json["correct_score_admission_holdout_allowed"] is True
    assert result.summary_json["correct_score_admission_production_allowed"] is False
    assert (
        result.summary_json[
            "correct_score_admission_candidate_correct_score_final_answer_count"
        ]
        == 0
    )
    assert result.summary_json["correct_score_admission_roi_delta"] == 0.011
    assert result.summary_json["runtime_profile_switch_preset"] == (
        RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1
    )
    assert result.summary_json["runtime_profile_switch_ready"] is True
    assert result.summary_json["runtime_profile_switch_replay_passed"] is True
    assert result.summary_json["runtime_profile_switch_replay_roi_delta"] == 0.016
    assert (
        result.summary_json[
            "runtime_profile_switch_replay_final_hit_harm_count_vs_original"
        ]
        == 0
    )
    assert (
        result.summary_json[
            "runtime_profile_switch_replay_profit_loss_harm_count_vs_original"
        ]
        == 0
    )
    assert result.summary_json[
        "final_answer_segment_penalty_runtime_replay_preset"
    ] == FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
    assert (
        result.summary_json[
            "final_answer_segment_penalty_runtime_replay_holdout_allowed"
        ]
        is True
    )
    assert result.summary_json[
        "final_answer_segment_penalty_runtime_replay_roi_delta"
    ] == 0.0703
    assert result.summary_json["market_movement_runtime_activation_present"] is True
    assert result.summary_json["market_movement_runtime_activation_ready"] is True
    assert (
        result.summary_json["market_movement_runtime_activation_selected_rule_count"]
        == 1
    )
    assert (
        result.summary_json[
            "market_movement_runtime_activation_selected_segment_group_keys"
        ]
        == ["competition_outcome:LA_LIGA:home_win"]
    )
    assert (
        result.summary_json["market_movement_runtime_activation_brier_score_delta"]
        == -0.001288445
    )
    assert (
        result.summary_json["market_movement_runtime_activation_default_path_changed"]
        is False
    )
    assert (
        result.summary_json["market_movement_activation_sample_expansion_present"]
        is True
    )
    assert (
        result.summary_json["market_movement_activation_sample_expansion_status"]
        == "shadow_only"
    )
    assert (
        result.summary_json[
            "market_movement_segment_replay_batch_adjusted_fixture_count"
        ]
        == 1323
    )
    assert result.summary_json["market_movement_segment_replay_batch_ready"] is True
    assert result.summary_json["replacement_reranker_shadow_admission_present"] is True
    assert result.summary_json["replacement_reranker_shadow_admission_status"] == (
        "accepted"
    )
    assert (
        result.summary_json[
            "replacement_reranker_shadow_admission_runtime_candidate_allowed"
        ]
        is True
    )
    assert (
        result.summary_json[
            "replacement_reranker_shadow_admission_scope_final_answer_count"
        ]
        == 19
    )
    assert result.summary_json["replacement_reranker_hit_delta_vs_model_top"] == 1
    assert (
        result.summary_json["replacement_reranker_profit_loss_delta_vs_model_top"]
        == 4.1
    )
    assert (
        result.summary_json["replacement_reranker_final_hit_harm_count_vs_model_top"]
        == 0
    )
    assert (
        result.summary_json["replacement_reranker_profit_loss_harm_count_vs_model_top"]
        == 0
    )
    assert result.summary_json["replacement_reranker_failed_fold_count"] == 0
    assert result.summary_json["global_planner_short_odds_adapter_gate_present"] is True
    assert result.summary_json["global_planner_short_odds_adapter_gate_passed"] is True
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_runtime_changed_final_answer_count"
        ]
        == 17
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_runtime_final_hit_harm_count"
        ]
        == 0
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_present"
        ]
        is True
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_status"
        ]
        == "research_only"
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_combined_changed_final_answer_count"
        ]
        == 19
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_watchlist_checks"
        ]
        == ["supplemental_changed_final_answer_count"]
    )
    assert result.summary_json["recommendation_strategy_promotion_gate_present"] is True
    assert result.summary_json["recommendation_strategy_promotion_gate_ready"] is True
    assert (
        result.summary_json[
            "recommendation_strategy_promotion_gate_changed_final_answer_count"
        ]
        == 13
    )
    assert (
        result.summary_json["recommendation_strategy_promotion_gate_profit_loss_delta"]
        == 15.74
    )
    assert (
        result.summary_json[
            "recommendation_strategy_staged_activation_smoke_present"
        ]
        is True
    )
    assert result.summary_json["recommendation_strategy_staged_activation_ready"] is True
    assert result.summary_json["recommendation_strategy_staged_rule_count"] == 1
    assert (
        result.summary_json["recommendation_strategy_staged_default_profile_written"]
        is False
    )
    assert (
        result.summary_json["recommendation_strategy_default_path_isolation_present"]
        is True
    )
    assert result.summary_json["recommendation_strategy_default_path_isolated"] is True
    assert (
        result.summary_json["recommendation_strategy_default_adapter_status"]
        == "disabled"
    )
    assert (
        result.summary_json[
            "recommendation_strategy_explicit_opt_in_selection_changed"
        ]
        is True
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_rolling_admission_present"
        ]
        is True
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_rolling_admission_status"
        ]
        == "accepted"
    )
    assert (
        result.summary_json["probability_calibration_profile_candidate_allowed"]
        is True
    )
    assert result.summary_json["probability_calibration_profile_mode"] == "active"
    assert result.summary_json["probability_calibration_profile_overall_gate_passed"]
    assert (
        result.summary_json[
            "probability_calibration_profile_active_competition_fold_count"
        ]
        == 2
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_active_season_cutoff_fold_count"
        ]
        == 3
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_active_rolling_fold_count"
        ]
        == 2
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_gate_present"
        ]
        is True
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_gate_status"
        ]
        == "model_quality_ready"
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_gate_ready"
        ]
        is True
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_adjusted_fixture_count"
        ]
        == 96
    )
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_brier_score_delta"
        ]
        == -0.01
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_governance_present"
        ]
        is True
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_governance_status"
        ]
        == "governance_ready"
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_governance_ready"
        ]
        is True
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_accepted_segment_count"
        ]
        == 3
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_accepted_validation_count"
        ]
        == 138
    )
    assert result.summary_json["prematch_feature_quality_cycle_present"] is True
    assert result.summary_json["prematch_feature_quality_cycle_passed"] is True
    assert (
        result.summary_json["prematch_feature_quality_cycle_final_answer_gate_key"]
        == "historical_prematch_feature_final_answer_gate:core"
    )
    assert result.summary_json["prematch_feature_quality_cycle_fixture_count"] == 600
    assert (
        result.summary_json[
            "prematch_feature_quality_cycle_best_feature_grid_candidate_id"
        ]
        == "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
    )
    assert (
        result.summary_json["prematch_feature_quality_cycle_best_brier_score_delta"]
        == -0.01
    )
    assert result.summary_json["prematch_feature_rolling_admission_present"] is True
    assert (
        result.summary_json["prematch_feature_rolling_admission_status"]
        == "accepted"
    )
    assert (
        result.summary_json["prematch_feature_rolling_admission_candidate_allowed"]
        is True
    )
    assert (
        result.summary_json[
            "prematch_feature_rolling_admission_overall_passing_candidate_count"
        ]
        == 1
    )
    assert (
        result.summary_json[
            "prematch_feature_rolling_admission_active_competition_fold_count"
        ]
        == 2
    )
    assert (
        result.summary_json[
            "prematch_feature_rolling_admission_best_feature_grid_candidate_id"
        ]
        == "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
    )
    assert result.summary_json["prematch_feature_sample_readiness_present"] is True
    assert (
        result.summary_json["prematch_feature_sample_readiness_status"]
        == "accepted"
    )
    assert result.summary_json["prematch_feature_sample_ready_allowed"] is True
    assert result.summary_json["prematch_feature_sample_ready_fixture_count"] == 600
    assert (
        result.summary_json[
            "prematch_feature_sample_readiness_target_profile"
        ]
        == "market_movement"
    )


def test_cycle_key_includes_runtime_profile_switch_preset() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                runtime_profile_switch_preset=(
                    RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1
                )
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "runtime_profile_switch_preset:short_odds_candidate_v1"
    )
    assert result.summary_json["cycle_key"] == result.cycle_key


def test_cycle_key_includes_segment_penalty_runtime_replay_preset() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                final_answer_segment_penalty_runtime_replay_preset=(
                    FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
                )
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "final_answer_segment_penalty_runtime_replay_preset:"
        "final_answer_segment_penalty_ger_regime_holdout_v1"
    )
    assert result.summary_json["cycle_key"] == result.cycle_key


def test_cycle_key_includes_recommendation_strategy_governance_preset() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                recommendation_strategy_governance_preset=(
                    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
                )
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "recommendation_strategy_governance_preset:"
        "probability_preserving_13change_v1"
    )
    assert result.summary_json["cycle_key"] == result.cycle_key


def test_cycle_key_includes_unified_candidate_pool_guard_preset() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
            gate_options=RecommendationBenchmarkQualityGateOptions(
                unified_candidate_pool_guard_preset=(
                    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
                )
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json={
                **_gate_summary_with_historical_suite_evidence(),
                "unified_candidate_pool_guard_preset": (
                    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
                ),
                "unified_candidate_pool_multiple_value_candidate_count": 2,
                "unified_candidate_pool_multiple_value_admitted_candidate_count": 2,
                "unified_candidate_pool_multiple_value_rejected_candidate_count": 0,
                "unified_candidate_pool_multiple_value_extra_option_count": 4,
                "unified_candidate_pool_selected_multiple_value_statuses": [
                    "admitted"
                ],
                "unified_candidate_pool_selected_multiple_value_admitted_count": 1,
                "unified_candidate_pool_selected_multiple_value_rejected_count": 0,
                "unified_candidate_pool_selected_multiple_extra_option_count": 2,
                "unified_candidate_pool_multiple_value_rejection_reason_counts": {},
            },
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "unified_candidate_pool_guard_preset:"
        "v3_2_unified_candidate_pool_guard_v1"
    )
    assert result.summary_json["unified_candidate_pool_guard_preset"] == (
        UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
    )
    assert result.summary_json["unified_candidate_pool_multiple_value_candidate_count"] == 2
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_value_rejected_count"
        ]
        == 0
    )


def test_cycle_key_includes_cycle_preset() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            cycle_preset=(
                RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
            ),
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "cycle_preset:probability_preserving_13change_governance_v1"
    )
    assert result.summary_json["cycle_preset"] == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
    )


def test_cycle_key_includes_committed_core_replay_seed() -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                cadence="daily",
                save_report=True,
            ),
            commit_core_replay_seed=True,
            core_replay_seed_profile="mixed_outcomes",
            core_replay_seed_reset=False,
        ),
        core_replay_seed_runner=lambda database, *, options: _core_replay_seed_result(
            options=options,
            passed=True,
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
        ),
    )

    assert result.cycle_key == (
        "recommendation_benchmark_cycle:daily-core:daily:gate:"
        "core_replay_seed:mixed_outcomes:append"
    )


def test_cycle_saves_cycle_report_when_enabled() -> None:
    repository = FakeCycleRunRepository()

    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=True,
            ),
            save_cycle_report=True,
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
        cycle_repository=repository,
    )

    assert result.stored_cycle_report is not None
    assert result.stored_cycle_report.recommendation_benchmark_cycle_run_id == 401
    assert repository.saved is not None
    assert repository.saved.cycle_key == result.cycle_key
    assert repository.saved.summary_json["historical_suite_quality_gate_key"] == (
        "historical_recommendation_suite_quality_gate:core"
    )


def test_write_cycle_output_creates_parent_directory(tmp_path: Path) -> None:
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            cycle_preset=(
                RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
            ),
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="dry-run-smoke",
                cadence="once",
                save_report=True,
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda database, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )
    output_path = tmp_path / "reports" / "cycle.json"

    _write_cycle_output(result, output_path)

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["cycle_key"] == result.cycle_key
    assert payload["summary_json"]["cycle_preset"] == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
    )


def test_postgres_cycle_repository_writes_and_lists_runs() -> None:
    database = FakeCycleDatabase()
    repository = PostgresRecommendationBenchmarkCycleRunRepository(database)
    result = run_recommendation_benchmark_cycle(
        FakeDatabase(),
        options=RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="daily-core",
                save_report=True,
            )
        ),
        schedule_runner=lambda db, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        gate_runner=lambda db, *, options: _gate_result(
            options=options,
            passed=True,
            summary_json=_gate_summary_with_historical_suite_evidence(),
        ),
    )

    listed = repository.list_history(
        cycle_key=result.cycle_key,
        benchmark_key="recommendation_benchmark:cycle",
        limit=500,
    )
    stored = repository.save_run(result)

    assert listed[0].cycle_key == result.cycle_key
    assert stored.recommendation_benchmark_cycle_run_id == 402
    assert stored.benchmark_run_id == 88
    assert stored.historical_suite_quality_gate_key == (
        "historical_recommendation_suite_quality_gate:core"
    )
    assert stored.historical_suite_lifecycle_source_status_synced is True
    assert database.fetch_all_calls == [
        (
            LIST_RECOMMENDATION_BENCHMARK_CYCLE_RUNS_QUERY,
            {
                "cycle_key": result.cycle_key,
                "benchmark_key": "recommendation_benchmark:cycle",
                "limit": 200,
            },
        )
    ]
    insert_query, params = database.fetch_one_calls[0]
    assert insert_query == INSERT_RECOMMENDATION_BENCHMARK_CYCLE_RUN_QUERY
    assert params["cycle_key"] == result.cycle_key
    assert params["benchmark_run_id"] == 88
    assert params["gate_passed"] is True
    assert params["historical_suite_quality_gate_key"] == (
        "historical_recommendation_suite_quality_gate:core"
    )
    assert params["historical_suite_lifecycle_effective_leaf_count"] == 1


def test_cycle_cli_args_map_to_nested_options() -> None:
    args = _parse_args(
        [
            "--schedule-name",
            "weekly-core",
            "--cadence",
            "weekly",
            "--run-at-utc",
            "2026-05-12T00:00:00Z",
            "--window-count",
            "4",
            "--pass-types",
            "2x1,8x1",
            "--modes",
            "single,multiple",
            "--budgets",
            "10,50",
            "--strategy",
            "budget_constrained",
            "--save-report",
            "--save-cycle-report",
            "--include-prematch-pipeline",
            "--gate-history-limit",
            "5",
            "--gate-min-completed-ratio",
            "0.9",
            "--gate-max-warning-count",
            "2",
            "--gate-min-global-best-selected-count",
            "4",
            "--gate-min-global-best-candidate-count",
            "20",
            "--gate-min-global-best-generated-option-count",
            "5",
            "--gate-min-core-replay-ready-ratio",
            "0.7",
            "--gate-min-chain-integrity-ready-ratio",
            "1.0",
            "--gate-max-chain-integrity-critical-issue-count",
            "0",
            "--gate-min-successor-chain-evaluation-passed-ratio",
            "0.8",
            "--gate-min-successor-chain-effective-leaf-count",
            "8",
            "--gate-max-successor-chain-critical-issue-count",
            "0",
            "--gate-max-successor-chain-ambiguous-source-count",
            "1",
            "--gate-max-successor-chain-source-status-sync-required-count",
            "2",
            "--gate-max-ambiguous-successor-source-count",
            "1",
            "--gate-max-stale-recommendation-count",
            "2",
            "--gate-max-successor-recompute-required-count",
            "3",
            "--gate-min-final-hit-sample-size",
            "10",
            "--gate-min-final-hit-coverage-ratio",
            "0.8",
            "--gate-min-final-hit-rate",
            "0.55",
            "--gate-min-average-core-replay-roi",
            "-0.05",
            "--gate-min-upset-capture-sample-size",
            "4",
            "--gate-min-upset-capture-rate",
            "0.25",
            "--gate-require-unified-candidate-pool",
            "--gate-min-unified-candidate-pool-present-count",
            "10",
            "--gate-min-unified-candidate-pool-valid-candidate-count",
            "20",
            "--gate-min-unified-candidate-pool-unique-family-count",
            "3",
            "--gate-max-unified-candidate-pool-selection-mismatch-count",
            "0",
            "--gate-max-unified-candidate-pool-selected-2x1-rate",
            "0.5",
            "--gate-require-unified-candidate-pool-multiple-value-admission",
            "--gate-min-unified-candidate-pool-multiple-value-candidate-count",
            "4",
            "--gate-min-unified-candidate-pool-multiple-value-admitted-candidate-count",
            "3",
            "--gate-min-unified-candidate-pool-multiple-value-extra-option-count",
            "8",
            "--gate-max-unified-candidate-pool-multiple-value-rejected-candidate-count",
            "1",
            "--gate-max-unified-candidate-pool-selected-multiple-value-rejected-count",
            "0",
            "--gate-historical-suite-quality-gate-report-path",
            "configs/recommendations/historical_reports/core_gate.json",
            "--gate-require-historical-suite-quality-gate",
            "--gate-allow-missing-historical-suite-lifecycle-evidence",
            "--gate-allow-unsynced-historical-suite-lifecycle-source-status",
            "--gate-min-historical-suite-slice-count",
            "30",
            "--gate-min-historical-suite-comparison-count",
            "30",
            "--gate-min-historical-suite-candidate-final-hit-sample-size",
            "30",
            "--gate-min-historical-suite-candidate-final-hit-coverage-ratio",
            "1.0",
            "--gate-min-historical-suite-candidate-dynamic-mixed-final-answer-count",
            "6",
            "--gate-min-historical-suite-candidate-dynamic-mixed-final-answer-rate",
            "0.7",
            "--gate-min-historical-suite-candidate-handicap-final-answer-count",
            "5",
            "--gate-min-historical-suite-candidate-correct-score-final-answer-count",
            "4",
            "--gate-min-historical-suite-candidate-multiple-choice-final-answer-count",
            "3",
            "--gate-max-historical-suite-failed-check-count",
            "0",
            "--gate-min-historical-suite-lifecycle-effective-leaf-count",
            "1",
            "--gate-min-historical-suite-lifecycle-active-edge-count",
            "1",
            "--gate-max-historical-suite-lifecycle-critical-issue-count",
            "0",
            "--gate-max-historical-suite-lifecycle-source-status-sync-required-count",
            "0",
            "--gate-require-historical-suite-successor-chain-evaluation",
            "--gate-min-historical-suite-successor-effective-leaf-count",
            "2",
            "--gate-min-historical-suite-successor-active-edge-count",
            "1",
            "--gate-max-historical-suite-successor-critical-issue-count",
            "0",
            "--gate-max-historical-suite-successor-ambiguous-source-count",
            "0",
            "--gate-max-historical-suite-successor-source-status-sync-required-count",
            "0",
            "--gate-budget-stability-audit-report-path",
            "configs/recommendations/historical_reports/budget_stability.json",
            "--gate-require-budget-stability-audit",
            "--gate-min-budget-stability-slice-count",
            "240",
            "--gate-min-budget-stability-comparable-count",
            "240",
            "--gate-max-budget-stability-signature-change-rate",
            "0.02",
            "--gate-max-budget-stability-harmful-change-count",
            "2",
            "--gate-min-budget-stability-hit-delta-count",
            "-1",
            "--gate-min-budget-stability-profit-loss-delta",
            "-3",
            "--gate-min-budget-stability-roi-delta",
            "-0.005",
            "--gate-max-budget-stability-warning-count",
            "0",
            "--gate-runtime-profile-switch-report-path",
            "configs/recommendations/historical_reports/switch.json",
            "--gate-runtime-profile-switch-replay-report-path",
            "configs/recommendations/historical_reports/replay.json",
            "--gate-require-runtime-profile-switch-gate",
            "--gate-allow-missing-runtime-profile-switch-replay",
            "--gate-allow-runtime-profile-switch-applied",
            "--gate-min-runtime-profile-switch-rule-count",
            "2",
            "--gate-min-runtime-profile-switch-allowed-competition-count",
            "3",
            "--gate-min-runtime-profile-switch-final-answer-count",
            "12",
            "--gate-min-runtime-profile-switch-changed-final-answer-count",
            "4",
            "--gate-min-runtime-profile-switch-final-answer-hit-rate-delta",
            "0.01",
            "--gate-min-runtime-profile-switch-roi-delta",
            "0.02",
            "--gate-min-runtime-profile-switch-profit-loss-delta",
            "0.03",
            "--gate-max-runtime-profile-switch-harm-count-vs-original",
            "1",
            "--gate-max-runtime-profile-switch-final-hit-harm-count-vs-original",
            "2",
            "--gate-max-runtime-profile-switch-profit-loss-harm-count-vs-original",
            "3",
            "--gate-min-runtime-profile-switch-average-hit-probability-delta",
            "-0.03",
            "--gate-final-answer-segment-penalty-runtime-replay-report-path",
            "configs/recommendations/historical_reports/segment_replay.json",
            "--gate-require-final-answer-segment-penalty-runtime-replay",
            "--gate-allow-missing-final-answer-segment-penalty-runtime-replay-holdout",
            "--gate-require-final-answer-segment-penalty-runtime-replay-runtime-allowed",
            "--gate-min-final-answer-segment-penalty-runtime-replay-rule-count",
            "2",
            "--gate-min-final-answer-segment-penalty-runtime-replay-selected-rule-count",
            "1",
            "--gate-max-final-answer-segment-penalty-runtime-replay-selected-rule-count",
            "2",
            "--gate-min-final-answer-segment-penalty-runtime-replay-final-answer-count",
            "30",
            "--gate-min-final-answer-segment-penalty-runtime-replay-changed-final-answer-count",
            "2",
            "--gate-min-final-answer-segment-penalty-runtime-replay-penalty-option-count",
            "2",
            "--gate-min-final-answer-segment-penalty-runtime-replay-hit-count-delta",
            "1",
            "--gate-min-final-answer-segment-penalty-runtime-replay-hit-rate-delta",
            "0.01",
            "--gate-min-final-answer-segment-penalty-runtime-replay-roi-delta",
            "0.02",
            "--gate-min-final-answer-segment-penalty-runtime-replay-profit-loss-delta",
            "1.0",
            "--gate-min-final-answer-segment-penalty-runtime-replay-candidate-roi",
            "0.0",
            "--gate-max-final-answer-segment-penalty-runtime-replay-brier-score-delta",
            "0.01",
            "--gate-max-final-answer-segment-penalty-runtime-replay-log-loss-delta",
            "0.02",
            "--gate-max-final-answer-segment-penalty-runtime-replay-calibration-error-delta",
            "0.03",
            "--gate-max-final-answer-segment-penalty-runtime-replay-harm-count-vs-baseline",
            "1",
            "--gate-max-final-answer-segment-penalty-runtime-replay-final-hit-harm-count-vs-baseline",
            "2",
            "--gate-max-final-answer-segment-penalty-runtime-replay-profit-loss-harm-count-vs-baseline",
            "3",
            "--gate-allow-final-answer-segment-penalty-runtime-replay-production-change",
            "--gate-allow-final-answer-segment-penalty-runtime-replay-public-change",
            "--gate-market-movement-runtime-activation-report-path",
            "configs/recommendations/historical_reports/market_movement_activation.json",
            "--gate-require-market-movement-runtime-activation",
            "--gate-allow-market-movement-runtime-activation-not-ready",
            "--gate-min-market-movement-runtime-activation-rule-count",
            "1",
            "--gate-min-market-movement-runtime-activation-selected-rule-count",
            "1",
            "--gate-max-market-movement-runtime-activation-selected-rule-count",
            "1",
            "--gate-min-market-movement-runtime-activation-adjusted-fixture-count",
            "120",
            "--gate-min-market-movement-runtime-activation-adjusted-prediction-count",
            "360",
            "--gate-min-market-movement-runtime-activation-final-hit-rate-delta",
            "0.0",
            "--gate-min-market-movement-runtime-activation-roi-delta",
            "0.01",
            "--gate-min-market-movement-runtime-activation-profit-loss-delta",
            "1.0",
            "--gate-max-market-movement-runtime-activation-brier-score-delta",
            "0.02",
            "--gate-max-market-movement-runtime-activation-log-loss-delta",
            "0.03",
            "--gate-max-market-movement-runtime-activation-calibration-delta",
            "0.04",
            "--gate-allow-market-movement-runtime-activation-default-profile-write",
            "--gate-allow-market-movement-runtime-activation-default-path-change",
            "--gate-allow-market-movement-runtime-activation-production-change",
            "--gate-allow-market-movement-runtime-activation-public-change",
            "--gate-market-movement-runtime-activation-sample-expansion-report-path",
            "configs/recommendations/historical_reports/market_movement_sample_expansion.json",
            "--gate-require-market-movement-runtime-activation-sample-expansion",
            "--gate-require-market-movement-runtime-activation-sample-expansion-promotion-ready",
            "--gate-market-movement-runtime-activation-segment-replay-batch-gate-report-path",
            "configs/recommendations/historical_reports/market_movement_segment_replay_batch_gate.json",
            "--gate-require-market-movement-runtime-activation-segment-replay-batch-gate",
            "--gate-allow-market-movement-runtime-activation-segment-replay-batch-not-ready",
            "--gate-require-market-movement-runtime-activation-segment-replay-batch-promotion-ready",
            "--gate-min-market-movement-runtime-activation-segment-replay-batch-report-count",
            "4",
            "--gate-min-market-movement-runtime-activation-segment-replay-batch-passed-count",
            "4",
            "--gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-fixture-count",
            "1200",
            "--gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-prediction-count",
            "3600",
            "--gate-replacement-reranker-shadow-admission-report-path",
            "configs/recommendations/historical_reports/replacement_admission.json",
            "--gate-require-replacement-reranker-shadow-admission",
            "--gate-allow-replacement-reranker-shadow-only",
            "--gate-require-replacement-reranker-scoped-evidence",
            "--gate-require-replacement-reranker-prematch-source-surface",
            "--gate-min-replacement-reranker-scope-final-answer-count",
            "19",
            "--gate-min-replacement-reranker-shadow-final-answer-count",
            "17",
            "--gate-min-replacement-reranker-changed-from-model-top-count",
            "5",
            "--gate-min-replacement-reranker-hit-delta-vs-model-top",
            "1",
            "--gate-min-replacement-reranker-profit-loss-delta-vs-model-top",
            "4.0",
            "--gate-min-replacement-reranker-roi-delta-vs-model-top",
            "0.10",
            "--gate-max-replacement-reranker-harm-count-vs-model-top",
            "0",
            "--gate-max-replacement-reranker-final-hit-harm-count-vs-model-top",
            "2",
            "--gate-max-replacement-reranker-profit-loss-harm-count-vs-model-top",
            "3",
            "--gate-max-replacement-reranker-failed-fold-count",
            "0",
            "--gate-min-replacement-reranker-active-competition-fold-count",
            "2",
            "--gate-min-replacement-reranker-active-season-fold-count",
            "3",
            "--gate-min-replacement-reranker-active-rolling-fold-count",
            "4",
            "--gate-global-planner-short-odds-adapter-gate-report-path",
            "configs/recommendations/historical_reports/planner_adapter_gate.json",
            "--gate-require-global-planner-short-odds-adapter-gate",
            "--gate-allow-global-planner-short-odds-adapter-default-path-change",
            "--gate-allow-global-planner-short-odds-adapter-shadow-path-change",
            "--gate-allow-global-planner-short-odds-adapter-missing-explicit-opt-in-change",
            "--gate-min-global-planner-short-odds-adapter-runtime-final-answer-count",
            "31",
            "--gate-min-global-planner-short-odds-adapter-runtime-changed-final-answer-count",
            "6",
            "--gate-min-global-planner-short-odds-adapter-runtime-final-answer-hit-rate-delta",
            "0.01",
            "--gate-min-global-planner-short-odds-adapter-runtime-roi-delta",
            "0.02",
            "--gate-min-global-planner-short-odds-adapter-runtime-profit-loss-delta",
            "0.03",
            "--gate-max-global-planner-short-odds-adapter-runtime-harm-count-vs-original",
            "1",
            "--gate-max-global-planner-short-odds-adapter-runtime-final-hit-harm-count-vs-original",
            "2",
            "--gate-max-global-planner-short-odds-adapter-runtime-profit-loss-harm-count-vs-original",
            "3",
            "--gate-min-global-planner-short-odds-adapter-runtime-average-hit-probability-delta",
            "-0.03",
            "--gate-allow-global-planner-short-odds-adapter-runtime-public-change",
            "--gate-allow-global-planner-short-odds-adapter-runtime-production-change",
            "--gate-global-planner-short-odds-adapter-sample-expansion-report-path",
            "configs/recommendations/historical_reports/sample_expansion.json",
            "--gate-require-global-planner-short-odds-adapter-sample-expansion",
            "--gate-require-global-planner-short-odds-adapter-sample-expansion-promotion-ready",
            "--gate-probability-calibration-profile-rolling-admission-report-path",
            "configs/recommendations/historical_reports/probability_calibration_admission.json",
            "--gate-require-probability-calibration-profile-rolling-admission",
            "--gate-allow-probability-calibration-profile-shadow-only",
            "--gate-allow-probability-calibration-profile-non-active-profile",
            "--gate-min-probability-calibration-profile-overall-adjusted-fixture-count",
            "24",
            "--gate-min-probability-calibration-profile-overall-bucket-count",
            "3",
            "--gate-max-probability-calibration-profile-failed-fold-count",
            "1",
            "--gate-min-probability-calibration-profile-active-competition-fold-count",
            "2",
            "--gate-min-probability-calibration-profile-active-season-cutoff-fold-count",
            "3",
            "--gate-min-probability-calibration-profile-active-rolling-fold-count",
            "4",
            "--gate-probability-calibration-profile-model-quality-gate-report-path",
            "configs/recommendations/historical_reports/probability_model_quality_gate.json",
            "--gate-require-probability-calibration-profile-model-quality-gate",
            "--gate-allow-probability-calibration-profile-model-quality-not-ready",
            "--gate-min-probability-calibration-profile-model-quality-selected-competition-count",
            "4",
            "--gate-min-probability-calibration-profile-model-quality-adjusted-slice-count",
            "4",
            "--gate-min-probability-calibration-profile-model-quality-adjusted-fixture-count",
            "96",
            "--gate-max-probability-calibration-profile-model-quality-skipped-fixture-count",
            "2",
            "--gate-max-probability-calibration-profile-model-quality-final-answer-changed-count",
            "1",
            "--gate-min-probability-calibration-profile-model-quality-final-answer-hit-count-delta",
            "1",
            "--gate-min-probability-calibration-profile-model-quality-final-answer-hit-rate-delta",
            "0.01",
            "--gate-min-probability-calibration-profile-model-quality-roi-delta",
            "0.02",
            "--gate-min-probability-calibration-profile-model-quality-profit-loss-delta",
            "1.0",
            "--gate-max-probability-calibration-profile-model-quality-brier-score-delta",
            "0.01",
            "--gate-max-probability-calibration-profile-model-quality-log-loss-delta",
            "0.02",
            "--gate-max-probability-calibration-profile-model-quality-calibration-error-delta",
            "0.03",
            "--gate-asian-handicap-segmented-model-quality-governance-report-path",
            "configs/recommendations/historical_reports/asian_handicap_governance.json",
            "--gate-require-asian-handicap-segmented-model-quality-governance",
            "--gate-allow-asian-handicap-segmented-model-quality-not-ready",
            "--gate-allow-asian-handicap-segmented-model-quality-non-internal",
            "--gate-allow-asian-handicap-segmented-model-quality-default-path-not-isolated",
            "--gate-allow-asian-handicap-segmented-model-quality-production-change",
            "--gate-allow-asian-handicap-segmented-model-quality-public-response-change",
            "--gate-min-asian-handicap-segmented-model-quality-accepted-segment-count",
            "3",
            "--gate-max-asian-handicap-segmented-model-quality-shadow-segment-count",
            "0",
            "--gate-max-asian-handicap-segmented-model-quality-fallback-segment-count",
            "2",
            "--gate-max-asian-handicap-segmented-model-quality-rejected-segment-count",
            "0",
            "--gate-min-asian-handicap-segmented-model-quality-accepted-validation-count",
            "100",
            "--gate-min-asian-handicap-segmented-model-quality-calibration-applied-count",
            "2",
            "--gate-min-asian-handicap-segmented-model-quality-hit-rate-delta",
            "0.0",
            "--gate-max-asian-handicap-segmented-model-quality-brier-score-delta",
            "0.01",
            "--gate-max-asian-handicap-segmented-model-quality-log-loss-delta",
            "0.02",
            "--gate-max-asian-handicap-segmented-model-quality-calibration-error-delta",
            "0.03",
            "--gate-min-asian-handicap-segmented-model-quality-actual-probability-delta",
            "-0.01",
            "--gate-prematch-feature-quality-cycle-report-path",
            "configs/recommendations/historical_reports/prematch_feature_quality_cycle.json",
            "--gate-require-prematch-feature-quality-cycle",
            "--gate-allow-failed-prematch-feature-quality-cycle",
            "--gate-allow-prematch-feature-quality-cycle-best-gate-failed",
            "--gate-min-prematch-feature-quality-cycle-slice-count",
            "25",
            "--gate-min-prematch-feature-quality-cycle-fixture-count",
            "600",
            "--gate-min-prematch-feature-quality-cycle-evaluated-candidate-count",
            "5",
            "--gate-min-prematch-feature-quality-cycle-passing-candidate-count",
            "1",
            "--gate-max-prematch-feature-quality-cycle-warning-count",
            "2",
            "--gate-max-prematch-feature-quality-cycle-best-brier-score-delta",
            "0.01",
            "--gate-max-prematch-feature-quality-cycle-best-log-loss-delta",
            "0.02",
            "--gate-max-prematch-feature-quality-cycle-best-calibration-error-delta",
            "0.03",
            "--gate-prematch-feature-rolling-admission-report-path",
            "configs/recommendations/historical_reports/prematch_feature_rolling_admission.json",
            "--gate-require-prematch-feature-rolling-admission",
            "--gate-allow-prematch-feature-rolling-admission-shadow-only",
            "--gate-min-prematch-feature-rolling-admission-overall-evaluated-candidate-count",
            "5",
            "--gate-min-prematch-feature-rolling-admission-overall-passing-candidate-count",
            "1",
            "--gate-max-prematch-feature-rolling-admission-failed-fold-count",
            "1",
            "--gate-min-prematch-feature-rolling-admission-active-competition-fold-count",
            "2",
            "--gate-min-prematch-feature-rolling-admission-active-season-cutoff-fold-count",
            "3",
            "--gate-min-prematch-feature-rolling-admission-active-rolling-fold-count",
            "4",
            "--gate-max-prematch-feature-rolling-admission-overall-brier-score-delta",
            "0.01",
            "--gate-max-prematch-feature-rolling-admission-overall-log-loss-delta",
            "0.02",
            "--gate-max-prematch-feature-rolling-admission-overall-calibration-error-delta",
            "0.03",
            "--gate-prematch-feature-sample-readiness-report-path",
            "configs/recommendations/historical_reports/prematch_feature_sample_readiness.json",
            "--gate-require-prematch-feature-sample-readiness",
            "--gate-allow-prematch-feature-sample-readiness-shadow-only",
            "--gate-min-prematch-feature-sample-ready-source-count",
            "2",
            "--gate-min-prematch-feature-sample-ready-fixture-count",
            "600",
            "--gate-min-prematch-feature-sample-ready-competition-count",
            "3",
            "--gate-min-prematch-feature-sample-ready-season-count",
            "2",
            "--gate-min-prematch-feature-sample-ready-competition-season-count",
            "5",
            "--gate-max-prematch-feature-sample-readiness-warning-count",
            "4",
            "--gate-fail-on-history-statuses",
            "regressed,mixed",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.run_gate is True
    assert options.schedule_options.schedule_name == "weekly-core"
    assert options.schedule_options.cadence == "weekly"
    assert options.schedule_options.run_at_utc == _dt(2026, 5, 12, 0)
    assert options.schedule_options.window_count == 4
    assert options.schedule_options.pass_types == ("2x1", "8x1")
    assert options.schedule_options.modes == ("single", "multiple")
    assert options.schedule_options.max_budgets == (10.0, 50.0)
    assert options.schedule_options.strategy == "budget_constrained"
    assert options.schedule_options.save_report is True
    assert options.save_cycle_report is True
    assert options.schedule_options.run_prematch_pipeline is True
    assert options.gate_options.strategy == "budget_constrained"
    assert options.gate_options.history_limit == 5
    assert options.gate_options.min_completed_ratio == 0.9
    assert options.gate_options.max_warning_count == 2
    assert options.gate_options.min_global_best_selected_count == 4
    assert options.gate_options.min_global_best_candidate_count == 20
    assert options.gate_options.min_global_best_generated_option_count == 5
    assert options.gate_options.min_core_replay_ready_ratio == 0.7
    assert options.gate_options.min_chain_integrity_ready_ratio == 1.0
    assert options.gate_options.max_chain_integrity_critical_issue_count == 0
    assert options.gate_options.min_successor_chain_evaluation_passed_ratio == 0.8
    assert options.gate_options.min_successor_chain_effective_leaf_count == 8
    assert options.gate_options.max_successor_chain_critical_issue_count == 0
    assert options.gate_options.max_successor_chain_ambiguous_source_count == 1
    assert options.gate_options.max_successor_chain_source_status_sync_required_count == 2
    assert options.gate_options.max_ambiguous_successor_source_count == 1
    assert options.gate_options.max_stale_recommendation_count == 2
    assert options.gate_options.max_successor_recompute_required_count == 3
    assert options.gate_options.min_final_hit_sample_size == 10
    assert options.gate_options.min_final_hit_coverage_ratio == 0.8
    assert options.gate_options.min_final_hit_rate == 0.55
    assert options.gate_options.min_average_core_replay_roi == -0.05
    assert options.gate_options.min_upset_capture_sample_size == 4
    assert options.gate_options.min_upset_capture_rate == 0.25
    assert options.gate_options.require_unified_candidate_pool is True
    assert options.gate_options.min_unified_candidate_pool_present_count == 10
    assert options.gate_options.min_unified_candidate_pool_valid_candidate_count == 20
    assert options.gate_options.min_unified_candidate_pool_unique_family_count == 3
    assert options.gate_options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert options.gate_options.max_unified_candidate_pool_selected_2x1_rate == 0.5
    assert (
        options.gate_options.require_unified_candidate_pool_multiple_value_admission
        is True
    )
    assert (
        options.gate_options.min_unified_candidate_pool_multiple_value_candidate_count
        == 4
    )
    assert (
        options.gate_options.min_unified_candidate_pool_multiple_value_admitted_candidate_count
        == 3
    )
    assert (
        options.gate_options.min_unified_candidate_pool_multiple_value_extra_option_count
        == 8
    )
    assert (
        options.gate_options.max_unified_candidate_pool_multiple_value_rejected_candidate_count
        == 1
    )
    assert (
        options.gate_options.max_unified_candidate_pool_selected_multiple_value_rejected_count
        == 0
    )
    assert options.gate_options.historical_suite_quality_gate_report_path is not None
    assert str(options.gate_options.historical_suite_quality_gate_report_path).endswith(
        "core_gate.json"
    )
    assert options.gate_options.require_historical_suite_quality_gate is True
    assert options.gate_options.require_historical_suite_lifecycle_evidence is False
    assert (
        options.gate_options.require_historical_suite_lifecycle_source_status_synced
        is False
    )
    assert options.gate_options.min_historical_suite_slice_count == 30
    assert options.gate_options.min_historical_suite_comparison_count == 30
    assert (
        options.gate_options.min_historical_suite_candidate_final_hit_sample_size
        == 30
    )
    assert (
        options.gate_options.min_historical_suite_candidate_final_hit_coverage_ratio
        == 1.0
    )
    assert (
        options.gate_options.min_historical_suite_candidate_dynamic_mixed_final_answer_count
        == 6
    )
    assert (
        options.gate_options.min_historical_suite_candidate_dynamic_mixed_final_answer_rate
        == 0.7
    )
    assert options.gate_options.min_historical_suite_candidate_handicap_final_answer_count == 5
    assert (
        options.gate_options.min_historical_suite_candidate_correct_score_final_answer_count
        == 4
    )
    assert (
        options.gate_options.min_historical_suite_candidate_multiple_choice_final_answer_count
        == 3
    )
    assert options.gate_options.max_historical_suite_failed_check_count == 0
    assert options.gate_options.min_historical_suite_lifecycle_effective_leaf_count == 1
    assert options.gate_options.min_historical_suite_lifecycle_active_edge_count == 1
    assert (
        options.gate_options.max_historical_suite_lifecycle_critical_issue_count == 0
    )
    assert (
        options.gate_options.max_historical_suite_lifecycle_source_status_sync_required_count
        == 0
    )
    assert (
        options.gate_options.require_historical_suite_successor_chain_evaluation
        is True
    )
    assert (
        options.gate_options.min_historical_suite_successor_effective_leaf_count == 2
    )
    assert options.gate_options.min_historical_suite_successor_active_edge_count == 1
    assert options.gate_options.max_historical_suite_successor_critical_issue_count == 0
    assert options.gate_options.max_historical_suite_successor_ambiguous_source_count == 0
    assert (
        options.gate_options.max_historical_suite_successor_source_status_sync_required_count
        == 0
    )
    assert options.gate_options.budget_stability_audit_report_path is not None
    assert str(options.gate_options.budget_stability_audit_report_path).endswith(
        "budget_stability.json"
    )
    assert options.gate_options.require_budget_stability_audit is True
    assert options.gate_options.min_budget_stability_slice_count == 240
    assert options.gate_options.min_budget_stability_comparable_count == 240
    assert options.gate_options.max_budget_stability_signature_change_rate == 0.02
    assert options.gate_options.max_budget_stability_harmful_change_count == 2
    assert options.gate_options.min_budget_stability_hit_delta_count == -1
    assert options.gate_options.min_budget_stability_profit_loss_delta == -3.0
    assert options.gate_options.min_budget_stability_roi_delta == -0.005
    assert options.gate_options.max_budget_stability_warning_count == 0
    assert options.gate_options.runtime_profile_switch_report_path is not None
    assert str(options.gate_options.runtime_profile_switch_report_path).endswith(
        "switch.json"
    )
    assert options.gate_options.runtime_profile_switch_replay_report_path is not None
    assert str(
        options.gate_options.runtime_profile_switch_replay_report_path
    ).endswith("replay.json")
    assert options.gate_options.require_runtime_profile_switch_gate is True
    assert options.gate_options.require_runtime_profile_switch_replay is False
    assert options.gate_options.require_runtime_profile_switch_staged_only is False
    assert options.gate_options.min_runtime_profile_switch_rule_count == 2
    assert (
        options.gate_options.min_runtime_profile_switch_allowed_competition_count == 3
    )
    assert options.gate_options.min_runtime_profile_switch_final_answer_count == 12
    assert (
        options.gate_options.min_runtime_profile_switch_changed_final_answer_count == 4
    )
    assert (
        options.gate_options.min_runtime_profile_switch_final_answer_hit_rate_delta
        == 0.01
    )
    assert options.gate_options.min_runtime_profile_switch_roi_delta == 0.02
    assert options.gate_options.min_runtime_profile_switch_profit_loss_delta == 0.03
    assert options.gate_options.max_runtime_profile_switch_harm_count_vs_original == 1
    assert (
        options.gate_options.max_runtime_profile_switch_final_hit_harm_count_vs_original
        == 2
    )
    assert (
        options.gate_options.max_runtime_profile_switch_profit_loss_harm_count_vs_original
        == 3
    )
    assert (
        options.gate_options.min_runtime_profile_switch_average_hit_probability_delta
        == -0.03
    )
    assert (
        options.gate_options.final_answer_segment_penalty_runtime_replay_report_path
        is not None
    )
    assert str(
        options.gate_options.final_answer_segment_penalty_runtime_replay_report_path
    ).endswith("segment_replay.json")
    assert (
        options.gate_options.require_final_answer_segment_penalty_runtime_replay
        is True
    )
    assert (
        options.gate_options.require_final_answer_segment_penalty_runtime_replay_holdout_allowed
        is False
    )
    assert (
        options.gate_options.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        is True
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_rule_count
        == 2
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 1
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 2
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_final_answer_count
        == 30
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        == 2
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        == 2
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_hit_count_delta
        == 1
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_hit_rate_delta
        == 0.01
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_roi_delta
        == 0.02
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_profit_loss_delta
        == 1.0
    )
    assert (
        options.gate_options.min_final_answer_segment_penalty_runtime_replay_candidate_roi
        == 0.0
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_brier_score_delta
        == 0.01
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_log_loss_delta
        == 0.02
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_calibration_error_delta
        == 0.03
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
        == 1
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        == 2
    )
    assert (
        options.gate_options.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        == 3
    )
    assert (
        options.gate_options.require_final_answer_segment_penalty_runtime_replay_no_production_change
        is False
    )
    assert (
        options.gate_options.require_final_answer_segment_penalty_runtime_replay_no_public_response_change
        is False
    )
    assert (
        options.gate_options.market_movement_runtime_activation_report_path
        is not None
    )
    assert str(
        options.gate_options.market_movement_runtime_activation_report_path
    ).endswith("market_movement_activation.json")
    assert options.gate_options.require_market_movement_runtime_activation is True
    assert options.gate_options.require_market_movement_runtime_activation_ready is False
    assert options.gate_options.min_market_movement_runtime_activation_rule_count == 1
    assert (
        options.gate_options.min_market_movement_runtime_activation_selected_rule_count
        == 1
    )
    assert (
        options.gate_options.max_market_movement_runtime_activation_selected_rule_count
        == 1
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_adjusted_fixture_count
        == 120
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_adjusted_prediction_count
        == 360
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_final_hit_rate_delta
        == 0.0
    )
    assert options.gate_options.min_market_movement_runtime_activation_roi_delta == 0.01
    assert (
        options.gate_options.min_market_movement_runtime_activation_profit_loss_delta
        == 1.0
    )
    assert (
        options.gate_options.max_market_movement_runtime_activation_brier_score_delta
        == 0.02
    )
    assert (
        options.gate_options.max_market_movement_runtime_activation_log_loss_delta
        == 0.03
    )
    assert (
        options.gate_options.max_market_movement_runtime_activation_mean_calibration_error_delta
        == 0.04
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_no_default_profile_write
        is False
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_no_default_path_change
        is False
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_no_production_change
        is False
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_no_public_response_change
        is False
    )
    assert (
        options.gate_options.market_movement_runtime_activation_sample_expansion_report_path
        is not None
    )
    assert str(
        options.gate_options.market_movement_runtime_activation_sample_expansion_report_path
    ).endswith("market_movement_sample_expansion.json")
    assert (
        options.gate_options.require_market_movement_runtime_activation_sample_expansion
        is True
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_sample_expansion_promotion_ready
        is True
    )
    assert (
        options.gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        is not None
    )
    assert str(
        options.gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
    ).endswith("market_movement_segment_replay_batch_gate.json")
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_gate
        is True
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_ready
        is False
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
        is True
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_report_count
        == 4
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_passed_count
        == 4
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
        == 1200
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
        == 3600
    )
    assert (
        options.gate_options.replacement_reranker_shadow_admission_report_path
        is not None
    )
    assert str(
        options.gate_options.replacement_reranker_shadow_admission_report_path
    ).endswith("replacement_admission.json")
    assert options.gate_options.require_replacement_reranker_shadow_admission is True
    assert (
        options.gate_options.require_replacement_reranker_runtime_candidate_allowed
        is False
    )
    assert options.gate_options.require_replacement_reranker_scoped_evidence is True
    assert (
        options.gate_options.require_replacement_reranker_prematch_source_surface
        is True
    )
    assert options.gate_options.min_replacement_reranker_scope_final_answer_count == 19
    assert options.gate_options.min_replacement_reranker_shadow_final_answer_count == 17
    assert options.gate_options.min_replacement_reranker_changed_from_model_top_count == 5
    assert options.gate_options.min_replacement_reranker_hit_delta_vs_model_top == 1
    assert (
        options.gate_options.min_replacement_reranker_profit_loss_delta_vs_model_top
        == 4.0
    )
    assert options.gate_options.min_replacement_reranker_roi_delta_vs_model_top == 0.10
    assert options.gate_options.max_replacement_reranker_harm_count_vs_model_top == 0
    assert (
        options.gate_options.max_replacement_reranker_final_hit_harm_count_vs_model_top
        == 2
    )
    assert (
        options.gate_options.max_replacement_reranker_profit_loss_harm_count_vs_model_top
        == 3
    )
    assert options.gate_options.max_replacement_reranker_failed_fold_count == 0
    assert (
        options.gate_options.min_replacement_reranker_active_competition_fold_count
        == 2
    )
    assert options.gate_options.min_replacement_reranker_active_season_fold_count == 3
    assert options.gate_options.min_replacement_reranker_active_rolling_fold_count == 4
    assert (
        options.gate_options.global_planner_short_odds_adapter_gate_report_path
        is not None
    )
    assert str(
        options.gate_options.global_planner_short_odds_adapter_gate_report_path
    ).endswith("planner_adapter_gate.json")
    assert options.gate_options.require_global_planner_short_odds_adapter_gate is True
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_default_path_unchanged
        is False
    )
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_shadow_path_unchanged
        is False
    )
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_explicit_opt_in_changed
        is False
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_final_answer_count
        == 31
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_changed_final_answer_count
        == 6
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta
        == 0.01
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_roi_delta
        == 0.02
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_profit_loss_delta
        == 0.03
    )
    assert (
        options.gate_options.max_global_planner_short_odds_adapter_runtime_harm_count_vs_original
        == 1
    )
    assert (
        options.gate_options.max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original
        == 2
    )
    assert (
        options.gate_options.max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original
        == 3
    )
    assert (
        options.gate_options.min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta
        == -0.03
    )
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_runtime_public_unchanged
        is False
    )
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_runtime_production_unchanged
        is False
    )
    assert (
        options.gate_options.global_planner_short_odds_adapter_sample_expansion_report_path
        is not None
    )
    assert str(
        options.gate_options.global_planner_short_odds_adapter_sample_expansion_report_path
    ).endswith("sample_expansion.json")
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_sample_expansion
        is True
    )
    assert (
        options.gate_options.require_global_planner_short_odds_adapter_sample_expansion_promotion_ready
        is True
    )
    assert (
        options.gate_options.probability_calibration_profile_rolling_admission_report_path
        is not None
    )
    assert str(
        options.gate_options.probability_calibration_profile_rolling_admission_report_path
    ).endswith("probability_calibration_admission.json")
    assert (
        options.gate_options.require_probability_calibration_profile_rolling_admission
        is True
    )
    assert (
        options.gate_options.require_probability_calibration_profile_candidate_allowed
        is False
    )
    assert (
        options.gate_options.require_probability_calibration_profile_active_profile
        is False
    )
    assert (
        options.gate_options.min_probability_calibration_profile_overall_adjusted_fixture_count
        == 24
    )
    assert (
        options.gate_options.min_probability_calibration_profile_overall_bucket_count
        == 3
    )
    assert (
        options.gate_options.max_probability_calibration_profile_failed_fold_count
        == 1
    )
    assert (
        options.gate_options.min_probability_calibration_profile_active_competition_fold_count
        == 2
    )
    assert (
        options.gate_options.min_probability_calibration_profile_active_season_cutoff_fold_count
        == 3
    )
    assert (
        options.gate_options.min_probability_calibration_profile_active_rolling_fold_count
        == 4
    )
    assert (
        options.gate_options.probability_calibration_profile_model_quality_gate_report_path
        is not None
    )
    assert str(
        options.gate_options.probability_calibration_profile_model_quality_gate_report_path
    ).endswith("probability_model_quality_gate.json")
    assert (
        options.gate_options.require_probability_calibration_profile_model_quality_gate
        is True
    )
    assert (
        options.gate_options.require_probability_calibration_profile_model_quality_ready
        is False
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_selected_competition_count
        == 4
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_adjusted_slice_count
        == 4
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_adjusted_fixture_count
        == 96
    )
    assert (
        options.gate_options.max_probability_calibration_profile_model_quality_skipped_fixture_count
        == 2
    )
    assert (
        options.gate_options.max_probability_calibration_profile_model_quality_final_answer_changed_count
        == 1
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_final_answer_hit_count_delta
        == 1
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta
        == 0.01
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_roi_delta
        == 0.02
    )
    assert (
        options.gate_options.min_probability_calibration_profile_model_quality_profit_loss_delta
        == 1.0
    )
    assert (
        options.gate_options.max_probability_calibration_profile_model_quality_brier_score_delta
        == 0.01
    )
    assert (
        options.gate_options.max_probability_calibration_profile_model_quality_log_loss_delta
        == 0.02
    )
    assert (
        options.gate_options.max_probability_calibration_profile_model_quality_calibration_error_delta
        == 0.03
    )
    assert (
        options.gate_options.asian_handicap_segmented_model_quality_governance_report_path
        is not None
    )
    assert str(
        options.gate_options.asian_handicap_segmented_model_quality_governance_report_path
    ).endswith("asian_handicap_governance.json")
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_governance
        is True
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_ready
        is False
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_internal_only
        is False
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_default_path_isolated
        is False
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_no_production_change
        is False
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_no_public_response_change
        is False
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_accepted_segment_count
        == 3
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_shadow_segment_count
        == 0
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_fallback_segment_count
        == 2
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_rejected_segment_count
        == 0
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_accepted_validation_count
        == 100
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_calibration_applied_count
        == 2
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_hit_rate_delta
        == 0.0
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_brier_score_delta
        == 0.01
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_log_loss_delta
        == 0.02
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_calibration_error_delta
        == 0.03
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_actual_probability_delta
        == -0.01
    )
    assert (
        options.gate_options.prematch_feature_quality_cycle_report_path
        is not None
    )
    assert str(
        options.gate_options.prematch_feature_quality_cycle_report_path
    ).endswith("prematch_feature_quality_cycle.json")
    assert options.gate_options.require_prematch_feature_quality_cycle is True
    assert (
        options.gate_options.require_prematch_feature_quality_cycle_passed
        is False
    )
    assert (
        options.gate_options.require_prematch_feature_quality_cycle_best_gate_passed
        is False
    )
    assert options.gate_options.min_prematch_feature_quality_cycle_slice_count == 25
    assert options.gate_options.min_prematch_feature_quality_cycle_fixture_count == 600
    assert (
        options.gate_options.min_prematch_feature_quality_cycle_evaluated_candidate_count
        == 5
    )
    assert (
        options.gate_options.min_prematch_feature_quality_cycle_passing_candidate_count
        == 1
    )
    assert options.gate_options.max_prematch_feature_quality_cycle_warning_count == 2
    assert (
        options.gate_options.max_prematch_feature_quality_cycle_best_brier_score_delta
        == 0.01
    )
    assert (
        options.gate_options.max_prematch_feature_quality_cycle_best_log_loss_delta
        == 0.02
    )
    assert (
        options.gate_options.max_prematch_feature_quality_cycle_best_calibration_error_delta
        == 0.03
    )
    assert (
        options.gate_options.prematch_feature_rolling_admission_report_path
        is not None
    )
    assert str(
        options.gate_options.prematch_feature_rolling_admission_report_path
    ).endswith("prematch_feature_rolling_admission.json")
    assert options.gate_options.require_prematch_feature_rolling_admission is True
    assert (
        options.gate_options.require_prematch_feature_rolling_admission_candidate_allowed
        is False
    )
    assert (
        options.gate_options.min_prematch_feature_rolling_admission_overall_evaluated_candidate_count
        == 5
    )
    assert (
        options.gate_options.min_prematch_feature_rolling_admission_overall_passing_candidate_count
        == 1
    )
    assert (
        options.gate_options.max_prematch_feature_rolling_admission_failed_fold_count
        == 1
    )
    assert (
        options.gate_options.min_prematch_feature_rolling_admission_active_competition_fold_count
        == 2
    )
    assert (
        options.gate_options.min_prematch_feature_rolling_admission_active_season_cutoff_fold_count
        == 3
    )
    assert (
        options.gate_options.min_prematch_feature_rolling_admission_active_rolling_fold_count
        == 4
    )
    assert (
        options.gate_options.max_prematch_feature_rolling_admission_overall_brier_score_delta
        == 0.01
    )
    assert (
        options.gate_options.max_prematch_feature_rolling_admission_overall_log_loss_delta
        == 0.02
    )
    assert (
        options.gate_options.max_prematch_feature_rolling_admission_overall_calibration_error_delta
        == 0.03
    )
    assert (
        options.gate_options.prematch_feature_sample_readiness_report_path
        is not None
    )
    assert str(
        options.gate_options.prematch_feature_sample_readiness_report_path
    ).endswith("prematch_feature_sample_readiness.json")
    assert options.gate_options.require_prematch_feature_sample_readiness is True
    assert options.gate_options.require_prematch_feature_sample_ready_allowed is False
    assert options.gate_options.min_prematch_feature_sample_ready_source_count == 2
    assert options.gate_options.min_prematch_feature_sample_ready_fixture_count == 600
    assert (
        options.gate_options.min_prematch_feature_sample_ready_competition_count
        == 3
    )
    assert options.gate_options.min_prematch_feature_sample_ready_season_count == 2
    assert (
        options.gate_options.min_prematch_feature_sample_ready_competition_season_count
        == 5
    )
    assert options.gate_options.max_prematch_feature_sample_readiness_warning_count == 4
    assert options.gate_options.fail_on_history_statuses == ("regressed", "mixed")


def test_cycle_cli_final_answer_market_concentration_args_map_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-final-answer-market-concentration-audit-report-path",
            "configs/recommendations/historical_reports/final_answer_market.json",
            "--gate-require-final-answer-market-concentration-audit",
            "--gate-min-final-answer-market-concentration-slice-count",
            "5",
            "--gate-min-final-answer-market-concentration-dynamic-mixed-final-answer-count",
            "5",
            "--gate-min-final-answer-market-concentration-effective-constraint-profile-count",
            "2",
            "--gate-max-final-answer-market-concentration-failed-check-count",
            "0",
            "--gate-max-final-answer-market-concentration-warning-count",
            "0",
        ]
    )

    options = _options_from_args(args)
    gate_options = options.gate_options

    assert gate_options.final_answer_market_concentration_audit_report_path is not None
    assert str(
        gate_options.final_answer_market_concentration_audit_report_path
    ).endswith("final_answer_market.json")
    assert gate_options.require_final_answer_market_concentration_audit is True
    assert gate_options.min_final_answer_market_concentration_slice_count == 5
    assert (
        gate_options.min_final_answer_market_concentration_dynamic_mixed_final_answer_count
        == 5
    )
    assert (
        gate_options.min_final_answer_market_concentration_effective_constraint_profile_count
        == 2
    )
    assert gate_options.max_final_answer_market_concentration_failed_check_count == 0
    assert gate_options.max_final_answer_market_concentration_warning_count == 0


def test_cycle_cli_correct_score_admission_args_map_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-correct-score-admission-report-path",
            "configs/recommendations/historical_reports/correct_score_admission.json",
            "--gate-require-correct-score-admission",
            "--gate-allow-correct-score-admission-holdout-not-allowed",
            "--gate-require-correct-score-admission-production-allowed",
            "--gate-min-correct-score-admission-slice-count",
            "10",
            "--gate-min-correct-score-admission-comparison-count",
            "11",
            "--gate-min-correct-score-admission-candidate-final-hit-sample-size",
            "12",
            "--gate-min-correct-score-admission-candidate-final-hit-coverage-ratio",
            "0.9",
            "--gate-min-correct-score-admission-candidate-final-hit-rate",
            "0.55",
            "--gate-min-correct-score-admission-candidate-roi",
            "0.01",
            "--gate-min-correct-score-admission-candidate-correct-score-final-answer-count",
            "3",
            "--gate-min-correct-score-admission-candidate-correct-score-final-answer-rate",
            "0.03",
            "--gate-min-correct-score-admission-final-hit-rate-delta",
            "0.001",
            "--gate-min-correct-score-admission-roi-delta",
            "0.002",
            "--gate-min-correct-score-admission-profit-loss-delta",
            "0.003",
            "--gate-max-correct-score-admission-brier-score-delta",
            "0.004",
            "--gate-max-correct-score-admission-log-loss-delta",
            "0.005",
            "--gate-max-correct-score-admission-mean-calibration-error-delta",
            "0.006",
            "--gate-max-correct-score-admission-failed-check-count",
            "1",
            "--gate-max-correct-score-admission-warning-count",
            "2",
        ]
    )

    options = _options_from_args(args)
    gate_options = options.gate_options

    assert gate_options.correct_score_admission_report_path is not None
    assert str(gate_options.correct_score_admission_report_path).endswith(
        "correct_score_admission.json"
    )
    assert gate_options.require_correct_score_admission is True
    assert gate_options.require_correct_score_admission_holdout_allowed is False
    assert gate_options.require_correct_score_admission_production_allowed is True
    assert gate_options.min_correct_score_admission_slice_count == 10
    assert gate_options.min_correct_score_admission_comparison_count == 11
    assert gate_options.min_correct_score_admission_candidate_final_hit_sample_size == 12
    assert (
        gate_options.min_correct_score_admission_candidate_final_hit_coverage_ratio
        == 0.9
    )
    assert gate_options.min_correct_score_admission_candidate_final_hit_rate == 0.55
    assert gate_options.min_correct_score_admission_candidate_roi == 0.01
    assert (
        gate_options.min_correct_score_admission_candidate_correct_score_final_answer_count
        == 3
    )
    assert (
        gate_options.min_correct_score_admission_candidate_correct_score_final_answer_rate
        == 0.03
    )
    assert gate_options.min_correct_score_admission_final_hit_rate_delta == 0.001
    assert gate_options.min_correct_score_admission_roi_delta == 0.002
    assert gate_options.min_correct_score_admission_profit_loss_delta == 0.003
    assert gate_options.max_correct_score_admission_brier_score_delta == 0.004
    assert gate_options.max_correct_score_admission_log_loss_delta == 0.005
    assert gate_options.max_correct_score_admission_mean_calibration_error_delta == 0.006
    assert gate_options.max_correct_score_admission_failed_check_count == 1
    assert gate_options.max_correct_score_admission_warning_count == 2


def test_cycle_cli_unified_candidate_pool_args_map_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-require-unified-candidate-pool",
            "--gate-min-unified-candidate-pool-present-count",
            "12",
            "--gate-min-unified-candidate-pool-valid-candidate-count",
            "24",
            "--gate-min-unified-candidate-pool-unique-family-count",
            "4",
            "--gate-max-unified-candidate-pool-selection-mismatch-count",
            "0",
            "--gate-max-unified-candidate-pool-selected-2x1-rate",
            "0.6",
            "--gate-require-unified-candidate-pool-multiple-value-admission",
            "--gate-min-unified-candidate-pool-multiple-value-candidate-count",
            "4",
            "--gate-min-unified-candidate-pool-multiple-value-admitted-candidate-count",
            "3",
            "--gate-min-unified-candidate-pool-multiple-value-extra-option-count",
            "8",
            "--gate-max-unified-candidate-pool-multiple-value-rejected-candidate-count",
            "1",
            "--gate-max-unified-candidate-pool-selected-multiple-value-rejected-count",
            "0",
        ]
    )

    gate_options = _options_from_args(args).gate_options

    assert gate_options.require_unified_candidate_pool is True
    assert gate_options.min_unified_candidate_pool_present_count == 12
    assert gate_options.min_unified_candidate_pool_valid_candidate_count == 24
    assert gate_options.min_unified_candidate_pool_unique_family_count == 4
    assert gate_options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert gate_options.max_unified_candidate_pool_selected_2x1_rate == 0.6
    assert gate_options.require_unified_candidate_pool_multiple_value_admission is True
    assert gate_options.min_unified_candidate_pool_multiple_value_candidate_count == 4
    assert (
        gate_options.min_unified_candidate_pool_multiple_value_admitted_candidate_count
        == 3
    )
    assert gate_options.min_unified_candidate_pool_multiple_value_extra_option_count == 8
    assert (
        gate_options.max_unified_candidate_pool_multiple_value_rejected_candidate_count
        == 1
    )
    assert (
        gate_options.max_unified_candidate_pool_selected_multiple_value_rejected_count
        == 0
    )


def test_cycle_cli_unified_candidate_pool_guard_preset_maps_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-unified-candidate-pool-guard-preset",
            UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
        ]
    )

    gate_options = _options_from_args(args).gate_options

    assert (
        gate_options.unified_candidate_pool_guard_preset
        == UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
    )
    assert gate_options.require_unified_candidate_pool is True
    assert gate_options.min_unified_candidate_pool_present_count == 1
    assert gate_options.min_unified_candidate_pool_valid_candidate_count == 1
    assert gate_options.min_unified_candidate_pool_unique_family_count == 2
    assert gate_options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert gate_options.max_unified_candidate_pool_selected_2x1_rate == 0.80
    assert (
        gate_options.max_unified_candidate_pool_selected_multiple_value_rejected_count
        == 0
    )
    assert (
        gate_options.max_unified_candidate_pool_selected_multiple_value_rejected_count
        == 0
    )


def test_cycle_cli_runtime_profile_switch_preset_maps_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-runtime-profile-switch-preset",
            RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1,
        ]
    )

    options = _options_from_args(args)
    gate_options = options.gate_options

    assert (
        gate_options.runtime_profile_switch_preset
        == RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1
    )
    assert gate_options.runtime_profile_switch_report_path is not None
    assert str(gate_options.runtime_profile_switch_report_path).endswith(
        "runtime_profile_switch_v1.json"
    )
    assert gate_options.runtime_profile_switch_replay_report_path is not None
    assert str(gate_options.runtime_profile_switch_replay_report_path).endswith(
        "runtime_shadow_replay_switch_staged_v1.json"
    )
    assert gate_options.require_runtime_profile_switch_gate is True
    assert gate_options.require_runtime_profile_switch_replay is True
    assert gate_options.require_runtime_profile_switch_staged_only is True
    assert gate_options.min_runtime_profile_switch_rule_count == 1
    assert gate_options.min_runtime_profile_switch_allowed_competition_count == 4
    assert gate_options.min_runtime_profile_switch_final_answer_count == 30
    assert gate_options.min_runtime_profile_switch_changed_final_answer_count == 5
    assert gate_options.min_runtime_profile_switch_roi_delta == 0.0
    assert gate_options.max_runtime_profile_switch_harm_count_vs_original == 0
    assert gate_options.max_runtime_profile_switch_final_hit_harm_count_vs_original == 0
    assert gate_options.max_runtime_profile_switch_profit_loss_harm_count_vs_original == 0


def test_cycle_cli_recommendation_strategy_governance_args_map_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-recommendation-strategy-promotion-gate-report-path",
            "configs/recommendations/historical_reports/strategy_gate.json",
            "--gate-require-recommendation-strategy-promotion-gate",
            "--gate-allow-recommendation-strategy-gate-not-ready",
            "--gate-min-recommendation-strategy-gate-final-answer-count",
            "99",
            "--gate-min-recommendation-strategy-gate-changed-final-answer-count",
            "13",
            "--gate-min-recommendation-strategy-gate-hit-delta-count",
            "4",
            "--gate-min-recommendation-strategy-gate-profit-loss-delta",
            "15.7",
            "--gate-min-recommendation-strategy-gate-minimum-roi-delta",
            "0.04",
            "--gate-max-recommendation-strategy-gate-harm-count",
            "1",
            "--gate-max-recommendation-strategy-gate-final-hit-harm-count",
            "2",
            "--gate-max-recommendation-strategy-gate-profit-loss-harm-count",
            "3",
            "--gate-allow-recommendation-strategy-gate-production-change",
            "--gate-allow-recommendation-strategy-gate-public-change",
            "--gate-recommendation-strategy-staged-activation-smoke-report-path",
            "configs/recommendations/historical_reports/staged_smoke.json",
            "--gate-require-recommendation-strategy-staged-activation-smoke",
            "--gate-allow-recommendation-strategy-staged-activation-not-ready",
            "--gate-allow-recommendation-strategy-staged-default-write",
            "--gate-allow-recommendation-strategy-staged-production-change",
            "--gate-allow-recommendation-strategy-staged-public-change",
            "--gate-min-recommendation-strategy-staged-rule-count",
            "2",
            "--gate-min-recommendation-strategy-staged-allowed-competition-count",
            "5",
            "--gate-recommendation-strategy-default-path-isolation-report-path",
            "configs/recommendations/historical_reports/isolation.json",
            "--gate-require-recommendation-strategy-default-path-isolation",
            "--gate-allow-recommendation-strategy-default-path-not-isolated",
            "--gate-allow-recommendation-strategy-default-adapter-enabled",
            "--gate-allow-recommendation-strategy-default-adapter-change",
            "--gate-allow-recommendation-strategy-missing-explicit-opt-in",
            "--gate-allow-recommendation-strategy-isolation-default-write",
            "--gate-allow-recommendation-strategy-isolation-production-change",
            "--gate-allow-recommendation-strategy-isolation-public-change",
        ]
    )

    gate_options = _options_from_args(args).gate_options

    assert gate_options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(gate_options.recommendation_strategy_promotion_gate_report_path).endswith(
        "strategy_gate.json"
    )
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_gate_ready is False
    assert gate_options.min_recommendation_strategy_gate_final_answer_count == 99
    assert gate_options.min_recommendation_strategy_gate_changed_final_answer_count == 13
    assert gate_options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert gate_options.min_recommendation_strategy_gate_profit_loss_delta == 15.7
    assert gate_options.min_recommendation_strategy_gate_minimum_roi_delta == 0.04
    assert gate_options.max_recommendation_strategy_gate_harm_count == 1
    assert gate_options.max_recommendation_strategy_gate_final_hit_harm_count == 2
    assert gate_options.max_recommendation_strategy_gate_profit_loss_harm_count == 3
    assert gate_options.require_recommendation_strategy_gate_no_production_change is False
    assert gate_options.require_recommendation_strategy_gate_no_public_response_change is False
    assert (
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
        is not None
    )
    assert str(
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith("staged_smoke.json")
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_staged_activation_ready is False
    assert gate_options.require_recommendation_strategy_staged_no_default_write is False
    assert gate_options.require_recommendation_strategy_staged_no_production_change is False
    assert gate_options.require_recommendation_strategy_staged_no_public_response_change is False
    assert gate_options.min_recommendation_strategy_staged_rule_count == 2
    assert gate_options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert gate_options.recommendation_strategy_default_path_isolation_report_path is not None
    assert str(
        gate_options.recommendation_strategy_default_path_isolation_report_path
    ).endswith("isolation.json")
    assert gate_options.require_recommendation_strategy_default_path_isolation is True
    assert gate_options.require_recommendation_strategy_default_path_isolated is False
    assert gate_options.require_recommendation_strategy_default_adapter_disabled is False
    assert gate_options.require_recommendation_strategy_default_adapter_unchanged is False
    assert gate_options.require_recommendation_strategy_explicit_opt_in_applied is False
    assert gate_options.require_recommendation_strategy_isolation_no_default_write is False
    assert gate_options.require_recommendation_strategy_isolation_no_production_change is False
    assert gate_options.require_recommendation_strategy_isolation_no_public_response_change is False


def test_cycle_cli_recommendation_strategy_governance_preset_maps_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-recommendation-strategy-governance-preset",
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
        ]
    )

    gate_options = _options_from_args(args).gate_options

    assert (
        gate_options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
    )
    assert gate_options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(gate_options.recommendation_strategy_promotion_gate_report_path).endswith(
        "probability_preserving_adjacent_threshold_13plus_strategy_promotion_gate_v1.json"
    )
    assert (
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
        is not None
    )
    assert str(
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith(
        "probability_preserving_adjacent_threshold_13plus_staged_activation_smoke_v1.json"
    )
    assert (
        gate_options.recommendation_strategy_default_path_isolation_report_path
        is not None
    )
    assert str(
        gate_options.recommendation_strategy_default_path_isolation_report_path
    ).endswith(
        "probability_preserving_adjacent_threshold_13plus_default_path_isolation_v1.json"
    )
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_default_path_isolation is True
    assert gate_options.min_recommendation_strategy_gate_changed_final_answer_count == 13
    assert gate_options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert gate_options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert gate_options.require_recommendation_strategy_default_adapter_disabled is True
    assert gate_options.require_recommendation_strategy_default_adapter_unchanged is True


def test_cycle_cli_quality_score_strategy_preset_maps_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-recommendation-strategy-governance-preset",
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
        ]
    )

    gate_options = _options_from_args(args).gate_options

    assert (
        gate_options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1
    )
    assert gate_options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(gate_options.recommendation_strategy_promotion_gate_report_path).endswith(
        "probability_preserving_quality_score_strategy_promotion_gate_v1.json"
    )
    assert (
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
        is not None
    )
    assert str(
        gate_options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith("probability_preserving_quality_score_staged_activation_smoke_v1.json")
    assert (
        gate_options.recommendation_strategy_default_path_isolation_report_path
        is not None
    )
    assert str(
        gate_options.recommendation_strategy_default_path_isolation_report_path
    ).endswith("probability_preserving_quality_score_default_path_isolation_v1.json")
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_default_path_isolation is True
    assert gate_options.min_recommendation_strategy_gate_final_answer_count == 99
    assert gate_options.min_recommendation_strategy_gate_changed_final_answer_count == 14
    assert gate_options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert gate_options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert gate_options.require_recommendation_strategy_default_adapter_disabled is True
    assert gate_options.require_recommendation_strategy_default_adapter_unchanged is True


def test_cycle_cli_strategy_governance_cycle_preset_maps_shadow_options() -> None:
    args = _parse_args(
        [
            "--cycle-preset",
            RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1,
            "--output-path",
            "configs/recommendations/historical_reports/cycle_smoke.json",
            "--skip-gate",
            "--commit",
            "--skip-core-replay",
            "--skip-chain-integrity",
            "--skip-successor-chain-evaluation",
        ]
    )

    options = _options_from_args(args)
    schedule_options = options.schedule_options
    gate_options = options.gate_options

    assert options.cycle_preset == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1
    )
    assert args.output_path == Path(
        "configs/recommendations/historical_reports/cycle_smoke.json"
    )
    assert options.run_gate is True
    assert schedule_options.schedule_name == "probability-preserving-13change-governance"
    assert schedule_options.cadence == "once"
    assert schedule_options.dry_run is True
    assert schedule_options.run_core_replay is True
    assert schedule_options.run_chain_integrity is True
    assert schedule_options.run_successor_chain_evaluation is True
    assert schedule_options.run_prematch_pipeline is False
    assert (
        gate_options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
    )
    assert gate_options.min_global_best_selected_count == 1
    assert gate_options.min_global_best_candidate_count == 1
    assert gate_options.min_global_best_generated_option_count == 1
    assert gate_options.min_core_replay_ready_ratio == 1.0
    assert gate_options.min_final_hit_sample_size == 1
    assert gate_options.min_final_hit_coverage_ratio == 1.0
    assert gate_options.historical_suite_quality_gate_report_path == (
        CORE_PLUS_EXPANDED_A_LEAGUES_SUCCESSOR_EFFECTIVE_FINAL_ONLY_HISTORICAL_GATE_REPORT_PATH
    )
    assert gate_options.require_historical_suite_quality_gate is True
    assert gate_options.require_historical_suite_lifecycle_evidence is False
    assert gate_options.require_historical_suite_lifecycle_source_status_synced is False
    assert gate_options.min_historical_suite_slice_count == 240
    assert gate_options.min_historical_suite_comparison_count == 240
    assert gate_options.min_historical_suite_candidate_final_hit_sample_size == 240
    assert gate_options.min_historical_suite_candidate_final_hit_coverage_ratio == 1.0
    assert gate_options.max_historical_suite_failed_check_count == 0
    assert gate_options.require_historical_suite_successor_chain_evaluation is True
    assert gate_options.min_historical_suite_successor_effective_leaf_count == 1
    assert gate_options.min_historical_suite_successor_active_edge_count == 1
    assert gate_options.max_historical_suite_successor_critical_issue_count == 0
    assert gate_options.max_historical_suite_successor_ambiguous_source_count == 0
    assert (
        gate_options.max_historical_suite_successor_source_status_sync_required_count
        == 0
    )
    assert gate_options.budget_stability_audit_report_path == (
        CORE_PLUS_EXPANDED_A_LEAGUES_BUDGET_STABILITY_AUDIT_REPORT_PATH
    )
    assert gate_options.require_budget_stability_audit is True
    assert gate_options.min_budget_stability_slice_count == 240
    assert gate_options.min_budget_stability_comparable_count == 240
    assert gate_options.max_budget_stability_signature_change_rate == 0.0
    assert gate_options.max_budget_stability_harmful_change_count == 0
    assert gate_options.min_budget_stability_hit_delta_count == 0
    assert gate_options.min_budget_stability_profit_loss_delta == 0.0
    assert gate_options.min_budget_stability_roi_delta == 0.0
    assert gate_options.max_budget_stability_warning_count == 0
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_default_path_isolation is True


def test_cycle_cli_quality_score_governance_cycle_preset_maps_shadow_options() -> None:
    args = _parse_args(
        [
            "--cycle-preset",
            RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1,
            "--skip-gate",
            "--commit",
            "--skip-core-replay",
            "--skip-chain-integrity",
            "--skip-successor-chain-evaluation",
        ]
    )

    options = _options_from_args(args)
    schedule_options = options.schedule_options
    gate_options = options.gate_options

    assert options.cycle_preset == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_GOVERNANCE_V1
    )
    assert options.run_gate is True
    assert schedule_options.schedule_name == (
        "probability-preserving-quality-score-governance"
    )
    assert schedule_options.cadence == "once"
    assert schedule_options.dry_run is True
    assert schedule_options.run_core_replay is True
    assert schedule_options.run_chain_integrity is True
    assert schedule_options.run_successor_chain_evaluation is True
    assert (
        gate_options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1
    )
    assert gate_options.min_recommendation_strategy_gate_final_answer_count == 99
    assert gate_options.min_recommendation_strategy_gate_changed_final_answer_count == 14
    assert gate_options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert gate_options.require_historical_suite_quality_gate is True
    assert gate_options.require_budget_stability_audit is True
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_default_path_isolation is True


def test_cycle_cli_core_accuracy_governance_preset_maps_combined_gate_options() -> None:
    args = _parse_args(
        [
            "--cycle-preset",
            RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1,
            "--skip-gate",
            "--commit",
            "--skip-core-replay",
            "--skip-chain-integrity",
            "--skip-successor-chain-evaluation",
        ]
    )

    options = _options_from_args(args)
    schedule_options = options.schedule_options
    gate_options = options.gate_options

    assert options.cycle_preset == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1
    )
    assert options.run_gate is True
    assert schedule_options.schedule_name == "v3-2-core-accuracy-governance"
    assert schedule_options.cadence == "once"
    assert schedule_options.dry_run is True
    assert schedule_options.run_global_best is True
    assert schedule_options.run_core_replay is True
    assert schedule_options.run_chain_integrity is True
    assert schedule_options.run_successor_chain_evaluation is True
    assert (
        gate_options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
    )
    assert gate_options.require_recommendation_strategy_promotion_gate is True
    assert gate_options.require_recommendation_strategy_staged_activation_smoke is True
    assert gate_options.require_recommendation_strategy_default_path_isolation is True
    assert gate_options.require_budget_stability_audit is True
    assert gate_options.historical_suite_quality_gate_report_path == (
        CORE_PLUS_EXPANDED_A_LEAGUES_SUCCESSOR_EFFECTIVE_FINAL_ONLY_HISTORICAL_GATE_REPORT_PATH
    )
    assert gate_options.budget_stability_audit_report_path == (
        CORE_PLUS_EXPANDED_A_LEAGUES_BUDGET_STABILITY_AUDIT_REPORT_PATH
    )
    assert gate_options.final_answer_market_concentration_audit_report_path == (
        CORE_PLUS_EXPANDED_A_LEAGUES_DYNAMIC_MIX_CONSTRAINT_RUNTIME_SMOKE_REPORT_PATH
    )
    assert gate_options.require_final_answer_market_concentration_audit is True
    assert gate_options.min_final_answer_market_concentration_slice_count == 5
    assert (
        gate_options.min_final_answer_market_concentration_dynamic_mixed_final_answer_count
        == 5
    )
    assert (
        gate_options.min_final_answer_market_concentration_effective_constraint_profile_count
        == 2
    )
    assert gate_options.max_final_answer_market_concentration_failed_check_count == 0
    assert gate_options.max_final_answer_market_concentration_warning_count == 0
    assert (
        gate_options.require_market_movement_runtime_activation_sample_expansion
        is True
    )
    assert (
        gate_options.require_market_movement_runtime_activation_sample_expansion_promotion_ready
        is True
    )
    assert (
        gate_options.market_movement_runtime_activation_sample_expansion_report_path
        is not None
    )
    assert str(
        gate_options.market_movement_runtime_activation_sample_expansion_report_path
    ).endswith("sample_expansion_segment_replay_ready_v1.json")
    assert (
        gate_options.require_market_movement_runtime_activation_segment_replay_batch_gate
        is True
    )
    assert (
        gate_options.require_market_movement_runtime_activation_segment_replay_batch_ready
        is True
    )
    assert (
        gate_options.require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
        is True
    )
    assert (
        gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        is not None
    )
    assert str(
        gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
    ).endswith("segment_replay_batch_gate_sample_ready_v1.json")
    assert (
        gate_options.min_market_movement_runtime_activation_segment_replay_batch_report_count
        == 4
    )
    assert (
        gate_options.min_market_movement_runtime_activation_segment_replay_batch_passed_count
        == 4
    )
    assert (
        gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
        == 1200
    )
    assert (
        gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
        == 3600
    )


def test_cycle_cli_unified_candidate_pool_cycle_preset_maps_guard_options() -> None:
    args = _parse_args(
        [
            "--cycle-preset",
            RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1,
            "--skip-gate",
            "--commit",
            "--skip-global-best",
            "--skip-core-replay",
            "--skip-chain-integrity",
            "--skip-successor-chain-evaluation",
        ]
    )

    options = _options_from_args(args)
    schedule_options = options.schedule_options
    gate_options = options.gate_options

    assert options.cycle_preset == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_UNIFIED_CANDIDATE_POOL_GUARD_V1
    )
    assert options.run_gate is True
    assert schedule_options.schedule_name == "v3-2-unified-candidate-pool-guard"
    assert schedule_options.cadence == "once"
    assert schedule_options.pass_types == (
        "1x1",
        "2x1",
        "3x1",
        "4x1",
        "5x1",
        "6x1",
        "7x1",
        "8x1",
    )
    assert schedule_options.run_global_best is True
    assert schedule_options.run_core_replay is False
    assert schedule_options.run_chain_integrity is False
    assert schedule_options.run_successor_chain_evaluation is False
    assert schedule_options.run_prematch_pipeline is False
    assert schedule_options.dry_run is True
    assert schedule_options.save_report is True
    assert (
        gate_options.unified_candidate_pool_guard_preset
        == UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
    )
    assert gate_options.require_unified_candidate_pool is True
    assert gate_options.min_global_best_selected_count == 1
    assert gate_options.min_global_best_candidate_count == 1
    assert gate_options.min_global_best_generated_option_count == 1
    assert gate_options.min_unified_candidate_pool_unique_family_count == 2
    assert gate_options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert gate_options.max_unified_candidate_pool_selected_2x1_rate == 0.80


def test_cycle_cli_maps_core_replay_seed_options() -> None:
    args = _parse_args(
        [
            "--commit-core-replay-seed",
            "--core-replay-seed-profile",
            "mixed_outcomes",
            "--no-core-replay-seed-reset",
        ]
    )

    options = _options_from_args(args)

    assert options.commit_core_replay_seed is True
    assert options.core_replay_seed_profile == "mixed_outcomes"
    assert options.core_replay_seed_reset is False


def test_strategy_governance_cycle_preset_preserves_explicit_schedule_name() -> None:
    options = apply_recommendation_benchmark_cycle_preset(
        RecommendationBenchmarkCycleOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="manual-shadow",
                cadence="weekly",
            ),
            run_gate=False,
        ),
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_PROBABILITY_PRESERVING_13CHANGE_GOVERNANCE_V1,
    )

    assert options.schedule_options.schedule_name == "manual-shadow"
    assert options.schedule_options.cadence == "weekly"
    assert options.run_gate is True
    assert options.schedule_options.dry_run is True


def test_market_movement_segment_replay_batch_cycle_preset_maps_gate_options() -> None:
    options = apply_recommendation_benchmark_cycle_preset(
        RecommendationBenchmarkCycleOptions(),
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1,
    )

    assert options.cycle_preset == (
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_MARKET_MOVEMENT_SEGMENT_REPLAY_BATCH_GATE_V1
    )
    assert options.run_gate is True
    assert options.schedule_options.schedule_name == (
        "v3-2-market-movement-segment-replay-batch-gate"
    )
    assert options.schedule_options.cadence == "once"
    assert options.schedule_options.run_global_best is True
    assert options.schedule_options.run_core_replay is False
    assert (
        options.gate_options.market_movement_runtime_activation_sample_expansion_report_path
        is not None
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_sample_expansion
        is True
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_sample_expansion_promotion_ready
        is False
    )
    assert (
        options.gate_options.market_movement_runtime_activation_segment_replay_batch_gate_report_path
        is not None
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_gate
        is True
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_ready
        is True
    )
    assert (
        options.gate_options.require_market_movement_runtime_activation_segment_replay_batch_promotion_ready
        is False
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_report_count
        == 4
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_passed_count
        == 4
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count
        == 1200
    )
    assert (
        options.gate_options.min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count
        == 3600
    )


def test_core_accuracy_governance_cycle_preset_requires_asian_handicap_governance() -> None:
    options = apply_recommendation_benchmark_cycle_preset(
        RecommendationBenchmarkCycleOptions(),
        RECOMMENDATION_BENCHMARK_CYCLE_PRESET_V3_2_CORE_ACCURACY_GOVERNANCE_V1,
    )

    assert (
        options.gate_options.asian_handicap_segmented_model_quality_governance_report_path
        is not None
    )
    assert str(
        options.gate_options.asian_handicap_segmented_model_quality_governance_report_path
    ).endswith(
        "football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_governance_review_v1.json"
    )
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_governance
        is True
    )
    assert options.gate_options.require_asian_handicap_segmented_model_quality_ready
    assert (
        options.gate_options.require_asian_handicap_segmented_model_quality_internal_only
        is True
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_accepted_segment_count
        == 3
    )
    assert (
        options.gate_options.max_asian_handicap_segmented_model_quality_fallback_segment_count
        == 2
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_accepted_validation_count
        == 100
    )
    assert (
        options.gate_options.min_asian_handicap_segmented_model_quality_calibration_applied_count
        == 2
    )


def test_cycle_cli_segment_penalty_runtime_replay_preset_maps_gate_options() -> None:
    args = _parse_args(
        [
            "--gate-final-answer-segment-penalty-runtime-replay-preset",
            FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1,
        ]
    )

    options = _options_from_args(args)
    gate_options = options.gate_options

    assert (
        gate_options.final_answer_segment_penalty_runtime_replay_preset
        == FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
    )
    assert gate_options.final_answer_segment_penalty_runtime_replay_report_path is not None
    assert str(
        gate_options.final_answer_segment_penalty_runtime_replay_report_path
    ).endswith(
        "final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_replay_v1.json"
    )
    assert gate_options.require_final_answer_segment_penalty_runtime_replay is True
    assert (
        gate_options.require_final_answer_segment_penalty_runtime_replay_holdout_allowed
        is True
    )
    assert (
        gate_options.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        is False
    )
    assert gate_options.min_final_answer_segment_penalty_runtime_replay_rule_count == 1
    assert (
        gate_options.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        == 2
    )
    assert (
        gate_options.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        == 2
    )
    assert gate_options.min_final_answer_segment_penalty_runtime_replay_candidate_roi is None
    assert (
        gate_options.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        == 0
    )
    assert (
        gate_options.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        == 0
    )


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


class FakeCycleRunRepository:
    def __init__(self) -> None:
        self.saved: RecommendationBenchmarkCycleRunResult | None = None

    def list_history(
        self,
        *,
        cycle_key: str | None = None,
        benchmark_key: str | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkCycleRun]:
        raise AssertionError("unexpected list_history call")

    def save_run(
        self,
        result: RecommendationBenchmarkCycleRunResult,
        *,
        source: str = "recommendation_benchmark_cycle_v3_1",
    ) -> StoredRecommendationBenchmarkCycleRun:
        self.saved = result
        return _stored_cycle_run(
            recommendation_benchmark_cycle_run_id=401,
            cycle_key=result.cycle_key,
            summary_json=result.summary_json,
        )


class FakeCycleDatabase:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        return [
            _stored_cycle_row(
                recommendation_benchmark_cycle_run_id=401,
                cycle_key=str(params["cycle_key"]),
                summary_json=_gate_summary_with_historical_suite_evidence(),
            )
        ]

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return _stored_cycle_row(
            recommendation_benchmark_cycle_run_id=402,
            cycle_key=str(params["cycle_key"]),
            summary_json=params["summary_json"],
        )


def _core_replay_seed_result(
    *,
    options: RecommendationBenchmarkCoreReplaySeedOptions,
    passed: bool = True,
    stored_run_count: int = 6,
    warnings: list[str] | None = None,
    calls: list[RecommendationBenchmarkCoreReplaySeedOptions] | None = None,
) -> RecommendationBenchmarkCoreReplaySeedResult:
    if calls is not None:
        calls.append(options)
    seed = RecommendationBaselineSeedResult(
        as_of_time_utc=options.normalized_as_of_time_utc,
        reset=options.reset_seed,
        profile=options.profile,
        competition_id=options.competition_id,
        fixture_count=8,
        fixture_ids=[f"bench_v3_{index:03d}" for index in range(1, 9)],
        odds_snapshot_count=24,
        result_count=8,
        summary_json={},
    )
    benchmark = RecommendationBenchmarkRunResult(
        benchmark_key="recommendation_benchmark:core_replay_seed",
        dry_run=False,
        strategy=options.strategy,
        scenario_count=stored_run_count,
        completed_count=stored_run_count,
        failed_count=0 if passed else 1,
        warnings=warnings or [],
        summary_json={},
    )
    return RecommendationBenchmarkCoreReplaySeedResult(
        passed=passed,
        as_of_time_utc=options.normalized_as_of_time_utc,
        profile=options.profile,
        reset_seed=options.reset_seed,
        seed_budget=options.seed_budget or options.max_budgets[0],
        seed=seed,
        benchmark=benchmark,
        stored_recommendation_run_ids=list(range(1, stored_run_count + 1)),
        expected_scenario_count=stored_run_count,
        stored_run_count=stored_run_count,
        warnings=warnings or [],
        summary_json={},
    )


def _schedule_result(
    *,
    options: RecommendationBenchmarkScheduleOptions,
    stored_report: bool,
    warnings: list[str] | None = None,
) -> RecommendationBenchmarkScheduleRunResult:
    benchmark = RecommendationBenchmarkRunResult(
        benchmark_key="recommendation_benchmark:cycle",
        dry_run=options.dry_run,
        strategy=options.strategy,
        scenario_count=6,
        completed_count=6,
        failed_count=0,
        warnings=warnings or [],
        summary_json={
            "scenario_count": 6,
            "completed_count": 6,
            "failed_count": 0,
        },
        stored_report=_stored_run() if stored_report else None,
    )
    return RecommendationBenchmarkScheduleRunResult(
        schedule_key="recommendation_benchmark_schedule:daily-core:daily",
        schedule_name=options.schedule_name,
        cadence=options.cadence,
        run_at_utc=options.normalized_run_at_utc,
        generated_as_of_times_utc=[options.normalized_run_at_utc],
        dry_run=options.dry_run,
        save_report=options.save_report,
        benchmark=benchmark,
        warnings=warnings or [],
        summary_json={"benchmark_key": benchmark.benchmark_key},
    )


def _gate_result(
    *,
    options: RecommendationBenchmarkQualityGateOptions,
    passed: bool,
    warnings: list[str] | None = None,
    calls: list[RecommendationBenchmarkQualityGateOptions] | None = None,
    summary_json: dict[str, object] | None = None,
) -> RecommendationBenchmarkQualityGateResult:
    if calls is not None:
        calls.append(options)
    return RecommendationBenchmarkQualityGateResult(
        gate_key=f"recommendation_benchmark_quality_gate:{options.benchmark_key}",
        status="passed" if passed else "failed",
        passed=passed,
        warnings=warnings or [],
        summary_json=summary_json or {"passed": passed},
    )


def _gate_summary_with_historical_suite_evidence() -> dict[str, object]:
    return {
        "passed": True,
        "failed_checks": [],
        "core_replay_ready_ratio": 1.0,
        "final_hit_sample_size": 27,
        "final_hit_coverage_ratio": 1.0,
        "final_hit_rate": 2 / 3,
        "average_core_replay_roi": 0.12,
        "historical_suite_quality_gate_present": True,
        "historical_suite_quality_gate_passed": True,
        "historical_suite_quality_gate_key": (
            "historical_recommendation_suite_quality_gate:core"
        ),
        "historical_suite_quality_gate_status": "passed",
        "historical_suite_quality_gate_suite_status": "unchanged",
        "historical_suite_slice_count": 30,
        "historical_suite_comparison_count": 30,
        "historical_suite_candidate_final_hit_sample_size": 30,
        "historical_suite_candidate_final_hit_coverage_ratio": 1.0,
        "historical_suite_candidate_final_hit_rate": 2 / 3,
        "historical_suite_candidate_roi": 0.12,
        "historical_suite_baseline_dynamic_mixed_final_answer_count": 5,
        "historical_suite_candidate_dynamic_mixed_final_answer_count": 6,
        "historical_suite_baseline_dynamic_mixed_final_answer_rate": 0.50,
        "historical_suite_candidate_dynamic_mixed_final_answer_rate": 0.60,
        "historical_suite_baseline_final_answer_market_type_counts": {
            "1x2": 10,
            "cn_handicap_1x2": 5,
        },
        "historical_suite_candidate_final_answer_market_type_counts": {
            "1x2": 10,
            "cn_handicap_1x2": 6,
        },
        "historical_suite_baseline_handicap_final_answer_count": 5,
        "historical_suite_candidate_handicap_final_answer_count": 6,
        "historical_suite_baseline_handicap_final_answer_rate": 0.50,
        "historical_suite_candidate_handicap_final_answer_rate": 0.60,
        "historical_suite_baseline_correct_score_final_answer_count": 1,
        "historical_suite_candidate_correct_score_final_answer_count": 2,
        "historical_suite_baseline_multiple_choice_final_answer_count": 2,
        "historical_suite_candidate_multiple_choice_final_answer_count": 3,
        "historical_suite_baseline_final_answer_selected_candidate_count": 20,
        "historical_suite_candidate_final_answer_selected_candidate_count": 25,
        "historical_suite_baseline_final_answer_multiple_choice_fixture_count": 3,
        "historical_suite_candidate_final_answer_multiple_choice_fixture_count": 4,
        "historical_suite_failed_check_count": 0,
        "historical_suite_lifecycle_quality_cycle_present": True,
        "historical_suite_lifecycle_quality_cycle_passed": True,
        "historical_suite_lifecycle_persisted_smoke_present": True,
        "historical_suite_lifecycle_persisted_smoke_passed": True,
        "historical_suite_lifecycle_source_status_synced": True,
        "historical_suite_lifecycle_effective_leaf_count": 1,
        "historical_suite_lifecycle_active_edge_count": 1,
        "historical_suite_lifecycle_critical_issue_count": 0,
        "historical_suite_lifecycle_source_status_sync_required_count": 0,
        "budget_stability_audit_present": True,
        "budget_stability_audit_key": "historical_budget_stability_audit:core",
        "budget_stability_audit_status": "generated",
        "budget_stability_slice_count": 240,
        "budget_stability_budgets": [10.0, 20.0],
        "budget_stability_reference_budget": 20.0,
        "budget_stability_comparable_count": 240,
        "budget_stability_signature_changed_count": 4,
        "budget_stability_signature_change_rate": 4 / 240,
        "budget_stability_harmful_change_count": 2,
        "budget_stability_beneficial_change_count": 2,
        "budget_stability_hit_delta_count": -1,
        "budget_stability_profit_loss_delta": -2.5,
        "budget_stability_roi_delta": -0.004,
        "budget_stability_warning_count": 0,
        "final_answer_market_concentration_audit_present": True,
        "final_answer_market_concentration_audit_key": (
            "historical_final_answer_market_concentration_audit:core"
        ),
        "final_answer_market_concentration_audit_status": "passed",
        "final_answer_market_concentration_audit_passed": True,
        "final_answer_market_concentration_slice_count": 5,
        "final_answer_market_concentration_final_answer_count": 5,
        "final_answer_market_concentration_dynamic_mixed_final_answer_count": 5,
        "final_answer_market_concentration_dynamic_mixed_final_answer_rate": 1.0,
        "final_answer_market_concentration_effective_pass_types": ["2x1", "3x1"],
        "final_answer_market_concentration_effective_constraint_profiles": [
            {"profile_key": "2x1:multiple:max_outcomes_per_fixture=1"},
            {"profile_key": "3x1:multiple:max_outcomes_per_fixture=2"},
        ],
        "final_answer_market_concentration_effective_constraint_profile_count": 2,
        "final_answer_market_concentration_candidate_completed_dynamic_mix_lane_count": 10,
        "final_answer_market_concentration_candidate_final_answer_dynamic_mix_lane_count": 5,
        "final_answer_market_concentration_failed_check_count": 0,
        "final_answer_market_concentration_warning_count": 0,
        "correct_score_admission_present": True,
        "correct_score_admission_key": "historical_correct_score_admission:core",
        "correct_score_admission_status": "holdout_only",
        "correct_score_admission_production_allowed": False,
        "correct_score_admission_holdout_allowed": True,
        "correct_score_admission_source_gate_key": (
            "historical_recommendation_suite_quality_gate:derived_markets"
        ),
        "correct_score_admission_source_gate_status": "passed",
        "correct_score_admission_source_suite_status": "unchanged",
        "correct_score_admission_slice_count": 100,
        "correct_score_admission_comparison_count": 100,
        "correct_score_admission_candidate_final_hit_sample_size": 100,
        "correct_score_admission_candidate_final_hit_coverage_ratio": 1.0,
        "correct_score_admission_candidate_final_hit_rate": 0.65,
        "correct_score_admission_candidate_roi": 0.04,
        "correct_score_admission_candidate_correct_score_final_answer_count": 0,
        "correct_score_admission_candidate_correct_score_final_answer_rate": 0.0,
        "correct_score_admission_final_hit_rate_delta": 0.014,
        "correct_score_admission_roi_delta": 0.011,
        "correct_score_admission_profit_loss_delta": 4.75,
        "correct_score_admission_brier_score_delta": -0.012,
        "correct_score_admission_log_loss_delta": -0.033,
        "correct_score_admission_mean_calibration_error_delta": -0.014,
        "correct_score_admission_production_recommendation_changed": False,
        "correct_score_admission_public_response_changed": False,
        "correct_score_admission_failed_checks": [
            "candidate_correct_score_final_answer_count"
        ],
        "correct_score_admission_failed_check_count": 1,
        "correct_score_admission_warning_count": 2,
        "correct_score_admission_warnings": [
            "correct_score_admission:failed_check:candidate_correct_score_final_answer_count",
            "correct_score_admission:holdout_only",
        ],
        "runtime_profile_switch_preset": (
            RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1
        ),
        "runtime_profile_switch_gate_present": True,
        "runtime_profile_switch_ready": True,
        "runtime_profile_switch_key": "historical_short_odds_runtime_profile_switch:core",
        "runtime_profile_switch_status": "switch_ready",
        "runtime_profile_switch_rule_count": 1,
        "runtime_profile_switch_default_profile_written": False,
        "runtime_profile_switch_replay_present": True,
        "runtime_profile_switch_replay_passed": True,
        "runtime_profile_switch_replay_key": (
            "historical_short_odds_runtime_shadow_replay:core"
        ),
        "runtime_profile_switch_replay_status": "shadow_replay_passed",
        "runtime_profile_switch_replay_final_answer_count": 30,
        "runtime_profile_switch_replay_roi_delta": 0.016,
        "runtime_profile_switch_replay_final_hit_harm_count_vs_original": 0,
        "runtime_profile_switch_replay_profit_loss_harm_count_vs_original": 0,
        "final_answer_segment_penalty_runtime_replay_preset": (
            FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
        ),
        "final_answer_segment_penalty_runtime_replay_present": True,
        "final_answer_segment_penalty_runtime_replay_holdout_allowed": True,
        "final_answer_segment_penalty_runtime_replay_runtime_allowed": False,
        "final_answer_segment_penalty_runtime_replay_key": (
            "historical_final_answer_segment_penalty_runtime_replay:core"
        ),
        "final_answer_segment_penalty_runtime_replay_status": "holdout_replay_passed",
        "final_answer_segment_penalty_runtime_replay_final_answer_count": 30,
        "final_answer_segment_penalty_runtime_replay_hit_count_delta": 2,
        "final_answer_segment_penalty_runtime_replay_roi_delta": 0.0703,
        "final_answer_segment_penalty_runtime_replay_harm_count": 0,
        "final_answer_segment_penalty_runtime_replay_final_hit_harm_count": 0,
        "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count": 0,
        "market_movement_runtime_activation_present": True,
        "market_movement_runtime_activation_key": (
            "historical_market_movement_runtime_activation:core"
        ),
        "market_movement_runtime_activation_status": "staged_activation_ready",
        "market_movement_runtime_activation_ready": True,
        "market_movement_runtime_activation_rule_count": 1,
        "market_movement_runtime_activation_selected_rule_count": 1,
        "market_movement_runtime_activation_selected_rule_ids": [
            "market_movement_risk_filter_runtime_shadow_candidate_v1"
        ],
        "market_movement_runtime_activation_selected_segment_group_keys": [
            "competition_outcome:LA_LIGA:home_win"
        ],
        "market_movement_runtime_activation_adjusted_fixture_count": 120,
        "market_movement_runtime_activation_adjusted_prediction_count": 360,
        "market_movement_runtime_activation_final_hit_rate_delta": 0.0,
        "market_movement_runtime_activation_roi_delta": 0.0,
        "market_movement_runtime_activation_profit_loss_delta": 0.0,
        "market_movement_runtime_activation_brier_score_delta": -0.001288445,
        "market_movement_runtime_activation_log_loss_delta": -0.002760848,
        "market_movement_runtime_activation_calibration_delta": -0.001278256,
        "market_movement_runtime_activation_default_profile_written": False,
        "market_movement_runtime_activation_default_path_changed": False,
        "market_movement_runtime_activation_production_changed": False,
        "market_movement_runtime_activation_public_changed": False,
        "market_movement_runtime_activation_blockers": [],
        "market_movement_runtime_activation_failed_checks": [],
        "market_movement_activation_sample_expansion_present": True,
        "market_movement_activation_sample_expansion_key": (
            "historical_market_movement_activation_sample_expansion:core"
        ),
        "market_movement_activation_sample_expansion_status": "shadow_only",
        "market_movement_activation_sample_expansion_passed": True,
        "market_movement_activation_sample_expansion_promotion_ready": False,
        "market_movement_activation_sample_expansion_combined_fixture_count": 3120,
        "market_movement_activation_sample_expansion_combined_competition_count": 12,
        "market_movement_activation_sample_expansion_adjusted_fixture_count": 120,
        "market_movement_activation_sample_expansion_adjusted_ratio": 120 / 3120,
        "market_movement_activation_sample_expansion_watchlist": [
            "selected_segment_count_for_promotion"
        ],
        "market_movement_activation_sample_expansion_blockers": [],
        "market_movement_segment_replay_batch_present": True,
        "market_movement_segment_replay_batch_key": (
            "historical_market_movement_segment_replay_batch_gate:core"
        ),
        "market_movement_segment_replay_batch_status": "watchlist",
        "market_movement_segment_replay_batch_passed": True,
        "market_movement_segment_replay_batch_ready": True,
        "market_movement_segment_replay_batch_promotion_ready": False,
        "market_movement_segment_replay_batch_report_count": 4,
        "market_movement_segment_replay_batch_passed_count": 4,
        "market_movement_segment_replay_batch_failed_count": 0,
        "market_movement_segment_replay_batch_adjusted_fixture_count": 1323,
        "market_movement_segment_replay_batch_adjusted_prediction_count": 3969,
        "market_movement_segment_replay_batch_weighted_brier_delta": -0.001158,
        "market_movement_segment_replay_batch_weighted_log_loss_delta": -0.002435,
        "market_movement_segment_replay_batch_weighted_calibration_delta": -0.001259,
        "market_movement_segment_replay_batch_watchlist": [
            "segment_expansion_production_promotion_ready"
        ],
        "market_movement_segment_replay_batch_blockers": [],
        "replacement_reranker_shadow_admission_present": True,
        "replacement_reranker_shadow_admission_key": (
            "historical_replacement_reranker_shadow_admission:core"
        ),
        "replacement_reranker_shadow_admission_status": "accepted",
        "replacement_reranker_shadow_admission_runtime_candidate_allowed": True,
        "replacement_reranker_shadow_admission_shadow_allowed": True,
        "replacement_reranker_source_surface_kind": "prematch_replacement_surface",
        "replacement_reranker_source_surface_missed_legs_only": False,
        "replacement_reranker_source_surface_selected_leg_count": 27,
        "replacement_reranker_source_surface_final_answer_count": 42,
        "replacement_reranker_shadow_admission_scope_enabled": True,
        "replacement_reranker_shadow_admission_scope_final_answer_count": 19,
        "replacement_reranker_shadow_final_answer_count": 17,
        "replacement_reranker_changed_from_model_top_count": 5,
        "replacement_reranker_hit_delta_vs_model_top": 1,
        "replacement_reranker_profit_loss_delta_vs_model_top": 4.1,
        "replacement_reranker_roi_delta_vs_model_top": 0.12058823529411763,
        "replacement_reranker_harm_count_vs_model_top": 0,
        "replacement_reranker_final_hit_harm_count_vs_model_top": 0,
        "replacement_reranker_profit_loss_harm_count_vs_model_top": 0,
        "replacement_reranker_failed_fold_count": 0,
        "replacement_reranker_active_competition_fold_count": 2,
        "replacement_reranker_active_season_fold_count": 3,
        "replacement_reranker_active_rolling_fold_count": 4,
        "global_planner_short_odds_adapter_gate_present": True,
        "global_planner_short_odds_adapter_gate_key": (
            "global_planner_short_odds_adapter_gate:core"
        ),
        "global_planner_short_odds_adapter_gate_status": "passed",
        "global_planner_short_odds_adapter_gate_passed": True,
        "global_planner_short_odds_adapter_default_path_changed": False,
        "global_planner_short_odds_adapter_shadow_path_changed": False,
        "global_planner_short_odds_adapter_explicit_opt_in_changed": True,
        "global_planner_short_odds_adapter_runtime_final_answer_count": 30,
        "global_planner_short_odds_adapter_runtime_changed_final_answer_count": 17,
        "global_planner_short_odds_adapter_runtime_roi_delta": 0.0176,
        "global_planner_short_odds_adapter_runtime_final_hit_harm_count": 0,
        "global_planner_short_odds_adapter_runtime_profit_loss_harm_count": 0,
        "global_planner_short_odds_adapter_sample_expansion_present": True,
        "global_planner_short_odds_adapter_sample_expansion_key": (
            "global_planner_short_odds_adapter_sample_expansion:core"
        ),
        "global_planner_short_odds_adapter_sample_expansion_status": "research_only",
        "global_planner_short_odds_adapter_sample_expansion_passed": True,
        "global_planner_short_odds_adapter_sample_expansion_promotion_ready": False,
        "global_planner_short_odds_adapter_sample_expansion_supplemental_final_answer_count": 26,
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "supplemental_changed_final_answer_count"
        ): 2,
        "global_planner_short_odds_adapter_sample_expansion_combined_final_answer_count": 86,
        (
            "global_planner_short_odds_adapter_sample_expansion_"
            "combined_changed_final_answer_count"
        ): 19,
        "global_planner_short_odds_adapter_sample_expansion_combined_roi_delta": 0.0208,
        "global_planner_short_odds_adapter_sample_expansion_combined_harm_count": 0,
        "global_planner_short_odds_adapter_sample_expansion_watchlist_checks": [
            "supplemental_changed_final_answer_count"
        ],
        "recommendation_strategy_promotion_gate_present": True,
        "recommendation_strategy_promotion_gate_key": (
            "recommendation_strategy_promotion_gate:core"
        ),
        "recommendation_strategy_promotion_gate_status": "ready",
        "recommendation_strategy_promotion_gate_ready": True,
        "recommendation_strategy_promotion_gate_final_answer_count": 99,
        "recommendation_strategy_promotion_gate_changed_final_answer_count": 13,
        "recommendation_strategy_promotion_gate_hit_delta_count": 4,
        "recommendation_strategy_promotion_gate_profit_loss_delta": 15.74,
        "recommendation_strategy_promotion_gate_harm_count": 0,
        "recommendation_strategy_staged_activation_smoke_present": True,
        "recommendation_strategy_staged_activation_smoke_key": (
            "recommendation_strategy_staged_activation_smoke:core"
        ),
        "recommendation_strategy_staged_activation_smoke_status": (
            "staged_activation_ready"
        ),
        "recommendation_strategy_staged_activation_ready": True,
        "recommendation_strategy_staged_rule_count": 1,
        "recommendation_strategy_staged_allowed_competition_count": 5,
        "recommendation_strategy_staged_default_profile_written": False,
        "recommendation_strategy_default_path_isolation_present": True,
        "recommendation_strategy_default_path_isolation_key": (
            "recommendation_strategy_default_path_isolation:core"
        ),
        "recommendation_strategy_default_path_isolation_status": "isolated",
        "recommendation_strategy_default_path_isolated": True,
        "recommendation_strategy_default_adapter_status": "disabled",
        "recommendation_strategy_default_adapter_selection_changed": False,
        "recommendation_strategy_explicit_opt_in_selection_changed": True,
        "recommendation_strategy_isolation_default_profile_written": False,
        "probability_calibration_profile_rolling_admission_present": True,
        "probability_calibration_profile_rolling_admission_key": (
            "historical_probability_calibration_profile_rolling_admission:core"
        ),
        "probability_calibration_profile_rolling_admission_status": "accepted",
        "probability_calibration_profile_candidate_allowed": True,
        "probability_calibration_profile_shadow_allowed": True,
        "probability_calibration_profile_mode": "active",
        "probability_calibration_profile_key": (
            "candidate_probability_calibration_profile:core"
        ),
        "probability_calibration_profile_overall_gate_passed": True,
        "probability_calibration_profile_overall_adjusted_fixture_count": 24,
        "probability_calibration_profile_overall_bucket_count": 3,
        "probability_calibration_profile_failed_fold_count": 0,
        "probability_calibration_profile_active_competition_fold_count": 2,
        "probability_calibration_profile_active_season_cutoff_fold_count": 3,
        "probability_calibration_profile_active_rolling_fold_count": 2,
        "probability_calibration_profile_model_quality_gate_present": True,
        "probability_calibration_profile_model_quality_gate_key": (
            "historical_probability_calibration_profile_model_quality_gate:core"
        ),
        "probability_calibration_profile_model_quality_gate_status": (
            "model_quality_ready"
        ),
        "probability_calibration_profile_model_quality_gate_ready": True,
        "probability_calibration_profile_model_quality_selected_competition_count": 4,
        "probability_calibration_profile_model_quality_adjusted_slice_count": 4,
        "probability_calibration_profile_model_quality_adjusted_fixture_count": 96,
        "probability_calibration_profile_model_quality_skipped_fixture_count": 0,
        "probability_calibration_profile_model_quality_final_answer_changed_count": 0,
        "probability_calibration_profile_model_quality_brier_score_delta": -0.01,
        "probability_calibration_profile_model_quality_log_loss_delta": -0.02,
        "probability_calibration_profile_model_quality_mean_calibration_error_delta": (
            -0.01
        ),
        "asian_handicap_segmented_model_quality_governance_present": True,
        "asian_handicap_segmented_model_quality_governance_key": (
            "historical_prematch_feature_asian_handicap_segmented_governance_review:core"
        ),
        "asian_handicap_segmented_model_quality_governance_status": (
            "governance_ready"
        ),
        "asian_handicap_segmented_model_quality_governance_ready": True,
        "asian_handicap_segmented_model_quality_internal_only": True,
        "asian_handicap_segmented_model_quality_default_path_isolated": True,
        "asian_handicap_segmented_model_quality_production_allowed": False,
        "asian_handicap_segmented_model_quality_production_changed": False,
        "asian_handicap_segmented_model_quality_public_response_changed": False,
        "asian_handicap_segmented_model_quality_accepted_segment_count": 3,
        "asian_handicap_segmented_model_quality_shadow_segment_count": 0,
        "asian_handicap_segmented_model_quality_fallback_segment_count": 2,
        "asian_handicap_segmented_model_quality_rejected_segment_count": 0,
        "asian_handicap_segmented_model_quality_accepted_validation_count": 138,
        "asian_handicap_segmented_model_quality_calibration_applied_count": 2,
        "asian_handicap_segmented_model_quality_brier_score_delta": -0.001,
        "asian_handicap_segmented_model_quality_log_loss_delta": -0.002,
        "asian_handicap_segmented_model_quality_calibration_error_delta": -0.0003,
        "asian_handicap_segmented_model_quality_actual_probability_delta": 0.0002,
        "prematch_feature_quality_cycle_present": True,
        "prematch_feature_quality_cycle_key": (
            "historical_prematch_feature_quality_cycle:core"
        ),
        "prematch_feature_quality_cycle_status": "passed",
        "prematch_feature_quality_cycle_passed": True,
        "prematch_feature_quality_cycle_final_answer_gate_key": (
            "historical_prematch_feature_final_answer_gate:core"
        ),
        "prematch_feature_quality_cycle_grid_key": (
            "historical_prematch_feature_ablation_grid:core"
        ),
        "prematch_feature_quality_cycle_slice_count": 25,
        "prematch_feature_quality_cycle_fixture_count": 600,
        "prematch_feature_quality_cycle_evaluated_candidate_count": 5,
        "prematch_feature_quality_cycle_passing_candidate_count": 1,
        "prematch_feature_quality_cycle_best_feature_grid_candidate_id": (
            "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
        ),
        "prematch_feature_quality_cycle_best_feature_grid_rank": 1,
        "prematch_feature_quality_cycle_best_gate_passed": True,
        "prematch_feature_quality_cycle_best_suite_status": "improved",
        "prematch_feature_quality_cycle_best_brier_score_delta": -0.01,
        "prematch_feature_quality_cycle_best_log_loss_delta": -0.02,
        "prematch_feature_quality_cycle_best_calibration_error_delta": -0.01,
        "prematch_feature_quality_cycle_best_failed_quality_check_names": [],
        "prematch_feature_quality_cycle_warning_count": 0,
        "prematch_feature_rolling_admission_present": True,
        "prematch_feature_rolling_admission_key": (
            "historical_prematch_feature_rolling_admission:core"
        ),
        "prematch_feature_rolling_admission_status": "accepted",
        "prematch_feature_rolling_admission_candidate_allowed": True,
        "prematch_feature_rolling_admission_shadow_allowed": True,
        "prematch_feature_rolling_admission_source_grid_key": (
            "historical_prematch_feature_ablation_grid:core"
        ),
        "prematch_feature_rolling_admission_overall_gate_key": (
            "historical_prematch_feature_final_answer_gate:core"
        ),
        "prematch_feature_rolling_admission_overall_gate_passed": True,
        "prematch_feature_rolling_admission_overall_evaluated_candidate_count": 5,
        "prematch_feature_rolling_admission_overall_passing_candidate_count": 1,
        "prematch_feature_rolling_admission_failed_fold_count": 0,
        "prematch_feature_rolling_admission_active_competition_fold_count": 2,
        "prematch_feature_rolling_admission_active_season_cutoff_fold_count": 3,
        "prematch_feature_rolling_admission_active_rolling_fold_count": 2,
        "prematch_feature_rolling_admission_best_feature_grid_candidate_id": (
            "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
        ),
        "prematch_feature_rolling_admission_best_gate_passed": True,
        "prematch_feature_rolling_admission_best_suite_status": "improved",
        "prematch_feature_rolling_admission_overall_brier_score_delta": -0.01,
        "prematch_feature_rolling_admission_overall_log_loss_delta": -0.02,
        "prematch_feature_rolling_admission_overall_calibration_error_delta": -0.01,
        "prematch_feature_rolling_admission_failed_checks": [],
        "prematch_feature_rolling_admission_warning_count": 0,
        "prematch_feature_sample_readiness_present": True,
        "prematch_feature_sample_readiness_key": (
            "historical_prematch_feature_sample_readiness:core"
        ),
        "prematch_feature_sample_readiness_status": "accepted",
        "prematch_feature_sample_readiness_target_profile": "market_movement",
        "prematch_feature_sample_ready_allowed": True,
        "prematch_feature_sample_readiness_shadow_allowed": True,
        "prematch_feature_sample_readiness_coverage_audit_key": (
            "historical_sample_coverage_audit:core"
        ),
        "prematch_feature_sample_ready_source_count": 1,
        "prematch_feature_sample_ready_fixture_count": 600,
        "prematch_feature_sample_ready_slice_count": 25,
        "prematch_feature_sample_ready_competition_count": 3,
        "prematch_feature_sample_ready_season_count": 2,
        "prematch_feature_sample_ready_competition_season_count": 3,
        "prematch_feature_sample_readiness_failed_checks": [],
        "prematch_feature_sample_readiness_warning_count": 0,
    }


def _stored_run() -> StoredRecommendationBenchmarkRun:
    return StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=88,
        benchmark_key="recommendation_benchmark:cycle",
        dry_run=True,
        strategy="accuracy_first",
        scenario_count=6,
        completed_count=6,
        failed_count=0,
        global_best_selected_count=6,
        core_replay_ready_count=6,
        core_replay_total_run_count=6,
        core_replay_total_settled_run_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        average_core_replay_roi=0.12,
        warning_count=0,
        history_comparison_json={"status": "improved"},
        summary_json={"history_status": "improved"},
        created_at=_dt(2026, 5, 12, 0),
    )


def _stored_cycle_run(
    *,
    recommendation_benchmark_cycle_run_id: int,
    cycle_key: str,
    summary_json: dict[str, object],
) -> StoredRecommendationBenchmarkCycleRun:
    return StoredRecommendationBenchmarkCycleRun(
        recommendation_benchmark_cycle_run_id=recommendation_benchmark_cycle_run_id,
        cycle_key=cycle_key,
        status="passed",
        passed=True,
        schedule_key="recommendation_benchmark_schedule:daily-core:daily",
        benchmark_key="recommendation_benchmark:cycle",
        benchmark_run_id=88,
        gate_key="recommendation_benchmark_quality_gate:recommendation_benchmark:cycle",
        gate_status="passed",
        gate_passed=True,
        historical_suite_quality_gate_key=(
            "historical_recommendation_suite_quality_gate:core"
        ),
        historical_suite_quality_gate_passed=True,
        historical_suite_lifecycle_source_status_synced=True,
        historical_suite_lifecycle_effective_leaf_count=1,
        historical_suite_lifecycle_active_edge_count=1,
        historical_suite_lifecycle_critical_issue_count=0,
        historical_suite_lifecycle_source_status_sync_required_count=0,
        failed_checks_json=[],
        summary_json=summary_json,
        warnings_json=[],
        created_at=_dt(2026, 5, 12, 0),
    )


def _stored_cycle_row(
    *,
    recommendation_benchmark_cycle_run_id: int,
    cycle_key: str,
    summary_json: object,
) -> DatabaseRow:
    return {
        "recommendation_benchmark_cycle_run_id": (
            recommendation_benchmark_cycle_run_id
        ),
        "cycle_key": cycle_key,
        "status": "passed",
        "passed": True,
        "schedule_key": "recommendation_benchmark_schedule:daily-core:daily",
        "benchmark_key": "recommendation_benchmark:cycle",
        "benchmark_run_id": 88,
        "gate_key": "recommendation_benchmark_quality_gate:cycle",
        "gate_status": "passed",
        "gate_passed": True,
        "historical_suite_quality_gate_key": (
            "historical_recommendation_suite_quality_gate:core"
        ),
        "historical_suite_quality_gate_passed": True,
        "historical_suite_lifecycle_source_status_synced": True,
        "historical_suite_lifecycle_effective_leaf_count": 1,
        "historical_suite_lifecycle_active_edge_count": 1,
        "historical_suite_lifecycle_critical_issue_count": 0,
        "historical_suite_lifecycle_source_status_sync_required_count": 0,
        "failed_checks_json": [],
        "summary_json": summary_json,
        "warnings_json": [],
        "created_at": _dt(2026, 5, 12, 0),
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
