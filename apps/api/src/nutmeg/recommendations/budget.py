from __future__ import annotations

from collections.abc import Collection, Sequence
from itertools import combinations, product

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayEvaluation, ParlayLegSelection
from nutmeg.parlay import evaluate_parlay


class RemovedParlayOption(BaseModel):
    fixture_id: str
    outcome: str
    reason: str
    marginal_score: float
    marginal_quality_loss: float = Field(default=0.0, ge=0.0)
    projected_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    projected_total_atomic_bets: int = Field(default=0, ge=0)
    projected_total_stake: float = Field(default=0.0, ge=0.0)
    projected_hit_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    projected_expected_value: float = 0.0
    projected_roi: float = 0.0


class BudgetOptimizationResult(BaseModel):
    original_evaluation: ParlayEvaluation
    optimized_evaluation: ParlayEvaluation
    optimized_legs: list[ParlayLegSelection]
    removed_options: list[RemovedParlayOption] = Field(default_factory=list)
    within_budget: bool
    warning_codes: list[str] = Field(default_factory=list)
    optimization_basis: str = "budget_constrained_quality_search_v1"
    original_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    optimized_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    quality_score_delta: float = 0.0


class _BudgetSolution(BaseModel):
    legs: list[ParlayLegSelection]
    evaluation: ParlayEvaluation
    quality_score: float

    @property
    def sort_key(self) -> tuple[int, float, float, float, float, float]:
        return (
            self.evaluation.total_atomic_bets,
            self.quality_score,
            self.evaluation.expected_value,
            self.evaluation.hit_probability,
            self.evaluation.roi,
            -self.evaluation.total_stake,
        )


class _RemovalProjection(BaseModel):
    leg_index: int
    removed: RemovedParlayOption
    projected_legs: list[ParlayLegSelection]
    projected_evaluation: ParlayEvaluation
    projected_quality_score: float

    @property
    def sort_key(self) -> tuple[bool, float, float, float, int, float]:
        return (
            self.projected_evaluation.rule_valid,
            self.projected_quality_score,
            self.projected_evaluation.expected_value,
            self.projected_evaluation.hit_probability,
            self.projected_evaluation.total_atomic_bets,
            -self.projected_evaluation.total_stake,
        )


_MAX_EXACT_REMOVABLE_OUTCOMES = 16


def optimize_multiple_parlay_budget(
    legs: Sequence[ParlayLegSelection],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float | None,
    multiplier: int = 1,
    locked_outcomes: Collection[tuple[str, str]] = (),
) -> BudgetOptimizationResult:
    working_legs = [leg.model_copy(deep=True) for leg in legs]
    original_evaluation = evaluate_parlay(
        working_legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        multiplier=multiplier,
        max_budget=max_budget,
    )
    if max_budget is None or original_evaluation.total_stake <= max_budget:
        quality_score = _budget_solution_quality(
            original_evaluation,
            working_legs,
            max_budget=max_budget,
        )
        return BudgetOptimizationResult(
            original_evaluation=original_evaluation,
            optimized_evaluation=original_evaluation,
            optimized_legs=working_legs,
            within_budget=True,
            original_quality_score=quality_score,
            optimized_quality_score=quality_score,
        )

    locked_outcome_set = set(locked_outcomes)
    original_quality_score = _budget_solution_quality(
        original_evaluation,
        working_legs,
        max_budget=max_budget,
    )
    solution = _find_exact_budget_solution(
        working_legs,
        original_evaluation=original_evaluation,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        multiplier=multiplier,
        locked_outcomes=locked_outcome_set,
    )
    optimization_basis = "budget_constrained_quality_search_v1"
    warning_codes: list[str] = []
    if solution is None:
        solution = _find_greedy_budget_solution(
            working_legs,
            original_evaluation=original_evaluation,
            original_quality_score=original_quality_score,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            multiplier=multiplier,
            locked_outcomes=locked_outcome_set,
        )
        optimization_basis = "budget_constrained_quality_greedy_fallback_v1"
        warning_codes.append("budget_exact_search_fell_back_to_greedy_projection")

    removed_options = _removed_options_from_solution(
        working_legs,
        solution.legs,
        original_evaluation=original_evaluation,
        original_quality_score=original_quality_score,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        multiplier=multiplier,
    )
    within_budget = solution.evaluation.total_stake <= max_budget
    if not within_budget:
        warning_codes.append("budget_cannot_be_reduced_with_locked_outcomes")
    return BudgetOptimizationResult(
        original_evaluation=original_evaluation,
        optimized_evaluation=solution.evaluation,
        optimized_legs=solution.legs,
        removed_options=removed_options,
        within_budget=within_budget,
        warning_codes=warning_codes,
        optimization_basis=optimization_basis,
        original_quality_score=original_quality_score,
        optimized_quality_score=solution.quality_score,
        quality_score_delta=solution.quality_score - original_quality_score,
    )


def _find_exact_budget_solution(
    legs: Sequence[ParlayLegSelection],
    *,
    original_evaluation: ParlayEvaluation,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    multiplier: int,
    locked_outcomes: set[tuple[str, str]],
) -> _BudgetSolution | None:
    if _removable_outcome_count(legs, locked_outcomes=locked_outcomes) > (
        _MAX_EXACT_REMOVABLE_OUTCOMES
    ):
        return None

    best_within_budget: _BudgetSolution | None = None
    best_reduced_over_budget: _BudgetSolution | None = None
    for outcome_groups in product(
        *[
            _valid_outcome_subsets(leg, locked_outcomes=locked_outcomes)
            for leg in legs
        ]
    ):
        candidate_legs = [
            _leg_with_outcomes(leg, list(outcomes))
            for leg, outcomes in zip(legs, outcome_groups, strict=True)
        ]
        evaluation = evaluate_parlay(
            candidate_legs,
            pass_type=pass_type,
            unit_stake=unit_stake,
            multiplier=multiplier,
            max_budget=max_budget,
        )
        if evaluation.total_stake > original_evaluation.total_stake:
            continue
        solution = _BudgetSolution(
            legs=candidate_legs,
            evaluation=evaluation,
            quality_score=_budget_solution_quality(
                evaluation,
                candidate_legs,
                max_budget=max_budget,
            ),
        )
        if evaluation.total_stake <= max_budget:
            if best_within_budget is None or solution.sort_key > best_within_budget.sort_key:
                best_within_budget = solution
        elif (
            best_reduced_over_budget is None
            or _over_budget_solution_sort_key(solution) > _over_budget_solution_sort_key(
                best_reduced_over_budget
            )
        ):
            best_reduced_over_budget = solution
    return best_within_budget or best_reduced_over_budget


def _find_greedy_budget_solution(
    legs: Sequence[ParlayLegSelection],
    *,
    original_evaluation: ParlayEvaluation,
    original_quality_score: float,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    multiplier: int,
    locked_outcomes: set[tuple[str, str]],
) -> _BudgetSolution:
    working_legs = [leg.model_copy(deep=True) for leg in legs]
    current_evaluation = original_evaluation
    current_quality_score = original_quality_score
    while current_evaluation.total_stake > max_budget:
        projection = _find_best_removal_projection(
            working_legs,
            current_quality_score=current_quality_score,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            multiplier=multiplier,
            locked_outcomes=locked_outcomes,
        )
        if projection is None:
            break
        working_legs = projection.projected_legs
        current_evaluation = projection.projected_evaluation
        current_quality_score = projection.projected_quality_score
    return _BudgetSolution(
        legs=working_legs,
        evaluation=current_evaluation,
        quality_score=current_quality_score,
    )


def _find_best_removal_projection(
    legs: Sequence[ParlayLegSelection],
    *,
    current_quality_score: float,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    multiplier: int,
    locked_outcomes: set[tuple[str, str]],
) -> _RemovalProjection | None:
    best_projection: _RemovalProjection | None = None
    for leg_index, leg in enumerate(legs):
        if len(leg.outcomes) <= 1:
            continue
        for outcome in leg.outcomes:
            if (leg.fixture_id, outcome) in locked_outcomes:
                continue
            projected_legs = list(legs)
            projected_legs[leg_index] = _remove_outcome(leg, outcome)
            projected_evaluation = evaluate_parlay(
                projected_legs,
                pass_type=pass_type,
                unit_stake=unit_stake,
                multiplier=multiplier,
                max_budget=max_budget,
            )
            projected_quality_score = _budget_solution_quality(
                projected_evaluation,
                projected_legs,
                max_budget=max_budget,
            )
            removed = _removed_option_payload(
                leg,
                outcome,
                current_quality_score=current_quality_score,
                projected_evaluation=projected_evaluation,
                projected_quality_score=projected_quality_score,
            )
            projection = _RemovalProjection(
                leg_index=leg_index,
                removed=removed,
                projected_legs=projected_legs,
                projected_evaluation=projected_evaluation,
                projected_quality_score=projected_quality_score,
            )
            if best_projection is None or projection.sort_key > best_projection.sort_key:
                best_projection = projection
    return best_projection


def _removed_options_from_solution(
    original_legs: Sequence[ParlayLegSelection],
    optimized_legs: Sequence[ParlayLegSelection],
    *,
    original_evaluation: ParlayEvaluation,
    original_quality_score: float,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    multiplier: int,
) -> list[RemovedParlayOption]:
    optimized_outcomes_by_fixture = {
        leg.fixture_id: set(leg.outcomes) for leg in optimized_legs
    }
    removed_options: list[RemovedParlayOption] = []
    for leg_index, leg in enumerate(original_legs):
        kept_outcomes = optimized_outcomes_by_fixture.get(leg.fixture_id, set())
        for outcome in leg.outcomes:
            if outcome in kept_outcomes:
                continue
            projected_legs = list(original_legs)
            projected_legs[leg_index] = _remove_outcome(leg, outcome)
            projected_evaluation = evaluate_parlay(
                projected_legs,
                pass_type=pass_type,
                unit_stake=unit_stake,
                multiplier=multiplier,
                max_budget=max_budget,
            )
            projected_quality_score = _budget_solution_quality(
                projected_evaluation,
                projected_legs,
                max_budget=max_budget,
            )
            removed_options.append(
                _removed_option_payload(
                    leg,
                    outcome,
                    current_quality_score=original_quality_score,
                    projected_evaluation=projected_evaluation,
                    projected_quality_score=projected_quality_score,
                )
            )
    return sorted(
        removed_options,
        key=lambda item: (
            item.marginal_quality_loss,
            item.marginal_score,
            item.fixture_id,
            item.outcome,
        ),
    )


def _removed_option_payload(
    leg: ParlayLegSelection,
    outcome: str,
    *,
    current_quality_score: float,
    projected_evaluation: ParlayEvaluation,
    projected_quality_score: float,
) -> RemovedParlayOption:
    return RemovedParlayOption(
        fixture_id=leg.fixture_id,
        outcome=outcome,
        reason="lowest_marginal_quality_under_budget_constraint",
        marginal_score=_outcome_marginal_score(leg, outcome),
        marginal_quality_loss=max(current_quality_score - projected_quality_score, 0.0),
        projected_quality_score=projected_quality_score,
        projected_total_atomic_bets=projected_evaluation.total_atomic_bets,
        projected_total_stake=projected_evaluation.total_stake,
        projected_hit_probability=projected_evaluation.hit_probability,
        projected_expected_value=projected_evaluation.expected_value,
        projected_roi=projected_evaluation.roi,
    )


def _outcome_marginal_score(leg: ParlayLegSelection, outcome: str) -> float:
    try:
        probability = leg.probabilities[outcome]
        odds = leg.odds[outcome]
    except KeyError as exc:
        raise ValueError(f"missing probability or odds for outcome {outcome}") from exc
    return probability * max(odds - 1.0, 0.0) + probability


def _budget_solution_quality(
    evaluation: ParlayEvaluation,
    legs: Sequence[ParlayLegSelection],
    *,
    max_budget: float | None,
) -> float:
    total_stake = max(evaluation.total_stake, 1.0)
    expected_payout_component = _clamp(evaluation.expected_payout / total_stake / 2.5)
    roi_component = _clamp(0.50 + evaluation.roi / 2.0)
    risk_component = 1.0 - evaluation.risk_score
    data_quality_component = _average_data_quality(legs)
    budget_component = _budget_fit_component(evaluation.total_stake, max_budget=max_budget)
    return _clamp(
        0.34 * evaluation.hit_probability
        + 0.26 * expected_payout_component
        + 0.16 * roi_component
        + 0.12 * risk_component
        + 0.08 * data_quality_component
        + 0.04 * budget_component
    )


def _average_data_quality(legs: Sequence[ParlayLegSelection]) -> float:
    scores = [
        leg.data_quality_score / 100.0
        for leg in legs
        if leg.data_quality_score is not None
    ]
    if not scores:
        return 0.75
    return _clamp(sum(scores) / len(scores))


def _budget_fit_component(total_stake: float, *, max_budget: float | None) -> float:
    if max_budget is None or max_budget <= 0:
        return 1.0
    if total_stake <= max_budget:
        return 1.0
    overage_ratio = (total_stake - max_budget) / max_budget
    return _clamp(1.0 - overage_ratio)


def _over_budget_solution_sort_key(
    solution: _BudgetSolution,
) -> tuple[float, float, float, float]:
    return (
        -solution.evaluation.total_stake,
        solution.quality_score,
        solution.evaluation.hit_probability,
        solution.evaluation.expected_value,
    )


def _removable_outcome_count(
    legs: Sequence[ParlayLegSelection],
    *,
    locked_outcomes: set[tuple[str, str]],
) -> int:
    count = 0
    for leg in legs:
        if len(leg.outcomes) <= 1:
            continue
        for outcome in leg.outcomes:
            if (leg.fixture_id, outcome) not in locked_outcomes:
                count += 1
    return count


def _valid_outcome_subsets(
    leg: ParlayLegSelection,
    *,
    locked_outcomes: set[tuple[str, str]],
) -> list[tuple[str, ...]]:
    locked = [
        outcome
        for outcome in leg.outcomes
        if (leg.fixture_id, outcome) in locked_outcomes
    ]
    minimum_size = max(1, len(locked))
    subsets: list[tuple[str, ...]] = []
    for size in range(minimum_size, len(leg.outcomes) + 1):
        for combo in combinations(leg.outcomes, size):
            if all(outcome in combo for outcome in locked):
                combo_set = set(combo)
                subsets.append(
                    tuple(outcome for outcome in leg.outcomes if outcome in combo_set)
                )
    return subsets


def _leg_with_outcomes(
    leg: ParlayLegSelection,
    outcomes: list[str],
) -> ParlayLegSelection:
    outcome_set = set(outcomes)
    return leg.model_copy(
        deep=True,
        update={
            "outcomes": outcomes,
            "probabilities": {
                key: value for key, value in leg.probabilities.items() if key in outcome_set
            },
            "odds": {key: value for key, value in leg.odds.items() if key in outcome_set},
        },
    )


def _remove_outcome(leg: ParlayLegSelection, outcome: str) -> ParlayLegSelection:
    next_outcomes = [current for current in leg.outcomes if current != outcome]
    return _leg_with_outcomes(leg, next_outcomes)


def _clamp(value: float, *, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
