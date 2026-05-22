from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PersistedRecommendationRunSnapshot,
    RecommendationPrematchChangeReportOptions,
    RecommendationProviderIncidentEventRecord,
    build_recommendation_prematch_change_report,
    run_recommendation_prematch_change_report,
)
from nutmeg.recommendations.incidents import (
    LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY,
)
from nutmeg.recommendations.lifecycle_replay import (
    LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
)
from nutmeg.recommendations.prematch_report import (
    INSERT_RECOMMENDATION_PREMATCH_CHANGE_REPORT_QUERY,
)


class FakePrematchReportDatabase:
    def __init__(
        self,
        *,
        run_rows: Sequence[DatabaseRow],
        incident_rows: Sequence[DatabaseRow],
    ) -> None:
        self.run_rows = list(run_rows)
        self.incident_rows = list(incident_rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY:
            return self.run_rows
        if query in {
            LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
            LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
            LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
            LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
        }:
            return []
        if query == LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY:
            return self.incident_rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_PREMATCH_CHANGE_REPORT_QUERY:
            return {
                "recommendation_prematch_change_report_id": 901,
                "created_at": _dt(2026, 5, 1, 13),
                "updated_at": _dt(2026, 5, 1, 13),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_build_prematch_change_report_summarizes_replay_and_incidents() -> None:
    options = _options()
    snapshots = [
        _snapshot(1, "run-1", _dt(2026, 5, 1, 10), ["A", "B"]),
        _snapshot(2, "run-2", _dt(2026, 5, 1, 12), ["A", "C"]),
    ]
    incident = _incident("incident-A", fixture_id="A", severity="critical")

    report = build_recommendation_prematch_change_report(
        snapshots,
        [incident],
        options=options,
    )

    assert report.report_key.startswith("prematch_change:")
    assert report.checkpoint_count == 2
    assert report.summary_json["stage_count"] == 2
    assert report.summary_json["changed_stage_count"] == 1
    assert report.summary_json["incident_count"] == 1
    assert report.summary_json["critical_incident_count"] == 1
    assert report.summary_json["final_selected_fixture_ids"] == ["A", "C"]
    assert report.summary_json["continuation_stage_count"] == 2
    assert report.summary_json["final_continuation_fixture_ids"] == ["A", "C"]
    assert report.summary_json["final_remaining_open_leg_count"] == 2
    assert report.provider_incidents[0].provider_incident_key == "incident-A"


def test_prematch_change_report_runner_reads_sources_and_persists_report() -> None:
    database = FakePrematchReportDatabase(
        run_rows=[
            _run_row(11, "run-11", _dt(2026, 5, 1, 10), ["A", "B"]),
            _run_row(12, "run-12", _dt(2026, 5, 1, 12), ["A", "C"]),
        ],
        incident_rows=[_incident_row("incident-A", "A", "critical")],
    )

    result = run_recommendation_prematch_change_report(
        database,
        options=_options(dry_run=False),
    )

    assert result.dry_run is False
    assert result.report.summary_json["stage_count"] == 2
    assert result.report.summary_json["incident_count"] == 1
    assert result.stored_report is not None
    assert result.stored_report.recommendation_prematch_change_report_id == 901
    assert [query for query, _params in database.fetch_all_calls] == [
        LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
        LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY,
    ]
    assert database.fetch_one_calls[0][0] == INSERT_RECOMMENDATION_PREMATCH_CHANGE_REPORT_QUERY
    params = database.fetch_one_calls[0][1]
    assert params["stage_count"] == 2
    assert params["changed_stage_count"] == 1
    assert params["incident_count"] == 1
    assert params["critical_incident_count"] == 1
    assert '"continuation_stage_count":2' in str(params["report_json"])
    assert '"final_remaining_open_leg_count":2' in str(params["report_json"])


def _options(*, dry_run: bool = True) -> RecommendationPrematchChangeReportOptions:
    return RecommendationPrematchChangeReportOptions(
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 2, 0),
        pass_type="2x1",
        mode="single",
        strategy="accuracy_first",
        dry_run=dry_run,
        limit=50,
    )


def _snapshot(
    recommendation_run_id: int,
    run_key: str,
    as_of_time_utc: datetime,
    selected_fixture_ids: list[str],
) -> PersistedRecommendationRunSnapshot:
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=as_of_time_utc,
        strategy="accuracy_first",
        pass_type="2x1",
        mode="single",
        status="current",
        unit_stake=2.0,
        max_budget=20.0,
        candidate_count=len(selected_fixture_ids),
        excluded_candidate_count=0,
        selected_fixture_ids=selected_fixture_ids,
        source="unit-test",
        created_at=as_of_time_utc,
    )


def _run_row(
    recommendation_run_id: int,
    run_key: str,
    as_of_time_utc: datetime,
    selected_fixture_ids: list[str],
) -> DatabaseRow:
    return {
        "recommendation_run_id": recommendation_run_id,
        "run_key": run_key,
        "as_of_time_utc": as_of_time_utc,
        "strategy": "accuracy_first",
        "pass_type": "2x1",
        "mode": "single",
        "status": "current",
        "unit_stake": 2,
        "max_budget": 20,
        "candidate_count": len(selected_fixture_ids),
        "excluded_candidate_count": 0,
        "selected_fixture_ids_json": selected_fixture_ids,
        "locked_fixture_ids_json": [],
        "total_score": 0.80,
        "parlay_evaluation_json": {},
        "explanation_json": {},
        "source": "unit-test",
        "created_at": as_of_time_utc,
    }


def _incident(
    key: str,
    *,
    fixture_id: str,
    severity: str,
) -> RecommendationProviderIncidentEventRecord:
    return RecommendationProviderIncidentEventRecord(
        recommendation_provider_incident_event_id=701,
        provider_incident_key=key,
        provider_name="sportmonks",
        fixture_id=fixture_id,
        competition_id="EPL",
        incident_type="player_availability_injured",
        severity=severity,  # type: ignore[arg-type]
        event_time_utc=_dt(2026, 5, 1, 11),
        observed_at_utc=_dt(2026, 5, 1, 11),
        status="open",
        affects_recommendations=True,
        excluded_fixture_ids=[fixture_id],
        summary="player injured",
        created_at=_dt(2026, 5, 1, 11),
        updated_at=_dt(2026, 5, 1, 11),
    )


def _incident_row(key: str, fixture_id: str, severity: str) -> DatabaseRow:
    return {
        "recommendation_provider_incident_event_id": 701,
        "provider_incident_key": key,
        "provider_name": "sportmonks",
        "provider_runtime_incident_report_id": None,
        "fixture_id": fixture_id,
        "competition_id": "EPL",
        "incident_type": "player_availability_injured",
        "severity": severity,
        "event_time_utc": _dt(2026, 5, 1, 11),
        "observed_at_utc": _dt(2026, 5, 1, 11),
        "status": "open",
        "affects_recommendations": True,
        "excluded_fixture_ids_json": [fixture_id],
        "summary": "player injured",
        "payload_json": {},
        "created_at": _dt(2026, 5, 1, 11),
        "updated_at": _dt(2026, 5, 1, 11),
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
