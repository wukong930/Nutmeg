from __future__ import annotations

from math import isclose

from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.parlay import evaluate_parlay, expand_atomic_bets, hit_probability, is_multiple_parlay


def test_single_selection_two_by_one_parlay() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.6},
            odds={"home_win": 2.0},
            model_version="poisson-m1.0.0",
            prediction_snapshot_id=101,
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["away_win"],
            probabilities={"away_win": 0.5},
            odds={"away_win": 1.8},
            model_version="poisson-m1.0.0",
            prediction_snapshot_id=102,
        ),
    ]

    evaluation = evaluate_parlay(legs, pass_type="2x1", unit_stake=2.0)

    assert evaluation.total_atomic_bets == 1
    assert evaluation.is_multiple is False
    assert evaluation.total_stake == 2.0
    assert evaluation.hit_probability == 0.3
    assert isclose(evaluation.expected_payout, 2.16)
    assert isclose(evaluation.expected_value, 0.16)
    assert isclose(evaluation.roi, 0.08)
    assert evaluation.rule_valid is True
    assert evaluation.risk_level == "medium_high"
    assert evaluation.explanation_json["is_multiple"] is False
    assert evaluation.explanation_json["model_lineage"] == {
        "model_versions": ["poisson-m1.0.0"],
        "prediction_snapshot_ids": [101, 102],
    }


def test_multiple_selection_four_by_one_expands_to_atomic_bets() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["away_win", "draw"],
            probabilities={"away_win": 0.4, "draw": 0.3},
            odds={"away_win": 2.5, "draw": 3.2},
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["away_win"],
            probabilities={"away_win": 0.55},
            odds={"away_win": 1.9},
        ),
        ParlayLegSelection(
            fixture_id="C",
            market_type="1x2",
            outcomes=["draw", "away_win"],
            probabilities={"draw": 0.28, "away_win": 0.33},
            odds={"draw": 3.4, "away_win": 2.7},
        ),
        ParlayLegSelection(
            fixture_id="D",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.62},
            odds={"home_win": 1.6},
        ),
    ]

    atomic_bets = expand_atomic_bets(legs, unit_stake=2.0)
    evaluation = evaluate_parlay(legs, pass_type="4x1", unit_stake=2.0)

    assert len(atomic_bets) == 4
    assert is_multiple_parlay(legs)
    assert evaluation.total_atomic_bets == 4
    assert evaluation.is_multiple is True
    assert evaluation.total_stake == 8.0
    assert isclose(evaluation.hit_probability, 0.7 * 0.55 * 0.61 * 0.62)
    assert evaluation.expected_payout == sum(atomic.expected_payout for atomic in atomic_bets)
    assert isclose(evaluation.expected_value, evaluation.expected_payout - evaluation.total_stake)
    assert isclose(evaluation.roi, evaluation.expected_value / evaluation.total_stake)
    assert evaluation.explanation_json["calculation_basis"] == "independent_fixture_approximation"
    selected_probabilities = evaluation.explanation_json["selected_probability_by_fixture"]
    assert isinstance(selected_probabilities, dict)
    assert isclose(selected_probabilities["A"], 0.7)
    assert isclose(selected_probabilities["B"], 0.55)
    assert isclose(selected_probabilities["C"], 0.61)
    assert isclose(selected_probabilities["D"], 0.62)


def test_budget_limit_marks_parlay_rule_invalid() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win", "draw"],
            probabilities={"home_win": 0.5, "draw": 0.25},
            odds={"home_win": 1.8, "draw": 3.1},
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["away_win", "draw"],
            probabilities={"away_win": 0.45, "draw": 0.25},
            odds={"away_win": 2.1, "draw": 3.0},
        ),
    ]

    evaluation = evaluate_parlay(legs, pass_type="2x1", unit_stake=2.0, max_budget=6.0)

    assert evaluation.total_atomic_bets == 4
    assert evaluation.total_stake == 8.0
    assert evaluation.rule_valid is False
    assert evaluation.explanation_json["budget"] == {
        "max_budget": 6.0,
        "total_stake": 8.0,
        "within_budget": False,
    }
    assert "budget_exceeded" in evaluation.explanation_json["rule_reasons"]


def test_correlation_penalty_adjusts_hit_probability_and_risk() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.6},
            odds={"home_win": 2.0},
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["away_win"],
            probabilities={"away_win": 0.5},
            odds={"away_win": 1.8},
        ),
    ]

    evaluation = evaluate_parlay(
        legs,
        pass_type="2x1",
        unit_stake=2.0,
        correlation_penalty=0.10,
    )

    assert isclose(hit_probability(legs), 0.30)
    assert isclose(evaluation.hit_probability, 0.27)
    assert evaluation.correlation_penalty == 0.10
    assert evaluation.risk_score > 1 - evaluation.hit_probability
    assert (
        evaluation.explanation_json["hit_probability_after_correlation_penalty"]
        == evaluation.hit_probability
    )


def test_repeated_correlation_keys_derive_correlation_penalty() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.8},
            odds={"home_win": 1.4},
            correlation_key="team:favorite-fc",
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.7},
            odds={"home_win": 1.5},
            correlation_key="team:favorite-fc",
        ),
        ParlayLegSelection(
            fixture_id="C",
            market_type="1x2",
            outcomes=["away_win"],
            probabilities={"away_win": 0.6},
            odds={"away_win": 1.8},
            correlation_key="team:another-fc",
        ),
    ]

    evaluation = evaluate_parlay(
        legs,
        pass_type="3x1",
        unit_stake=2.0,
        derive_correlation_penalty=True,
    )

    assert isclose(hit_probability(legs), 0.336)
    assert evaluation.correlation_penalty == 0.07
    assert isclose(evaluation.hit_probability, 0.31248)
    assert evaluation.explanation_json["correlation_exposures"] == {
        "team:favorite-fc": 2,
    }


def test_same_fixture_multiple_markets_are_rule_invalid() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.6},
            odds={"home_win": 2.0},
        ),
        ParlayLegSelection(
            fixture_id="A",
            market_type="cn_handicap_1x2",
            outcomes=["handicap_home_win"],
            probabilities={"handicap_home_win": 0.4},
            odds={"handicap_home_win": 2.3},
            line=-1,
        ),
    ]

    evaluation = evaluate_parlay(legs, pass_type="2x1", unit_stake=2.0)

    assert evaluation.rule_valid is False
    assert (
        "same_fixture_multiple_markets_not_allowed"
        in evaluation.explanation_json["rule_reasons"]
    )


def test_market_leg_limit_is_enforced_for_correct_score() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id=f"F{i}",
            market_type="correct_score",
            outcomes=["1-1"],
            probabilities={"1-1": 0.1},
            odds={"1-1": 6.0},
        )
        for i in range(5)
    ]

    evaluation = evaluate_parlay(legs, pass_type="5x1", unit_stake=2.0)

    assert evaluation.rule_valid is False
    assert "market_leg_limit_exceeded" in evaluation.explanation_json["rule_reasons"]


def test_low_data_quality_marks_parlay_rule_invalid() -> None:
    legs = [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.6},
            odds={"home_win": 2.0},
            data_quality_score=45.0,
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["away_win"],
            probabilities={"away_win": 0.5},
            odds={"away_win": 1.8},
            data_quality_score=82.0,
        ),
    ]

    evaluation = evaluate_parlay(legs, pass_type="2x1", unit_stake=2.0)

    assert evaluation.rule_valid is False
    assert "data_quality_too_low" in evaluation.explanation_json["rule_reasons"]
    assert evaluation.explanation_json["data_quality"] == {
        "minimum_score_for_recommendation": 50.0,
        "leg_scores": {"A": 45.0, "B": 82.0},
    }
