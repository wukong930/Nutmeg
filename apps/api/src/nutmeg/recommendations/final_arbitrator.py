from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.recommendations.competition_profiles import (
    CompetitionFinalAnswerValueGuard,
    CompetitionRecommendationProfile,
    competition_recommendation_profile_index,
    default_competition_recommendation_profile_index,
    default_competition_recommendation_profile_version,
)
from nutmeg.recommendations.models import (
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.upset_policy import (
    aggregate_upset_quality,
    build_upset_policy_payload,
)


class RecommendationFinalAnswerOption(Protocol):
    @property
    def option_key(self) -> str: ...

    @property
    def option_type(self) -> str: ...

    @property
    def pass_type(self) -> str: ...

    @property
    def mode(self) -> RecommendationMode: ...

    @property
    def planner_score(self) -> float: ...

    @property
    def within_budget(self) -> bool: ...

    @property
    def selection(self) -> RecommendationSelection: ...


class RecommendationFinalAnswerScore(BaseModel):
    option_key: str
    final_answer_score: float = Field(ge=0.0, le=1.0)
    score_components: dict[str, float] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    calculation_basis: str = "final_answer_arbitrator_v3_1"


CORE_FIRST_FINAL_ANSWER_WEIGHTS = {
    "planner": 0.20,
    "hit_probability": 0.15,
    "roi": 0.26,
    "risk": 0.10,
    "data_quality": 0.08,
    "budget_efficiency": 0.04,
    "stake_discipline": 0.13,
    "fixture_depth": 0.01,
    "answer_type": 0.03,
}
MULTIPLE_COVERAGE_TIE_BREAKER_ADJUSTMENT = 0.003


def rank_final_answer_options[OptionT: RecommendationFinalAnswerOption](
    options: Sequence[OptionT],
    *,
    competition_profiles: Sequence[CompetitionRecommendationProfile] | None = None,
) -> list[OptionT]:
    profile_index = _resolved_profile_index(competition_profiles)
    return sorted(
        options,
        key=lambda option: final_answer_sort_key(
            option,
            competition_profile_index=profile_index,
        ),
        reverse=True,
    )


def final_answer_sort_key(
    option: RecommendationFinalAnswerOption,
    *,
    competition_profile_index: (dict[str, CompetitionRecommendationProfile] | None) = None,
) -> tuple[float, float, float, float, float, int]:
    evaluation = option.selection.evaluation
    score = score_final_answer_option(
        option,
        competition_profile_index=competition_profile_index,
    )
    data_quality = _average(
        item.candidate.data_quality_score for item in option.selection.selected_candidates
    )
    return (
        score.final_answer_score,
        evaluation.hit_probability,
        evaluation.roi,
        1.0 - evaluation.risk_score,
        data_quality / 100.0 if data_quality is not None else 0.0,
        len(option.selection.fixture_ids),
    )


def score_final_answer_option(
    option: RecommendationFinalAnswerOption,
    *,
    competition_profiles: Sequence[CompetitionRecommendationProfile] | None = None,
    competition_profile_index: (dict[str, CompetitionRecommendationProfile] | None) = None,
) -> RecommendationFinalAnswerScore:
    evaluation = option.selection.evaluation
    profile_index = (
        competition_profile_index
        if competition_profile_index is not None
        else _resolved_profile_index(competition_profiles)
    )
    competition_profile_adjustment = _competition_profile_adjustment(
        option,
        profile_index=profile_index,
    )
    competition_value_guard_penalty = _competition_value_guard_penalty(
        option,
        profile_index=profile_index,
    )
    budget_adjustment_quality = _budget_adjustment_quality_component(option.selection)
    budget_adjustment_penalty = _budget_adjustment_penalty_component(option.selection)
    multiple_coverage_adjustment = _multiple_coverage_adjustment(option)
    if not evaluation.rule_valid or not option.within_budget:
        return RecommendationFinalAnswerScore(
            option_key=option.option_key,
            final_answer_score=0.0,
            score_components={
                "planner": _clamp(option.planner_score),
                "hit_probability": _clamp(evaluation.hit_probability),
                "roi": _roi_component(evaluation.roi),
                "risk": _clamp(1.0 - evaluation.risk_score),
                "data_quality": _data_quality_component(option.selection),
                "budget_efficiency": _budget_efficiency_component(option.selection),
                "stake_discipline": _stake_discipline_component(option.selection),
                "competition_profile_adjustment": competition_profile_adjustment,
                "competition_value_guard_penalty": competition_value_guard_penalty,
                "budget_adjustment_quality": budget_adjustment_quality,
                "budget_adjustment_penalty": budget_adjustment_penalty,
                "multiple_coverage_adjustment": multiple_coverage_adjustment,
                "fixture_depth": _fixture_depth_component(option.selection),
                "answer_type": _answer_type_component(option),
                "upset_quality_diagnostic": _upset_quality_component(option.selection),
            },
            reason_codes=_reason_codes(
                option,
                competition_profile_adjustment=competition_profile_adjustment,
                competition_value_guard_penalty=competition_value_guard_penalty,
                budget_adjustment_penalty=budget_adjustment_penalty,
                multiple_coverage_adjustment=multiple_coverage_adjustment,
            ),
        )

    components = {
        "planner": _clamp(option.planner_score),
        "hit_probability": _clamp(evaluation.hit_probability),
        "roi": _roi_component(evaluation.roi),
        "risk": _clamp(1.0 - evaluation.risk_score),
        "data_quality": _data_quality_component(option.selection),
        "budget_efficiency": _budget_efficiency_component(option.selection),
        "stake_discipline": _stake_discipline_component(option.selection),
        "competition_profile_adjustment": competition_profile_adjustment,
        "competition_value_guard_penalty": competition_value_guard_penalty,
        "budget_adjustment_quality": budget_adjustment_quality,
        "budget_adjustment_penalty": budget_adjustment_penalty,
        "multiple_coverage_adjustment": multiple_coverage_adjustment,
        "fixture_depth": _fixture_depth_component(option.selection),
        "answer_type": _answer_type_component(option),
        "upset_quality_diagnostic": _upset_quality_component(option.selection),
    }
    score = (
        CORE_FIRST_FINAL_ANSWER_WEIGHTS["planner"] * components["planner"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["hit_probability"] * components["hit_probability"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["roi"] * components["roi"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["risk"] * components["risk"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["data_quality"] * components["data_quality"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["budget_efficiency"] * components["budget_efficiency"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["stake_discipline"] * components["stake_discipline"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["fixture_depth"] * components["fixture_depth"]
        + CORE_FIRST_FINAL_ANSWER_WEIGHTS["answer_type"] * components["answer_type"]
        + components["competition_profile_adjustment"]
        + components["multiple_coverage_adjustment"]
        - components["competition_value_guard_penalty"]
        - components["budget_adjustment_penalty"]
    )
    return RecommendationFinalAnswerScore(
        option_key=option.option_key,
        final_answer_score=_clamp(score),
        score_components=components,
        reason_codes=_reason_codes(
            option,
            competition_profile_adjustment=competition_profile_adjustment,
            competition_value_guard_penalty=competition_value_guard_penalty,
            budget_adjustment_penalty=budget_adjustment_penalty,
            multiple_coverage_adjustment=multiple_coverage_adjustment,
        ),
    )


def build_final_answer_arbitration_payload(
    option: RecommendationFinalAnswerOption,
    *,
    rank: int,
    candidate_count: int,
) -> dict[str, object]:
    score = score_final_answer_option(option)
    market_types = _market_types(option.selection)
    return {
        "calculation_basis": score.calculation_basis,
        "rank": rank,
        "candidate_count": candidate_count,
        "option_key": option.option_key,
        "answer_type": option.option_type,
        "pass_type": option.pass_type,
        "mode": option.mode,
        "fixture_count": len(option.selection.fixture_ids),
        "market_types": market_types,
        "market_count": len(market_types),
        "dynamic_mixed_market_answer": len(market_types) > 1,
        "selected_candidate_count": len(option.selection.selected_candidates),
        "multiple_choice_fixture_count": _multiple_choice_fixture_count(
            option.selection
        ),
        "final_answer_score": score.final_answer_score,
        "score_components": score.score_components,
        "upset_policy": build_upset_policy_payload(
            [item.candidate for item in option.selection.selected_candidates]
        ),
        "reason_codes": score.reason_codes,
        "profile_version": default_competition_recommendation_profile_version(),
    }


def final_answer_reason_codes(
    option: RecommendationFinalAnswerOption,
    *,
    competition_profiles: Sequence[CompetitionRecommendationProfile] | None = None,
) -> list[str]:
    profile_index = _resolved_profile_index(competition_profiles)
    return _reason_codes(
        option,
        competition_profile_adjustment=_competition_profile_adjustment(
            option,
            profile_index=profile_index,
        ),
        competition_value_guard_penalty=_competition_value_guard_penalty(
            option,
            profile_index=profile_index,
        ),
        budget_adjustment_penalty=_budget_adjustment_penalty_component(option.selection),
        multiple_coverage_adjustment=_multiple_coverage_adjustment(option),
    )


def _reason_codes(
    option: RecommendationFinalAnswerOption,
    *,
    competition_profile_adjustment: float,
    competition_value_guard_penalty: float,
    budget_adjustment_penalty: float,
    multiple_coverage_adjustment: float,
) -> list[str]:
    evaluation = option.selection.evaluation
    reason_codes = ["final_answer_candidate"]
    if evaluation.rule_valid:
        reason_codes.append("rule_valid")
    if option.within_budget:
        reason_codes.append("within_budget")
    if evaluation.expected_value > 0:
        reason_codes.append("positive_expected_value")
    if evaluation.hit_probability >= 0.50:
        reason_codes.append("strong_hit_probability")
    if evaluation.risk_score <= 0.60:
        reason_codes.append("risk_within_range")
    if evaluation.is_multiple:
        reason_codes.append("multiple_answer")
    elif option.pass_type == "1x1":
        reason_codes.append("standalone_single_answer")
    else:
        reason_codes.append("single_parlay_answer")
    market_types = _market_types(option.selection)
    if len(market_types) > 1:
        reason_codes.append("mixed_market_answer")
    if _multiple_choice_fixture_count(option.selection) > 0:
        reason_codes.append("includes_multiple_choice_leg")
    if any(
        market_type in {"cn_handicap_1x2", "european_handicap_1x2"}
        for market_type in market_types
    ):
        reason_codes.append("includes_handicap_market")
    if any(
        item.candidate.market_type == "correct_score"
        for item in option.selection.selected_candidates
    ):
        reason_codes.append("includes_correct_score_market")
    if abs(competition_profile_adjustment) > 1e-12:
        reason_codes.append("competition_profile_adjustment_applied")
    if competition_value_guard_penalty > 1e-12:
        reason_codes.append("competition_value_guard_applied")
    if _budget_adjustment_payload(option.selection) is not None:
        reason_codes.append("budget_adjustment_applied")
    if budget_adjustment_penalty > 1e-12:
        reason_codes.append("budget_adjustment_quality_penalty_applied")
    if multiple_coverage_adjustment > 1e-12:
        reason_codes.append("multiple_coverage_tie_breaker_applied")
    if _budget_adjustment_warning_codes(option.selection):
        reason_codes.append("budget_adjustment_warning")
    return reason_codes


def _roi_component(roi: float) -> float:
    return _clamp(0.50 + roi / 2.0)


def _data_quality_component(selection: RecommendationSelection) -> float:
    data_quality = _average(
        item.candidate.data_quality_score for item in selection.selected_candidates
    )
    if data_quality is None:
        return 0.0
    return _clamp(data_quality / 100.0)


def _budget_efficiency_component(selection: RecommendationSelection) -> float:
    budget_payload = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget_payload, dict):
        return 1.0
    return 1.0 if budget_payload.get("within_budget", True) else 0.0


def _stake_discipline_component(selection: RecommendationSelection) -> float:
    evaluation = selection.evaluation
    if evaluation.total_stake <= 0:
        return 0.0
    unit_stake_ratio = _clamp(evaluation.unit_stake / evaluation.total_stake)
    if evaluation.roi <= 0:
        return unit_stake_ratio
    return _clamp(0.50 + 0.50 * unit_stake_ratio)


def _fixture_depth_component(selection: RecommendationSelection) -> float:
    return _clamp(len(selection.fixture_ids) / 8.0)


def _answer_type_component(option: RecommendationFinalAnswerOption) -> float:
    if option.option_type == "single_parlay":
        return 1.0
    if option.option_type == "multiple_parlay":
        return 0.95
    return 0.85


def _multiple_coverage_adjustment(option: RecommendationFinalAnswerOption) -> float:
    evaluation = option.selection.evaluation
    if option.mode != "multiple" or not evaluation.is_multiple:
        return 0.0
    if evaluation.total_atomic_bets <= 1:
        return 0.0
    return MULTIPLE_COVERAGE_TIE_BREAKER_ADJUSTMENT


def _upset_quality_component(selection: RecommendationSelection) -> float:
    return aggregate_upset_quality([item.candidate for item in selection.selected_candidates])


def _market_types(selection: RecommendationSelection) -> list[str]:
    return sorted({item.candidate.market_type for item in selection.selected_candidates})


def _multiple_choice_fixture_count(selection: RecommendationSelection) -> int:
    outcome_counts_by_fixture: dict[str, int] = {}
    for item in selection.selected_candidates:
        outcome_counts_by_fixture[item.candidate.fixture_id] = (
            outcome_counts_by_fixture.get(item.candidate.fixture_id, 0) + 1
        )
    return sum(1 for count in outcome_counts_by_fixture.values() if count > 1)


def _competition_profile_adjustment(
    option: RecommendationFinalAnswerOption,
    *,
    profile_index: dict[str, CompetitionRecommendationProfile],
) -> float:
    competition_id = _single_competition_id(option.selection)
    if competition_id is None:
        return 0.0
    profile = profile_index.get(competition_id)
    if profile is None:
        return 0.0
    return profile.final_answer_adjustment(
        pass_type=option.pass_type,
        mode=option.mode,
    )


def _competition_value_guard_penalty(
    option: RecommendationFinalAnswerOption,
    *,
    profile_index: dict[str, CompetitionRecommendationProfile],
) -> float:
    selected = option.selection.selected_candidates
    if not selected:
        return 0.0
    total_penalty = 0.0
    for scored in selected:
        competition_id = _candidate_competition_id(scored.candidate.metadata_json)
        if competition_id is None:
            continue
        profile = profile_index.get(competition_id)
        if profile is None:
            continue
        for guard in profile.final_answer_value_guards:
            if _value_guard_applies(scored, guard):
                total_penalty += guard.penalty_strength
    return _clamp(total_penalty / len(selected))


def _budget_adjustment_quality_component(selection: RecommendationSelection) -> float:
    adjustment = _budget_adjustment_payload(selection)
    if adjustment is None:
        return 1.0
    original_quality = _numeric(adjustment.get("original_quality_score"))
    optimized_quality = _numeric(adjustment.get("optimized_quality_score"))
    original_atomic_bets = _numeric(adjustment.get("original_total_atomic_bets"))
    optimized_atomic_bets = _numeric(adjustment.get("optimized_total_atomic_bets"))
    quality_retention = (
        _clamp(optimized_quality / original_quality)
        if original_quality is not None
        and original_quality > 0
        and optimized_quality is not None
        else 0.50
    )
    atomic_retention = (
        _clamp(optimized_atomic_bets / original_atomic_bets)
        if original_atomic_bets is not None
        and original_atomic_bets > 0
        and optimized_atomic_bets is not None
        else 0.50
    )
    warning_component = (
        0.0 if _budget_adjustment_warning_codes(selection) else 1.0
    )
    return _clamp(
        0.65 * quality_retention
        + 0.25 * atomic_retention
        + 0.10 * warning_component
    )


def _budget_adjustment_penalty_component(selection: RecommendationSelection) -> float:
    adjustment = _budget_adjustment_payload(selection)
    if adjustment is None:
        return 0.0
    quality = _budget_adjustment_quality_component(selection)
    warning_penalty = 0.04 if _budget_adjustment_warning_codes(selection) else 0.0
    return min(0.20, max(0.0, (1.0 - quality) * 0.16 + warning_penalty))


def _budget_adjustment_payload(
    selection: RecommendationSelection,
) -> dict[str, object] | None:
    payload = selection.explanation_json.get("budget_adjustment")
    if isinstance(payload, dict):
        return payload
    return None


def _budget_adjustment_warning_codes(selection: RecommendationSelection) -> list[str]:
    adjustment = _budget_adjustment_payload(selection)
    if adjustment is None:
        return []
    raw_codes = adjustment.get("warning_codes", [])
    if not isinstance(raw_codes, list):
        return []
    return [str(code) for code in raw_codes if str(code)]


def _numeric(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _value_guard_applies(
    scored: ScoredRecommendationCandidate,
    guard: CompetitionFinalAnswerValueGuard,
) -> bool:
    candidate = scored.candidate
    if candidate.decimal_odds is None:
        return False
    if candidate.probability < guard.probability_min:
        return False
    if candidate.probability >= guard.probability_max:
        return False
    if candidate.decimal_odds < guard.min_decimal_odds:
        return False
    if guard.max_decimal_odds is not None and candidate.decimal_odds > guard.max_decimal_odds:
        return False
    if (
        guard.max_model_edge is not None
        and candidate.effective_model_edge() >= guard.max_model_edge
    ):
        return False
    if scored.score < guard.score_min:
        return False
    return scored.score <= guard.score_max


def _single_competition_id(selection: RecommendationSelection) -> str | None:
    competition_ids: set[str] = set()
    for item in selection.selected_candidates:
        competition_id = _candidate_competition_id(item.candidate.metadata_json)
        if competition_id is not None:
            competition_ids.add(competition_id)
    if len(competition_ids) != 1:
        return None
    return next(iter(competition_ids))


def _candidate_competition_id(metadata_json: dict[str, object]) -> str | None:
    raw_competition_id = metadata_json.get("competition_id")
    if isinstance(raw_competition_id, str) and raw_competition_id:
        return raw_competition_id
    return None


def _resolved_profile_index(
    profiles: Sequence[CompetitionRecommendationProfile] | None,
) -> dict[str, CompetitionRecommendationProfile]:
    if profiles is None:
        return default_competition_recommendation_profile_index()
    return competition_recommendation_profile_index(tuple(profiles))


def _average(values: Iterable[float]) -> float | None:
    collected = [float(value) for value in values]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
