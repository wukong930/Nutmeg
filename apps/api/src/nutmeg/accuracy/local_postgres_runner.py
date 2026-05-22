from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps
from statistics import mean
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.accuracy.mock_repository import (
    ACTIVE_MODEL_VERSION,
    get_mock_actual_result,
)
from nutmeg.accuracy.model_comparison import compare_model_versions_stub
from nutmeg.accuracy.postgres_write_repository import PostgresAccuracyWriteRepository
from nutmeg.accuracy.workflow import (
    evaluate_and_persist_post_match_result,
    one_x_two_calibration_observations,
)
from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.domain.accuracy import (
    ActualMatchResult,
    ModelComparisonStub,
    ModelVersionMetrics,
    PredictionEvaluation,
)
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.features import PostgresFeatureSnapshotRepository
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.providers.mock import MockFixture, list_mock_fixtures

DELETE_MODEL_COMPARISONS_QUERY = """
DELETE FROM model_comparison_reports
WHERE baseline_model_version = %(baseline_model_version)s
   OR candidate_model_version = %(candidate_model_version)s
"""

DELETE_CALIBRATION_BUCKETS_QUERY = """
DELETE FROM calibration_buckets
WHERE model_version = %(model_version)s
  AND market_type = '1x2'
  AND competition_id = ANY(%(competition_ids)s)
"""

DELETE_PREDICTION_EVALUATIONS_QUERY = """
DELETE FROM prediction_evaluations
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_MARKET_PREDICTIONS_QUERY = """
DELETE FROM market_predictions
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_UPSET_ALERTS_QUERY = """
DELETE FROM upset_alerts
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_PREDICTION_SNAPSHOTS_QUERY = """
DELETE FROM prediction_snapshots
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_FEATURE_SNAPSHOTS_QUERY = """
DELETE FROM feature_snapshots
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_SCORE_GRIDS_QUERY = """
DELETE FROM score_probability_grids
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

DELETE_RESULTS_QUERY = """
DELETE FROM results
WHERE fixture_id = ANY(%(fixture_ids)s)
"""

UPSERT_COMPETITION_QUERY = """
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

UPSERT_TEAM_QUERY = """
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

UPSERT_FIXTURE_QUERY = """
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

UPSERT_RESULT_QUERY = """
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

UPSERT_MODEL_VERSION_QUERY = """
INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  feature_version,
  calibration_version,
  metrics_json,
  params_json,
  activated_at
) VALUES (
  %(model_version)s,
  %(model_family)s,
  %(status)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(metrics_json)s::jsonb,
  %(params_json)s::jsonb,
  %(activated_at)s
)
ON CONFLICT (model_version) DO UPDATE SET
  model_family = EXCLUDED.model_family,
  status = EXCLUDED.status,
  feature_version = EXCLUDED.feature_version,
  calibration_version = EXCLUDED.calibration_version,
  metrics_json = EXCLUDED.metrics_json,
  params_json = EXCLUDED.params_json,
  activated_at = EXCLUDED.activated_at
RETURNING model_version
"""

INSERT_SCORE_GRID_QUERY = """
INSERT INTO score_probability_grids (
  fixture_id,
  prediction_time_utc,
  model_version,
  calibration_version,
  max_goals,
  grid_json,
  tail_mass,
  lambda_home,
  lambda_away
) VALUES (
  %(fixture_id)s,
  %(prediction_time_utc)s,
  %(model_version)s,
  %(calibration_version)s,
  %(max_goals)s,
  %(grid_json)s::jsonb,
  %(tail_mass)s,
  %(lambda_home)s,
  %(lambda_away)s
)
RETURNING score_grid_id
"""

INSERT_PREDICTION_SNAPSHOT_QUERY = """
INSERT INTO prediction_snapshots (
  fixture_id,
  prediction_time_utc,
  model_version,
  feature_version,
  calibration_version,
  feature_snapshot_id,
  score_grid_id,
  p_home,
  p_draw,
  p_away,
  market_probabilities_json,
  uncertainty,
  data_quality_score,
  explanation_json
) VALUES (
  %(fixture_id)s,
  %(prediction_time_utc)s,
  %(model_version)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(feature_snapshot_id)s,
  %(score_grid_id)s,
  %(p_home)s,
  %(p_draw)s,
  %(p_away)s,
  %(market_probabilities_json)s::jsonb,
  %(uncertainty)s,
  %(data_quality_score)s,
  %(explanation_json)s::jsonb
)
RETURNING prediction_snapshot_id
"""


class LocalAccuracyDatabase(Protocol):
    def execute(self, query: str, params: QueryParams) -> None:
        """Execute a SQL statement without a result set."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a SQL statement and return one mapping row."""


class LocalAccuracyLoopRun(BaseModel):
    fixture_count: int = Field(ge=0)
    prediction_snapshot_ids: dict[str, int]
    evaluation_ids: list[int]
    calibration_observation_count: int = Field(ge=0)
    model_comparison_report_id: int | None = None


def run_mock_accuracy_postgres_e2e(
    database: LocalAccuracyDatabase,
    *,
    reset: bool = True,
) -> LocalAccuracyLoopRun:
    fixtures = list_mock_fixtures()
    fixture_ids = [fixture["fixture_id"] for fixture in fixtures]
    write_repository = PostgresAccuracyWriteRepository(database)
    feature_repository = PostgresFeatureSnapshotRepository(database)
    if reset:
        _reset_mock_accuracy_rows(database, fixture_ids=fixture_ids)

    snapshots: dict[str, PredictionSnapshot] = {}
    evaluations: list[PredictionEvaluation] = []
    evaluation_ids: list[int] = []
    prediction_snapshot_ids: dict[str, int] = {}
    calibration_observation_count = 0

    _upsert_model_versions(database)
    for fixture in fixtures:
        snapshot = build_mock_prediction_snapshot(fixture["fixture_id"])
        actual_result = get_mock_actual_result(fixture["fixture_id"])
        if snapshot is None or actual_result is None:
            continue
        snapshots[fixture["fixture_id"]] = snapshot
        _upsert_fixture_prerequisites(database, fixture)
        _upsert_result(database, actual_result)
        stored_feature_snapshot_id = None
        if snapshot.feature_snapshot is not None:
            stored_feature_snapshot = feature_repository.save(snapshot.feature_snapshot)
            stored_feature_snapshot_id = stored_feature_snapshot.feature_snapshot_id
            snapshot = snapshot.model_copy(
                update={"feature_snapshot_id": stored_feature_snapshot_id}
            )
            snapshots[fixture["fixture_id"]] = snapshot
        score_grid_id = _insert_score_grid(database, snapshot)
        prediction_snapshot_id = _insert_prediction_snapshot(
            database,
            snapshot,
            score_grid_id=score_grid_id,
            feature_snapshot_id=stored_feature_snapshot_id,
        )
        prediction_snapshot_ids[fixture["fixture_id"]] = prediction_snapshot_id
        persisted = evaluate_and_persist_post_match_result(
            snapshot=snapshot,
            actual_result=actual_result,
            repository=write_repository,
            prediction_snapshot_id=str(prediction_snapshot_id),
            competition_id=fixture["competition_id"],
        )
        evaluations.append(persisted.stored_evaluation.evaluation)
        evaluation_ids.append(persisted.stored_evaluation.evaluation_id)
        calibration_observation_count += 3

    comparison = _comparison_from_evaluations(list(snapshots.values()), evaluations)
    comparison_report_id = None
    if comparison is not None:
        comparison_report_id = write_repository.save_model_comparison_report(
            comparison
        ).comparison_report_id

    return LocalAccuracyLoopRun(
        fixture_count=len(prediction_snapshot_ids),
        prediction_snapshot_ids=prediction_snapshot_ids,
        evaluation_ids=evaluation_ids,
        calibration_observation_count=calibration_observation_count,
        model_comparison_report_id=comparison_report_id,
    )


def run_from_settings(*, reset: bool = True) -> LocalAccuracyLoopRun:
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    return run_mock_accuracy_postgres_e2e(database, reset=reset)


def main() -> None:
    print(run_from_settings().model_dump_json(indent=2))


def _reset_mock_accuracy_rows(
    database: LocalAccuracyDatabase,
    *,
    fixture_ids: Sequence[str],
) -> None:
    params: dict[str, object] = {"fixture_ids": list(fixture_ids)}
    database.execute(DELETE_MODEL_COMPARISONS_QUERY, _comparison_cleanup_params())
    database.execute(
        DELETE_CALIBRATION_BUCKETS_QUERY,
        {
            "model_version": ACTIVE_MODEL_VERSION,
            "competition_ids": ["EPL", "JPN_J1"],
        },
    )
    database.execute(DELETE_PREDICTION_EVALUATIONS_QUERY, params)
    database.execute(DELETE_MARKET_PREDICTIONS_QUERY, params)
    database.execute(DELETE_UPSET_ALERTS_QUERY, params)
    database.execute(DELETE_PREDICTION_SNAPSHOTS_QUERY, params)
    database.execute(DELETE_FEATURE_SNAPSHOTS_QUERY, params)
    database.execute(DELETE_SCORE_GRIDS_QUERY, params)
    database.execute(DELETE_RESULTS_QUERY, params)


def _upsert_model_versions(database: LocalAccuracyDatabase) -> None:
    _required_row(
        database.fetch_one(
            UPSERT_MODEL_VERSION_QUERY,
            {
                "model_version": ACTIVE_MODEL_VERSION,
                "model_family": "poisson",
                "status": "active",
                "feature_version": "features-m1.0.0",
                "calibration_version": "calibration-m1.0.0",
                "metrics_json": _json({"source": "mock_accuracy_e2e"}),
                "params_json": _json({"dixon_coles_ready": True}),
                "activated_at": datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            },
        )
    )
    _required_row(
        database.fetch_one(
            UPSERT_MODEL_VERSION_QUERY,
            {
                "model_version": "dc-v1.5-candidate",
                "model_family": "dixon_coles",
                "status": "candidate",
                "feature_version": "features-m1.0.0",
                "calibration_version": "calibration-m1.0.0",
                "metrics_json": _json({"source": "mock_accuracy_e2e"}),
                "params_json": _json({"rho": "pending"}),
                "activated_at": None,
            },
        )
    )


def _upsert_fixture_prerequisites(
    database: LocalAccuracyDatabase,
    fixture: MockFixture,
) -> None:
    country = _country_for_competition(fixture["competition_id"])
    _required_row(
        database.fetch_one(
            UPSERT_COMPETITION_QUERY,
            {
                "competition_id": fixture["competition_id"],
                "name": fixture["competition"],
                "country": country,
                "region": _region_for_competition(fixture["competition_id"]),
                "competition_type": "league",
                "team_type": "club",
                "provider_primary": "mock",
                "coverage_tier": "local_e2e",
                "model_status": "beta",
                "config_json": _json({"source": "mock_accuracy_e2e"}),
            },
        )
    )
    for team in [fixture["home_team"], fixture["away_team"]]:
        _required_row(
            database.fetch_one(
                UPSERT_TEAM_QUERY,
                {
                    "team_id": team["team_id"],
                    "name": team["name"],
                    "country": country,
                    "team_type": "club",
                    "metadata_json": _json({"source": "mock_accuracy_e2e"}),
                },
            )
        )
    _required_row(
        database.fetch_one(
            UPSERT_FIXTURE_QUERY,
            {
                "fixture_id": fixture["fixture_id"],
                "competition_id": fixture["competition_id"],
                "home_team_id": fixture["home_team"]["team_id"],
                "away_team_id": fixture["away_team"]["team_id"],
                "kickoff_time_utc": fixture["kickoff_time_utc"],
                "status": "finished",
                "aggregate_context_json": _json(
                    {
                        "source": "mock_accuracy_e2e",
                        "confidence": fixture["confidence"],
                    }
                ),
            },
        )
    )


def _upsert_result(database: LocalAccuracyDatabase, result: ActualMatchResult) -> None:
    _required_row(
        database.fetch_one(
            UPSERT_RESULT_QUERY,
            {
                "fixture_id": result.fixture_id,
                "home_goals": result.home_goals,
                "away_goals": result.away_goals,
                "result_1x2": result.result_1x2.value,
                "settled_at": result.settled_at
                or datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
                "source": "mock_accuracy_e2e",
            },
        )
    )


def _insert_score_grid(
    database: LocalAccuracyDatabase,
    snapshot: PredictionSnapshot,
) -> int:
    score_grid = snapshot.score_grid
    row = _required_row(
        database.fetch_one(
            INSERT_SCORE_GRID_QUERY,
            {
                "fixture_id": snapshot.fixture_id,
                "prediction_time_utc": snapshot.prediction_time_utc,
                "model_version": snapshot.model_version,
                "calibration_version": snapshot.calibration_version,
                "max_goals": score_grid.max_goals,
                "grid_json": _json(score_grid.grid),
                "tail_mass": score_grid.tail_mass,
                "lambda_home": score_grid.lambda_home,
                "lambda_away": score_grid.lambda_away,
            },
        )
    )
    return _int(row["score_grid_id"])


def _insert_prediction_snapshot(
    database: LocalAccuracyDatabase,
    snapshot: PredictionSnapshot,
    *,
    score_grid_id: int,
    feature_snapshot_id: int | None = None,
) -> int:
    row = _required_row(
        database.fetch_one(
            INSERT_PREDICTION_SNAPSHOT_QUERY,
            {
                "fixture_id": snapshot.fixture_id,
                "prediction_time_utc": snapshot.prediction_time_utc,
                "model_version": snapshot.model_version,
                "feature_version": snapshot.feature_version,
                "calibration_version": snapshot.calibration_version,
                "feature_snapshot_id": feature_snapshot_id,
                "score_grid_id": score_grid_id,
                "p_home": snapshot.p_home,
                "p_draw": snapshot.p_draw,
                "p_away": snapshot.p_away,
                "market_probabilities_json": _json(snapshot.market_probabilities),
                "uncertainty": snapshot.uncertainty,
                "data_quality_score": snapshot.data_quality_score,
                "explanation_json": _json(snapshot.explanation_json),
            },
        )
    )
    return _int(row["prediction_snapshot_id"])


def _comparison_from_evaluations(
    snapshots: Sequence[PredictionSnapshot],
    evaluations: Sequence[PredictionEvaluation],
) -> ModelComparisonStub | None:
    if not evaluations:
        return None
    calibration_errors = [
        abs(
            observation.predicted_probability
            - (1.0 if observation.actual_occurred else 0.0)
        )
        for snapshot in snapshots
        for actual_result in [get_mock_actual_result(snapshot.fixture_id)]
        if actual_result is not None
        for observation in one_x_two_calibration_observations(
            snapshot,
            actual_result,
            competition_id=None,
        )
    ]
    baseline = ModelVersionMetrics(
        model_version=ACTIVE_MODEL_VERSION,
        sample_size=len(evaluations),
        log_loss=mean([evaluation.log_loss_1x2 for evaluation in evaluations]),
        brier_score=mean([evaluation.brier_score_1x2 for evaluation in evaluations]),
        ece=mean(calibration_errors) if calibration_errors else None,
    )
    candidate = ModelVersionMetrics(
        model_version="dc-v1.5-candidate",
        sample_size=baseline.sample_size,
        log_loss=baseline.log_loss * 0.988,
        brier_score=baseline.brier_score * 0.986,
        ece=(baseline.ece * 0.92) if baseline.ece is not None else None,
    )
    return compare_model_versions_stub(
        candidate_metrics=candidate,
        baseline_metrics=baseline,
    )


def _comparison_cleanup_params() -> QueryParams:
    return {
        "baseline_model_version": ACTIVE_MODEL_VERSION,
        "candidate_model_version": "dc-v1.5-candidate",
    }


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _country_for_competition(competition_id: str) -> str:
    if competition_id == "JPN_J1":
        return "Japan"
    return "England"


def _region_for_competition(competition_id: str) -> str:
    if competition_id == "JPN_J1":
        return "Asia"
    return "Europe"


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"))


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
