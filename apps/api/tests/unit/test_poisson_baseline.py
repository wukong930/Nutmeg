from __future__ import annotations

from math import isclose

import pytest

from nutmeg.domain.modeling import PoissonBaselineInput
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver import score_grid_to_market_probabilities
from nutmeg.modeling import (
    build_poisson_score_grid_from_estimate,
    estimate_poisson_lambdas,
    score_grid_tail_metrics,
    top_score_probabilities,
)
from nutmeg.modeling.poisson import poisson_pmf


@pytest.fixture
def deterministic_poisson_input() -> PoissonBaselineInput:
    return PoissonBaselineInput(
        fixture_id="deterministic_fixture",
        home_attack_strength=1.10,
        away_attack_strength=0.95,
        home_defense_weakness=0.90,
        away_defense_weakness=1.05,
        league_avg_home_goals=1.35,
        league_avg_away_goals=1.10,
        home_advantage_multiplier=1.08,
    )


def test_estimate_poisson_lambdas_is_deterministic(
    deterministic_poisson_input: PoissonBaselineInput,
) -> None:
    estimate = estimate_poisson_lambdas(deterministic_poisson_input)

    assert estimate.fixture_id == "deterministic_fixture"
    assert estimate.model_family == "poisson"
    assert estimate.rho is None
    assert estimate.time_decay_weight is None
    assert isclose(estimate.lambda_home, 1.35 * 1.10 * 1.05 * 1.08)
    assert isclose(estimate.lambda_away, 1.10 * 0.95 * 0.90)


def test_poisson_score_grid_generates_normalized_grid_and_tail_mass(
    deterministic_poisson_input: PoissonBaselineInput,
) -> None:
    estimate = estimate_poisson_lambdas(deterministic_poisson_input)
    score_grid = build_poisson_score_grid_from_estimate(estimate, max_goals=2)

    bounded_mass = sum(
        poisson_pmf(home_goals, estimate.lambda_home)
        * poisson_pmf(away_goals, estimate.lambda_away)
        for home_goals in range(3)
        for away_goals in range(3)
    )

    assert score_grid.fixture_id == estimate.fixture_id
    assert score_grid.max_goals == 2
    assert score_grid.is_normalized(tolerance=1e-12)
    assert isclose(score_grid.tail_mass, 1.0 - bounded_mass)
    assert score_grid.model_version == estimate.model_version
    assert score_grid.calibration_version == estimate.calibration_version


def test_top_score_probabilities_extracts_highest_probability_scores(
    deterministic_poisson_input: PoissonBaselineInput,
) -> None:
    estimate = estimate_poisson_lambdas(deterministic_poisson_input)
    score_grid = build_poisson_score_grid_from_estimate(estimate, max_goals=8)
    top_scores = top_score_probabilities(score_grid, top_n=3)

    assert len(top_scores) == 3
    assert top_scores[0].probability >= top_scores[1].probability >= top_scores[2].probability
    assert (top_scores[0].home_goals, top_scores[0].away_goals) == (1, 0)


def test_tail_metrics_extracts_blowout_and_high_score_signals() -> None:
    score_grid = ScoreProbabilityGrid(
        max_goals=4,
        tail_mass=0.03,
        grid=[
            [0.0, 0.0, 0.0, 0.0, 0.10],
            [0.0, 0.40, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.30, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.20, 0.0, 0.0, 0.0, 0.0],
        ],
    )

    metrics = score_grid_tail_metrics(score_grid)

    assert metrics.truncated_tail_mass == 0.03
    assert metrics.home_win_by_3plus == 0.20
    assert metrics.away_win_by_3plus == 0.10
    assert isclose(metrics.any_team_4plus_goals, 0.30)
    assert metrics.total_goals_5plus == 0.30
    assert metrics.blowout_tail_risk == "high"


def test_market_probabilities_are_derived_from_poisson_score_grid(
    deterministic_poisson_input: PoissonBaselineInput,
) -> None:
    estimate = estimate_poisson_lambdas(deterministic_poisson_input)
    score_grid = build_poisson_score_grid_from_estimate(estimate, max_goals=8)
    payload = score_grid_to_market_probabilities(
        score_grid,
        cn_handicaps=(-1,),
        asian_handicap_lines=(-0.25,),
        european_handicaps=(-1,),
        correct_score_top_n=5,
    )

    one_x_two = payload["1x2"]
    assert isinstance(one_x_two, dict)
    assert isclose(sum(one_x_two.values()), 1.0)
    assert "cn_handicap_1x2:-1" in payload
    assert "asian_handicap:home:-0.25" in payload
    assert "european_handicap_1x2:-1" in payload
    assert "correct_score_top_n" in payload
