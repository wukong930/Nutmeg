from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

FootballDataOrgMatchStatus = Literal[
    "SCHEDULED",
    "TIMED",
    "IN_PLAY",
    "PAUSED",
    "FINISHED",
    "POSTPONED",
    "SUSPENDED",
    "CANCELLED",
    "AWARDED",
]


class NormalizedCompetition(BaseModel):
    provider: str = "football-data.org"
    provider_entity_id: str
    canonical_hint: str
    name: str
    competition_type: str | None = None
    country: str | None = None


class NormalizedTeam(BaseModel):
    provider: str = "football-data.org"
    provider_entity_id: str
    canonical_hint: str
    name: str
    short_name: str | None = None
    tla: str | None = None


class NormalizedFixture(BaseModel):
    provider: str = "football-data.org"
    provider_entity_id: str
    competition_provider_id: str
    competition_code: str | None = None
    competition_name: str | None = None
    season_provider_id: str | None = None
    season_start_date: date | None = None
    season_end_date: date | None = None
    kickoff_time_utc: datetime
    status: str
    matchday: int | None = None
    stage: str | None = None
    group: str | None = None
    venue: str | None = None
    home_team: NormalizedTeam
    away_team: NormalizedTeam
    result: NormalizedResult | None = None
    raw_status: FootballDataOrgMatchStatus | str


class NormalizedResult(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    result_1x2: Literal["home_win", "draw", "away_win"]


def normalize_competition(payload: dict[str, object]) -> NormalizedCompetition:
    area = _dict(payload.get("area"))
    provider_entity_id = _required_text(payload.get("id"), "competition.id")
    code = _optional_text(payload.get("code"))
    name = _required_text(payload.get("name"), "competition.name")
    return NormalizedCompetition(
        provider_entity_id=provider_entity_id,
        canonical_hint=code or provider_entity_id,
        name=name,
        competition_type=_optional_text(payload.get("type")),
        country=_optional_text(area.get("name")),
    )


def normalize_team(payload: dict[str, object]) -> NormalizedTeam:
    provider_entity_id = _required_text(payload.get("id"), "team.id")
    name = _required_text(payload.get("name"), "team.name")
    return NormalizedTeam(
        provider_entity_id=provider_entity_id,
        canonical_hint=_optional_text(payload.get("tla")) or provider_entity_id,
        name=name,
        short_name=_optional_text(payload.get("shortName")),
        tla=_optional_text(payload.get("tla")),
    )


def normalize_match(payload: dict[str, object]) -> NormalizedFixture:
    competition = _dict(payload.get("competition"))
    season = _dict(payload.get("season"))
    home_team = _dict(payload.get("homeTeam"))
    away_team = _dict(payload.get("awayTeam"))
    raw_status = _required_text(payload.get("status"), "match.status")

    return NormalizedFixture(
        provider_entity_id=_required_text(payload.get("id"), "match.id"),
        competition_provider_id=_required_text(competition.get("id"), "match.competition.id"),
        competition_code=_optional_text(competition.get("code")),
        competition_name=_optional_text(competition.get("name")),
        season_provider_id=_optional_text(season.get("id")),
        season_start_date=_optional_date(season.get("startDate")),
        season_end_date=_optional_date(season.get("endDate")),
        kickoff_time_utc=_datetime(payload.get("utcDate")),
        status=_fixture_status(raw_status),
        matchday=_optional_int(payload.get("matchday")),
        stage=_optional_text(payload.get("stage")),
        group=_optional_text(payload.get("group")),
        venue=_optional_text(payload.get("venue")),
        home_team=normalize_team(home_team),
        away_team=normalize_team(away_team),
        result=_result_from_match(payload),
        raw_status=raw_status,
    )


def _result_from_match(payload: dict[str, object]) -> NormalizedResult | None:
    if payload.get("status") != "FINISHED":
        return None
    score = _dict(payload.get("score"))
    full_time = _dict(score.get("fullTime"))
    home_goals = full_time.get("home")
    away_goals = full_time.get("away")
    if not isinstance(home_goals, int) or not isinstance(away_goals, int):
        return None
    if home_goals > away_goals:
        result_1x2: Literal["home_win", "draw", "away_win"] = "home_win"
    elif home_goals == away_goals:
        result_1x2 = "draw"
    else:
        result_1x2 = "away_win"
    return NormalizedResult(
        home_goals=home_goals,
        away_goals=away_goals,
        result_1x2=result_1x2,
    )


def _fixture_status(status: str) -> str:
    if status in {"SCHEDULED", "TIMED"}:
        return "scheduled"
    if status in {"IN_PLAY", "PAUSED"}:
        return "live"
    if status in {"POSTPONED", "SUSPENDED", "CANCELLED"}:
        return "postponed"
    if status in {"FINISHED", "AWARDED"}:
        return "finished"
    return "unknown"


def _dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"missing required football-data.org field: {field_name}")
    return str(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise ValueError(f"expected integer-like value, got {type(value).__name__}")


def _datetime(value: object) -> datetime:
    text = _required_text(value, "match.utcDate")
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value))
