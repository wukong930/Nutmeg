from __future__ import annotations

from math import exp

from nutmeg.domain.modeling import DixonColesInput, GoalLambdaEstimate
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.modeling.poisson import poisson_pmf

MIN_SCORE_PROBABILITY = 1e-12


def dixon_coles_time_decay_weight(*, days_since_match: float, xi: float) -> float:
    if days_since_match < 0:
        raise ValueError("days_since_match must be non-negative")
    if xi < 0:
        raise ValueError("xi must be non-negative")
    return exp(-xi * days_since_match)


def dixon_coles_tau(
    *,
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if home_goals < 0 or away_goals < 0:
        raise ValueError("goals must be non-negative")
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("Dixon-Coles lambdas must be positive")
    if home_goals == 0 and away_goals == 0:
        return max(0.0, 1 - lambda_home * lambda_away * rho)
    if home_goals == 0 and away_goals == 1:
        return max(0.0, 1 + lambda_home * rho)
    if home_goals == 1 and away_goals == 0:
        return max(0.0, 1 + lambda_away * rho)
    if home_goals == 1 and away_goals == 1:
        return max(0.0, 1 - rho)
    return 1.0


def dixon_coles_score_probability(
    *,
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    base_probability = poisson_pmf(home_goals, lambda_home) * poisson_pmf(
        away_goals,
        lambda_away,
    )
    adjusted_probability = base_probability * dixon_coles_tau(
        home_goals=home_goals,
        away_goals=away_goals,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        rho=rho,
    )
    return max(MIN_SCORE_PROBABILITY, adjusted_probability)


def estimate_dixon_coles_lambdas(model_input: DixonColesInput) -> GoalLambdaEstimate:
    lambda_home = exp(
        model_input.mu
        + model_input.home_advantage
        + model_input.home_attack
        - model_input.away_defense
        + model_input.home_context_adjustment
    )
    lambda_away = exp(
        model_input.mu
        + model_input.away_attack
        - model_input.home_defense
        + model_input.away_context_adjustment
    )
    time_decay_weight = (
        dixon_coles_time_decay_weight(
            days_since_match=model_input.days_since_reference_match,
            xi=model_input.time_decay_xi,
        )
        if model_input.days_since_reference_match is not None
        else None
    )
    return GoalLambdaEstimate(
        fixture_id=model_input.fixture_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_family="dixon_coles",
        model_version=model_input.model_version,
        feature_version=model_input.feature_version,
        calibration_version=model_input.calibration_version,
        rho=model_input.rho,
        time_decay_weight=time_decay_weight,
        metadata_json={
            "input": model_input.model_dump(mode="json"),
            "dixon_coles_v15": {
                "low_score_adjustment": True,
                "time_decay_placeholder": True,
                "tau_safety": "non_negative_and_normalized",
                "training_status": "skeleton_not_fitted",
            },
            **model_input.metadata_json,
        },
    )


def build_dixon_coles_score_grid(
    *,
    fixture_id: str | None,
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int = 8,
    model_version: str = "dc-v1.5.0",
    calibration_version: str = "calibration-m1.0.0",
) -> ScoreProbabilityGrid:
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("Dixon-Coles lambdas must be positive")

    raw_grid: list[list[float]] = []
    base_bounded_mass = 0.0
    for home_goals in range(max_goals + 1):
        row: list[float] = []
        for away_goals in range(max_goals + 1):
            base_probability = poisson_pmf(home_goals, lambda_home) * poisson_pmf(
                away_goals,
                lambda_away,
            )
            base_bounded_mass += base_probability
            row.append(
                max(
                    0.0,
                    base_probability
                    * dixon_coles_tau(
                        home_goals=home_goals,
                        away_goals=away_goals,
                        lambda_home=lambda_home,
                        lambda_away=lambda_away,
                        rho=rho,
                    ),
                )
            )
        raw_grid.append(row)

    adjusted_bounded_mass = sum(sum(row) for row in raw_grid)
    if adjusted_bounded_mass <= 0:
        raise ValueError("Dixon-Coles grid probability mass must be positive")
    normalized_grid = [
        [value / adjusted_bounded_mass for value in row] for row in raw_grid
    ]
    return ScoreProbabilityGrid(
        fixture_id=fixture_id,
        max_goals=max_goals,
        grid=normalized_grid,
        tail_mass=max(0.0, 1.0 - base_bounded_mass),
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_version=model_version,
        calibration_version=calibration_version,
    )


def build_dixon_coles_score_grid_from_estimate(
    estimate: GoalLambdaEstimate,
    *,
    max_goals: int = 8,
) -> ScoreProbabilityGrid:
    if estimate.rho is None:
        raise ValueError("Dixon-Coles score grid requires an estimate rho")
    return build_dixon_coles_score_grid(
        fixture_id=estimate.fixture_id,
        lambda_home=estimate.lambda_home,
        lambda_away=estimate.lambda_away,
        rho=estimate.rho,
        max_goals=max_goals,
        model_version=estimate.model_version,
        calibration_version=estimate.calibration_version,
    )
