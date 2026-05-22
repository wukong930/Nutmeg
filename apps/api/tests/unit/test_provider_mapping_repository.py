from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.mapping_repository import (
    LIST_PROVIDER_ENTITY_MAPPINGS_QUERY,
    LIST_PROVIDER_FIXTURE_MAPPINGS_BY_COMPETITION_QUERY,
    PROVIDER_ENTITY_MAPPING_SUMMARY_QUERY,
    PostgresProviderEntityMappingRepository,
    ProviderEntityMappingUpsert,
)


class FakeProviderMappingDatabase:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_ENTITY_MAPPINGS_QUERY:
            return [
                {
                    "mapping_id": 101,
                    "provider": "football-data.org",
                    "entity_type": "fixture",
                    "provider_entity_id": "330299",
                    "canonical_entity_id": "fd_fixture_330299",
                    "confidence": Decimal("1.0"),
                    "created_at": datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    "updated_at": datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                }
            ]
        if query == PROVIDER_ENTITY_MAPPING_SUMMARY_QUERY:
            return [
                {
                    "provider": "football-data.org",
                    "entity_type": "fixture",
                    "mapping_count": 1,
                    "average_confidence": Decimal("1.0"),
                    "minimum_confidence": Decimal("1.0"),
                    "latest_updated_at": datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                }
            ]
        if query == LIST_PROVIDER_FIXTURE_MAPPINGS_BY_COMPETITION_QUERY:
            return [
                {
                    "mapping_id": 102,
                    "provider": "the-odds-api",
                    "entity_type": "fixture",
                    "provider_entity_id": "event_123",
                    "canonical_entity_id": "fd_fixture_330299",
                    "confidence": Decimal("0.99"),
                    "created_at": datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    "updated_at": datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if "provider_entity_mappings" in query:
            return {"mapping_id": 202}
        raise AssertionError(f"unexpected query: {query}")


def test_provider_mapping_repository_lists_records_and_summary() -> None:
    database = FakeProviderMappingDatabase()
    repository = PostgresProviderEntityMappingRepository(database)

    result = repository.list_mappings(
        provider="football-data.org",
        entity_type="fixture",
        canonical_entity_id="fd_fixture_330299",
        limit=50,
    )

    assert len(result.items) == 1
    assert result.items[0].mapping_id == 101
    assert result.items[0].provider_entity_id == "330299"
    assert result.items[0].canonical_entity_id == "fd_fixture_330299"
    assert result.items[0].confidence == 1.0
    assert len(result.summary) == 1
    assert result.summary[0].mapping_count == 1
    assert database.fetch_all_calls == [
        (
            LIST_PROVIDER_ENTITY_MAPPINGS_QUERY,
            {
                "provider": "football-data.org",
                "entity_type": "fixture",
                "canonical_entity_id": "fd_fixture_330299",
                "limit": 50,
            },
        ),
        (
            PROVIDER_ENTITY_MAPPING_SUMMARY_QUERY,
            {
                "provider": "football-data.org",
                "entity_type": "fixture",
                "canonical_entity_id": "fd_fixture_330299",
                "limit": 50,
            },
        ),
    ]


def test_provider_mapping_repository_upserts_mapping() -> None:
    database = FakeProviderMappingDatabase()
    repository = PostgresProviderEntityMappingRepository(database)

    mapping_id = repository.upsert_mapping(
        ProviderEntityMappingUpsert(
            provider="the-odds-api",
            entity_type="fixture",
            provider_entity_id="event-1",
            canonical_entity_id="fd_fixture_330299",
            confidence=0.99,
        )
    )

    assert mapping_id == 202
    assert database.fetch_one_calls[0][1] == {
        "provider": "the-odds-api",
        "entity_type": "fixture",
        "provider_entity_id": "event-1",
        "canonical_entity_id": "fd_fixture_330299",
        "confidence": 0.99,
    }


def test_provider_mapping_repository_lists_fixture_mappings_for_competition() -> None:
    database = FakeProviderMappingDatabase()
    repository = PostgresProviderEntityMappingRepository(database)

    result = repository.list_fixture_mappings_for_competition(
        provider="the-odds-api",
        competition_id="EPL",
        min_confidence=0.82,
        limit=20,
    )

    assert len(result) == 1
    assert result[0].provider == "the-odds-api"
    assert result[0].provider_entity_id == "event_123"
    assert result[0].canonical_entity_id == "fd_fixture_330299"
    assert database.fetch_all_calls[-1] == (
        LIST_PROVIDER_FIXTURE_MAPPINGS_BY_COMPETITION_QUERY,
        {
            "provider": "the-odds-api",
            "competition_id": "EPL",
            "min_confidence": 0.82,
            "limit": 20,
        },
    )
