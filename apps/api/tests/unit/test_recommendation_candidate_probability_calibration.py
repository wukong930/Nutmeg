from __future__ import annotations

import pytest

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
    apply_candidate_probability_calibration_profile,
)
from nutmeg.recommendations.models import RecommendationCandidate
from nutmeg.recommendations.policy import rank_candidates, select_best_single_parlay


def test_candidate_probability_calibration_reweights_complete_1x2_group() -> None:
    candidates = [
        _candidate(
            "eng_a",
            "home_win",
            probability=0.64,
            decimal_odds=1.75,
            competition_id="ENG_CHAMPIONSHIP",
        ),
        _candidate(
            "eng_a",
            "draw",
            probability=0.22,
            decimal_odds=3.50,
            competition_id="ENG_CHAMPIONSHIP",
        ),
        _candidate(
            "eng_a",
            "away_win",
            probability=0.14,
            decimal_odds=4.80,
            competition_id="ENG_CHAMPIONSHIP",
        ),
        _candidate("epl_b", "home_win", probability=0.60, decimal_odds=1.82),
        _candidate("epl_b", "draw", probability=0.24, decimal_odds=3.40),
        _candidate("epl_b", "away_win", probability=0.16, decimal_odds=4.50),
    ]
    profile = CandidateProbabilityCalibrationProfile(
        profile_key="eng-championship-home-downshift-v1",
        source_report_key="historical_probability_calibration_profile_grid:test",
        target_competition_ids=("ENG_CHAMPIONSHIP",),
        target_outcomes=("home_win",),
        buckets=[
            CandidateProbabilityCalibrationBucket(
                competition_id="ENG_CHAMPIONSHIP",
                outcome="home_win",
                bucket_start=0.60,
                bucket_end=0.70,
                calibrated_probability=0.48,
                sample_size=80,
            )
        ],
    )

    result = apply_candidate_probability_calibration_profile(candidates, profile=profile)

    assert result.status == "applied"
    assert result.adjusted_candidate_count == 3
    assert result.adjusted_fixture_count == 1
    adjusted_eng = [
        candidate for candidate in result.candidates if candidate.fixture_id == "eng_a"
    ]
    assert sum(candidate.probability for candidate in adjusted_eng) == pytest.approx(1.0)
    eng_home = next(
        candidate for candidate in adjusted_eng if candidate.outcome == "home_win"
    )
    assert eng_home.model_probability == 0.64
    assert eng_home.calibrated_probability == pytest.approx(0.5714285714)
    assert eng_home.probability_source == "calibrated"
    assert eng_home.effective_model_edge() == pytest.approx(
        eng_home.probability - eng_home.effective_market_probability()
    )
    assert eng_home.metadata_json["calibration_directly_adjusted"] is True

    ranked = rank_candidates(result.candidates)
    scored_eng_home = next(
        item
        for item in ranked
        if item.candidate.fixture_id == "eng_a"
        and item.candidate.outcome == "home_win"
    )
    assert ranked[0].candidate.fixture_id == "epl_b"
    selection = select_best_single_parlay(
        result.candidates,
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=10.0,
    )
    assert selection.fixture_ids == ["epl_b", "eng_a"]
    assert selection.evaluation.hit_probability == pytest.approx(
        0.60 * eng_home.probability
    )
    assert "calibrated_probability_component" in scored_eng_home.reason_codes


def test_candidate_probability_calibration_shadow_mode_preserves_effective_probability() -> None:
    candidates = [
        _candidate("fix_a", "home_win", probability=0.62, decimal_odds=1.70),
        _candidate("fix_a", "draw", probability=0.23, decimal_odds=3.30),
        _candidate("fix_a", "away_win", probability=0.15, decimal_odds=4.60),
    ]
    profile = CandidateProbabilityCalibrationProfile(
        profile_key="shadow-calibration-v1",
        mode="shadow",
        target_outcomes=("home_win",),
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="home_win",
                bucket_start=0.60,
                bucket_end=0.70,
                calibrated_probability=0.52,
                sample_size=40,
            )
        ],
    )

    result = apply_candidate_probability_calibration_profile(candidates, profile=profile)
    home = next(candidate for candidate in result.candidates if candidate.outcome == "home_win")

    assert home.probability == 0.62
    assert home.effective_probability() == 0.62
    assert home.calibrated_probability is not None
    assert home.probability_source == "model"
    assert home.metadata_json["candidate_probability_calibration_mode"] == "shadow"


def test_candidate_probability_calibration_can_match_market_odds_band() -> None:
    candidates = [
        _candidate("fix_a", "home_win", probability=0.64, decimal_odds=1.75),
        _candidate("fix_a", "draw", probability=0.22, decimal_odds=3.50),
        _candidate("fix_a", "away_win", probability=0.14, decimal_odds=4.80),
    ]
    profile = CandidateProbabilityCalibrationProfile(
        profile_key="market-odds-band-calibration-v1",
        segment_mode="market_odds_band",
        target_outcomes=("home_win",),
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="home_win",
                segment_mode="market_odds_band",
                bucket_start=0.55,
                bucket_end=0.60,
                calibrated_probability=0.52,
                sample_size=40,
            )
        ],
    )

    result = apply_candidate_probability_calibration_profile(candidates, profile=profile)
    home = next(candidate for candidate in result.candidates if candidate.outcome == "home_win")

    assert result.status == "applied"
    assert result.summary_json["segment_mode"] == "market_odds_band"
    assert home.model_probability == 0.64
    assert home.calibrated_probability is not None
    assert home.metadata_json["calibration_directly_adjusted"] is True


def test_candidate_probability_calibration_respects_competition_season_guard() -> None:
    candidates = [
        _candidate(
            "eng_old",
            "home_win",
            probability=0.45,
            decimal_odds=2.10,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2020-2021",
            competition_season_index=1,
        ),
        _candidate(
            "eng_old",
            "draw",
            probability=0.30,
            decimal_odds=3.20,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2020-2021",
            competition_season_index=1,
        ),
        _candidate(
            "eng_old",
            "away_win",
            probability=0.25,
            decimal_odds=3.80,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2020-2021",
            competition_season_index=1,
        ),
        _candidate(
            "eng_new",
            "home_win",
            probability=0.45,
            decimal_odds=2.10,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2022-2023",
            competition_season_index=3,
        ),
        _candidate(
            "eng_new",
            "draw",
            probability=0.30,
            decimal_odds=3.20,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2022-2023",
            competition_season_index=3,
        ),
        _candidate(
            "eng_new",
            "away_win",
            probability=0.25,
            decimal_odds=3.80,
            competition_id="ENG_CHAMPIONSHIP",
            season_id="2022-2023",
            competition_season_index=3,
        ),
    ]
    profile = CandidateProbabilityCalibrationProfile(
        profile_key="eng-championship-season-guard-v1",
        segment_mode="market_odds_band",
        target_competition_ids=("ENG_CHAMPIONSHIP",),
        target_outcomes=("draw",),
        min_decimal_odds=2.25,
        max_decimal_odds=3.45,
        min_competition_season_index_by_competition_id={"ENG_CHAMPIONSHIP": 3},
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.35,
                calibrated_probability=0.45,
                sample_size=20,
                market_type="1x2",
            )
        ],
    )

    result = apply_candidate_probability_calibration_profile(candidates, profile=profile)

    assert result.status == "applied"
    assert result.adjusted_fixture_count == 1
    assert result.adjusted_candidate_count == 3
    old_draw = next(
        candidate
        for candidate in result.candidates
        if candidate.fixture_id == "eng_old" and candidate.outcome == "draw"
    )
    new_draw = next(
        candidate
        for candidate in result.candidates
        if candidate.fixture_id == "eng_new" and candidate.outcome == "draw"
    )
    assert "candidate_probability_calibration_profile_key" not in old_draw.metadata_json
    assert new_draw.metadata_json["candidate_probability_calibration_profile_key"] == (
        "eng-championship-season-guard-v1"
    )


def test_candidate_probability_calibration_skips_incomplete_1x2_group() -> None:
    candidates = [
        _candidate("fix_a", "home_win", probability=0.62, decimal_odds=1.70),
        _candidate("fix_a", "draw", probability=0.23, decimal_odds=3.30),
    ]
    profile = CandidateProbabilityCalibrationProfile(
        profile_key="incomplete-group-v1",
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="home_win",
                bucket_start=0.60,
                bucket_end=0.70,
                calibrated_probability=0.52,
                sample_size=40,
            )
        ],
    )

    result = apply_candidate_probability_calibration_profile(candidates, profile=profile)

    assert result.status == "not_applicable"
    assert result.adjusted_candidate_count == 0
    assert result.skipped_group_count == 1
    assert result.candidates == candidates


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float,
    competition_id: str = "EPL",
    season_id: str | None = None,
    competition_season_index: int | None = None,
) -> RecommendationCandidate:
    metadata_json: dict[str, object] = {"competition_id": competition_id}
    if season_id is not None:
        metadata_json["season_id"] = season_id
    if competition_season_index is not None:
        metadata_json["competition_season_index"] = competition_season_index
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        data_quality_score=90,
        model_confidence_score=0.90,
        calibration_score=0.90,
        odds_stability_score=0.92,
        volatility_penalty=0.02,
        metadata_json=metadata_json,
    )
