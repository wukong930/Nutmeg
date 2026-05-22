from __future__ import annotations

from collections.abc import Sequence
from json import dumps
from re import sub
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.football_data_org.normalizer import NormalizedFixture, NormalizedTeam

UPSERT_PROVIDER_MAPPING_QUERY = """
INSERT INTO provider_entity_mappings (
  provider,
  entity_type,
  provider_entity_id,
  canonical_entity_id,
  confidence
) VALUES (
  %(provider)s,
  %(entity_type)s,
  %(provider_entity_id)s,
  %(canonical_entity_id)s,
  %(confidence)s
)
ON CONFLICT (provider, entity_type, provider_entity_id)
DO UPDATE SET
  canonical_entity_id = EXCLUDED.canonical_entity_id,
  confidence = EXCLUDED.confidence,
  updated_at = now()
RETURNING mapping_id
"""

UPSERT_COMPETITION_QUERY = """
INSERT INTO competitions (
  competition_id,
  name,
  country,
  region,
  competition_type,
  team_type,
  season_calendar,
  provider_primary,
  provider_secondary,
  coverage_tier,
  model_status,
  config_json
) VALUES (
  %(competition_id)s,
  %(name)s,
  %(country)s,
  %(region)s,
  %(competition_type)s,
  %(team_type)s,
  %(season_calendar)s,
  %(provider_primary)s,
  %(provider_secondary)s,
  %(coverage_tier)s,
  %(model_status)s,
  %(config_json)s::jsonb
)
ON CONFLICT (competition_id)
DO UPDATE SET
  provider_secondary = COALESCE(competitions.provider_secondary, EXCLUDED.provider_secondary),
  config_json = competitions.config_json || EXCLUDED.config_json,
  updated_at = now()
RETURNING competition_id
"""

UPSERT_SEASON_QUERY = """
INSERT INTO seasons (
  season_id,
  competition_id,
  name,
  start_date,
  end_date,
  current_matchday,
  status
) VALUES (
  %(season_id)s,
  %(competition_id)s,
  %(name)s,
  %(start_date)s,
  %(end_date)s,
  %(current_matchday)s,
  %(status)s
)
ON CONFLICT (season_id)
DO UPDATE SET
  start_date = COALESCE(EXCLUDED.start_date, seasons.start_date),
  end_date = COALESCE(EXCLUDED.end_date, seasons.end_date),
  current_matchday = COALESCE(EXCLUDED.current_matchday, seasons.current_matchday),
  status = COALESCE(EXCLUDED.status, seasons.status),
  updated_at = now()
RETURNING season_id
"""

UPSERT_TEAM_QUERY = """
INSERT INTO teams (
  team_id,
  name,
  country,
  team_type,
  metadata_json
) VALUES (
  %(team_id)s,
  %(name)s,
  %(country)s,
  %(team_type)s,
  %(metadata_json)s::jsonb
)
ON CONFLICT (team_id)
DO UPDATE SET
  name = EXCLUDED.name,
  metadata_json = teams.metadata_json || EXCLUDED.metadata_json,
  updated_at = now()
RETURNING team_id
"""

UPSERT_FIXTURE_QUERY = """
INSERT INTO fixtures (
  fixture_id,
  competition_id,
  season_id,
  stage,
  "round",
  matchday,
  home_team_id,
  away_team_id,
  kickoff_time_utc,
  venue,
  neutral_venue,
  aggregate_context_json,
  status
) VALUES (
  %(fixture_id)s,
  %(competition_id)s,
  %(season_id)s,
  %(stage)s,
  %(round)s,
  %(matchday)s,
  %(home_team_id)s,
  %(away_team_id)s,
  %(kickoff_time_utc)s,
  %(venue)s,
  %(neutral_venue)s,
  %(aggregate_context_json)s::jsonb,
  %(status)s
)
ON CONFLICT (fixture_id)
DO UPDATE SET
  competition_id = EXCLUDED.competition_id,
  season_id = EXCLUDED.season_id,
  stage = EXCLUDED.stage,
  "round" = EXCLUDED."round",
  matchday = EXCLUDED.matchday,
  home_team_id = EXCLUDED.home_team_id,
  away_team_id = EXCLUDED.away_team_id,
  kickoff_time_utc = EXCLUDED.kickoff_time_utc,
  venue = EXCLUDED.venue,
  aggregate_context_json = fixtures.aggregate_context_json || EXCLUDED.aggregate_context_json,
  status = EXCLUDED.status,
  updated_at = now()
RETURNING fixture_id
"""

UPSERT_RESULT_QUERY = """
INSERT INTO results (
  fixture_id,
  home_goals,
  away_goals,
  result_1x2,
  settled_at,
  source
) VALUES (
  %(fixture_id)s,
  %(home_goals)s,
  %(away_goals)s,
  %(result_1x2)s,
  now(),
  %(source)s
)
ON CONFLICT (fixture_id)
DO UPDATE SET
  home_goals = EXCLUDED.home_goals,
  away_goals = EXCLUDED.away_goals,
  result_1x2 = EXCLUDED.result_1x2,
  settled_at = EXCLUDED.settled_at,
  source = EXCLUDED.source,
  updated_at = now()
RETURNING fixture_id
"""


class CanonicalWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute an upsert statement with RETURNING and return one row."""


class CanonicalCompetitionMetadata(BaseModel):
    name: str
    country: str | None = None
    region: str | None = None
    competition_type: str = "domestic_league"
    team_type: str = "club"
    season_calendar: str = "unknown"
    provider_primary: str = "football_data_org"
    provider_secondary: str | None = None
    coverage_tier: str = "D_beta"
    model_status: str = "beta"
    config_json: dict[str, object] = Field(default_factory=dict)


class CanonicalFixtureWriteSummary(BaseModel):
    competitions: int = Field(default=0, ge=0)
    seasons: int = Field(default=0, ge=0)
    teams: int = Field(default=0, ge=0)
    fixtures: int = Field(default=0, ge=0)
    results: int = Field(default=0, ge=0)
    provider_mappings: int = Field(default=0, ge=0)
    canonical_fixture_ids: list[str] = Field(default_factory=list)


class PostgresFootballDataCanonicalRepository:
    def __init__(self, database: CanonicalWriteDatabaseExecutor) -> None:
        self.database = database

    def upsert_fixtures(
        self,
        fixtures: Sequence[NormalizedFixture],
        *,
        canonical_competition_id: str,
        season: str,
        provider_competition_id: str | None = None,
        competition_metadata: CanonicalCompetitionMetadata | None = None,
    ) -> CanonicalFixtureWriteSummary:
        if not fixtures:
            return CanonicalFixtureWriteSummary()

        first = fixtures[0]
        metadata = competition_metadata or CanonicalCompetitionMetadata(
            name=first.competition_name or canonical_competition_id,
            config_json={"source": "football-data.org"},
        )
        season_id = canonical_season_id(canonical_competition_id, season)
        summary = CanonicalFixtureWriteSummary()

        self._upsert_competition(canonical_competition_id, metadata)
        summary.competitions = 1

        mapped_competition_ids = {
            first.competition_provider_id,
            *(fixture.competition_provider_id for fixture in fixtures),
        }
        if provider_competition_id is not None:
            mapped_competition_ids.add(provider_competition_id)
        for provider_id in sorted(mapped_competition_ids):
            self._upsert_mapping(
                provider=first.provider,
                entity_type="competition",
                provider_entity_id=provider_id,
                canonical_entity_id=canonical_competition_id,
            )
            summary.provider_mappings += 1

        self._upsert_season(
            season_id=season_id,
            canonical_competition_id=canonical_competition_id,
            season=season,
            fixture=first,
        )
        summary.seasons = 1
        if first.season_provider_id:
            self._upsert_mapping(
                provider=first.provider,
                entity_type="season",
                provider_entity_id=first.season_provider_id,
                canonical_entity_id=season_id,
            )
            summary.provider_mappings += 1

        written_team_ids: set[str] = set()
        for fixture in fixtures:
            home_team_id = football_data_canonical_id("team", fixture.home_team.provider_entity_id)
            away_team_id = football_data_canonical_id("team", fixture.away_team.provider_entity_id)
            for team_id, team in [
                (home_team_id, fixture.home_team),
                (away_team_id, fixture.away_team),
            ]:
                if team_id not in written_team_ids:
                    self._upsert_team(team_id, team, team_type=metadata.team_type)
                    written_team_ids.add(team_id)
                    summary.teams += 1
                self._upsert_mapping(
                    provider=team.provider,
                    entity_type="team",
                    provider_entity_id=team.provider_entity_id,
                    canonical_entity_id=team_id,
                )
                summary.provider_mappings += 1

            fixture_id = football_data_canonical_id("fixture", fixture.provider_entity_id)
            self._upsert_mapping(
                provider=fixture.provider,
                entity_type="fixture",
                provider_entity_id=fixture.provider_entity_id,
                canonical_entity_id=fixture_id,
            )
            summary.provider_mappings += 1
            self._upsert_fixture(
                fixture_id=fixture_id,
                fixture=fixture,
                canonical_competition_id=canonical_competition_id,
                season_id=season_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
            )
            summary.fixtures += 1
            summary.canonical_fixture_ids.append(fixture_id)

            if fixture.result is not None:
                self._upsert_result(fixture_id, fixture)
                summary.results += 1

        return summary

    def _upsert_mapping(
        self,
        *,
        provider: str,
        entity_type: str,
        provider_entity_id: str,
        canonical_entity_id: str,
    ) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_PROVIDER_MAPPING_QUERY,
                {
                    "provider": provider,
                    "entity_type": entity_type,
                    "provider_entity_id": provider_entity_id,
                    "canonical_entity_id": canonical_entity_id,
                    "confidence": 1.0,
                },
            )
        )

    def _upsert_competition(
        self,
        canonical_competition_id: str,
        metadata: CanonicalCompetitionMetadata,
    ) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_COMPETITION_QUERY,
                {
                    "competition_id": canonical_competition_id,
                    "name": metadata.name,
                    "country": metadata.country,
                    "region": metadata.region,
                    "competition_type": metadata.competition_type,
                    "team_type": metadata.team_type,
                    "season_calendar": metadata.season_calendar,
                    "provider_primary": metadata.provider_primary,
                    "provider_secondary": metadata.provider_secondary,
                    "coverage_tier": metadata.coverage_tier,
                    "model_status": metadata.model_status,
                    "config_json": _json(metadata.config_json),
                },
            )
        )

    def _upsert_season(
        self,
        *,
        season_id: str,
        canonical_competition_id: str,
        season: str,
        fixture: NormalizedFixture,
    ) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_SEASON_QUERY,
                {
                    "season_id": season_id,
                    "competition_id": canonical_competition_id,
                    "name": season,
                    "start_date": fixture.season_start_date,
                    "end_date": fixture.season_end_date,
                    "current_matchday": fixture.matchday,
                    "status": "active" if fixture.status != "finished" else "completed",
                },
            )
        )

    def _upsert_team(self, team_id: str, team: NormalizedTeam, *, team_type: str) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_TEAM_QUERY,
                {
                    "team_id": team_id,
                    "name": team.name,
                    "country": None,
                    "team_type": team_type,
                    "metadata_json": _json(
                        {
                            "provider": team.provider,
                            "provider_entity_id": team.provider_entity_id,
                            "short_name": team.short_name,
                            "tla": team.tla,
                        }
                    ),
                },
            )
        )

    def _upsert_fixture(
        self,
        *,
        fixture_id: str,
        fixture: NormalizedFixture,
        canonical_competition_id: str,
        season_id: str,
        home_team_id: str,
        away_team_id: str,
    ) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_FIXTURE_QUERY,
                {
                    "fixture_id": fixture_id,
                    "competition_id": canonical_competition_id,
                    "season_id": season_id,
                    "stage": fixture.stage,
                    "round": fixture.group,
                    "matchday": fixture.matchday,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "kickoff_time_utc": fixture.kickoff_time_utc,
                    "venue": fixture.venue,
                    "neutral_venue": False,
                    "aggregate_context_json": _json(
                        {
                            "provider": fixture.provider,
                            "provider_entity_id": fixture.provider_entity_id,
                            "competition_provider_id": fixture.competition_provider_id,
                            "raw_status": fixture.raw_status,
                        }
                    ),
                    "status": fixture.status,
                },
            )
        )

    def _upsert_result(self, fixture_id: str, fixture: NormalizedFixture) -> None:
        if fixture.result is None:
            return
        _required_row(
            self.database.fetch_one(
                UPSERT_RESULT_QUERY,
                {
                    "fixture_id": fixture_id,
                    "home_goals": fixture.result.home_goals,
                    "away_goals": fixture.result.away_goals,
                    "result_1x2": fixture.result.result_1x2,
                    "source": fixture.provider,
                },
            )
        )


def canonical_season_id(canonical_competition_id: str, season: str) -> str:
    return f"{canonical_competition_id}:{season}"


def football_data_canonical_id(entity_type: str, provider_entity_id: str) -> str:
    normalized_id = sub(r"[^A-Za-z0-9]+", "_", provider_entity_id).strip("_").lower()
    return f"fd_{entity_type}_{normalized_id}"


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


