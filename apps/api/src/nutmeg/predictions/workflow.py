from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.config import Settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.parlay import (
    MarketPredictionParlayGenerationOptions,
    MarketPredictionParlayGenerationResult,
    PostgresParlayRecommendationRepository,
    run_market_prediction_parlay_generation,
)
from nutmeg.predictions.job_repository import (
    PostgresPredictionJobRunRepository,
    PredictionJobType,
)
from nutmeg.predictions.jobs import PredictionJobResult, run_audited_prediction_job

type PrematchWorkflowRunStatus = Literal["running", "completed", "failed"]

INSERT_PREMATCH_WORKFLOW_RUN_QUERY = """
INSERT INTO prematch_workflow_runs (
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
  prematch_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  prediction_job_run_id,
  prediction_job_type,
  prediction_fixture_count,
  prediction_generated_count,
  parlay_generated_count,
  parlay_recommendation_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

COMPLETE_PREMATCH_WORKFLOW_RUN_QUERY = """
UPDATE prematch_workflow_runs
SET
  status = 'completed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  prediction_job_run_id = %(prediction_job_run_id)s,
  prediction_job_type = %(prediction_job_type)s,
  prediction_fixture_count = %(prediction_fixture_count)s,
  prediction_generated_count = %(prediction_generated_count)s,
  parlay_generated_count = %(parlay_generated_count)s,
  parlay_recommendation_ids_json = %(parlay_recommendation_ids_json)s::jsonb,
  warnings_json = %(warnings_json)s::jsonb,
  error_message = NULL
WHERE prematch_workflow_run_id = %(prematch_workflow_run_id)s
RETURNING
  prematch_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  prediction_job_run_id,
  prediction_job_type,
  prediction_fixture_count,
  prediction_generated_count,
  parlay_generated_count,
  parlay_recommendation_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

FAIL_PREMATCH_WORKFLOW_RUN_QUERY = """
UPDATE prematch_workflow_runs
SET
  status = 'failed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  error_message = %(error_message)s,
  warnings_json = %(warnings_json)s::jsonb
WHERE prematch_workflow_run_id = %(prematch_workflow_run_id)s
RETURNING
  prematch_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  prediction_job_run_id,
  prediction_job_type,
  prediction_fixture_count,
  prediction_generated_count,
  parlay_generated_count,
  parlay_recommendation_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

LIST_PREMATCH_WORKFLOW_RUNS_QUERY = """
SELECT
  prematch_workflow_run_id,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  prediction_job_run_id,
  prediction_job_type,
  prediction_fixture_count,
  prediction_generated_count,
  parlay_generated_count,
  parlay_recommendation_ids_json,
  warnings_json,
  error_message,
  metadata_json
FROM prematch_workflow_runs
ORDER BY started_at DESC, prematch_workflow_run_id DESC
LIMIT %(limit)s
"""


class PrematchWorkflowDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class PrematchWorkflowRunRecord(BaseModel):
    prematch_workflow_run_id: int = Field(gt=0)
    status: PrematchWorkflowRunStatus
    dry_run: bool
    requested_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    prediction_job_run_id: int | None = Field(default=None, gt=0)
    prediction_job_type: PredictionJobType | None = None
    prediction_fixture_count: int = Field(default=0, ge=0)
    prediction_generated_count: int = Field(default=0, ge=0)
    parlay_generated_count: int = Field(default=0, ge=0)
    parlay_recommendation_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PrematchWorkflowOptions(BaseModel):
    prediction_job_type: PredictionJobType = "canonical_prematch_predictions"
    fixture_ids: list[str] = Field(default_factory=list)
    competition_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    as_of_time_utc: datetime | None = None
    window_hours: int = Field(default=72, ge=1, le=720)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    prediction_limit: int = Field(default=100, ge=1, le=500)
    enforce_odds_quality_gate: bool = True
    run_parlay_generation: bool = True
    parlay_pass_type: str = "2x1"
    parlay_unit_stake: float = Field(default=2.0, gt=0.0)
    parlay_max_budget: float | None = Field(default=20.0, gt=0.0)
    parlay_allowed_markets: tuple[str, ...] = ("1x2", "cn_handicap_1x2")
    parlay_min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    parlay_min_model_edge: float = 0.0
    parlay_min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    parlay_candidate_limit: int = Field(default=100, ge=1, le=1_000)
    parlay_model_version: str | None = Field(default=None, min_length=1)

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc or datetime.now(UTC))


class PrematchWorkflowResult(BaseModel):
    prematch_workflow_run_id: int | None = Field(default=None, gt=0)
    status: Literal["completed"] = "completed"
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    prediction: PredictionJobResult
    parlay: MarketPredictionParlayGenerationResult | None = None
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class PrematchWorkflowAuditRepository(Protocol):
    def start_workflow(
        self,
        *,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> PrematchWorkflowRunRecord: ...

    def complete_workflow(
        self,
        *,
        prematch_workflow_run_id: int,
        prediction_job_run_id: int | None,
        prediction_job_type: PredictionJobType,
        prediction_fixture_count: int,
        prediction_generated_count: int,
        parlay_generated_count: int,
        parlay_recommendation_ids: Sequence[int],
        warnings: Sequence[str],
    ) -> PrematchWorkflowRunRecord: ...

    def fail_workflow(
        self,
        *,
        prematch_workflow_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> PrematchWorkflowRunRecord: ...


class PostgresPrematchWorkflowRunRepository:
    def __init__(self, database: PrematchWorkflowDatabase) -> None:
        self.database = database

    def start_workflow(
        self,
        *,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> PrematchWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PREMATCH_WORKFLOW_RUN_QUERY,
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
        prematch_workflow_run_id: int,
        prediction_job_run_id: int | None,
        prediction_job_type: PredictionJobType,
        prediction_fixture_count: int,
        prediction_generated_count: int,
        parlay_generated_count: int,
        parlay_recommendation_ids: Sequence[int],
        warnings: Sequence[str],
    ) -> PrematchWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_PREMATCH_WORKFLOW_RUN_QUERY,
                {
                    "prematch_workflow_run_id": prematch_workflow_run_id,
                    "prediction_job_run_id": prediction_job_run_id,
                    "prediction_job_type": prediction_job_type,
                    "prediction_fixture_count": prediction_fixture_count,
                    "prediction_generated_count": prediction_generated_count,
                    "parlay_generated_count": parlay_generated_count,
                    "parlay_recommendation_ids_json": _json(
                        list(parlay_recommendation_ids)
                    ),
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)

    def fail_workflow(
        self,
        *,
        prematch_workflow_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> PrematchWorkflowRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_PREMATCH_WORKFLOW_RUN_QUERY,
                {
                    "prematch_workflow_run_id": prematch_workflow_run_id,
                    "error_message": error_message[:500],
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)

    def list_latest(self, *, limit: int = 10) -> list[PrematchWorkflowRunRecord]:
        rows = self.database.fetch_all(
            LIST_PREMATCH_WORKFLOW_RUNS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_record_from_row(row) for row in rows]


def run_audited_prematch_workflow(
    settings: Settings,
    *,
    options: PrematchWorkflowOptions,
    requested_by: str | None = None,
    database: PrematchWorkflowDatabase | None = None,
    audit_repository: PrematchWorkflowAuditRepository | None = None,
    prediction_audit_repository: PostgresPredictionJobRunRepository | None = None,
) -> PrematchWorkflowResult:
    if database is None:
        postgres_database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        target_database: PrematchWorkflowDatabase = postgres_database
    else:
        target_database = database

    if audit_repository is None:
        if database is not None:
            raise ValueError("audit_repository is required when injecting a database")
        target_audit_repository: PrematchWorkflowAuditRepository = (
            PostgresPrematchWorkflowRunRepository(target_database)
        )
    else:
        target_audit_repository = audit_repository

    if prediction_audit_repository is None:
        if database is not None:
            raise ValueError(
                "prediction_audit_repository is required when injecting a database"
            )
        target_prediction_audit_repository = PostgresPredictionJobRunRepository(
            target_database
        )
    else:
        target_prediction_audit_repository = prediction_audit_repository

    warnings: list[str] = []
    started = target_audit_repository.start_workflow(
        dry_run=options.dry_run,
        requested_by=requested_by,
        metadata_json={
            "source": "admin_api",
            "prediction_job_type": options.prediction_job_type,
            "fixture_ids": options.fixture_ids,
            "competition_id": options.competition_id,
            "window_hours": options.window_hours,
            "max_snapshot_lag_hours": options.max_snapshot_lag_hours,
            "prediction_limit": options.prediction_limit,
            "enforce_odds_quality_gate": options.enforce_odds_quality_gate,
            "run_parlay_generation": options.run_parlay_generation,
            "parlay_pass_type": options.parlay_pass_type,
            "parlay_allowed_markets": list(options.parlay_allowed_markets),
        },
    )

    try:
        prediction = run_audited_prediction_job(
            settings,
            job_type=options.prediction_job_type,
            fixture_ids=options.fixture_ids or None,
            competition_id=options.competition_id,
            dry_run=options.dry_run,
            as_of_time_utc=options.normalized_as_of_time_utc,
            window_hours=options.window_hours,
            max_snapshot_lag_hours=options.max_snapshot_lag_hours,
            limit=options.prediction_limit,
            enforce_odds_quality_gate=options.enforce_odds_quality_gate,
            requested_by=requested_by,
            database=target_database,
            audit_repository=target_prediction_audit_repository,
        )
        warnings.extend(prediction.warnings)
        parlay_result = _run_workflow_parlay_generation(
            target_database,
            settings=settings,
            options=options,
            prediction=prediction,
            warnings=warnings,
        )
    except Exception as exc:
        target_audit_repository.fail_workflow(
            prematch_workflow_run_id=started.prematch_workflow_run_id,
            error_message=str(exc),
            warnings=warnings,
        )
        raise

    if parlay_result is not None:
        warnings.extend(parlay_result.warnings)
    completed = target_audit_repository.complete_workflow(
        prematch_workflow_run_id=started.prematch_workflow_run_id,
        prediction_job_run_id=prediction.prediction_job_run_id,
        prediction_job_type=prediction.job_type,
        prediction_fixture_count=prediction.fixture_count,
        prediction_generated_count=prediction.generated_count,
        parlay_generated_count=parlay_result.generated_count
        if parlay_result is not None
        else 0,
        parlay_recommendation_ids=parlay_result.stored_recommendation_ids
        if parlay_result is not None
        else [],
        warnings=warnings,
    )
    return PrematchWorkflowResult(
        prematch_workflow_run_id=completed.prematch_workflow_run_id,
        dry_run=options.dry_run,
        requested_by=completed.requested_by,
        started_at_utc=completed.started_at,
        completed_at_utc=completed.completed_at,
        duration_ms=completed.duration_ms,
        prediction=prediction,
        parlay=parlay_result,
        warnings=warnings,
    )


def _run_workflow_parlay_generation(
    database: PrematchWorkflowDatabase,
    *,
    settings: Settings,
    options: PrematchWorkflowOptions,
    prediction: PredictionJobResult,
    warnings: list[str],
) -> MarketPredictionParlayGenerationResult | None:
    if not options.run_parlay_generation:
        return None
    fixture_ids = tuple(prediction.data_quality_scores.keys())
    if not fixture_ids:
        warnings.append("parlay_generation_skipped:no_prediction_fixtures")
        return None
    if not options.dry_run and settings.parlay_repository != "postgres":
        raise ValueError("committed prematch parlay generation requires postgres repository")

    return run_market_prediction_parlay_generation(
        database,
        options=MarketPredictionParlayGenerationOptions(
            as_of_time_utc=prediction.prediction_time_utc,
            pass_type=options.parlay_pass_type,
            unit_stake=options.parlay_unit_stake,
            max_budget=options.parlay_max_budget,
            competition_id=options.competition_id,
            fixture_ids=fixture_ids,
            model_version=options.parlay_model_version,
            allowed_markets=options.parlay_allowed_markets,
            min_probability=options.parlay_min_probability,
            min_model_edge=options.parlay_min_model_edge,
            min_data_quality_score=options.parlay_min_data_quality_score,
            candidate_limit=options.parlay_candidate_limit,
            dry_run=options.dry_run,
        ),
        repository=PostgresParlayRecommendationRepository(database)
        if not options.dry_run
        else None,
    )


def _record_from_row(row: DatabaseRow) -> PrematchWorkflowRunRecord:
    return PrematchWorkflowRunRecord(
        prematch_workflow_run_id=_int(row["prematch_workflow_run_id"]),
        status=_status(row["status"]),
        dry_run=_bool(row["dry_run"]),
        requested_by=_optional_str(row["requested_by"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        prediction_job_run_id=_optional_int(row["prediction_job_run_id"]),
        prediction_job_type=_optional_prediction_job_type(row["prediction_job_type"]),
        prediction_fixture_count=_int(row["prediction_fixture_count"]),
        prediction_generated_count=_int(row["prediction_generated_count"]),
        parlay_generated_count=_int(row["parlay_generated_count"]),
        parlay_recommendation_ids=_int_list(row["parlay_recommendation_ids_json"]),
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


def _status(value: object) -> PrematchWorkflowRunStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unsupported prematch workflow run status: {text}")
    return cast(PrematchWorkflowRunStatus, text)


def _optional_prediction_job_type(value: object) -> PredictionJobType | None:
    if value is None:
        return None
    text = str(value)
    if text not in {"mock_prematch_predictions", "canonical_prematch_predictions"}:
        raise ValueError(f"unsupported prediction job type: {text}")
    return cast(PredictionJobType, text)


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
