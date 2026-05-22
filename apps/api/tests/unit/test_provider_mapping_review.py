from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.mapping_repository import ProviderEntityMappingRecord
from nutmeg.providers.mapping_review import (
    INSERT_PROVIDER_MAPPING_REVIEW_RUN_QUERY,
    LIST_PROVIDER_MAPPING_REVIEW_RUNS_QUERY,
    PostgresProviderMappingReviewRunRepository,
    ProviderMappingReviewOptions,
    review_provider_entity_mappings,
)


class FakeProviderMappingReviewDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_MAPPING_REVIEW_RUN_QUERY:
            return _review_run_row(
                provider=params["provider"],
                entity_type=params["entity_type"],
                canonical_entity_id=params["canonical_entity_id"],
                checked_mapping_count=params["checked_mapping_count"],
                issue_count=params["issue_count"],
                critical_count=params["critical_count"],
                warning_count=params["warning_count"],
                info_count=params["info_count"],
                issues_json=params["issues_json"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_MAPPING_REVIEW_RUNS_QUERY:
            return [_review_run_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_mapping_review_flags_collision_low_confidence_and_stale() -> None:
    result = review_provider_entity_mappings(
        [
            _mapping(1, "fixture_a", "fix_a", confidence=0.99),
            _mapping(2, "fixture_b", "fix_a", confidence=0.41),
            _mapping(
                3,
                "fixture_old",
                "fix_old",
                confidence=1.0,
                updated_at=datetime(2025, 1, 1, tzinfo=UTC),
            ),
        ],
        options=ProviderMappingReviewOptions(
            low_confidence_threshold=0.95,
            stale_after_days=180,
            as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
        ),
    )

    assert result.checked_mapping_count == 3
    assert result.issue_count == 3
    assert result.critical_count == 2
    assert result.info_count == 1
    assert [issue.issue_type for issue in result.issues] == [
        "low_confidence",
        "same_provider_canonical_collision",
        "stale_mapping",
    ]
    assert result.issues[0].severity == "critical"
    assert result.issues[1].provider_entity_ids == ["fixture_a", "fixture_b"]
    assert result.issues[2].recommended_action == (
        "refresh_mapping_evidence_before_production_use"
    )


def test_provider_mapping_review_run_repository_saves_and_lists_review_runs() -> None:
    database = FakeProviderMappingReviewDatabase()
    review = review_provider_entity_mappings(
        [_mapping(1, "fixture_a", "fix_a", confidence=0.4)],
        options=ProviderMappingReviewOptions(
            low_confidence_threshold=0.95,
            stale_after_days=180,
            as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
        ),
        dry_run=False,
    )
    repository = PostgresProviderMappingReviewRunRepository(database)

    saved = repository.save_review(
        result=review,
        provider="football-data.org",
        entity_type="fixture",
        requested_by="admin_api",
    )
    listed = repository.list_latest(limit=5)

    assert saved.provider_mapping_review_run_id == 301
    assert saved.issue_count == 1
    assert saved.issues[0].issue_type == "low_confidence"
    assert listed[0].provider_mapping_review_run_id == 301
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_MAPPING_REVIEW_RUNS_QUERY, {"limit": 5})
    ]


def _mapping(
    mapping_id: int,
    provider_entity_id: str,
    canonical_entity_id: str,
    *,
    confidence: float,
    updated_at: datetime | None = None,
) -> ProviderEntityMappingRecord:
    timestamp = updated_at or datetime(2026, 5, 7, tzinfo=UTC)
    return ProviderEntityMappingRecord(
        mapping_id=mapping_id,
        provider="football-data.org",
        entity_type="fixture",
        provider_entity_id=provider_entity_id,
        canonical_entity_id=canonical_entity_id,
        confidence=confidence,
        created_at_utc=timestamp,
        updated_at_utc=timestamp,
    )


def _review_run_row(**overrides: object) -> DatabaseRow:
    row = {
        "provider_mapping_review_run_id": 301,
        "provider": "football-data.org",
        "entity_type": "fixture",
        "canonical_entity_id": None,
        "low_confidence_threshold": 0.95,
        "stale_after_days": 180,
        "checked_mapping_count": 1,
        "issue_count": 1,
        "critical_count": 1,
        "warning_count": 0,
        "info_count": 0,
        "issues_json": (
            '[{"issue_id":"abc","issue_type":"low_confidence","severity":"critical",'
            '"provider":"football-data.org","entity_type":"fixture",'
            '"canonical_entity_id":"fix_a","provider_entity_ids":["fixture_a"],'
            '"mapping_ids":[1],"confidence_min":0.4,'
            '"latest_updated_at_utc":"2026-05-07T00:00:00Z",'
            '"reasons":["confidence_below_0.95"],'
            '"recommended_action":"review_provider_entity_match"}]'
        ),
        "requested_by": "admin_api",
        "created_at": datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        "metadata_json": '{"low_confidence_threshold":0.95,"stale_after_days":180}',
    }
    row.update(overrides)
    return row
