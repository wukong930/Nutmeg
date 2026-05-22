from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    competition_data_quality_threshold_grid,
)
from nutmeg.recommendations.competition_data_quality_threshold_grid import (
    HistoricalCompetitionDataQualityThresholdGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_competition_data_quality_threshold_grid_report,
)


def test_competition_data_quality_threshold_grid_uses_competition_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[tuple[float, dict[str, float]]] = []

    def fake_backtest(
        historical_slice: HistoricalRecommendationSlice,
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
    ) -> HistoricalRecommendationBacktestResult:
        assert options is not None
        call_log.append(
            (
                options.min_data_quality_score,
                dict(options.min_data_quality_score_by_competition_id),
            )
        )
        if options.min_data_quality_score_by_competition_id.get("FRA_LIGUE_2") == 70:
            return _backtest_result(
                historical_slice.metadata.slice_id,
                final_hit_sample_size=2,
                final_hit_count=2,
                profit_loss=4.0,
            )
        return _backtest_result(
            historical_slice.metadata.slice_id,
            final_hit_sample_size=1,
            final_hit_count=1,
            profit_loss=2.0,
        )

    monkeypatch.setattr(
        competition_data_quality_threshold_grid,
        "run_historical_recommendation_backtest",
        fake_backtest,
    )

    report = build_historical_competition_data_quality_threshold_grid_report(
        [_slice()],
        options=HistoricalCompetitionDataQualityThresholdGridOptions(
            baseline_min_data_quality_score=80,
            competition_ids=("FRA_LIGUE_2",),
            candidate_min_data_quality_score_values=(80.0, 70.0),
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
        ),
    )

    assert call_log == [
        (80.0, {}),
        (80.0, {"FRA_LIGUE_2": 80.0}),
        (80.0, {"FRA_LIGUE_2": 70.0}),
    ]
    assert report.candidate_count == 2
    threshold_80 = report.candidates[0]
    threshold_70 = report.candidates[1]
    assert threshold_80.status == "rejected"
    assert threshold_80.newly_admitted_prediction_count == 0
    assert "competition_data_quality_threshold:newly_admitted_prediction_count_too_low" in (
        threshold_80.reason_codes
    )
    assert threshold_70.status == "accepted"
    assert threshold_70.newly_admitted_prediction_count == 1
    assert threshold_70.newly_admitted_fixture_count == 1
    assert threshold_70.final_hit_sample_size_delta == 1
    assert threshold_70.objective_improvement_metric_codes == [
        "final_hit_count_delta",
    ]


def test_competition_data_quality_threshold_grid_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json",
            "--output-path",
            "tmp/competition-data-quality-threshold-grid.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "solver",
            "--baseline-min-data-quality-score",
            "80",
            "--competitions",
            "FRA_LIGUE_2,ENG_CHAMPIONSHIP",
            "--candidate-min-data-quality-score-values",
            "75,70",
            "--min-newly-admitted-prediction-count",
            "2",
            "--min-final-hit-sample-size-delta",
            "1",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == Path("tmp/competition-data-quality-threshold-grid.json")
    assert args.suite_manifest == [
        Path("configs/recommendations/historical_suites/euro_2024_knockout_suite.json"),
        Path("configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json"),
    ]
    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "value_first"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.backtest_options.derive_market_context_signals is True
    assert options.optimizer_profile == "solver"
    assert options.baseline_min_data_quality_score == 80
    assert options.competition_ids == ("FRA_LIGUE_2", "ENG_CHAMPIONSHIP")
    assert options.candidate_min_data_quality_score_values == (75.0, 70.0)
    assert options.min_newly_admitted_prediction_count == 2
    assert options.min_final_hit_sample_size_delta == 1
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def _backtest_result(
    slice_id: str,
    *,
    final_hit_sample_size: int,
    final_hit_count: int,
    profit_loss: float,
) -> HistoricalRecommendationBacktestResult:
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"fake_{slice_id}_{final_hit_sample_size}_{final_hit_count}",
        slice_id=slice_id,
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixture_count=2,
        candidate_count=4,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=None,
        scenarios=[],
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        final_hit_rate=final_hit_count / final_hit_sample_size,
        total_stake=float(final_hit_sample_size * 2),
        actual_return=float(final_hit_sample_size * 2) + profit_loss,
        profit_loss=profit_loss,
        roi=profit_loss / float(final_hit_sample_size * 2),
        mean_calibration_error=0.20,
        brier_score=0.20,
        log_loss=0.50,
        upset_opportunity_count=1,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="competition_data_quality_threshold_grid_unit_slice",
            name="Competition data quality threshold grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture("fra_candidate", competition_id="FRA_LIGUE_2", data_quality_score=72),
            _fixture("epl_candidate", competition_id="EPL", data_quality_score=72),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    competition_id: str,
    data_quality_score: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=competition_id,
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=1,
        actual_away_goals=0,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-competition-quality-threshold-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.55,
                decimal_odds=2.10,
                market_probability=1.0 / 2.10,
                model_edge=-0.03,
                data_quality_score=data_quality_score,
                model_confidence_score=0.70,
                calibration_score=0.70,
                odds_stability_score=0.70,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
