from __future__ import annotations

from collections.abc import Mapping, Sequence
from re import sub

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow
from nutmeg.providers.canonical_repository import (
    UPSERT_PROVIDER_MAPPING_QUERY,
    CanonicalWriteDatabaseExecutor,
)
from nutmeg.providers.sportmonks.normalizer import (
    NormalizedLineupSnapshot,
    NormalizedPlayerAvailabilitySnapshot,
)

INSERT_LINEUP_SNAPSHOT_QUERY = """
INSERT INTO lineup_snapshots (
  fixture_id,
  team_id,
  lineup_type,
  player_id,
  player_name,
  position,
  probability_start,
  is_starter,
  source,
  snapshot_time_utc,
  payload_id
) VALUES (
  %(fixture_id)s,
  %(team_id)s,
  %(lineup_type)s,
  %(player_id)s,
  %(player_name)s,
  %(position)s,
  %(probability_start)s,
  %(is_starter)s,
  %(source)s,
  %(snapshot_time_utc)s,
  %(payload_id)s
)
RETURNING lineup_snapshot_id
"""

INSERT_PLAYER_AVAILABILITY_SNAPSHOT_QUERY = """
INSERT INTO player_availability_snapshots (
  fixture_id,
  team_id,
  player_id,
  player_name,
  status,
  reason,
  expected_return_date,
  source,
  source_confidence,
  snapshot_time_utc,
  payload_id
) VALUES (
  %(fixture_id)s,
  %(team_id)s,
  %(player_id)s,
  %(player_name)s,
  %(status)s,
  %(reason)s,
  %(expected_return_date)s,
  %(source)s,
  %(source_confidence)s,
  %(snapshot_time_utc)s,
  %(payload_id)s
)
RETURNING availability_snapshot_id
"""


class AvailabilitySnapshotWriteSummary(BaseModel):
    lineup_snapshots: int = Field(default=0, ge=0)
    availability_snapshots: int = Field(default=0, ge=0)
    provider_mappings: int = Field(default=0, ge=0)
    player_mappings: int = Field(default=0, ge=0)
    canonical_fixture_id: str
    canonical_team_ids: list[str] = Field(default_factory=list)


class PostgresAvailabilitySnapshotRepository:
    def __init__(self, database: CanonicalWriteDatabaseExecutor) -> None:
        self.database = database

    def save_sportmonks_fixture_availability(
        self,
        *,
        lineups: Sequence[NormalizedLineupSnapshot],
        availabilities: Sequence[NormalizedPlayerAvailabilitySnapshot],
        canonical_fixture_id: str,
        provider_fixture_id: str,
        team_mappings: Mapping[str, str],
        lineup_payload_id: int,
        availability_payload_ids: Mapping[str, int],
    ) -> AvailabilitySnapshotWriteSummary:
        self._upsert_mapping(
            provider="sportmonks",
            entity_type="fixture",
            provider_entity_id=provider_fixture_id,
            canonical_entity_id=canonical_fixture_id,
        )
        provider_mapping_count = 1

        canonical_team_ids: set[str] = set()
        for provider_team_id, canonical_team_id in sorted(team_mappings.items()):
            self._upsert_mapping(
                provider="sportmonks",
                entity_type="team",
                provider_entity_id=provider_team_id,
                canonical_entity_id=canonical_team_id,
            )
            provider_mapping_count += 1
            canonical_team_ids.add(canonical_team_id)

        player_mapping_count = 0
        mapped_players: set[str] = set()
        lineup_count = 0
        for lineup in lineups:
            canonical_team_id = _canonical_team_id(
                team_mappings,
                provider_team_id=lineup.provider_team_id,
            )
            player_id = _canonical_player_id(lineup.provider_player_id)
            if lineup.provider_player_id and lineup.provider_player_id not in mapped_players:
                player_mapping_id = sportmonks_player_canonical_id(lineup.provider_player_id)
                self._upsert_mapping(
                    provider=lineup.provider,
                    entity_type="player",
                    provider_entity_id=lineup.provider_player_id,
                    canonical_entity_id=player_mapping_id,
                )
                mapped_players.add(lineup.provider_player_id)
                provider_mapping_count += 1
                player_mapping_count += 1
            _required_row(
                self.database.fetch_one(
                    INSERT_LINEUP_SNAPSHOT_QUERY,
                    {
                        "fixture_id": canonical_fixture_id,
                        "team_id": canonical_team_id,
                        "lineup_type": lineup.lineup_type,
                        "player_id": player_id,
                        "player_name": lineup.player_name,
                        "position": lineup.position,
                        "probability_start": lineup.probability_start,
                        "is_starter": lineup.is_starter,
                        "source": lineup.source,
                        "snapshot_time_utc": lineup.snapshot_time_utc,
                        "payload_id": lineup_payload_id,
                    },
                )
            )
            lineup_count += 1

        availability_count = 0
        for availability in availabilities:
            canonical_team_id = _canonical_team_id(
                team_mappings,
                provider_team_id=availability.provider_team_id,
            )
            payload_id = availability_payload_ids.get(availability.provider_team_id)
            if payload_id is None:
                raise ValueError(
                    "availability payload id missing for provider team "
                    f"{availability.provider_team_id}"
                )
            player_id = _canonical_player_id(availability.provider_player_id)
            if (
                availability.provider_player_id
                and availability.provider_player_id not in mapped_players
            ):
                player_mapping_id = sportmonks_player_canonical_id(
                    availability.provider_player_id
                )
                self._upsert_mapping(
                    provider=availability.provider,
                    entity_type="player",
                    provider_entity_id=availability.provider_player_id,
                    canonical_entity_id=player_mapping_id,
                )
                mapped_players.add(availability.provider_player_id)
                provider_mapping_count += 1
                player_mapping_count += 1
            _required_row(
                self.database.fetch_one(
                    INSERT_PLAYER_AVAILABILITY_SNAPSHOT_QUERY,
                    {
                        "fixture_id": canonical_fixture_id,
                        "team_id": canonical_team_id,
                        "player_id": player_id,
                        "player_name": availability.player_name,
                        "status": availability.status,
                        "reason": availability.reason,
                        "expected_return_date": availability.expected_return_date,
                        "source": availability.source,
                        "source_confidence": availability.source_confidence,
                        "snapshot_time_utc": availability.snapshot_time_utc,
                        "payload_id": payload_id,
                    },
                )
            )
            availability_count += 1

        return AvailabilitySnapshotWriteSummary(
            lineup_snapshots=lineup_count,
            availability_snapshots=availability_count,
            provider_mappings=provider_mapping_count,
            player_mappings=player_mapping_count,
            canonical_fixture_id=canonical_fixture_id,
            canonical_team_ids=sorted(canonical_team_ids),
        )

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


def sportmonks_player_canonical_id(provider_player_id: str) -> str:
    normalized_id = sub(r"[^A-Za-z0-9]+", "_", provider_player_id).strip("_").lower()
    return f"sm_player_{normalized_id}"


def _canonical_player_id(provider_player_id: str | None) -> str | None:
    if provider_player_id is None:
        return None
    return sportmonks_player_canonical_id(provider_player_id)


def _canonical_team_id(team_mappings: Mapping[str, str], *, provider_team_id: str) -> str:
    canonical_team_id = team_mappings.get(provider_team_id)
    if canonical_team_id is None:
        raise ValueError(
            "canonical team mapping missing for SportMonks provider team "
            f"{provider_team_id}"
        )
    return canonical_team_id


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row
