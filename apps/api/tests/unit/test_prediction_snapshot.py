from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.predictions.snapshot_builder import build_prediction_snapshot_from_lambda_estimate


def test_prediction_snapshot_contains_required_traceability_fields() -> None:
    snapshot = build_mock_prediction_snapshot("fix_epl_001")

    assert snapshot is not None
    assert snapshot.fixture_id == "fix_epl_001"
    assert snapshot.model_version == "poisson-m1.0.0"
    assert snapshot.feature_version == "features-m1.0.0"
    assert snapshot.calibration_version == "calibration-m1.0.0"
    assert snapshot.feature_snapshot is not None
    assert snapshot.feature_snapshot.data_quality_score == 82.0
    assert snapshot.explanation_json["feature_snapshot"]["source_snapshot_refs"] == {
        "mock_fixture": "fix_epl_001"
    }
    assert snapshot.score_grid.is_normalized()
    assert set(snapshot.market_probabilities["1x2"]) == {"home_win", "draw", "away_win"}


def test_prediction_snapshot_applies_dixon_coles_grid_when_rho_is_present() -> None:
    snapshot = build_prediction_snapshot_from_lambda_estimate(
        GoalLambdaEstimate(
            fixture_id="dc_fixture",
            lambda_home=1.4,
            lambda_away=1.1,
            model_family="dixon_coles",
            model_version="dc-v1.5.0",
            feature_version="features-m1.2.0",
            calibration_version="calibration-m1.0.0",
            rho=-0.05,
            time_decay_weight=0.93,
        ),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    assert snapshot.score_grid.is_normalized()
    assert snapshot.model_version == "dc-v1.5.0"
    assert snapshot.explanation_json["model_family"] == "dixon_coles"
    assert snapshot.explanation_json["model_notes"]["dixon_coles_applied"] is True
    assert snapshot.explanation_json["model_notes"]["rho"] == -0.05
    assert snapshot.explanation_json["model_notes"]["time_decay_weight"] == 0.93
