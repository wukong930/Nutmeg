from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.availability_coverage import (
    FIXTURE_AVAILABILITY_COVERAGE_ROWS_QUERY,
    PostgresAvailabilityCoverageRepository,
)


class FakeAvailabilityDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows


def test_postgres_availability_coverage_repository_lists_fixture_coverage() -> None:
    database = FakeAvailabilityDatabase([_covered_row(), _missing_row()])
    repository = PostgresAvailabilityCoverageRepository(database)

    coverage = repository.list_fixture_coverage(
        fixture_ids=["fix_epl_001", "fix_epl_001", "fix_epl_002"],
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        max_snapshot_lag_hours=24,
    )

    assert database.calls[0][0] == FIXTURE_AVAILABILITY_COVERAGE_ROWS_QUERY
    assert database.calls[0][1]["fixture_ids"] == ["fix_epl_001", "fix_epl_002"]
    assert len(coverage) == 2
    assert coverage[0].fixture_id == "fix_epl_001"
    assert coverage[0].has_availability is True
    assert coverage[0].has_lineup is True
    assert coverage[0].fresh_enough is True
    assert coverage[0].availability_snapshot_lag_hours == 2.0
    assert coverage[0].lineup_snapshot_lag_hours == 3.0
    assert coverage[1].has_availability is False
    assert coverage[1].has_lineup is False
    assert coverage[1].fresh_enough is False


def _covered_row() -> Mapping[str, object]:
    return {
        "fixture_id": "fix_epl_001",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "kickoff_time_utc": "2026-05-06T19:00:00+00:00",
        "availability_snapshot_count": Decimal("2"),
        "latest_availability_snapshot_time_utc": "2026-05-06T17:00:00+00:00",
        "lineup_snapshot_count": Decimal("22"),
        "latest_lineup_snapshot_time_utc": "2026-05-06T16:00:00+00:00",
    }


def _missing_row() -> Mapping[str, object]:
    return {
        "fixture_id": "fix_epl_002",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "kickoff_time_utc": "2026-05-06T21:00:00+00:00",
        "availability_snapshot_count": Decimal("0"),
        "latest_availability_snapshot_time_utc": None,
        "lineup_snapshot_count": Decimal("0"),
        "latest_lineup_snapshot_time_utc": None,
    }
