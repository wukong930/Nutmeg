from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationPolicyConfig,
    RecommendationSelection,
)
from nutmeg.recommendations.optimizer import (
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)
from nutmeg.recommendations.policy import (
    parse_pass_type_leg_count,
    score_candidate,
)

type PrematchLifecycleBacktestStageStatus = Literal["selected", "no_selection"]


class PrematchRecommendationBacktestCheckpoint(BaseModel):
    checkpoint_id: str
    as_of_time_utc: datetime
    candidates: list[RecommendationCandidate]
    locked_fixture_ids: list[str] = Field(default_factory=list)
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    incident_notes: dict[str, str] = Field(default_factory=dict)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PrematchRecommendationLifecycleStage(BaseModel):
    checkpoint_id: str
    as_of_time_utc: datetime
    status: PrematchLifecycleBacktestStageStatus
    selection: RecommendationSelection | None = None
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    preserved_locked_fixture_ids: list[str] = Field(default_factory=list)
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    started_unlocked_fixture_ids: list[str] = Field(default_factory=list)
    started_locked_fixture_ids: list[str] = Field(default_factory=list)
    continuation_fixture_ids: list[str] = Field(default_factory=list)
    remaining_open_leg_count: int = Field(default=0, ge=0)
    changed_fixture_ids: list[str] = Field(default_factory=list)
    event_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation_json: dict[str, object] = Field(default_factory=dict)


class PrematchRecommendationLifecycleBacktestResult(BaseModel):
    pass_type: str
    mode: RecommendationMode
    unit_stake: float = Field(gt=0.0)
    max_budget: float | None = Field(default=None, gt=0.0)
    stages: list[PrematchRecommendationLifecycleStage] = Field(default_factory=list)
    final_selection: RecommendationSelection | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_prematch_recommendation_lifecycle_backtest(
    checkpoints: Sequence[PrematchRecommendationBacktestCheckpoint],
    *,
    pass_type: str,
    mode: RecommendationMode,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig | None = None,
    max_outcomes_per_fixture: int = 2,
    min_marginal_quality_gain: float = 0.0,
) -> PrematchRecommendationLifecycleBacktestResult:
    if not checkpoints:
        raise ValueError("at least one prematch lifecycle checkpoint is required")

    resolved_config = config or RecommendationPolicyConfig()
    leg_count = parse_pass_type_leg_count(pass_type)
    stages: list[PrematchRecommendationLifecycleStage] = []
    locked_candidate_by_fixture: dict[str, RecommendationCandidate] = {}
    previous_selection: RecommendationSelection | None = None

    for checkpoint in sorted(checkpoints, key=lambda item: item.as_of_time_utc):
        as_of_time_utc = _aware_utc(checkpoint.as_of_time_utc)
        checkpoint_locked_fixture_ids = _dedupe_strings(checkpoint.locked_fixture_ids)
        checkpoint_excluded_fixture_ids = _dedupe_strings(checkpoint.excluded_fixture_ids)
        warnings: list[str] = []
        event_codes: list[str] = []

        for fixture_id in checkpoint_locked_fixture_ids:
            locked_candidate = _resolve_locked_candidate(
                fixture_id,
                previous_selection=previous_selection,
                candidates=checkpoint.candidates,
                config=resolved_config,
            )
            if locked_candidate is None:
                warnings.append(f"locked_fixture_candidate_unavailable:{fixture_id}")
                continue
            locked_candidate_by_fixture[fixture_id] = locked_candidate

        active_locked_fixture_ids = list(locked_candidate_by_fixture)
        active_locked_candidates = list(locked_candidate_by_fixture.values())
        started_locked_fixture_ids = _started_locked_fixture_ids(
            locked_candidate_by_fixture,
            as_of_time_utc=as_of_time_utc,
        )
        started_unlocked_fixture_ids = _started_unlocked_fixture_ids(
            checkpoint.candidates,
            locked_fixture_ids=set(active_locked_fixture_ids),
            as_of_time_utc=as_of_time_utc,
        )
        if started_locked_fixture_ids:
            event_codes.append("started_locked_fixtures_retained")
        if started_unlocked_fixture_ids:
            event_codes.append("started_unlocked_fixtures_excluded")
        if checkpoint_excluded_fixture_ids:
            event_codes.append("incident_exclusion_applied")
        locked_excluded_fixture_ids = [
            fixture_id
            for fixture_id in active_locked_fixture_ids
            if fixture_id in checkpoint_excluded_fixture_ids
        ]
        for fixture_id in locked_excluded_fixture_ids:
            warnings.append(f"locked_fixture_has_incident_exclusion:{fixture_id}")

        filtered_candidates = [
            candidate
            for candidate in checkpoint.candidates
            if candidate.fixture_id not in checkpoint_excluded_fixture_ids
            and candidate.fixture_id not in locked_candidate_by_fixture
        ]

        try:
            selection = _select_lifecycle_stage_recommendation(
                filtered_candidates,
                locked_candidates=active_locked_candidates,
                pass_type=pass_type,
                mode=mode,
                unit_stake=unit_stake,
                max_budget=max_budget,
                config=resolved_config,
                as_of_time_utc=as_of_time_utc,
                max_outcomes_per_fixture=max_outcomes_per_fixture,
                min_marginal_quality_gain=min_marginal_quality_gain,
            )
        except ValueError as exc:
            event_codes.append("no_recommendation_available")
            stage = PrematchRecommendationLifecycleStage(
                checkpoint_id=checkpoint.checkpoint_id,
                as_of_time_utc=as_of_time_utc,
                status="no_selection",
                locked_fixture_ids=active_locked_fixture_ids,
                excluded_fixture_ids=checkpoint_excluded_fixture_ids,
                started_unlocked_fixture_ids=started_unlocked_fixture_ids,
                started_locked_fixture_ids=started_locked_fixture_ids,
                remaining_open_leg_count=_remaining_open_leg_count(
                    leg_count,
                    locked_fixture_ids=active_locked_fixture_ids,
                ),
                event_codes=_dedupe_strings(event_codes),
                warnings=[*warnings, str(exc)],
                explanation_json={
                    "calculation_basis": "prematch_recommendation_lifecycle_backtest",
                    "incident_notes": checkpoint.incident_notes,
                    "metadata_json": checkpoint.metadata_json,
                },
            )
            stages.append(stage)
            continue

        selected_fixture_ids = selection.fixture_ids
        continuation_fixture_ids = _continuation_fixture_ids(
            selected_fixture_ids,
            locked_fixture_ids=active_locked_fixture_ids,
        )
        remaining_open_leg_count = len(continuation_fixture_ids)
        preserved_locked_fixture_ids = [
            fixture_id
            for fixture_id in active_locked_fixture_ids
            if fixture_id in selected_fixture_ids
        ]
        if preserved_locked_fixture_ids:
            event_codes.append("locked_fixtures_preserved")
        changed_fixture_ids = _changed_fixture_ids(previous_selection, selection)
        if previous_selection is None:
            event_codes.append("initial_recommendation")
        elif changed_fixture_ids:
            event_codes.append("recommendation_changed")
        else:
            event_codes.append("recommendation_unchanged")
        if continuation_fixture_ids:
            event_codes.append("remaining_fixtures_continue")

        stage = PrematchRecommendationLifecycleStage(
            checkpoint_id=checkpoint.checkpoint_id,
            as_of_time_utc=as_of_time_utc,
            status="selected",
            selection=selection,
            selected_fixture_ids=selected_fixture_ids,
            locked_fixture_ids=active_locked_fixture_ids,
            preserved_locked_fixture_ids=preserved_locked_fixture_ids,
            excluded_fixture_ids=checkpoint_excluded_fixture_ids,
            started_unlocked_fixture_ids=started_unlocked_fixture_ids,
            started_locked_fixture_ids=started_locked_fixture_ids,
            continuation_fixture_ids=continuation_fixture_ids,
            remaining_open_leg_count=remaining_open_leg_count,
            changed_fixture_ids=changed_fixture_ids,
            event_codes=_dedupe_strings(event_codes),
            warnings=warnings,
            explanation_json={
                "calculation_basis": "prematch_recommendation_lifecycle_backtest",
                "incident_notes": checkpoint.incident_notes,
                "metadata_json": checkpoint.metadata_json,
                "locked_candidate_outcomes": {
                    fixture_id: candidate.outcome
                    for fixture_id, candidate in locked_candidate_by_fixture.items()
                },
                "continuation": {
                    "pass_type": pass_type,
                    "total_leg_count": leg_count,
                    "locked_fixture_ids": active_locked_fixture_ids,
                    "started_locked_fixture_ids": started_locked_fixture_ids,
                    "continuation_fixture_ids": continuation_fixture_ids,
                    "remaining_open_leg_count": remaining_open_leg_count,
                    "selection_basis": (
                        "locked legs stay as constraints; continuation fixtures "
                        "remain eligible for future prematch recomputation"
                    ),
                },
            },
        )
        stages.append(stage)
        previous_selection = selection

    final_selection = stages[-1].selection if stages and stages[-1].status == "selected" else None
    return PrematchRecommendationLifecycleBacktestResult(
        pass_type=pass_type,
        mode=mode,
        unit_stake=unit_stake,
        max_budget=max_budget,
        stages=stages,
        final_selection=final_selection,
        summary_json=_lifecycle_backtest_summary(stages),
    )


def _select_lifecycle_stage_recommendation(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_candidates: Sequence[RecommendationCandidate],
    pass_type: str,
    mode: RecommendationMode,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
    max_outcomes_per_fixture: int,
    min_marginal_quality_gain: float,
) -> RecommendationSelection:
    if mode == "multiple":
        return select_budget_constrained_multiple_parlay(
            candidates,
            pass_type=pass_type,
            unit_stake=unit_stake,
            max_budget=max_budget,
            config=config,
            as_of_time_utc=as_of_time_utc,
            locked_candidates=locked_candidates,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
            min_marginal_quality_gain=min_marginal_quality_gain,
        )
    return select_budget_constrained_single_parlay(
        candidates,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
        config=config,
        as_of_time_utc=as_of_time_utc,
        locked_candidates=locked_candidates,
        min_quality_gain=min_marginal_quality_gain,
    )


def _resolve_locked_candidate(
    fixture_id: str,
    *,
    previous_selection: RecommendationSelection | None,
    candidates: Sequence[RecommendationCandidate],
    config: RecommendationPolicyConfig,
) -> RecommendationCandidate | None:
    if previous_selection is not None:
        for scored in previous_selection.selected_candidates:
            if scored.candidate.fixture_id == fixture_id:
                return scored.candidate

    fixture_candidates = [
        candidate for candidate in candidates if candidate.fixture_id == fixture_id
    ]
    if not fixture_candidates:
        return None
    return max(
        fixture_candidates,
        key=lambda candidate: score_candidate(candidate, config=config).score,
    )


def _started_unlocked_fixture_ids(
    candidates: Sequence[RecommendationCandidate],
    *,
    locked_fixture_ids: set[str],
    as_of_time_utc: datetime,
) -> list[str]:
    fixture_ids: list[str] = []
    for candidate in candidates:
        if candidate.fixture_id in locked_fixture_ids:
            continue
        if not candidate.has_started(as_of_time_utc):
            continue
        if candidate.fixture_id in fixture_ids:
            continue
        fixture_ids.append(candidate.fixture_id)
    return fixture_ids


def _started_locked_fixture_ids(
    locked_candidate_by_fixture: dict[str, RecommendationCandidate],
    *,
    as_of_time_utc: datetime,
) -> list[str]:
    return [
        fixture_id
        for fixture_id, candidate in locked_candidate_by_fixture.items()
        if candidate.has_started(as_of_time_utc)
    ]


def _continuation_fixture_ids(
    selected_fixture_ids: Sequence[str],
    *,
    locked_fixture_ids: Sequence[str],
) -> list[str]:
    locked = set(locked_fixture_ids)
    return [
        fixture_id
        for fixture_id in selected_fixture_ids
        if fixture_id not in locked
    ]


def _remaining_open_leg_count(
    leg_count: int,
    *,
    locked_fixture_ids: Sequence[str],
) -> int:
    return max(leg_count - len(set(locked_fixture_ids)), 0)


def _changed_fixture_ids(
    previous_selection: RecommendationSelection | None,
    current_selection: RecommendationSelection,
) -> list[str]:
    if previous_selection is None:
        return []
    previous_fixture_ids = set(previous_selection.fixture_ids)
    current_fixture_ids = set(current_selection.fixture_ids)
    return sorted(previous_fixture_ids.symmetric_difference(current_fixture_ids))


def _lifecycle_backtest_summary(
    stages: Sequence[PrematchRecommendationLifecycleStage],
) -> dict[str, object]:
    return {
        "stage_count": len(stages),
        "selected_stage_count": sum(1 for stage in stages if stage.status == "selected"),
        "changed_stage_count": sum(
            1 for stage in stages if "recommendation_changed" in stage.event_codes
        ),
        "incident_stage_count": sum(
            1 for stage in stages if "incident_exclusion_applied" in stage.event_codes
        ),
        "locked_preservation_stage_count": sum(
            1 for stage in stages if "locked_fixtures_preserved" in stage.event_codes
        ),
        "started_locked_stage_count": sum(
            1 for stage in stages if stage.started_locked_fixture_ids
        ),
        "continuation_stage_count": sum(
            1 for stage in stages if stage.continuation_fixture_ids
        ),
        "final_selected_fixture_ids": (
            stages[-1].selected_fixture_ids if stages and stages[-1].status == "selected" else []
        ),
        "final_continuation_fixture_ids": (
            stages[-1].continuation_fixture_ids
            if stages and stages[-1].status == "selected"
            else []
        ),
        "final_remaining_open_leg_count": (
            stages[-1].remaining_open_leg_count
            if stages and stages[-1].status == "selected"
            else 0
        ),
        "calculation_basis": "prematch_recommendation_lifecycle_backtest_stage_summary",
    }


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
