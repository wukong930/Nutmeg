from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

type HistoricalGlobalPlannerShortOddsAdapterGateStatus = Literal["passed", "failed"]
type HistoricalGlobalPlannerShortOddsAdapterGateCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalGlobalPlannerShortOddsAdapterGateOptions(BaseModel):
    require_default_path_unchanged: bool = True
    require_shadow_path_unchanged: bool = True
    require_explicit_opt_in_changed: bool = True
    require_shadow_adapter_applied: bool = True
    require_opt_in_adapter_applied: bool = True
    require_runtime_replay_passed: bool = True
    min_runtime_final_answer_count: int = Field(default=30, ge=0)
    min_runtime_changed_final_answer_count: int = Field(default=5, ge=0)
    min_runtime_final_answer_hit_rate_delta: float = 0.0
    min_runtime_roi_delta: float = 0.0
    min_runtime_profit_loss_delta: float = 0.0
    max_runtime_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_runtime_final_hit_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_runtime_profit_loss_harm_count_vs_original: int | None = Field(default=0, ge=0)
    min_runtime_average_hit_probability_delta: float = -0.02
    require_runtime_public_response_unchanged: bool = True
    require_runtime_production_recommendation_unchanged: bool = True


class HistoricalGlobalPlannerShortOddsAdapterGateCheck(BaseModel):
    name: str
    status: HistoricalGlobalPlannerShortOddsAdapterGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalGlobalPlannerShortOddsAdapterGateReport(BaseModel):
    report_key: str
    status: HistoricalGlobalPlannerShortOddsAdapterGateStatus
    passed: bool
    source_planner_branch_report_key: str
    source_runtime_shadow_replay_report_key: str
    source_rule_profile_version: str
    planner_default_path_changed: bool | None = None
    planner_shadow_path_changed: bool | None = None
    planner_explicit_opt_in_changed: bool | None = None
    planner_shadow_adapter_status: str | None = None
    planner_opt_in_adapter_status: str | None = None
    runtime_replay_passed: bool
    runtime_replay_status: str
    runtime_final_answer_count: int = Field(ge=0)
    runtime_changed_final_answer_count: int = Field(ge=0)
    runtime_final_answer_hit_rate_delta: float | None = None
    runtime_roi_delta: float | None = None
    runtime_profit_loss_delta: float
    runtime_harm_count_vs_original: int = Field(ge=0)
    runtime_final_hit_harm_count_vs_original: int = Field(ge=0)
    runtime_profit_loss_harm_count_vs_original: int = Field(ge=0)
    runtime_average_hit_probability_delta: float | None = None
    runtime_public_response_changed: bool
    runtime_production_recommendation_changed: bool
    checks: list[HistoricalGlobalPlannerShortOddsAdapterGateCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_global_planner_short_odds_adapter_gate_report(
    planner_branch_report: Mapping[str, object],
    runtime_shadow_replay: HistoricalShortOddsRuntimeShadowReplayReport,
    *,
    options: HistoricalGlobalPlannerShortOddsAdapterGateOptions | None = None,
) -> HistoricalGlobalPlannerShortOddsAdapterGateReport:
    resolved_options = options or HistoricalGlobalPlannerShortOddsAdapterGateOptions()
    default_path_changed = _optional_bool(
        planner_branch_report.get("default_path_changed")
    )
    shadow_path_changed = _optional_bool(planner_branch_report.get("shadow_path_changed"))
    explicit_opt_in_changed = _optional_bool(
        planner_branch_report.get("explicit_opt_in_changed")
    )
    shadow_case = _case(planner_branch_report, "shadow_only")
    opt_in_case = _case(planner_branch_report, "explicit_opt_in")
    shadow_status = _adapter_status(shadow_case)
    opt_in_status = _adapter_status(opt_in_case)
    final_hit_harm_count = runtime_shadow_replay.final_hit_harm_count_vs_original
    profit_loss_harm_count = runtime_shadow_replay.profit_loss_harm_count_vs_original
    checks = [
        _required_bool_check(
            name="planner_default_path_unchanged",
            actual=default_path_changed is False,
            required=resolved_options.require_default_path_unchanged,
            detail="default-disabled planner branch must not change the final answer",
        ),
        _required_bool_check(
            name="planner_shadow_path_unchanged",
            actual=shadow_path_changed is False,
            required=resolved_options.require_shadow_path_unchanged,
            detail="shadow-only planner branch must not change the final answer",
        ),
        _required_bool_check(
            name="planner_explicit_opt_in_changed",
            actual=explicit_opt_in_changed is True,
            required=resolved_options.require_explicit_opt_in_changed,
            detail="explicit opt-in branch should exercise the adapter replacement",
        ),
        _required_bool_check(
            name="planner_shadow_adapter_applied",
            actual=shadow_status == "applied",
            required=resolved_options.require_shadow_adapter_applied,
            detail="shadow-only planner branch should record an applied adapter summary",
        ),
        _required_bool_check(
            name="planner_opt_in_adapter_applied",
            actual=opt_in_status == "applied",
            required=resolved_options.require_opt_in_adapter_applied,
            detail="explicit opt-in planner branch should apply the adapter",
        ),
        _required_bool_check(
            name="runtime_shadow_replay_passed",
            actual=runtime_shadow_replay.passed,
            required=resolved_options.require_runtime_replay_passed,
            detail="source real-history runtime shadow replay should pass",
        ),
        _required_bool_check(
            name="runtime_shadow_replay_status_passed",
            actual=runtime_shadow_replay.status == "shadow_replay_passed",
            required=resolved_options.require_runtime_replay_passed,
            detail="source real-history runtime shadow replay status should be passed",
        ),
        _check_minimum(
            name="runtime_final_answer_count",
            actual=runtime_shadow_replay.final_answer_count,
            threshold=resolved_options.min_runtime_final_answer_count,
            detail="source replay should cover enough final answers",
        ),
        _check_minimum(
            name="runtime_changed_final_answer_count",
            actual=runtime_shadow_replay.changed_final_answer_count,
            threshold=resolved_options.min_runtime_changed_final_answer_count,
            detail="source replay should affect enough final answers",
        ),
        _check_optional_minimum(
            name="runtime_final_answer_hit_rate_delta",
            actual=runtime_shadow_replay.final_answer_hit_rate_delta,
            threshold=resolved_options.min_runtime_final_answer_hit_rate_delta,
            detail="source replay hit rate should not regress",
        ),
        _check_optional_minimum(
            name="runtime_roi_delta",
            actual=runtime_shadow_replay.roi_delta,
            threshold=resolved_options.min_runtime_roi_delta,
            detail="source replay ROI should not regress",
        ),
        _check_minimum(
            name="runtime_profit_loss_delta",
            actual=runtime_shadow_replay.profit_loss_delta,
            threshold=resolved_options.min_runtime_profit_loss_delta,
            detail="source replay profit/loss should not regress",
        ),
        _check_optional_maximum(
            name="runtime_harm_count_vs_original",
            actual=runtime_shadow_replay.harm_count_vs_original,
            threshold=resolved_options.max_runtime_harm_count_vs_original,
            detail="source replay should not harm original final answers",
        ),
        _check_optional_maximum(
            name="runtime_final_hit_harm_count_vs_original",
            actual=final_hit_harm_count,
            threshold=resolved_options.max_runtime_final_hit_harm_count_vs_original,
            detail="source replay should not turn original hits into misses",
        ),
        _check_optional_maximum(
            name="runtime_profit_loss_harm_count_vs_original",
            actual=profit_loss_harm_count,
            threshold=resolved_options.max_runtime_profit_loss_harm_count_vs_original,
            detail="source replay should not reduce original final-answer profit/loss",
        ),
        _check_optional_minimum(
            name="runtime_average_hit_probability_delta",
            actual=runtime_shadow_replay.average_hit_probability_delta_vs_original,
            threshold=resolved_options.min_runtime_average_hit_probability_delta,
            detail="source replay hit-probability loss should stay inside tolerance",
        ),
        _required_bool_check(
            name="runtime_public_response_unchanged",
            actual=not runtime_shadow_replay.public_response_changed,
            required=resolved_options.require_runtime_public_response_unchanged,
            detail="source replay should not change public responses",
        ),
        _required_bool_check(
            name="runtime_production_recommendation_unchanged",
            actual=not runtime_shadow_replay.production_recommendation_changed,
            required=(
                resolved_options.require_runtime_production_recommendation_unchanged
            ),
            detail="source replay should not change production recommendations",
        ),
    ]
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    warnings = [
        f"global_planner_short_odds_adapter_gate:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary = {
        "calculation_basis": "global_planner_short_odds_adapter_gate_v3_1",
        "passed": passed,
        "failed_checks": [check.name for check in failed_checks],
        "source_planner_branch_report_key": _planner_branch_report_key(
            planner_branch_report
        ),
        "source_runtime_shadow_replay_report_key": runtime_shadow_replay.report_key,
        "source_rule_profile_version": runtime_shadow_replay.source_rule_profile_version,
        "planner_default_path_changed": default_path_changed,
        "planner_shadow_path_changed": shadow_path_changed,
        "planner_explicit_opt_in_changed": explicit_opt_in_changed,
        "planner_shadow_adapter_status": shadow_status,
        "planner_opt_in_adapter_status": opt_in_status,
        "runtime_replay_passed": runtime_shadow_replay.passed,
        "runtime_replay_status": runtime_shadow_replay.status,
        "runtime_final_answer_count": runtime_shadow_replay.final_answer_count,
        "runtime_changed_final_answer_count": (
            runtime_shadow_replay.changed_final_answer_count
        ),
        "runtime_final_answer_hit_rate_delta": (
            runtime_shadow_replay.final_answer_hit_rate_delta
        ),
        "runtime_roi_delta": runtime_shadow_replay.roi_delta,
        "runtime_profit_loss_delta": runtime_shadow_replay.profit_loss_delta,
        "runtime_harm_count_vs_original": runtime_shadow_replay.harm_count_vs_original,
        "runtime_final_hit_harm_count_vs_original": final_hit_harm_count,
        "runtime_profit_loss_harm_count_vs_original": profit_loss_harm_count,
        "runtime_average_hit_probability_delta": (
            runtime_shadow_replay.average_hit_probability_delta_vs_original
        ),
        "runtime_public_response_changed": runtime_shadow_replay.public_response_changed,
        "runtime_production_recommendation_changed": (
            runtime_shadow_replay.production_recommendation_changed
        ),
        "warnings": warnings,
    }
    report_key = _report_key(summary)
    return HistoricalGlobalPlannerShortOddsAdapterGateReport(
        report_key=report_key,
        status="passed" if passed else "failed",
        passed=passed,
        source_planner_branch_report_key=str(summary["source_planner_branch_report_key"]),
        source_runtime_shadow_replay_report_key=runtime_shadow_replay.report_key,
        source_rule_profile_version=runtime_shadow_replay.source_rule_profile_version,
        planner_default_path_changed=default_path_changed,
        planner_shadow_path_changed=shadow_path_changed,
        planner_explicit_opt_in_changed=explicit_opt_in_changed,
        planner_shadow_adapter_status=shadow_status,
        planner_opt_in_adapter_status=opt_in_status,
        runtime_replay_passed=runtime_shadow_replay.passed,
        runtime_replay_status=runtime_shadow_replay.status,
        runtime_final_answer_count=runtime_shadow_replay.final_answer_count,
        runtime_changed_final_answer_count=(
            runtime_shadow_replay.changed_final_answer_count
        ),
        runtime_final_answer_hit_rate_delta=(
            runtime_shadow_replay.final_answer_hit_rate_delta
        ),
        runtime_roi_delta=runtime_shadow_replay.roi_delta,
        runtime_profit_loss_delta=runtime_shadow_replay.profit_loss_delta,
        runtime_harm_count_vs_original=runtime_shadow_replay.harm_count_vs_original,
        runtime_final_hit_harm_count_vs_original=final_hit_harm_count,
        runtime_profit_loss_harm_count_vs_original=profit_loss_harm_count,
        runtime_average_hit_probability_delta=(
            runtime_shadow_replay.average_hit_probability_delta_vs_original
        ),
        runtime_public_response_changed=runtime_shadow_replay.public_response_changed,
        runtime_production_recommendation_changed=(
            runtime_shadow_replay.production_recommendation_changed
        ),
        checks=checks,
        warnings=warnings,
        summary_json=summary,
    )


def load_global_planner_short_odds_adapter_gate_report(
    path: Path | str,
) -> HistoricalGlobalPlannerShortOddsAdapterGateReport:
    return HistoricalGlobalPlannerShortOddsAdapterGateReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_global_planner_short_odds_adapter_branch_report(
    path: Path | str,
) -> dict[str, object]:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("global planner short-odds adapter branch report must be a JSON object")
    return payload


def load_historical_short_odds_runtime_shadow_replay_report(
    path: Path | str,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_global_planner_short_odds_adapter_gate_report(
        load_global_planner_short_odds_adapter_branch_report(
            args.planner_branch_report
        ),
        load_historical_short_odds_runtime_shadow_replay_report(
            args.runtime_shadow_replay_report
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _case(report: Mapping[str, object], case_name: str) -> Mapping[str, object] | None:
    cases = report.get("cases")
    if not isinstance(cases, Sequence) or isinstance(cases, str | bytes | bytearray):
        return None
    for item in cases:
        if isinstance(item, Mapping) and item.get("case") == case_name:
            return item
    return None


def _adapter_status(case: Mapping[str, object] | None) -> str | None:
    if case is None:
        return None
    summary = case.get("adapter_summary")
    if not isinstance(summary, Mapping):
        return None
    status = summary.get("status")
    return str(status) if status is not None else None


def _planner_branch_report_key(report: Mapping[str, object]) -> str:
    basis = report.get("calculation_basis")
    payload = {
        "calculation_basis": basis,
        "default_path_changed": report.get("default_path_changed"),
        "shadow_path_changed": report.get("shadow_path_changed"),
        "explicit_opt_in_changed": report.get("explicit_opt_in_changed"),
        "cases": [
            {
                "case": item.get("case"),
                "best_fixture_ids": item.get("best_fixture_ids"),
                "adapter_status": _adapter_status(item),
            }
            for item in _case_items(report)
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"global_planner_short_odds_adapter_branch:{digest}"


def _case_items(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    cases = report.get("cases")
    if not isinstance(cases, Sequence) or isinstance(cases, str | bytes | bytearray):
        return []
    return [item for item in cases if isinstance(item, Mapping)]


def _report_key(summary: Mapping[str, object]) -> str:
    digest = sha256(
        dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"global_planner_short_odds_adapter_gate:{digest}"


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterGateCheck:
    if not required:
        return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=True,
            detail=detail,
        )
    return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _check_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterGateCheck:
    if actual is None:
        return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterGateCheck:
    if threshold is None:
        return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return _check_minimum(name=name, actual=actual, threshold=threshold, detail=detail)


def _check_optional_maximum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterGateCheck:
    if threshold is None:
        return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    if actual is None:
        return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalGlobalPlannerShortOddsAdapterGateCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Gate the global planner short-odds adapter branch against real-history "
            "runtime shadow replay evidence."
        )
    )
    parser.add_argument("--planner-branch-report", type=Path, required=True)
    parser.add_argument("--runtime-shadow-replay-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--allow-default-path-change", action="store_true")
    parser.add_argument("--allow-shadow-path-change", action="store_true")
    parser.add_argument("--allow-missing-explicit-opt-in-change", action="store_true")
    parser.add_argument("--allow-shadow-adapter-not-applied", action="store_true")
    parser.add_argument("--allow-opt-in-adapter-not-applied", action="store_true")
    parser.add_argument("--allow-runtime-replay-failure", action="store_true")
    parser.add_argument("--min-runtime-final-answer-count", type=int, default=30)
    parser.add_argument("--min-runtime-changed-final-answer-count", type=int, default=5)
    parser.add_argument(
        "--min-runtime-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-runtime-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-runtime-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-runtime-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-runtime-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-runtime-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-runtime-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--allow-runtime-public-response-change", action="store_true")
    parser.add_argument(
        "--allow-runtime-production-recommendation-change",
        action="store_true",
    )
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalGlobalPlannerShortOddsAdapterGateOptions:
    return HistoricalGlobalPlannerShortOddsAdapterGateOptions(
        require_default_path_unchanged=not args.allow_default_path_change,
        require_shadow_path_unchanged=not args.allow_shadow_path_change,
        require_explicit_opt_in_changed=(
            not args.allow_missing_explicit_opt_in_change
        ),
        require_shadow_adapter_applied=not args.allow_shadow_adapter_not_applied,
        require_opt_in_adapter_applied=not args.allow_opt_in_adapter_not_applied,
        require_runtime_replay_passed=not args.allow_runtime_replay_failure,
        min_runtime_final_answer_count=args.min_runtime_final_answer_count,
        min_runtime_changed_final_answer_count=(
            args.min_runtime_changed_final_answer_count
        ),
        min_runtime_final_answer_hit_rate_delta=(
            args.min_runtime_final_answer_hit_rate_delta
        ),
        min_runtime_roi_delta=args.min_runtime_roi_delta,
        min_runtime_profit_loss_delta=args.min_runtime_profit_loss_delta,
        max_runtime_harm_count_vs_original=args.max_runtime_harm_count_vs_original,
        max_runtime_final_hit_harm_count_vs_original=(
            args.max_runtime_final_hit_harm_count_vs_original
        ),
        max_runtime_profit_loss_harm_count_vs_original=(
            args.max_runtime_profit_loss_harm_count_vs_original
        ),
        min_runtime_average_hit_probability_delta=(
            args.min_runtime_average_hit_probability_delta
        ),
        require_runtime_public_response_unchanged=(
            not args.allow_runtime_public_response_change
        ),
        require_runtime_production_recommendation_unchanged=(
            not args.allow_runtime_production_recommendation_change
        ),
    )
