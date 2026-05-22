"""Modeling layer skeleton."""

from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.modeling.dixon_coles import (
    build_dixon_coles_score_grid,
    build_dixon_coles_score_grid_from_estimate,
    dixon_coles_score_probability,
    dixon_coles_tau,
    dixon_coles_time_decay_weight,
    estimate_dixon_coles_lambdas,
)
from nutmeg.modeling.dixon_coles_training import (
    DixonColesFittedParameters,
    DixonColesTeamParameter,
    DixonColesTrainingConfig,
    DixonColesTrainingMatch,
    DixonColesTrainingReport,
    build_dixon_coles_training_report,
    estimate_dixon_coles_lambdas_for_match,
    fit_dixon_coles_attack_defense_parameters,
    negative_weighted_log_likelihood,
)
from nutmeg.modeling.poisson import (
    build_poisson_score_grid,
    build_poisson_score_grid_from_estimate,
    estimate_poisson_lambdas,
)
from nutmeg.modeling.score_grid_analysis import (
    score_grid_tail_metrics,
    top_score_probabilities,
)
from nutmeg.modeling.team_strength import (
    CompetitionHistoricalStrengthSnapshot,
    HistoricalFixtureResult,
    TeamStrengthRating,
    build_competition_historical_strength_snapshot,
    estimate_goal_lambdas_from_team_strength,
)


def build_score_grid_from_estimate(
    estimate: GoalLambdaEstimate,
    *,
    max_goals: int = 8,
) -> ScoreProbabilityGrid:
    if estimate.rho is not None:
        return build_dixon_coles_score_grid_from_estimate(estimate, max_goals=max_goals)
    return build_poisson_score_grid_from_estimate(estimate, max_goals=max_goals)


__all__ = [
    "CompetitionHistoricalStrengthSnapshot",
    "DixonColesFittedParameters",
    "DixonColesTeamParameter",
    "DixonColesTrainingConfig",
    "DixonColesTrainingMatch",
    "DixonColesTrainingReport",
    "HistoricalFixtureResult",
    "TeamStrengthRating",
    "build_dixon_coles_score_grid",
    "build_dixon_coles_score_grid_from_estimate",
    "build_dixon_coles_training_report",
    "build_poisson_score_grid",
    "build_poisson_score_grid_from_estimate",
    "build_score_grid_from_estimate",
    "build_competition_historical_strength_snapshot",
    "dixon_coles_score_probability",
    "dixon_coles_tau",
    "dixon_coles_time_decay_weight",
    "estimate_dixon_coles_lambdas_for_match",
    "estimate_dixon_coles_lambdas",
    "estimate_poisson_lambdas",
    "estimate_goal_lambdas_from_team_strength",
    "fit_dixon_coles_attack_defense_parameters",
    "negative_weighted_log_likelihood",
    "score_grid_tail_metrics",
    "top_score_probabilities",
]
