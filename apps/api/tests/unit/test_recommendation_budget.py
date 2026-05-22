from __future__ import annotations

from math import isclose

from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.recommendations import optimize_multiple_parlay_budget


def test_budget_optimizer_removes_lowest_marginal_option_until_within_budget() -> None:
    result = optimize_multiple_parlay_budget(
        _multiple_legs(),
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    assert result.within_budget is True
    assert result.original_evaluation.total_atomic_bets == 4
    assert result.optimized_evaluation.total_atomic_bets == 2
    assert result.optimized_evaluation.total_stake == 4.0
    assert [(item.fixture_id, item.outcome) for item in result.removed_options] == [
        ("C", "draw")
    ]
    assert isclose(result.removed_options[0].marginal_score, 0.576)


def test_budget_optimizer_preserves_locked_outcomes_when_pruning() -> None:
    result = optimize_multiple_parlay_budget(
        _multiple_legs(),
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=4.0,
        locked_outcomes={("C", "draw")},
    )

    assert result.within_budget is True
    assert [(item.fixture_id, item.outcome) for item in result.removed_options] == [
        ("A", "draw")
    ]
    optimized_by_fixture = {leg.fixture_id: leg.outcomes for leg in result.optimized_legs}
    assert optimized_by_fixture["C"] == ["away_win", "draw"]


def test_budget_optimizer_uses_projected_combination_quality_for_pruning() -> None:
    result = optimize_multiple_parlay_budget(
        [
            ParlayLegSelection(
                fixture_id="A",
                market_type="1x2",
                outcomes=["home_win", "draw"],
                probabilities={"home_win": 0.65, "draw": 0.14},
                odds={"home_win": 1.50, "draw": 8.00},
                data_quality_score=90.0,
            ),
            ParlayLegSelection(
                fixture_id="B",
                market_type="1x2",
                outcomes=["home_win", "draw"],
                probabilities={"home_win": 0.62, "draw": 0.36},
                odds={"home_win": 1.40, "draw": 1.80},
                data_quality_score=90.0,
            ),
            ParlayLegSelection(
                fixture_id="C",
                market_type="1x2",
                outcomes=["away_win"],
                probabilities={"away_win": 0.70},
                odds={"away_win": 1.50},
                data_quality_score=90.0,
            ),
        ],
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    assert result.within_budget is True
    assert result.optimization_basis == "budget_constrained_quality_search_v1"
    assert result.optimized_evaluation.total_atomic_bets == 2
    optimized_by_fixture = {leg.fixture_id: leg.outcomes for leg in result.optimized_legs}
    assert optimized_by_fixture == {
        "A": ["home_win"],
        "B": ["home_win", "draw"],
        "C": ["away_win"],
    }
    assert [(item.fixture_id, item.outcome) for item in result.removed_options] == [
        ("A", "draw")
    ]
    assert result.removed_options[0].marginal_score > 1.0
    assert result.removed_options[0].projected_total_stake == 4.0
    assert isclose(
        result.removed_options[0].projected_quality_score,
        result.optimized_quality_score,
    )


def test_budget_optimizer_reports_when_locked_single_options_cannot_fit_budget() -> None:
    result = optimize_multiple_parlay_budget(
        [
            ParlayLegSelection(
                fixture_id="A",
                market_type="1x2",
                outcomes=["home_win"],
                probabilities={"home_win": 0.6},
                odds={"home_win": 1.8},
            ),
            ParlayLegSelection(
                fixture_id="B",
                market_type="1x2",
                outcomes=["away_win"],
                probabilities={"away_win": 0.5},
                odds={"away_win": 1.9},
            ),
        ],
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=1.0,
    )

    assert result.within_budget is False
    assert result.removed_options == []
    assert result.warning_codes == ["budget_cannot_be_reduced_with_locked_outcomes"]


def _multiple_legs() -> list[ParlayLegSelection]:
    return [
        ParlayLegSelection(
            fixture_id="A",
            market_type="1x2",
            outcomes=["home_win", "draw"],
            probabilities={"home_win": 0.60, "draw": 0.20},
            odds={"home_win": 1.60, "draw": 3.00},
        ),
        ParlayLegSelection(
            fixture_id="B",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.70},
            odds={"home_win": 1.40},
        ),
        ParlayLegSelection(
            fixture_id="C",
            market_type="1x2",
            outcomes=["away_win", "draw"],
            probabilities={"away_win": 0.55, "draw": 0.18},
            odds={"away_win": 1.90, "draw": 3.20},
        ),
        ParlayLegSelection(
            fixture_id="D",
            market_type="1x2",
            outcomes=["home_win"],
            probabilities={"home_win": 0.65},
            odds={"home_win": 1.50},
        ),
    ]
