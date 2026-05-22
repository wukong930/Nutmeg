from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.recommendations import (
    RecommendationCandidate,
    aggregate_upset_quality,
    analyze_candidate_upset_signal,
    assess_upset_signal_calibration,
    build_upset_focus_policy_config,
    build_upset_policy_payload,
    rank_candidates,
    score_candidate,
)


def test_upset_signal_splits_fragile_favorite_from_protection_direction() -> None:
    fragile_favorite = _candidate(
        "A",
        "home_win",
        probability=0.70,
        decimal_odds=1.48,
        upset_protection_score=0.88,
        odds_stability_score=0.45,
        volatility_penalty=0.18,
        metadata_json={"favorite_fragility_score": 0.88, "upset_score": 0.76},
    )
    draw_protection = _candidate(
        "A",
        "draw",
        probability=0.29,
        decimal_odds=3.70,
        upset_protection_score=0.72,
        odds_stability_score=0.45,
        volatility_penalty=0.18,
        metadata_json={"target_outcome": "draw", "upset_score": 0.72},
    )

    favorite_signal = analyze_candidate_upset_signal(fragile_favorite)
    draw_signal = analyze_candidate_upset_signal(draw_protection)

    assert favorite_signal.direction == "favorite_fragility_avoidance"
    assert favorite_signal.avoidance_penalty > 0.50
    assert favorite_signal.protection_score < 0.10
    assert draw_signal.direction == "draw_overlooked"
    assert draw_signal.protection_score > 0.60
    assert draw_signal.avoidance_penalty == 0.0


def test_accuracy_policy_avoids_fragile_favorite_despite_high_raw_probability() -> None:
    fragile_favorite = _candidate(
        "A",
        "home_win",
        probability=0.70,
        decimal_odds=1.48,
        upset_protection_score=0.88,
        odds_stability_score=0.45,
        volatility_penalty=0.18,
        metadata_json={"favorite_fragility_score": 0.88, "upset_score": 0.76},
    )
    steadier_pick = _candidate(
        "B",
        "home_win",
        probability=0.64,
        decimal_odds=1.75,
        odds_stability_score=0.75,
        volatility_penalty=0.02,
    )

    ranked = rank_candidates([fragile_favorite, steadier_pick])

    assert ranked[0].candidate.fixture_id == "B"
    assert ranked[1].component_scores["upset_avoidance_penalty"] > 0.50
    assert "upset_avoidance_penalty_applied" in ranked[1].reason_codes


def test_upset_focus_policy_prefers_protection_direction_not_fragile_favorite() -> None:
    fragile_favorite = _candidate(
        "A",
        "home_win",
        probability=0.70,
        decimal_odds=1.48,
        upset_protection_score=0.88,
        odds_stability_score=0.45,
        volatility_penalty=0.18,
        metadata_json={"favorite_fragility_score": 0.88, "upset_score": 0.76},
    )
    draw_protection = _candidate(
        "A",
        "draw",
        probability=0.29,
        decimal_odds=3.70,
        upset_protection_score=0.72,
        odds_stability_score=0.45,
        volatility_penalty=0.18,
        metadata_json={"target_outcome": "draw", "upset_score": 0.72},
    )
    steady_pick = _candidate("B", "home_win", probability=0.64, decimal_odds=1.75)

    ranked = rank_candidates(
        [fragile_favorite, draw_protection, steady_pick],
        config=build_upset_focus_policy_config(
            strategy="upset_protection",
            allowed_markets=("1x2",),
            min_probability=0.10,
            min_model_edge=None,
            min_data_quality_score=50.0,
            require_odds=True,
        ),
    )

    assert ranked[0].candidate.outcome == "draw"
    assert ranked[-1].candidate.fixture_id == "A"
    assert ranked[-1].candidate.outcome == "home_win"


def test_upset_quality_payload_rewards_protection_and_penalizes_fragility() -> None:
    fragile_favorite = _candidate(
        "A",
        "home_win",
        probability=0.70,
        decimal_odds=1.48,
        upset_protection_score=0.88,
        metadata_json={"favorite_fragility_score": 0.88},
    )
    draw_protection = _candidate(
        "A",
        "draw",
        probability=0.29,
        decimal_odds=3.70,
        upset_protection_score=0.72,
        metadata_json={"target_outcome": "draw", "upset_score": 0.72},
    )

    fragile_quality = aggregate_upset_quality([fragile_favorite])
    protected_quality = aggregate_upset_quality([draw_protection])
    payload = build_upset_policy_payload([draw_protection])

    assert protected_quality > fragile_quality
    assert payload["calculation_basis"] == "recommendation_upset_policy_v3_1"
    assert payload["directions"] == ["draw_overlooked"]


def test_accuracy_policy_marks_uncalibrated_longshot_upset_risk() -> None:
    longshot = _candidate(
        "A",
        "away_win",
        probability=0.16,
        decimal_odds=7.0,
        upset_protection_score=0.90,
        odds_stability_score=0.42,
        volatility_penalty=0.25,
        calibration_score=0.75,
        metadata_json={"target_outcome": "away_win", "upset_score": 0.90},
    )

    scored = score_candidate(longshot)

    assert scored.component_scores["calibration_risk"] > 0.25
    assert scored.component_scores["longshot_upset_risk"] > 0.35
    assert "calibration_risk_penalty_applied" in scored.reason_codes
    assert "longshot_upset_penalty_applied" in scored.reason_codes


def test_accuracy_policy_allows_calibrated_upset_exposure() -> None:
    calibrated = _candidate(
        "A",
        "away_win",
        probability=0.26,
        decimal_odds=4.60,
        upset_protection_score=0.82,
        odds_stability_score=0.78,
        volatility_penalty=0.04,
        calibration_score=0.91,
        data_quality_score=94.0,
        model_confidence_score=0.90,
        metadata_json={"target_outcome": "away_win", "upset_score": 0.82},
    )

    scored = score_candidate(calibrated)

    assert scored.component_scores["calibrated_upset_exposure"] > 0.45
    assert scored.component_scores["longshot_upset_risk"] < 0.16
    assert "calibrated_upset_exposure_allowed" in scored.reason_codes


def test_upset_signal_calibration_penalizes_observed_probability_gap() -> None:
    risky_profile = _candidate(
        "A",
        "draw",
        probability=0.24,
        decimal_odds=3.80,
        market_probability=0.27,
        upset_protection_score=0.82,
        odds_stability_score=0.74,
        volatility_penalty=0.05,
        calibration_score=0.88,
        metadata_json={
            "target_outcome": "draw",
            "upset_score": 0.82,
            "historical_upset_signal_profile_key": "profile:epl:near_miss",
            "historical_upset_signal_observation_count": 3,
            "historical_upset_signal_average_hit_probability_delta": -0.27,
            "historical_upset_signal_average_brier_score_delta": 0.35,
            "historical_upset_signal_average_log_loss_delta": 0.80,
            "historical_upset_signal_average_calibration_error_delta": 0.27,
        },
    )

    calibration = assess_upset_signal_calibration(risky_profile)
    scored = score_candidate(risky_profile)

    assert calibration.observed_profile is True
    assert calibration.hit_probability_deficit == 0.27
    assert calibration.risk_score > 0.60
    assert calibration.reliability_score < 0.40
    assert scored.component_scores["upset_signal_calibration_risk"] == pytest.approx(
        calibration.risk_score
    )
    assert "upset_signal_calibration_penalty_applied" in scored.reason_codes
    assert "upset_signal_calibration:hit_probability_deficit" in scored.reason_codes


def test_upset_signal_calibration_keeps_reliable_profile_available() -> None:
    reliable_profile = _candidate(
        "A",
        "draw",
        probability=0.31,
        decimal_odds=3.30,
        market_probability=0.30,
        upset_protection_score=0.70,
        calibration_score=0.92,
        metadata_json={
            "target_outcome": "draw",
            "upset_score": 0.70,
            "upset_signal_calibration": {
                "profile_key": "profile:epl:reliable_draw",
                "observation_count": 5,
                "average_hit_probability_delta": 0.01,
                "average_brier_score_delta": -0.02,
                "average_log_loss_delta": -0.04,
                "average_calibration_error_delta": -0.01,
            },
        },
    )

    calibration = assess_upset_signal_calibration(reliable_profile)
    scored = score_candidate(reliable_profile)

    assert calibration.observed_profile is True
    assert calibration.risk_score < 0.10
    assert calibration.reliability_score > 0.90
    assert scored.component_scores["upset_signal_reliability"] > 0.90
    assert "upset_signal_calibration_penalty_applied" not in scored.reason_codes


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float,
    market_probability: float | None = None,
    upset_protection_score: float = 0.0,
    odds_stability_score: float = 0.75,
    volatility_penalty: float = 0.02,
    calibration_score: float = 0.86,
    data_quality_score: float = 90.0,
    model_confidence_score: float = 0.88,
    metadata_json: dict[str, object] | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=(
            market_probability if market_probability is not None else 1.0 / decimal_odds
        ),
        data_quality_score=data_quality_score,
        model_confidence_score=model_confidence_score,
        calibration_score=calibration_score,
        upset_protection_score=upset_protection_score,
        odds_stability_score=odds_stability_score,
        volatility_penalty=volatility_penalty,
        model_version="poisson-v3.1-baseline",
        prediction_snapshot_id=101,
        prediction_time_utc=datetime(2026, 5, 1, 12, tzinfo=UTC),
        kickoff_time_utc=datetime(2026, 5, 2, 12, tzinfo=UTC),
        metadata_json=metadata_json or {},
    )
