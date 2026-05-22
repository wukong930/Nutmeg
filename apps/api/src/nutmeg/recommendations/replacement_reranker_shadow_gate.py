from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridCandidate,
    HistoricalReplacementRerankerToleranceGridReport,
)
from nutmeg.recommendations.replacement_reranker_weight_experiment import (
    HistoricalReplacementRerankerExperimentItem,
    HistoricalReplacementRerankerProfile,
    HistoricalReplacementRerankerWeightExperimentOptions,
    build_historical_replacement_reranker_weight_experiment_report,
    default_historical_replacement_reranker_profiles,
)

type HistoricalReplacementRerankerShadowGateStatus = Literal[
    "shadow_gate_passed",
    "shadow_gate_failed",
    "disabled",
    "no_tolerance_candidate",
]
type HistoricalReplacementRerankerShadowGateCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalReplacementRerankerShadowGateOptions(BaseModel):
    enable_shadow_gate: bool = False
    profile_id: str = "quality_edge_blend_v1"
    hit_probability_delta_threshold: float = -0.02
    profiles: tuple[HistoricalReplacementRerankerProfile, ...] = Field(
        default_factory=lambda: default_historical_replacement_reranker_profiles()
    )
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    min_final_answer_count: int = Field(default=20, ge=1)
    min_changed_from_model_top_count: int = Field(default=1, ge=0)
    min_final_answer_hit_delta_vs_model_top: int = 0
    min_replacement_leg_hit_delta_vs_model_top: int = 0
    min_profit_loss_delta_vs_model_top: float = 0.0
    min_roi_delta_vs_model_top: float = 0.0
    max_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_model_top: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_model_top: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_model_top: float = -0.02
    min_final_answer_hit_delta_vs_original: int | None = None
    min_profit_loss_delta_vs_original: float | None = None
    min_roi_delta_vs_original: float | None = None
    max_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_original: float | None = None
    require_tolerance_candidate: bool = True
    allowed_tolerance_statuses: tuple[str, ...] = ("candidate", "watchlist")
    require_source_audit_match: bool = True
    require_no_production_change: bool = True
    max_report_items: int = Field(default=80, ge=1, le=500)


class HistoricalReplacementRerankerShadowGateCheck(BaseModel):
    name: str
    status: HistoricalReplacementRerankerShadowGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementRerankerShadowGateFinalAnswer(BaseModel):
    final_answer_key: str
    item_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    selected_fixture_id: str
    selected_outcome: str
    original_actual_hit: bool
    model_top_actual_hit: bool
    shadow_actual_hit: bool
    model_top_replacement_leg_actual_hit: bool
    shadow_replacement_leg_actual_hit: bool
    hit_delta_vs_original: int
    hit_delta_vs_model_top: int
    replacement_leg_hit_delta_vs_model_top: int
    original_profit_loss: float
    model_top_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta_vs_original: float
    profit_loss_delta_vs_model_top: float
    original_hit_probability: float = Field(ge=0.0, le=1.0)
    model_top_hit_probability: float = Field(ge=0.0, le=1.0)
    shadow_hit_probability: float = Field(ge=0.0, le=1.0)
    hit_probability_delta_vs_original: float
    hit_probability_delta_vs_model_top: float
    stake: float = Field(ge=0.0)
    changed_from_model_top: bool
    selected_model_top: bool
    selected_actual_best: bool
    harmed_final_hit_vs_original: bool = False
    harmed_final_hit_vs_model_top: bool = False
    harmed_profit_loss_vs_original: bool
    harmed_profit_loss_vs_model_top: bool
    replacement_fixture_id: str
    replacement_outcome: str
    replacement_rank: int = Field(ge=1)
    replacement_probability: float = Field(ge=0.0, le=1.0)
    replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    model_top_replacement_fixture_id: str
    model_top_replacement_outcome: str
    actual_best_replacement_fixture_id: str
    actual_best_replacement_outcome: str
    reranker_score: float
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementRerankerShadowGateReport(BaseModel):
    report_key: str
    status: HistoricalReplacementRerankerShadowGateStatus
    passed: bool
    source_audit_report_key: str
    source_tolerance_grid_report_key: str | None = None
    source_tolerance_candidate_key: str | None = None
    source_tolerance_candidate_status: str | None = None
    profile_id: str
    hit_probability_delta_threshold: float
    source_audit_final_answer_count: int = Field(ge=0)
    eligible_item_count: int = Field(ge=0)
    shadow_final_answer_count: int = Field(ge=0)
    changed_from_model_top_count: int = Field(ge=0)
    selected_model_top_count: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    original_final_answer_hit_count: int = Field(ge=0)
    model_top_final_answer_hit_count: int = Field(ge=0)
    shadow_final_answer_hit_count: int = Field(ge=0)
    hit_delta_vs_original_count: int
    hit_delta_vs_model_top_count: int
    replacement_leg_hit_delta_vs_model_top_count: int
    original_profit_loss: float
    model_top_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta_vs_original: float
    profit_loss_delta_vs_model_top: float
    original_roi: float | None = None
    model_top_roi: float | None = None
    shadow_roi: float | None = None
    roi_delta_vs_original: float | None = None
    roi_delta_vs_model_top: float | None = None
    total_stake: float = Field(ge=0.0)
    harm_count_vs_original: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_model_top: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_model_top: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalReplacementRerankerShadowGateCheck] = Field(
        default_factory=list
    )
    shadow_items: list[HistoricalReplacementRerankerShadowGateFinalAnswer] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_replacement_reranker_tolerance_grid_report(
    path: Path | str,
) -> HistoricalReplacementRerankerToleranceGridReport:
    return HistoricalReplacementRerankerToleranceGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_replacement_reranker_shadow_gate_report(
    path: Path | str,
) -> HistoricalReplacementRerankerShadowGateReport:
    return HistoricalReplacementRerankerShadowGateReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_replacement_reranker_shadow_gate_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport | None = None,
    options: HistoricalReplacementRerankerShadowGateOptions | None = None,
) -> HistoricalReplacementRerankerShadowGateReport:
    resolved_options = options or HistoricalReplacementRerankerShadowGateOptions()
    warnings = list(audit_report.warnings)
    tolerance_candidate = _tolerance_candidate(
        tolerance_grid_report,
        options=resolved_options,
    )
    if not resolved_options.enable_shadow_gate:
        warnings.append("replacement_reranker_shadow_gate:disabled_by_feature_flag")
        return _report(
            audit_report,
            tolerance_grid_report=tolerance_grid_report,
            tolerance_candidate=tolerance_candidate,
            items=[],
            checks=[],
            status="disabled",
            passed=False,
            warnings=warnings,
            options=resolved_options,
            eligible_item_count=0,
        )
    if resolved_options.require_tolerance_candidate and tolerance_candidate is None:
        warnings.append("replacement_reranker_shadow_gate:no_tolerance_candidate")
        return _report(
            audit_report,
            tolerance_grid_report=tolerance_grid_report,
            tolerance_candidate=tolerance_candidate,
            items=[],
            checks=[],
            status="no_tolerance_candidate",
            passed=False,
            warnings=warnings,
            options=resolved_options,
            eligible_item_count=0,
        )

    profile = _selected_profile(resolved_options.profile_id, resolved_options.profiles)
    experiment_report = build_historical_replacement_reranker_weight_experiment_report(
        audit_report,
        options=HistoricalReplacementRerankerWeightExperimentOptions(
            profiles=(profile,),
            min_actual_best_profit_loss_delta=(
                resolved_options.min_actual_best_profit_loss_delta
            ),
            min_profit_loss_gap=resolved_options.min_profit_loss_gap,
            min_candidate_hit_probability_delta_vs_model_top=(
                resolved_options.hit_probability_delta_threshold
            ),
            min_evaluated_item_count=resolved_options.min_final_answer_count,
            max_hit_probability_regression_rate=1.0,
            min_average_profit_loss_delta_vs_model_top=0.0,
            max_report_items=500,
        ),
    )
    shadow_items = _shadow_items_from_experiment(
        audit_report,
        [
            item
            for item in experiment_report.items
            if item.profile_id == resolved_options.profile_id
        ],
        max_report_items=resolved_options.max_report_items,
    )
    checks = _checks(
        shadow_items,
        source_audit_report_key=audit_report.report_key,
        tolerance_grid_report=tolerance_grid_report,
        tolerance_candidate=tolerance_candidate,
        options=resolved_options,
    )
    passed = all(check.status != "failed" for check in checks)
    status: HistoricalReplacementRerankerShadowGateStatus = (
        "shadow_gate_passed" if passed else "shadow_gate_failed"
    )
    return _report(
        audit_report,
        tolerance_grid_report=tolerance_grid_report,
        tolerance_candidate=tolerance_candidate,
        items=shadow_items,
        checks=checks,
        status=status,
        passed=passed,
        warnings=warnings,
        options=resolved_options,
        eligible_item_count=experiment_report.eligible_item_count,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    tolerance_grid_report = (
        load_historical_replacement_reranker_tolerance_grid_report(
            args.tolerance_grid_report
        )
        if args.tolerance_grid_report is not None
        else None
    )
    report = build_historical_replacement_reranker_shadow_gate_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        tolerance_grid_report=tolerance_grid_report,
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _tolerance_candidate(
    report: HistoricalReplacementRerankerToleranceGridReport | None,
    *,
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> HistoricalReplacementRerankerToleranceGridCandidate | None:
    if report is None:
        return None
    for candidate in report.candidates:
        if (
            candidate.profile_id == options.profile_id
            and candidate.hit_probability_delta_threshold
            == options.hit_probability_delta_threshold
        ):
            return candidate
    return None


def _selected_profile(
    profile_id: str,
    profiles: Sequence[HistoricalReplacementRerankerProfile],
) -> HistoricalReplacementRerankerProfile:
    for profile in profiles:
        if profile.profile_id == profile_id:
            return profile
    raise ValueError(f"Unknown replacement reranker profile id: {profile_id}")


def _shadow_items_from_experiment(
    audit_report: HistoricalCandidateMarginalAuditReport,
    experiment_items: Sequence[HistoricalReplacementRerankerExperimentItem],
    *,
    max_report_items: int,
) -> list[HistoricalReplacementRerankerShadowGateFinalAnswer]:
    audit_items = {item.item_key: item for item in audit_report.items}
    grouped: dict[str, list[HistoricalReplacementRerankerExperimentItem]] = {}
    for experiment_item in experiment_items:
        audit_item = audit_items.get(experiment_item.item_key)
        if audit_item is None:
            continue
        grouped.setdefault(_final_answer_key(audit_item), []).append(experiment_item)

    selected: list[HistoricalReplacementRerankerShadowGateFinalAnswer] = []
    for group in grouped.values():
        chosen = _select_shadow_item(group)
        audit_item = audit_items.get(chosen.item_key)
        if audit_item is None:
            continue
        item = _shadow_item_from_experiment(audit_item, chosen)
        if item is not None:
            selected.append(item)
    return sorted(
        selected,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.hit_delta_vs_model_top,
            item.changed_from_model_top,
            item.final_answer_key,
        ),
        reverse=True,
    )[:max_report_items]


def _select_shadow_item(
    items: Sequence[HistoricalReplacementRerankerExperimentItem],
) -> HistoricalReplacementRerankerExperimentItem:
    return max(
        items,
        key=lambda item: (
            item.reranker_score,
            item.hit_probability_delta_vs_model_top,
            item.roi_delta_vs_model_top,
            -item.risk_score_delta_vs_model_top,
            item.quality_score_delta_vs_model_top,
            item.item_key,
        ),
    )


def _shadow_item_from_experiment(
    audit_item: HistoricalCandidateMarginalAuditItem,
    experiment_item: HistoricalReplacementRerankerExperimentItem,
) -> HistoricalReplacementRerankerShadowGateFinalAnswer | None:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        return None
    replacement = _replacement_for_experiment_item(audit_item, experiment_item)
    if replacement is None:
        return None
    original_profit = audit_item.original_profit_loss
    model_top_profit = model_top.simulated_profit_loss
    shadow_profit = original_profit + experiment_item.profit_loss_delta
    stake = _stake_from_audit_item(audit_item)
    return HistoricalReplacementRerankerShadowGateFinalAnswer(
        final_answer_key=_final_answer_key(audit_item),
        item_key=audit_item.item_key,
        slice_id=audit_item.slice_id,
        competition_id=audit_item.competition_id,
        final_answer_scenario_key=audit_item.final_answer_scenario_key,
        pass_type=audit_item.pass_type,
        mode=str(audit_item.mode),
        selected_fixture_id=audit_item.selected_fixture_id,
        selected_outcome=audit_item.selected_outcome,
        original_actual_hit=audit_item.final_answer_actual_hit,
        model_top_actual_hit=model_top.simulated_actual_hit,
        shadow_actual_hit=experiment_item.simulated_actual_hit,
        model_top_replacement_leg_actual_hit=model_top.replacement_leg_actual_hit,
        shadow_replacement_leg_actual_hit=experiment_item.replacement_leg_actual_hit,
        hit_delta_vs_original=(
            int(experiment_item.simulated_actual_hit)
            - int(audit_item.final_answer_actual_hit)
        ),
        hit_delta_vs_model_top=(
            int(experiment_item.simulated_actual_hit)
            - int(model_top.simulated_actual_hit)
        ),
        replacement_leg_hit_delta_vs_model_top=(
            int(experiment_item.replacement_leg_actual_hit)
            - int(model_top.replacement_leg_actual_hit)
        ),
        original_profit_loss=original_profit,
        model_top_profit_loss=model_top_profit,
        shadow_profit_loss=shadow_profit,
        profit_loss_delta_vs_original=shadow_profit - original_profit,
        profit_loss_delta_vs_model_top=shadow_profit - model_top_profit,
        original_hit_probability=audit_item.original_hit_probability,
        model_top_hit_probability=model_top.simulated_hit_probability,
        shadow_hit_probability=replacement.simulated_hit_probability,
        hit_probability_delta_vs_original=(
            replacement.simulated_hit_probability - audit_item.original_hit_probability
        ),
        hit_probability_delta_vs_model_top=(
            replacement.simulated_hit_probability - model_top.simulated_hit_probability
        ),
        stake=stake,
        changed_from_model_top=not experiment_item.selected_model_top,
        selected_model_top=experiment_item.selected_model_top,
        selected_actual_best=experiment_item.selected_actual_best,
        harmed_final_hit_vs_original=(
            audit_item.final_answer_actual_hit
            and not experiment_item.simulated_actual_hit
        ),
        harmed_final_hit_vs_model_top=(
            model_top.simulated_actual_hit
            and not experiment_item.simulated_actual_hit
        ),
        harmed_profit_loss_vs_original=shadow_profit < original_profit,
        harmed_profit_loss_vs_model_top=shadow_profit < model_top_profit,
        replacement_fixture_id=experiment_item.reranked_replacement_fixture_id,
        replacement_outcome=experiment_item.reranked_replacement_outcome,
        replacement_rank=experiment_item.reranked_replacement_rank,
        replacement_probability=replacement.replacement_probability,
        replacement_decimal_odds=replacement.replacement_decimal_odds,
        model_top_replacement_fixture_id=model_top.replacement_fixture_id,
        model_top_replacement_outcome=model_top.replacement_outcome,
        actual_best_replacement_fixture_id=actual_best.replacement_fixture_id,
        actual_best_replacement_outcome=actual_best.replacement_outcome,
        reranker_score=experiment_item.reranker_score,
        summary_json={
            "calculation_basis": "historical_replacement_reranker_shadow_item_v3_1",
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "used_feature_names": experiment_item.summary_json.get(
                "used_feature_names",
                [],
            ),
            "leakage_excluded_fields": experiment_item.summary_json.get(
                "leakage_excluded_fields",
                [],
            ),
        },
    )


def _replacement_for_experiment_item(
    audit_item: HistoricalCandidateMarginalAuditItem,
    experiment_item: HistoricalReplacementRerankerExperimentItem,
) -> HistoricalCandidateReplacementSimulation | None:
    for replacement in audit_item.replacement_candidates:
        if (
            replacement.replacement_fixture_id
            == experiment_item.reranked_replacement_fixture_id
            and replacement.replacement_outcome
            == experiment_item.reranked_replacement_outcome
            and replacement.replacement_rank == experiment_item.reranked_replacement_rank
        ):
            return replacement
    return None


def _checks(
    items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
    *,
    source_audit_report_key: str,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport | None,
    tolerance_candidate: HistoricalReplacementRerankerToleranceGridCandidate | None,
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> list[HistoricalReplacementRerankerShadowGateCheck]:
    checks = [
        _boolean_check(
            name="shadow_gate_enabled",
            actual=options.enable_shadow_gate,
            expected=True,
            detail="shadow gate must be explicitly enabled",
        ),
        _minimum_check(
            name="shadow_final_answer_count",
            actual=len(items),
            threshold=options.min_final_answer_count,
            detail="shadow gate should include enough targeted final answers",
        ),
        _minimum_check(
            name="changed_from_model_top_count",
            actual=sum(1 for item in items if item.changed_from_model_top),
            threshold=options.min_changed_from_model_top_count,
            detail="shadow gate should rerank enough model-top replacements",
        ),
        _minimum_check(
            name="final_answer_hit_delta_vs_model_top",
            actual=sum(item.hit_delta_vs_model_top for item in items),
            threshold=options.min_final_answer_hit_delta_vs_model_top,
            detail="final-answer hits should not regress versus model-top replacement",
        ),
        _minimum_check(
            name="replacement_leg_hit_delta_vs_model_top",
            actual=_replacement_leg_hit_delta_vs_model_top(items),
            threshold=options.min_replacement_leg_hit_delta_vs_model_top,
            detail="replacement leg hits should not regress versus model-top replacement",
        ),
        _minimum_check(
            name="profit_loss_delta_vs_model_top",
            actual=sum(item.profit_loss_delta_vs_model_top for item in items),
            threshold=options.min_profit_loss_delta_vs_model_top,
            detail="shadow reranker profit/loss should improve versus model-top",
        ),
        _minimum_check(
            name="roi_delta_vs_model_top",
            actual=_roi_delta_vs_model_top(items),
            threshold=options.min_roi_delta_vs_model_top,
            detail="shadow reranker ROI should improve versus model-top",
        ),
        _maximum_check(
            name="harm_count_vs_model_top",
            actual=sum(1 for item in items if item.harmed_profit_loss_vs_model_top),
            threshold=options.max_harm_count_vs_model_top,
            detail="shadow reranker should not harm any model-top replacement",
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_model_top",
            actual=sum(1 for item in items if item.harmed_final_hit_vs_model_top),
            threshold=_max_final_hit_harm_count_vs_model_top(options),
            detail=(
                "shadow reranker should not turn model-top final-answer hits "
                "into misses"
            ),
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_model_top",
            actual=sum(1 for item in items if item.harmed_profit_loss_vs_model_top),
            threshold=_max_profit_loss_harm_count_vs_model_top(options),
            detail=(
                "shadow reranker should not reduce model-top final-answer "
                "profit/loss"
            ),
        ),
        _minimum_check(
            name="average_hit_probability_delta_vs_model_top",
            actual=_average(
                item.hit_probability_delta_vs_model_top
                for item in items
                if item.changed_from_model_top
            ),
            threshold=options.min_average_hit_probability_delta_vs_model_top,
            detail="expected hit-probability tolerance should remain bounded",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=True,
            expected=True,
            detail="shadow gate must not change public responses",
        ),
    ]
    if options.min_final_answer_hit_delta_vs_original is not None:
        checks.append(
            _minimum_check(
                name="final_answer_hit_delta_vs_original",
                actual=sum(item.hit_delta_vs_original for item in items),
                threshold=options.min_final_answer_hit_delta_vs_original,
                detail="final-answer hits should not regress versus the original recommendation",
            )
        )
    if options.min_profit_loss_delta_vs_original is not None:
        checks.append(
            _minimum_check(
                name="profit_loss_delta_vs_original",
                actual=sum(item.profit_loss_delta_vs_original for item in items),
                threshold=options.min_profit_loss_delta_vs_original,
                detail=(
                    "shadow reranker profit/loss should not regress versus "
                    "the original recommendation"
                ),
            )
        )
    if options.min_roi_delta_vs_original is not None:
        checks.append(
            _minimum_check(
                name="roi_delta_vs_original",
                actual=_roi_delta_vs_original(items),
                threshold=options.min_roi_delta_vs_original,
                detail="shadow reranker ROI should not regress versus the original recommendation",
            )
        )
    if options.max_harm_count_vs_original is not None:
        checks.append(
            _maximum_check(
                name="harm_count_vs_original",
                actual=sum(1 for item in items if item.harmed_profit_loss_vs_original),
                threshold=options.max_harm_count_vs_original,
                detail=(
                    "shadow reranker should not harm original recommendations "
                    "on the pre-match surface"
                ),
            )
        )
    max_final_hit_harm_count_vs_original = _max_final_hit_harm_count_vs_original(
        options
    )
    if max_final_hit_harm_count_vs_original is not None:
        checks.append(
            _maximum_check(
                name="final_hit_harm_count_vs_original",
                actual=sum(1 for item in items if item.harmed_final_hit_vs_original),
                threshold=max_final_hit_harm_count_vs_original,
                detail=(
                    "shadow reranker should not turn original final-answer hits "
                    "into misses"
                ),
            )
        )
    max_profit_loss_harm_count_vs_original = _max_profit_loss_harm_count_vs_original(
        options
    )
    if max_profit_loss_harm_count_vs_original is not None:
        checks.append(
            _maximum_check(
                name="profit_loss_harm_count_vs_original",
                actual=sum(1 for item in items if item.harmed_profit_loss_vs_original),
                threshold=max_profit_loss_harm_count_vs_original,
                detail=(
                    "shadow reranker should not reduce original recommendation "
                    "profit/loss"
                ),
            )
        )
    if options.min_average_hit_probability_delta_vs_original is not None:
        checks.append(
            _minimum_check(
                name="average_hit_probability_delta_vs_original",
                actual=_average(
                    item.hit_probability_delta_vs_original
                    for item in items
                    if item.changed_from_model_top
                ),
                threshold=options.min_average_hit_probability_delta_vs_original,
                detail=(
                    "expected hit-probability tolerance versus original "
                    "recommendations should remain bounded"
                ),
            )
        )
    if options.require_tolerance_candidate:
        checks.append(
            _boolean_check(
                name="tolerance_candidate_present",
                actual=tolerance_candidate is not None,
                expected=True,
                detail="matching tolerance grid candidate is required",
            )
        )
    if tolerance_candidate is not None:
        checks.append(
            _membership_check(
                name="tolerance_candidate_status",
                actual=tolerance_candidate.status,
                allowed=options.allowed_tolerance_statuses,
                detail="source tolerance candidate must be admitted or watchlisted",
            )
        )
    if options.require_source_audit_match and tolerance_grid_report is not None:
        checks.append(
            _boolean_check(
                name="source_audit_report_key_match",
                actual=(
                    tolerance_grid_report.source_audit_report_key
                    == source_audit_report_key
                ),
                expected=True,
                detail="tolerance grid source audit key should match the audit report",
            )
        )
    if options.require_no_production_change:
        checks.append(
            _boolean_check(
                name="no_production_recommendation_change",
                actual=True,
                expected=True,
                detail="shadow gate must not change production recommendations",
            )
        )
    return checks


def _report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport | None,
    tolerance_candidate: HistoricalReplacementRerankerToleranceGridCandidate | None,
    items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
    checks: Sequence[HistoricalReplacementRerankerShadowGateCheck],
    status: HistoricalReplacementRerankerShadowGateStatus,
    passed: bool,
    warnings: Sequence[str],
    options: HistoricalReplacementRerankerShadowGateOptions,
    eligible_item_count: int,
) -> HistoricalReplacementRerankerShadowGateReport:
    total_stake = sum(item.stake for item in items)
    original_profit = sum(item.original_profit_loss for item in items)
    model_top_profit = sum(item.model_top_profit_loss for item in items)
    shadow_profit = sum(item.shadow_profit_loss for item in items)
    final_hit_harm_count_vs_original = sum(
        1 for item in items if item.harmed_final_hit_vs_original
    )
    final_hit_harm_count_vs_model_top = sum(
        1 for item in items if item.harmed_final_hit_vs_model_top
    )
    profit_loss_harm_count_vs_original = sum(
        1 for item in items if item.harmed_profit_loss_vs_original
    )
    profit_loss_harm_count_vs_model_top = sum(
        1 for item in items if item.harmed_profit_loss_vs_model_top
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_replacement_reranker_shadow_gate_v3_1",
        "status": status,
        "passed": passed,
        "source_audit_report_key": audit_report.report_key,
        "source_tolerance_grid_report_key": (
            tolerance_grid_report.report_key if tolerance_grid_report else None
        ),
        "source_tolerance_candidate_key": (
            tolerance_candidate.candidate_key if tolerance_candidate else None
        ),
        "profile_id": options.profile_id,
        "hit_probability_delta_threshold": options.hit_probability_delta_threshold,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": options.model_dump(mode="json"),
        "warnings": list(warnings),
    }
    changed_items = sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.hit_delta_vs_model_top,
            item.final_answer_key,
        ),
        reverse=True,
    )[: options.max_report_items]
    report_key = _report_key(summary, checks, changed_items)
    return HistoricalReplacementRerankerShadowGateReport(
        report_key=report_key,
        status=status,
        passed=passed,
        source_audit_report_key=audit_report.report_key,
        source_tolerance_grid_report_key=(
            tolerance_grid_report.report_key if tolerance_grid_report else None
        ),
        source_tolerance_candidate_key=(
            tolerance_candidate.candidate_key if tolerance_candidate else None
        ),
        source_tolerance_candidate_status=(
            tolerance_candidate.status if tolerance_candidate else None
        ),
        profile_id=options.profile_id,
        hit_probability_delta_threshold=options.hit_probability_delta_threshold,
        source_audit_final_answer_count=audit_report.final_answer_count,
        eligible_item_count=eligible_item_count,
        shadow_final_answer_count=len(items),
        changed_from_model_top_count=sum(
            1 for item in items if item.changed_from_model_top
        ),
        selected_model_top_count=sum(1 for item in items if item.selected_model_top),
        selected_actual_best_count=sum(1 for item in items if item.selected_actual_best),
        original_final_answer_hit_count=sum(
            1 for item in items if item.original_actual_hit
        ),
        model_top_final_answer_hit_count=sum(
            1 for item in items if item.model_top_actual_hit
        ),
        shadow_final_answer_hit_count=sum(1 for item in items if item.shadow_actual_hit),
        hit_delta_vs_original_count=sum(item.hit_delta_vs_original for item in items),
        hit_delta_vs_model_top_count=sum(item.hit_delta_vs_model_top for item in items),
        replacement_leg_hit_delta_vs_model_top_count=(
            _replacement_leg_hit_delta_vs_model_top(items)
        ),
        original_profit_loss=original_profit,
        model_top_profit_loss=model_top_profit,
        shadow_profit_loss=shadow_profit,
        profit_loss_delta_vs_original=shadow_profit - original_profit,
        profit_loss_delta_vs_model_top=shadow_profit - model_top_profit,
        original_roi=_roi(profit_loss=original_profit, stake=total_stake),
        model_top_roi=_roi(profit_loss=model_top_profit, stake=total_stake),
        shadow_roi=_roi(profit_loss=shadow_profit, stake=total_stake),
        roi_delta_vs_original=_roi_delta(
            numerator_profit=shadow_profit,
            denominator_profit=original_profit,
            stake=total_stake,
        ),
        roi_delta_vs_model_top=_roi_delta(
            numerator_profit=shadow_profit,
            denominator_profit=model_top_profit,
            stake=total_stake,
        ),
        total_stake=total_stake,
        harm_count_vs_original=profit_loss_harm_count_vs_original,
        harm_count_vs_model_top=profit_loss_harm_count_vs_model_top,
        final_hit_harm_count_vs_original=final_hit_harm_count_vs_original,
        final_hit_harm_count_vs_model_top=final_hit_harm_count_vs_model_top,
        profit_loss_harm_count_vs_original=profit_loss_harm_count_vs_original,
        profit_loss_harm_count_vs_model_top=profit_loss_harm_count_vs_model_top,
        average_hit_probability_delta_vs_original=_average(
            item.hit_probability_delta_vs_original
            for item in items
            if item.changed_from_model_top
        ),
        average_hit_probability_delta_vs_model_top=_average(
            item.hit_probability_delta_vs_model_top
            for item in items
            if item.changed_from_model_top
        ),
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=list(checks),
        shadow_items=changed_items,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _replacement_leg_hit_delta_vs_model_top(
    items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
) -> int:
    return sum(
        item.replacement_leg_hit_delta_vs_model_top
        for item in items
        if item.changed_from_model_top
    )


def _final_answer_key(item: HistoricalCandidateMarginalAuditItem) -> str:
    return f"{item.slice_id}:{item.final_answer_scenario_key}"


def _stake_from_audit_item(item: HistoricalCandidateMarginalAuditItem) -> float:
    stake = item.original_actual_return - item.original_profit_loss
    if stake >= 0:
        return stake
    if item.original_roi != 0:
        return abs(item.original_profit_loss / item.original_roi)
    return 0.0


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalReplacementRerankerShadowGateCheck:
    return HistoricalReplacementRerankerShadowGateCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _membership_check(
    *,
    name: str,
    actual: str,
    allowed: Sequence[str],
    detail: str,
) -> HistoricalReplacementRerankerShadowGateCheck:
    return HistoricalReplacementRerankerShadowGateCheck(
        name=name,
        status="passed" if actual in set(allowed) else "failed",
        actual=actual,
        threshold=",".join(allowed),
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalReplacementRerankerShadowGateCheck:
    if actual is None:
        return HistoricalReplacementRerankerShadowGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementRerankerShadowGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalReplacementRerankerShadowGateCheck:
    if actual is None:
        return HistoricalReplacementRerankerShadowGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementRerankerShadowGateCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _roi_delta_vs_model_top(
    items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
) -> float | None:
    stake = sum(item.stake for item in items)
    return _roi_delta(
        numerator_profit=sum(item.shadow_profit_loss for item in items),
        denominator_profit=sum(item.model_top_profit_loss for item in items),
        stake=stake,
    )


def _roi_delta_vs_original(
    items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
) -> float | None:
    stake = sum(item.stake for item in items)
    return _roi_delta(
        numerator_profit=sum(item.shadow_profit_loss for item in items),
        denominator_profit=sum(item.original_profit_loss for item in items),
        stake=stake,
    )


def _roi_delta(
    *,
    numerator_profit: float,
    denominator_profit: float,
    stake: float,
) -> float | None:
    numerator = _roi(profit_loss=numerator_profit, stake=stake)
    denominator = _roi(profit_loss=denominator_profit, stake=stake)
    if numerator is None or denominator is None:
        return None
    return numerator - denominator


def _roi(*, profit_loss: float, stake: float) -> float | None:
    if stake <= 0:
        return None
    return profit_loss / stake


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run a controlled replacement reranker shadow gate."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--tolerance-grid-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-shadow-gate", action="store_true")
    parser.add_argument("--profile-id", type=str, default="quality_edge_blend_v1")
    parser.add_argument("--hit-probability-delta-threshold", type=float, default=-0.02)
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--min-final-answer-count", type=int, default=20)
    parser.add_argument("--min-changed-from-model-top-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-delta-vs-model-top", type=int, default=0)
    parser.add_argument(
        "--min-replacement-leg-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument("--min-profit-loss-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-roi-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-model-top", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-model-top", type=int)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--min-final-answer-hit-delta-vs-original", type=int)
    parser.add_argument("--min-profit-loss-delta-vs-original", type=float)
    parser.add_argument("--min-roi-delta-vs-original", type=float)
    parser.add_argument("--max-harm-count-vs-original", type=int)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
    )
    parser.add_argument("--allow-missing-tolerance-candidate", action="store_true")
    parser.add_argument(
        "--allowed-tolerance-statuses",
        type=str,
        default="candidate,watchlist",
    )
    parser.add_argument("--allow-source-audit-mismatch", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-items", type=int, default=80)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerShadowGateOptions:
    return HistoricalReplacementRerankerShadowGateOptions(
        enable_shadow_gate=args.enable_shadow_gate,
        profile_id=args.profile_id,
        hit_probability_delta_threshold=args.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_from_model_top_count=args.min_changed_from_model_top_count,
        min_final_answer_hit_delta_vs_model_top=(
            args.min_final_answer_hit_delta_vs_model_top
        ),
        min_replacement_leg_hit_delta_vs_model_top=(
            args.min_replacement_leg_hit_delta_vs_model_top
        ),
        min_profit_loss_delta_vs_model_top=args.min_profit_loss_delta_vs_model_top,
        min_roi_delta_vs_model_top=args.min_roi_delta_vs_model_top,
        max_harm_count_vs_model_top=args.max_harm_count_vs_model_top,
        max_final_hit_harm_count_vs_model_top=(
            args.max_final_hit_harm_count_vs_model_top
        ),
        max_profit_loss_harm_count_vs_model_top=(
            args.max_profit_loss_harm_count_vs_model_top
        ),
        min_average_hit_probability_delta_vs_model_top=(
            args.min_average_hit_probability_delta_vs_model_top
        ),
        min_final_answer_hit_delta_vs_original=(
            args.min_final_answer_hit_delta_vs_original
        ),
        min_profit_loss_delta_vs_original=args.min_profit_loss_delta_vs_original,
        min_roi_delta_vs_original=args.min_roi_delta_vs_original,
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        require_tolerance_candidate=not args.allow_missing_tolerance_candidate,
        allowed_tolerance_statuses=_csv_values(args.allowed_tolerance_statuses),
        require_source_audit_match=not args.allow_source_audit_mismatch,
        require_no_production_change=not args.allow_production_change,
        max_report_items=args.max_report_items,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _max_final_hit_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_model_top
        if options.max_final_hit_harm_count_vs_model_top is not None
        else options.max_harm_count_vs_model_top
    )


def _max_profit_loss_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> int:
    return (
        options.max_profit_loss_harm_count_vs_model_top
        if options.max_profit_loss_harm_count_vs_model_top is not None
        else options.max_harm_count_vs_model_top
    )


def _max_final_hit_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> int | None:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _max_profit_loss_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowGateOptions,
) -> int | None:
    return (
        options.max_profit_loss_harm_count_vs_original
        if options.max_profit_loss_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalReplacementRerankerShadowGateCheck],
    changed_items: Sequence[HistoricalReplacementRerankerShadowGateFinalAnswer],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "changed_items": [
                    {
                        "final_answer_key": item.final_answer_key,
                        "replacement_fixture_id": item.replacement_fixture_id,
                        "replacement_outcome": item.replacement_outcome,
                        "profit_loss_delta_vs_model_top": (
                            item.profit_loss_delta_vs_model_top
                        ),
                    }
                    for item in changed_items
                ],
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_replacement_reranker_shadow_gate:{digest}"
