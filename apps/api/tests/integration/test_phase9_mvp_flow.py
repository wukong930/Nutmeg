from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from nutmeg.accuracy.calibration import calibration_bucket_key_for_probability
from nutmeg.accuracy.summary import CalibrationObservation
from nutmeg.accuracy.workflow import evaluate_and_persist_post_match_result
from nutmeg.domain.accuracy import (
    ActualMatchResult,
    CalibrationBucket,
    PredictionEvaluation,
    StoredPredictionEvaluation,
)
from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.main import app
from nutmeg.market_resolver import score_grid_to_market_probabilities
from nutmeg.parlay import evaluate_parlay
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.providers.mock import list_mock_fixtures

client = TestClient(app)


class InMemoryAccuracyWriteRepository:
    def __init__(self) -> None:
        self.evaluations: list[PredictionEvaluation] = []
        self.buckets: dict[str, CalibrationBucket] = {}

    def save_prediction_evaluation(
        self,
        evaluation: PredictionEvaluation,
    ) -> StoredPredictionEvaluation:
        self.evaluations.append(evaluation)
        return StoredPredictionEvaluation(
            evaluation_id=len(self.evaluations),
            evaluation=evaluation,
        )

    def upsert_calibration_observations(
        self,
        observations: Sequence[CalibrationObservation],
        *,
        model_version: str,
        bucket_size: float = 0.10,
    ) -> list[CalibrationBucket]:
        for observation in observations:
            key = calibration_bucket_key_for_probability(
                predicted_probability=observation.predicted_probability,
                model_version=model_version,
                market_type=observation.market_type,
                outcome=observation.outcome,
                bucket_size=bucket_size,
                competition_id=observation.competition_id,
            )
            bucket = self.buckets.get(key.stable_id) or CalibrationBucket(key=key)
            self.buckets[key.stable_id] = bucket.model_copy(
                update={
                    "sample_size": bucket.sample_size + 1,
                    "predicted_probability_sum": (
                        bucket.predicted_probability_sum
                        + observation.predicted_probability
                    ),
                    "actual_count": bucket.actual_count
                    + (1 if observation.actual_occurred else 0),
                }
            )
        return list(self.buckets.values())


def test_phase9_complete_mock_flow_from_fixture_to_accuracy() -> None:
    fixtures = list_mock_fixtures()
    assert len(fixtures) >= 2

    first_snapshot = build_mock_prediction_snapshot(fixtures[0]["fixture_id"])
    second_snapshot = build_mock_prediction_snapshot(fixtures[1]["fixture_id"])
    assert first_snapshot is not None
    assert second_snapshot is not None

    assert first_snapshot.model_version == "poisson-m1.0.0"
    assert first_snapshot.feature_version == "features-m1.0.0"
    assert first_snapshot.calibration_version == "calibration-m1.0.0"
    assert first_snapshot.prediction_time_utc == fixtures[0]["prediction_time_utc"]
    assert first_snapshot.score_grid.is_normalized(tolerance=1e-5)

    derived_markets = score_grid_to_market_probabilities(
        first_snapshot.score_grid,
        cn_handicaps=(fixtures[0]["cn_handicap"],),
        asian_handicap_lines=(fixtures[0]["asian_handicap_line"],),
        european_handicaps=(fixtures[0]["european_handicap"],),
        correct_score_top_n=5,
    )
    assert derived_markets["1x2"] == first_snapshot.market_probabilities["1x2"]
    assert f"cn_handicap_1x2:{fixtures[0]['cn_handicap']}" in derived_markets
    assert "correct_score_top_n" in derived_markets

    first_leg = ParlayLegSelection(
        fixture_id=first_snapshot.fixture_id,
        market_type="1x2",
        outcomes=["home_win"],
        probabilities={
            "home_win": first_snapshot.p_home,
            "draw": first_snapshot.p_draw,
            "away_win": first_snapshot.p_away,
        },
        odds={"home_win": 2.4, "draw": 3.2, "away_win": 3.0},
        data_quality_score=fixtures[0]["data_quality_score"],
    )
    second_leg = ParlayLegSelection(
        fixture_id=second_snapshot.fixture_id,
        market_type="1x2",
        outcomes=["draw", "away_win"],
        probabilities={
            "home_win": second_snapshot.p_home,
            "draw": second_snapshot.p_draw,
            "away_win": second_snapshot.p_away,
        },
        odds={"home_win": 1.9, "draw": 3.5, "away_win": 4.1},
        data_quality_score=fixtures[1]["data_quality_score"],
    )
    parlay = evaluate_parlay(
        [first_leg, second_leg],
        pass_type="2x1",
        unit_stake=2,
        max_budget=10,
        correlation_penalty=0.05,
    )

    assert parlay.rule_valid is True
    assert parlay.is_multiple is True
    assert parlay.total_atomic_bets == 2
    assert parlay.total_stake == 4
    assert parlay.expected_payout > 0
    assert parlay.explanation_json["calculation_basis"] == "independent_fixture_approximation"
    assert parlay.explanation_json["budget"] == {
        "max_budget": 10.0,
        "total_stake": 4.0,
        "within_budget": True,
    }

    repository = InMemoryAccuracyWriteRepository()
    persisted = evaluate_and_persist_post_match_result(
        snapshot=first_snapshot,
        actual_result=ActualMatchResult(
            fixture_id=first_snapshot.fixture_id,
            home_goals=1,
            away_goals=1,
        ),
        repository=repository,
        prediction_snapshot_id="phase9-snapshot-1",
        competition_id=fixtures[0]["competition_id"],
    )

    assert persisted.stored_evaluation.evaluation.fixture_id == fixtures[0]["fixture_id"]
    assert persisted.stored_evaluation.evaluation.log_loss_1x2 >= 0
    assert persisted.stored_evaluation.evaluation.brier_score_1x2 >= 0
    assert len(persisted.calibration_buckets) == 3
    assert {bucket.key.outcome for bucket in persisted.calibration_buckets} == {
        "home_win",
        "draw",
        "away_win",
    }


def test_phase9_api_flow_exposes_mvp_acceptance_markers() -> None:
    fixtures_response = client.get("/api/v1/fixtures")
    assert fixtures_response.status_code == 200
    fixtures_payload = fixtures_response.json()
    assert len(fixtures_payload["items"]) >= 3

    first_item = fixtures_payload["items"][0]
    prediction = first_item["prediction"]
    assert prediction["model_version"]
    assert prediction["prediction_time_utc"]
    assert prediction["data_quality_score"] >= 0
    assert prediction["p_home"] + prediction["p_draw"] + prediction["p_away"] == pytest.approx(1)

    fixture_id = first_item["fixture_id"]
    prediction_response = client.get(f"/api/v1/fixtures/{fixture_id}/prediction")
    assert prediction_response.status_code == 200
    prediction_payload = prediction_response.json()
    assert prediction_payload["score_top_n"]
    assert "1x2" in prediction_payload["odds_comparison"]
    assert "asian_handicap" in prediction_payload["odds_comparison"]
    assert prediction_payload["model_metadata"]["model_version"] == prediction["model_version"]

    score_grid_response = client.get(f"/api/v1/fixtures/{fixture_id}/score-grid")
    assert score_grid_response.status_code == 200
    score_grid_payload = score_grid_response.json()
    assert sum(sum(row) for row in score_grid_payload["grid"]) == pytest.approx(1)

    parlay_response = client.post(
        "/api/v1/parlays/recommend",
        json={
            "date": "2026-05-06",
            "pass_types": ["2x1", "4x1"],
            "strategy": "balanced",
            "unit_stake": 2,
            "max_budget": 20,
            "allow_multiple_outcomes_per_fixture": True,
            "allowed_markets": ["1x2", "cn_handicap_1x2"],
            "exclude_beta_competitions": False,
        },
    )
    assert parlay_response.status_code == 200
    parlay_items = parlay_response.json()["items"]
    assert parlay_items
    assert parlay_items[0]["atomic_bet_count"] >= 1
    assert parlay_items[0]["total_stake"] >= parlay_items[0]["unit_stake"]
    assert parlay_items[0]["expected_payout"] >= 0
    assert "roi" in parlay_items[0]
    assert parlay_items[0]["explanation_json"]["calculation_basis"]

    accuracy_response = client.get(
        "/api/v1/accuracy/summary?model_version=active&competition_id=all&market=all&window=90d"
    )
    assert accuracy_response.status_code == 200
    accuracy_payload = accuracy_response.json()
    assert accuracy_payload["sample_size"] > 0
    assert accuracy_payload["log_loss"] is not None
    assert accuracy_payload["brier_score"] is not None
    assert accuracy_payload["calibration_buckets"]
    assert accuracy_payload["model_comparisons"]
