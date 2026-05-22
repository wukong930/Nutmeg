from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.conflicts import (
    FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY,
    INSERT_PROVIDER_CONFLICT_EVENT_QUERY,
    INSERT_PROVIDER_OBSERVATION_QUERY,
    LIST_PROVIDER_CONFLICT_EVENTS_QUERY,
    LIST_PROVIDER_CONFLICT_QUALITY_IMPACTS_QUERY,
    LIST_PROVIDER_OBSERVATIONS_QUERY,
    UPDATE_PROVIDER_CONFLICT_RESOLUTION_QUERY,
    PostgresProviderConflictEventRepository,
    PostgresProviderObservationRepository,
    ProviderObservation,
    detect_provider_observation_conflicts,
    evaluate_mapping_review_conflicts,
)
from nutmeg.providers.mapping_repository import ProviderEntityMappingRecord
from nutmeg.providers.mapping_review import (
    ProviderMappingReviewOptions,
    review_provider_entity_mappings,
)


class FakeProviderConflictDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.find_existing_open_event = False

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY:
            if self.find_existing_open_event:
                return _conflict_event_row(
                    conflict_type=params["conflict_type"],
                    entity_type=params["entity_type"],
                    canonical_entity_id=params["canonical_entity_id"],
                    provider_names_json=params["provider_names_json"],
                    provider_entity_ids_json=params["provider_entity_ids_json"],
                )
            return None
        if query == INSERT_PROVIDER_CONFLICT_EVENT_QUERY:
            return _conflict_event_row(
                conflict_type=params["conflict_type"],
                severity=params["severity"],
                entity_type=params["entity_type"],
                canonical_entity_id=params["canonical_entity_id"],
                provider_names_json=params["provider_names_json"],
                provider_entity_ids_json=params["provider_entity_ids_json"],
                trusted_provider=params["trusted_provider"],
                data_quality_score_delta=params["data_quality_score_delta"],
                evidence_json=params["evidence_json"],
                recommended_action=params["recommended_action"],
                requested_by=params["requested_by"],
            )
        if query == INSERT_PROVIDER_OBSERVATION_QUERY:
            return _provider_observation_row(
                provider_name=params["provider_name"],
                capability=params["capability"],
                entity_type=params["entity_type"],
                canonical_entity_id=params["canonical_entity_id"],
                provider_entity_id=params["provider_entity_id"],
                field_name=params["field_name"],
                observed_value=params["observed_value"],
                observed_at_utc=params["observed_at_utc"],
                confidence=params["confidence"],
                payload_id=params["payload_id"],
                metadata_json=params["metadata_json"],
            )
        if query == UPDATE_PROVIDER_CONFLICT_RESOLUTION_QUERY:
            return _conflict_event_row(
                provider_conflict_event_id=params["provider_conflict_event_id"],
                resolution_status=params["resolution_status"],
                resolved_at=(
                    None
                    if params["resolution_status"] == "open"
                    else datetime(2026, 5, 8, 3, 0, tzinfo=UTC)
                ),
                evidence_json=params["resolution_metadata_json"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_CONFLICT_EVENTS_QUERY:
            return [_conflict_event_row()]
        if query == LIST_PROVIDER_CONFLICT_QUALITY_IMPACTS_QUERY:
            return [
                {
                    "canonical_entity_id": "fix_a",
                    "conflict_count": 2,
                    "data_quality_score_delta": -5.0,
                    "latest_conflict_at": datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
                }
            ]
        if query == LIST_PROVIDER_OBSERVATIONS_QUERY:
            return [_provider_observation_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_mapping_review_conflicts_create_quality_penalty_events() -> None:
    mapping_review = review_provider_entity_mappings(
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

    result = evaluate_mapping_review_conflicts(mapping_review)

    assert result.checked_issue_count == 3
    assert result.conflict_count == 2
    assert result.critical_count == 2
    assert result.data_quality_score_delta == -7.0
    assert result.provider_consistency_after_conflicts == 0.3
    assert [event.conflict_type for event in result.events] == [
        "provider_mapping_conflict",
        "provider_mapping_conflict",
    ]
    assert result.events[0].trusted_provider == "football-data.org"
    assert result.events[0].evidence_json["mapping_issue_type"] == "low_confidence"


def test_provider_observation_conflict_uses_trusted_priority() -> None:
    events = detect_provider_observation_conflicts(
        [
            _observation("football-data.org", "fixtures", "kickoff_time", "2026-05-08T18:00Z"),
            _observation("sportmonks", "fixtures", "kickoff_time", "2026-05-08T19:00Z"),
        ]
    )

    assert len(events) == 1
    assert events[0].conflict_type == "provider_observation_conflict"
    assert events[0].severity == "warning"
    assert events[0].trusted_provider == "football-data.org"
    assert events[0].data_quality_score_delta == -1.5
    assert events[0].evidence_json["field_name"] == "kickoff_time"


def test_provider_observation_conflict_ignores_single_provider_variance() -> None:
    events = detect_provider_observation_conflicts(
        [
            _observation("the-odds-api", "odds", "fair_probability:1x2:none:none:home", "0.44"),
            _observation("the-odds-api", "odds", "fair_probability:1x2:none:none:home", "0.45"),
        ]
    )

    assert events == []


def test_provider_conflict_repository_saves_and_lists_events() -> None:
    database = FakeProviderConflictDatabase()
    mapping_review = review_provider_entity_mappings(
        [_mapping(1, "fixture_a", "fix_a", confidence=0.4)],
        options=ProviderMappingReviewOptions(
            low_confidence_threshold=0.95,
            stale_after_days=180,
            as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
        ),
    )
    result = evaluate_mapping_review_conflicts(mapping_review, dry_run=False)
    repository = PostgresProviderConflictEventRepository(database)

    saved = repository.save_events(result=result, requested_by="admin_api")
    listed = repository.list_latest(status="open", limit=5)

    assert saved[0].provider_conflict_event_id == 501
    assert saved[0].source_issue_id == result.events[0].source_issue_id
    assert saved[0].resolution_status == "open"
    assert listed[0].provider_conflict_event_id == 501
    assert database.fetch_one_calls[0][0] == FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY
    assert database.fetch_one_calls[1][0] == INSERT_PROVIDER_CONFLICT_EVENT_QUERY
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_CONFLICT_EVENTS_QUERY, {"status": "open", "limit": 5})
    ]


def test_provider_conflict_repository_reuses_existing_open_events() -> None:
    database = FakeProviderConflictDatabase()
    database.find_existing_open_event = True
    mapping_review = review_provider_entity_mappings(
        [_mapping(1, "fixture_a", "fix_a", confidence=0.4)],
        options=ProviderMappingReviewOptions(
            low_confidence_threshold=0.95,
            stale_after_days=180,
            as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
        ),
    )
    result = evaluate_mapping_review_conflicts(mapping_review, dry_run=False)
    repository = PostgresProviderConflictEventRepository(database)

    saved = repository.save_events(result=result, requested_by="admin_api")

    assert saved[0].provider_conflict_event_id == 501
    assert [call[0] for call in database.fetch_one_calls] == [
        FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY
    ]


def test_provider_conflict_repository_lists_quality_impacts() -> None:
    database = FakeProviderConflictDatabase()
    repository = PostgresProviderConflictEventRepository(database)

    impacts = repository.list_quality_impacts(fixture_ids=["fix_a", "fix_b"])

    assert impacts["fix_a"].conflict_count == 2
    assert impacts["fix_a"].data_quality_score_delta == -5.0
    assert impacts["fix_a"].provider_consistency_score == 0.5
    assert database.fetch_all_calls == [
        (
            LIST_PROVIDER_CONFLICT_QUALITY_IMPACTS_QUERY,
            {"fixture_ids": ["fix_a", "fix_b"]},
        )
    ]


def test_provider_conflict_repository_updates_resolution_status() -> None:
    database = FakeProviderConflictDatabase()
    repository = PostgresProviderConflictEventRepository(database)

    record = repository.update_resolution_status(
        provider_conflict_event_id=501,
        resolution_status="resolved",
        requested_by="admin_api",
        resolution_note="trusted provider payload reviewed",
    )

    assert record is not None
    assert record.resolution_status == "resolved"
    assert record.resolved_at_utc == datetime(2026, 5, 8, 3, 0, tzinfo=UTC)
    query, params = database.fetch_one_calls[0]
    assert query == UPDATE_PROVIDER_CONFLICT_RESOLUTION_QUERY
    assert params["provider_conflict_event_id"] == 501
    assert params["resolution_status"] == "resolved"
    assert "trusted provider payload reviewed" in str(params["resolution_metadata_json"])


def test_provider_observation_repository_saves_and_lists_recent_observations() -> None:
    database = FakeProviderConflictDatabase()
    repository = PostgresProviderObservationRepository(database)

    saved = repository.save_observations(
        [
            _observation(
                "football-data.org",
                "fixtures",
                "kickoff_time_utc",
                "2026-05-08T18:00:00Z",
            )
        ]
    )
    listed = repository.list_recent(
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        lookback_hours=72,
        provider_name="football-data.org",
        capability="fixtures",
        entity_type="fixture",
        canonical_entity_id="fix_a",
        limit=10,
    )

    assert saved[0].provider_observation_id == 701
    assert saved[0].value == "2026-05-08T18:00:00Z"
    assert listed[0].provider_name == "football-data.org"
    assert database.fetch_all_calls[0][0] == LIST_PROVIDER_OBSERVATIONS_QUERY
    assert database.fetch_all_calls[0][1]["provider_name"] == "football-data.org"
    assert database.fetch_all_calls[0][1]["limit"] == 10


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


def _observation(
    provider_name: str,
    capability: str,
    field_name: str,
    value: str,
) -> ProviderObservation:
    return ProviderObservation(
        provider_name=provider_name,
        capability=capability,
        entity_type="fixture",
        canonical_entity_id="fix_a",
        field_name=field_name,
        value=value,
        observed_at_utc=datetime(2026, 5, 8, tzinfo=UTC),
        provider_entity_id=f"{provider_name}:fix_a",
    )


def _conflict_event_row(**overrides: object) -> DatabaseRow:
    row = {
        "provider_conflict_event_id": 501,
        "source_review_run_id": None,
        "conflict_type": "provider_mapping_conflict",
        "severity": "critical",
        "entity_type": "fixture",
        "canonical_entity_id": "fix_a",
        "provider_names_json": '["football-data.org"]',
        "provider_entity_ids_json": '["fixture_a"]',
        "trusted_provider": "football-data.org",
        "resolution_status": "open",
        "data_quality_score_delta": -3.5,
        "evidence_json": (
            '{"source_issue_id":"abc","mapping_issue_type":"low_confidence",'
            '"mapping_ids":[1],"confidence_min":0.4}'
        ),
        "recommended_action": "review_provider_entity_match",
        "requested_by": "admin_api",
        "created_at": datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        "resolved_at": None,
    }
    row.update(overrides)
    return row


def _provider_observation_row(**overrides: object) -> DatabaseRow:
    row = {
        "provider_observation_id": 701,
        "provider_name": "football-data.org",
        "capability": "fixtures",
        "entity_type": "fixture",
        "canonical_entity_id": "fix_a",
        "provider_entity_id": "provider-fix-a",
        "field_name": "kickoff_time_utc",
        "observed_value": "2026-05-08T18:00:00Z",
        "observed_at_utc": datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        "confidence": 1.0,
        "payload_id": 11,
        "metadata_json": "{}",
        "created_at": datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
    }
    row.update(overrides)
    return row
