from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations import (
    CompetitionFinalAnswerValueGuard,
    CompetitionRecommendationProfile,
    RecommendationCandidate,
    RecommendationGlobalPlanOption,
    RecommendationSelection,
    ScoredRecommendationCandidate,
    build_final_answer_arbitration_payload,
    rank_final_answer_options,
    score_final_answer_option,
)
from nutmeg.recommendations.global_planner import RecommendationPlanOptionType
from nutmeg.recommendations.models import RecommendationMarketType, RecommendationMode


def test_final_answer_arbitrator_prefers_positive_ev_parlay_over_negative_ev_single() -> None:
    negative_value_single = _option(
        option_key="standalone_single:1x1:single",
        option_type="standalone_single",
        pass_type="1x1",
        fixture_ids=("A",),
        planner_score=0.68,
        hit_probability=0.82,
        roi=-0.75,
        risk_score=0.18,
        data_quality=92.0,
    )
    positive_value_parlay = _option(
        option_key="single_parlay:2x1:single",
        option_type="single_parlay",
        pass_type="2x1",
        fixture_ids=("B", "C"),
        planner_score=0.66,
        hit_probability=0.44,
        roi=0.95,
        risk_score=0.55,
        data_quality=88.0,
    )

    ranked = rank_final_answer_options([negative_value_single, positive_value_parlay])
    payload = build_final_answer_arbitration_payload(
        ranked[0],
        rank=1,
        candidate_count=2,
    )

    assert ranked[0].option_key == "single_parlay:2x1:single"
    assert payload["calculation_basis"] == "final_answer_arbitrator_v3_1"
    assert payload["answer_type"] == "single_parlay"
    reason_codes = cast(list[str], payload["reason_codes"])
    assert "positive_expected_value" in reason_codes
    assert "strategy" not in str(payload)


def test_final_answer_arbitrator_sends_invalid_or_over_budget_options_last() -> None:
    valid_option = _option(
        option_key="single_parlay:2x1:single",
        option_type="single_parlay",
        pass_type="2x1",
        fixture_ids=("A", "B"),
        planner_score=0.50,
        hit_probability=0.40,
        roi=0.20,
        risk_score=0.45,
        data_quality=80.0,
    )
    over_budget_option = _option(
        option_key="multiple_parlay:6x1:multiple",
        option_type="multiple_parlay",
        pass_type="6x1",
        mode="multiple",
        fixture_ids=("C", "D", "E", "F", "G", "H"),
        planner_score=0.99,
        hit_probability=0.70,
        roi=1.80,
        risk_score=0.30,
        data_quality=95.0,
        within_budget=False,
    )

    ranked = rank_final_answer_options([over_budget_option, valid_option])
    score = score_final_answer_option(over_budget_option)

    assert ranked[0].option_key == "single_parlay:2x1:single"
    assert ranked[-1].option_key == "multiple_parlay:6x1:multiple"
    assert score.final_answer_score == 0.0


def test_final_answer_arbitrator_prefers_stake_disciplined_single_when_ev_is_negative() -> None:
    single = _option(
        option_key="single_parlay:2x1:single",
        option_type="single_parlay",
        pass_type="2x1",
        fixture_ids=("A", "B"),
        planner_score=0.61,
        hit_probability=0.49,
        roi=-0.12,
        risk_score=0.51,
        data_quality=82.0,
        total_stake=2.0,
    )
    expensive_cover = _option(
        option_key="multiple_parlay:2x1:multiple",
        option_type="multiple_parlay",
        pass_type="2x1",
        mode="multiple",
        fixture_ids=("A", "C"),
        planner_score=0.54,
        hit_probability=0.79,
        roi=-0.12,
        risk_score=0.32,
        data_quality=82.0,
        total_stake=8.0,
        upset_protection_score=0.65,
    )

    ranked = rank_final_answer_options([expensive_cover, single])
    expensive_score = score_final_answer_option(expensive_cover)

    assert ranked[0].option_key == "single_parlay:2x1:single"
    assert expensive_score.score_components["stake_discipline"] < 0.30


def test_final_answer_arbitrator_applies_competition_profile_adjustment() -> None:
    two_leg = _option(
        option_key="single_parlay:2x1:single",
        option_type="single_parlay",
        pass_type="2x1",
        fixture_ids=("A", "B"),
        planner_score=0.64,
        hit_probability=0.70,
        roi=-0.10,
        risk_score=0.30,
        data_quality=82.0,
        competition_id="TEST_LEAGUE",
    )
    three_leg = _option(
        option_key="single_parlay:3x1:single",
        option_type="single_parlay",
        pass_type="3x1",
        fixture_ids=("C", "D", "E"),
        planner_score=0.61,
        hit_probability=0.58,
        roi=-0.12,
        risk_score=0.42,
        data_quality=82.0,
        competition_id="TEST_LEAGUE",
    )
    profiles = [
        CompetitionRecommendationProfile(
            competition_id="TEST_LEAGUE",
            final_answer_score_adjustments={"3x1:single": 0.12},
        )
    ]

    ranked = rank_final_answer_options(
        [two_leg, three_leg],
        competition_profiles=profiles,
    )
    score = score_final_answer_option(
        three_leg,
        competition_profiles=profiles,
    )

    assert ranked[0].option_key == "single_parlay:3x1:single"
    assert score.score_components["competition_profile_adjustment"] == 0.12
    assert "competition_profile_adjustment_applied" in score.reason_codes


def test_final_answer_arbitrator_applies_competition_value_guard_penalty() -> None:
    safe_option = _option(
        option_key="single_parlay:2x1:single",
        option_type="single_parlay",
        pass_type="2x1",
        fixture_ids=("A", "B"),
        planner_score=0.68,
        hit_probability=0.72,
        roi=0.04,
        risk_score=0.28,
        data_quality=84.0,
        competition_id="TEST_LEAGUE",
        decimal_odds=1.70,
        model_edge=0.03,
    )
    exposed_option = _option(
        option_key="single_parlay:3x1:single",
        option_type="single_parlay",
        pass_type="3x1",
        fixture_ids=("C", "D", "E"),
        planner_score=0.78,
        hit_probability=0.70,
        roi=0.12,
        risk_score=0.32,
        data_quality=84.0,
        competition_id="TEST_LEAGUE",
        decimal_odds=2.40,
        model_edge=-0.04,
    )
    profiles = [
        CompetitionRecommendationProfile(
            competition_id="TEST_LEAGUE",
            final_answer_value_guards=[
                CompetitionFinalAnswerValueGuard(
                    penalty_strength=0.18,
                    probability_min=0.0,
                    probability_max=0.80,
                    min_decimal_odds=2.0,
                    max_decimal_odds=10.0,
                    max_model_edge=-0.02,
                )
            ],
        )
    ]

    ranked = rank_final_answer_options(
        [safe_option, exposed_option],
        competition_profiles=profiles,
    )
    score = score_final_answer_option(
        exposed_option,
        competition_profiles=profiles,
    )

    assert ranked[0].option_key == "single_parlay:2x1:single"
    assert abs(score.score_components["competition_value_guard_penalty"] - 0.18) < 1e-12
    assert "competition_value_guard_applied" in score.reason_codes


def test_final_answer_arbitrator_penalizes_heavily_trimmed_budget_multiple() -> None:
    stable_single = _option(
        option_key="single_parlay:3x1:single",
        option_type="single_parlay",
        pass_type="3x1",
        fixture_ids=("A", "B", "C"),
        planner_score=0.66,
        hit_probability=0.50,
        roi=0.08,
        risk_score=0.50,
        data_quality=88.0,
    )
    trimmed_multiple = _option(
        option_key="multiple_parlay:3x1:multiple",
        option_type="multiple_parlay",
        pass_type="3x1",
        mode="multiple",
        fixture_ids=("D", "E", "F"),
        planner_score=0.66,
        hit_probability=0.53,
        roi=0.08,
        risk_score=0.47,
        data_quality=88.0,
        budget_adjustment={
            "original_total_atomic_bets": 16,
            "optimized_total_atomic_bets": 2,
            "original_quality_score": 0.82,
            "optimized_quality_score": 0.33,
            "quality_score_delta": -0.49,
            "warning_codes": [],
        },
    )

    ranked = rank_final_answer_options([trimmed_multiple, stable_single])
    score = score_final_answer_option(trimmed_multiple)

    assert ranked[0].option_key == "single_parlay:3x1:single"
    assert 0.0 < score.score_components["budget_adjustment_quality"] < 0.50
    assert score.score_components["budget_adjustment_penalty"] > 0.08
    assert "budget_adjustment_applied" in score.reason_codes
    assert "budget_adjustment_quality_penalty_applied" in score.reason_codes


def test_final_answer_arbitrator_treats_within_budget_efficiency_as_binary() -> None:
    tight_budget_multiple = _option(
        option_key="multiple_parlay:2x1:multiple",
        option_type="multiple_parlay",
        pass_type="2x1",
        mode="multiple",
        fixture_ids=("B", "C"),
        planner_score=0.84,
        hit_probability=0.70,
        roi=0.22,
        risk_score=0.25,
        data_quality=88.0,
        max_budget=10.0,
        total_stake=8.0,
    )
    relaxed_budget_multiple = _option(
        option_key="multiple_parlay:2x1:multiple:relaxed",
        option_type="multiple_parlay",
        pass_type="2x1",
        mode="multiple",
        fixture_ids=("B", "C"),
        planner_score=0.84,
        hit_probability=0.70,
        roi=0.22,
        risk_score=0.25,
        data_quality=88.0,
        max_budget=20.0,
        total_stake=8.0,
    )

    tight_score = score_final_answer_option(tight_budget_multiple)
    relaxed_score = score_final_answer_option(relaxed_budget_multiple)

    assert tight_score.score_components["budget_efficiency"] == 1.0
    assert relaxed_score.score_components["budget_efficiency"] == 1.0
    assert "budget_stake_pressure_penalty_applied" not in tight_score.reason_codes


def test_final_answer_arbitrator_applies_tiny_multiple_coverage_tie_breaker() -> None:
    stable_single = _option(
        option_key="standalone_single:1x1:single",
        option_type="standalone_single",
        pass_type="1x1",
        fixture_ids=("A",),
        planner_score=0.635,
        hit_probability=0.56,
        roi=0.04,
        risk_score=0.44,
        data_quality=88.0,
        total_stake=2.0,
    )
    coverage_multiple = _option(
        option_key="multiple_parlay:2x1:multiple",
        option_type="multiple_parlay",
        pass_type="2x1",
        mode="multiple",
        fixture_ids=("B", "C"),
        planner_score=0.635,
        hit_probability=0.67,
        roi=0.04,
        risk_score=0.33,
        data_quality=88.0,
        total_stake=4.0,
        total_atomic_bets=2,
    )

    ranked = rank_final_answer_options([stable_single, coverage_multiple])
    score = score_final_answer_option(coverage_multiple)

    assert ranked[0].option_key == "multiple_parlay:2x1:multiple"
    assert score.score_components["multiple_coverage_adjustment"] == 0.003
    assert "multiple_coverage_tie_breaker_applied" in score.reason_codes


def test_final_answer_arbitrator_records_correct_score_market_without_strategy() -> None:
    option = _option(
        option_key="standalone_single:1x1:single",
        option_type="standalone_single",
        pass_type="1x1",
        fixture_ids=("A",),
        planner_score=0.70,
        hit_probability=0.24,
        roi=1.10,
        risk_score=0.72,
        data_quality=78.0,
        market_type="correct_score",
    )

    payload = build_final_answer_arbitration_payload(
        option,
        rank=1,
        candidate_count=1,
    )

    assert payload["market_types"] == ["correct_score"]
    reason_codes = cast(list[str], payload["reason_codes"])
    assert "includes_correct_score_market" in reason_codes
    assert "strategy" not in str(payload)


def test_final_answer_arbitrator_marks_dynamic_mixed_market_multiple_answer() -> None:
    candidates = [
        _scored_candidate(
            fixture_id="A",
            market_type="1x2",
            probability=0.56,
            data_quality=90.0,
            outcome="home_win",
        ),
        _scored_candidate(
            fixture_id="A",
            market_type="1x2",
            probability=0.25,
            data_quality=90.0,
            outcome="draw",
            decimal_odds=4.20,
        ),
        _scored_candidate(
            fixture_id="B",
            market_type="cn_handicap_1x2",
            probability=0.62,
            data_quality=90.0,
            outcome="handicap_home_win",
        ),
        _scored_candidate(
            fixture_id="C",
            market_type="correct_score",
            probability=0.28,
            data_quality=90.0,
            outcome="1-0",
            decimal_odds=4.60,
        ),
    ]
    evaluation = ParlayEvaluation(
        pass_type="3x1",
        is_multiple=True,
        unit_stake=2.0,
        total_atomic_bets=2,
        total_stake=4.0,
        hit_probability=0.31,
        expected_payout=6.2,
        expected_value=2.2,
        roi=0.55,
        risk_score=0.52,
        risk_level="medium",
        rule_valid=True,
        explanation_json={"budget": {"max_budget": 20.0, "within_budget": True}},
    )
    option = RecommendationGlobalPlanOption(
        option_key="multiple_parlay:3x1:multiple",
        option_type="multiple_parlay",
        pass_type="3x1",
        mode="multiple",
        planner_score=0.68,
        within_budget=True,
        selection=RecommendationSelection(
            pass_type="3x1",
            mode="multiple",
            selected_candidates=candidates,
            evaluation=evaluation,
            total_score=0.68,
            candidate_count=len(candidates),
            excluded_candidate_count=0,
        ),
    )

    payload = build_final_answer_arbitration_payload(
        option,
        rank=1,
        candidate_count=1,
    )

    assert payload["market_types"] == [
        "1x2",
        "cn_handicap_1x2",
        "correct_score",
    ]
    assert payload["market_count"] == 3
    assert payload["dynamic_mixed_market_answer"] is True
    assert payload["multiple_choice_fixture_count"] == 1
    reason_codes = cast(list[str], payload["reason_codes"])
    assert "mixed_market_answer" in reason_codes
    assert "includes_multiple_choice_leg" in reason_codes
    assert "includes_handicap_market" in reason_codes
    assert "includes_correct_score_market" in reason_codes


def test_final_answer_arbitrator_records_upset_quality_without_strategy() -> None:
    option = _option(
        option_key="standalone_single:1x1:single",
        option_type="standalone_single",
        pass_type="1x1",
        fixture_ids=("A",),
        planner_score=0.70,
        hit_probability=0.29,
        roi=0.35,
        risk_score=0.68,
        data_quality=84.0,
        outcome="draw",
        upset_protection_score=0.74,
        metadata_json={"target_outcome": "draw", "upset_score": 0.74},
    )

    payload = build_final_answer_arbitration_payload(
        option,
        rank=1,
        candidate_count=1,
    )

    upset_policy = payload["upset_policy"]
    assert isinstance(upset_policy, dict)
    assert upset_policy["directions"] == ["draw_overlooked"]
    score_components = cast(dict[str, float], payload["score_components"])
    assert score_components["upset_quality_diagnostic"] > 0.0
    reason_codes = cast(list[str], payload["reason_codes"])
    assert "upset_protection_considered" not in reason_codes
    assert "strategy" not in str(payload)


def _option(
    *,
    option_key: str,
    option_type: str,
    pass_type: str,
    fixture_ids: tuple[str, ...],
    planner_score: float,
    hit_probability: float,
    roi: float,
    risk_score: float,
    data_quality: float,
    mode: str = "single",
    market_type: str = "1x2",
    within_budget: bool = True,
    total_stake: float = 2.0,
    competition_id: str | None = None,
    outcome: str | None = None,
    upset_protection_score: float = 0.0,
    metadata_json: dict[str, object] | None = None,
    decimal_odds: float = 2.0,
    model_edge: float | None = None,
    candidate_score: float = 0.70,
    budget_adjustment: dict[str, object] | None = None,
    max_budget: float = 20.0,
    total_atomic_bets: int = 1,
) -> RecommendationGlobalPlanOption:
    candidates = [
        _scored_candidate(
            fixture_id=fixture_id,
            market_type=market_type,
            probability=max(0.05, hit_probability),
            data_quality=data_quality,
            outcome=outcome,
            upset_protection_score=upset_protection_score,
            decimal_odds=decimal_odds,
            model_edge=model_edge,
            score=candidate_score,
            metadata_json=(
                {
                    **(metadata_json or {}),
                    **({"competition_id": competition_id} if competition_id else {}),
                }
            ),
        )
        for fixture_id in fixture_ids
    ]
    evaluation = ParlayEvaluation(
        pass_type=pass_type,
        is_multiple=mode == "multiple",
        unit_stake=2.0,
        multiplier=1,
        total_atomic_bets=total_atomic_bets,
        total_stake=total_stake,
        hit_probability=hit_probability,
        expected_payout=total_stake * (1.0 + roi),
        expected_value=total_stake * roi,
        roi=roi,
        risk_score=risk_score,
        risk_level="medium",
        rule_valid=within_budget,
        explanation_json={
            "budget": {
                "max_budget": max_budget,
                "within_budget": within_budget,
            }
        },
    )
    return RecommendationGlobalPlanOption(
        option_key=option_key,
        option_type=cast(RecommendationPlanOptionType, option_type),
        pass_type=pass_type,
        mode=cast(RecommendationMode, mode),
        planner_score=planner_score,
        within_budget=within_budget,
        selection=RecommendationSelection(
            pass_type=pass_type,
            mode=cast(RecommendationMode, mode),
            selected_candidates=candidates,
            evaluation=evaluation,
            total_score=planner_score,
            candidate_count=len(candidates),
            excluded_candidate_count=0,
            explanation_json=(
                {"budget_adjustment": budget_adjustment}
                if budget_adjustment is not None
                else {}
            ),
        ),
    )


def _scored_candidate(
    *,
    fixture_id: str,
    market_type: str,
    probability: float,
    data_quality: float,
    outcome: str | None = None,
    upset_protection_score: float = 0.0,
    metadata_json: dict[str, object] | None = None,
    decimal_odds: float = 2.0,
    model_edge: float | None = None,
    score: float = 0.70,
) -> ScoredRecommendationCandidate:
    candidate = RecommendationCandidate(
        fixture_id=fixture_id,
        market_type=cast(RecommendationMarketType, market_type),
        outcome=outcome or ("home_win" if market_type != "correct_score" else "2-1"),
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        model_edge=model_edge,
        data_quality_score=data_quality,
        model_confidence_score=0.80,
        calibration_score=0.80,
        upset_protection_score=upset_protection_score,
        model_version="poisson-v3.1-baseline",
        prediction_time_utc=datetime(2026, 5, 1, 12, tzinfo=UTC),
        kickoff_time_utc=datetime(2026, 5, 2, 12, tzinfo=UTC),
        metadata_json=metadata_json or {},
    )
    return ScoredRecommendationCandidate(candidate=candidate, score=score)
