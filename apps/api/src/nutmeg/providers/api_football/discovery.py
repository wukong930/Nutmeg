from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher
from re import sub
from typing import Protocol
from unicodedata import normalize

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.providers.api_football.adapter import (
    ApiFootballAdapter,
    ApiFootballConfig,
    ApiFootballPlanLimitError,
)


class ApiFootballDiscoveryAdapter(Protocol):
    def fetch_leagues(
        self,
        *,
        country: str | None = None,
        season: str | None = None,
        search: str | None = None,
        current: bool | None = None,
    ) -> list[dict[str, object]]: ...


class ApiFootballSeasonDiscoveryCandidate(BaseModel):
    provider_season_id: str
    year: int = Field(ge=1800)
    score: float = Field(ge=0.0, le=1.0)
    current: bool | None = None
    start: str | None = None
    end: str | None = None
    coverage: dict[str, object] = Field(default_factory=dict)


class ApiFootballCompetitionDiscoveryCandidate(BaseModel):
    provider_competition_id: str
    name: str
    country_name: str | None = None
    competition_type: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    seasons: list[ApiFootballSeasonDiscoveryCandidate] = Field(default_factory=list)
    recommended_season: ApiFootballSeasonDiscoveryCandidate | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ApiFootballCompetitionDiscoveryResult(BaseModel):
    provider_name: str = "api-football"
    target_competition_name: str
    target_country_name: str | None = None
    target_season: str
    min_competition_score: float = Field(ge=0.0, le=1.0)
    checked_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    recommended_competition: ApiFootballCompetitionDiscoveryCandidate | None = None
    recommended_season: ApiFootballSeasonDiscoveryCandidate | None = None
    candidates: list[ApiFootballCompetitionDiscoveryCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime


def discover_api_football_competition_season(
    settings: Settings,
    *,
    target_competition_name: str = "Premier League",
    target_country_name: str | None = "England",
    target_season: str = "2025",
    max_competition_candidates: int = 5,
    max_season_candidates: int = 6,
    min_competition_score: float = 0.75,
    adapter: ApiFootballDiscoveryAdapter | None = None,
) -> ApiFootballCompetitionDiscoveryResult:
    warnings: list[str] = []
    api_adapter = adapter or ApiFootballAdapter(
        ApiFootballConfig(
            api_key=(
                SecretStr(settings.api_football_api_key)
                if settings.api_football_api_key
                else None
            ),
            base_url=settings.api_football_api_base_url,
            timeout_seconds=settings.api_football_api_timeout_seconds,
        )
    )
    try:
        raw_leagues = api_adapter.fetch_leagues(
            search=target_competition_name,
        )
        if not raw_leagues and target_country_name:
            warnings.append("api_football_search_returned_no_leagues")
            raw_leagues = api_adapter.fetch_leagues(
                country=target_country_name,
            )
    except ApiFootballPlanLimitError:
        warnings.append("api_football_plan_limited_for_target_season")
        return ApiFootballCompetitionDiscoveryResult(
            target_competition_name=target_competition_name,
            target_country_name=target_country_name,
            target_season=target_season,
            min_competition_score=min_competition_score,
            checked_competition_count=0,
            candidate_count=0,
            recommended_competition=None,
            recommended_season=None,
            candidates=[],
            warnings=warnings,
            generated_at_utc=datetime.now(UTC),
        )

    parsed_candidates: list[ApiFootballCompetitionDiscoveryCandidate] = []
    for raw_league in raw_leagues:
        try:
            parsed_candidates.append(
                _competition_candidate(
                    raw_league,
                    target_competition_name=target_competition_name,
                    target_country_name=target_country_name,
                    target_season=target_season,
                    max_season_candidates=max_season_candidates,
                )
            )
        except ValueError:
            warnings.append("api_football_competition_candidate_parse_skipped")

    candidates = sorted(
        parsed_candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )[:max_competition_candidates]
    recommended_competition = _recommended_competition(
        candidates,
        min_competition_score=min_competition_score,
    )
    recommended_season = (
        recommended_competition.recommended_season
        if recommended_competition is not None
        else None
    )
    if not candidates:
        warnings.append("no_api_football_competition_candidates")
    elif recommended_competition is None:
        warnings.append("no_api_football_competition_above_confidence_threshold")
    if recommended_competition is not None and recommended_season is None:
        warnings.append("no_api_football_season_candidate_for_recommendation")

    return ApiFootballCompetitionDiscoveryResult(
        target_competition_name=target_competition_name,
        target_country_name=target_country_name,
        target_season=target_season,
        min_competition_score=min_competition_score,
        checked_competition_count=len(raw_leagues),
        candidate_count=len(candidates),
        recommended_competition=recommended_competition,
        recommended_season=recommended_season,
        candidates=candidates,
        warnings=warnings,
        generated_at_utc=datetime.now(UTC),
    )


def _competition_candidate(
    raw_league: Mapping[str, object],
    *,
    target_competition_name: str,
    target_country_name: str | None,
    target_season: str,
    max_season_candidates: int,
) -> ApiFootballCompetitionDiscoveryCandidate:
    league = _required_mapping(raw_league.get("league"), "league")
    country = _optional_mapping(raw_league.get("country"))
    seasons_payload = raw_league.get("seasons")
    seasons = _season_candidates(
        seasons_payload if isinstance(seasons_payload, list) else [],
        target_season=target_season,
    )[:max_season_candidates]
    name = _required_text(league.get("name"), "league.name")
    country_name = _optional_text(country.get("name")) if country is not None else None
    name_score = _text_score(name, target_competition_name)
    country_score = _country_score(country_name, target_country_name)
    type_score = 0.05 if _optional_text(league.get("type")) == "League" else 0.0
    season_score = seasons[0].score * 0.10 if seasons else 0.0
    score = min(
        1.0,
        max(0.0, (name_score * 0.68) + (country_score * 0.17) + season_score + type_score),
    )
    return ApiFootballCompetitionDiscoveryCandidate(
        provider_competition_id=_required_text(league.get("id"), "league.id"),
        name=name,
        country_name=country_name,
        competition_type=_optional_text(league.get("type")),
        score=round(score, 4),
        seasons=seasons,
        recommended_season=seasons[0] if seasons else None,
        metadata={
            "country_code": _optional_text(country.get("code"))
            if country is not None
            else None,
        },
    )


def _season_candidates(
    raw_seasons: Sequence[object],
    *,
    target_season: str,
) -> list[ApiFootballSeasonDiscoveryCandidate]:
    candidates: list[ApiFootballSeasonDiscoveryCandidate] = []
    target_year = _target_year(target_season)
    for raw_season in raw_seasons:
        if not isinstance(raw_season, Mapping):
            continue
        year_value = raw_season.get("year")
        if not isinstance(year_value, int):
            continue
        score = 1.0 if year_value == target_year else 0.0
        if year_value == target_year - 1 or year_value == target_year + 1:
            score = max(score, 0.45)
        coverage = raw_season.get("coverage")
        candidates.append(
            ApiFootballSeasonDiscoveryCandidate(
                provider_season_id=str(year_value),
                year=year_value,
                score=score,
                current=_optional_bool(raw_season.get("current")),
                start=_optional_text(raw_season.get("start")),
                end=_optional_text(raw_season.get("end")),
                coverage=dict(coverage) if isinstance(coverage, Mapping) else {},
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def _recommended_competition(
    candidates: Sequence[ApiFootballCompetitionDiscoveryCandidate],
    *,
    min_competition_score: float,
) -> ApiFootballCompetitionDiscoveryCandidate | None:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.score >= min_competition_score
    ]
    for candidate in eligible:
        if candidate.recommended_season is not None:
            return candidate
    return eligible[0] if eligible else None


def _country_score(country_name: str | None, target_country_name: str | None) -> float:
    if not target_country_name:
        return 1.0
    if country_name is None:
        return 0.5
    return _text_score(country_name, target_country_name)


def _text_score(left: str, right: str) -> float:
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 0.92
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _normalize_text(value: str) -> str:
    ascii_text = (
        normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace("&", " and ")
        .lower()
    )
    return sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _target_year(value: str) -> int:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 4:
        raise ValueError("target season must contain a four-digit year")
    return int(digits[:4])


def _required_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"missing required API-Football discovery field: {field_name}")
    return value


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"missing required API-Football discovery field: {field_name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"missing required API-Football discovery field: {field_name}")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
