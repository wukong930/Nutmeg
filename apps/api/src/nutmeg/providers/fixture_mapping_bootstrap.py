from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from re import sub
from typing import Protocol
from unicodedata import normalize

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.api_football import ApiFootballAdapter, ApiFootballConfig
from nutmeg.providers.canonical_repository import football_data_canonical_id
from nutmeg.providers.football_data_org import FootballDataOrgAdapter, FootballDataOrgConfig
from nutmeg.providers.football_data_org.normalizer import NormalizedFixture
from nutmeg.providers.mapping_repository import (
    PostgresProviderEntityMappingRepository,
    ProviderEntityMappingUpsert,
)
from nutmeg.providers.sportmonks import SportMonksAdapter, SportMonksConfig
from nutmeg.providers.sync import fetch_normalized_football_data_fixtures
from nutmeg.providers.the_odds_api import TheOddsApiAdapter, TheOddsApiConfig

_TEAM_TOKEN_STOPWORDS = {
    "afc",
    "cf",
    "club",
    "fc",
    "football",
    "sc",
    "the",
}

_TEAM_ALIASES = {
    "man city": "manchester city",
    "man utd": "manchester united",
    "man united": "manchester united",
    "newcastle": "newcastle united",
    "nottingham": "nottingham forest",
    "spurs": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
}


class FixtureMappingWriter(Protocol):
    def upsert_mappings(
        self,
        mappings: Sequence[ProviderEntityMappingUpsert],
    ) -> list[int]: ...


class CanonicalFixtureMappingCandidate(BaseModel):
    canonical_fixture_id: str
    provider_fixture_id: str
    home_team_name: str
    away_team_name: str
    kickoff_time_utc: datetime
    status: str


class ProviderFixtureMappingCandidate(BaseModel):
    provider_name: str
    provider_fixture_id: str
    home_team_name: str
    away_team_name: str
    kickoff_time_utc: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class FixtureMappingMatchCandidate(BaseModel):
    provider_name: str
    provider_fixture_id: str
    canonical_fixture_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    home_team_score: float = Field(ge=0.0, le=1.0)
    away_team_score: float = Field(ge=0.0, le=1.0)
    time_delta_minutes: float = Field(ge=0.0)
    reasons: list[str] = Field(default_factory=list)
    ambiguous: bool = False
    persisted_mapping_id: int | None = Field(default=None, gt=0)


class FixtureMappingBootstrapResult(BaseModel):
    provider_name: str
    dry_run: bool
    source_provider: str
    source_competition_id: str
    canonical_competition_id: str
    source_season: str
    provider_sport_key: str
    source_fixture_count: int = Field(ge=0)
    provider_fixture_count: int = Field(ge=0)
    provider_fixture_source: str = "events"
    matched_count: int = Field(ge=0)
    persisted_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    unmatched_provider_fixture_count: int = Field(ge=0)
    unmatched_canonical_fixture_count: int = Field(default=0, ge=0)
    min_confidence: float = Field(ge=0.0, le=1.0)
    kickoff_tolerance_minutes: int = Field(ge=1)
    matches: list[FixtureMappingMatchCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime


def build_fixture_mapping_matches(
    *,
    canonical_fixtures: Sequence[CanonicalFixtureMappingCandidate],
    provider_fixtures: Sequence[ProviderFixtureMappingCandidate],
    kickoff_tolerance_minutes: int = 180,
    min_confidence: float = 0.82,
) -> list[FixtureMappingMatchCandidate]:
    matches: list[FixtureMappingMatchCandidate] = []
    used_canonical_ids: set[str] = set()
    for provider_fixture in provider_fixtures:
        ranked = sorted(
            (
                _score_candidate(
                    provider_fixture,
                    canonical_fixture,
                    kickoff_tolerance_minutes=kickoff_tolerance_minutes,
                )
                for canonical_fixture in canonical_fixtures
                if canonical_fixture.canonical_fixture_id not in used_canonical_ids
            ),
            key=lambda item: item.confidence,
            reverse=True,
        )
        if not ranked:
            continue
        best = ranked[0]
        if best.confidence < min_confidence:
            continue
        if (
            len(ranked) > 1
            and ranked[1].confidence >= min_confidence
            and best.confidence - ranked[1].confidence < 0.03
        ):
            best = best.model_copy(
                update={
                    "ambiguous": True,
                    "reasons": [*best.reasons, "ambiguous_second_candidate"],
                }
            )
        if not best.ambiguous:
            used_canonical_ids.add(best.canonical_fixture_id)
        matches.append(best)
    return matches


def run_the_odds_api_fixture_mapping_bootstrap(
    settings: Settings,
    *,
    provider_competition_id: str,
    canonical_competition_id: str,
    season: str,
    sport_key: str,
    regions: str,
    markets: str,
    bookmakers: str | None,
    dry_run: bool,
    kickoff_tolerance_minutes: int = 180,
    min_confidence: float = 0.82,
    max_provider_events: int = 100,
    mapping_writer: FixtureMappingWriter | None = None,
) -> FixtureMappingBootstrapResult:
    football_data_adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=(
                SecretStr(settings.football_data_api_key)
                if settings.football_data_api_key
                else None
            ),
            base_url=settings.football_data_api_base_url,
            timeout_seconds=settings.football_data_api_timeout_seconds,
        )
    )
    football_data_result = fetch_normalized_football_data_fixtures(
        adapter=football_data_adapter,
        competition_id=provider_competition_id,
        season=season,
    )
    source_candidates = _canonical_candidates_from_football_data(
        football_data_result.fixtures
    )

    odds_adapter = TheOddsApiAdapter(
        TheOddsApiConfig(
            api_key=(
                SecretStr(settings.the_odds_api_key)
                if settings.the_odds_api_key
                else None
            ),
            base_url=settings.the_odds_api_base_url,
            timeout_seconds=settings.the_odds_api_timeout_seconds,
        )
    )
    raw_provider_events = _fetch_the_odds_api_fixture_events(
        adapter=odds_adapter,
        sport_key=sport_key,
        canonical_fixtures=source_candidates,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
    )
    provider_candidates = _provider_candidates_from_the_odds_api(
        raw_provider_events[:max_provider_events]
    )
    matches = build_fixture_mapping_matches(
        canonical_fixtures=source_candidates,
        provider_fixtures=provider_candidates,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        min_confidence=min_confidence,
    )
    persistable_matches = [match for match in matches if not match.ambiguous]
    warnings: list[str] = []
    persisted_count = 0
    if not dry_run and persistable_matches:
        writer = mapping_writer or PostgresProviderEntityMappingRepository(
            PsycopgSyncDatabaseExecutor(
                settings.database_url,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        )
        mapping_ids = writer.upsert_mappings(
            [
                ProviderEntityMappingUpsert(
                    provider="the-odds-api",
                    entity_type="fixture",
                    provider_entity_id=match.provider_fixture_id,
                    canonical_entity_id=match.canonical_fixture_id,
                    confidence=match.confidence,
                )
                for match in persistable_matches
            ]
        )
        persisted_count = len(mapping_ids)
        matches = [
            match.model_copy(update={"persisted_mapping_id": mapping_id})
            if not match.ambiguous
            else match
            for match, mapping_id in zip(persistable_matches, mapping_ids, strict=True)
        ] + [match for match in matches if match.ambiguous]

    if not persistable_matches:
        warnings.append("no_unambiguous_provider_fixture_matches")
    if len(raw_provider_events) > max_provider_events:
        warnings.append("provider_event_limit_applied")

    return FixtureMappingBootstrapResult(
        provider_name="the-odds-api",
        dry_run=dry_run,
        source_provider="football-data.org",
        source_competition_id=provider_competition_id,
        canonical_competition_id=canonical_competition_id,
        source_season=season,
        provider_sport_key=sport_key,
        source_fixture_count=len(source_candidates),
        provider_fixture_count=len(provider_candidates),
        provider_fixture_source="events",
        matched_count=len(matches),
        persisted_count=persisted_count,
        ambiguous_count=sum(1 for match in matches if match.ambiguous),
        unmatched_provider_fixture_count=max(len(provider_candidates) - len(matches), 0),
        unmatched_canonical_fixture_count=max(len(source_candidates) - len(matches), 0),
        min_confidence=min_confidence,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        matches=matches,
        warnings=warnings,
        generated_at_utc=datetime.now(UTC),
    )


def run_sportmonks_fixture_mapping_bootstrap(
    settings: Settings,
    *,
    source_provider_competition_id: str,
    canonical_competition_id: str,
    source_season: str,
    sportmonks_competition_id: str,
    sportmonks_season: str,
    dry_run: bool,
    kickoff_tolerance_minutes: int = 180,
    min_confidence: float = 0.82,
    max_provider_fixtures: int = 500,
    mapping_writer: FixtureMappingWriter | None = None,
) -> FixtureMappingBootstrapResult:
    football_data_adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=(
                SecretStr(settings.football_data_api_key)
                if settings.football_data_api_key
                else None
            ),
            base_url=settings.football_data_api_base_url,
            timeout_seconds=settings.football_data_api_timeout_seconds,
        )
    )
    football_data_result = fetch_normalized_football_data_fixtures(
        adapter=football_data_adapter,
        competition_id=source_provider_competition_id,
        season=source_season,
    )
    source_candidates = _canonical_candidates_from_football_data(
        football_data_result.fixtures
    )

    sportmonks_adapter = SportMonksAdapter(
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
    raw_provider_fixtures = sportmonks_adapter.fetch_fixtures(
        sportmonks_competition_id,
        sportmonks_season,
    )
    limited_provider_fixtures = raw_provider_fixtures[:max_provider_fixtures]
    provider_candidates = _provider_candidates_from_sportmonks(
        limited_provider_fixtures
    )
    matches = build_fixture_mapping_matches(
        canonical_fixtures=source_candidates,
        provider_fixtures=provider_candidates,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        min_confidence=min_confidence,
    )
    persistable_matches = [match for match in matches if not match.ambiguous]
    warnings: list[str] = []
    persisted_count = 0
    if not dry_run and persistable_matches:
        writer = mapping_writer or PostgresProviderEntityMappingRepository(
            PsycopgSyncDatabaseExecutor(
                settings.database_url,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        )
        mapping_ids = writer.upsert_mappings(
            [
                ProviderEntityMappingUpsert(
                    provider="sportmonks",
                    entity_type="fixture",
                    provider_entity_id=match.provider_fixture_id,
                    canonical_entity_id=match.canonical_fixture_id,
                    confidence=match.confidence,
                )
                for match in persistable_matches
            ]
        )
        persisted_count = len(mapping_ids)
        matches = [
            match.model_copy(update={"persisted_mapping_id": mapping_id})
            if not match.ambiguous
            else match
            for match, mapping_id in zip(persistable_matches, mapping_ids, strict=True)
        ] + [match for match in matches if match.ambiguous]

    if not persistable_matches:
        warnings.append("no_unambiguous_provider_fixture_matches")
    if len(raw_provider_fixtures) > max_provider_fixtures:
        warnings.append("provider_fixture_limit_applied")
    if len(provider_candidates) < len(limited_provider_fixtures):
        warnings.append("sportmonks_fixture_candidate_parse_skipped")

    return FixtureMappingBootstrapResult(
        provider_name="sportmonks",
        dry_run=dry_run,
        source_provider="football-data.org",
        source_competition_id=source_provider_competition_id,
        canonical_competition_id=canonical_competition_id,
        source_season=source_season,
        provider_sport_key=(
            f"sportmonks:{sportmonks_competition_id}:{sportmonks_season}"
        ),
        source_fixture_count=len(source_candidates),
        provider_fixture_count=len(provider_candidates),
        provider_fixture_source="fixtures",
        matched_count=len(matches),
        persisted_count=persisted_count,
        ambiguous_count=sum(1 for match in matches if match.ambiguous),
        unmatched_provider_fixture_count=max(len(provider_candidates) - len(matches), 0),
        unmatched_canonical_fixture_count=max(len(source_candidates) - len(matches), 0),
        min_confidence=min_confidence,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        matches=matches,
        warnings=warnings,
        generated_at_utc=datetime.now(UTC),
    )


def run_api_football_fixture_mapping_bootstrap(
    settings: Settings,
    *,
    source_provider_competition_id: str,
    canonical_competition_id: str,
    source_season: str,
    api_football_league_id: str,
    api_football_season: str,
    dry_run: bool,
    kickoff_tolerance_minutes: int = 180,
    min_confidence: float = 0.82,
    max_provider_fixtures: int = 500,
    mapping_writer: FixtureMappingWriter | None = None,
) -> FixtureMappingBootstrapResult:
    football_data_adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=(
                SecretStr(settings.football_data_api_key)
                if settings.football_data_api_key
                else None
            ),
            base_url=settings.football_data_api_base_url,
            timeout_seconds=settings.football_data_api_timeout_seconds,
        )
    )
    football_data_result = fetch_normalized_football_data_fixtures(
        adapter=football_data_adapter,
        competition_id=source_provider_competition_id,
        season=source_season,
    )
    source_candidates = _canonical_candidates_from_football_data(
        football_data_result.fixtures
    )

    api_football_adapter = ApiFootballAdapter(
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
    raw_provider_fixtures = api_football_adapter.fetch_fixtures(
        league_id=api_football_league_id,
        season=api_football_season,
    )
    limited_provider_fixtures = raw_provider_fixtures[:max_provider_fixtures]
    provider_candidates = _provider_candidates_from_api_football(
        limited_provider_fixtures
    )
    matches = build_fixture_mapping_matches(
        canonical_fixtures=source_candidates,
        provider_fixtures=provider_candidates,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        min_confidence=min_confidence,
    )
    persistable_matches = [match for match in matches if not match.ambiguous]
    warnings: list[str] = []
    persisted_count = 0
    if not dry_run and persistable_matches:
        writer = mapping_writer or PostgresProviderEntityMappingRepository(
            PsycopgSyncDatabaseExecutor(
                settings.database_url,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        )
        mapping_ids = writer.upsert_mappings(
            [
                ProviderEntityMappingUpsert(
                    provider="api-football",
                    entity_type="fixture",
                    provider_entity_id=match.provider_fixture_id,
                    canonical_entity_id=match.canonical_fixture_id,
                    confidence=match.confidence,
                )
                for match in persistable_matches
            ]
        )
        persisted_count = len(mapping_ids)
        matches = [
            match.model_copy(update={"persisted_mapping_id": mapping_id})
            if not match.ambiguous
            else match
            for match, mapping_id in zip(persistable_matches, mapping_ids, strict=True)
        ] + [match for match in matches if match.ambiguous]

    if not persistable_matches:
        warnings.append("no_unambiguous_provider_fixture_matches")
    if len(raw_provider_fixtures) > max_provider_fixtures:
        warnings.append("provider_fixture_limit_applied")
    if len(provider_candidates) < len(limited_provider_fixtures):
        warnings.append("api_football_fixture_candidate_parse_skipped")

    return FixtureMappingBootstrapResult(
        provider_name="api-football",
        dry_run=dry_run,
        source_provider="football-data.org",
        source_competition_id=source_provider_competition_id,
        canonical_competition_id=canonical_competition_id,
        source_season=source_season,
        provider_sport_key=f"api-football:{api_football_league_id}:{api_football_season}",
        source_fixture_count=len(source_candidates),
        provider_fixture_count=len(provider_candidates),
        provider_fixture_source="fixtures",
        matched_count=len(matches),
        persisted_count=persisted_count,
        ambiguous_count=sum(1 for match in matches if match.ambiguous),
        unmatched_provider_fixture_count=max(len(provider_candidates) - len(matches), 0),
        unmatched_canonical_fixture_count=max(len(source_candidates) - len(matches), 0),
        min_confidence=min_confidence,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        matches=matches,
        warnings=warnings,
        generated_at_utc=datetime.now(UTC),
    )


def _fetch_the_odds_api_fixture_events(
    *,
    adapter: TheOddsApiAdapter,
    sport_key: str,
    canonical_fixtures: Sequence[CanonicalFixtureMappingCandidate],
    kickoff_tolerance_minutes: int,
) -> list[dict[str, object]]:
    if not canonical_fixtures:
        return []
    margin = timedelta(minutes=kickoff_tolerance_minutes)
    commence_time_from = min(
        fixture.kickoff_time_utc.astimezone(UTC) for fixture in canonical_fixtures
    ) - margin
    commence_time_to = max(
        fixture.kickoff_time_utc.astimezone(UTC) for fixture in canonical_fixtures
    ) + margin
    return adapter.fetch_sport_events(
        sport_key=sport_key,
        date_format="iso",
        commence_time_from=_api_timestamp(commence_time_from),
        commence_time_to=_api_timestamp(commence_time_to),
    )


def _canonical_candidates_from_football_data(
    fixtures: Sequence[NormalizedFixture],
) -> list[CanonicalFixtureMappingCandidate]:
    return [
        CanonicalFixtureMappingCandidate(
            canonical_fixture_id=football_data_canonical_id(
                "fixture",
                fixture.provider_entity_id,
            ),
            provider_fixture_id=fixture.provider_entity_id,
            home_team_name=fixture.home_team.name,
            away_team_name=fixture.away_team.name,
            kickoff_time_utc=fixture.kickoff_time_utc.astimezone(UTC),
            status=fixture.status,
        )
        for fixture in fixtures
    ]


def _provider_candidates_from_the_odds_api(
    events: Sequence[dict[str, object]],
) -> list[ProviderFixtureMappingCandidate]:
    candidates: list[ProviderFixtureMappingCandidate] = []
    for event in events:
        try:
            candidates.append(
                ProviderFixtureMappingCandidate(
                    provider_name="the-odds-api",
                    provider_fixture_id=_required_text(event.get("id"), "event.id"),
                    home_team_name=_required_text(event.get("home_team"), "event.home_team"),
                    away_team_name=_required_text(event.get("away_team"), "event.away_team"),
                    kickoff_time_utc=_datetime(event.get("commence_time")),
                    metadata={
                        "sport_key": _optional_text(event.get("sport_key")),
                        "sport_title": _optional_text(event.get("sport_title")),
                    },
                )
            )
        except ValueError:
            continue
    return candidates


def _provider_candidates_from_sportmonks(
    fixtures: Sequence[dict[str, object]],
) -> list[ProviderFixtureMappingCandidate]:
    candidates: list[ProviderFixtureMappingCandidate] = []
    for fixture in fixtures:
        try:
            home_team_name, away_team_name = _sportmonks_fixture_team_names(fixture)
            candidates.append(
                ProviderFixtureMappingCandidate(
                    provider_name="sportmonks",
                    provider_fixture_id=_required_text(fixture.get("id"), "fixture.id"),
                    home_team_name=home_team_name,
                    away_team_name=away_team_name,
                    kickoff_time_utc=_sportmonks_fixture_kickoff_time(fixture),
                    metadata={
                        "league_id": _optional_text(
                            fixture.get("league_id") or fixture.get("leagueId")
                        ),
                        "season_id": _optional_text(
                            fixture.get("season_id") or fixture.get("seasonId")
                        ),
                    },
                )
            )
        except ValueError:
            continue
    return candidates


def _provider_candidates_from_api_football(
    fixtures: Sequence[dict[str, object]],
) -> list[ProviderFixtureMappingCandidate]:
    candidates: list[ProviderFixtureMappingCandidate] = []
    for fixture in fixtures:
        try:
            fixture_payload = _required_mapping(fixture.get("fixture"), "fixture")
            teams = _required_mapping(fixture.get("teams"), "teams")
            home_team = _required_mapping(teams.get("home"), "teams.home")
            away_team = _required_mapping(teams.get("away"), "teams.away")
            league = _as_mapping(fixture.get("league"))
            candidates.append(
                ProviderFixtureMappingCandidate(
                    provider_name="api-football",
                    provider_fixture_id=_required_text(
                        fixture_payload.get("id"),
                        "fixture.id",
                    ),
                    home_team_name=_required_text(home_team.get("name"), "home.name"),
                    away_team_name=_required_text(away_team.get("name"), "away.name"),
                    kickoff_time_utc=_datetime(fixture_payload.get("date")),
                    metadata={
                        "league_id": _optional_text(league.get("id"))
                        if league is not None
                        else None,
                        "season": _optional_text(league.get("season"))
                        if league is not None
                        else None,
                    },
                )
            )
        except ValueError:
            continue
    return candidates


def _sportmonks_fixture_kickoff_time(fixture: Mapping[str, object]) -> datetime:
    for key in (
        "starting_at",
        "startingAt",
        "start_time",
        "startTime",
        "kickoff_time",
        "kickoffTime",
    ):
        value = fixture.get(key)
        if value is not None:
            return _datetime(value)
    time_payload = _as_mapping(fixture.get("time"))
    if time_payload is not None:
        for key in ("starting_at", "startingAt", "start_time", "startTime"):
            value = time_payload.get(key)
            if value is not None:
                return _datetime(value)
    raise ValueError("missing required provider fixture field: fixture.kickoff_time")


def _sportmonks_fixture_team_names(fixture: Mapping[str, object]) -> tuple[str, str]:
    home_name = _first_text(
        fixture,
        (
            "home_team_name",
            "homeTeamName",
            "localteam_name",
            "localTeamName",
        ),
    )
    away_name = _first_text(
        fixture,
        (
            "away_team_name",
            "awayTeamName",
            "visitorteam_name",
            "visitorTeamName",
        ),
    )
    for key in ("homeTeam", "home_team", "localteam", "localTeam", "homeParticipant"):
        team = _as_mapping(fixture.get(key))
        if team is not None:
            home_name = home_name or _first_text(team, ("name", "display_name"))
    for key in (
        "awayTeam",
        "away_team",
        "visitorteam",
        "visitorTeam",
        "awayParticipant",
    ):
        team = _as_mapping(fixture.get(key))
        if team is not None:
            away_name = away_name or _first_text(team, ("name", "display_name"))

    participants = _sportmonks_participants(fixture.get("participants"))
    for participant in participants:
        location = _sportmonks_participant_location(participant)
        participant_name = _first_text(participant, ("name", "display_name"))
        if location == "home":
            home_name = home_name or participant_name
        elif location == "away":
            away_name = away_name or participant_name

    if (not home_name or not away_name) and len(participants) >= 2:
        home_name = home_name or _first_text(participants[0], ("name", "display_name"))
        away_name = away_name or _first_text(participants[1], ("name", "display_name"))

    return (
        _required_text(home_name, "fixture.home_team"),
        _required_text(away_name, "fixture.away_team"),
    )


def _sportmonks_participants(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    payload = _as_mapping(value)
    if payload is None:
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    return []


def _sportmonks_participant_location(participant: Mapping[str, object]) -> str | None:
    location = _optional_text(
        participant.get("location")
        or participant.get("side")
        or participant.get("type")
    )
    meta = _as_mapping(participant.get("meta"))
    if location is None and meta is not None:
        location = _optional_text(
            meta.get("location") or meta.get("side") or meta.get("type")
        )
    if location is None:
        if participant.get("home") is True or participant.get("is_home") is True:
            return "home"
        if participant.get("away") is True or participant.get("is_away") is True:
            return "away"
        return None
    normalized = location.strip().lower()
    if normalized in {"home", "local", "localteam"}:
        return "home"
    if normalized in {"away", "visitor", "visitorteam"}:
        return "away"
    return None


def _first_text(
    payload: Mapping[str, object],
    keys: Sequence[str],
) -> str | None:
    for key in keys:
        text = _optional_text(payload.get(key))
        if text is not None:
            return text
    return None


def _as_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _required_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"missing required provider fixture field: {field_name}")
    return value


def _score_candidate(
    provider_fixture: ProviderFixtureMappingCandidate,
    canonical_fixture: CanonicalFixtureMappingCandidate,
    *,
    kickoff_tolerance_minutes: int,
) -> FixtureMappingMatchCandidate:
    delta_minutes = abs(
        (
            provider_fixture.kickoff_time_utc.astimezone(UTC)
            - canonical_fixture.kickoff_time_utc.astimezone(UTC)
        ).total_seconds()
    ) / 60.0
    if delta_minutes > kickoff_tolerance_minutes:
        time_score = 0.0
    else:
        time_score = 1.0 - (delta_minutes / kickoff_tolerance_minutes) * 0.5
    home_score = _team_name_score(
        provider_fixture.home_team_name,
        canonical_fixture.home_team_name,
    )
    away_score = _team_name_score(
        provider_fixture.away_team_name,
        canonical_fixture.away_team_name,
    )
    confidence = max(
        0.0,
        min(1.0, (home_score * 0.45) + (away_score * 0.45) + (time_score * 0.10)),
    )
    reasons = [
        f"home_team_score:{home_score:.3f}",
        f"away_team_score:{away_score:.3f}",
        f"time_delta_minutes:{delta_minutes:.1f}",
    ]
    if delta_minutes <= 5:
        reasons.append("kickoff_exact_or_near_exact")
    return FixtureMappingMatchCandidate(
        provider_name=provider_fixture.provider_name,
        provider_fixture_id=provider_fixture.provider_fixture_id,
        canonical_fixture_id=canonical_fixture.canonical_fixture_id,
        confidence=round(confidence, 4),
        home_team_score=round(home_score, 4),
        away_team_score=round(away_score, 4),
        time_delta_minutes=round(delta_minutes, 2),
        reasons=reasons,
    )


def _team_name_score(left: str, right: str) -> float:
    normalized_left = _normalize_team_name(left)
    normalized_right = _normalize_team_name(right)
    if normalized_left == normalized_right:
        return 1.0
    ratio = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    if not left_tokens or not right_tokens:
        return ratio
    overlap = len(left_tokens & right_tokens)
    precision = overlap / len(left_tokens)
    recall = overlap / len(right_tokens)
    token_score = (
        0.0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall)
    )
    return max(ratio, token_score)


def _normalize_team_name(value: str) -> str:
    ascii_text = (
        normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace("&", " and ")
        .lower()
    )
    ascii_text = sub(r"[^a-z0-9]+", " ", ascii_text)
    compact = " ".join(
        token
        for token in ascii_text.split()
        if token not in _TEAM_TOKEN_STOPWORDS
    )
    return _TEAM_ALIASES.get(compact, compact)


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"missing required provider fixture field: {field_name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"missing required provider fixture field: {field_name}")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _datetime(value: object) -> datetime:
    text = _required_text(value, "fixture.kickoff_time")
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _api_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
