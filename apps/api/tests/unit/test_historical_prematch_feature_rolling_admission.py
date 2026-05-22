from __future__ import annotations

from json import loads
from typing import Literal

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridOptions,
    build_historical_prematch_feature_ablation_grid_report,
)
from nutmeg.recommendations import build_enriched_historical_feature_sample
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    HistoricalPrematchFeatureFinalAnswerGateOptions,
)
from nutmeg.recommendations.historical_prematch_feature_rolling_admission import (
    HistoricalPrematchFeatureRollingAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_prematch_feature_rolling_admission_report,
    main,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_prematch_feature_rolling_admission_accepts_stable_candidate() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = _grid_options()
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    report = build_historical_prematch_feature_rolling_admission_report(
        [historical_slice],
        grid_report=grid_report,
        options=_admission_options(grid_options=grid_options),
    )

    assert report.status == "accepted"
    assert report.candidate_feature_allowed is True
    assert report.shadow_allowed is True
    assert report.overall_fold.passed_final_answer_gate is True
    assert report.overall_fold.grid_report_key == grid_report.report_key
    assert report.overall_fold.passing_candidate_count >= 1
    assert report.failed_fold_count == 0
    assert report.active_competition_fold_count == 1
    assert report.active_season_cutoff_fold_count == 1
    assert report.active_rolling_fold_count == 1


def test_prematch_feature_rolling_admission_shadows_when_fold_coverage_is_thin() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = _grid_options()
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    report = build_historical_prematch_feature_rolling_admission_report(
        [historical_slice],
        grid_report=grid_report,
        options=_admission_options(
            grid_options=grid_options,
            min_active_competition_fold_count=2,
        ),
    )

    assert report.status == "shadow_only"
    assert report.candidate_feature_allowed is False
    assert report.shadow_allowed is True
    assert report.overall_fold.passed_final_answer_gate is True
    assert "active_competition_fold_count" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_prematch_feature_rolling_admission_shadows_when_sample_is_not_ready() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = _grid_options()
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    report = build_historical_prematch_feature_rolling_admission_report(
        [historical_slice],
        grid_report=grid_report,
        sample_readiness_report=_sample_readiness_report(
            status="shadow_only",
            sample_ready_allowed=False,
            shadow_allowed=True,
        ),
        options=_admission_options(
            grid_options=grid_options,
            require_sample_readiness=True,
        ),
    )

    assert report.status == "shadow_only"
    assert report.candidate_feature_allowed is False
    assert report.shadow_allowed is True
    assert report.sample_readiness_key == "historical_prematch_feature_sample_readiness:test"
    assert report.sample_readiness_status == "shadow_only"
    assert "prematch_feature_sample_readiness_accepted" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_prematch_feature_rolling_admission_rejects_when_overall_gate_fails() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = _grid_options()
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    report = build_historical_prematch_feature_rolling_admission_report(
        [historical_slice],
        grid_report=grid_report,
        options=_admission_options(
            grid_options=grid_options,
            quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                fail_on_suite_statuses=(),
                min_final_hit_sample_size=999,
                min_final_hit_rate_delta=None,
                max_brier_score_delta=None,
                max_log_loss_delta=None,
                max_mean_calibration_error_delta=None,
            ),
        ),
    )

    assert report.status == "rejected"
    assert report.candidate_feature_allowed is False
    assert report.shadow_allowed is False
    assert report.overall_fold.passed_final_answer_gate is False
    assert report.overall_fold.passing_candidate_count == 0
    assert "overall_final_answer_gate_passed" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_prematch_feature_rolling_admission_cli_writes_report(
    tmp_path,
    capsys,
) -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = _grid_options()
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )
    slice_path = tmp_path / "slice.json"
    grid_path = tmp_path / "grid.json"
    output_path = tmp_path / "rolling_admission.json"
    slice_path.write_text(
        f"{historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    grid_path.write_text(
        f"{grid_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(slice_path),
            "--grid-report-path",
            str(grid_path),
            "--output-path",
            str(output_path),
            "--top-candidate-limit",
            "2",
            "--pass-types",
            "1x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "solver",
            "--unit-stake",
            "2",
            "--max-budget",
            "4",
            "--min-final-hit-rate-delta",
            "-1.0",
            "--max-brier-score-delta",
            "1.0",
            "--max-log-loss-delta",
            "1.0",
            "--max-mean-calibration-error-delta",
            "1.0",
            "--rolling-window-season-count",
            "1",
        ]
    )

    printed = loads(capsys.readouterr().out)
    payload = loads(output_path.read_text(encoding="utf-8"))
    assert printed["report_key"] == payload["report_key"]
    assert payload["status"] == "accepted"
    assert payload["candidate_feature_allowed"] is True
    assert payload["source_grid_report_key"] == grid_report.report_key


def test_prematch_feature_rolling_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--grid-report-path",
            "tmp/grid.json",
            "--sample-readiness-report-path",
            "tmp/sample_readiness.json",
            "--output-path",
            "tmp/rolling.json",
            "--rolling-admission-id",
            "admission-test",
            "--gate-id",
            "gate-test",
            "--top-candidate-limit",
            "3",
            "--allow-grid-regression-candidates",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--unit-stake",
            "5",
            "--max-budget",
            "30",
            "--min-probability",
            "0.22",
            "--min-data-quality-score",
            "72",
            "--candidate-fixture-limit",
            "8",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "1",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "heuristic",
            "--min-slice-count",
            "2",
            "--min-comparison-count",
            "2",
            "--min-final-hit-sample-size",
            "2",
            "--min-final-hit-rate-delta",
            "-0.10",
            "--max-brier-score-delta",
            "0.05",
            "--max-log-loss-delta",
            "0.06",
            "--max-mean-calibration-error-delta",
            "0.07",
            "--max-warning-count",
            "4",
            "--min-overall-evaluated-candidate-count",
            "4",
            "--min-overall-passing-candidate-count",
            "3",
            "--min-fold-slice-count",
            "2",
            "--min-fold-fixture-count",
            "8",
            "--min-fold-evaluated-candidate-count",
            "2",
            "--min-fold-passing-candidate-count",
            "1",
            "--max-failed-fold-count",
            "1",
            "--min-active-competition-fold-count",
            "2",
            "--min-active-season-cutoff-fold-count",
            "3",
            "--min-active-rolling-fold-count",
            "4",
            "--rolling-window-season-count",
            "5",
            "--rolling-window-step",
            "2",
            "--max-report-folds",
            "40",
            "--require-sample-readiness",
            "--allow-sample-readiness-shadow-only",
        ]
    )

    options = _options_from_args(args)
    final_options = options.final_answer_gate_options

    assert options.admission_id == "admission-test"
    assert options.sample_readiness_report_path is not None
    assert str(options.sample_readiness_report_path).endswith("sample_readiness.json")
    assert options.require_sample_readiness is True
    assert options.require_sample_ready_allowed is False
    assert final_options.gate_id == "gate-test"
    assert final_options.top_candidate_limit == 3
    assert final_options.require_grid_non_regression_candidate is False
    assert final_options.backtest_options.pass_types == ("1x1", "2x1")
    assert final_options.backtest_options.modes == ("single",)
    assert final_options.backtest_options.strategy == "value_first"
    assert final_options.backtest_options.unit_stake == 5
    assert final_options.backtest_options.max_budget == 30
    assert final_options.backtest_options.min_probability == 0.22
    assert final_options.backtest_options.min_data_quality_score == 72
    assert final_options.backtest_options.candidate_fixture_limit == 8
    assert final_options.backtest_options.max_candidates_per_fixture == 2
    assert final_options.backtest_options.scenario_candidate_fixture_buffer == 1
    assert final_options.backtest_options.derive_market_context_signals is True
    assert final_options.backtest_options.optimizer_profile == "heuristic"
    assert final_options.quality_gate_options.min_slice_count == 2
    assert final_options.quality_gate_options.min_comparison_count == 2
    assert final_options.quality_gate_options.min_final_hit_sample_size == 2
    assert final_options.quality_gate_options.min_final_hit_rate_delta == -0.10
    assert final_options.quality_gate_options.max_brier_score_delta == 0.05
    assert final_options.quality_gate_options.max_log_loss_delta == 0.06
    assert final_options.quality_gate_options.max_mean_calibration_error_delta == 0.07
    assert final_options.quality_gate_options.max_warning_count == 4
    assert options.min_overall_evaluated_candidate_count == 4
    assert options.min_overall_passing_candidate_count == 3
    assert options.min_fold_slice_count == 2
    assert options.min_fold_fixture_count == 8
    assert options.min_fold_evaluated_candidate_count == 2
    assert options.min_fold_passing_candidate_count == 1
    assert options.max_failed_fold_count == 1
    assert options.min_active_competition_fold_count == 2
    assert options.min_active_season_cutoff_fold_count == 3
    assert options.min_active_rolling_fold_count == 4
    assert options.rolling_window_season_count == 5
    assert options.rolling_window_step == 2
    assert options.max_report_folds == 40


def _admission_options(
    *,
    grid_options: HistoricalPrematchFeatureAblationGridOptions,
    quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions | None = None,
    min_active_competition_fold_count: int = 1,
    require_sample_readiness: bool = False,
) -> HistoricalPrematchFeatureRollingAdmissionOptions:
    return HistoricalPrematchFeatureRollingAdmissionOptions(
        require_sample_readiness=require_sample_readiness,
        final_answer_gate_options=HistoricalPrematchFeatureFinalAnswerGateOptions(
            top_candidate_limit=2,
            grid_options=grid_options,
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=4.0,
                optimizer_profile="solver",
            ),
            quality_gate_options=quality_gate_options
            or HistoricalRecommendationSuiteQualityGateOptions(
                fail_on_suite_statuses=(),
                min_final_hit_rate_delta=-1.0,
                max_brier_score_delta=None,
                max_log_loss_delta=None,
                max_mean_calibration_error_delta=None,
            ),
        ),
        min_active_competition_fold_count=min_active_competition_fold_count,
        rolling_window_season_count=1,
    )


def _sample_readiness_report(
    *,
    status: Literal["accepted", "shadow_only", "rejected"] = "accepted",
    sample_ready_allowed: bool = True,
    shadow_allowed: bool = True,
) -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport(
        readiness_key="historical_prematch_feature_sample_readiness:test",
        status=status,
        sample_ready_allowed=sample_ready_allowed,
        shadow_allowed=shadow_allowed,
        readiness_id="sample-readiness-test",
        target_profile="market_movement",
        coverage_audit_key="historical_sample_coverage_audit:test",
        source_count=1,
        evaluated_source_count=1,
        accepted_source_count=1 if status == "accepted" else 0,
        shadow_only_source_count=1 if status == "shadow_only" else 0,
        rejected_source_count=1 if status == "rejected" else 0,
        ready_source_ids=["market_feature_suite"] if status == "accepted" else [],
        ready_fixture_count=600 if status == "accepted" else 0,
        ready_slice_count=25 if status == "accepted" else 0,
        ready_competition_count=3 if status == "accepted" else 0,
        ready_season_count=2 if status == "accepted" else 0,
        ready_competition_season_count=3 if status == "accepted" else 0,
        checks=[],
        sources=[],
        warnings=[],
        summary_json={"status": status},
    )


def _grid_options() -> HistoricalPrematchFeatureAblationGridOptions:
    return HistoricalPrematchFeatureAblationGridOptions(
        min_feature_data_quality_score=80.0,
        max_probability_shifts=(0.0, 0.08),
        odds_movement_weights=(0.0, 0.35),
        tracked_fragility_weights=(0.0, 1.0),
        lineup_strength_weights=(0.0,),
        draw_signal_weights=(0.0, 0.35),
        prediction_sample_limit=0,
    )
