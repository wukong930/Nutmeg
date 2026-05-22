from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import (
    DatabaseReadError,
    DatabaseRow,
    PsycopgSyncDatabaseExecutor,
    QueryParams,
)

type RecommendationBenchmarkPreflightCheckStatus = Literal[
    "passed",
    "warning",
    "failed",
]
type RecommendationBenchmarkPreflightStatus = Literal["ready", "warning", "blocked"]

DEFAULT_REQUIRED_BENCHMARK_TABLES = (
    "recommendation_benchmark_runs",
    "recommendation_benchmark_strategy_pair_runs",
    "recommendation_runs",
    "recommendation_candidate_pool_snapshots",
    "recommendation_candidate_pool_items",
    "prediction_snapshots",
    "odds_snapshots",
    "fixtures",
    "results",
)

DATABASE_CONNECTIVITY_QUERY = "SELECT 1 AS ok"

TABLE_EXISTS_QUERY = """
SELECT to_regclass(%(relation_name)s) AS relation_name
"""

BENCHMARK_HISTORY_COUNT_QUERY = """
SELECT
  COUNT(*) AS run_count,
  MAX(created_at) AS latest_created_at
FROM recommendation_benchmark_runs
"""


class RecommendationBenchmarkPreflightDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read rows for benchmark baseline preflight checks."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Read a single row for benchmark baseline preflight checks."""


class RecommendationBenchmarkPreflightOptions(BaseModel):
    required_tables: tuple[str, ...] = DEFAULT_REQUIRED_BENCHMARK_TABLES
    min_benchmark_history_count: int = Field(default=0, ge=0)
    warn_on_empty_history: bool = True


class RecommendationBenchmarkPreflightCheck(BaseModel):
    name: str
    status: RecommendationBenchmarkPreflightCheckStatus
    detail: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationBenchmarkPreflightResult(BaseModel):
    status: RecommendationBenchmarkPreflightStatus
    ready: bool
    checks: list[RecommendationBenchmarkPreflightCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_benchmark_preflight(
    database: RecommendationBenchmarkPreflightDatabaseExecutor,
    *,
    options: RecommendationBenchmarkPreflightOptions,
) -> RecommendationBenchmarkPreflightResult:
    checks: list[RecommendationBenchmarkPreflightCheck] = []
    try:
        database.fetch_all(DATABASE_CONNECTIVITY_QUERY, {})
    except (DatabaseReadError, RuntimeError) as exc:
        checks.append(
            RecommendationBenchmarkPreflightCheck(
                name="database_connectivity",
                status="failed",
                detail="database connection failed",
                metadata_json={"error": _safe_error_message(exc)},
            )
        )
        return _preflight_result(checks)

    checks.append(
        RecommendationBenchmarkPreflightCheck(
            name="database_connectivity",
            status="passed",
            detail="database connection is available",
        )
    )
    checks.extend(_table_checks(database, options=options))
    if any(
        check.name.startswith("required_table:")
        and check.status == "failed"
        and check.name.endswith(":recommendation_benchmark_runs")
        for check in checks
    ):
        return _preflight_result(checks)
    checks.append(_benchmark_history_check(database, options=options))
    return _preflight_result(checks)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_benchmark_preflight(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))
    if not result.ready and not args.no_fail_process:
        raise SystemExit(1)


def _table_checks(
    database: RecommendationBenchmarkPreflightDatabaseExecutor,
    *,
    options: RecommendationBenchmarkPreflightOptions,
) -> list[RecommendationBenchmarkPreflightCheck]:
    checks: list[RecommendationBenchmarkPreflightCheck] = []
    for table_name in options.required_tables:
        relation_name = f"public.{table_name}"
        try:
            row = database.fetch_one(
                TABLE_EXISTS_QUERY,
                {"relation_name": relation_name},
            )
        except (DatabaseReadError, RuntimeError) as exc:
            checks.append(
                RecommendationBenchmarkPreflightCheck(
                    name=f"required_table:{table_name}",
                    status="failed",
                    detail="table existence check failed",
                    metadata_json={"error": _safe_error_message(exc)},
                )
            )
            continue
        exists = bool(row and row.get("relation_name"))
        checks.append(
            RecommendationBenchmarkPreflightCheck(
                name=f"required_table:{table_name}",
                status="passed" if exists else "failed",
                detail="required table exists" if exists else "required table is missing",
                metadata_json={"relation_name": relation_name},
            )
        )
    return checks


def _benchmark_history_check(
    database: RecommendationBenchmarkPreflightDatabaseExecutor,
    *,
    options: RecommendationBenchmarkPreflightOptions,
) -> RecommendationBenchmarkPreflightCheck:
    try:
        row = database.fetch_one(BENCHMARK_HISTORY_COUNT_QUERY, {})
    except (DatabaseReadError, RuntimeError) as exc:
        return RecommendationBenchmarkPreflightCheck(
            name="benchmark_history",
            status="failed",
            detail="benchmark history count check failed",
            metadata_json={"error": _safe_error_message(exc)},
        )
    run_count = _int(row.get("run_count") if row else 0)
    latest_created_at = row.get("latest_created_at") if row else None
    if run_count < options.min_benchmark_history_count:
        status: RecommendationBenchmarkPreflightCheckStatus = "failed"
        detail = "benchmark history is below the configured minimum"
    elif run_count == 0 and options.warn_on_empty_history:
        status = "warning"
        detail = "benchmark history is empty; first saved baseline can be created"
    else:
        status = "passed"
        detail = "benchmark history is available"
    return RecommendationBenchmarkPreflightCheck(
        name="benchmark_history",
        status=status,
        detail=detail,
        metadata_json={
            "run_count": run_count,
            "min_benchmark_history_count": options.min_benchmark_history_count,
            "latest_created_at": _optional_datetime_json(latest_created_at),
        },
    )


def _preflight_result(
    checks: Sequence[RecommendationBenchmarkPreflightCheck],
) -> RecommendationBenchmarkPreflightResult:
    failed = [check for check in checks if check.status == "failed"]
    warning = [check for check in checks if check.status == "warning"]
    status: RecommendationBenchmarkPreflightStatus
    if failed:
        status = "blocked"
    elif warning:
        status = "warning"
    else:
        status = "ready"
    warnings = [
        f"benchmark_preflight:{check.status}:{check.name}"
        for check in checks
        if check.status in {"failed", "warning"}
    ]
    return RecommendationBenchmarkPreflightResult(
        status=status,
        ready=not failed,
        checks=list(checks),
        warnings=warnings,
        summary_json={
            "status": status,
            "ready": not failed,
            "check_count": len(checks),
            "failed_check_count": len(failed),
            "warning_check_count": len(warning),
            "failed_checks": [check.name for check in failed],
            "warning_checks": [check.name for check in warning],
            "warnings": warnings,
            "calculation_basis": "recommendation_benchmark_preflight_v3_1",
        },
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Check readiness for Nutmeg recommendation benchmark baselines."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument(
        "--required-tables",
        default=",".join(DEFAULT_REQUIRED_BENCHMARK_TABLES),
    )
    parser.add_argument("--min-benchmark-history-count", type=int, default=0)
    parser.add_argument("--no-empty-history-warning", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkPreflightOptions:
    return RecommendationBenchmarkPreflightOptions(
        required_tables=tuple(_csv(args.required_tables)),
        min_benchmark_history_count=args.min_benchmark_history_count,
        warn_on_empty_history=not args.no_empty_history_warning,
    )


def _safe_error_message(exc: Exception) -> str:
    cause = exc.__cause__
    message = str(cause or exc)
    return message.replace("\n", " ")[:500]


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _optional_datetime_json(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
