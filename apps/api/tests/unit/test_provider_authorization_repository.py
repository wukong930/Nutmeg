from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.authorization_repository import (
    LIST_PROVIDER_AUTHORIZATIONS_QUERY,
    PostgresProviderAuthorizationRepository,
)


class FakeProviderAuthorizationDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows


def test_postgres_provider_authorization_repository_maps_registry_metadata() -> None:
    database = FakeProviderAuthorizationDatabase([_api_football_row()])
    repository = PostgresProviderAuthorizationRepository(database)

    records = repository.list_authorizations()

    assert database.calls == [(LIST_PROVIDER_AUTHORIZATIONS_QUERY, {})]
    assert len(records) == 1
    record = records[0]
    assert record.provider_name == "api-football"
    assert record.capabilities == ("competitions", "seasons", "fixtures", "results")
    assert record.terms_checked_at_utc == datetime(2026, 5, 8, tzinfo=UTC)
    assert record.allowed_use == "fixture_result_fallback_research_dry_run"
    assert record.rate_limit == "free_plan_provider_defined"
    assert record.historical_data_allowed is False
    assert record.redistribution_allowed is False
    assert record.terms_url == "https://www.api-football.com/terms"
    assert record.last_reviewed_at == datetime(2026, 5, 8, 9, 0, tzinfo=UTC)
    assert record.next_review_due_at == datetime(2026, 11, 4, tzinfo=UTC)
    assert record.owner == "nutmeg-ops"
    assert record.api_key_env_var == "API_FOOTBALL_API_KEY"


def _api_football_row() -> Mapping[str, object]:
    return {
        "provider_name": "api-football",
        "status": "pending_review",
        "capabilities_json": '["competitions", "seasons", "fixtures", "results"]',
        "terms_checked_at_utc": "2026-05-08T00:00:00+00:00",
        "commercial_use_allowed": False,
        "retention_allowed": False,
        "allowed_use": "fixture_result_fallback_research_dry_run",
        "rate_limit": "free_plan_provider_defined",
        "historical_data_allowed": False,
        "redistribution_allowed": False,
        "terms_url": "https://www.api-football.com/terms",
        "last_reviewed_at": "2026-05-08T09:00:00+00:00",
        "next_review_due_at": "2026-11-04T00:00:00+00:00",
        "owner": "nutmeg-ops",
        "api_key_env_var": "API_FOOTBALL_API_KEY",
        "notes": "Candidate broad fixture/result fallback.",
    }
