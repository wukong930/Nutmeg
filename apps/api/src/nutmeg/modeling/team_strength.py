from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from nutmeg.domain.modeling import GoalLambdaEstimate

DEFAULT_MIN_TEAM_MATCHES = 3
DEFAULT_HISTORICAL_RESULT_LIMIT = 200
MIN_LAMBDA = 0.2
MAX_LAMBDA = 3.5


class HistoricalFixtureResult(BaseModel):
    fixture_id: str
    competition_id: str
    season: str | None = None
    kickoff_time_utc: datetime
    home_team_id: str
    away_team_id: str
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)


class TeamStrengthRating(BaseModel):
    team_id: str
    matches: int = Field(ge=0)
    home_matches: int = Field(ge=0)
    away_matches: int = Field(ge=0)
    goals_for: int = Field(ge=0)
    goals_against: int = Field(ge=0)
    goals_for_per_match: float = Field(ge=0.0)
    goals_against_per_match: float = Field(ge=0.0)
    attack_strength: float = Field(gt=0.0)
    defense_weakness: float = Field(gt=0.0)


class CompetitionHistoricalStrengthSnapshot(BaseModel):
    competition_id: str
    as_of_time_utc: datetime
    match_count: int = Field(ge=0)
    team_count: int = Field(ge=0)
    min_team_matches: int = Field(ge=1)
    avg_home_goals: float = Field(ge=0.0)
    avg_away_goals: float = Field(ge=0.0)
    avg_goals_per_team_match: float = Field(gt=0.0)
    source_fixture_ids: list[str] = Field(default_factory=list)
    team_ratings: dict[str, TeamStrengthRating] = Field(default_factory=dict)


def build_competition_historical_strength_snapshot(
    results: Sequence[HistoricalFixtureResult],
    *,
    competition_id: str,
    as_of_time_utc: datetime,
    min_team_matches: int = DEFAULT_MIN_TEAM_MATCHES,
    max_results: int = DEFAULT_HISTORICAL_RESULT_LIMIT,
) -> CompetitionHistoricalStrengthSnapshot:
    normalized_as_of = _aware_utc(as_of_time_utc)
    eligible_results = [
        result
        for result in results
        if result.competition_id == competition_id
        and _aware_utc(result.kickoff_time_utc) < normalized_as_of
    ]
    eligible_results = sorted(
        eligible_results,
        key=lambda result: (result.kickoff_time_utc, result.fixture_id),
        reverse=True,
    )[: max(1, max_results)]

    match_count = len(eligible_results)
    if match_count == 0:
        return CompetitionHistoricalStrengthSnapshot(
            competition_id=competition_id,
            as_of_time_utc=normalized_as_of,
            match_count=0,
            team_count=0,
            min_team_matches=max(1, min_team_matches),
            avg_home_goals=0.0,
            avg_away_goals=0.0,
            avg_goals_per_team_match=1.0,
            source_fixture_ids=[],
            team_ratings={},
        )

    total_home_goals = sum(result.home_goals for result in eligible_results)
    total_away_goals = sum(result.away_goals for result in eligible_results)
    avg_home_goals = total_home_goals / match_count
    avg_away_goals = total_away_goals / match_count
    league_goals_per_team_match = max(
        0.1,
        (total_home_goals + total_away_goals) / (match_count * 2),
    )
    team_totals: dict[str, dict[str, int]] = {}

    for result in eligible_results:
        _add_team_result(
            team_totals,
            team_id=result.home_team_id,
            goals_for=result.home_goals,
            goals_against=result.away_goals,
            home_match=True,
        )
        _add_team_result(
            team_totals,
            team_id=result.away_team_id,
            goals_for=result.away_goals,
            goals_against=result.home_goals,
            home_match=False,
        )

    team_ratings = {
        team_id: _team_strength_rating(
            team_id=team_id,
            totals=totals,
            league_goals_per_team_match=league_goals_per_team_match,
        )
        for team_id, totals in team_totals.items()
    }

    return CompetitionHistoricalStrengthSnapshot(
        competition_id=competition_id,
        as_of_time_utc=normalized_as_of,
        match_count=match_count,
        team_count=len(team_ratings),
        min_team_matches=max(1, min_team_matches),
        avg_home_goals=avg_home_goals,
        avg_away_goals=avg_away_goals,
        avg_goals_per_team_match=league_goals_per_team_match,
        source_fixture_ids=[result.fixture_id for result in eligible_results],
        team_ratings=team_ratings,
    )


def estimate_goal_lambdas_from_team_strength(
    snapshot: CompetitionHistoricalStrengthSnapshot,
    *,
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    neutral_venue: bool = False,
    model_version: str = "poisson-m1.1.0",
    feature_version: str = "features-m1.2.0",
    calibration_version: str = "calibration-m1.0.0",
) -> GoalLambdaEstimate | None:
    home_rating = snapshot.team_ratings.get(home_team_id)
    away_rating = snapshot.team_ratings.get(away_team_id)
    if home_rating is None or away_rating is None:
        return None
    if (
        home_rating.matches < snapshot.min_team_matches
        or away_rating.matches < snapshot.min_team_matches
    ):
        return None

    lambda_home = (
        snapshot.avg_home_goals
        * home_rating.attack_strength
        * away_rating.defense_weakness
    )
    lambda_away = (
        snapshot.avg_away_goals
        * away_rating.attack_strength
        * home_rating.defense_weakness
    )
    if neutral_venue:
        total = lambda_home + lambda_away
        lambda_home = total * 0.52
        lambda_away = total * 0.48

    lambda_home = _clamp(lambda_home, MIN_LAMBDA, MAX_LAMBDA)
    lambda_away = _clamp(lambda_away, MIN_LAMBDA, MAX_LAMBDA)
    return GoalLambdaEstimate(
        fixture_id=fixture_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_family="poisson",
        model_version=model_version,
        feature_version=feature_version,
        calibration_version=calibration_version,
        metadata_json={
            "lambda_source": "historical_team_strength",
            "team_strength_method": "rolling_result_attack_defense_v1",
            "competition_id": snapshot.competition_id,
            "as_of_time_utc": snapshot.as_of_time_utc.isoformat(),
            "historical_match_count": snapshot.match_count,
            "historical_team_count": snapshot.team_count,
            "min_team_matches": snapshot.min_team_matches,
            "avg_home_goals": snapshot.avg_home_goals,
            "avg_away_goals": snapshot.avg_away_goals,
            "avg_goals_per_team_match": snapshot.avg_goals_per_team_match,
            "home_sample_matches": home_rating.matches,
            "away_sample_matches": away_rating.matches,
            "home_attack_strength": home_rating.attack_strength,
            "away_attack_strength": away_rating.attack_strength,
            "home_defense_weakness": home_rating.defense_weakness,
            "away_defense_weakness": away_rating.defense_weakness,
            "neutral_venue_adjusted": neutral_venue,
            "dixon_coles_v15_compatible": True,
        },
    )


def _add_team_result(
    team_totals: dict[str, dict[str, int]],
    *,
    team_id: str,
    goals_for: int,
    goals_against: int,
    home_match: bool,
) -> None:
    totals = team_totals.setdefault(
        team_id,
        {
            "matches": 0,
            "home_matches": 0,
            "away_matches": 0,
            "goals_for": 0,
            "goals_against": 0,
        },
    )
    totals["matches"] += 1
    totals["home_matches" if home_match else "away_matches"] += 1
    totals["goals_for"] += goals_for
    totals["goals_against"] += goals_against


def _team_strength_rating(
    *,
    team_id: str,
    totals: dict[str, int],
    league_goals_per_team_match: float,
) -> TeamStrengthRating:
    matches = max(1, totals["matches"])
    goals_for_per_match = totals["goals_for"] / matches
    goals_against_per_match = totals["goals_against"] / matches
    return TeamStrengthRating(
        team_id=team_id,
        matches=totals["matches"],
        home_matches=totals["home_matches"],
        away_matches=totals["away_matches"],
        goals_for=totals["goals_for"],
        goals_against=totals["goals_against"],
        goals_for_per_match=goals_for_per_match,
        goals_against_per_match=goals_against_per_match,
        attack_strength=_clamp(goals_for_per_match / league_goals_per_team_match, 0.45, 1.9),
        defense_weakness=_clamp(
            goals_against_per_match / league_goals_per_team_match,
            0.45,
            1.9,
        ),
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
