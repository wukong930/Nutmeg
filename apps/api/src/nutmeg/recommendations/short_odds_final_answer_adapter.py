from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type ShortOddsFinalAnswerAdapterStatus = Literal[
    "disabled",
    "no_rules",
    "unsupported_selection",
    "unchanged",
    "applied",
]


class ShortOddsFinalAnswerAdapterOptions(BaseModel):
    enable_adapter: bool = False
    rule_ids: tuple[str, ...] = ()
    allowed_modes: tuple[RecommendationMode, ...] = ("single",)
    same_market_type_only: bool = True
    require_rule_valid_replacement: bool = True
    require_no_production_change: bool = True
    max_report_candidates: int = Field(default=20, ge=1, le=200)


class ShortOddsFinalAnswerReplacementAction(BaseModel):
    rule_id: str
    profile_id: str
    competition_id: str | None = None
    removed_index: int = Field(ge=0)
    removed_fixture_id: str
    removed_market_type: str
    removed_outcome: str
    removed_probability: float = Field(ge=0.0, le=1.0)
    removed_decimal_odds: float | None = Field(default=None, gt=1.0)
    replacement_fixture_id: str
    replacement_market_type: str
    replacement_outcome: str
    replacement_probability: float = Field(ge=0.0, le=1.0)
    replacement_decimal_odds: float = Field(gt=1.0)
    replacement_rank: int = Field(ge=1)
    original_hit_probability: float = Field(ge=0.0, le=1.0)
    adapted_hit_probability: float = Field(ge=0.0, le=1.0)
    hit_probability_delta: float
    original_roi: float
    adapted_roi: float
    roi_delta: float
    original_expected_value: float
    adapted_expected_value: float
    expected_value_delta: float
    original_total_score: float = Field(ge=0.0, le=1.0)
    adapted_total_score: float = Field(ge=0.0, le=1.0)
    total_score_delta: float
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class ShortOddsFinalAnswerAdapterResult(BaseModel):
    report_key: str
    status: ShortOddsFinalAnswerAdapterStatus
    enabled: bool
    adapter_selection_changed: bool
    default_path_changed: bool = False
    public_response_changed: bool = False
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    eligible_candidate_count: int = Field(ge=0)
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    original_selection: RecommendationSelection
    adapted_selection: RecommendationSelection
    selected_action: ShortOddsFinalAnswerReplacementAction | None = None
    candidate_actions: list[ShortOddsFinalAnswerReplacementAction] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _CandidateAction(BaseModel):
    selected_action: ShortOddsFinalAnswerReplacementAction
    selected_scored: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    total_score: float = Field(ge=0.0, le=1.0)
    sort_key: tuple[float, ...]


def apply_short_odds_final_answer_adapter(
    selection: RecommendationSelection,
    *,
    candidate_pool: Sequence[ScoredRecommendationCandidate],
    rule_set: ShortOddsRuntimeRuleSet,
    options: ShortOddsFinalAnswerAdapterOptions | None = None,
) -> ShortOddsFinalAnswerAdapterResult:
    resolved_options = options or ShortOddsFinalAnswerAdapterOptions()
    if not resolved_options.enable_adapter:
        return _result(
            "disabled",
            selection,
            adapted_selection=selection,
            rule_set=rule_set,
            selected_rules=[],
            options=resolved_options,
            candidate_count=len(candidate_pool),
            candidate_actions=[],
            rejection_reasons=[],
            warnings=["short_odds_final_answer_adapter:disabled_by_feature_flag"],
        )
    selected_rules = rule_set.selected_rules(
        rule_ids=resolved_options.rule_ids,
        require_proposed_production_enabled=True,
        require_no_production_change=resolved_options.require_no_production_change,
    )
    if not selected_rules:
        return _result(
            "no_rules",
            selection,
            adapted_selection=selection,
            rule_set=rule_set,
            selected_rules=selected_rules,
            options=resolved_options,
            candidate_count=len(candidate_pool),
            candidate_actions=[],
            rejection_reasons=["no_enabled_rules"],
            warnings=["short_odds_final_answer_adapter:no_enabled_rules"],
        )
    if selection.mode not in resolved_options.allowed_modes:
        return _result(
            "unsupported_selection",
            selection,
            adapted_selection=selection,
            rule_set=rule_set,
            selected_rules=selected_rules,
            options=resolved_options,
            candidate_count=len(candidate_pool),
            candidate_actions=[],
            rejection_reasons=[f"unsupported_mode:{selection.mode}"],
            warnings=[f"short_odds_final_answer_adapter:unsupported_mode:{selection.mode}"],
        )

    rejection_reasons: list[str] = []
    candidate_actions = _candidate_actions(
        selection,
        candidate_pool=candidate_pool,
        rules=selected_rules,
        options=resolved_options,
        rejection_reasons=rejection_reasons,
    )
    if not candidate_actions:
        return _result(
            "unchanged",
            selection,
            adapted_selection=selection,
            rule_set=rule_set,
            selected_rules=selected_rules,
            options=resolved_options,
            candidate_count=len(candidate_pool),
            candidate_actions=[],
            rejection_reasons=rejection_reasons,
            warnings=["short_odds_final_answer_adapter:no_eligible_replacement"],
        )
    selected_candidate_action = max(
        candidate_actions,
        key=lambda action: action.sort_key,
    )
    adapted_selection = _adapted_selection(
        selection,
        selected_candidate_action=selected_candidate_action,
        rule_set=rule_set,
    )
    return _result(
        "applied",
        selection,
        adapted_selection=adapted_selection,
        rule_set=rule_set,
        selected_rules=selected_rules,
        options=resolved_options,
        candidate_count=len(candidate_pool),
        candidate_actions=candidate_actions,
        rejection_reasons=rejection_reasons,
        selected_candidate_action=selected_candidate_action,
        warnings=[],
    )


def build_short_odds_final_answer_adapter_smoke_report(
    rule_set: ShortOddsRuntimeRuleSet,
    *,
    options: ShortOddsFinalAnswerAdapterOptions | None = None,
    competition_id: str | None = None,
) -> ShortOddsFinalAnswerAdapterResult:
    selected_rule = next(
        (
            rule
            for rule in rule_set.selected_rules()
            if rule.allowed_competition_ids or competition_id is not None
        ),
        None,
    )
    resolved_competition_id = (
        competition_id
        or (selected_rule.allowed_competition_ids[0] if selected_rule else "EPL")
    )
    selection, candidate_pool = _deterministic_smoke_selection(
        competition_id=resolved_competition_id,
    )
    return apply_short_odds_final_answer_adapter(
        selection,
        candidate_pool=candidate_pool,
        rule_set=rule_set,
        options=options
        or ShortOddsFinalAnswerAdapterOptions(
            enable_adapter=True,
        ),
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = build_short_odds_final_answer_adapter_smoke_report(
        load_short_odds_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=args.enable_shadow_replay,
        ),
        options=_options_from_args(args),
        competition_id=args.competition_id,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{result.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if result.status != "applied" and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_actions(
    selection: RecommendationSelection,
    *,
    candidate_pool: Sequence[ScoredRecommendationCandidate],
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: ShortOddsFinalAnswerAdapterOptions,
    rejection_reasons: list[str],
) -> list[_CandidateAction]:
    actions: list[_CandidateAction] = []
    selected_fixture_ids = {item.candidate.fixture_id for item in selection.selected_candidates}
    locked_fixture_ids = set(selection.locked_fixture_ids)
    for removed_index, selected_scored in enumerate(selection.selected_candidates):
        if selected_scored.candidate.fixture_id in locked_fixture_ids:
            rejection_reasons.append("removed_fixture_locked")
            continue
        for replacement_rank, replacement_scored in enumerate(candidate_pool, 1):
            for rule in rules:
                candidate_action = _candidate_action(
                    selection,
                    selected_scored=selected_scored,
                    removed_index=removed_index,
                    replacement_scored=replacement_scored,
                    replacement_rank=replacement_rank,
                    selected_fixture_ids=selected_fixture_ids,
                    rule=rule,
                    options=options,
                    rejection_reasons=rejection_reasons,
                )
                if candidate_action is not None:
                    actions.append(candidate_action)
    return actions


def _candidate_action(
    selection: RecommendationSelection,
    *,
    selected_scored: ScoredRecommendationCandidate,
    removed_index: int,
    replacement_scored: ScoredRecommendationCandidate,
    replacement_rank: int,
    selected_fixture_ids: set[str],
    rule: ShortOddsRuntimeReplacementRule,
    options: ShortOddsFinalAnswerAdapterOptions,
    rejection_reasons: list[str],
) -> _CandidateAction | None:
    selected = selected_scored.candidate
    replacement = replacement_scored.candidate
    reason = _basic_rejection_reason(
        selected,
        replacement,
        selected_fixture_ids=selected_fixture_ids,
        rule=rule,
        options=options,
    )
    if reason is not None:
        rejection_reasons.append(reason)
        return None
    constraints = rule.constraints()
    assert replacement.decimal_odds is not None
    assert selected.decimal_odds is not None
    probability_delta_vs_selected = replacement.probability - selected.probability
    odds_delta_vs_selected = replacement.decimal_odds - selected.decimal_odds
    if replacement.probability < constraints.min_replacement_probability:
        rejection_reasons.append("replacement_probability_below_floor")
        return None
    if replacement.decimal_odds > constraints.max_replacement_decimal_odds:
        rejection_reasons.append("replacement_decimal_odds_above_ceiling")
        return None
    if (
        probability_delta_vs_selected
        < constraints.min_candidate_hit_probability_delta_vs_model_top
        or probability_delta_vs_selected
        > constraints.max_candidate_hit_probability_delta_vs_model_top
    ):
        rejection_reasons.append("probability_delta_vs_selected_out_of_range")
        return None
    if odds_delta_vs_selected < constraints.min_decimal_odds_delta_vs_model_top:
        rejection_reasons.append("decimal_odds_delta_vs_selected_below_floor")
        return None

    selected_scored_candidates = list(selection.selected_candidates)
    selected_scored_candidates[removed_index] = replacement_scored
    evaluation = evaluate_parlay(
        [item.candidate.to_leg_selection() for item in selected_scored_candidates],
        pass_type=selection.pass_type,
        unit_stake=selection.evaluation.unit_stake,
        multiplier=selection.evaluation.multiplier,
        max_budget=_max_budget(selection),
    )
    if options.require_rule_valid_replacement and not evaluation.rule_valid:
        rejection_reasons.append("replacement_selection_rule_invalid")
        return None
    hit_probability_delta = (
        evaluation.hit_probability - selection.evaluation.hit_probability
    )
    if (
        constraints.min_candidate_hit_probability_delta_vs_original is not None
        and hit_probability_delta
        < constraints.min_candidate_hit_probability_delta_vs_original
    ):
        rejection_reasons.append("hit_probability_delta_vs_original_below_floor")
        return None
    total_score = _average(item.score for item in selected_scored_candidates) or 0.0
    action = ShortOddsFinalAnswerReplacementAction(
        rule_id=rule.rule_id,
        profile_id=rule.profile_id,
        competition_id=_candidate_competition_id(replacement),
        removed_index=removed_index,
        removed_fixture_id=selected.fixture_id,
        removed_market_type=selected.market_type,
        removed_outcome=selected.outcome,
        removed_probability=selected.probability,
        removed_decimal_odds=selected.decimal_odds,
        replacement_fixture_id=replacement.fixture_id,
        replacement_market_type=replacement.market_type,
        replacement_outcome=replacement.outcome,
        replacement_probability=replacement.probability,
        replacement_decimal_odds=replacement.decimal_odds,
        replacement_rank=replacement_rank,
        original_hit_probability=selection.evaluation.hit_probability,
        adapted_hit_probability=evaluation.hit_probability,
        hit_probability_delta=hit_probability_delta,
        original_roi=selection.evaluation.roi,
        adapted_roi=evaluation.roi,
        roi_delta=evaluation.roi - selection.evaluation.roi,
        original_expected_value=selection.evaluation.expected_value,
        adapted_expected_value=evaluation.expected_value,
        expected_value_delta=(
            evaluation.expected_value - selection.evaluation.expected_value
        ),
        original_total_score=selection.total_score,
        adapted_total_score=total_score,
        total_score_delta=total_score - selection.total_score,
        reason_codes=[
            "short_odds_final_answer_replacement_candidate",
            "rule_enabled",
            "competition_allowed",
            "explicit_opt_in_required",
        ],
        summary_json={
            "calculation_basis": "short_odds_final_answer_adapter_candidate_v3_1",
            "probability_delta_vs_selected": probability_delta_vs_selected,
            "decimal_odds_delta_vs_selected": odds_delta_vs_selected,
            "default_path_changed": False,
            "public_response_changed": False,
        },
    )
    return _CandidateAction(
        selected_action=action,
        selected_scored=selected_scored_candidates,
        evaluation=evaluation,
        total_score=total_score,
        sort_key=_candidate_sort_key(
            action,
            replacement_scored=replacement_scored,
            rule=rule,
        ),
    )


def _basic_rejection_reason(
    selected: RecommendationCandidate,
    replacement: RecommendationCandidate,
    *,
    selected_fixture_ids: set[str],
    rule: ShortOddsRuntimeReplacementRule,
    options: ShortOddsFinalAnswerAdapterOptions,
) -> str | None:
    if _same_candidate(selected, replacement):
        return "same_candidate"
    if (
        replacement.fixture_id in selected_fixture_ids
        and replacement.fixture_id != selected.fixture_id
    ):
        return "replacement_fixture_already_selected"
    if options.same_market_type_only and replacement.market_type != selected.market_type:
        return "market_type_mismatch"
    if selected.decimal_odds is None:
        return "selected_decimal_odds_missing"
    if replacement.decimal_odds is None:
        return "replacement_decimal_odds_missing"
    selected_competition_id = _candidate_competition_id(selected)
    replacement_competition_id = _candidate_competition_id(replacement)
    competition_id = replacement_competition_id or selected_competition_id
    if competition_id is None:
        return "competition_id_missing"
    if selected_competition_id is not None and not rule.allows_competition(
        selected_competition_id
    ):
        return "selected_competition_not_allowed"
    if not rule.allows_competition(competition_id):
        return "replacement_competition_not_allowed"
    return None


def _adapted_selection(
    selection: RecommendationSelection,
    *,
    selected_candidate_action: _CandidateAction,
    rule_set: ShortOddsRuntimeRuleSet,
) -> RecommendationSelection:
    action = selected_candidate_action.selected_action
    return selection.model_copy(
        update={
            "selected_candidates": selected_candidate_action.selected_scored,
            "evaluation": selected_candidate_action.evaluation,
            "total_score": selected_candidate_action.total_score,
            "explanation_json": {
                **selection.explanation_json,
                "short_odds_final_answer_adapter": {
                    "calculation_basis": "short_odds_final_answer_adapter_v3_1",
                    "enabled": True,
                    "applied": True,
                    "rule_profile_version": rule_set.profile_version,
                    "rule_id": action.rule_id,
                    "removed_fixture_id": action.removed_fixture_id,
                    "replacement_fixture_id": action.replacement_fixture_id,
                    "hit_probability_delta": action.hit_probability_delta,
                    "roi_delta": action.roi_delta,
                    "expected_value_delta": action.expected_value_delta,
                    "default_path_changed": False,
                    "public_response_changed": False,
                },
            },
        }
    )


def _result(
    status: ShortOddsFinalAnswerAdapterStatus,
    original_selection: RecommendationSelection,
    *,
    adapted_selection: RecommendationSelection,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: ShortOddsFinalAnswerAdapterOptions,
    candidate_count: int,
    candidate_actions: Sequence[_CandidateAction],
    rejection_reasons: Sequence[str],
    selected_candidate_action: _CandidateAction | None = None,
    warnings: Sequence[str],
) -> ShortOddsFinalAnswerAdapterResult:
    selected_action = (
        selected_candidate_action.selected_action
        if selected_candidate_action is not None
        else None
    )
    reported_actions = [
        action.selected_action
        for action in sorted(
            candidate_actions,
            key=lambda item: item.sort_key,
            reverse=True,
        )[: options.max_report_candidates]
    ]
    rejection_reason_counts = dict(sorted(Counter(rejection_reasons).items()))
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_final_answer_adapter_v3_1",
        "status": status,
        "enabled": options.enable_adapter,
        "adapter_selection_changed": status == "applied",
        "default_path_changed": False,
        "public_response_changed": False,
        "source_rule_profile_version": rule_set.profile_version,
        "rule_count": len(rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "candidate_count": candidate_count,
        "eligible_candidate_count": len(candidate_actions),
        "selected_rule_ids": [rule.rule_id for rule in selected_rules],
        "selected_action": (
            selected_action.model_dump(mode="json") if selected_action else None
        ),
        "rejection_reason_counts": rejection_reason_counts,
        "warnings": list(warnings),
    }
    report_key = _report_key(summary, reported_actions)
    return ShortOddsFinalAnswerAdapterResult(
        report_key=report_key,
        status=status,
        enabled=options.enable_adapter,
        adapter_selection_changed=status == "applied",
        default_path_changed=False,
        public_response_changed=False,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        candidate_count=candidate_count,
        eligible_candidate_count=len(candidate_actions),
        rejection_reason_counts=rejection_reason_counts,
        original_selection=original_selection,
        adapted_selection=adapted_selection,
        selected_action=selected_action,
        candidate_actions=reported_actions,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _candidate_sort_key(
    action: ShortOddsFinalAnswerReplacementAction,
    *,
    replacement_scored: ScoredRecommendationCandidate,
    rule: ShortOddsRuntimeReplacementRule,
) -> tuple[float, ...]:
    replacement = replacement_scored.candidate
    model_edge = replacement.effective_model_edge()
    if rule.profile_id == "max_short_odds_within_deficit_v1":
        return (
            action.replacement_decimal_odds,
            -(
                action.replacement_probability
                - action.removed_probability
            ),
            action.roi_delta,
            model_edge,
            replacement_scored.score,
            -float(action.replacement_rank),
        )
    return (
        action.adapted_hit_probability,
        action.roi_delta,
        action.replacement_probability,
        action.replacement_decimal_odds,
        model_edge,
        replacement_scored.score,
        -float(action.replacement_rank),
    )


def _deterministic_smoke_selection(
    *,
    competition_id: str,
) -> tuple[RecommendationSelection, list[ScoredRecommendationCandidate]]:
    selected_a = _scored_candidate(
        fixture_id="adapter_selected_a",
        outcome="home_win",
        probability=0.62,
        decimal_odds=1.12,
        score=0.78,
        competition_id=competition_id,
    )
    selected_b = _scored_candidate(
        fixture_id="adapter_selected_b",
        outcome="away_win",
        probability=0.72,
        decimal_odds=1.40,
        score=0.76,
        competition_id=competition_id,
    )
    replacement = _scored_candidate(
        fixture_id="adapter_replacement_c",
        outcome="home_win",
        probability=0.611,
        decimal_odds=1.18,
        score=0.77,
        competition_id=competition_id,
    )
    blocked = _scored_candidate(
        fixture_id="adapter_blocked_d",
        outcome="draw",
        probability=0.50,
        decimal_odds=2.80,
        score=0.60,
        competition_id=competition_id,
    )
    selected = [selected_a, selected_b]
    evaluation = evaluate_parlay(
        [item.candidate.to_leg_selection() for item in selected],
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=20.0,
    )
    selection = RecommendationSelection(
        pass_type="2x1",
        mode="single",
        selected_candidates=selected,
        evaluation=evaluation,
        total_score=_average(item.score for item in selected) or 0.0,
        candidate_count=4,
        excluded_candidate_count=0,
        explanation_json={
            "selection_basis": "short_odds_final_answer_adapter_smoke_fixture",
        },
    )
    return selection, [selected_a, selected_b, replacement, blocked]


def _scored_candidate(
    *,
    fixture_id: str,
    outcome: str,
    probability: float,
    decimal_odds: float,
    score: float,
    competition_id: str,
) -> ScoredRecommendationCandidate:
    return ScoredRecommendationCandidate(
        candidate=RecommendationCandidate(
            fixture_id=fixture_id,
            market_type="1x2",
            outcome=outcome,
            probability=probability,
            decimal_odds=decimal_odds,
            market_probability=1.0 / decimal_odds,
            model_edge=probability - 1.0 / decimal_odds,
            data_quality_score=88.0,
            model_confidence_score=0.82,
            calibration_score=0.80,
            metadata_json={"competition_id": competition_id},
        ),
        score=score,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run a deterministic opt-in short-odds final-answer adapter smoke."
    )
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-adapter", action="store_true")
    parser.add_argument("--enable-shadow-replay", action="store_true")
    parser.add_argument("--rule-ids", default="")
    parser.add_argument("--competition-id")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-multiple-mode", action="store_true")
    parser.add_argument("--allow-cross-market", action="store_true")
    parser.add_argument("--allow-rule-invalid-replacement", action="store_true")
    parser.add_argument("--max-report-candidates", type=int, default=20)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> ShortOddsFinalAnswerAdapterOptions:
    allowed_modes: tuple[RecommendationMode, ...] = (
        ("single", "multiple") if args.allow_multiple_mode else ("single",)
    )
    return ShortOddsFinalAnswerAdapterOptions(
        enable_adapter=args.enable_adapter,
        rule_ids=_csv_values(args.rule_ids),
        allowed_modes=allowed_modes,
        same_market_type_only=not args.allow_cross_market,
        require_rule_valid_replacement=not args.allow_rule_invalid_replacement,
        require_no_production_change=not args.allow_production_change,
        max_report_candidates=args.max_report_candidates,
    )


def _max_budget(selection: RecommendationSelection) -> float | None:
    budget = selection.evaluation.explanation_json.get("budget")
    if not isinstance(budget, dict):
        return None
    value = budget.get("max_budget")
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return None


def _same_candidate(
    left: RecommendationCandidate,
    right: RecommendationCandidate,
) -> bool:
    return (
        left.fixture_id == right.fixture_id
        and left.market_type == right.market_type
        and left.outcome == right.outcome
    )


def _candidate_competition_id(candidate: RecommendationCandidate) -> str | None:
    competition_id = candidate.metadata_json.get("competition_id")
    if isinstance(competition_id, str) and competition_id:
        return competition_id
    return None


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _average(values: Iterable[float]) -> float | None:
    collected = [float(value) for value in values]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _report_key(
    summary: dict[str, object],
    reported_actions: Sequence[ShortOddsFinalAnswerReplacementAction],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "reported_actions": [
                    {
                        "rule_id": action.rule_id,
                        "removed_fixture_id": action.removed_fixture_id,
                        "replacement_fixture_id": action.replacement_fixture_id,
                        "replacement_outcome": action.replacement_outcome,
                    }
                    for action in reported_actions
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"short_odds_final_answer_adapter:{digest}"
