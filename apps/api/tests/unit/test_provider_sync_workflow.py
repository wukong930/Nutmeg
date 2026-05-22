from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.predictions.jobs import PredictionJobResult
from nutmeg.predictions.workflow import PrematchWorkflowOptions, PrematchWorkflowResult
from nutmeg.providers.availability_repository import AvailabilitySnapshotWriteSummary
from nutmeg.providers.availability_sync import SportMonksFixtureAvailabilitySyncResult
from nutmeg.providers.canonical_repository import CanonicalFixtureWriteSummary
from nutmeg.providers.conflicts import (
    LIST_PROVIDER_OBSERVATIONS_QUERY,
    ProviderConflictEvaluationResult,
)
from nutmeg.providers.mock_dry_run import MOCK_PROVIDER_DRY_RUN_WARNING
from nutmeg.providers.odds_repository import OddsSnapshotWriteSummary
from nutmeg.providers.odds_sync import TheOddsApiEventOddsSyncResult
from nutmeg.providers.repository import ProviderSyncRunRecord, StoredRawProviderPayload
from nutmeg.providers.sync import FootballDataFixtureSyncResult
from nutmeg.providers.workflow import (
    COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
    FAIL_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
    GET_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
    INSERT_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
    LIST_PROVIDER_SYNC_WORKFLOW_RUNS_QUERY,
    FootballDataFixtureSyncTask,
    PostgresProviderSyncWorkflowRunRepository,
    ProviderSyncWorkflowOptions,
    SportMonksFixtureAvailabilitySyncTask,
    TheOddsApiEventOddsSyncTask,
    run_audited_provider_sync_workflow,
    run_provider_sync_workflow_conflict_detection,
)


class FakeProviderSyncWorkflowDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_SYNC_WORKFLOW_RUN_QUERY:
            return _workflow_row(status="running", completed_at=None)
        if query == COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY:
            return _workflow_row(
                status="completed",
                completed_at=datetime(2026, 5, 8, 4, 5, tzinfo=UTC),
                fixture_sync_run_id=params["fixture_sync_run_id"],
                odds_sync_run_ids_json=params["odds_sync_run_ids_json"],
                availability_sync_run_ids_json=params[
                    "availability_sync_run_ids_json"
                ],
                fixture_count=params["fixture_count"],
                odds_snapshot_count=params["odds_snapshot_count"],
                availability_snapshot_count=params["availability_snapshot_count"],
                raw_payload_ids_json=params["raw_payload_ids_json"],
                canonical_fixture_ids_json=params["canonical_fixture_ids_json"],
                prematch_workflow_run_id=params["prematch_workflow_run_id"],
                warnings_json=params["warnings_json"],
                duration_ms=75,
            )
        if query == FAIL_PROVIDER_SYNC_WORKFLOW_RUN_QUERY:
            return _workflow_row(
                status="failed",
                completed_at=datetime(2026, 5, 8, 4, 6, tzinfo=UTC),
                error_message=params["error_message"],
                warnings_json=params["warnings_json"],
                duration_ms=20,
            )
        if query == GET_PROVIDER_SYNC_WORKFLOW_RUN_QUERY:
            if params["provider_sync_workflow_run_id"] == 404:
                return None
            return _workflow_row(status="failed", error_message="provider timeout")
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_SYNC_WORKFLOW_RUNS_QUERY:
            return [_workflow_row(status="completed")]
        raise AssertionError(f"unexpected query: {query}")


class FakeProviderSyncWorkflowConflictDetectionDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_OBSERVATIONS_QUERY:
            if params["canonical_entity_id"] != "fd_fixture_1":
                return []
            return [
                _provider_observation_row(
                    901,
                    provider_name="football-data.org",
                    provider_entity_id="fd_event_1",
                    observed_value="2-1",
                ),
                _provider_observation_row(
                    902,
                    provider_name="sportmonks",
                    provider_entity_id="sm_fixture_1",
                    observed_value="1-1",
                ),
            ]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_sync_workflow_runs_child_syncs_and_records_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeProviderSyncWorkflowDatabase()
    fixture_calls: list[dict[str, object]] = []
    odds_calls: list[dict[str, object]] = []
    availability_calls: list[dict[str, object]] = []
    prematch_calls: list[dict[str, object]] = []

    def fake_fixture_sync(settings: Settings, **kwargs: object) -> FootballDataFixtureSyncResult:
        fixture_calls.append(kwargs)
        return FootballDataFixtureSyncResult(
            provider_competition_id="PL",
            canonical_competition_id="EPL",
            season="2025",
            sync_run=_sync_run("football-data.org", "fixtures", 11, entity_count=2),
            raw_payload=_raw_payload(31, provider="football-data.org"),
            canonical_write=CanonicalFixtureWriteSummary(
                fixtures=2,
                results=1,
                canonical_fixture_ids=["fd_fixture_1", "fd_fixture_2"],
            ),
        )

    def fake_odds_sync(settings: Settings, **kwargs: object) -> TheOddsApiEventOddsSyncResult:
        odds_calls.append(kwargs)
        return TheOddsApiEventOddsSyncResult(
            sport_key="soccer_epl",
            provider_event_id=str(kwargs["provider_event_id"]),
            canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
            sync_run=_sync_run("the-odds-api", "odds", 12, entity_count=5),
            raw_payload=_raw_payload(32, provider="the-odds-api"),
            odds_write=OddsSnapshotWriteSummary(
                odds_snapshots=5,
                provider_mappings=1,
                bookmaker_count=1,
                market_types=["1x2"],
                canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
            ),
            warnings=["odds_bookmaker_partial"],
        )

    def fake_availability_sync(
        settings: Settings,
        **kwargs: object,
    ) -> SportMonksFixtureAvailabilitySyncResult:
        availability_calls.append(kwargs)
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=str(kwargs["provider_fixture_id"]),
            canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
            provider_team_ids=["57", "64"],
            sync_run=_sync_run("sportmonks", "lineups_injuries", 13, entity_count=5),
            raw_payloads=[
                _raw_payload(33, provider="sportmonks"),
                _raw_payload(34, provider="sportmonks"),
            ],
            availability_write=AvailabilitySnapshotWriteSummary(
                lineup_snapshots=2,
                availability_snapshots=3,
                provider_mappings=4,
                player_mappings=3,
                canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
                canonical_team_ids=["fd_team_57", "fd_team_64"],
            ),
        )

    def fake_prematch_workflow(
        settings: Settings,
        *,
        options: object,
        requested_by: str | None,
    ) -> PrematchWorkflowResult:
        prematch_calls.append(
            {
                "dry_run": options.dry_run,
                "competition_id": options.competition_id,
                "requested_by": requested_by,
            }
        )
        return _prematch_result()

    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_football_data_fixture_sync",
        fake_fixture_sync,
    )
    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_the_odds_api_event_odds_sync",
        fake_odds_sync,
    )
    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_sportmonks_fixture_availability_sync",
        fake_availability_sync,
    )
    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_audited_prematch_workflow",
        fake_prematch_workflow,
    )

    result = run_audited_provider_sync_workflow(
        Settings(),
        options=ProviderSyncWorkflowOptions(
            dry_run=False,
            fixture_sync=FootballDataFixtureSyncTask(
                provider_competition_id="PL",
                canonical_competition_id="EPL",
                season="2025",
            ),
            odds_syncs=(
                TheOddsApiEventOddsSyncTask(
                    sport_key="soccer_epl",
                    provider_event_id="event_1",
                    canonical_fixture_id="fd_fixture_1",
                ),
            ),
            availability_syncs=(
                SportMonksFixtureAvailabilitySyncTask(
                    provider_fixture_id="sm_fixture_1",
                    canonical_fixture_id="fd_fixture_1",
                    team_mappings={"57": "fd_team_57", "64": "fd_team_64"},
                ),
            ),
            run_prematch_workflow=True,
            prematch_options=_prematch_options(),
        ),
        requested_by="admin_api",
        database=database,
        audit_repository=PostgresProviderSyncWorkflowRunRepository(database),
    )

    assert result.provider_sync_workflow_run_id == 501
    assert result.fixture_count == 2
    assert result.odds_snapshot_count == 5
    assert result.availability_snapshot_count == 5
    assert result.raw_payload_ids == [31, 32, 33, 34]
    assert result.canonical_fixture_ids == ["fd_fixture_1", "fd_fixture_2"]
    assert result.warnings == ["the_odds_api_event_odds:event_1:odds_bookmaker_partial"]
    assert fixture_calls[0]["dry_run"] is False
    assert odds_calls[0]["provider_event_id"] == "event_1"
    assert availability_calls[0]["team_mappings"] == {
        "57": "fd_team_57",
        "64": "fd_team_64",
    }
    assert prematch_calls == [
        {"dry_run": False, "competition_id": "EPL", "requested_by": "admin_api"}
    ]
    complete_query, complete_params = database.fetch_one_calls[-1]
    assert complete_query == COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY
    assert complete_params["fixture_sync_run_id"] == 11
    assert complete_params["odds_sync_run_ids_json"] == "[12]"
    assert complete_params["availability_sync_run_ids_json"] == "[13]"
    assert complete_params["prematch_workflow_run_id"] == 44


def test_provider_sync_workflow_requires_canonical_competition_for_fixture_commit() -> None:
    database = FakeProviderSyncWorkflowDatabase()

    with pytest.raises(ValueError, match="canonical_competition_id"):
        run_audited_provider_sync_workflow(
            Settings(),
            options=ProviderSyncWorkflowOptions(
                dry_run=False,
                fixture_sync=FootballDataFixtureSyncTask(
                    provider_competition_id="PL",
                    season="2025",
                ),
            ),
            database=database,
            audit_repository=PostgresProviderSyncWorkflowRunRepository(database),
        )

    assert database.fetch_one_calls[-1][0] == FAIL_PROVIDER_SYNC_WORKFLOW_RUN_QUERY


def test_provider_sync_workflow_uses_mock_dry_run_samples_without_api_keys() -> None:
    database = FakeProviderSyncWorkflowDatabase()

    result = run_audited_provider_sync_workflow(
        Settings(provider_sync_mock_dry_run_enabled=True),
        options=ProviderSyncWorkflowOptions(
            dry_run=True,
            fixture_sync=FootballDataFixtureSyncTask(
                provider_competition_id="PL",
                canonical_competition_id="EPL",
                season="2025",
            ),
            odds_syncs=(
                TheOddsApiEventOddsSyncTask(
                    sport_key="soccer_epl",
                    provider_event_id="event-id",
                    canonical_fixture_id="fd_fixture_330299",
                ),
            ),
            availability_syncs=(
                SportMonksFixtureAvailabilitySyncTask(
                    provider_fixture_id="sportmonks-fixture-id",
                    canonical_fixture_id="fd_fixture_330299",
                    team_mappings={"57": "fd_team_57", "64": "fd_team_64"},
                ),
            ),
        ),
        requested_by="admin_api",
        database=database,
        audit_repository=PostgresProviderSyncWorkflowRunRepository(database),
    )

    assert result.dry_run is True
    assert result.fixture_count == 1
    assert result.odds_snapshot_count == 5
    assert result.availability_snapshot_count == 4
    assert result.canonical_fixture_ids == ["fd_fixture_330299"]
    assert result.fixture_sync is not None
    assert result.fixture_sync.fixtures[0].provider_entity_id == "330299"
    assert result.odds_syncs[0].snapshots
    assert result.availability_syncs[0].provider_observation_count > 0
    assert result.warnings == [
        f"football_data_fixture_sync:{MOCK_PROVIDER_DRY_RUN_WARNING}",
        f"the_odds_api_event_odds:event-id:{MOCK_PROVIDER_DRY_RUN_WARNING}",
        (
            "sportmonks_availability:sportmonks-fixture-id:"
            f"{MOCK_PROVIDER_DRY_RUN_WARNING}"
        ),
    ]
    complete_query, complete_params = database.fetch_one_calls[-1]
    assert complete_query == COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY
    assert complete_params["fixture_count"] == 1
    assert complete_params["odds_snapshot_count"] == 5
    assert complete_params["availability_snapshot_count"] == 4


def test_provider_sync_workflow_conflict_detection_evaluates_recent_observations() -> None:
    database = FakeProviderSyncWorkflowConflictDetectionDatabase()

    result = run_provider_sync_workflow_conflict_detection(
        database,
        canonical_fixture_ids=["fd_fixture_1"],
        dry_run=True,
        requested_by="admin_api",
        lookback_hours=24,
        limit=25,
        as_of_time_utc=datetime(2026, 5, 8, 4, 2, tzinfo=UTC),
    )

    assert result.dry_run is True
    assert result.checked_issue_count == 2
    assert result.conflict_count == 1
    assert result.critical_count == 1
    assert result.events[0].trusted_provider == "football-data.org"
    assert result.events[0].evidence_json["values_by_provider"] == {
        "football-data.org": "2-1",
        "sportmonks": "1-1",
    }
    assert result.metadata_json == {
        "source": "provider_sync_workflow_observation_conflict_detection",
        "quality_policy": "provider_conflict_quality_penalty_v1",
        "canonical_fixture_ids": ["fd_fixture_1"],
        "observation_lookback_hours": 24,
        "observation_limit": 25,
    }
    assert database.fetch_one_calls == []
    assert database.fetch_all_calls[0][0] == LIST_PROVIDER_OBSERVATIONS_QUERY
    assert database.fetch_all_calls[0][1]["canonical_entity_id"] == "fd_fixture_1"
    assert database.fetch_all_calls[0][1]["entity_type"] == "fixture"


def test_provider_sync_workflow_can_run_observation_conflict_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakeProviderSyncWorkflowDatabase()
    execution_order: list[str] = []
    conflict_calls: list[dict[str, object]] = []
    prematch_calls: list[dict[str, object]] = []

    def fake_odds_sync(settings: Settings, **kwargs: object) -> TheOddsApiEventOddsSyncResult:
        execution_order.append("odds_sync")
        return TheOddsApiEventOddsSyncResult(
            sport_key="soccer_epl",
            provider_event_id=str(kwargs["provider_event_id"]),
            canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
            sync_run=_sync_run("the-odds-api", "odds", 12, entity_count=5),
            raw_payload=_raw_payload(32, provider="the-odds-api"),
            odds_write=OddsSnapshotWriteSummary(
                odds_snapshots=5,
                provider_mappings=1,
                bookmaker_count=1,
                market_types=["1x2"],
                canonical_fixture_id=str(kwargs["canonical_fixture_id"]),
            ),
        )

    def fake_conflict_detection(
        database_arg: object,
        *,
        canonical_fixture_ids: Sequence[str],
        dry_run: bool,
        requested_by: str | None,
        lookback_hours: int,
        limit: int,
    ) -> ProviderConflictEvaluationResult:
        execution_order.append("conflict_detection")
        conflict_calls.append(
            {
                "database": database_arg,
                "canonical_fixture_ids": list(canonical_fixture_ids),
                "dry_run": dry_run,
                "requested_by": requested_by,
                "lookback_hours": lookback_hours,
                "limit": limit,
            }
        )
        return ProviderConflictEvaluationResult(
            dry_run=dry_run,
            as_of_time_utc=datetime(2026, 5, 8, 4, 2, tzinfo=UTC),
            checked_issue_count=2,
            conflict_count=1,
            critical_count=0,
            warning_count=1,
            info_count=0,
            provider_consistency_after_conflicts=0.5,
            data_quality_score_delta=-5.0,
            metadata_json={"source": "unit_test"},
        )

    def fake_prematch_workflow(
        settings: Settings,
        *,
        options: object,
        requested_by: str | None,
    ) -> PrematchWorkflowResult:
        execution_order.append("prematch_workflow")
        prematch_calls.append({"dry_run": options.dry_run, "requested_by": requested_by})
        return _prematch_result()

    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_the_odds_api_event_odds_sync",
        fake_odds_sync,
    )
    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_provider_sync_workflow_conflict_detection",
        fake_conflict_detection,
    )
    monkeypatch.setattr(
        "nutmeg.providers.workflow.run_audited_prematch_workflow",
        fake_prematch_workflow,
    )

    result = run_audited_provider_sync_workflow(
        Settings(),
        options=ProviderSyncWorkflowOptions(
            dry_run=False,
            odds_syncs=(
                TheOddsApiEventOddsSyncTask(
                    sport_key="soccer_epl",
                    provider_event_id="event_1",
                    canonical_fixture_id="fd_fixture_1",
                ),
            ),
            run_conflict_detection=True,
            conflict_observation_lookback_hours=24,
            conflict_limit=25,
            run_prematch_workflow=True,
            prematch_options=_prematch_options(),
        ),
        requested_by="admin_api",
        database=database,
        audit_repository=PostgresProviderSyncWorkflowRunRepository(database),
    )

    assert execution_order == ["odds_sync", "conflict_detection", "prematch_workflow"]
    assert result.provider_conflict_evaluation is not None
    assert result.provider_conflict_evaluation.conflict_count == 1
    assert result.warnings == ["provider_conflict_detection:1_open_conflicts"]
    assert conflict_calls == [
        {
            "database": database,
            "canonical_fixture_ids": ["fd_fixture_1"],
            "dry_run": False,
            "requested_by": "admin_api",
            "lookback_hours": 24,
            "limit": 25,
        }
    ]
    assert prematch_calls == [{"dry_run": False, "requested_by": "admin_api"}]
    complete_query, complete_params = database.fetch_one_calls[-1]
    assert complete_query == COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY
    assert (
        complete_params["warnings_json"]
        == '["provider_conflict_detection:1_open_conflicts"]'
    )


def test_provider_sync_workflow_repository_lists_latest_records() -> None:
    database = FakeProviderSyncWorkflowDatabase()
    records = PostgresProviderSyncWorkflowRunRepository(database).list_latest(limit=5)

    assert len(records) == 1
    assert records[0].provider_sync_workflow_run_id == 501
    assert records[0].fixture_sync_run_id == 11
    assert records[0].odds_sync_run_ids == [12]
    assert records[0].availability_sync_run_ids == [13]
    assert records[0].raw_payload_ids == [31, 32, 33, 34]
    assert records[0].canonical_fixture_ids == ["fd_fixture_1", "fd_fixture_2"]
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_SYNC_WORKFLOW_RUNS_QUERY, {"limit": 5})
    ]


def test_provider_sync_workflow_repository_gets_run_detail() -> None:
    database = FakeProviderSyncWorkflowDatabase()
    record = PostgresProviderSyncWorkflowRunRepository(database).get_by_id(
        provider_sync_workflow_run_id=501,
    )

    assert record is not None
    assert record.provider_sync_workflow_run_id == 501
    assert record.status == "failed"
    assert record.error_message == "provider timeout"
    assert record.metadata_json == {"source": "admin_api"}
    assert database.fetch_one_calls == [
        (
            GET_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
            {"provider_sync_workflow_run_id": 501},
        )
    ]


def test_provider_sync_workflow_repository_returns_none_for_missing_detail() -> None:
    database = FakeProviderSyncWorkflowDatabase()
    record = PostgresProviderSyncWorkflowRunRepository(database).get_by_id(
        provider_sync_workflow_run_id=404,
    )

    assert record is None


def _sync_run(
    provider_name: str,
    capability: str,
    provider_sync_run_id: int,
    *,
    entity_count: int,
) -> ProviderSyncRunRecord:
    return ProviderSyncRunRecord(
        provider_sync_run_id=provider_sync_run_id,
        provider_name=provider_name,
        capability=capability,
        status="completed",
        started_at=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
        duration_ms=1000,
        entity_count=entity_count,
    )


def _raw_payload(payload_id: int, *, provider: str) -> StoredRawProviderPayload:
    return StoredRawProviderPayload(
        payload_id=payload_id,
        provider=provider,
        endpoint="/mock",
        request_hash=f"hash_{payload_id}",
        fetched_at=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
    )


def _prematch_options() -> PrematchWorkflowOptions:
    return PrematchWorkflowOptions(
        competition_id="EPL",
        dry_run=False,
    )


def _prematch_result() -> PrematchWorkflowResult:
    return PrematchWorkflowResult(
        prematch_workflow_run_id=44,
        dry_run=False,
        prediction=PredictionJobResult(
            prediction_job_run_id=19,
            job_type="canonical_prematch_predictions",
            dry_run=False,
            prediction_time_utc=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
            fixture_count=2,
            generated_count=2,
            data_quality_scores={"fd_fixture_1": 82.0, "fd_fixture_2": 81.0},
        ),
    )


def _workflow_row(
    *,
    status: str,
    completed_at: datetime | None = datetime(2026, 5, 8, 4, 5, tzinfo=UTC),
    duration_ms: int | None = 75,
    fixture_sync_run_id: object | None = 11,
    odds_sync_run_ids_json: object = "[12]",
    availability_sync_run_ids_json: object = "[13]",
    fixture_count: object = 2,
    odds_snapshot_count: object = 5,
    availability_snapshot_count: object = 5,
    raw_payload_ids_json: object = "[31,32,33,34]",
    canonical_fixture_ids_json: object = '["fd_fixture_1","fd_fixture_2"]',
    prematch_workflow_run_id: object | None = 44,
    warnings_json: object = '["provider_warning"]',
    error_message: object | None = None,
) -> DatabaseRow:
    return {
        "provider_sync_workflow_run_id": 501,
        "status": status,
        "dry_run": False,
        "requested_by": "admin_api",
        "started_at": datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "fixture_sync_run_id": fixture_sync_run_id,
        "odds_sync_run_ids_json": odds_sync_run_ids_json,
        "availability_sync_run_ids_json": availability_sync_run_ids_json,
        "fixture_count": fixture_count,
        "odds_snapshot_count": odds_snapshot_count,
        "availability_snapshot_count": availability_snapshot_count,
        "raw_payload_ids_json": raw_payload_ids_json,
        "canonical_fixture_ids_json": canonical_fixture_ids_json,
        "prematch_workflow_run_id": prematch_workflow_run_id,
        "warnings_json": warnings_json,
        "error_message": error_message,
        "metadata_json": '{"source":"admin_api"}',
    }


def _provider_observation_row(
    provider_observation_id: int,
    *,
    provider_name: str,
    provider_entity_id: str,
    observed_value: str,
) -> DatabaseRow:
    return {
        "provider_observation_id": provider_observation_id,
        "provider_name": provider_name,
        "capability": "results",
        "entity_type": "fixture",
        "canonical_entity_id": "fd_fixture_1",
        "provider_entity_id": provider_entity_id,
        "field_name": "full_time_score",
        "observed_value": observed_value,
        "observed_at_utc": datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        "confidence": 1.0,
        "payload_id": 31,
        "metadata_json": "{}",
        "created_at": datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
    }
