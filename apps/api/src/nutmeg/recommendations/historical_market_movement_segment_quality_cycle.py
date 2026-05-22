from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateReport,
)
from nutmeg.recommendations.persisted_lifecycle_smoke import (
    RecommendationPersistedLifecycleSmokeResult,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationResult,
)

type HistoricalMarketMovementSegmentQualityCycleStatus = Literal["passed", "failed"]
type HistoricalMarketMovementSegmentQualityCycleCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]

DEFAULT_MARKET_MOVEMENT_SEGMENT_QUALITY_CYCLE_ID = (
    "market-movement-segment-quality-cycle-shadow-v3.1"
)


class HistoricalMarketMovementSegmentQualityCycleOptions(BaseModel):
    cycle_id: str = DEFAULT_MARKET_MOVEMENT_SEGMENT_QUALITY_CYCLE_ID
    min_accepted_candidate_count: int = Field(default=1, ge=0)
    require_best_candidate_accepted: bool = True
    min_best_final_answer_changed_count: int = Field(default=1, ge=0)
    min_best_final_hit_rate_delta: float | None = 0.0
    max_best_brier_score_delta: float | None = 0.0
    max_best_log_loss_delta: float | None = 0.0
    max_best_mean_calibration_error_delta: float | None = 0.0
    require_successor_chain_evaluation: bool = False
    min_successor_effective_leaf_count: int = Field(default=0, ge=0)
    min_successor_active_edge_count: int = Field(default=0, ge=0)
    max_successor_critical_issue_count: int | None = Field(default=0, ge=0)
    max_successor_ambiguous_source_count: int | None = Field(default=0, ge=0)
    max_successor_source_status_sync_required_count: int | None = Field(
        default=None,
        ge=0,
    )
    require_persisted_lifecycle_smoke: bool = False
    require_persisted_lifecycle_source_status_synced: bool = True
    min_persisted_lifecycle_effective_leaf_count: int = Field(default=0, ge=0)
    min_persisted_lifecycle_active_edge_count: int = Field(default=0, ge=0)
    max_persisted_lifecycle_critical_issue_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_persisted_lifecycle_source_status_sync_required_count: int | None = Field(
        default=0,
        ge=0,
    )
    max_cycle_warning_count: int | None = Field(default=None, ge=0)


class HistoricalMarketMovementSegmentQualityCycleCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementSegmentQualityCycleCheckStatus
    detail: str
    observed_value: int | float | str | bool | None = None
    threshold: int | float | str | bool | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementSegmentQualityCycleResult(BaseModel):
    cycle_key: str
    status: HistoricalMarketMovementSegmentQualityCycleStatus
    passed: bool
    cycle_id: str
    segment_gate_report_key: str
    segment_gate_report_path: Path | None = None
    successor_chain_evaluation_report_path: Path | None = None
    successor_chain_evaluation_present: bool = False
    successor_chain_evaluation_passed: bool | None = None
    persisted_lifecycle_smoke_report_path: Path | None = None
    persisted_lifecycle_smoke_present: bool = False
    persisted_lifecycle_smoke_passed: bool | None = None
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    best_candidate_id: str | None = None
    best_segment_group_key: str | None = None
    best_decision: str | None = None
    best_final_answer_changed_count: int = Field(ge=0)
    best_final_answer_deltas_json: dict[str, object] = Field(default_factory=dict)
    checks: list[HistoricalMarketMovementSegmentQualityCycleCheck] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    segment_gate_summary_json: dict[str, object] = Field(default_factory=dict)
    successor_chain_summary_json: dict[str, object] = Field(default_factory=dict)
    persisted_lifecycle_smoke_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_historical_market_movement_segment_quality_cycle(
    *,
    segment_gate_report: HistoricalMarketMovementSegmentGateReport,
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None = None,
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None = None,
    options: HistoricalMarketMovementSegmentQualityCycleOptions | None = None,
    segment_gate_report_path: Path | None = None,
    successor_chain_evaluation_report_path: Path | None = None,
    persisted_lifecycle_smoke_report_path: Path | None = None,
) -> HistoricalMarketMovementSegmentQualityCycleResult:
    resolved_options = options or HistoricalMarketMovementSegmentQualityCycleOptions()
    checks = _cycle_checks(
        segment_gate_report,
        successor_chain_evaluation=successor_chain_evaluation,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        options=resolved_options,
    )
    warnings = _cycle_warnings(
        segment_gate_report,
        successor_chain_evaluation=successor_chain_evaluation,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        checks=checks,
        options=resolved_options,
    )
    passed = all(check.status != "failed" for check in checks)
    cycle_key = _cycle_key(
        segment_gate_report,
        successor_chain_evaluation=successor_chain_evaluation,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        options=resolved_options,
    )
    status: HistoricalMarketMovementSegmentQualityCycleStatus = (
        "passed" if passed else "failed"
    )
    best = segment_gate_report.best_candidate
    best_final_answer_deltas = best.final_answer_deltas_json if best is not None else {}
    best_final_answer_changed_count = _summary_int(
        best_final_answer_deltas,
        "final_answer_changed_count",
    )
    successor_summary = (
        successor_chain_evaluation.summary_json
        if successor_chain_evaluation is not None
        else {}
    )
    persisted_lifecycle_summary = (
        persisted_lifecycle_smoke.summary_json
        if persisted_lifecycle_smoke is not None
        else {}
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_segment_quality_cycle_v3_1"
        ),
        "cycle_key": cycle_key,
        "cycle_id": resolved_options.cycle_id,
        "status": status,
        "passed": passed,
        "shadow_only": True,
        "segment_gate_report_key": segment_gate_report.report_key,
        "segment_gate_report_path": (
            str(segment_gate_report_path)
            if segment_gate_report_path is not None
            else None
        ),
        "successor_chain_evaluation_present": (
            successor_chain_evaluation is not None
        ),
        "successor_chain_evaluation_passed": (
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else None
        ),
        "successor_chain_evaluation_report_path": (
            str(successor_chain_evaluation_report_path)
            if successor_chain_evaluation_report_path is not None
            else None
        ),
        "persisted_lifecycle_smoke_present": persisted_lifecycle_smoke is not None,
        "persisted_lifecycle_smoke_passed": (
            persisted_lifecycle_smoke.passed
            if persisted_lifecycle_smoke is not None
            else None
        ),
        "persisted_lifecycle_smoke_report_path": (
            str(persisted_lifecycle_smoke_report_path)
            if persisted_lifecycle_smoke_report_path is not None
            else None
        ),
        "candidate_count": segment_gate_report.candidate_count,
        "accepted_count": segment_gate_report.accepted_count,
        "rejected_count": segment_gate_report.rejected_count,
        "best_candidate_id": best.candidate_id if best is not None else None,
        "best_segment_group_key": (
            best.segment_group_key if best is not None else None
        ),
        "best_decision": best.decision if best is not None else None,
        "best_final_answer_changed_count": best_final_answer_changed_count,
        "best_final_answer_deltas": best_final_answer_deltas,
        "successor_chain_effective_leaf_count": _summary_int(
            successor_summary,
            "effective_leaf_count",
        ),
        "successor_chain_active_edge_count": _summary_int(
            successor_summary,
            "active_edge_count",
        ),
        "successor_chain_critical_issue_count": _summary_int(
            successor_summary,
            "chain_integrity_critical_issue_count",
        ),
        "successor_chain_ambiguous_source_count": _summary_int(
            successor_summary,
            "ambiguous_successor_source_count",
        ),
        "successor_chain_source_status_sync_required_count": _summary_int(
            successor_summary,
            "source_status_sync_required_count",
        ),
        "persisted_lifecycle_source_status_synced": bool(
            persisted_lifecycle_summary.get("source_status_synced", False)
        ),
        "persisted_lifecycle_successor_chain_evaluation_passed": bool(
            persisted_lifecycle_summary.get(
                "successor_chain_evaluation_passed",
                False,
            )
        ),
        "persisted_lifecycle_effective_leaf_count": _summary_int(
            persisted_lifecycle_summary,
            "successor_chain_effective_leaf_count",
        ),
        "persisted_lifecycle_active_edge_count": _summary_int(
            persisted_lifecycle_summary,
            "successor_chain_active_edge_count",
        ),
        "persisted_lifecycle_critical_issue_count": _summary_int(
            persisted_lifecycle_summary,
            "successor_chain_critical_issue_count",
        ),
        "persisted_lifecycle_source_status_sync_required_count": _summary_int(
            persisted_lifecycle_summary,
            "successor_chain_source_status_sync_required_count",
        ),
        "failed_check_names": [
            check.name for check in checks if check.status == "failed"
        ],
        "warnings": warnings,
    }
    return HistoricalMarketMovementSegmentQualityCycleResult(
        cycle_key=cycle_key,
        status=status,
        passed=passed,
        cycle_id=resolved_options.cycle_id,
        segment_gate_report_key=segment_gate_report.report_key,
        segment_gate_report_path=segment_gate_report_path,
        successor_chain_evaluation_report_path=successor_chain_evaluation_report_path,
        successor_chain_evaluation_present=successor_chain_evaluation is not None,
        successor_chain_evaluation_passed=(
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else None
        ),
        persisted_lifecycle_smoke_report_path=persisted_lifecycle_smoke_report_path,
        persisted_lifecycle_smoke_present=persisted_lifecycle_smoke is not None,
        persisted_lifecycle_smoke_passed=(
            persisted_lifecycle_smoke.passed
            if persisted_lifecycle_smoke is not None
            else None
        ),
        candidate_count=segment_gate_report.candidate_count,
        accepted_count=segment_gate_report.accepted_count,
        rejected_count=segment_gate_report.rejected_count,
        best_candidate_id=best.candidate_id if best is not None else None,
        best_segment_group_key=best.segment_group_key if best is not None else None,
        best_decision=best.decision if best is not None else None,
        best_final_answer_changed_count=best_final_answer_changed_count,
        best_final_answer_deltas_json=dict(best_final_answer_deltas),
        checks=checks,
        warnings=warnings,
        segment_gate_summary_json=dict(segment_gate_report.summary_json),
        successor_chain_summary_json=dict(successor_summary),
        persisted_lifecycle_smoke_summary_json=dict(persisted_lifecycle_summary),
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    segment_gate_report = _load_segment_gate_report(args.segment_gate_report_path)
    successor_chain_evaluation = _load_successor_chain_evaluation(
        args.successor_chain_evaluation_report_path
    )
    persisted_lifecycle_smoke = _load_persisted_lifecycle_smoke(
        args.persisted_lifecycle_smoke_report_path
    )
    result = run_historical_market_movement_segment_quality_cycle(
        segment_gate_report=segment_gate_report,
        successor_chain_evaluation=successor_chain_evaluation,
        persisted_lifecycle_smoke=persisted_lifecycle_smoke,
        options=_options_from_args(args),
        segment_gate_report_path=args.segment_gate_report_path,
        successor_chain_evaluation_report_path=(
            args.successor_chain_evaluation_report_path
        ),
        persisted_lifecycle_smoke_report_path=args.persisted_lifecycle_smoke_report_path,
    )
    output = dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _cycle_checks(
    segment_gate_report: HistoricalMarketMovementSegmentGateReport,
    *,
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None,
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> list[HistoricalMarketMovementSegmentQualityCycleCheck]:
    best = segment_gate_report.best_candidate
    best_final_answer_deltas = best.final_answer_deltas_json if best is not None else {}
    checks = [
        _minimum_check(
            name="accepted_candidate_count",
            observed=segment_gate_report.accepted_count,
            threshold=options.min_accepted_candidate_count,
            detail="market-movement segment gate should produce enough accepted candidates",
        ),
        _best_candidate_decision_check(best, options=options),
        _minimum_check(
            name="best_final_answer_changed_count",
            observed=_summary_int(best_final_answer_deltas, "final_answer_changed_count"),
            threshold=options.min_best_final_answer_changed_count,
            detail=(
                "best accepted shadow candidate should change enough final answers "
                "before lifecycle promotion"
            ),
        ),
        _optional_minimum_check(
            name="best_final_hit_rate_delta",
            observed=_summary_float(best_final_answer_deltas, "final_hit_rate_delta"),
            threshold=options.min_best_final_hit_rate_delta,
            detail="best candidate final-hit rate should not regress",
        ),
        _optional_maximum_check(
            name="best_brier_score_delta",
            observed=_summary_float(best_final_answer_deltas, "brier_score_delta"),
            threshold=options.max_best_brier_score_delta,
            detail="best candidate final-answer Brier score should not regress",
        ),
        _optional_maximum_check(
            name="best_log_loss_delta",
            observed=_summary_float(best_final_answer_deltas, "log_loss_delta"),
            threshold=options.max_best_log_loss_delta,
            detail="best candidate final-answer log loss should not regress",
        ),
        _optional_maximum_check(
            name="best_mean_calibration_error_delta",
            observed=_summary_float(
                best_final_answer_deltas,
                "mean_calibration_error_delta",
            ),
            threshold=options.max_best_mean_calibration_error_delta,
            detail=(
                "best candidate final-answer calibration error should not regress"
            ),
        ),
        _successor_chain_present_check(
            successor_chain_evaluation,
            options=options,
        ),
        _persisted_lifecycle_smoke_present_check(
            persisted_lifecycle_smoke,
            options=options,
        ),
    ]
    checks.extend(
        _successor_chain_checks(
            successor_chain_evaluation,
            options=options,
        )
    )
    checks.extend(
        _persisted_lifecycle_smoke_checks(
            persisted_lifecycle_smoke,
            options=options,
        )
    )
    return checks


def _best_candidate_decision_check(
    best: HistoricalMarketMovementSegmentCandidate | None,
    *,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if not options.require_best_candidate_accepted:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name="best_candidate_accepted",
            status="skipped",
            detail="best candidate acceptance is not required by this cycle",
            observed_value=best.decision if best is not None else None,
            threshold="accepted",
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name="best_candidate_accepted",
        status=(
            "passed"
            if best is not None and best.decision == "accepted"
            else "failed"
        ),
        detail="best segment candidate should be accepted by segment gate",
        observed_value=best.decision if best is not None else None,
        threshold="accepted",
    )


def _successor_chain_present_check(
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None,
    *,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if not options.require_successor_chain_evaluation:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name="successor_chain_evaluation_present",
            status="skipped",
            detail="successor-chain evaluation is optional for this cycle",
            observed_value=successor_chain_evaluation is not None,
            threshold=True,
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name="successor_chain_evaluation_present",
        status="passed" if successor_chain_evaluation is not None else "failed",
        detail=(
            "successor-chain evaluation must be attached before treating the "
            "shadow candidate as lifecycle-ready"
        ),
        observed_value=successor_chain_evaluation is not None,
        threshold=True,
    )


def _successor_chain_checks(
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None,
    *,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> list[HistoricalMarketMovementSegmentQualityCycleCheck]:
    if successor_chain_evaluation is None:
        return []
    summary = successor_chain_evaluation.summary_json
    checks = [
        HistoricalMarketMovementSegmentQualityCycleCheck(
            name="successor_chain_evaluation_passed",
            status="passed" if successor_chain_evaluation.passed else "failed",
            detail="successor-chain evaluation should pass all configured checks",
            observed_value=successor_chain_evaluation.passed,
            threshold=True,
        ),
        _minimum_check(
            name="successor_chain_effective_leaf_count",
            observed=_summary_int(summary, "effective_leaf_count"),
            threshold=options.min_successor_effective_leaf_count,
            detail="successor-chain should include enough final effective leaf runs",
        ),
        _minimum_check(
            name="successor_chain_active_edge_count",
            observed=_summary_int(summary, "active_edge_count"),
            threshold=options.min_successor_active_edge_count,
            detail="successor-chain should observe enough active source->successor edges",
        ),
        _optional_maximum_int_check(
            name="successor_chain_critical_issue_count",
            observed=_summary_int(summary, "chain_integrity_critical_issue_count"),
            threshold=options.max_successor_critical_issue_count,
            detail="successor-chain critical issues should stay within the limit",
        ),
        _optional_maximum_int_check(
            name="successor_chain_ambiguous_source_count",
            observed=_summary_int(summary, "ambiguous_successor_source_count"),
            threshold=options.max_successor_ambiguous_source_count,
            detail="ambiguous successor sources should stay within the limit",
        ),
        _optional_maximum_int_check(
            name="successor_chain_source_status_sync_required_count",
            observed=_summary_int(summary, "source_status_sync_required_count"),
            threshold=options.max_successor_source_status_sync_required_count,
            detail="successor source status sync debt should stay within the limit",
        ),
    ]
    return checks


def _persisted_lifecycle_smoke_present_check(
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None,
    *,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if not options.require_persisted_lifecycle_smoke:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name="persisted_lifecycle_smoke_present",
            status="skipped",
            detail="persisted lifecycle smoke is optional for this cycle",
            observed_value=persisted_lifecycle_smoke is not None,
            threshold=True,
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name="persisted_lifecycle_smoke_present",
        status="passed" if persisted_lifecycle_smoke is not None else "failed",
        detail=(
            "persisted lifecycle smoke must be attached before treating the "
            "shadow candidate as persisted-lifecycle-ready"
        ),
        observed_value=persisted_lifecycle_smoke is not None,
        threshold=True,
    )


def _persisted_lifecycle_smoke_checks(
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None,
    *,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> list[HistoricalMarketMovementSegmentQualityCycleCheck]:
    if persisted_lifecycle_smoke is None:
        return []
    summary = persisted_lifecycle_smoke.summary_json
    checks = [
        HistoricalMarketMovementSegmentQualityCycleCheck(
            name="persisted_lifecycle_smoke_passed",
            status="passed" if persisted_lifecycle_smoke.passed else "failed",
            detail="persisted lifecycle smoke should pass end-to-end",
            observed_value=persisted_lifecycle_smoke.passed,
            threshold=True,
        ),
        HistoricalMarketMovementSegmentQualityCycleCheck(
            name="persisted_lifecycle_source_status_synced",
            status=(
                "passed"
                if (
                    not options.require_persisted_lifecycle_source_status_synced
                    or bool(summary.get("source_status_synced", False))
                )
                else "failed"
            ),
            detail="source run should be superseded after a persisted successor exists",
            observed_value=bool(summary.get("source_status_synced", False)),
            threshold=options.require_persisted_lifecycle_source_status_synced,
        ),
        HistoricalMarketMovementSegmentQualityCycleCheck(
            name="persisted_lifecycle_successor_chain_evaluation_passed",
            status=(
                "passed"
                if bool(summary.get("successor_chain_evaluation_passed", False))
                else "failed"
            ),
            detail="persisted lifecycle smoke should include a passing successor-chain evaluation",
            observed_value=bool(
                summary.get("successor_chain_evaluation_passed", False)
            ),
            threshold=True,
        ),
        _minimum_check(
            name="persisted_lifecycle_effective_leaf_count",
            observed=_summary_int(summary, "successor_chain_effective_leaf_count"),
            threshold=options.min_persisted_lifecycle_effective_leaf_count,
            detail="persisted lifecycle should include enough effective leaf runs",
        ),
        _minimum_check(
            name="persisted_lifecycle_active_edge_count",
            observed=_summary_int(summary, "successor_chain_active_edge_count"),
            threshold=options.min_persisted_lifecycle_active_edge_count,
            detail="persisted lifecycle should include enough active source->successor edges",
        ),
        _optional_maximum_int_check(
            name="persisted_lifecycle_critical_issue_count",
            observed=_summary_int(summary, "successor_chain_critical_issue_count"),
            threshold=options.max_persisted_lifecycle_critical_issue_count,
            detail="persisted lifecycle critical issues should stay within the limit",
        ),
        _optional_maximum_int_check(
            name="persisted_lifecycle_source_status_sync_required_count",
            observed=_summary_int(
                summary,
                "successor_chain_source_status_sync_required_count",
            ),
            threshold=(
                options.max_persisted_lifecycle_source_status_sync_required_count
            ),
            detail="persisted lifecycle source-status sync debt should stay within the limit",
        ),
    ]
    return checks


def _cycle_warnings(
    segment_gate_report: HistoricalMarketMovementSegmentGateReport,
    *,
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None,
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None,
    checks: Sequence[HistoricalMarketMovementSegmentQualityCycleCheck],
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> list[str]:
    warnings = list(segment_gate_report.warnings)
    warnings.extend(
        f"market_movement_segment_quality_cycle:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    )
    if (
        options.require_successor_chain_evaluation
        and successor_chain_evaluation is None
    ):
        warnings.append(
            "market_movement_segment_quality_cycle:missing_successor_chain_evaluation"
        )
    if (
        options.require_persisted_lifecycle_smoke
        and persisted_lifecycle_smoke is None
    ):
        warnings.append(
            "market_movement_segment_quality_cycle:missing_persisted_lifecycle_smoke"
        )
    if successor_chain_evaluation is not None:
        warnings.extend(
            f"successor_chain_evaluation:{warning}"
            for warning in successor_chain_evaluation.warnings
        )
    if persisted_lifecycle_smoke is not None:
        warnings.extend(
            f"persisted_lifecycle_smoke:{warning}"
            for warning in persisted_lifecycle_smoke.warnings
        )
    if (
        options.max_cycle_warning_count is not None
        and len(_dedupe_strings(warnings)) > options.max_cycle_warning_count
    ):
        warnings.append(
            "market_movement_segment_quality_cycle:max_warning_count_exceeded"
        )
    return _dedupe_strings(warnings)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a compact quality cycle over segmented market-movement shadow "
            "candidate gate output."
        )
    )
    parser.add_argument("--segment-gate-report-path", type=Path, required=True)
    parser.add_argument("--successor-chain-evaluation-report-path", type=Path)
    parser.add_argument("--persisted-lifecycle-smoke-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--cycle-id",
        default=DEFAULT_MARKET_MOVEMENT_SEGMENT_QUALITY_CYCLE_ID,
    )
    parser.add_argument("--min-accepted-candidate-count", type=int, default=1)
    parser.add_argument("--allow-best-candidate-rejected", action="store_true")
    parser.add_argument("--min-best-final-answer-changed-count", type=int, default=1)
    parser.add_argument("--min-best-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-best-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-best-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-best-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--require-successor-chain-evaluation", action="store_true")
    parser.add_argument("--min-successor-effective-leaf-count", type=int, default=0)
    parser.add_argument("--min-successor-active-edge-count", type=int, default=0)
    parser.add_argument("--max-successor-critical-issue-count", type=int, default=0)
    parser.add_argument("--max-successor-ambiguous-source-count", type=int, default=0)
    parser.add_argument("--max-successor-source-status-sync-required-count", type=int)
    parser.add_argument("--require-persisted-lifecycle-smoke", action="store_true")
    parser.add_argument(
        "--allow-unsynced-persisted-lifecycle-source-status",
        action="store_true",
    )
    parser.add_argument(
        "--min-persisted-lifecycle-effective-leaf-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-persisted-lifecycle-active-edge-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-persisted-lifecycle-critical-issue-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-persisted-lifecycle-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument("--max-cycle-warning-count", type=int)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementSegmentQualityCycleOptions:
    return HistoricalMarketMovementSegmentQualityCycleOptions(
        cycle_id=args.cycle_id,
        min_accepted_candidate_count=args.min_accepted_candidate_count,
        require_best_candidate_accepted=not args.allow_best_candidate_rejected,
        min_best_final_answer_changed_count=args.min_best_final_answer_changed_count,
        min_best_final_hit_rate_delta=args.min_best_final_hit_rate_delta,
        max_best_brier_score_delta=args.max_best_brier_score_delta,
        max_best_log_loss_delta=args.max_best_log_loss_delta,
        max_best_mean_calibration_error_delta=(
            args.max_best_mean_calibration_error_delta
        ),
        require_successor_chain_evaluation=args.require_successor_chain_evaluation,
        min_successor_effective_leaf_count=args.min_successor_effective_leaf_count,
        min_successor_active_edge_count=args.min_successor_active_edge_count,
        max_successor_critical_issue_count=args.max_successor_critical_issue_count,
        max_successor_ambiguous_source_count=(
            args.max_successor_ambiguous_source_count
        ),
        max_successor_source_status_sync_required_count=(
            args.max_successor_source_status_sync_required_count
        ),
        require_persisted_lifecycle_smoke=args.require_persisted_lifecycle_smoke,
        require_persisted_lifecycle_source_status_synced=(
            not args.allow_unsynced_persisted_lifecycle_source_status
        ),
        min_persisted_lifecycle_effective_leaf_count=(
            args.min_persisted_lifecycle_effective_leaf_count
        ),
        min_persisted_lifecycle_active_edge_count=(
            args.min_persisted_lifecycle_active_edge_count
        ),
        max_persisted_lifecycle_critical_issue_count=(
            args.max_persisted_lifecycle_critical_issue_count
        ),
        max_persisted_lifecycle_source_status_sync_required_count=(
            args.max_persisted_lifecycle_source_status_sync_required_count
        ),
        max_cycle_warning_count=args.max_cycle_warning_count,
    )


def _load_segment_gate_report(path: Path) -> HistoricalMarketMovementSegmentGateReport:
    return HistoricalMarketMovementSegmentGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_successor_chain_evaluation(
    path: Path | None,
) -> RecommendationSuccessorChainEvaluationResult | None:
    if path is None:
        return None
    return RecommendationSuccessorChainEvaluationResult.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_persisted_lifecycle_smoke(
    path: Path | None,
) -> RecommendationPersistedLifecycleSmokeResult | None:
    if path is None:
        return None
    return RecommendationPersistedLifecycleSmokeResult.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _minimum_check(
    *,
    name: str,
    observed: int,
    threshold: int,
    detail: str,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name=name,
        status="passed" if observed >= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
    )


def _optional_minimum_check(
    *,
    name: str,
    observed: float | None,
    threshold: float | None,
    detail: str,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if threshold is None:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name=name,
            status="skipped",
            detail=detail,
            observed_value=observed,
            threshold=threshold,
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name=name,
        status="passed" if observed is not None and observed >= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
    )


def _optional_maximum_check(
    *,
    name: str,
    observed: float | None,
    threshold: float | None,
    detail: str,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if threshold is None:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name=name,
            status="skipped",
            detail=detail,
            observed_value=observed,
            threshold=threshold,
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name=name,
        status="passed" if observed is not None and observed <= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
    )


def _optional_maximum_int_check(
    *,
    name: str,
    observed: int,
    threshold: int | None,
    detail: str,
) -> HistoricalMarketMovementSegmentQualityCycleCheck:
    if threshold is None:
        return HistoricalMarketMovementSegmentQualityCycleCheck(
            name=name,
            status="skipped",
            detail=detail,
            observed_value=observed,
            threshold=threshold,
        )
    return HistoricalMarketMovementSegmentQualityCycleCheck(
        name=name,
        status="passed" if observed <= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
    )


def _cycle_key(
    segment_gate_report: HistoricalMarketMovementSegmentGateReport,
    *,
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None,
    persisted_lifecycle_smoke: RecommendationPersistedLifecycleSmokeResult | None,
    options: HistoricalMarketMovementSegmentQualityCycleOptions,
) -> str:
    payload = {
        "cycle_id": options.cycle_id,
        "segment_gate_report_key": segment_gate_report.report_key,
        "accepted_count": segment_gate_report.accepted_count,
        "best_candidate_id": (
            segment_gate_report.best_candidate.candidate_id
            if segment_gate_report.best_candidate is not None
            else None
        ),
        "successor_chain_present": successor_chain_evaluation is not None,
        "successor_chain_passed": (
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else None
        ),
        "persisted_lifecycle_smoke_present": persisted_lifecycle_smoke is not None,
        "persisted_lifecycle_smoke_passed": (
            persisted_lifecycle_smoke.passed
            if persisted_lifecycle_smoke is not None
            else None
        ),
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_segment_quality_cycle:{digest}"


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _summary_float(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped
