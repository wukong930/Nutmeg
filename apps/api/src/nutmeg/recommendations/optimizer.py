from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from itertools import combinations
from math import isclose
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayEvaluation, ParlayLegSelection
from nutmeg.parlay import evaluate_parlay
from nutmeg.parlay.risk import placeholder_risk_score, risk_level_from_score
from nutmeg.recommendations.budget import optimize_multiple_parlay_budget
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationPolicyConfig,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.policy import (
    clamp_unit_interval,
    parse_pass_type_leg_count,
    rank_candidates,
    score_candidate,
    select_best_single_parlay,
)
from nutmeg.recommendations.upset_policy import (
    build_upset_policy_payload,
)

type MultipleOptionAction = Literal["added", "skipped"]
type FixtureReplacementAction = Literal["replaced", "skipped"]

SOLVER_MIN_QUALITY_DELTA = 0.0015


class MultipleOptionDecision(BaseModel):
    fixture_id: str
    market_type: str
    outcome: str
    action: MultipleOptionAction
    reason_code: str
    marginal_quality_gain: float
    projected_total_stake: float = Field(ge=0.0)
    projected_hit_probability: float = Field(ge=0.0, le=1.0)


class FixtureReplacementDecision(BaseModel):
    old_fixture_id: str
    new_fixture_id: str
    action: FixtureReplacementAction
    reason_code: str
    quality_delta: float
    projected_total_stake: float = Field(ge=0.0)
    projected_hit_probability: float = Field(ge=0.0, le=1.0)
    replacement_outcomes: list[str] = Field(default_factory=list)


class LockedRecommendationComparison(BaseModel):
    locked_preserving_selection: RecommendationSelection
    current_best_selection: RecommendationSelection
    changed_fixture_ids: list[str] = Field(default_factory=list)
    explanation_json: dict[str, object] = Field(default_factory=dict)


def select_budget_constrained_single_parlay(
    candidates: Sequence[RecommendationCandidate],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
    locked_candidates: Sequence[RecommendationCandidate] = (),
    min_quality_gain: float = 0.0,
    enable_solver_search: bool = True,
) -> RecommendationSelection:
    resolved_config = config or RecommendationPolicyConfig()
    leg_count = parse_pass_type_leg_count(pass_type)
    base_selection = select_best_single_parlay(
        candidates,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=resolved_config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=locked_candidates,
    )
    if (
        not enable_solver_search
        or max_budget is None
        or base_selection.evaluation.total_stake > max_budget
    ):
        return base_selection

    base_quality = _parlay_quality(
        base_selection.evaluation,
        base_selection.selected_candidates,
    )
    solver_result = _solver_backed_budget_constrained_selection(
        candidates,
        locked_candidates=locked_candidates,
        leg_count=leg_count,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=resolved_config,
        as_of_time_utc=as_of_time_utc,
        max_outcomes_per_fixture=1,
    )
    if solver_result is None:
        return base_selection

    quality_delta = solver_result.quality - base_quality
    if quality_delta <= _solver_required_quality_gain(min_quality_gain):
        return base_selection

    total_score = sum(item.score for item in solver_result.selected_scored) / len(
        solver_result.selected_scored
    )
    return RecommendationSelection(
        pass_type=pass_type,
        mode="single",
        selected_candidates=solver_result.selected_scored,
        evaluation=solver_result.evaluation,
        total_score=total_score,
        locked_fixture_ids=base_selection.locked_fixture_ids,
        candidate_count=base_selection.candidate_count,
        excluded_candidate_count=base_selection.excluded_candidate_count,
        explanation_json={
            **base_selection.explanation_json,
            "selection_basis": "v3_1_single_integer_optimizer",
            "base_fixture_ids": base_selection.fixture_ids,
            "solver_search": {
                "strategy": "budget_constrained_integer_solver",
                "search_mode": solver_result.search_mode,
                "accepted": True,
                "exact": solver_result.exact,
                "candidate_fixture_count": solver_result.candidate_fixture_count,
                "fixture_variant_count": solver_result.fixture_variant_count,
                "evaluated_complete_states": (solver_result.evaluated_complete_states),
                "generated_state_count": solver_result.generated_state_count,
                "pruned_state_count": solver_result.pruned_state_count,
                "state_limit": solver_result.state_limit,
                "previous_quality_score": base_quality,
                "quality_delta": quality_delta,
                "selected_fixture_ids": [leg.fixture_id for leg in solver_result.legs],
                "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(solver_result.legs),
                "supersedes_heuristic_path": True,
            },
        },
    )


def select_budget_constrained_multiple_parlay(
    candidates: Sequence[RecommendationCandidate],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
    locked_candidates: Sequence[RecommendationCandidate] = (),
    max_outcomes_per_fixture: int = 2,
    min_marginal_quality_gain: float = 0.0,
    enable_solver_search: bool = True,
    solver_first_candidate_fixture_threshold: int = 16,
) -> RecommendationSelection:
    if max_outcomes_per_fixture < 1:
        raise ValueError("max_outcomes_per_fixture must be at least 1")
    resolved_config = config or RecommendationPolicyConfig()
    leg_count = parse_pass_type_leg_count(pass_type)
    base_selection = select_best_single_parlay(
        candidates,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=resolved_config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=locked_candidates,
    )
    if max_outcomes_per_fixture == 1:
        single_selection = select_budget_constrained_single_parlay(
            candidates,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
            locked_candidates=locked_candidates,
            min_quality_gain=min_marginal_quality_gain,
            enable_solver_search=enable_solver_search,
        )
        return single_selection.model_copy(
            update={
                "mode": "multiple",
                "explanation_json": {
                    **single_selection.explanation_json,
                    "selection_basis": "v3_1_multiple_single_outcome_integer_optimizer",
                },
            }
        )

    solver_first_result: _SolverSearchResult | None = None
    if (
        enable_solver_search
        and max_budget is not None
        and _should_use_solver_first_path(
            candidates,
            locked_candidates=locked_candidates,
            leg_count=leg_count,
            candidate_fixture_threshold=solver_first_candidate_fixture_threshold,
        )
    ):
        base_quality = _parlay_quality(
            base_selection.evaluation,
            base_selection.selected_candidates,
        )
        solver_first_result = _solver_backed_budget_constrained_selection(
            candidates,
            locked_candidates=locked_candidates,
            leg_count=leg_count,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
        )
        if solver_first_result is not None:
            quality_delta = solver_first_result.quality - base_quality
            solver_accepted = quality_delta > _solver_required_quality_gain(
                min_marginal_quality_gain
            )
            if solver_accepted:
                return _selection_from_solver_result(
                    solver_first_result,
                    base_selection=base_selection,
                    pass_type=pass_type,
                    mode="multiple",
                    selection_basis="v3_1_multiple_solver_first_optimizer",
                    previous_quality=base_quality,
                    quality_delta=quality_delta,
                    accepted=True,
                    supersedes_heuristic_path=True,
                    solver_first_fast_path=True,
                    max_outcomes_per_fixture=max_outcomes_per_fixture,
                )

    working_legs = [
        item.candidate.to_leg_selection() for item in base_selection.selected_candidates
    ]
    selected_scored = list(base_selection.selected_candidates)
    selected_keys = {_candidate_key(item.candidate) for item in selected_scored}
    fixture_to_leg_index = {leg.fixture_id: index for index, leg in enumerate(working_legs)}
    blocked_fixture_ids = {
        item.candidate.fixture_id
        for item in selected_scored
        if as_of_time_utc is not None and item.candidate.has_started(as_of_time_utc)
    }
    addable_options = _rank_addable_options(
        candidates,
        base_legs=working_legs,
        selected_keys=selected_keys,
        blocked_fixture_ids=blocked_fixture_ids,
        config=resolved_config,
        as_of_time_utc=as_of_time_utc,
    )
    decisions: list[MultipleOptionDecision] = []
    skipped_budget_keys: set[tuple[str, str, str]] = set()
    current_evaluation = evaluate_parlay(
        working_legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=None,
    )
    current_quality = _parlay_quality(current_evaluation, selected_scored)

    while True:
        best_projection: _OptionProjection | None = None
        for scored in addable_options:
            candidate = scored.candidate
            key = _candidate_key(candidate)
            if key in selected_keys:
                continue
            leg_index = fixture_to_leg_index.get(candidate.fixture_id)
            if leg_index is None:
                continue
            leg = working_legs[leg_index]
            if len(leg.outcomes) >= max_outcomes_per_fixture:
                continue
            projected_legs = list(working_legs)
            projected_legs[leg_index] = _add_candidate_to_leg(leg, candidate)
            projected_evaluation = evaluate_parlay(
                projected_legs,
                pass_type=pass_type,
                unit_stake=unit_stake,
                max_budget=None,
            )
            projected_selected = [*selected_scored, scored]
            projected_quality = _parlay_quality(projected_evaluation, projected_selected)
            marginal_quality_gain = projected_quality - current_quality
            if marginal_quality_gain < min_marginal_quality_gain:
                continue
            projection = _OptionProjection(
                scored_candidate=scored,
                leg_index=leg_index,
                projected_legs=projected_legs,
                projected_evaluation=projected_evaluation,
                projected_quality=projected_quality,
                marginal_quality_gain=marginal_quality_gain,
            )
            if best_projection is None or projection.sort_key > best_projection.sort_key:
                best_projection = projection
        if best_projection is None:
            break

        added_candidate = best_projection.scored_candidate.candidate
        working_legs = best_projection.projected_legs
        current_evaluation = best_projection.projected_evaluation
        current_quality = best_projection.projected_quality
        selected_scored.append(best_projection.scored_candidate)
        selected_keys.add(_candidate_key(added_candidate))
        decisions.append(
            MultipleOptionDecision(
                fixture_id=added_candidate.fixture_id,
                market_type=added_candidate.market_type,
                outcome=added_candidate.outcome,
                action="added",
                reason_code="positive_marginal_quality_before_budget_pruning",
                marginal_quality_gain=best_projection.marginal_quality_gain,
                projected_total_stake=current_evaluation.total_stake,
                projected_hit_probability=current_evaluation.hit_probability,
            )
        )

    budget_adjustment: dict[str, object] | None = None
    if max_budget is not None:
        locked_outcomes = {
            (candidate.fixture_id, candidate.outcome) for candidate in locked_candidates
        }
        budget_result = optimize_multiple_parlay_budget(
            working_legs,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            locked_outcomes=locked_outcomes,
        )
        if (
            budget_result.optimized_evaluation.total_atomic_bets
            != budget_result.original_evaluation.total_atomic_bets
            or budget_result.warning_codes
        ):
            kept_outcome_keys = {
                (leg.fixture_id, outcome)
                for leg in budget_result.optimized_legs
                for outcome in leg.outcomes
            }
            selected_scored = [
                item
                for item in selected_scored
                if (item.candidate.fixture_id, item.candidate.outcome) in kept_outcome_keys
            ]
            for removed in budget_result.removed_options:
                key = (removed.fixture_id, "", removed.outcome)
                if key not in skipped_budget_keys:
                    decisions.append(
                        MultipleOptionDecision(
                            fixture_id=removed.fixture_id,
                            market_type=_market_type_for_removed_option(
                                working_legs,
                                fixture_id=removed.fixture_id,
                            ),
                            outcome=removed.outcome,
                            action="skipped",
                            reason_code="budget_exceeded",
                            marginal_quality_gain=removed.marginal_score,
                            projected_total_stake=removed.projected_total_stake,
                            projected_hit_probability=removed.projected_hit_probability,
                        )
                    )
                    skipped_budget_keys.add(key)
            working_legs = budget_result.optimized_legs
            current_evaluation = budget_result.optimized_evaluation
            selected_scored = _selected_scored_from_legs(working_legs, selected_scored)
            current_quality = _parlay_quality(current_evaluation, selected_scored)
            budget_adjustment = {
                "strategy": "prune_lowest_marginal_unlocked_options",
                "optimization_basis": budget_result.optimization_basis,
                "original_total_atomic_bets": (budget_result.original_evaluation.total_atomic_bets),
                "optimized_total_atomic_bets": (
                    budget_result.optimized_evaluation.total_atomic_bets
                ),
                "original_total_stake": budget_result.original_evaluation.total_stake,
                "optimized_total_stake": budget_result.optimized_evaluation.total_stake,
                "within_budget": budget_result.within_budget,
                "original_quality_score": budget_result.original_quality_score,
                "optimized_quality_score": budget_result.optimized_quality_score,
                "quality_score_delta": budget_result.quality_score_delta,
                "removed_options": [
                    removed.model_dump() for removed in budget_result.removed_options
                ],
                "warning_codes": budget_result.warning_codes,
            }
        else:
            current_evaluation = budget_result.optimized_evaluation
            current_quality = _parlay_quality(current_evaluation, selected_scored)

    replacement_decisions: list[FixtureReplacementDecision] = []
    if (
        enable_solver_search
        and max_budget is not None
        and current_evaluation.total_stake <= max_budget
    ):
        replacement_result = _search_budget_safe_fixture_replacements(
            candidates,
            working_legs=working_legs,
            selected_scored=selected_scored,
            current_evaluation=current_evaluation,
            current_quality=current_quality,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            locked_fixture_ids=set(base_selection.locked_fixture_ids),
            blocked_fixture_ids=blocked_fixture_ids,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
            min_quality_gain=min_marginal_quality_gain,
        )
        if replacement_result.decisions:
            working_legs = replacement_result.legs
            selected_scored = replacement_result.selected_scored
            current_evaluation = replacement_result.evaluation
            current_quality = replacement_result.quality
            replacement_decisions = replacement_result.decisions

    solver_search_summary: dict[str, object] | None = None
    solver_accepted = False
    if (
        enable_solver_search
        and max_budget is not None
        and current_evaluation.total_stake <= max_budget
    ):
        solver_result = (
            solver_first_result
            if solver_first_result is not None
            else _solver_backed_budget_constrained_selection(
                candidates,
                locked_candidates=locked_candidates,
                leg_count=leg_count,
                pass_type=pass_type,
                unit_stake=unit_stake,
                max_budget=max_budget,
                config=resolved_config,
                as_of_time_utc=as_of_time_utc,
                max_outcomes_per_fixture=max_outcomes_per_fixture,
            )
        )
        if solver_result is not None:
            previous_quality = current_quality
            quality_delta = solver_result.quality - current_quality
            solver_accepted = quality_delta > _solver_required_quality_gain(
                min_marginal_quality_gain
            )
            solver_search_summary = {
                "strategy": "budget_constrained_integer_solver",
                "search_mode": solver_result.search_mode,
                "accepted": solver_accepted,
                "exact": solver_result.exact,
                "candidate_fixture_count": solver_result.candidate_fixture_count,
                "fixture_variant_count": solver_result.fixture_variant_count,
                "evaluated_complete_states": solver_result.evaluated_complete_states,
                "generated_state_count": solver_result.generated_state_count,
                "pruned_state_count": solver_result.pruned_state_count,
                "state_limit": solver_result.state_limit,
                "previous_quality_score": previous_quality,
                "quality_delta": quality_delta,
                "selected_fixture_ids": [leg.fixture_id for leg in solver_result.legs],
                "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(solver_result.legs),
                "supersedes_heuristic_path": solver_accepted,
                "solver_first_fast_path": solver_first_result is not None,
            }
            if solver_accepted:
                working_legs = solver_result.legs
                selected_scored = solver_result.selected_scored
                current_evaluation = solver_result.evaluation
                current_quality = solver_result.quality
                replacement_decisions = []

    beam_search_summary: dict[str, object] | None = None
    if (
        enable_solver_search
        and not solver_accepted
        and max_budget is not None
        and current_evaluation.total_stake <= max_budget
    ):
        beam_result = _beam_search_budget_constrained_selection(
            candidates,
            locked_candidates=locked_candidates,
            leg_count=leg_count,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
        )
        if beam_result is not None:
            previous_quality = current_quality
            quality_delta = beam_result.quality - current_quality
            if quality_delta > max(min_marginal_quality_gain, 1e-9):
                working_legs = beam_result.legs
                selected_scored = beam_result.selected_scored
                current_evaluation = beam_result.evaluation
                current_quality = beam_result.quality
                replacement_decisions = []
                beam_search_summary = {
                    "strategy": "budget_constrained_beam_search",
                    "accepted": True,
                    "beam_width": beam_result.beam_width,
                    "candidate_fixture_count": beam_result.candidate_fixture_count,
                    "fixture_variant_count": beam_result.fixture_variant_count,
                    "evaluated_complete_states": beam_result.evaluated_complete_states,
                    "previous_quality_score": previous_quality,
                    "quality_delta": quality_delta,
                    "selected_fixture_ids": [leg.fixture_id for leg in beam_result.legs],
                    "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(beam_result.legs),
                    "supersedes_heuristic_path": True,
                }

    total_score = sum(item.score for item in selected_scored) / len(selected_scored)
    explanation_json: dict[str, object] = {
        **base_selection.explanation_json,
        "selection_basis": "v3_1_multiple_budget_optimizer",
        "base_fixture_ids": base_selection.fixture_ids,
        "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(working_legs),
        "multiple_option_decisions": [decision.model_dump() for decision in decisions],
        "quality_score": current_quality,
        "upset_policy": build_upset_policy_payload([item.candidate for item in selected_scored]),
        "max_outcomes_per_fixture": max_outcomes_per_fixture,
    }
    if budget_adjustment is not None:
        explanation_json["budget_adjustment"] = budget_adjustment
    if replacement_decisions:
        explanation_json["fixture_replacement_search"] = {
            "strategy": "replace_unlocked_fixture_with_budget_safe_candidate",
            "accepted_replacements": [decision.model_dump() for decision in replacement_decisions],
        }
    if solver_search_summary is not None:
        explanation_json["solver_search"] = solver_search_summary
    if beam_search_summary is not None:
        explanation_json["beam_search"] = beam_search_summary
    return RecommendationSelection(
        pass_type=pass_type,
        mode="multiple",
        selected_candidates=selected_scored,
        evaluation=current_evaluation,
        total_score=total_score,
        locked_fixture_ids=base_selection.locked_fixture_ids,
        candidate_count=base_selection.candidate_count,
        excluded_candidate_count=base_selection.excluded_candidate_count,
        explanation_json=explanation_json,
    )


def compare_locked_preserving_to_current_best(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_candidates: Sequence[RecommendationCandidate],
    pass_type: str,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
    max_outcomes_per_fixture: int = 2,
) -> LockedRecommendationComparison:
    locked_selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=locked_candidates,
        max_outcomes_per_fixture=max_outcomes_per_fixture,
    )
    current_best_selection = select_budget_constrained_multiple_parlay(
        candidates,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=(),
        max_outcomes_per_fixture=max_outcomes_per_fixture,
    )
    locked_fixture_set = set(locked_selection.fixture_ids)
    current_fixture_set = set(current_best_selection.fixture_ids)
    changed_fixture_ids = sorted(locked_fixture_set.symmetric_difference(current_fixture_set))
    return LockedRecommendationComparison(
        locked_preserving_selection=locked_selection,
        current_best_selection=current_best_selection,
        changed_fixture_ids=changed_fixture_ids,
        explanation_json={
            "comparison_basis": "locked_preserving_vs_current_best",
            "locked_fixture_ids": [candidate.fixture_id for candidate in locked_candidates],
            "locked_preserving_total_score": locked_selection.total_score,
            "current_best_total_score": current_best_selection.total_score,
        },
    )


class _OptionProjection(BaseModel):
    scored_candidate: ScoredRecommendationCandidate
    leg_index: int
    projected_legs: list[ParlayLegSelection]
    projected_evaluation: ParlayEvaluation
    projected_quality: float
    marginal_quality_gain: float

    @property
    def sort_key(self) -> tuple[float, float, float]:
        return (
            self.marginal_quality_gain,
            self.scored_candidate.score,
            self.projected_evaluation.hit_probability,
        )


class _ReplacementProjection(BaseModel):
    old_fixture_id: str
    new_fixture_id: str
    leg_index: int
    legs: list[ParlayLegSelection]
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    quality: float
    quality_delta: float

    @property
    def sort_key(self) -> tuple[float, float, float, str]:
        return (
            self.quality_delta,
            self.quality,
            self.evaluation.hit_probability,
            self.new_fixture_id,
        )


class _FixtureReplacementSearchResult(BaseModel):
    legs: list[ParlayLegSelection]
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    quality: float
    decisions: list[FixtureReplacementDecision] = Field(default_factory=list)


class _FixtureOptionVariant(BaseModel):
    fixture_id: str
    leg: ParlayLegSelection
    scored_candidates: list[ScoredRecommendationCandidate]
    sort_key: tuple[float, float, float, float]
    selected_probability: float = Field(ge=0.0)
    score_sum: float
    score_count: int = Field(ge=1)


class _BeamState(BaseModel):
    variants: list[_FixtureOptionVariant] = Field(default_factory=list)


class _BeamSearchResult(BaseModel):
    legs: list[ParlayLegSelection]
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    quality: float
    candidate_fixture_count: int
    fixture_variant_count: int
    evaluated_complete_states: int
    beam_width: int


class _SolverState(BaseModel):
    variants: list[_FixtureOptionVariant] = Field(default_factory=list)
    atomic_count: int = Field(default=1, ge=1)
    selected_probability_product: float = Field(default=1.0, ge=0.0)
    selected_score_sum: float = 0.0
    selected_score_count: int = Field(default=0, ge=0)
    variant_quality_sum: float = 0.0


class _SolverSearchResult(BaseModel):
    legs: list[ParlayLegSelection]
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    quality: float
    candidate_fixture_count: int
    fixture_variant_count: int
    evaluated_complete_states: int
    generated_state_count: int
    pruned_state_count: int
    state_limit: int
    search_mode: str
    exact: bool


def _solver_required_quality_gain(configured_min_quality_gain: float) -> float:
    return max(configured_min_quality_gain, SOLVER_MIN_QUALITY_DELTA, 1e-9)


def _replacement_required_quality_gain(configured_min_quality_gain: float) -> float:
    return max(configured_min_quality_gain, SOLVER_MIN_QUALITY_DELTA, 1e-9)


def _should_use_solver_first_path(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_candidates: Sequence[RecommendationCandidate],
    leg_count: int,
    candidate_fixture_threshold: int,
) -> bool:
    if candidate_fixture_threshold <= 0:
        return False
    fixture_ids = {candidate.fixture_id for candidate in candidates}
    fixture_ids.update(candidate.fixture_id for candidate in locked_candidates)
    return len(fixture_ids) >= max(leg_count + 2, candidate_fixture_threshold)


def _selection_from_solver_result(
    solver_result: _SolverSearchResult,
    *,
    base_selection: RecommendationSelection,
    pass_type: str,
    mode: RecommendationMode,
    selection_basis: str,
    previous_quality: float,
    quality_delta: float,
    accepted: bool,
    supersedes_heuristic_path: bool,
    solver_first_fast_path: bool,
    max_outcomes_per_fixture: int,
) -> RecommendationSelection:
    total_score = sum(item.score for item in solver_result.selected_scored) / len(
        solver_result.selected_scored
    )
    return RecommendationSelection(
        pass_type=pass_type,
        mode=mode,
        selected_candidates=solver_result.selected_scored,
        evaluation=solver_result.evaluation,
        total_score=total_score,
        locked_fixture_ids=base_selection.locked_fixture_ids,
        candidate_count=base_selection.candidate_count,
        excluded_candidate_count=base_selection.excluded_candidate_count,
        explanation_json={
            **base_selection.explanation_json,
            "selection_basis": selection_basis,
            "base_fixture_ids": base_selection.fixture_ids,
            "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(solver_result.legs),
            "quality_score": solver_result.quality,
            "upset_policy": build_upset_policy_payload(
                [item.candidate for item in solver_result.selected_scored]
            ),
            "max_outcomes_per_fixture": max_outcomes_per_fixture,
            "solver_search": _solver_search_summary(
                solver_result,
                accepted=accepted,
                previous_quality=previous_quality,
                quality_delta=quality_delta,
                supersedes_heuristic_path=supersedes_heuristic_path,
                solver_first_fast_path=solver_first_fast_path,
            ),
        },
    )


def _multiple_base_fallback_selection(
    base_selection: RecommendationSelection,
    *,
    solver_result: _SolverSearchResult,
    base_quality: float,
    quality_delta: float,
    max_outcomes_per_fixture: int,
) -> RecommendationSelection:
    base_legs = [item.candidate.to_leg_selection() for item in base_selection.selected_candidates]
    return base_selection.model_copy(
        update={
            "mode": "multiple",
            "explanation_json": {
                **base_selection.explanation_json,
                "selection_basis": "v3_1_multiple_solver_first_base_fallback",
                "base_fixture_ids": base_selection.fixture_ids,
                "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(base_legs),
                "multiple_option_decisions": [],
                "quality_score": base_quality,
                "upset_policy": build_upset_policy_payload(
                    [item.candidate for item in base_selection.selected_candidates]
                ),
                "max_outcomes_per_fixture": max_outcomes_per_fixture,
                "solver_search": _solver_search_summary(
                    solver_result,
                    accepted=False,
                    previous_quality=base_quality,
                    quality_delta=quality_delta,
                    supersedes_heuristic_path=False,
                    solver_first_fast_path=True,
                ),
            },
        }
    )


def _solver_search_summary(
    solver_result: _SolverSearchResult,
    *,
    accepted: bool,
    previous_quality: float,
    quality_delta: float,
    supersedes_heuristic_path: bool,
    solver_first_fast_path: bool,
) -> dict[str, object]:
    return {
        "strategy": "budget_constrained_integer_solver",
        "search_mode": solver_result.search_mode,
        "accepted": accepted,
        "exact": solver_result.exact,
        "candidate_fixture_count": solver_result.candidate_fixture_count,
        "fixture_variant_count": solver_result.fixture_variant_count,
        "evaluated_complete_states": solver_result.evaluated_complete_states,
        "generated_state_count": solver_result.generated_state_count,
        "pruned_state_count": solver_result.pruned_state_count,
        "state_limit": solver_result.state_limit,
        "previous_quality_score": previous_quality,
        "quality_delta": quality_delta,
        "selected_fixture_ids": [leg.fixture_id for leg in solver_result.legs],
        "selected_outcomes_by_fixture": _selected_outcomes_by_fixture(solver_result.legs),
        "supersedes_heuristic_path": supersedes_heuristic_path,
        "solver_first_fast_path": solver_first_fast_path,
    }


def _solver_backed_budget_constrained_selection(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_candidates: Sequence[RecommendationCandidate],
    leg_count: int,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
    max_outcomes_per_fixture: int,
    candidate_fixture_limit: int = 160,
    per_fixture_variant_limit: int = 10,
    exact_state_limit: int = 2_000,
    states_per_bucket: int = 24,
) -> _SolverSearchResult | None:
    locked_variants = _locked_fixture_variants(locked_candidates, config=config)
    if len(locked_variants) > leg_count:
        return None
    locked_atomic_count = _variant_atomic_count(locked_variants)
    if locked_atomic_count * unit_stake > max_budget:
        return None

    locked_fixture_ids = {candidate.fixture_id for candidate in locked_candidates}
    ranked_candidates = [
        scored
        for scored in rank_candidates(candidates, config=config, as_of_time_utc=as_of_time_utc)
        if scored.candidate.fixture_id not in locked_fixture_ids
    ]
    variants_by_fixture = _beam_fixture_variants_by_fixture(
        ranked_candidates,
        max_outcomes_per_fixture=max_outcomes_per_fixture,
        per_fixture_variant_limit=per_fixture_variant_limit,
    )
    fixture_variant_groups = sorted(
        variants_by_fixture.values(),
        key=_fixture_variant_group_sort_key,
        reverse=True,
    )[:candidate_fixture_limit]
    remaining_count = leg_count - len(locked_variants)
    if remaining_count == 0:
        return _solver_result_from_variants(
            locked_variants,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            candidate_fixture_count=0,
            fixture_variant_count=0,
            evaluated_complete_states=1,
            generated_state_count=1,
            pruned_state_count=0,
            state_limit=exact_state_limit,
            search_mode="exact_integer_search",
            exact=True,
        )
    if len(fixture_variant_groups) < remaining_count:
        return None

    fixture_variant_count = sum(len(variants) for variants in fixture_variant_groups)
    estimated_states = _estimate_complete_solver_state_count(
        fixture_variant_groups,
        choose_count=remaining_count,
        limit=exact_state_limit,
    )
    if estimated_states <= exact_state_limit:
        return _exact_integer_solver_search(
            locked_variants,
            fixture_variant_groups,
            leg_count=leg_count,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            candidate_fixture_count=len(fixture_variant_groups),
            fixture_variant_count=fixture_variant_count,
            state_limit=exact_state_limit,
        )
    return _dynamic_programming_integer_solver_search(
        locked_variants,
        fixture_variant_groups,
        leg_count=leg_count,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        candidate_fixture_count=len(fixture_variant_groups),
        fixture_variant_count=fixture_variant_count,
        states_per_bucket=states_per_bucket,
    )


def _exact_integer_solver_search(
    locked_variants: Sequence[_FixtureOptionVariant],
    fixture_variant_groups: Sequence[Sequence[_FixtureOptionVariant]],
    *,
    leg_count: int,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    candidate_fixture_count: int,
    fixture_variant_count: int,
    state_limit: int,
) -> _SolverSearchResult | None:
    best_variants: list[_FixtureOptionVariant] | None = None
    best_sort_key = _solver_result_sort_key(None)
    evaluated_complete_states = 0
    generated_state_count = 1

    def search(
        group_index: int,
        selected_variants: list[_FixtureOptionVariant],
        atomic_count: int,
    ) -> None:
        nonlocal best_variants
        nonlocal best_sort_key
        nonlocal evaluated_complete_states
        nonlocal generated_state_count
        selected_count = len(selected_variants)
        remaining_groups = len(fixture_variant_groups) - group_index
        if selected_count == leg_count:
            evaluated_complete_states += 1
            sort_key = _solver_result_sort_key_from_variants(
                selected_variants,
                pass_type=pass_type,
                unit_stake=unit_stake,
                max_budget=max_budget,
            )
            if sort_key > best_sort_key:
                best_sort_key = sort_key
                best_variants = list(selected_variants)
            return
        if group_index >= len(fixture_variant_groups):
            return
        if selected_count + remaining_groups < leg_count:
            return

        search(group_index + 1, selected_variants, atomic_count)
        if selected_count >= leg_count:
            return
        for variant in fixture_variant_groups[group_index]:
            next_atomic_count = atomic_count * _variant_outcome_count(variant)
            if next_atomic_count * unit_stake > max_budget:
                continue
            generated_state_count += 1
            search(
                group_index + 1,
                [*selected_variants, variant],
                next_atomic_count,
            )

    search(
        0,
        list(locked_variants),
        _variant_atomic_count(locked_variants),
    )
    if best_variants is None:
        return None
    return _solver_result_from_variants(
        best_variants,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        candidate_fixture_count=candidate_fixture_count,
        fixture_variant_count=fixture_variant_count,
        evaluated_complete_states=evaluated_complete_states,
        generated_state_count=generated_state_count,
        pruned_state_count=0,
        state_limit=state_limit,
        search_mode="exact_integer_search",
        exact=True,
    )


def _dynamic_programming_integer_solver_search(
    locked_variants: Sequence[_FixtureOptionVariant],
    fixture_variant_groups: Sequence[Sequence[_FixtureOptionVariant]],
    *,
    leg_count: int,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    candidate_fixture_count: int,
    fixture_variant_count: int,
    states_per_bucket: int,
) -> _SolverSearchResult | None:
    max_atomic_count = int(max_budget / unit_stake)
    locked_atomic_count = _variant_atomic_count(locked_variants)
    initial_state = _solver_state_from_variants(
        locked_variants,
        atomic_count=locked_atomic_count,
    )
    states_by_bucket: dict[tuple[int, int], list[_SolverState]] = {
        (len(locked_variants), locked_atomic_count): [initial_state]
    }
    generated_state_count = 1
    pruned_state_count = 0

    for group_index, variants in enumerate(fixture_variant_groups):
        next_states_by_bucket = {
            bucket: list(states) for bucket, states in states_by_bucket.items()
        }
        for (selected_count, atomic_count), states in states_by_bucket.items():
            if selected_count >= leg_count:
                continue
            for state in states:
                for variant in variants:
                    next_atomic_count = atomic_count * _variant_outcome_count(variant)
                    if next_atomic_count > max_atomic_count:
                        continue
                    generated_state_count += 1
                    bucket = (selected_count + 1, next_atomic_count)
                    next_states_by_bucket.setdefault(bucket, []).append(
                        _solver_state_with_variant(
                            state,
                            variant,
                            atomic_count=next_atomic_count,
                        )
                    )
        remaining_group_count = len(fixture_variant_groups) - group_index - 1
        states_by_bucket, pruned_count = _prune_solver_state_buckets(
            next_states_by_bucket,
            leg_count=leg_count,
            unit_stake=unit_stake,
            max_budget=max_budget,
            states_per_bucket=states_per_bucket,
            remaining_group_count=remaining_group_count,
        )
        pruned_state_count += pruned_count

    best_result: _SolverSearchResult | None = None
    evaluated_complete_states = 0
    for (selected_count, _atomic_count), states in states_by_bucket.items():
        if selected_count != leg_count:
            continue
        for state in states:
            evaluated_complete_states += 1
            result = _solver_result_from_variants(
                state.variants,
                pass_type=pass_type,
                unit_stake=unit_stake,
                max_budget=max_budget,
                candidate_fixture_count=candidate_fixture_count,
                fixture_variant_count=fixture_variant_count,
                evaluated_complete_states=evaluated_complete_states,
                generated_state_count=generated_state_count,
                pruned_state_count=pruned_state_count,
                state_limit=states_per_bucket,
                search_mode="dynamic_programming_integer_search",
                exact=False,
            )
            if result is not None and _solver_result_sort_key(result) > (
                _solver_result_sort_key(best_result) if best_result is not None else ()
            ):
                best_result = result
    if best_result is None:
        return None
    return best_result.model_copy(update={"evaluated_complete_states": evaluated_complete_states})


def _solver_result_from_variants(
    variants: Sequence[_FixtureOptionVariant],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    candidate_fixture_count: int,
    fixture_variant_count: int,
    evaluated_complete_states: int,
    generated_state_count: int,
    pruned_state_count: int,
    state_limit: int,
    search_mode: str,
    exact: bool,
) -> _SolverSearchResult | None:
    legs = [variant.leg.model_copy(deep=True) for variant in variants]
    selected_scored = _solver_state_selected_scored(variants)
    evaluation = evaluate_parlay(
        legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
    )
    if evaluation.total_stake > max_budget or not evaluation.rule_valid:
        return None
    return _SolverSearchResult(
        legs=legs,
        selected_scored=selected_scored,
        evaluation=evaluation,
        quality=_parlay_quality(evaluation, selected_scored),
        candidate_fixture_count=candidate_fixture_count,
        fixture_variant_count=fixture_variant_count,
        evaluated_complete_states=evaluated_complete_states,
        generated_state_count=generated_state_count,
        pruned_state_count=pruned_state_count,
        state_limit=state_limit,
        search_mode=search_mode,
        exact=exact,
    )


def _solver_result_sort_key(
    result: _SolverSearchResult | None,
) -> tuple[
    float,
    float,
    float,
    float,
    float,
]:
    if result is None:
        return (-1.0, -1.0, -1.0, -1.0, 0.0)
    return (
        result.quality,
        result.evaluation.expected_value,
        result.evaluation.hit_probability,
        result.evaluation.roi,
        -result.evaluation.total_stake,
    )


def _solver_result_sort_key_from_variants(
    variants: Sequence[_FixtureOptionVariant],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
) -> tuple[float, float, float, float, float]:
    atomic_count = _variant_atomic_count(variants)
    total_stake = unit_stake * atomic_count
    if total_stake > max_budget:
        return _solver_result_sort_key(None)
    hit_probability = 1.0
    expected_payout_factor = 1.0
    is_multiple = False
    for variant in variants:
        hit_probability *= variant.selected_probability
        expected_payout_factor *= sum(
            variant.leg.probabilities[outcome] * variant.leg.odds[outcome]
            for outcome in variant.leg.outcomes
        )
        if len(variant.leg.outcomes) > 1:
            is_multiple = True
    expected_payout = unit_stake * expected_payout_factor
    expected_value = expected_payout - total_stake
    roi = expected_value / total_stake if total_stake > 0 else 0.0
    risk_score = placeholder_risk_score(
        hit_probability=hit_probability,
        total_atomic_bets=atomic_count,
        correlation_penalty=0.0,
    )
    evaluation = ParlayEvaluation(
        pass_type=pass_type,
        is_multiple=is_multiple,
        unit_stake=unit_stake,
        total_atomic_bets=atomic_count,
        total_stake=total_stake,
        hit_probability=hit_probability,
        expected_payout=expected_payout,
        expected_value=expected_value,
        roi=roi,
        risk_score=risk_score,
        risk_level=risk_level_from_score(risk_score),
        rule_valid=True,
    )
    selected_scored = _solver_state_selected_scored(variants)
    return (
        _parlay_quality(evaluation, selected_scored),
        expected_value,
        hit_probability,
        roi,
        -total_stake,
    )


def _estimate_complete_solver_state_count(
    fixture_variant_groups: Sequence[Sequence[_FixtureOptionVariant]],
    *,
    choose_count: int,
    limit: int,
) -> int:
    counts = [0] * (choose_count + 1)
    counts[0] = 1
    for variants in fixture_variant_groups:
        variant_count = len(variants)
        for selected_count in range(choose_count - 1, -1, -1):
            counts[selected_count + 1] += counts[selected_count] * variant_count
            if counts[selected_count + 1] > limit:
                counts[selected_count + 1] = limit + 1
        if counts[choose_count] > limit:
            return counts[choose_count]
    return counts[choose_count]


def _prune_solver_state_buckets(
    states_by_bucket: dict[tuple[int, int], list[_SolverState]],
    *,
    leg_count: int,
    unit_stake: float,
    max_budget: float,
    states_per_bucket: int,
    remaining_group_count: int,
) -> tuple[dict[tuple[int, int], list[_SolverState]], int]:
    pruned_by_bucket: dict[tuple[int, int], list[_SolverState]] = {}
    pruned_count = 0
    for bucket, states in states_by_bucket.items():
        selected_count, _atomic_count = bucket
        if selected_count > leg_count or selected_count + remaining_group_count < leg_count:
            pruned_count += len(states)
            continue
        seen_signatures: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
        unique_states: list[_SolverState] = []
        for state in sorted(
            states,
            key=lambda item: _solver_state_sort_key(
                item,
                leg_count=leg_count,
                unit_stake=unit_stake,
                max_budget=max_budget,
            ),
            reverse=True,
        ):
            signature = _solver_state_signature(state.variants)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            unique_states.append(state)
            if len(unique_states) >= states_per_bucket:
                break
        pruned_count += max(len(states) - len(unique_states), 0)
        pruned_by_bucket[bucket] = unique_states
    return pruned_by_bucket, pruned_count


def _solver_state_sort_key(
    state: _SolverState,
    *,
    leg_count: int,
    unit_stake: float,
    max_budget: float,
) -> tuple[float, int, float, float, float]:
    if not state.variants:
        return (0.0, 0, 0.0, 0.0, 0.0)
    selected_probability_product = state.selected_probability_product
    average_score = (
        state.selected_score_sum / state.selected_score_count if state.selected_score_count else 0.0
    )
    average_variant_quality = state.variant_quality_sum / len(state.variants)
    completion_ratio = len(state.variants) / leg_count
    budget_ratio = state.atomic_count * unit_stake / max_budget
    proxy_score = (
        0.34 * selected_probability_product
        + 0.24 * average_variant_quality
        + 0.20 * average_score
        + 0.17 * completion_ratio
        - 0.05 * budget_ratio
    )
    return (
        proxy_score,
        len(state.variants),
        selected_probability_product,
        average_score,
        -state.atomic_count * unit_stake,
    )


def _solver_state_from_variants(
    variants: Sequence[_FixtureOptionVariant],
    *,
    atomic_count: int,
) -> _SolverState:
    selected_probability_product = 1.0
    selected_score_sum = 0.0
    selected_score_count = 0
    variant_quality_sum = 0.0
    for variant in variants:
        selected_probability_product *= variant.selected_probability
        selected_score_sum += variant.score_sum
        selected_score_count += variant.score_count
        variant_quality_sum += variant.sort_key[0]
    return _SolverState(
        variants=list(variants),
        atomic_count=atomic_count,
        selected_probability_product=selected_probability_product,
        selected_score_sum=selected_score_sum,
        selected_score_count=selected_score_count,
        variant_quality_sum=variant_quality_sum,
    )


def _solver_state_with_variant(
    state: _SolverState,
    variant: _FixtureOptionVariant,
    *,
    atomic_count: int,
) -> _SolverState:
    return _SolverState(
        variants=[*state.variants, variant],
        atomic_count=atomic_count,
        selected_probability_product=(
            state.selected_probability_product * variant.selected_probability
        ),
        selected_score_sum=state.selected_score_sum + variant.score_sum,
        selected_score_count=state.selected_score_count + variant.score_count,
        variant_quality_sum=state.variant_quality_sum + variant.sort_key[0],
    )


def _variant_atomic_count(variants: Sequence[_FixtureOptionVariant]) -> int:
    atomic_count = 1
    for variant in variants:
        atomic_count *= _variant_outcome_count(variant)
    return atomic_count


def _variant_outcome_count(variant: _FixtureOptionVariant) -> int:
    return max(1, len(variant.leg.outcomes))


def _solver_state_signature(
    variants: Sequence[_FixtureOptionVariant],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(sorted((variant.fixture_id, tuple(variant.leg.outcomes)) for variant in variants))


def _solver_state_selected_scored(
    variants: Sequence[_FixtureOptionVariant],
) -> list[ScoredRecommendationCandidate]:
    selected: list[ScoredRecommendationCandidate] = []
    for variant in variants:
        selected.extend(variant.scored_candidates)
    return selected


def _beam_search_budget_constrained_selection(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_candidates: Sequence[RecommendationCandidate],
    leg_count: int,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
    max_outcomes_per_fixture: int,
    beam_width: int = 48,
    candidate_fixture_limit: int = 96,
    per_fixture_variant_limit: int = 8,
) -> _BeamSearchResult | None:
    locked_variants = _locked_fixture_variants(locked_candidates, config=config)
    if len(locked_variants) > leg_count:
        return None
    if _beam_state_minimum_stake(_BeamState(variants=locked_variants), unit_stake) > max_budget:
        return None

    locked_fixture_ids = {candidate.fixture_id for candidate in locked_candidates}
    ranked_candidates = [
        scored
        for scored in rank_candidates(candidates, config=config, as_of_time_utc=as_of_time_utc)
        if scored.candidate.fixture_id not in locked_fixture_ids
    ]
    variants_by_fixture = _beam_fixture_variants_by_fixture(
        ranked_candidates,
        max_outcomes_per_fixture=max_outcomes_per_fixture,
        per_fixture_variant_limit=per_fixture_variant_limit,
    )
    fixture_variant_groups = sorted(
        variants_by_fixture.values(),
        key=_fixture_variant_group_sort_key,
        reverse=True,
    )[:candidate_fixture_limit]

    states = [_BeamState(variants=locked_variants)]
    for variants in fixture_variant_groups:
        next_states = [state.model_copy(deep=True) for state in states]
        for state in states:
            if len(state.variants) >= leg_count:
                continue
            existing_fixture_ids = {variant.fixture_id for variant in state.variants}
            for variant in variants:
                if variant.fixture_id in existing_fixture_ids:
                    continue
                projected_state = _BeamState(variants=[*state.variants, variant])
                if _beam_state_minimum_stake(projected_state, unit_stake) > max_budget:
                    continue
                next_states.append(projected_state)
        states = _prune_beam_states(
            next_states,
            leg_count=leg_count,
            unit_stake=unit_stake,
            max_budget=max_budget,
            beam_width=beam_width,
        )

    best_result: _BeamSearchResult | None = None
    evaluated_complete_states = 0
    fixture_variant_count = sum(len(variants) for variants in fixture_variant_groups)
    for state in states:
        if len(state.variants) != leg_count:
            continue
        legs = _beam_state_legs(state)
        selected_scored = _beam_state_selected_scored(state)
        evaluation = evaluate_parlay(
            legs,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
        )
        evaluated_complete_states += 1
        if evaluation.total_stake > max_budget or not evaluation.rule_valid:
            continue
        quality = _parlay_quality(evaluation, selected_scored)
        result = _BeamSearchResult(
            legs=legs,
            selected_scored=selected_scored,
            evaluation=evaluation,
            quality=quality,
            candidate_fixture_count=len(fixture_variant_groups),
            fixture_variant_count=fixture_variant_count,
            evaluated_complete_states=evaluated_complete_states,
            beam_width=beam_width,
        )
        if best_result is None or result.quality > best_result.quality:
            best_result = result
    if best_result is not None:
        best_result.evaluated_complete_states = evaluated_complete_states
    return best_result


def _locked_fixture_variants(
    locked_candidates: Sequence[RecommendationCandidate],
    *,
    config: RecommendationPolicyConfig,
) -> list[_FixtureOptionVariant]:
    variants: list[_FixtureOptionVariant] = []
    seen_fixture_ids: set[str] = set()
    for candidate in locked_candidates:
        if candidate.fixture_id in seen_fixture_ids:
            continue
        seen_fixture_ids.add(candidate.fixture_id)
        scored = score_candidate(candidate, config=config)
        variants.append(
            _fixture_option_variant(
                fixture_id=candidate.fixture_id,
                leg=candidate.to_leg_selection(),
                scored_candidates=[scored],
            )
        )
    return variants


def _beam_fixture_variants_by_fixture(
    ranked_candidates: Sequence[ScoredRecommendationCandidate],
    *,
    max_outcomes_per_fixture: int,
    per_fixture_variant_limit: int,
) -> dict[str, list[_FixtureOptionVariant]]:
    scored_by_fixture: dict[str, list[ScoredRecommendationCandidate]] = {}
    for scored in ranked_candidates:
        scored_by_fixture.setdefault(scored.candidate.fixture_id, []).append(scored)

    variants_by_fixture: dict[str, list[_FixtureOptionVariant]] = {}
    for fixture_id, fixture_scored in scored_by_fixture.items():
        grouped: dict[
            tuple[str, float | None, str | None],
            list[ScoredRecommendationCandidate],
        ] = {}
        for scored in fixture_scored:
            candidate = scored.candidate
            group_key = (candidate.market_type, candidate.line, candidate.side)
            grouped.setdefault(group_key, []).append(scored)

        fixture_variants: list[_FixtureOptionVariant] = []
        for grouped_scored in grouped.values():
            limited_group = grouped_scored[: max(max_outcomes_per_fixture + 1, 3)]
            max_size = min(max_outcomes_per_fixture, len(limited_group))
            for size in range(1, max_size + 1):
                for combo in combinations(limited_group, size):
                    fixture_variants.append(_fixture_option_variant_from_scored(combo))

        variants_by_fixture[fixture_id] = sorted(
            fixture_variants,
            key=_fixture_option_variant_sort_key,
            reverse=True,
        )[:per_fixture_variant_limit]
    return variants_by_fixture


def _fixture_option_variant_from_scored(
    scored_candidates: Sequence[ScoredRecommendationCandidate],
) -> _FixtureOptionVariant:
    first_candidate = scored_candidates[0].candidate
    leg = first_candidate.to_leg_selection()
    for scored in scored_candidates[1:]:
        leg = _add_candidate_to_leg(leg, scored.candidate)
    return _fixture_option_variant(
        fixture_id=first_candidate.fixture_id,
        leg=leg,
        scored_candidates=list(scored_candidates),
    )


def _fixture_option_variant(
    *,
    fixture_id: str,
    leg: ParlayLegSelection,
    scored_candidates: Sequence[ScoredRecommendationCandidate],
) -> _FixtureOptionVariant:
    selected_probability = sum(leg.probabilities[outcome] for outcome in leg.outcomes)
    score_sum = sum(scored.score for scored in scored_candidates)
    return _FixtureOptionVariant(
        fixture_id=fixture_id,
        leg=leg,
        scored_candidates=list(scored_candidates),
        sort_key=_fixture_option_variant_sort_key_from_parts(leg, scored_candidates),
        selected_probability=selected_probability,
        score_sum=score_sum,
        score_count=len(scored_candidates),
    )


def _prune_beam_states(
    states: Sequence[_BeamState],
    *,
    leg_count: int,
    unit_stake: float,
    max_budget: float,
    beam_width: int,
) -> list[_BeamState]:
    pruned: list[_BeamState] = []
    seen_signatures: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
    for state in sorted(
        states,
        key=lambda item: _beam_state_sort_key(
            item,
            leg_count=leg_count,
            unit_stake=unit_stake,
            max_budget=max_budget,
        ),
        reverse=True,
    ):
        signature = _beam_state_signature(state)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        pruned.append(state)
        if len(pruned) >= beam_width:
            break
    return pruned


def _fixture_variant_group_sort_key(variants: Sequence[_FixtureOptionVariant]) -> float:
    if not variants:
        return 0.0
    return variants[0].sort_key[0]


def _fixture_option_variant_sort_key(
    variant: _FixtureOptionVariant,
) -> tuple[float, float, float, float]:
    return variant.sort_key


def _fixture_option_variant_sort_key_from_parts(
    leg: ParlayLegSelection,
    scored_candidates: Sequence[ScoredRecommendationCandidate],
) -> tuple[float, float, float, float]:
    selected_probability = sum(leg.probabilities[outcome] for outcome in leg.outcomes)
    average_score = sum(scored.score for scored in scored_candidates) / len(scored_candidates)
    expected_return_proxy = sum(
        scored.candidate.probability * (scored.candidate.decimal_odds or 1.0)
        for scored in scored_candidates
    ) / len(scored_candidates)
    calibration_risk = _component_portfolio_pressure(
        scored_candidates,
        "calibration_risk",
    )
    longshot_upset_risk = _component_portfolio_pressure(
        scored_candidates,
        "longshot_upset_risk",
    )
    fragile_favorite_risk = _component_portfolio_pressure(
        scored_candidates,
        "upset_avoidance_penalty",
    )
    option_penalty = 0.015 * (len(leg.outcomes) - 1)
    quality_proxy = (
        0.43 * selected_probability
        + 0.34 * average_score
        + 0.25 * clamp_unit_interval(expected_return_proxy - 0.80)
        - 0.06 * calibration_risk
        - 0.09 * longshot_upset_risk
        - 0.07 * fragile_favorite_risk
        - option_penalty
    )
    return (quality_proxy, selected_probability, average_score, -float(len(leg.outcomes)))


def _variant_component_pressure(
    variant: _FixtureOptionVariant,
    component_name: str,
) -> float:
    return _component_portfolio_pressure(variant.scored_candidates, component_name)


def _beam_state_sort_key(
    state: _BeamState,
    *,
    leg_count: int,
    unit_stake: float,
    max_budget: float,
) -> tuple[float, int, float, float]:
    if not state.variants:
        return (0.0, 0, 0.0, 0.0)
    selected_probability_product = 1.0
    selected_score_sum = 0.0
    selected_score_count = 0
    for variant in state.variants:
        selected_probability_product *= variant.selected_probability
        selected_score_sum += variant.score_sum
        selected_score_count += variant.score_count
    average_score = selected_score_sum / selected_score_count
    completion_ratio = len(state.variants) / leg_count
    budget_ratio = _beam_state_minimum_stake(state, unit_stake) / max_budget
    proxy_score = (
        0.45 * selected_probability_product
        + 0.35 * average_score
        + 0.15 * completion_ratio
        - 0.05 * budget_ratio
    )
    return (
        proxy_score,
        len(state.variants),
        selected_probability_product,
        -_beam_state_minimum_stake(state, unit_stake),
    )


def _beam_state_signature(
    state: _BeamState,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        sorted(
            (
                variant.fixture_id,
                tuple(variant.leg.outcomes),
            )
            for variant in state.variants
        )
    )


def _beam_state_minimum_stake(state: _BeamState, unit_stake: float) -> float:
    atomic_count = 1
    for variant in state.variants:
        atomic_count *= len(variant.leg.outcomes)
    return unit_stake * atomic_count


def _beam_state_legs(state: _BeamState) -> list[ParlayLegSelection]:
    return [variant.leg.model_copy(deep=True) for variant in state.variants]


def _beam_state_selected_scored(state: _BeamState) -> list[ScoredRecommendationCandidate]:
    selected: list[ScoredRecommendationCandidate] = []
    for variant in state.variants:
        selected.extend(variant.scored_candidates)
    return selected


def _rank_addable_options(
    candidates: Sequence[RecommendationCandidate],
    *,
    base_legs: Sequence[ParlayLegSelection],
    selected_keys: set[tuple[str, str, str]],
    blocked_fixture_ids: set[str],
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
) -> list[ScoredRecommendationCandidate]:
    leg_by_fixture = {leg.fixture_id: leg for leg in base_legs}
    options: list[ScoredRecommendationCandidate] = []
    for scored in rank_candidates(candidates, config=config, as_of_time_utc=as_of_time_utc):
        candidate = scored.candidate
        if _candidate_key(candidate) in selected_keys:
            continue
        if candidate.fixture_id in blocked_fixture_ids:
            continue
        leg = leg_by_fixture.get(candidate.fixture_id)
        if leg is None:
            continue
        if as_of_time_utc is not None and candidate.has_started(as_of_time_utc):
            continue
        if not _candidate_matches_leg(candidate, leg):
            continue
        options.append(scored)
    return options


def _search_budget_safe_fixture_replacements(
    candidates: Sequence[RecommendationCandidate],
    *,
    working_legs: Sequence[ParlayLegSelection],
    selected_scored: Sequence[ScoredRecommendationCandidate],
    current_evaluation: ParlayEvaluation,
    current_quality: float,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    locked_fixture_ids: set[str],
    blocked_fixture_ids: set[str],
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
    max_outcomes_per_fixture: int,
    min_quality_gain: float,
) -> _FixtureReplacementSearchResult:
    legs = [leg.model_copy(deep=True) for leg in working_legs]
    scored = _selected_scored_from_legs(legs, selected_scored)
    evaluation = current_evaluation
    quality = current_quality
    decisions: list[FixtureReplacementDecision] = []

    while True:
        best_projection = _find_best_fixture_replacement_projection(
            candidates,
            working_legs=legs,
            selected_scored=scored,
            current_quality=quality,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            locked_fixture_ids=locked_fixture_ids,
            blocked_fixture_ids=blocked_fixture_ids,
            config=config,
            as_of_time_utc=as_of_time_utc,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
            min_quality_gain=min_quality_gain,
        )
        if best_projection is None:
            break
        legs = best_projection.legs
        scored = best_projection.selected_scored
        evaluation = best_projection.evaluation
        quality = best_projection.quality
        decisions.append(
            FixtureReplacementDecision(
                old_fixture_id=best_projection.old_fixture_id,
                new_fixture_id=best_projection.new_fixture_id,
                action="replaced",
                reason_code="budget_safe_unlocked_fixture_replacement",
                quality_delta=best_projection.quality_delta,
                projected_total_stake=best_projection.evaluation.total_stake,
                projected_hit_probability=best_projection.evaluation.hit_probability,
                replacement_outcomes=legs[best_projection.leg_index].outcomes,
            )
        )

    return _FixtureReplacementSearchResult(
        legs=legs,
        selected_scored=scored,
        evaluation=evaluation,
        quality=quality,
        decisions=decisions,
    )


def _find_best_fixture_replacement_projection(
    candidates: Sequence[RecommendationCandidate],
    *,
    working_legs: Sequence[ParlayLegSelection],
    selected_scored: Sequence[ScoredRecommendationCandidate],
    current_quality: float,
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    locked_fixture_ids: set[str],
    blocked_fixture_ids: set[str],
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
    max_outcomes_per_fixture: int,
    min_quality_gain: float,
) -> _ReplacementProjection | None:
    current_fixture_ids = {leg.fixture_id for leg in working_legs}
    replaceable_indices = [
        index
        for index, leg in enumerate(working_legs)
        if leg.fixture_id not in locked_fixture_ids and leg.fixture_id not in blocked_fixture_ids
    ]
    if not replaceable_indices:
        return None

    ranked_replacement_candidates = [
        scored
        for scored in rank_candidates(candidates, config=config, as_of_time_utc=as_of_time_utc)
        if scored.candidate.fixture_id not in current_fixture_ids
        and scored.candidate.fixture_id not in locked_fixture_ids
        and scored.candidate.fixture_id not in blocked_fixture_ids
    ]
    best_projection: _ReplacementProjection | None = None
    required_quality_gain = _replacement_required_quality_gain(min_quality_gain)
    for leg_index in replaceable_indices:
        old_fixture_id = working_legs[leg_index].fixture_id
        base_scored_without_old_fixture = [
            item for item in selected_scored if item.candidate.fixture_id != old_fixture_id
        ]
        for scored_candidate in ranked_replacement_candidates:
            replacement_candidate = scored_candidate.candidate
            if replacement_candidate.fixture_id in current_fixture_ids:
                continue
            replacement_leg = replacement_candidate.to_leg_selection()
            projected_legs = [
                replacement_leg if index == leg_index else leg.model_copy(deep=True)
                for index, leg in enumerate(working_legs)
            ]
            projected_scored = _selected_scored_from_legs(
                projected_legs,
                [*base_scored_without_old_fixture, scored_candidate],
            )
            projected_legs, projected_scored, projected_evaluation, projected_quality = (
                _add_budget_safe_options_for_fixture(
                    candidates,
                    fixture_id=replacement_candidate.fixture_id,
                    working_legs=projected_legs,
                    selected_scored=projected_scored,
                    pass_type=pass_type,
                    unit_stake=unit_stake,
                    max_budget=max_budget,
                    blocked_fixture_ids=blocked_fixture_ids,
                    config=config,
                    as_of_time_utc=as_of_time_utc,
                    max_outcomes_per_fixture=max_outcomes_per_fixture,
                )
            )
            quality_delta = projected_quality - current_quality
            if projected_evaluation.total_stake > max_budget:
                continue
            if quality_delta < required_quality_gain:
                continue
            projection = _ReplacementProjection(
                old_fixture_id=old_fixture_id,
                new_fixture_id=replacement_candidate.fixture_id,
                leg_index=leg_index,
                legs=projected_legs,
                selected_scored=projected_scored,
                evaluation=projected_evaluation,
                quality=projected_quality,
                quality_delta=quality_delta,
            )
            if best_projection is None or projection.sort_key > best_projection.sort_key:
                best_projection = projection
    return best_projection


def _add_budget_safe_options_for_fixture(
    candidates: Sequence[RecommendationCandidate],
    *,
    fixture_id: str,
    working_legs: Sequence[ParlayLegSelection],
    selected_scored: Sequence[ScoredRecommendationCandidate],
    pass_type: str,
    unit_stake: float,
    max_budget: float,
    blocked_fixture_ids: set[str],
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
    max_outcomes_per_fixture: int,
) -> tuple[list[ParlayLegSelection], list[ScoredRecommendationCandidate], ParlayEvaluation, float]:
    legs = [leg.model_copy(deep=True) for leg in working_legs]
    scored = _selected_scored_from_legs(legs, selected_scored)
    evaluation = evaluate_parlay(
        legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
    )
    quality = _parlay_quality(evaluation, scored)
    selected_keys = {_candidate_key(item.candidate) for item in scored}
    fixture_to_leg_index = {leg.fixture_id: index for index, leg in enumerate(legs)}
    leg_index = fixture_to_leg_index[fixture_id]

    while len(legs[leg_index].outcomes) < max_outcomes_per_fixture:
        best_projection: _OptionProjection | None = None
        addable_options = _rank_addable_options(
            candidates,
            base_legs=legs,
            selected_keys=selected_keys,
            blocked_fixture_ids=blocked_fixture_ids,
            config=config,
            as_of_time_utc=as_of_time_utc,
        )
        for addable in addable_options:
            candidate = addable.candidate
            if candidate.fixture_id != fixture_id:
                continue
            leg = legs[leg_index]
            projected_legs = list(legs)
            projected_legs[leg_index] = _add_candidate_to_leg(leg, candidate)
            projected_evaluation = evaluate_parlay(
                projected_legs,
                pass_type=pass_type,
                unit_stake=unit_stake,
                max_budget=max_budget,
            )
            if projected_evaluation.total_stake > max_budget:
                continue
            projected_scored = _selected_scored_from_legs(
                projected_legs,
                [*scored, addable],
            )
            projected_quality = _parlay_quality(projected_evaluation, projected_scored)
            marginal_quality_gain = projected_quality - quality
            if marginal_quality_gain <= 0:
                continue
            projection = _OptionProjection(
                scored_candidate=addable,
                leg_index=leg_index,
                projected_legs=projected_legs,
                projected_evaluation=projected_evaluation,
                projected_quality=projected_quality,
                marginal_quality_gain=marginal_quality_gain,
            )
            if best_projection is None or projection.sort_key > best_projection.sort_key:
                best_projection = projection
        if best_projection is None:
            break
        legs = best_projection.projected_legs
        evaluation = best_projection.projected_evaluation
        quality = best_projection.projected_quality
        scored = _selected_scored_from_legs(
            legs,
            [*scored, best_projection.scored_candidate],
        )
        selected_keys.add(_candidate_key(best_projection.scored_candidate.candidate))

    return legs, scored, evaluation, quality


def _candidate_matches_leg(
    candidate: RecommendationCandidate,
    leg: ParlayLegSelection,
) -> bool:
    return (
        candidate.market_type == leg.market_type
        and _nullable_float_equal(candidate.line, leg.line)
        and candidate.side == leg.side
    )


def _nullable_float_equal(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return isclose(left, right, abs_tol=1e-9)


def _add_candidate_to_leg(
    leg: ParlayLegSelection,
    candidate: RecommendationCandidate,
) -> ParlayLegSelection:
    if candidate.decimal_odds is None:
        raise ValueError("decimal_odds is required for multiple parlay option")
    if not _candidate_matches_leg(candidate, leg):
        raise ValueError("multiple parlay options must match the base leg market")
    if candidate.outcome in leg.outcomes:
        return leg.model_copy(deep=True)
    return leg.model_copy(
        deep=True,
        update={
            "outcomes": [*leg.outcomes, candidate.outcome],
            "probabilities": {
                **leg.probabilities,
                candidate.outcome: candidate.probability,
            },
            "odds": {
                **leg.odds,
                candidate.outcome: candidate.decimal_odds,
            },
        },
    )


def _parlay_quality(
    evaluation: ParlayEvaluation,
    selected_candidates: Sequence[ScoredRecommendationCandidate],
) -> float:
    average_candidate_score = (
        sum(item.score for item in selected_candidates) / len(selected_candidates)
        if selected_candidates
        else 0.0
    )
    roi_component = clamp_unit_interval(0.50 + evaluation.roi / 2.0)
    ev_component = clamp_unit_interval(
        0.50 + evaluation.expected_value / max(evaluation.total_stake, 1.0) / 2.0
    )
    risk_component = 1.0 - evaluation.risk_score
    calibration_risk = _component_portfolio_pressure(
        selected_candidates,
        "calibration_risk",
    )
    longshot_upset_risk = _component_portfolio_pressure(
        selected_candidates,
        "longshot_upset_risk",
    )
    fragile_favorite_risk = _component_portfolio_pressure(
        selected_candidates,
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
    selected_candidates: Sequence[ScoredRecommendationCandidate],
    component_name: str,
) -> float:
    retained_probability = 1.0
    has_component = False
    for scored in selected_candidates:
        component_value = scored.component_scores.get(component_name)
        if component_value is None:
            continue
        has_component = True
        retained_probability *= 1.0 - clamp_unit_interval(component_value)
    if not has_component:
        return 0.0
    return clamp_unit_interval(1.0 - retained_probability)


def _selected_outcomes_by_fixture(
    legs: Sequence[ParlayLegSelection],
) -> dict[str, list[str]]:
    return {leg.fixture_id: list(leg.outcomes) for leg in legs}


def _selected_scored_from_legs(
    legs: Sequence[ParlayLegSelection],
    selected_scored: Sequence[ScoredRecommendationCandidate],
) -> list[ScoredRecommendationCandidate]:
    scored_by_key = {_candidate_key(item.candidate): item for item in selected_scored}
    result: list[ScoredRecommendationCandidate] = []
    for leg in legs:
        for outcome in leg.outcomes:
            key = (leg.fixture_id, leg.market_type, outcome)
            scored = scored_by_key.get(key)
            if scored is not None:
                result.append(scored)
    return result


def _candidate_key(candidate: RecommendationCandidate) -> tuple[str, str, str]:
    return (candidate.fixture_id, candidate.market_type, candidate.outcome)


def _market_type_for_removed_option(
    legs: Sequence[ParlayLegSelection],
    *,
    fixture_id: str,
) -> str:
    for leg in legs:
        if leg.fixture_id == fixture_id:
            return leg.market_type
    return "unknown"
