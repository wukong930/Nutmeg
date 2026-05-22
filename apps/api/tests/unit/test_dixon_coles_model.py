from __future__ import annotations

from math import exp, isclose

from nutmeg.domain.modeling import DixonColesInput, GoalLambdaEstimate
from nutmeg.modeling import (
    build_dixon_coles_score_grid,
    build_dixon_coles_score_grid_from_estimate,
    build_poisson_score_grid,
    build_score_grid_from_estimate,
    dixon_coles_tau,
    dixon_coles_time_decay_weight,
    estimate_dixon_coles_lambdas,
)


def test_dixon_coles_tau_applies_only_low_score_adjustments_safely() -> None:
    assert isclose(
        dixon_coles_tau(
            home_goals=0,
            away_goals=0,
            lambda_home=1.4,
            lambda_away=1.1,
            rho=0.05,
        ),
        1 - 1.4 * 1.1 * 0.05,
    )
    assert isclose(
        dixon_coles_tau(
            home_goals=0,
            away_goals=1,
            lambda_home=1.4,
            lambda_away=1.1,
            rho=0.05,
        ),
        1 + 1.4 * 0.05,
    )
    assert dixon_coles_tau(
        home_goals=2,
        away_goals=2,
        lambda_home=1.4,
        lambda_away=1.1,
        rho=0.05,
    ) == 1.0
    assert (
        dixon_coles_tau(
            home_goals=0,
            away_goals=0,
            lambda_home=4.0,
            lambda_away=4.0,
            rho=0.5,
        )
        == 0.0
    )


def test_dixon_coles_time_decay_uses_documented_exponential_placeholder() -> None:
    assert isclose(
        dixon_coles_time_decay_weight(days_since_match=14, xi=0.01),
        exp(-0.14),
    )


def test_estimate_dixon_coles_lambdas_uses_log_linear_contract() -> None:
    model_input = DixonColesInput(
        fixture_id="dc_fixture",
        mu=0.1,
        home_attack=0.2,
        away_attack=-0.1,
        home_defense=0.05,
        away_defense=-0.08,
        home_advantage=0.12,
        home_context_adjustment=0.03,
        away_context_adjustment=-0.02,
        rho=-0.04,
        days_since_reference_match=21,
        time_decay_xi=0.015,
    )

    estimate = estimate_dixon_coles_lambdas(model_input)

    assert estimate.model_family == "dixon_coles"
    assert estimate.model_version == "dc-v1.5.0"
    assert estimate.rho == -0.04
    assert isclose(estimate.time_decay_weight or 0.0, exp(-0.315))
    assert isclose(estimate.lambda_home, exp(0.1 + 0.12 + 0.2 - (-0.08) + 0.03))
    assert isclose(estimate.lambda_away, exp(0.1 - 0.1 - 0.05 - 0.02))
    assert estimate.metadata_json["dixon_coles_v15"]["training_status"] == (
        "skeleton_not_fitted"
    )


def test_dixon_coles_score_grid_is_non_negative_normalized_and_adjusts_low_scores() -> None:
    poisson_grid = build_poisson_score_grid(
        fixture_id="dc_fixture",
        lambda_home=1.4,
        lambda_away=1.1,
        max_goals=8,
    )
    dc_grid = build_dixon_coles_score_grid(
        fixture_id="dc_fixture",
        lambda_home=1.4,
        lambda_away=1.1,
        rho=-0.08,
        max_goals=8,
    )

    assert dc_grid.is_normalized(tolerance=1e-12)
    assert all(probability >= 0 for row in dc_grid.grid for probability in row)
    assert dc_grid.probability_for(0, 0) > poisson_grid.probability_for(0, 0)
    assert dc_grid.probability_for(1, 1) > poisson_grid.probability_for(1, 1)
    assert dc_grid.tail_mass >= 0.0


def test_score_grid_dispatch_uses_dixon_coles_when_rho_is_present() -> None:
    estimate = GoalLambdaEstimate(
        fixture_id="dc_fixture",
        lambda_home=1.4,
        lambda_away=1.1,
        model_family="dixon_coles",
        model_version="dc-v1.5.0",
        feature_version="features-m1.2.0",
        calibration_version="calibration-m1.0.0",
        rho=-0.05,
    )

    direct_grid = build_dixon_coles_score_grid_from_estimate(estimate)
    dispatched_grid = build_score_grid_from_estimate(estimate)

    assert dispatched_grid.grid == direct_grid.grid
    assert dispatched_grid.model_version == "dc-v1.5.0"
