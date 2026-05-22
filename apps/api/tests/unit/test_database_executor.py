from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace

import pytest

from nutmeg import database as database_module
from nutmeg.database import DatabaseReadError, DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams


class FakeCursor:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = rows
        self.executed: tuple[str, QueryParams] | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: QueryParams) -> object:
        self.executed = (query, params)
        return None

    def fetchall(self) -> Sequence[DatabaseRow]:
        return self.rows

    def fetchone(self) -> DatabaseRow | None:
        if not self.rows:
            return None
        return self.rows[0]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.row_factory: object | None = None

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def cursor(self, *, row_factory: object) -> FakeCursor:
        self.row_factory = row_factory
        return self.cursor_instance


def test_psycopg_executor_fetches_mapping_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    query = "SELECT * FROM prediction_evaluations WHERE fixture_id = %(fixture_id)s"
    params: Mapping[str, object] = {"fixture_id": "fix_epl_001"}
    dict_row = object()
    cursor = FakeCursor([{"fixture_id": "fix_epl_001", "sample_size": 1}])
    connection = FakeConnection(cursor)
    connect_calls: list[tuple[str, int]] = []

    def connect(database_url: str, *, connect_timeout: int) -> FakeConnection:
        connect_calls.append((database_url, connect_timeout))
        return connection

    def fake_import_module(name: str) -> object:
        if name == "psycopg":
            return SimpleNamespace(connect=connect)
        if name == "psycopg.rows":
            return SimpleNamespace(dict_row=dict_row)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)

    executor = PsycopgSyncDatabaseExecutor(
        "postgresql://nutmeg:test@localhost:5432/nutmeg",
        connect_timeout_seconds=7,
    )

    rows = executor.fetch_all(query, params)

    assert rows == [{"fixture_id": "fix_epl_001", "sample_size": 1}]
    assert connect_calls == [("postgresql://nutmeg:test@localhost:5432/nutmeg", 7)]
    assert connection.row_factory is dict_row
    assert cursor.executed == (query, params)


def test_psycopg_executor_fetches_one_mapping_row(monkeypatch: pytest.MonkeyPatch) -> None:
    dict_row = object()
    cursor = FakeCursor([{"evaluation_id": 42}])
    connection = FakeConnection(cursor)

    def connect(database_url: str, *, connect_timeout: int) -> FakeConnection:
        return connection

    def fake_import_module(name: str) -> object:
        if name == "psycopg":
            return SimpleNamespace(connect=connect)
        if name == "psycopg.rows":
            return SimpleNamespace(dict_row=dict_row)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)

    executor = PsycopgSyncDatabaseExecutor(
        "postgresql://nutmeg:test@localhost:5432/nutmeg",
        connect_timeout_seconds=7,
    )

    row = executor.fetch_one("INSERT ... RETURNING evaluation_id", {})

    assert row == {"evaluation_id": 42}
    assert connection.row_factory is dict_row


def test_psycopg_executor_executes_statement_without_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dict_row = object()
    cursor = FakeCursor([])
    connection = FakeConnection(cursor)

    def connect(database_url: str, *, connect_timeout: int) -> FakeConnection:
        return connection

    def fake_import_module(name: str) -> object:
        if name == "psycopg":
            return SimpleNamespace(connect=connect)
        if name == "psycopg.rows":
            return SimpleNamespace(dict_row=dict_row)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)

    executor = PsycopgSyncDatabaseExecutor(
        "postgresql://nutmeg:test@localhost:5432/nutmeg",
        connect_timeout_seconds=7,
    )

    executor.execute("DELETE FROM prediction_evaluations WHERE fixture_id = %(fixture_id)s", {})

    assert cursor.executed == (
        "DELETE FROM prediction_evaluations WHERE fixture_id = %(fixture_id)s",
        {},
    )
    assert connection.row_factory is dict_row


def test_psycopg_executor_reports_missing_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import_module(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)

    executor = PsycopgSyncDatabaseExecutor("postgresql://nutmeg:nutmeg@localhost/nutmeg")

    with pytest.raises(RuntimeError, match="psycopg"):
        executor.fetch_all("SELECT 1", {})


def test_psycopg_executor_wraps_database_read_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def connect(database_url: str, *, connect_timeout: int) -> FakeConnection:
        raise OSError("connection refused")

    def fake_import_module(name: str) -> object:
        if name == "psycopg":
            return SimpleNamespace(connect=connect)
        if name == "psycopg.rows":
            return SimpleNamespace(dict_row=object())
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)

    executor = PsycopgSyncDatabaseExecutor("postgresql://nutmeg:nutmeg@localhost/nutmeg")

    with pytest.raises(DatabaseReadError, match="database read failed"):
        executor.fetch_all("SELECT 1", {})
