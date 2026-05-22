from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.odds_coverage import (
    FIXTURE_ODDS_COVERAGE_ROWS_QUERY,
    ODDS_COVERAGE_GAP_ROWS_QUERY,
    ODDS_COVERAGE_ROWS_QUERY,
    PostgresOddsCoverageRepository,
)


class FakeCoverageDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows


class FakeSequentialCoverageDatabase:
    def __init__(self, responses: Sequence[Sequence[DatabaseRow]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.responses[len(self.calls) - 1]


def test_postgres_odds_coverage_repository_builds_component_patch() -> None:
    database = FakeCoverageDatabase([_covered_row(), _missing_row()])
    repository = PostgresOddsCoverageRepository(database)

    report = repository.build_competition_report(
        competition_id="EPL",
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        window_days=30,
        max_snapshot_lag_hours=24,
    )

    assert database.calls[0][0] == ODDS_COVERAGE_ROWS_QUERY
    assert database.calls[0][1]["competition_id"] == "EPL"
    assert report.fixture_count == 2
    assert report.fixtures_with_any_odds == 1
    assert report.fixtures_with_1x2 == 1
    assert report.fixtures_with_handicap == 1
    assert report.fresh_odds_fixture_count == 1
    assert report.odds_snapshot_count == 5
    assert report.bookmaker_count == 2
    assert report.average_bookmakers_per_fixture == 1.0
    assert report.odds_coverage == 0.5
    assert report.handicap_coverage == 0.5
    assert report.fresh_odds_coverage == 0.5
    assert report.market_types == ["1x2", "asian_handicap"]
    assert report.data_quality_component_patch.odds_coverage == 0.5
    assert report.data_quality_component_patch.handicap_coverage == 0.5
    assert report.data_quality_component_patch.data_freshness == 0.5
    assert report.fixtures[0].latest_snapshot_lag_hours == 2.0


def test_postgres_odds_coverage_repository_handles_empty_window() -> None:
    repository = PostgresOddsCoverageRepository(FakeCoverageDatabase([]))

    report = repository.build_competition_report(
        competition_id="JPN_J1",
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        window_days=30,
        max_snapshot_lag_hours=24,
    )

    assert report.competition_id == "JPN_J1"
    assert report.competition_name == "JPN_J1"
    assert report.fixture_count == 0
    assert report.odds_coverage == 0.0
    assert report.data_quality_component_patch.data_freshness == 0.0


def test_postgres_odds_coverage_repository_builds_gap_report() -> None:
    database = FakeSequentialCoverageDatabase(
        [
            [_covered_row(), _missing_row(), _stale_row()],
            [_gap_no_odds_row(), _gap_stale_row()],
        ]
    )
    repository = PostgresOddsCoverageRepository(database)

    report = repository.build_gap_report(
        competition_id="EPL",
        provider="the-odds-api",
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        window_days=90,
        max_snapshot_lag_hours=168,
        limit=50,
    )

    assert database.calls[0][0] == ODDS_COVERAGE_ROWS_QUERY
    assert database.calls[1][0] == ODDS_COVERAGE_GAP_ROWS_QUERY
    assert database.calls[1][1]["provider"] == "the-odds-api"
    assert database.calls[1][1]["limit"] == 50
    assert report.fixture_count == 3
    assert report.gap_count == 2
    assert report.no_odds_count == 1
    assert report.stale_odds_count == 1
    assert report.provider_event_unavailable_count == 1
    assert report.missing_1x2_count == 0
    assert report.missing_handicap_count == 1
    assert report.unmapped_fixture_count == 1
    assert report.mapped_gap_count == 1
    assert report.items[0].issue_types == [
        "unmapped",
        "provider_event_unavailable",
        "no_odds",
    ]
    assert report.items[0].recommended_action == "try_fallback_provider_event_mapping"
    assert report.items[0].fallback_candidates[0].provider_name == "api-football"
    assert report.items[0].fallback_candidates[1].provider_name == "sportmonks"
    assert report.items[1].issue_types == ["stale_odds", "missing_market"]
    assert report.items[1].provider_event_id == "odds_event_002"
    assert report.items[1].provider_mapping_confidence == 0.97


def test_postgres_odds_coverage_repository_lists_fixture_coverage() -> None:
    database = FakeCoverageDatabase([_covered_row()])
    repository = PostgresOddsCoverageRepository(database)

    fixtures = repository.list_fixture_coverage(
        fixture_ids=["fix_epl_001", "fix_epl_001"],
        as_of_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        max_snapshot_lag_hours=24,
    )

    assert database.calls[0][0] == FIXTURE_ODDS_COVERAGE_ROWS_QUERY
    assert database.calls[0][1]["fixture_ids"] == ["fix_epl_001"]
    assert len(fixtures) == 1
    assert fixtures[0].fixture_id == "fix_epl_001"
    assert fixtures[0].has_1x2 is True
    assert fixtures[0].has_handicap is True
    assert fixtures[0].fresh_enough is True


def _covered_row() -> Mapping[str, object]:
    return {
        "fixture_id": "fix_epl_001",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "kickoff_time_utc": "2026-05-06T19:00:00+00:00",
        "odds_snapshot_count": Decimal("5"),
        "bookmaker_count": Decimal("2"),
        "one_x_two_count": Decimal("3"),
        "handicap_count": Decimal("2"),
        "latest_snapshot_time_utc": "2026-05-06T17:00:00+00:00",
        "market_types_json": '["1x2", "asian_handicap"]',
    }


def _missing_row() -> Mapping[str, object]:
    return {
        "fixture_id": "fix_epl_002",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "kickoff_time_utc": "2026-05-07T19:00:00+00:00",
        "odds_snapshot_count": Decimal("0"),
        "bookmaker_count": Decimal("0"),
        "one_x_two_count": Decimal("0"),
        "handicap_count": Decimal("0"),
        "latest_snapshot_time_utc": None,
        "market_types_json": "[]",
    }


def _stale_row() -> Mapping[str, object]:
    return {
        "fixture_id": "fix_epl_003",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "kickoff_time_utc": "2026-05-08T19:00:00+00:00",
        "odds_snapshot_count": Decimal("3"),
        "bookmaker_count": Decimal("1"),
        "one_x_two_count": Decimal("3"),
        "handicap_count": Decimal("0"),
        "latest_snapshot_time_utc": "2026-04-28T17:00:00+00:00",
        "market_types_json": '["1x2"]',
    }


def _gap_no_odds_row() -> Mapping[str, object]:
    row = dict(_missing_row())
    row.update(
        {
            "home_team_name": "Arsenal",
            "away_team_name": "Brighton",
            "mapping_id": None,
            "provider_entity_id": None,
            "mapping_confidence": None,
            "mapping_updated_at": None,
        }
    )
    return row


def _gap_stale_row() -> Mapping[str, object]:
    row = dict(_stale_row())
    row.update(
        {
            "home_team_name": "Chelsea",
            "away_team_name": "Everton",
            "mapping_id": Decimal("42"),
            "provider_entity_id": "odds_event_002",
            "mapping_confidence": Decimal("0.97"),
            "mapping_updated_at": "2026-05-01T08:00:00+00:00",
        }
    )
    return row
