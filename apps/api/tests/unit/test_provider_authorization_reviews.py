from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.authorization_reviews import (
    LIST_PROVIDER_AUTHORIZATION_REVIEWS_QUERY,
    UPSERT_PROVIDER_AUTHORIZATION_REVIEW_QUERY,
    PostgresProviderAuthorizationReviewRepository,
    ProviderAuthorizationReviewInput,
)


class FakeProviderAuthorizationReviewDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = list(rows)
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return self.rows[0] if self.rows else None

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        return self.rows


def test_provider_authorization_review_repository_records_review_and_updates_snapshot() -> None:
    database = FakeProviderAuthorizationReviewDatabase([_review_row()])
    repository = PostgresProviderAuthorizationReviewRepository(database)

    record = repository.record_review(
        ProviderAuthorizationReviewInput(
            provider_name="api-football",
            review_reference="manual-2026-05-08",
            review_status="research_only",
            reviewed_by="ops-reviewer",
            reviewed_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            terms_url="https://www.api-football.com/terms",
            allowed_use="fixture_result_fallback_research_dry_run",
            rate_limit="free_plan_provider_defined",
            next_review_due_at=datetime(2026, 11, 4, tzinfo=UTC),
            evidence_json={"source": "manual_terms_review"},
            notes="Free plan is research-only until retention terms are approved.",
        )
    )

    assert database.fetch_one_calls[0][0] == UPSERT_PROVIDER_AUTHORIZATION_REVIEW_QUERY
    params = database.fetch_one_calls[0][1]
    assert params["provider_name"] == "api-football"
    assert params["review_reference"] == "manual-2026-05-08"
    assert params["review_status"] == "research_only"
    assert params["owner"] == "nutmeg-ops"
    assert "manual_terms_review" in str(params["evidence_json"])
    assert record.provider_name == "api-football"
    assert record.review_status == "research_only"
    assert record.reviewed_at == datetime(2026, 5, 8, 9, 0, tzinfo=UTC)
    assert record.next_review_due_at == datetime(2026, 11, 4, tzinfo=UTC)


def test_provider_authorization_review_repository_lists_recent_reviews() -> None:
    database = FakeProviderAuthorizationReviewDatabase([_review_row()])
    repository = PostgresProviderAuthorizationReviewRepository(database)

    records = repository.list_latest(limit=25)

    assert database.fetch_all_calls == [
        (LIST_PROVIDER_AUTHORIZATION_REVIEWS_QUERY, {"limit": 25})
    ]
    assert records[0].terms_url == "https://www.api-football.com/terms"
    assert records[0].evidence_json == {"source": "manual_terms_review"}


def _review_row() -> Mapping[str, object]:
    return {
        "provider_authorization_review_id": 12,
        "provider_name": "api-football",
        "review_reference": "manual-2026-05-08",
        "review_status": "research_only",
        "reviewed_by": "ops-reviewer",
        "reviewed_at": "2026-05-08T09:00:00+00:00",
        "terms_url": "https://www.api-football.com/terms",
        "terms_version_hash": None,
        "allowed_use": "fixture_result_fallback_research_dry_run",
        "commercial_use_allowed": False,
        "retention_allowed": False,
        "historical_data_allowed": False,
        "redistribution_allowed": False,
        "rate_limit": "free_plan_provider_defined",
        "next_review_due_at": "2026-11-04T00:00:00+00:00",
        "evidence_json": '{"source":"manual_terms_review"}',
        "notes": "Free plan is research-only.",
        "created_at": "2026-05-08T09:00:00+00:00",
    }
