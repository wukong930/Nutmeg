from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.global_planner_short_odds_adapter_gate import (
    HistoricalGlobalPlannerShortOddsAdapterGateReport,
    load_global_planner_short_odds_adapter_gate_report,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

type HistoricalGlobalPlannerShortOddsAdapterSampleExpansionStatus = Literal[
    "expansion_ready",
    "research_only",
    "blocked",
]
type HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheckStatus = Literal[
    "passed",
    "failed",
    "watchlist",
    "skipped",
]


class HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions(BaseModel):
    min_supplemental_report_count: int = Field(default=1, ge=0)
    min_supplemental_final_answer_count: int = Field(default=50, ge=0)
    min_supplemental_changed_final_answer_count: int = Field(default=1, ge=0)
    min_combined_final_answer_count: int = Field(default=80, ge=0)
    min_combined_changed_final_answer_count: int = Field(default=5, ge=0)
    min_combined_final_answer_hit_rate_delta: float = 0.0
    min_combined_roi_delta: float = 0.0
    min_combined_profit_loss_delta: float = 0.0
    max_combined_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_combined_final_hit_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    max_combined_profit_loss_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    min_combined_average_hit_probability_delta: float = -0.02
    require_no_public_response_change: bool = True
    require_no_production_recommendation_change: bool = True


class HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(BaseModel):
    name: str
    status: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport(BaseModel):
    report_key: str
    status: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionStatus
    passed: bool
    promotion_ready: bool
    base_gate_report_key: str
    base_gate_passed: bool
    supplemental_report_count: int = Field(ge=0)
    supplemental_passed_report_count: int = Field(ge=0)
    supplemental_failed_report_count: int = Field(ge=0)
    supplemental_final_answer_count: int = Field(ge=0)
    supplemental_changed_final_answer_count: int = Field(ge=0)
    supplemental_activation_rate: float | None = None
    combined_final_answer_count: int = Field(ge=0)
    combined_changed_final_answer_count: int = Field(ge=0)
    combined_activation_rate: float | None = None
    combined_final_answer_hit_rate_delta: float | None = None
    combined_roi_delta: float | None = None
    combined_profit_loss_delta: float
    combined_harm_count_vs_original: int = Field(ge=0)
    combined_final_hit_harm_count_vs_original: int = Field(ge=0)
    combined_profit_loss_harm_count_vs_original: int = Field(ge=0)
    combined_average_hit_probability_delta: float | None = None
    public_response_changed: bool
    production_recommendation_changed: bool
    checks: list[HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_global_planner_short_odds_adapter_sample_expansion_report(
    base_gate: HistoricalGlobalPlannerShortOddsAdapterGateReport,
    *,
    supplemental_replays: Sequence[HistoricalShortOddsRuntimeShadowReplayReport],
    options: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions | None = None,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport:
    resolved_options = (
        options or HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions()
    )
    combined = _combined_metrics(base_gate, supplemental_replays)
    supplemental_final_answer_count = sum(
        replay.final_answer_count for replay in supplemental_replays
    )
    supplemental_changed_final_answer_count = sum(
        replay.changed_final_answer_count for replay in supplemental_replays
    )
    public_response_changed = base_gate.runtime_public_response_changed or any(
        replay.public_response_changed for replay in supplemental_replays
    )
    production_recommendation_changed = (
        base_gate.runtime_production_recommendation_changed
        or any(replay.production_recommendation_changed for replay in supplemental_replays)
    )
    checks = [
        _required_bool_check(
            name="base_gate_passed",
            actual=base_gate.passed,
            detail="core planner adapter gate should pass before sample expansion",
        ),
        _minimum_check(
            name="supplemental_report_count",
            actual=len(supplemental_replays),
            threshold=resolved_options.min_supplemental_report_count,
            detail="sample expansion should include supplemental historical evidence",
        ),
        _maximum_check(
            name="supplemental_failed_report_count",
            actual=sum(1 for replay in supplemental_replays if not replay.passed),
            threshold=0,
            detail="supplemental shadow replay reports should not fail",
        ),
        _minimum_check(
            name="supplemental_final_answer_count",
            actual=supplemental_final_answer_count,
            threshold=resolved_options.min_supplemental_final_answer_count,
            detail="supplemental evidence should cover enough final answers",
        ),
        _watchlist_minimum_check(
            name="supplemental_changed_final_answer_count",
            actual=supplemental_changed_final_answer_count,
            threshold=resolved_options.min_supplemental_changed_final_answer_count,
            detail=(
                "supplemental evidence should activate replacements before promotion"
            ),
        ),
        _minimum_check(
            name="combined_final_answer_count",
            actual=combined.final_answer_count,
            threshold=resolved_options.min_combined_final_answer_count,
            detail="combined evidence should cover enough final answers",
        ),
        _watchlist_minimum_check(
            name="combined_changed_final_answer_count",
            actual=combined.changed_final_answer_count,
            threshold=resolved_options.min_combined_changed_final_answer_count,
            detail="combined evidence should affect enough final answers for promotion",
        ),
        _optional_minimum_check(
            name="combined_final_answer_hit_rate_delta",
            actual=combined.final_answer_hit_rate_delta,
            threshold=resolved_options.min_combined_final_answer_hit_rate_delta,
            detail="combined evidence should not regress final-answer hit rate",
        ),
        _optional_minimum_check(
            name="combined_roi_delta",
            actual=combined.roi_delta,
            threshold=resolved_options.min_combined_roi_delta,
            detail="combined evidence should not regress ROI",
        ),
        _minimum_check(
            name="combined_profit_loss_delta",
            actual=combined.profit_loss_delta,
            threshold=resolved_options.min_combined_profit_loss_delta,
            detail="combined evidence should not regress profit/loss",
        ),
        _optional_maximum_check(
            name="combined_harm_count_vs_original",
            actual=combined.harm_count_vs_original,
            threshold=resolved_options.max_combined_harm_count_vs_original,
            detail="combined evidence should not harm original final answers",
        ),
        _optional_maximum_check(
            name="combined_final_hit_harm_count_vs_original",
            actual=combined.final_hit_harm_count_vs_original,
            threshold=(
                resolved_options.max_combined_final_hit_harm_count_vs_original
            ),
            detail="combined evidence should not turn original hits into misses",
        ),
        _optional_maximum_check(
            name="combined_profit_loss_harm_count_vs_original",
            actual=combined.profit_loss_harm_count_vs_original,
            threshold=(
                resolved_options.max_combined_profit_loss_harm_count_vs_original
            ),
            detail="combined evidence should not reduce original profit/loss",
        ),
        _optional_minimum_check(
            name="combined_average_hit_probability_delta",
            actual=combined.average_hit_probability_delta,
            threshold=resolved_options.min_combined_average_hit_probability_delta,
            detail="combined hit-probability loss should stay inside tolerance",
        ),
        _required_bool_check(
            name="no_public_response_change",
            actual=not public_response_changed,
            required=resolved_options.require_no_public_response_change,
            detail="sample expansion should not change public responses",
        ),
        _required_bool_check(
            name="no_production_recommendation_change",
            actual=not production_recommendation_changed,
            required=resolved_options.require_no_production_recommendation_change,
            detail="sample expansion should not change production recommendations",
        ),
    ]
    blockers = [check for check in checks if check.status == "failed"]
    watchlist = [check for check in checks if check.status == "watchlist"]
    passed = not blockers
    promotion_ready = passed and not watchlist
    status: HistoricalGlobalPlannerShortOddsAdapterSampleExpansionStatus
    if blockers:
        status = "blocked"
    elif watchlist:
        status = "research_only"
    else:
        status = "expansion_ready"
    warnings = [
        f"global_planner_short_odds_adapter_sample_expansion:{check.status}:{check.name}"
        for check in [*blockers, *watchlist]
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "global_planner_short_odds_adapter_sample_expansion_v3_1"
        ),
        "status": status,
        "passed": passed,
        "promotion_ready": promotion_ready,
        "failed_checks": [check.name for check in blockers],
        "watchlist_checks": [check.name for check in watchlist],
        "base_gate_report_key": base_gate.report_key,
        "base_gate_passed": base_gate.passed,
        "supplemental_report_keys": [
            replay.report_key for replay in supplemental_replays
        ],
        "supplemental_report_count": len(supplemental_replays),
        "supplemental_passed_report_count": sum(
            1 for replay in supplemental_replays if replay.passed
        ),
        "supplemental_failed_report_count": sum(
            1 for replay in supplemental_replays if not replay.passed
        ),
        "supplemental_final_answer_count": supplemental_final_answer_count,
        "supplemental_changed_final_answer_count": (
            supplemental_changed_final_answer_count
        ),
        "supplemental_activation_rate": _ratio(
            supplemental_changed_final_answer_count,
            supplemental_final_answer_count,
        ),
        "combined_final_answer_count": combined.final_answer_count,
        "combined_changed_final_answer_count": combined.changed_final_answer_count,
        "combined_activation_rate": _ratio(
            combined.changed_final_answer_count,
            combined.final_answer_count,
        ),
        "combined_final_answer_hit_rate_delta": combined.final_answer_hit_rate_delta,
        "combined_roi_delta": combined.roi_delta,
        "combined_profit_loss_delta": combined.profit_loss_delta,
        "combined_harm_count_vs_original": combined.harm_count_vs_original,
        "combined_final_hit_harm_count_vs_original": (
            combined.final_hit_harm_count_vs_original
        ),
        "combined_profit_loss_harm_count_vs_original": (
            combined.profit_loss_harm_count_vs_original
        ),
        "combined_average_hit_probability_delta": (
            combined.average_hit_probability_delta
        ),
        "public_response_changed": public_response_changed,
        "production_recommendation_changed": production_recommendation_changed,
        "warnings": warnings,
    }
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport(
        report_key=_report_key(summary),
        status=status,
        passed=passed,
        promotion_ready=promotion_ready,
        base_gate_report_key=base_gate.report_key,
        base_gate_passed=base_gate.passed,
        supplemental_report_count=len(supplemental_replays),
        supplemental_passed_report_count=sum(
            1 for replay in supplemental_replays if replay.passed
        ),
        supplemental_failed_report_count=sum(
            1 for replay in supplemental_replays if not replay.passed
        ),
        supplemental_final_answer_count=supplemental_final_answer_count,
        supplemental_changed_final_answer_count=supplemental_changed_final_answer_count,
        supplemental_activation_rate=_ratio(
            supplemental_changed_final_answer_count,
            supplemental_final_answer_count,
        ),
        combined_final_answer_count=combined.final_answer_count,
        combined_changed_final_answer_count=combined.changed_final_answer_count,
        combined_activation_rate=_ratio(
            combined.changed_final_answer_count,
            combined.final_answer_count,
        ),
        combined_final_answer_hit_rate_delta=combined.final_answer_hit_rate_delta,
        combined_roi_delta=combined.roi_delta,
        combined_profit_loss_delta=combined.profit_loss_delta,
        combined_harm_count_vs_original=combined.harm_count_vs_original,
        combined_final_hit_harm_count_vs_original=(
            combined.final_hit_harm_count_vs_original
        ),
        combined_profit_loss_harm_count_vs_original=(
            combined.profit_loss_harm_count_vs_original
        ),
        combined_average_hit_probability_delta=combined.average_hit_probability_delta,
        public_response_changed=public_response_changed,
        production_recommendation_changed=production_recommendation_changed,
        checks=checks,
        warnings=warnings,
        summary_json=summary,
    )


def load_global_planner_short_odds_adapter_sample_expansion_report(
    path: Path | str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport:
    return (
        HistoricalGlobalPlannerShortOddsAdapterSampleExpansionReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def load_historical_short_odds_runtime_shadow_replay_report(
    path: Path | str,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_global_planner_short_odds_adapter_sample_expansion_report(
        load_global_planner_short_odds_adapter_gate_report(args.base_gate_report),
        supplemental_replays=[
            load_historical_short_odds_runtime_shadow_replay_report(path)
            for path in args.supplemental_runtime_shadow_replay_report
        ],
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


class _CombinedRuntimeMetrics(BaseModel):
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(ge=0)
    profit_loss_harm_count_vs_original: int = Field(ge=0)
    average_hit_probability_delta: float | None = None


def _combined_metrics(
    base_gate: HistoricalGlobalPlannerShortOddsAdapterGateReport,
    supplemental_replays: Sequence[HistoricalShortOddsRuntimeShadowReplayReport],
) -> _CombinedRuntimeMetrics:
    runtime_reports = [_runtime_from_base_gate(base_gate), *supplemental_replays]
    final_answer_count = sum(report.final_answer_count for report in runtime_reports)
    changed_final_answer_count = sum(
        report.changed_final_answer_count for report in runtime_reports
    )
    baseline_hits = sum(
        report.baseline_final_answer_hit_count for report in runtime_reports
    )
    shadow_hits = sum(
        report.shadow_final_answer_hit_count for report in runtime_reports
    )
    baseline_profit_loss = sum(report.baseline_profit_loss for report in runtime_reports)
    shadow_profit_loss = sum(report.shadow_profit_loss for report in runtime_reports)
    total_stake = sum(report.total_stake for report in runtime_reports)
    return _CombinedRuntimeMetrics(
        final_answer_count=final_answer_count,
        changed_final_answer_count=changed_final_answer_count,
        final_answer_hit_rate_delta=_ratio_delta(
            numerator=shadow_hits,
            baseline_numerator=baseline_hits,
            denominator=final_answer_count,
        ),
        roi_delta=(
            ((shadow_profit_loss - baseline_profit_loss) / total_stake)
            if total_stake > 0
            else None
        ),
        profit_loss_delta=shadow_profit_loss - baseline_profit_loss,
        harm_count_vs_original=sum(
            report.harm_count_vs_original for report in runtime_reports
        ),
        final_hit_harm_count_vs_original=sum(
            report.final_hit_harm_count_vs_original for report in runtime_reports
        ),
        profit_loss_harm_count_vs_original=sum(
            report.profit_loss_harm_count_vs_original for report in runtime_reports
        ),
        average_hit_probability_delta=_weighted_changed_average(runtime_reports),
    )


def _runtime_from_base_gate(
    base_gate: HistoricalGlobalPlannerShortOddsAdapterGateReport,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(
        {
            "report_key": base_gate.source_runtime_shadow_replay_report_key,
            "status": base_gate.runtime_replay_status,
            "passed": base_gate.runtime_replay_passed,
            "source_audit_report_key": "source_runtime_shadow_replay_from_base_gate",
            "source_rule_profile_version": base_gate.source_rule_profile_version,
            "rule_count": 1,
            "enabled_rule_count": 1,
            "final_answer_count": base_gate.runtime_final_answer_count,
            "changed_final_answer_count": base_gate.runtime_changed_final_answer_count,
            "baseline_final_answer_hit_count": 0,
            "shadow_final_answer_hit_count": 0,
            "final_answer_hit_delta_count": 0,
            "baseline_final_answer_hit_rate": None,
            "shadow_final_answer_hit_rate": None,
            "final_answer_hit_rate_delta": base_gate.runtime_final_answer_hit_rate_delta,
            "baseline_profit_loss": 0.0,
            "shadow_profit_loss": base_gate.runtime_profit_loss_delta,
            "profit_loss_delta": base_gate.runtime_profit_loss_delta,
            "baseline_roi": None,
            "shadow_roi": None,
            "roi_delta": base_gate.runtime_roi_delta,
            "total_stake": _stake_from_roi_delta(base_gate),
            "harm_count_vs_original": base_gate.runtime_harm_count_vs_original,
            "final_hit_harm_count_vs_original": (
                base_gate.runtime_final_hit_harm_count_vs_original
            ),
            "profit_loss_harm_count_vs_original": (
                base_gate.runtime_profit_loss_harm_count_vs_original
            ),
            "average_hit_probability_delta_vs_original": (
                base_gate.runtime_average_hit_probability_delta
            ),
            "production_recommendation_changed": (
                base_gate.runtime_production_recommendation_changed
            ),
            "public_response_changed": base_gate.runtime_public_response_changed,
            "checks": [],
            "rule_set_json": {},
            "changed_items": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _stake_from_roi_delta(
    base_gate: HistoricalGlobalPlannerShortOddsAdapterGateReport,
) -> float:
    if base_gate.runtime_roi_delta is None or base_gate.runtime_roi_delta == 0:
        return 0.0
    return abs(base_gate.runtime_profit_loss_delta / base_gate.runtime_roi_delta)


def _weighted_changed_average(
    reports: Sequence[HistoricalShortOddsRuntimeShadowReplayReport],
) -> float | None:
    weighted_sum = 0.0
    changed_count = 0
    for report in reports:
        if report.average_hit_probability_delta_vs_original is None:
            continue
        weighted_sum += (
            report.average_hit_probability_delta_vs_original
            * report.changed_final_answer_count
        )
        changed_count += report.changed_final_answer_count
    if changed_count <= 0:
        return 0.0
    return weighted_sum / changed_count


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    detail: str,
    required: bool = True,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    if not required:
        return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=True,
            detail=detail,
        )
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _watchlist_minimum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "watchlist",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    if threshold is None:
        return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck:
    if threshold is None:
        return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    if actual is None:
        return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return _maximum_check(name=name, actual=actual, threshold=threshold, detail=detail)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _ratio_delta(
    *,
    numerator: int,
    baseline_numerator: int,
    denominator: int,
) -> float | None:
    ratio = _ratio(numerator, denominator)
    baseline_ratio = _ratio(baseline_numerator, denominator)
    if ratio is None or baseline_ratio is None:
        return None
    return ratio - baseline_ratio


def _report_key(summary: dict[str, object]) -> str:
    digest = sha256(
        dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"global_planner_short_odds_adapter_sample_expansion:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Evaluate global planner short-odds adapter evidence against "
            "supplemental historical sample expansion."
        )
    )
    parser.add_argument("--base-gate-report", type=Path, required=True)
    parser.add_argument(
        "--supplemental-runtime-shadow-replay-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--min-supplemental-report-count", type=int, default=1)
    parser.add_argument("--min-supplemental-final-answer-count", type=int, default=50)
    parser.add_argument(
        "--min-supplemental-changed-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument("--min-combined-final-answer-count", type=int, default=80)
    parser.add_argument("--min-combined-changed-final-answer-count", type=int, default=5)
    parser.add_argument(
        "--min-combined-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-combined-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-combined-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-combined-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-combined-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-combined-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-combined-average-hit-probability-delta",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-production-recommendation-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions:
    return HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions(
        min_supplemental_report_count=args.min_supplemental_report_count,
        min_supplemental_final_answer_count=args.min_supplemental_final_answer_count,
        min_supplemental_changed_final_answer_count=(
            args.min_supplemental_changed_final_answer_count
        ),
        min_combined_final_answer_count=args.min_combined_final_answer_count,
        min_combined_changed_final_answer_count=(
            args.min_combined_changed_final_answer_count
        ),
        min_combined_final_answer_hit_rate_delta=(
            args.min_combined_final_answer_hit_rate_delta
        ),
        min_combined_roi_delta=args.min_combined_roi_delta,
        min_combined_profit_loss_delta=args.min_combined_profit_loss_delta,
        max_combined_harm_count_vs_original=(
            args.max_combined_harm_count_vs_original
        ),
        max_combined_final_hit_harm_count_vs_original=(
            args.max_combined_final_hit_harm_count_vs_original
        ),
        max_combined_profit_loss_harm_count_vs_original=(
            args.max_combined_profit_loss_harm_count_vs_original
        ),
        min_combined_average_hit_probability_delta=(
            args.min_combined_average_hit_probability_delta
        ),
        require_no_public_response_change=not args.allow_public_response_change,
        require_no_production_recommendation_change=(
            not args.allow_production_recommendation_change
        ),
    )
