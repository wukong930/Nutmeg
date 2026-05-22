from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport,
)
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationBenchmarkQualityGateOptions,
    RecommendationHistoricalSuiteQualityGateEvidence,
    StoredRecommendationBenchmarkRun,
    run_recommendation_benchmark_quality_gate,
)
from nutmeg.recommendations.benchmark_quality_gate import (
    FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
    RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
    RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1,
    UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
    _options_from_args,
    _parse_args,
    apply_unified_candidate_pool_guard_preset,
)
from nutmeg.recommendations.global_planner_short_odds_adapter_gate import (
    HistoricalGlobalPlannerShortOddsAdapterGateReport,
)
from nutmeg.recommendations.global_planner_short_odds_adapter_sample_expansion import (
    HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport,
)
from nutmeg.recommendations.historical_budget_stability_audit import (
    HistoricalBudgetRunSummary,
    HistoricalBudgetStabilityAuditReport,
    HistoricalBudgetStabilityComparisonSummary,
)
from nutmeg.recommendations.historical_correct_score_admission import (
    HistoricalCorrectScoreAdmissionCheck,
    HistoricalCorrectScoreAdmissionReport,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditReport,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_runtime_replay import (
    HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    HistoricalMarketMovementRiskFilterRuntimeActivationReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_sample_expansion import (
    HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_segment_replay_batch_gate import (  # noqa: E501
    HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport,
)
from nutmeg.recommendations.historical_prematch_feature_quality_cycle import (
    HistoricalPrematchFeatureQualityCycleResult,
)
from nutmeg.recommendations.historical_prematch_feature_rolling_admission import (
    HistoricalPrematchFeatureRollingAdmissionReport,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_model_quality_gate import (
    HistoricalProbabilityCalibrationProfileModelQualityGateReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
)
from nutmeg.recommendations.recommendation_strategy_default_path_isolation import (
    RecommendationStrategyDefaultPathIsolationReport,
)
from nutmeg.recommendations.recommendation_strategy_promotion_gate import (
    RecommendationStrategyPromotionGateReport,
)
from nutmeg.recommendations.recommendation_strategy_staged_activation_smoke import (
    RecommendationStrategyStagedActivationSmokeReport,
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


def test_quality_gate_passes_latest_benchmark_inside_thresholds() -> None:
    latest = _benchmark_run(
        recommendation_benchmark_run_id=12,
        completed_count=10,
        core_replay_ready_count=8,
        final_hit_sample_size=5,
        final_hit_count=3,
        average_core_replay_roi=0.08,
        history_status="improved",
    )
    previous = _benchmark_run(
        recommendation_benchmark_run_id=11,
        completed_count=10,
        core_replay_ready_count=7,
        final_hit_sample_size=5,
        final_hit_count=2,
        average_core_replay_roi=0.03,
        history_status="baseline",
    )
    repository = FakeQualityGateRepository([latest, previous])

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            benchmark_key="recommendation_benchmark:daily-core",
            strategy="accuracy_first",
            min_completed_ratio=0.95,
            max_failed_count=0,
            max_warning_count=1,
            min_core_replay_ready_ratio=0.70,
            min_final_hit_sample_size=5,
            min_final_hit_rate=0.60,
            min_average_core_replay_roi=0.05,
        ),
        repository=repository,
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.latest_run == latest
    assert result.previous_run == previous
    assert result.summary_json["completed_ratio"] == 1.0
    assert result.summary_json["final_hit_rate"] == 0.6
    assert result.summary_json["failed_checks"] == []
    assert repository.calls == [
        {
            "benchmark_key": "recommendation_benchmark:daily-core",
            "strategy": "accuracy_first",
            "limit": 2,
        }
    ]


def test_quality_gate_fails_benchmark_regressions_and_threshold_breaks() -> None:
    latest = _benchmark_run(
        scenario_count=10,
        completed_count=8,
        failed_count=2,
        warning_count=4,
        core_replay_ready_count=3,
        final_hit_sample_size=5,
        final_hit_count=1,
        average_core_replay_roi=-0.20,
        history_status="regressed",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            min_completed_ratio=0.95,
            max_failed_count=0,
            max_warning_count=1,
            min_core_replay_ready_ratio=0.70,
            min_final_hit_sample_size=5,
            min_final_hit_rate=0.50,
            min_average_core_replay_roi=0.0,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert result.status == "failed"
    assert failed_checks == {
        "completed_ratio",
        "failed_count",
        "warning_count",
        "core_replay_ready_ratio",
        "final_hit_rate",
        "average_core_replay_roi",
        "history_status",
    }
    assert result.summary_json["history_status"] == "regressed"
    assert result.warnings == [
        "benchmark_quality_gate:failed_check:completed_ratio",
        "benchmark_quality_gate:failed_check:failed_count",
        "benchmark_quality_gate:failed_check:warning_count",
        "benchmark_quality_gate:failed_check:core_replay_ready_ratio",
        "benchmark_quality_gate:failed_check:final_hit_rate",
        "benchmark_quality_gate:failed_check:average_core_replay_roi",
        "benchmark_quality_gate:failed_check:history_status",
    ]


def test_quality_gate_blocks_missing_recommendation_candidate_coverage() -> None:
    latest = _benchmark_run(
        completed_count=10,
        global_best_selected_count=0,
        global_best_candidate_count=0,
        global_best_generated_option_count=0,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            min_global_best_selected_count=1,
            min_global_best_candidate_count=1,
            min_global_best_generated_option_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert failed_checks == {
        "global_best_selected_count",
        "global_best_candidate_count",
        "global_best_generated_option_count",
    }
    assert result.summary_json["global_best_selected_count"] == 0
    assert result.summary_json["global_best_candidate_count"] == 0
    assert result.summary_json["global_best_generated_option_count"] == 0


def test_quality_gate_checks_unified_candidate_pool_coverage() -> None:
    latest = _benchmark_run()
    latest = latest.model_copy(
        update={
            "summary_json": {
                **latest.summary_json,
                "unified_candidate_pool_present_count": 10,
                "unified_candidate_pool_valid_candidate_count": 24,
                "unified_candidate_pool_unique_family_keys": [
                    "standalone_single:1x1:single",
                    "single_parlay:2x1:single",
                    "multiple_parlay:3x1:multiple",
                ],
                "unified_candidate_pool_selection_mismatch_count": 0,
                "unified_candidate_pool_selected_2x1_count": 3,
                "unified_candidate_pool_selected_2x1_rate": 0.30,
                "unified_candidate_pool_multiple_value_candidate_count": 4,
                "unified_candidate_pool_multiple_value_admitted_candidate_count": 3,
                "unified_candidate_pool_multiple_value_rejected_candidate_count": 1,
                "unified_candidate_pool_multiple_value_extra_option_count": 8,
                "unified_candidate_pool_selected_multiple_value_statuses": [
                    "not_multiple",
                    "admitted",
                ],
                "unified_candidate_pool_selected_multiple_value_admitted_count": 2,
                "unified_candidate_pool_selected_multiple_value_rejected_count": 0,
                "unified_candidate_pool_selected_multiple_extra_option_count": 5,
                "unified_candidate_pool_multiple_value_rejection_reason_counts": {
                    "marginal_quality_gain_negative": 1
                },
            }
        }
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_unified_candidate_pool=True,
            min_unified_candidate_pool_present_count=10,
            min_unified_candidate_pool_valid_candidate_count=20,
            min_unified_candidate_pool_unique_family_count=3,
            max_unified_candidate_pool_selected_2x1_rate=0.50,
            min_unified_candidate_pool_multiple_value_candidate_count=4,
            min_unified_candidate_pool_multiple_value_admitted_candidate_count=3,
            min_unified_candidate_pool_multiple_value_extra_option_count=8,
            max_unified_candidate_pool_multiple_value_rejected_candidate_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json["unified_candidate_pool_present_count"] == 10
    assert result.summary_json["unified_candidate_pool_unique_family_count"] == 3
    assert result.summary_json["unified_candidate_pool_selected_2x1_rate"] == 0.30
    assert result.summary_json["unified_candidate_pool_multiple_value_candidate_count"] == 4
    assert (
        result.summary_json[
            "unified_candidate_pool_multiple_value_admitted_candidate_count"
        ]
        == 3
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_value_rejected_count"
        ]
        == 0
    )
    assert result.summary_json[
        "unified_candidate_pool_multiple_value_rejection_reason_counts"
    ] == {"marginal_quality_gain_negative": 1}


def test_quality_gate_blocks_unified_candidate_pool_collapse() -> None:
    latest = _benchmark_run()
    latest = latest.model_copy(
        update={
            "summary_json": {
                **latest.summary_json,
                "unified_candidate_pool_present_count": 2,
                "unified_candidate_pool_valid_candidate_count": 2,
                "unified_candidate_pool_unique_family_keys": [
                    "single_parlay:2x1:single"
                ],
                "unified_candidate_pool_selection_mismatch_count": 1,
                "unified_candidate_pool_selected_2x1_rate": 1.0,
            }
        }
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_unified_candidate_pool=True,
            min_unified_candidate_pool_present_count=3,
            min_unified_candidate_pool_valid_candidate_count=4,
            min_unified_candidate_pool_unique_family_count=2,
            max_unified_candidate_pool_selection_mismatch_count=0,
            max_unified_candidate_pool_selected_2x1_rate=0.80,
        ),
        repository=FakeQualityGateRepository([latest]),
    )
    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "unified_candidate_pool_present_count",
        "unified_candidate_pool_valid_candidate_count",
        "unified_candidate_pool_unique_family_count",
        "unified_candidate_pool_selection_mismatch_count",
        "unified_candidate_pool_selected_2x1_rate",
    }.issubset(failed_checks)


def test_quality_gate_blocks_rejected_selected_multiple_value_expansion() -> None:
    latest = _benchmark_run()
    latest = latest.model_copy(
        update={
            "summary_json": {
                **latest.summary_json,
                "unified_candidate_pool_present_count": 4,
                "unified_candidate_pool_valid_candidate_count": 8,
                "unified_candidate_pool_unique_family_keys": [
                    "standalone_single:1x1:single",
                    "multiple_parlay:4x1:multiple",
                ],
                "unified_candidate_pool_multiple_value_candidate_count": 2,
                "unified_candidate_pool_multiple_value_admitted_candidate_count": 0,
                "unified_candidate_pool_multiple_value_rejected_candidate_count": 2,
                "unified_candidate_pool_multiple_value_extra_option_count": 4,
                "unified_candidate_pool_selected_multiple_value_rejected_count": 1,
            }
        }
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_unified_candidate_pool_multiple_value_admission=True,
            min_unified_candidate_pool_multiple_value_candidate_count=3,
            min_unified_candidate_pool_multiple_value_admitted_candidate_count=1,
            min_unified_candidate_pool_multiple_value_extra_option_count=5,
            max_unified_candidate_pool_multiple_value_rejected_candidate_count=1,
            max_unified_candidate_pool_selected_multiple_value_rejected_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
    )
    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "unified_candidate_pool_multiple_value_admission",
        "unified_candidate_pool_multiple_value_candidate_count",
        "unified_candidate_pool_multiple_value_admitted_candidate_count",
        "unified_candidate_pool_multiple_value_extra_option_count",
        "unified_candidate_pool_multiple_value_rejected_candidate_count",
        "unified_candidate_pool_selected_multiple_value_rejected_count",
    }.issubset(failed_checks)


def test_quality_gate_unified_candidate_pool_guard_preset_sets_thresholds() -> None:
    options = apply_unified_candidate_pool_guard_preset(
        RecommendationBenchmarkQualityGateOptions(),
        UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
    )

    assert (
        options.unified_candidate_pool_guard_preset
        == UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
    )
    assert options.require_unified_candidate_pool is True
    assert options.min_unified_candidate_pool_present_count == 1
    assert options.min_unified_candidate_pool_valid_candidate_count == 1
    assert options.min_unified_candidate_pool_unique_family_count == 2
    assert options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert options.max_unified_candidate_pool_selected_2x1_rate == 0.80
    assert (
        options.max_unified_candidate_pool_selected_multiple_value_rejected_count == 0
    )


def test_quality_gate_blocks_incomplete_final_answer_replay_coverage() -> None:
    latest = _benchmark_run(
        scenario_count=10,
        completed_count=10,
        core_replay_ready_count=10,
        final_hit_sample_size=6,
        final_hit_count=4,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            min_final_hit_coverage_ratio=1.0,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert "final_hit_coverage_ratio" in failed_checks
    assert result.summary_json["final_hit_sample_size"] == 6
    assert result.summary_json["final_hit_coverage_ratio"] == 0.6


def test_quality_gate_blocks_chain_integrity_critical_issues() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        core_replay_ready_count=3,
        chain_integrity_ready_count=2,
        chain_integrity_total_critical_issue_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            min_chain_integrity_ready_ratio=1.0,
            max_chain_integrity_critical_issue_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {
        "chain_integrity_ready_ratio",
        "chain_integrity_critical_issue_count",
    }
    assert result.summary_json["chain_integrity_ready_ratio"] == 2 / 3
    assert result.summary_json["chain_integrity_critical_issue_count"] == 1


def test_quality_gate_blocks_successor_chain_evaluation_regressions() -> None:
    latest = _benchmark_run(
        scenario_count=4,
        completed_count=4,
        successor_chain_evaluation_passed_count=3,
        successor_chain_effective_leaf_count=3,
        successor_chain_critical_issue_count=1,
        successor_chain_ambiguous_source_count=1,
        successor_chain_source_status_sync_required_count=2,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            min_successor_chain_evaluation_passed_ratio=1.0,
            min_successor_chain_effective_leaf_count=4,
            max_successor_chain_critical_issue_count=0,
            max_successor_chain_ambiguous_source_count=0,
            max_successor_chain_source_status_sync_required_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {
        "successor_chain_evaluation_passed_ratio",
        "successor_chain_effective_leaf_count",
        "successor_chain_critical_issue_count",
        "successor_chain_ambiguous_source_count",
        "successor_chain_source_status_sync_required_count",
    }
    assert result.summary_json["successor_chain_evaluation_passed_ratio"] == 0.75
    assert result.summary_json["successor_chain_effective_leaf_count"] == 3
    assert result.summary_json["successor_chain_critical_issue_count"] == 1


def test_quality_gate_blocks_lifecycle_and_upset_regressions() -> None:
    latest = _benchmark_run(
        scenario_count=4,
        completed_count=4,
        core_replay_ready_count=4,
        ambiguous_successor_source_count=1,
        stale_recommendation_count=2,
        successor_recompute_required_count=1,
        upset_opportunity_count=4,
        upset_capture_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            max_ambiguous_successor_source_count=0,
            max_stale_recommendation_count=0,
            max_successor_recompute_required_count=0,
            min_upset_capture_sample_size=4,
            min_upset_capture_rate=0.50,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {
        "ambiguous_successor_source_count",
        "stale_recommendation_count",
        "successor_recompute_required_count",
        "upset_capture_rate",
    }
    assert result.summary_json["ambiguous_successor_source_count"] == 1
    assert result.summary_json["stale_recommendation_count"] == 2
    assert result.summary_json["successor_recompute_required_count"] == 1
    assert result.summary_json["upset_capture_sample_size"] == 4
    assert result.summary_json["upset_capture_count"] == 1
    assert result.summary_json["upset_capture_rate"] == 0.25


def test_quality_gate_consumes_historical_suite_lifecycle_evidence() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    evidence = _historical_suite_gate_evidence(
        slice_count=30,
        comparison_count=30,
        lifecycle_effective_leaf_count=1,
        lifecycle_active_edge_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            min_historical_suite_slice_count=30,
            min_historical_suite_comparison_count=30,
            min_historical_suite_lifecycle_effective_leaf_count=1,
            min_historical_suite_lifecycle_active_edge_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    assert result.passed is True
    assert result.historical_suite_quality_gate_present is True
    assert result.historical_suite_quality_gate_passed is True
    assert result.summary_json["historical_suite_quality_gate_key"] == (
        "historical_recommendation_suite_quality_gate:core"
    )
    assert result.summary_json["historical_suite_slice_count"] == 30
    assert result.summary_json["historical_suite_comparison_count"] == 30
    assert result.summary_json["historical_suite_candidate_final_hit_sample_size"] == 30
    assert result.summary_json[
        "historical_suite_candidate_final_hit_coverage_ratio"
    ] == 1.0
    assert result.summary_json["historical_suite_candidate_final_hit_rate"] == 2 / 3
    assert result.summary_json["historical_suite_candidate_roi"] == 0.12
    assert result.summary_json["historical_suite_lifecycle_source_status_synced"] is True


def test_quality_gate_consumes_historical_suite_dynamic_mixed_evidence() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence(
        candidate_dynamic_mixed_final_answer_count=6,
        candidate_dynamic_mixed_final_answer_rate=0.60,
        candidate_final_answer_market_type_counts={
            "1x2": 10,
            "cn_handicap_1x2": 6,
        },
        candidate_handicap_final_answer_count=6,
        candidate_handicap_final_answer_rate=0.60,
        candidate_correct_score_final_answer_count=2,
        candidate_multiple_choice_final_answer_count=3,
        candidate_final_answer_selected_candidate_count=25,
        candidate_final_answer_multiple_choice_fixture_count=4,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            min_historical_suite_candidate_dynamic_mixed_final_answer_count=6,
            min_historical_suite_candidate_dynamic_mixed_final_answer_rate=0.50,
            min_historical_suite_candidate_handicap_final_answer_count=6,
            min_historical_suite_candidate_correct_score_final_answer_count=2,
            min_historical_suite_candidate_multiple_choice_final_answer_count=3,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )
    failed_result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            min_historical_suite_candidate_dynamic_mixed_final_answer_count=7,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    assert result.passed is True
    assert result.summary_json[
        "historical_suite_candidate_dynamic_mixed_final_answer_count"
    ] == 6
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
    assert result.summary_json[
        "historical_suite_candidate_final_answer_selected_candidate_count"
    ] == 25
    assert result.summary_json[
        "historical_suite_candidate_final_answer_multiple_choice_fixture_count"
    ] == 4
    assert failed_result.passed is False
    assert "historical_suite_candidate_dynamic_mixed_final_answer_count" in {
        check.name for check in failed_result.checks if check.status == "failed"
    }


def test_quality_gate_consumes_historical_suite_successor_chain_evidence() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence(
        successor_chain_evaluation_present=True,
        successor_chain_evaluation_passed=True,
        successor_effective_final_only_ready=True,
        successor_effective_leaf_count=1,
        successor_active_edge_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            require_historical_suite_successor_chain_evaluation=True,
            min_historical_suite_successor_effective_leaf_count=1,
            min_historical_suite_successor_active_edge_count=1,
            max_historical_suite_successor_critical_issue_count=0,
            max_historical_suite_successor_ambiguous_source_count=0,
            max_historical_suite_successor_source_status_sync_required_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    assert result.passed is True
    assert result.summary_json[
        "historical_suite_successor_chain_evaluation_present"
    ] is True
    assert result.summary_json[
        "historical_suite_successor_chain_evaluation_passed"
    ] is True
    assert result.summary_json[
        "historical_suite_successor_effective_final_only_ready"
    ] is True
    assert result.summary_json["historical_suite_successor_effective_leaf_count"] == 1


def test_quality_gate_blocks_missing_historical_suite_successor_chain_evidence() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence(
        successor_chain_evaluation_present=False,
        successor_chain_evaluation_passed=None,
        successor_effective_final_only_ready=False,
        successor_effective_leaf_count=0,
        successor_active_edge_count=0,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            require_historical_suite_successor_chain_evaluation=True,
            min_historical_suite_successor_effective_leaf_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "historical_suite_successor_chain_evaluation_present",
        "historical_suite_successor_chain_evaluation_passed",
        "historical_suite_successor_effective_final_only_ready",
        "historical_suite_successor_effective_leaf_count",
    }.issubset(failed_checks)


def test_quality_gate_consumes_historical_suite_market_movement_runtime_replay() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence(
        market_movement_runtime_replay_present=True,
        market_movement_runtime_replay_passed=True,
        market_movement_runtime_replay_allowed=True,
        market_movement_runtime_replay_status="runtime_shadow_replay_passed",
        market_movement_runtime_replay_rule_count=1,
        market_movement_runtime_replay_selected_rule_count=1,
        market_movement_runtime_replay_accepted_count=1,
        market_movement_runtime_replay_adjusted_fixture_count=120,
        market_movement_runtime_replay_adjusted_prediction_count=360,
        market_movement_runtime_replay_final_hit_rate_delta=0.0,
        market_movement_runtime_replay_roi_delta=0.0,
        market_movement_runtime_replay_profit_loss_delta=0.0,
        market_movement_runtime_replay_brier_score_delta=-0.001288,
        market_movement_runtime_replay_log_loss_delta=-0.002761,
        market_movement_runtime_replay_mean_calibration_error_delta=-0.001278,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            require_historical_suite_market_movement_runtime_replay=True,
            min_historical_suite_market_movement_runtime_replay_rule_count=1,
            min_historical_suite_market_movement_runtime_replay_selected_rule_count=1,
            min_historical_suite_market_movement_runtime_replay_accepted_count=1,
            min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count=120,
            min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count=360,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    assert result.passed is True
    assert result.summary_json[
        "historical_suite_market_movement_runtime_replay_present"
    ] is True
    assert result.summary_json[
        "historical_suite_market_movement_runtime_replay_allowed"
    ] is True
    assert result.summary_json[
        "historical_suite_market_movement_runtime_replay_adjusted_fixture_count"
    ] == 120
    assert result.summary_json[
        "historical_suite_market_movement_runtime_replay_calibration_delta"
    ] == -0.001278


def test_quality_gate_blocks_missing_historical_suite_market_movement_runtime_replay() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            require_historical_suite_market_movement_runtime_replay=True,
            min_historical_suite_market_movement_runtime_replay_rule_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert {
        "historical_suite_market_movement_runtime_replay_present",
        "historical_suite_market_movement_runtime_replay_passed",
        "historical_suite_market_movement_runtime_replay_allowed",
        "historical_suite_market_movement_runtime_replay_passed_status",
        "historical_suite_market_movement_runtime_replay_rule_count",
    }.issubset(failed_checks)


def test_quality_gate_blocks_incomplete_historical_suite_final_hit_coverage() -> None:
    latest = _benchmark_run(history_status="unchanged")
    evidence = _historical_suite_gate_evidence(
        comparison_count=210,
        candidate_final_hit_sample_size=100,
        candidate_final_hit_coverage_ratio=100 / 210,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            min_historical_suite_candidate_final_hit_sample_size=210,
            min_historical_suite_candidate_final_hit_coverage_ratio=1.0,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert "historical_suite_candidate_final_hit_sample_size" in failed_checks
    assert "historical_suite_candidate_final_hit_coverage_ratio" in failed_checks


def test_quality_gate_blocks_missing_required_historical_suite_evidence() -> None:
    latest = _benchmark_run()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {"historical_suite_quality_gate_present"}
    assert result.summary_json["historical_suite_quality_gate_present"] is False


def test_quality_gate_blocks_unsynced_historical_suite_lifecycle_source_status() -> None:
    latest = _benchmark_run()
    evidence = _historical_suite_gate_evidence(
        lifecycle_source_status_synced=False,
        lifecycle_source_status_sync_required_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_historical_suite_quality_gate=True,
            max_historical_suite_lifecycle_source_status_sync_required_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        historical_suite_quality_gate=evidence,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {
        "historical_suite_lifecycle_source_status_synced",
        "historical_suite_lifecycle_source_status_sync_required_count",
    }
    assert (
        result.summary_json[
            "historical_suite_lifecycle_source_status_sync_required_count"
        ]
        == 1
    )


def test_quality_gate_loads_historical_suite_gate_report_from_options(tmp_path) -> None:
    latest = _benchmark_run()
    report_path = tmp_path / "suite_gate.json"
    report_path.write_text(
        _historical_suite_gate_evidence().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            historical_suite_quality_gate_report_path=report_path,
            require_historical_suite_quality_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json["historical_suite_quality_gate_report_path"] == str(
        report_path
    )


def test_quality_gate_consumes_budget_stability_audit_evidence() -> None:
    latest = _benchmark_run(history_status="unchanged")
    audit = _budget_stability_audit_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_budget_stability_audit=True,
            min_budget_stability_slice_count=240,
            min_budget_stability_comparable_count=240,
            max_budget_stability_signature_change_rate=0.02,
            max_budget_stability_harmful_change_count=2,
            min_budget_stability_hit_delta_count=-1,
            min_budget_stability_roi_delta=-0.005,
            max_budget_stability_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        budget_stability_audit=audit,
    )

    assert result.passed is True
    assert result.budget_stability_audit_present is True
    assert result.summary_json["budget_stability_audit_key"] == (
        "historical_budget_stability_audit:test"
    )
    assert result.summary_json["budget_stability_slice_count"] == 240
    assert result.summary_json["budget_stability_comparable_count"] == 240
    assert result.summary_json["budget_stability_signature_change_rate"] == (
        4 / 240
    )
    assert result.summary_json["budget_stability_harmful_change_count"] == 2
    assert result.summary_json["budget_stability_hit_delta_count"] == -1
    assert result.summary_json["budget_stability_roi_delta"] == -0.004


def test_quality_gate_blocks_budget_stability_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")
    audit = _budget_stability_audit_report(
        harmful_change_count=3,
        signature_change_rate=0.04,
        hit_delta_count=-2,
        roi_delta=-0.02,
        warnings=["budget_stability:test_warning"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_budget_stability_audit=True,
            min_budget_stability_slice_count=240,
            min_budget_stability_comparable_count=240,
            max_budget_stability_signature_change_rate=0.02,
            max_budget_stability_harmful_change_count=2,
            min_budget_stability_hit_delta_count=-1,
            min_budget_stability_roi_delta=-0.005,
            max_budget_stability_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        budget_stability_audit=audit,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "budget_stability_signature_change_rate",
        "budget_stability_harmful_change_count",
        "budget_stability_hit_delta_count",
        "budget_stability_roi_delta",
        "budget_stability_warning_count",
    }.issubset(failed_checks)


def test_quality_gate_blocks_missing_required_budget_stability_audit() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_budget_stability_audit=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert failed_checks == {"budget_stability_audit_present"}
    assert result.summary_json["budget_stability_audit_present"] is False


def test_quality_gate_consumes_final_answer_market_concentration_audit() -> None:
    latest = _benchmark_run(history_status="unchanged")
    audit = _final_answer_market_concentration_audit_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_market_concentration_audit=True,
            min_final_answer_market_concentration_slice_count=5,
            min_final_answer_market_concentration_dynamic_mixed_final_answer_count=5,
            min_final_answer_market_concentration_effective_constraint_profile_count=2,
            max_final_answer_market_concentration_failed_check_count=0,
            max_final_answer_market_concentration_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        final_answer_market_concentration_audit=audit,
    )

    assert result.passed is True
    assert result.final_answer_market_concentration_audit_present is True
    assert result.final_answer_market_concentration_audit_passed is True
    assert result.summary_json["final_answer_market_concentration_audit_key"] == (
        "historical_final_answer_market_concentration_audit:test"
    )
    assert result.summary_json["final_answer_market_concentration_slice_count"] == 5
    assert (
        result.summary_json[
            "final_answer_market_concentration_dynamic_mixed_final_answer_count"
        ]
        == 5
    )
    assert result.summary_json[
        "final_answer_market_concentration_effective_pass_types"
    ] == ["2x1", "3x1"]
    assert (
        result.summary_json[
            "final_answer_market_concentration_effective_constraint_profile_count"
        ]
        == 2
    )
    assert result.summary_json[
        "final_answer_market_concentration_candidate_completed_dynamic_mix_lane_count"
    ] == 10
    assert {
        check.name
        for check in result.checks
        if check.name.startswith("final_answer_market_concentration")
    } >= {
        "final_answer_market_concentration_audit_present",
        "final_answer_market_concentration_audit_passed",
        "final_answer_market_concentration_slice_count",
        "final_answer_market_concentration_dynamic_mixed_final_answer_count",
        "final_answer_market_concentration_effective_constraint_profile_count",
    }


def test_quality_gate_blocks_missing_required_final_answer_market_concentration_audit() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_market_concentration_audit=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert failed_checks == {"final_answer_market_concentration_audit_present"}
    assert (
        result.summary_json["final_answer_market_concentration_audit_present"]
        is False
    )


def test_quality_gate_blocks_final_answer_market_concentration_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")
    audit = _final_answer_market_concentration_audit_report(
        status="failed",
        passed=False,
        slice_count=4,
        dynamic_mixed_final_answer_count=1,
        effective_constraint_profile_count=1,
        failed_checks=["dynamic_mixed_final_answer_count"],
        warnings=["final_answer_market_concentration:test_warning"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_market_concentration_audit=True,
            min_final_answer_market_concentration_slice_count=5,
            min_final_answer_market_concentration_dynamic_mixed_final_answer_count=5,
            min_final_answer_market_concentration_effective_constraint_profile_count=2,
            max_final_answer_market_concentration_failed_check_count=0,
            max_final_answer_market_concentration_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        final_answer_market_concentration_audit=audit,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "final_answer_market_concentration_audit_passed",
        "final_answer_market_concentration_audit_status",
        "final_answer_market_concentration_slice_count",
        "final_answer_market_concentration_dynamic_mixed_final_answer_count",
        "final_answer_market_concentration_effective_constraint_profile_count",
        "final_answer_market_concentration_failed_check_count",
        "final_answer_market_concentration_warning_count",
    }.issubset(failed_checks)


def test_quality_gate_consumes_correct_score_admission_holdout() -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission = _correct_score_admission_report(
        status="holdout_only",
        production_allowed=False,
        holdout_allowed=True,
        correct_score_count=0,
        failed_checks=["candidate_correct_score_final_answer_count"],
        warnings=[
            "correct_score_admission:failed_check:candidate_correct_score_final_answer_count",
            "correct_score_admission:holdout_only",
        ],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_correct_score_admission=True,
            min_correct_score_admission_slice_count=10,
            min_correct_score_admission_comparison_count=10,
            min_correct_score_admission_candidate_final_hit_sample_size=10,
            min_correct_score_admission_candidate_final_hit_coverage_ratio=1.0,
            min_correct_score_admission_candidate_roi=0.0,
            min_correct_score_admission_candidate_correct_score_final_answer_count=0,
            min_correct_score_admission_final_hit_rate_delta=0.0,
            min_correct_score_admission_roi_delta=0.0,
            min_correct_score_admission_profit_loss_delta=0.0,
            max_correct_score_admission_brier_score_delta=0.0,
            max_correct_score_admission_log_loss_delta=0.0,
            max_correct_score_admission_mean_calibration_error_delta=0.0,
            max_correct_score_admission_failed_check_count=None,
            max_correct_score_admission_warning_count=None,
        ),
        repository=FakeQualityGateRepository([latest]),
        correct_score_admission=admission,
    )

    assert result.passed is True
    assert result.correct_score_admission_present is True
    assert result.correct_score_admission_status == "holdout_only"
    assert result.correct_score_admission_holdout_allowed is True
    assert result.correct_score_admission_production_allowed is False
    assert result.summary_json["correct_score_admission_key"] == (
        "historical_correct_score_admission:test"
    )
    assert (
        result.summary_json[
            "correct_score_admission_candidate_correct_score_final_answer_count"
        ]
        == 0
    )
    assert result.summary_json["correct_score_admission_roi_delta"] == 0.01
    assert result.summary_json["correct_score_admission_failed_check_count"] == 1


def test_quality_gate_blocks_correct_score_admission_when_production_required() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_correct_score_admission=True,
            require_correct_score_admission_production_allowed=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        correct_score_admission=_correct_score_admission_report(
            status="holdout_only",
            production_allowed=False,
            holdout_allowed=True,
            correct_score_count=0,
            failed_checks=["candidate_correct_score_final_answer_count"],
        ),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert failed_checks == {"correct_score_admission_production_allowed"}


def test_quality_gate_loads_correct_score_admission_from_options(tmp_path) -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission_path = tmp_path / "correct_score_admission.json"
    admission_path.write_text(
        _correct_score_admission_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            correct_score_admission_report_path=admission_path,
            require_correct_score_admission=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.correct_score_admission_present is True
    assert result.summary_json["correct_score_admission_report_path"] == str(
        admission_path
    )


def test_quality_gate_consumes_runtime_profile_switch_evidence() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    switch = _runtime_profile_switch_report()
    replay = _runtime_profile_switch_replay_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_runtime_profile_switch_gate=True,
            min_runtime_profile_switch_rule_count=1,
            min_runtime_profile_switch_allowed_competition_count=4,
            min_runtime_profile_switch_final_answer_count=30,
            min_runtime_profile_switch_changed_final_answer_count=5,
        ),
        repository=FakeQualityGateRepository([latest]),
        runtime_profile_switch_gate=switch,
        runtime_profile_switch_replay=replay,
    )

    assert result.passed is True
    assert result.runtime_profile_switch_gate_present is True
    assert result.runtime_profile_switch_gate_switch_ready is True
    assert result.runtime_profile_switch_replay_present is True
    assert result.runtime_profile_switch_replay_passed is True
    assert result.summary_json["runtime_profile_switch_key"] == (
        "historical_short_odds_runtime_profile_switch:test"
    )
    assert result.summary_json["runtime_profile_switch_rule_count"] == 1
    assert result.summary_json["runtime_profile_switch_replay_final_answer_count"] == 30


def test_quality_gate_blocks_missing_required_runtime_profile_switch_evidence() -> None:
    latest = _benchmark_run()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_runtime_profile_switch_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert failed_checks == {"runtime_profile_switch_gate_present"}
    assert result.summary_json["runtime_profile_switch_gate_present"] is False


def test_quality_gate_blocks_runtime_profile_switch_replay_regression() -> None:
    latest = _benchmark_run()
    replay = _runtime_profile_switch_replay_report(
        passed=False,
        final_answer_hit_rate_delta=-0.01,
        roi_delta=-0.02,
        profit_loss_delta=-1.0,
        harm_count_vs_original=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_runtime_profile_switch_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        runtime_profile_switch_gate=_runtime_profile_switch_report(),
        runtime_profile_switch_replay=replay,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert {
        "runtime_profile_switch_replay_passed",
        "runtime_profile_switch_replay_status_passed",
        "runtime_profile_switch_replay_final_answer_hit_rate_delta",
        "runtime_profile_switch_replay_roi_delta",
        "runtime_profile_switch_replay_profit_loss_delta",
        "runtime_profile_switch_replay_harm_count_vs_original",
    }.issubset(failed_checks)


def test_quality_gate_blocks_runtime_profile_switch_explicit_harm() -> None:
    latest = _benchmark_run()
    replay = _runtime_profile_switch_replay_report(
        final_hit_harm_count_vs_original=1,
        profit_loss_harm_count_vs_original=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_runtime_profile_switch_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        runtime_profile_switch_gate=_runtime_profile_switch_report(),
        runtime_profile_switch_replay=replay,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert {
        "runtime_profile_switch_replay_final_hit_harm_count_vs_original",
        "runtime_profile_switch_replay_profit_loss_harm_count_vs_original",
    }.issubset(failed_checks)


def test_quality_gate_loads_runtime_profile_switch_reports_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run()
    switch_path = tmp_path / "switch.json"
    replay_path = tmp_path / "replay.json"
    switch_path.write_text(
        _runtime_profile_switch_report().model_dump_json(),
        encoding="utf-8",
    )
    replay_path.write_text(
        _runtime_profile_switch_replay_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            runtime_profile_switch_report_path=switch_path,
            runtime_profile_switch_replay_report_path=replay_path,
            require_runtime_profile_switch_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json["runtime_profile_switch_report_path"] == str(
        switch_path
    )
    assert result.summary_json["runtime_profile_switch_replay_report_path"] == str(
        replay_path
    )


def test_quality_gate_consumes_final_answer_segment_penalty_runtime_replay() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    replay = _segment_penalty_runtime_replay_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_segment_penalty_runtime_replay=True,
            min_final_answer_segment_penalty_runtime_replay_final_answer_count=30,
            min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count=2,
            min_final_answer_segment_penalty_runtime_replay_penalty_option_count=2,
        ),
        repository=FakeQualityGateRepository([latest]),
        final_answer_segment_penalty_runtime_replay=replay,
    )

    assert result.passed is True
    assert result.final_answer_segment_penalty_runtime_replay_present is True
    assert (
        result.final_answer_segment_penalty_runtime_replay_holdout_allowed is True
    )
    assert (
        result.final_answer_segment_penalty_runtime_replay_runtime_allowed is False
    )
    assert result.summary_json[
        "final_answer_segment_penalty_runtime_replay_key"
    ] == "historical_final_answer_segment_penalty_runtime_replay:test"
    assert (
        result.summary_json[
            "final_answer_segment_penalty_runtime_replay_failed_checks"
        ]
        == ["candidate_roi"]
    )


def test_quality_gate_blocks_segment_penalty_runtime_replay_regression() -> None:
    latest = _benchmark_run()
    replay = _segment_penalty_runtime_replay_report(
        holdout_replay_allowed=False,
        final_answer_hit_rate_delta=-0.01,
        roi_delta=-0.02,
        profit_loss_delta=-1.0,
        harm_count_vs_baseline=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_segment_penalty_runtime_replay=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        final_answer_segment_penalty_runtime_replay=replay,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert {
        "final_answer_segment_penalty_runtime_replay_holdout_allowed",
        "final_answer_segment_penalty_runtime_replay_hit_rate_delta",
        "final_answer_segment_penalty_runtime_replay_roi_delta",
        "final_answer_segment_penalty_runtime_replay_profit_loss_delta",
        "final_answer_segment_penalty_runtime_replay_harm_count",
    }.issubset(failed_checks)


def test_quality_gate_blocks_segment_penalty_runtime_replay_profit_loss_harm() -> None:
    latest = _benchmark_run()
    replay = _segment_penalty_runtime_replay_report(
        harm_count_vs_baseline=0,
        final_hit_harm_count_vs_baseline=0,
        profit_loss_harm_count_vs_baseline=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_final_answer_segment_penalty_runtime_replay=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        final_answer_segment_penalty_runtime_replay=replay,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert "final_answer_segment_penalty_runtime_replay_harm_count" not in failed_checks
    assert (
        "final_answer_segment_penalty_runtime_replay_final_hit_harm_count"
        not in failed_checks
    )
    assert (
        "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count"
        in failed_checks
    )
    assert (
        result.summary_json[
            "final_answer_segment_penalty_runtime_replay_profit_loss_harm_count"
        ]
        == 1
    )


def test_quality_gate_loads_segment_penalty_runtime_replay_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run()
    replay_path = tmp_path / "segment_replay.json"
    replay_path.write_text(
        _segment_penalty_runtime_replay_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            final_answer_segment_penalty_runtime_replay_report_path=replay_path,
            require_final_answer_segment_penalty_runtime_replay=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "final_answer_segment_penalty_runtime_replay_report_path"
    ] == str(replay_path)


def test_quality_gate_consumes_market_movement_runtime_activation() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    activation = _market_movement_runtime_activation_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation=True,
            min_market_movement_runtime_activation_rule_count=1,
            min_market_movement_runtime_activation_selected_rule_count=1,
            min_market_movement_runtime_activation_adjusted_fixture_count=120,
            min_market_movement_runtime_activation_adjusted_prediction_count=360,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation=activation,
    )

    assert result.passed is True
    assert result.market_movement_runtime_activation_present is True
    assert result.market_movement_runtime_activation_ready is True
    assert (
        result.summary_json["market_movement_runtime_activation_key"]
        == "historical_market_movement_runtime_activation:test"
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


def test_quality_gate_blocks_missing_market_movement_runtime_activation() -> None:
    latest = _benchmark_run()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation=True,
            min_market_movement_runtime_activation_rule_count=1,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert "market_movement_runtime_activation_present" in failed_checks


def test_quality_gate_blocks_harmful_market_movement_runtime_activation() -> None:
    latest = _benchmark_run()
    activation = _market_movement_runtime_activation_report(
        status="blocked",
        staged_activation_ready=False,
        final_hit_rate_delta=-0.01,
        roi_delta=-0.02,
        profit_loss_delta=-1.0,
        brier_score_delta=0.01,
        log_loss_delta=0.02,
        mean_calibration_error_delta=0.03,
        default_profile_written=True,
        default_recommendation_path_changed=True,
        production_recommendation_changed=True,
        public_response_changed=True,
        blockers=["brier_score_delta"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation=activation,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert {
        "market_movement_runtime_activation_ready",
        "market_movement_runtime_activation_status_ready",
        "market_movement_runtime_activation_no_blockers",
        "market_movement_runtime_activation_final_hit_rate_delta",
        "market_movement_runtime_activation_roi_delta",
        "market_movement_runtime_activation_profit_loss_delta",
        "market_movement_runtime_activation_brier_score_delta",
        "market_movement_runtime_activation_log_loss_delta",
        "market_movement_runtime_activation_calibration_delta",
        "market_movement_runtime_activation_default_profile_not_written",
        "market_movement_runtime_activation_default_path_unchanged",
        "market_movement_runtime_activation_production_unchanged",
        "market_movement_runtime_activation_public_unchanged",
    }.issubset(failed_checks)
    assert result.summary_json[
        "market_movement_runtime_activation_blockers"
    ] == ["brier_score_delta"]


def test_quality_gate_loads_market_movement_runtime_activation_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run()
    activation_path = tmp_path / "activation.json"
    activation_path.write_text(
        _market_movement_runtime_activation_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            market_movement_runtime_activation_report_path=activation_path,
            require_market_movement_runtime_activation=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "market_movement_runtime_activation_report_path"
    ] == str(activation_path)


def test_quality_gate_consumes_market_movement_activation_sample_expansion() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    expansion = _market_movement_activation_sample_expansion_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation_sample_expansion=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation_sample_expansion=expansion,
    )

    assert result.passed is True
    assert result.market_movement_runtime_activation_sample_expansion_present is True
    assert result.market_movement_runtime_activation_sample_expansion_passed is True
    assert (
        result.market_movement_runtime_activation_sample_expansion_promotion_ready
        is False
    )
    assert (
        result.summary_json["market_movement_activation_sample_expansion_status"]
        == "shadow_only"
    )
    assert (
        result.summary_json[
            "market_movement_activation_sample_expansion_combined_fixture_count"
        ]
        == 3120
    )
    assert result.summary_json[
        "market_movement_activation_sample_expansion_watchlist"
    ] == ["selected_segment_count_for_promotion"]


def test_quality_gate_blocks_market_movement_activation_sample_expansion_promotion() -> None:
    latest = _benchmark_run()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation_sample_expansion=True,
            require_market_movement_runtime_activation_sample_expansion_promotion_ready=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation_sample_expansion=(
            _market_movement_activation_sample_expansion_report()
        ),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert (
        "market_movement_activation_sample_expansion_promotion_ready"
        in failed_checks
    )


def test_quality_gate_consumes_market_movement_segment_replay_batch_gate() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    batch_gate = _market_movement_segment_replay_batch_gate_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation_segment_replay_batch_gate=True,
            min_market_movement_runtime_activation_segment_replay_batch_report_count=4,
            min_market_movement_runtime_activation_segment_replay_batch_passed_count=4,
            min_market_movement_runtime_activation_segment_replay_batch_adjusted_fixture_count=1200,
            min_market_movement_runtime_activation_segment_replay_batch_adjusted_prediction_count=3600,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation_segment_replay_batch_gate=batch_gate,
    )

    assert result.passed is True
    assert (
        result.market_movement_runtime_activation_segment_replay_batch_gate_present
        is True
    )
    assert result.market_movement_runtime_activation_segment_replay_batch_ready is True
    assert (
        result.market_movement_runtime_activation_segment_replay_batch_promotion_ready
        is False
    )
    assert (
        result.summary_json["market_movement_segment_replay_batch_adjusted_fixture_count"]
        == 1323
    )
    assert (
        result.summary_json["market_movement_segment_replay_batch_watchlist"]
        == ["segment_expansion_production_promotion_ready"]
    )


def test_quality_gate_blocks_market_movement_segment_replay_batch_promotion() -> None:
    latest = _benchmark_run()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_market_movement_runtime_activation_segment_replay_batch_gate=True,
            require_market_movement_runtime_activation_segment_replay_batch_promotion_ready=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        market_movement_runtime_activation_segment_replay_batch_gate=(
            _market_movement_segment_replay_batch_gate_report()
        ),
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }
    assert result.passed is False
    assert "market_movement_segment_replay_batch_promotion_ready" in failed_checks


def test_quality_gate_consumes_replacement_reranker_shadow_admission() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    admission = _replacement_reranker_shadow_admission_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_replacement_reranker_shadow_admission=True,
            require_replacement_reranker_scoped_evidence=True,
            require_replacement_reranker_prematch_source_surface=True,
            min_replacement_reranker_scope_final_answer_count=19,
            min_replacement_reranker_shadow_final_answer_count=17,
            min_replacement_reranker_changed_from_model_top_count=5,
            min_replacement_reranker_hit_delta_vs_model_top=1,
            min_replacement_reranker_profit_loss_delta_vs_model_top=4.0,
            min_replacement_reranker_roi_delta_vs_model_top=0.10,
            max_replacement_reranker_harm_count_vs_model_top=0,
            max_replacement_reranker_final_hit_harm_count_vs_model_top=0,
            max_replacement_reranker_profit_loss_harm_count_vs_model_top=0,
            max_replacement_reranker_failed_fold_count=0,
            min_replacement_reranker_active_competition_fold_count=2,
            min_replacement_reranker_active_season_fold_count=3,
            min_replacement_reranker_active_rolling_fold_count=4,
        ),
        repository=FakeQualityGateRepository([latest]),
        replacement_reranker_shadow_admission=admission,
    )

    assert result.passed is True
    assert result.replacement_reranker_shadow_admission_present is True
    assert (
        result.replacement_reranker_shadow_admission_runtime_candidate_allowed
        is True
    )
    assert result.replacement_reranker_shadow_admission_shadow_allowed is True
    assert result.summary_json["replacement_reranker_shadow_admission_key"] == (
        "historical_replacement_reranker_shadow_admission:test"
    )
    assert (
        result.summary_json["replacement_reranker_source_surface_kind"]
        == "prematch_replacement_surface"
    )
    assert (
        result.summary_json["replacement_reranker_source_surface_missed_legs_only"]
        is False
    )
    assert result.summary_json["replacement_reranker_source_surface_selected_leg_count"] == 27
    assert (
        result.summary_json[
            "replacement_reranker_shadow_admission_scope_final_answer_count"
        ]
        == 19
    )
    assert (
        result.summary_json["replacement_reranker_final_hit_harm_count_vs_model_top"]
        == 0
    )
    assert (
        result.summary_json["replacement_reranker_profit_loss_harm_count_vs_model_top"]
        == 0
    )


def test_quality_gate_blocks_replacement_reranker_missed_leg_source_surface() -> None:
    latest = _benchmark_run()
    admission = _replacement_reranker_shadow_admission_report(
        source_surface_kind="missed_leg_diagnostic_surface",
        source_surface_missed_legs_only=True,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_replacement_reranker_shadow_admission=True,
            require_replacement_reranker_prematch_source_surface=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        replacement_reranker_shadow_admission=admission,
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "replacement_reranker_prematch_source_surface" in failed_checks
    assert (
        result.summary_json["replacement_reranker_source_surface_kind"]
        == "missed_leg_diagnostic_surface"
    )
    assert (
        result.summary_json["replacement_reranker_source_surface_missed_legs_only"]
        is True
    )


def test_quality_gate_blocks_replacement_reranker_explicit_harm() -> None:
    latest = _benchmark_run()
    admission = _replacement_reranker_shadow_admission_report(
        final_hit_harm_count_vs_model_top=1,
        profit_loss_harm_count_vs_model_top=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_replacement_reranker_shadow_admission=True,
            max_replacement_reranker_harm_count_vs_model_top=0,
            max_replacement_reranker_final_hit_harm_count_vs_model_top=0,
            max_replacement_reranker_profit_loss_harm_count_vs_model_top=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        replacement_reranker_shadow_admission=admission,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert "replacement_reranker_final_hit_harm_count_vs_model_top" in failed_checks
    assert "replacement_reranker_profit_loss_harm_count_vs_model_top" in failed_checks


def test_quality_gate_blocks_replacement_reranker_shadow_admission_regression() -> None:
    latest = _benchmark_run()
    admission = _replacement_reranker_shadow_admission_report(
        status="shadow_only",
        runtime_profile_candidate_allowed=False,
        failed_fold_count=1,
        hit_delta_vs_model_top=-1,
        profit_loss_delta_vs_model_top=-2.0,
        harm_count_vs_model_top=1,
        scoped=False,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_replacement_reranker_shadow_admission=True,
            require_replacement_reranker_scoped_evidence=True,
            min_replacement_reranker_hit_delta_vs_model_top=0,
            min_replacement_reranker_profit_loss_delta_vs_model_top=0.0,
            max_replacement_reranker_harm_count_vs_model_top=0,
            max_replacement_reranker_failed_fold_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        replacement_reranker_shadow_admission=admission,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "replacement_reranker_shadow_admission_accepted",
        "replacement_reranker_shadow_admission_runtime_candidate_allowed",
        "replacement_reranker_shadow_admission_scoped",
        "replacement_reranker_hit_delta_vs_model_top",
        "replacement_reranker_profit_loss_delta_vs_model_top",
        "replacement_reranker_harm_count_vs_model_top",
        "replacement_reranker_failed_fold_count",
    }.issubset(failed_checks)


def test_quality_gate_loads_replacement_reranker_shadow_admission_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run()
    admission_path = tmp_path / "replacement_admission.json"
    admission_path.write_text(
        _replacement_reranker_shadow_admission_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            replacement_reranker_shadow_admission_report_path=admission_path,
            require_replacement_reranker_shadow_admission=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "replacement_reranker_shadow_admission_report_path"
    ] == str(admission_path)


def test_quality_gate_consumes_global_planner_short_odds_adapter_gate() -> None:
    latest = _benchmark_run(
        scenario_count=3,
        completed_count=3,
        final_hit_sample_size=3,
        final_hit_count=2,
        history_status="unchanged",
    )
    adapter_gate = _global_planner_short_odds_adapter_gate_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_global_planner_short_odds_adapter_gate=True,
            min_global_planner_short_odds_adapter_runtime_final_answer_count=30,
            min_global_planner_short_odds_adapter_runtime_changed_final_answer_count=5,
        ),
        repository=FakeQualityGateRepository([latest]),
        global_planner_short_odds_adapter_gate=adapter_gate,
    )

    assert result.passed is True
    assert result.global_planner_short_odds_adapter_gate_present is True
    assert result.global_planner_short_odds_adapter_gate_passed is True
    assert result.summary_json["global_planner_short_odds_adapter_gate_key"] == (
        "global_planner_short_odds_adapter_gate:test"
    )
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


def test_quality_gate_blocks_global_planner_short_odds_adapter_gate_regression() -> None:
    latest = _benchmark_run()
    adapter_gate = _global_planner_short_odds_adapter_gate_report(
        passed=False,
        default_path_changed=True,
        shadow_path_changed=True,
        explicit_opt_in_changed=False,
        roi_delta=-0.01,
        final_hit_harm_count=1,
        profit_loss_harm_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_global_planner_short_odds_adapter_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        global_planner_short_odds_adapter_gate=adapter_gate,
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert {
        "global_planner_short_odds_adapter_gate_passed",
        "global_planner_short_odds_adapter_gate_status_passed",
        "global_planner_short_odds_adapter_default_path_unchanged",
        "global_planner_short_odds_adapter_shadow_path_unchanged",
        "global_planner_short_odds_adapter_explicit_opt_in_changed",
        "global_planner_short_odds_adapter_runtime_roi_delta",
        "global_planner_short_odds_adapter_runtime_final_hit_harm_count",
        "global_planner_short_odds_adapter_runtime_profit_loss_harm_count",
    }.issubset(failed_checks)


def test_quality_gate_loads_global_planner_short_odds_adapter_gate_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run()
    gate_path = tmp_path / "global_planner_adapter_gate.json"
    gate_path.write_text(
        _global_planner_short_odds_adapter_gate_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            global_planner_short_odds_adapter_gate_report_path=gate_path,
            require_global_planner_short_odds_adapter_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "global_planner_short_odds_adapter_gate_report_path"
    ] == str(gate_path)


def test_quality_gate_consumes_global_planner_short_odds_sample_expansion() -> None:
    latest = _benchmark_run(history_status="unchanged")
    expansion = _global_planner_short_odds_adapter_sample_expansion_report(
        status="research_only",
        promotion_ready=False,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_global_planner_short_odds_adapter_sample_expansion=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        global_planner_short_odds_adapter_sample_expansion=expansion,
    )

    assert result.passed is True
    assert (
        result.global_planner_short_odds_adapter_sample_expansion_present is True
    )
    assert result.global_planner_short_odds_adapter_sample_expansion_passed is True
    assert (
        result.global_planner_short_odds_adapter_sample_expansion_promotion_ready
        is False
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_status"
        ]
        == "research_only"
    )
    assert (
        result.summary_json[
            "global_planner_short_odds_adapter_sample_expansion_watchlist_checks"
        ]
        == ["supplemental_changed_final_answer_count"]
    )


def test_quality_gate_can_require_global_planner_short_odds_sample_promotion_ready() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_global_planner_short_odds_adapter_sample_expansion=True,
            require_global_planner_short_odds_adapter_sample_expansion_promotion_ready=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        global_planner_short_odds_adapter_sample_expansion=(
            _global_planner_short_odds_adapter_sample_expansion_report(
                status="research_only",
                promotion_ready=False,
            )
        ),
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert (
        "global_planner_short_odds_adapter_sample_expansion_promotion_ready"
        in failed_checks
    )


def test_quality_gate_blocks_global_planner_short_odds_sample_expansion_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_global_planner_short_odds_adapter_sample_expansion=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        global_planner_short_odds_adapter_sample_expansion=(
            _global_planner_short_odds_adapter_sample_expansion_report(
                status="blocked",
                passed=False,
                promotion_ready=False,
            )
        ),
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert {
        "global_planner_short_odds_adapter_sample_expansion_passed",
        "global_planner_short_odds_adapter_sample_expansion_not_blocked",
    }.issubset(failed_checks)


def test_quality_gate_loads_global_planner_short_odds_sample_expansion_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    expansion_path = tmp_path / "sample_expansion.json"
    expansion_path.write_text(
        _global_planner_short_odds_adapter_sample_expansion_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            global_planner_short_odds_adapter_sample_expansion_report_path=(
                expansion_path
            ),
            require_global_planner_short_odds_adapter_sample_expansion=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "global_planner_short_odds_adapter_sample_expansion_report_path"
    ] == str(expansion_path)


def test_quality_gate_consumes_recommendation_strategy_governance_bundle() -> None:
    latest = _benchmark_run(history_status="unchanged")
    promotion_gate = _recommendation_strategy_promotion_gate_report()
    staged_smoke = _recommendation_strategy_staged_activation_smoke_report()
    isolation = _recommendation_strategy_default_path_isolation_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_recommendation_strategy_promotion_gate=True,
            require_recommendation_strategy_staged_activation_smoke=True,
            require_recommendation_strategy_default_path_isolation=True,
            min_recommendation_strategy_gate_final_answer_count=90,
            min_recommendation_strategy_gate_changed_final_answer_count=13,
            min_recommendation_strategy_staged_allowed_competition_count=5,
        ),
        repository=FakeQualityGateRepository([latest]),
        recommendation_strategy_promotion_gate=promotion_gate,
        recommendation_strategy_staged_activation_smoke=staged_smoke,
        recommendation_strategy_default_path_isolation=isolation,
    )

    assert result.passed is True
    assert result.recommendation_strategy_promotion_gate_present is True
    assert result.recommendation_strategy_promotion_gate_ready is True
    assert result.recommendation_strategy_staged_activation_smoke_present is True
    assert result.recommendation_strategy_staged_activation_ready is True
    assert result.recommendation_strategy_default_path_isolation_present is True
    assert result.recommendation_strategy_default_path_isolated is True
    assert result.summary_json["recommendation_strategy_promotion_gate_key"] == (
        "recommendation_strategy_promotion_gate:test"
    )
    assert result.summary_json["recommendation_strategy_staged_rule_count"] == 1
    assert (
        result.summary_json["recommendation_strategy_default_adapter_status"]
        == "disabled"
    )
    assert (
        result.summary_json["recommendation_strategy_explicit_opt_in_selection_changed"]
        is True
    )


def test_quality_gate_blocks_recommendation_strategy_governance_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_recommendation_strategy_promotion_gate=True,
            require_recommendation_strategy_staged_activation_smoke=True,
            require_recommendation_strategy_default_path_isolation=True,
        ),
        repository=FakeQualityGateRepository([latest]),
        recommendation_strategy_promotion_gate=(
            _recommendation_strategy_promotion_gate_report(
                status="blocked",
                strategy_gate_ready=False,
                total_final_answer_hit_delta_count=-1,
                total_profit_loss_delta=-1.5,
                minimum_roi_delta=-0.01,
                total_final_hit_harm_count_vs_original=1,
                production_recommendation_changed=True,
                public_response_changed=True,
                blockers=["strategy_gate_ready"],
            )
        ),
        recommendation_strategy_staged_activation_smoke=(
            _recommendation_strategy_staged_activation_smoke_report(
                status="blocked",
                staged_activation_ready=False,
                selected_rule_count=0,
                allowed_competition_ids=[],
                default_profile_written=True,
                production_recommendation_changed=True,
                public_response_changed=True,
                blockers=["default_profile_written"],
            )
        ),
        recommendation_strategy_default_path_isolation=(
            _recommendation_strategy_default_path_isolation_report(
                status="blocked",
                default_path_isolated=False,
                default_adapter_status="applied",
                default_adapter_selection_changed=True,
                default_adapter_default_path_changed=True,
                default_adapter_public_response_changed=True,
                explicit_opt_in_adapter_status="disabled",
                explicit_opt_in_selection_changed=False,
                explicit_opt_in_default_path_changed=True,
                explicit_opt_in_public_response_changed=True,
                default_profile_written=True,
                production_recommendation_changed=True,
                public_response_changed=True,
                blockers=["default_adapter_selection_changed"],
            )
        ),
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert {
        "recommendation_strategy_promotion_gate_ready",
        "recommendation_strategy_promotion_gate_status_ready",
        "recommendation_strategy_promotion_gate_hit_delta_count",
        "recommendation_strategy_promotion_gate_final_hit_harm_count",
        "recommendation_strategy_promotion_gate_production_unchanged",
        "recommendation_strategy_staged_activation_ready",
        "recommendation_strategy_staged_default_profile_not_written",
        "recommendation_strategy_default_path_isolated",
        "recommendation_strategy_default_adapter_disabled",
        "recommendation_strategy_default_adapter_selection_unchanged",
        "recommendation_strategy_explicit_opt_in_applied",
        "recommendation_strategy_isolation_default_profile_not_written",
    }.issubset(failed_checks)


def test_quality_gate_loads_recommendation_strategy_governance_bundle_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    promotion_path = tmp_path / "strategy_promotion_gate.json"
    staged_path = tmp_path / "staged_activation_smoke.json"
    isolation_path = tmp_path / "default_path_isolation.json"
    promotion_path.write_text(
        _recommendation_strategy_promotion_gate_report().model_dump_json(),
        encoding="utf-8",
    )
    staged_path.write_text(
        _recommendation_strategy_staged_activation_smoke_report().model_dump_json(),
        encoding="utf-8",
    )
    isolation_path.write_text(
        _recommendation_strategy_default_path_isolation_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            recommendation_strategy_promotion_gate_report_path=promotion_path,
            recommendation_strategy_staged_activation_smoke_report_path=staged_path,
            recommendation_strategy_default_path_isolation_report_path=isolation_path,
            require_recommendation_strategy_promotion_gate=True,
            require_recommendation_strategy_staged_activation_smoke=True,
            require_recommendation_strategy_default_path_isolation=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "recommendation_strategy_promotion_gate_report_path"
    ] == str(promotion_path)
    assert result.summary_json[
        "recommendation_strategy_staged_activation_smoke_report_path"
    ] == str(staged_path)
    assert result.summary_json[
        "recommendation_strategy_default_path_isolation_report_path"
    ] == str(isolation_path)


def test_quality_gate_consumes_probability_calibration_profile_rolling_admission() -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission = _probability_calibration_profile_rolling_admission_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_probability_calibration_profile_rolling_admission=True,
            min_probability_calibration_profile_overall_adjusted_fixture_count=24,
            min_probability_calibration_profile_overall_bucket_count=3,
            max_probability_calibration_profile_failed_fold_count=0,
            min_probability_calibration_profile_active_competition_fold_count=2,
            min_probability_calibration_profile_active_season_cutoff_fold_count=3,
            min_probability_calibration_profile_active_rolling_fold_count=2,
        ),
        repository=FakeQualityGateRepository([latest]),
        probability_calibration_profile_rolling_admission=admission,
    )

    assert result.passed is True
    assert result.probability_calibration_profile_rolling_admission_present is True
    assert (
        result.probability_calibration_profile_rolling_admission_candidate_allowed
        is True
    )
    assert (
        result.summary_json["probability_calibration_profile_rolling_admission_key"]
        == "historical_probability_calibration_profile_rolling_admission:test"
    )
    assert result.summary_json["probability_calibration_profile_mode"] == "active"
    assert (
        result.summary_json[
            "probability_calibration_profile_active_competition_fold_count"
        ]
        == 2
    )


def test_quality_gate_blocks_probability_calibration_profile_shadow_only() -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission = _probability_calibration_profile_rolling_admission_report(
        status="shadow_only",
        candidate_profile_allowed=False,
        profile_mode=None,
        failed_fold_count=1,
        active_competition_fold_count=1,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_probability_calibration_profile_rolling_admission=True,
            max_probability_calibration_profile_failed_fold_count=0,
            min_probability_calibration_profile_active_competition_fold_count=2,
        ),
        repository=FakeQualityGateRepository([latest]),
        probability_calibration_profile_rolling_admission=admission,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "probability_calibration_profile_rolling_admission_accepted",
        "probability_calibration_profile_rolling_admission_candidate_allowed",
        "probability_calibration_profile_rolling_admission_active_profile",
        "probability_calibration_profile_rolling_admission_failed_fold_count",
        "probability_calibration_profile_rolling_admission_active_competition_fold_count",
    }.issubset(failed_checks)


def test_quality_gate_loads_probability_calibration_profile_rolling_admission_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission_path = tmp_path / "probability_calibration_admission.json"
    admission_path.write_text(
        _probability_calibration_profile_rolling_admission_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            probability_calibration_profile_rolling_admission_report_path=(
                admission_path
            ),
            require_probability_calibration_profile_rolling_admission=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "probability_calibration_profile_rolling_admission_report_path"
    ] == str(admission_path)


def test_quality_gate_consumes_probability_calibration_profile_model_quality_gate() -> None:
    latest = _benchmark_run(history_status="unchanged")
    gate = _probability_calibration_profile_model_quality_gate_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_probability_calibration_profile_model_quality_gate=True,
            min_probability_calibration_profile_model_quality_selected_competition_count=4,
            min_probability_calibration_profile_model_quality_adjusted_slice_count=4,
            min_probability_calibration_profile_model_quality_adjusted_fixture_count=96,
            max_probability_calibration_profile_model_quality_skipped_fixture_count=0,
            max_probability_calibration_profile_model_quality_final_answer_changed_count=0,
            max_probability_calibration_profile_model_quality_brier_score_delta=0.0,
            max_probability_calibration_profile_model_quality_log_loss_delta=0.0,
            max_probability_calibration_profile_model_quality_calibration_error_delta=0.0,
        ),
        repository=FakeQualityGateRepository([latest]),
        probability_calibration_profile_model_quality_gate=gate,
    )

    assert result.passed is True
    assert result.probability_calibration_profile_model_quality_gate_present is True
    assert result.probability_calibration_profile_model_quality_gate_ready is True
    assert (
        result.summary_json[
            "probability_calibration_profile_model_quality_gate_status"
        ]
        == "model_quality_ready"
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


def test_quality_gate_blocks_probability_calibration_profile_model_quality_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")
    gate = _probability_calibration_profile_model_quality_gate_report(
        status="blocked",
        model_quality_gate_passed=False,
        selected_competition_ids=["EPL"],
        adjusted_slice_count=1,
        adjusted_fixture_count=12,
        skipped_fixture_count=3,
        final_answer_changed_count=2,
        final_answer_hit_count_delta=-1,
        final_answer_hit_rate_delta=-0.02,
        roi_delta=-0.03,
        profit_loss_delta=-1.5,
        brier_score_delta=0.01,
        log_loss_delta=0.02,
        mean_calibration_error_delta=0.03,
        failed_checks=["brier_score_delta"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_probability_calibration_profile_model_quality_gate=True,
            min_probability_calibration_profile_model_quality_selected_competition_count=4,
            min_probability_calibration_profile_model_quality_adjusted_slice_count=4,
            min_probability_calibration_profile_model_quality_adjusted_fixture_count=96,
            max_probability_calibration_profile_model_quality_skipped_fixture_count=0,
            max_probability_calibration_profile_model_quality_final_answer_changed_count=0,
            min_probability_calibration_profile_model_quality_final_answer_hit_count_delta=0,
            min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta=0.0,
            min_probability_calibration_profile_model_quality_roi_delta=0.0,
            min_probability_calibration_profile_model_quality_profit_loss_delta=0.0,
            max_probability_calibration_profile_model_quality_brier_score_delta=0.0,
            max_probability_calibration_profile_model_quality_log_loss_delta=0.0,
            max_probability_calibration_profile_model_quality_calibration_error_delta=0.0,
        ),
        repository=FakeQualityGateRepository([latest]),
        probability_calibration_profile_model_quality_gate=gate,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "probability_calibration_profile_model_quality_gate_ready",
        "probability_calibration_profile_model_quality_selected_competition_count",
        "probability_calibration_profile_model_quality_adjusted_slice_count",
        "probability_calibration_profile_model_quality_adjusted_fixture_count",
        "probability_calibration_profile_model_quality_skipped_fixture_count",
        "probability_calibration_profile_model_quality_final_answer_changed_count",
        "probability_calibration_profile_model_quality_final_answer_hit_count_delta",
        "probability_calibration_profile_model_quality_final_answer_hit_rate_delta",
        "probability_calibration_profile_model_quality_roi_delta",
        "probability_calibration_profile_model_quality_profit_loss_delta",
        "probability_calibration_profile_model_quality_brier_score_delta",
        "probability_calibration_profile_model_quality_log_loss_delta",
        "probability_calibration_profile_model_quality_calibration_error_delta",
    }.issubset(failed_checks)


def test_quality_gate_loads_probability_calibration_profile_model_quality_gate_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    gate_path = tmp_path / "probability_calibration_model_quality_gate.json"
    gate_path.write_text(
        _probability_calibration_profile_model_quality_gate_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            probability_calibration_profile_model_quality_gate_report_path=gate_path,
            require_probability_calibration_profile_model_quality_gate=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "probability_calibration_profile_model_quality_gate_report_path"
    ] == str(gate_path)


def test_quality_gate_consumes_asian_handicap_segmented_model_quality_governance() -> None:
    latest = _benchmark_run(history_status="unchanged")
    governance = _asian_handicap_segmented_model_quality_governance_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_asian_handicap_segmented_model_quality_governance=True,
            min_asian_handicap_segmented_model_quality_accepted_segment_count=3,
            max_asian_handicap_segmented_model_quality_shadow_segment_count=0,
            max_asian_handicap_segmented_model_quality_fallback_segment_count=2,
            max_asian_handicap_segmented_model_quality_rejected_segment_count=0,
            min_asian_handicap_segmented_model_quality_accepted_validation_count=100,
            min_asian_handicap_segmented_model_quality_calibration_applied_count=2,
            max_asian_handicap_segmented_model_quality_brier_score_delta=0.0,
            max_asian_handicap_segmented_model_quality_log_loss_delta=0.0,
            max_asian_handicap_segmented_model_quality_calibration_error_delta=0.0,
            min_asian_handicap_segmented_model_quality_actual_probability_delta=0.0,
        ),
        repository=FakeQualityGateRepository([latest]),
        asian_handicap_segmented_model_quality_governance=governance,
    )

    assert result.passed is True
    assert result.asian_handicap_segmented_model_quality_governance_present is True
    assert result.asian_handicap_segmented_model_quality_governance_ready is True
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_governance_status"
        ]
        == "governance_ready"
    )
    assert (
        result.summary_json[
            "asian_handicap_segmented_model_quality_accepted_validation_count"
        ]
        == 138
    )
    assert (
        result.summary_json["asian_handicap_segmented_model_quality_brier_score_delta"]
        == -0.001
    )


def test_quality_gate_blocks_asian_handicap_segmented_model_quality_regression() -> None:
    latest = _benchmark_run(history_status="unchanged")
    governance = _asian_handicap_segmented_model_quality_governance_report(
        status="watchlist",
        governance_review_ready=False,
        accepted_segment_count=1,
        fallback_segment_count=3,
        accepted_validation_count=42,
        calibration_sample_expansion_applied_count=0,
        brier_score_delta=0.001,
        log_loss_delta=0.002,
        calibration_error_delta=0.003,
        actual_probability_delta=-0.001,
        blockers=["accepted_segment_count"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_asian_handicap_segmented_model_quality_governance=True,
            min_asian_handicap_segmented_model_quality_accepted_segment_count=3,
            max_asian_handicap_segmented_model_quality_fallback_segment_count=2,
            min_asian_handicap_segmented_model_quality_accepted_validation_count=100,
            min_asian_handicap_segmented_model_quality_calibration_applied_count=2,
            max_asian_handicap_segmented_model_quality_brier_score_delta=0.0,
            max_asian_handicap_segmented_model_quality_log_loss_delta=0.0,
            max_asian_handicap_segmented_model_quality_calibration_error_delta=0.0,
            min_asian_handicap_segmented_model_quality_actual_probability_delta=0.0,
        ),
        repository=FakeQualityGateRepository([latest]),
        asian_handicap_segmented_model_quality_governance=governance,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "asian_handicap_segmented_model_quality_governance_ready",
        "asian_handicap_segmented_model_quality_accepted_segment_count",
        "asian_handicap_segmented_model_quality_fallback_segment_count",
        "asian_handicap_segmented_model_quality_accepted_validation_count",
        "asian_handicap_segmented_model_quality_calibration_applied_count",
        "asian_handicap_segmented_model_quality_brier_score_delta",
        "asian_handicap_segmented_model_quality_log_loss_delta",
        "asian_handicap_segmented_model_quality_calibration_error_delta",
        "asian_handicap_segmented_model_quality_actual_probability_delta",
    }.issubset(failed_checks)


def test_quality_gate_loads_asian_handicap_segmented_model_quality_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    governance_path = tmp_path / "asian_handicap_segmented_governance.json"
    governance_path.write_text(
        _asian_handicap_segmented_model_quality_governance_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            asian_handicap_segmented_model_quality_governance_report_path=(
                governance_path
            ),
            require_asian_handicap_segmented_model_quality_governance=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "asian_handicap_segmented_model_quality_governance_report_path"
    ] == str(governance_path)


def test_quality_gate_consumes_prematch_feature_quality_cycle() -> None:
    latest = _benchmark_run(history_status="unchanged")
    cycle = _prematch_feature_quality_cycle_result()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_quality_cycle=True,
            min_prematch_feature_quality_cycle_slice_count=25,
            min_prematch_feature_quality_cycle_fixture_count=600,
            min_prematch_feature_quality_cycle_evaluated_candidate_count=5,
            min_prematch_feature_quality_cycle_passing_candidate_count=1,
            max_prematch_feature_quality_cycle_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_quality_cycle=cycle,
    )

    assert result.passed is True
    assert result.prematch_feature_quality_cycle_present is True
    assert result.prematch_feature_quality_cycle_passed is True
    assert (
        result.summary_json["prematch_feature_quality_cycle_key"]
        == "historical_prematch_feature_quality_cycle:test"
    )
    assert result.summary_json["prematch_feature_quality_cycle_fixture_count"] == 600
    assert (
        result.summary_json[
            "prematch_feature_quality_cycle_best_feature_grid_candidate_id"
        ]
        == "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
    )


def test_quality_gate_blocks_failed_prematch_feature_quality_cycle() -> None:
    latest = _benchmark_run(history_status="unchanged")
    cycle = _prematch_feature_quality_cycle_result(
        passed=False,
        passing_candidate_count=0,
        best_quality_gate_passed=False,
        brier_score_delta=0.02,
        log_loss_delta=0.03,
        mean_calibration_error_delta=0.01,
        warnings=["prematch_feature_quality_cycle:no_passing_final_answer_candidate"],
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_quality_cycle=True,
            min_prematch_feature_quality_cycle_passing_candidate_count=1,
            max_prematch_feature_quality_cycle_warning_count=0,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_quality_cycle=cycle,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "prematch_feature_quality_cycle_passed",
        "prematch_feature_quality_cycle_best_gate_passed",
        "prematch_feature_quality_cycle_passing_candidate_count",
        "prematch_feature_quality_cycle_warning_count",
        "prematch_feature_quality_cycle_best_brier_score_delta",
        "prematch_feature_quality_cycle_best_log_loss_delta",
        "prematch_feature_quality_cycle_best_calibration_error_delta",
    }.issubset(failed_checks)


def test_quality_gate_loads_prematch_feature_quality_cycle_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    cycle_path = tmp_path / "prematch_feature_quality_cycle.json"
    cycle_path.write_text(
        _prematch_feature_quality_cycle_result().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            prematch_feature_quality_cycle_report_path=cycle_path,
            require_prematch_feature_quality_cycle=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json["prematch_feature_quality_cycle_report_path"] == str(
        cycle_path
    )


def test_quality_gate_consumes_prematch_feature_rolling_admission() -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission = _prematch_feature_rolling_admission_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_rolling_admission=True,
            min_prematch_feature_rolling_admission_overall_evaluated_candidate_count=5,
            min_prematch_feature_rolling_admission_overall_passing_candidate_count=1,
            max_prematch_feature_rolling_admission_failed_fold_count=0,
            min_prematch_feature_rolling_admission_active_competition_fold_count=2,
            min_prematch_feature_rolling_admission_active_season_cutoff_fold_count=3,
            min_prematch_feature_rolling_admission_active_rolling_fold_count=2,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_rolling_admission=admission,
    )

    assert result.passed is True
    assert result.prematch_feature_rolling_admission_present is True
    assert result.prematch_feature_rolling_admission_candidate_allowed is True
    assert (
        result.summary_json["prematch_feature_rolling_admission_key"]
        == "historical_prematch_feature_rolling_admission:test"
    )
    assert (
        result.summary_json[
            "prematch_feature_rolling_admission_best_feature_grid_candidate_id"
        ]
        == "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
    )
    assert (
        result.summary_json[
            "prematch_feature_rolling_admission_active_competition_fold_count"
        ]
        == 2
    )


def test_quality_gate_blocks_prematch_feature_rolling_admission_shadow_only() -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission = _prematch_feature_rolling_admission_report(
        status="shadow_only",
        candidate_feature_allowed=False,
        failed_fold_count=1,
        active_competition_fold_count=1,
        brier_score_delta=0.02,
        log_loss_delta=0.03,
        mean_calibration_error_delta=0.01,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_rolling_admission=True,
            max_prematch_feature_rolling_admission_failed_fold_count=0,
            min_prematch_feature_rolling_admission_active_competition_fold_count=2,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_rolling_admission=admission,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "prematch_feature_rolling_admission_accepted",
        "prematch_feature_rolling_admission_candidate_allowed",
        "prematch_feature_rolling_admission_failed_fold_count",
        "prematch_feature_rolling_admission_active_competition_fold_count",
        "prematch_feature_rolling_admission_overall_brier_score_delta",
        "prematch_feature_rolling_admission_overall_log_loss_delta",
        "prematch_feature_rolling_admission_overall_calibration_error_delta",
    }.issubset(failed_checks)


def test_quality_gate_loads_prematch_feature_rolling_admission_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    admission_path = tmp_path / "prematch_feature_rolling_admission.json"
    admission_path.write_text(
        _prematch_feature_rolling_admission_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            prematch_feature_rolling_admission_report_path=admission_path,
            require_prematch_feature_rolling_admission=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "prematch_feature_rolling_admission_report_path"
    ] == str(admission_path)


def test_quality_gate_consumes_prematch_feature_sample_readiness() -> None:
    latest = _benchmark_run(history_status="unchanged")
    readiness = _prematch_feature_sample_readiness_report()

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_sample_readiness=True,
            min_prematch_feature_sample_ready_source_count=1,
            min_prematch_feature_sample_ready_fixture_count=600,
            min_prematch_feature_sample_ready_competition_count=3,
            min_prematch_feature_sample_ready_season_count=2,
            min_prematch_feature_sample_ready_competition_season_count=3,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_sample_readiness=readiness,
    )

    assert result.passed is True
    assert result.prematch_feature_sample_readiness_present is True
    assert result.prematch_feature_sample_readiness_sample_ready_allowed is True
    assert result.summary_json["prematch_feature_sample_readiness_key"] == (
        "historical_prematch_feature_sample_readiness:test"
    )
    assert result.summary_json["prematch_feature_sample_ready_fixture_count"] == 600
    assert result.summary_json["prematch_feature_sample_readiness_target_profile"] == (
        "market_movement"
    )


def test_quality_gate_blocks_prematch_feature_sample_readiness_shadow_only() -> None:
    latest = _benchmark_run(history_status="unchanged")
    readiness = _prematch_feature_sample_readiness_report(
        status="shadow_only",
        sample_ready_allowed=False,
        accepted_source_count=0,
        ready_fixture_count=0,
        ready_competition_count=0,
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            require_prematch_feature_sample_readiness=True,
            min_prematch_feature_sample_ready_fixture_count=600,
            min_prematch_feature_sample_ready_competition_count=3,
        ),
        repository=FakeQualityGateRepository([latest]),
        prematch_feature_sample_readiness=readiness,
    )

    failed_checks = {
        check.name for check in result.checks if check.status == "failed"
    }

    assert result.passed is False
    assert {
        "prematch_feature_sample_readiness_accepted",
        "prematch_feature_sample_ready_allowed",
        "prematch_feature_sample_ready_source_count",
        "prematch_feature_sample_ready_fixture_count",
        "prematch_feature_sample_ready_competition_count",
    }.issubset(failed_checks)
    assert result.prematch_feature_sample_readiness_shadow_allowed is True


def test_quality_gate_loads_prematch_feature_sample_readiness_from_options(
    tmp_path,
) -> None:
    latest = _benchmark_run(history_status="unchanged")
    readiness_path = tmp_path / "prematch_feature_sample_readiness.json"
    readiness_path.write_text(
        _prematch_feature_sample_readiness_report().model_dump_json(),
        encoding="utf-8",
    )

    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(
            prematch_feature_sample_readiness_report_path=readiness_path,
            require_prematch_feature_sample_readiness=True,
        ),
        repository=FakeQualityGateRepository([latest]),
    )

    assert result.passed is True
    assert result.summary_json[
        "prematch_feature_sample_readiness_report_path"
    ] == str(readiness_path)


def test_quality_gate_handles_missing_history_strictly_by_default() -> None:
    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(),
        repository=FakeQualityGateRepository([]),
    )

    assert result.passed is False
    assert result.status == "insufficient_history"
    assert result.summary_json["history_count"] == 0
    assert result.warnings == ["benchmark_quality_gate:no_persisted_benchmark_history"]


def test_quality_gate_can_allow_missing_history_for_first_bootstrap_run() -> None:
    result = run_recommendation_benchmark_quality_gate(
        FakeDatabase(),
        options=RecommendationBenchmarkQualityGateOptions(allow_missing_history=True),
        repository=FakeQualityGateRepository([]),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.summary_json["allow_missing_history"] is True


def test_quality_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--benchmark-key",
            "recommendation_benchmark:daily-core",
            "--strategy",
            "accuracy_first",
            "--history-limit",
            "5",
            "--allow-missing-history",
            "--min-scenario-count",
            "6",
            "--min-completed-ratio",
            "0.9",
            "--max-failed-count",
            "1",
            "--max-warning-count",
            "3",
            "--min-global-best-selected-count",
            "4",
            "--min-global-best-candidate-count",
            "20",
            "--min-global-best-generated-option-count",
            "5",
            "--min-core-replay-ready-ratio",
            "0.7",
            "--min-chain-integrity-ready-ratio",
            "1.0",
            "--max-chain-integrity-critical-issue-count",
            "0",
            "--min-successor-chain-evaluation-passed-ratio",
            "0.8",
            "--min-successor-chain-effective-leaf-count",
            "8",
            "--max-successor-chain-critical-issue-count",
            "0",
            "--max-successor-chain-ambiguous-source-count",
            "1",
            "--max-successor-chain-source-status-sync-required-count",
            "2",
            "--max-ambiguous-successor-source-count",
            "1",
            "--max-stale-recommendation-count",
            "2",
            "--max-successor-recompute-required-count",
            "3",
            "--min-final-hit-sample-size",
            "10",
            "--min-final-hit-coverage-ratio",
            "0.8",
            "--min-final-hit-rate",
            "0.55",
            "--min-average-core-replay-roi",
            "-0.05",
            "--min-upset-capture-sample-size",
            "4",
            "--min-upset-capture-rate",
            "0.25",
            "--require-unified-candidate-pool",
            "--min-unified-candidate-pool-present-count",
            "10",
            "--min-unified-candidate-pool-valid-candidate-count",
            "20",
            "--min-unified-candidate-pool-unique-family-count",
            "3",
            "--max-unified-candidate-pool-selection-mismatch-count",
            "0",
            "--max-unified-candidate-pool-selected-2x1-rate",
            "0.5",
            "--require-unified-candidate-pool-multiple-value-admission",
            "--min-unified-candidate-pool-multiple-value-candidate-count",
            "4",
            "--min-unified-candidate-pool-multiple-value-admitted-candidate-count",
            "3",
            "--min-unified-candidate-pool-multiple-value-extra-option-count",
            "8",
            "--max-unified-candidate-pool-multiple-value-rejected-candidate-count",
            "1",
            "--max-unified-candidate-pool-selected-multiple-value-rejected-count",
            "0",
            "--historical-suite-quality-gate-report-path",
            "configs/recommendations/historical_reports/core_gate.json",
            "--require-historical-suite-quality-gate",
            "--allow-missing-historical-suite-lifecycle-evidence",
            "--allow-unsynced-historical-suite-lifecycle-source-status",
            "--min-historical-suite-slice-count",
            "30",
            "--min-historical-suite-comparison-count",
            "30",
            "--min-historical-suite-candidate-final-hit-sample-size",
            "30",
            "--min-historical-suite-candidate-final-hit-coverage-ratio",
            "1.0",
            "--min-historical-suite-candidate-dynamic-mixed-final-answer-count",
            "6",
            "--min-historical-suite-candidate-dynamic-mixed-final-answer-rate",
            "0.7",
            "--min-historical-suite-candidate-handicap-final-answer-count",
            "5",
            "--min-historical-suite-candidate-correct-score-final-answer-count",
            "4",
            "--min-historical-suite-candidate-multiple-choice-final-answer-count",
            "3",
            "--max-historical-suite-failed-check-count",
            "0",
            "--min-historical-suite-lifecycle-effective-leaf-count",
            "1",
            "--min-historical-suite-lifecycle-active-edge-count",
            "1",
            "--max-historical-suite-lifecycle-critical-issue-count",
            "0",
            "--max-historical-suite-lifecycle-source-status-sync-required-count",
            "0",
            "--require-historical-suite-successor-chain-evaluation",
            "--min-historical-suite-successor-effective-leaf-count",
            "2",
            "--min-historical-suite-successor-active-edge-count",
            "1",
            "--max-historical-suite-successor-critical-issue-count",
            "0",
            "--max-historical-suite-successor-ambiguous-source-count",
            "0",
            "--max-historical-suite-successor-source-status-sync-required-count",
            "0",
            "--require-historical-suite-market-movement-runtime-replay",
            "--allow-historical-suite-market-movement-runtime-replay-not-allowed",
            "--allow-historical-suite-market-movement-runtime-replay-non-passed-status",
            "--min-historical-suite-market-movement-runtime-replay-rule-count",
            "1",
            "--min-historical-suite-market-movement-runtime-replay-selected-rule-count",
            "1",
            "--min-historical-suite-market-movement-runtime-replay-accepted-count",
            "1",
            "--min-historical-suite-market-movement-runtime-replay-adjusted-fixture-count",
            "120",
            "--min-historical-suite-market-movement-runtime-replay-adjusted-prediction-count",
            "360",
            "--min-historical-suite-market-movement-runtime-replay-final-hit-rate-delta",
            "0.0",
            "--min-historical-suite-market-movement-runtime-replay-roi-delta",
            "0.01",
            "--min-historical-suite-market-movement-runtime-replay-profit-loss-delta",
            "1.0",
            "--max-historical-suite-market-movement-runtime-replay-brier-score-delta",
            "0.02",
            "--max-historical-suite-market-movement-runtime-replay-log-loss-delta",
            "0.03",
            "--max-historical-suite-market-movement-runtime-replay-calibration-delta",
            "0.04",
            "--allow-historical-suite-market-movement-runtime-replay-production-change",
            "--allow-historical-suite-market-movement-runtime-replay-public-change",
            "--runtime-profile-switch-report-path",
            "configs/recommendations/historical_reports/switch.json",
            "--runtime-profile-switch-replay-report-path",
            "configs/recommendations/historical_reports/replay.json",
            "--require-runtime-profile-switch-gate",
            "--allow-missing-runtime-profile-switch-replay",
            "--allow-runtime-profile-switch-applied",
            "--min-runtime-profile-switch-rule-count",
            "2",
            "--min-runtime-profile-switch-allowed-competition-count",
            "3",
            "--min-runtime-profile-switch-final-answer-count",
            "12",
            "--min-runtime-profile-switch-changed-final-answer-count",
            "4",
            "--min-runtime-profile-switch-final-answer-hit-rate-delta",
            "0.01",
            "--min-runtime-profile-switch-roi-delta",
            "0.02",
            "--min-runtime-profile-switch-profit-loss-delta",
            "0.03",
            "--max-runtime-profile-switch-harm-count-vs-original",
            "1",
            "--max-runtime-profile-switch-final-hit-harm-count-vs-original",
            "2",
            "--max-runtime-profile-switch-profit-loss-harm-count-vs-original",
            "3",
            "--min-runtime-profile-switch-average-hit-probability-delta",
            "-0.03",
            "--final-answer-segment-penalty-runtime-replay-report-path",
            "configs/recommendations/historical_reports/segment_replay.json",
            "--require-final-answer-segment-penalty-runtime-replay",
            "--allow-missing-final-answer-segment-penalty-runtime-replay-holdout",
            "--require-final-answer-segment-penalty-runtime-replay-runtime-allowed",
            "--min-final-answer-segment-penalty-runtime-replay-rule-count",
            "2",
            "--min-final-answer-segment-penalty-runtime-replay-selected-rule-count",
            "1",
            "--max-final-answer-segment-penalty-runtime-replay-selected-rule-count",
            "2",
            "--min-final-answer-segment-penalty-runtime-replay-final-answer-count",
            "30",
            "--min-final-answer-segment-penalty-runtime-replay-changed-final-answer-count",
            "2",
            "--min-final-answer-segment-penalty-runtime-replay-penalty-option-count",
            "2",
            "--min-final-answer-segment-penalty-runtime-replay-hit-count-delta",
            "1",
            "--min-final-answer-segment-penalty-runtime-replay-hit-rate-delta",
            "0.01",
            "--min-final-answer-segment-penalty-runtime-replay-roi-delta",
            "0.02",
            "--min-final-answer-segment-penalty-runtime-replay-profit-loss-delta",
            "1.0",
            "--min-final-answer-segment-penalty-runtime-replay-candidate-roi",
            "0.0",
            "--max-final-answer-segment-penalty-runtime-replay-brier-score-delta",
            "0.01",
            "--max-final-answer-segment-penalty-runtime-replay-log-loss-delta",
            "0.02",
            "--max-final-answer-segment-penalty-runtime-replay-calibration-error-delta",
            "0.03",
            "--max-final-answer-segment-penalty-runtime-replay-harm-count-vs-baseline",
            "1",
            "--max-final-answer-segment-penalty-runtime-replay-final-hit-harm-count-vs-baseline",
            "2",
            "--max-final-answer-segment-penalty-runtime-replay-profit-loss-harm-count-vs-baseline",
            "3",
            "--allow-final-answer-segment-penalty-runtime-replay-production-change",
            "--allow-final-answer-segment-penalty-runtime-replay-public-change",
            "--market-movement-runtime-activation-report-path",
            "configs/recommendations/historical_reports/market_movement_activation.json",
            "--require-market-movement-runtime-activation",
            "--allow-market-movement-runtime-activation-not-ready",
            "--min-market-movement-runtime-activation-rule-count",
            "1",
            "--min-market-movement-runtime-activation-selected-rule-count",
            "1",
            "--max-market-movement-runtime-activation-selected-rule-count",
            "1",
            "--min-market-movement-runtime-activation-adjusted-fixture-count",
            "120",
            "--min-market-movement-runtime-activation-adjusted-prediction-count",
            "360",
            "--min-market-movement-runtime-activation-final-hit-rate-delta",
            "0.0",
            "--min-market-movement-runtime-activation-roi-delta",
            "0.01",
            "--min-market-movement-runtime-activation-profit-loss-delta",
            "1.0",
            "--max-market-movement-runtime-activation-brier-score-delta",
            "0.02",
            "--max-market-movement-runtime-activation-log-loss-delta",
            "0.03",
            "--max-market-movement-runtime-activation-calibration-delta",
            "0.04",
            "--allow-market-movement-runtime-activation-default-profile-write",
            "--allow-market-movement-runtime-activation-default-path-change",
            "--allow-market-movement-runtime-activation-production-change",
            "--allow-market-movement-runtime-activation-public-change",
            "--replacement-reranker-shadow-admission-report-path",
            "configs/recommendations/historical_reports/replacement_admission.json",
            "--require-replacement-reranker-shadow-admission",
            "--allow-replacement-reranker-shadow-only",
            "--require-replacement-reranker-scoped-evidence",
            "--require-replacement-reranker-prematch-source-surface",
            "--min-replacement-reranker-scope-final-answer-count",
            "19",
            "--min-replacement-reranker-shadow-final-answer-count",
            "17",
            "--min-replacement-reranker-changed-from-model-top-count",
            "5",
            "--min-replacement-reranker-hit-delta-vs-model-top",
            "1",
            "--min-replacement-reranker-profit-loss-delta-vs-model-top",
            "4.0",
            "--min-replacement-reranker-roi-delta-vs-model-top",
            "0.10",
            "--max-replacement-reranker-harm-count-vs-model-top",
            "0",
            "--max-replacement-reranker-final-hit-harm-count-vs-model-top",
            "2",
            "--max-replacement-reranker-profit-loss-harm-count-vs-model-top",
            "3",
            "--max-replacement-reranker-failed-fold-count",
            "0",
            "--min-replacement-reranker-active-competition-fold-count",
            "2",
            "--min-replacement-reranker-active-season-fold-count",
            "3",
            "--min-replacement-reranker-active-rolling-fold-count",
            "4",
            "--global-planner-short-odds-adapter-gate-report-path",
            "configs/recommendations/historical_reports/global_planner_adapter_gate.json",
            "--require-global-planner-short-odds-adapter-gate",
            "--allow-global-planner-short-odds-adapter-default-path-change",
            "--allow-global-planner-short-odds-adapter-shadow-path-change",
            "--allow-global-planner-short-odds-adapter-missing-explicit-opt-in-change",
            "--min-global-planner-short-odds-adapter-runtime-final-answer-count",
            "30",
            "--min-global-planner-short-odds-adapter-runtime-changed-final-answer-count",
            "17",
            "--min-global-planner-short-odds-adapter-runtime-final-answer-hit-rate-delta",
            "0.01",
            "--min-global-planner-short-odds-adapter-runtime-roi-delta",
            "0.02",
            "--min-global-planner-short-odds-adapter-runtime-profit-loss-delta",
            "1.0",
            "--max-global-planner-short-odds-adapter-runtime-harm-count-vs-original",
            "1",
            "--max-global-planner-short-odds-adapter-runtime-final-hit-harm-count-vs-original",
            "2",
            "--max-global-planner-short-odds-adapter-runtime-profit-loss-harm-count-vs-original",
            "3",
            "--min-global-planner-short-odds-adapter-runtime-average-hit-probability-delta",
            "-0.03",
            "--allow-global-planner-short-odds-adapter-runtime-public-change",
            "--allow-global-planner-short-odds-adapter-runtime-production-change",
            "--global-planner-short-odds-adapter-sample-expansion-report-path",
            "configs/recommendations/historical_reports/sample_expansion.json",
            "--require-global-planner-short-odds-adapter-sample-expansion",
            "--require-global-planner-short-odds-adapter-sample-expansion-promotion-ready",
            "--probability-calibration-profile-rolling-admission-report-path",
            "configs/recommendations/historical_reports/probability_calibration_admission.json",
            "--require-probability-calibration-profile-rolling-admission",
            "--allow-probability-calibration-profile-shadow-only",
            "--allow-probability-calibration-profile-non-active-profile",
            "--min-probability-calibration-profile-overall-adjusted-fixture-count",
            "24",
            "--min-probability-calibration-profile-overall-bucket-count",
            "3",
            "--max-probability-calibration-profile-failed-fold-count",
            "1",
            "--min-probability-calibration-profile-active-competition-fold-count",
            "2",
            "--min-probability-calibration-profile-active-season-cutoff-fold-count",
            "3",
            "--min-probability-calibration-profile-active-rolling-fold-count",
            "4",
            "--probability-calibration-profile-model-quality-gate-report-path",
            "configs/recommendations/historical_reports/probability_model_quality_gate.json",
            "--require-probability-calibration-profile-model-quality-gate",
            "--allow-probability-calibration-profile-model-quality-not-ready",
            "--min-probability-calibration-profile-model-quality-selected-competition-count",
            "4",
            "--min-probability-calibration-profile-model-quality-adjusted-slice-count",
            "4",
            "--min-probability-calibration-profile-model-quality-adjusted-fixture-count",
            "96",
            "--max-probability-calibration-profile-model-quality-skipped-fixture-count",
            "2",
            "--max-probability-calibration-profile-model-quality-final-answer-changed-count",
            "1",
            "--min-probability-calibration-profile-model-quality-final-answer-hit-count-delta",
            "1",
            "--min-probability-calibration-profile-model-quality-final-answer-hit-rate-delta",
            "0.01",
            "--min-probability-calibration-profile-model-quality-roi-delta",
            "0.02",
            "--min-probability-calibration-profile-model-quality-profit-loss-delta",
            "1.0",
            "--max-probability-calibration-profile-model-quality-brier-score-delta",
            "0.01",
            "--max-probability-calibration-profile-model-quality-log-loss-delta",
            "0.02",
            "--max-probability-calibration-profile-model-quality-calibration-error-delta",
            "0.03",
            "--prematch-feature-quality-cycle-report-path",
            "configs/recommendations/historical_reports/prematch_feature_quality_cycle.json",
            "--require-prematch-feature-quality-cycle",
            "--allow-failed-prematch-feature-quality-cycle",
            "--allow-prematch-feature-quality-cycle-best-gate-failed",
            "--min-prematch-feature-quality-cycle-slice-count",
            "25",
            "--min-prematch-feature-quality-cycle-fixture-count",
            "600",
            "--min-prematch-feature-quality-cycle-evaluated-candidate-count",
            "5",
            "--min-prematch-feature-quality-cycle-passing-candidate-count",
            "1",
            "--max-prematch-feature-quality-cycle-warning-count",
            "2",
            "--max-prematch-feature-quality-cycle-best-brier-score-delta",
            "0.01",
            "--max-prematch-feature-quality-cycle-best-log-loss-delta",
            "0.02",
            "--max-prematch-feature-quality-cycle-best-calibration-error-delta",
            "0.03",
            "--prematch-feature-rolling-admission-report-path",
            "configs/recommendations/historical_reports/prematch_feature_rolling_admission.json",
            "--require-prematch-feature-rolling-admission",
            "--allow-prematch-feature-rolling-admission-shadow-only",
            "--min-prematch-feature-rolling-admission-overall-evaluated-candidate-count",
            "5",
            "--min-prematch-feature-rolling-admission-overall-passing-candidate-count",
            "1",
            "--max-prematch-feature-rolling-admission-failed-fold-count",
            "1",
            "--min-prematch-feature-rolling-admission-active-competition-fold-count",
            "2",
            "--min-prematch-feature-rolling-admission-active-season-cutoff-fold-count",
            "3",
            "--min-prematch-feature-rolling-admission-active-rolling-fold-count",
            "4",
            "--max-prematch-feature-rolling-admission-overall-brier-score-delta",
            "0.01",
            "--max-prematch-feature-rolling-admission-overall-log-loss-delta",
            "0.02",
            "--max-prematch-feature-rolling-admission-overall-calibration-error-delta",
            "0.03",
            "--prematch-feature-sample-readiness-report-path",
            "configs/recommendations/historical_reports/prematch_feature_sample_readiness.json",
            "--require-prematch-feature-sample-readiness",
            "--allow-prematch-feature-sample-readiness-shadow-only",
            "--min-prematch-feature-sample-ready-source-count",
            "2",
            "--min-prematch-feature-sample-ready-fixture-count",
            "600",
            "--min-prematch-feature-sample-ready-competition-count",
            "3",
            "--min-prematch-feature-sample-ready-season-count",
            "2",
            "--min-prematch-feature-sample-ready-competition-season-count",
            "5",
            "--max-prematch-feature-sample-readiness-warning-count",
            "4",
            "--fail-on-history-statuses",
            "regressed,mixed",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.benchmark_key == "recommendation_benchmark:daily-core"
    assert options.strategy == "accuracy_first"
    assert options.history_limit == 5
    assert options.allow_missing_history is True
    assert options.min_scenario_count == 6
    assert options.min_completed_ratio == 0.9
    assert options.max_failed_count == 1
    assert options.max_warning_count == 3
    assert options.min_global_best_selected_count == 4
    assert options.min_global_best_candidate_count == 20
    assert options.min_global_best_generated_option_count == 5
    assert options.min_core_replay_ready_ratio == 0.7
    assert options.min_chain_integrity_ready_ratio == 1.0
    assert options.max_chain_integrity_critical_issue_count == 0
    assert options.min_successor_chain_evaluation_passed_ratio == 0.8
    assert options.min_successor_chain_effective_leaf_count == 8
    assert options.max_successor_chain_critical_issue_count == 0
    assert options.max_successor_chain_ambiguous_source_count == 1
    assert options.max_successor_chain_source_status_sync_required_count == 2
    assert options.max_ambiguous_successor_source_count == 1
    assert options.max_stale_recommendation_count == 2
    assert options.max_successor_recompute_required_count == 3
    assert options.min_final_hit_sample_size == 10
    assert options.min_final_hit_coverage_ratio == 0.8
    assert options.min_final_hit_rate == 0.55
    assert options.min_average_core_replay_roi == -0.05
    assert options.min_upset_capture_sample_size == 4
    assert options.min_upset_capture_rate == 0.25
    assert options.require_unified_candidate_pool is True
    assert options.min_unified_candidate_pool_present_count == 10
    assert options.min_unified_candidate_pool_valid_candidate_count == 20
    assert options.min_unified_candidate_pool_unique_family_count == 3
    assert options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert options.max_unified_candidate_pool_selected_2x1_rate == 0.5
    assert options.require_unified_candidate_pool_multiple_value_admission is True
    assert options.min_unified_candidate_pool_multiple_value_candidate_count == 4
    assert (
        options.min_unified_candidate_pool_multiple_value_admitted_candidate_count == 3
    )
    assert options.min_unified_candidate_pool_multiple_value_extra_option_count == 8
    assert options.max_unified_candidate_pool_multiple_value_rejected_candidate_count == 1
    assert (
        options.max_unified_candidate_pool_selected_multiple_value_rejected_count == 0
    )
    assert options.historical_suite_quality_gate_report_path is not None
    assert str(options.historical_suite_quality_gate_report_path).endswith(
        "core_gate.json"
    )
    assert options.require_historical_suite_quality_gate is True
    assert options.require_historical_suite_lifecycle_evidence is False
    assert options.require_historical_suite_lifecycle_source_status_synced is False
    assert options.min_historical_suite_slice_count == 30
    assert options.min_historical_suite_comparison_count == 30
    assert options.min_historical_suite_candidate_final_hit_sample_size == 30
    assert options.min_historical_suite_candidate_final_hit_coverage_ratio == 1.0
    assert options.min_historical_suite_candidate_dynamic_mixed_final_answer_count == 6
    assert options.min_historical_suite_candidate_dynamic_mixed_final_answer_rate == 0.7
    assert options.min_historical_suite_candidate_handicap_final_answer_count == 5
    assert options.min_historical_suite_candidate_correct_score_final_answer_count == 4
    assert options.min_historical_suite_candidate_multiple_choice_final_answer_count == 3
    assert options.max_historical_suite_failed_check_count == 0
    assert options.min_historical_suite_lifecycle_effective_leaf_count == 1
    assert options.min_historical_suite_lifecycle_active_edge_count == 1
    assert options.max_historical_suite_lifecycle_critical_issue_count == 0
    assert (
        options.max_historical_suite_lifecycle_source_status_sync_required_count == 0
    )
    assert options.require_historical_suite_successor_chain_evaluation is True
    assert options.min_historical_suite_successor_effective_leaf_count == 2
    assert options.min_historical_suite_successor_active_edge_count == 1
    assert options.max_historical_suite_successor_critical_issue_count == 0
    assert options.max_historical_suite_successor_ambiguous_source_count == 0
    assert (
        options.max_historical_suite_successor_source_status_sync_required_count == 0
    )
    assert options.require_historical_suite_market_movement_runtime_replay is True
    assert (
        options.require_historical_suite_market_movement_runtime_replay_allowed
        is False
    )
    assert (
        options.require_historical_suite_market_movement_runtime_replay_passed_status
        is False
    )
    assert options.min_historical_suite_market_movement_runtime_replay_rule_count == 1
    assert (
        options.min_historical_suite_market_movement_runtime_replay_selected_rule_count
        == 1
    )
    assert options.min_historical_suite_market_movement_runtime_replay_accepted_count == 1
    assert (
        options.min_historical_suite_market_movement_runtime_replay_adjusted_fixture_count
        == 120
    )
    assert (
        options.min_historical_suite_market_movement_runtime_replay_adjusted_prediction_count
        == 360
    )
    assert (
        options.min_historical_suite_market_movement_runtime_replay_final_hit_rate_delta
        == 0.0
    )
    assert options.min_historical_suite_market_movement_runtime_replay_roi_delta == 0.01
    assert (
        options.min_historical_suite_market_movement_runtime_replay_profit_loss_delta
        == 1.0
    )
    assert (
        options.max_historical_suite_market_movement_runtime_replay_brier_score_delta
        == 0.02
    )
    assert (
        options.max_historical_suite_market_movement_runtime_replay_log_loss_delta
        == 0.03
    )
    assert (
        options.max_historical_suite_market_movement_runtime_replay_mean_calibration_error_delta
        == 0.04
    )
    assert (
        options.require_historical_suite_market_movement_runtime_replay_production_unchanged
        is False
    )
    assert (
        options.require_historical_suite_market_movement_runtime_replay_public_response_unchanged
        is False
    )
    assert options.runtime_profile_switch_report_path is not None
    assert str(options.runtime_profile_switch_report_path).endswith("switch.json")
    assert options.runtime_profile_switch_replay_report_path is not None
    assert str(options.runtime_profile_switch_replay_report_path).endswith(
        "replay.json"
    )
    assert options.require_runtime_profile_switch_gate is True
    assert options.require_runtime_profile_switch_replay is False
    assert options.require_runtime_profile_switch_staged_only is False
    assert options.min_runtime_profile_switch_rule_count == 2
    assert options.min_runtime_profile_switch_allowed_competition_count == 3
    assert options.min_runtime_profile_switch_final_answer_count == 12
    assert options.min_runtime_profile_switch_changed_final_answer_count == 4
    assert options.min_runtime_profile_switch_final_answer_hit_rate_delta == 0.01
    assert options.min_runtime_profile_switch_roi_delta == 0.02
    assert options.min_runtime_profile_switch_profit_loss_delta == 0.03
    assert options.max_runtime_profile_switch_harm_count_vs_original == 1
    assert options.max_runtime_profile_switch_final_hit_harm_count_vs_original == 2
    assert options.max_runtime_profile_switch_profit_loss_harm_count_vs_original == 3
    assert options.min_runtime_profile_switch_average_hit_probability_delta == -0.03
    assert options.final_answer_segment_penalty_runtime_replay_report_path is not None
    assert str(
        options.final_answer_segment_penalty_runtime_replay_report_path
    ).endswith("segment_replay.json")
    assert options.require_final_answer_segment_penalty_runtime_replay is True
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_holdout_allowed
        is False
    )
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        is True
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_rule_count == 2
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 1
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 2
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_final_answer_count == 30
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        == 2
    )
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        == 2
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_hit_count_delta == 1
    assert options.min_final_answer_segment_penalty_runtime_replay_hit_rate_delta == 0.01
    assert options.min_final_answer_segment_penalty_runtime_replay_roi_delta == 0.02
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_profit_loss_delta
        == 1.0
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_candidate_roi == 0.0
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_brier_score_delta
        == 0.01
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_log_loss_delta
        == 0.02
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_calibration_error_delta
        == 0.03
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
        == 1
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        == 2
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        == 3
    )
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_no_production_change
        is False
    )
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_no_public_response_change
        is False
    )
    assert options.market_movement_runtime_activation_report_path is not None
    assert str(options.market_movement_runtime_activation_report_path).endswith(
        "market_movement_activation.json"
    )
    assert options.require_market_movement_runtime_activation is True
    assert options.require_market_movement_runtime_activation_ready is False
    assert options.min_market_movement_runtime_activation_rule_count == 1
    assert options.min_market_movement_runtime_activation_selected_rule_count == 1
    assert options.max_market_movement_runtime_activation_selected_rule_count == 1
    assert options.min_market_movement_runtime_activation_adjusted_fixture_count == 120
    assert (
        options.min_market_movement_runtime_activation_adjusted_prediction_count
        == 360
    )
    assert options.min_market_movement_runtime_activation_final_hit_rate_delta == 0.0
    assert options.min_market_movement_runtime_activation_roi_delta == 0.01
    assert options.min_market_movement_runtime_activation_profit_loss_delta == 1.0
    assert options.max_market_movement_runtime_activation_brier_score_delta == 0.02
    assert options.max_market_movement_runtime_activation_log_loss_delta == 0.03
    assert (
        options.max_market_movement_runtime_activation_mean_calibration_error_delta
        == 0.04
    )
    assert (
        options.require_market_movement_runtime_activation_no_default_profile_write
        is False
    )
    assert (
        options.require_market_movement_runtime_activation_no_default_path_change
        is False
    )
    assert (
        options.require_market_movement_runtime_activation_no_production_change
        is False
    )
    assert (
        options.require_market_movement_runtime_activation_no_public_response_change
        is False
    )
    assert options.replacement_reranker_shadow_admission_report_path is not None
    assert str(options.replacement_reranker_shadow_admission_report_path).endswith(
        "replacement_admission.json"
    )
    assert options.require_replacement_reranker_shadow_admission is True
    assert options.require_replacement_reranker_runtime_candidate_allowed is False
    assert options.require_replacement_reranker_scoped_evidence is True
    assert options.require_replacement_reranker_prematch_source_surface is True
    assert options.min_replacement_reranker_scope_final_answer_count == 19
    assert options.min_replacement_reranker_shadow_final_answer_count == 17
    assert options.min_replacement_reranker_changed_from_model_top_count == 5
    assert options.min_replacement_reranker_hit_delta_vs_model_top == 1
    assert options.min_replacement_reranker_profit_loss_delta_vs_model_top == 4.0
    assert options.min_replacement_reranker_roi_delta_vs_model_top == 0.10
    assert options.max_replacement_reranker_harm_count_vs_model_top == 0
    assert options.max_replacement_reranker_final_hit_harm_count_vs_model_top == 2
    assert options.max_replacement_reranker_profit_loss_harm_count_vs_model_top == 3
    assert options.max_replacement_reranker_failed_fold_count == 0
    assert options.min_replacement_reranker_active_competition_fold_count == 2
    assert options.min_replacement_reranker_active_season_fold_count == 3
    assert options.min_replacement_reranker_active_rolling_fold_count == 4
    assert options.global_planner_short_odds_adapter_gate_report_path is not None
    assert str(options.global_planner_short_odds_adapter_gate_report_path).endswith(
        "global_planner_adapter_gate.json"
    )
    assert options.require_global_planner_short_odds_adapter_gate is True
    assert (
        options.require_global_planner_short_odds_adapter_default_path_unchanged
        is False
    )
    assert (
        options.require_global_planner_short_odds_adapter_shadow_path_unchanged
        is False
    )
    assert (
        options.require_global_planner_short_odds_adapter_explicit_opt_in_changed
        is False
    )
    assert (
        options.min_global_planner_short_odds_adapter_runtime_final_answer_count
        == 30
    )
    assert (
        options.min_global_planner_short_odds_adapter_runtime_changed_final_answer_count
        == 17
    )
    assert (
        options.min_global_planner_short_odds_adapter_runtime_final_answer_hit_rate_delta
        == 0.01
    )
    assert options.min_global_planner_short_odds_adapter_runtime_roi_delta == 0.02
    assert (
        options.min_global_planner_short_odds_adapter_runtime_profit_loss_delta
        == 1.0
    )
    assert (
        options.max_global_planner_short_odds_adapter_runtime_harm_count_vs_original
        == 1
    )
    assert (
        options.max_global_planner_short_odds_adapter_runtime_final_hit_harm_count_vs_original
        == 2
    )
    assert (
        options.max_global_planner_short_odds_adapter_runtime_profit_loss_harm_count_vs_original
        == 3
    )
    assert (
        options.min_global_planner_short_odds_adapter_runtime_average_hit_probability_delta
        == -0.03
    )
    assert (
        options.require_global_planner_short_odds_adapter_runtime_public_unchanged
        is False
    )
    assert (
        options.require_global_planner_short_odds_adapter_runtime_production_unchanged
        is False
    )
    assert (
        options.global_planner_short_odds_adapter_sample_expansion_report_path
        is not None
    )
    assert str(
        options.global_planner_short_odds_adapter_sample_expansion_report_path
    ).endswith("sample_expansion.json")
    assert (
        options.require_global_planner_short_odds_adapter_sample_expansion
        is True
    )
    assert (
        options.require_global_planner_short_odds_adapter_sample_expansion_promotion_ready
        is True
    )
    assert (
        options.probability_calibration_profile_rolling_admission_report_path
        is not None
    )
    assert str(
        options.probability_calibration_profile_rolling_admission_report_path
    ).endswith("probability_calibration_admission.json")
    assert (
        options.require_probability_calibration_profile_rolling_admission is True
    )
    assert options.require_probability_calibration_profile_candidate_allowed is False
    assert options.require_probability_calibration_profile_active_profile is False
    assert (
        options.min_probability_calibration_profile_overall_adjusted_fixture_count
        == 24
    )
    assert options.min_probability_calibration_profile_overall_bucket_count == 3
    assert options.max_probability_calibration_profile_failed_fold_count == 1
    assert (
        options.min_probability_calibration_profile_active_competition_fold_count
        == 2
    )
    assert (
        options.probability_calibration_profile_model_quality_gate_report_path
        is not None
    )
    assert str(
        options.probability_calibration_profile_model_quality_gate_report_path
    ).endswith("probability_model_quality_gate.json")
    assert options.require_probability_calibration_profile_model_quality_gate is True
    assert options.require_probability_calibration_profile_model_quality_ready is False
    assert (
        options.min_probability_calibration_profile_model_quality_selected_competition_count
        == 4
    )
    assert (
        options.min_probability_calibration_profile_model_quality_adjusted_slice_count
        == 4
    )
    assert (
        options.min_probability_calibration_profile_model_quality_adjusted_fixture_count
        == 96
    )
    assert (
        options.max_probability_calibration_profile_model_quality_skipped_fixture_count
        == 2
    )
    assert (
        options.max_probability_calibration_profile_model_quality_final_answer_changed_count
        == 1
    )
    assert (
        options.min_probability_calibration_profile_model_quality_final_answer_hit_count_delta
        == 1
    )
    assert (
        options.min_probability_calibration_profile_model_quality_final_answer_hit_rate_delta
        == 0.01
    )
    assert options.min_probability_calibration_profile_model_quality_roi_delta == 0.02
    assert (
        options.min_probability_calibration_profile_model_quality_profit_loss_delta
        == 1.0
    )
    assert (
        options.max_probability_calibration_profile_model_quality_brier_score_delta
        == 0.01
    )
    assert (
        options.max_probability_calibration_profile_model_quality_log_loss_delta
        == 0.02
    )
    assert (
        options.max_probability_calibration_profile_model_quality_calibration_error_delta
        == 0.03
    )
    assert (
        options.min_probability_calibration_profile_active_season_cutoff_fold_count
        == 3
    )
    assert options.min_probability_calibration_profile_active_rolling_fold_count == 4
    assert options.prematch_feature_quality_cycle_report_path is not None
    assert str(options.prematch_feature_quality_cycle_report_path).endswith(
        "prematch_feature_quality_cycle.json"
    )
    assert options.require_prematch_feature_quality_cycle is True
    assert options.require_prematch_feature_quality_cycle_passed is False
    assert options.require_prematch_feature_quality_cycle_best_gate_passed is False
    assert options.min_prematch_feature_quality_cycle_slice_count == 25
    assert options.min_prematch_feature_quality_cycle_fixture_count == 600
    assert options.min_prematch_feature_quality_cycle_evaluated_candidate_count == 5
    assert options.min_prematch_feature_quality_cycle_passing_candidate_count == 1
    assert options.max_prematch_feature_quality_cycle_warning_count == 2
    assert options.max_prematch_feature_quality_cycle_best_brier_score_delta == 0.01
    assert options.max_prematch_feature_quality_cycle_best_log_loss_delta == 0.02
    assert (
        options.max_prematch_feature_quality_cycle_best_calibration_error_delta
        == 0.03
    )
    assert options.prematch_feature_rolling_admission_report_path is not None
    assert str(options.prematch_feature_rolling_admission_report_path).endswith(
        "prematch_feature_rolling_admission.json"
    )
    assert options.require_prematch_feature_rolling_admission is True
    assert (
        options.require_prematch_feature_rolling_admission_candidate_allowed
        is False
    )
    assert (
        options.min_prematch_feature_rolling_admission_overall_evaluated_candidate_count
        == 5
    )
    assert (
        options.min_prematch_feature_rolling_admission_overall_passing_candidate_count
        == 1
    )
    assert options.max_prematch_feature_rolling_admission_failed_fold_count == 1
    assert (
        options.min_prematch_feature_rolling_admission_active_competition_fold_count
        == 2
    )
    assert (
        options.min_prematch_feature_rolling_admission_active_season_cutoff_fold_count
        == 3
    )
    assert (
        options.min_prematch_feature_rolling_admission_active_rolling_fold_count
        == 4
    )
    assert (
        options.max_prematch_feature_rolling_admission_overall_brier_score_delta
        == 0.01
    )
    assert (
        options.max_prematch_feature_rolling_admission_overall_log_loss_delta
        == 0.02
    )
    assert (
        options.max_prematch_feature_rolling_admission_overall_calibration_error_delta
        == 0.03
    )
    assert options.prematch_feature_sample_readiness_report_path is not None
    assert str(options.prematch_feature_sample_readiness_report_path).endswith(
        "prematch_feature_sample_readiness.json"
    )
    assert options.require_prematch_feature_sample_readiness is True
    assert options.require_prematch_feature_sample_ready_allowed is False
    assert options.min_prematch_feature_sample_ready_source_count == 2
    assert options.min_prematch_feature_sample_ready_fixture_count == 600
    assert options.min_prematch_feature_sample_ready_competition_count == 3
    assert options.min_prematch_feature_sample_ready_season_count == 2
    assert options.min_prematch_feature_sample_ready_competition_season_count == 5
    assert options.max_prematch_feature_sample_readiness_warning_count == 4
    assert options.fail_on_history_statuses == ("regressed", "mixed")


def test_quality_gate_cli_budget_stability_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--budget-stability-audit-report-path",
            "configs/recommendations/historical_reports/budget_stability.json",
            "--require-budget-stability-audit",
            "--min-budget-stability-slice-count",
            "240",
            "--min-budget-stability-comparable-count",
            "240",
            "--max-budget-stability-signature-change-rate",
            "0.02",
            "--max-budget-stability-harmful-change-count",
            "2",
            "--min-budget-stability-hit-delta-count",
            "-1",
            "--min-budget-stability-profit-loss-delta",
            "-3",
            "--min-budget-stability-roi-delta",
            "-0.005",
            "--max-budget-stability-warning-count",
            "0",
        ]
    )

    options = _options_from_args(args)

    assert options.budget_stability_audit_report_path is not None
    assert str(options.budget_stability_audit_report_path).endswith(
        "budget_stability.json"
    )
    assert options.require_budget_stability_audit is True
    assert options.min_budget_stability_slice_count == 240
    assert options.min_budget_stability_comparable_count == 240
    assert options.max_budget_stability_signature_change_rate == 0.02
    assert options.max_budget_stability_harmful_change_count == 2
    assert options.min_budget_stability_hit_delta_count == -1
    assert options.min_budget_stability_profit_loss_delta == -3.0
    assert options.min_budget_stability_roi_delta == -0.005
    assert options.max_budget_stability_warning_count == 0


def test_quality_gate_cli_final_answer_market_concentration_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--final-answer-market-concentration-audit-report-path",
            "configs/recommendations/historical_reports/final_answer_market.json",
            "--require-final-answer-market-concentration-audit",
            "--min-final-answer-market-concentration-slice-count",
            "5",
            "--min-final-answer-market-concentration-dynamic-mixed-final-answer-count",
            "5",
            "--min-final-answer-market-concentration-effective-constraint-profile-count",
            "2",
            "--max-final-answer-market-concentration-failed-check-count",
            "0",
            "--max-final-answer-market-concentration-warning-count",
            "0",
        ]
    )

    options = _options_from_args(args)

    assert options.final_answer_market_concentration_audit_report_path is not None
    assert str(options.final_answer_market_concentration_audit_report_path).endswith(
        "final_answer_market.json"
    )
    assert options.require_final_answer_market_concentration_audit is True
    assert options.min_final_answer_market_concentration_slice_count == 5
    assert (
        options.min_final_answer_market_concentration_dynamic_mixed_final_answer_count
        == 5
    )
    assert (
        options.min_final_answer_market_concentration_effective_constraint_profile_count
        == 2
    )
    assert options.max_final_answer_market_concentration_failed_check_count == 0
    assert options.max_final_answer_market_concentration_warning_count == 0


def test_quality_gate_cli_correct_score_admission_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--correct-score-admission-report-path",
            "configs/recommendations/historical_reports/correct_score_admission.json",
            "--require-correct-score-admission",
            "--allow-correct-score-admission-holdout-not-allowed",
            "--require-correct-score-admission-production-allowed",
            "--min-correct-score-admission-slice-count",
            "10",
            "--min-correct-score-admission-comparison-count",
            "11",
            "--min-correct-score-admission-candidate-final-hit-sample-size",
            "12",
            "--min-correct-score-admission-candidate-final-hit-coverage-ratio",
            "0.9",
            "--min-correct-score-admission-candidate-final-hit-rate",
            "0.55",
            "--min-correct-score-admission-candidate-roi",
            "0.01",
            "--min-correct-score-admission-candidate-correct-score-final-answer-count",
            "3",
            "--min-correct-score-admission-candidate-correct-score-final-answer-rate",
            "0.03",
            "--min-correct-score-admission-final-hit-rate-delta",
            "0.001",
            "--min-correct-score-admission-roi-delta",
            "0.002",
            "--min-correct-score-admission-profit-loss-delta",
            "0.003",
            "--max-correct-score-admission-brier-score-delta",
            "0.004",
            "--max-correct-score-admission-log-loss-delta",
            "0.005",
            "--max-correct-score-admission-mean-calibration-error-delta",
            "0.006",
            "--max-correct-score-admission-failed-check-count",
            "1",
            "--max-correct-score-admission-warning-count",
            "2",
        ]
    )

    options = _options_from_args(args)

    assert options.correct_score_admission_report_path is not None
    assert str(options.correct_score_admission_report_path).endswith(
        "correct_score_admission.json"
    )
    assert options.require_correct_score_admission is True
    assert options.require_correct_score_admission_holdout_allowed is False
    assert options.require_correct_score_admission_production_allowed is True
    assert options.min_correct_score_admission_slice_count == 10
    assert options.min_correct_score_admission_comparison_count == 11
    assert options.min_correct_score_admission_candidate_final_hit_sample_size == 12
    assert options.min_correct_score_admission_candidate_final_hit_coverage_ratio == 0.9
    assert options.min_correct_score_admission_candidate_final_hit_rate == 0.55
    assert options.min_correct_score_admission_candidate_roi == 0.01
    assert (
        options.min_correct_score_admission_candidate_correct_score_final_answer_count
        == 3
    )
    assert (
        options.min_correct_score_admission_candidate_correct_score_final_answer_rate
        == 0.03
    )
    assert options.min_correct_score_admission_final_hit_rate_delta == 0.001
    assert options.min_correct_score_admission_roi_delta == 0.002
    assert options.min_correct_score_admission_profit_loss_delta == 0.003
    assert options.max_correct_score_admission_brier_score_delta == 0.004
    assert options.max_correct_score_admission_log_loss_delta == 0.005
    assert options.max_correct_score_admission_mean_calibration_error_delta == 0.006
    assert options.max_correct_score_admission_failed_check_count == 1
    assert options.max_correct_score_admission_warning_count == 2


def test_quality_gate_cli_recommendation_strategy_governance_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--recommendation-strategy-promotion-gate-report-path",
            "configs/recommendations/historical_reports/strategy_gate.json",
            "--require-recommendation-strategy-promotion-gate",
            "--allow-recommendation-strategy-gate-not-ready",
            "--min-recommendation-strategy-gate-final-answer-count",
            "99",
            "--min-recommendation-strategy-gate-changed-final-answer-count",
            "13",
            "--min-recommendation-strategy-gate-hit-delta-count",
            "4",
            "--min-recommendation-strategy-gate-profit-loss-delta",
            "15.7",
            "--min-recommendation-strategy-gate-minimum-roi-delta",
            "0.04",
            "--max-recommendation-strategy-gate-harm-count",
            "1",
            "--max-recommendation-strategy-gate-final-hit-harm-count",
            "2",
            "--max-recommendation-strategy-gate-profit-loss-harm-count",
            "3",
            "--allow-recommendation-strategy-gate-production-change",
            "--allow-recommendation-strategy-gate-public-change",
            "--recommendation-strategy-staged-activation-smoke-report-path",
            "configs/recommendations/historical_reports/staged_smoke.json",
            "--require-recommendation-strategy-staged-activation-smoke",
            "--allow-recommendation-strategy-staged-activation-not-ready",
            "--allow-recommendation-strategy-staged-default-write",
            "--allow-recommendation-strategy-staged-production-change",
            "--allow-recommendation-strategy-staged-public-change",
            "--min-recommendation-strategy-staged-rule-count",
            "2",
            "--min-recommendation-strategy-staged-allowed-competition-count",
            "5",
            "--recommendation-strategy-default-path-isolation-report-path",
            "configs/recommendations/historical_reports/isolation.json",
            "--require-recommendation-strategy-default-path-isolation",
            "--allow-recommendation-strategy-default-path-not-isolated",
            "--allow-recommendation-strategy-default-adapter-enabled",
            "--allow-recommendation-strategy-default-adapter-change",
            "--allow-recommendation-strategy-missing-explicit-opt-in",
            "--allow-recommendation-strategy-isolation-default-write",
            "--allow-recommendation-strategy-isolation-production-change",
            "--allow-recommendation-strategy-isolation-public-change",
        ]
    )

    options = _options_from_args(args)

    assert options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(options.recommendation_strategy_promotion_gate_report_path).endswith(
        "strategy_gate.json"
    )
    assert options.require_recommendation_strategy_promotion_gate is True
    assert options.require_recommendation_strategy_gate_ready is False
    assert options.min_recommendation_strategy_gate_final_answer_count == 99
    assert options.min_recommendation_strategy_gate_changed_final_answer_count == 13
    assert options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert options.min_recommendation_strategy_gate_profit_loss_delta == 15.7
    assert options.min_recommendation_strategy_gate_minimum_roi_delta == 0.04
    assert options.max_recommendation_strategy_gate_harm_count == 1
    assert options.max_recommendation_strategy_gate_final_hit_harm_count == 2
    assert options.max_recommendation_strategy_gate_profit_loss_harm_count == 3
    assert options.require_recommendation_strategy_gate_no_production_change is False
    assert options.require_recommendation_strategy_gate_no_public_response_change is False
    assert options.recommendation_strategy_staged_activation_smoke_report_path is not None
    assert str(
        options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith("staged_smoke.json")
    assert options.require_recommendation_strategy_staged_activation_smoke is True
    assert options.require_recommendation_strategy_staged_activation_ready is False
    assert options.require_recommendation_strategy_staged_no_default_write is False
    assert options.require_recommendation_strategy_staged_no_production_change is False
    assert options.require_recommendation_strategy_staged_no_public_response_change is False
    assert options.min_recommendation_strategy_staged_rule_count == 2
    assert options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert options.recommendation_strategy_default_path_isolation_report_path is not None
    assert str(
        options.recommendation_strategy_default_path_isolation_report_path
    ).endswith("isolation.json")
    assert options.require_recommendation_strategy_default_path_isolation is True
    assert options.require_recommendation_strategy_default_path_isolated is False
    assert options.require_recommendation_strategy_default_adapter_disabled is False
    assert options.require_recommendation_strategy_default_adapter_unchanged is False
    assert options.require_recommendation_strategy_explicit_opt_in_applied is False
    assert options.require_recommendation_strategy_isolation_no_default_write is False
    assert (
        options.require_recommendation_strategy_isolation_no_production_change
        is False
    )
    assert options.require_recommendation_strategy_isolation_no_public_response_change is False


def test_quality_gate_cli_recommendation_strategy_governance_preset_maps_options() -> None:
    args = _parse_args(
        [
            "--recommendation-strategy-governance-preset",
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1,
        ]
    )

    options = _options_from_args(args)

    assert (
        options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_13CHANGE_V1
    )
    assert options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(options.recommendation_strategy_promotion_gate_report_path).endswith(
        "probability_preserving_adjacent_threshold_13plus_strategy_promotion_gate_v1.json"
    )
    assert options.recommendation_strategy_staged_activation_smoke_report_path is not None
    assert str(
        options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith(
        "probability_preserving_adjacent_threshold_13plus_staged_activation_smoke_v1.json"
    )
    assert options.recommendation_strategy_default_path_isolation_report_path is not None
    assert str(
        options.recommendation_strategy_default_path_isolation_report_path
    ).endswith(
        "probability_preserving_adjacent_threshold_13plus_default_path_isolation_v1.json"
    )
    assert options.require_recommendation_strategy_promotion_gate is True
    assert options.require_recommendation_strategy_staged_activation_smoke is True
    assert options.require_recommendation_strategy_default_path_isolation is True
    assert options.min_recommendation_strategy_gate_final_answer_count == 90
    assert options.min_recommendation_strategy_gate_changed_final_answer_count == 13
    assert options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert options.min_recommendation_strategy_gate_profit_loss_delta == 15.0
    assert options.min_recommendation_strategy_gate_minimum_roi_delta == 0.04
    assert options.max_recommendation_strategy_gate_harm_count == 0
    assert options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert options.require_recommendation_strategy_default_adapter_disabled is True
    assert options.require_recommendation_strategy_default_adapter_unchanged is True


def test_quality_gate_cli_quality_score_strategy_preset_maps_options() -> None:
    args = _parse_args(
        [
            "--recommendation-strategy-governance-preset",
            RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1,
        ]
    )

    options = _options_from_args(args)

    assert (
        options.recommendation_strategy_governance_preset
        == RECOMMENDATION_STRATEGY_GOVERNANCE_PRESET_PROBABILITY_PRESERVING_QUALITY_SCORE_V1
    )
    assert options.recommendation_strategy_promotion_gate_report_path is not None
    assert str(options.recommendation_strategy_promotion_gate_report_path).endswith(
        "probability_preserving_quality_score_strategy_promotion_gate_v1.json"
    )
    assert options.recommendation_strategy_staged_activation_smoke_report_path is not None
    assert str(
        options.recommendation_strategy_staged_activation_smoke_report_path
    ).endswith("probability_preserving_quality_score_staged_activation_smoke_v1.json")
    assert options.recommendation_strategy_default_path_isolation_report_path is not None
    assert str(
        options.recommendation_strategy_default_path_isolation_report_path
    ).endswith("probability_preserving_quality_score_default_path_isolation_v1.json")
    assert options.require_recommendation_strategy_promotion_gate is True
    assert options.require_recommendation_strategy_staged_activation_smoke is True
    assert options.require_recommendation_strategy_default_path_isolation is True
    assert options.min_recommendation_strategy_gate_final_answer_count == 99
    assert options.min_recommendation_strategy_gate_changed_final_answer_count == 14
    assert options.min_recommendation_strategy_gate_hit_delta_count == 4
    assert options.min_recommendation_strategy_gate_profit_loss_delta == 15.0
    assert options.min_recommendation_strategy_gate_minimum_roi_delta == 0.04
    assert options.max_recommendation_strategy_gate_harm_count == 0
    assert options.min_recommendation_strategy_staged_allowed_competition_count == 5
    assert options.require_recommendation_strategy_default_adapter_disabled is True
    assert options.require_recommendation_strategy_default_adapter_unchanged is True


def test_quality_gate_cli_runtime_profile_switch_preset_maps_options() -> None:
    args = _parse_args(
        [
            "--runtime-profile-switch-preset",
            RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1,
        ]
    )

    options = _options_from_args(args)

    assert (
        options.runtime_profile_switch_preset
        == RUNTIME_PROFILE_SWITCH_PRESET_SHORT_ODDS_CANDIDATE_V1
    )
    assert options.runtime_profile_switch_report_path is not None
    assert str(options.runtime_profile_switch_report_path).endswith(
        "runtime_profile_switch_v1.json"
    )
    assert options.runtime_profile_switch_replay_report_path is not None
    assert str(options.runtime_profile_switch_replay_report_path).endswith(
        "runtime_shadow_replay_switch_staged_v1.json"
    )
    assert options.require_runtime_profile_switch_gate is True
    assert options.require_runtime_profile_switch_replay is True
    assert options.require_runtime_profile_switch_staged_only is True
    assert options.min_runtime_profile_switch_rule_count == 1
    assert options.min_runtime_profile_switch_allowed_competition_count == 4
    assert options.min_runtime_profile_switch_final_answer_count == 30
    assert options.min_runtime_profile_switch_changed_final_answer_count == 5
    assert options.min_runtime_profile_switch_roi_delta == 0.0
    assert options.max_runtime_profile_switch_harm_count_vs_original == 0
    assert options.max_runtime_profile_switch_final_hit_harm_count_vs_original == 0
    assert options.max_runtime_profile_switch_profit_loss_harm_count_vs_original == 0


def test_quality_gate_cli_unified_candidate_pool_guard_preset_maps_options() -> None:
    args = _parse_args(
        [
            "--unified-candidate-pool-guard-preset",
            UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1,
        ]
    )

    options = _options_from_args(args)

    assert (
        options.unified_candidate_pool_guard_preset
        == UNIFIED_CANDIDATE_POOL_GUARD_PRESET_V3_2_FINAL_ANSWER_V1
    )
    assert options.require_unified_candidate_pool is True
    assert options.min_unified_candidate_pool_present_count == 1
    assert options.min_unified_candidate_pool_valid_candidate_count == 1
    assert options.min_unified_candidate_pool_unique_family_count == 2
    assert options.max_unified_candidate_pool_selection_mismatch_count == 0
    assert options.max_unified_candidate_pool_selected_2x1_rate == 0.80
    assert (
        options.max_unified_candidate_pool_selected_multiple_value_rejected_count == 0
    )


def test_quality_gate_cli_segment_penalty_runtime_replay_preset_maps_options() -> None:
    args = _parse_args(
        [
            "--final-answer-segment-penalty-runtime-replay-preset",
            FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1,
        ]
    )

    options = _options_from_args(args)

    assert (
        options.final_answer_segment_penalty_runtime_replay_preset
        == FINAL_ANSWER_SEGMENT_PENALTY_RUNTIME_REPLAY_PRESET_GER_REGIME_HOLDOUT_V1
    )
    assert options.final_answer_segment_penalty_runtime_replay_report_path is not None
    assert str(
        options.final_answer_segment_penalty_runtime_replay_report_path
    ).endswith(
        "final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_replay_v1.json"
    )
    assert options.require_final_answer_segment_penalty_runtime_replay is True
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_holdout_allowed
        is True
    )
    assert (
        options.require_final_answer_segment_penalty_runtime_replay_runtime_allowed
        is False
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_rule_count == 1
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 1
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_selected_rule_count
        == 1
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_final_answer_count == 30
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_changed_final_answer_count
        == 2
    )
    assert (
        options.min_final_answer_segment_penalty_runtime_replay_penalty_option_count
        == 2
    )
    assert options.min_final_answer_segment_penalty_runtime_replay_roi_delta == 0.0
    assert options.min_final_answer_segment_penalty_runtime_replay_candidate_roi is None
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline
        == 0
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline
        == 0
    )
    assert (
        options.max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline
        == 0
    )


class FakeQualityGateRepository:
    def __init__(self, history: list[StoredRecommendationBenchmarkRun]) -> None:
        self.history = history
        self.calls: list[dict[str, object]] = []

    def list_history(
        self,
        *,
        benchmark_key: str | None = None,
        strategy: str | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkRun]:
        self.calls.append(
            {
                "benchmark_key": benchmark_key,
                "strategy": strategy,
                "limit": limit,
            }
        )
        return self.history[:limit]


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


def _benchmark_run(
    *,
    recommendation_benchmark_run_id: int = 20,
    benchmark_key: str = "recommendation_benchmark:daily-core",
    scenario_count: int = 10,
    completed_count: int = 10,
    failed_count: int = 0,
    warning_count: int = 0,
    global_best_selected_count: int | None = None,
    global_best_candidate_count: int = 10,
    global_best_generated_option_count: int = 10,
    core_replay_ready_count: int = 10,
    final_hit_sample_size: int = 0,
    final_hit_count: int = 0,
    average_core_replay_roi: float | None = None,
    chain_integrity_ready_count: int = 10,
    chain_integrity_total_critical_issue_count: int = 0,
    successor_chain_evaluation_passed_count: int = 10,
    successor_chain_effective_leaf_count: int = 10,
    successor_chain_critical_issue_count: int = 0,
    successor_chain_ambiguous_source_count: int = 0,
    successor_chain_source_status_sync_required_count: int = 0,
    ambiguous_successor_source_count: int = 0,
    stale_recommendation_count: int = 0,
    successor_recompute_required_count: int = 0,
    upset_opportunity_count: int = 0,
    upset_capture_count: int = 0,
    history_status: str = "baseline",
) -> StoredRecommendationBenchmarkRun:
    return StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=recommendation_benchmark_run_id,
        benchmark_key=benchmark_key,
        dry_run=True,
        strategy="accuracy_first",
        scenario_count=scenario_count,
        completed_count=completed_count,
        failed_count=failed_count,
        global_best_selected_count=(
            completed_count
            if global_best_selected_count is None
            else global_best_selected_count
        ),
        core_replay_ready_count=core_replay_ready_count,
        core_replay_total_run_count=completed_count,
        core_replay_total_settled_run_count=final_hit_sample_size,
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        average_core_replay_roi=average_core_replay_roi,
        warning_count=warning_count,
        history_comparison_json={"status": history_status},
        summary_json={
            "history_status": history_status,
            "failed_count": failed_count,
            "warning_count": warning_count,
            "global_best_candidate_count": global_best_candidate_count,
            "global_best_generated_option_count": global_best_generated_option_count,
            "chain_integrity_ready_count": chain_integrity_ready_count,
            "chain_integrity_total_critical_issue_count": (
                chain_integrity_total_critical_issue_count
            ),
            "successor_chain_evaluation_passed_count": (
                successor_chain_evaluation_passed_count
            ),
            "successor_chain_effective_leaf_count": (
                successor_chain_effective_leaf_count
            ),
            "successor_chain_critical_issue_count": (
                successor_chain_critical_issue_count
            ),
            "successor_chain_ambiguous_source_count": (
                successor_chain_ambiguous_source_count
            ),
            "successor_chain_source_status_sync_required_count": (
                successor_chain_source_status_sync_required_count
            ),
            "ambiguous_successor_source_count": ambiguous_successor_source_count,
            "stale_recommendation_count": stale_recommendation_count,
            "successor_recompute_required_count": successor_recompute_required_count,
            "final_hit_sample_size": final_hit_sample_size,
            "final_hit_count": final_hit_count,
            "average_core_replay_roi": average_core_replay_roi,
            "upset_opportunity_count": upset_opportunity_count,
            "upset_capture_count": upset_capture_count,
        },
        created_at=datetime(2026, 5, 11, 0, tzinfo=UTC),
    )


def _historical_suite_gate_evidence(
    *,
    passed: bool = True,
    status: str = "passed",
    suite_status: str = "unchanged",
    slice_count: int = 30,
    comparison_count: int = 30,
    candidate_final_hit_sample_size: int = 30,
    candidate_final_hit_coverage_ratio: float = 1.0,
    candidate_final_hit_rate: float = 2 / 3,
    candidate_roi: float = 0.12,
    baseline_dynamic_mixed_final_answer_count: int = 0,
    candidate_dynamic_mixed_final_answer_count: int = 0,
    baseline_dynamic_mixed_final_answer_rate: float | None = None,
    candidate_dynamic_mixed_final_answer_rate: float | None = None,
    baseline_final_answer_market_type_counts: dict[str, int] | None = None,
    candidate_final_answer_market_type_counts: dict[str, int] | None = None,
    baseline_handicap_final_answer_count: int = 0,
    candidate_handicap_final_answer_count: int = 0,
    baseline_handicap_final_answer_rate: float | None = None,
    candidate_handicap_final_answer_rate: float | None = None,
    baseline_correct_score_final_answer_count: int = 0,
    candidate_correct_score_final_answer_count: int = 0,
    baseline_multiple_choice_final_answer_count: int = 0,
    candidate_multiple_choice_final_answer_count: int = 0,
    baseline_final_answer_selected_candidate_count: int = 0,
    candidate_final_answer_selected_candidate_count: int = 0,
    baseline_final_answer_multiple_choice_fixture_count: int = 0,
    candidate_final_answer_multiple_choice_fixture_count: int = 0,
    failed_checks: list[str] | None = None,
    lifecycle_quality_cycle_present: bool = True,
    lifecycle_quality_cycle_passed: bool = True,
    lifecycle_persisted_smoke_present: bool = True,
    lifecycle_persisted_smoke_passed: bool = True,
    lifecycle_source_status_synced: bool = True,
    lifecycle_effective_leaf_count: int = 1,
    lifecycle_active_edge_count: int = 1,
    lifecycle_critical_issue_count: int = 0,
    lifecycle_source_status_sync_required_count: int = 0,
    successor_chain_evaluation_present: bool = False,
    successor_chain_evaluation_passed: bool | None = None,
    successor_effective_final_only_ready: bool = False,
    successor_effective_leaf_count: int = 0,
    successor_active_edge_count: int = 0,
    successor_critical_issue_count: int = 0,
    successor_ambiguous_source_count: int = 0,
    successor_source_status_sync_required_count: int = 0,
    market_movement_runtime_replay_present: bool = False,
    market_movement_runtime_replay_passed: bool | None = None,
    market_movement_runtime_replay_status: str | None = None,
    market_movement_runtime_replay_allowed: bool = False,
    market_movement_runtime_replay_holdout_allowed: bool = False,
    market_movement_runtime_replay_rule_count: int = 0,
    market_movement_runtime_replay_selected_rule_count: int = 0,
    market_movement_runtime_replay_candidate_count: int = 0,
    market_movement_runtime_replay_accepted_count: int = 0,
    market_movement_runtime_replay_adjusted_fixture_count: int = 0,
    market_movement_runtime_replay_adjusted_prediction_count: int = 0,
    market_movement_runtime_replay_final_hit_rate_delta: float | None = None,
    market_movement_runtime_replay_roi_delta: float | None = None,
    market_movement_runtime_replay_profit_loss_delta: float | None = None,
    market_movement_runtime_replay_brier_score_delta: float | None = None,
    market_movement_runtime_replay_log_loss_delta: float | None = None,
    market_movement_runtime_replay_mean_calibration_error_delta: float | None = None,
    market_movement_runtime_replay_production_changed: bool = False,
    market_movement_runtime_replay_public_changed: bool = False,
) -> RecommendationHistoricalSuiteQualityGateEvidence:
    return RecommendationHistoricalSuiteQualityGateEvidence(
        gate_key="historical_recommendation_suite_quality_gate:core",
        passed=passed,
        status=status,
        suite_key="historical_recommendation_backtest_suite:core",
        suite_status=suite_status,
        summary_json={
            "suite_status": suite_status,
            "slice_count": slice_count,
            "comparison_count": comparison_count,
            "candidate_final_hit_sample_size": candidate_final_hit_sample_size,
            "candidate_final_hit_coverage_ratio": candidate_final_hit_coverage_ratio,
            "candidate_final_hit_rate": candidate_final_hit_rate,
            "candidate_roi": candidate_roi,
            "baseline_dynamic_mixed_final_answer_count": (
                baseline_dynamic_mixed_final_answer_count
            ),
            "candidate_dynamic_mixed_final_answer_count": (
                candidate_dynamic_mixed_final_answer_count
            ),
            "baseline_dynamic_mixed_final_answer_rate": (
                baseline_dynamic_mixed_final_answer_rate
            ),
            "candidate_dynamic_mixed_final_answer_rate": (
                candidate_dynamic_mixed_final_answer_rate
            ),
            "baseline_final_answer_market_type_counts": (
                baseline_final_answer_market_type_counts or {}
            ),
            "candidate_final_answer_market_type_counts": (
                candidate_final_answer_market_type_counts or {}
            ),
            "baseline_handicap_final_answer_count": (
                baseline_handicap_final_answer_count
            ),
            "candidate_handicap_final_answer_count": (
                candidate_handicap_final_answer_count
            ),
            "baseline_handicap_final_answer_rate": baseline_handicap_final_answer_rate,
            "candidate_handicap_final_answer_rate": candidate_handicap_final_answer_rate,
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
            "failed_checks": failed_checks or [],
            "lifecycle_quality_cycle_present": lifecycle_quality_cycle_present,
            "lifecycle_quality_cycle_passed": lifecycle_quality_cycle_passed,
            "lifecycle_persisted_smoke_present": lifecycle_persisted_smoke_present,
            "lifecycle_persisted_smoke_passed": lifecycle_persisted_smoke_passed,
            "lifecycle_source_status_synced": lifecycle_source_status_synced,
            "lifecycle_effective_leaf_count": lifecycle_effective_leaf_count,
            "lifecycle_active_edge_count": lifecycle_active_edge_count,
            "lifecycle_critical_issue_count": lifecycle_critical_issue_count,
            "lifecycle_source_status_sync_required_count": (
                lifecycle_source_status_sync_required_count
            ),
            "successor_chain_evaluation_present": (
                successor_chain_evaluation_present
            ),
            "successor_chain_evaluation_passed": successor_chain_evaluation_passed,
            "successor_effective_final_only_ready": successor_effective_final_only_ready,
            "successor_effective_leaf_count": successor_effective_leaf_count,
            "successor_active_edge_count": successor_active_edge_count,
            "successor_critical_issue_count": successor_critical_issue_count,
            "successor_ambiguous_source_count": successor_ambiguous_source_count,
            "successor_source_status_sync_required_count": (
                successor_source_status_sync_required_count
            ),
            "market_movement_runtime_replay_present": (
                market_movement_runtime_replay_present
            ),
            "market_movement_runtime_replay_passed": (
                market_movement_runtime_replay_passed
            ),
            "market_movement_runtime_replay_status": (
                market_movement_runtime_replay_status
            ),
            "market_movement_runtime_replay_allowed": (
                market_movement_runtime_replay_allowed
            ),
            "market_movement_runtime_replay_holdout_allowed": (
                market_movement_runtime_replay_holdout_allowed
            ),
            "market_movement_runtime_replay_rule_count": (
                market_movement_runtime_replay_rule_count
            ),
            "market_movement_runtime_replay_selected_rule_count": (
                market_movement_runtime_replay_selected_rule_count
            ),
            "market_movement_runtime_replay_candidate_count": (
                market_movement_runtime_replay_candidate_count
            ),
            "market_movement_runtime_replay_accepted_count": (
                market_movement_runtime_replay_accepted_count
            ),
            "market_movement_runtime_replay_adjusted_fixture_count": (
                market_movement_runtime_replay_adjusted_fixture_count
            ),
            "market_movement_runtime_replay_adjusted_prediction_count": (
                market_movement_runtime_replay_adjusted_prediction_count
            ),
            "market_movement_runtime_replay_final_hit_rate_delta": (
                market_movement_runtime_replay_final_hit_rate_delta
            ),
            "market_movement_runtime_replay_roi_delta": (
                market_movement_runtime_replay_roi_delta
            ),
            "market_movement_runtime_replay_profit_loss_delta": (
                market_movement_runtime_replay_profit_loss_delta
            ),
            "market_movement_runtime_replay_brier_score_delta": (
                market_movement_runtime_replay_brier_score_delta
            ),
            "market_movement_runtime_replay_log_loss_delta": (
                market_movement_runtime_replay_log_loss_delta
            ),
            "market_movement_runtime_replay_mean_calibration_error_delta": (
                market_movement_runtime_replay_mean_calibration_error_delta
            ),
            "market_movement_runtime_replay_production_changed": (
                market_movement_runtime_replay_production_changed
            ),
            "market_movement_runtime_replay_public_changed": (
                market_movement_runtime_replay_public_changed
            ),
        },
    )


def _budget_stability_audit_report(
    *,
    slice_count: int = 240,
    comparable_count: int = 240,
    signature_changed_count: int = 4,
    signature_change_rate: float = 4 / 240,
    harmful_change_count: int = 2,
    beneficial_change_count: int = 2,
    hit_delta_count: int = -1,
    profit_loss_delta: float = -2.5,
    roi_delta: float = -0.004,
    warnings: list[str] | None = None,
) -> HistoricalBudgetStabilityAuditReport:
    comparison = HistoricalBudgetStabilityComparisonSummary(
        budget=10.0,
        reference_budget=20.0,
        comparable_count=comparable_count,
        signature_changed_count=signature_changed_count,
        signature_change_rate=signature_change_rate,
        harmful_change_count=harmful_change_count,
        beneficial_change_count=beneficial_change_count,
        hit_delta_count=hit_delta_count,
        profit_loss_delta=profit_loss_delta,
        roi_delta=roi_delta,
        stake_delta=12.0,
        budget_adjusted_change_count=0,
    )
    return HistoricalBudgetStabilityAuditReport(
        report_key="historical_budget_stability_audit:test",
        status="generated",
        slice_count=slice_count,
        budgets=(10.0, 20.0),
        reference_budget=20.0,
        budget_runs=[
            HistoricalBudgetRunSummary(
                budget=10.0,
                final_answer_count=slice_count,
                final_hit_count=168,
                final_hit_rate=0.7,
                total_stake=684.0,
                profit_loss=9.1,
                roi=0.013,
                average_total_stake=2.85,
                multiple_final_answer_count=34,
                budget_adjusted_final_answer_count=0,
                heavy_budget_adjusted_final_answer_count=0,
                warning_count=0,
            ),
            HistoricalBudgetRunSummary(
                budget=20.0,
                final_answer_count=slice_count,
                final_hit_count=169,
                final_hit_rate=0.7041666666666667,
                total_stake=672.0,
                profit_loss=11.68,
                roi=0.017,
                average_total_stake=2.8,
                multiple_final_answer_count=32,
                budget_adjusted_final_answer_count=0,
                heavy_budget_adjusted_final_answer_count=0,
                warning_count=0,
            ),
        ],
        comparison_summaries=[comparison],
        changed_slice_count=signature_changed_count,
        harmful_change_count=harmful_change_count,
        beneficial_change_count=beneficial_change_count,
        warnings=warnings or [],
        summary_json={
            "calculation_basis": "historical_budget_stability_audit_v3_1",
            "slice_count": slice_count,
            "budgets": [10.0, 20.0],
            "reference_budget": 20.0,
            "signature_changed_count": signature_changed_count,
            "changed_slice_count": signature_changed_count,
            "harmful_change_count": harmful_change_count,
            "beneficial_change_count": beneficial_change_count,
            "comparison_summaries": [comparison.model_dump(mode="json")],
            "warnings": warnings or [],
        },
    )


def _final_answer_market_concentration_audit_report(
    *,
    status: str = "passed",
    passed: bool = True,
    slice_count: int = 5,
    final_answer_count: int = 5,
    dynamic_mixed_final_answer_count: int = 5,
    effective_constraint_profile_count: int = 2,
    failed_checks: list[str] | None = None,
    warnings: list[str] | None = None,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    constraint_profiles = [
        {
            "profile_key": (
                f"{pass_type}:multiple:max_outcomes_per_fixture={max_outcomes}"
                "|min_marginal_quality_gain=0"
            ),
            "pass_type": pass_type,
            "mode": "multiple",
            "constraint_profile_id": (
                f"max_outcomes_per_fixture={max_outcomes}|min_marginal_quality_gain=0"
            ),
            "constraint_profile_json": {
                "max_outcomes_per_fixture": max_outcomes,
                "min_marginal_quality_gain": 0.0,
            },
        }
        for pass_type, max_outcomes in (("2x1", 1), ("3x1", 2))[
            :effective_constraint_profile_count
        ]
    ]
    report = {
        "report_key": "historical_final_answer_market_concentration_audit:test",
        "audit_id": "historical-final-answer-market-concentration-audit-v3.1",
        "status": status,
        "passed": passed,
        "suite_key": "historical_recommendation_backtest_suite:test",
        "suite_status": "unchanged",
        "slice_count": slice_count,
        "comparison_count": slice_count,
        "final_answer_count": final_answer_count,
        "market_type_count": 2,
        "market_type_counts": {"1x2": 5, "cn_handicap_1x2": 2},
        "market_type_rates": {"1x2": 1.0, "cn_handicap_1x2": 0.4},
        "single_market_final_answer_count": 0,
        "single_market_final_answer_rate": 0.0,
        "single_market_type_counts": {},
        "single_market_type_rates": {},
        "dominant_single_market_type": None,
        "dominant_single_market_count": 0,
        "dominant_single_market_rate": None,
        "market_concentration_hhi": 0.5,
        "dynamic_mixed_final_answer_count": dynamic_mixed_final_answer_count,
        "dynamic_mixed_final_answer_rate": (
            dynamic_mixed_final_answer_count / final_answer_count
            if final_answer_count
            else None
        ),
        "handicap_final_answer_count": 2,
        "correct_score_final_answer_count": 0,
        "multiple_choice_final_answer_count": 5,
        "candidate_final_hit_rate": 0.6,
        "candidate_roi": 0.02,
        "candidate_profit_loss": 1.2,
        "aggregate_deltas_json": {},
        "checks": [
            {
                "name": name,
                "status": "failed",
                "actual": 0,
                "threshold": 1,
                "detail": "fixture check",
            }
            for name in failed_checks or []
        ],
        "single_market_slice_samples": [],
        "dynamic_mixed_slice_samples": [],
        "warnings": warnings or [],
        "summary_json": {
            "slice_count": slice_count,
            "final_answer_count": final_answer_count,
            "dynamic_mixed_final_answer_count": dynamic_mixed_final_answer_count,
            "dynamic_mixed_final_answer_rate": (
                dynamic_mixed_final_answer_count / final_answer_count
                if final_answer_count
                else None
            ),
            "dynamic_mix_final_answer_lane_effective_pass_types": ["2x1", "3x1"][
                :effective_constraint_profile_count
            ],
            "dynamic_mix_final_answer_lane_effective_constraint_profiles": (
                constraint_profiles
            ),
            "candidate_completed_dynamic_mix_final_answer_lane_count": 10,
            "candidate_final_answer_dynamic_mix_final_answer_lane_count": 5,
            "failed_checks": failed_checks or [],
            "warnings": warnings or [],
        },
    }
    return HistoricalFinalAnswerMarketConcentrationAuditReport.model_validate(report)


def _correct_score_admission_report(
    *,
    status: str = "accepted",
    production_allowed: bool = True,
    holdout_allowed: bool = True,
    correct_score_count: int = 3,
    failed_checks: list[str] | None = None,
    warnings: list[str] | None = None,
    roi_delta: float = 0.01,
    brier_score_delta: float = -0.01,
) -> HistoricalCorrectScoreAdmissionReport:
    failed_check_names = failed_checks or []
    return HistoricalCorrectScoreAdmissionReport(
        report_key="historical_correct_score_admission:test",
        status=status,
        production_recommendation_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
        source_gate_key="historical_recommendation_suite_quality_gate:test",
        source_gate_status="passed",
        source_suite_status="unchanged",
        slice_count=100,
        comparison_count=100,
        candidate_final_hit_sample_size=100,
        candidate_final_hit_coverage_ratio=1.0,
        candidate_final_hit_rate=0.65,
        candidate_roi=0.04,
        candidate_correct_score_final_answer_count=correct_score_count,
        candidate_correct_score_final_answer_rate=correct_score_count / 100,
        final_hit_rate_delta=0.01,
        roi_delta=roi_delta,
        profit_loss_delta=5.0,
        brier_score_delta=brier_score_delta,
        log_loss_delta=-0.01,
        mean_calibration_error_delta=-0.01,
        checks=[
            HistoricalCorrectScoreAdmissionCheck(
                name=name,
                status="failed",
                actual=0,
                threshold=1,
                detail="fixture check",
            )
            for name in failed_check_names
        ],
        decision_payload_json={
            "default_recommendation_path_changed": False,
        },
        warnings=warnings or [],
        summary_json={
            "status": status,
            "production_recommendation_allowed": production_allowed,
            "holdout_allowed": holdout_allowed,
            "candidate_correct_score_final_answer_count": correct_score_count,
            "failed_checks": failed_check_names,
            "warnings": warnings or [],
        },
    )


def _runtime_profile_switch_report(
    *,
    status: str = "switch_ready",
    switch_ready: bool = True,
    default_profile_write_requested: bool = False,
    default_profile_written: bool = False,
) -> HistoricalShortOddsRuntimeProfileSwitchReport:
    return HistoricalShortOddsRuntimeProfileSwitchReport.model_validate(
        {
            "report_key": "historical_short_odds_runtime_profile_switch:test",
            "status": status,
            "switch_ready": switch_ready,
            "activated_profile_version": "activated-profile-v1",
            "current_profile_version": "current-v1",
            "source_runtime_profile_activation_report_key": (
                "historical_short_odds_runtime_profile_activation:test"
            ),
            "source_activated_runtime_shadow_replay_report_key": (
                "historical_short_odds_runtime_shadow_replay:test"
            ),
            "candidate_rule_count": 1,
            "allowed_competition_ids": [
                "EPL",
                "FRA_LIGUE_1",
                "GER_BUNDESLIGA",
                "ITA_SERIE_A",
            ],
            "excluded_competition_ids": ["ESP_LA_LIGA"],
            "default_profile_write_requested": default_profile_write_requested,
            "default_profile_written": default_profile_written,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "blockers": [],
            "staged_profile_json": {},
            "warnings": [],
            "summary_json": {},
        }
    )


def _runtime_profile_switch_replay_report(
    *,
    passed: bool = True,
    final_answer_hit_rate_delta: float = 0.0,
    roi_delta: float = 0.016,
    profit_loss_delta: float = 1.0,
    harm_count_vs_original: int = 0,
    final_hit_harm_count_vs_original: int = 0,
    profit_loss_harm_count_vs_original: int = 0,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(
        {
            "report_key": "historical_short_odds_runtime_shadow_replay:test",
            "status": "shadow_replay_passed" if passed else "shadow_replay_failed",
            "passed": passed,
            "source_audit_report_key": "historical_candidate_marginal_audit:test",
            "source_rule_profile_version": "activated-profile-v1",
            "rule_count": 1,
            "enabled_rule_count": 1,
            "final_answer_count": 30,
            "changed_final_answer_count": 17,
            "baseline_final_answer_hit_count": 20,
            "shadow_final_answer_hit_count": 20,
            "final_answer_hit_delta_count": 0,
            "baseline_final_answer_hit_rate": 20 / 30,
            "shadow_final_answer_hit_rate": 20 / 30,
            "final_answer_hit_rate_delta": final_answer_hit_rate_delta,
            "baseline_profit_loss": 3.0,
            "shadow_profit_loss": 4.0,
            "profit_loss_delta": profit_loss_delta,
            "baseline_roi": 0.05,
            "shadow_roi": 0.066,
            "roi_delta": roi_delta,
            "total_stake": 60.0,
            "harm_count_vs_original": harm_count_vs_original,
            "final_hit_harm_count_vs_original": final_hit_harm_count_vs_original,
            "profit_loss_harm_count_vs_original": profit_loss_harm_count_vs_original,
            "average_hit_probability_delta_vs_original": -0.014,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "rule_set_json": {},
            "changed_items": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _global_planner_short_odds_adapter_gate_report(
    *,
    passed: bool = True,
    default_path_changed: bool = False,
    shadow_path_changed: bool = False,
    explicit_opt_in_changed: bool = True,
    roi_delta: float = 0.016,
    profit_loss_delta: float = 1.0,
    final_hit_harm_count: int = 0,
    profit_loss_harm_count: int = 0,
) -> HistoricalGlobalPlannerShortOddsAdapterGateReport:
    return HistoricalGlobalPlannerShortOddsAdapterGateReport.model_validate(
        {
            "report_key": "global_planner_short_odds_adapter_gate:test",
            "status": "passed" if passed else "failed",
            "passed": passed,
            "source_planner_branch_report_key": (
                "global_planner_short_odds_adapter_branch:test"
            ),
            "source_runtime_shadow_replay_report_key": (
                "historical_short_odds_runtime_shadow_replay:test"
            ),
            "source_rule_profile_version": "activated-profile-v1",
            "planner_default_path_changed": default_path_changed,
            "planner_shadow_path_changed": shadow_path_changed,
            "planner_explicit_opt_in_changed": explicit_opt_in_changed,
            "planner_shadow_adapter_status": "applied",
            "planner_opt_in_adapter_status": (
                "applied" if explicit_opt_in_changed else "unchanged"
            ),
            "runtime_replay_passed": passed,
            "runtime_replay_status": (
                "shadow_replay_passed" if passed else "shadow_replay_failed"
            ),
            "runtime_final_answer_count": 30,
            "runtime_changed_final_answer_count": 17,
            "runtime_final_answer_hit_rate_delta": 0.0,
            "runtime_roi_delta": roi_delta,
            "runtime_profit_loss_delta": profit_loss_delta,
            "runtime_harm_count_vs_original": (
                final_hit_harm_count + profit_loss_harm_count
            ),
            "runtime_final_hit_harm_count_vs_original": final_hit_harm_count,
            "runtime_profit_loss_harm_count_vs_original": profit_loss_harm_count,
            "runtime_average_hit_probability_delta": -0.014,
            "runtime_public_response_changed": False,
            "runtime_production_recommendation_changed": False,
            "checks": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _global_planner_short_odds_adapter_sample_expansion_report(
    *,
    status: str = "research_only",
    passed: bool = True,
    promotion_ready: bool = False,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport:
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport.model_validate(
        {
            "report_key": "global_planner_short_odds_adapter_sample_expansion:test",
            "status": status,
            "passed": passed,
            "promotion_ready": promotion_ready,
            "base_gate_report_key": "global_planner_short_odds_adapter_gate:test",
            "base_gate_passed": True,
            "supplemental_report_count": 1,
            "supplemental_passed_report_count": 1 if passed else 0,
            "supplemental_failed_report_count": 0 if passed else 1,
            "supplemental_final_answer_count": 56,
            "supplemental_changed_final_answer_count": 0,
            "supplemental_activation_rate": 0.0,
            "combined_final_answer_count": 86,
            "combined_changed_final_answer_count": 17,
            "combined_activation_rate": 17 / 86,
            "combined_final_answer_hit_rate_delta": 0.0,
            "combined_roi_delta": 0.0032,
            "combined_profit_loss_delta": 1.05,
            "combined_harm_count_vs_original": 0 if passed else 1,
            "combined_final_hit_harm_count_vs_original": 0 if passed else 1,
            "combined_profit_loss_harm_count_vs_original": 0 if passed else 1,
            "combined_average_hit_probability_delta": -0.014,
            "public_response_changed": False,
            "production_recommendation_changed": False,
            "checks": [],
            "warnings": [],
            "summary_json": {
                "watchlist_checks": (
                    []
                    if promotion_ready
                    else ["supplemental_changed_final_answer_count"]
                ),
                "failed_checks": [] if passed else ["combined_harm_count"],
            },
        }
    )


def _recommendation_strategy_promotion_gate_report(
    *,
    status: str = "ready",
    strategy_gate_ready: bool = True,
    total_final_answer_count: int = 99,
    total_changed_final_answer_count: int = 13,
    total_final_answer_hit_delta_count: int = 4,
    total_profit_loss_delta: float = 15.74,
    minimum_roi_delta: float | None = 0.040358974358974356,
    total_harm_count_vs_original: int = 0,
    total_final_hit_harm_count_vs_original: int = 0,
    total_profit_loss_harm_count_vs_original: int = 0,
    production_recommendation_changed: bool = False,
    public_response_changed: bool = False,
    blockers: Sequence[str] = (),
) -> RecommendationStrategyPromotionGateReport:
    return RecommendationStrategyPromotionGateReport.model_validate(
        {
            "gate_key": "recommendation_strategy_promotion_gate:test",
            "status": status,
            "strategy_gate_ready": strategy_gate_ready,
            "strategy_key": "probability_preserving_replacement",
            "gate_id": "v3_1_recommendation_strategy_promotion_gate",
            "production_recommendation_allowed": False,
            "production_recommendation_changed": production_recommendation_changed,
            "public_response_changed": public_response_changed,
            "evidence_count": 1,
            "ready_evidence_count": 1 if strategy_gate_ready else 0,
            "watchlist_evidence_count": 0,
            "blocked_evidence_count": 1 if status == "blocked" else 0,
            "selected_candidate_keys": ["candidate:probability_preserving"],
            "allowed_competition_ids": [
                "ENG_CHAMPIONSHIP",
                "ESP_SEGUNDA_DIVISION",
                "FRA_LIGUE_2",
                "GER_2_BUNDESLIGA",
                "ITA_SERIE_B",
            ],
            "total_final_answer_count": total_final_answer_count,
            "total_changed_final_answer_count": total_changed_final_answer_count,
            "total_final_answer_hit_delta_count": total_final_answer_hit_delta_count,
            "total_profit_loss_delta": total_profit_loss_delta,
            "minimum_roi_delta": minimum_roi_delta,
            "total_harm_count_vs_original": total_harm_count_vs_original,
            "total_final_hit_harm_count_vs_original": (
                total_final_hit_harm_count_vs_original
            ),
            "total_profit_loss_harm_count_vs_original": (
                total_profit_loss_harm_count_vs_original
            ),
            "minimum_active_surface_count": 8,
            "total_failed_surface_count": 0,
            "minimum_active_competition_fold_count": 5,
            "minimum_active_season_fold_count": 5,
            "minimum_active_rolling_fold_count": 13,
            "total_failed_fold_count": 0,
            "evidence": [],
            "checks": [],
            "blockers": list(blockers),
            "warnings": [],
            "summary_json": {
                "status": status,
                "strategy_gate_ready": strategy_gate_ready,
            },
        }
    )


def _recommendation_strategy_staged_activation_smoke_report(
    *,
    status: str = "staged_activation_ready",
    staged_activation_ready: bool = True,
    selected_rule_count: int = 1,
    allowed_competition_ids: Sequence[str] = (
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
    ),
    default_profile_written: bool = False,
    production_recommendation_changed: bool = False,
    public_response_changed: bool = False,
    blockers: Sequence[str] = (),
) -> RecommendationStrategyStagedActivationSmokeReport:
    return RecommendationStrategyStagedActivationSmokeReport.model_validate(
        {
            "report_key": "recommendation_strategy_staged_activation_smoke:test",
            "status": status,
            "staged_activation_ready": staged_activation_ready,
            "staged_profile_version": "strategy-staged-profile-test",
            "source_strategy_gate_key": "recommendation_strategy_promotion_gate:test",
            "source_strategy_key": "probability_preserving_replacement",
            "source_gate_id": "v3_1_recommendation_strategy_promotion_gate",
            "source_promotion_review_report_keys": ["promotion-review:test"],
            "source_selected_candidate_keys": ["candidate:probability_preserving"],
            "rule_profile_version": "strategy-staged-profile-test",
            "rule_count": 1,
            "selected_rule_count": selected_rule_count,
            "allowed_competition_ids": list(allowed_competition_ids),
            "excluded_competition_ids": [],
            "total_final_answer_count": 99,
            "total_changed_final_answer_count": 13,
            "total_final_answer_hit_delta_count": 4,
            "total_profit_loss_delta": 15.74,
            "minimum_roi_delta": 0.040358974358974356,
            "total_harm_count_vs_original": 0,
            "total_final_hit_harm_count_vs_original": 0,
            "total_profit_loss_harm_count_vs_original": 0,
            "minimum_active_surface_count": 8,
            "total_failed_surface_count": 0,
            "minimum_active_competition_fold_count": 5,
            "minimum_active_season_fold_count": 5,
            "minimum_active_rolling_fold_count": 13,
            "total_failed_fold_count": 0,
            "default_profile_write_requested": default_profile_written,
            "default_profile_written": default_profile_written,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": production_recommendation_changed,
            "public_response_changed": public_response_changed,
            "checks": [],
            "blockers": list(blockers),
            "staged_profile_json": {
                "profile_version": "strategy-staged-profile-test",
                "staged_only": True,
                "dry_run_only": True,
            },
            "public_contract_json": {
                "public_response_changed": public_response_changed,
                "production_recommendation_changed": production_recommendation_changed,
                "default_profile_written": default_profile_written,
            },
            "warnings": [],
            "summary_json": {
                "status": status,
                "staged_activation_ready": staged_activation_ready,
            },
        }
    )


def _recommendation_strategy_default_path_isolation_report(
    *,
    status: str = "isolated",
    default_path_isolated: bool = True,
    default_adapter_status: str = "disabled",
    default_adapter_selection_changed: bool = False,
    default_adapter_default_path_changed: bool = False,
    default_adapter_public_response_changed: bool = False,
    explicit_opt_in_adapter_status: str = "applied",
    explicit_opt_in_selection_changed: bool = True,
    explicit_opt_in_default_path_changed: bool = False,
    explicit_opt_in_public_response_changed: bool = False,
    default_profile_written: bool = False,
    production_recommendation_changed: bool = False,
    public_response_changed: bool = False,
    blockers: Sequence[str] = (),
) -> RecommendationStrategyDefaultPathIsolationReport:
    return RecommendationStrategyDefaultPathIsolationReport.model_validate(
        {
            "report_key": "recommendation_strategy_default_path_isolation:test",
            "status": status,
            "default_path_isolated": default_path_isolated,
            "isolation_id": "v3_1_recommendation_strategy_default_path_isolation",
            "source_staged_activation_smoke_report_key": (
                "recommendation_strategy_staged_activation_smoke:test"
            ),
            "source_strategy_gate_key": "recommendation_strategy_promotion_gate:test",
            "default_profile_path": "configs/recommendations/default.json",
            "default_profile_version": "default-profile-test",
            "staged_profile_path": "configs/recommendations/staged.json",
            "staged_profile_version": "strategy-staged-profile-test",
            "staged_profile_rule_count": 1,
            "staged_selected_rule_count": 1,
            "staged_allowed_competition_ids": [
                "ENG_CHAMPIONSHIP",
                "ESP_SEGUNDA_DIVISION",
                "FRA_LIGUE_2",
                "GER_2_BUNDESLIGA",
                "ITA_SERIE_B",
            ],
            "default_adapter_status": default_adapter_status,
            "default_adapter_selection_changed": default_adapter_selection_changed,
            "default_adapter_default_path_changed": (
                default_adapter_default_path_changed
            ),
            "default_adapter_public_response_changed": (
                default_adapter_public_response_changed
            ),
            "explicit_opt_in_adapter_status": explicit_opt_in_adapter_status,
            "explicit_opt_in_selection_changed": explicit_opt_in_selection_changed,
            "explicit_opt_in_default_path_changed": (
                explicit_opt_in_default_path_changed
            ),
            "explicit_opt_in_public_response_changed": (
                explicit_opt_in_public_response_changed
            ),
            "default_profile_written": default_profile_written,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": production_recommendation_changed,
            "public_response_changed": public_response_changed,
            "checks": [],
            "blockers": list(blockers),
            "default_adapter_result_json": {"status": default_adapter_status},
            "explicit_opt_in_adapter_result_json": {
                "status": explicit_opt_in_adapter_status
            },
            "warnings": [],
            "summary_json": {
                "status": status,
                "default_path_isolated": default_path_isolated,
            },
        }
    )


def _probability_calibration_profile_rolling_admission_report(
    *,
    status: str = "accepted",
    candidate_profile_allowed: bool = True,
    shadow_allowed: bool = True,
    profile_mode: str | None = "active",
    failed_fold_count: int = 0,
    active_competition_fold_count: int = 2,
    active_season_cutoff_fold_count: int = 3,
    active_rolling_fold_count: int = 2,
    adjusted_fixture_count: int = 24,
    bucket_count: int = 3,
    overall_gate_passed: bool = True,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    profile = (
        {
            "profile_key": "candidate_probability_calibration_profile:test",
            "source_report_key": (
                "historical_probability_calibration_profile_gate:test"
            ),
            "mode": profile_mode,
            "buckets": [
                {
                    "competition_id": "TEST",
                    "market_type": "1x2",
                    "outcome": "home_win",
                    "bucket_start": 0.0,
                    "bucket_end": 0.4,
                    "calibrated_probability": 0.36,
                    "sample_size": 30,
                },
                {
                    "competition_id": "TEST",
                    "market_type": "1x2",
                    "outcome": "draw",
                    "bucket_start": 0.0,
                    "bucket_end": 0.4,
                    "calibrated_probability": 0.28,
                    "sample_size": 30,
                },
                {
                    "competition_id": "TEST",
                    "market_type": "1x2",
                    "outcome": "away_win",
                    "bucket_start": 0.0,
                    "bucket_end": 0.4,
                    "calibrated_probability": 0.36,
                    "sample_size": 30,
                },
            ],
            "target_competition_ids": ["TEST"],
            "target_market_types": ["1x2"],
        }
        if profile_mode is not None
        else None
    )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport.model_validate(
        {
            "report_key": (
                "historical_probability_calibration_profile_rolling_admission:test"
            ),
            "status": status,
            "candidate_profile_allowed": candidate_profile_allowed,
            "shadow_allowed": shadow_allowed,
            "source_artifact_report_key": (
                "historical_probability_calibration_profile_artifact:test"
            ),
            "source_gate_report_key": (
                "historical_probability_calibration_profile_gate:test"
            ),
            "profile": profile,
            "overall_fold": {
                "fold_id": "overall:all",
                "fold_type": "overall",
                "status": "passed" if overall_gate_passed else "failed",
                "passed_final_answer_gate": overall_gate_passed,
                "emitted_profile": profile is not None,
                "adjusted_fixture_count": adjusted_fixture_count,
                "bucket_count": bucket_count,
                "selected_competition_ids": ["TEST"],
                "final_hit_rate_delta": 0.0,
                "roi_delta": 0.01,
                "profit_loss_delta": 1.0,
                "brier_score_delta": -0.01,
                "log_loss_delta": -0.02,
                "mean_calibration_error_delta": -0.01,
            },
            "fold_count": 7,
            "active_fold_count": (
                active_competition_fold_count
                + active_season_cutoff_fold_count
                + active_rolling_fold_count
            ),
            "failed_fold_count": failed_fold_count,
            "active_competition_fold_count": active_competition_fold_count,
            "active_season_cutoff_fold_count": active_season_cutoff_fold_count,
            "active_rolling_fold_count": active_rolling_fold_count,
            "checks": [],
            "folds": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _probability_calibration_profile_model_quality_gate_report(
    *,
    status: str = "model_quality_ready",
    model_quality_gate_passed: bool = True,
    selected_competition_ids: list[str] | None = None,
    adjusted_slice_count: int = 4,
    adjusted_fixture_count: int = 96,
    skipped_fixture_count: int = 0,
    final_answer_changed_count: int = 0,
    final_answer_hit_count_delta: int = 0,
    final_answer_hit_rate_delta: float | None = 0.0,
    roi_delta: float | None = 0.0,
    profit_loss_delta: float = 0.0,
    brier_score_delta: float | None = -0.01,
    log_loss_delta: float | None = -0.02,
    mean_calibration_error_delta: float | None = -0.01,
    failed_checks: list[str] | None = None,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateReport:
    resolved_competition_ids = selected_competition_ids or [
        "BUNDESLIGA",
        "EPL",
        "LA_LIGA",
        "SERIE_A",
    ]
    resolved_failed_checks = failed_checks or []
    return HistoricalProbabilityCalibrationProfileModelQualityGateReport.model_validate(
        {
            "report_key": (
                "historical_probability_calibration_profile_model_quality_gate:test"
            ),
            "status": status,
            "gate_id": "probability-calibration-profile-model-quality-test",
            "profile_gate_report_key": (
                "historical_probability_calibration_profile_gate:test"
            ),
            "model_quality_gate_passed": model_quality_gate_passed,
            "selected_competition_ids": resolved_competition_ids,
            "adjusted_slice_count": adjusted_slice_count,
            "adjusted_fixture_count": adjusted_fixture_count,
            "skipped_fixture_count": skipped_fixture_count,
            "final_answer_changed_count": final_answer_changed_count,
            "final_answer_hit_count_delta": final_answer_hit_count_delta,
            "final_answer_hit_rate_delta": final_answer_hit_rate_delta,
            "roi_delta": roi_delta,
            "profit_loss_delta": profit_loss_delta,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": log_loss_delta,
            "mean_calibration_error_delta": mean_calibration_error_delta,
            "checks": [
                {
                    "name": name,
                    "status": "failed",
                    "actual": None,
                    "threshold": None,
                    "detail": "test failed check",
                }
                for name in resolved_failed_checks
            ],
            "warnings": [],
            "summary_json": {
                "report_key": (
                    "historical_probability_calibration_profile_model_quality_gate:test"
                ),
                "status": status,
                "failed_checks": resolved_failed_checks,
            },
        }
    )


def _asian_handicap_segmented_model_quality_governance_report(
    *,
    status: str = "governance_ready",
    governance_review_ready: bool = True,
    accepted_segment_count: int = 3,
    shadow_segment_count: int = 0,
    fallback_segment_count: int = 2,
    rejected_segment_count: int = 0,
    accepted_validation_count: int = 138,
    calibration_sample_expansion_applied_count: int = 2,
    hit_rate_delta: float = 0.0,
    brier_score_delta: float = -0.001,
    log_loss_delta: float = -0.002,
    calibration_error_delta: float = -0.0003,
    actual_probability_delta: float = 0.0002,
    blockers: list[str] | None = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport:
    resolved_blockers = blockers or []
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport.model_validate(
        {
            "report_key": (
                "historical_prematch_feature_asian_handicap_segmented_governance_review:test"
            ),
            "status": status,
            "governance_review_ready": governance_review_ready,
            "internal_review_only": True,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "default_path_isolated": True,
            "review_id": "asian-handicap-segmented-governance-test",
            "source_admission_count": 1,
            "ready_admission_count": 1 if governance_review_ready else 0,
            "watchlist_admission_count": 0 if governance_review_ready else 1,
            "blocked_admission_count": 0,
            "accepted_segment_count": accepted_segment_count,
            "shadow_segment_count": shadow_segment_count,
            "fallback_segment_count": fallback_segment_count,
            "rejected_segment_count": rejected_segment_count,
            "calibration_sample_expansion_applied_count": (
                calibration_sample_expansion_applied_count
            ),
            "accepted_validation_count": accepted_validation_count,
            "accepted_segment_deltas_json": {
                "hit_rate_delta": hit_rate_delta,
                "brier_score_delta": brier_score_delta,
                "log_loss_delta": log_loss_delta,
                "expected_calibration_error_delta": calibration_error_delta,
                "average_actual_probability_delta": actual_probability_delta,
            },
            "accepted_segment_ids": ["EPL", "LIGUE_1", "SERIE_A"][
                :accepted_segment_count
            ],
            "fallback_segment_ids": ["LA_LIGA", "BUNDESLIGA"][
                :fallback_segment_count
            ],
            "shadow_segment_ids": [],
            "rejected_segment_ids": [],
            "evidence": [],
            "checks": [
                {
                    "name": name,
                    "status": "failed",
                    "actual": None,
                    "threshold": None,
                    "detail": "test failed check",
                }
                for name in resolved_blockers
            ],
            "blockers": resolved_blockers,
            "warnings": [],
            "staged_profile_json": {
                "dry_run_only": True,
                "internal_review_only": True,
                "production_recommendation_allowed": False,
                "production_recommendation_changed": False,
                "public_response_changed": False,
                "default_path_isolated": True,
            },
            "summary_json": {
                "report_key": (
                    "historical_prematch_feature_asian_handicap_segmented_governance_review:test"
                ),
                "status": status,
                "blockers": resolved_blockers,
            },
        }
    )


def _prematch_feature_quality_cycle_result(
    *,
    passed: bool = True,
    passing_candidate_count: int = 1,
    best_quality_gate_passed: bool = True,
    brier_score_delta: float = -0.01,
    log_loss_delta: float = -0.02,
    mean_calibration_error_delta: float = -0.01,
    warnings: list[str] | None = None,
) -> HistoricalPrematchFeatureQualityCycleResult:
    return HistoricalPrematchFeatureQualityCycleResult.model_validate(
        {
            "cycle_key": "historical_prematch_feature_quality_cycle:test",
            "status": "passed" if passed else "failed",
            "passed": passed,
            "cycle_id": "prematch-feature-quality-cycle-test",
            "final_answer_gate_report_key": (
                "historical_prematch_feature_final_answer_gate:test"
            ),
            "grid_report_key": "historical_prematch_feature_ablation_grid:test",
            "slice_count": 25,
            "fixture_count": 600,
            "evaluated_candidate_count": 5,
            "passing_candidate_count": passing_candidate_count,
            "best_feature_grid_candidate_id": (
                "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
            ),
            "best_feature_grid_rank": 1,
            "best_passed_final_answer_gate": best_quality_gate_passed,
            "best_suite_status": "improved" if passed else "mixed",
            "best_quality_gate_key": (
                "historical_recommendation_suite_quality_gate:test"
            ),
            "best_quality_gate_passed": best_quality_gate_passed,
            "best_failed_quality_check_names": (
                []
                if best_quality_gate_passed
                else [
                    "brier_score_delta",
                    "log_loss_delta",
                    "mean_calibration_error_delta",
                ]
            ),
            "best_deltas_json": {
                "final_hit_rate_delta": 0.02,
                "roi_delta": 0.03,
                "profit_loss_delta": 2.4,
                "brier_score_delta": brier_score_delta,
                "log_loss_delta": log_loss_delta,
                "mean_calibration_error_delta": mean_calibration_error_delta,
            },
            "final_answer_gate_summary_json": {"shadow_only": True},
            "warnings": warnings or [],
            "summary_json": {},
        }
    )


def _prematch_feature_rolling_admission_report(
    *,
    status: str = "accepted",
    candidate_feature_allowed: bool = True,
    shadow_allowed: bool = True,
    failed_fold_count: int = 0,
    active_competition_fold_count: int = 2,
    active_season_cutoff_fold_count: int = 3,
    active_rolling_fold_count: int = 2,
    evaluated_candidate_count: int = 5,
    passing_candidate_count: int = 1,
    overall_gate_passed: bool = True,
    brier_score_delta: float = -0.01,
    log_loss_delta: float = -0.02,
    mean_calibration_error_delta: float = -0.01,
) -> HistoricalPrematchFeatureRollingAdmissionReport:
    return HistoricalPrematchFeatureRollingAdmissionReport.model_validate(
        {
            "report_key": "historical_prematch_feature_rolling_admission:test",
            "status": status,
            "candidate_feature_allowed": candidate_feature_allowed,
            "shadow_allowed": shadow_allowed,
            "source_grid_report_key": (
                "historical_prematch_feature_ablation_grid:test"
            ),
            "overall_gate_report_key": (
                "historical_prematch_feature_final_answer_gate:test"
            ),
            "overall_fold": {
                "fold_id": "overall:all",
                "fold_type": "overall",
                "status": "passed" if overall_gate_passed else "failed",
                "grid_report_key": (
                    "historical_prematch_feature_ablation_grid:test"
                ),
                "gate_report_key": (
                    "historical_prematch_feature_final_answer_gate:test"
                ),
                "passed_final_answer_gate": overall_gate_passed,
                "evaluated_candidate_count": evaluated_candidate_count,
                "passing_candidate_count": passing_candidate_count,
                "adjusted_fixture_count": 600,
                "best_feature_grid_candidate_id": (
                    "prematch-feature-ablation-grid-shadow-v3.1:candidate_0001"
                ),
                "best_feature_grid_rank": 1,
                "best_quality_gate_passed": overall_gate_passed,
                "best_suite_status": "improved" if overall_gate_passed else "mixed",
                "final_hit_rate_delta": 0.02,
                "roi_delta": 0.03,
                "profit_loss_delta": 2.4,
                "brier_score_delta": brier_score_delta,
                "log_loss_delta": log_loss_delta,
                "mean_calibration_error_delta": mean_calibration_error_delta,
            },
            "fold_count": 7,
            "active_fold_count": (
                active_competition_fold_count
                + active_season_cutoff_fold_count
                + active_rolling_fold_count
            ),
            "failed_fold_count": failed_fold_count,
            "active_competition_fold_count": active_competition_fold_count,
            "active_season_cutoff_fold_count": active_season_cutoff_fold_count,
            "active_rolling_fold_count": active_rolling_fold_count,
            "checks": [],
            "folds": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _prematch_feature_sample_readiness_report(
    *,
    status: str = "accepted",
    sample_ready_allowed: bool = True,
    shadow_allowed: bool = True,
    accepted_source_count: int = 1,
    ready_fixture_count: int = 600,
    ready_competition_count: int = 3,
    ready_season_count: int = 2,
    ready_competition_season_count: int = 3,
) -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport.model_validate(
        {
            "readiness_key": "historical_prematch_feature_sample_readiness:test",
            "status": status,
            "sample_ready_allowed": sample_ready_allowed,
            "shadow_allowed": shadow_allowed,
            "readiness_id": "sample-readiness-test",
            "target_profile": "market_movement",
            "coverage_audit_key": "historical_sample_coverage_audit:test",
            "source_count": 1,
            "evaluated_source_count": 1,
            "accepted_source_count": accepted_source_count,
            "shadow_only_source_count": 1 if status == "shadow_only" else 0,
            "rejected_source_count": 1 if status == "rejected" else 0,
            "ready_source_ids": (
                ["market_feature_suite"] if accepted_source_count else []
            ),
            "ready_fixture_count": ready_fixture_count,
            "ready_slice_count": 25 if accepted_source_count else 0,
            "ready_competition_count": ready_competition_count,
            "ready_season_count": ready_season_count,
            "ready_competition_season_count": ready_competition_season_count,
            "checks": [],
            "sources": [],
            "warnings": [],
            "summary_json": {"status": status},
        }
    )


def _segment_penalty_runtime_replay_report(
    *,
    holdout_replay_allowed: bool = True,
    runtime_replay_allowed: bool = False,
    final_answer_hit_rate_delta: float = 2 / 30,
    roi_delta: float = 0.0703,
    profit_loss_delta: float = 4.22,
    harm_count_vs_baseline: int = 0,
    final_hit_harm_count_vs_baseline: int | None = None,
    profit_loss_harm_count_vs_baseline: int = 0,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport:
    status = (
        "runtime_replay_passed"
        if runtime_replay_allowed
        else "holdout_replay_passed"
        if holdout_replay_allowed
        else "shadow_replay_failed"
    )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport.model_validate(
        {
            "report_key": "historical_final_answer_segment_penalty_runtime_replay:test",
            "status": status,
            "runtime_replay_allowed": runtime_replay_allowed,
            "holdout_replay_allowed": holdout_replay_allowed,
            "source_rule_profile_version": "segment-profile-v1",
            "rule_count": 1,
            "selected_rule_count": 1,
            "baseline_suite_key": "historical_recommendation_backtest_suite:base",
            "candidate_suite_key": "historical_recommendation_backtest_suite:candidate",
            "final_answer_count": 30,
            "changed_final_answer_count": 2,
            "penalty_option_count": 2,
            "baseline_final_answer_hit_count": 23,
            "candidate_final_answer_hit_count": 25,
            "final_answer_hit_delta_count": 2,
            "final_answer_hit_rate_delta": final_answer_hit_rate_delta,
            "baseline_roi": -0.08,
            "candidate_roi": -0.01,
            "roi_delta": roi_delta,
            "profit_loss_delta": profit_loss_delta,
            "brier_score_delta": -0.03,
            "log_loss_delta": -0.07,
            "mean_calibration_error_delta": -0.04,
            "harm_count_vs_baseline": harm_count_vs_baseline,
            "final_hit_harm_count_vs_baseline": (
                harm_count_vs_baseline
                if final_hit_harm_count_vs_baseline is None
                else final_hit_harm_count_vs_baseline
            ),
            "profit_loss_harm_count_vs_baseline": (
                profit_loss_harm_count_vs_baseline
            ),
            "improvement_count_vs_baseline": 2,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [
                {
                    "name": "candidate_roi",
                    "status": "failed",
                    "actual": -0.01,
                    "threshold": 0.0,
                    "detail": "absolute ROI remains below production floor",
                }
            ],
            "rule_set_json": {},
            "selected_rule_json": {},
            "warnings": [],
            "summary_json": {},
        }
    )


def _market_movement_runtime_activation_report(
    *,
    status: str = "staged_activation_ready",
    staged_activation_ready: bool = True,
    selected_rule_count: int = 1,
    adjusted_fixture_count: int = 120,
    adjusted_prediction_count: int = 360,
    final_hit_rate_delta: float = 0.0,
    roi_delta: float = 0.0,
    profit_loss_delta: float = 0.0,
    brier_score_delta: float = -0.001288445,
    log_loss_delta: float = -0.002760848,
    mean_calibration_error_delta: float = -0.001278256,
    default_profile_written: bool = False,
    default_recommendation_path_changed: bool = False,
    production_recommendation_changed: bool = False,
    public_response_changed: bool = False,
    blockers: list[str] | None = None,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationReport:
    resolved_blockers = blockers or []
    return HistoricalMarketMovementRiskFilterRuntimeActivationReport.model_validate(
        {
            "report_key": "historical_market_movement_runtime_activation:test",
            "status": status,
            "staged_activation_ready": staged_activation_ready,
            "staged_profile_version": "market-movement-staged-v1",
            "source_suite_gate_key": "historical_suite_quality_gate:test",
            "source_runtime_replay_report_key": "runtime-replay:test",
            "source_runtime_profile_version": "market-movement-runtime-v1",
            "rule_count": 1,
            "selected_rule_count": selected_rule_count,
            "selected_rule_ids": [
                "market_movement_risk_filter_runtime_shadow_candidate_v1"
            ],
            "selected_segment_group_keys": ["competition_outcome:LA_LIGA:home_win"],
            "rollback_conditions": [
                "disable_if_shadow_replay_fails_no_harm_gate"
            ],
            "adjusted_fixture_count": adjusted_fixture_count,
            "adjusted_prediction_count": adjusted_prediction_count,
            "final_hit_rate_delta": final_hit_rate_delta,
            "roi_delta": roi_delta,
            "profit_loss_delta": profit_loss_delta,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": log_loss_delta,
            "mean_calibration_error_delta": mean_calibration_error_delta,
            "default_profile_write_requested": False,
            "default_profile_written": default_profile_written,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": production_recommendation_changed,
            "default_recommendation_path_changed": (
                default_recommendation_path_changed
            ),
            "public_response_changed": public_response_changed,
            "checks": [
                {
                    "name": blocker,
                    "status": "failed",
                    "actual": False,
                    "threshold": True,
                    "detail": "test blocker",
                }
                for blocker in resolved_blockers
            ],
            "blockers": resolved_blockers,
            "staged_profile_json": {"staged_only": True},
            "public_contract_json": {
                "public_response_changed": public_response_changed,
                "production_recommendation_changed": production_recommendation_changed,
                "default_recommendation_path_changed": (
                    default_recommendation_path_changed
                ),
                "default_profile_written": default_profile_written,
            },
            "warnings": [],
            "summary_json": {
                "status": status,
                "staged_activation_ready": staged_activation_ready,
                "selected_rule_count": selected_rule_count,
                "adjusted_fixture_count": adjusted_fixture_count,
                "adjusted_prediction_count": adjusted_prediction_count,
                "brier_score_delta": brier_score_delta,
                "blockers": resolved_blockers,
            },
        }
    )


def _market_movement_activation_sample_expansion_report(
    *,
    status: str = "shadow_only",
    passed: bool = True,
    promotion_ready: bool = False,
    blockers: list[str] | None = None,
    watchlist: list[str] | None = None,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionReport:
    resolved_blockers = blockers or []
    resolved_watchlist = watchlist or ["selected_segment_count_for_promotion"]
    return HistoricalMarketMovementRuntimeActivationSampleExpansionReport.model_validate(
        {
            "report_key": (
                "historical_market_movement_runtime_activation_sample_expansion:test"
            ),
            "status": status,
            "passed": passed,
            "promotion_ready": promotion_ready,
            "expansion_id": "market-movement-runtime-activation-sample-expansion-test",
            "source_activation_report_key": (
                "historical_market_movement_runtime_activation:test"
            ),
            "activation_status": "staged_activation_ready",
            "activation_ready": True,
            "selected_segment_group_keys": ["competition_outcome:LA_LIGA:home_win"],
            "selected_segment_competition_ids": ["LA_LIGA"],
            "selected_segment_competition_count": 1,
            "selected_segment_competition_season_count": 5,
            "readiness_report_count": 1,
            "coverage_audit_report_count": 1,
            "ready_source_count": 1,
            "supplemental_source_count": 1,
            "ready_fixture_count": 600,
            "ready_slice_count": 25,
            "ready_competition_count": 5,
            "ready_season_count": 5,
            "ready_competition_season_count": 25,
            "supplemental_fixture_count": 2520,
            "supplemental_slice_count": 210,
            "combined_fixture_count": 3120,
            "combined_slice_count": 235,
            "combined_competition_count": 12,
            "combined_season_count": 5,
            "combined_competition_season_count": 60,
            "adjusted_fixture_count": 120,
            "adjusted_prediction_count": 360,
            "adjusted_to_combined_fixture_ratio": 120 / 3120,
            "default_profile_written": False,
            "default_recommendation_path_changed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [
                {
                    "name": name,
                    "status": "failed",
                    "actual": False,
                    "threshold": True,
                    "detail": "test blocker",
                }
                for name in resolved_blockers
            ],
            "sources": [],
            "blockers": resolved_blockers,
            "watchlist": resolved_watchlist,
            "warnings": [],
            "summary_json": {
                "status": status,
                "passed": passed,
                "promotion_ready": promotion_ready,
                "combined_fixture_count": 3120,
                "watchlist": resolved_watchlist,
            },
        }
    )


def _market_movement_segment_replay_batch_gate_report(
    *,
    passed: bool = True,
    runtime_ready: bool = True,
    promotion_ready: bool = False,
    status: str = "watchlist",
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport:
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport.model_validate(
        {
            "report_key": "historical_market_movement_segment_replay_batch_gate:test",
            "status": status,
            "passed": passed,
            "runtime_replay_batch_ready": runtime_ready,
            "production_promotion_ready": promotion_ready,
            "gate_id": "segment-replay-batch-test",
            "source_segment_expansion_report_key": (
                "historical_market_movement_runtime_activation_segment_expansion:test"
            ),
            "source_segment_expansion_status": "watchlist",
            "source_segment_expansion_passed": True,
            "source_runtime_replay_expansion_ready": True,
            "source_production_promotion_ready": False,
            "replay_report_count": 4,
            "passed_replay_count": 4,
            "failed_replay_count": 0,
            "runtime_allowed_replay_count": 4,
            "distinct_rule_count": 4,
            "distinct_segment_count": 4,
            "covered_selected_segment_count": 4,
            "total_adjusted_fixture_count": 1323,
            "total_adjusted_prediction_count": 3969,
            "weighted_final_hit_rate_delta": 0.0,
            "weighted_roi_delta": 0.0,
            "total_profit_loss_delta": 0.0,
            "weighted_brier_score_delta": -0.001158,
            "weighted_log_loss_delta": -0.002435,
            "weighted_mean_calibration_error_delta": -0.001259,
            "worst_final_hit_rate_delta": 0.0,
            "worst_roi_delta": 0.0,
            "worst_brier_score_delta": -0.000296,
            "worst_log_loss_delta": -0.000656,
            "worst_mean_calibration_error_delta": -0.000299,
            "selected_rule_ids": ["rule-a", "rule-b", "rule-c", "rule-d"],
            "selected_segment_group_keys": [
                "segment:a",
                "segment:b",
                "segment:c",
                "segment:d",
            ],
            "replayed_rule_ids": ["rule-a", "rule-b", "rule-c", "rule-d"],
            "replayed_segment_group_keys": [
                "segment:a",
                "segment:b",
                "segment:c",
                "segment:d",
            ],
            "missing_selected_segment_group_keys": [],
            "unexpected_replayed_rule_ids": [],
            "unexpected_replayed_segment_group_keys": [],
            "default_recommendation_path_changed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "replay_summaries": [],
            "checks": [],
            "blockers": [] if passed else ["batch_gate_failed"],
            "watchlist": ["segment_expansion_production_promotion_ready"]
            if not promotion_ready
            else [],
            "warnings": [],
            "summary_json": {
                "status": status,
                "passed": passed,
                "runtime_replay_batch_ready": runtime_ready,
                "production_promotion_ready": promotion_ready,
                "replay_report_count": 4,
                "passed_replay_count": 4,
                "total_adjusted_fixture_count": 1323,
                "total_adjusted_prediction_count": 3969,
            },
        }
    )


def _replacement_reranker_shadow_admission_report(
    *,
    status: str = "accepted",
    runtime_profile_candidate_allowed: bool = True,
    shadow_allowed: bool = True,
    scoped: bool = True,
    failed_fold_count: int = 0,
    hit_delta_vs_model_top: int = 1,
    profit_loss_delta_vs_model_top: float = 4.1,
    roi_delta_vs_model_top: float = 0.12058823529411763,
    harm_count_vs_model_top: int = 0,
    final_hit_harm_count_vs_model_top: int = 0,
    profit_loss_harm_count_vs_model_top: int = 0,
    source_surface_kind: str = "prematch_replacement_surface",
    source_surface_missed_legs_only: bool | None = False,
) -> HistoricalReplacementRerankerShadowAdmissionReport:
    return HistoricalReplacementRerankerShadowAdmissionReport.model_validate(
        {
            "report_key": "historical_replacement_reranker_shadow_admission:test",
            "status": status,
            "runtime_profile_candidate_allowed": runtime_profile_candidate_allowed,
            "shadow_allowed": shadow_allowed,
            "source_audit_report_key": "historical_candidate_marginal_audit:test",
            "source_tolerance_grid_report_key": (
                "historical_replacement_reranker_tolerance_grid:test"
            ),
            "overall_shadow_gate_report_key": (
                "historical_replacement_reranker_shadow_gate:test"
            ),
            "profile_id": "quality_edge_blend_v1",
            "hit_probability_delta_threshold": -0.02,
            "fold_count": 12,
            "active_fold_count": 9,
            "failed_fold_count": failed_fold_count,
            "active_competition_fold_count": 2,
            "active_season_fold_count": 3,
            "active_rolling_fold_count": 4,
            "checks": [],
            "folds": [],
            "warnings": [],
            "summary_json": {
                "source_surface": {
                    "kind": source_surface_kind,
                    "missed_legs_only": source_surface_missed_legs_only,
                    "selected_leg_count": 27,
                    "final_answer_count": 42,
                },
                "scope": {
                    "enabled": scoped,
                    "scoped_final_answer_count": 19 if scoped else 0,
                    "scoped_competition_ids": (
                        ["ENG_CHAMPIONSHIP", "FRA_LIGUE_2"] if scoped else []
                    ),
                    "scoped_season_ids": (
                        ["2020_2021", "2021_2022"] if scoped else []
                    ),
                },
                "overall_shadow_final_answer_count": 17,
                "overall_changed_from_model_top_count": 5,
                "overall_hit_delta_vs_model_top_count": hit_delta_vs_model_top,
                "overall_profit_loss_delta_vs_model_top": (
                    profit_loss_delta_vs_model_top
                ),
                "overall_roi_delta_vs_model_top": roi_delta_vs_model_top,
                "overall_harm_count_vs_model_top": harm_count_vs_model_top,
                "overall_final_hit_harm_count_vs_model_top": (
                    final_hit_harm_count_vs_model_top
                ),
                "overall_profit_loss_harm_count_vs_model_top": (
                    profit_loss_harm_count_vs_model_top
                ),
            },
        }
    )
