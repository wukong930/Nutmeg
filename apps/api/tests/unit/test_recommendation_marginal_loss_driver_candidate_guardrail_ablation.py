from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.marginal_loss_driver_candidate_guardrail_ablation import (
    HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
    _historical_slices_from_args,
    _options_from_args,
    _parse_args,
    build_historical_marginal_loss_driver_candidate_guardrail_ablation_report,
)


def test_marginal_loss_driver_candidate_guardrail_ablation_counts_exclusions() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_ids=("TEST",),
            probability_min=0.65,
            probability_max=0.80,
            max_decimal_odds=1.50,
            max_model_edge=-0.02,
        ),
    )

    assert report.excluded_candidate_count == 2
    assert report.items[0].excluded_candidate_count == 2
    assert report.final_hit_harm_count_vs_baseline == 0
    assert report.profit_loss_harm_count_vs_baseline == 0
    assert report.decision == "rejected"
    assert "loss_driver_guardrail:objective_improvement_missing" in report.reason_codes


def test_marginal_loss_driver_candidate_guardrail_blocks_original_harm() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
        [_harm_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_ids=("TEST",),
            probability_min=0.65,
            probability_max=0.80,
            max_decimal_odds=1.50,
            max_model_edge=-0.02,
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
            require_objective_improvement=False,
        ),
    )

    assert report.excluded_candidate_count == 2
    assert report.final_hit_harm_count_vs_baseline == 1
    assert report.profit_loss_harm_count_vs_baseline == 1
    assert report.items[0].final_hit_harmed_vs_baseline is True
    assert report.items[0].profit_loss_harmed_vs_baseline is True
    assert report.decision == "rejected"
    assert (
        "loss_driver_guardrail:final_hit_harm_count_above_threshold"
        in report.reason_codes
    )
    assert (
        "loss_driver_guardrail:profit_loss_harm_count_above_threshold"
        in report.reason_codes
    )


def test_marginal_loss_driver_candidate_guardrail_ablation_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/loss-driver-candidate-guardrail.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--min-data-quality-score",
            "70",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "solver",
            "--competitions",
            "JPN_J1,ESP_LA_LIGA",
            "--probability-min",
            "0.60",
            "--probability-max",
            "0.82",
            "--max-decimal-odds",
            "1.55",
            "--max-model-edge",
            "-0.01",
            "--max-calibration-score",
            "0.85",
            "--max-model-confidence-score",
            "0.87",
            "--max-odds-stability-score",
            "0.74",
            "--min-excluded-candidate-count",
            "2",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.backtest_options.derive_market_context_signals is True
    assert options.optimizer_profile == "solver"
    assert options.competition_ids == ("JPN_J1", "ESP_LA_LIGA")
    assert options.probability_min == 0.60
    assert options.probability_max == 0.82
    assert options.max_decimal_odds == 1.55
    assert options.max_model_edge == -0.01
    assert options.max_calibration_score == 0.85
    assert options.max_model_confidence_score == 0.87
    assert options.max_odds_stability_score == 0.74
    assert options.min_excluded_candidate_count == 2
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def test_marginal_loss_driver_candidate_guardrail_loads_multiple_suite_manifests(
    tmp_path,
) -> None:
    slice_a = tmp_path / "slice_a.json"
    slice_b = tmp_path / "slice_b.json"
    manifest_a = tmp_path / "manifest_a.json"
    manifest_b = tmp_path / "manifest_b.json"
    slice_a.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    slice_b.write_text(
        f"{_harm_slice().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    manifest_a.write_text(
        """
{
  "suite_id": "unit-suite-a",
  "name": "Unit suite A",
  "slices": [{"slice_path": "slice_a.json"}]
}
""".lstrip(),
        encoding="utf-8",
    )
    manifest_b.write_text(
        """
{
  "suite_id": "unit-suite-b",
  "name": "Unit suite B",
  "slices": [{"slice_path": "slice_b.json"}]
}
""".lstrip(),
        encoding="utf-8",
    )
    args = _parse_args(
        [
            "--suite-manifest",
            str(manifest_a),
            "--suite-manifest",
            str(manifest_b),
        ]
    )

    loaded = _historical_slices_from_args(args)

    assert [result.manifest.suite_id for result in loaded.manifest_results] == [
        "unit-suite-a",
        "unit-suite-b",
    ]
    assert loaded.manifest_result is None
    assert [historical_slice.metadata.slice_id for historical_slice in loaded.slices] == [
        "loss_driver_candidate_guardrail_unit_slice",
        "loss_driver_candidate_guardrail_harm_slice",
    ]


def test_marginal_loss_driver_candidate_guardrail_ablation_quality_cap_is_opt_in() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_ids=("TEST",),
            probability_min=0.65,
            probability_max=0.80,
            max_decimal_odds=1.50,
            max_model_edge=-0.02,
            max_calibration_score=0.85,
        ),
    )

    assert report.excluded_candidate_count == 0
    assert "loss_driver_guardrail:excluded_candidate_count_too_low" in report.reason_codes


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_candidate_guardrail_unit_slice",
            name="Loss-driver candidate guardrail unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "bad_profile_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.79,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _fixture(
                "bad_profile_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.78,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
            _fixture(
                "good_value_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _fixture(
                "good_value_b",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.65,
                decimal_odds=1.86,
                model_edge=0.11,
            ),
        ],
    )


def _harm_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_candidate_guardrail_harm_slice",
            name="Loss-driver candidate guardrail harm slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "risky_winner_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.79,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _fixture(
                "risky_winner_b",
                actual_home_goals=1,
                actual_away_goals=0,
                probability=0.78,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
        ],
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
        model_version="poisson-v3.1-loss-driver-candidate-guardrail-test",
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
