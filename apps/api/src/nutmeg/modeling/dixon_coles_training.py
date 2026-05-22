from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from math import isfinite, log

from pydantic import BaseModel, Field, model_validator

from nutmeg.domain.modeling import DixonColesInput, GoalLambdaEstimate
from nutmeg.modeling.dixon_coles import (
    build_dixon_coles_score_grid_from_estimate,
    dixon_coles_score_probability,
    dixon_coles_time_decay_weight,
    estimate_dixon_coles_lambdas,
)


class DixonColesTrainingMatch(BaseModel):
    fixture_id: str
    competition_id: str
    kickoff_time_utc: datetime
    home_team_id: str
    away_team_id: str
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)


class DixonColesTrainingConfig(BaseModel):
    as_of_time_utc: datetime
    model_version: str = "dc-v1.5-candidate"
    feature_version: str = "features-m1.2.0"
    calibration_version: str = "calibration-m1.0.0"
    train_window_days: int = Field(default=365, ge=1)
    validation_window_days: int = Field(default=90, ge=1)
    time_decay_xi: float = Field(default=0.0065, ge=0.0)
    rho_candidates: tuple[float, ...] = (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10)
    max_goals: int = Field(default=8, ge=1, le=20)
    min_training_matches: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def validate_candidates_and_windows(self) -> DixonColesTrainingConfig:
        if not self.rho_candidates:
            raise ValueError("rho_candidates must not be empty")
        if any(rho < -0.5 or rho > 0.5 for rho in self.rho_candidates):
            raise ValueError("rho_candidates must be between -0.5 and 0.5")
        if self.train_window_days <= self.validation_window_days:
            raise ValueError("train_window_days must exceed validation_window_days")
        return self


class DixonColesTeamParameter(BaseModel):
    team_id: str
    match_count: int = Field(ge=0)
    weighted_match_sum: float = Field(ge=0.0)
    attack: float
    defense: float
    attack_strength: float = Field(gt=0.0)
    defense_weakness: float = Field(gt=0.0)


class DixonColesFittedParameters(BaseModel):
    mu: float
    home_advantage: float
    avg_home_goals: float = Field(gt=0.0)
    avg_away_goals: float = Field(gt=0.0)
    league_goals_per_team_match: float = Field(gt=0.0)
    selected_rho: float
    team_parameters: dict[str, DixonColesTeamParameter]


class DixonColesTrainingReport(BaseModel):
    model_version: str
    as_of_time_utc: datetime
    train_start_utc: datetime
    validation_start_utc: datetime
    validation_end_utc: datetime
    competition_ids: list[str]
    train_sample_size: int = Field(ge=0)
    validation_sample_size: int = Field(ge=0)
    selected_rho: float
    time_decay_xi: float = Field(ge=0.0)
    train_negative_weighted_log_likelihood: float = Field(ge=0.0)
    validation_negative_weighted_log_likelihood: float = Field(ge=0.0)
    rho_search: dict[str, float]
    fitted_parameters: DixonColesFittedParameters
    score_grid_regression_passed: bool
    warnings: list[str] = Field(default_factory=list)

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "model_family": "dixon_coles",
            "model_version": self.model_version,
            "train_sample_size": self.train_sample_size,
            "validation_sample_size": self.validation_sample_size,
            "selected_rho": self.selected_rho,
            "time_decay_xi": self.time_decay_xi,
            "train_negative_weighted_log_likelihood": (
                self.train_negative_weighted_log_likelihood
            ),
            "validation_negative_weighted_log_likelihood": (
                self.validation_negative_weighted_log_likelihood
            ),
            "score_grid_regression_passed": self.score_grid_regression_passed,
            "rho_search": self.rho_search,
            "warnings": self.warnings,
        }


def build_dixon_coles_training_report(
    matches: Sequence[DixonColesTrainingMatch],
    *,
    config: DixonColesTrainingConfig,
) -> DixonColesTrainingReport:
    normalized_as_of = _aware_utc(config.as_of_time_utc)
    train_start = normalized_as_of - timedelta(days=config.train_window_days)
    validation_start = normalized_as_of - timedelta(days=config.validation_window_days)
    eligible_matches = [
        match
        for match in matches
        if train_start <= _aware_utc(match.kickoff_time_utc) < normalized_as_of
    ]
    train_matches = [
        match
        for match in eligible_matches
        if _aware_utc(match.kickoff_time_utc) < validation_start
    ]
    validation_matches = [
        match
        for match in eligible_matches
        if _aware_utc(match.kickoff_time_utc) >= validation_start
    ]
    if len(train_matches) < config.min_training_matches:
        raise ValueError("not enough training matches for Dixon-Coles fitting")
    if not validation_matches:
        raise ValueError("validation window has no matches")

    base_parameters = fit_dixon_coles_attack_defense_parameters(
        train_matches,
        config=config,
    )
    rho_search = {
        _rho_key(rho): negative_weighted_log_likelihood(
            train_matches,
            parameters=base_parameters,
            rho=rho,
            as_of_time_utc=normalized_as_of,
            time_decay_xi=config.time_decay_xi,
        )
        for rho in config.rho_candidates
    }
    selected_rho = min(config.rho_candidates, key=lambda rho: rho_search[_rho_key(rho)])
    fitted_parameters = base_parameters.model_copy(update={"selected_rho": selected_rho})
    validation_nwll = negative_weighted_log_likelihood(
        validation_matches,
        parameters=fitted_parameters,
        rho=selected_rho,
        as_of_time_utc=normalized_as_of,
        time_decay_xi=config.time_decay_xi,
    )
    warnings = []
    if len(validation_matches) < config.min_training_matches:
        warnings.append("validation_sample_size_below_training_minimum")

    return DixonColesTrainingReport(
        model_version=config.model_version,
        as_of_time_utc=normalized_as_of,
        train_start_utc=train_start,
        validation_start_utc=validation_start,
        validation_end_utc=normalized_as_of,
        competition_ids=sorted({match.competition_id for match in eligible_matches}),
        train_sample_size=len(train_matches),
        validation_sample_size=len(validation_matches),
        selected_rho=selected_rho,
        time_decay_xi=config.time_decay_xi,
        train_negative_weighted_log_likelihood=rho_search[_rho_key(selected_rho)],
        validation_negative_weighted_log_likelihood=validation_nwll,
        rho_search=rho_search,
        fitted_parameters=fitted_parameters,
        score_grid_regression_passed=_score_grid_regression_passed(
            validation_matches[0],
            parameters=fitted_parameters,
            config=config,
        ),
        warnings=warnings,
    )


def fit_dixon_coles_attack_defense_parameters(
    matches: Sequence[DixonColesTrainingMatch],
    *,
    config: DixonColesTrainingConfig,
) -> DixonColesFittedParameters:
    if not matches:
        raise ValueError("at least one match is required")
    normalized_as_of = _aware_utc(config.as_of_time_utc)
    weighted_home_goals = 0.0
    weighted_away_goals = 0.0
    weighted_match_sum = 0.0
    team_totals: dict[str, dict[str, float]] = {}

    for match in matches:
        weight = _match_weight(match, as_of_time_utc=normalized_as_of, xi=config.time_decay_xi)
        weighted_match_sum += weight
        weighted_home_goals += match.home_goals * weight
        weighted_away_goals += match.away_goals * weight
        _add_team_total(
            team_totals,
            team_id=match.home_team_id,
            goals_for=match.home_goals,
            goals_against=match.away_goals,
            weight=weight,
        )
        _add_team_total(
            team_totals,
            team_id=match.away_team_id,
            goals_for=match.away_goals,
            goals_against=match.home_goals,
            weight=weight,
        )

    if weighted_match_sum <= 0:
        raise ValueError("weighted match sum must be positive")
    avg_home_goals = max(0.05, weighted_home_goals / weighted_match_sum)
    avg_away_goals = max(0.05, weighted_away_goals / weighted_match_sum)
    league_goals_per_team_match = max(
        0.05,
        (weighted_home_goals + weighted_away_goals) / (weighted_match_sum * 2),
    )
    return DixonColesFittedParameters(
        mu=log(avg_away_goals),
        home_advantage=log(avg_home_goals / avg_away_goals),
        avg_home_goals=avg_home_goals,
        avg_away_goals=avg_away_goals,
        league_goals_per_team_match=league_goals_per_team_match,
        selected_rho=0.0,
        team_parameters={
            team_id: _team_parameter(
                team_id=team_id,
                totals=totals,
                league_goals_per_team_match=league_goals_per_team_match,
            )
            for team_id, totals in team_totals.items()
        },
    )


def negative_weighted_log_likelihood(
    matches: Sequence[DixonColesTrainingMatch],
    *,
    parameters: DixonColesFittedParameters,
    rho: float,
    as_of_time_utc: datetime,
    time_decay_xi: float,
) -> float:
    if not matches:
        raise ValueError("at least one match is required")
    normalized_as_of = _aware_utc(as_of_time_utc)
    weighted_loss = 0.0
    total_weight = 0.0
    for match in matches:
        estimate = estimate_dixon_coles_lambdas_for_match(
            match,
            parameters=parameters,
            rho=rho,
            as_of_time_utc=normalized_as_of,
            time_decay_xi=time_decay_xi,
            model_version="dc-v1.5-training",
            feature_version="features-training",
            calibration_version="calibration-training",
        )
        probability = dixon_coles_score_probability(
            home_goals=match.home_goals,
            away_goals=match.away_goals,
            lambda_home=estimate.lambda_home,
            lambda_away=estimate.lambda_away,
            rho=rho,
        )
        weight = _match_weight(match, as_of_time_utc=normalized_as_of, xi=time_decay_xi)
        weighted_loss += -log(probability) * weight
        total_weight += weight
    if total_weight <= 0:
        raise ValueError("total match weight must be positive")
    result = weighted_loss / total_weight
    if not isfinite(result):
        raise ValueError("negative weighted log likelihood must be finite")
    return result


def estimate_dixon_coles_lambdas_for_match(
    match: DixonColesTrainingMatch,
    *,
    parameters: DixonColesFittedParameters,
    rho: float,
    as_of_time_utc: datetime,
    time_decay_xi: float,
    model_version: str,
    feature_version: str,
    calibration_version: str,
) -> GoalLambdaEstimate:
    home_parameter = parameters.team_parameters.get(match.home_team_id)
    away_parameter = parameters.team_parameters.get(match.away_team_id)
    if home_parameter is None or away_parameter is None:
        raise ValueError("team parameters are missing for match")
    days_since_match = _days_between(_aware_utc(match.kickoff_time_utc), as_of_time_utc)
    return estimate_dixon_coles_lambdas(
        DixonColesInput(
            fixture_id=match.fixture_id,
            mu=parameters.mu,
            home_attack=home_parameter.attack,
            away_attack=away_parameter.attack,
            home_defense=home_parameter.defense,
            away_defense=away_parameter.defense,
            home_advantage=parameters.home_advantage,
            rho=rho,
            days_since_reference_match=days_since_match,
            time_decay_xi=time_decay_xi,
            model_version=model_version,
            feature_version=feature_version,
            calibration_version=calibration_version,
            metadata_json={
                "training_method": "weighted_attack_defense_grid_search_v1",
                "selected_rho": rho,
            },
        )
    )


def _score_grid_regression_passed(
    match: DixonColesTrainingMatch,
    *,
    parameters: DixonColesFittedParameters,
    config: DixonColesTrainingConfig,
) -> bool:
    estimate = estimate_dixon_coles_lambdas_for_match(
        match,
        parameters=parameters,
        rho=parameters.selected_rho,
        as_of_time_utc=_aware_utc(config.as_of_time_utc),
        time_decay_xi=config.time_decay_xi,
        model_version=config.model_version,
        feature_version=config.feature_version,
        calibration_version=config.calibration_version,
    )
    grid = build_dixon_coles_score_grid_from_estimate(estimate, max_goals=config.max_goals)
    return grid.is_normalized(tolerance=1e-9) and all(
        probability >= 0 for row in grid.grid for probability in row
    )


def _add_team_total(
    team_totals: dict[str, dict[str, float]],
    *,
    team_id: str,
    goals_for: int,
    goals_against: int,
    weight: float,
) -> None:
    totals = team_totals.setdefault(
        team_id,
        {
            "match_count": 0.0,
            "weighted_match_sum": 0.0,
            "weighted_goals_for": 0.0,
            "weighted_goals_against": 0.0,
        },
    )
    totals["match_count"] += 1.0
    totals["weighted_match_sum"] += weight
    totals["weighted_goals_for"] += goals_for * weight
    totals["weighted_goals_against"] += goals_against * weight


def _team_parameter(
    *,
    team_id: str,
    totals: dict[str, float],
    league_goals_per_team_match: float,
) -> DixonColesTeamParameter:
    weighted_match_sum = max(1e-9, totals["weighted_match_sum"])
    goals_for_per_match = totals["weighted_goals_for"] / weighted_match_sum
    goals_against_per_match = totals["weighted_goals_against"] / weighted_match_sum
    attack_strength = _clamp(
        goals_for_per_match / league_goals_per_team_match,
        0.45,
        1.9,
    )
    defense_weakness = _clamp(
        goals_against_per_match / league_goals_per_team_match,
        0.45,
        1.9,
    )
    return DixonColesTeamParameter(
        team_id=team_id,
        match_count=int(totals["match_count"]),
        weighted_match_sum=totals["weighted_match_sum"],
        attack=log(attack_strength),
        defense=-log(defense_weakness),
        attack_strength=attack_strength,
        defense_weakness=defense_weakness,
    )


def _match_weight(
    match: DixonColesTrainingMatch,
    *,
    as_of_time_utc: datetime,
    xi: float,
) -> float:
    days_since_match = _days_between(_aware_utc(match.kickoff_time_utc), as_of_time_utc)
    return dixon_coles_time_decay_weight(days_since_match=days_since_match, xi=xi)


def _days_between(start: datetime, end: datetime) -> float:
    normalized_start = _aware_utc(start)
    normalized_end = _aware_utc(end)
    return max(0.0, (normalized_end - normalized_start).total_seconds() / 86400)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _rho_key(rho: float) -> str:
    return f"{rho:.3f}"
