from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.features import FeatureSnapshot
from nutmeg.features import PostgresFeatureSnapshotRepository


class FakeFeatureDatabase:
    def __init__(self) -> None:
        self.queries: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.queries.append((query, params))
        if "INSERT INTO feature_snapshots" in query:
            return {"feature_snapshot_id": 91}
        raise AssertionError(f"unexpected query: {query}")


def test_feature_snapshot_repository_persists_json_refs_and_quality_score() -> None:
    database = FakeFeatureDatabase()
    repository = PostgresFeatureSnapshotRepository(database)
    snapshot = FeatureSnapshot(
        fixture_id="fix_epl_001",
        feature_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        feature_version="features-m1.0.0",
        features_json={"coverage": {"odds": {"score": 1.0}}},
        source_snapshot_refs={"odds": {"snapshot_count": 6}},
        data_quality_score=85.7,
    )

    stored = repository.save(snapshot)

    assert stored.feature_snapshot_id == 91
    assert stored.snapshot == snapshot
    params = database.queries[0][1]
    assert params["fixture_id"] == "fix_epl_001"
    assert params["feature_version"] == "features-m1.0.0"
    assert params["data_quality_score"] == 85.7
    assert '"snapshot_count":6' in str(params["source_snapshot_refs"])
