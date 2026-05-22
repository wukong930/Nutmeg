from __future__ import annotations

from math import exp, factorial

from nutmeg.domain.modeling import GoalLambdaEstimate, PoissonBaselineInput
from nutmeg.domain.score_grid import ScoreProbabilityGrid


def poisson_pmf(k: int, rate: float) -> float:
    if k < 0:
        raise ValueError("k must be non-negative")
    if rate <= 0:
        raise ValueError("rate must be positive")
    return exp(-rate) * rate**k / factorial(k)


def build_poisson_score_grid(
    *,
    fixture_id: str | None,
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 8,
    model_version: str = "poisson-m1.0.0",
    calibration_version: str = "calibration-m1.0.0",
) -> ScoreProbabilityGrid:
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("Poisson lambdas must be positive")

    raw_grid = [
        [poisson_pmf(home_goals, lambda_home) * poisson_pmf(away_goals, lambda_away)
         for away_goals in range(max_goals + 1)]
        for home_goals in range(max_goals + 1)
    ]
    bounded_mass = sum(sum(row) for row in raw_grid)
    if bounded_mass <= 0:
        raise ValueError("Poisson grid probability mass must be positive")
    normalized_grid = [[value / bounded_mass for value in row] for row in raw_grid]
    tail_mass = max(0.0, 1.0 - bounded_mass)
    return ScoreProbabilityGrid(
        fixture_id=fixture_id,
        max_goals=max_goals,
        grid=normalized_grid,
        tail_mass=tail_mass,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_version=model_version,
        calibration_version=calibration_version,
    )


def estimate_poisson_lambdas(model_input: PoissonBaselineInput) -> GoalLambdaEstimate:
    lambda_home = (
        model_input.league_avg_home_goals
        * model_input.home_attack_strength
        * model_input.away_defense_weakness
        * model_input.home_advantage_multiplier
    )
    lambda_away = (
        model_input.league_avg_away_goals
        * model_input.away_attack_strength
        * model_input.home_defense_weakness
    )
    return GoalLambdaEstimate(
        fixture_id=model_input.fixture_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_family="poisson",
        model_version=model_input.model_version,
        feature_version=model_input.feature_version,
        calibration_version=model_input.calibration_version,
        metadata_json={
            "input": model_input.model_dump(mode="json"),
            "dc_compatibility": {
                "rho": None,
                "time_decay_weight": None,
                "score_grid_contract": "lambda_home/lambda_away -> score_probability_grid",
            },
        },
    )


def build_poisson_score_grid_from_estimate(
    estimate: GoalLambdaEstimate,
    *,
    max_goals: int = 8,
) -> ScoreProbabilityGrid:
    return build_poisson_score_grid(
        fixture_id=estimate.fixture_id,
        lambda_home=estimate.lambda_home,
        lambda_away=estimate.lambda_away,
        max_goals=max_goals,
        model_version=estimate.model_version,
        calibration_version=estimate.calibration_version,
    )
