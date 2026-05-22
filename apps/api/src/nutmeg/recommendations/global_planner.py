from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.final_answer_candidate_pool import (
    build_unified_final_answer_candidate_pool,
)
from nutmeg.recommendations.final_arbitrator import (
    build_final_answer_arbitration_payload,
    final_answer_reason_codes,
    rank_final_answer_options,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationMode,
    RecommendationPolicyConfig,
    RecommendationSelection,
    RecommendationStrategy,
)
from nutmeg.recommendations.multiple_value_admission import (
    build_multiple_value_admission_summary,
)
from nutmeg.recommendations.optimizer import (
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)
from nutmeg.recommendations.policy import (
    build_recommendation_policy_config,
    parse_pass_type_leg_count,
    rank_candidates,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationCandidateQueryOptions,
    RecommendationDatabaseExecutor,
    StoredRecommendationRun,
)
from nutmeg.recommendations.short_odds_final_answer_adapter import (
    ShortOddsFinalAnswerAdapterOptions,
    ShortOddsFinalAnswerAdapterResult,
    apply_short_odds_final_answer_adapter,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    load_short_odds_runtime_rule_set,
)
from nutmeg.recommendations.upset_policy import aggregate_upset_quality

type RecommendationPlanOptionType = Literal[
    "standalone_single",
    "single_parlay",
    "multiple_parlay",
]


class RecommendationGlobalPlannerOptions(BaseModel):
    as_of_time_utc: datetime
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    allowed_markets: tuple[RecommendationMarketType, ...] = (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
        "correct_score",
    )
    pass_types: tuple[str, ...] = (
        "1x1",
        "2x1",
        "3x1",
        "4x1",
        "5x1",
        "6x1",
        "7x1",
        "8x1",
    )
    modes: tuple[RecommendationMode, ...] = ("single", "multiple")
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    require_odds: bool = True
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    fixture_ids: tuple[str, ...] = ()
    excluded_fixture_ids: tuple[str, ...] = ()
    locked_candidates: tuple[RecommendationCandidate, ...] = ()
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    short_odds_adapter_enabled: bool = False
    short_odds_adapter_shadow_only: bool = True
    short_odds_adapter_rule_profile_path: Path | None = None
    short_odds_adapter_rule_ids: tuple[str, ...] = ()
    short_odds_adapter_max_report_candidates: int = Field(default=20, ge=1, le=200)
    dry_run: bool = True
    internal_trace_json: dict[str, object] = Field(default_factory=dict)


class RecommendationGlobalPlanOption(BaseModel):
    option_key: str
    option_type: RecommendationPlanOptionType
    pass_type: str
    mode: RecommendationMode
    planner_score: float = Field(ge=0.0, le=1.0)
    within_budget: bool
    selection: RecommendationSelection
    reason_codes: list[str] = Field(default_factory=list)
    explanation_json: dict[str, object] = Field(default_factory=dict)


class RecommendationGlobalPlanAttempt(BaseModel):
    pass_type: str
    mode: RecommendationMode
    attempted: bool = True
    generated: bool = False
    warning_codes: list[str] = Field(default_factory=list)


class RecommendationGlobalPlannerResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    candidate_count: int = Field(ge=0)
    evaluated_option_count: int = Field(ge=0)
    generated_option_count: int = Field(ge=0)
    best_option: RecommendationGlobalPlanOption | None = None
    alternatives: list[RecommendationGlobalPlanOption] = Field(default_factory=list)
    attempts: list[RecommendationGlobalPlanAttempt] = Field(default_factory=list)
    stored_run: StoredRecommendationRun | None = None
    warnings: list[str] = Field(default_factory=list)
    final_answer_decision_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_global_planner(
    database: RecommendationDatabaseExecutor,
    *,
    options: RecommendationGlobalPlannerOptions,
    repository: PostgresRecommendationRepository | None = None,
) -> RecommendationGlobalPlannerResult:
    reader = PostgresRecommendationRepository(database)
    candidates = reader.list_candidates(
        options=RecommendationCandidateQueryOptions(
            as_of_time_utc=options.as_of_time_utc,
            allowed_markets=options.allowed_markets,
            min_probability=options.min_probability,
            min_model_edge=options.min_model_edge,
            min_data_quality_score=options.min_data_quality_score,
            require_odds=options.require_odds,
            candidate_limit=options.candidate_limit,
            fixture_ids=options.fixture_ids,
            competition_id=options.competition_id,
            model_version=options.model_version,
        )
    )
    if options.excluded_fixture_ids:
        excluded_fixture_ids = set(options.excluded_fixture_ids)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.fixture_id not in excluded_fixture_ids
        ]

    policy_config = build_recommendation_policy_config(
        strategy=options.strategy,
        allowed_markets=options.allowed_markets,
        min_probability=options.min_probability,
        min_model_edge=options.min_model_edge,
        min_data_quality_score=options.min_data_quality_score,
        require_odds=options.require_odds,
    )
    attempts: list[RecommendationGlobalPlanAttempt] = []
    generated_options: list[RecommendationGlobalPlanOption] = []
    for pass_type in _normalized_pass_types(options.pass_types):
        try:
            modes = _modes_for_pass_type(pass_type, options.modes)
        except ValueError as exc:
            attempts.append(
                RecommendationGlobalPlanAttempt(
                    pass_type=pass_type,
                    mode="single",
                    generated=False,
                    warning_codes=[str(exc)],
                )
            )
            continue
        for mode in modes:
            try:
                selection = _select_option(
                    candidates,
                    pass_type=pass_type,
                    mode=mode,
                    unit_stake=options.unit_stake,
                    max_budget=options.max_budget,
                    config=policy_config,
                    as_of_time_utc=options.as_of_time_utc,
                    locked_candidates=options.locked_candidates,
                    max_outcomes_per_fixture=options.max_outcomes_per_fixture,
                    min_marginal_quality_gain=options.min_marginal_quality_gain,
                )
            except ValueError as exc:
                attempts.append(
                    RecommendationGlobalPlanAttempt(
                        pass_type=pass_type,
                        mode=mode,
                        generated=False,
                        warning_codes=[str(exc)],
                    )
                )
                continue

            option = _plan_option(selection, strategy=options.strategy)
            generated_options.append(option)
            attempts.append(
                RecommendationGlobalPlanAttempt(
                    pass_type=pass_type,
                    mode=mode,
                    generated=True,
                )
            )

    valid_options = [
        option
        for option in generated_options
        if option.selection.evaluation.rule_valid and option.within_budget
    ]
    ranked_options = _arbitrate_final_answer_options(valid_options)
    ranked_options, short_odds_adapter_summary, short_odds_adapter_warnings = (
        _apply_short_odds_adapter_branch(
            ranked_options,
            candidates=candidates,
            policy_config=policy_config,
            options=options,
        )
    )
    best_option = ranked_options[0] if ranked_options else None
    stored_run = None
    if not options.dry_run and best_option is not None:
        writer = repository or PostgresRecommendationRepository(database)
        stored_run = writer.save_selection(
            best_option.selection,
            as_of_time_utc=options.as_of_time_utc,
            run_key=_global_plan_run_key(best_option, options=options),
            source="recommendation_global_planner_v3_1",
            internal_trace_json={
                **options.internal_trace_json,
                "global_planner": {
                    "selected_option_key": best_option.option_key,
                    "evaluated_option_count": len(generated_options),
                    "valid_option_count": len(valid_options),
                    "pass_types": list(_normalized_pass_types(options.pass_types)),
                    "modes": list(options.modes),
                },
                "final_answer_arbitration": best_option.explanation_json.get(
                    "final_answer_arbitration"
                ),
                "short_odds_final_answer_adapter": short_odds_adapter_summary,
            },
            candidate_pool=candidates,
            candidate_query_json=_candidate_query_json(options),
        )

    warnings = _dedupe_strings(
        [
            *_planner_warnings(
                attempts=attempts,
                generated_options=generated_options,
                best_option=best_option,
            ),
            *short_odds_adapter_warnings,
        ]
    )
    return RecommendationGlobalPlannerResult(
        dry_run=options.dry_run,
        as_of_time_utc=options.as_of_time_utc,
        candidate_count=len(candidates),
        evaluated_option_count=len(attempts),
        generated_option_count=len(generated_options),
        best_option=best_option,
        alternatives=ranked_options[1:10],
        attempts=attempts,
        stored_run=stored_run,
        warnings=warnings,
        final_answer_decision_json=_final_answer_decision_json(
            ranked_options,
            generated_options=generated_options,
            evaluated_option_count=len(generated_options),
            valid_option_count=len(valid_options),
            short_odds_adapter_summary=short_odds_adapter_summary,
        ),
    )


def _select_option(
    candidates: Sequence[RecommendationCandidate],
    *,
    pass_type: str,
    mode: RecommendationMode,
    unit_stake: float,
    max_budget: float | None,
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime,
    locked_candidates: Sequence[RecommendationCandidate],
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


def _plan_option(
    selection: RecommendationSelection,
    *,
    strategy: RecommendationStrategy,
) -> RecommendationGlobalPlanOption:
    option_type = _option_type(selection)
    within_budget = _within_budget(selection)
    planner_score = _planner_score(selection, within_budget=within_budget)
    option_key = f"{option_type}:{selection.pass_type}:{selection.mode}"
    multiple_value_admission = build_multiple_value_admission_summary(
        selection
    ).model_dump(mode="json")
    return RecommendationGlobalPlanOption(
        option_key=option_key,
        option_type=option_type,
        pass_type=selection.pass_type,
        mode=selection.mode,
        planner_score=planner_score,
        within_budget=within_budget,
        selection=selection.model_copy(
            update={
                "explanation_json": {
                    **selection.explanation_json,
                    "strategy": strategy,
                    "global_planner": {
                        "option_key": option_key,
                        "option_type": option_type,
                        "planner_score": planner_score,
                        "within_budget": within_budget,
                        "selection_basis": "v3_1_global_best_recommendation_planner",
                    },
                    "multiple_value_admission": multiple_value_admission,
                }
            }
        ),
        reason_codes=_option_reason_codes(selection, within_budget=within_budget),
        explanation_json={
            "calculation_basis": "global_best_recommendation_planner_v3_1",
            "option_type": option_type,
            "planner_score": planner_score,
            "within_budget": within_budget,
            "fixture_count": len(selection.fixture_ids),
            "upset_quality_diagnostic": aggregate_upset_quality(
                [item.candidate for item in selection.selected_candidates]
            ),
            "multiple_value_admission": multiple_value_admission,
        },
    )


def _planner_score(selection: RecommendationSelection, *, within_budget: bool) -> float:
    evaluation = selection.evaluation
    if not evaluation.rule_valid or not within_budget:
        return 0.0
    data_quality = _average(
        item.candidate.data_quality_score for item in selection.selected_candidates
    )
    roi_component = _clamp(0.50 + evaluation.roi / 2.0)
    risk_component = _clamp(1.0 - evaluation.risk_score)
    fixture_depth = _clamp(len(selection.fixture_ids) / 8.0)
    budget_component = _budget_efficiency(selection)
    score = (
        0.28 * selection.total_score
        + 0.25 * evaluation.hit_probability
        + 0.20 * roi_component
        + 0.11 * (data_quality / 100.0 if data_quality is not None else 0.0)
        + 0.08 * risk_component
        + 0.05 * budget_component
        + 0.03 * fixture_depth
    )
    return _clamp(score)


def _budget_efficiency(selection: RecommendationSelection) -> float:
    budget_payload = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget_payload, dict):
        return 1.0
    raw_budget = budget_payload.get("max_budget")
    if not isinstance(raw_budget, int | float) or raw_budget <= 0:
        return 1.0
    ratio = selection.evaluation.total_stake / float(raw_budget)
    return _clamp(1.0 - 0.50 * ratio)


def _within_budget(selection: RecommendationSelection) -> bool:
    budget_payload = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget_payload, dict):
        return True
    return bool(budget_payload.get("within_budget", True))


def _option_type(selection: RecommendationSelection) -> RecommendationPlanOptionType:
    if selection.pass_type == "1x1":
        return "standalone_single"
    if selection.mode == "multiple":
        return "multiple_parlay"
    return "single_parlay"


def _option_reason_codes(
    selection: RecommendationSelection,
    *,
    within_budget: bool,
) -> list[str]:
    reason_codes = ["global_planner_candidate"]
    if selection.evaluation.rule_valid:
        reason_codes.append("rule_valid")
    if within_budget:
        reason_codes.append("within_budget")
    if selection.evaluation.is_multiple:
        reason_codes.append("multiple_selection_budget_checked")
    if selection.locked_fixture_ids:
        reason_codes.append("locked_fixtures_preserved")
    return reason_codes


def _normalized_pass_types(pass_types: Sequence[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for pass_type in pass_types:
        if pass_type.lower() == "all":
            expanded.extend(["1x1", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"])
        else:
            expanded.append(pass_type.lower())
    return tuple(dict.fromkeys(expanded))


def _modes_for_pass_type(
    pass_type: str,
    requested_modes: Sequence[RecommendationMode],
) -> tuple[RecommendationMode, ...]:
    leg_count = parse_pass_type_leg_count(pass_type)
    if leg_count == 1:
        return ("single",)
    modes: list[RecommendationMode] = []
    for mode in requested_modes:
        if mode in modes:
            continue
        modes.append(mode)
    return tuple(modes)


def _option_sort_key(option: RecommendationGlobalPlanOption) -> tuple[float, float, float, int]:
    evaluation = option.selection.evaluation
    return (
        option.planner_score,
        evaluation.hit_probability,
        evaluation.roi,
        len(option.selection.fixture_ids),
    )


def _arbitrate_final_answer_options(
    options: Sequence[RecommendationGlobalPlanOption],
) -> list[RecommendationGlobalPlanOption]:
    ranked = rank_final_answer_options(options)
    return [
        _with_final_answer_arbitration(
            option,
            rank=rank,
            candidate_count=len(ranked),
        )
        for rank, option in enumerate(ranked, 1)
    ]


def _apply_short_odds_adapter_branch(
    ranked_options: Sequence[RecommendationGlobalPlanOption],
    *,
    candidates: Sequence[RecommendationCandidate],
    policy_config: RecommendationPolicyConfig,
    options: RecommendationGlobalPlannerOptions,
) -> tuple[list[RecommendationGlobalPlanOption], dict[str, object] | None, list[str]]:
    ranked = list(ranked_options)
    if not options.short_odds_adapter_enabled:
        return ranked, None, []
    if not ranked:
        summary = {
            "calculation_basis": "short_odds_final_answer_adapter_planner_branch_v3_1",
            "enabled": True,
            "status": "skipped",
            "reason": "no_ranked_final_answer_option",
            "shadow_only": options.short_odds_adapter_shadow_only,
            "planner_option_changed": False,
        }
        return ranked, summary, ["short_odds_final_answer_adapter:no_ranked_option"]
    if options.short_odds_adapter_rule_profile_path is None:
        summary = {
            "calculation_basis": "short_odds_final_answer_adapter_planner_branch_v3_1",
            "enabled": True,
            "status": "skipped",
            "reason": "rule_profile_path_missing",
            "shadow_only": options.short_odds_adapter_shadow_only,
            "planner_option_changed": False,
        }
        return ranked, summary, ["short_odds_final_answer_adapter:rule_profile_path_missing"]

    rule_set = load_short_odds_runtime_rule_set(
        options.short_odds_adapter_rule_profile_path,
        enable_shadow_replay=True,
    )
    adapter_result = apply_short_odds_final_answer_adapter(
        ranked[0].selection,
        candidate_pool=rank_candidates(
            candidates,
            config=policy_config,
            as_of_time_utc=options.as_of_time_utc,
        ),
        rule_set=rule_set,
        options=ShortOddsFinalAnswerAdapterOptions(
            enable_adapter=True,
            rule_ids=options.short_odds_adapter_rule_ids,
            max_report_candidates=options.short_odds_adapter_max_report_candidates,
        ),
    )
    planner_option_changed = (
        adapter_result.status == "applied"
        and adapter_result.adapter_selection_changed
        and not options.short_odds_adapter_shadow_only
    )
    summary = _short_odds_adapter_planner_summary(
        adapter_result,
        shadow_only=options.short_odds_adapter_shadow_only,
        planner_option_changed=planner_option_changed,
        rule_profile_path=options.short_odds_adapter_rule_profile_path,
    )
    if not planner_option_changed:
        return (
            [
                _with_short_odds_adapter_summary(ranked[0], summary),
                *ranked[1:],
            ],
            summary,
            adapter_result.warnings,
        )

    adapted_option = _with_short_odds_adapter_applied_selection(
        ranked[0],
        adapter_result=adapter_result,
        summary=summary,
    )
    return (
        _arbitrate_final_answer_options([adapted_option, *ranked[1:]]),
        summary,
        adapter_result.warnings,
    )


def _short_odds_adapter_planner_summary(
    result: ShortOddsFinalAnswerAdapterResult,
    *,
    shadow_only: bool,
    planner_option_changed: bool,
    rule_profile_path: Path,
) -> dict[str, object]:
    selected_action = result.selected_action
    action_summary: dict[str, object] | None = None
    if selected_action is not None:
        action_summary = {
            "rule_id": selected_action.rule_id,
            "profile_id": selected_action.profile_id,
            "removed_fixture_id": selected_action.removed_fixture_id,
            "replacement_fixture_id": selected_action.replacement_fixture_id,
            "hit_probability_delta": selected_action.hit_probability_delta,
            "roi_delta": selected_action.roi_delta,
            "expected_value_delta": selected_action.expected_value_delta,
            "total_score_delta": selected_action.total_score_delta,
        }
    return {
        "calculation_basis": "short_odds_final_answer_adapter_planner_branch_v3_1",
        "report_key": result.report_key,
        "status": result.status,
        "enabled": result.enabled,
        "shadow_only": shadow_only,
        "adapter_selection_changed": result.adapter_selection_changed,
        "planner_option_changed": planner_option_changed,
        "default_path_changed": planner_option_changed,
        "public_response_changed": planner_option_changed,
        "source_rule_profile_version": result.source_rule_profile_version,
        "rule_profile_path": str(rule_profile_path),
        "selected_rule_count": result.selected_rule_count,
        "candidate_count": result.candidate_count,
        "eligible_candidate_count": result.eligible_candidate_count,
        "selected_action": action_summary,
        "rejection_reason_counts": result.rejection_reason_counts,
        "warnings": result.warnings,
    }


def _with_short_odds_adapter_summary(
    option: RecommendationGlobalPlanOption,
    summary: dict[str, object],
) -> RecommendationGlobalPlanOption:
    selection = option.selection.model_copy(
        update={
            "explanation_json": {
                **option.selection.explanation_json,
                "short_odds_final_answer_adapter": summary,
            }
        }
    )
    return option.model_copy(
        update={
            "selection": selection,
            "explanation_json": {
                **option.explanation_json,
                "short_odds_final_answer_adapter": summary,
            },
        }
    )


def _with_short_odds_adapter_applied_selection(
    option: RecommendationGlobalPlanOption,
    *,
    adapter_result: ShortOddsFinalAnswerAdapterResult,
    summary: dict[str, object],
) -> RecommendationGlobalPlanOption:
    selection = adapter_result.adapted_selection.model_copy(
        update={
            "explanation_json": {
                **adapter_result.adapted_selection.explanation_json,
                "short_odds_final_answer_adapter": summary,
            }
        }
    )
    within_budget = _within_budget(selection)
    planner_score = _planner_score(selection, within_budget=within_budget)
    return option.model_copy(
        update={
            "planner_score": planner_score,
            "within_budget": within_budget,
            "selection": selection,
            "reason_codes": _dedupe_strings(
                [*option.reason_codes, "short_odds_final_answer_adapter_applied"]
            ),
            "explanation_json": {
                **option.explanation_json,
                "planner_score": planner_score,
                "within_budget": within_budget,
                "short_odds_final_answer_adapter": summary,
            },
        }
    )


def _with_final_answer_arbitration(
    option: RecommendationGlobalPlanOption,
    *,
    rank: int,
    candidate_count: int,
) -> RecommendationGlobalPlanOption:
    payload = build_final_answer_arbitration_payload(
        option,
        rank=rank,
        candidate_count=candidate_count,
    )
    selection = option.selection.model_copy(
        update={
            "explanation_json": {
                **option.selection.explanation_json,
                "final_answer_arbitration": payload,
            }
        }
    )
    return option.model_copy(
        update={
            "selection": selection,
            "reason_codes": _dedupe_strings(
                [*option.reason_codes, *final_answer_reason_codes(option)]
            ),
            "explanation_json": {
                **option.explanation_json,
                "final_answer_arbitration": payload,
            },
        }
    )


def _final_answer_decision_json(
    ranked_options: Sequence[RecommendationGlobalPlanOption],
    *,
    generated_options: Sequence[RecommendationGlobalPlanOption],
    evaluated_option_count: int,
    valid_option_count: int,
    short_odds_adapter_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    best_option = ranked_options[0] if ranked_options else None
    arbitration_payload = _best_arbitration_payload(best_option)
    candidate_pool = build_unified_final_answer_candidate_pool(
        generated_options,
        selected_option=best_option,
    )
    payload: dict[str, object] = {
        "calculation_basis": "final_answer_arbitrator_v3_1",
        "evaluated_option_count": evaluated_option_count,
        "valid_option_count": valid_option_count,
        "selected_option_key": best_option.option_key if best_option else None,
        "selected_pass_type": best_option.pass_type if best_option else None,
        "selected_mode": best_option.mode if best_option else None,
        "selected_answer_type": best_option.option_type if best_option else None,
        "selected_market_types": (
            arbitration_payload.get("market_types") if arbitration_payload else []
        ),
        "dynamic_mixed_market_answer": (
            bool(arbitration_payload.get("dynamic_mixed_market_answer"))
            if arbitration_payload
            else False
        ),
        "multiple_choice_fixture_count": (
            arbitration_payload.get("multiple_choice_fixture_count")
            if arbitration_payload
            else 0
        ),
        "candidate_option_keys": [option.option_key for option in ranked_options],
        "unified_candidate_pool": candidate_pool.model_dump(mode="json"),
    }
    if short_odds_adapter_summary is not None:
        payload["short_odds_final_answer_adapter"] = short_odds_adapter_summary
    return payload


def _best_arbitration_payload(
    option: RecommendationGlobalPlanOption | None,
) -> dict[str, object] | None:
    if option is None:
        return None
    payload = option.explanation_json.get("final_answer_arbitration")
    if isinstance(payload, dict):
        return payload
    return None


def _planner_warnings(
    *,
    attempts: Sequence[RecommendationGlobalPlanAttempt],
    generated_options: Sequence[RecommendationGlobalPlanOption],
    best_option: RecommendationGlobalPlanOption | None,
) -> list[str]:
    warnings: list[str] = []
    if not generated_options:
        warnings.append("global_planner_no_generated_options")
    if best_option is None:
        warnings.append("global_planner_no_valid_budget_safe_option")
    for attempt in attempts:
        for warning in attempt.warning_codes:
            warnings.append(f"{attempt.pass_type}:{attempt.mode}:{warning}")
    return _dedupe_strings(warnings)


def _global_plan_run_key(
    option: RecommendationGlobalPlanOption,
    *,
    options: RecommendationGlobalPlannerOptions,
) -> str:
    fixture_part = "_".join(option.selection.fixture_ids)
    payload = "|".join(
        [
            options.as_of_time_utc.isoformat(),
            option.option_key,
            fixture_part,
            str(option.planner_score),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"v3_1_global_{option.pass_type}_{fixture_part}_{digest}"


def _candidate_query_json(options: RecommendationGlobalPlannerOptions) -> dict[str, object]:
    return {
        "as_of_time_utc": options.as_of_time_utc.isoformat(),
        "allowed_markets": list(options.allowed_markets),
        "pass_types": list(_normalized_pass_types(options.pass_types)),
        "modes": list(options.modes),
        "min_probability": options.min_probability,
        "min_model_edge": options.min_model_edge,
        "min_data_quality_score": options.min_data_quality_score,
        "candidate_limit": options.candidate_limit,
        "require_odds": options.require_odds,
        "fixture_ids": list(options.fixture_ids),
        "excluded_fixture_ids": list(options.excluded_fixture_ids),
        "locked_fixture_ids": [
            candidate.fixture_id for candidate in options.locked_candidates
        ],
        "competition_id": options.competition_id,
        "model_version": options.model_version,
        "short_odds_adapter_enabled": options.short_odds_adapter_enabled,
        "short_odds_adapter_shadow_only": options.short_odds_adapter_shadow_only,
        "short_odds_adapter_rule_profile_path": (
            str(options.short_odds_adapter_rule_profile_path)
            if options.short_odds_adapter_rule_profile_path is not None
            else None
        ),
        "short_odds_adapter_rule_ids": list(options.short_odds_adapter_rule_ids),
        "source": "recommendation_global_planner_options",
    }


def _average(values: Iterable[float]) -> float | None:
    collected = [float(value) for value in values]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result
