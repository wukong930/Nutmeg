from __future__ import annotations

from nutmeg.recommendations import (
    MultipleValueAdmissionOptions,
    RecommendationCandidate,
    build_multiple_value_admission_summary,
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)


def test_multiple_value_admission_scores_each_extra_option() -> None:
    selection = select_budget_constrained_multiple_parlay(
        _candidate_pool(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    summary = build_multiple_value_admission_summary(selection)

    assert summary.status == "admitted"
    assert summary.admitted is True
    assert summary.multiple_choice_fixture_count == 1
    assert summary.extra_option_count == 1
    assert summary.admitted_extra_option_count == 1
    assert summary.rejected_extra_option_count == 0
    assert summary.base_total_atomic_bets == 1
    assert summary.final_total_atomic_bets == 2
    assert summary.base_total_stake == 2.0
    assert summary.final_total_stake == 4.0
    contribution = summary.contributions[0]
    assert contribution.fixture_id == "A"
    assert contribution.base_outcome == "home_win"
    assert contribution.added_outcome == "draw"
    assert contribution.admitted is True
    assert contribution.marginal_quality_gain >= 0.0
    assert contribution.total_stake_delta == 2.0
    assert contribution.atomic_bet_delta == 1


def test_multiple_value_admission_rejects_extra_option_below_threshold() -> None:
    selection = select_budget_constrained_multiple_parlay(
        _candidate_pool(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=4.0,
    )

    summary = build_multiple_value_admission_summary(
        selection,
        options=MultipleValueAdmissionOptions(min_marginal_quality_gain=1.0),
    )

    assert summary.status == "rejected"
    assert summary.admitted is False
    assert summary.rejected_extra_option_count == 1
    assert summary.rejection_reason_counts == {
        "marginal_quality_gain_below_threshold": 1
    }


def test_multiple_value_admission_marks_single_parlay_as_not_multiple() -> None:
    selection = select_budget_constrained_single_parlay(
        _candidate_pool(),
        pass_type="3x1",
        unit_stake=2.0,
        max_budget=2.0,
    )

    summary = build_multiple_value_admission_summary(selection)

    assert summary.status == "not_multiple"
    assert summary.admitted is True
    assert summary.extra_option_count == 0
    assert summary.contributions == []


def _candidate_pool() -> list[RecommendationCandidate]:
    return [
        _candidate("A", "home_win", probability=0.62, decimal_odds=1.70),
        _candidate("A", "draw", probability=0.26, decimal_odds=3.40),
        _candidate("A", "away_win", probability=0.12, decimal_odds=5.80),
        _candidate("B", "home_win", probability=0.60, decimal_odds=1.80),
        _candidate("B", "draw", probability=0.20, decimal_odds=3.80),
        _candidate("C", "away_win", probability=0.59, decimal_odds=1.80),
        _candidate("C", "draw", probability=0.19, decimal_odds=3.90),
    ]


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        model_edge=probability - (1.0 / decimal_odds),
        data_quality_score=90.0,
        model_confidence_score=0.88,
        calibration_score=0.84,
        odds_stability_score=0.80,
        metadata_json={"competition_id": "EPL"},
    )
