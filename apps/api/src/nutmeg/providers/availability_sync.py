from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.availability_repository import (
    AvailabilitySnapshotWriteSummary,
    PostgresAvailabilitySnapshotRepository,
    sportmonks_player_canonical_id,
)
from nutmeg.providers.conflicts import (
    PostgresProviderObservationRepository,
    ProviderObservation,
    StoredProviderObservation,
)
from nutmeg.providers.mock_dry_run import (
    MOCK_PROVIDER_DRY_RUN_TOKEN,
    MOCK_PROVIDER_DRY_RUN_WARNING,
    MockSportMonksDryRunTransport,
    should_use_mock_provider_dry_run,
)
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
    ProviderSyncRunRecord,
    StoredRawProviderPayload,
)
from nutmeg.providers.sportmonks import (
    NormalizedLineupSnapshot,
    NormalizedPlayerAvailabilitySnapshot,
    SportMonksAdapter,
    SportMonksConfig,
    normalize_injuries,
    normalize_lineups,
)
from nutmeg.providers.sync import ProviderObservationWriter, RawPayloadWriter, SyncRunWriter


class AvailabilitySnapshotWriter(Protocol):
    def save_sportmonks_fixture_availability(
        self,
        *,
        lineups: list[NormalizedLineupSnapshot],
        availabilities: list[NormalizedPlayerAvailabilitySnapshot],
        canonical_fixture_id: str,
        provider_fixture_id: str,
        team_mappings: Mapping[str, str],
        lineup_payload_id: int,
        availability_payload_ids: Mapping[str, int],
    ) -> AvailabilitySnapshotWriteSummary: ...


class SportMonksTeamInjuryFetchResult(BaseModel):
    provider_team_id: str
    endpoint: str = "/football/injuries"
    request_params: dict[str, object] = Field(default_factory=dict)
    payload: dict[str, object] = Field(default_factory=dict)
    availabilities: list[NormalizedPlayerAvailabilitySnapshot] = Field(default_factory=list)


class SportMonksFixtureAvailabilityFetchResult(BaseModel):
    provider_fixture_id: str
    lineup_endpoint: str
    lineup_request_params: dict[str, object] = Field(default_factory=dict)
    lineup_payload: dict[str, object] = Field(default_factory=dict)
    lineups: list[NormalizedLineupSnapshot] = Field(default_factory=list)
    injury_fetches: list[SportMonksTeamInjuryFetchResult] = Field(default_factory=list)

    @property
    def availabilities(self) -> list[NormalizedPlayerAvailabilitySnapshot]:
        return [
            availability
            for injury_fetch in self.injury_fetches
            for availability in injury_fetch.availabilities
        ]


class SportMonksFixtureAvailabilitySyncResult(BaseModel):
    provider_name: str = "sportmonks"
    provider_fixture_id: str
    canonical_fixture_id: str
    provider_team_ids: list[str]
    dry_run: bool = False
    sync_run: ProviderSyncRunRecord | None = None
    raw_payloads: list[StoredRawProviderPayload] = Field(default_factory=list)
    lineups: list[NormalizedLineupSnapshot] = Field(default_factory=list)
    availabilities: list[NormalizedPlayerAvailabilitySnapshot] = Field(default_factory=list)
    availability_write: AvailabilitySnapshotWriteSummary | None = None
    provider_observations: list[StoredProviderObservation] = Field(default_factory=list)
    provider_observation_count: int = Field(default=0, ge=0)
    request_params: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def fetch_normalized_sportmonks_fixture_availability(
    *,
    adapter: SportMonksAdapter,
    provider_fixture_id: str,
    provider_team_ids: list[str],
    snapshot_time_utc: datetime | None = None,
) -> SportMonksFixtureAvailabilityFetchResult:
    normalized_snapshot_time = _aware_utc(snapshot_time_utc or datetime.now(UTC))
    lineup_endpoint = f"/football/fixtures/{provider_fixture_id}/lineups"
    lineup_payload = adapter.fetch_lineups_payload(provider_fixture_id)
    lineups = normalize_lineups(
        lineup_payload,
        provider_fixture_id=provider_fixture_id,
        snapshot_time_utc=normalized_snapshot_time,
    )

    injury_fetches: list[SportMonksTeamInjuryFetchResult] = []
    for provider_team_id in provider_team_ids:
        request_params: dict[str, object] = {"filters": f"injuryTeam:{provider_team_id}"}
        injury_payload = adapter.fetch_injuries_payload(provider_team_id)
        availabilities = normalize_injuries(
            injury_payload,
            provider_team_id=provider_team_id,
            provider_fixture_id=provider_fixture_id,
            snapshot_time_utc=normalized_snapshot_time,
        )
        injury_fetches.append(
            SportMonksTeamInjuryFetchResult(
                provider_team_id=provider_team_id,
                request_params=request_params,
                payload=injury_payload,
                availabilities=availabilities,
            )
        )

    return SportMonksFixtureAvailabilityFetchResult(
        provider_fixture_id=provider_fixture_id,
        lineup_endpoint=lineup_endpoint,
        lineup_payload=lineup_payload,
        lineups=lineups,
        injury_fetches=injury_fetches,
    )


def sync_sportmonks_fixture_availability(
    *,
    adapter: SportMonksAdapter,
    raw_payload_repository: RawPayloadWriter,
    sync_run_repository: SyncRunWriter,
    provider_fixture_id: str,
    canonical_fixture_id: str,
    team_mappings: Mapping[str, str],
    availability_repository: AvailabilitySnapshotWriter | None = None,
    observation_repository: ProviderObservationWriter | None = None,
) -> SportMonksFixtureAvailabilitySyncResult:
    provider_team_ids = sorted(team_mappings)
    sync_run = sync_run_repository.start_sync_run(
        provider_name=adapter.provider_name,
        capability="lineups_injuries",
        metadata_json={
            "provider_fixture_id": provider_fixture_id,
            "canonical_fixture_id": canonical_fixture_id,
            "provider_team_ids": provider_team_ids,
            "canonical_team_ids": sorted(team_mappings.values()),
        },
    )
    try:
        fetch_result = fetch_normalized_sportmonks_fixture_availability(
            adapter=adapter,
            provider_fixture_id=provider_fixture_id,
            provider_team_ids=provider_team_ids,
        )
        raw_payloads: list[StoredRawProviderPayload] = []
        lineup_raw_payload = raw_payload_repository.save_raw_payload(
            provider=adapter.provider_name,
            endpoint=fetch_result.lineup_endpoint,
            request_params=fetch_result.lineup_request_params,
            response_json=fetch_result.lineup_payload,
            entity_type="fixture",
            entity_id_hint=provider_fixture_id,
        )
        raw_payloads.append(lineup_raw_payload)

        availability_payload_ids: dict[str, int] = {}
        for injury_fetch in fetch_result.injury_fetches:
            injury_raw_payload = raw_payload_repository.save_raw_payload(
                provider=adapter.provider_name,
                endpoint=injury_fetch.endpoint,
                request_params=injury_fetch.request_params,
                response_json=injury_fetch.payload,
                entity_type="team",
                entity_id_hint=injury_fetch.provider_team_id,
            )
            raw_payloads.append(injury_raw_payload)
            availability_payload_ids[injury_fetch.provider_team_id] = (
                injury_raw_payload.payload_id
            )

        availability_write = None
        if availability_repository is not None:
            availability_write = availability_repository.save_sportmonks_fixture_availability(
                lineups=fetch_result.lineups,
                availabilities=fetch_result.availabilities,
                canonical_fixture_id=canonical_fixture_id,
                provider_fixture_id=provider_fixture_id,
                team_mappings=team_mappings,
                lineup_payload_id=lineup_raw_payload.payload_id,
                availability_payload_ids=availability_payload_ids,
            )

        provider_observations: list[StoredProviderObservation] = []
        if observation_repository is not None:
            provider_observations = observation_repository.save_observations(
                _sportmonks_fixture_availability_observations(
                    lineups=fetch_result.lineups,
                    availabilities=fetch_result.availabilities,
                    canonical_fixture_id=canonical_fixture_id,
                    provider_fixture_id=provider_fixture_id,
                    team_mappings=team_mappings,
                    lineup_payload_id=lineup_raw_payload.payload_id,
                    availability_payload_ids=availability_payload_ids,
                )
            )

        completed = sync_run_repository.complete_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            entity_count=len(fetch_result.lineups) + len(fetch_result.availabilities),
            metadata_json={
                "provider_fixture_id": provider_fixture_id,
                "canonical_fixture_id": canonical_fixture_id,
                "raw_payload_ids": [payload.payload_id for payload in raw_payloads],
                "availability_write": availability_write.model_dump()
                if availability_write is not None
                else None,
                "provider_observation_count": len(provider_observations),
                "provider_observation_ids": [
                    observation.provider_observation_id
                    for observation in provider_observations
                ],
            },
        )
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=provider_fixture_id,
            canonical_fixture_id=canonical_fixture_id,
            provider_team_ids=provider_team_ids,
            sync_run=completed,
            raw_payloads=raw_payloads,
            lineups=fetch_result.lineups,
            availabilities=fetch_result.availabilities,
            availability_write=availability_write,
            provider_observations=provider_observations,
            provider_observation_count=len(provider_observations),
            request_params={"provider_team_ids": provider_team_ids},
        )
    except Exception as exc:
        failed = sync_run_repository.fail_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            error_message=str(exc),
            metadata_json={
                "provider_fixture_id": provider_fixture_id,
                "canonical_fixture_id": canonical_fixture_id,
                "provider_team_ids": provider_team_ids,
            },
        )
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=provider_fixture_id,
            canonical_fixture_id=canonical_fixture_id,
            provider_team_ids=provider_team_ids,
            sync_run=failed,
            warnings=[str(exc)],
        )


def run_sportmonks_fixture_availability_sync(
    settings: Settings,
    *,
    provider_fixture_id: str,
    canonical_fixture_id: str,
    team_mappings: Mapping[str, str],
    dry_run: bool,
) -> SportMonksFixtureAvailabilitySyncResult:
    use_mock_dry_run = should_use_mock_provider_dry_run(
        dry_run=dry_run,
        enabled=settings.provider_sync_mock_dry_run_enabled,
        api_key=settings.sportmonks_api_key,
    )
    provider_team_ids = sorted(team_mappings)
    adapter = SportMonksAdapter(
        SportMonksConfig(
            api_token=(
                SecretStr(settings.sportmonks_api_key)
                if settings.sportmonks_api_key
                else SecretStr(MOCK_PROVIDER_DRY_RUN_TOKEN)
                if use_mock_dry_run
                else None
            ),
            base_url=settings.sportmonks_api_base_url,
            timeout_seconds=settings.sportmonks_api_timeout_seconds,
        ),
        transport=(
            MockSportMonksDryRunTransport(
                provider_fixture_id=provider_fixture_id,
                provider_team_ids=provider_team_ids,
            )
            if use_mock_dry_run
            else None
        ),
    )
    if dry_run:
        fetch_result = fetch_normalized_sportmonks_fixture_availability(
            adapter=adapter,
            provider_fixture_id=provider_fixture_id,
            provider_team_ids=provider_team_ids,
        )
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=provider_fixture_id,
            canonical_fixture_id=canonical_fixture_id,
            provider_team_ids=provider_team_ids,
            dry_run=True,
            lineups=fetch_result.lineups,
            availabilities=fetch_result.availabilities,
            provider_observation_count=len(
                _sportmonks_fixture_availability_observations(
                    lineups=fetch_result.lineups,
                    availabilities=fetch_result.availabilities,
                    canonical_fixture_id=canonical_fixture_id,
                    provider_fixture_id=provider_fixture_id,
                    team_mappings=team_mappings,
                    lineup_payload_id=None,
                    availability_payload_ids={},
                )
            ),
            request_params={"provider_team_ids": provider_team_ids},
            warnings=[MOCK_PROVIDER_DRY_RUN_WARNING] if use_mock_dry_run else [],
        )

    database = PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    return sync_sportmonks_fixture_availability(
        adapter=adapter,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        availability_repository=PostgresAvailabilitySnapshotRepository(database),
        observation_repository=PostgresProviderObservationRepository(database),
        provider_fixture_id=provider_fixture_id,
        canonical_fixture_id=canonical_fixture_id,
        team_mappings=team_mappings,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sportmonks_fixture_availability_observations(
    *,
    lineups: list[NormalizedLineupSnapshot],
    availabilities: list[NormalizedPlayerAvailabilitySnapshot],
    canonical_fixture_id: str,
    provider_fixture_id: str,
    team_mappings: Mapping[str, str],
    lineup_payload_id: int | None,
    availability_payload_ids: Mapping[str, int],
) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for lineup in lineups:
        canonical_team_id = _canonical_team_id(
            team_mappings,
            provider_team_id=lineup.provider_team_id,
        )
        player_key = _player_key(
            provider_player_id=lineup.provider_player_id,
            player_name=lineup.player_name,
        )
        observations.extend(
            _lineup_observations(
                lineup=lineup,
                canonical_fixture_id=canonical_fixture_id,
                provider_fixture_id=provider_fixture_id,
                canonical_team_id=canonical_team_id,
                player_key=player_key,
                payload_id=lineup_payload_id,
            )
        )
    for availability in availabilities:
        canonical_team_id = _canonical_team_id(
            team_mappings,
            provider_team_id=availability.provider_team_id,
        )
        player_key = _player_key(
            provider_player_id=availability.provider_player_id,
            player_name=availability.player_name,
        )
        observations.extend(
            _availability_observations(
                availability=availability,
                canonical_fixture_id=canonical_fixture_id,
                provider_fixture_id=provider_fixture_id,
                canonical_team_id=canonical_team_id,
                player_key=player_key,
                payload_id=availability_payload_ids.get(availability.provider_team_id),
            )
        )
    return observations


def _lineup_observations(
    *,
    lineup: NormalizedLineupSnapshot,
    canonical_fixture_id: str,
    provider_fixture_id: str,
    canonical_team_id: str,
    player_key: str,
    payload_id: int | None,
) -> list[ProviderObservation]:
    values: list[tuple[str, str]] = [
        ("lineup_type", lineup.lineup_type),
    ]
    if lineup.position is not None:
        values.append(("position", lineup.position))
    if lineup.probability_start is not None:
        values.append(("probability_start", f"{lineup.probability_start:.4f}"))
    if lineup.is_starter is not None:
        values.append(("is_starter", str(lineup.is_starter).lower()))
    return [
        _sportmonks_observation(
            capability="lineups",
            canonical_fixture_id=canonical_fixture_id,
            provider_fixture_id=provider_fixture_id,
            canonical_team_id=canonical_team_id,
            player_key=player_key,
            provider_player_id=lineup.provider_player_id,
            player_name=lineup.player_name,
            field_name=f"lineup:{canonical_team_id}:{player_key}:{field}",
            value=value,
            observed_at_utc=lineup.snapshot_time_utc,
            payload_id=payload_id,
            metadata_json={"lineup_type": lineup.lineup_type},
        )
        for field, value in values
    ]


def _availability_observations(
    *,
    availability: NormalizedPlayerAvailabilitySnapshot,
    canonical_fixture_id: str,
    provider_fixture_id: str,
    canonical_team_id: str,
    player_key: str,
    payload_id: int | None,
) -> list[ProviderObservation]:
    values: list[tuple[str, str]] = [
        ("status", availability.status),
    ]
    if availability.reason is not None:
        values.append(("reason", availability.reason))
    if availability.expected_return_date is not None:
        values.append(
            ("expected_return_date", availability.expected_return_date.isoformat())
        )
    return [
        _sportmonks_observation(
            capability="injuries",
            canonical_fixture_id=canonical_fixture_id,
            provider_fixture_id=provider_fixture_id,
            canonical_team_id=canonical_team_id,
            player_key=player_key,
            provider_player_id=availability.provider_player_id,
            player_name=availability.player_name,
            field_name=f"availability:{canonical_team_id}:{player_key}:{field}",
            value=value,
            observed_at_utc=availability.snapshot_time_utc,
            payload_id=payload_id,
            metadata_json={
                "status": availability.status,
                "source_confidence": availability.source_confidence,
            },
        )
        for field, value in values
    ]


def _sportmonks_observation(
    *,
    capability: str,
    canonical_fixture_id: str,
    provider_fixture_id: str,
    canonical_team_id: str,
    player_key: str,
    provider_player_id: str | None,
    player_name: str | None,
    field_name: str,
    value: str,
    observed_at_utc: datetime,
    payload_id: int | None,
    metadata_json: dict[str, object],
) -> ProviderObservation:
    return ProviderObservation(
        provider_name="sportmonks",
        capability=capability,
        entity_type="fixture",
        canonical_entity_id=canonical_fixture_id,
        provider_entity_id=provider_fixture_id,
        field_name=field_name,
        value=value,
        observed_at_utc=observed_at_utc,
        payload_id=payload_id,
        metadata_json={
            "canonical_team_id": canonical_team_id,
            "provider_player_id": provider_player_id,
            "player_key": player_key,
            "player_name": player_name,
            **metadata_json,
        },
    )


def _canonical_team_id(
    team_mappings: Mapping[str, str],
    *,
    provider_team_id: str,
) -> str:
    canonical_team_id = team_mappings.get(provider_team_id)
    if canonical_team_id is None:
        raise ValueError(
            "canonical team mapping missing for SportMonks provider team "
            f"{provider_team_id}"
        )
    return canonical_team_id


def _player_key(*, provider_player_id: str | None, player_name: str | None) -> str:
    if provider_player_id is not None:
        return sportmonks_player_canonical_id(provider_player_id)
    if player_name:
        return _slug(player_name)
    return "unknown_player"


def _slug(value: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_" for character in value
    ).strip("_")
