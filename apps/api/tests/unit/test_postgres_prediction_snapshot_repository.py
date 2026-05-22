from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.predictions import build_mock_prediction_snapshot_with_context
from nutmeg.predictions.repository import (
    INSERT_MARKET_PREDICTION_QUERY,
    INSERT_POSTGRES_PREDICTION_SNAPSHOT_QUERY,
    INSERT_SCORE_GRID_QUERY,
    UPSERT_MODEL_VERSION_FOR_PREDICTION_QUERY,
    PostgresPredictionSnapshotRepository,
)


class FakePredictionDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.calls.append((query, params))
        if query == UPSERT_MODEL_VERSION_FOR_PREDICTION_QUERY:
            return {"model_version": params["model_version"]}
        if query == INSERT_SCORE_GRID_QUERY:
            return {"score_grid_id": 42}
        if query == INSERT_POSTGRES_PREDICTION_SNAPSHOT_QUERY:
            return {"prediction_snapshot_id": 84}
        if query == INSERT_MARKET_PREDICTION_QUERY:
            return {"market_prediction_id": len(self.calls)}
        raise AssertionError(f"unexpected query: {query}")


def test_postgres_prediction_repository_persists_model_grid_and_snapshot() -> None:
    prediction = build_mock_prediction_snapshot_with_context(
        "fix_epl_001",
        feature_snapshot_id=7,
        prediction_time_utc=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
    )
    assert prediction is not None
    database = FakePredictionDatabase()

    stored = PostgresPredictionSnapshotRepository(database).save(prediction)

    assert stored.prediction_snapshot_id == 84
    assert stored.score_grid_id == 42
    assert [query for query, _ in database.calls] == [
        UPSERT_MODEL_VERSION_FOR_PREDICTION_QUERY,
        INSERT_SCORE_GRID_QUERY,
        INSERT_POSTGRES_PREDICTION_SNAPSHOT_QUERY,
        *[INSERT_MARKET_PREDICTION_QUERY] * 19,
    ]
    prediction_params = database.calls[-1][1]
    market_prediction_params = [
        params for query, params in database.calls if query == INSERT_MARKET_PREDICTION_QUERY
    ]
    prediction_params = database.calls[2][1]
    assert prediction_params["fixture_id"] == "fix_epl_001"
    assert prediction_params["feature_snapshot_id"] == 7
    assert prediction_params["score_grid_id"] == 42
    assert '"home_win"' in str(prediction_params["market_probabilities_json"])
    assert market_prediction_params[0]["market_type"] == "1x2"
    assert market_prediction_params[0]["outcome"] == "home_win"
    assert market_prediction_params[0]["prediction_snapshot_id"] == 84
    assert any(
        params["market_type"] == "asian_handicap"
        and params["line"] == -0.25
        and params["side"] == "home"
        and params["outcome"] == "half_loss"
        for params in market_prediction_params
    )
    assert all(params["outcome"] != "expected_return" for params in market_prediction_params)
