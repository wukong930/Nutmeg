from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

FIXTURE_AVAILABILITY_COVERAGE_ROWS_QUERY = """
WITH availability AS (
  SELECT
    fixture_id,
    COUNT(availability_snapshot_id) AS availability_snapshot_count,
    MAX(snapshot_time_utc) AS latest_availability_snapshot_time_utc
  FROM player_availability_snapshots
  WHERE fixture_id = ANY(%(fixture_ids)s::text[])
    AND snapshot_time_utc <= %(as_of_time_utc)s::timestamptz
  GROUP BY fixture_id
),
lineups AS (
  SELECT
    fixture_id,
    COUNT(lineup_snapshot_id) AS lineup_snapshot_count,
    MAX(snapshot_time_utc) AS latest_lineup_snapshot_time_utc
  FROM lineup_snapshots
  WHERE fixture_id = ANY(%(fixture_ids)s::text[])
    AND snapshot_time_utc <= %(as_of_time_utc)s::timestamptz
  GROUP BY fixture_id
)
SELECT
  f.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  f.kickoff_time_utc,
  COALESCE(a.availability_snapshot_count, 0) AS availability_snapshot_count,
  a.latest_availability_snapshot_time_utc,
  COALESCE(l.lineup_snapshot_count, 0) AS lineup_snapshot_count,
  l.latest_lineup_snapshot_time_utc
FROM fixtures f
JOIN competitions c
  ON c.competition_id = f.competition_id
LEFT JOIN availability a
  ON a.fixture_id = f.fixture_id
LEFT JOIN lineups l
  ON l.fixture_id = f.fixture_id
WHERE f.fixture_id = ANY(%(fixture_ids)s::text[])
ORDER BY f.kickoff_time_utc ASC, f.fixture_id ASC
"""


class AvailabilityCoverageDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only availability coverage query."""


class FixtureAvailabilityCoverage(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_time_utc: datetime
    availability_snapshot_count: int = Field(ge=0)
    lineup_snapshot_count: int = Field(ge=0)
    latest_availability_snapshot_time_utc: datetime | None = None
    availability_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    latest_lineup_snapshot_time_utc: datetime | None = None
    lineup_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    has_availability: bool
    has_lineup: bool
    availability_fresh_enough: bool
    lineup_fresh_enough: bool
    fresh_enough: bool


class PostgresAvailabilityCoverageRepository:
    def __init__(self, database: AvailabilityCoverageDatabaseExecutor) -> None:
        self.database = database

    def list_fixture_coverage(
        self,
        *,
        fixture_ids: Sequence[str],
        as_of_time_utc: datetime,
        max_snapshot_lag_hours: int,
    ) -> list[FixtureAvailabilityCoverage]:
        if not fixture_ids:
            return []
        normalized_as_of = _aware_utc(as_of_time_utc)
        rows = self.database.fetch_all(
            FIXTURE_AVAILABILITY_COVERAGE_ROWS_QUERY,
            {
                "fixture_ids": list(dict.fromkeys(fixture_ids)),
                "as_of_time_utc": normalized_as_of,
            },
        )
        return [
            _availability_coverage_from_row(
                row,
                max_snapshot_lag_hours=max_snapshot_lag_hours,
            )
            for row in rows
        ]


def _availability_coverage_from_row(
    row: DatabaseRow,
    *,
    max_snapshot_lag_hours: int,
) -> FixtureAvailabilityCoverage:
    kickoff_time = _datetime(row["kickoff_time_utc"])
    latest_availability_time = _optional_datetime(
        row["latest_availability_snapshot_time_utc"]
    )
    latest_lineup_time = _optional_datetime(row["latest_lineup_snapshot_time_utc"])
    availability_lag = _snapshot_lag_hours(kickoff_time, latest_availability_time)
    lineup_lag = _snapshot_lag_hours(kickoff_time, latest_lineup_time)
    availability_snapshot_count = _int(row["availability_snapshot_count"])
    lineup_snapshot_count = _int(row["lineup_snapshot_count"])
    availability_fresh = (
        availability_lag is not None and availability_lag <= max_snapshot_lag_hours
    )
    lineup_fresh = lineup_lag is not None and lineup_lag <= max_snapshot_lag_hours
    return FixtureAvailabilityCoverage(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        kickoff_time_utc=kickoff_time,
        availability_snapshot_count=availability_snapshot_count,
        lineup_snapshot_count=lineup_snapshot_count,
        latest_availability_snapshot_time_utc=latest_availability_time,
        availability_snapshot_lag_hours=availability_lag,
        latest_lineup_snapshot_time_utc=latest_lineup_time,
        lineup_snapshot_lag_hours=lineup_lag,
        has_availability=availability_snapshot_count > 0,
        has_lineup=lineup_snapshot_count > 0,
        availability_fresh_enough=availability_fresh,
        lineup_fresh_enough=lineup_fresh,
        fresh_enough=availability_fresh and lineup_fresh,
    )


def _snapshot_lag_hours(kickoff_time: datetime, snapshot_time: datetime | None) -> float | None:
    if snapshot_time is None:
        return None
    return round(max(0.0, (kickoff_time - snapshot_time).total_seconds() / 3600), 2)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    return int(str(value))
