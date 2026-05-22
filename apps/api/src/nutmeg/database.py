from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from importlib import import_module
from typing import Protocol, cast

type QueryParams = Mapping[str, object]
type DatabaseRow = Mapping[str, object]


class DatabaseReadError(RuntimeError):
    """Raised when a configured database read cannot be completed."""


class DatabaseCursor(Protocol):
    def execute(self, query: str, params: QueryParams) -> object:
        """Execute a SQL statement with named parameters."""

    def fetchall(self) -> Sequence[DatabaseRow]:
        """Return all rows as mapping-like records."""

    def fetchone(self) -> DatabaseRow | None:
        """Return one row as a mapping-like record."""


class DatabaseConnection(Protocol):
    def cursor(self, *, row_factory: object) -> AbstractContextManager[DatabaseCursor]:
        """Open a cursor using a mapping row factory."""


class PsycopgModule(Protocol):
    connect: Callable[..., AbstractContextManager[DatabaseConnection]]


class PsycopgRowsModule(Protocol):
    dict_row: object


class PsycopgSyncDatabaseExecutor:
    """Small synchronous read executor for repository adapters.

    The psycopg import is intentionally lazy so the mock-first local API and
    unit tests do not require a live Postgres driver until the Postgres-backed
    repository mode is selected.
    """

    def __init__(self, database_url: str, *, connect_timeout_seconds: int = 3) -> None:
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        try:
            psycopg_module = cast(PsycopgModule, import_module("psycopg"))
            rows_module = cast(PsycopgRowsModule, import_module("psycopg.rows"))
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "psycopg is required when NUTMEG_ACCURACY_REPOSITORY=postgres"
            ) from exc

        try:
            with psycopg_module.connect(
                self.database_url,
                connect_timeout=self.connect_timeout_seconds,
            ) as connection, connection.cursor(row_factory=rows_module.dict_row) as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            raise DatabaseReadError("database read failed") from exc

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        try:
            psycopg_module = cast(PsycopgModule, import_module("psycopg"))
            rows_module = cast(PsycopgRowsModule, import_module("psycopg.rows"))
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "psycopg is required when NUTMEG_ACCURACY_REPOSITORY=postgres"
            ) from exc

        try:
            with psycopg_module.connect(
                self.database_url,
                connect_timeout=self.connect_timeout_seconds,
            ) as connection, connection.cursor(row_factory=rows_module.dict_row) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
        except Exception as exc:
            raise DatabaseReadError("database read failed") from exc

    def execute(self, query: str, params: QueryParams) -> None:
        try:
            psycopg_module = cast(PsycopgModule, import_module("psycopg"))
            rows_module = cast(PsycopgRowsModule, import_module("psycopg.rows"))
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "psycopg is required when NUTMEG_ACCURACY_REPOSITORY=postgres"
            ) from exc

        try:
            with psycopg_module.connect(
                self.database_url,
                connect_timeout=self.connect_timeout_seconds,
            ) as connection, connection.cursor(row_factory=rows_module.dict_row) as cursor:
                cursor.execute(query, params)
        except Exception as exc:
            raise DatabaseReadError("database statement failed") from exc
