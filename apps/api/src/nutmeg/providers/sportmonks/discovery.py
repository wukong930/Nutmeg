from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher
from re import sub
from typing import Protocol
from unicodedata import normalize

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.providers.sportmonks.adapter import (
    SportMonksAdapter,
    SportMonksConfig,
    SportMonksHttpError,
)


class SportMonksDiscoveryAdapter(Protocol):
    def fetch_competitions(
        self,
        *,
        include_country: bool = False,
    ) -> list[dict[str, object]]: ...

    def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]: ...


class SportMonksSeasonDiscoveryCandidate(BaseModel):
    provider_season_id: str
    name: str
    score: float = Field(ge=0.0, le=1.0)
    is_current: bool | None = None
    finished: bool | None = None
    starting_at: str | None = None
    ending_at: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SportMonksCompetitionDiscoveryCandidate(BaseModel):
    provider_competition_id: str
    name: str
    country_name: str | None = None
    competition_type: str | None = None
    active: bool | None = None
    score: float = Field(ge=0.0, le=1.0)
    seasons: list[SportMonksSeasonDiscoveryCandidate] = Field(default_factory=list)
    recommended_season: SportMonksSeasonDiscoveryCandidate | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SportMonksCompetitionDiscoveryResult(BaseModel):
    provider_name: str = "sportmonks"
    target_competition_name: str
    target_country_name: str | None = None
    target_season: str
    min_competition_score: float = Field(ge=0.0, le=1.0)
    checked_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    recommended_competition: SportMonksCompetitionDiscoveryCandidate | None = None
    recommended_season: SportMonksSeasonDiscoveryCandidate | None = None
    candidates: list[SportMonksCompetitionDiscoveryCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime


def discover_sportmonks_competition_season(
    settings: Settings,
    *,
    target_competition_name: str = "Premier League",
    target_country_name: str | None = "England",
    target_season: str = "2025",
    max_competition_candidates: int = 5,
    max_season_candidates: int = 6,
    min_competition_score: float = 0.75,
    adapter: SportMonksDiscoveryAdapter | None = None,
) -> SportMonksCompetitionDiscoveryResult:
    warnings: list[str] = []
    sportmonks_adapter = adapter or SportMonksAdapter(
        SportMonksConfig(
            api_token=(
                SecretStr(settings.sportmonks_api_key)
                if settings.sportmonks_api_key
                else None
            ),
            base_url=settings.sportmonks_api_base_url,
            timeout_seconds=settings.sportmonks_api_timeout_seconds,
        )
    )
    raw_competitions = _fetch_competitions(
        sportmonks_adapter,
        warnings=warnings,
    )
    parsed_competitions: list[SportMonksCompetitionDiscoveryCandidate] = []
    for raw_competition in raw_competitions:
        try:
            parsed_competitions.append(
                _competition_candidate(
                    raw_competition,
                    target_competition_name=target_competition_name,
                    target_country_name=target_country_name,
                )
            )
        except ValueError:
            warnings.append("sportmonks_competition_candidate_parse_skipped")
    competition_candidates = sorted(
        parsed_competitions,
        key=lambda candidate: candidate.score,
        reverse=True,
    )[:max_competition_candidates]
    competition_candidates = [
        _with_discovered_seasons(
            sportmonks_adapter,
            candidate,
            target_season=target_season,
            max_season_candidates=max_season_candidates,
            warnings=warnings,
        )
        for candidate in competition_candidates
    ]
    recommended_competition = _recommended_competition(
        competition_candidates,
        min_competition_score=min_competition_score,
    )
    recommended_season = (
        recommended_competition.recommended_season
        if recommended_competition is not None
        else None
    )
    if not competition_candidates:
        warnings.append("no_sportmonks_competition_candidates")
    elif recommended_competition is None:
        warnings.append("no_sportmonks_competition_above_confidence_threshold")
    if recommended_competition is not None and recommended_season is None:
        warnings.append("no_sportmonks_season_candidate_for_recommendation")

    return SportMonksCompetitionDiscoveryResult(
        target_competition_name=target_competition_name,
        target_country_name=target_country_name,
        target_season=target_season,
        min_competition_score=min_competition_score,
        checked_competition_count=len(raw_competitions),
        candidate_count=len(competition_candidates),
        recommended_competition=recommended_competition,
        recommended_season=recommended_season,
        candidates=competition_candidates,
        warnings=warnings,
        generated_at_utc=datetime.now(UTC),
    )


def _fetch_competitions(
    adapter: SportMonksDiscoveryAdapter,
    *,
    warnings: list[str],
) -> list[dict[str, object]]:
    try:
        return adapter.fetch_competitions(include_country=True)
    except SportMonksHttpError as exc:
        if exc.status_code not in {400, 422}:
            raise
        warnings.append("sportmonks_country_include_unavailable")
        return adapter.fetch_competitions()


def _with_discovered_seasons(
    adapter: SportMonksDiscoveryAdapter,
    candidate: SportMonksCompetitionDiscoveryCandidate,
    *,
    target_season: str,
    max_season_candidates: int,
    warnings: list[str],
) -> SportMonksCompetitionDiscoveryCandidate:
    try:
        raw_seasons = adapter.fetch_seasons(candidate.provider_competition_id)
    except SportMonksHttpError as exc:
        warnings.append(
            f"sportmonks_season_fetch_failed:{candidate.provider_competition_id}:"
            f"{exc.status_code}"
        )
        return candidate
    parsed_seasons: list[SportMonksSeasonDiscoveryCandidate] = []
    for raw_season in raw_seasons:
        try:
            parsed_seasons.append(
                _season_candidate(raw_season, target_season=target_season)
            )
        except ValueError:
            warnings.append(
                f"sportmonks_season_candidate_parse_skipped:"
                f"{candidate.provider_competition_id}"
            )
    seasons = sorted(
        parsed_seasons,
        key=lambda season: season.score,
        reverse=True,
    )[:max_season_candidates]
    return candidate.model_copy(
        update={
            "seasons": seasons,
            "recommended_season": seasons[0] if seasons else None,
            "metadata": {
                **candidate.metadata,
                "raw_season_count": len(raw_seasons),
            },
        }
    )


def _competition_candidate(
    raw_competition: Mapping[str, object],
    *,
    target_competition_name: str,
    target_country_name: str | None,
) -> SportMonksCompetitionDiscoveryCandidate:
    name = _required_text(raw_competition.get("name"), "competition.name")
    country_name = _country_name(raw_competition)
    name_score = _text_score(name, target_competition_name)
    country_score = _country_score(country_name, target_country_name)
    active = _optional_bool(raw_competition.get("active"))
    active_score = 1.0 if active is True else 0.0
    score = min(
        1.0,
        max(0.0, (name_score * 0.75) + (country_score * 0.20) + (active_score * 0.05)),
    )
    return SportMonksCompetitionDiscoveryCandidate(
        provider_competition_id=_required_text(raw_competition.get("id"), "competition.id"),
        name=name,
        country_name=country_name,
        competition_type=_optional_text(
            raw_competition.get("type") or raw_competition.get("sub_type")
        ),
        active=active,
        score=round(score, 4),
        metadata={
            "country_id": _optional_text(raw_competition.get("country_id")),
            "short_code": _optional_text(
                raw_competition.get("short_code") or raw_competition.get("shortCode")
            ),
        },
    )


def _season_candidate(
    raw_season: Mapping[str, object],
    *,
    target_season: str,
) -> SportMonksSeasonDiscoveryCandidate:
    name = _required_text(raw_season.get("name"), "season.name")
    start_year = _start_year(target_season)
    end_year = start_year + 1 if start_year is not None else None
    starting_at = _optional_text(
        raw_season.get("starting_at") or raw_season.get("startingAt")
    )
    ending_at = _optional_text(
        raw_season.get("ending_at") or raw_season.get("endingAt")
    )
    normalized_name = _normalize_text(name)
    target_tokens = [target_season]
    if start_year is not None:
        target_tokens.append(str(start_year))
    if end_year is not None:
        target_tokens.append(str(end_year))

    textual_score = max(
        (_text_score(normalized_name, token) for token in target_tokens if token),
        default=0.0,
    )
    if start_year is not None and str(start_year) in normalized_name:
        textual_score = max(textual_score, 0.82)
    if end_year is not None and str(end_year) in normalized_name:
        textual_score = max(textual_score, 0.72)
    if starting_at and start_year is not None and starting_at.startswith(str(start_year)):
        textual_score = max(textual_score, 0.86)

    is_current = _optional_bool(
        raw_season.get("is_current") or raw_season.get("isCurrent")
    )
    finished = _optional_bool(raw_season.get("finished"))
    current_score = 0.10 if is_current is True else 0.0
    not_finished_score = 0.04 if finished is False else 0.0
    score = min(1.0, max(0.0, textual_score + current_score + not_finished_score))
    return SportMonksSeasonDiscoveryCandidate(
        provider_season_id=_required_text(raw_season.get("id"), "season.id"),
        name=name,
        score=round(score, 4),
        is_current=is_current,
        finished=finished,
        starting_at=starting_at,
        ending_at=ending_at,
        metadata={
            "league_id": _optional_text(
                raw_season.get("league_id") or raw_season.get("leagueId")
            ),
        },
    )


def _recommended_competition(
    candidates: Sequence[SportMonksCompetitionDiscoveryCandidate],
    *,
    min_competition_score: float,
) -> SportMonksCompetitionDiscoveryCandidate | None:
    eligible_candidates = [
        candidate
        for candidate in candidates
        if candidate.score >= min_competition_score
    ]
    for candidate in eligible_candidates:
        if candidate.recommended_season is not None:
            return candidate
    return eligible_candidates[0] if eligible_candidates else None


def _country_name(raw_competition: Mapping[str, object]) -> str | None:
    direct = _optional_text(
        raw_competition.get("country_name") or raw_competition.get("countryName")
    )
    if direct is not None:
        return direct
    country = raw_competition.get("country")
    if isinstance(country, Mapping):
        return _optional_text(country.get("name"))
    if isinstance(country, dict):
        return _optional_text(country.get("name"))
    return None


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


def _start_year(value: str) -> int | None:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 4:
        return None
    return int(digits[:4])


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"missing required SportMonks discovery field: {field_name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"missing required SportMonks discovery field: {field_name}")
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
