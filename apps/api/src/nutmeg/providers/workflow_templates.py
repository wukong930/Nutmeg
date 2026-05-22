from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.providers.workflow import ProviderSyncWorkflowOptions

type ProviderSyncWorkflowPreflightSeverity = Literal["error", "warning", "info"]

INSERT_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY = """
INSERT INTO provider_sync_workflow_templates (
  template_name,
  description,
  dry_run,
  fixture_sync_json,
  odds_syncs_json,
  availability_syncs_json,
  run_conflict_detection,
  conflict_observation_lookback_hours,
  conflict_limit,
  created_by,
  metadata_json
) VALUES (
  %(template_name)s,
  %(description)s,
  %(dry_run)s,
  %(fixture_sync_json)s::jsonb,
  %(odds_syncs_json)s::jsonb,
  %(availability_syncs_json)s::jsonb,
  %(run_conflict_detection)s,
  %(conflict_observation_lookback_hours)s,
  %(conflict_limit)s,
  %(created_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_sync_workflow_template_id,
  template_name,
  description,
  dry_run,
  fixture_sync_json,
  odds_syncs_json,
  availability_syncs_json,
  run_conflict_detection,
  conflict_observation_lookback_hours,
  conflict_limit,
  created_by,
  created_at,
  updated_at,
  archived_at,
  archived_by,
  archive_reason,
  metadata_json
"""

LIST_PROVIDER_SYNC_WORKFLOW_TEMPLATES_QUERY = """
SELECT
  provider_sync_workflow_template_id,
  template_name,
  description,
  dry_run,
  fixture_sync_json,
  odds_syncs_json,
  availability_syncs_json,
  run_conflict_detection,
  conflict_observation_lookback_hours,
  conflict_limit,
  created_by,
  created_at,
  updated_at,
  archived_at,
  archived_by,
  archive_reason,
  metadata_json
FROM provider_sync_workflow_templates
WHERE archived_at IS NULL
ORDER BY updated_at DESC, provider_sync_workflow_template_id DESC
LIMIT %(limit)s
"""

UPDATE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY = """
UPDATE provider_sync_workflow_templates
SET
  template_name = %(template_name)s,
  description = %(description)s,
  dry_run = %(dry_run)s,
  fixture_sync_json = %(fixture_sync_json)s::jsonb,
  odds_syncs_json = %(odds_syncs_json)s::jsonb,
  availability_syncs_json = %(availability_syncs_json)s::jsonb,
  run_conflict_detection = %(run_conflict_detection)s,
  conflict_observation_lookback_hours = %(conflict_observation_lookback_hours)s,
  conflict_limit = %(conflict_limit)s,
  updated_at = now(),
  metadata_json = metadata_json || %(metadata_json)s::jsonb
WHERE provider_sync_workflow_template_id = %(provider_sync_workflow_template_id)s
  AND archived_at IS NULL
RETURNING
  provider_sync_workflow_template_id,
  template_name,
  description,
  dry_run,
  fixture_sync_json,
  odds_syncs_json,
  availability_syncs_json,
  run_conflict_detection,
  conflict_observation_lookback_hours,
  conflict_limit,
  created_by,
  created_at,
  updated_at,
  archived_at,
  archived_by,
  archive_reason,
  metadata_json
"""

ARCHIVE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY = """
UPDATE provider_sync_workflow_templates
SET
  archived_at = now(),
  archived_by = %(archived_by)s,
  archive_reason = %(archive_reason)s,
  updated_at = now(),
  metadata_json = metadata_json || %(metadata_json)s::jsonb
WHERE provider_sync_workflow_template_id = %(provider_sync_workflow_template_id)s
  AND archived_at IS NULL
RETURNING
  provider_sync_workflow_template_id,
  template_name,
  description,
  dry_run,
  fixture_sync_json,
  odds_syncs_json,
  availability_syncs_json,
  run_conflict_detection,
  conflict_observation_lookback_hours,
  conflict_limit,
  created_by,
  created_at,
  updated_at,
  archived_at,
  archived_by,
  archive_reason,
  metadata_json
"""


class ProviderSyncWorkflowTemplateDatabase:
    def __init__(
        self,
        database_url: str,
        *,
        connect_timeout_seconds: int = 3,
    ) -> None:
        self.executor = PsycopgSyncDatabaseExecutor(
            database_url,
            connect_timeout_seconds=connect_timeout_seconds,
        )

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        return self.executor.fetch_one(query, params)

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        return self.executor.fetch_all(query, params)


class ProviderSyncWorkflowPreflightIssue(BaseModel):
    severity: ProviderSyncWorkflowPreflightSeverity
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field_path: str | None = None


class ProviderSyncWorkflowPreflightResult(BaseModel):
    valid: bool
    task_count: int = Field(ge=0)
    sync_types: list[str] = Field(default_factory=list)
    canonical_fixture_ids: list[str] = Field(default_factory=list)
    issue_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    issues: list[ProviderSyncWorkflowPreflightIssue] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderSyncWorkflowTemplateRecord(BaseModel):
    provider_sync_workflow_template_id: int = Field(gt=0)
    template_name: str
    description: str | None = None
    dry_run: bool = True
    fixture_sync: dict[str, object] | None = None
    odds_syncs: list[dict[str, object]] = Field(default_factory=list)
    availability_syncs: list[dict[str, object]] = Field(default_factory=list)
    run_conflict_detection: bool = False
    conflict_observation_lookback_hours: int = Field(default=168, ge=1, le=8_760)
    conflict_limit: int = Field(default=1_000, ge=1, le=5_000)
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    archived_by: str | None = None
    archive_reason: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PostgresProviderSyncWorkflowTemplateRepository:
    def __init__(self, database: ProviderSyncWorkflowTemplateDatabase) -> None:
        self.database = database

    def save_template(
        self,
        *,
        template_name: str,
        description: str | None,
        dry_run: bool,
        fixture_sync: Mapping[str, object] | None,
        odds_syncs: Sequence[Mapping[str, object]],
        availability_syncs: Sequence[Mapping[str, object]],
        run_conflict_detection: bool,
        conflict_observation_lookback_hours: int,
        conflict_limit: int,
        created_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowTemplateRecord:
        row = self.database.fetch_one(
            INSERT_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
            {
                "template_name": template_name,
                "description": description,
                "dry_run": dry_run,
                "fixture_sync_json": (
                    _json(dict(fixture_sync)) if fixture_sync is not None else None
                ),
                "odds_syncs_json": _json([dict(item) for item in odds_syncs]),
                "availability_syncs_json": _json(
                    [dict(item) for item in availability_syncs]
                ),
                "run_conflict_detection": run_conflict_detection,
                "conflict_observation_lookback_hours": (
                    conflict_observation_lookback_hours
                ),
                "conflict_limit": conflict_limit,
                "created_by": created_by,
                "metadata_json": _json(dict(metadata_json or {})),
            },
        )
        if row is None:
            raise ValueError("expected provider sync template RETURNING row")
        return _template_record_from_row(row)

    def update_template(
        self,
        *,
        provider_sync_workflow_template_id: int,
        template_name: str,
        description: str | None,
        dry_run: bool,
        fixture_sync: Mapping[str, object] | None,
        odds_syncs: Sequence[Mapping[str, object]],
        availability_syncs: Sequence[Mapping[str, object]],
        run_conflict_detection: bool,
        conflict_observation_lookback_hours: int,
        conflict_limit: int,
        updated_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowTemplateRecord | None:
        row = self.database.fetch_one(
            UPDATE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
            {
                "provider_sync_workflow_template_id": (
                    provider_sync_workflow_template_id
                ),
                "template_name": template_name,
                "description": description,
                "dry_run": dry_run,
                "fixture_sync_json": (
                    _json(dict(fixture_sync)) if fixture_sync is not None else None
                ),
                "odds_syncs_json": _json([dict(item) for item in odds_syncs]),
                "availability_syncs_json": _json(
                    [dict(item) for item in availability_syncs]
                ),
                "run_conflict_detection": run_conflict_detection,
                "conflict_observation_lookback_hours": (
                    conflict_observation_lookback_hours
                ),
                "conflict_limit": conflict_limit,
                "metadata_json": _json(
                    {"updated_by": updated_by, **dict(metadata_json or {})}
                ),
            },
        )
        if row is None:
            return None
        return _template_record_from_row(row)

    def archive_template(
        self,
        *,
        provider_sync_workflow_template_id: int,
        archived_by: str | None,
        archive_reason: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowTemplateRecord | None:
        row = self.database.fetch_one(
            ARCHIVE_PROVIDER_SYNC_WORKFLOW_TEMPLATE_QUERY,
            {
                "provider_sync_workflow_template_id": (
                    provider_sync_workflow_template_id
                ),
                "archived_by": archived_by,
                "archive_reason": archive_reason,
                "metadata_json": _json(
                    {"archived_by": archived_by, **dict(metadata_json or {})}
                ),
            },
        )
        if row is None:
            return None
        return _template_record_from_row(row)

    def list_latest(
        self,
        *,
        limit: int = 10,
    ) -> list[ProviderSyncWorkflowTemplateRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_SYNC_WORKFLOW_TEMPLATES_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_template_record_from_row(row) for row in rows]


def preflight_provider_sync_workflow(
    options: ProviderSyncWorkflowOptions,
) -> ProviderSyncWorkflowPreflightResult:
    issues: list[ProviderSyncWorkflowPreflightIssue] = []
    sync_types: list[str] = []
    canonical_fixture_ids: list[str] = []

    if options.fixture_sync is not None:
        sync_types.append("fixture")
    if options.odds_syncs:
        sync_types.append("odds")
        canonical_fixture_ids.extend(task.canonical_fixture_id for task in options.odds_syncs)
    if options.availability_syncs:
        sync_types.append("availability")
        canonical_fixture_ids.extend(
            task.canonical_fixture_id for task in options.availability_syncs
        )

    task_count = (
        (1 if options.fixture_sync is not None else 0)
        + len(options.odds_syncs)
        + len(options.availability_syncs)
    )
    if task_count == 0:
        issues.append(
            ProviderSyncWorkflowPreflightIssue(
                severity="error",
                code="provider_sync_task_required",
                message="At least one explicit provider sync task is required.",
            )
        )

    if (
        not options.dry_run
        and options.fixture_sync is not None
        and options.fixture_sync.canonical_competition_id is None
    ):
        issues.append(
            ProviderSyncWorkflowPreflightIssue(
                severity="error",
                code="fixture_commit_requires_canonical_competition",
                message="Committed fixture sync requires canonical_competition_id.",
                field_path="fixture_sync.canonical_competition_id",
            )
        )

    if options.run_conflict_detection and not canonical_fixture_ids:
        issues.append(
            ProviderSyncWorkflowPreflightIssue(
                severity="warning",
                code="conflict_detection_without_fixture_scope",
                message=(
                    "Conflict detection has no explicit canonical fixture scope; "
                    "prefer odds or availability tasks with canonical_fixture_id."
                ),
                field_path="run_conflict_detection",
            )
        )

    for index, task in enumerate(options.availability_syncs):
        if len(task.team_mappings) < 2:
            issues.append(
                ProviderSyncWorkflowPreflightIssue(
                    severity="warning",
                    code="availability_team_mapping_partial",
                    message="Availability sync should include both team mappings when possible.",
                    field_path=f"availability_syncs[{index}].team_mappings",
                )
            )

    if options.run_prematch_workflow and options.prematch_options is None:
        issues.append(
            ProviderSyncWorkflowPreflightIssue(
                severity="error",
                code="prematch_options_required",
                message="Prematch options are required when run_prematch_workflow=true.",
                field_path="prematch",
            )
        )

    deduped_fixture_ids = sorted(set(canonical_fixture_ids))
    if len(deduped_fixture_ids) < len(canonical_fixture_ids):
        issues.append(
            ProviderSyncWorkflowPreflightIssue(
                severity="info",
                code="canonical_fixture_ids_deduplicated",
                message="Repeated canonical fixture IDs will be deduplicated in audit summaries.",
            )
        )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    info_count = sum(1 for issue in issues if issue.severity == "info")
    return ProviderSyncWorkflowPreflightResult(
        valid=error_count == 0,
        task_count=task_count,
        sync_types=sync_types,
        canonical_fixture_ids=deduped_fixture_ids,
        issue_count=len(issues),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        issues=issues,
        metadata_json={
            "dry_run": options.dry_run,
            "fixture_sync_requested": options.fixture_sync is not None,
            "odds_sync_count": len(options.odds_syncs),
            "availability_sync_count": len(options.availability_syncs),
            "run_conflict_detection": options.run_conflict_detection,
            "run_prematch_workflow": options.run_prematch_workflow,
        },
    )


def _template_record_from_row(row: DatabaseRow) -> ProviderSyncWorkflowTemplateRecord:
    return ProviderSyncWorkflowTemplateRecord(
        provider_sync_workflow_template_id=_int(
            row["provider_sync_workflow_template_id"]
        ),
        template_name=str(row["template_name"]),
        description=_optional_str(row["description"]),
        dry_run=_bool(row["dry_run"]),
        fixture_sync=_optional_object_mapping(row["fixture_sync_json"]),
        odds_syncs=_object_list(row["odds_syncs_json"]),
        availability_syncs=_object_list(row["availability_syncs_json"]),
        run_conflict_detection=_bool(row["run_conflict_detection"]),
        conflict_observation_lookback_hours=_int(
            row["conflict_observation_lookback_hours"]
        ),
        conflict_limit=_int(row["conflict_limit"]),
        created_by=_optional_str(row["created_by"]),
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
        archived_at=_optional_datetime(row.get("archived_at")),
        archived_by=_optional_str(row.get("archived_by")),
        archive_reason=_optional_str(row.get("archive_reason")),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_json(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _optional_object_mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return _object_mapping(value)


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _object_list(value: object) -> list[dict[str, object]]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        return []
    items: list[dict[str, object]] = []
    for item in parsed:
        if isinstance(item, dict):
            items.append({str(key): value for key, value in item.items()})
    return items


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
