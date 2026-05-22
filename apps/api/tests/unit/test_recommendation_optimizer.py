from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from nutmeg.recommendations import (
    RecommendationCandidate,
    compare_locked_preserving_to_current_best,
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)


def test_multiple_optimizer_adds_positive_marginal_protection_within_budget() -> None:
    selection = select_budget_constrained_multiple_parlay(
        _candidate_pool(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    assert selection.mode == "multiple"
    assert selection.fixture_ids == ["A", "B", "C"]
    assert selection.evaluation.total_atomic_bets == 2
    assert selection.evaluation.total_stake == 4.0
    budget = selection.evaluation.explanation_json["budget"]
    assert isinstance(budget, dict)
    assert budget["max_budget"] == 4.0
    assert budget["within_budget"] is True
    selected_outcomes = cast(
        dict[str, list[str]],
        selection.explanation_json["selected_outcomes_by_fixture"],
    )
    assert selected_outcomes == {
        "A": ["home_win", "draw"],
        "B": ["home_win"],
        "C": ["away_win"],
    }
    decisions = selection.explanation_json["multiple_option_decisions"]
    assert isinstance(decisions, list)
    assert decisions[0]["action"] == "added"
    assert decisions[0]["fixture_id"] == "A"
    assert decisions[0]["outcome"] == "draw"


def test_multiple_optimizer_skips_protection_when_budget_is_too_small() -> None:
    selection = select_budget_constrained_multiple_parlay(
        _candidate_pool(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=2.0,
    )

    assert selection.evaluation.total_atomic_bets == 1
    assert selection.evaluation.total_stake == 2.0
    decisions = selection.explanation_json["multiple_option_decisions"]
    assert isinstance(decisions, list)
    assert any(decision["reason_code"] == "budget_exceeded" for decision in decisions)
    budget_adjustment = selection.explanation_json["budget_adjustment"]
    assert isinstance(budget_adjustment, dict)
    assert budget_adjustment["strategy"] == "prune_lowest_marginal_unlocked_options"
    assert budget_adjustment["original_total_stake"] > budget_adjustment["optimized_total_stake"]
    assert budget_adjustment["optimized_total_stake"] == 2.0
    assert budget_adjustment["within_budget"] is True


def test_multiple_optimizer_uses_core_quality_without_forced_upset_pruning() -> None:
    selection = select_budget_constrained_multiple_parlay(
        _candidate_pool_for_budget_pruning(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    assert selection.evaluation.total_atomic_bets == 2
    assert selection.evaluation.total_stake == 4.0
    assert "budget_adjustment" not in selection.explanation_json
    selected_outcomes = cast(
        dict[str, list[str]],
        selection.explanation_json["selected_outcomes_by_fixture"],
    )
    assert selected_outcomes == {
        "A": ["home_win", "draw"],
        "B": ["home_win"],
        "C": ["away_win"],
    }


def test_multiple_optimizer_does_not_add_options_to_started_locked_fixture() -> None:
    as_of_time = datetime(2026, 5, 2, 12, tzinfo=UTC)
    locked = [
        _candidate(
            "A",
            "home_win",
            probability=0.62,
            decimal_odds=1.70,
            kickoff_time_utc=datetime(2026, 5, 1, 20, tzinfo=UTC),
        )
    ]
    candidates = [
        *_candidate_pool(),
        _candidate(
            "A",
            "draw",
            probability=0.30,
            decimal_odds=3.20,
            kickoff_time_utc=datetime(2026, 5, 1, 20, tzinfo=UTC),
        ),
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
        as_of_time_utc=as_of_time,
        locked_candidates=locked,
    )

    selected_outcomes = cast(
        dict[str, list[str]],
        selection.explanation_json["selected_outcomes_by_fixture"],
    )
    assert selected_outcomes["A"] == ["home_win"]


def test_locked_comparison_keeps_user_constraint_but_shows_current_best_delta() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.42, decimal_odds=2.40),
        _candidate("B", "home_win", probability=0.74, decimal_odds=1.50),
        _candidate("C", "away_win", probability=0.69, decimal_odds=1.55),
        _candidate("D", "home_win", probability=0.68, decimal_odds=1.57),
    ]
    comparison = compare_locked_preserving_to_current_best(
        candidates,
        locked_candidates=[candidates[0]],
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=2.0,
        max_outcomes_per_fixture=1,
    )

    assert comparison.locked_preserving_selection.fixture_ids == ["A", "B"]
    assert comparison.current_best_selection.fixture_ids == ["B", "C"]
    assert comparison.changed_fixture_ids == ["A", "C"]
    assert comparison.explanation_json["comparison_basis"] == ("locked_preserving_vs_current_best")


def test_multiple_optimizer_replaces_unlocked_fixture_for_budget_safe_protection() -> None:
    locked = [_candidate("A", "home_win", probability=0.65, decimal_odds=1.55)]
    candidates = [
        _candidate("B", "home_win", probability=0.62, decimal_odds=1.60),
        _candidate("C", "away_win", probability=0.61, decimal_odds=1.65),
        _candidate("D", "home_win", probability=0.57, decimal_odds=1.75),
        _candidate(
            "D",
            "draw",
            probability=0.32,
            decimal_odds=3.20,
            upset_protection_score=0.90,
        ),
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
        locked_candidates=locked,
    )

    assert selection.fixture_ids == ["A", "C", "D"]
    assert selection.locked_fixture_ids == ["A"]
    assert selection.evaluation.total_stake == 4.0
    budget = selection.evaluation.explanation_json["budget"]
    assert isinstance(budget, dict)
    assert budget["max_budget"] == 4.0
    assert budget["within_budget"] is True
    selected_outcomes = cast(
        dict[str, list[str]],
        selection.explanation_json["selected_outcomes_by_fixture"],
    )
    assert selected_outcomes["A"] == ["home_win"]
    assert selected_outcomes["C"] == ["away_win"]
    assert selected_outcomes["D"] == ["home_win", "draw"]
    upset_policy = selection.explanation_json["upset_policy"]
    assert isinstance(upset_policy, dict)
    assert upset_policy["max_protection_score"] > 0.0
    assert "upset_quality" in upset_policy
    replacement_search = selection.explanation_json["fixture_replacement_search"]
    assert isinstance(replacement_search, dict)
    replacements = replacement_search["accepted_replacements"]
    assert isinstance(replacements, list)
    assert replacements[0]["old_fixture_id"] == "B"
    assert replacements[0]["new_fixture_id"] == "D"
    assert replacements[0]["replacement_outcomes"] == ["home_win", "draw"]


def test_multiple_optimizer_budget_path_keeps_upset_quality_selection() -> None:
    candidates = [
        _candidate(
            "A",
            "home_win",
            probability=0.366,
            decimal_odds=2.495,
            upset_protection_score=0.147,
        ),
        _candidate(
            "A",
            "away_win",
            probability=0.461,
            decimal_odds=2.063,
            upset_protection_score=0.335,
        ),
        _candidate(
            "B",
            "home_win",
            probability=0.571,
            decimal_odds=1.440,
            upset_protection_score=0.242,
        ),
        _candidate(
            "B",
            "draw",
            probability=0.304,
            decimal_odds=3.882,
            upset_protection_score=0.501,
        ),
        _candidate(
            "C",
            "home_win",
            probability=0.215,
            decimal_odds=3.807,
            upset_protection_score=0.181,
        ),
        _candidate(
            "D",
            "home_win",
            probability=0.688,
            decimal_odds=1.709,
            upset_protection_score=0.162,
        ),
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=8.0,
    )

    assert selection.evaluation.total_stake <= 8.0
    assert selection.fixture_ids == ["D", "B", "A", "C"]
    selected_outcomes = cast(
        dict[str, list[str]],
        selection.explanation_json["selected_outcomes_by_fixture"],
    )
    assert selected_outcomes == {
        "B": ["draw"],
        "D": ["home_win"],
        "A": ["away_win"],
        "C": ["home_win"],
    }
    upset_policy = selection.explanation_json["upset_policy"]
    assert isinstance(upset_policy, dict)
    assert upset_policy["max_protection_score"] > 0.45
    assert "draw_overlooked" in upset_policy["directions"]


def test_single_optimizer_uses_exact_solver_when_pair_quality_beats_greedy() -> None:
    candidates = [
        _candidate(
            "A",
            "home_win",
            probability=0.75,
            decimal_odds=1.30,
            model_edge=0.20,
        ),
        _candidate(
            "B",
            "home_win",
            probability=0.74,
            decimal_odds=1.31,
            model_edge=0.20,
        ),
        _candidate(
            "C",
            "home_win",
            probability=0.50,
            decimal_odds=2.80,
            model_edge=-0.10,
        ),
        _candidate(
            "D",
            "home_win",
            probability=0.50,
            decimal_odds=2.80,
            model_edge=-0.10,
        ),
    ]

    selection = select_budget_constrained_single_parlay(
        candidates,
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=2.0,
    )

    assert selection.fixture_ids == ["C", "D"]
    assert selection.evaluation.expected_value > 0
    solver_search = selection.explanation_json["solver_search"]
    assert isinstance(solver_search, dict)
    assert solver_search["strategy"] == "budget_constrained_integer_solver"
    assert solver_search["search_mode"] == "exact_integer_search"
    assert solver_search["accepted"] is True
    assert solver_search["exact"] is True
    assert solver_search["supersedes_heuristic_path"] is True


def test_multiple_optimizer_uses_dynamic_programming_solver_for_large_pool() -> None:
    candidates = [
        _candidate(
            f"F{index:02d}",
            "home_win",
            probability=0.62 - index * 0.002,
            decimal_odds=1.80 + index * 0.01,
        )
        for index in range(30)
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=2.0,
        max_outcomes_per_fixture=2,
    )

    assert selection.evaluation.total_stake <= 2.0
    solver_search = selection.explanation_json["solver_search"]
    assert isinstance(solver_search, dict)
    assert solver_search["strategy"] == "budget_constrained_integer_solver"
    assert solver_search["search_mode"] == "dynamic_programming_integer_search"
    assert solver_search["exact"] is False
    assert solver_search["solver_first_fast_path"] is True
    assert solver_search["candidate_fixture_count"] == 30
    assert solver_search["evaluated_complete_states"] > 0


def test_multiple_optimizer_prunes_dynamic_solver_for_budgeted_large_window() -> None:
    candidates: list[RecommendationCandidate] = []
    for index in range(18):
        candidates.extend(
            [
                _candidate(
                    f"W{index:02d}",
                    "home_win",
                    probability=0.59 - index * 0.002,
                    decimal_odds=1.78 + index * 0.01,
                ),
                _candidate(
                    f"W{index:02d}",
                    "draw",
                    probability=0.29 + index * 0.001,
                    decimal_odds=3.10 + index * 0.02,
                    upset_protection_score=0.48 + index * 0.01,
                ),
            ]
        )

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="8x1",
        unit_stake=2.0,
        max_budget=64.0,
        max_outcomes_per_fixture=2,
    )

    assert len(selection.fixture_ids) == 8
    assert selection.evaluation.total_stake <= 64.0
    solver_search = selection.explanation_json["solver_search"]
    assert isinstance(solver_search, dict)
    assert solver_search["search_mode"] == "dynamic_programming_integer_search"
    assert solver_search["exact"] is False
    assert solver_search["generated_state_count"] > solver_search["evaluated_complete_states"]
    assert solver_search["pruned_state_count"] > 0


def test_large_multiple_optimizer_keeps_heuristic_path_when_solver_does_not_improve() -> None:
    candidates = [
        _candidate(
            f"F{index:02d}",
            "home_win",
            probability=0.64 - index * 0.003,
            decimal_odds=1.55 + index * 0.01,
        )
        for index in range(18)
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=2.0,
        max_outcomes_per_fixture=2,
    )

    assert selection.mode == "multiple"
    assert selection.evaluation.total_stake == 2.0
    assert selection.explanation_json["selection_basis"] == ("v3_1_multiple_budget_optimizer")
    solver_search = selection.explanation_json["solver_search"]
    assert isinstance(solver_search, dict)
    assert solver_search["solver_first_fast_path"] is True
    assert solver_search["accepted"] is False
    assert selection.explanation_json["multiple_option_decisions"] == []


def test_multiple_optimizer_respects_disabled_solver_search() -> None:
    candidates = [
        _candidate(
            f"F{index:02d}",
            "home_win",
            probability=0.62 - index * 0.002,
            decimal_odds=1.80 + index * 0.01,
        )
        for index in range(30)
    ]

    selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type="4x1",
        unit_stake=2.0,
        max_budget=2.0,
        max_outcomes_per_fixture=2,
        enable_solver_search=False,
    )

    assert selection.evaluation.total_stake <= 2.0
    assert "solver_search" not in selection.explanation_json
    assert "beam_search" not in selection.explanation_json


def _candidate_pool() -> list[RecommendationCandidate]:
    return [
        _candidate("A", "home_win", probability=0.62, decimal_odds=1.70),
        _candidate("A", "draw", probability=0.26, decimal_odds=3.40),
        _candidate("A", "away_win", probability=0.12, decimal_odds=5.80),
        _candidate("B", "home_win", probability=0.60, decimal_odds=1.80),
        _candidate("B", "draw", probability=0.20, decimal_odds=3.80),
        _candidate("C", "away_win", probability=0.59, decimal_odds=1.80),
        _candidate("C", "draw", probability=0.19, decimal_odds=3.90),
    ]


def _candidate_pool_for_budget_pruning() -> list[RecommendationCandidate]:
    candidates = _candidate_pool()
    return [
        (
            _candidate(
                "B",
                "draw",
                probability=0.20,
                decimal_odds=3.80,
                upset_protection_score=0.90,
            )
            if candidate.fixture_id == "B" and candidate.outcome == "draw"
            else candidate
        )
        for candidate in candidates
    ]


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float,
    kickoff_time_utc: datetime | None = None,
    upset_protection_score: float | None = None,
    model_edge: float | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        model_edge=model_edge,
        data_quality_score=90.0,
        model_confidence_score=0.88,
        calibration_score=0.86,
        upset_protection_score=(
            upset_protection_score
            if upset_protection_score is not None
            else 0.20
            if outcome == "draw"
            else 0.0
        ),
        odds_stability_score=0.75,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=101,
        prediction_time_utc=datetime(2026, 5, 1, 12, tzinfo=UTC),
        kickoff_time_utc=kickoff_time_utc or datetime(2026, 5, 3, 20, tzinfo=UTC),
    )
