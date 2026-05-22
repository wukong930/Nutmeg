from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from json import dumps
from typing import Literal, Protocol, Self, cast

from pydantic import BaseModel, Field, model_validator

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.features import PostgresFeatureSnapshotRepository
from nutmeg.predictions import (
    PostgresPredictionSnapshotRepository,
    build_prediction_snapshot_from_lambda_estimate,
)

DEFAULT_BASELINE_AS_OF_TIME_UTC = datetime(2026, 5, 12, 0, 0, tzinfo=UTC)
BASELINE_COMPETITION_ID = "BENCH_V3"
BASELINE_MODEL_VERSION = "poisson-v3.1-baseline"
BASELINE_FEATURE_VERSION = "features-v3.1-baseline"
BASELINE_CALIBRATION_VERSION = "calibration-v3.1-baseline"
BASELINE_PROVIDER = "deterministic-baseline"
BASELINE_BOOKMAKER = "baseline-book"

UPSERT_BASELINE_COMPETITION_QUERY = """
INSERT INTO competitions (
  competition_id,
  name,
  country,
  region,
  competition_type,
  team_type,
  provider_primary,
  coverage_tier,
  model_status,
  config_json,
  updated_at
) VALUES (
  %(competition_id)s,
  %(name)s,
  %(country)s,
  %(region)s,
  %(competition_type)s,
  %(team_type)s,
  %(provider_primary)s,
  %(coverage_tier)s,
  %(model_status)s,
  %(config_json)s::jsonb,
  now()
)
ON CONFLICT (competition_id) DO UPDATE SET
  name = EXCLUDED.name,
  country = EXCLUDED.country,
  region = EXCLUDED.region,
  provider_primary = EXCLUDED.provider_primary,
  coverage_tier = EXCLUDED.coverage_tier,
  model_status = EXCLUDED.model_status,
  config_json = EXCLUDED.config_json,
  updated_at = now()
RETURNING competition_id
"""

UPSERT_BASELINE_TEAM_QUERY = """
INSERT INTO teams (
  team_id,
  name,
  country,
  team_type,
  metadata_json,
  updated_at
) VALUES (
  %(team_id)s,
  %(name)s,
  %(country)s,
  %(team_type)s,
  %(metadata_json)s::jsonb,
  now()
)
ON CONFLICT (team_id) DO UPDATE SET
  name = EXCLUDED.name,
  country = EXCLUDED.country,
  metadata_json = EXCLUDED.metadata_json,
  updated_at = now()
RETURNING team_id
"""

UPSERT_BASELINE_FIXTURE_QUERY = """
INSERT INTO fixtures (
  fixture_id,
  competition_id,
  home_team_id,
  away_team_id,
  kickoff_time_utc,
  status,
  aggregate_context_json,
  updated_at
) VALUES (
  %(fixture_id)s,
  %(competition_id)s,
  %(home_team_id)s,
  %(away_team_id)s,
  %(kickoff_time_utc)s,
  %(status)s,
  %(aggregate_context_json)s::jsonb,
  now()
)
ON CONFLICT (fixture_id) DO UPDATE SET
  competition_id = EXCLUDED.competition_id,
  home_team_id = EXCLUDED.home_team_id,
  away_team_id = EXCLUDED.away_team_id,
  kickoff_time_utc = EXCLUDED.kickoff_time_utc,
  status = EXCLUDED.status,
  aggregate_context_json = EXCLUDED.aggregate_context_json,
  updated_at = now()
RETURNING fixture_id
"""

UPSERT_BASELINE_RESULT_QUERY = """
INSERT INTO results (
  fixture_id,
  home_goals,
  away_goals,
  result_1x2,
  settled_at,
  source,
  updated_at
) VALUES (
  %(fixture_id)s,
  %(home_goals)s,
  %(away_goals)s,
  %(result_1x2)s,
  %(settled_at)s,
  %(source)s,
  now()
)
ON CONFLICT (fixture_id) DO UPDATE SET
  home_goals = EXCLUDED.home_goals,
  away_goals = EXCLUDED.away_goals,
  result_1x2 = EXCLUDED.result_1x2,
  settled_at = EXCLUDED.settled_at,
  source = EXCLUDED.source,
  updated_at = now()
RETURNING fixture_id
"""

INSERT_BASELINE_ODDS_SNAPSHOT_QUERY = """
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
  liquidity,
  spread,
  snapshot_time_utc,
  is_opening,
  is_closing
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
  %(liquidity)s,
  %(spread)s,
  %(snapshot_time_utc)s,
  %(is_opening)s,
  %(is_closing)s
)
RETURNING odds_snapshot_id
"""

DELETE_BASELINE_RECOMMENDATION_EVALUATIONS_QUERY = """
DELETE FROM recommendation_run_evaluations
WHERE recommendation_run_id IN (
  SELECT recommendation_run_id
  FROM recommendation_runs
  WHERE source = ANY(%(recommendation_sources)s)
    AND selected_fixture_ids_json ?| %(fixture_ids)s::text[]
)
"""

DELETE_BASELINE_RECOMMENDATION_POOL_ITEMS_QUERY = """
DELETE FROM recommendation_candidate_pool_items
WHERE recommendation_candidate_pool_snapshot_id IN (
  SELECT recommendation_candidate_pool_snapshot_id
  FROM recommendation_candidate_pool_snapshots
  WHERE recommendation_run_id IN (
    SELECT recommendation_run_id
    FROM recommendation_runs
    WHERE source = ANY(%(recommendation_sources)s)
      AND selected_fixture_ids_json ?| %(fixture_ids)s::text[]
  )
)
"""

DELETE_BASELINE_RECOMMENDATION_CHILD_QUERY_TEMPLATE = """
DELETE FROM {table_name}
WHERE recommendation_run_id IN (
  SELECT recommendation_run_id
  FROM recommendation_runs
  WHERE source = ANY(%(recommendation_sources)s)
    AND selected_fixture_ids_json ?| %(fixture_ids)s::text[]
)
"""

DELETE_BASELINE_RECOMMENDATION_RUNS_QUERY = """
DELETE FROM recommendation_runs
WHERE source = ANY(%(recommendation_sources)s)
  AND selected_fixture_ids_json ?| %(fixture_ids)s::text[]
"""

DELETE_BASELINE_FIXTURE_TABLE_QUERY_TEMPLATE = """
DELETE FROM {table_name}
WHERE fixture_id = ANY(%(fixture_ids)s::text[])
"""


class RecommendationBaselineSeedDatabase(Protocol):
    def execute(self, query: str, params: QueryParams) -> None:
        """Execute seed cleanup statements."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute seed upserts/inserts with RETURNING."""


type SeededOneXTwoOutcome = Literal["home_win", "draw", "away_win"]
type RecommendationBaselineSeedProfile = Literal[
    "happy_path",
    "mixed_outcomes",
    "upset_stress",
    "adverse_odds",
    "low_quality_filter",
    "missing_result",
]

BASELINE_SEED_PROFILES: tuple[RecommendationBaselineSeedProfile, ...] = (
    "happy_path",
    "mixed_outcomes",
    "upset_stress",
    "adverse_odds",
    "low_quality_filter",
    "missing_result",
)
DEFAULT_BASELINE_SEED_PROFILE: RecommendationBaselineSeedProfile = "happy_path"


class RecommendationBaselineSeedFixture(BaseModel):
    fixture_id: str
    kickoff_offset_hours: int = Field(gt=0)
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    lambda_home: float = Field(gt=0.0)
    lambda_away: float = Field(gt=0.0)
    actual_home_goals: int | None = Field(default=None, ge=0)
    actual_away_goals: int | None = Field(default=None, ge=0)
    data_quality_score: float = Field(ge=0.0, le=100.0)
    fixture_status: str = "scheduled"
    odds_anchor_outcome: SeededOneXTwoOutcome | None = None

    @model_validator(mode="after")
    def _validate_result_pair(self) -> Self:
        has_home = self.actual_home_goals is not None
        has_away = self.actual_away_goals is not None
        if has_home != has_away:
            raise ValueError("actual_home_goals and actual_away_goals must be paired")
        return self

    @property
    def has_result(self) -> bool:
        return self.actual_home_goals is not None and self.actual_away_goals is not None

    @property
    def actual_1x2(self) -> SeededOneXTwoOutcome | None:
        if self.actual_home_goals is None or self.actual_away_goals is None:
            return None
        if self.actual_home_goals > self.actual_away_goals:
            return "home_win"
        if self.actual_home_goals < self.actual_away_goals:
            return "away_win"
        return "draw"


class RecommendationBaselineSeedOptions(BaseModel):
    as_of_time_utc: datetime = DEFAULT_BASELINE_AS_OF_TIME_UTC
    reset: bool = True
    profile: RecommendationBaselineSeedProfile = DEFAULT_BASELINE_SEED_PROFILE
    competition_id: str = BASELINE_COMPETITION_ID
    model_version: str = BASELINE_MODEL_VERSION
    feature_version: str = BASELINE_FEATURE_VERSION
    calibration_version: str = BASELINE_CALIBRATION_VERSION
    provider: str = BASELINE_PROVIDER
    bookmaker: str = BASELINE_BOOKMAKER

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class RecommendationBaselineSeedResult(BaseModel):
    as_of_time_utc: datetime
    reset: bool
    profile: RecommendationBaselineSeedProfile
    competition_id: str
    fixture_count: int = Field(ge=0)
    fixture_ids: list[str] = Field(default_factory=list)
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    odds_snapshot_count: int = Field(ge=0)
    result_count: int = Field(ge=0)
    missing_result_fixture_ids: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_baseline_seed(
    database: RecommendationBaselineSeedDatabase,
    *,
    options: RecommendationBaselineSeedOptions | None = None,
) -> RecommendationBaselineSeedResult:
    seed_options = options or RecommendationBaselineSeedOptions()
    as_of_time = seed_options.normalized_as_of_time_utc
    fixtures = _baseline_fixtures(profile=seed_options.profile)
    fixture_ids = [fixture.fixture_id for fixture in fixtures]
    if seed_options.reset:
        _reset_seeded_rows(database, fixture_ids=_all_baseline_fixture_ids())

    _upsert_competition(database, options=seed_options)
    feature_repository = PostgresFeatureSnapshotRepository(database)
    prediction_repository = PostgresPredictionSnapshotRepository(database)
    feature_snapshot_ids: dict[str, int] = {}
    prediction_snapshot_ids: dict[str, int] = {}
    odds_snapshot_count = 0
    result_count = 0

    for fixture in fixtures:
        _upsert_teams(database, fixture=fixture)
        kickoff_time = as_of_time + timedelta(hours=fixture.kickoff_offset_hours)
        _upsert_fixture(
            database,
            fixture=fixture,
            options=seed_options,
            kickoff_time_utc=kickoff_time,
        )
        feature_snapshot = _feature_snapshot(
            fixture,
            options=seed_options,
            as_of_time_utc=as_of_time,
            kickoff_time_utc=kickoff_time,
        )
        stored_feature = feature_repository.save(feature_snapshot)
        feature_snapshot_ids[fixture.fixture_id] = stored_feature.feature_snapshot_id
        prediction_snapshot = _prediction_snapshot(
            fixture,
            options=seed_options,
            as_of_time_utc=as_of_time,
            feature_snapshot=feature_snapshot,
            feature_snapshot_id=stored_feature.feature_snapshot_id,
        )
        stored_prediction = prediction_repository.save(prediction_snapshot)
        prediction_snapshot_ids[fixture.fixture_id] = (
            stored_prediction.prediction_snapshot_id
        )
        odds_snapshot_count += _insert_one_x_two_odds(
            database,
            snapshot=prediction_snapshot,
            fixture=fixture,
            options=seed_options,
            snapshot_time_utc=as_of_time,
        )
        if fixture.has_result:
            _upsert_result(
                database,
                fixture=fixture,
                settled_at_utc=kickoff_time + timedelta(hours=3),
            )
            result_count += 1

    missing_result_fixture_ids = [
        fixture.fixture_id for fixture in fixtures if not fixture.has_result
    ]

    return RecommendationBaselineSeedResult(
        as_of_time_utc=as_of_time,
        reset=seed_options.reset,
        profile=seed_options.profile,
        competition_id=seed_options.competition_id,
        fixture_count=len(fixtures),
        fixture_ids=fixture_ids,
        feature_snapshot_ids=feature_snapshot_ids,
        prediction_snapshot_ids=prediction_snapshot_ids,
        odds_snapshot_count=odds_snapshot_count,
        result_count=result_count,
        missing_result_fixture_ids=missing_result_fixture_ids,
        summary_json={
            "calculation_basis": "recommendation_baseline_seed_v3_1",
            "model_version": seed_options.model_version,
            "feature_version": seed_options.feature_version,
            "calibration_version": seed_options.calibration_version,
            "profile": seed_options.profile,
            "odds_scope": "1x2_only",
            "missing_result_fixture_ids": missing_result_fixture_ids,
            "fixture_status_note": (
                "fixtures remain pre-match eligible while deterministic result rows "
                "exist for replay unless the selected profile intentionally omits "
                "some results"
            ),
        },
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_baseline_seed(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))


def _reset_seeded_rows(
    database: RecommendationBaselineSeedDatabase,
    *,
    fixture_ids: Sequence[str],
) -> None:
    params: QueryParams = {
        "fixture_ids": list(fixture_ids),
        "recommendation_sources": [
            "recommendation_global_planner_v3_1",
            "recommendation_engine_v3_1",
            "recommendation_baseline_seed_v3_1",
        ],
    }
    database.execute(DELETE_BASELINE_RECOMMENDATION_EVALUATIONS_QUERY, params)
    database.execute(DELETE_BASELINE_RECOMMENDATION_POOL_ITEMS_QUERY, params)
    for table_name in (
        "recommendation_candidate_pool_snapshots",
        "recommendation_budget_adjustments",
        "recommendation_versions",
        "recommendation_candidates",
        "recommendation_locked_legs",
        "recommendation_lifecycle_events",
    ):
        database.execute(
            DELETE_BASELINE_RECOMMENDATION_CHILD_QUERY_TEMPLATE.format(
                table_name=table_name
            ),
            params,
        )
    database.execute(DELETE_BASELINE_RECOMMENDATION_RUNS_QUERY, params)
    for table_name in (
        "prediction_evaluations",
        "market_predictions",
        "upset_alerts",
        "prediction_snapshots",
        "odds_snapshots",
        "feature_snapshots",
        "score_probability_grids",
        "results",
        "fixtures",
    ):
        database.execute(
            DELETE_BASELINE_FIXTURE_TABLE_QUERY_TEMPLATE.format(table_name=table_name),
            {"fixture_ids": list(fixture_ids)},
        )


def _upsert_competition(
    database: RecommendationBaselineSeedDatabase,
    *,
    options: RecommendationBaselineSeedOptions,
) -> None:
    _required_row(
        database.fetch_one(
            UPSERT_BASELINE_COMPETITION_QUERY,
            {
                "competition_id": options.competition_id,
                "name": "Nutmeg V3.1 Deterministic Benchmark League",
                "country": "Local",
                "region": "Internal",
                "competition_type": "league",
                "team_type": "club",
                "provider_primary": options.provider,
                "coverage_tier": "local_benchmark",
                "model_status": "beta",
                "config_json": _json(
                    {
                        "source": "recommendation_baseline_seed_v3_1",
                        "purpose": "deterministic recommendation benchmark baseline",
                        "seed_profile": options.profile,
                    }
                ),
            },
        )
    )


def _upsert_teams(
    database: RecommendationBaselineSeedDatabase,
    *,
    fixture: RecommendationBaselineSeedFixture,
) -> None:
    for team_id, team_name in (
        (fixture.home_team_id, fixture.home_team_name),
        (fixture.away_team_id, fixture.away_team_name),
    ):
        _required_row(
            database.fetch_one(
                UPSERT_BASELINE_TEAM_QUERY,
                {
                    "team_id": team_id,
                    "name": team_name,
                    "country": "Local",
                    "team_type": "club",
                    "metadata_json": _json(
                        {"source": "recommendation_baseline_seed_v3_1"}
                    ),
                },
            )
        )


def _upsert_fixture(
    database: RecommendationBaselineSeedDatabase,
    *,
    fixture: RecommendationBaselineSeedFixture,
    options: RecommendationBaselineSeedOptions,
    kickoff_time_utc: datetime,
) -> None:
    _required_row(
        database.fetch_one(
            UPSERT_BASELINE_FIXTURE_QUERY,
            {
                "fixture_id": fixture.fixture_id,
                "competition_id": options.competition_id,
                "home_team_id": fixture.home_team_id,
                "away_team_id": fixture.away_team_id,
                "kickoff_time_utc": kickoff_time_utc,
                "status": fixture.fixture_status,
                "aggregate_context_json": _json(
                    {
                        "source": "recommendation_baseline_seed_v3_1",
                        "seed_profile": options.profile,
                        "lambda_home": fixture.lambda_home,
                        "lambda_away": fixture.lambda_away,
                        "actual_1x2": fixture.actual_1x2,
                        "result_available": fixture.has_result,
                        "odds_anchor_outcome": fixture.odds_anchor_outcome,
                    }
                ),
            },
        )
    )


def _upsert_result(
    database: RecommendationBaselineSeedDatabase,
    *,
    fixture: RecommendationBaselineSeedFixture,
    settled_at_utc: datetime,
) -> None:
    actual_home_goals = fixture.actual_home_goals
    actual_away_goals = fixture.actual_away_goals
    actual_1x2 = fixture.actual_1x2
    if (
        actual_home_goals is None
        or actual_away_goals is None
        or actual_1x2 is None
    ):
        raise ValueError("cannot upsert a baseline result for an unresolved fixture")
    _required_row(
        database.fetch_one(
            UPSERT_BASELINE_RESULT_QUERY,
            {
                "fixture_id": fixture.fixture_id,
                "home_goals": actual_home_goals,
                "away_goals": actual_away_goals,
                "result_1x2": actual_1x2,
                "settled_at": settled_at_utc,
                "source": "recommendation_baseline_seed_v3_1",
            },
        )
    )


def _feature_snapshot(
    fixture: RecommendationBaselineSeedFixture,
    *,
    options: RecommendationBaselineSeedOptions,
    as_of_time_utc: datetime,
    kickoff_time_utc: datetime,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        fixture_id=fixture.fixture_id,
        feature_time_utc=as_of_time_utc,
        feature_version=options.feature_version,
        features_json={
            "competition_id": options.competition_id,
            "kickoff_time_utc": kickoff_time_utc.isoformat(),
            "deterministic_baseline": True,
            "seed_profile": options.profile,
            "data_quality": {
                "score": fixture.data_quality_score,
                "grade": _quality_grade(fixture.data_quality_score),
                "components": {
                    "fixture_reliability": 1.0,
                    "odds_coverage": 1.0,
                    "lineup_injury_coverage": 0.75,
                    "historical_stats_completeness": 0.82,
                    "provider_consistency": 0.95,
                    "data_freshness": 1.0,
                },
                "messages": ["deterministic benchmark quality fixture"],
            },
        },
        source_snapshot_refs={
            "seed": "recommendation_baseline_seed_v3_1",
            "provider": options.provider,
        },
        data_quality_score=fixture.data_quality_score,
    )


def _prediction_snapshot(
    fixture: RecommendationBaselineSeedFixture,
    *,
    options: RecommendationBaselineSeedOptions,
    as_of_time_utc: datetime,
    feature_snapshot: FeatureSnapshot,
    feature_snapshot_id: int,
) -> PredictionSnapshot:
    estimate = GoalLambdaEstimate(
        fixture_id=fixture.fixture_id,
        lambda_home=fixture.lambda_home,
        lambda_away=fixture.lambda_away,
        model_family="poisson",
        model_version=options.model_version,
        feature_version=options.feature_version,
        calibration_version=options.calibration_version,
        metadata_json={
            "source": "recommendation_baseline_seed_v3_1",
            "dixon_coles_compatibility": {
                "rho": None,
                "time_decay_weight": None,
                "future_upgrade": "dc-v1.5",
            },
        },
    )
    return build_prediction_snapshot_from_lambda_estimate(
        estimate,
        prediction_time_utc=as_of_time_utc,
        data_quality_score=fixture.data_quality_score,
        uncertainty="low",
        cn_handicaps=(-1, 0, 1),
        asian_handicap_lines=(),
        european_handicaps=(-1, 0, 1),
        feature_snapshot=feature_snapshot,
        feature_snapshot_id=feature_snapshot_id,
    )


def _insert_one_x_two_odds(
    database: RecommendationBaselineSeedDatabase,
    *,
    snapshot: PredictionSnapshot,
    fixture: RecommendationBaselineSeedFixture,
    options: RecommendationBaselineSeedOptions,
    snapshot_time_utc: datetime,
) -> int:
    market = snapshot.market_probabilities["1x2"]
    if not isinstance(market, dict):
        raise ValueError("baseline seed expected 1x2 probability map")
    anchor_outcome = _odds_anchor_outcome(fixture, market=market)
    inserted_count = 0
    for outcome, raw_probability in market.items():
        probability = float(raw_probability)
        fair_probability = _seed_market_probability(
            model_probability=probability,
            outcome=str(outcome),
            anchor_outcome=anchor_outcome,
        )
        _required_row(
            database.fetch_one(
                INSERT_BASELINE_ODDS_SNAPSHOT_QUERY,
                {
                    "fixture_id": fixture.fixture_id,
                    "provider": options.provider,
                    "bookmaker": options.bookmaker,
                    "market_type": "1x2",
                    "line": None,
                    "side": None,
                    "outcome": str(outcome),
                    "decimal_odds": round(1.0 / fair_probability, 4),
                    "raw_implied_probability": fair_probability,
                    "fair_probability": fair_probability,
                    "overround": 0.0,
                    "liquidity": 1.0,
                    "spread": 0.0,
                    "snapshot_time_utc": snapshot_time_utc,
                    "is_opening": True,
                    "is_closing": False,
                },
            )
        )
        inserted_count += 1
    return inserted_count


def _seed_market_probability(
    *,
    model_probability: float,
    outcome: str,
    anchor_outcome: SeededOneXTwoOutcome,
) -> float:
    if outcome == anchor_outcome:
        return round(max(0.05, model_probability - 0.10), 6)
    return round(min(0.92, model_probability + 0.04), 6)


def _baseline_fixtures(
    *,
    profile: RecommendationBaselineSeedProfile = DEFAULT_BASELINE_SEED_PROFILE,
) -> list[RecommendationBaselineSeedFixture]:
    fixtures = _happy_path_baseline_fixtures()
    if profile == "happy_path":
        return fixtures
    if profile == "mixed_outcomes":
        return _mixed_outcome_baseline_fixtures(fixtures)
    if profile == "upset_stress":
        return _upset_stress_baseline_fixtures(fixtures)
    if profile == "adverse_odds":
        return _adverse_odds_baseline_fixtures(fixtures)
    if profile == "low_quality_filter":
        return _low_quality_filter_baseline_fixtures(fixtures)
    if profile == "missing_result":
        return _missing_result_baseline_fixtures(fixtures)
    raise ValueError(f"unknown recommendation baseline seed profile: {profile}")


def _happy_path_baseline_fixtures() -> list[RecommendationBaselineSeedFixture]:
    return [
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_001",
            kickoff_offset_hours=18,
            home_team_id="bench_alpha",
            home_team_name="Benchmark Alpha",
            away_team_id="bench_bravo",
            away_team_name="Benchmark Bravo",
            lambda_home=1.92,
            lambda_away=0.72,
            actual_home_goals=2,
            actual_away_goals=0,
            data_quality_score=91.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_002",
            kickoff_offset_hours=20,
            home_team_id="bench_charlie",
            home_team_name="Benchmark Charlie",
            away_team_id="bench_delta",
            away_team_name="Benchmark Delta",
            lambda_home=1.74,
            lambda_away=0.88,
            actual_home_goals=2,
            actual_away_goals=1,
            data_quality_score=89.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_003",
            kickoff_offset_hours=22,
            home_team_id="bench_echo",
            home_team_name="Benchmark Echo",
            away_team_id="bench_foxtrot",
            away_team_name="Benchmark Foxtrot",
            lambda_home=0.70,
            lambda_away=1.82,
            actual_home_goals=0,
            actual_away_goals=2,
            data_quality_score=88.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_004",
            kickoff_offset_hours=24,
            home_team_id="bench_golf",
            home_team_name="Benchmark Golf",
            away_team_id="bench_hotel",
            away_team_name="Benchmark Hotel",
            lambda_home=2.05,
            lambda_away=0.98,
            actual_home_goals=3,
            actual_away_goals=1,
            data_quality_score=86.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_005",
            kickoff_offset_hours=26,
            home_team_id="bench_india",
            home_team_name="Benchmark India",
            away_team_id="bench_juliet",
            away_team_name="Benchmark Juliet",
            lambda_home=0.92,
            lambda_away=1.66,
            actual_home_goals=1,
            actual_away_goals=2,
            data_quality_score=84.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_006",
            kickoff_offset_hours=28,
            home_team_id="bench_kilo",
            home_team_name="Benchmark Kilo",
            away_team_id="bench_lima",
            away_team_name="Benchmark Lima",
            lambda_home=1.54,
            lambda_away=0.78,
            actual_home_goals=1,
            actual_away_goals=0,
            data_quality_score=83.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_007",
            kickoff_offset_hours=30,
            home_team_id="bench_mike",
            home_team_name="Benchmark Mike",
            away_team_id="bench_november",
            away_team_name="Benchmark November",
            lambda_home=0.82,
            lambda_away=1.44,
            actual_home_goals=0,
            actual_away_goals=1,
            data_quality_score=82.0,
        ),
        RecommendationBaselineSeedFixture(
            fixture_id="bench_v3_008",
            kickoff_offset_hours=32,
            home_team_id="bench_oscar",
            home_team_name="Benchmark Oscar",
            away_team_id="bench_papa",
            away_team_name="Benchmark Papa",
            lambda_home=1.80,
            lambda_away=0.64,
            actual_home_goals=2,
            actual_away_goals=0,
            data_quality_score=81.0,
        ),
    ]


def _mixed_outcome_baseline_fixtures(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
) -> list[RecommendationBaselineSeedFixture]:
    actual_overrides = {
        # Keep the two strongest legs as hits, then flip several deeper legs.
        # This creates useful regression evidence for 4x1+ and multiple tickets
        # without making the whole local benchmark an all-or-nothing failure.
        "bench_v3_004": {"actual_home_goals": 1, "actual_away_goals": 1},
        "bench_v3_005": {"actual_home_goals": 2, "actual_away_goals": 1},
        "bench_v3_006": {"actual_home_goals": 1, "actual_away_goals": 1},
        "bench_v3_007": {"actual_home_goals": 2, "actual_away_goals": 1},
    }
    mixed: list[RecommendationBaselineSeedFixture] = []
    for fixture in fixtures:
        override = actual_overrides.get(fixture.fixture_id)
        if override is None:
            mixed.append(fixture)
            continue
        mixed.append(fixture.model_copy(update=override))
    return mixed


def _upset_stress_baseline_fixtures(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
) -> list[RecommendationBaselineSeedFixture]:
    actual_overrides: dict[str, dict[str, object]] = {
        "bench_v3_001": {"actual_home_goals": 1, "actual_away_goals": 1},
        "bench_v3_003": {"actual_home_goals": 1, "actual_away_goals": 1},
        "bench_v3_004": {"actual_home_goals": 1, "actual_away_goals": 2},
        "bench_v3_008": {"actual_home_goals": 0, "actual_away_goals": 1},
    }
    return _copy_fixtures_with_overrides(fixtures, actual_overrides)


def _adverse_odds_baseline_fixtures(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
) -> list[RecommendationBaselineSeedFixture]:
    odds_overrides: dict[str, dict[str, object]] = {
        "bench_v3_001": {"odds_anchor_outcome": "draw"},
        "bench_v3_002": {"odds_anchor_outcome": "draw"},
        "bench_v3_003": {"odds_anchor_outcome": "draw"},
        "bench_v3_004": {"odds_anchor_outcome": "draw"},
        "bench_v3_005": {"odds_anchor_outcome": "draw"},
        "bench_v3_006": {"odds_anchor_outcome": "draw"},
        "bench_v3_007": {"odds_anchor_outcome": "draw"},
        "bench_v3_008": {"odds_anchor_outcome": "draw"},
    }
    return _copy_fixtures_with_overrides(fixtures, odds_overrides)


def _low_quality_filter_baseline_fixtures(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
) -> list[RecommendationBaselineSeedFixture]:
    quality_overrides: dict[str, dict[str, object]] = {
        "bench_v3_001": {"data_quality_score": 44.0},
        "bench_v3_003": {"data_quality_score": 47.0},
    }
    return _copy_fixtures_with_overrides(fixtures, quality_overrides)


def _missing_result_baseline_fixtures(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
) -> list[RecommendationBaselineSeedFixture]:
    result_overrides: dict[str, dict[str, object]] = {
        "bench_v3_004": {
            "actual_home_goals": None,
            "actual_away_goals": None,
            "odds_anchor_outcome": "home_win",
        },
        "bench_v3_008": {
            "actual_home_goals": None,
            "actual_away_goals": None,
            "odds_anchor_outcome": "home_win",
        },
    }
    return _copy_fixtures_with_overrides(fixtures, result_overrides)


def _copy_fixtures_with_overrides(
    fixtures: Sequence[RecommendationBaselineSeedFixture],
    overrides: dict[str, dict[str, object]],
) -> list[RecommendationBaselineSeedFixture]:
    copied: list[RecommendationBaselineSeedFixture] = []
    for fixture in fixtures:
        override = overrides.get(fixture.fixture_id)
        if override is None:
            copied.append(fixture)
            continue
        copied.append(fixture.model_copy(update=override))
    return copied


def _all_baseline_fixture_ids() -> list[str]:
    fixture_ids: list[str] = []
    seen_fixture_ids: set[str] = set()
    for profile in BASELINE_SEED_PROFILES:
        for fixture in _baseline_fixtures(profile=profile):
            if fixture.fixture_id in seen_fixture_ids:
                continue
            fixture_ids.append(fixture.fixture_id)
            seen_fixture_ids.add(fixture.fixture_id)
    return fixture_ids


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Seed deterministic local data for Nutmeg recommendation baselines.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument(
        "--as-of-time-utc",
        default=DEFAULT_BASELINE_AS_OF_TIME_UTC.isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument(
        "--profile",
        choices=BASELINE_SEED_PROFILES,
        default=DEFAULT_BASELINE_SEED_PROFILE,
    )
    parser.add_argument("--no-reset", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBaselineSeedOptions:
    return RecommendationBaselineSeedOptions(
        as_of_time_utc=_parse_datetime(args.as_of_time_utc),
        reset=not args.no_reset,
        profile=args.profile,
    )


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return _aware_utc(datetime.fromisoformat(normalized))


def _quality_grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _odds_anchor_outcome(
    fixture: RecommendationBaselineSeedFixture,
    *,
    market: dict[str, float],
) -> SeededOneXTwoOutcome:
    if fixture.odds_anchor_outcome is not None:
        return fixture.odds_anchor_outcome
    actual_outcome = fixture.actual_1x2
    if actual_outcome is not None:
        return actual_outcome
    return _most_likely_one_x_two_outcome(market)


def _most_likely_one_x_two_outcome(
    market: dict[str, float],
) -> SeededOneXTwoOutcome:
    outcome_text = str(max(market.items(), key=lambda item: float(item[1]))[0])
    if outcome_text not in {"home_win", "draw", "away_win"}:
        raise ValueError(f"unsupported 1x2 outcome in baseline seed: {outcome_text}")
    return cast(SeededOneXTwoOutcome, outcome_text)


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


if __name__ == "__main__":
    main()
