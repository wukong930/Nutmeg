from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayOptions,
    HistoricalShortOddsRuntimeShadowReplayReport,
    build_historical_short_odds_runtime_shadow_replay_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type ShortOddsAdapterActivationGridStatus = Literal[
    "accepted_candidate_found",
    "no_accepted_candidate",
    "no_rules",
    "no_audit_items",
]
type ShortOddsAdapterActivationGridCandidateStatus = Literal["accepted", "rejected"]


DEFAULT_MIN_REPLACEMENT_PROBABILITY_VALUES = (0.55, 0.53, 0.50, 0.48)
DEFAULT_MAX_REPLACEMENT_DECIMAL_ODDS_VALUES = (1.75, 1.90, 2.10)
DEFAULT_MIN_DELTA_VS_MODEL_TOP_VALUES = (-0.015, -0.03, -0.05)
DEFAULT_MIN_DELTA_VS_ORIGINAL_VALUES = (-0.025, -0.05, -0.08)


class ShortOddsAdapterActivationGridOptions(BaseModel):
    rule_ids: tuple[str, ...] = ()
    probe_competition_ids: tuple[str, ...] = ()
    min_replacement_probability_values: tuple[float, ...] = (
        DEFAULT_MIN_REPLACEMENT_PROBABILITY_VALUES
    )
    max_replacement_decimal_odds_values: tuple[float, ...] = (
        DEFAULT_MAX_REPLACEMENT_DECIMAL_ODDS_VALUES
    )
    min_candidate_hit_probability_delta_vs_model_top_values: tuple[float, ...] = (
        DEFAULT_MIN_DELTA_VS_MODEL_TOP_VALUES
    )
    min_candidate_hit_probability_delta_vs_original_values: tuple[float, ...] = (
        DEFAULT_MIN_DELTA_VS_ORIGINAL_VALUES
    )
    max_candidate_hit_probability_delta_vs_model_top: float = 0.0
    min_decimal_odds_delta_vs_model_top: float = 0.0
    min_changed_final_answer_count: int = Field(default=2, ge=0)
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    max_report_items: int = Field(default=50, ge=1, le=500)
    max_candidate_count: int = Field(default=200, ge=1, le=5000)


class ShortOddsAdapterActivationGridCandidate(BaseModel):
    candidate_key: str
    status: ShortOddsAdapterActivationGridCandidateStatus
    accepted: bool
    rule_ids: list[str] = Field(default_factory=list)
    rule_profile_ids: list[str] = Field(default_factory=list)
    probe_competition_ids: list[str] = Field(default_factory=list)
    min_replacement_probability: float
    max_replacement_decimal_odds: float
    min_candidate_hit_probability_delta_vs_model_top: float
    max_candidate_hit_probability_delta_vs_model_top: float
    min_decimal_odds_delta_vs_model_top: float
    min_candidate_hit_probability_delta_vs_original: float
    shadow_replay_report_key: str
    shadow_replay_status: str
    shadow_replay_passed: bool
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(ge=0)
    profit_loss_harm_count_vs_original: int = Field(ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    changed_competition_counts: dict[str, int] = Field(default_factory=dict)
    failed_checks: list[str] = Field(default_factory=list)
    public_response_changed: bool = False
    production_recommendation_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class ShortOddsAdapterActivationGridReport(BaseModel):
    report_key: str
    status: ShortOddsAdapterActivationGridStatus
    accepted_candidate_found: bool
    source_audit_report_key: str
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    audit_final_answer_count: int = Field(ge=0)
    audit_item_count: int = Field(ge=0)
    audit_competition_ids: list[str] = Field(default_factory=list)
    probe_competition_ids: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    candidate_limit_reached: bool = False
    best_candidate_key: str | None = None
    best_candidate: ShortOddsAdapterActivationGridCandidate | None = None
    candidates: list[ShortOddsAdapterActivationGridCandidate] = Field(
        default_factory=list
    )
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_short_odds_adapter_activation_grid_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    options: ShortOddsAdapterActivationGridOptions | None = None,
) -> ShortOddsAdapterActivationGridReport:
    resolved_options = options or ShortOddsAdapterActivationGridOptions()
    selected_rules = rule_set.selected_rules(
        rule_ids=resolved_options.rule_ids,
        require_proposed_production_enabled=True,
        require_no_production_change=True,
    )
    audit_competition_ids = _audit_competition_ids(audit_report)
    probe_competition_ids = _probe_competition_ids(
        audit_competition_ids,
        options=resolved_options,
    )
    warnings = list(audit_report.warnings)
    if not selected_rules:
        warnings.append("short_odds_adapter_activation_grid:no_enabled_rules")
        return _report(
            status="no_rules",
            audit_report=audit_report,
            rule_set=rule_set,
            selected_rules=selected_rules,
            audit_competition_ids=audit_competition_ids,
            probe_competition_ids=probe_competition_ids,
            candidates=[],
            candidate_limit_reached=False,
            warnings=warnings,
            options=resolved_options,
        )
    if not audit_report.items:
        warnings.append("short_odds_adapter_activation_grid:no_audit_items")
        return _report(
            status="no_audit_items",
            audit_report=audit_report,
            rule_set=rule_set,
            selected_rules=selected_rules,
            audit_competition_ids=audit_competition_ids,
            probe_competition_ids=probe_competition_ids,
            candidates=[],
            candidate_limit_reached=False,
            warnings=warnings,
            options=resolved_options,
        )

    candidates: list[ShortOddsAdapterActivationGridCandidate] = []
    candidate_limit_reached = False
    for grid in _grid_parameters(resolved_options):
        if len(candidates) >= resolved_options.max_candidate_count:
            candidate_limit_reached = True
            warnings.append("short_odds_adapter_activation_grid:candidate_limit_reached")
            break
        replay = build_historical_short_odds_runtime_shadow_replay_report(
            audit_report,
            rule_set=_candidate_rule_set(
                rule_set,
                selected_rules=selected_rules,
                probe_competition_ids=probe_competition_ids,
                grid=grid,
            ),
            options=_shadow_options(resolved_options),
        )
        candidates.append(
            _candidate(
                replay,
                selected_rules=selected_rules,
                probe_competition_ids=probe_competition_ids,
                grid=grid,
            )
        )

    accepted_count = sum(1 for candidate in candidates if candidate.accepted)
    status: ShortOddsAdapterActivationGridStatus = (
        "accepted_candidate_found" if accepted_count > 0 else "no_accepted_candidate"
    )
    return _report(
        status=status,
        audit_report=audit_report,
        rule_set=rule_set,
        selected_rules=selected_rules,
        audit_competition_ids=audit_competition_ids,
        probe_competition_ids=probe_competition_ids,
        candidates=sorted(candidates, key=_candidate_sort_key, reverse=True),
        candidate_limit_reached=candidate_limit_reached,
        warnings=warnings,
        options=resolved_options,
    )


def load_short_odds_adapter_activation_grid_report(
    path: Path | str,
) -> ShortOddsAdapterActivationGridReport:
    return ShortOddsAdapterActivationGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_short_odds_adapter_activation_grid_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        rule_set=load_short_odds_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=True,
        ),
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
    if (
        args.require_accepted_candidate
        and not report.accepted_candidate_found
        and not args.no_fail_process
    ):
        raise SystemExit(1)


class _GridParameter(BaseModel):
    min_replacement_probability: float
    max_replacement_decimal_odds: float
    min_candidate_hit_probability_delta_vs_model_top: float
    max_candidate_hit_probability_delta_vs_model_top: float
    min_decimal_odds_delta_vs_model_top: float
    min_candidate_hit_probability_delta_vs_original: float


def _grid_parameters(
    options: ShortOddsAdapterActivationGridOptions,
) -> list[_GridParameter]:
    return [
        _GridParameter(
            min_replacement_probability=min_probability,
            max_replacement_decimal_odds=max_odds,
            min_candidate_hit_probability_delta_vs_model_top=min_delta_vs_model_top,
            max_candidate_hit_probability_delta_vs_model_top=(
                options.max_candidate_hit_probability_delta_vs_model_top
            ),
            min_decimal_odds_delta_vs_model_top=(
                options.min_decimal_odds_delta_vs_model_top
            ),
            min_candidate_hit_probability_delta_vs_original=min_delta_vs_original,
        )
        for (
            min_probability,
            max_odds,
            min_delta_vs_model_top,
            min_delta_vs_original,
        ) in product(
            _unique_floats(options.min_replacement_probability_values),
            _unique_floats(options.max_replacement_decimal_odds_values),
            _unique_floats(
                options.min_candidate_hit_probability_delta_vs_model_top_values
            ),
            _unique_floats(
                options.min_candidate_hit_probability_delta_vs_original_values
            ),
        )
    ]


def _candidate_rule_set(
    rule_set: ShortOddsRuntimeRuleSet,
    *,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    probe_competition_ids: Sequence[str],
    grid: _GridParameter,
) -> ShortOddsRuntimeRuleSet:
    patched_rules = [
        _candidate_rule(
            rule,
            probe_competition_ids=probe_competition_ids,
            grid=grid,
        )
        for rule in selected_rules
    ]
    return rule_set.model_copy(
        update={
            "shadow_replay_enabled": True,
            "rules": _replace_selected_rules(rule_set.rules, patched_rules),
        }
    )


def _candidate_rule(
    rule: ShortOddsRuntimeReplacementRule,
    *,
    probe_competition_ids: Sequence[str],
    grid: _GridParameter,
) -> ShortOddsRuntimeReplacementRule:
    constraints: dict[str, object] = dict(
        rule.constraints().model_dump(mode="json", exclude_none=True)
    )
    constraints.update(
        {
            "min_replacement_probability": grid.min_replacement_probability,
            "max_replacement_decimal_odds": grid.max_replacement_decimal_odds,
            "min_candidate_hit_probability_delta_vs_model_top": (
                grid.min_candidate_hit_probability_delta_vs_model_top
            ),
            "max_candidate_hit_probability_delta_vs_model_top": (
                grid.max_candidate_hit_probability_delta_vs_model_top
            ),
            "min_decimal_odds_delta_vs_model_top": (
                grid.min_decimal_odds_delta_vs_model_top
            ),
            "min_candidate_hit_probability_delta_vs_original": (
                grid.min_candidate_hit_probability_delta_vs_original
            ),
        }
    )
    return rule.model_copy(
        update={
            "allowed_competition_ids": list(probe_competition_ids),
            "constraints_json": constraints,
        }
    )


def _replace_selected_rules(
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    replacements: Sequence[ShortOddsRuntimeReplacementRule],
) -> list[ShortOddsRuntimeReplacementRule]:
    by_rule_id = {rule.rule_id: rule for rule in replacements}
    return [by_rule_id.get(rule.rule_id, rule) for rule in rules]


def _shadow_options(
    options: ShortOddsAdapterActivationGridOptions,
) -> HistoricalShortOddsRuntimeShadowReplayOptions:
    return HistoricalShortOddsRuntimeShadowReplayOptions(
        enable_shadow_replay=True,
        rule_ids=options.rule_ids,
        min_final_answer_count=1,
        min_changed_final_answer_count=options.min_changed_final_answer_count,
        min_final_answer_hit_rate_delta=options.min_final_answer_hit_rate_delta,
        min_roi_delta=options.min_roi_delta,
        min_profit_loss_delta=options.min_profit_loss_delta,
        max_harm_count_vs_original=options.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            options.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            options.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_average_hit_probability_delta_vs_original
        ),
        require_no_production_change=True,
        max_report_items=options.max_report_items,
    )


def _candidate(
    replay: HistoricalShortOddsRuntimeShadowReplayReport,
    *,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    probe_competition_ids: Sequence[str],
    grid: _GridParameter,
) -> ShortOddsAdapterActivationGridCandidate:
    failed_checks = [check.name for check in replay.checks if check.status == "failed"]
    accepted = (
        replay.passed
        and not replay.public_response_changed
        and not replay.production_recommendation_changed
    )
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_adapter_activation_grid_candidate_v3_1",
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "rule_ids": [rule.rule_id for rule in selected_rules],
        "probe_competition_ids": list(probe_competition_ids),
        "grid": grid.model_dump(mode="json"),
        "shadow_replay_report_key": replay.report_key,
        "shadow_replay_passed": replay.passed,
        "changed_final_answer_count": replay.changed_final_answer_count,
        "final_answer_hit_rate_delta": replay.final_answer_hit_rate_delta,
        "roi_delta": replay.roi_delta,
        "profit_loss_delta": replay.profit_loss_delta,
        "harm_count_vs_original": replay.harm_count_vs_original,
        "final_hit_harm_count_vs_original": replay.final_hit_harm_count_vs_original,
        "profit_loss_harm_count_vs_original": (
            replay.profit_loss_harm_count_vs_original
        ),
        "failed_checks": failed_checks,
        "production_recommendation_changed": replay.production_recommendation_changed,
        "public_response_changed": replay.public_response_changed,
    }
    candidate_key = _digest_key("short_odds_adapter_activation_grid_candidate", summary)
    return ShortOddsAdapterActivationGridCandidate(
        candidate_key=candidate_key,
        status="accepted" if accepted else "rejected",
        accepted=accepted,
        rule_ids=[rule.rule_id for rule in selected_rules],
        rule_profile_ids=[rule.profile_id for rule in selected_rules],
        probe_competition_ids=list(probe_competition_ids),
        min_replacement_probability=grid.min_replacement_probability,
        max_replacement_decimal_odds=grid.max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top=(
            grid.min_candidate_hit_probability_delta_vs_model_top
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            grid.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=grid.min_decimal_odds_delta_vs_model_top,
        min_candidate_hit_probability_delta_vs_original=(
            grid.min_candidate_hit_probability_delta_vs_original
        ),
        shadow_replay_report_key=replay.report_key,
        shadow_replay_status=replay.status,
        shadow_replay_passed=replay.passed,
        final_answer_count=replay.final_answer_count,
        changed_final_answer_count=replay.changed_final_answer_count,
        final_answer_hit_rate_delta=replay.final_answer_hit_rate_delta,
        roi_delta=replay.roi_delta,
        profit_loss_delta=replay.profit_loss_delta,
        harm_count_vs_original=replay.harm_count_vs_original,
        final_hit_harm_count_vs_original=replay.final_hit_harm_count_vs_original,
        profit_loss_harm_count_vs_original=(
            replay.profit_loss_harm_count_vs_original
        ),
        average_hit_probability_delta_vs_original=(
            replay.average_hit_probability_delta_vs_original
        ),
        changed_competition_counts=_changed_competition_counts(replay),
        failed_checks=failed_checks,
        public_response_changed=replay.public_response_changed,
        production_recommendation_changed=replay.production_recommendation_changed,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _report(
    *,
    status: ShortOddsAdapterActivationGridStatus,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    audit_competition_ids: Sequence[str],
    probe_competition_ids: Sequence[str],
    candidates: Sequence[ShortOddsAdapterActivationGridCandidate],
    candidate_limit_reached: bool,
    warnings: Sequence[str],
    options: ShortOddsAdapterActivationGridOptions,
) -> ShortOddsAdapterActivationGridReport:
    accepted_candidates = [candidate for candidate in candidates if candidate.accepted]
    best_candidate = accepted_candidates[0] if accepted_candidates else None
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_adapter_activation_grid_v3_1",
        "status": status,
        "accepted_candidate_found": status == "accepted_candidate_found",
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "selected_rule_count": len(selected_rules),
        "audit_final_answer_count": audit_report.final_answer_count,
        "audit_item_count": len(audit_report.items),
        "audit_competition_ids": list(audit_competition_ids),
        "probe_competition_ids": list(probe_competition_ids),
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "candidate_limit_reached": candidate_limit_reached,
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "options": options.model_dump(mode="json"),
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "warnings": list(warnings),
    }
    report_key = _digest_key(
        "short_odds_adapter_activation_grid",
        {
            **summary,
            "candidate_keys": [candidate.candidate_key for candidate in candidates],
        },
    )
    return ShortOddsAdapterActivationGridReport(
        report_key=report_key,
        status=status,
        accepted_candidate_found=status == "accepted_candidate_found",
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        audit_final_answer_count=audit_report.final_answer_count,
        audit_item_count=len(audit_report.items),
        audit_competition_ids=list(audit_competition_ids),
        probe_competition_ids=list(probe_competition_ids),
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        candidate_limit_reached=candidate_limit_reached,
        best_candidate_key=(
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        best_candidate=best_candidate,
        candidates=list(candidates)[: options.max_report_items],
        production_recommendation_changed=False,
        public_response_changed=False,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _candidate_sort_key(
    candidate: ShortOddsAdapterActivationGridCandidate,
) -> tuple[float, float, float, float, float, float, float]:
    return (
        1.0 if candidate.accepted else 0.0,
        candidate.final_answer_hit_rate_delta
        if candidate.final_answer_hit_rate_delta is not None
        else -999.0,
        candidate.roi_delta if candidate.roi_delta is not None else -999.0,
        candidate.profit_loss_delta,
        float(candidate.changed_final_answer_count),
        candidate.average_hit_probability_delta_vs_original
        if candidate.average_hit_probability_delta_vs_original is not None
        else -999.0,
        -candidate.min_replacement_probability,
    )


def _changed_competition_counts(
    replay: HistoricalShortOddsRuntimeShadowReplayReport,
) -> dict[str, int]:
    counts: Counter[str] = Counter(
        item.competition_id for item in replay.changed_items if item.changed_by_shadow
    )
    return {
        key: value
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _audit_competition_ids(
    audit_report: HistoricalCandidateMarginalAuditReport,
) -> list[str]:
    return sorted({item.competition_id for item in audit_report.items})


def _probe_competition_ids(
    audit_competition_ids: Sequence[str],
    *,
    options: ShortOddsAdapterActivationGridOptions,
) -> tuple[str, ...]:
    if options.probe_competition_ids:
        return tuple(sorted(set(options.probe_competition_ids)))
    return tuple(audit_competition_ids)


def _unique_floats(values: Sequence[float]) -> tuple[float, ...]:
    seen: set[float] = set()
    unique: list[float] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


def _digest_key(prefix: str, payload: Mapping[str, object]) -> str:
    body = dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Search expanded-league short-odds adapter thresholds with no-harm gates."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--rule-ids", default="")
    parser.add_argument("--probe-competition-ids", default="")
    parser.add_argument(
        "--min-replacement-probability-values",
        default=_csv_default(DEFAULT_MIN_REPLACEMENT_PROBABILITY_VALUES),
    )
    parser.add_argument(
        "--max-replacement-decimal-odds-values",
        default=_csv_default(DEFAULT_MAX_REPLACEMENT_DECIMAL_ODDS_VALUES),
    )
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-model-top-values",
        default=_csv_default(DEFAULT_MIN_DELTA_VS_MODEL_TOP_VALUES),
    )
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-original-values",
        default=_csv_default(DEFAULT_MIN_DELTA_VS_ORIGINAL_VALUES),
    )
    parser.add_argument(
        "--max-candidate-hit-probability-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-decimal-odds-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=2)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-report-items", type=int, default=50)
    parser.add_argument("--max-candidate-count", type=int, default=200)
    parser.add_argument("--require-accepted-candidate", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> ShortOddsAdapterActivationGridOptions:
    return ShortOddsAdapterActivationGridOptions(
        rule_ids=tuple(_csv(args.rule_ids)),
        probe_competition_ids=tuple(_csv(args.probe_competition_ids)),
        min_replacement_probability_values=_csv_floats(
            args.min_replacement_probability_values
        ),
        max_replacement_decimal_odds_values=_csv_floats(
            args.max_replacement_decimal_odds_values
        ),
        min_candidate_hit_probability_delta_vs_model_top_values=_csv_floats(
            args.min_candidate_hit_probability_delta_vs_model_top_values
        ),
        min_candidate_hit_probability_delta_vs_original_values=_csv_floats(
            args.min_candidate_hit_probability_delta_vs_original_values
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            args.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=args.min_decimal_odds_delta_vs_model_top,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=args.max_final_hit_harm_count_vs_original,
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        max_report_items=args.max_report_items,
        max_candidate_count=args.max_candidate_count,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _csv_floats(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _csv_default(values: Sequence[float]) -> str:
    return ",".join(str(value) for value in values)
