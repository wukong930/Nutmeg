from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalCompetitionProfileEvidenceOptions,
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    build_historical_competition_profile_evidence_report,
)
from nutmeg.recommendations.competition_profile_evidence import (
    _options_from_args,
    _parse_args,
)


def test_competition_profile_evidence_accepts_roi_lift_without_hit_regression() -> None:
    historical_slice = _historical_slice(
        "accept_slice",
        competition_id="TEST_ACCEPT",
        actual_outcomes=["home_win", "home_win", "home_win"],
        home_win_odds=1.60,
    )

    report = build_historical_competition_profile_evidence_report(
        [historical_slice],
        options=HistoricalCompetitionProfileEvidenceOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1", "3x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=8.0,
                min_data_quality_score=80.0,
            ),
            baseline_scenario_keys_by_competition={"TEST_ACCEPT": "2x1:single"},
            min_sample_size=1,
        ),
    )

    decision = report.decisions[0]

    assert report.summary_json["accepted_count"] == 1
    assert decision.status == "candidate_accepted"
    assert decision.recommended_scenario_key == "3x1:single"
    assert decision.hit_count_delta == 0
    assert decision.roi_delta is not None and decision.roi_delta > 0
    assert decision.profit_loss_delta is not None and decision.profit_loss_delta > 0
    assert (
        decision.reason_codes
        == [
            "competition_profile_evidence:hit_count_preserved",
            "competition_profile_evidence:roi_improved",
            "competition_profile_evidence:profit_loss_improved",
        ]
    )


def test_competition_profile_evidence_rejects_top_roi_when_hit_count_drops() -> None:
    winning_slice = _historical_slice(
        "roi_win_slice",
        competition_id="TEST_RETAIN",
        actual_outcomes=["home_win", "home_win", "home_win"],
        home_win_odds=2.50,
    )
    losing_long_parlay_slice = _historical_slice(
        "roi_miss_slice",
        competition_id="TEST_RETAIN",
        actual_outcomes=["home_win", "home_win", "draw"],
        home_win_odds=2.50,
    )

    report = build_historical_competition_profile_evidence_report(
        [winning_slice, losing_long_parlay_slice],
        options=HistoricalCompetitionProfileEvidenceOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1", "3x1"),
                modes=("single",),
                unit_stake=2.0,
                max_budget=8.0,
                min_data_quality_score=80.0,
            ),
            baseline_scenario_keys_by_competition={"TEST_RETAIN": "2x1:single"},
            min_sample_size=1,
        ),
    )

    decision = report.decisions[0]

    assert decision.status == "baseline_retained"
    assert decision.recommended_scenario_key == "2x1:single"
    assert decision.rejected_top_roi_metric is not None
    assert decision.rejected_top_roi_metric.scenario_key == "3x1:single"
    assert decision.rejected_top_roi_metric.roi is not None
    assert decision.baseline_metric is not None
    assert decision.baseline_metric.roi is not None
    assert decision.rejected_top_roi_metric.roi > decision.baseline_metric.roi
    assert (
        "competition_profile_evidence:top_roi_candidate_reduced_hit_count"
        in decision.reason_codes
    )


def test_competition_profile_evidence_summary_counts_repeated_warnings() -> None:
    thin_slice = _historical_slice(
        "thin_slice",
        competition_id="TEST_WARNINGS",
        actual_outcomes=["home_win"],
        home_win_odds=1.80,
    )

    report = build_historical_competition_profile_evidence_report(
        [thin_slice],
        options=HistoricalCompetitionProfileEvidenceOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single", "multiple"),
                unit_stake=2.0,
                max_budget=8.0,
                min_data_quality_score=80.0,
            ),
            min_sample_size=1,
        ),
    )

    assert report.summary_json["warning_count"] == 3
    assert report.summary_json["warning_counts"] == {
        "historical_backtest_no_final_answer": 1,
        "scenario_failed:2x1:multiple:insufficient_distinct_fixture_candidates": 1,
        "scenario_failed:2x1:single:insufficient_distinct_fixture_candidates": 1,
    }


def test_competition_profile_evidence_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/profile-evidence.json",
            "--pass-types",
            "2x1,6x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.22",
            "--min-data-quality-score",
            "75",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.4",
            "--candidate-fixture-limit",
            "32",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "5",
            "--derive-market-context-signals",
            "--short-price-negative-edge-guardrail",
            "--short-price-negative-edge-max-decimal-odds",
            "1.42",
            "--short-price-negative-edge-min-probability",
            "0.72",
            "--short-price-negative-edge-max-model-edge",
            "-0.02",
            "--short-price-negative-edge-soft-penalty",
            "--short-price-negative-edge-soft-penalty-strength",
            "0.8",
            "--short-price-negative-edge-soft-penalty-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--baseline-scenario",
            "EPL=2x1:single",
            "--min-sample-size",
            "5",
            "--min-hit-count-delta",
            "1",
            "--min-roi-delta",
            "0.05",
            "--min-profit-loss-delta",
            "1.5",
            "--allow-partial-candidate-coverage",
            "--suggested-score-adjustment",
            "0.08",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/profile-evidence.json")
    assert options.backtest_options.pass_types == ("2x1", "6x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "value_first"
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 18
    assert options.backtest_options.min_probability == 0.22
    assert options.backtest_options.min_data_quality_score == 75
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.4
    assert options.backtest_options.candidate_fixture_limit == 32
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 5
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.short_price_negative_edge_guardrail is True
    assert options.backtest_options.short_price_negative_edge_max_decimal_odds == 1.42
    assert options.backtest_options.short_price_negative_edge_min_probability == 0.72
    assert options.backtest_options.short_price_negative_edge_max_model_edge == -0.02
    assert options.backtest_options.short_price_negative_edge_soft_penalty is True
    assert options.backtest_options.short_price_negative_edge_soft_penalty_strength == 0.8
    assert options.backtest_options.short_price_negative_edge_soft_penalty_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert options.baseline_scenario_keys_by_competition == {"EPL": "2x1:single"}
    assert options.min_sample_size == 5
    assert options.min_hit_count_delta == 1
    assert options.min_roi_delta == 0.05
    assert options.min_profit_loss_delta == 1.5
    assert options.require_full_candidate_coverage is False
    assert options.suggested_score_adjustment == 0.08


def _historical_slice(
    slice_id: str,
    *,
    competition_id: str,
    actual_outcomes: list[str],
    home_win_odds: float,
) -> HistoricalRecommendationSlice:
    as_of_time = datetime(2026, 1, 1, 8, tzinfo=UTC)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id=competition_id,
            season="2025-2026",
            result_source="deterministic_test_fixture",
            odds_source="deterministic_test_fixture",
            prediction_source="deterministic_test_fixture",
        ),
        as_of_time_utc=as_of_time,
        fixtures=[
            _fixture(
                index=index,
                competition_id=competition_id,
                prediction_time=as_of_time,
                actual_outcome=actual_outcome,
                home_win_odds=home_win_odds,
            )
            for index, actual_outcome in enumerate(actual_outcomes)
        ],
    )


def _fixture(
    *,
    index: int,
    competition_id: str,
    prediction_time: datetime,
    actual_outcome: str,
    home_win_odds: float,
) -> HistoricalFixture:
    actual_home_goals = 2 if actual_outcome == "home_win" else 1
    actual_away_goals = 0 if actual_outcome == "home_win" else 1
    kickoff_time = prediction_time + timedelta(days=index + 1)
    return HistoricalFixture(
        fixture_id=f"{competition_id.lower()}_{index}",
        competition_id=competition_id,
        kickoff_time_utc=kickoff_time,
        home_team_name=f"Home {index}",
        away_team_name=f"Away {index}",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=prediction_time,
        model_version="test-model-v1",
        feature_version="test-features-v1",
        calibration_version="test-calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.82 - index * 0.02,
                decimal_odds=home_win_odds,
                market_probability=1 / home_win_odds,
                model_edge=0.12,
                data_quality_score=95.0,
                model_confidence_score=0.90,
                calibration_score=0.90,
                odds_stability_score=0.90,
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.10,
                decimal_odds=3.80,
                market_probability=1 / 3.80,
                model_edge=-0.05,
                data_quality_score=95.0,
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.08,
                decimal_odds=5.00,
                market_probability=1 / 5.00,
                model_edge=-0.08,
                data_quality_score=95.0,
            ),
        ],
    )
