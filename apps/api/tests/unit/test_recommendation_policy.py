from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.recommendations import (
    RecommendationCandidate,
    RecommendationPolicyConfig,
    build_recommendation_policy_config,
    build_single_focus_policy_config,
    build_upset_focus_policy_config,
    rank_candidates,
    select_best_candidate,
    select_best_single_parlay,
)


def test_accuracy_first_policy_prefers_probability_quality_over_flashy_odds() -> None:
    steady_candidate = _candidate(
        "A",
        "home_win",
        probability=0.64,
        decimal_odds=1.72,
        market_probability=0.59,
    )
    flashy_longshot = _candidate(
        "B",
        "away_win",
        probability=0.34,
        decimal_odds=5.20,
        market_probability=0.20,
    )

    selected = select_best_candidate([flashy_longshot, steady_candidate])

    assert selected.candidate.fixture_id == "A"
    assert selected.score > 0.70
    assert "accuracy_first_probability_component" in selected.reason_codes


def test_single_focus_policy_prefers_high_confidence_probability_quality() -> None:
    steady_candidate = _candidate(
        "A",
        "home_win",
        probability=0.66,
        market_probability=0.62,
        data_quality_score=92,
        model_confidence_score=0.92,
        calibration_score=0.90,
    )
    upset_candidate = _candidate(
        "B",
        "away_win",
        probability=0.63,
        market_probability=0.56,
        data_quality_score=80,
        model_confidence_score=0.75,
        calibration_score=0.78,
        upset_protection_score=0.95,
    )

    ranked = rank_candidates(
        [upset_candidate, steady_candidate],
        config=build_single_focus_policy_config(
            strategy="accuracy_first",
            allowed_markets=("1x2",),
            min_probability=0.10,
            min_model_edge=None,
            min_data_quality_score=50,
            require_odds=True,
        ),
    )

    assert ranked[0].candidate.fixture_id == "A"


def test_upset_focus_policy_prioritizes_upset_signal_when_quality_is_acceptable() -> None:
    steady_candidate = _candidate(
        "A",
        "home_win",
        probability=0.66,
        market_probability=0.62,
        data_quality_score=92,
        model_confidence_score=0.92,
        calibration_score=0.90,
    )
    upset_candidate = _candidate(
        "B",
        "away_win",
        probability=0.63,
        market_probability=0.56,
        data_quality_score=80,
        model_confidence_score=0.75,
        calibration_score=0.78,
        upset_protection_score=0.95,
    )

    ranked = rank_candidates(
        [steady_candidate, upset_candidate],
        config=build_upset_focus_policy_config(
            strategy="upset_protection",
            allowed_markets=("1x2",),
            min_probability=0.10,
            min_model_edge=None,
            min_data_quality_score=50,
            require_odds=True,
        ),
    )

    assert ranked[0].candidate.fixture_id == "B"
    assert ranked[0].component_scores["upset_protection"] == 0.95


def test_value_first_policy_filters_negative_edge_and_prefers_price_quality() -> None:
    high_probability_bad_price = _candidate(
        "A",
        "home_win",
        probability=0.70,
        decimal_odds=1.25,
        market_probability=0.80,
    )
    lower_probability_good_price = _candidate(
        "B",
        "draw",
        probability=0.31,
        decimal_odds=4.00,
        market_probability=0.25,
    )

    ranked = rank_candidates(
        [high_probability_bad_price, lower_probability_good_price],
        config=build_recommendation_policy_config(
            strategy="value_first",
            allowed_markets=("1x2",),
            min_probability=0.20,
            min_model_edge=None,
            min_data_quality_score=50,
            require_odds=True,
        ),
    )

    assert [item.candidate.fixture_id for item in ranked] == ["B"]
    assert ranked[0].candidate.effective_model_edge() > 0


def test_policy_applies_internal_candidate_score_penalty() -> None:
    penalized_high_probability = _candidate(
        "A",
        "home_win",
        probability=0.74,
        decimal_odds=1.35,
        metadata_json={"internal_candidate_score_penalty": 0.40},
    )
    cleaner_candidate = _candidate(
        "B",
        "home_win",
        probability=0.66,
        decimal_odds=1.82,
        market_probability=0.55,
    )

    ranked = rank_candidates([penalized_high_probability, cleaner_candidate])

    assert ranked[0].candidate.fixture_id == "B"
    assert ranked[1].component_scores["candidate_score_penalty"] == 0.40
    assert "candidate_score_penalty_applied" in ranked[1].reason_codes


def test_policy_can_lower_data_quality_threshold_for_one_competition() -> None:
    beta_competition_candidate = _candidate(
        "A",
        "home_win",
        probability=0.62,
        data_quality_score=72,
        metadata_json={"competition_id": "FRA_LIGUE_2"},
    )
    protected_competition_candidate = _candidate(
        "B",
        "home_win",
        probability=0.61,
        data_quality_score=72,
        metadata_json={"competition_id": "EPL"},
    )

    ranked = rank_candidates(
        [beta_competition_candidate, protected_competition_candidate],
        config=RecommendationPolicyConfig(
            min_probability=0.10,
            min_data_quality_score=80,
            min_data_quality_score_by_competition_id={"FRA_LIGUE_2": 70},
        ),
    )

    assert [item.candidate.fixture_id for item in ranked] == ["A"]


def test_policy_beta_quality_lane_filters_lowered_threshold_candidates() -> None:
    stable_candidate = _candidate(
        "A",
        "home_win",
        probability=0.56,
        decimal_odds=2.10,
        market_probability=0.49,
        data_quality_score=72,
        metadata_json={"competition_id": "FRA_LIGUE_2"},
        odds_stability_score=0.96,
        volatility_penalty=0.03,
    )
    volatile_candidate = _candidate(
        "B",
        "home_win",
        probability=0.57,
        decimal_odds=2.05,
        market_probability=0.49,
        data_quality_score=72,
        metadata_json={"competition_id": "FRA_LIGUE_2"},
        odds_stability_score=0.82,
        volatility_penalty=0.12,
    )

    ranked = rank_candidates(
        [volatile_candidate, stable_candidate],
        config=RecommendationPolicyConfig(
            min_probability=0.10,
            min_data_quality_score=80,
            min_data_quality_score_by_competition_id={"FRA_LIGUE_2": 70},
            data_quality_beta_lane_enabled=True,
            data_quality_beta_lane_competition_ids=("FRA_LIGUE_2",),
            data_quality_beta_lane_min_probability=0.50,
            data_quality_beta_lane_max_decimal_odds=2.30,
            data_quality_beta_lane_min_model_edge=0.0,
            data_quality_beta_lane_min_odds_stability_score=0.90,
            data_quality_beta_lane_max_volatility_penalty=0.08,
        ),
    )

    assert [item.candidate.fixture_id for item in ranked] == ["A"]


def test_policy_beta_quality_lane_can_be_limited_to_season_regime() -> None:
    matching_regime_candidate = _candidate(
        "A",
        "home_win",
        probability=0.56,
        decimal_odds=2.10,
        market_probability=0.49,
        data_quality_score=72,
        metadata_json={
            "competition_id": "FRA_LIGUE_2",
            "season_id": "2022_2023",
            "competition_season_index": 3,
        },
        odds_stability_score=0.96,
        volatility_penalty=0.03,
    )
    wrong_season_candidate = _candidate(
        "B",
        "home_win",
        probability=0.57,
        decimal_odds=2.05,
        market_probability=0.49,
        data_quality_score=72,
        metadata_json={
            "competition_id": "FRA_LIGUE_2",
            "season_id": "2021_2022",
            "competition_season_index": 2,
        },
        odds_stability_score=0.96,
        volatility_penalty=0.03,
    )

    ranked = rank_candidates(
        [wrong_season_candidate, matching_regime_candidate],
        config=RecommendationPolicyConfig(
            min_probability=0.10,
            min_data_quality_score=80,
            min_data_quality_score_by_competition_id={"FRA_LIGUE_2": 70},
            data_quality_beta_lane_enabled=True,
            data_quality_beta_lane_competition_ids=("FRA_LIGUE_2",),
            data_quality_beta_lane_season_ids=("2022_2023",),
            data_quality_beta_lane_min_competition_season_index=3,
            data_quality_beta_lane_min_probability=0.50,
            data_quality_beta_lane_max_decimal_odds=2.30,
            data_quality_beta_lane_min_model_edge=0.0,
            data_quality_beta_lane_min_odds_stability_score=0.90,
            data_quality_beta_lane_max_volatility_penalty=0.08,
        ),
    )

    assert [item.candidate.fixture_id for item in ranked] == ["A"]


def test_six_by_one_selection_preserves_locked_started_legs_and_fills_future_matches() -> None:
    as_of_time = datetime(2026, 5, 2, 12, tzinfo=UTC)
    locked_candidates = [
        _candidate("A", "home_win", probability=0.61, kickoff_time_utc=_dt(2026, 5, 1, 18)),
        _candidate("B", "draw", probability=0.33, kickoff_time_utc=_dt(2026, 5, 1, 20)),
    ]
    future_candidates = [
        _candidate("C", "away_win", probability=0.57, kickoff_time_utc=_dt(2026, 5, 3, 18)),
        _candidate("D", "home_win", probability=0.56, kickoff_time_utc=_dt(2026, 5, 3, 19)),
        _candidate("E", "home_win", probability=0.55, kickoff_time_utc=_dt(2026, 5, 4, 18)),
        _candidate("F", "away_win", probability=0.54, kickoff_time_utc=_dt(2026, 5, 4, 20)),
        _candidate("G", "draw", probability=0.28, kickoff_time_utc=_dt(2026, 5, 4, 21)),
    ]

    selection = select_best_single_parlay(
        future_candidates,
        pass_type="6x1",
        unit_stake=2.0,
        max_budget=10.0,
        as_of_time_utc=as_of_time,
        locked_candidates=locked_candidates,
    )

    assert selection.fixture_ids == ["A", "B", "C", "D", "E", "F"]
    assert selection.locked_fixture_ids == ["A", "B"]
    assert selection.evaluation.total_atomic_bets == 1
    assert selection.evaluation.pass_type == "6x1"
    assert selection.explanation_json["started_locked_fixture_ids"] == ["A", "B"]


def test_unlocked_started_candidates_are_excluded_from_new_recommendations() -> None:
    as_of_time = datetime(2026, 5, 2, 12, tzinfo=UTC)
    started_high_probability = _candidate(
        "A",
        "home_win",
        probability=0.88,
        kickoff_time_utc=_dt(2026, 5, 1, 18),
    )
    future_candidates = [
        _candidate("B", "home_win", probability=0.57, kickoff_time_utc=_dt(2026, 5, 3, 18)),
        _candidate("C", "away_win", probability=0.56, kickoff_time_utc=_dt(2026, 5, 3, 20)),
    ]

    selection = select_best_single_parlay(
        [started_high_probability, *future_candidates],
        pass_type="2x1",
        unit_stake=2.0,
        as_of_time_utc=as_of_time,
    )

    assert selection.fixture_ids == ["B", "C"]
    assert selection.excluded_candidate_count == 1


def test_selection_requires_enough_distinct_fixture_candidates() -> None:
    with pytest.raises(ValueError, match="insufficient_distinct_fixture_candidates"):
        select_best_single_parlay(
            [
                _candidate("A", "home_win", probability=0.61),
                _candidate("A", "draw", probability=0.28),
            ],
            pass_type="2x1",
            unit_stake=2.0,
        )


def test_policy_supports_one_to_eight_by_one_only() -> None:
    selection = select_best_single_parlay(
        [_candidate("A", "home_win", probability=0.61)],
        pass_type="1x1",
        unit_stake=2.0,
        config=RecommendationPolicyConfig(min_probability=0.10),
    )

    assert selection.fixture_ids == ["A"]

    with pytest.raises(ValueError, match="1x1 through 8x1"):
        select_best_single_parlay(
            [_candidate("A", "home_win", probability=0.61)],
            pass_type="9x1",
            unit_stake=2.0,
            config=RecommendationPolicyConfig(min_probability=0.10),
        )


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float = 1.90,
    market_probability: float | None = None,
    data_quality_score: float = 88.0,
    model_confidence_score: float = 0.90,
    calibration_score: float = 0.85,
    upset_protection_score: float = 0.0,
    odds_stability_score: float = 0.70,
    volatility_penalty: float = 0.0,
    kickoff_time_utc: datetime | None = None,
    metadata_json: dict[str, object] | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=market_probability,
        data_quality_score=data_quality_score,
        model_confidence_score=model_confidence_score,
        calibration_score=calibration_score,
        upset_protection_score=upset_protection_score,
        odds_stability_score=odds_stability_score,
        volatility_penalty=volatility_penalty,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=100,
        prediction_time_utc=datetime(2026, 5, 1, 12, tzinfo=UTC),
        kickoff_time_utc=kickoff_time_utc,
        metadata_json=metadata_json or {},
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
