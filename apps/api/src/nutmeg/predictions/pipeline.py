from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from json import loads
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.features import PostgresFeatureSnapshotRepository, StoredFeatureSnapshot
from nutmeg.features.builder import build_fixture_feature_snapshot
from nutmeg.modeling.team_strength import (
    DEFAULT_HISTORICAL_RESULT_LIMIT,
    DEFAULT_MIN_TEAM_MATCHES,
    CompetitionHistoricalStrengthSnapshot,
    HistoricalFixtureResult,
    build_competition_historical_strength_snapshot,
    estimate_goal_lambdas_from_team_strength,
)
from nutmeg.predictions.repository import (
    PostgresPredictionSnapshotRepository,
    StoredPostgresPredictionSnapshot,
)
from nutmeg.predictions.snapshot_builder import (
    build_mock_prediction_snapshot_with_context,
    build_prediction_snapshot_from_lambda_estimate,
)
from nutmeg.providers.availability_coverage import (
    FixtureAvailabilityCoverage,
    PostgresAvailabilityCoverageRepository,
)
from nutmeg.providers.conflicts import (
    PostgresProviderConflictEventRepository,
    ProviderConflictQualityImpact,
)
from nutmeg.providers.mock import list_mock_fixtures
from nutmeg.providers.mock.data import MockFixture
from nutmeg.providers.odds_coverage import FixtureOddsCoverage, PostgresOddsCoverageRepository

LIST_CANONICAL_FIXTURES_FOR_PREDICTION_QUERY = """
SELECT
  f.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  c.model_status,
  c.coverage_tier,
  c.config_json,
  f.kickoff_time_utc,
  f.status,
  f.neutral_venue,
  f.aggregate_context_json,
  ht.team_id AS home_team_id,
  ht.name AS home_team_name,
  at.team_id AS away_team_id,
  at.name AS away_team_name
FROM fixtures f
JOIN competitions c
  ON c.competition_id = f.competition_id
JOIN teams ht
  ON ht.team_id = f.home_team_id
JOIN teams at
  ON at.team_id = f.away_team_id
WHERE f.status = ANY(%(statuses)s::text[])
  AND f.kickoff_time_utc >= %(window_start_utc)s
  AND f.kickoff_time_utc < %(window_end_utc)s
  AND (
    %(competition_id)s::text IS NULL
    OR f.competition_id = %(competition_id)s
  )
  AND (
    %(fixture_ids)s::text[] IS NULL
    OR f.fixture_id = ANY(%(fixture_ids)s::text[])
  )
ORDER BY f.kickoff_time_utc ASC, f.fixture_id ASC
LIMIT %(limit)s
"""

LIST_HISTORICAL_RESULTS_FOR_PREDICTION_QUERY = """
WITH ranked_results AS (
  SELECT
    f.fixture_id,
    f.competition_id,
    f.kickoff_time_utc,
    f.home_team_id,
    f.away_team_id,
    r.home_goals,
    r.away_goals,
    row_number() OVER (
      PARTITION BY f.competition_id
      ORDER BY f.kickoff_time_utc DESC, f.fixture_id DESC
    ) AS result_rank
  FROM fixtures f
  JOIN results r
    ON r.fixture_id = f.fixture_id
  WHERE f.competition_id = ANY(%(competition_ids)s::text[])
    AND f.status = 'finished'
    AND f.kickoff_time_utc < %(as_of_time_utc)s
    AND COALESCE(r.settled_at, f.kickoff_time_utc) <= %(as_of_time_utc)s
    AND r.home_goals IS NOT NULL
    AND r.away_goals IS NOT NULL
)
SELECT
  fixture_id,
  competition_id,
  kickoff_time_utc,
  home_team_id,
  away_team_id,
  home_goals,
  away_goals
FROM ranked_results
WHERE result_rank <= %(per_competition_limit)s
ORDER BY competition_id ASC, kickoff_time_utc DESC, fixture_id DESC
"""

CANONICAL_FIXTURE_STATUS_VALUES = ("scheduled", "beta")


class FeatureSnapshotWriteRepository(Protocol):
    def save(self, snapshot: FeatureSnapshot) -> StoredFeatureSnapshot:
        """Persist one feature snapshot."""


class PredictionSnapshotWriteRepository(Protocol):
    def save(self, snapshot: PredictionSnapshot) -> StoredPostgresPredictionSnapshot:
        """Persist one prediction snapshot and its score grid."""


class PreMatchPredictionDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read query and return rows."""


class PreMatchPredictionPipelineResult(BaseModel):
    prediction_time_utc: datetime
    fixture_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    dry_run: bool = False
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    score_grid_ids: dict[str, int] = Field(default_factory=dict)
    data_quality_scores: dict[str, float] = Field(default_factory=dict)
    skipped_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CanonicalFixturePredictionCandidate(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    model_status: str | None = None
    coverage_tier: str | None = None
    config_json: dict[str, object] = Field(default_factory=dict)
    kickoff_time_utc: datetime
    status: str
    neutral_venue: bool = False
    aggregate_context_json: dict[str, object] = Field(default_factory=dict)
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str


def run_mock_prematch_prediction_pipeline(
    *,
    feature_repository: FeatureSnapshotWriteRepository | None = None,
    prediction_repository: PredictionSnapshotWriteRepository | None = None,
    fixture_ids: Sequence[str] | None = None,
    odds_coverage: Mapping[str, FixtureOddsCoverage] | None = None,
    availability_coverage: Mapping[str, FixtureAvailabilityCoverage] | None = None,
    prediction_time_utc: datetime | None = None,
    dry_run: bool = False,
) -> PreMatchPredictionPipelineResult:
    if not dry_run and (feature_repository is None or prediction_repository is None):
        raise ValueError("feature and prediction repositories are required for commit runs")
    target_feature_repository = feature_repository
    target_prediction_repository = prediction_repository

    normalized_prediction_time = _aware_utc(prediction_time_utc or datetime.now(UTC))
    fixture_id_filter = list(dict.fromkeys(fixture_ids or []))
    requested_ids = set(fixture_id_filter)
    fixtures = list_mock_fixtures()
    selected_fixtures = [
        fixture
        for fixture in fixtures
        if not requested_ids or fixture["fixture_id"] in requested_ids
    ]
    known_ids = {fixture["fixture_id"] for fixture in fixtures}
    skipped_fixture_ids = sorted(requested_ids - known_ids)
    warnings = [
        f"fixture_not_found:{fixture_id}" for fixture_id in skipped_fixture_ids
    ]

    feature_snapshot_ids: dict[str, int] = {}
    prediction_snapshot_ids: dict[str, int] = {}
    score_grid_ids: dict[str, int] = {}
    data_quality_scores: dict[str, float] = {}

    for fixture in selected_fixtures:
        fixture_id = fixture["fixture_id"]
        prediction = build_mock_prediction_snapshot_with_context(
            fixture_id,
            odds_coverage=odds_coverage.get(fixture_id)
            if odds_coverage is not None
            else None,
            availability_coverage=availability_coverage.get(fixture_id)
            if availability_coverage is not None
            else None,
            prediction_time_utc=normalized_prediction_time,
        )
        if prediction is None:
            skipped_fixture_ids.append(fixture_id)
            warnings.append(f"prediction_build_failed:{fixture_id}")
            continue

        feature_snapshot = prediction.feature_snapshot
        if prediction.data_quality_score < 50:
            warnings.append(f"fixture_data_quality_below_parlay_threshold:{fixture_id}")

        if not dry_run:
            if target_feature_repository is None or target_prediction_repository is None:
                raise ValueError(
                    "feature and prediction repositories are required for commit runs"
                )
            if feature_snapshot is not None:
                stored_feature = target_feature_repository.save(feature_snapshot)
                feature_snapshot_ids[fixture_id] = stored_feature.feature_snapshot_id
                prediction = prediction.model_copy(
                    update={"feature_snapshot_id": stored_feature.feature_snapshot_id}
                )
            stored_prediction = target_prediction_repository.save(prediction)
            prediction_snapshot_ids[fixture_id] = (
                stored_prediction.prediction_snapshot_id
            )
            score_grid_ids[fixture_id] = stored_prediction.score_grid_id

        data_quality_scores[fixture_id] = prediction.data_quality_score

    return PreMatchPredictionPipelineResult(
        prediction_time_utc=normalized_prediction_time,
        fixture_count=len(selected_fixtures),
        generated_count=len(data_quality_scores),
        dry_run=dry_run,
        feature_snapshot_ids=feature_snapshot_ids,
        prediction_snapshot_ids=prediction_snapshot_ids,
        score_grid_ids=score_grid_ids,
        data_quality_scores=data_quality_scores,
        skipped_fixture_ids=skipped_fixture_ids,
        warnings=warnings,
    )


def run_postgres_mock_prematch_prediction_pipeline(
    *,
    database: PreMatchPredictionDatabase,
    fixture_ids: Sequence[str] | None = None,
    as_of_time_utc: datetime | None = None,
    max_snapshot_lag_hours: int = 24,
    dry_run: bool = False,
) -> PreMatchPredictionPipelineResult:
    normalized_as_of = _aware_utc(as_of_time_utc or datetime.now(UTC))
    selected_fixture_ids = _selected_fixture_ids(fixture_ids)
    odds_items = PostgresOddsCoverageRepository(database).list_fixture_coverage(
        fixture_ids=selected_fixture_ids,
        as_of_time_utc=normalized_as_of,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
    )
    availability_items = PostgresAvailabilityCoverageRepository(database).list_fixture_coverage(
        fixture_ids=selected_fixture_ids,
        as_of_time_utc=normalized_as_of,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
    )
    return run_mock_prematch_prediction_pipeline(
        feature_repository=PostgresFeatureSnapshotRepository(database),
        prediction_repository=PostgresPredictionSnapshotRepository(database),
        fixture_ids=selected_fixture_ids,
        odds_coverage={item.fixture_id: item for item in odds_items},
        availability_coverage={item.fixture_id: item for item in availability_items},
        prediction_time_utc=normalized_as_of,
        dry_run=dry_run,
    )


def list_canonical_fixtures_for_prediction(
    database: PreMatchPredictionDatabase,
    *,
    as_of_time_utc: datetime,
    window_hours: int,
    competition_id: str | None = None,
    fixture_ids: Sequence[str] | None = None,
    limit: int = 100,
) -> list[CanonicalFixturePredictionCandidate]:
    normalized_as_of = _aware_utc(as_of_time_utc)
    rows = database.fetch_all(
        LIST_CANONICAL_FIXTURES_FOR_PREDICTION_QUERY,
        {
            "statuses": list(CANONICAL_FIXTURE_STATUS_VALUES),
            "window_start_utc": normalized_as_of,
            "window_end_utc": normalized_as_of + _hours(window_hours),
            "competition_id": competition_id,
            "fixture_ids": list(dict.fromkeys(fixture_ids or [])) or None,
            "limit": max(1, min(limit, 500)),
        },
    )
    return [_canonical_fixture_from_row(row) for row in rows]


def list_historical_results_for_prediction(
    database: PreMatchPredictionDatabase,
    *,
    competition_ids: Sequence[str],
    as_of_time_utc: datetime,
    per_competition_limit: int = DEFAULT_HISTORICAL_RESULT_LIMIT,
) -> list[HistoricalFixtureResult]:
    normalized_as_of = _aware_utc(as_of_time_utc)
    normalized_competition_ids = sorted(set(competition_ids))
    if not normalized_competition_ids:
        return []
    rows = database.fetch_all(
        LIST_HISTORICAL_RESULTS_FOR_PREDICTION_QUERY,
        {
            "competition_ids": normalized_competition_ids,
            "as_of_time_utc": normalized_as_of,
            "per_competition_limit": max(1, min(per_competition_limit, 1000)),
        },
    )
    return [_historical_result_from_row(row) for row in rows]


def run_canonical_prematch_prediction_pipeline(
    *,
    fixtures: Sequence[CanonicalFixturePredictionCandidate],
    feature_repository: FeatureSnapshotWriteRepository | None = None,
    prediction_repository: PredictionSnapshotWriteRepository | None = None,
    odds_coverage: Mapping[str, FixtureOddsCoverage] | None = None,
    availability_coverage: Mapping[str, FixtureAvailabilityCoverage] | None = None,
    provider_conflict_impacts: Mapping[str, ProviderConflictQualityImpact] | None = None,
    historical_strength_snapshots: Mapping[
        str,
        CompetitionHistoricalStrengthSnapshot,
    ]
    | None = None,
    prediction_time_utc: datetime | None = None,
    enforce_odds_quality_gate: bool = True,
    dry_run: bool = False,
) -> PreMatchPredictionPipelineResult:
    if not dry_run and (feature_repository is None or prediction_repository is None):
        raise ValueError("feature and prediction repositories are required for commit runs")
    target_feature_repository = feature_repository
    target_prediction_repository = prediction_repository
    normalized_prediction_time = _aware_utc(prediction_time_utc or datetime.now(UTC))

    feature_snapshot_ids: dict[str, int] = {}
    prediction_snapshot_ids: dict[str, int] = {}
    score_grid_ids: dict[str, int] = {}
    data_quality_scores: dict[str, float] = {}
    skipped_fixture_ids: list[str] = []
    warnings: list[str] = []

    for fixture in fixtures:
        fixture_odds_coverage = (
            odds_coverage.get(fixture.fixture_id) if odds_coverage is not None else None
        )
        skip_for_odds_gate, odds_gate_warnings = _canonical_odds_gate_warnings(
            fixture,
            fixture_odds_coverage,
            enforce=(
                enforce_odds_quality_gate
                and fixture.status in CANONICAL_FIXTURE_STATUS_VALUES
            ),
        )
        warnings.extend(odds_gate_warnings)
        if skip_for_odds_gate:
            skipped_fixture_ids.append(fixture.fixture_id)
            continue
        try:
            prediction = build_canonical_fixture_prediction_snapshot(
                fixture,
                odds_coverage=fixture_odds_coverage,
                availability_coverage=availability_coverage.get(fixture.fixture_id)
                if availability_coverage is not None
                else None,
                provider_conflict_impact=(
                    provider_conflict_impacts.get(fixture.fixture_id)
                    if provider_conflict_impacts is not None
                    else None
                ),
                historical_strength_snapshot=(
                    historical_strength_snapshots.get(fixture.competition_id)
                    if historical_strength_snapshots is not None
                    else None
                ),
                prediction_time_utc=normalized_prediction_time,
            )
        except ValueError as exc:
            skipped_fixture_ids.append(fixture.fixture_id)
            warnings.append(f"prediction_build_failed:{fixture.fixture_id}:{exc}")
            continue

        if prediction.data_quality_score < 50:
            warnings.append(
                f"fixture_data_quality_below_parlay_threshold:{fixture.fixture_id}"
            )

        if not dry_run:
            if target_feature_repository is None or target_prediction_repository is None:
                raise ValueError(
                    "feature and prediction repositories are required for commit runs"
                )
            feature_snapshot = prediction.feature_snapshot
            if feature_snapshot is not None:
                stored_feature = target_feature_repository.save(feature_snapshot)
                feature_snapshot_ids[fixture.fixture_id] = (
                    stored_feature.feature_snapshot_id
                )
                prediction = prediction.model_copy(
                    update={"feature_snapshot_id": stored_feature.feature_snapshot_id}
                )
            stored_prediction = target_prediction_repository.save(prediction)
            prediction_snapshot_ids[fixture.fixture_id] = (
                stored_prediction.prediction_snapshot_id
            )
            score_grid_ids[fixture.fixture_id] = stored_prediction.score_grid_id

        data_quality_scores[fixture.fixture_id] = prediction.data_quality_score

    return PreMatchPredictionPipelineResult(
        prediction_time_utc=normalized_prediction_time,
        fixture_count=len(fixtures),
        generated_count=len(data_quality_scores),
        dry_run=dry_run,
        feature_snapshot_ids=feature_snapshot_ids,
        prediction_snapshot_ids=prediction_snapshot_ids,
        score_grid_ids=score_grid_ids,
        data_quality_scores=data_quality_scores,
        skipped_fixture_ids=skipped_fixture_ids,
        warnings=warnings,
    )


def run_postgres_canonical_prematch_prediction_pipeline(
    *,
    database: PreMatchPredictionDatabase,
    fixture_ids: Sequence[str] | None = None,
    competition_id: str | None = None,
    as_of_time_utc: datetime | None = None,
    window_hours: int = 72,
    max_snapshot_lag_hours: int = 24,
    limit: int = 100,
    enforce_odds_quality_gate: bool = True,
    dry_run: bool = False,
) -> PreMatchPredictionPipelineResult:
    normalized_as_of = _aware_utc(as_of_time_utc or datetime.now(UTC))
    fixtures = list_canonical_fixtures_for_prediction(
        database,
        as_of_time_utc=normalized_as_of,
        window_hours=window_hours,
        competition_id=competition_id,
        fixture_ids=fixture_ids,
        limit=limit,
    )
    fixture_ids_for_coverage = [fixture.fixture_id for fixture in fixtures]
    historical_strength_snapshots = _historical_strength_snapshots_for_fixtures(
        database,
        fixtures=fixtures,
        as_of_time_utc=normalized_as_of,
    )
    odds_items = PostgresOddsCoverageRepository(database).list_fixture_coverage(
        fixture_ids=fixture_ids_for_coverage,
        as_of_time_utc=normalized_as_of,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
    )
    availability_items = PostgresAvailabilityCoverageRepository(database).list_fixture_coverage(
        fixture_ids=fixture_ids_for_coverage,
        as_of_time_utc=normalized_as_of,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
    )
    provider_conflict_impacts = PostgresProviderConflictEventRepository(
        database
    ).list_quality_impacts(fixture_ids=fixture_ids_for_coverage)
    return run_canonical_prematch_prediction_pipeline(
        fixtures=fixtures,
        feature_repository=PostgresFeatureSnapshotRepository(database),
        prediction_repository=PostgresPredictionSnapshotRepository(database),
        odds_coverage={item.fixture_id: item for item in odds_items},
        availability_coverage={item.fixture_id: item for item in availability_items},
        provider_conflict_impacts=provider_conflict_impacts,
        historical_strength_snapshots=historical_strength_snapshots,
        prediction_time_utc=normalized_as_of,
        enforce_odds_quality_gate=enforce_odds_quality_gate,
        dry_run=dry_run,
    )


def build_canonical_fixture_prediction_snapshot(
    fixture: CanonicalFixturePredictionCandidate,
    *,
    odds_coverage: FixtureOddsCoverage | None = None,
    availability_coverage: FixtureAvailabilityCoverage | None = None,
    provider_conflict_impact: ProviderConflictQualityImpact | None = None,
    historical_strength_snapshot: CompetitionHistoricalStrengthSnapshot | None = None,
    prediction_time_utc: datetime | None = None,
) -> PredictionSnapshot:
    normalized_prediction_time = _aware_utc(prediction_time_utc or datetime.now(UTC))
    estimate = _canonical_lambda_estimate(
        fixture,
        historical_strength_snapshot=historical_strength_snapshot,
    )
    feature_snapshot = build_fixture_feature_snapshot(
        _mock_fixture_payload_for_canonical(
            fixture,
            estimate=estimate,
            prediction_time_utc=normalized_prediction_time,
        ),
        feature_time_utc=normalized_prediction_time,
        feature_version=estimate.feature_version,
        odds_coverage=odds_coverage,
        availability_coverage=availability_coverage,
        provider_consistency_override=(
            provider_conflict_impact.provider_consistency_score
            if provider_conflict_impact is not None
            else None
        ),
        provider_conflict_context=(
            provider_conflict_impact.model_dump(mode="json")
            if provider_conflict_impact is not None
            else None
        ),
    )
    prediction = build_prediction_snapshot_from_lambda_estimate(
        estimate,
        prediction_time_utc=normalized_prediction_time,
        data_quality_score=feature_snapshot.data_quality_score,
        uncertainty=_uncertainty_from_quality(feature_snapshot.data_quality_score),
        cn_handicaps=(_handicap_line_int(fixture, estimate=estimate),),
        asian_handicap_lines=(_asian_handicap_line(fixture, estimate=estimate),),
        european_handicaps=(_handicap_line_int(fixture, estimate=estimate),),
        feature_snapshot=feature_snapshot,
    )
    return prediction.model_copy(
        update={
            "explanation_json": {
                **prediction.explanation_json,
                "canonical_fixture": {
                    "competition_id": fixture.competition_id,
                    "competition_name": fixture.competition_name,
                    "home_team_id": fixture.home_team_id,
                    "away_team_id": fixture.away_team_id,
                    "lambda_source": estimate.metadata_json.get("lambda_source"),
                    "cold_start_strategy": estimate.metadata_json.get(
                        "cold_start_strategy"
                    ),
                },
            }
        }
    )


def _selected_fixture_ids(fixture_ids: Sequence[str] | None) -> list[str]:
    if fixture_ids:
        return list(dict.fromkeys(fixture_ids))
    return [fixture["fixture_id"] for fixture in list_mock_fixtures()]


def _canonical_odds_gate_warnings(
    fixture: CanonicalFixturePredictionCandidate,
    odds_coverage: FixtureOddsCoverage | None,
    *,
    enforce: bool,
) -> tuple[bool, list[str]]:
    if not enforce:
        return False, []
    if odds_coverage is None or not odds_coverage.has_any_odds:
        return True, [f"canonical_odds_gate_failed:no_odds:{fixture.fixture_id}"]
    if not odds_coverage.has_1x2:
        return True, [f"canonical_odds_gate_failed:missing_1x2:{fixture.fixture_id}"]

    warnings: list[str] = []
    if not odds_coverage.fresh_enough:
        warnings.append(f"canonical_odds_gate_warning:stale_odds:{fixture.fixture_id}")
    if not odds_coverage.has_handicap:
        warnings.append(
            f"canonical_odds_gate_warning:missing_handicap:{fixture.fixture_id}"
        )
    return False, warnings


def _canonical_fixture_from_row(row: DatabaseRow) -> CanonicalFixturePredictionCandidate:
    return CanonicalFixturePredictionCandidate(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        model_status=_optional_str(row.get("model_status")),
        coverage_tier=_optional_str(row.get("coverage_tier")),
        config_json=_object_mapping(row.get("config_json")),
        kickoff_time_utc=_datetime(row["kickoff_time_utc"]),
        status=str(row["status"]),
        neutral_venue=_bool(row.get("neutral_venue")),
        aggregate_context_json=_object_mapping(row.get("aggregate_context_json")),
        home_team_id=str(row["home_team_id"]),
        home_team_name=str(row["home_team_name"]),
        away_team_id=str(row["away_team_id"]),
        away_team_name=str(row["away_team_name"]),
    )


def _historical_result_from_row(row: DatabaseRow) -> HistoricalFixtureResult:
    return HistoricalFixtureResult(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        kickoff_time_utc=_datetime(row["kickoff_time_utc"]),
        home_team_id=str(row["home_team_id"]),
        away_team_id=str(row["away_team_id"]),
        home_goals=_int(row["home_goals"]),
        away_goals=_int(row["away_goals"]),
    )


def _historical_strength_snapshots_for_fixtures(
    database: PreMatchPredictionDatabase,
    *,
    fixtures: Sequence[CanonicalFixturePredictionCandidate],
    as_of_time_utc: datetime,
) -> dict[str, CompetitionHistoricalStrengthSnapshot]:
    competition_ids = sorted({fixture.competition_id for fixture in fixtures})
    if not competition_ids:
        return {}
    result_limit = max(_historical_result_limit(fixture) for fixture in fixtures)
    historical_results = list_historical_results_for_prediction(
        database,
        competition_ids=competition_ids,
        as_of_time_utc=as_of_time_utc,
        per_competition_limit=result_limit,
    )
    results_by_competition: dict[str, list[HistoricalFixtureResult]] = {
        competition_id: [] for competition_id in competition_ids
    }
    for result in historical_results:
        results_by_competition.setdefault(result.competition_id, []).append(result)

    min_matches_by_competition: dict[str, int] = {}
    for fixture in fixtures:
        min_matches_by_competition[fixture.competition_id] = max(
            min_matches_by_competition.get(
                fixture.competition_id,
                _historical_min_team_matches(fixture),
            ),
            _historical_min_team_matches(fixture),
        )

    return {
        competition_id: build_competition_historical_strength_snapshot(
            results,
            competition_id=competition_id,
            as_of_time_utc=as_of_time_utc,
            min_team_matches=min_matches_by_competition.get(
                competition_id,
                DEFAULT_MIN_TEAM_MATCHES,
            ),
            max_results=result_limit,
        )
        for competition_id, results in results_by_competition.items()
    }


def _canonical_lambda_estimate(
    fixture: CanonicalFixturePredictionCandidate,
    *,
    historical_strength_snapshot: CompetitionHistoricalStrengthSnapshot | None = None,
) -> GoalLambdaEstimate:
    context = fixture.aggregate_context_json
    versions = _model_versions(fixture)
    lambda_home = _first_optional_float(
        _nested_float(context, "lambda_home"),
        _nested_float(context, "modeling.lambda_home"),
    )
    lambda_away = _first_optional_float(
        _nested_float(context, "lambda_away"),
        _nested_float(context, "modeling.lambda_away"),
    )
    rho = _first_optional_float(
        _nested_float(context, "rho"),
        _nested_float(context, "modeling.rho"),
    )
    time_decay_weight = _first_optional_float(
        _nested_float(context, "time_decay_weight"),
        _nested_float(context, "modeling.time_decay_weight"),
    )
    if rho is not None and versions["model_version"].startswith("poisson-"):
        versions = {**versions, "model_version": "dc-v1.5.0"}
    lambda_source = "aggregate_context"
    if lambda_home is None or lambda_away is None:
        historical_estimate = (
            estimate_goal_lambdas_from_team_strength(
                historical_strength_snapshot,
                fixture_id=fixture.fixture_id,
                home_team_id=fixture.home_team_id,
                away_team_id=fixture.away_team_id,
                neutral_venue=fixture.neutral_venue,
                model_version=versions["model_version"],
                feature_version=versions["feature_version"],
                calibration_version=versions["calibration_version"],
            )
            if historical_strength_snapshot is not None
            else None
        )
        if historical_estimate is not None:
            return historical_estimate.model_copy(
                update={
                    "metadata_json": {
                        **historical_estimate.metadata_json,
                        "cold_start_strategy": _cold_start_strategy(fixture),
                        "coverage_tier": fixture.coverage_tier,
                        "model_status": fixture.model_status,
                        "neutral_venue": fixture.neutral_venue,
                    }
                }
            )
        lambda_home, lambda_away = _competition_baseline_lambdas(fixture)
        lambda_source = "competition_cold_start_baseline"
    if fixture.neutral_venue:
        total = lambda_home + lambda_away
        lambda_home = max(0.05, total * 0.52)
        lambda_away = max(0.05, total * 0.48)

    return GoalLambdaEstimate(
        fixture_id=fixture.fixture_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_family="dixon_coles" if rho is not None else "poisson",
        model_version=versions["model_version"],
        feature_version=versions["feature_version"],
        calibration_version=versions["calibration_version"],
        rho=rho,
        time_decay_weight=time_decay_weight,
        metadata_json={
            "lambda_source": lambda_source,
            "cold_start_strategy": _cold_start_strategy(fixture),
            "competition_id": fixture.competition_id,
            "coverage_tier": fixture.coverage_tier,
            "model_status": fixture.model_status,
            "neutral_venue": fixture.neutral_venue,
            "rho": rho,
            "time_decay_weight": time_decay_weight,
            "dixon_coles_v15_compatible": True,
        },
    )


def _competition_baseline_lambdas(
    fixture: CanonicalFixturePredictionCandidate,
) -> tuple[float, float]:
    config_baseline = _object_mapping(
        _object_mapping(fixture.config_json.get("model")).get("goal_baseline")
    )
    home_from_config = _optional_float(config_baseline.get("lambda_home"))
    away_from_config = _optional_float(config_baseline.get("lambda_away"))
    if home_from_config is not None and away_from_config is not None:
        return max(0.05, home_from_config), max(0.05, away_from_config)
    if fixture.competition_id == "EPL":
        return 1.45, 1.12
    if fixture.competition_id == "JPN_J1":
        return 1.32, 1.16
    return 1.35, 1.10


def _mock_fixture_payload_for_canonical(
    fixture: CanonicalFixturePredictionCandidate,
    *,
    estimate: GoalLambdaEstimate,
    prediction_time_utc: datetime,
) -> MockFixture:
    return MockFixture(
        fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        competition=fixture.competition_name,
        kickoff_time_utc=fixture.kickoff_time_utc,
        home_team={"team_id": fixture.home_team_id, "name": fixture.home_team_name},
        away_team={"team_id": fixture.away_team_id, "name": fixture.away_team_name},
        home_lambda=estimate.lambda_home,
        away_lambda=estimate.lambda_away,
        prediction_time_utc=prediction_time_utc,
        status=_prediction_status(fixture),
        confidence="low",
        data_quality_score=_baseline_quality_score(fixture),
        cn_handicap=_handicap_line_int(fixture, estimate=estimate),
        asian_handicap_line=_asian_handicap_line(fixture, estimate=estimate),
        european_handicap=_handicap_line_int(fixture, estimate=estimate),
        market_1x2={},
        market_cn_handicap_1x2={},
        market_european_handicap_1x2={},
        key_factors={},
    )


def _prediction_status(fixture: CanonicalFixturePredictionCandidate) -> str:
    if fixture.model_status in {"beta", "production"}:
        return fixture.model_status
    if fixture.status == "scheduled":
        return "scheduled"
    return "beta"


def _baseline_quality_score(fixture: CanonicalFixturePredictionCandidate) -> float:
    if fixture.coverage_tier == "A_full":
        return 78.0
    if fixture.coverage_tier == "B_medium":
        return 68.0
    if fixture.coverage_tier == "C_basic":
        return 58.0
    return 48.0


def _uncertainty_from_quality(score: float) -> str:
    if score >= 80:
        return "medium"
    return "low"


def _handicap_line_int(
    fixture: CanonicalFixturePredictionCandidate,
    *,
    estimate: GoalLambdaEstimate | None = None,
) -> int:
    value = _nested_float(fixture.aggregate_context_json, "cn_handicap")
    if value is not None:
        return int(round(value))
    if estimate is not None:
        lambda_home = estimate.lambda_home
        lambda_away = estimate.lambda_away
    else:
        lambda_home, lambda_away = _competition_baseline_lambdas(fixture)
    if lambda_home - lambda_away >= 0.45:
        return -1
    if lambda_away - lambda_home >= 0.45:
        return 1
    return 0


def _asian_handicap_line(
    fixture: CanonicalFixturePredictionCandidate,
    *,
    estimate: GoalLambdaEstimate | None = None,
) -> float:
    value = _nested_float(fixture.aggregate_context_json, "asian_handicap_line")
    if value is not None:
        return _round_to_quarter(value)
    if estimate is not None:
        lambda_home = estimate.lambda_home
        lambda_away = estimate.lambda_away
    else:
        lambda_home, lambda_away = _competition_baseline_lambdas(fixture)
    return _round_to_quarter(-(lambda_home - lambda_away))


def _model_versions(fixture: CanonicalFixturePredictionCandidate) -> dict[str, str]:
    modeling = _object_mapping(fixture.aggregate_context_json.get("modeling"))
    return {
        "model_version": str(
            modeling.get("model_version")
            or fixture.aggregate_context_json.get("model_version")
            or "poisson-m1.1.0"
        ),
        "feature_version": str(
            modeling.get("feature_version")
            or fixture.aggregate_context_json.get("feature_version")
            or "features-m1.2.0"
        ),
        "calibration_version": str(
            modeling.get("calibration_version")
            or fixture.aggregate_context_json.get("calibration_version")
            or "calibration-m1.0.0"
        ),
    }


def _cold_start_strategy(fixture: CanonicalFixturePredictionCandidate) -> str | None:
    config_model = _object_mapping(fixture.config_json.get("model"))
    value = config_model.get("cold_start_strategy")
    return str(value) if value is not None else None


def _historical_min_team_matches(fixture: CanonicalFixturePredictionCandidate) -> int:
    config_model = _object_mapping(fixture.config_json.get("model"))
    return _config_int(
        config_model,
        keys=("min_team_matches", "min_historical_team_matches"),
        default=DEFAULT_MIN_TEAM_MATCHES,
        lower=1,
        upper=50,
    )


def _historical_result_limit(fixture: CanonicalFixturePredictionCandidate) -> int:
    config_model = _object_mapping(fixture.config_json.get("model"))
    return _config_int(
        config_model,
        keys=("historical_result_limit", "max_historical_results"),
        default=DEFAULT_HISTORICAL_RESULT_LIMIT,
        lower=20,
        upper=1000,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hours(value: int) -> timedelta:
    return timedelta(hours=max(1, min(value, 24 * 30)))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _object_mapping(value: object) -> dict[str, object]:
    raw = loads(value) if isinstance(value, str) else value
    if not isinstance(raw, dict):
        return {}
    return {str(key): item for key, item in raw.items()}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"true", "t", "1", "yes"}


def _nested_float(payload: Mapping[str, object], dotted_path: str) -> float | None:
    current: object = payload
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return _optional_float(current)


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _first_optional_float(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return int(value)
    return int(str(value))


def _config_int(
    payload: Mapping[str, object],
    *,
    keys: Sequence[str],
    default: int,
    lower: int,
    upper: int,
) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            parsed = int(str(value))
        except ValueError:
            continue
        return max(lower, min(parsed, upper))
    return default


def _round_to_quarter(value: float) -> float:
    return round(round(value * 4) / 4, 2)
