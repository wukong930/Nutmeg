from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.chain_integrity import (
    RecommendationChainIntegrityOptions,
    RecommendationChainRunNode,
    build_recommendation_chain_integrity_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentGateOptions,
    HistoricalMarketMovementSegmentGateReport,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_market_movement_segment_quality_cycle import (
    HistoricalMarketMovementSegmentQualityCycleOptions,
    _options_from_args,
    _parse_args,
    run_historical_market_movement_segment_quality_cycle,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.persisted_lifecycle_smoke import (
    RecommendationPersistedLifecycleSmokeResult,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationOptions,
    RecommendationSuccessorChainEvaluationResult,
    build_recommendation_successor_chain_evaluation_result,
)


def test_market_movement_segment_quality_cycle_passes_with_successor_chain_gate() -> None:
    segment_gate_report = _segment_gate_report()
    successor_chain = _successor_chain_evaluation()

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        successor_chain_evaluation=successor_chain,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            require_successor_chain_evaluation=True,
            min_successor_effective_leaf_count=1,
            min_successor_active_edge_count=1,
            min_best_final_answer_changed_count=0,
            max_best_brier_score_delta=None,
            max_best_log_loss_delta=None,
            max_best_mean_calibration_error_delta=None,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.accepted_count == 1
    assert result.successor_chain_evaluation_present is True
    assert result.successor_chain_evaluation_passed is True
    assert result.summary_json["successor_chain_effective_leaf_count"] == 1
    assert result.summary_json["successor_chain_active_edge_count"] == 1
    assert all(check.status != "failed" for check in result.checks)


def test_market_movement_segment_quality_cycle_passes_with_persisted_lifecycle_smoke() -> (
    None
):
    segment_gate_report = _segment_gate_report()
    persisted_lifecycle_smoke = _persisted_lifecycle_smoke()

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            require_persisted_lifecycle_smoke=True,
            min_persisted_lifecycle_effective_leaf_count=1,
            min_persisted_lifecycle_active_edge_count=1,
            min_best_final_answer_changed_count=0,
            max_best_brier_score_delta=None,
            max_best_log_loss_delta=None,
            max_best_mean_calibration_error_delta=None,
        ),
    )

    assert result.passed is True
    assert result.persisted_lifecycle_smoke_present is True
    assert result.persisted_lifecycle_smoke_passed is True
    assert result.summary_json["persisted_lifecycle_source_status_synced"] is True
    assert result.summary_json["persisted_lifecycle_effective_leaf_count"] == 1
    assert result.summary_json["persisted_lifecycle_active_edge_count"] == 1
    assert all(check.status != "failed" for check in result.checks)


def test_market_movement_segment_quality_cycle_fails_without_required_successor_chain() -> (
    None
):
    segment_gate_report = _segment_gate_report()

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            require_successor_chain_evaluation=True,
            min_best_final_answer_changed_count=0,
        ),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "successor_chain_evaluation_present" in failed_names
    assert (
        "market_movement_segment_quality_cycle:missing_successor_chain_evaluation"
        in result.warnings
    )


def test_market_movement_segment_quality_cycle_fails_without_required_persisted_smoke() -> (
    None
):
    segment_gate_report = _segment_gate_report()

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            require_persisted_lifecycle_smoke=True,
            min_best_final_answer_changed_count=0,
        ),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "persisted_lifecycle_smoke_present" in failed_names
    assert (
        "market_movement_segment_quality_cycle:missing_persisted_lifecycle_smoke"
        in result.warnings
    )


def test_market_movement_segment_quality_cycle_blocks_unsynced_persisted_source() -> (
    None
):
    segment_gate_report = _segment_gate_report()
    persisted_lifecycle_smoke = _persisted_lifecycle_smoke(
        passed=True,
        source_status_synced=False,
    )

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            require_persisted_lifecycle_smoke=True,
            min_best_final_answer_changed_count=0,
        ),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "persisted_lifecycle_source_status_synced" in failed_names


def test_market_movement_segment_quality_cycle_blocks_no_effective_final_answer_change() -> None:
    segment_gate_report = _segment_gate_report()

    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        options=HistoricalMarketMovementSegmentQualityCycleOptions(
            min_best_final_answer_changed_count=99,
        ),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "best_final_answer_changed_count" in failed_names
    assert (
        "market_movement_segment_quality_cycle:failed_check:"
        "best_final_answer_changed_count"
    ) in result.warnings


def test_market_movement_segment_quality_cycle_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--segment-gate-report-path",
            "tmp/segment_gate.json",
            "--successor-chain-evaluation-report-path",
            "tmp/successor_chain.json",
            "--persisted-lifecycle-smoke-report-path",
            "tmp/persisted_lifecycle_smoke.json",
            "--output-path",
            "tmp/segment_quality_cycle.json",
            "--cycle-id",
            "segment-cycle-test",
            "--min-accepted-candidate-count",
            "2",
            "--allow-best-candidate-rejected",
            "--min-best-final-answer-changed-count",
            "3",
            "--min-best-final-hit-rate-delta",
            "-0.10",
            "--max-best-brier-score-delta",
            "0.03",
            "--max-best-log-loss-delta",
            "0.04",
            "--max-best-mean-calibration-error-delta",
            "0.05",
            "--require-successor-chain-evaluation",
            "--min-successor-effective-leaf-count",
            "4",
            "--min-successor-active-edge-count",
            "2",
            "--max-successor-critical-issue-count",
            "0",
            "--max-successor-ambiguous-source-count",
            "1",
            "--max-successor-source-status-sync-required-count",
            "2",
            "--require-persisted-lifecycle-smoke",
            "--allow-unsynced-persisted-lifecycle-source-status",
            "--min-persisted-lifecycle-effective-leaf-count",
            "6",
            "--min-persisted-lifecycle-active-edge-count",
            "3",
            "--max-persisted-lifecycle-critical-issue-count",
            "1",
            "--max-persisted-lifecycle-source-status-sync-required-count",
            "4",
            "--max-cycle-warning-count",
            "5",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.cycle_id == "segment-cycle-test"
    assert options.min_accepted_candidate_count == 2
    assert options.require_best_candidate_accepted is False
    assert options.min_best_final_answer_changed_count == 3
    assert options.min_best_final_hit_rate_delta == -0.10
    assert options.max_best_brier_score_delta == 0.03
    assert options.max_best_log_loss_delta == 0.04
    assert options.max_best_mean_calibration_error_delta == 0.05
    assert options.require_successor_chain_evaluation is True
    assert options.min_successor_effective_leaf_count == 4
    assert options.min_successor_active_edge_count == 2
    assert options.max_successor_critical_issue_count == 0
    assert options.max_successor_ambiguous_source_count == 1
    assert options.max_successor_source_status_sync_required_count == 2
    assert options.require_persisted_lifecycle_smoke is True
    assert options.require_persisted_lifecycle_source_status_synced is False
    assert options.min_persisted_lifecycle_effective_leaf_count == 6
    assert options.min_persisted_lifecycle_active_edge_count == 3
    assert options.max_persisted_lifecycle_critical_issue_count == 1
    assert options.max_persisted_lifecycle_source_status_sync_required_count == 4
    assert options.max_cycle_warning_count == 5


def _segment_gate_report() -> HistoricalMarketMovementSegmentGateReport:
    return build_historical_market_movement_segment_gate_report(
        [_away_movement_slice()],
        options=HistoricalMarketMovementSegmentGateOptions(
            segment_group_keys=("competition_outcome:TEST:away_win",),
            movement_weight=1.0,
            max_probability_shift=0.20,
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                min_probability=0.05,
                max_outcomes_per_fixture=1,
                max_candidates_per_fixture=1,
                optimizer_profile="solver",
            ),
            quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                min_slice_count=1,
                min_comparison_count=1,
                min_final_hit_sample_size=0,
                fail_on_suite_statuses=(),
                min_final_hit_rate_delta=None,
                max_brier_score_delta=None,
                max_log_loss_delta=None,
                max_mean_calibration_error_delta=None,
            ),
        ),
    )


def _successor_chain_evaluation() -> RecommendationSuccessorChainEvaluationResult:
    options = RecommendationChainIntegrityOptions(
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 3, 0),
    )
    chain_integrity = build_recommendation_chain_integrity_report(
        [
            _node(1, status="superseded"),
            _node(2, status="current", source_recommendation_run_id=1),
        ],
        options=options,
    )
    return build_recommendation_successor_chain_evaluation_result(
        chain_integrity,
        options=RecommendationSuccessorChainEvaluationOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            min_effective_leaf_count=1,
            min_active_edge_count=1,
            max_critical_issue_count=0,
            max_ambiguous_successor_source_count=0,
            max_source_status_sync_required_count=0,
        ),
    )


def _persisted_lifecycle_smoke(
    *,
    passed: bool = True,
    source_status_synced: bool = True,
) -> RecommendationPersistedLifecycleSmokeResult:
    return RecommendationPersistedLifecycleSmokeResult(
        passed=passed,
        dry_run=False,
        executed=True,
        as_of_time_utc=_dt(2026, 5, 1, 0),
        lock_time_utc=_dt(2026, 5, 1, 12),
        successor_as_of_time_utc=_dt(2026, 5, 1, 19),
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 2, 0),
        pass_type="1x1",
        mode="single",
        strategy="accuracy_first",
        source_recommendation_run_id=1,
        successor_recommendation_run_id=2,
        locked_fixture_ids=["A"],
        continuation_fixture_ids=[],
        summary_json={
            "passed": passed,
            "executed": True,
            "source_status_synced": source_status_synced,
            "successor_chain_evaluation_passed": passed,
            "successor_chain_effective_leaf_count": 1,
            "successor_chain_active_edge_count": 1,
            "successor_chain_critical_issue_count": 0,
            "successor_chain_source_status_sync_required_count": 0,
        },
    )


def _node(
    recommendation_run_id: int,
    *,
    status: str,
    source_recommendation_run_id: int | None = None,
) -> RecommendationChainRunNode:
    return RecommendationChainRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=f"run-{recommendation_run_id}",
        as_of_time_utc=_dt(2026, 5, recommendation_run_id, 10),
        strategy="accuracy_first",
        pass_type="1x1",
        mode="single",
        status=status,
        selected_fixture_ids=["A"],
        locked_fixture_ids=[],
        source_recommendation_run_id=source_recommendation_run_id,
        source_run_key=f"run-{source_recommendation_run_id}"
        if source_recommendation_run_id
        else None,
        created_at=_dt(2026, 5, recommendation_run_id, 10),
    )


def _away_movement_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="market_movement_segment_quality_cycle_unit_slice",
            name="Market movement segment quality cycle unit slice",
            competition_id="TEST",
            season="2024-2025",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=_dt(2024, 8, 1, 12),
        fixtures=[
            _fixture("fixture_1", day_offset=1),
            _fixture("fixture_2", day_offset=2),
            _fixture("fixture_3", day_offset=3),
        ],
    )


def _fixture(fixture_id: str, *, day_offset: int) -> HistoricalFixture:
    kickoff = _dt(2024, 8, 1, 12) + timedelta(days=day_offset)
    opening = (0.43, 0.27, 0.30)
    closing = (0.34, 0.21, 0.45)
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff,
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=0,
        actual_away_goals=1,
        prediction_time_utc=kickoff - timedelta(days=1),
        model_version="market-movement-segment-quality-cycle-test",
        feature_version="market-movement-feature-test",
        calibration_version="uncalibrated",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome=outcome,
                probability=probability,
                decimal_odds=1.0 / probability,
                market_probability=probability,
            )
            for outcome, probability in zip(
                ("home_win", "draw", "away_win"),
                opening,
                strict=True,
            )
        ],
        feature_snapshot=FeatureSnapshot(
            fixture_id=fixture_id,
            feature_time_utc=kickoff - timedelta(days=1),
            feature_version="market-movement-feature-test",
            data_quality_score=80.0,
            features_json={
                "prematch_context": {
                    "odds_movement": [
                        _movement(outcome, opening_probability, closing_probability)
                        for outcome, opening_probability, closing_probability in zip(
                            ("home_win", "draw", "away_win"),
                            opening,
                            closing,
                            strict=True,
                        )
                    ]
                }
            },
            source_snapshot_refs={"prematch": {"odds_movement": [fixture_id]}},
        ),
    )


def _movement(
    outcome: str,
    opening_probability: float,
    closing_probability: float,
) -> dict[str, object]:
    return {
        "market_type": "1x2",
        "outcome": outcome,
        "opening_prob": opening_probability,
        "current_prob": closing_probability,
        "probability_delta": closing_probability - opening_probability,
        "opening_decimal_odds": 1.0 / opening_probability,
        "current_decimal_odds": 1.0 / closing_probability,
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
