from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.config import Settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.predictions.workflow import (
    PrematchWorkflowOptions,
    PrematchWorkflowResult,
    run_audited_prematch_workflow,
)
from nutmeg.providers.availability_sync import (
    SportMonksFixtureAvailabilitySyncResult,
    run_sportmonks_fixture_availability_sync,
)
from nutmeg.providers.conflicts import (
    PostgresProviderConflictEventRepository,
    PostgresProviderObservationRepository,
    ProviderConflictEvaluationResult,
    ProviderObservation,
    detect_provider_observation_conflicts,
    evaluate_provider_conflict_events,
)
from nutmeg.providers.odds_sync import (
    TheOddsApiEventOddsSyncResult,
    run_the_odds_api_event_odds_sync,
)
from nutmeg.providers.sync import (
    FootballDataFixtureSyncResult,
    run_football_data_fixture_sync,
)

type ProviderSyncWorkflowRunStatus = Literal["running", "completed", "failed"]

INSERT_PROVIDER_SYNC_WORKFLOW_RUN_QUERY = """
INSERT INTO provider_sync_workflow_runs (
  status,
  dry_run,
  requested_by,
  metadata_json
) VALUES (
  'running',
  %(dry_run)s,
  %(requested_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_sync_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_sync_run_id,
  odds_sync_run_ids_json,
  availability_sync_run_ids_json,
  fixture_count,
  odds_snapshot_count,
  availability_snapshot_count,
  raw_payload_ids_json,
  canonical_fixture_ids_json,
  prematch_workflow_run_id,
  warnings_json,
  error_message,
  metadata_json
"""

COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY = """
UPDATE provider_sync_workflow_runs
SET
  status = 'completed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  fixture_sync_run_id = %(fixture_sync_run_id)s,
  odds_sync_run_ids_json = %(odds_sync_run_ids_json)s::jsonb,
  availability_sync_run_ids_json = %(availability_sync_run_ids_json)s::jsonb,
  fixture_count = %(fixture_count)s,
  odds_snapshot_count = %(odds_snapshot_count)s,
  availability_snapshot_count = %(availability_snapshot_count)s,
  raw_payload_ids_json = %(raw_payload_ids_json)s::jsonb,
  canonical_fixture_ids_json = %(canonical_fixture_ids_json)s::jsonb,
  prematch_workflow_run_id = %(prematch_workflow_run_id)s,
  warnings_json = %(warnings_json)s::jsonb,
  error_message = NULL
WHERE provider_sync_workflow_run_id = %(provider_sync_workflow_run_id)s
RETURNING
  provider_sync_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_sync_run_id,
  odds_sync_run_ids_json,
  availability_sync_run_ids_json,
  fixture_count,
  odds_snapshot_count,
  availability_snapshot_count,
  raw_payload_ids_json,
  canonical_fixture_ids_json,
  prematch_workflow_run_id,
  warnings_json,
  error_message,
  metadata_json
"""

FAIL_PROVIDER_SYNC_WORKFLOW_RUN_QUERY = """
UPDATE provider_sync_workflow_runs
SET
  status = 'failed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  error_message = %(error_message)s,
  warnings_json = %(warnings_json)s::jsonb
WHERE provider_sync_workflow_run_id = %(provider_sync_workflow_run_id)s
RETURNING
  provider_sync_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_sync_run_id,
  odds_sync_run_ids_json,
  availability_sync_run_ids_json,
  fixture_count,
  odds_snapshot_count,
  availability_snapshot_count,
  raw_payload_ids_json,
  canonical_fixture_ids_json,
  prematch_workflow_run_id,
  warnings_json,
  error_message,
  metadata_json
"""

LIST_PROVIDER_SYNC_WORKFLOW_RUNS_QUERY = """
SELECT
  provider_sync_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_sync_run_id,
  odds_sync_run_ids_json,
  availability_sync_run_ids_json,
  fixture_count,
  odds_snapshot_count,
  availability_snapshot_count,
  raw_payload_ids_json,
  canonical_fixture_ids_json,
  prematch_workflow_run_id,
  warnings_json,
  error_message,
  metadata_json
FROM provider_sync_workflow_runs
ORDER BY started_at DESC, provider_sync_workflow_run_id DESC
LIMIT %(limit)s
"""

GET_PROVIDER_SYNC_WORKFLOW_RUN_QUERY = """
SELECT
  provider_sync_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_sync_run_id,
  odds_sync_run_ids_json,
  availability_sync_run_ids_json,
  fixture_count,
  odds_snapshot_count,
  availability_snapshot_count,
  raw_payload_ids_json,
  canonical_fixture_ids_json,
  prematch_workflow_run_id,
  warnings_json,
  error_message,
  metadata_json
FROM provider_sync_workflow_runs
WHERE provider_sync_workflow_run_id = %(provider_sync_workflow_run_id)s
"""


class ProviderSyncWorkflowDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class FootballDataFixtureSyncTask(BaseModel):
    provider_competition_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    canonical_competition_id: str | None = Field(default=None, min_length=1)


class TheOddsApiEventOddsSyncTask(BaseModel):
    sport_key: str = Field(min_length=1)
    provider_event_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    regions: str = Field(default="eu", min_length=1)
    markets: str = Field(default="h2h,spreads", min_length=1)
    bookmakers: str | None = Field(default=None, min_length=1)


class SportMonksFixtureAvailabilitySyncTask(BaseModel):
    provider_fixture_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    team_mappings: dict[str, str] = Field(min_length=1)


class ProviderSyncWorkflowOptions(BaseModel):
    dry_run: bool = True
    fixture_sync: FootballDataFixtureSyncTask | None = None
    odds_syncs: tuple[TheOddsApiEventOddsSyncTask, ...] = Field(default_factory=tuple)
    availability_syncs: tuple[SportMonksFixtureAvailabilitySyncTask, ...] = Field(
        default_factory=tuple
    )
    run_prematch_workflow: bool = False
    prematch_options: PrematchWorkflowOptions | None = None
    run_conflict_detection: bool = False
    conflict_observation_lookback_hours: int = Field(default=168, ge=1, le=8_760)
    conflict_limit: int = Field(default=1_000, ge=1, le=5_000)


class ProviderSyncWorkflowRunRecord(BaseModel):
    provider_sync_workflow_run_id: int = Field(gt=0)
    status: ProviderSyncWorkflowRunStatus
    dry_run: bool
    requested_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_sync_run_id: int | None = Field(default=None, gt=0)
    odds_sync_run_ids: list[int] = Field(default_factory=list)
    availability_sync_run_ids: list[int] = Field(default_factory=list)
    fixture_count: int = Field(default=0, ge=0)
    odds_snapshot_count: int = Field(default=0, ge=0)
    availability_snapshot_count: int = Field(default=0, ge=0)
    raw_payload_ids: list[int] = Field(default_factory=list)
    canonical_fixture_ids: list[str] = Field(default_factory=list)
    prematch_workflow_run_id: int | None = Field(default=None, gt=0)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderSyncWorkflowResult(BaseModel):
    provider_sync_workflow_run_id: int | None = Field(default=None, gt=0)
    operator_approval_id: int | None = Field(default=None, gt=0)
    status: Literal["completed"] = "completed"
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_sync: FootballDataFixtureSyncResult | None = None
    odds_syncs: list[TheOddsApiEventOddsSyncResult] = Field(default_factory=list)
    availability_syncs: list[SportMonksFixtureAvailabilitySyncResult] = Field(
        default_factory=list
    )
    prematch_workflow: PrematchWorkflowResult | None = None
    provider_conflict_evaluation: ProviderConflictEvaluationResult | None = None
    fixture_count: int = Field(default=0, ge=0)
    odds_snapshot_count: int = Field(default=0, ge=0)
    availability_snapshot_count: int = Field(default=0, ge=0)
    raw_payload_ids: list[int] = Field(default_factory=list)
    canonical_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowAuditRepository(Protocol):
    def start_workflow(
        self,
        *,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowRunRecord: ...

    def complete_workflow(
        self,
        *,
        provider_sync_workflow_run_id: int,
        fixture_sync_run_id: int | None,
        odds_sync_run_ids: Sequence[int],
        availability_sync_run_ids: Sequence[int],
        fixture_count: int,
        odds_snapshot_count: int,
        availability_snapshot_count: int,
        raw_payload_ids: Sequence[int],
        canonical_fixture_ids: Sequence[str],
        prematch_workflow_run_id: int | None,
        warnings: Sequence[str],
    ) -> ProviderSyncWorkflowRunRecord: ...

    def fail_workflow(
        self,
        *,
        provider_sync_workflow_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> ProviderSyncWorkflowRunRecord: ...

    def get_by_id(
        self,
        *,
        provider_sync_workflow_run_id: int,
    ) -> ProviderSyncWorkflowRunRecord | None: ...


class PostgresProviderSyncWorkflowRunRepository:
    def __init__(self, database: ProviderSyncWorkflowDatabase) -> None:
        self.database = database

    def start_workflow(
        self,
        *,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
                {
                    "dry_run": dry_run,
                    "requested_by": requested_by,
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _record_from_row(row)

    def complete_workflow(
        self,
        *,
        provider_sync_workflow_run_id: int,
        fixture_sync_run_id: int | None,
        odds_sync_run_ids: Sequence[int],
        availability_sync_run_ids: Sequence[int],
        fixture_count: int,
        odds_snapshot_count: int,
        availability_snapshot_count: int,
        raw_payload_ids: Sequence[int],
        canonical_fixture_ids: Sequence[str],
        prematch_workflow_run_id: int | None,
        warnings: Sequence[str],
    ) -> ProviderSyncWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
                {
                    "provider_sync_workflow_run_id": provider_sync_workflow_run_id,
                    "fixture_sync_run_id": fixture_sync_run_id,
                    "odds_sync_run_ids_json": _json(list(odds_sync_run_ids)),
                    "availability_sync_run_ids_json": _json(
                        list(availability_sync_run_ids)
                    ),
                    "fixture_count": fixture_count,
                    "odds_snapshot_count": odds_snapshot_count,
                    "availability_snapshot_count": availability_snapshot_count,
                    "raw_payload_ids_json": _json(list(raw_payload_ids)),
                    "canonical_fixture_ids_json": _json(list(canonical_fixture_ids)),
                    "prematch_workflow_run_id": prematch_workflow_run_id,
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)

    def fail_workflow(
        self,
        *,
        provider_sync_workflow_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> ProviderSyncWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
                {
                    "provider_sync_workflow_run_id": provider_sync_workflow_run_id,
                    "error_message": error_message[:500],
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)

    def list_latest(self, *, limit: int = 10) -> list[ProviderSyncWorkflowRunRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_SYNC_WORKFLOW_RUNS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_record_from_row(row) for row in rows]

    def get_by_id(
        self,
        *,
        provider_sync_workflow_run_id: int,
    ) -> ProviderSyncWorkflowRunRecord | None:
        row = self.database.fetch_one(
            GET_PROVIDER_SYNC_WORKFLOW_RUN_QUERY,
            {"provider_sync_workflow_run_id": provider_sync_workflow_run_id},
        )
        if row is None:
            return None
        return _record_from_row(row)


def run_audited_provider_sync_workflow(
    settings: Settings,
    *,
    options: ProviderSyncWorkflowOptions,
    requested_by: str | None = None,
    database: ProviderSyncWorkflowDatabase | None = None,
    audit_repository: ProviderSyncWorkflowAuditRepository | None = None,
) -> ProviderSyncWorkflowResult:
    if database is None:
        postgres_database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        target_database: ProviderSyncWorkflowDatabase = postgres_database
    else:
        target_database = database

    if audit_repository is None:
        if database is not None:
            raise ValueError("audit_repository is required when injecting a database")
        target_audit_repository: ProviderSyncWorkflowAuditRepository = (
            PostgresProviderSyncWorkflowRunRepository(target_database)
        )
    else:
        target_audit_repository = audit_repository

    warnings: list[str] = []
    started = target_audit_repository.start_workflow(
        dry_run=options.dry_run,
        requested_by=requested_by,
        metadata_json={
            "source": "admin_api",
            "fixture_sync_requested": options.fixture_sync is not None,
            "odds_sync_count": len(options.odds_syncs),
            "availability_sync_count": len(options.availability_syncs),
            "run_prematch_workflow": options.run_prematch_workflow,
            "run_conflict_detection": options.run_conflict_detection,
            "conflict_observation_lookback_hours": (
                options.conflict_observation_lookback_hours
            ),
            "conflict_limit": options.conflict_limit,
        },
    )

    try:
        fixture_result = _run_fixture_sync(settings, options=options)
        odds_results = _run_odds_syncs(settings, options=options)
        availability_results = _run_availability_syncs(settings, options=options)
        warnings.extend(_collect_warnings(fixture_result, odds_results, availability_results))
        synced_fixture_ids = _canonical_fixture_ids_from_sync_results(
            fixture_result=fixture_result,
            odds_results=odds_results,
            availability_results=availability_results,
        )
        provider_conflict_evaluation = _run_conflict_detection_if_requested(
            target_database,
            options=options,
            canonical_fixture_ids=synced_fixture_ids,
            requested_by=requested_by,
        )
        if (
            provider_conflict_evaluation is not None
            and provider_conflict_evaluation.conflict_count > 0
        ):
            warnings.append(
                "provider_conflict_detection:"
                f"{provider_conflict_evaluation.conflict_count}_open_conflicts"
            )
        prematch_result = _run_prematch_if_requested(
            settings,
            options=options,
            requested_by=requested_by,
        )
        if prematch_result is not None:
            warnings.extend(prematch_result.warnings)
    except Exception as exc:
        target_audit_repository.fail_workflow(
            provider_sync_workflow_run_id=started.provider_sync_workflow_run_id,
            error_message=str(exc),
            warnings=warnings,
        )
        raise

    summary = _workflow_summary(
        fixture_result=fixture_result,
        odds_results=odds_results,
        availability_results=availability_results,
        prematch_result=prematch_result,
    )
    completed = target_audit_repository.complete_workflow(
        provider_sync_workflow_run_id=started.provider_sync_workflow_run_id,
        fixture_sync_run_id=summary.fixture_sync_run_id,
        odds_sync_run_ids=summary.odds_sync_run_ids,
        availability_sync_run_ids=summary.availability_sync_run_ids,
        fixture_count=summary.fixture_count,
        odds_snapshot_count=summary.odds_snapshot_count,
        availability_snapshot_count=summary.availability_snapshot_count,
        raw_payload_ids=summary.raw_payload_ids,
        canonical_fixture_ids=summary.canonical_fixture_ids,
        prematch_workflow_run_id=summary.prematch_workflow_run_id,
        warnings=warnings,
    )

    return ProviderSyncWorkflowResult(
        provider_sync_workflow_run_id=completed.provider_sync_workflow_run_id,
        dry_run=options.dry_run,
        requested_by=completed.requested_by,
        started_at_utc=completed.started_at,
        completed_at_utc=completed.completed_at,
        duration_ms=completed.duration_ms,
        fixture_sync=fixture_result,
        odds_syncs=odds_results,
        availability_syncs=availability_results,
        prematch_workflow=prematch_result,
        provider_conflict_evaluation=provider_conflict_evaluation,
        fixture_count=summary.fixture_count,
        odds_snapshot_count=summary.odds_snapshot_count,
        availability_snapshot_count=summary.availability_snapshot_count,
        raw_payload_ids=summary.raw_payload_ids,
        canonical_fixture_ids=summary.canonical_fixture_ids,
        warnings=warnings,
    )


class _WorkflowSummary(BaseModel):
    fixture_sync_run_id: int | None = None
    odds_sync_run_ids: list[int] = Field(default_factory=list)
    availability_sync_run_ids: list[int] = Field(default_factory=list)
    fixture_count: int = 0
    odds_snapshot_count: int = 0
    availability_snapshot_count: int = 0
    raw_payload_ids: list[int] = Field(default_factory=list)
    canonical_fixture_ids: list[str] = Field(default_factory=list)
    prematch_workflow_run_id: int | None = None


def _run_fixture_sync(
    settings: Settings,
    *,
    options: ProviderSyncWorkflowOptions,
) -> FootballDataFixtureSyncResult | None:
    if options.fixture_sync is None:
        return None
    task = options.fixture_sync
    if not options.dry_run and task.canonical_competition_id is None:
        raise ValueError("fixture sync commit requires canonical_competition_id")
    return run_football_data_fixture_sync(
        settings,
        provider_competition_id=task.provider_competition_id,
        season=task.season,
        canonical_competition_id=task.canonical_competition_id,
        dry_run=options.dry_run,
    )


def _run_odds_syncs(
    settings: Settings,
    *,
    options: ProviderSyncWorkflowOptions,
) -> list[TheOddsApiEventOddsSyncResult]:
    return [
        run_the_odds_api_event_odds_sync(
            settings,
            sport_key=task.sport_key,
            provider_event_id=task.provider_event_id,
            canonical_fixture_id=task.canonical_fixture_id,
            regions=task.regions,
            markets=task.markets,
            bookmakers=task.bookmakers,
            dry_run=options.dry_run,
        )
        for task in options.odds_syncs
    ]


def _run_availability_syncs(
    settings: Settings,
    *,
    options: ProviderSyncWorkflowOptions,
) -> list[SportMonksFixtureAvailabilitySyncResult]:
    return [
        run_sportmonks_fixture_availability_sync(
            settings,
            provider_fixture_id=task.provider_fixture_id,
            canonical_fixture_id=task.canonical_fixture_id,
            team_mappings=task.team_mappings,
            dry_run=options.dry_run,
        )
        for task in options.availability_syncs
    ]


def _run_conflict_detection_if_requested(
    database: ProviderSyncWorkflowDatabase,
    *,
    options: ProviderSyncWorkflowOptions,
    canonical_fixture_ids: Sequence[str],
    requested_by: str | None,
) -> ProviderConflictEvaluationResult | None:
    if not options.run_conflict_detection:
        return None
    return run_provider_sync_workflow_conflict_detection(
        database,
        canonical_fixture_ids=canonical_fixture_ids,
        dry_run=options.dry_run,
        requested_by=requested_by,
        lookback_hours=options.conflict_observation_lookback_hours,
        limit=options.conflict_limit,
    )


def run_provider_sync_workflow_conflict_detection(
    database: ProviderSyncWorkflowDatabase,
    *,
    canonical_fixture_ids: Sequence[str],
    dry_run: bool,
    requested_by: str | None = None,
    lookback_hours: int = 168,
    limit: int = 1_000,
    as_of_time_utc: datetime | None = None,
) -> ProviderConflictEvaluationResult:
    as_of_time = as_of_time_utc or datetime.now(UTC)
    observations = _recent_provider_observations_for_fixtures(
        database,
        canonical_fixture_ids=canonical_fixture_ids,
        as_of_time_utc=as_of_time,
        lookback_hours=lookback_hours,
        limit=limit,
    )
    events = detect_provider_observation_conflicts(observations)
    result = evaluate_provider_conflict_events(
        events,
        dry_run=dry_run,
        as_of_time_utc=as_of_time,
        checked_issue_count=len(observations),
        metadata_json={
            "source": "provider_sync_workflow_observation_conflict_detection",
            "quality_policy": "provider_conflict_quality_penalty_v1",
            "canonical_fixture_ids": list(dict.fromkeys(canonical_fixture_ids)),
            "observation_lookback_hours": lookback_hours,
            "observation_limit": limit,
        },
    )
    if not dry_run:
        PostgresProviderConflictEventRepository(database).save_events(
            result=result,
            requested_by=requested_by,
        )
    return result


def _recent_provider_observations_for_fixtures(
    database: ProviderSyncWorkflowDatabase,
    *,
    canonical_fixture_ids: Sequence[str],
    as_of_time_utc: datetime,
    lookback_hours: int,
    limit: int,
) -> list[ProviderObservation]:
    observation_repository = PostgresProviderObservationRepository(database)
    fixture_ids = list(dict.fromkeys(canonical_fixture_ids))
    if not fixture_ids:
        return observation_repository.list_recent(
            as_of_time_utc=as_of_time_utc,
            lookback_hours=lookback_hours,
            entity_type="fixture",
            limit=limit,
        )

    observations_by_key: dict[int | tuple[str, str, str, str, str], ProviderObservation] = {}
    per_fixture_limit = max(1, min(limit, 5_000))
    for fixture_id in fixture_ids:
        for observation in observation_repository.list_recent(
            as_of_time_utc=as_of_time_utc,
            lookback_hours=lookback_hours,
            entity_type="fixture",
            canonical_entity_id=fixture_id,
            limit=per_fixture_limit,
        ):
            key = _provider_observation_key(observation)
            observations_by_key[key] = observation
    return list(observations_by_key.values())[:per_fixture_limit]


def _provider_observation_key(
    observation: ProviderObservation,
) -> int | tuple[str, str, str, str, str]:
    observation_id = getattr(observation, "provider_observation_id", None)
    if isinstance(observation_id, int):
        return observation_id
    return (
        observation.provider_name,
        observation.capability,
        observation.canonical_entity_id,
        observation.field_name,
        observation.value,
    )


def _run_prematch_if_requested(
    settings: Settings,
    *,
    options: ProviderSyncWorkflowOptions,
    requested_by: str | None,
) -> PrematchWorkflowResult | None:
    if not options.run_prematch_workflow:
        return None
    if options.prematch_options is None:
        raise ValueError("prematch_options are required when run_prematch_workflow=true")
    return run_audited_prematch_workflow(
        settings,
        options=options.prematch_options.model_copy(
            update={"dry_run": options.dry_run}
        ),
        requested_by=requested_by,
    )


def _collect_warnings(
    fixture_result: FootballDataFixtureSyncResult | None,
    odds_results: Sequence[TheOddsApiEventOddsSyncResult],
    availability_results: Sequence[SportMonksFixtureAvailabilitySyncResult],
) -> list[str]:
    warnings: list[str] = []
    if fixture_result is not None:
        warnings.extend(
            f"football_data_fixture_sync:{warning}"
            for warning in fixture_result.warnings
        )
    for odds_result in odds_results:
        warnings.extend(
            f"the_odds_api_event_odds:{odds_result.provider_event_id}:{warning}"
            for warning in odds_result.warnings
        )
    for availability_result in availability_results:
        warnings.extend(
            f"sportmonks_availability:{availability_result.provider_fixture_id}:{warning}"
            for warning in availability_result.warnings
        )
    return warnings


def _canonical_fixture_ids_from_sync_results(
    *,
    fixture_result: FootballDataFixtureSyncResult | None,
    odds_results: Sequence[TheOddsApiEventOddsSyncResult],
    availability_results: Sequence[SportMonksFixtureAvailabilitySyncResult],
) -> list[str]:
    fixture_ids: list[str] = []
    if fixture_result is not None and fixture_result.canonical_write is not None:
        fixture_ids.extend(fixture_result.canonical_write.canonical_fixture_ids)
    fixture_ids.extend(odds_result.canonical_fixture_id for odds_result in odds_results)
    fixture_ids.extend(
        availability_result.canonical_fixture_id
        for availability_result in availability_results
    )
    return sorted(set(fixture_ids))


def _workflow_summary(
    *,
    fixture_result: FootballDataFixtureSyncResult | None,
    odds_results: Sequence[TheOddsApiEventOddsSyncResult],
    availability_results: Sequence[SportMonksFixtureAvailabilitySyncResult],
    prematch_result: PrematchWorkflowResult | None,
) -> _WorkflowSummary:
    summary = _WorkflowSummary()
    if fixture_result is not None:
        if fixture_result.sync_run is not None:
            summary.fixture_sync_run_id = fixture_result.sync_run.provider_sync_run_id
        summary.fixture_count = _fixture_count(fixture_result)
        if fixture_result.raw_payload is not None:
            summary.raw_payload_ids.append(fixture_result.raw_payload.payload_id)
        if fixture_result.canonical_write is not None:
            summary.canonical_fixture_ids.extend(
                fixture_result.canonical_write.canonical_fixture_ids
            )

    for odds_result in odds_results:
        if odds_result.sync_run is not None:
            summary.odds_sync_run_ids.append(odds_result.sync_run.provider_sync_run_id)
        summary.odds_snapshot_count += _odds_snapshot_count(odds_result)
        if odds_result.raw_payload is not None:
            summary.raw_payload_ids.append(odds_result.raw_payload.payload_id)
        summary.canonical_fixture_ids.append(odds_result.canonical_fixture_id)

    for availability_result in availability_results:
        if availability_result.sync_run is not None:
            summary.availability_sync_run_ids.append(
                availability_result.sync_run.provider_sync_run_id
            )
        summary.availability_snapshot_count += _availability_snapshot_count(
            availability_result
        )
        summary.raw_payload_ids.extend(
            payload.payload_id for payload in availability_result.raw_payloads
        )
        summary.canonical_fixture_ids.append(availability_result.canonical_fixture_id)

    if prematch_result is not None:
        summary.prematch_workflow_run_id = prematch_result.prematch_workflow_run_id

    summary.raw_payload_ids = sorted(set(summary.raw_payload_ids))
    summary.canonical_fixture_ids = sorted(set(summary.canonical_fixture_ids))
    return summary


def _fixture_count(result: FootballDataFixtureSyncResult) -> int:
    if result.canonical_write is not None:
        return result.canonical_write.fixtures
    return len(result.fixtures)


def _odds_snapshot_count(result: TheOddsApiEventOddsSyncResult) -> int:
    if result.odds_write is not None:
        return result.odds_write.odds_snapshots
    return len(result.snapshots)


def _availability_snapshot_count(
    result: SportMonksFixtureAvailabilitySyncResult,
) -> int:
    if result.availability_write is not None:
        return (
            result.availability_write.lineup_snapshots
            + result.availability_write.availability_snapshots
        )
    return len(result.lineups) + len(result.availabilities)


def _record_from_row(row: DatabaseRow) -> ProviderSyncWorkflowRunRecord:
    return ProviderSyncWorkflowRunRecord(
        provider_sync_workflow_run_id=_int(row["provider_sync_workflow_run_id"]),
        status=_status(row["status"]),
        dry_run=_bool(row["dry_run"]),
        requested_by=_optional_str(row["requested_by"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        fixture_sync_run_id=_optional_int(row["fixture_sync_run_id"]),
        odds_sync_run_ids=_int_list(row["odds_sync_run_ids_json"]),
        availability_sync_run_ids=_int_list(row["availability_sync_run_ids_json"]),
        fixture_count=_int(row["fixture_count"]),
        odds_snapshot_count=_int(row["odds_snapshot_count"]),
        availability_snapshot_count=_int(row["availability_snapshot_count"]),
        raw_payload_ids=_int_list(row["raw_payload_ids_json"]),
        canonical_fixture_ids=_string_list(row["canonical_fixture_ids_json"]),
        prematch_workflow_run_id=_optional_int(row["prematch_workflow_run_id"]),
        warnings=_string_list(row["warnings_json"]),
        error_message=_optional_str(row["error_message"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_json(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _status(value: object) -> ProviderSyncWorkflowRunStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unsupported provider sync workflow run status: {text}")
    return cast(ProviderSyncWorkflowRunStatus, text)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _int_list(value: object) -> list[int]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        return []
    return [_int(item) for item in parsed]


def _string_list(value: object) -> list[str]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
