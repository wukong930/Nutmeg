from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayEvaluation, ParlayLegSelection
from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.models import (
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.policy import clamp_unit_interval

type MultipleValueAdmissionStatus = Literal["not_multiple", "admitted", "rejected"]


class MultipleValueAdmissionOptions(BaseModel):
    min_marginal_quality_gain: float = 0.0
    require_within_budget: bool = True


class MultipleValueContribution(BaseModel):
    fixture_id: str
    market_type: str
    base_outcome: str
    added_outcome: str
    admitted: bool
    reason_codes: list[str] = Field(default_factory=list)
    marginal_quality_gain: float
    hit_probability_delta: float
    expected_value_delta: float
    roi_delta: float
    total_stake_delta: float
    atomic_bet_delta: int


class MultipleValueAdmissionSummary(BaseModel):
    calculation_basis: str = "multiple_value_admission_v3_2"
    status: MultipleValueAdmissionStatus
    admitted: bool
    is_multiple: bool
    multiple_choice_fixture_count: int = Field(ge=0)
    extra_option_count: int = Field(ge=0)
    admitted_extra_option_count: int = Field(ge=0)
    rejected_extra_option_count: int = Field(ge=0)
    budget_pruned_option_count: int = Field(ge=0)
    total_marginal_quality_gain: float
    average_marginal_quality_gain: float | None = None
    min_marginal_quality_gain: float
    base_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    final_hit_probability: float = Field(ge=0.0, le=1.0)
    base_expected_value: float | None = None
    final_expected_value: float
    base_roi: float | None = None
    final_roi: float
    base_total_stake: float | None = Field(default=None, ge=0.0)
    final_total_stake: float = Field(ge=0.0)
    base_total_atomic_bets: int | None = Field(default=None, ge=0)
    final_total_atomic_bets: int = Field(ge=0)
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    contributions: list[MultipleValueContribution] = Field(default_factory=list)


def build_multiple_value_admission_summary(
    selection: RecommendationSelection,
    *,
    options: MultipleValueAdmissionOptions | None = None,
) -> MultipleValueAdmissionSummary:
    resolved_options = options or MultipleValueAdmissionOptions()
    legs = _selection_legs(selection)
    extra_options = _extra_option_candidates(selection, legs=legs)
    budget_within = _selection_within_budget(selection)
    if not selection.evaluation.is_multiple or not extra_options:
        rejection_reasons = (
            {"budget_exceeded": 1}
            if resolved_options.require_within_budget and not budget_within
            else {}
        )
        status: MultipleValueAdmissionStatus = (
            "rejected" if rejection_reasons else "not_multiple"
        )
        return MultipleValueAdmissionSummary(
            status=status,
            admitted=not rejection_reasons,
            is_multiple=selection.evaluation.is_multiple,
            multiple_choice_fixture_count=0,
            extra_option_count=0,
            admitted_extra_option_count=0,
            rejected_extra_option_count=0,
            budget_pruned_option_count=_budget_pruned_option_count(selection),
            total_marginal_quality_gain=0.0,
            min_marginal_quality_gain=resolved_options.min_marginal_quality_gain,
            final_hit_probability=selection.evaluation.hit_probability,
            final_expected_value=selection.evaluation.expected_value,
            final_roi=selection.evaluation.roi,
            final_total_stake=selection.evaluation.total_stake,
            final_total_atomic_bets=selection.evaluation.total_atomic_bets,
            rejection_reason_counts=rejection_reasons,
        )

    current_quality = _selection_quality(
        selection.evaluation,
        selection.selected_candidates,
    )
    base_legs = _base_single_outcome_legs(legs)
    base_evaluation = evaluate_parlay(
        base_legs,
        pass_type=selection.pass_type,
        unit_stake=selection.evaluation.unit_stake,
        max_budget=_max_budget(selection),
    )
    contributions = [
        _contribution_for_extra_option(
            selection,
            legs=legs,
            extra=extra,
            current_quality=current_quality,
            options=resolved_options,
        )
        for extra in extra_options
    ]
    rejected = [
        contribution for contribution in contributions if not contribution.admitted
    ]
    rejection_reason_counts = Counter(
        reason
        for contribution in rejected
        for reason in contribution.reason_codes
        if reason.endswith("_below_threshold")
        or reason in {"marginal_quality_gain_negative"}
    )
    if resolved_options.require_within_budget and not budget_within:
        rejection_reason_counts["budget_exceeded"] += 1
    total_gain = sum(item.marginal_quality_gain for item in contributions)
    status = "rejected" if rejection_reason_counts else "admitted"
    return MultipleValueAdmissionSummary(
        status=status,
        admitted=status == "admitted",
        is_multiple=selection.evaluation.is_multiple,
        multiple_choice_fixture_count=_multiple_choice_fixture_count(legs),
        extra_option_count=len(contributions),
        admitted_extra_option_count=sum(1 for item in contributions if item.admitted),
        rejected_extra_option_count=len(rejected),
        budget_pruned_option_count=_budget_pruned_option_count(selection),
        total_marginal_quality_gain=total_gain,
        average_marginal_quality_gain=(
            total_gain / len(contributions) if contributions else None
        ),
        min_marginal_quality_gain=resolved_options.min_marginal_quality_gain,
        base_hit_probability=base_evaluation.hit_probability,
        final_hit_probability=selection.evaluation.hit_probability,
        base_expected_value=base_evaluation.expected_value,
        final_expected_value=selection.evaluation.expected_value,
        base_roi=base_evaluation.roi,
        final_roi=selection.evaluation.roi,
        base_total_stake=base_evaluation.total_stake,
        final_total_stake=selection.evaluation.total_stake,
        base_total_atomic_bets=base_evaluation.total_atomic_bets,
        final_total_atomic_bets=selection.evaluation.total_atomic_bets,
        rejection_reason_counts=dict(sorted(rejection_reason_counts.items())),
        contributions=contributions,
    )


def _contribution_for_extra_option(
    selection: RecommendationSelection,
    *,
    legs: Sequence[ParlayLegSelection],
    extra: ScoredRecommendationCandidate,
    current_quality: float,
    options: MultipleValueAdmissionOptions,
) -> MultipleValueContribution:
    candidate = extra.candidate
    reduced_legs = _legs_without_outcome(
        legs,
        fixture_id=candidate.fixture_id,
        market_type=candidate.market_type,
        outcome=candidate.outcome,
    )
    reduced_selected = [
        item
        for item in selection.selected_candidates
        if _candidate_key(item) != _candidate_key(extra)
    ]
    reduced_evaluation = evaluate_parlay(
        reduced_legs,
        pass_type=selection.pass_type,
        unit_stake=selection.evaluation.unit_stake,
        max_budget=_max_budget(selection),
    )
    reduced_quality = _selection_quality(reduced_evaluation, reduced_selected)
    marginal_quality_gain = current_quality - reduced_quality
    reason_codes = _contribution_reason_codes(
        marginal_quality_gain,
        min_marginal_quality_gain=options.min_marginal_quality_gain,
    )
    return MultipleValueContribution(
        fixture_id=candidate.fixture_id,
        market_type=candidate.market_type,
        base_outcome=_base_outcome_for_extra(legs, extra),
        added_outcome=candidate.outcome,
        admitted="marginal_quality_gain_below_threshold" not in reason_codes
        and "marginal_quality_gain_negative" not in reason_codes,
        reason_codes=reason_codes,
        marginal_quality_gain=marginal_quality_gain,
        hit_probability_delta=(
            selection.evaluation.hit_probability - reduced_evaluation.hit_probability
        ),
        expected_value_delta=(
            selection.evaluation.expected_value - reduced_evaluation.expected_value
        ),
        roi_delta=selection.evaluation.roi - reduced_evaluation.roi,
        total_stake_delta=(
            selection.evaluation.total_stake - reduced_evaluation.total_stake
        ),
        atomic_bet_delta=(
            selection.evaluation.total_atomic_bets
            - reduced_evaluation.total_atomic_bets
        ),
    )


def _selection_legs(selection: RecommendationSelection) -> list[ParlayLegSelection]:
    legs: list[ParlayLegSelection] = []
    leg_index_by_key: dict[tuple[str, str, float | None, str | None], int] = {}
    for scored in selection.selected_candidates:
        leg = scored.candidate.to_leg_selection()
        key = _leg_key(leg)
        leg_index = leg_index_by_key.get(key)
        if leg_index is None:
            leg_index_by_key[key] = len(legs)
            legs.append(leg)
            continue
        existing = legs[leg_index]
        if scored.candidate.outcome in existing.outcomes:
            continue
        legs[leg_index] = existing.model_copy(
            deep=True,
            update={
                "outcomes": [*existing.outcomes, scored.candidate.outcome],
                "probabilities": {
                    **existing.probabilities,
                    scored.candidate.outcome: scored.candidate.effective_probability(),
                },
                "odds": {
                    **existing.odds,
                    scored.candidate.outcome: scored.candidate.decimal_odds,
                },
            },
        )
    return legs


def _extra_option_candidates(
    selection: RecommendationSelection,
    *,
    legs: Sequence[ParlayLegSelection],
) -> list[ScoredRecommendationCandidate]:
    base_outcomes_by_key = {_leg_key(leg): leg.outcomes[0] for leg in legs}
    result: list[ScoredRecommendationCandidate] = []
    for scored in selection.selected_candidates:
        candidate = scored.candidate
        key = (
            candidate.fixture_id,
            candidate.market_type,
            candidate.line,
            candidate.side,
        )
        if candidate.outcome == base_outcomes_by_key.get(key):
            continue
        result.append(scored)
    return result


def _base_single_outcome_legs(
    legs: Sequence[ParlayLegSelection],
) -> list[ParlayLegSelection]:
    return [
        leg.model_copy(
            deep=True,
            update={
                "outcomes": [leg.outcomes[0]],
                "probabilities": {leg.outcomes[0]: leg.probabilities[leg.outcomes[0]]},
                "odds": {leg.outcomes[0]: leg.odds[leg.outcomes[0]]},
            },
        )
        for leg in legs
    ]


def _legs_without_outcome(
    legs: Sequence[ParlayLegSelection],
    *,
    fixture_id: str,
    market_type: str,
    outcome: str,
) -> list[ParlayLegSelection]:
    result: list[ParlayLegSelection] = []
    for leg in legs:
        if (
            leg.fixture_id != fixture_id
            or leg.market_type != market_type
            or outcome not in leg.outcomes
        ):
            result.append(leg.model_copy(deep=True))
            continue
        outcomes = [item for item in leg.outcomes if item != outcome]
        result.append(
            leg.model_copy(
                deep=True,
                update={
                    "outcomes": outcomes,
                    "probabilities": {
                        item: probability
                        for item, probability in leg.probabilities.items()
                        if item in outcomes
                    },
                    "odds": {
                        item: decimal_odds
                        for item, decimal_odds in leg.odds.items()
                        if item in outcomes
                    },
                },
            )
        )
    return result


def _selected_scored_for_legs(
    legs: Sequence[ParlayLegSelection],
    selected: Sequence[ScoredRecommendationCandidate],
) -> list[ScoredRecommendationCandidate]:
    allowed = {
        (leg.fixture_id, leg.market_type, outcome)
        for leg in legs
        for outcome in leg.outcomes
    }
    return [
        scored
        for scored in selected
        if (
            scored.candidate.fixture_id,
            scored.candidate.market_type,
            scored.candidate.outcome,
        )
        in allowed
    ]


def _selection_quality(
    evaluation: ParlayEvaluation,
    selected: Sequence[ScoredRecommendationCandidate],
) -> float:
    average_candidate_score = (
        sum(item.score for item in selected) / len(selected) if selected else 0.0
    )
    roi_component = clamp_unit_interval(0.50 + evaluation.roi / 2.0)
    ev_component = clamp_unit_interval(
        0.50 + evaluation.expected_value / max(evaluation.total_stake, 1.0) / 2.0
    )
    risk_component = 1.0 - evaluation.risk_score
    calibration_risk = _component_portfolio_pressure(selected, "calibration_risk")
    longshot_upset_risk = _component_portfolio_pressure(selected, "longshot_upset_risk")
    fragile_favorite_risk = _component_portfolio_pressure(
        selected,
        "upset_avoidance_penalty",
    )
    return clamp_unit_interval(
        0.39 * evaluation.hit_probability
        + 0.28 * ev_component
        + 0.21 * average_candidate_score
        + 0.11 * roi_component
        + 0.09 * risk_component
        - 0.07 * calibration_risk
        - 0.10 * longshot_upset_risk
        - 0.08 * fragile_favorite_risk
    )


def _component_portfolio_pressure(
    selected: Sequence[ScoredRecommendationCandidate],
    component_name: str,
) -> float:
    retained_probability = 1.0
    has_component = False
    for scored in selected:
        component_value = scored.component_scores.get(component_name)
        if component_value is None:
            continue
        has_component = True
        retained_probability *= 1.0 - clamp_unit_interval(component_value)
    if not has_component:
        return 0.0
    return clamp_unit_interval(1.0 - retained_probability)


def _contribution_reason_codes(
    marginal_quality_gain: float,
    *,
    min_marginal_quality_gain: float,
) -> list[str]:
    reason_codes: list[str] = []
    if marginal_quality_gain < 0:
        reason_codes.append("marginal_quality_gain_negative")
    if marginal_quality_gain < min_marginal_quality_gain:
        reason_codes.append("marginal_quality_gain_below_threshold")
    if marginal_quality_gain >= min_marginal_quality_gain:
        reason_codes.append("marginal_quality_gain_admitted")
    return reason_codes


def _base_outcome_for_extra(
    legs: Sequence[ParlayLegSelection],
    extra: ScoredRecommendationCandidate,
) -> str:
    candidate = extra.candidate
    for leg in legs:
        if (
            leg.fixture_id == candidate.fixture_id
            and leg.market_type == candidate.market_type
        ):
            return leg.outcomes[0]
    return ""


def _multiple_choice_fixture_count(legs: Sequence[ParlayLegSelection]) -> int:
    return sum(1 for leg in legs if len(leg.outcomes) > 1)


def _budget_pruned_option_count(selection: RecommendationSelection) -> int:
    decisions = selection.explanation_json.get("multiple_option_decisions")
    if not isinstance(decisions, list):
        return 0
    return sum(
        1
        for decision in decisions
        if isinstance(decision, dict) and decision.get("reason_code") == "budget_exceeded"
    )


def _max_budget(selection: RecommendationSelection) -> float | None:
    budget = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget, dict):
        return None
    value = budget.get("max_budget")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _selection_within_budget(selection: RecommendationSelection) -> bool:
    budget = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget, dict):
        return True
    return bool(budget.get("within_budget", True))


def _leg_key(leg: ParlayLegSelection) -> tuple[str, str, float | None, str | None]:
    return (leg.fixture_id, leg.market_type, leg.line, leg.side)


def _candidate_key(
    scored: ScoredRecommendationCandidate,
) -> tuple[str, str, str, float | None, str | None]:
    candidate = scored.candidate
    return (
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
        candidate.line,
        candidate.side,
    )
