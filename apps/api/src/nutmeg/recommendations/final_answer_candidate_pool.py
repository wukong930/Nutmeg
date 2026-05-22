from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import (
    RecommendationMode,
    RecommendationSelection,
)
from nutmeg.recommendations.multiple_value_admission import (
    MultipleValueAdmissionSummary,
    build_multiple_value_admission_summary,
)


class FinalAnswerCandidatePoolOption(Protocol):
    @property
    def option_key(self) -> str: ...

    @property
    def option_type(self) -> str: ...

    @property
    def pass_type(self) -> str: ...

    @property
    def mode(self) -> RecommendationMode: ...

    @property
    def within_budget(self) -> bool: ...

    @property
    def selection(self) -> RecommendationSelection: ...


class UnifiedFinalAnswerCandidateFamily(BaseModel):
    family_key: str
    option_type: str
    pass_type: str
    mode: RecommendationMode
    generated_count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    fixture_counts: list[int] = Field(default_factory=list)
    multiple_value_candidate_count: int = Field(default=0, ge=0)
    multiple_value_admitted_count: int = Field(default=0, ge=0)
    multiple_value_rejected_count: int = Field(default=0, ge=0)
    multiple_extra_option_count: int = Field(default=0, ge=0)
    selected: bool = False


class UnifiedFinalAnswerCandidatePool(BaseModel):
    calculation_basis: str = "unified_final_answer_candidate_pool_v3_2"
    candidate_count: int = Field(ge=0)
    valid_candidate_count: int = Field(ge=0)
    family_count: int = Field(ge=0)
    selected_option_key: str | None = None
    selected_family_key: str | None = None
    selected_pass_type: str | None = None
    selected_mode: RecommendationMode | None = None
    candidate_family_keys: list[str] = Field(default_factory=list)
    pass_types: list[str] = Field(default_factory=list)
    modes: list[RecommendationMode] = Field(default_factory=list)
    market_types: list[str] = Field(default_factory=list)
    families: list[UnifiedFinalAnswerCandidateFamily] = Field(default_factory=list)
    standalone_single_family_count: int = Field(ge=0)
    single_parlay_family_count: int = Field(ge=0)
    multiple_parlay_family_count: int = Field(ge=0)
    two_x_one_is_candidate_family: bool
    correct_score_candidate_present: bool
    handicap_candidate_present: bool
    multiple_value_candidate_count: int = Field(default=0, ge=0)
    multiple_value_admitted_candidate_count: int = Field(default=0, ge=0)
    multiple_value_rejected_candidate_count: int = Field(default=0, ge=0)
    multiple_value_extra_option_count: int = Field(default=0, ge=0)
    selected_multiple_value_status: str | None = None
    selected_multiple_value_admitted: bool | None = None
    selected_multiple_extra_option_count: int = Field(default=0, ge=0)
    multiple_value_rejection_reason_counts: dict[str, int] = Field(
        default_factory=dict
    )


def build_unified_final_answer_candidate_pool(
    options: Sequence[FinalAnswerCandidatePoolOption],
    *,
    selected_option: FinalAnswerCandidatePoolOption | None = None,
) -> UnifiedFinalAnswerCandidatePool:
    selected_family_key = (
        _family_key(selected_option) if selected_option is not None else None
    )
    multiple_value_summaries = {
        option.option_key: build_multiple_value_admission_summary(option.selection)
        for option in options
    }
    families = _candidate_families(
        options,
        selected_family_key=selected_family_key,
        multiple_value_summaries=multiple_value_summaries,
    )
    market_types = _ordered_unique(
        market_type
        for option in options
        for market_type in _selection_market_types(option.selection)
    )
    pass_types = _ordered_unique(option.pass_type for option in options)
    modes = _ordered_unique(option.mode for option in options)
    valid_count = sum(1 for option in options if _is_valid_final_answer_option(option))
    selected_multiple_value_summary = (
        multiple_value_summaries.get(selected_option.option_key)
        if selected_option is not None
        else None
    )
    multiple_value_candidates = [
        summary
        for summary in multiple_value_summaries.values()
        if summary.extra_option_count > 0
    ]
    return UnifiedFinalAnswerCandidatePool(
        candidate_count=len(options),
        valid_candidate_count=valid_count,
        family_count=len(families),
        selected_option_key=(
            selected_option.option_key if selected_option is not None else None
        ),
        selected_family_key=selected_family_key,
        selected_pass_type=selected_option.pass_type if selected_option is not None else None,
        selected_mode=selected_option.mode if selected_option is not None else None,
        candidate_family_keys=[family.family_key for family in families],
        pass_types=pass_types,
        modes=modes,
        market_types=market_types,
        families=families,
        standalone_single_family_count=sum(
            1 for family in families if family.option_type == "standalone_single"
        ),
        single_parlay_family_count=sum(
            1 for family in families if family.option_type == "single_parlay"
        ),
        multiple_parlay_family_count=sum(
            1 for family in families if family.option_type == "multiple_parlay"
        ),
        two_x_one_is_candidate_family=any(
            family.pass_type == "2x1" for family in families
        ),
        correct_score_candidate_present="correct_score" in market_types,
        handicap_candidate_present=any(
            market_type in {"cn_handicap_1x2", "european_handicap_1x2"}
            for market_type in market_types
        ),
        multiple_value_candidate_count=len(multiple_value_candidates),
        multiple_value_admitted_candidate_count=sum(
            1 for summary in multiple_value_candidates if summary.admitted
        ),
        multiple_value_rejected_candidate_count=sum(
            1 for summary in multiple_value_candidates if not summary.admitted
        ),
        multiple_value_extra_option_count=sum(
            summary.extra_option_count for summary in multiple_value_candidates
        ),
        selected_multiple_value_status=(
            selected_multiple_value_summary.status
            if selected_multiple_value_summary is not None
            else None
        ),
        selected_multiple_value_admitted=(
            selected_multiple_value_summary.admitted
            if selected_multiple_value_summary is not None
            else None
        ),
        selected_multiple_extra_option_count=(
            selected_multiple_value_summary.extra_option_count
            if selected_multiple_value_summary is not None
            else 0
        ),
        multiple_value_rejection_reason_counts=_rejection_reason_counts(
            multiple_value_candidates
        ),
    )


def _candidate_families(
    options: Sequence[FinalAnswerCandidatePoolOption],
    *,
    selected_family_key: str | None,
    multiple_value_summaries: dict[str, MultipleValueAdmissionSummary],
) -> list[UnifiedFinalAnswerCandidateFamily]:
    families: dict[str, UnifiedFinalAnswerCandidateFamily] = {}
    for option in options:
        family_key = _family_key(option)
        existing = families.get(family_key)
        market_types = _selection_market_types(option.selection)
        fixture_count = len(option.selection.fixture_ids)
        multiple_value_summary = multiple_value_summaries[option.option_key]
        is_multiple_value_candidate = multiple_value_summary.extra_option_count > 0
        multiple_value_admitted_count = (
            1 if is_multiple_value_candidate and multiple_value_summary.admitted else 0
        )
        multiple_value_rejected_count = (
            1 if is_multiple_value_candidate and not multiple_value_summary.admitted else 0
        )
        if existing is None:
            families[family_key] = UnifiedFinalAnswerCandidateFamily(
                family_key=family_key,
                option_type=option.option_type,
                pass_type=option.pass_type,
                mode=option.mode,
                generated_count=1,
                valid_count=1 if _is_valid_final_answer_option(option) else 0,
                market_types=market_types,
                fixture_counts=[fixture_count],
                multiple_value_candidate_count=(
                    1 if is_multiple_value_candidate else 0
                ),
                multiple_value_admitted_count=multiple_value_admitted_count,
                multiple_value_rejected_count=multiple_value_rejected_count,
                multiple_extra_option_count=multiple_value_summary.extra_option_count,
                selected=family_key == selected_family_key,
            )
            continue
        families[family_key] = existing.model_copy(
            update={
                "generated_count": existing.generated_count + 1,
                "valid_count": existing.valid_count
                + (1 if _is_valid_final_answer_option(option) else 0),
                "market_types": _ordered_unique(
                    [*existing.market_types, *market_types]
                ),
                "fixture_counts": _ordered_unique(
                    [*existing.fixture_counts, fixture_count]
                ),
                "multiple_value_candidate_count": (
                    existing.multiple_value_candidate_count
                    + (1 if is_multiple_value_candidate else 0)
                ),
                "multiple_value_admitted_count": (
                    existing.multiple_value_admitted_count
                    + multiple_value_admitted_count
                ),
                "multiple_value_rejected_count": (
                    existing.multiple_value_rejected_count
                    + multiple_value_rejected_count
                ),
                "multiple_extra_option_count": (
                    existing.multiple_extra_option_count
                    + multiple_value_summary.extra_option_count
                ),
                "selected": existing.selected or family_key == selected_family_key,
            }
        )
    return list(families.values())


def _family_key(option: FinalAnswerCandidatePoolOption) -> str:
    return f"{option.option_type}:{option.pass_type}:{option.mode}"


def _selection_market_types(selection: RecommendationSelection) -> list[str]:
    return _ordered_unique(
        item.candidate.market_type for item in selection.selected_candidates
    )


def _is_valid_final_answer_option(option: FinalAnswerCandidatePoolOption) -> bool:
    return option.selection.evaluation.rule_valid and option.within_budget


def _rejection_reason_counts(
    summaries: Sequence[MultipleValueAdmissionSummary],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for summary in summaries:
        for reason, count in summary.rejection_reason_counts.items():
            counts[reason] = counts.get(reason, 0) + count
    return dict(sorted(counts.items()))


def _ordered_unique[ItemT](values: Iterable[ItemT]) -> list[ItemT]:
    result: list[ItemT] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result
