from __future__ import annotations

from datetime import UTC, datetime
from json import loads
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.final_answer_quality_signal_profile_grid import (
    HistoricalFinalAnswerQualitySignalProfileGridOptions,
    _historical_slices_from_args,
    _options_from_args,
    _parse_args,
    _parse_merge_args,
    _quality_signal_profile_comparison_items,
    _rejection_reason_codes,
    _suite_deltas,
    build_historical_final_answer_quality_signal_profile_grid_report,
    merge_historical_final_answer_quality_signal_profile_grid_reports,
)


def test_quality_signal_profile_grid_accepts_non_regressing_candidate() -> None:
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.35,),
            max_model_edge_values=(0.0,),
            strength_values=(0.04,),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
        ),
    )

    assert report.accepted_count == 1
    assert report.rejected_count == 0
    candidate = report.accepted_candidates[0]
    assert candidate.status == "accepted"
    assert candidate.competition_ids == ("TEST",)
    assert candidate.affected_leg_count >= 1
    assert candidate.reason_codes == []
    assert report.best_candidate == candidate
    assert report.summary_json["accepted_candidate_keys"] == [candidate.candidate_key]


def test_quality_signal_profile_grid_rejects_inactive_competition_group() -> None:
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("OTHER",),),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
        ),
    )

    assert report.accepted_count == 0
    assert report.rejected_count == 1
    candidate = report.candidates[0]
    assert candidate.affected_leg_count == 0
    assert "quality_signal_profile:affected_leg_count_too_low" in candidate.reason_codes


def test_quality_signal_profile_grid_rejects_candidate_below_roi_floor() -> None:
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.35,),
            max_model_edge_values=(0.0,),
            strength_values=(0.04,),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
            min_candidate_roi=2.0,
        ),
    )

    assert report.accepted_count == 0
    assert report.rejected_count == 1
    candidate = report.candidates[0]
    assert "quality_signal_profile:candidate_roi_below_floor" in candidate.reason_codes
    assert candidate.watchlist_eligible is False
    assert candidate.watchlist_reason_codes == []
    assert report.watchlist_count == 0
    assert report.summary_json["min_candidate_roi"] == 2.0


def test_quality_signal_profile_grid_marks_near_roi_floor_watchlist_candidate() -> None:
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.35,),
            max_model_edge_values=(0.0,),
            strength_values=(0.04,),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
            min_candidate_roi=2.0,
            watchlist_max_candidate_roi_shortfall=3.0,
            watchlist_min_final_hit_count_delta=0,
            watchlist_min_roi_delta=0.0,
            watchlist_min_profit_loss_delta=0.0,
        ),
    )

    assert report.accepted_count == 0
    assert report.rejected_count == 1
    assert report.watchlist_count == 1
    candidate = report.candidates[0]
    assert candidate.status == "rejected"
    assert candidate.watchlist_eligible is True
    assert candidate.watchlist_reason_codes == []
    assert report.watchlist_candidates == [candidate]
    assert report.best_watchlist_candidate == candidate
    assert report.summary_json["watchlist_candidate_keys"] == [candidate.candidate_key]
    assert report.summary_json["best_watchlist_candidate_key"] == candidate.candidate_key


def test_quality_signal_profile_grid_rejects_original_candidate_harm() -> None:
    baseline_suite = _suite_result(
        suite_key="baseline-suite",
        slice_id="harm_slice",
        actual_hit=True,
        profit_loss=0.60,
        final_answer_fixture_ids=("safe_a",),
        candidate_summary={
            "candidate_final_hit_count": 1,
            "candidate_final_hit_rate": 1.0,
            "candidate_roi": 0.30,
            "candidate_profit_loss": 0.60,
            "candidate_brier_score": 0.04,
            "candidate_log_loss": 0.20,
            "candidate_mean_calibration_error": 0.20,
            "candidate_upset_capture_rate": 0.0,
            "candidate_final_answer_quality_signal_affected_leg_count": 0,
            "final_answer_changed_count": 0,
        },
    )
    candidate_suite = _suite_result(
        suite_key="candidate-suite",
        slice_id="harm_slice",
        actual_hit=False,
        profit_loss=-2.00,
        final_answer_fixture_ids=("risky_b",),
        candidate_summary={
            "candidate_final_hit_count": 0,
            "candidate_final_hit_rate": 0.0,
            "candidate_roi": -1.0,
            "candidate_profit_loss": -2.00,
            "candidate_brier_score": 0.49,
            "candidate_log_loss": 1.20,
            "candidate_mean_calibration_error": 0.70,
            "candidate_upset_capture_rate": 0.0,
            "candidate_final_answer_quality_signal_affected_leg_count": 1,
            "final_answer_changed_count": 1,
        },
    )

    deltas = _suite_deltas(baseline_suite, candidate_suite)
    strict_options = HistoricalFinalAnswerQualitySignalProfileGridOptions(
        min_affected_leg_count=0,
        fail_on_suite_statuses=(),
        min_final_hit_count_delta=-1,
        min_final_hit_rate_delta=-1.0,
        min_roi_delta=-2.0,
        min_profit_loss_delta=-10.0,
        max_final_hit_harm_count_vs_baseline=0,
        max_profit_loss_harm_count_vs_baseline=0,
        max_brier_score_delta=10.0,
        max_log_loss_delta=10.0,
        max_mean_calibration_error_delta=10.0,
        require_objective_improvement=False,
    )
    permissive_options = strict_options.model_copy(
        update={
            "max_final_hit_harm_count_vs_baseline": 1,
            "max_profit_loss_harm_count_vs_baseline": 1,
        }
    )

    assert deltas["final_answer_changed_count_vs_baseline"] == 1
    assert deltas["final_hit_harm_count_vs_baseline"] == 1
    assert deltas["profit_loss_harm_count_vs_baseline"] == 1
    comparison_items = _quality_signal_profile_comparison_items(
        [_quality_signal_profile_slice(slice_id="harm_slice")],
        baseline_suite,
        candidate_suite,
        filter_mode="harmed",
        limit=10,
    )
    assert len(comparison_items) == 1
    comparison_item = comparison_items[0]
    assert comparison_item.slice_id == "harm_slice"
    assert comparison_item.competition_id == "TEST"
    assert comparison_item.final_answer_changed is True
    assert comparison_item.final_hit_harmed_vs_baseline is True
    assert comparison_item.profit_loss_harmed_vs_baseline is True
    assert comparison_item.profit_loss_delta == -2.6
    assert comparison_item.reason_codes == [
        "quality_signal_profile_item:final_answer_changed",
        "quality_signal_profile_item:final_hit_harmed",
        "quality_signal_profile_item:profit_loss_harmed",
    ]
    strict_reason_codes = _rejection_reason_codes(
        candidate_suite,
        deltas=deltas,
        objective_improvement_satisfied=True,
        options=strict_options,
    )
    assert (
        "quality_signal_profile:final_hit_harm_count_above_threshold"
        in strict_reason_codes
    )
    assert (
        "quality_signal_profile:profit_loss_harm_count_above_threshold"
        in strict_reason_codes
    )
    assert (
        "quality_signal_profile:final_hit_harm_count_above_threshold"
        not in _rejection_reason_codes(
            candidate_suite,
            deltas=deltas,
            objective_improvement_satisfied=True,
            options=permissive_options,
        )
    )


def test_quality_signal_profile_grid_batches_and_reuses_candidate_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "quality-signal-profile-cache"
    options = HistoricalFinalAnswerQualitySignalProfileGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1", "2x1"),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
        competition_groups=(("TEST",), ("OTHER",)),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="heuristic",
        require_objective_improvement=False,
        candidate_start_index=0,
        candidate_limit=1,
        candidate_cache_dir=cache_dir,
    )

    first_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=options,
    )
    second_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=options,
    )

    assert first_report.total_grid_candidate_count == 2
    assert first_report.candidate_count == 1
    assert first_report.candidate_start_index == 0
    assert first_report.candidate_limit == 1
    assert first_report.cache_hit_count == 0
    assert first_report.cache_miss_count == 1
    assert first_report.cache_write_count == 1
    assert first_report.candidates[0].candidate_index == 0
    assert first_report.candidates[0].candidate_cache_status == "miss"
    assert len(list(cache_dir.glob("*.json"))) == 1

    assert second_report.cache_hit_count == 1
    assert second_report.cache_miss_count == 0
    assert second_report.cache_write_count == 0
    assert second_report.candidates[0].candidate_key == first_report.candidates[0].candidate_key
    assert second_report.candidates[0].candidate_cache_status == "hit"


def test_quality_signal_profile_grid_reuses_baseline_cache(
    tmp_path: Path,
) -> None:
    baseline_cache_dir = tmp_path / "quality-signal-profile-baseline-cache"
    options = HistoricalFinalAnswerQualitySignalProfileGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1", "2x1"),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
        competition_groups=(("TEST",),),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="heuristic",
        require_objective_improvement=False,
        baseline_cache_dir=baseline_cache_dir,
    )

    first_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=options,
    )
    second_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=options,
    )

    assert first_report.baseline_cache_status == "miss"
    assert first_report.baseline_cache_written is True
    assert first_report.baseline_cache_key is not None
    assert first_report.summary_json["baseline_cache_status"] == "miss"
    assert first_report.summary_json["baseline_cache_written"] is True
    assert len(list(baseline_cache_dir.glob("baseline-*.json"))) == 1

    assert second_report.baseline_cache_status == "hit"
    assert second_report.baseline_cache_written is False
    assert second_report.baseline_cache_key == first_report.baseline_cache_key
    assert second_report.baseline_suite_key == first_report.baseline_suite_key
    assert second_report.summary_json["baseline_cache_status"] == "hit"


def test_quality_signal_profile_grid_writes_progress_jsonl(tmp_path: Path) -> None:
    progress_path = tmp_path / "quality-signal-profile-progress.jsonl"
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
            progress_jsonl_path=progress_path,
        ),
    )

    events = [
        loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
    ]

    assert [event["event"] for event in events] == [
        "grid_started",
        "baseline_completed",
        "candidate_started",
        "candidate_completed",
        "grid_completed",
    ]
    assert events[-1]["report_key"] == report.report_key
    assert events[-1]["candidate_count"] == 1
    assert report.progress_event_count == 5
    assert report.summary_json["progress_event_count"] == 5
    assert report.summary_json["progress_jsonl_path"] == str(progress_path)
    assert report.baseline_evaluation_elapsed_seconds >= 0.0
    assert report.candidate_evaluation_elapsed_seconds >= 0.0
    assert report.grid_evaluation_elapsed_seconds >= 0.0
    assert report.candidates[0].evaluation_elapsed_seconds is not None
    assert events[3]["candidate_key"] == report.candidates[0].candidate_key


def test_quality_signal_profile_grid_selects_explicit_candidate_indices() -> None:
    report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=HistoricalFinalAnswerQualitySignalProfileGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",), ("OTHER",), ("THIRD",)),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
            require_objective_improvement=False,
            candidate_indices=(1,),
        ),
    )

    assert report.total_grid_candidate_count == 3
    assert report.candidate_count == 1
    assert [candidate.candidate_index for candidate in report.candidates] == [1]
    assert report.summary_json["candidate_selection_mode"] == "explicit_indices"
    assert report.summary_json["requested_candidate_indices"] == [1]
    assert report.summary_json["unmatched_requested_candidate_indices"] == []
    assert report.summary_json["candidate_indices"] == [1]
    assert report.summary_json["missing_candidate_indices"] == [0, 2]
    assert report.summary_json["is_full_grid"] is False


def test_quality_signal_profile_grid_merges_batch_reports() -> None:
    base_options = HistoricalFinalAnswerQualitySignalProfileGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1", "2x1"),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
        competition_groups=(("TEST",), ("OTHER",)),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="heuristic",
        require_objective_improvement=False,
        candidate_limit=1,
    )
    first_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=base_options.model_copy(update={"candidate_start_index": 0}),
    )
    second_report = build_historical_final_answer_quality_signal_profile_grid_report(
        [_quality_signal_profile_slice()],
        options=base_options.model_copy(update={"candidate_start_index": 1}),
    )

    merged = merge_historical_final_answer_quality_signal_profile_grid_reports(
        [second_report, first_report],
        source_paths=(Path("batch-1.json"), Path("batch-0.json")),
    )

    assert merged.total_grid_candidate_count == 2
    assert merged.candidate_count == 2
    assert merged.candidate_limit == 2
    assert [candidate.candidate_index for candidate in merged.candidates] == [0, 1]
    assert merged.summary_json["missing_candidate_indices"] == []
    assert merged.summary_json["duplicate_candidate_indices"] == []
    assert merged.summary_json["is_full_grid"] is True
    assert merged.summary_json["source_report_paths"] == [
        "batch-1.json",
        "batch-0.json",
    ]


def test_quality_signal_profile_grid_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/quality-signal-profile-grid.json",
            "--pass-types",
            "2x1,4x1",
            "--modes",
            "single",
            "--strategy",
            "accuracy_first",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--min-probability",
            "0.2",
            "--min-data-quality-score",
            "70",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.4",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "6",
            "--derive-market-context-signals",
            "--final-answer-stake-efficiency-guard",
            "--final-answer-stake-efficiency-penalty-strength",
            "0.12",
            "--final-answer-stake-efficiency-max-stake-multiplier",
            "2.5",
            "--final-answer-stake-efficiency-min-roi",
            "0.03",
            "--final-answer-stake-efficiency-modes",
            "multiple",
            "--final-answer-stake-efficiency-scope",
            "quality_signal_affected",
            "--baseline-optimizer-profile",
            "heuristic",
            "--candidate-optimizer-profile",
            "solver",
            "--competition-group",
            "ESP_LA_LIGA,JPN_J1",
            "--competition-group",
            "GER_BUNDESLIGA",
            "--probability-min-values",
            "0.65,0.70",
            "--probability-max-values",
            "0.80,0.90",
            "--min-decimal-odds-values",
            "1.00,2.00",
            "--max-decimal-odds-values",
            "1.25,1.35",
            "--max-model-edge-values",
            "0.0,-0.02",
            "--score-min-values",
            "0.55,0.65",
            "--score-max-values",
            "0.65,0.80",
            "--strength-values",
            "0.02,0.04",
            "--fail-on-suite-statuses",
            "regressed,mixed,unchanged",
            "--min-affected-leg-count",
            "2",
            "--min-final-hit-count-delta",
            "1",
            "--min-final-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "1.5",
            "--max-final-hit-harm-count-vs-baseline",
            "2",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--max-brier-score-delta",
            "0.03",
            "--max-log-loss-delta",
            "0.04",
            "--max-mean-calibration-error-delta",
            "0.05",
            "--min-upset-capture-rate-delta",
            "0.06",
            "--min-candidate-roi",
            "0.09",
            "--watchlist-max-candidate-roi-shortfall",
            "0.02",
            "--watchlist-min-final-hit-count-delta",
            "2",
            "--watchlist-min-roi-delta",
            "0.03",
            "--watchlist-min-profit-loss-delta",
            "2.5",
            "--watchlist-max-final-hit-harm-count-vs-baseline",
            "1",
            "--watchlist-max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
            "--min-objective-roi-delta",
            "0.07",
            "--min-objective-upset-capture-rate-delta",
            "0.08",
            "--comparison-epsilon",
            "0.000000001",
            "--candidate-start-index",
            "3",
            "--candidate-limit",
            "8",
            "--candidate-indices",
            "1,3",
            "--candidate-cache-dir",
            "tmp/quality-signal-profile-grid-cache",
            "--no-candidate-cache-read",
            "--no-candidate-cache-write",
            "--baseline-cache-dir",
            "tmp/quality-signal-profile-baseline-cache",
            "--no-baseline-cache-read",
            "--no-baseline-cache-write",
            "--progress-jsonl-path",
            "tmp/quality-signal-profile-progress.jsonl",
            "--include-comparison-items",
            "--comparison-item-filter",
            "changed",
            "--comparison-item-limit",
            "12",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/quality-signal-profile-grid.json")
    assert options.backtest_options.pass_types == ("2x1", "4x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "accuracy_first"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_probability == 0.2
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.4
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 6
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.final_answer_stake_efficiency_guard is True
    assert (
        options.backtest_options.final_answer_stake_efficiency_penalty_strength
        == 0.12
    )
    assert (
        options.backtest_options.final_answer_stake_efficiency_max_stake_multiplier
        == 2.5
    )
    assert options.backtest_options.final_answer_stake_efficiency_min_roi == 0.03
    assert options.backtest_options.final_answer_stake_efficiency_modes == ("multiple",)
    assert (
        options.backtest_options.final_answer_stake_efficiency_scope
        == "quality_signal_affected"
    )
    assert options.baseline_optimizer_profile == "heuristic"
    assert options.candidate_optimizer_profile == "solver"
    assert options.competition_groups == (
        ("ESP_LA_LIGA", "JPN_J1"),
        ("GER_BUNDESLIGA",),
    )
    assert options.probability_min_values == (0.65, 0.70)
    assert options.probability_max_values == (0.80, 0.90)
    assert options.min_decimal_odds_values == (1.00, 2.00)
    assert options.max_decimal_odds_values == (1.25, 1.35)
    assert options.max_model_edge_values == (0.0, -0.02)
    assert options.score_min_values == (0.55, 0.65)
    assert options.score_max_values == (0.65, 0.80)
    assert options.strength_values == (0.02, 0.04)
    assert options.fail_on_suite_statuses == ("regressed", "mixed", "unchanged")
    assert options.min_affected_leg_count == 2
    assert options.min_final_hit_count_delta == 1
    assert options.min_final_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 1.5
    assert options.max_final_hit_harm_count_vs_baseline == 2
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.max_brier_score_delta == 0.03
    assert options.max_log_loss_delta == 0.04
    assert options.max_mean_calibration_error_delta == 0.05
    assert options.min_upset_capture_rate_delta == 0.06
    assert options.min_candidate_roi == 0.09
    assert options.watchlist_max_candidate_roi_shortfall == 0.02
    assert options.watchlist_min_final_hit_count_delta == 2
    assert options.watchlist_min_roi_delta == 0.03
    assert options.watchlist_min_profit_loss_delta == 2.5
    assert options.watchlist_max_final_hit_harm_count_vs_baseline == 1
    assert options.watchlist_max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False
    assert options.min_objective_roi_delta == 0.07
    assert options.min_objective_upset_capture_rate_delta == 0.08
    assert options.comparison_epsilon == 0.000000001
    assert options.candidate_start_index == 3
    assert options.candidate_limit == 8
    assert options.candidate_indices == (1, 3)
    assert options.candidate_cache_dir == Path("tmp/quality-signal-profile-grid-cache")
    assert options.read_candidate_cache is False
    assert options.write_candidate_cache is False
    assert options.baseline_cache_dir == Path("tmp/quality-signal-profile-baseline-cache")
    assert options.read_baseline_cache is False
    assert options.write_baseline_cache is False
    assert options.progress_jsonl_path == Path("tmp/quality-signal-profile-progress.jsonl")
    assert options.include_comparison_items is True
    assert options.comparison_item_filter == "changed"
    assert options.comparison_item_limit == 12


def test_quality_signal_profile_grid_cli_accepts_multiple_suite_manifests(
    tmp_path: Path,
) -> None:
    first_slice_path = tmp_path / "first_slice.json"
    second_slice_path = tmp_path / "second_slice.json"
    first_slice_path.write_text(
        _quality_signal_profile_slice(slice_id="first_suite_slice").model_dump_json(indent=2),
        encoding="utf-8",
    )
    second_slice_path.write_text(
        _quality_signal_profile_slice(slice_id="second_suite_slice").model_dump_json(indent=2),
        encoding="utf-8",
    )
    first_manifest_path = tmp_path / "first_manifest.json"
    second_manifest_path = tmp_path / "second_manifest.json"
    first_manifest_path.write_text(
        _manifest_json(suite_id="first_suite", slice_path=first_slice_path.name),
        encoding="utf-8",
    )
    second_manifest_path.write_text(
        _manifest_json(suite_id="second_suite", slice_path=second_slice_path.name),
        encoding="utf-8",
    )

    loaded = _historical_slices_from_args(
        _parse_args(
            [
                "--suite-manifest",
                str(first_manifest_path),
                "--suite-manifest",
                str(second_manifest_path),
            ]
        )
    )

    assert [historical_slice.metadata.slice_id for historical_slice in loaded.slices] == [
        "first_suite_slice",
        "second_suite_slice",
    ]
    assert loaded.manifest_result is None
    assert [bundle.manifest.suite_id for bundle in loaded.manifest_results] == [
        "first_suite",
        "second_suite",
    ]
    assert loaded.warnings == []


def test_quality_signal_profile_grid_merge_cli_args_map_to_paths() -> None:
    args = _parse_merge_args(
        [
            "tmp/batch-0.json",
            "tmp/batch-1.json",
            "--output-path",
            "tmp/merged.json",
        ]
    )

    assert args.report_paths == [Path("tmp/batch-0.json"), Path("tmp/batch-1.json")]
    assert args.output_path == Path("tmp/merged.json")


def _quality_signal_profile_slice(
    slice_id: str = "quality_signal_profile_grid_unit_slice",
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Quality signal profile grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "risky_a",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.74,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _fixture(
                "risky_b",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.73,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
        ],
    )


def _manifest_json(*, suite_id: str, slice_path: str) -> str:
    return (
        "{"
        f'"suite_id":"{suite_id}",'
        f'"name":"{suite_id}",'
        f'"slices":[{{"slice_path":"{slice_path}"}}]'
        "}"
    )


def _suite_result(
    *,
    suite_key: str,
    slice_id: str,
    actual_hit: bool,
    profit_loss: float,
    final_answer_fixture_ids: tuple[str, ...],
    candidate_summary: dict[str, object],
) -> HistoricalRecommendationBacktestSuiteResult:
    backtest_result = _backtest_result(
        backtest_key=f"{suite_key}:candidate",
        slice_id=slice_id,
        actual_hit=actual_hit,
        profit_loss=profit_loss,
        final_answer_fixture_ids=final_answer_fixture_ids,
    )
    comparison = HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"{suite_key}:comparison",
        slice_id=slice_id,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        status="unchanged",
        baseline=backtest_result,
        candidate=backtest_result,
        deltas_json={},
        summary_json={"final_answer_changed": False},
    )
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=suite_key,
        status="unchanged",
        slice_count=1,
        comparison_count=1,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=[comparison],
        aggregate_deltas_json={},
        warnings=[],
        summary_json=candidate_summary,
    )


def _backtest_result(
    *,
    backtest_key: str,
    slice_id: str,
    actual_hit: bool,
    profit_loss: float,
    final_answer_fixture_ids: tuple[str, ...],
) -> HistoricalRecommendationBacktestResult:
    total_stake = 2.0
    actual_return = total_stake + profit_loss
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key="2x1:single",
            pass_type="2x1",
            mode="single",
        ),
        status="completed",
        selected_fixture_ids=list(final_answer_fixture_ids),
        selected_outcomes={
            fixture_id: ["home_win"] for fixture_id in final_answer_fixture_ids
        },
        total_stake=total_stake,
        actual_return=max(actual_return, 0.0),
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        expected_hit_probability=0.70,
        actual_hit=actual_hit,
        calibration_error=0.30 if actual_hit else 0.70,
        brier_score=0.09 if actual_hit else 0.49,
        log_loss=0.20 if actual_hit else 1.20,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=backtest_key,
        slice_id=slice_id,
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixture_count=len(final_answer_fixture_ids),
        candidate_count=len(final_answer_fixture_ids),
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=final_answer,
        scenarios=[final_answer],
        final_hit_sample_size=1,
        final_hit_count=1 if actual_hit else 0,
        final_hit_rate=1.0 if actual_hit else 0.0,
        total_stake=total_stake,
        actual_return=max(actual_return, 0.0),
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        mean_calibration_error=0.30 if actual_hit else 0.70,
        brier_score=0.09 if actual_hit else 0.49,
        log_loss=0.20 if actual_hit else 1.20,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=None,
        warnings=[],
        summary_json={},
    )


def _fixture(
    fixture_id: str,
    *,
    actual_home_goals: int,
    actual_away_goals: int,
    probability: float,
    decimal_odds: float,
    model_edge: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-quality-signal-profile-grid-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=model_edge,
                data_quality_score=90.0,
                model_confidence_score=0.88,
                calibration_score=0.86,
                odds_stability_score=0.75,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
