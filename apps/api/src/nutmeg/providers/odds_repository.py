from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow
from nutmeg.providers.canonical_repository import (
    UPSERT_PROVIDER_MAPPING_QUERY,
    CanonicalWriteDatabaseExecutor,
)
from nutmeg.providers.the_odds_api.normalizer import NormalizedOddsSnapshot

INSERT_ODDS_SNAPSHOT_QUERY = """
INSERT INTO odds_snapshots (
  fixture_id,
  provider,
  bookmaker,
  market_type,
  line,
  side,
  outcome,
  decimal_odds,
  raw_implied_probability,
  fair_probability,
  overround,
  snapshot_time_utc,
  is_opening,
  is_closing,
  payload_id
) VALUES (
  %(fixture_id)s,
  %(provider)s,
  %(bookmaker)s,
  %(market_type)s,
  %(line)s,
  %(side)s,
  %(outcome)s,
  %(decimal_odds)s,
  %(raw_implied_probability)s,
  %(fair_probability)s,
  %(overround)s,
  %(snapshot_time_utc)s,
  %(is_opening)s,
  %(is_closing)s,
  %(payload_id)s
)
ON CONFLICT (
  fixture_id,
  provider,
  bookmaker,
  market_type,
  line,
  side,
  outcome,
  snapshot_time_utc
)
DO UPDATE SET
  decimal_odds = EXCLUDED.decimal_odds,
  raw_implied_probability = EXCLUDED.raw_implied_probability,
  fair_probability = EXCLUDED.fair_probability,
  overround = EXCLUDED.overround,
  is_opening = EXCLUDED.is_opening,
  is_closing = EXCLUDED.is_closing,
  payload_id = EXCLUDED.payload_id
RETURNING odds_snapshot_id, (xmax = 0) AS inserted
"""


class OddsSnapshotWriteSummary(BaseModel):
    odds_snapshots: int = Field(default=0, ge=0)
    inserted_snapshots: int = Field(default=0, ge=0)
    updated_snapshots: int = Field(default=0, ge=0)
    provider_mappings: int = Field(default=0, ge=0)
    bookmaker_count: int = Field(default=0, ge=0)
    market_types: list[str] = Field(default_factory=list)
    canonical_fixture_id: str


class PostgresOddsSnapshotRepository:
    def __init__(self, database: CanonicalWriteDatabaseExecutor) -> None:
        self.database = database

    def save_the_odds_api_event_odds(
        self,
        snapshots: Sequence[NormalizedOddsSnapshot],
        *,
        canonical_fixture_id: str,
        provider_event_id: str,
        payload_id: int,
    ) -> OddsSnapshotWriteSummary:
        if not snapshots:
            return OddsSnapshotWriteSummary(canonical_fixture_id=canonical_fixture_id)

        first = snapshots[0]
        _required_row(
            self.database.fetch_one(
                UPSERT_PROVIDER_MAPPING_QUERY,
                {
                    "provider": first.provider,
                    "entity_type": "fixture",
                    "provider_entity_id": provider_event_id,
                    "canonical_entity_id": canonical_fixture_id,
                    "confidence": 1.0,
                },
            )
        )

        snapshot_count = 0
        inserted_count = 0
        updated_count = 0
        for snapshot in snapshots:
            row = _required_row(
                self.database.fetch_one(
                    INSERT_ODDS_SNAPSHOT_QUERY,
                    _snapshot_params(
                        snapshot,
                        canonical_fixture_id=canonical_fixture_id,
                        payload_id=payload_id,
                    ),
                )
            )
            snapshot_count += 1
            if _bool(row.get("inserted")):
                inserted_count += 1
            else:
                updated_count += 1

        return OddsSnapshotWriteSummary(
            odds_snapshots=snapshot_count,
            inserted_snapshots=inserted_count,
            updated_snapshots=updated_count,
            provider_mappings=1,
            bookmaker_count=len({snapshot.bookmaker for snapshot in snapshots}),
            market_types=sorted({str(snapshot.market_type) for snapshot in snapshots}),
            canonical_fixture_id=canonical_fixture_id,
        )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _snapshot_params(
    snapshot: NormalizedOddsSnapshot,
    *,
    canonical_fixture_id: str,
    payload_id: int,
) -> dict[str, object]:
    return {
        "fixture_id": canonical_fixture_id,
        "provider": snapshot.provider,
        "bookmaker": snapshot.bookmaker,
        "market_type": snapshot.market_type,
        "line": snapshot.line,
        "side": snapshot.side,
        "outcome": snapshot.outcome,
        "decimal_odds": snapshot.decimal_odds,
        "raw_implied_probability": snapshot.raw_implied_probability,
        "fair_probability": snapshot.fair_probability,
        "overround": snapshot.overround,
        "snapshot_time_utc": snapshot.snapshot_time_utc,
        "is_opening": False,
        "is_closing": False,
        "payload_id": payload_id,
    }


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"true", "t", "1", "yes"}
