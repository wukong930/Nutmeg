from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from math import ceil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_runtime_admission as admission,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_runtime_replay as replay,
)

RuntimeAdmissionReport = (
    admission.HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionReport
)
RuntimeReplayReport = replay.HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport

type HistoricalFinalAnswerSelectionValueSignalRoiFloorGapStatus = Literal[
    "gap_quantified",
    "no_gap",
    "blocked",
]
type HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions(BaseModel):
    candidate_roi_floor: float = 0.0
    min_abs_roi_delta_for_stake_estimate: float = Field(default=1e-12, gt=0.0)
    require_source_runtime_replay_key_match: bool = True


class HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapStatus
    production_recommendation_allowed: bool
    holdout_allowed: bool
    source_runtime_admission_report_key: str
    source_runtime_admission_status: str
    source_runtime_replay_report_key: str
    source_runtime_replay_status: str | None = None
    source_rule_profile_version: str
    candidate_roi: float | None = None
    candidate_roi_floor: float = 0.0
    candidate_roi_gap: float | None = None
    baseline_roi: float | None = None
    roi_delta: float | None = None
    required_roi_delta_for_floor: float | None = None
    additional_roi_delta_needed: float | None = None
    profit_loss_delta: float = 0.0
    estimated_total_stake: float | None = None
    baseline_profit_loss_estimate: float | None = None
    candidate_profit_loss_estimate: float | None = None
    required_profit_loss_delta_for_floor: float | None = None
    additional_profit_loss_needed: float | None = None
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    movement_count: int = Field(ge=0)
    positive_movement_count: int = Field(ge=0)
    harmful_movement_count: int = Field(ge=0)
    probability_quality_harm_movement_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    final_hit_harm_count_vs_baseline: int = Field(ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(ge=0)
    average_profit_loss_delta_per_positive_movement: float | None = None
    estimated_additional_clean_positive_movement_count: int | None = None
    failed_admission_check_names: list[str] = Field(default_factory=list)
    checks: list[HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck] = (
        Field(default_factory=list)
    )
    search_guidance_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_selection_value_signal_runtime_admission_report(
    path: Path | str,
) -> RuntimeAdmissionReport:
    return RuntimeAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_final_answer_selection_value_signal_runtime_replay_report(
    path: Path | str,
) -> RuntimeReplayReport:
    return RuntimeReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_final_answer_selection_value_signal_roi_floor_gap_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_selection_value_signal_roi_floor_gap_report(
    runtime_admission: RuntimeAdmissionReport,
    *,
    runtime_replay: RuntimeReplayReport | None = None,
    options: (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions()
    )
    candidate_roi = _candidate_roi(runtime_admission, runtime_replay)
    baseline_roi = _baseline_roi(runtime_admission, runtime_replay)
    roi_delta = _roi_delta(runtime_admission, runtime_replay)
    profit_loss_delta = _profit_loss_delta(runtime_admission, runtime_replay)
    candidate_roi_gap = _candidate_roi_gap(
        candidate_roi,
        floor=resolved_options.candidate_roi_floor,
    )
    required_roi_delta_for_floor = _required_roi_delta_for_floor(
        baseline_roi,
        floor=resolved_options.candidate_roi_floor,
    )
    additional_roi_delta_needed = _additional_roi_delta_needed(
        required_roi_delta_for_floor,
        roi_delta,
    )
    estimated_total_stake = _estimated_total_stake(
        roi_delta,
        profit_loss_delta,
        min_abs_roi_delta=resolved_options.min_abs_roi_delta_for_stake_estimate,
    )
    baseline_profit_loss = _profit_loss_estimate(
        baseline_roi,
        estimated_total_stake,
    )
    candidate_profit_loss = _profit_loss_estimate(
        candidate_roi,
        estimated_total_stake,
    )
    required_profit_loss_delta = _required_profit_loss_delta_for_floor(
        required_roi_delta_for_floor,
        estimated_total_stake,
    )
    additional_profit_loss_needed = _additional_profit_loss_needed(
        additional_roi_delta_needed,
        estimated_total_stake,
    )
    average_positive_movement_delta = _average_positive_movement_delta(
        profit_loss_delta,
        runtime_admission.positive_movement_count,
    )
    estimated_additional_clean_movements = (
        _estimated_additional_clean_positive_movement_count(
            additional_profit_loss_needed,
            average_positive_movement_delta,
        )
    )
    failed_admission_checks = _failed_admission_check_names(runtime_admission)
    checks = _checks(
        runtime_admission,
        runtime_replay,
        candidate_roi=candidate_roi,
        baseline_roi=baseline_roi,
        estimated_total_stake=estimated_total_stake,
        options=resolved_options,
    )
    status = _status(
        runtime_admission,
        candidate_roi=candidate_roi,
        estimated_total_stake=estimated_total_stake,
        source_key_match_failed=_source_key_match_failed(checks),
        options=resolved_options,
    )
    warnings = _warnings(
        status=status,
        runtime_replay=runtime_replay,
        failed_admission_check_names=failed_admission_checks,
    )
    search_guidance = _search_guidance(
        status=status,
        candidate_roi_floor=resolved_options.candidate_roi_floor,
        candidate_roi_gap=candidate_roi_gap,
        additional_roi_delta_needed=additional_roi_delta_needed,
        additional_profit_loss_needed=additional_profit_loss_needed,
        estimated_additional_clean_movements=estimated_additional_clean_movements,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_gap_v3_1"
        ),
        "status": status,
        "production_recommendation_allowed": (
            runtime_admission.production_recommendation_allowed
        ),
        "holdout_allowed": runtime_admission.holdout_allowed,
        "source_runtime_admission_report_key": runtime_admission.report_key,
        "source_runtime_admission_status": runtime_admission.status,
        "source_runtime_replay_report_key": (
            runtime_admission.source_runtime_replay_report_key
        ),
        "source_runtime_replay_status": _source_runtime_replay_status(
            runtime_admission,
            runtime_replay,
        ),
        "source_rule_profile_version": runtime_admission.source_rule_profile_version,
        "candidate_roi": candidate_roi,
        "candidate_roi_floor": resolved_options.candidate_roi_floor,
        "candidate_roi_gap": candidate_roi_gap,
        "baseline_roi": baseline_roi,
        "roi_delta": roi_delta,
        "required_roi_delta_for_floor": required_roi_delta_for_floor,
        "additional_roi_delta_needed": additional_roi_delta_needed,
        "profit_loss_delta": profit_loss_delta,
        "estimated_total_stake": estimated_total_stake,
        "baseline_profit_loss_estimate": baseline_profit_loss,
        "candidate_profit_loss_estimate": candidate_profit_loss,
        "required_profit_loss_delta_for_floor": required_profit_loss_delta,
        "additional_profit_loss_needed": additional_profit_loss_needed,
        "average_profit_loss_delta_per_positive_movement": (
            average_positive_movement_delta
        ),
        "estimated_additional_clean_positive_movement_count": (
            estimated_additional_clean_movements
        ),
        "failed_admission_check_names": failed_admission_checks,
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, search_guidance)
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=(
            runtime_admission.production_recommendation_allowed
        ),
        holdout_allowed=runtime_admission.holdout_allowed,
        source_runtime_admission_report_key=runtime_admission.report_key,
        source_runtime_admission_status=runtime_admission.status,
        source_runtime_replay_report_key=(
            runtime_admission.source_runtime_replay_report_key
        ),
        source_runtime_replay_status=_source_runtime_replay_status(
            runtime_admission,
            runtime_replay,
        ),
        source_rule_profile_version=runtime_admission.source_rule_profile_version,
        candidate_roi=candidate_roi,
        candidate_roi_floor=resolved_options.candidate_roi_floor,
        candidate_roi_gap=candidate_roi_gap,
        baseline_roi=baseline_roi,
        roi_delta=roi_delta,
        required_roi_delta_for_floor=required_roi_delta_for_floor,
        additional_roi_delta_needed=additional_roi_delta_needed,
        profit_loss_delta=profit_loss_delta,
        estimated_total_stake=estimated_total_stake,
        baseline_profit_loss_estimate=baseline_profit_loss,
        candidate_profit_loss_estimate=candidate_profit_loss,
        required_profit_loss_delta_for_floor=required_profit_loss_delta,
        additional_profit_loss_needed=additional_profit_loss_needed,
        final_answer_count=runtime_admission.final_answer_count,
        changed_final_answer_count=runtime_admission.changed_final_answer_count,
        movement_count=runtime_admission.movement_count,
        positive_movement_count=runtime_admission.positive_movement_count,
        harmful_movement_count=runtime_admission.harmful_movement_count,
        probability_quality_harm_movement_count=(
            runtime_admission.probability_quality_harm_movement_count
        ),
        final_answer_hit_delta_count=runtime_admission.final_answer_hit_delta_count,
        final_hit_harm_count_vs_baseline=(
            runtime_admission.final_hit_harm_count_vs_baseline
        ),
        profit_loss_harm_count_vs_baseline=(
            runtime_admission.profit_loss_harm_count_vs_baseline
        ),
        average_profit_loss_delta_per_positive_movement=(
            average_positive_movement_delta
        ),
        estimated_additional_clean_positive_movement_count=(
            estimated_additional_clean_movements
        ),
        failed_admission_check_names=failed_admission_checks,
        checks=checks,
        search_guidance_json=search_guidance,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    runtime_replay = (
        load_historical_final_answer_selection_value_signal_runtime_replay_report(
            args.runtime_replay_report
        )
        if args.runtime_replay_report is not None
        else None
    )
    report = build_historical_final_answer_selection_value_signal_roi_floor_gap_report(
        load_historical_final_answer_selection_value_signal_runtime_admission_report(
            args.runtime_admission_report
        ),
        runtime_replay=runtime_replay,
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_roi(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
) -> float | None:
    if runtime_replay is not None and runtime_replay.candidate_roi is not None:
        return runtime_replay.candidate_roi
    return runtime_admission.candidate_roi


def _baseline_roi(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
) -> float | None:
    if runtime_replay is not None and runtime_replay.baseline_roi is not None:
        return runtime_replay.baseline_roi
    if runtime_admission.candidate_roi is None or runtime_admission.roi_delta is None:
        return None
    return runtime_admission.candidate_roi - runtime_admission.roi_delta


def _roi_delta(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
) -> float | None:
    if runtime_replay is not None and runtime_replay.roi_delta is not None:
        return runtime_replay.roi_delta
    return runtime_admission.roi_delta


def _profit_loss_delta(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
) -> float:
    if runtime_replay is not None:
        return runtime_replay.profit_loss_delta
    return runtime_admission.profit_loss_delta


def _candidate_roi_gap(
    candidate_roi: float | None,
    *,
    floor: float,
) -> float | None:
    if candidate_roi is None:
        return None
    return max(0.0, floor - candidate_roi)


def _required_roi_delta_for_floor(
    baseline_roi: float | None,
    *,
    floor: float,
) -> float | None:
    if baseline_roi is None:
        return None
    return floor - baseline_roi


def _additional_roi_delta_needed(
    required_roi_delta_for_floor: float | None,
    roi_delta: float | None,
) -> float | None:
    if required_roi_delta_for_floor is None or roi_delta is None:
        return None
    return max(0.0, required_roi_delta_for_floor - roi_delta)


def _estimated_total_stake(
    roi_delta: float | None,
    profit_loss_delta: float,
    *,
    min_abs_roi_delta: float,
) -> float | None:
    if roi_delta is None or abs(roi_delta) < min_abs_roi_delta:
        return None
    return profit_loss_delta / roi_delta


def _profit_loss_estimate(
    roi: float | None,
    estimated_total_stake: float | None,
) -> float | None:
    if roi is None or estimated_total_stake is None:
        return None
    return roi * estimated_total_stake


def _required_profit_loss_delta_for_floor(
    required_roi_delta_for_floor: float | None,
    estimated_total_stake: float | None,
) -> float | None:
    if required_roi_delta_for_floor is None or estimated_total_stake is None:
        return None
    return required_roi_delta_for_floor * estimated_total_stake


def _additional_profit_loss_needed(
    additional_roi_delta_needed: float | None,
    estimated_total_stake: float | None,
) -> float | None:
    if additional_roi_delta_needed is None or estimated_total_stake is None:
        return None
    return additional_roi_delta_needed * estimated_total_stake


def _average_positive_movement_delta(
    profit_loss_delta: float,
    positive_movement_count: int,
) -> float | None:
    if positive_movement_count <= 0:
        return None
    return profit_loss_delta / positive_movement_count


def _estimated_additional_clean_positive_movement_count(
    additional_profit_loss_needed: float | None,
    average_profit_loss_delta_per_positive_movement: float | None,
) -> int | None:
    if additional_profit_loss_needed is None:
        return None
    if additional_profit_loss_needed <= 0.0:
        return 0
    if (
        average_profit_loss_delta_per_positive_movement is None
        or average_profit_loss_delta_per_positive_movement <= 0.0
    ):
        return None
    return ceil(
        additional_profit_loss_needed
        / average_profit_loss_delta_per_positive_movement
    )


def _checks(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
    *,
    candidate_roi: float | None,
    baseline_roi: float | None,
    estimated_total_stake: float | None,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck]:
    return [
        _boolean_check(
            "admission_holdout_allowed",
            runtime_admission.holdout_allowed,
            threshold=True,
            detail="runtime admission must preserve no-harm holdout eligibility",
        ),
        _boolean_check(
            "candidate_roi_available",
            candidate_roi is not None,
            threshold=True,
            detail="candidate ROI is required to quantify the floor gap",
        ),
        _minimum_check(
            "candidate_roi_floor",
            candidate_roi,
            options.candidate_roi_floor,
            detail="candidate absolute ROI should meet the production floor",
        ),
        _boolean_check(
            "baseline_roi_available",
            baseline_roi is not None,
            threshold=True,
            detail="baseline ROI is required to derive the needed ROI delta",
        ),
        _boolean_check(
            "stake_estimate_available",
            estimated_total_stake is not None,
            threshold=True,
            detail="stake estimate is required to translate ROI gap to P&L gap",
        ),
        _source_runtime_replay_key_match_check(
            runtime_admission,
            runtime_replay,
            require_match=options.require_source_runtime_replay_key_match,
        ),
    ]


def _status(
    runtime_admission: RuntimeAdmissionReport,
    *,
    candidate_roi: float | None,
    estimated_total_stake: float | None,
    source_key_match_failed: bool,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapStatus:
    if source_key_match_failed:
        return "blocked"
    if candidate_roi is None:
        return "blocked"
    if candidate_roi >= options.candidate_roi_floor:
        if runtime_admission.production_recommendation_allowed:
            return "no_gap"
        return "blocked"
    if not runtime_admission.holdout_allowed or runtime_admission.status == "rejected":
        return "blocked"
    if estimated_total_stake is None:
        return "blocked"
    return "gap_quantified"


def _source_runtime_replay_key_match_check(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
    *,
    require_match: bool,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck:
    if runtime_replay is None:
        return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck(
            name="source_runtime_replay_key_match",
            status="skipped",
            actual=None,
            threshold=None,
            detail="runtime replay report was not provided",
        )
    matches = runtime_admission.source_runtime_replay_report_key == runtime_replay.report_key
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck(
        name="source_runtime_replay_key_match",
        status="passed" if matches or not require_match else "failed",
        actual=runtime_replay.report_key,
        threshold=runtime_admission.source_runtime_replay_report_key,
        detail="runtime replay report should match the admission source key",
    )


def _source_key_match_failed(
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck],
) -> bool:
    return any(
        check.name == "source_runtime_replay_key_match" and check.status == "failed"
        for check in checks
    )


def _boolean_check(
    name: str,
    actual: bool,
    *,
    threshold: bool,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int,
    *,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _failed_admission_check_names(
    runtime_admission: RuntimeAdmissionReport,
) -> list[str]:
    return [
        check.name for check in runtime_admission.checks if check.status == "failed"
    ]


def _source_runtime_replay_status(
    runtime_admission: RuntimeAdmissionReport,
    runtime_replay: RuntimeReplayReport | None,
) -> str | None:
    if runtime_replay is not None:
        return runtime_replay.status
    return runtime_admission.source_runtime_replay_status


def _warnings(
    *,
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapStatus,
    runtime_replay: RuntimeReplayReport | None,
    failed_admission_check_names: Sequence[str],
) -> list[str]:
    warnings: list[str] = [f"selection_value_signal_roi_floor_gap:{status}"]
    if runtime_replay is None:
        warnings.append("selection_value_signal_roi_floor_gap:runtime_replay_not_loaded")
    unexpected_failed_checks = [
        name for name in failed_admission_check_names if name != "candidate_roi"
    ]
    warnings.extend(
        f"selection_value_signal_roi_floor_gap:unexpected_admission_failed_check:{name}"
        for name in unexpected_failed_checks
    )
    if status == "gap_quantified":
        warnings.append(
            "selection_value_signal_roi_floor_gap:default_activation_blocked_by_roi_floor"
        )
    return warnings


def _search_guidance(
    *,
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorGapStatus,
    candidate_roi_floor: float,
    candidate_roi_gap: float | None,
    additional_roi_delta_needed: float | None,
    additional_profit_loss_needed: float | None,
    estimated_additional_clean_movements: int | None,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_gap_guidance_v3_1"
        ),
        "status": status,
        "default_profile_action": "do_not_activate",
        "candidate_roi_floor": candidate_roi_floor,
        "candidate_roi_gap": candidate_roi_gap,
        "minimum_additional_roi_delta_needed": additional_roi_delta_needed,
        "minimum_additional_profit_loss_needed": additional_profit_loss_needed,
        "estimated_additional_clean_positive_movement_count": (
            estimated_additional_clean_movements
        ),
        "next_search_constraints": [
            "keep strict non-negative absolute candidate ROI floor",
            "keep final-hit, profit/loss, movement, and probability-quality no-harm checks",
            "search for additional movement-conditioned buckets before broad activation",
            "do not expose internal search strategy in the public recommendation response",
        ],
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Quantify the ROI-floor gap for selection-value runtime admission."
        )
    )
    parser.add_argument("runtime_admission_report", type=Path)
    parser.add_argument("--runtime-replay-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--candidate-roi-floor", type=float, default=0.0)
    parser.add_argument(
        "--min-abs-roi-delta-for-stake-estimate",
        type=float,
        default=1e-12,
    )
    parser.add_argument("--allow-source-runtime-replay-key-mismatch", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorGapOptions(
        candidate_roi_floor=args.candidate_roi_floor,
        min_abs_roi_delta_for_stake_estimate=(
            args.min_abs_roi_delta_for_stake_estimate
        ),
        require_source_runtime_replay_key_match=(
            not args.allow_source_runtime_replay_key_mismatch
        ),
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorGapCheck],
    search_guidance: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "search_guidance": search_guidance,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_roi_floor_gap:{digest}"


if __name__ == "__main__":
    main()
