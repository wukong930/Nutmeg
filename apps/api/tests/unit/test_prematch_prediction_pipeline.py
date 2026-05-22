from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.features import StoredFeatureSnapshot
from nutmeg.modeling.team_strength import (
    HistoricalFixtureResult,
    build_competition_historical_strength_snapshot,
)
from nutmeg.predictions.pipeline import (
    LIST_CANONICAL_FIXTURES_FOR_PREDICTION_QUERY,
    LIST_HISTORICAL_RESULTS_FOR_PREDICTION_QUERY,
    CanonicalFixturePredictionCandidate,
    build_canonical_fixture_prediction_snapshot,
    list_canonical_fixtures_for_prediction,
    list_historical_results_for_prediction,
    run_canonical_prematch_prediction_pipeline,
    run_mock_prematch_prediction_pipeline,
)
from nutmeg.predictions.repository import StoredPostgresPredictionSnapshot
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.conflicts import ProviderConflictQualityImpact
from nutmeg.providers.odds_coverage import FixtureOddsCoverage


class FakeFeatureRepository:
    def __init__(self) -> None:
        self.saved: list[FeatureSnapshot] = []

    def save(self, snapshot: FeatureSnapshot) -> StoredFeatureSnapshot:
        self.saved.append(snapshot)
        return StoredFeatureSnapshot(
            feature_snapshot_id=500 + len(self.saved),
            snapshot=snapshot,
        )


class FakePredictionRepository:
    def __init__(self) -> None:
        self.saved: list[PredictionSnapshot] = []

    def save(self, snapshot: PredictionSnapshot) -> StoredPostgresPredictionSnapshot:
        self.saved.append(snapshot)
        index = len(self.saved)
        return StoredPostgresPredictionSnapshot(
            prediction_snapshot_id=800 + index,
            score_grid_id=700 + index,
            snapshot=snapshot,
        )


def test_prematch_pipeline_persists_feature_before_prediction_with_coverage_context() -> None:
    feature_repository = FakeFeatureRepository()
    prediction_repository = FakePredictionRepository()
    prediction_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    result = run_mock_prematch_prediction_pipeline(
        feature_repository=feature_repository,
        prediction_repository=prediction_repository,
        fixture_ids=["fix_epl_001", "missing_fixture"],
        odds_coverage={"fix_epl_001": _fresh_odds_coverage()},
        availability_coverage={"fix_epl_001": _fresh_availability_coverage()},
        prediction_time_utc=prediction_time,
        dry_run=False,
    )

    assert result.fixture_count == 1
    assert result.generated_count == 1
    assert result.feature_snapshot_ids == {"fix_epl_001": 501}
    assert result.prediction_snapshot_ids == {"fix_epl_001": 801}
    assert result.score_grid_ids == {"fix_epl_001": 701}
    assert result.data_quality_scores == {"fix_epl_001": 95.7}
    assert result.skipped_fixture_ids == ["missing_fixture"]
    assert result.warnings == ["fixture_not_found:missing_fixture"]
    assert feature_repository.saved[0].feature_time_utc == prediction_time
    saved_prediction = prediction_repository.saved[0]
    assert saved_prediction.feature_snapshot_id == 501
    assert saved_prediction.explanation_json["feature_snapshot"] != {}


def test_prematch_pipeline_dry_run_requires_no_repositories() -> None:
    result = run_mock_prematch_prediction_pipeline(
        fixture_ids=["fix_j1_001"],
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.fixture_count == 1
    assert result.generated_count == 1
    assert result.feature_snapshot_ids == {}
    assert result.prediction_snapshot_ids == {}
    assert result.data_quality_scores == {"fix_j1_001": 66.0}


def test_canonical_fixture_prediction_uses_context_lambdas_and_versions() -> None:
    prediction = build_canonical_fixture_prediction_snapshot(
        _canonical_candidate(
            aggregate_context_json={
                "modeling": {
                    "lambda_home": 1.62,
                    "lambda_away": 0.94,
                    "model_version": "poisson-test",
                    "feature_version": "features-test",
                },
                "asian_handicap_line": -0.75,
            }
        ),
        odds_coverage=_fresh_odds_coverage(),
        availability_coverage=_fresh_availability_coverage(),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    assert prediction.model_version == "poisson-test"
    assert prediction.feature_version == "features-test"
    assert prediction.score_grid.lambda_home == 1.62
    assert prediction.score_grid.lambda_away == 0.94
    assert prediction.explanation_json["canonical_fixture"] == {
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "home_team_id": "ars",
        "away_team_id": "liv",
        "lambda_source": "aggregate_context",
        "cold_start_strategy": "market_prior_plus_elo",
    }
    assert prediction.explanation_json["estimation_metadata"][
        "dixon_coles_v15_compatible"
    ] is True
    assert prediction.data_quality_score == 95.7


def test_canonical_fixture_prediction_applies_provider_conflict_quality_impact() -> None:
    prediction = build_canonical_fixture_prediction_snapshot(
        _canonical_candidate(),
        odds_coverage=_fresh_odds_coverage(),
        availability_coverage=_fresh_availability_coverage(),
        provider_conflict_impact=ProviderConflictQualityImpact(
            fixture_id="canonical_fix_001",
            conflict_count=1,
            data_quality_score_delta=-3.5,
            provider_consistency_score=0.65,
            latest_conflict_at_utc=datetime(2026, 5, 6, 10, 0, tzinfo=UTC),
        ),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    assert prediction.data_quality_score == 92.9
    feature_snapshot = prediction.feature_snapshot
    assert feature_snapshot is not None
    assert feature_snapshot.features_json["coverage"]["provider_conflicts"][
        "conflict_count"
    ] == 1


def test_canonical_fixture_prediction_uses_dixon_coles_context_when_rho_present() -> None:
    prediction = build_canonical_fixture_prediction_snapshot(
        _canonical_candidate(
            aggregate_context_json={
                "modeling": {
                    "lambda_home": 1.62,
                    "lambda_away": 0.94,
                    "rho": -0.05,
                    "time_decay_weight": 0.91,
                }
            }
        ),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    assert prediction.model_version == "dc-v1.5.0"
    assert prediction.explanation_json["model_family"] == "dixon_coles"
    assert prediction.explanation_json["model_notes"]["dixon_coles_applied"] is True
    assert prediction.explanation_json["model_notes"]["rho"] == -0.05
    assert prediction.explanation_json["estimation_metadata"]["time_decay_weight"] == 0.91


def test_canonical_fixture_prediction_uses_historical_team_strength_before_cold_start() -> None:
    prediction_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    historical_snapshot = build_competition_historical_strength_snapshot(
        [
            _historical_result("r1", "ars", "city", 3, 1),
            _historical_result("r2", "whu", "ars", 0, 2),
            _historical_result("r3", "ars", "che", 2, 0),
            _historical_result("r4", "liv", "city", 1, 2),
            _historical_result("r5", "whu", "liv", 2, 1),
            _historical_result("r6", "liv", "che", 0, 1),
        ],
        competition_id="EPL",
        as_of_time_utc=prediction_time,
        min_team_matches=3,
    )

    prediction = build_canonical_fixture_prediction_snapshot(
        _canonical_candidate(),
        historical_strength_snapshot=historical_snapshot,
        prediction_time_utc=prediction_time,
    )

    assert prediction.score_grid.lambda_home != 1.45
    assert prediction.score_grid.lambda_away != 1.12
    assert prediction.score_grid.lambda_home > prediction.score_grid.lambda_away
    assert prediction.explanation_json["canonical_fixture"]["lambda_source"] == (
        "historical_team_strength"
    )
    metadata = prediction.explanation_json["estimation_metadata"]
    assert metadata["historical_match_count"] == 6
    assert metadata["home_sample_matches"] == 3
    assert metadata["away_sample_matches"] == 3


def test_canonical_pipeline_persists_generic_postgres_fixture() -> None:
    feature_repository = FakeFeatureRepository()
    prediction_repository = FakePredictionRepository()

    result = run_canonical_prematch_prediction_pipeline(
        fixtures=[_canonical_candidate()],
        feature_repository=feature_repository,
        prediction_repository=prediction_repository,
        odds_coverage={"canonical_fix_001": _fresh_odds_coverage("canonical_fix_001")},
        availability_coverage={
            "canonical_fix_001": _fresh_availability_coverage("canonical_fix_001")
        },
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        dry_run=False,
    )

    assert result.fixture_count == 1
    assert result.generated_count == 1
    assert result.feature_snapshot_ids == {"canonical_fix_001": 501}
    assert result.prediction_snapshot_ids == {"canonical_fix_001": 801}
    assert result.score_grid_ids == {"canonical_fix_001": 701}
    assert prediction_repository.saved[0].fixture_id == "canonical_fix_001"
    assert prediction_repository.saved[0].feature_snapshot_id == 501


def test_canonical_pipeline_skips_fixture_without_required_1x2_odds() -> None:
    result = run_canonical_prematch_prediction_pipeline(
        fixtures=[_canonical_candidate()],
        odds_coverage={},
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        dry_run=True,
    )

    assert result.fixture_count == 1
    assert result.generated_count == 0
    assert result.skipped_fixture_ids == ["canonical_fix_001"]
    assert result.warnings == [
        "canonical_odds_gate_failed:no_odds:canonical_fix_001"
    ]


def test_canonical_pipeline_warns_for_stale_or_missing_handicap_odds() -> None:
    result = run_canonical_prematch_prediction_pipeline(
        fixtures=[_canonical_candidate()],
        odds_coverage={
            "canonical_fix_001": _fresh_odds_coverage(
                "canonical_fix_001",
                has_handicap=False,
                fresh_enough=False,
            )
        },
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        dry_run=True,
    )

    assert result.generated_count == 1
    assert result.warnings == [
        "canonical_odds_gate_warning:stale_odds:canonical_fix_001",
        "canonical_odds_gate_warning:missing_handicap:canonical_fix_001",
    ]
    assert result.data_quality_scores["canonical_fix_001"] < 70


def test_canonical_fixture_query_maps_rows_and_applies_filters() -> None:
    database = FakeCanonicalFixtureDatabase()
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    fixtures = list_canonical_fixtures_for_prediction(
        database,
        as_of_time_utc=as_of_time,
        window_hours=48,
        competition_id="EPL",
        fixture_ids=["canonical_fix_001"],
        limit=25,
    )

    assert [fixture.fixture_id for fixture in fixtures] == ["canonical_fix_001"]
    assert fixtures[0].aggregate_context_json["lambda_home"] == 1.5
    query, params = database.calls[0]
    assert query == LIST_CANONICAL_FIXTURES_FOR_PREDICTION_QUERY
    assert params["competition_id"] == "EPL"
    assert params["fixture_ids"] == ["canonical_fix_001"]
    assert params["limit"] == 25


def test_historical_result_query_maps_rows_and_is_as_of_safe() -> None:
    database = FakeHistoricalResultDatabase()
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    results = list_historical_results_for_prediction(
        database,
        competition_ids=["EPL", "EPL"],
        as_of_time_utc=as_of_time,
        per_competition_limit=30,
    )

    assert [result.fixture_id for result in results] == ["hist_fix_001"]
    query, params = database.calls[0]
    assert query == LIST_HISTORICAL_RESULTS_FOR_PREDICTION_QUERY
    assert "f.kickoff_time_utc < %(as_of_time_utc)s" in query
    assert "COALESCE(r.settled_at, f.kickoff_time_utc)" in query
    assert params["competition_ids"] == ["EPL"]
    assert params["as_of_time_utc"] == as_of_time
    assert params["per_competition_limit"] == 30


class FakeCanonicalFixtureDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, query: str, params: object) -> list[dict[str, object]]:
        self.calls.append((query, params))
        return [
            {
                "fixture_id": "canonical_fix_001",
                "competition_id": "EPL",
                "competition_name": "Premier League",
                "model_status": "beta",
                "coverage_tier": "A_full",
                "config_json": {
                    "model": {"cold_start_strategy": "market_prior_plus_elo"}
                },
                "kickoff_time_utc": datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
                "status": "scheduled",
                "neutral_venue": False,
                "aggregate_context_json": {"lambda_home": 1.5, "lambda_away": 1.0},
                "home_team_id": "ars",
                "home_team_name": "Arsenal",
                "away_team_id": "liv",
                "away_team_name": "Liverpool",
            }
        ]

    def fetch_one(self, query: str, params: object) -> dict[str, object] | None:
        raise AssertionError(f"unexpected query: {query}")


class FakeHistoricalResultDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def fetch_all(self, query: str, params: object) -> list[dict[str, object]]:
        self.calls.append((query, params))
        return [
            {
                "fixture_id": "hist_fix_001",
                "competition_id": "EPL",
                "kickoff_time_utc": datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                "home_team_id": "ars",
                "away_team_id": "liv",
                "home_goals": 2,
                "away_goals": 1,
            }
        ]

    def fetch_one(self, query: str, params: object) -> dict[str, object] | None:
        raise AssertionError(f"unexpected query: {query}")


def _canonical_candidate(
    *,
    aggregate_context_json: dict[str, object] | None = None,
) -> CanonicalFixturePredictionCandidate:
    return CanonicalFixturePredictionCandidate(
        fixture_id="canonical_fix_001",
        competition_id="EPL",
        competition_name="Premier League",
        model_status="beta",
        coverage_tier="A_full",
        config_json={"model": {"cold_start_strategy": "market_prior_plus_elo"}},
        kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        status="scheduled",
        neutral_venue=False,
        aggregate_context_json=aggregate_context_json or {},
        home_team_id="ars",
        home_team_name="Arsenal",
        away_team_id="liv",
        away_team_name="Liverpool",
    )


def _historical_result(
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixtureResult:
    return HistoricalFixtureResult(
        fixture_id=fixture_id,
        competition_id="EPL",
        kickoff_time_utc=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_goals=home_goals,
        away_goals=away_goals,
    )


def _fresh_odds_coverage(
    fixture_id: str = "fix_epl_001",
    *,
    has_1x2: bool = True,
    has_handicap: bool = True,
    fresh_enough: bool = True,
) -> FixtureOddsCoverage:
    kickoff = datetime(2026, 5, 6, 19, 0, tzinfo=UTC)
    market_types = []
    if has_1x2:
        market_types.append("1x2")
    if has_handicap:
        market_types.append("asian_handicap")
    return FixtureOddsCoverage(
        fixture_id=fixture_id,
        competition_id="EPL",
        competition_name="Premier League",
        kickoff_time_utc=kickoff,
        odds_snapshot_count=len(market_types) * 4,
        bookmaker_count=3,
        has_any_odds=bool(market_types),
        has_1x2=has_1x2,
        has_handicap=has_handicap,
        latest_snapshot_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        latest_snapshot_lag_hours=7.0,
        fresh_enough=fresh_enough,
        market_types=market_types,
    )


def _fresh_availability_coverage(
    fixture_id: str = "fix_epl_001",
) -> FixtureAvailabilityCoverage:
    kickoff = datetime(2026, 5, 6, 19, 0, tzinfo=UTC)
    return FixtureAvailabilityCoverage(
        fixture_id=fixture_id,
        competition_id="EPL",
        competition_name="Premier League",
        kickoff_time_utc=kickoff,
        availability_snapshot_count=5,
        lineup_snapshot_count=22,
        latest_availability_snapshot_time_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
        availability_snapshot_lag_hours=6.5,
        latest_lineup_snapshot_time_utc=datetime(2026, 5, 6, 13, 0, tzinfo=UTC),
        lineup_snapshot_lag_hours=6.0,
        has_availability=True,
        has_lineup=True,
        availability_fresh_enough=True,
        lineup_fresh_enough=True,
        fresh_enough=True,
    )
