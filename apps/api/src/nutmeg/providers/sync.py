from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, SecretStr

from nutmeg.competition import load_competition_configs
from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.canonical_repository import (
    CanonicalCompetitionMetadata,
    CanonicalFixtureWriteSummary,
    PostgresFootballDataCanonicalRepository,
    football_data_canonical_id,
)
from nutmeg.providers.conflicts import (
    PostgresProviderObservationRepository,
    ProviderObservation,
    StoredProviderObservation,
)
from nutmeg.providers.football_data_org import (
    FootballDataOrgAdapter,
    FootballDataOrgConfig,
    normalize_match,
)
from nutmeg.providers.football_data_org.normalizer import NormalizedFixture
from nutmeg.providers.mock_dry_run import (
    MOCK_PROVIDER_DRY_RUN_WARNING,
    MockFootballDataDryRunTransport,
    should_use_mock_provider_dry_run,
)
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
    ProviderSyncRunRecord,
    StoredRawProviderPayload,
)


class RawPayloadWriter(Protocol):
    def save_raw_payload(
        self,
        *,
        provider: str,
        endpoint: str,
        request_params: Mapping[str, object],
        response_json: Mapping[str, object],
        entity_type: str | None = None,
        entity_id_hint: str | None = None,
    ) -> StoredRawProviderPayload: ...


class SyncRunWriter(Protocol):
    def start_sync_run(
        self,
        *,
        provider_name: str,
        capability: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord: ...

    def complete_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        entity_count: int,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord: ...

    def fail_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        error_message: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord: ...


class CanonicalFixtureWriter(Protocol):
    def upsert_fixtures(
        self,
        fixtures: list[NormalizedFixture],
        *,
        canonical_competition_id: str,
        season: str,
        provider_competition_id: str | None = None,
        competition_metadata: CanonicalCompetitionMetadata | None = None,
    ) -> CanonicalFixtureWriteSummary: ...


class ProviderObservationWriter(Protocol):
    def save_observations(
        self,
        observations: list[ProviderObservation],
    ) -> list[StoredProviderObservation]: ...


class FootballDataFixtureFetchResult(BaseModel):
    endpoint: str
    request_params: dict[str, object] = Field(default_factory=dict)
    payload: dict[str, object] = Field(default_factory=dict)
    fixtures: list[NormalizedFixture] = Field(default_factory=list)


class FootballDataFixtureSyncResult(BaseModel):
    provider_name: str = "football-data.org"
    provider_competition_id: str
    canonical_competition_id: str
    season: str
    dry_run: bool = False
    sync_run: ProviderSyncRunRecord | None = None
    raw_payload: StoredRawProviderPayload | None = None
    fixtures: list[NormalizedFixture] = Field(default_factory=list)
    canonical_write: CanonicalFixtureWriteSummary | None = None
    request_params: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def fetch_normalized_football_data_fixtures(
    *,
    adapter: FootballDataOrgAdapter,
    competition_id: str,
    season: str,
) -> FootballDataFixtureFetchResult:
    request_params: dict[str, object] = {"season": season}
    endpoint = f"/competitions/{competition_id}/matches"
    payload = adapter.fetch_competition_matches(competition_id, season=season)
    raw_fixtures = payload.get("matches")
    if not isinstance(raw_fixtures, list):
        raise ValueError("football-data.org matches response missing matches list")
    fixtures = [
        normalize_match(item)
        for item in raw_fixtures
        if isinstance(item, dict)
    ]
    return FootballDataFixtureFetchResult(
        endpoint=endpoint,
        request_params=request_params,
        payload=payload,
        fixtures=fixtures,
    )


def sync_football_data_fixtures(
    *,
    adapter: FootballDataOrgAdapter,
    raw_payload_repository: RawPayloadWriter,
    sync_run_repository: SyncRunWriter,
    competition_id: str,
    season: str,
    canonical_repository: CanonicalFixtureWriter | None = None,
    observation_repository: ProviderObservationWriter | None = None,
    canonical_competition_id: str | None = None,
    competition_metadata: CanonicalCompetitionMetadata | None = None,
) -> FootballDataFixtureSyncResult:
    effective_canonical_competition_id = canonical_competition_id or competition_id
    sync_run = sync_run_repository.start_sync_run(
        provider_name=adapter.provider_name,
        capability="fixtures",
        metadata_json={
            "provider_competition_id": competition_id,
            "canonical_competition_id": effective_canonical_competition_id,
            "season": season,
        },
    )
    try:
        fetch_result = fetch_normalized_football_data_fixtures(
            adapter=adapter,
            competition_id=competition_id,
            season=season,
        )
        if canonical_competition_id is None and fetch_result.fixtures:
            effective_canonical_competition_id = _canonical_competition_id(
                competition_id,
                fetch_result.fixtures,
            )
        raw_payload = raw_payload_repository.save_raw_payload(
            provider=adapter.provider_name,
            endpoint=fetch_result.endpoint,
            request_params=fetch_result.request_params,
            response_json=fetch_result.payload,
            entity_type="competition",
            entity_id_hint=competition_id,
        )
        canonical_write = None
        if canonical_repository is not None:
            canonical_write = canonical_repository.upsert_fixtures(
                fetch_result.fixtures,
                canonical_competition_id=effective_canonical_competition_id,
                season=season,
                provider_competition_id=competition_id,
                competition_metadata=competition_metadata,
            )
        if observation_repository is not None:
            observation_repository.save_observations(
                _football_data_fixture_observations(
                    fetch_result.fixtures,
                    payload_id=raw_payload.payload_id,
                    observed_at_utc=raw_payload.fetched_at,
                )
            )
        completed = sync_run_repository.complete_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            entity_count=len(fetch_result.fixtures),
            metadata_json={
                "provider_competition_id": competition_id,
                "canonical_competition_id": effective_canonical_competition_id,
                "season": season,
                "raw_payload_id": raw_payload.payload_id,
                "canonical_write": canonical_write.model_dump()
                if canonical_write is not None
                else None,
            },
        )
        return FootballDataFixtureSyncResult(
            provider_competition_id=competition_id,
            canonical_competition_id=effective_canonical_competition_id,
            season=season,
            sync_run=completed,
            raw_payload=raw_payload,
            fixtures=fetch_result.fixtures,
            canonical_write=canonical_write,
            request_params=fetch_result.request_params,
        )
    except Exception as exc:
        failed = sync_run_repository.fail_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            error_message=str(exc),
            metadata_json={
                "provider_competition_id": competition_id,
                "canonical_competition_id": effective_canonical_competition_id,
                "season": season,
            },
        )
        return FootballDataFixtureSyncResult(
            provider_competition_id=competition_id,
            canonical_competition_id=effective_canonical_competition_id,
            season=season,
            sync_run=failed,
            fixtures=[],
            warnings=[str(exc)],
        )


def run_football_data_fixture_sync(
    settings: Settings,
    *,
    provider_competition_id: str,
    season: str,
    dry_run: bool,
    canonical_competition_id: str | None = None,
) -> FootballDataFixtureSyncResult:
    use_mock_dry_run = should_use_mock_provider_dry_run(
        dry_run=dry_run,
        enabled=settings.provider_sync_mock_dry_run_enabled,
        api_key=settings.football_data_api_key,
    )
    adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=SecretStr(settings.football_data_api_key)
            if settings.football_data_api_key
            else None,
            base_url=settings.football_data_api_base_url,
            timeout_seconds=settings.football_data_api_timeout_seconds,
        ),
        transport=(
            MockFootballDataDryRunTransport(
                competition_id=provider_competition_id,
                season=season,
            )
            if use_mock_dry_run
            else None
        ),
    )
    if dry_run:
        fetch_result = fetch_normalized_football_data_fixtures(
            adapter=adapter,
            competition_id=provider_competition_id,
            season=season,
        )
        effective_canonical_competition_id = canonical_competition_id or _canonical_competition_id(
            provider_competition_id,
            fetch_result.fixtures,
        )
        return FootballDataFixtureSyncResult(
            provider_competition_id=provider_competition_id,
            canonical_competition_id=effective_canonical_competition_id,
            season=season,
            dry_run=True,
            fixtures=fetch_result.fixtures,
            request_params=fetch_result.request_params,
            warnings=[MOCK_PROVIDER_DRY_RUN_WARNING] if use_mock_dry_run else [],
        )

    effective_canonical_competition_id = canonical_competition_id or provider_competition_id
    database = PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    metadata = _competition_metadata(
        settings,
        canonical_competition_id=effective_canonical_competition_id,
        fallback_name=effective_canonical_competition_id,
    )
    return sync_football_data_fixtures(
        adapter=adapter,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        competition_id=provider_competition_id,
        season=season,
        canonical_repository=PostgresFootballDataCanonicalRepository(database),
        observation_repository=PostgresProviderObservationRepository(database),
        canonical_competition_id=effective_canonical_competition_id,
        competition_metadata=metadata,
    )


def _canonical_competition_id(
    provider_competition_id: str,
    fixtures: list[NormalizedFixture],
) -> str:
    if fixtures and fixtures[0].competition_code:
        return fixtures[0].competition_code or provider_competition_id
    return provider_competition_id


def _competition_metadata(
    settings: Settings,
    *,
    canonical_competition_id: str,
    fallback_name: str,
) -> CanonicalCompetitionMetadata:
    configs = load_competition_configs(settings.competition_config_dir)
    config = next(
        (
            item
            for item in configs
            if item.competition_id == canonical_competition_id
        ),
        None,
    )
    if config is None:
        return CanonicalCompetitionMetadata(
            name=fallback_name,
            config_json={
                "source": "football-data.org",
                "onboarding_stage": "provider_sync",
            },
        )
    return CanonicalCompetitionMetadata(
        name=config.name,
        country=config.country,
        region=config.region,
        competition_type=config.competition_type,
        team_type=config.team_type,
        season_calendar=config.season_calendar,
        provider_primary=config.provider_primary,
        provider_secondary=config.provider_secondary,
        coverage_tier=config.coverage_tier,
        model_status=config.model_status,
        config_json={
            "source": "competition_config",
            "model": config.model.model_dump(),
            "markets": config.markets.model_dump(),
            "quality_requirements": config.quality_requirements.model_dump(),
        },
    )


def _football_data_fixture_observations(
    fixtures: list[NormalizedFixture],
    *,
    payload_id: int,
    observed_at_utc: datetime,
) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for fixture in fixtures:
        canonical_fixture_id = football_data_canonical_id(
            "fixture",
            fixture.provider_entity_id,
        )
        observations.extend(
            [
                _football_data_fixture_observation(
                    fixture=fixture,
                    canonical_fixture_id=canonical_fixture_id,
                    payload_id=payload_id,
                    observed_at_utc=observed_at_utc,
                    capability="fixtures",
                    field_name="kickoff_time_utc",
                    value=fixture.kickoff_time_utc.isoformat(),
                ),
                _football_data_fixture_observation(
                    fixture=fixture,
                    canonical_fixture_id=canonical_fixture_id,
                    payload_id=payload_id,
                    observed_at_utc=observed_at_utc,
                    capability="fixtures",
                    field_name="status",
                    value=fixture.status,
                ),
                _football_data_fixture_observation(
                    fixture=fixture,
                    canonical_fixture_id=canonical_fixture_id,
                    payload_id=payload_id,
                    observed_at_utc=observed_at_utc,
                    capability="fixtures",
                    field_name="home_team_provider_id",
                    value=fixture.home_team.provider_entity_id,
                ),
                _football_data_fixture_observation(
                    fixture=fixture,
                    canonical_fixture_id=canonical_fixture_id,
                    payload_id=payload_id,
                    observed_at_utc=observed_at_utc,
                    capability="fixtures",
                    field_name="away_team_provider_id",
                    value=fixture.away_team.provider_entity_id,
                ),
            ]
        )
        if fixture.result is not None:
            observations.extend(
                [
                    _football_data_fixture_observation(
                        fixture=fixture,
                        canonical_fixture_id=canonical_fixture_id,
                        payload_id=payload_id,
                        observed_at_utc=observed_at_utc,
                        capability="results",
                        field_name="home_goals",
                        value=str(fixture.result.home_goals),
                    ),
                    _football_data_fixture_observation(
                        fixture=fixture,
                        canonical_fixture_id=canonical_fixture_id,
                        payload_id=payload_id,
                        observed_at_utc=observed_at_utc,
                        capability="results",
                        field_name="away_goals",
                        value=str(fixture.result.away_goals),
                    ),
                    _football_data_fixture_observation(
                        fixture=fixture,
                        canonical_fixture_id=canonical_fixture_id,
                        payload_id=payload_id,
                        observed_at_utc=observed_at_utc,
                        capability="results",
                        field_name="result_1x2",
                        value=fixture.result.result_1x2,
                    ),
                ]
            )
    return observations


def _football_data_fixture_observation(
    *,
    fixture: NormalizedFixture,
    canonical_fixture_id: str,
    payload_id: int,
    observed_at_utc: datetime,
    capability: str,
    field_name: str,
    value: str,
) -> ProviderObservation:
    return ProviderObservation(
        provider_name=fixture.provider,
        capability=capability,
        entity_type="fixture",
        canonical_entity_id=canonical_fixture_id,
        provider_entity_id=fixture.provider_entity_id,
        field_name=field_name,
        value=value,
        observed_at_utc=observed_at_utc,
        payload_id=payload_id,
    )
