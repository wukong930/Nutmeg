from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.canonical_repository import UPSERT_PROVIDER_MAPPING_QUERY

LIST_PROVIDER_ENTITY_MAPPINGS_QUERY = """
SELECT
  mapping_id,
  provider,
  entity_type,
  provider_entity_id,
  canonical_entity_id,
  confidence,
  created_at,
  updated_at
FROM provider_entity_mappings
WHERE (%(provider)s::text IS NULL OR provider = %(provider)s::text)
  AND (%(entity_type)s::text IS NULL OR entity_type = %(entity_type)s::text)
  AND (
    %(canonical_entity_id)s::text IS NULL
    OR canonical_entity_id = %(canonical_entity_id)s::text
  )
ORDER BY updated_at DESC, mapping_id DESC
LIMIT %(limit)s
"""

PROVIDER_ENTITY_MAPPING_SUMMARY_QUERY = """
SELECT
  provider,
  entity_type,
  COUNT(*) AS mapping_count,
  AVG(confidence) AS average_confidence,
  MIN(confidence) AS minimum_confidence,
  MAX(updated_at) AS latest_updated_at
FROM provider_entity_mappings
WHERE (%(provider)s::text IS NULL OR provider = %(provider)s::text)
  AND (%(entity_type)s::text IS NULL OR entity_type = %(entity_type)s::text)
  AND (
    %(canonical_entity_id)s::text IS NULL
    OR canonical_entity_id = %(canonical_entity_id)s::text
  )
GROUP BY provider, entity_type
ORDER BY provider ASC, entity_type ASC
"""

LIST_PROVIDER_FIXTURE_MAPPINGS_BY_COMPETITION_QUERY = """
SELECT
  pem.mapping_id,
  pem.provider,
  pem.entity_type,
  pem.provider_entity_id,
  pem.canonical_entity_id,
  pem.confidence,
  pem.created_at,
  pem.updated_at
FROM provider_entity_mappings pem
JOIN fixtures f
  ON f.fixture_id = pem.canonical_entity_id
WHERE pem.provider = %(provider)s
  AND pem.entity_type = 'fixture'
  AND f.competition_id = %(competition_id)s
  AND pem.confidence >= %(min_confidence)s
ORDER BY f.kickoff_time_utc ASC, pem.updated_at DESC, pem.mapping_id DESC
LIMIT %(limit)s
"""


class ProviderMappingDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only provider mapping query."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a provider mapping write query and return one row."""


class ProviderEntityMappingRecord(BaseModel):
    mapping_id: int = Field(gt=0)
    provider: str
    entity_type: str
    provider_entity_id: str
    canonical_entity_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_at_utc: datetime
    updated_at_utc: datetime


class ProviderEntityMappingSummary(BaseModel):
    provider: str
    entity_type: str
    mapping_count: int = Field(ge=0)
    average_confidence: float = Field(ge=0.0, le=1.0)
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    latest_updated_at_utc: datetime


class ProviderEntityMappingList(BaseModel):
    items: list[ProviderEntityMappingRecord] = Field(default_factory=list)
    summary: list[ProviderEntityMappingSummary] = Field(default_factory=list)


class ProviderEntityMappingUpsert(BaseModel):
    provider: str
    entity_type: str
    provider_entity_id: str
    canonical_entity_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class PostgresProviderEntityMappingRepository:
    def __init__(self, database: ProviderMappingDatabaseExecutor) -> None:
        self.database = database

    def list_mappings(
        self,
        *,
        provider: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        limit: int = 100,
    ) -> ProviderEntityMappingList:
        normalized_limit = min(max(limit, 1), 500)
        params: QueryParams = {
            "provider": provider,
            "entity_type": entity_type,
            "canonical_entity_id": canonical_entity_id,
            "limit": normalized_limit,
        }
        item_rows = self.database.fetch_all(LIST_PROVIDER_ENTITY_MAPPINGS_QUERY, params)
        summary_rows = self.database.fetch_all(
            PROVIDER_ENTITY_MAPPING_SUMMARY_QUERY,
            params,
        )
        return ProviderEntityMappingList(
            items=[_mapping_record_from_row(row) for row in item_rows],
            summary=[_summary_from_row(row) for row in summary_rows],
        )

    def list_review_candidates(
        self,
        *,
        provider: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        limit: int = 1_000,
    ) -> list[ProviderEntityMappingRecord]:
        normalized_limit = min(max(limit, 1), 2_000)
        rows = self.database.fetch_all(
            LIST_PROVIDER_ENTITY_MAPPINGS_QUERY,
            {
                "provider": provider,
                "entity_type": entity_type,
                "canonical_entity_id": canonical_entity_id,
                "limit": normalized_limit,
            },
        )
        return [_mapping_record_from_row(row) for row in rows]

    def list_fixture_mappings_for_competition(
        self,
        *,
        provider: str,
        competition_id: str,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[ProviderEntityMappingRecord]:
        normalized_limit = min(max(limit, 1), 500)
        rows = self.database.fetch_all(
            LIST_PROVIDER_FIXTURE_MAPPINGS_BY_COMPETITION_QUERY,
            {
                "provider": provider,
                "competition_id": competition_id,
                "min_confidence": min_confidence,
                "limit": normalized_limit,
            },
        )
        return [_mapping_record_from_row(row) for row in rows]

    def upsert_mapping(self, mapping: ProviderEntityMappingUpsert) -> int:
        row = self.database.fetch_one(
            UPSERT_PROVIDER_MAPPING_QUERY,
            mapping.model_dump(),
        )
        if row is None:
            raise ValueError("expected provider mapping RETURNING row")
        return _int(row["mapping_id"])

    def upsert_mappings(
        self,
        mappings: Sequence[ProviderEntityMappingUpsert],
    ) -> list[int]:
        return [self.upsert_mapping(mapping) for mapping in mappings]


def _mapping_record_from_row(row: DatabaseRow) -> ProviderEntityMappingRecord:
    return ProviderEntityMappingRecord(
        mapping_id=_int(row["mapping_id"]),
        provider=str(row["provider"]),
        entity_type=str(row["entity_type"]),
        provider_entity_id=str(row["provider_entity_id"]),
        canonical_entity_id=str(row["canonical_entity_id"]),
        confidence=_float(row["confidence"]),
        created_at_utc=_datetime(row["created_at"]),
        updated_at_utc=_datetime(row["updated_at"]),
    )


def _summary_from_row(row: DatabaseRow) -> ProviderEntityMappingSummary:
    return ProviderEntityMappingSummary(
        provider=str(row["provider"]),
        entity_type=str(row["entity_type"]),
        mapping_count=_int(row["mapping_count"]),
        average_confidence=_float(row["average_confidence"]),
        minimum_confidence=_float(row["minimum_confidence"]),
        latest_updated_at_utc=_datetime(row["latest_updated_at"]),
    )


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    return int(str(value))


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))
