from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    HistoricalMarketMovementRiskFilterRuntimeReplayReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_segment_expansion import (
    HistoricalMarketMovementRuntimeActivationSegmentExpansionReport,
    load_historical_market_movement_runtime_activation_segment_expansion_report,
)

type HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateStatus = Literal[
    "segment_replay_batch_ready",
    "watchlist",
    "blocked",
]
type HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheckStatus = Literal[
    "passed",
    "failed",
    "watchlist",
    "skipped",
]

DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_REPLAY_BATCH_GATE_ID = (
    "market-movement-runtime-activation-segment-replay-batch-gate-v3.2"
)


class HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions(
    BaseModel
):
    gate_id: str = (
        DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_REPLAY_BATCH_GATE_ID
    )
    min_replay_report_count: int = Field(default=1, ge=0)
    min_passed_replay_count: int = Field(default=1, ge=0)
    max_failed_replay_count: int | None = Field(default=0, ge=0)
    min_distinct_rule_count: int = Field(default=1, ge=0)
    min_distinct_segment_count: int = Field(default=1, ge=0)
    min_covered_selected_segment_count: int = Field(default=1, ge=0)
    min_total_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_total_adjusted_prediction_count: int = Field(default=1, ge=0)
    min_worst_final_hit_rate_delta: float | None = 0.0
    min_worst_roi_delta: float | None = 0.0
    min_total_profit_loss_delta: float | None = 0.0
    max_worst_brier_score_delta: float | None = 0.0
    max_worst_log_loss_delta: float | None = 0.0
    max_worst_mean_calibration_error_delta: float | None = 0.0
    require_segment_expansion_passed: bool = True
    require_segment_expansion_runtime_ready: bool = True
    require_segment_expansion_production_promotion_ready: bool = False
    require_all_expansion_selected_segments_replayed: bool = True
    require_replay_allowed: bool = True
    require_replay_passed_status: bool = True
    require_replay_rule_subset_of_expansion: bool = True
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
    BaseModel
):
    name: str
    status: HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class HistoricalMarketMovementRuntimeActivationSegmentReplaySummary(BaseModel):
    report_key: str
    report_path: str | None = None
    status: str
    runtime_shadow_replay_allowed: bool
    holdout_replay_allowed: bool
    selected_rule_id: str | None = None
    selected_segment_group_key: str | None = None
    adjusted_fixture_count: int = Field(ge=0)
    adjusted_prediction_count: int = Field(ge=0)
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False


class HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport(
    BaseModel
):
    report_key: str
    status: HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateStatus
    passed: bool
    runtime_replay_batch_ready: bool
    production_promotion_ready: bool
    gate_id: str
    source_segment_expansion_report_key: str
    source_segment_expansion_status: str
    source_segment_expansion_passed: bool
    source_runtime_replay_expansion_ready: bool
    source_production_promotion_ready: bool
    replay_report_count: int = Field(ge=0)
    passed_replay_count: int = Field(ge=0)
    failed_replay_count: int = Field(ge=0)
    runtime_allowed_replay_count: int = Field(ge=0)
    distinct_rule_count: int = Field(ge=0)
    distinct_segment_count: int = Field(ge=0)
    covered_selected_segment_count: int = Field(ge=0)
    total_adjusted_fixture_count: int = Field(ge=0)
    total_adjusted_prediction_count: int = Field(ge=0)
    weighted_final_hit_rate_delta: float | None = None
    weighted_roi_delta: float | None = None
    total_profit_loss_delta: float | None = None
    weighted_brier_score_delta: float | None = None
    weighted_log_loss_delta: float | None = None
    weighted_mean_calibration_error_delta: float | None = None
    worst_final_hit_rate_delta: float | None = None
    worst_roi_delta: float | None = None
    worst_brier_score_delta: float | None = None
    worst_log_loss_delta: float | None = None
    worst_mean_calibration_error_delta: float | None = None
    selected_rule_ids: list[str] = Field(default_factory=list)
    selected_segment_group_keys: list[str] = Field(default_factory=list)
    replayed_rule_ids: list[str] = Field(default_factory=list)
    replayed_segment_group_keys: list[str] = Field(default_factory=list)
    missing_selected_segment_group_keys: list[str] = Field(default_factory=list)
    unexpected_replayed_rule_ids: list[str] = Field(default_factory=list)
    unexpected_replayed_segment_group_keys: list[str] = Field(default_factory=list)
    default_recommendation_path_changed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    replay_summaries: list[
        HistoricalMarketMovementRuntimeActivationSegmentReplaySummary
    ] = Field(default_factory=list)
    checks: list[
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck
    ] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
    segment_expansion: HistoricalMarketMovementRuntimeActivationSegmentExpansionReport,
    *,
    replay_reports: Sequence[HistoricalMarketMovementRiskFilterRuntimeReplayReport],
    replay_report_paths: Sequence[Path | str] = (),
    options: (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions | None
    ) = None,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport:
    resolved_options = (
        options
        or HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions()
    )
    replay_summaries = [
        _replay_summary(
            replay,
            path=replay_report_paths[index]
            if index < len(replay_report_paths)
            else None,
        )
        for index, replay in enumerate(replay_reports)
    ]
    selected_rule_ids = _unique(
        _string_or_none(rule.get("rule_id"))
        for rule in _profile_rules(segment_expansion)
    )
    selected_segment_group_keys = list(segment_expansion.selected_segment_group_keys)
    replayed_rule_ids = _unique(
        summary.selected_rule_id for summary in replay_summaries
    )
    replayed_segment_group_keys = _unique(
        summary.selected_segment_group_key for summary in replay_summaries
    )
    selected_segments = set(selected_segment_group_keys)
    selected_rules = set(selected_rule_ids)
    replayed_segments = set(replayed_segment_group_keys)
    replayed_rules = set(replayed_rule_ids)
    missing_selected_segments = sorted(selected_segments - replayed_segments)
    unexpected_replayed_segments = sorted(replayed_segments - selected_segments)
    unexpected_replayed_rules = sorted(replayed_rules - selected_rules)
    passed_replay_count = sum(1 for summary in replay_summaries if _replay_passed(summary))
    runtime_allowed_replay_count = sum(
        1 for summary in replay_summaries if summary.runtime_shadow_replay_allowed
    )
    failed_replay_count = len(replay_summaries) - passed_replay_count
    total_adjusted_fixture_count = sum(
        summary.adjusted_fixture_count for summary in replay_summaries
    )
    total_adjusted_prediction_count = sum(
        summary.adjusted_prediction_count for summary in replay_summaries
    )
    production_changed = segment_expansion.production_recommendation_changed or any(
        summary.production_recommendation_changed for summary in replay_summaries
    )
    public_changed = segment_expansion.public_response_changed or any(
        summary.public_response_changed for summary in replay_summaries
    )
    default_path_changed = segment_expansion.default_recommendation_path_changed
    total_profit_loss_delta = _sum_optional(
        summary.profit_loss_delta for summary in replay_summaries
    )
    checks = _checks(
        segment_expansion,
        replay_summaries=replay_summaries,
        selected_rule_ids=selected_rule_ids,
        selected_segment_group_keys=selected_segment_group_keys,
        replayed_rule_ids=replayed_rule_ids,
        replayed_segment_group_keys=replayed_segment_group_keys,
        missing_selected_segments=missing_selected_segments,
        unexpected_replayed_rules=unexpected_replayed_rules,
        unexpected_replayed_segments=unexpected_replayed_segments,
        passed_replay_count=passed_replay_count,
        runtime_allowed_replay_count=runtime_allowed_replay_count,
        failed_replay_count=failed_replay_count,
        total_adjusted_fixture_count=total_adjusted_fixture_count,
        total_adjusted_prediction_count=total_adjusted_prediction_count,
        total_profit_loss_delta=total_profit_loss_delta,
        default_path_changed=default_path_changed,
        production_changed=production_changed,
        public_changed=public_changed,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    watchlist = [check.name for check in checks if check.status == "watchlist"]
    passed = not blockers
    runtime_replay_batch_ready = (
        passed
        and passed_replay_count >= resolved_options.min_passed_replay_count
        and total_adjusted_fixture_count
        >= resolved_options.min_total_adjusted_fixture_count
        and total_adjusted_prediction_count
        >= resolved_options.min_total_adjusted_prediction_count
    )
    production_promotion_ready = (
        runtime_replay_batch_ready
        and segment_expansion.production_promotion_ready
        and "segment_expansion_production_promotion_ready" not in watchlist
    )
    if blockers:
        status: HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateStatus = (
            "blocked"
        )
    elif watchlist:
        status = "watchlist"
    else:
        status = "segment_replay_batch_ready"
    warnings = [
        *[
            f"market_movement_segment_replay_batch_gate:failed:{name}"
            for name in blockers
        ],
        *[
            f"market_movement_segment_replay_batch_gate:watchlist:{name}"
            for name in watchlist
        ],
    ]
    weighted_final_hit_rate_delta = _weighted_average(
        replay_summaries,
        metric="final_hit_rate_delta",
    )
    weighted_roi_delta = _weighted_average(replay_summaries, metric="roi_delta")
    weighted_brier_score_delta = _weighted_average(
        replay_summaries,
        metric="brier_score_delta",
    )
    weighted_log_loss_delta = _weighted_average(
        replay_summaries,
        metric="log_loss_delta",
    )
    weighted_calibration_delta = _weighted_average(
        replay_summaries,
        metric="mean_calibration_error_delta",
    )
    worst_final_hit_rate_delta = _minimum_optional(
        summary.final_hit_rate_delta for summary in replay_summaries
    )
    worst_roi_delta = _minimum_optional(summary.roi_delta for summary in replay_summaries)
    worst_brier_score_delta = _maximum_optional(
        summary.brier_score_delta for summary in replay_summaries
    )
    worst_log_loss_delta = _maximum_optional(
        summary.log_loss_delta for summary in replay_summaries
    )
    worst_calibration_delta = _maximum_optional(
        summary.mean_calibration_error_delta for summary in replay_summaries
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_runtime_activation_segment_replay_"
            "batch_gate_v3_2"
        ),
        "status": status,
        "passed": passed,
        "runtime_replay_batch_ready": runtime_replay_batch_ready,
        "production_promotion_ready": production_promotion_ready,
        "gate_id": resolved_options.gate_id,
        "source_segment_expansion_report_key": segment_expansion.report_key,
        "source_segment_expansion_status": segment_expansion.status,
        "source_segment_expansion_passed": segment_expansion.passed,
        "source_runtime_replay_expansion_ready": (
            segment_expansion.runtime_replay_expansion_ready
        ),
        "source_production_promotion_ready": (
            segment_expansion.production_promotion_ready
        ),
        "replay_report_keys": [summary.report_key for summary in replay_summaries],
        "replay_report_count": len(replay_summaries),
        "passed_replay_count": passed_replay_count,
        "failed_replay_count": failed_replay_count,
        "runtime_allowed_replay_count": runtime_allowed_replay_count,
        "distinct_rule_count": len(replayed_rules),
        "distinct_segment_count": len(replayed_segments),
        "covered_selected_segment_count": len(selected_segments & replayed_segments),
        "total_adjusted_fixture_count": total_adjusted_fixture_count,
        "total_adjusted_prediction_count": total_adjusted_prediction_count,
        "weighted_final_hit_rate_delta": weighted_final_hit_rate_delta,
        "weighted_roi_delta": weighted_roi_delta,
        "total_profit_loss_delta": total_profit_loss_delta,
        "weighted_brier_score_delta": weighted_brier_score_delta,
        "weighted_log_loss_delta": weighted_log_loss_delta,
        "weighted_mean_calibration_error_delta": weighted_calibration_delta,
        "worst_final_hit_rate_delta": worst_final_hit_rate_delta,
        "worst_roi_delta": worst_roi_delta,
        "worst_brier_score_delta": worst_brier_score_delta,
        "worst_log_loss_delta": worst_log_loss_delta,
        "worst_mean_calibration_error_delta": worst_calibration_delta,
        "selected_rule_ids": selected_rule_ids,
        "selected_segment_group_keys": selected_segment_group_keys,
        "replayed_rule_ids": replayed_rule_ids,
        "replayed_segment_group_keys": replayed_segment_group_keys,
        "missing_selected_segment_group_keys": missing_selected_segments,
        "unexpected_replayed_rule_ids": unexpected_replayed_rules,
        "unexpected_replayed_segment_group_keys": unexpected_replayed_segments,
        "default_recommendation_path_changed": default_path_changed,
        "production_recommendation_changed": production_changed,
        "public_response_changed": public_changed,
        "blockers": blockers,
        "watchlist": watchlist,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks)
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport(
        report_key=report_key,
        status=status,
        passed=passed,
        runtime_replay_batch_ready=runtime_replay_batch_ready,
        production_promotion_ready=production_promotion_ready,
        gate_id=resolved_options.gate_id,
        source_segment_expansion_report_key=segment_expansion.report_key,
        source_segment_expansion_status=segment_expansion.status,
        source_segment_expansion_passed=segment_expansion.passed,
        source_runtime_replay_expansion_ready=(
            segment_expansion.runtime_replay_expansion_ready
        ),
        source_production_promotion_ready=(
            segment_expansion.production_promotion_ready
        ),
        replay_report_count=len(replay_summaries),
        passed_replay_count=passed_replay_count,
        failed_replay_count=failed_replay_count,
        runtime_allowed_replay_count=runtime_allowed_replay_count,
        distinct_rule_count=len(replayed_rules),
        distinct_segment_count=len(replayed_segments),
        covered_selected_segment_count=len(selected_segments & replayed_segments),
        total_adjusted_fixture_count=total_adjusted_fixture_count,
        total_adjusted_prediction_count=total_adjusted_prediction_count,
        weighted_final_hit_rate_delta=weighted_final_hit_rate_delta,
        weighted_roi_delta=weighted_roi_delta,
        total_profit_loss_delta=total_profit_loss_delta,
        weighted_brier_score_delta=weighted_brier_score_delta,
        weighted_log_loss_delta=weighted_log_loss_delta,
        weighted_mean_calibration_error_delta=weighted_calibration_delta,
        worst_final_hit_rate_delta=worst_final_hit_rate_delta,
        worst_roi_delta=worst_roi_delta,
        worst_brier_score_delta=worst_brier_score_delta,
        worst_log_loss_delta=worst_log_loss_delta,
        worst_mean_calibration_error_delta=worst_calibration_delta,
        selected_rule_ids=selected_rule_ids,
        selected_segment_group_keys=selected_segment_group_keys,
        replayed_rule_ids=replayed_rule_ids,
        replayed_segment_group_keys=replayed_segment_group_keys,
        missing_selected_segment_group_keys=missing_selected_segments,
        unexpected_replayed_rule_ids=unexpected_replayed_rules,
        unexpected_replayed_segment_group_keys=unexpected_replayed_segments,
        default_recommendation_path_changed=default_path_changed,
        production_recommendation_changed=production_changed,
        public_response_changed=public_changed,
        replay_summaries=replay_summaries,
        checks=checks,
        blockers=blockers,
        watchlist=watchlist,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
    path: Path | str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport:
    return (
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def load_historical_market_movement_risk_filter_runtime_replay_report(
    path: Path | str,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayReport:
    return HistoricalMarketMovementRiskFilterRuntimeReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    replay_paths = tuple(args.runtime_replay_report)
    report = (
        build_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
            load_historical_market_movement_runtime_activation_segment_expansion_report(
                args.segment_expansion_report
            ),
            replay_reports=[
                load_historical_market_movement_risk_filter_runtime_replay_report(path)
                for path in replay_paths
            ],
            replay_report_paths=replay_paths,
            options=_options_from_args(args),
        )
    )
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _replay_summary(
    replay: HistoricalMarketMovementRiskFilterRuntimeReplayReport,
    *,
    path: Path | str | None,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplaySummary:
    return HistoricalMarketMovementRuntimeActivationSegmentReplaySummary(
        report_key=replay.report_key,
        report_path=str(path) if path is not None else None,
        status=replay.status,
        runtime_shadow_replay_allowed=replay.runtime_shadow_replay_allowed,
        holdout_replay_allowed=replay.holdout_replay_allowed,
        selected_rule_id=replay.selected_rule_id,
        selected_segment_group_key=replay.selected_segment_group_key,
        adjusted_fixture_count=replay.adjusted_fixture_count,
        adjusted_prediction_count=replay.adjusted_prediction_count,
        final_hit_rate_delta=replay.final_hit_rate_delta,
        roi_delta=replay.roi_delta,
        profit_loss_delta=replay.profit_loss_delta,
        brier_score_delta=replay.brier_score_delta,
        log_loss_delta=replay.log_loss_delta,
        mean_calibration_error_delta=replay.mean_calibration_error_delta,
        production_recommendation_changed=replay.production_recommendation_changed,
        public_response_changed=replay.public_response_changed,
    )


def _checks(
    segment_expansion: HistoricalMarketMovementRuntimeActivationSegmentExpansionReport,
    *,
    replay_summaries: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentReplaySummary
    ],
    selected_rule_ids: Sequence[str],
    selected_segment_group_keys: Sequence[str],
    replayed_rule_ids: Sequence[str],
    replayed_segment_group_keys: Sequence[str],
    missing_selected_segments: Sequence[str],
    unexpected_replayed_rules: Sequence[str],
    unexpected_replayed_segments: Sequence[str],
    passed_replay_count: int,
    runtime_allowed_replay_count: int,
    failed_replay_count: int,
    total_adjusted_fixture_count: int,
    total_adjusted_prediction_count: int,
    total_profit_loss_delta: float | None,
    default_path_changed: bool,
    production_changed: bool,
    public_changed: bool,
    options: HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions,
) -> list[HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck]:
    return [
        _required_bool_check(
            name="segment_expansion_passed",
            actual=segment_expansion.passed,
            required=options.require_segment_expansion_passed,
            detail="source segment-expansion evidence should pass",
        ),
        _required_bool_check(
            name="segment_expansion_runtime_ready",
            actual=segment_expansion.runtime_replay_expansion_ready,
            required=options.require_segment_expansion_runtime_ready,
            detail="source segment-expansion evidence should be runtime-ready",
        ),
        _watchlist_bool_check(
            name="segment_expansion_production_promotion_ready",
            actual=segment_expansion.production_promotion_ready,
            required=options.require_segment_expansion_production_promotion_ready,
            detail=(
                "source segment-expansion evidence should be production-ready "
                "only when promotion is explicitly required"
            ),
        ),
        _minimum_check(
            name="replay_report_count",
            actual=len(replay_summaries),
            threshold=options.min_replay_report_count,
            detail="batch gate should include enough runtime replay reports",
        ),
        _minimum_check(
            name="passed_replay_count",
            actual=passed_replay_count,
            threshold=options.min_passed_replay_count,
            detail="batch gate should include enough passed replay reports",
        ),
        _optional_maximum_check(
            name="failed_replay_count",
            actual=failed_replay_count,
            threshold=options.max_failed_replay_count,
            detail="runtime replay reports should not fail",
        ),
        _minimum_check(
            name="runtime_allowed_replay_count",
            actual=runtime_allowed_replay_count,
            threshold=options.min_passed_replay_count
            if options.require_replay_allowed
            else 0,
            detail="runtime replay reports should be explicitly allowed",
        ),
        _minimum_check(
            name="distinct_rule_count",
            actual=len(replayed_rule_ids),
            threshold=options.min_distinct_rule_count,
            detail="batch gate should replay enough distinct rules",
        ),
        _minimum_check(
            name="distinct_segment_count",
            actual=len(replayed_segment_group_keys),
            threshold=options.min_distinct_segment_count,
            detail="batch gate should cover enough distinct segments",
        ),
        _minimum_check(
            name="covered_selected_segment_count",
            actual=len(set(selected_segment_group_keys) & set(replayed_segment_group_keys)),
            threshold=options.min_covered_selected_segment_count,
            detail="batch gate should cover source-selected expansion segments",
        ),
        _required_bool_check(
            name="all_expansion_selected_segments_replayed",
            actual=not missing_selected_segments,
            required=options.require_all_expansion_selected_segments_replayed,
            detail="every source-selected segment should receive a runtime replay",
        ),
        _required_bool_check(
            name="replay_rule_subset_of_expansion",
            actual=not unexpected_replayed_rules and not unexpected_replayed_segments,
            required=options.require_replay_rule_subset_of_expansion,
            detail="runtime replay reports should match the staged expansion profile",
        ),
        _required_bool_check(
            name="all_replays_passed_status",
            actual=all(
                summary.status == "runtime_shadow_replay_passed"
                for summary in replay_summaries
            ),
            required=options.require_replay_passed_status,
            detail="all attached replays should have passed runtime-shadow status",
        ),
        _minimum_check(
            name="total_adjusted_fixture_count",
            actual=total_adjusted_fixture_count,
            threshold=options.min_total_adjusted_fixture_count,
            detail="batch replay should cover enough adjusted fixtures",
        ),
        _minimum_check(
            name="total_adjusted_prediction_count",
            actual=total_adjusted_prediction_count,
            threshold=options.min_total_adjusted_prediction_count,
            detail="batch replay should cover enough adjusted predictions",
        ),
        _optional_minimum_check(
            name="worst_final_hit_rate_delta",
            actual=_minimum_optional(
                summary.final_hit_rate_delta for summary in replay_summaries
            ),
            threshold=options.min_worst_final_hit_rate_delta,
            detail="no replay segment should regress final-hit rate",
        ),
        _optional_minimum_check(
            name="worst_roi_delta",
            actual=_minimum_optional(summary.roi_delta for summary in replay_summaries),
            threshold=options.min_worst_roi_delta,
            detail="no replay segment should regress ROI",
        ),
        _optional_minimum_check(
            name="total_profit_loss_delta",
            actual=total_profit_loss_delta,
            threshold=options.min_total_profit_loss_delta,
            detail="batch replay should not regress profit/loss",
        ),
        _optional_maximum_check(
            name="worst_brier_score_delta",
            actual=_maximum_optional(
                summary.brier_score_delta for summary in replay_summaries
            ),
            threshold=options.max_worst_brier_score_delta,
            detail="no replay segment should regress Brier score",
        ),
        _optional_maximum_check(
            name="worst_log_loss_delta",
            actual=_maximum_optional(
                summary.log_loss_delta for summary in replay_summaries
            ),
            threshold=options.max_worst_log_loss_delta,
            detail="no replay segment should regress log loss",
        ),
        _optional_maximum_check(
            name="worst_calibration_delta",
            actual=_maximum_optional(
                summary.mean_calibration_error_delta for summary in replay_summaries
            ),
            threshold=options.max_worst_mean_calibration_error_delta,
            detail="no replay segment should regress calibration error",
        ),
        _required_bool_check(
            name="default_path_unchanged",
            actual=not default_path_changed,
            required=options.require_no_default_path_change,
            detail="batch gate should not change the default recommendation path",
        ),
        _required_bool_check(
            name="production_unchanged",
            actual=not production_changed,
            required=options.require_no_production_change,
            detail="batch gate should not change production recommendations",
        ),
        _required_bool_check(
            name="public_response_unchanged",
            actual=not public_changed,
            required=options.require_no_public_response_change,
            detail="batch gate should not change public responses",
        ),
    ]


def _profile_rules(
    segment_expansion: HistoricalMarketMovementRuntimeActivationSegmentExpansionReport,
) -> list[dict[str, object]]:
    rules = segment_expansion.profile_json.get("rules")
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _replay_passed(
    summary: HistoricalMarketMovementRuntimeActivationSegmentReplaySummary,
) -> bool:
    return (
        summary.status == "runtime_shadow_replay_passed"
        and summary.runtime_shadow_replay_allowed
    )


def _unique(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str)})


def _weighted_average(
    replay_summaries: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentReplaySummary
    ],
    *,
    metric: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for summary in replay_summaries:
        value = getattr(summary, metric)
        if not isinstance(value, int | float):
            continue
        if summary.adjusted_prediction_count <= 0:
            continue
        numerator += float(value) * summary.adjusted_prediction_count
        denominator += summary.adjusted_prediction_count
    if denominator == 0:
        return None
    return numerator / denominator


def _sum_optional(values: Iterable[float | None]) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, int | float)]
    if not numeric_values:
        return None
    return sum(numeric_values)


def _minimum_optional(values: Iterable[float | None]) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, int | float)]
    if not numeric_values:
        return None
    return min(numeric_values)


def _maximum_optional(values: Iterable[float | None]) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, int | float)]
    if not numeric_values:
        return None
    return max(numeric_values)


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | None,
    threshold: float | None,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
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
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool = True,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    if not required:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _watchlist_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    if required:
        return _required_bool_check(
            name=name,
            actual=actual,
            required=True,
            detail=detail,
        )
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="passed" if actual else "watchlist",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | list[str] | None,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck:
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _report_key(
    summary: dict[str, object],
    checks: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateCheck
    ],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_market_movement_segment_replay_batch_gate:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser()
    parser.add_argument("--segment-expansion-report", type=Path, required=True)
    parser.add_argument(
        "--runtime-replay-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--gate-id", default=None)
    parser.add_argument("--min-replay-report-count", type=int, default=1)
    parser.add_argument("--min-passed-replay-count", type=int, default=1)
    parser.add_argument("--max-failed-replay-count", type=int, default=0)
    parser.add_argument("--min-distinct-rule-count", type=int, default=1)
    parser.add_argument("--min-distinct-segment-count", type=int, default=1)
    parser.add_argument("--min-covered-selected-segment-count", type=int, default=1)
    parser.add_argument("--min-total-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-total-adjusted-prediction-count", type=int, default=1)
    parser.add_argument("--min-worst-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-worst-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-total-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-worst-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-worst-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-worst-calibration-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--allow-segment-expansion-not-passed", action="store_true")
    parser.add_argument("--allow-segment-expansion-not-ready", action="store_true")
    parser.add_argument(
        "--require-segment-expansion-production-promotion-ready",
        action="store_true",
    )
    parser.add_argument("--allow-missing-expansion-selected-segment", action="store_true")
    parser.add_argument("--allow-replay-not-allowed", action="store_true")
    parser.add_argument("--allow-replay-non-passed-status", action="store_true")
    parser.add_argument("--allow-replay-outside-expansion", action="store_true")
    parser.add_argument("--allow-default-path-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions:
    updates: dict[str, object] = {
        "min_replay_report_count": args.min_replay_report_count,
        "min_passed_replay_count": args.min_passed_replay_count,
        "max_failed_replay_count": args.max_failed_replay_count,
        "min_distinct_rule_count": args.min_distinct_rule_count,
        "min_distinct_segment_count": args.min_distinct_segment_count,
        "min_covered_selected_segment_count": (
            args.min_covered_selected_segment_count
        ),
        "min_total_adjusted_fixture_count": args.min_total_adjusted_fixture_count,
        "min_total_adjusted_prediction_count": (
            args.min_total_adjusted_prediction_count
        ),
        "min_worst_final_hit_rate_delta": args.min_worst_final_hit_rate_delta,
        "min_worst_roi_delta": args.min_worst_roi_delta,
        "min_total_profit_loss_delta": args.min_total_profit_loss_delta,
        "max_worst_brier_score_delta": args.max_worst_brier_score_delta,
        "max_worst_log_loss_delta": args.max_worst_log_loss_delta,
        "max_worst_mean_calibration_error_delta": args.max_worst_calibration_delta,
        "require_segment_expansion_passed": (
            not args.allow_segment_expansion_not_passed
        ),
        "require_segment_expansion_runtime_ready": (
            not args.allow_segment_expansion_not_ready
        ),
        "require_segment_expansion_production_promotion_ready": (
            args.require_segment_expansion_production_promotion_ready
        ),
        "require_all_expansion_selected_segments_replayed": (
            not args.allow_missing_expansion_selected_segment
        ),
        "require_replay_allowed": not args.allow_replay_not_allowed,
        "require_replay_passed_status": (
            not args.allow_replay_non_passed_status
        ),
        "require_replay_rule_subset_of_expansion": (
            not args.allow_replay_outside_expansion
        ),
        "require_no_default_path_change": not args.allow_default_path_change,
        "require_no_production_change": not args.allow_production_change,
        "require_no_public_response_change": not args.allow_public_response_change,
    }
    if args.gate_id is not None:
        updates["gate_id"] = args.gate_id
    return HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions.model_validate(
        updates
    )


if __name__ == "__main__":
    main()
