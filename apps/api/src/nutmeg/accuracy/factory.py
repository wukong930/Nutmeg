from __future__ import annotations

from nutmeg.accuracy.mock_repository import MockAccuracyEventRepository
from nutmeg.accuracy.postgres_repository import PostgresAccuracyRepository
from nutmeg.accuracy.repository import AccuracyRepository
from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.providers.mock import list_mock_fixtures


def build_accuracy_repository(settings: Settings) -> AccuracyRepository:
    if settings.accuracy_repository == "postgres":
        return PostgresAccuracyRepository(
            PsycopgSyncDatabaseExecutor(
                settings.database_url,
                connect_timeout_seconds=settings.database_connect_timeout_seconds,
            )
        )
    return MockAccuracyEventRepository(_build_mock_prediction_snapshots())


def _build_mock_prediction_snapshots() -> dict[str, PredictionSnapshot]:
    snapshots: dict[str, PredictionSnapshot] = {}
    for fixture in list_mock_fixtures():
        prediction = build_mock_prediction_snapshot(fixture["fixture_id"])
        if prediction is not None:
            snapshots[fixture["fixture_id"]] = prediction
    return snapshots
