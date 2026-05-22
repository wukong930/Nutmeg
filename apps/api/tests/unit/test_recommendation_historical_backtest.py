from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
    run_historical_recommendation_backtest_comparison,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.global_planner import RecommendationGlobalPlanOption
from nutmeg.recommendations.historical_backtest import (
    _candidates_from_fixtures,
    _final_answer_quality_signal_penalty_applies,
    _final_answer_quality_signal_penalty_score,
    _final_answer_segment_penalty_score,
    _final_answer_stake_efficiency_penalty_score,
    _parse_args,
    _rank_historical_final_answer_options,
    build_historical_competition_season_index_by_slice_id,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.policy import rank_candidates


def test_historical_backtest_loads_real_result_slice_and_reports_core_metrics() -> None:
    historical_slice = load_historical_recommendation_slice(
        Path("configs/recommendations/historical_slices/euro_2024_knockout_sample.json")
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1", "2x1"),
            modes=("single", "multiple"),
            unit_stake=2.0,
            max_budget=8.0,
        ),
    )

    assert result.slice_id == "euro_2024_knockout_sample_v1"
    assert result.fixture_count == 7
    assert result.candidate_count == 21
    assert result.scenario_count == 3
    assert result.completed_count == 3
    assert result.final_answer is not None
    assert result.final_hit_sample_size == 1
    assert result.summary_json["scenario_hit_sample_size"] == 3
    assert result.roi is not None
    assert result.mean_calibration_error is not None
    assert result.brier_score is not None
    assert result.upset_opportunity_count == 2
    assert result.summary_json["result_source"] == (
        "UEFA Euro 2024 public match records, manually curated"
    )


def test_historical_backtest_can_limit_candidate_fixture_pool() -> None:
    historical_slice = load_historical_recommendation_slice(
        Path("configs/recommendations/historical_slices/euro_2024_knockout_sample.json")
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            candidate_fixture_limit=2,
            max_candidates_per_fixture=1,
            scenario_candidate_fixture_buffer=0,
        ),
    )

    assert result.candidate_count == 2
    assert result.summary_json["eligible_candidate_count"] == 21
    assert result.summary_json["candidate_pool_count"] == 2
    assert result.summary_json["candidate_pool_fixture_count"] == 2
    assert result.summary_json["candidate_fixture_limit"] == 2
    assert result.summary_json["scenario_candidate_fixture_buffer"] == 0
    assert result.completed_count == 1


def test_historical_competition_season_index_groups_windows_by_season() -> None:
    index_by_slice_id = build_historical_competition_season_index_by_slice_id(
        [
            _slice_for_season_index(
                "ita_2021_window_2",
                competition_id="ITA_SERIE_B",
                season="2021_2022",
            ),
            _slice_for_season_index(
                "ita_2020_window_1",
                competition_id="ITA_SERIE_B",
                season="2020_2021",
            ),
            _slice_for_season_index(
                "ita_2021_window_1",
                competition_id="ITA_SERIE_B",
                season="2021_2022",
            ),
            _slice_for_season_index(
                "eng_2021_window_1",
                competition_id="ENG_CHAMPIONSHIP",
                season="2021_2022",
            ),
        ]
    )

    assert index_by_slice_id == {
        "ita_2020_window_1": 1,
        "ita_2021_window_1": 2,
        "ita_2021_window_2": 2,
        "eng_2021_window_1": 1,
    }


def test_historical_backtest_captures_upset_when_final_answer_selects_protection() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_upset",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Favorite FC",
                away_team_name="Draw Town",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.52,
                        decimal_odds=1.72,
                        market_probability=0.58,
                        upset_protection_score=0.74,
                        odds_stability_score=0.46,
                        volatility_penalty=0.18,
                        metadata_json={"favorite_fragility_score": 0.76},
                    ),
                    HistoricalMarketPrediction(
                        outcome="draw",
                        probability=0.34,
                        decimal_odds=3.45,
                        market_probability=0.29,
                        upset_protection_score=0.82,
                        odds_stability_score=0.48,
                        volatility_penalty=0.12,
                        metadata_json={"target_outcome": "draw", "upset_score": 0.82},
                    ),
                ],
            )
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            strategy="upset_protection",
            min_probability=0.10,
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.selected_outcomes == {"fixture_upset": ["draw"]}
    assert result.final_answer.actual_hit is True
    assert result.upset_opportunity_count == 1
    assert result.upset_capture_count == 1
    assert result.upset_capture_rate == 1.0


def test_historical_backtest_derives_market_context_fragility_from_fixture_prices() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_market_context_fragility_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _full_market_fixture(
                "fragile_favorite",
                home_team_name="Popular FC",
                away_team_name="Trap Town",
                actual_home_goals=1,
                actual_away_goals=1,
                probabilities={
                    "home_win": 0.65,
                    "draw": 0.24,
                    "away_win": 0.11,
                },
                odds={
                    "home_win": 1.45,
                    "draw": 4.60,
                    "away_win": 8.00,
                },
                odds_stability_score=0.86,
                volatility_penalty=0.02,
            ),
            _full_market_fixture(
                "steady_favorite",
                home_team_name="Steady FC",
                away_team_name="Baseline United",
                actual_home_goals=2,
                actual_away_goals=0,
                probabilities={
                    "home_win": 0.64,
                    "draw": 0.15,
                    "away_win": 0.21,
                },
                odds={
                    "home_win": 2.10,
                    "draw": 4.00,
                    "away_win": 4.00,
                },
                odds_stability_score=0.86,
                volatility_penalty=0.02,
            ),
        ],
    )

    baseline_ranked = rank_candidates(_candidates_from_fixtures(historical_slice.fixtures))
    context_ranked = rank_candidates(
        _candidates_from_fixtures(
            historical_slice.fixtures,
            derive_market_context_signals=True,
        )
    )

    assert baseline_ranked[0].candidate.fixture_id == "fragile_favorite"
    assert context_ranked[0].candidate.fixture_id == "steady_favorite"
    assert context_ranked[1].candidate.fixture_id == "fragile_favorite"
    assert context_ranked[1].component_scores["favorite_fragility"] > 0.25
    assert context_ranked[1].component_scores["upset_avoidance_penalty"] > 0.20
    assert (
        context_ranked[1].candidate.metadata_json["market_context_signal_basis"]
        == "historical_1x2_market_context_v3_1"
    )


def test_historical_backtest_short_price_negative_edge_guardrail_is_opt_in() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_short_price_negative_edge_guardrail_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "bad_short_favorite_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.86,
                decimal_odds=1.18,
                model_edge=-0.035,
            ),
            _comparison_fixture(
                "bad_short_favorite_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.85,
                decimal_odds=1.20,
                model_edge=-0.025,
            ),
            _comparison_fixture(
                "good_value_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _comparison_fixture(
                "good_value_b",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.65,
                decimal_odds=1.86,
                model_edge=0.11,
            ),
        ],
    )

    baseline = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    guarded = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            short_price_negative_edge_guardrail=True,
        ),
    )

    assert baseline.final_answer is not None
    assert set(baseline.final_answer.selected_fixture_ids) == {
        "bad_short_favorite_a",
        "bad_short_favorite_b",
    }
    assert baseline.final_answer.actual_hit is False
    assert (
        baseline.summary_json["short_price_negative_edge_guardrail_excluded_candidate_count"] == 0
    )
    assert guarded.final_answer is not None
    assert set(guarded.final_answer.selected_fixture_ids) == {
        "good_value_a",
        "good_value_b",
    }
    assert guarded.final_answer.actual_hit is True
    assert guarded.candidate_count == 2
    assert guarded.summary_json["short_price_negative_edge_guardrail_excluded_candidate_count"] == 2


def test_historical_backtest_marginal_loss_driver_candidate_guardrail_is_opt_in() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_marginal_loss_driver_candidate_guardrail_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "bad_profile_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.79,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _comparison_fixture(
                "bad_profile_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.78,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
            _comparison_fixture(
                "good_value_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _comparison_fixture(
                "good_value_b",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.65,
                decimal_odds=1.86,
                model_edge=0.11,
            ),
        ],
    )

    baseline = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    inactive_competition = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            marginal_loss_driver_candidate_guardrail=True,
            marginal_loss_driver_candidate_guardrail_competition_ids=("OTHER",),
        ),
    )
    guarded = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            marginal_loss_driver_candidate_guardrail=True,
            marginal_loss_driver_candidate_guardrail_competition_ids=("TEST",),
        ),
    )
    quality_capped = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            marginal_loss_driver_candidate_guardrail=True,
            marginal_loss_driver_candidate_guardrail_competition_ids=("TEST",),
            marginal_loss_driver_candidate_guardrail_max_calibration_score=0.85,
        ),
    )

    assert baseline.final_answer is not None
    assert baseline.candidate_count == 4
    assert (
        baseline.summary_json["marginal_loss_driver_candidate_guardrail_excluded_candidate_count"]
        == 0
    )
    assert (
        inactive_competition.summary_json[
            "marginal_loss_driver_candidate_guardrail_excluded_candidate_count"
        ]
        == 0
    )
    assert guarded.final_answer is not None
    assert set(guarded.final_answer.selected_fixture_ids) == {
        "good_value_a",
        "good_value_b",
    }
    assert guarded.final_answer.actual_hit is True
    assert guarded.candidate_count == 2
    assert (
        guarded.summary_json["marginal_loss_driver_candidate_guardrail_excluded_candidate_count"]
        == 2
    )
    assert quality_capped.candidate_count == 4
    assert (
        quality_capped.summary_json[
            "marginal_loss_driver_candidate_guardrail_excluded_candidate_count"
        ]
        == 0
    )


def test_historical_backtest_short_price_negative_edge_soft_penalty_keeps_candidates() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_short_price_negative_edge_soft_penalty"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "bad_short_favorite_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.86,
                decimal_odds=1.18,
                model_edge=-0.035,
            ),
            _comparison_fixture(
                "bad_short_favorite_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.85,
                decimal_odds=1.20,
                model_edge=-0.025,
            ),
            _comparison_fixture(
                "good_value_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _comparison_fixture(
                "good_value_b",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.65,
                decimal_odds=1.86,
                model_edge=0.11,
            ),
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            short_price_negative_edge_soft_penalty=True,
            short_price_negative_edge_soft_penalty_strength=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.candidate_count == 4
    assert set(result.final_answer.selected_fixture_ids) == {
        "good_value_a",
        "good_value_b",
    }
    assert result.final_answer.actual_hit is True
    assert result.summary_json["short_price_negative_edge_soft_penalty_candidate_count"] == 2
    assert result.summary_json["short_price_negative_edge_guardrail_excluded_candidate_count"] == 0


def test_historical_backtest_final_answer_quality_signal_penalty_is_opt_in() -> None:
    safe_option = _quality_signal_plan_option(
        "safe_1x1",
        candidates=[
            _quality_signal_candidate(
                "safe_fixture",
                probability=0.86,
                decimal_odds=1.20,
                model_edge=0.03,
            )
        ],
        planner_score=0.76,
        hit_probability=0.86,
        roi=0.08,
        risk_score=0.14,
        pass_type="1x1",
    )
    risky_option = _quality_signal_plan_option(
        "risky_2x1",
        candidates=[
            _quality_signal_candidate(
                "risky_fixture_a",
                probability=0.74,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _quality_signal_candidate(
                "risky_fixture_b",
                probability=0.73,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
        ],
        planner_score=0.98,
        hit_probability=0.68,
        roi=0.35,
        risk_score=0.32,
        pass_type="2x1",
    )

    disabled_options = HistoricalRecommendationBacktestOptions()
    enabled_options = HistoricalRecommendationBacktestOptions(
        final_answer_quality_signal_penalty=True,
        final_answer_quality_signal_penalty_strength=0.04,
        final_answer_quality_signal_competition_ids=("TEST",),
    )
    inactive_competition_options = enabled_options.model_copy(
        update={"final_answer_quality_signal_competition_ids": ("OTHER",)}
    )
    inactive_score_options = enabled_options.model_copy(
        update={"final_answer_quality_signal_score_max": 0.79}
    )
    inactive_odds_floor_options = enabled_options.model_copy(
        update={"final_answer_quality_signal_min_decimal_odds": 1.50}
    )

    assert (
        _rank_historical_final_answer_options(
            [safe_option, risky_option],
            backtest_options=disabled_options,
        )[0].option_key
        == "risky_2x1"
    )
    assert (
        _rank_historical_final_answer_options(
            [safe_option, risky_option],
            backtest_options=enabled_options,
        )[0].option_key
        == "safe_1x1"
    )
    assert (
        _final_answer_quality_signal_penalty_score(
            safe_option,
            backtest_options=enabled_options,
        )
        == 0.0
    )
    assert _final_answer_quality_signal_penalty_score(
        risky_option,
        backtest_options=enabled_options,
    ) == pytest.approx(0.04)
    assert (
        _final_answer_quality_signal_penalty_score(
            risky_option,
            backtest_options=inactive_competition_options,
        )
        == 0.0
    )
    assert (
        _final_answer_quality_signal_penalty_score(
            risky_option,
            backtest_options=inactive_score_options,
        )
        == 0.0
    )
    assert (
        _final_answer_quality_signal_penalty_score(
            risky_option,
            backtest_options=inactive_odds_floor_options,
        )
        == 0.0
    )
    assert _final_answer_quality_signal_penalty_applies(
        risky_option.selection.selected_candidates[0].candidate,
        backtest_options=enabled_options,
    )
    assert not _final_answer_quality_signal_penalty_applies(
        risky_option.selection.selected_candidates[0].candidate,
        backtest_options=inactive_competition_options,
    )
    assert not _final_answer_quality_signal_penalty_applies(
        safe_option.selection.selected_candidates[0].candidate,
        backtest_options=enabled_options,
    )
    assert not _final_answer_quality_signal_penalty_applies(
        risky_option.selection.selected_candidates[0].candidate,
        backtest_options=inactive_odds_floor_options,
    )


def test_historical_backtest_final_answer_segment_penalty_is_opt_in() -> None:
    safe_option = _quality_signal_plan_option(
        "safe_1x1",
        candidates=[
            _quality_signal_candidate(
                "safe_fixture",
                probability=0.82,
                decimal_odds=1.44,
                model_edge=0.05,
            )
        ],
        planner_score=0.76,
        hit_probability=0.82,
        roi=0.18,
        risk_score=0.18,
        pass_type="1x1",
    )
    risky_segment_option = _quality_signal_plan_option(
        "risky_3x1",
        candidates=[
            _quality_signal_candidate(
                "risky_segment_fixture_a",
                probability=0.96,
                decimal_odds=1.18,
                model_edge=-0.01,
            ),
            _quality_signal_candidate(
                "risky_segment_fixture_b",
                probability=0.95,
                decimal_odds=1.19,
                model_edge=-0.01,
            ),
            _quality_signal_candidate(
                "risky_segment_fixture_c",
                probability=0.94,
                decimal_odds=1.20,
                model_edge=-0.01,
            ),
        ],
        planner_score=0.99,
        hit_probability=0.86,
        roi=0.25,
        risk_score=0.14,
        pass_type="3x1",
    )
    disabled_options = HistoricalRecommendationBacktestOptions()
    enabled_options = HistoricalRecommendationBacktestOptions(
        final_answer_segment_penalty=True,
        final_answer_segment_penalty_strength=0.20,
        final_answer_segment_pass_types=("3x1",),
        final_answer_segment_modes=("single",),
        final_answer_segment_competition_ids=("TEST",),
        final_answer_segment_min_hit_probability=0.85,
        final_answer_segment_max_average_leg_decimal_odds=1.30,
    )
    inactive_pass_type_options = enabled_options.model_copy(
        update={"final_answer_segment_pass_types": ("2x1",)}
    )
    inactive_competition_options = enabled_options.model_copy(
        update={"final_answer_segment_competition_ids": ("OTHER",)}
    )
    active_season_options = enabled_options.model_copy(
        update={"final_answer_segment_season_ids": ("2023-2024",)}
    )
    inactive_season_options = enabled_options.model_copy(
        update={"final_answer_segment_season_ids": ("2022-2023",)}
    )
    active_competition_season_index_options = enabled_options.model_copy(
        update={"final_answer_segment_min_competition_season_index": 4}
    )
    inactive_competition_season_index_options = enabled_options.model_copy(
        update={"final_answer_segment_min_competition_season_index": 5}
    )

    assert (
        _rank_historical_final_answer_options(
            [safe_option, risky_segment_option],
            backtest_options=disabled_options,
        )[0].option_key
        == "risky_3x1"
    )
    assert (
        _rank_historical_final_answer_options(
            [safe_option, risky_segment_option],
            backtest_options=enabled_options,
        )[0].option_key
        == "safe_1x1"
    )
    assert _final_answer_segment_penalty_score(
        risky_segment_option,
        backtest_options=enabled_options,
    ) == pytest.approx(0.20)
    assert _final_answer_segment_penalty_score(
        risky_segment_option,
        backtest_options=active_season_options,
    ) == pytest.approx(0.20)
    assert _final_answer_segment_penalty_score(
        risky_segment_option,
        backtest_options=active_competition_season_index_options,
    ) == pytest.approx(0.20)
    assert (
        _final_answer_segment_penalty_score(
            risky_segment_option,
            backtest_options=inactive_pass_type_options,
        )
        == 0.0
    )
    assert (
        _final_answer_segment_penalty_score(
            risky_segment_option,
            backtest_options=inactive_competition_options,
        )
        == 0.0
    )
    assert (
        _final_answer_segment_penalty_score(
            risky_segment_option,
            backtest_options=inactive_season_options,
        )
        == 0.0
    )
    assert (
        _final_answer_segment_penalty_score(
            risky_segment_option,
            backtest_options=inactive_competition_season_index_options,
        )
        == 0.0
    )
    assert (
        _final_answer_segment_penalty_score(
            safe_option,
            backtest_options=enabled_options,
        )
        == 0.0
    )


def test_historical_backtest_final_answer_stake_efficiency_guard_is_opt_in() -> None:
    safe_option = _quality_signal_plan_option(
        "safe_1x1",
        candidates=[
            _quality_signal_candidate(
                "stake_safe_fixture",
                probability=0.82,
                decimal_odds=1.44,
                model_edge=0.05,
            )
        ],
        planner_score=0.76,
        hit_probability=0.82,
        roi=0.18,
        risk_score=0.18,
        pass_type="1x1",
    )
    costly_multiple_option = _quality_signal_plan_option(
        "costly_2x1_multiple",
        candidates=[
            _quality_signal_candidate(
                "stake_costly_fixture_a",
                probability=0.76,
                decimal_odds=1.42,
                model_edge=0.04,
            ),
            _quality_signal_candidate(
                "stake_costly_fixture_b",
                probability=0.75,
                decimal_odds=1.45,
                model_edge=0.04,
            ),
        ],
        planner_score=0.99,
        hit_probability=0.88,
        roi=0.36,
        risk_score=0.16,
        pass_type="2x1",
        mode="multiple",
        total_atomic_bets=4,
        total_stake=8.0,
        multiplier=4,
    )
    disabled_options = HistoricalRecommendationBacktestOptions()
    enabled_options = HistoricalRecommendationBacktestOptions(
        final_answer_stake_efficiency_guard=True,
        final_answer_stake_efficiency_penalty_strength=0.12,
        final_answer_stake_efficiency_max_stake_multiplier=2.0,
        final_answer_stake_efficiency_min_roi=0.0,
    )
    inactive_mode_options = enabled_options.model_copy(
        update={"final_answer_stake_efficiency_modes": ("single",)}
    )
    inactive_stake_options = enabled_options.model_copy(
        update={"final_answer_stake_efficiency_max_stake_multiplier": 4.0}
    )
    scoped_inactive_options = enabled_options.model_copy(
        update={"final_answer_stake_efficiency_scope": "quality_signal_affected"}
    )
    scoped_active_options = scoped_inactive_options.model_copy(
        update={
            "final_answer_quality_signal_penalty": True,
            "final_answer_quality_signal_probability_min": 0.50,
            "final_answer_quality_signal_probability_max": 0.58,
            "final_answer_quality_signal_min_decimal_odds": 1.75,
            "final_answer_quality_signal_max_decimal_odds": 2.20,
            "final_answer_quality_signal_max_model_edge": -0.03,
            "final_answer_quality_signal_competition_ids": ("TEST",),
        }
    )
    quality_signal_multiple_option = _quality_signal_plan_option(
        "quality_signal_costly_2x1_multiple",
        candidates=[
            _quality_signal_candidate(
                "stake_quality_signal_fixture_a",
                probability=0.55,
                decimal_odds=1.90,
                model_edge=-0.05,
            ),
            _quality_signal_candidate(
                "stake_quality_signal_fixture_b",
                probability=0.54,
                decimal_odds=1.91,
                model_edge=-0.05,
            ),
        ],
        planner_score=0.92,
        hit_probability=0.62,
        roi=0.10,
        risk_score=0.28,
        pass_type="2x1",
        mode="multiple",
        total_atomic_bets=4,
        total_stake=8.0,
        multiplier=4,
    )

    assert (
        _rank_historical_final_answer_options(
            [safe_option, costly_multiple_option],
            backtest_options=disabled_options,
        )[0].option_key
        == "costly_2x1_multiple"
    )
    assert (
        _rank_historical_final_answer_options(
            [safe_option, costly_multiple_option],
            backtest_options=enabled_options,
        )[0].option_key
        == "safe_1x1"
    )
    assert _final_answer_stake_efficiency_penalty_score(
        costly_multiple_option,
        backtest_options=enabled_options,
    ) == pytest.approx(0.12)
    assert (
        _final_answer_stake_efficiency_penalty_score(
            safe_option,
            backtest_options=enabled_options,
        )
        == 0.0
    )
    assert (
        _final_answer_stake_efficiency_penalty_score(
            costly_multiple_option,
            backtest_options=inactive_mode_options,
        )
        == 0.0
    )
    assert (
        _final_answer_stake_efficiency_penalty_score(
            costly_multiple_option,
            backtest_options=inactive_stake_options,
        )
        == 0.0
    )
    assert (
        _final_answer_stake_efficiency_penalty_score(
            costly_multiple_option,
            backtest_options=scoped_inactive_options,
        )
        == 0.0
    )
    assert _final_answer_stake_efficiency_penalty_score(
        quality_signal_multiple_option,
        backtest_options=scoped_active_options,
    ) == pytest.approx(0.12)


def test_historical_backtest_suite_aggregates_final_answer_quality_signal_counts() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _quality_signal_backtest_slice("quality_signal_slice_a"),
            _quality_signal_backtest_slice("quality_signal_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            final_answer_quality_signal_penalty=True,
        ),
    )

    assert suite.summary_json["final_answer_quality_signal_penalty"] is True
    assert suite.summary_json["candidate_final_answer_quality_signal_affected_leg_count"] == 4
    assert suite.summary_json["baseline_final_answer_quality_signal_affected_leg_count"] == 4


def test_historical_backtest_suite_aggregates_final_answer_segment_penalty_counts() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _quality_signal_backtest_slice("segment_penalty_slice_a"),
            _quality_signal_backtest_slice("segment_penalty_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            optimizer_profile="heuristic",
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            final_answer_segment_penalty=True,
            final_answer_segment_penalty_strength=0.03,
            final_answer_segment_pass_types=("2x1",),
            final_answer_segment_modes=("single",),
            final_answer_segment_competition_ids=("TEST",),
            final_answer_segment_min_hit_probability=0.50,
            final_answer_segment_max_average_leg_decimal_odds=1.35,
        ),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="heuristic",
    )

    assert suite.summary_json["final_answer_segment_penalty"] is True
    assert suite.summary_json["final_answer_segment_penalty_strength"] == 0.03
    assert suite.summary_json["final_answer_segment_pass_types"] == ["2x1"]
    assert suite.summary_json["candidate_final_answer_segment_penalty_option_count"] == 2
    assert suite.summary_json["baseline_final_answer_segment_penalty_option_count"] == 2


def test_historical_backtest_settles_losing_parlay_and_calibration() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_a",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.70,
                        decimal_odds=1.50,
                        market_probability=0.66,
                        data_quality_score=90,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id="fixture_b",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 20),
                home_team_name="Charlie",
                away_team_name="Delta",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.65,
                        decimal_odds=1.60,
                        market_probability=0.62,
                        data_quality_score=90,
                    )
                ],
            ),
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.completed_count == 1
    assert result.final_answer is not None
    assert result.final_answer.actual_hit is False
    assert result.actual_return == 0.0
    assert result.profit_loss == -2.0
    assert result.roi == -1.0
    assert result.final_answer.expected_hit_probability == pytest.approx(0.455)
    assert result.mean_calibration_error == pytest.approx(0.455)
    assert result.brier_score == pytest.approx(0.455**2)


def test_historical_backtest_settles_cn_and_european_handicap_candidates() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_handicap_settlement_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_cn",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="China Home",
                away_team_name="China Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-handicap-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="cn_handicap_1x2",
                        outcome="handicap_draw",
                        probability=0.54,
                        decimal_odds=3.0,
                        market_probability=1 / 3.0,
                        data_quality_score=92,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                        line=-1.0,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id="fixture_european",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 20),
                home_team_name="Euro Home",
                away_team_name="Euro Away",
                actual_home_goals=0,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-handicap-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="european_handicap_1x2",
                        outcome="handicap_draw",
                        probability=0.51,
                        decimal_odds=3.1,
                        market_probability=1 / 3.1,
                        data_quality_score=92,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                        line=1.0,
                    )
                ],
            ),
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            allowed_markets=("cn_handicap_1x2", "european_handicap_1x2"),
            min_probability=0.10,
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.completed_count == 1
    assert result.final_answer is not None
    assert result.final_answer.actual_hit is True
    assert result.actual_return == pytest.approx(18.6)
    assert result.profit_loss == pytest.approx(16.6)
    assert result.final_answer.selected_outcomes == {
        "fixture_cn": ["handicap_draw"],
        "fixture_european": ["handicap_draw"],
    }


def test_historical_backtest_reports_dynamic_mixed_final_answer_markets() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_dynamic_mixed_final_answer_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_1x2",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Plain Home",
                away_team_name="Plain Away",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-dynamic-mixed-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.64,
                        decimal_odds=1.80,
                        market_probability=1 / 1.80,
                        data_quality_score=92,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id="fixture_cn_handicap",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 20),
                home_team_name="Handicap Home",
                away_team_name="Handicap Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-dynamic-mixed-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="cn_handicap_1x2",
                        outcome="handicap_draw",
                        probability=0.56,
                        decimal_odds=2.75,
                        market_probability=1 / 2.75,
                        data_quality_score=91,
                        model_confidence_score=0.87,
                        calibration_score=0.85,
                        line=-1.0,
                    )
                ],
            ),
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            min_probability=0.10,
            allowed_markets=("1x2", "cn_handicap_1x2"),
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.actual_hit is True
    assert result.summary_json["final_answer_market_types"] == [
        "1x2",
        "cn_handicap_1x2",
    ]
    assert result.summary_json["final_answer_market_count"] == 2
    assert result.summary_json["final_answer_dynamic_mixed_market"] is True
    assert result.summary_json["final_answer_has_handicap_market"] is True
    assert result.summary_json["final_answer_has_correct_score_market"] is False
    assert result.summary_json["final_answer_selected_candidate_count"] == 2
    assert result.summary_json["final_answer_multiple_choice_fixture_count"] == 0
    arbitration = result.summary_json["final_answer_arbitration"]
    assert isinstance(arbitration, dict)
    assert arbitration["dynamic_mixed_market_answer"] is True
    assert arbitration["market_types"] == ["1x2", "cn_handicap_1x2"]


def test_historical_backtest_correct_score_lane_can_seed_bounded_final_answer() -> None:
    result = run_historical_recommendation_backtest(
        _correct_score_lane_slice("unit_test_correct_score_lane_admitted"),
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            min_probability=0.50,
            allowed_markets=("1x2", "correct_score"),
            correct_score_final_answer_lane=True,
            correct_score_final_answer_lane_pass_types=("2x1",),
            correct_score_final_answer_lane_min_correct_score_probability=0.20,
            correct_score_final_answer_lane_score_boost=1.0,
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "correct_score_lane:2x1:single"
    assert result.final_answer.selected_outcomes == {
        "fixture_score": ["2-1"],
        "fixture_anchor": ["home_win"],
    }
    assert result.final_answer.actual_hit is True
    assert result.summary_json["completed_correct_score_final_answer_lane_count"] == 1
    assert result.summary_json["final_answer_correct_score_final_answer_lane"] is True
    assert result.summary_json["final_answer_has_correct_score_market"] is True
    assert (
        result.summary_json[
            "final_answer_correct_score_final_answer_lane_selected_candidate_count"
        ]
        == 1
    )


def test_historical_backtest_correct_score_lane_guard_blocks_harmful_seed() -> None:
    result = run_historical_recommendation_backtest(
        _correct_score_lane_slice("unit_test_correct_score_lane_guarded"),
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            min_probability=0.50,
            allowed_markets=("1x2", "correct_score"),
            correct_score_final_answer_lane=True,
            correct_score_final_answer_lane_pass_types=("2x1",),
            correct_score_final_answer_lane_min_correct_score_probability=0.20,
            correct_score_final_answer_lane_score_boost=1.0,
            correct_score_final_answer_lane_max_hit_probability_deficit=0.0,
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "2x1:single"
    assert result.final_answer.selected_outcomes == {
        "fixture_score": ["home_win"],
        "fixture_anchor": ["home_win"],
    }
    assert result.summary_json["completed_correct_score_final_answer_lane_count"] == 1
    assert (
        result.summary_json[
            "correct_score_final_answer_lane_quality_guard_blocked_option_count"
        ]
        == 1
    )
    assert result.summary_json["final_answer_correct_score_final_answer_lane"] is False
    assert result.summary_json["final_answer_has_correct_score_market"] is False


def test_historical_backtest_cli_accepts_correct_score_lane_args(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "nutmeg-recommendation-historical-backtest",
            "tmp/slice.json",
            "--correct-score-final-answer-lane",
            "--correct-score-final-answer-lane-pass-types",
            "2x1,8x1",
            "--correct-score-final-answer-lane-mode",
            "single",
            "--correct-score-final-answer-lane-modes",
            "single,multiple",
            "--correct-score-final-answer-lane-candidate-limit",
            "48",
            "--correct-score-final-answer-lane-min-probability",
            "0.02",
            "--correct-score-final-answer-lane-min-correct-score-probability",
            "0.08",
            "--correct-score-final-answer-lane-max-correct-score-per-selection",
            "2",
            "--correct-score-final-answer-lane-score-boost",
            "0.2",
            "--correct-score-final-answer-lane-max-hit-probability-deficit",
            "0.15",
            "--correct-score-final-answer-lane-min-roi-delta",
            "-0.03",
            "--correct-score-final-answer-lane-outcomes",
            "1-0,2-1",
        ],
    )

    args = _parse_args()

    assert args.correct_score_final_answer_lane is True
    assert args.correct_score_final_answer_lane_pass_types == "2x1,8x1"
    assert args.correct_score_final_answer_lane_mode == "single"
    assert args.correct_score_final_answer_lane_modes == "single,multiple"
    assert args.correct_score_final_answer_lane_candidate_limit == 48
    assert args.correct_score_final_answer_lane_min_probability == 0.02
    assert args.correct_score_final_answer_lane_min_correct_score_probability == 0.08
    assert args.correct_score_final_answer_lane_max_correct_score_per_selection == 2
    assert args.correct_score_final_answer_lane_score_boost == 0.2
    assert args.correct_score_final_answer_lane_max_hit_probability_deficit == 0.15
    assert args.correct_score_final_answer_lane_min_roi_delta == -0.03
    assert args.correct_score_final_answer_lane_outcomes == "1-0,2-1"


def test_historical_backtest_beta_lane_probability_repair_lifts_market_floor() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_beta_lane_probability_repair"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="beta_fixture",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Beta Home",
                away_team_name="Beta Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-beta-repair-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.50,
                        decimal_odds=1.66,
                        market_probability=0.60,
                        model_edge=-0.10,
                        data_quality_score=72,
                        model_confidence_score=0.72,
                        calibration_score=0.74,
                        odds_stability_score=0.96,
                        volatility_penalty=0.02,
                    )
                ],
            )
        ],
    )

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            min_probability=0.10,
            min_data_quality_score=80,
            min_data_quality_score_by_competition_id={"TEST": 70},
            data_quality_beta_lane_enabled=True,
            data_quality_beta_lane_competition_ids=("TEST",),
            data_quality_beta_lane_min_probability=0.45,
            data_quality_beta_lane_max_decimal_odds=2.30,
            data_quality_beta_lane_min_model_edge=-0.12,
            data_quality_beta_lane_min_model_confidence_score=0.70,
            data_quality_beta_lane_min_calibration_score=0.70,
            data_quality_beta_lane_min_odds_stability_score=0.90,
            data_quality_beta_lane_max_volatility_penalty=0.05,
            data_quality_beta_lane_probability_repair_enabled=True,
            data_quality_beta_lane_probability_repair_strength=0.0,
            data_quality_beta_lane_probability_repair_max_delta=0.04,
            data_quality_beta_lane_probability_repair_min_market_probability_delta=0.01,
            data_quality_beta_lane_probability_repair_extra_uplift=0.04,
            unit_stake=2.0,
            max_budget=2.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.expected_hit_probability == pytest.approx(0.54)
    assert result.mean_calibration_error == pytest.approx(0.46)
    assert result.summary_json["data_quality_beta_lane_probability_repair_candidate_count"] == 1
    assert (
        result.summary_json[
            "data_quality_beta_lane_probability_repair_final_answer_selected_candidate_count"
        ]
        == 1
    )


def test_historical_backtest_beta_lane_probability_repair_honors_season_regime() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(
            slice_id="unit_test_beta_lane_probability_repair_season_regime",
        ).model_copy(update={"season": "2022_2023"}),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="beta_fixture",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Beta Home",
                away_team_name="Beta Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-beta-repair-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.50,
                        decimal_odds=1.66,
                        market_probability=0.60,
                        model_edge=-0.10,
                        data_quality_score=72,
                        model_confidence_score=0.72,
                        calibration_score=0.74,
                        odds_stability_score=0.96,
                        volatility_penalty=0.02,
                    )
                ],
            )
        ],
    )
    base_options = HistoricalRecommendationBacktestOptions(
        pass_types=("1x1",),
        modes=("single",),
        min_probability=0.10,
        min_data_quality_score=80,
        min_data_quality_score_by_competition_id={"TEST": 70},
        competition_season_index_by_slice_id={
            "unit_test_beta_lane_probability_repair_season_regime": 2,
        },
        data_quality_beta_lane_enabled=True,
        data_quality_beta_lane_competition_ids=("TEST",),
        data_quality_beta_lane_min_competition_season_index=2,
        data_quality_beta_lane_max_competition_season_index=2,
        data_quality_beta_lane_min_probability=0.45,
        data_quality_beta_lane_max_decimal_odds=2.30,
        data_quality_beta_lane_min_model_edge=-0.12,
        data_quality_beta_lane_min_model_confidence_score=0.70,
        data_quality_beta_lane_min_calibration_score=0.70,
        data_quality_beta_lane_min_odds_stability_score=0.90,
        data_quality_beta_lane_max_volatility_penalty=0.05,
        data_quality_beta_lane_probability_repair_enabled=True,
        data_quality_beta_lane_probability_repair_strength=0.0,
        data_quality_beta_lane_probability_repair_max_delta=0.04,
        data_quality_beta_lane_probability_repair_min_market_probability_delta=0.01,
        data_quality_beta_lane_probability_repair_extra_uplift=0.04,
        unit_stake=2.0,
        max_budget=2.0,
    )

    matched = run_historical_recommendation_backtest(
        historical_slice,
        options=base_options.model_copy(
            update={"data_quality_beta_lane_season_ids": ("2022_2023",)}
        ),
    )
    mismatched = run_historical_recommendation_backtest(
        historical_slice,
        options=base_options.model_copy(
            update={"data_quality_beta_lane_season_ids": ("2021_2022",)}
        ),
    )

    assert matched.final_answer is not None
    assert matched.final_answer.expected_hit_probability == pytest.approx(0.54)
    assert (
        matched.summary_json["data_quality_beta_lane_probability_repair_candidate_count"]
        == 1
    )
    assert mismatched.final_answer is None
    assert (
        mismatched.summary_json[
            "data_quality_beta_lane_probability_repair_candidate_count"
        ]
        == 0
    )


def test_historical_backtest_comparison_reports_solver_delta_against_heuristic() -> None:
    historical_slice = _solver_improvement_slice()

    comparison = run_historical_recommendation_backtest_comparison(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    assert comparison.status == "improved"
    assert comparison.baseline.final_answer is not None
    assert comparison.candidate.final_answer is not None
    assert comparison.baseline.final_answer.selected_fixture_ids == [
        "fixture_a",
        "fixture_b",
    ]
    assert comparison.candidate.final_answer.selected_fixture_ids == [
        "fixture_c",
        "fixture_d",
    ]
    assert comparison.baseline.final_hit_count == 0
    assert comparison.candidate.final_hit_count == 1
    assert comparison.deltas_json["final_hit_rate_delta"] == 1.0
    assert comparison.deltas_json["profit_loss_delta"] > 0
    assert comparison.deltas_json["brier_score_delta"] < 0
    assert comparison.deltas_json["candidate_solver_selected_scenario_count"] == 1
    assert comparison.summary_json["final_answer_changed"] is True


def test_historical_backtest_group_upset_stress_slice_rejects_uncalibrated_override() -> None:
    historical_slice = load_historical_recommendation_slice(
        Path("configs/recommendations/historical_slices/euro_2024_group_upset_sample.json")
    )

    comparison = run_historical_recommendation_backtest_comparison(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert comparison.status == "unchanged"
    assert comparison.summary_json["final_answer_changed"] is False
    assert comparison.baseline.final_answer is not None
    assert comparison.candidate.final_answer is not None
    assert comparison.baseline.final_answer.selected_fixture_ids == [
        "euro2024_group_por_cze",
        "euro2024_group_tur_geo",
    ]
    assert comparison.candidate.final_answer.selected_fixture_ids == [
        "euro2024_group_por_cze",
        "euro2024_group_tur_geo",
    ]
    assert comparison.candidate.final_answer.selection_diagnostics_json["solver_selected"] is False
    assert comparison.deltas_json["candidate_solver_selected_scenario_count"] == 0
    assert comparison.deltas_json["upset_capture_count_delta"] == 0
    assert comparison.deltas_json["profit_loss_delta"] == 0.0
    assert comparison.deltas_json["brier_score_delta"] == 0.0
    assert comparison.deltas_json["log_loss_delta"] == 0.0


def test_historical_backtest_keeps_upset_exposure_diagnostic_only() -> None:
    historical_slice = _calibrated_upset_exposure_slice()

    comparison = run_historical_recommendation_backtest_comparison(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    assert comparison.status == "unchanged"
    assert comparison.baseline.final_answer is not None
    assert comparison.candidate.final_answer is not None
    assert comparison.baseline.final_answer.selected_fixture_ids == [
        "fixture_safe_a",
        "fixture_safe_b",
    ]
    assert comparison.candidate.final_answer.selected_fixture_ids == [
        "fixture_safe_a",
        "fixture_safe_b",
    ]
    assert comparison.candidate.final_answer.selection_diagnostics_json["solver_selected"] is False
    assert comparison.deltas_json["candidate_solver_selected_scenario_count"] == 0
    assert comparison.deltas_json["final_hit_rate_delta"] == 0.0
    assert comparison.deltas_json["upset_capture_count_delta"] == 0
    assert comparison.deltas_json["profit_loss_delta"] == 0.0
    assert comparison.deltas_json["brier_score_delta"] == 0.0


def test_historical_backtest_suite_aggregates_solver_quality_across_slices() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _solver_improvement_slice(slice_id="solver_improvement_slice_a"),
            _solver_improvement_slice(slice_id="solver_improvement_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    assert suite.status == "improved"
    assert suite.slice_count == 2
    assert suite.comparison_count == 2
    assert suite.summary_json["baseline_final_hit_count"] == 0
    assert suite.summary_json["candidate_final_hit_count"] == 2
    assert suite.summary_json["candidate_solver_selected_scenario_count"] == 2
    assert suite.summary_json["final_answer_changed_count"] == 2
    assert suite.aggregate_deltas_json["final_hit_rate_delta"] == 1.0
    assert suite.aggregate_deltas_json["profit_loss_delta"] > 0
    assert suite.aggregate_deltas_json["brier_score_delta"] < 0
    assert suite.warnings == []


def test_historical_backtest_upset_exposure_reserve_is_opt_in() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            scenario_candidate_fixture_buffer=0,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
        ),
    )

    assert result.final_answer is None
    assert result.candidate_count == 1
    assert result.summary_json["candidate_pool_fixture_count"] == 1
    assert result.summary_json["upset_exposure_reserve"] is False
    assert result.summary_json["candidate_pool_upset_exposure_reserve_candidate_count"] == 0
    assert result.summary_json["upset_final_answer_lane"] is False
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 0
    assert result.summary_json["final_answer_upset_final_answer_lane_selected_candidate_count"] == 0


def test_historical_backtest_upset_exposure_reserve_adds_fixture() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            scenario_candidate_fixture_buffer=0,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_exposure_reserve=True,
            upset_exposure_reserve_fixture_count=1,
            upset_exposure_reserve_min_protection_score=0.45,
            upset_exposure_reserve_min_probability=0.15,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.actual_hit is True
    assert result.final_answer.selected_outcomes == {
        "safe_home": ["home_win"],
        "reserve_draw": ["draw"],
    }
    assert result.upset_capture_count == 1
    assert result.summary_json["candidate_pool_fixture_count"] == 2
    assert result.summary_json["candidate_pool_upset_exposure_reserve_fixture_count"] == 1
    assert result.summary_json["final_answer_upset_exposure_reserve_selected_candidate_count"] == 1
    assert result.summary_json["final_answer_upset_exposure_reserve_selected_fixture_ids"] == [
        "reserve_draw"
    ]


def test_historical_backtest_upset_final_answer_lane_can_win_arbitration() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            scenario_candidate_fixture_buffer=0,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_candidate_limit=4,
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_decimal_odds=3.5,
            upset_final_answer_lane_max_decimal_odds=5.0,
            upset_final_answer_lane_min_model_edge=-0.05,
            upset_final_answer_lane_max_model_edge=0.0,
            upset_final_answer_lane_competition_ids=("TEST",),
            upset_final_answer_lane_excluded_competition_ids=("OTHER",),
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "upset_lane:1x1:single"
    assert result.final_answer.selected_outcomes == {"reserve_draw": ["draw"]}
    assert result.final_answer.actual_hit is True
    assert result.upset_capture_count == 1
    assert result.scenario_count == 2
    assert result.completed_count == 2
    assert result.summary_json["upset_final_answer_lane"] is True
    assert result.summary_json["upset_final_answer_lane_min_decimal_odds"] == 3.5
    assert result.summary_json["upset_final_answer_lane_max_model_edge"] == 0.0
    assert result.summary_json["upset_final_answer_lane_competition_ids"] == ["TEST"]
    assert result.summary_json["upset_final_answer_lane_excluded_competition_ids"] == ["OTHER"]
    assert result.summary_json["upset_final_answer_lane_max_hit_probability_deficit"] is None
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 1
    assert result.summary_json["candidate_pool_upset_final_answer_lane_candidate_count"] == 0
    assert result.summary_json["completed_upset_final_answer_lane_count"] == 1
    assert result.summary_json["final_answer_upset_final_answer_lane"] is True
    assert result.summary_json["final_answer_upset_final_answer_lane_selected_candidate_count"] == 1
    assert result.summary_json["final_answer_upset_final_answer_lane_selected_fixture_ids"] == [
        "reserve_draw"
    ]


def test_historical_backtest_upset_lane_calibration_guard_blocks_large_deficit() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            scenario_candidate_fixture_buffer=0,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_candidate_limit=4,
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_decimal_odds=3.5,
            upset_final_answer_lane_max_decimal_odds=5.0,
            upset_final_answer_lane_min_model_edge=-0.05,
            upset_final_answer_lane_max_model_edge=0.0,
            upset_final_answer_lane_competition_ids=("TEST",),
            upset_final_answer_lane_max_hit_probability_deficit=0.10,
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "1x1:single"
    assert result.final_answer.selected_outcomes == {"safe_home": ["home_win"]}
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 1
    assert result.summary_json["completed_upset_final_answer_lane_count"] == 1
    assert (
        result.summary_json["upset_final_answer_lane_calibration_guard_blocked_option_count"] == 1
    )
    assert result.summary_json["final_answer_upset_final_answer_lane"] is False
    assert (
        result.summary_json["final_answer_upset_final_answer_lane_hit_probability_deficit"] is None
    )


def test_historical_backtest_upset_lane_calibration_guard_allows_tolerated_deficit() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            scenario_candidate_fixture_buffer=0,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_candidate_limit=4,
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_decimal_odds=3.5,
            upset_final_answer_lane_max_decimal_odds=5.0,
            upset_final_answer_lane_min_model_edge=-0.05,
            upset_final_answer_lane_max_model_edge=0.0,
            upset_final_answer_lane_competition_ids=("TEST",),
            upset_final_answer_lane_max_hit_probability_deficit=0.70,
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "upset_lane:1x1:single"
    assert result.final_answer.selected_outcomes == {"reserve_draw": ["draw"]}
    assert (
        result.summary_json["upset_final_answer_lane_calibration_guard_blocked_option_count"] == 0
    )
    assert result.summary_json["final_answer_upset_final_answer_lane"] is True
    assert (
        result.summary_json["final_answer_upset_final_answer_lane_hit_probability_deficit"] == 0.64
    )


def test_historical_backtest_upset_final_answer_lane_competition_guard_is_enforced() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_decimal_odds=3.5,
            upset_final_answer_lane_max_decimal_odds=5.0,
            upset_final_answer_lane_min_model_edge=-0.05,
            upset_final_answer_lane_max_model_edge=0.0,
            upset_final_answer_lane_competition_ids=("OTHER",),
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "1x1:single"
    assert result.final_answer.selected_outcomes == {"safe_home": ["home_win"]}
    assert result.failed_count == 1
    assert result.warnings == [
        "scenario_failed:upset_lane:1x1:single:upset_final_answer_lane_no_candidates"
    ]
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 0
    assert result.summary_json["final_answer_upset_final_answer_lane_selected_candidate_count"] == 0


def test_historical_backtest_upset_final_answer_lane_quality_filter_is_enforced() -> None:
    historical_slice = _upset_reserve_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_model_edge=0.0,
            upset_final_answer_lane_min_calibration_score=0.92,
            upset_final_answer_lane_min_model_confidence_score=0.90,
            upset_final_answer_lane_min_odds_stability_score=0.70,
            upset_final_answer_lane_max_volatility_penalty=0.05,
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "1x1:single"
    assert result.final_answer.selected_outcomes == {"safe_home": ["home_win"]}
    assert result.upset_capture_count == 0
    assert result.failed_count == 1
    assert result.warnings == [
        "scenario_failed:upset_lane:1x1:single:upset_final_answer_lane_no_candidates"
    ]
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 0
    assert result.summary_json["final_answer_upset_final_answer_lane_selected_candidate_count"] == 0


def test_historical_backtest_upset_lane_signal_calibration_filter_is_enforced() -> None:
    historical_slice = _upset_signal_calibration_risk_slice()

    result = run_historical_recommendation_backtest(
        historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_fixture_limit=1,
            max_candidates_per_fixture=1,
            min_probability=0.15,
            min_data_quality_score=80.0,
            unit_stake=2.0,
            max_budget=4.0,
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type="1x1",
            upset_final_answer_lane_min_protection_score=0.45,
            upset_final_answer_lane_min_probability=0.15,
            upset_final_answer_lane_min_decimal_odds=3.5,
            upset_final_answer_lane_max_decimal_odds=5.0,
            upset_final_answer_lane_min_model_edge=-0.05,
            upset_final_answer_lane_max_model_edge=0.0,
            upset_final_answer_lane_competition_ids=("TEST",),
            upset_final_answer_lane_max_signal_calibration_risk=0.20,
            upset_final_answer_lane_min_signal_reliability_score=0.70,
            upset_final_answer_lane_score_boost=1.0,
        ),
    )

    assert result.final_answer is not None
    assert result.final_answer.scenario.scenario_key == "1x1:single"
    assert result.final_answer.selected_outcomes == {"safe_home": ["home_win"]}
    assert result.failed_count == 1
    assert result.warnings == [
        "scenario_failed:upset_lane:1x1:single:upset_final_answer_lane_no_candidates"
    ]
    assert result.summary_json["upset_final_answer_lane_candidate_count"] == 0
    assert result.summary_json["upset_final_answer_lane_max_signal_calibration_risk"] == 0.20
    assert result.summary_json["upset_final_answer_lane_min_signal_reliability_score"] == 0.70


def _correct_score_lane_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata(slice_id=slice_id),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_score",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Score Home",
                away_team_name="Score Away",
                actual_home_goals=2,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.2-correct-score-lane-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.56,
                        decimal_odds=1.60,
                        market_probability=1 / 1.60,
                        data_quality_score=94,
                        model_confidence_score=0.91,
                        calibration_score=0.90,
                    ),
                    HistoricalMarketPrediction(
                        market_type="correct_score",
                        outcome="2-1",
                        probability=0.30,
                        decimal_odds=6.00,
                        market_probability=1 / 6.00,
                        data_quality_score=94,
                        model_confidence_score=0.91,
                        calibration_score=0.90,
                    ),
                ],
            ),
            HistoricalFixture(
                fixture_id="fixture_anchor",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 20),
                home_team_name="Anchor Home",
                away_team_name="Anchor Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.2-correct-score-lane-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.70,
                        decimal_odds=1.55,
                        market_probability=1 / 1.55,
                        data_quality_score=93,
                        model_confidence_score=0.90,
                        calibration_score=0.89,
                    )
                ],
            ),
        ],
    )


def _metadata(
    slice_id: str = "unit_test_historical_slice",
) -> HistoricalRecommendationSliceMetadata:
    return HistoricalRecommendationSliceMetadata(
        slice_id=slice_id,
        name="Unit test historical slice",
        competition_id="TEST",
        result_source="unit test final scores",
        odds_source="unit test odds",
        prediction_source="unit test predictions",
    )


def _slice_for_season_index(
    slice_id: str,
    *,
    competition_id: str,
    season: str,
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=f"{slice_id} slice",
            competition_id=competition_id,
            season=season,
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture",
                competition_id=competition_id,
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.70,
                        decimal_odds=1.50,
                    )
                ],
            )
        ],
    )


def _upset_reserve_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_upset_reserve_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="safe_home",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 16),
                home_team_name="Reliable FC",
                away_team_name="Away FC",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.88,
                        decimal_odds=1.38,
                        market_probability=0.72,
                        model_edge=0.16,
                        data_quality_score=95.0,
                        model_confidence_score=0.95,
                        calibration_score=0.94,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id="reserve_draw",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Fragile Favorite",
                away_team_name="Draw Town",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-historical-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="draw",
                        probability=0.24,
                        decimal_odds=3.60,
                        market_probability=0.28,
                        model_edge=-0.04,
                        data_quality_score=92.0,
                        model_confidence_score=0.88,
                        calibration_score=0.90,
                        upset_protection_score=0.82,
                        metadata_json={
                            "target_outcome": "draw",
                            "upset_score": 0.82,
                            "upset_direction": "draw_overlooked",
                        },
                    )
                ],
            ),
        ],
    )


def _upset_signal_calibration_risk_slice() -> HistoricalRecommendationSlice:
    historical_slice = _upset_reserve_slice()
    historical_slice.metadata.slice_id = "unit_test_upset_signal_calibration_risk_slice"
    risky_prediction = historical_slice.fixtures[1].predictions[0]
    risky_prediction.metadata_json.update(
        {
            "historical_upset_signal_profile_key": "profile:test:risky_draw",
            "historical_upset_signal_observation_count": 3,
            "historical_upset_signal_average_hit_probability_delta": -0.27,
            "historical_upset_signal_average_brier_score_delta": 0.35,
            "historical_upset_signal_average_log_loss_delta": 0.80,
            "historical_upset_signal_average_calibration_error_delta": 0.27,
        }
    )
    return historical_slice


def _solver_improvement_slice(
    slice_id: str = "unit_test_historical_slice",
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata(slice_id=slice_id),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "fixture_a",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.75,
                decimal_odds=1.30,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_b",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.74,
                decimal_odds=1.31,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_c",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.67,
                decimal_odds=2.00,
                model_edge=-0.20,
            ),
            _comparison_fixture(
                "fixture_d",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.67,
                decimal_odds=2.00,
                model_edge=-0.20,
            ),
        ],
    )


def _calibrated_upset_exposure_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata(slice_id="unit_test_calibrated_upset_exposure_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "fixture_safe_a",
                actual_home_goals=1,
                actual_away_goals=0,
                probability=0.90,
                decimal_odds=1.18,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_safe_b",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.88,
                decimal_odds=1.20,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_upset_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.48,
                decimal_odds=3.35,
                model_edge=0.02,
                upset_protection_score=0.84,
                odds_stability_score=0.82,
                volatility_penalty=0.04,
                calibration_score=0.92,
                data_quality_score=94,
                model_confidence_score=0.91,
                metadata_json={"target_outcome": "home_win", "upset_score": 0.84},
            ),
            _comparison_fixture(
                "fixture_upset_b",
                actual_home_goals=1,
                actual_away_goals=0,
                probability=0.47,
                decimal_odds=3.30,
                model_edge=0.02,
                upset_protection_score=0.82,
                odds_stability_score=0.80,
                volatility_penalty=0.05,
                calibration_score=0.91,
                data_quality_score=93,
                model_confidence_score=0.90,
                metadata_json={"target_outcome": "home_win", "upset_score": 0.82},
            ),
        ],
    )


def _quality_signal_backtest_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata(slice_id=slice_id),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "quality_signal_risky_a",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.74,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _comparison_fixture(
                "quality_signal_risky_b",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.73,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
        ],
    )


def _quality_signal_candidate(
    fixture_id: str,
    *,
    probability: float,
    decimal_odds: float,
    model_edge: float,
    season_id: str = "2023-2024",
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome="home_win",
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        model_edge=model_edge,
        data_quality_score=90.0,
        model_confidence_score=0.88,
        calibration_score=0.86,
        odds_stability_score=0.75,
        metadata_json={
            "competition_id": "TEST",
            "season_id": season_id,
            "competition_season_index": 4,
        },
    )


def _quality_signal_plan_option(
    option_key: str,
    *,
    candidates: list[RecommendationCandidate],
    planner_score: float,
    hit_probability: float,
    roi: float,
    risk_score: float,
    pass_type: str,
    mode: RecommendationMode = "single",
    total_atomic_bets: int = 1,
    total_stake: float = 2.0,
    multiplier: int = 1,
) -> RecommendationGlobalPlanOption:
    selected_candidates = [
        ScoredRecommendationCandidate(
            candidate=candidate,
            score=0.80,
            component_scores={},
            reason_codes=[],
        )
        for candidate in candidates
    ]
    selection = RecommendationSelection(
        pass_type=pass_type,
        mode=mode,
        selected_candidates=selected_candidates,
        evaluation=ParlayEvaluation(
            pass_type=pass_type,
            is_multiple=mode == "multiple",
            unit_stake=2.0,
            multiplier=multiplier,
            total_atomic_bets=total_atomic_bets,
            total_stake=total_stake,
            hit_probability=hit_probability,
            expected_payout=total_stake * (1.0 + roi),
            expected_value=total_stake * roi,
            roi=roi,
            risk_score=risk_score,
            risk_level="low",
            rule_valid=True,
            atomic_bets=[],
        ),
        total_score=planner_score,
        candidate_count=len(candidates),
        excluded_candidate_count=0,
    )
    return RecommendationGlobalPlanOption(
        option_key=option_key,
        option_type=_quality_signal_plan_option_type(pass_type, mode),
        pass_type=pass_type,
        mode=mode,
        planner_score=planner_score,
        within_budget=True,
        selection=selection,
    )


def _quality_signal_plan_option_type(
    pass_type: str,
    mode: RecommendationMode,
) -> str:
    if mode == "multiple":
        return "multiple_parlay"
    if pass_type == "1x1":
        return "standalone_single"
    return "single_parlay"


def _comparison_fixture(
    fixture_id: str,
    *,
    actual_home_goals: int,
    actual_away_goals: int,
    probability: float,
    decimal_odds: float,
    model_edge: float,
    upset_protection_score: float = 0.0,
    odds_stability_score: float = 0.75,
    volatility_penalty: float = 0.0,
    calibration_score: float = 0.86,
    data_quality_score: float = 90.0,
    model_confidence_score: float = 0.88,
    metadata_json: dict[str, object] | None = None,
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
        model_version="poisson-v3.1-historical-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=model_edge,
                data_quality_score=data_quality_score,
                model_confidence_score=model_confidence_score,
                calibration_score=calibration_score,
                upset_protection_score=upset_protection_score,
                odds_stability_score=odds_stability_score,
                volatility_penalty=volatility_penalty,
                metadata_json=metadata_json or {},
            )
        ],
    )


def _full_market_fixture(
    fixture_id: str,
    *,
    home_team_name: str,
    away_team_name: str,
    actual_home_goals: int,
    actual_away_goals: int,
    probabilities: dict[str, float],
    odds: dict[str, float],
    odds_stability_score: float,
    volatility_penalty: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-historical-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome=outcome,
                probability=probabilities[outcome],
                decimal_odds=odds[outcome],
                market_probability=probabilities[outcome],
                model_edge=0.0,
                data_quality_score=92.0,
                model_confidence_score=0.90,
                calibration_score=0.88,
                upset_protection_score=0.0,
                odds_stability_score=odds_stability_score,
                volatility_penalty=volatility_penalty,
            )
            for outcome in ("home_win", "draw", "away_win")
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
