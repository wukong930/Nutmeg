from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from json import loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

ODDS_COVERAGE_ROWS_QUERY = """
SELECT
  f.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  f.kickoff_time_utc,
  COUNT(os.odds_snapshot_id) AS odds_snapshot_count,
  COUNT(DISTINCT os.bookmaker) FILTER (WHERE os.bookmaker IS NOT NULL) AS bookmaker_count,
  COUNT(os.odds_snapshot_id) FILTER (WHERE os.market_type = '1x2') AS one_x_two_count,
  COUNT(os.odds_snapshot_id) FILTER (
    WHERE os.market_type IN ('asian_handicap', 'cn_handicap_1x2', 'european_handicap_1x2')
  ) AS handicap_count,
  MAX(os.snapshot_time_utc) AS latest_snapshot_time_utc,
  COALESCE(jsonb_agg(DISTINCT os.market_type) FILTER (WHERE os.market_type IS NOT NULL), '[]')
    AS market_types_json
FROM fixtures f
JOIN competitions c
  ON c.competition_id = f.competition_id
LEFT JOIN odds_snapshots os
  ON os.fixture_id = f.fixture_id
  AND os.snapshot_time_utc <= LEAST(f.kickoff_time_utc, %(as_of_time_utc)s::timestamptz)
WHERE f.competition_id = %(competition_id)s
  AND f.kickoff_time_utc >= %(window_start_utc)s
  AND f.kickoff_time_utc < %(as_of_time_utc)s
GROUP BY
  f.fixture_id,
  f.competition_id,
  c.name,
  f.kickoff_time_utc
ORDER BY f.kickoff_time_utc DESC, f.fixture_id ASC
"""

FIXTURE_ODDS_COVERAGE_ROWS_QUERY = """
SELECT
  f.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  f.kickoff_time_utc,
  COUNT(os.odds_snapshot_id) AS odds_snapshot_count,
  COUNT(DISTINCT os.bookmaker) FILTER (WHERE os.bookmaker IS NOT NULL) AS bookmaker_count,
  COUNT(os.odds_snapshot_id) FILTER (WHERE os.market_type = '1x2') AS one_x_two_count,
  COUNT(os.odds_snapshot_id) FILTER (
    WHERE os.market_type IN ('asian_handicap', 'cn_handicap_1x2', 'european_handicap_1x2')
  ) AS handicap_count,
  MAX(os.snapshot_time_utc) AS latest_snapshot_time_utc,
  COALESCE(jsonb_agg(DISTINCT os.market_type) FILTER (WHERE os.market_type IS NOT NULL), '[]')
    AS market_types_json
FROM fixtures f
JOIN competitions c
  ON c.competition_id = f.competition_id
LEFT JOIN odds_snapshots os
  ON os.fixture_id = f.fixture_id
  AND os.snapshot_time_utc <= LEAST(f.kickoff_time_utc, %(as_of_time_utc)s::timestamptz)
WHERE f.fixture_id = ANY(%(fixture_ids)s::text[])
GROUP BY
  f.fixture_id,
  f.competition_id,
  c.name,
  f.kickoff_time_utc
ORDER BY f.kickoff_time_utc ASC, f.fixture_id ASC
"""

ODDS_COVERAGE_GAP_ROWS_QUERY = """
SELECT
  f.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  f.kickoff_time_utc,
  ht.name AS home_team_name,
  at.name AS away_team_name,
  COUNT(os.odds_snapshot_id) AS odds_snapshot_count,
  COUNT(DISTINCT os.bookmaker) FILTER (WHERE os.bookmaker IS NOT NULL) AS bookmaker_count,
  COUNT(os.odds_snapshot_id) FILTER (WHERE os.market_type = '1x2') AS one_x_two_count,
  COUNT(os.odds_snapshot_id) FILTER (
    WHERE os.market_type IN ('asian_handicap', 'cn_handicap_1x2', 'european_handicap_1x2')
  ) AS handicap_count,
  MAX(os.snapshot_time_utc) AS latest_snapshot_time_utc,
  COALESCE(jsonb_agg(DISTINCT os.market_type) FILTER (WHERE os.market_type IS NOT NULL), '[]')
    AS market_types_json,
  pem.mapping_id,
  pem.provider_entity_id,
  pem.confidence AS mapping_confidence,
  pem.updated_at AS mapping_updated_at
FROM fixtures f
JOIN competitions c
  ON c.competition_id = f.competition_id
JOIN teams ht
  ON ht.team_id = f.home_team_id
JOIN teams at
  ON at.team_id = f.away_team_id
LEFT JOIN LATERAL (
  SELECT
    mapping_id,
    provider_entity_id,
    confidence,
    updated_at
  FROM provider_entity_mappings
  WHERE provider = %(provider)s
    AND entity_type = 'fixture'
    AND canonical_entity_id = f.fixture_id
  ORDER BY confidence DESC, updated_at DESC, mapping_id DESC
  LIMIT 1
) pem ON true
LEFT JOIN odds_snapshots os
  ON os.fixture_id = f.fixture_id
  AND os.snapshot_time_utc <= LEAST(f.kickoff_time_utc, %(as_of_time_utc)s::timestamptz)
WHERE f.competition_id = %(competition_id)s
  AND f.kickoff_time_utc >= %(window_start_utc)s
  AND f.kickoff_time_utc < %(as_of_time_utc)s
GROUP BY
  f.fixture_id,
  f.competition_id,
  c.name,
  f.kickoff_time_utc,
  ht.name,
  at.name,
  pem.mapping_id,
  pem.provider_entity_id,
  pem.confidence,
  pem.updated_at
HAVING
  COUNT(os.odds_snapshot_id) = 0
  OR COUNT(os.odds_snapshot_id) FILTER (WHERE os.market_type = '1x2') = 0
  OR COUNT(os.odds_snapshot_id) FILTER (
    WHERE os.market_type IN ('asian_handicap', 'cn_handicap_1x2', 'european_handicap_1x2')
  ) = 0
  OR MAX(os.snapshot_time_utc) IS NULL
  OR EXTRACT(EPOCH FROM (f.kickoff_time_utc - MAX(os.snapshot_time_utc))) / 3600
    > %(max_snapshot_lag_hours)s
ORDER BY
  CASE
    WHEN COUNT(os.odds_snapshot_id) = 0 THEN 0
    WHEN MAX(os.snapshot_time_utc) IS NULL
      OR EXTRACT(EPOCH FROM (f.kickoff_time_utc - MAX(os.snapshot_time_utc))) / 3600
        > %(max_snapshot_lag_hours)s THEN 1
    ELSE 2
  END,
  f.kickoff_time_utc ASC,
  f.fixture_id ASC
LIMIT %(limit)s
"""


class OddsCoverageDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only coverage query and return mapping rows."""


class FixtureOddsCoverage(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_time_utc: datetime
    odds_snapshot_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    has_any_odds: bool
    has_1x2: bool
    has_handicap: bool
    latest_snapshot_time_utc: datetime | None = None
    latest_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    fresh_enough: bool
    market_types: list[str] = Field(default_factory=list)


type OddsCoverageGapStatus = Literal[
    "no_odds",
    "missing_market",
    "stale_odds",
    "unmapped",
    "provider_event_unavailable",
]


class OddsCoverageFallbackProviderCandidate(BaseModel):
    provider_name: str
    coverage_role: str
    adapter_status: Literal["supported_now", "adapter_planned"]
    required_env_var: str
    recommended_action: str


class OddsCoverageGapItem(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    issue_types: list[OddsCoverageGapStatus]
    recommended_action: str
    odds_snapshot_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    has_1x2: bool
    has_handicap: bool
    fresh_enough: bool
    latest_snapshot_time_utc: datetime | None = None
    latest_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    market_types: list[str] = Field(default_factory=list)
    has_provider_mapping: bool
    provider: str
    provider_event_id: str | None = None
    provider_mapping_id: int | None = Field(default=None, gt=0)
    provider_mapping_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider_mapping_updated_at_utc: datetime | None = None
    event_availability_note: str | None = None
    fallback_candidates: list[OddsCoverageFallbackProviderCandidate] = Field(
        default_factory=list
    )


class OddsCoverageGapReport(BaseModel):
    competition_id: str
    competition_name: str
    provider: str
    window_start_utc: datetime
    as_of_time_utc: datetime
    max_snapshot_lag_hours: int = Field(gt=0)
    fixture_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    no_odds_count: int = Field(ge=0)
    stale_odds_count: int = Field(ge=0)
    provider_event_unavailable_count: int = Field(default=0, ge=0)
    missing_1x2_count: int = Field(ge=0)
    missing_handicap_count: int = Field(ge=0)
    unmapped_fixture_count: int = Field(ge=0)
    mapped_gap_count: int = Field(ge=0)
    items: list[OddsCoverageGapItem] = Field(default_factory=list)
    generated_at_utc: datetime


class OddsCoverageComponentPatch(BaseModel):
    odds_coverage: float = Field(ge=0.0, le=1.0)
    handicap_coverage: float = Field(ge=0.0, le=1.0)
    data_freshness: float = Field(ge=0.0, le=1.0)


class CompetitionOddsCoverageReport(BaseModel):
    competition_id: str
    competition_name: str
    window_start_utc: datetime
    as_of_time_utc: datetime
    max_snapshot_lag_hours: int = Field(gt=0)
    fixture_count: int = Field(ge=0)
    fixtures_with_any_odds: int = Field(ge=0)
    fixtures_with_1x2: int = Field(ge=0)
    fixtures_with_handicap: int = Field(ge=0)
    fresh_odds_fixture_count: int = Field(ge=0)
    odds_snapshot_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    average_bookmakers_per_fixture: float = Field(ge=0.0)
    odds_coverage: float = Field(ge=0.0, le=1.0)
    one_x_two_coverage: float = Field(ge=0.0, le=1.0)
    handicap_coverage: float = Field(ge=0.0, le=1.0)
    fresh_odds_coverage: float = Field(ge=0.0, le=1.0)
    market_types: list[str] = Field(default_factory=list)
    data_quality_component_patch: OddsCoverageComponentPatch
    fixtures: list[FixtureOddsCoverage] = Field(default_factory=list)
    generated_at_utc: datetime


class PostgresOddsCoverageRepository:
    def __init__(self, database: OddsCoverageDatabaseExecutor) -> None:
        self.database = database

    def build_competition_report(
        self,
        *,
        competition_id: str,
        as_of_time_utc: datetime,
        window_days: int,
        max_snapshot_lag_hours: int,
    ) -> CompetitionOddsCoverageReport:
        normalized_as_of = _aware_utc(as_of_time_utc)
        window_start = normalized_as_of - timedelta(days=window_days)
        rows = self.database.fetch_all(
            ODDS_COVERAGE_ROWS_QUERY,
            {
                "competition_id": competition_id,
                "as_of_time_utc": normalized_as_of,
                "window_start_utc": window_start,
            },
        )
        fixtures = [
            _fixture_coverage_from_row(row, max_snapshot_lag_hours=max_snapshot_lag_hours)
            for row in rows
        ]
        return build_odds_coverage_report(
            fixtures,
            competition_id=competition_id,
            window_start_utc=window_start,
            as_of_time_utc=normalized_as_of,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
        )

    def list_fixture_coverage(
        self,
        *,
        fixture_ids: Sequence[str],
        as_of_time_utc: datetime,
        max_snapshot_lag_hours: int,
    ) -> list[FixtureOddsCoverage]:
        if not fixture_ids:
            return []
        normalized_as_of = _aware_utc(as_of_time_utc)
        rows = self.database.fetch_all(
            FIXTURE_ODDS_COVERAGE_ROWS_QUERY,
            {
                "fixture_ids": list(dict.fromkeys(fixture_ids)),
                "as_of_time_utc": normalized_as_of,
            },
        )
        return [
            _fixture_coverage_from_row(row, max_snapshot_lag_hours=max_snapshot_lag_hours)
            for row in rows
        ]

    def build_gap_report(
        self,
        *,
        competition_id: str,
        as_of_time_utc: datetime,
        window_days: int,
        max_snapshot_lag_hours: int,
        provider: str = "the-odds-api",
        limit: int = 100,
    ) -> OddsCoverageGapReport:
        normalized_as_of = _aware_utc(as_of_time_utc)
        window_start = normalized_as_of - timedelta(days=window_days)
        coverage_report = self.build_competition_report(
            competition_id=competition_id,
            as_of_time_utc=normalized_as_of,
            window_days=window_days,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
        )
        rows = self.database.fetch_all(
            ODDS_COVERAGE_GAP_ROWS_QUERY,
            {
                "competition_id": competition_id,
                "as_of_time_utc": normalized_as_of,
                "window_start_utc": window_start,
                "max_snapshot_lag_hours": max_snapshot_lag_hours,
                "provider": provider,
                "limit": min(max(limit, 1), 500),
            },
        )
        items = [
            _gap_item_from_row(
                row,
                provider=provider,
                max_snapshot_lag_hours=max_snapshot_lag_hours,
            )
            for row in rows
        ]
        return OddsCoverageGapReport(
            competition_id=competition_id,
            competition_name=coverage_report.competition_name,
            provider=provider,
            window_start_utc=window_start,
            as_of_time_utc=normalized_as_of,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
            fixture_count=coverage_report.fixture_count,
            gap_count=len(items),
            no_odds_count=sum("no_odds" in item.issue_types for item in items),
            stale_odds_count=sum("stale_odds" in item.issue_types for item in items),
            provider_event_unavailable_count=sum(
                "provider_event_unavailable" in item.issue_types for item in items
            ),
            missing_1x2_count=sum(
                "missing_market" in item.issue_types and not item.has_1x2
                for item in items
            ),
            missing_handicap_count=sum(
                "missing_market" in item.issue_types and not item.has_handicap
                for item in items
            ),
            unmapped_fixture_count=sum(
                "unmapped" in item.issue_types for item in items
            ),
            mapped_gap_count=sum(item.has_provider_mapping for item in items),
            items=items,
            generated_at_utc=normalized_as_of,
        )


def build_odds_coverage_report(
    fixtures: Sequence[FixtureOddsCoverage],
    *,
    competition_id: str,
    window_start_utc: datetime,
    as_of_time_utc: datetime,
    max_snapshot_lag_hours: int,
) -> CompetitionOddsCoverageReport:
    fixture_count = len(fixtures)
    competition_name = fixtures[0].competition_name if fixtures else competition_id
    fixtures_with_any = sum(1 for fixture in fixtures if fixture.has_any_odds)
    fixtures_with_1x2 = sum(1 for fixture in fixtures if fixture.has_1x2)
    fixtures_with_handicap = sum(1 for fixture in fixtures if fixture.has_handicap)
    fresh_count = sum(1 for fixture in fixtures if fixture.fresh_enough)
    snapshot_count = sum(fixture.odds_snapshot_count for fixture in fixtures)
    bookmaker_count = sum(fixture.bookmaker_count for fixture in fixtures)
    market_types = sorted(
        {market_type for fixture in fixtures for market_type in fixture.market_types}
    )
    average_bookmakers = (
        round(
            sum(fixture.bookmaker_count for fixture in fixtures) / fixture_count,
            2,
        )
        if fixture_count
        else 0.0
    )
    odds_coverage = _rate(fixtures_with_any, fixture_count)
    one_x_two_coverage = _rate(fixtures_with_1x2, fixture_count)
    handicap_coverage = _rate(fixtures_with_handicap, fixture_count)
    fresh_odds_coverage = _rate(fresh_count, fixture_count)

    return CompetitionOddsCoverageReport(
        competition_id=competition_id,
        competition_name=competition_name,
        window_start_utc=window_start_utc,
        as_of_time_utc=as_of_time_utc,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
        fixture_count=fixture_count,
        fixtures_with_any_odds=fixtures_with_any,
        fixtures_with_1x2=fixtures_with_1x2,
        fixtures_with_handicap=fixtures_with_handicap,
        fresh_odds_fixture_count=fresh_count,
        odds_snapshot_count=snapshot_count,
        bookmaker_count=bookmaker_count,
        average_bookmakers_per_fixture=average_bookmakers,
        odds_coverage=odds_coverage,
        one_x_two_coverage=one_x_two_coverage,
        handicap_coverage=handicap_coverage,
        fresh_odds_coverage=fresh_odds_coverage,
        market_types=market_types,
        data_quality_component_patch=OddsCoverageComponentPatch(
            odds_coverage=odds_coverage,
            handicap_coverage=handicap_coverage,
            data_freshness=fresh_odds_coverage,
        ),
        fixtures=list(fixtures),
        generated_at_utc=as_of_time_utc,
    )


def _fixture_coverage_from_row(
    row: DatabaseRow,
    *,
    max_snapshot_lag_hours: int,
) -> FixtureOddsCoverage:
    kickoff_time = _datetime(row["kickoff_time_utc"])
    latest_snapshot_time = _optional_datetime(row["latest_snapshot_time_utc"])
    lag_hours = None
    if latest_snapshot_time is not None:
        lag_hours = round(
            max(0.0, (kickoff_time - latest_snapshot_time).total_seconds() / 3600),
            2,
        )
    odds_snapshot_count = _int(row["odds_snapshot_count"])
    one_x_two_count = _int(row["one_x_two_count"])
    handicap_count = _int(row["handicap_count"])
    return FixtureOddsCoverage(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        kickoff_time_utc=kickoff_time,
        odds_snapshot_count=odds_snapshot_count,
        bookmaker_count=_int(row["bookmaker_count"]),
        has_any_odds=odds_snapshot_count > 0,
        has_1x2=one_x_two_count > 0,
        has_handicap=handicap_count > 0,
        latest_snapshot_time_utc=latest_snapshot_time,
        latest_snapshot_lag_hours=lag_hours,
        fresh_enough=lag_hours is not None and lag_hours <= max_snapshot_lag_hours,
        market_types=_string_list(row["market_types_json"]),
    )


def _gap_item_from_row(
    row: DatabaseRow,
    *,
    provider: str,
    max_snapshot_lag_hours: int,
) -> OddsCoverageGapItem:
    kickoff_time = _datetime(row["kickoff_time_utc"])
    latest_snapshot_time = _optional_datetime(row["latest_snapshot_time_utc"])
    lag_hours = None
    if latest_snapshot_time is not None:
        lag_hours = round(
            max(0.0, (kickoff_time - latest_snapshot_time).total_seconds() / 3600),
            2,
        )
    odds_snapshot_count = _int(row["odds_snapshot_count"])
    has_1x2 = _int(row["one_x_two_count"]) > 0
    has_handicap = _int(row["handicap_count"]) > 0
    fresh_enough = lag_hours is not None and lag_hours <= max_snapshot_lag_hours
    has_mapping = row.get("mapping_id") is not None
    issue_types: list[OddsCoverageGapStatus] = []
    if not has_mapping:
        issue_types.append("unmapped")
    if odds_snapshot_count == 0:
        if not has_mapping:
            issue_types.append("provider_event_unavailable")
        issue_types.append("no_odds")
    elif not fresh_enough:
        issue_types.append("stale_odds")
    if odds_snapshot_count > 0 and (not has_1x2 or not has_handicap):
        issue_types.append("missing_market")
    return OddsCoverageGapItem(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        kickoff_time_utc=kickoff_time,
        home_team_name=str(row["home_team_name"]),
        away_team_name=str(row["away_team_name"]),
        issue_types=issue_types,
        recommended_action=_gap_recommended_action(issue_types, has_mapping),
        odds_snapshot_count=odds_snapshot_count,
        bookmaker_count=_int(row["bookmaker_count"]),
        has_1x2=has_1x2,
        has_handicap=has_handicap,
        fresh_enough=fresh_enough,
        latest_snapshot_time_utc=latest_snapshot_time,
        latest_snapshot_lag_hours=lag_hours,
        market_types=_string_list(row["market_types_json"]),
        has_provider_mapping=has_mapping,
        provider=provider,
        provider_event_id=(
            str(row["provider_entity_id"])
            if row.get("provider_entity_id") is not None
            else None
        ),
        provider_mapping_id=(
            _int(row["mapping_id"]) if row.get("mapping_id") is not None else None
        ),
        provider_mapping_confidence=(
            _float(row["mapping_confidence"])
            if row.get("mapping_confidence") is not None
            else None
        ),
        provider_mapping_updated_at_utc=_optional_datetime(row["mapping_updated_at"]),
        event_availability_note=_gap_event_availability_note(issue_types, provider),
        fallback_candidates=_gap_fallback_candidates(issue_types, provider),
    )


def _gap_recommended_action(
    issue_types: Sequence[OddsCoverageGapStatus],
    has_mapping: bool,
) -> str:
    if "provider_event_unavailable" in issue_types:
        return "try_fallback_provider_event_mapping"
    if "unmapped" in issue_types:
        return "bootstrap_or_review_fixture_mapping"
    if "no_odds" in issue_types and has_mapping:
        return "sync_mapped_event_odds"
    if "stale_odds" in issue_types:
        return "refresh_mapped_event_odds"
    if "missing_market" in issue_types:
        return "review_provider_markets"
    return "review_gap"


def _gap_event_availability_note(
    issue_types: Sequence[OddsCoverageGapStatus],
    provider: str,
) -> str | None:
    if "provider_event_unavailable" not in issue_types:
        return None
    return (
        f"{provider} has no mapped event for this fixture in the current "
        "provider-event bootstrap window; check fallback provider coverage."
    )


def _gap_fallback_candidates(
    issue_types: Sequence[OddsCoverageGapStatus],
    provider: str,
) -> list[OddsCoverageFallbackProviderCandidate]:
    if "provider_event_unavailable" not in issue_types or provider != "the-odds-api":
        return []
    return [
        OddsCoverageFallbackProviderCandidate(
            provider_name="api-football",
            coverage_role="broad_fixture_result_provider_candidate",
            adapter_status="supported_now",
            required_env_var="NUTMEG_API_FOOTBALL_API_KEY",
            recommended_action="bootstrap_api_football_fixture_mapping",
        ),
        OddsCoverageFallbackProviderCandidate(
            provider_name="sportmonks",
            coverage_role="odds_fixture_fallback_candidate",
            adapter_status="supported_now",
            required_env_var="NUTMEG_SPORTMONKS_API_KEY",
            recommended_action="probe_sportmonks_fixture_odds_coverage",
        ),
    ]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


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


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected float value")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))


def _string_list(value: object) -> list[str]:
    raw = loads(value) if isinstance(value, str) else value
    if not isinstance(raw, list):
        return []
    return sorted({str(item) for item in raw if item is not None})
