from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.features import build_fixture_feature_snapshot
from nutmeg.market_resolver import resolve_1x2, score_grid_to_market_probabilities
from nutmeg.modeling import build_score_grid_from_estimate, score_grid_tail_metrics
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.mock import get_mock_fixture
from nutmeg.providers.odds_coverage import FixtureOddsCoverage


def build_prediction_snapshot_from_lambda_estimate(
    estimate: GoalLambdaEstimate,
    *,
    prediction_time_utc: datetime,
    data_quality_score: float = 75.0,
    uncertainty: str = "medium",
    cn_handicaps: tuple[int, ...] = (-1,),
    asian_handicap_lines: tuple[float, ...] = (-0.25,),
    european_handicaps: tuple[int, ...] = (-1,),
    max_goals: int = 8,
    feature_snapshot: FeatureSnapshot | None = None,
    feature_snapshot_id: int | None = None,
) -> PredictionSnapshot:
    score_grid = build_score_grid_from_estimate(estimate, max_goals=max_goals)
    one_x_two = resolve_1x2(score_grid)
    market_probabilities = score_grid_to_market_probabilities(
        score_grid,
        cn_handicaps=cn_handicaps,
        asian_handicap_lines=asian_handicap_lines,
        european_handicaps=european_handicaps,
        correct_score_top_n=5,
    )
    tail_metrics = score_grid_tail_metrics(score_grid)
    effective_data_quality_score = (
        feature_snapshot.data_quality_score
        if feature_snapshot is not None
        else data_quality_score
    )
    feature_explanation: dict[str, object] = {}
    if feature_snapshot is not None:
        feature_explanation = {
            "feature_time_utc": feature_snapshot.feature_time_utc.isoformat(),
            "feature_version": feature_snapshot.feature_version,
            "source_snapshot_refs": feature_snapshot.source_snapshot_refs,
            "data_quality_score": feature_snapshot.data_quality_score,
            "data_quality": feature_snapshot.features_json.get("data_quality", {}),
            "coverage": feature_snapshot.features_json.get("coverage", {}),
        }
    return PredictionSnapshot(
        fixture_id=estimate.fixture_id,
        prediction_time_utc=prediction_time_utc,
        model_version=estimate.model_version,
        feature_version=estimate.feature_version,
        calibration_version=estimate.calibration_version,
        feature_snapshot_id=feature_snapshot_id,
        feature_snapshot=feature_snapshot,
        score_grid=score_grid,
        market_probabilities=market_probabilities,
        p_home=one_x_two.home_win,
        p_draw=one_x_two.draw,
        p_away=one_x_two.away_win,
        uncertainty=uncertainty,
        data_quality_score=effective_data_quality_score,
        explanation_json={
            "model_family": estimate.model_family,
            "lambda_home": estimate.lambda_home,
            "lambda_away": estimate.lambda_away,
            "feature_snapshot": feature_explanation,
            "tail_metrics": tail_metrics.model_dump(mode="json"),
            "estimation_metadata": estimate.metadata_json,
            "model_notes": {
                "primary_model": estimate.model_family,
                "fallback_used": False,
                "dixon_coles_ready": True,
                "dixon_coles_applied": estimate.rho is not None,
                "rho": estimate.rho,
                "time_decay_weight": estimate.time_decay_weight,
            },
        },
    )


def build_mock_prediction_snapshot(fixture_id: str) -> PredictionSnapshot | None:
    return build_mock_prediction_snapshot_with_context(fixture_id)


def build_mock_prediction_snapshot_with_context(
    fixture_id: str,
    *,
    odds_coverage: FixtureOddsCoverage | None = None,
    availability_coverage: FixtureAvailabilityCoverage | None = None,
    feature_snapshot_id: int | None = None,
    prediction_time_utc: datetime | None = None,
) -> PredictionSnapshot | None:
    fixture = get_mock_fixture(fixture_id)
    if fixture is None:
        return None

    model_version = "poisson-m1.0.0"
    feature_version = "features-m1.0.0"
    calibration_version = "calibration-m1.0.0"
    effective_prediction_time = prediction_time_utc or fixture.get(
        "prediction_time_utc",
        datetime.now(tz=UTC),
    )
    feature_snapshot = build_fixture_feature_snapshot(
        fixture,
        feature_time_utc=effective_prediction_time,
        feature_version=feature_version,
        odds_coverage=odds_coverage,
        availability_coverage=availability_coverage,
    )
    estimate = GoalLambdaEstimate(
        fixture_id=fixture_id,
        lambda_home=fixture["home_lambda"],
        lambda_away=fixture["away_lambda"],
        model_family="poisson",
        model_version=model_version,
        feature_version=feature_version,
        calibration_version=calibration_version,
    )
    return build_prediction_snapshot_from_lambda_estimate(
        estimate,
        prediction_time_utc=effective_prediction_time,
        data_quality_score=fixture.get("data_quality_score", 75.0),
        uncertainty=fixture.get("confidence", "medium"),
        cn_handicaps=(fixture.get("cn_handicap", -1),),
        asian_handicap_lines=(fixture.get("asian_handicap_line", -0.25),),
        european_handicaps=(fixture.get("european_handicap", -1),),
        feature_snapshot=feature_snapshot,
        feature_snapshot_id=feature_snapshot_id,
    )
