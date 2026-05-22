from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.local_postgres_runner import (
    LocalAccuracyLoopRun,
    run_mock_accuracy_postgres_e2e,
)
from nutmeg.accuracy.mock_repository import ACTIVE_MODEL_VERSION
from nutmeg.accuracy.postgres_repository import PostgresAccuracyRepository
from nutmeg.accuracy.repository import AccuracySummaryService
from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor

DEFAULT_MIGRATION_DIR = Path("db/migrations")


class MigrationCursor(Protocol):
    def execute(self, query: str) -> object:
        """Execute one SQL statement."""


class MigrationConnection(Protocol):
    def cursor(self) -> AbstractContextManager[MigrationCursor]:
        """Open a cursor for migration statements."""


class PsycopgMigrationModule(Protocol):
    connect: Callable[..., AbstractContextManager[MigrationConnection]]


class PostgresAccuracySmokeResult(BaseModel):
    applied_migrations: list[str] = Field(default_factory=list)
    loop_run: LocalAccuracyLoopRun
    summary_sample_size: int = Field(ge=0)
    one_x_two_sample_size: int = Field(ge=0)
    calibration_bucket_count: int = Field(ge=0)
    model_comparison_count: int = Field(ge=0)


def run_accuracy_postgres_smoke(
    *,
    database_url: str,
    migration_dir: Path = DEFAULT_MIGRATION_DIR,
    apply_migrations_first: bool = True,
    reset: bool = True,
    connect_timeout_seconds: int = 3,
) -> PostgresAccuracySmokeResult:
    applied_migrations: list[str] = []
    if apply_migrations_first:
        applied_migrations = apply_migrations(
            database_url=database_url,
            migration_dir=migration_dir,
            connect_timeout_seconds=connect_timeout_seconds,
        )

    database = PsycopgSyncDatabaseExecutor(
        database_url,
        connect_timeout_seconds=connect_timeout_seconds,
    )
    loop_run = run_mock_accuracy_postgres_e2e(database, reset=reset)
    summary = AccuracySummaryService(
        PostgresAccuracyRepository(database),
        active_model_version=ACTIVE_MODEL_VERSION,
    ).build_summary(
        model_version="active",
        competition_id="all",
        market="1x2",
        window="90d",
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
    )

    return PostgresAccuracySmokeResult(
        applied_migrations=applied_migrations,
        loop_run=loop_run,
        summary_sample_size=summary.sample_size,
        one_x_two_sample_size=(
            summary.by_market["1x2"].sample_size if "1x2" in summary.by_market else 0
        ),
        calibration_bucket_count=len(summary.calibration_buckets),
        model_comparison_count=len(summary.model_comparisons),
    )


def apply_migrations(
    *,
    database_url: str,
    migration_dir: Path = DEFAULT_MIGRATION_DIR,
    connect_timeout_seconds: int = 3,
) -> list[str]:
    migration_files = sorted(migration_dir.glob("*.sql"))
    if not migration_files:
        raise ValueError(f"no migration files found in {migration_dir}")

    try:
        psycopg_module = cast(PsycopgMigrationModule, import_module("psycopg"))
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for the Postgres smoke runner") from exc

    applied: list[str] = []
    with psycopg_module.connect(
        database_url,
        connect_timeout=connect_timeout_seconds,
    ) as connection, connection.cursor() as cursor:
        for migration_file in migration_files:
            for statement in split_sql_statements(
                migration_file.read_text(encoding="utf-8")
            ):
                cursor.execute(statement)
            applied.append(migration_file.name)
    return applied


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    single_quoted = False
    double_quoted = False
    dollar_quote_tag: str | None = None

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if dollar_quote_tag is not None:
            if sql.startswith(dollar_quote_tag, index):
                buffer.append(dollar_quote_tag)
                index += len(dollar_quote_tag)
                dollar_quote_tag = None
                continue
            buffer.append(char)
            index += 1
            continue

        if single_quoted:
            buffer.append(char)
            if char == "'" and next_char == "'":
                buffer.append(next_char)
                index += 2
                continue
            if char == "'":
                single_quoted = False
            index += 1
            continue

        if double_quoted:
            buffer.append(char)
            if char == '"' and next_char == '"':
                buffer.append(next_char)
                index += 2
                continue
            if char == '"':
                double_quoted = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            index = _skip_line_comment(sql, index + 2)
            buffer.append("\n")
            continue

        if char == "/" and next_char == "*":
            index = _skip_block_comment(sql, index + 2)
            buffer.append("\n")
            continue

        dollar_quote_tag = _dollar_quote_tag_at(sql, index)
        if dollar_quote_tag is not None:
            buffer.append(dollar_quote_tag)
            index += len(dollar_quote_tag)
            continue

        if char == "'":
            single_quoted = True
            buffer.append(char)
            index += 1
            continue

        if char == '"':
            double_quoted = True
            buffer.append(char)
            index += 1
            continue

        if char == ";":
            _append_sql_statement(statements, buffer)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    _append_sql_statement(statements, buffer)
    return statements


def _append_sql_statement(statements: list[str], buffer: list[str]) -> None:
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)


def _skip_line_comment(sql: str, index: int) -> int:
    while index < len(sql) and sql[index] not in "\r\n":
        index += 1
    return index


def _skip_block_comment(sql: str, index: int) -> int:
    while index + 1 < len(sql):
        if sql[index] == "*" and sql[index + 1] == "/":
            return index + 2
        index += 1
    return len(sql)


def _dollar_quote_tag_at(sql: str, index: int) -> str | None:
    if sql[index] != "$":
        return None
    end = index + 1
    while end < len(sql) and (sql[end].isalnum() or sql[end] == "_"):
        end += 1
    if end < len(sql) and sql[end] == "$":
        return sql[index : end + 1]
    return None


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    result = run_accuracy_postgres_smoke(
        database_url=args.database_url or settings.database_url,
        migration_dir=Path(args.migration_dir),
        apply_migrations_first=not args.skip_migrations,
        reset=not args.no_reset,
        connect_timeout_seconds=args.connect_timeout_seconds
        or settings.database_connect_timeout_seconds,
    )
    print(result.model_dump_json(indent=2))


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(description="Run Nutmeg Accuracy Postgres smoke loop.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--migration-dir", default=str(DEFAULT_MIGRATION_DIR))
    parser.add_argument("--skip-migrations", action="store_true")
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
