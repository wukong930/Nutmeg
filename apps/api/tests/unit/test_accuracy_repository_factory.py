from __future__ import annotations

from nutmeg.accuracy.factory import build_accuracy_repository
from nutmeg.accuracy.mock_repository import MockAccuracyEventRepository
from nutmeg.accuracy.postgres_repository import PostgresAccuracyRepository
from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor


def test_accuracy_repository_factory_uses_mock_by_default() -> None:
    repository = build_accuracy_repository(Settings())

    assert isinstance(repository, MockAccuracyEventRepository)
    assert repository.list_evaluation_events()


def test_accuracy_repository_factory_can_select_postgres_executor() -> None:
    repository = build_accuracy_repository(
        Settings(
            accuracy_repository="postgres",
            database_url="postgresql://nutmeg:test@localhost:5432/nutmeg",
            database_connect_timeout_seconds=9,
        )
    )

    assert isinstance(repository, PostgresAccuracyRepository)
    assert isinstance(repository.database, PsycopgSyncDatabaseExecutor)
    assert repository.database.database_url == "postgresql://nutmeg:test@localhost:5432/nutmeg"
    assert repository.database.connect_timeout_seconds == 9
