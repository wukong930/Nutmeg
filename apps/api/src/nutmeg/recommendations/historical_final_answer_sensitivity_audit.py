from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from statistics import mean
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.final_arbitrator import score_final_answer_option
from nutmeg.recommendations.global_planner import RecommendationGlobalPlanOption
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    _rank_historical_final_answer_options,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateReport,
)
from nutmeg.recommendations.models import RecommendationMode

type HistoricalFinalAnswerSensitivityAuditSide = Literal["baseline", "candidate"]
type HistoricalFinalAnswerSensitivityAuditStatus = Literal["generated"]


class HistoricalFinalAnswerSensitivityAuditOptions(BaseModel):
    side: HistoricalFinalAnswerSensitivityAuditSide = "candidate"
    max_near_miss_score_gap: float = Field(default=0.03, ge=0.0, le=1.0)
    top_near_miss_limit: int = Field(default=20, ge=1, le=200)
    include_same_signature_runner_up: bool = False


class HistoricalFinalAnswerSensitivityItem(BaseModel):
    slice_id: str
    winner_option_key: str
    runner_up_option_key: str
    winner_pass_type: str
    runner_up_pass_type: str
    winner_mode: RecommendationMode
    runner_up_mode: RecommendationMode
    winner_score: float = Field(ge=0.0, le=1.0)
    runner_up_score: float = Field(ge=0.0, le=1.0)
    score_gap: float = Field(ge=0.0)
    winner_hit_probability: float = Field(ge=0.0, le=1.0)
    runner_up_hit_probability: float = Field(ge=0.0, le=1.0)
    runner_up_hit_probability_delta: float
    winner_roi: float
    runner_up_roi: float
    roi_delta: float
    winner_profit_loss: float
    runner_up_profit_loss: float
    profit_loss_delta: float
    winner_actual_hit: bool
    runner_up_actual_hit: bool
    final_answer_signature_changed: bool
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerSensitivityAuditReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSensitivityAuditStatus
    suite_key: str
    source_report_key: str | None = None
    evaluation_side: HistoricalFinalAnswerSensitivityAuditSide
    comparison_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    runner_up_count: int = Field(ge=0)
    runner_up_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    near_miss_count: int = Field(ge=0)
    near_miss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    actionable_near_miss_count: int = Field(ge=0)
    actionable_near_miss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    runner_up_higher_hit_probability_count: int = Field(ge=0)
    winner_loss_runner_up_hit_count: int = Field(ge=0)
    average_score_gap: float | None = Field(default=None, ge=0.0)
    min_score_gap: float | None = Field(default=None, ge=0.0)
    diagnostic_codes: list[str] = Field(default_factory=list)
    top_near_misses: list[HistoricalFinalAnswerSensitivityItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_final_answer_sensitivity_audit_report(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalFinalAnswerSensitivityAuditOptions | None = None,
    source_report_key: str | None = None,
) -> HistoricalFinalAnswerSensitivityAuditReport:
    resolved_options = options or HistoricalFinalAnswerSensitivityAuditOptions()
    warnings = list(suite.warnings)
    items: list[HistoricalFinalAnswerSensitivityItem] = []
    final_answer_count = 0
    for comparison in suite.comparisons:
        result = _comparison_result(comparison, side=resolved_options.side)
        if result.final_answer is None:
            warnings.append(
                f"historical_final_answer_sensitivity:no_final_answer:{result.slice_id}"
            )
            continue
        final_answer_count += 1
        item = _sensitivity_item(result, options=resolved_options)
        if item is not None:
            items.append(item)
    near_misses = [
        item
        for item in items
        if item.score_gap <= resolved_options.max_near_miss_score_gap
    ]
    actionable = [
        item
        for item in near_misses
        if item.runner_up_hit_probability_delta > 0
        or (not item.winner_actual_hit and item.runner_up_actual_hit)
    ]
    score_gaps = [item.score_gap for item in items]
    runner_up_coverage_rate = _ratio(len(items), final_answer_count)
    near_miss_rate = _ratio(len(near_misses), final_answer_count)
    actionable_near_miss_rate = _ratio(len(actionable), final_answer_count)
    diagnostic_codes = _diagnostic_codes(
        final_answer_count=final_answer_count,
        runner_up_count=len(items),
        near_miss_count=len(near_misses),
        actionable_near_miss_count=len(actionable),
        runner_up_higher_hit_probability_count=sum(
            1 for item in items if item.runner_up_hit_probability_delta > 0
        ),
    )
    top_near_misses = sorted(
        near_misses,
        key=lambda item: (
            item.score_gap,
            -item.runner_up_hit_probability_delta,
            -item.profit_loss_delta,
            item.slice_id,
        ),
    )[: resolved_options.top_near_miss_limit]
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_sensitivity_audit_v3_1",
        "suite_key": suite.suite_key,
        "source_report_key": source_report_key,
        "evaluation_side": resolved_options.side,
        "comparison_count": suite.comparison_count,
        "final_answer_count": final_answer_count,
        "runner_up_count": len(items),
        "runner_up_coverage_rate": runner_up_coverage_rate,
        "near_miss_count": len(near_misses),
        "near_miss_rate": near_miss_rate,
        "actionable_near_miss_count": len(actionable),
        "actionable_near_miss_rate": actionable_near_miss_rate,
        "runner_up_higher_hit_probability_count": sum(
            1 for item in items if item.runner_up_hit_probability_delta > 0
        ),
        "winner_loss_runner_up_hit_count": sum(
            1
            for item in items
            if not item.winner_actual_hit and item.runner_up_actual_hit
        ),
        "average_score_gap": mean(score_gaps) if score_gaps else None,
        "min_score_gap": min(score_gaps) if score_gaps else None,
        "diagnostic_codes": diagnostic_codes,
        "max_near_miss_score_gap": resolved_options.max_near_miss_score_gap,
        "top_near_miss_slice_ids": [item.slice_id for item in top_near_misses],
        "warnings": warnings,
    }
    report_key = _report_key(summary, top_near_misses)
    return HistoricalFinalAnswerSensitivityAuditReport(
        report_key=report_key,
        status="generated",
        suite_key=suite.suite_key,
        source_report_key=source_report_key,
        evaluation_side=resolved_options.side,
        comparison_count=suite.comparison_count,
        final_answer_count=final_answer_count,
        runner_up_count=len(items),
        runner_up_coverage_rate=runner_up_coverage_rate,
        near_miss_count=len(near_misses),
        near_miss_rate=near_miss_rate,
        actionable_near_miss_count=len(actionable),
        actionable_near_miss_rate=actionable_near_miss_rate,
        runner_up_higher_hit_probability_count=sum(
            1 for item in items if item.runner_up_hit_probability_delta > 0
        ),
        winner_loss_runner_up_hit_count=sum(
            1
            for item in items
            if not item.winner_actual_hit and item.runner_up_actual_hit
        ),
        average_score_gap=mean(score_gaps) if score_gaps else None,
        min_score_gap=min(score_gaps) if score_gaps else None,
        diagnostic_codes=diagnostic_codes,
        top_near_misses=top_near_misses,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_final_answer_sensitivity_audit_report(
    path: Path | str,
) -> HistoricalFinalAnswerSensitivityAuditReport:
    return HistoricalFinalAnswerSensitivityAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    suite, source_report_key = _suite_from_args(args)
    report = build_historical_final_answer_sensitivity_audit_report(
        suite,
        options=HistoricalFinalAnswerSensitivityAuditOptions(
            side=cast(HistoricalFinalAnswerSensitivityAuditSide, args.side),
            max_near_miss_score_gap=args.max_near_miss_score_gap,
            top_near_miss_limit=args.top_near_miss_limit,
            include_same_signature_runner_up=args.include_same_signature_runner_up,
        ),
        source_report_key=source_report_key,
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


def _sensitivity_item(
    result: HistoricalRecommendationBacktestResult,
    *,
    options: HistoricalFinalAnswerSensitivityAuditOptions,
) -> HistoricalFinalAnswerSensitivityItem | None:
    scenario_options = [
        scenario.option
        for scenario in result.scenarios
        if scenario.status == "completed" and scenario.option is not None
    ]
    if len(scenario_options) < 2:
        return None
    ranked_options = _rank_historical_final_answer_options(
        scenario_options,
        backtest_options=_backtest_options_from_result(result),
    )
    if not ranked_options:
        return None
    winner = ranked_options[0]
    winner_signature = _option_signature(winner)
    runner_up = next(
        (
            option
            for option in ranked_options[1:]
            if options.include_same_signature_runner_up
            or _option_signature(option) != winner_signature
        ),
        None,
    )
    if runner_up is None:
        return None
    winner_score = score_final_answer_option(winner).final_answer_score
    runner_up_score = score_final_answer_option(runner_up).final_answer_score
    winner_result = _scenario_result_for_option(result, winner.option_key)
    runner_up_result = _scenario_result_for_option(result, runner_up.option_key)
    if winner_result is None or runner_up_result is None:
        return None
    score_gap = max(0.0, winner_score - runner_up_score)
    runner_up_hit_probability_delta = (
        runner_up.selection.evaluation.hit_probability
        - winner.selection.evaluation.hit_probability
    )
    roi_delta = runner_up.selection.evaluation.roi - winner.selection.evaluation.roi
    profit_loss_delta = runner_up_result.profit_loss - winner_result.profit_loss
    reason_codes = _reason_codes(
        score_gap=score_gap,
        runner_up_hit_probability_delta=runner_up_hit_probability_delta,
        winner_actual_hit=winner_result.actual_hit,
        runner_up_actual_hit=runner_up_result.actual_hit,
        profit_loss_delta=profit_loss_delta,
        options=options,
    )
    return HistoricalFinalAnswerSensitivityItem(
        slice_id=result.slice_id,
        winner_option_key=winner.option_key,
        runner_up_option_key=runner_up.option_key,
        winner_pass_type=winner.pass_type,
        runner_up_pass_type=runner_up.pass_type,
        winner_mode=winner.mode,
        runner_up_mode=runner_up.mode,
        winner_score=winner_score,
        runner_up_score=runner_up_score,
        score_gap=score_gap,
        winner_hit_probability=winner.selection.evaluation.hit_probability,
        runner_up_hit_probability=runner_up.selection.evaluation.hit_probability,
        runner_up_hit_probability_delta=runner_up_hit_probability_delta,
        winner_roi=winner.selection.evaluation.roi,
        runner_up_roi=runner_up.selection.evaluation.roi,
        roi_delta=roi_delta,
        winner_profit_loss=winner_result.profit_loss,
        runner_up_profit_loss=runner_up_result.profit_loss,
        profit_loss_delta=profit_loss_delta,
        winner_actual_hit=winner_result.actual_hit,
        runner_up_actual_hit=runner_up_result.actual_hit,
        final_answer_signature_changed=_option_signature(runner_up) != winner_signature,
        reason_codes=reason_codes,
        summary_json={
            "winner_fixture_ids": winner.selection.fixture_ids,
            "runner_up_fixture_ids": runner_up.selection.fixture_ids,
            "winner_selected_outcomes": _selected_outcomes(winner_result),
            "runner_up_selected_outcomes": _selected_outcomes(runner_up_result),
        },
    )


def _comparison_result(
    comparison: HistoricalRecommendationBacktestComparisonResult,
    *,
    side: HistoricalFinalAnswerSensitivityAuditSide,
) -> HistoricalRecommendationBacktestResult:
    return comparison.baseline if side == "baseline" else comparison.candidate


def _backtest_options_from_result(
    result: HistoricalRecommendationBacktestResult,
) -> HistoricalRecommendationBacktestOptions:
    pass_types = tuple(
        sorted(
            {
                scenario.scenario.pass_type
                for scenario in result.scenarios
                if scenario.status == "completed"
            }
        )
    )
    modes = tuple(
        sorted(
            {
                scenario.scenario.mode
                for scenario in result.scenarios
                if scenario.status == "completed"
            }
        )
    )
    return HistoricalRecommendationBacktestOptions(
        pass_types=pass_types or ("1x1",),
        modes=modes or ("single",),
    )


def _scenario_result_for_option(
    result: HistoricalRecommendationBacktestResult,
    option_key: str,
) -> HistoricalRecommendationScenarioResult | None:
    return next(
        (
            scenario
            for scenario in result.scenarios
            if scenario.option is not None and scenario.option.option_key == option_key
        ),
        None,
    )


def _option_signature(option: RecommendationGlobalPlanOption) -> tuple[object, ...]:
    return (
        option.option_key,
        tuple(option.selection.fixture_ids),
        tuple(
            (
                scored.candidate.fixture_id,
                scored.candidate.market_type,
                scored.candidate.outcome,
                scored.candidate.line,
                scored.candidate.side,
            )
            for scored in option.selection.selected_candidates
        ),
    )


def _selected_outcomes(
    result: HistoricalRecommendationScenarioResult,
) -> dict[str, list[str]]:
    return {
        fixture_id: list(outcomes)
        for fixture_id, outcomes in result.selected_outcomes.items()
    }


def _reason_codes(
    *,
    score_gap: float,
    runner_up_hit_probability_delta: float,
    winner_actual_hit: bool,
    runner_up_actual_hit: bool,
    profit_loss_delta: float,
    options: HistoricalFinalAnswerSensitivityAuditOptions,
) -> list[str]:
    reason_codes = ["runner_up_available"]
    if score_gap <= options.max_near_miss_score_gap:
        reason_codes.append("near_miss_score_gap")
    if runner_up_hit_probability_delta > 0:
        reason_codes.append("runner_up_higher_hit_probability")
    if not winner_actual_hit and runner_up_actual_hit:
        reason_codes.append("winner_lost_runner_up_hit")
    if profit_loss_delta > 0:
        reason_codes.append("runner_up_higher_profit_loss")
    return reason_codes


def _diagnostic_codes(
    *,
    final_answer_count: int,
    runner_up_count: int,
    near_miss_count: int,
    actionable_near_miss_count: int,
    runner_up_higher_hit_probability_count: int,
) -> list[str]:
    if final_answer_count == 0:
        return ["no_final_answers"]
    codes: list[str] = []
    coverage = runner_up_count / final_answer_count
    if coverage < 0.50:
        codes.append("candidate_generation_sparse")
    if runner_up_count == 0:
        codes.append("no_distinct_runner_up_options")
    if near_miss_count == 0:
        codes.append("no_near_miss_margin")
    if runner_up_higher_hit_probability_count == 0:
        codes.append("no_higher_hit_probability_runner_up")
    if actionable_near_miss_count == 0:
        codes.append("no_actionable_near_miss")
    return codes


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _suite_from_args(
    args: Namespace,
) -> tuple[HistoricalRecommendationBacktestSuiteResult, str | None]:
    if args.profile_gate_report is not None:
        gate_report = HistoricalProbabilityCalibrationProfileGateReport.model_validate_json(
            args.profile_gate_report.read_text(encoding="utf-8")
        )
        if gate_report.suite is None:
            raise SystemExit("profile gate report does not include a suite")
        return gate_report.suite, gate_report.report_key
    if args.suite_report is not None:
        suite = HistoricalRecommendationBacktestSuiteResult.model_validate_json(
            args.suite_report.read_text(encoding="utf-8")
        )
        return suite, suite.suite_key
    raise SystemExit("provide --profile-gate-report or --suite-report")


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Audit final-answer arbitration sensitivity by comparing the chosen "
            "answer with the nearest runner-up in a historical suite."
        )
    )
    parser.add_argument("--profile-gate-report", type=Path)
    parser.add_argument("--suite-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--side", choices=["baseline", "candidate"], default="candidate")
    parser.add_argument("--max-near-miss-score-gap", type=float, default=0.03)
    parser.add_argument("--top-near-miss-limit", type=int, default=20)
    parser.add_argument("--include-same-signature-runner-up", action="store_true")
    args = parser.parse_args(argv)
    if args.profile_gate_report is None and args.suite_report is None:
        parser.error("provide --profile-gate-report or --suite-report")
    if args.profile_gate_report is not None and args.suite_report is not None:
        parser.error("provide only one of --profile-gate-report or --suite-report")
    return args


def _report_key(
    summary: dict[str, object],
    top_near_misses: Sequence[HistoricalFinalAnswerSensitivityItem],
) -> str:
    payload = {
        "summary": summary,
        "top_near_misses": [
            item.model_dump(mode="json") for item in top_near_misses
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_sensitivity_audit:{digest}"
