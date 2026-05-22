from __future__ import annotations

from math import log

from nutmeg.accuracy.evaluator import evaluate_prediction_snapshot
from nutmeg.accuracy.model_comparison import compare_model_versions_stub
from nutmeg.accuracy.summary import AccuracyEvaluationEvent, CalibrationObservation
from nutmeg.domain.accuracy import ActualMatchResult, ModelComparisonStub, ModelVersionMetrics
from nutmeg.domain.prediction import MarketProbabilityValue, PredictionSnapshot
from nutmeg.market_resolver.settlement import settle_asian_handicap, settle_cn_handicap_1x2
from nutmeg.providers.mock import MockFixture, list_mock_fixtures

ACTIVE_MODEL_VERSION = "poisson-m1.0.0"

_ACTUAL_RESULTS: dict[str, ActualMatchResult] = {
    "fix_epl_001": ActualMatchResult(
        fixture_id="fix_epl_001",
        home_goals=1,
        away_goals=1,
    ),
    "fix_epl_002": ActualMatchResult(
        fixture_id="fix_epl_002",
        home_goals=2,
        away_goals=1,
    ),
    "fix_j1_001": ActualMatchResult(
        fixture_id="fix_j1_001",
        home_goals=1,
        away_goals=2,
    ),
}


def list_mock_actual_results() -> dict[str, ActualMatchResult]:
    return dict(_ACTUAL_RESULTS)


def get_mock_actual_result(fixture_id: str) -> ActualMatchResult | None:
    return _ACTUAL_RESULTS.get(fixture_id)


class MockAccuracyEventRepository:
    def __init__(self, snapshots: dict[str, PredictionSnapshot]) -> None:
        self.snapshots = snapshots

    def list_evaluation_events(self) -> list[AccuracyEvaluationEvent]:
        events: list[AccuracyEvaluationEvent] = []
        for fixture in list_mock_fixtures():
            snapshot = self.snapshots.get(fixture["fixture_id"])
            actual_result = _ACTUAL_RESULTS.get(fixture["fixture_id"])
            if snapshot is None or actual_result is None:
                continue
            events.extend(_events_for_fixture(fixture, snapshot, actual_result))
        return events

    def list_model_comparisons(
        self,
        events: list[AccuracyEvaluationEvent],
    ) -> list[ModelComparisonStub]:
        if not events:
            return []
        baseline_ece = _mean(
            [
                abs(
                    observation.predicted_probability
                    - (1.0 if observation.actual_occurred else 0.0)
                )
                for event in events
                for observation in event.calibration_observations
            ]
        )
        baseline = ModelVersionMetrics(
            model_version=ACTIVE_MODEL_VERSION,
            sample_size=len(events),
            log_loss=_mean([event.log_loss for event in events]),
            brier_score=_mean([event.brier_score for event in events]),
            ece=baseline_ece,
        )
        candidate = ModelVersionMetrics(
            model_version="dc-v1.5-candidate",
            sample_size=len(events),
            log_loss=baseline.log_loss * 0.988,
            brier_score=baseline.brier_score * 0.986,
            ece=(baseline_ece * 0.92) if baseline_ece is not None else None,
        )
        return [
            compare_model_versions_stub(
                candidate_metrics=candidate,
                baseline_metrics=baseline,
            )
        ]


def _events_for_fixture(
    fixture: MockFixture,
    snapshot: PredictionSnapshot,
    actual_result: ActualMatchResult,
) -> list[AccuracyEvaluationEvent]:
    evaluation = evaluate_prediction_snapshot(snapshot, actual_result)
    one_x_two_probabilities = _probability_map(snapshot.market_probabilities["1x2"])
    events = [
        AccuracyEvaluationEvent(
            fixture_id=fixture["fixture_id"],
            competition_id=fixture["competition_id"],
            competition_name=fixture["competition"],
            market_type="1x2",
            model_version=snapshot.model_version,
            prediction_time_utc=snapshot.prediction_time_utc,
            log_loss=evaluation.log_loss_1x2,
            brier_score=evaluation.brier_score_1x2,
            calibration_observations=_observations(
                market_type="1x2",
                probabilities=one_x_two_probabilities,
                actual_outcome=evaluation.actual_result_1x2.value,
                competition_id=fixture["competition_id"],
            ),
            error_tags=tuple(evaluation.error_tags),
        )
    ]

    cn_key = f"cn_handicap_1x2:{fixture['cn_handicap']}"
    cn_probabilities = _probability_map(snapshot.market_probabilities[cn_key])
    cn_actual = settle_cn_handicap_1x2(
        actual_result.home_goals,
        actual_result.away_goals,
        handicap=fixture["cn_handicap"],
    ).value
    events.append(
        _market_event(
            fixture,
            snapshot,
            market_type="cn_handicap_1x2",
            probabilities=cn_probabilities,
            actual_outcome=cn_actual,
        )
    )

    asian_key = f"asian_handicap:home:{fixture['asian_handicap_line']:g}"
    asian_probabilities = {
        key: value
        for key, value in _probability_map(snapshot.market_probabilities[asian_key]).items()
        if key != "expected_return"
    }
    asian_actual = settle_asian_handicap(
        actual_result.home_goals,
        actual_result.away_goals,
        line=fixture["asian_handicap_line"],
        side="home",
    ).value
    events.append(
        _market_event(
            fixture,
            snapshot,
            market_type="asian_handicap",
            probabilities=asian_probabilities,
            actual_outcome=asian_actual,
        )
    )
    return events


def _market_event(
    fixture: MockFixture,
    snapshot: PredictionSnapshot,
    *,
    market_type: str,
    probabilities: dict[str, float],
    actual_outcome: str,
) -> AccuracyEvaluationEvent:
    predicted_outcome = max(probabilities, key=lambda outcome: probabilities[outcome])
    error_tags = ("handicap_miss",) if predicted_outcome != actual_outcome else ()
    return AccuracyEvaluationEvent(
        fixture_id=fixture["fixture_id"],
        competition_id=fixture["competition_id"],
        competition_name=fixture["competition"],
        market_type=market_type,
        model_version=snapshot.model_version,
        prediction_time_utc=snapshot.prediction_time_utc,
        log_loss=_log_loss(probabilities[actual_outcome]),
        brier_score=_brier_score(probabilities, actual_outcome),
        calibration_observations=_observations(
            market_type=market_type,
            probabilities=probabilities,
            actual_outcome=actual_outcome,
            competition_id=fixture["competition_id"],
        ),
        error_tags=error_tags,
    )


def _observations(
    *,
    market_type: str,
    probabilities: dict[str, float],
    actual_outcome: str,
    competition_id: str,
) -> tuple[CalibrationObservation, ...]:
    return tuple(
        CalibrationObservation(
            market_type=market_type,
            outcome=outcome,
            predicted_probability=probability,
            actual_occurred=outcome == actual_outcome,
            competition_id=competition_id,
        )
        for outcome, probability in probabilities.items()
    )


def _probability_map(value: MarketProbabilityValue) -> dict[str, float]:
    if not isinstance(value, dict):
        raise TypeError("expected market probability map")
    return {str(key): float(probability) for key, probability in value.items()}


def _brier_score(probabilities: dict[str, float], actual_outcome: str) -> float:
    return sum(
        (probability - (1.0 if outcome == actual_outcome else 0.0)) ** 2
        for outcome, probability in probabilities.items()
    )


def _log_loss(probability: float, *, epsilon: float = 1e-15) -> float:
    bounded_probability = max(epsilon, min(1.0 - epsilon, probability))
    return -log(bounded_probability)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
