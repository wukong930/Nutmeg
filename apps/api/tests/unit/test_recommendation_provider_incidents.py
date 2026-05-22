from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PostgresRecommendationProviderIncidentRepository,
    RecommendationProviderIncidentEventInput,
    RecommendationProviderIncidentEventRecord,
    RecommendationProviderIncidentQueryOptions,
    apply_provider_incidents_to_backtest_checkpoints,
)
from nutmeg.recommendations.incidents import (
    INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY,
    LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY,
)
from nutmeg.recommendations.lifecycle_backtest import (
    PrematchRecommendationBacktestCheckpoint,
)


class FakeRecommendationProviderIncidentDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = list(rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY:
            return self.rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY:
            return {
                **params,
                "recommendation_provider_incident_event_id": 77,
                "created_at": _dt(2026, 5, 1, 10),
                "updated_at": _dt(2026, 5, 1, 10),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_provider_incident_repository_records_and_lists_raw_recommendation_events() -> None:
    database = FakeRecommendationProviderIncidentDatabase(
        [
            _incident_row(
                "provider:lineup:A",
                fixture_id="A",
                excluded_fixture_ids=["A"],
            )
        ]
    )
    repository = PostgresRecommendationProviderIncidentRepository(database)

    recorded = repository.record_event(
        RecommendationProviderIncidentEventInput(
            provider_incident_key="provider:lineup:A",
            provider_name="football-data",
            fixture_id="A",
            competition_id="EPL",
            incident_type="late_lineup_risk",
            severity="warning",
            event_time_utc=_dt(2026, 5, 1, 9),
            observed_at_utc=_dt(2026, 5, 1, 9),
            excluded_fixture_ids=["A"],
            summary="key player absent",
            payload_json={"source": "unit-test"},
        )
    )
    events = repository.list_events(
        options=RecommendationProviderIncidentQueryOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 2, 0),
            fixture_ids=("A",),
            competition_id="EPL",
            limit=10,
        )
    )

    assert recorded.recommendation_provider_incident_event_id == 77
    assert recorded.excluded_fixture_ids == ["A"]
    assert events[0].provider_incident_key == "provider:lineup:A"
    assert events[0].affected_fixture_ids() == ["A"]
    record_params = database.fetch_one_calls[0][1]
    assert record_params["excluded_fixture_ids_json"] == '["A"]'
    list_params = database.fetch_all_calls[0][1]
    assert list_params["fixture_ids"] == ["A"]
    assert list_params["competition_id"] == "EPL"
    assert list_params["only_affecting_recommendations"] is True


def test_apply_provider_incidents_to_checkpoints_only_uses_active_past_events() -> None:
    checkpoints = [
        PrematchRecommendationBacktestCheckpoint(
            checkpoint_id="before",
            as_of_time_utc=_dt(2026, 5, 1, 8),
            candidates=[],
        ),
        PrematchRecommendationBacktestCheckpoint(
            checkpoint_id="after",
            as_of_time_utc=_dt(2026, 5, 1, 12),
            candidates=[],
            excluded_fixture_ids=["B"],
            incident_notes={"B": "existing_note"},
        ),
    ]
    incidents = [
        _incident_record("open-A", event_time_utc=_dt(2026, 5, 1, 9), fixture_id="A"),
        _incident_record(
            "resolved-C",
            event_time_utc=_dt(2026, 5, 1, 9),
            fixture_id="C",
            status="resolved",
        ),
        _incident_record(
            "future-D",
            event_time_utc=_dt(2026, 5, 1, 13),
            fixture_id="D",
        ),
    ]

    updated = apply_provider_incidents_to_backtest_checkpoints(checkpoints, incidents)

    assert updated[0].excluded_fixture_ids == []
    assert updated[1].excluded_fixture_ids == ["B", "A"]
    assert updated[1].incident_notes == {
        "B": "existing_note",
        "A": "late_lineup_risk",
    }
    assert updated[1].metadata_json["provider_incident_event_keys"] == ["open-A"]


def _incident_row(
    provider_incident_key: str,
    *,
    fixture_id: str,
    excluded_fixture_ids: list[str],
) -> DatabaseRow:
    return {
        "recommendation_provider_incident_event_id": 77,
        "provider_incident_key": provider_incident_key,
        "provider_name": "football-data",
        "provider_runtime_incident_report_id": None,
        "fixture_id": fixture_id,
        "competition_id": "EPL",
        "incident_type": "late_lineup_risk",
        "severity": "warning",
        "event_time_utc": _dt(2026, 5, 1, 9),
        "observed_at_utc": _dt(2026, 5, 1, 9),
        "status": "open",
        "affects_recommendations": True,
        "excluded_fixture_ids_json": excluded_fixture_ids,
        "summary": "key player absent",
        "payload_json": {"source": "unit-test"},
        "created_at": _dt(2026, 5, 1, 10),
        "updated_at": _dt(2026, 5, 1, 10),
    }


def _incident_record(
    provider_incident_key: str,
    *,
    event_time_utc: datetime,
    fixture_id: str,
    status: str = "open",
) -> RecommendationProviderIncidentEventRecord:
    return RecommendationProviderIncidentEventRecord(
        recommendation_provider_incident_event_id=77,
        provider_incident_key=provider_incident_key,
        provider_name="football-data",
        fixture_id=fixture_id,
        competition_id="EPL",
        incident_type="late_lineup_risk",
        severity="warning",
        event_time_utc=event_time_utc,
        observed_at_utc=event_time_utc,
        status=status,  # type: ignore[arg-type]
        affects_recommendations=True,
        excluded_fixture_ids=[],
        summary="late_lineup_risk",
        created_at=event_time_utc,
        updated_at=event_time_utc,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
