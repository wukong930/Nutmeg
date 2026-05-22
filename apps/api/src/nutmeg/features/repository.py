from __future__ import annotations

from json import dumps
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.features import FeatureSnapshot

INSERT_FEATURE_SNAPSHOT_QUERY = """
INSERT INTO feature_snapshots (
  fixture_id,
  feature_time_utc,
  feature_version,
  features_json,
  source_snapshot_refs,
  data_quality_score
) VALUES (
  %(fixture_id)s,
  %(feature_time_utc)s,
  %(feature_version)s,
  %(features_json)s::jsonb,
  %(source_snapshot_refs)s::jsonb,
  %(data_quality_score)s
)
RETURNING feature_snapshot_id
"""


class FeatureSnapshotWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""


class StoredFeatureSnapshot(BaseModel):
    feature_snapshot_id: int = Field(gt=0)
    snapshot: FeatureSnapshot


class PostgresFeatureSnapshotRepository:
    def __init__(self, database: FeatureSnapshotWriteDatabaseExecutor) -> None:
        self.database = database

    def save(self, snapshot: FeatureSnapshot) -> StoredFeatureSnapshot:
        row = _required_row(
            self.database.fetch_one(
                INSERT_FEATURE_SNAPSHOT_QUERY,
                {
                    "fixture_id": snapshot.fixture_id,
                    "feature_time_utc": snapshot.feature_time_utc,
                    "feature_version": snapshot.feature_version,
                    "features_json": _json(snapshot.features_json),
                    "source_snapshot_refs": _json(snapshot.source_snapshot_refs),
                    "data_quality_score": snapshot.data_quality_score,
                },
            )
        )
        return StoredFeatureSnapshot(
            feature_snapshot_id=_int(row["feature_snapshot_id"]),
            snapshot=snapshot,
        )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))
