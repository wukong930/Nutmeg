from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalFinalAnswerAuditSide = Literal["baseline", "candidate"]
type HistoricalFinalAnswerSegmentType = Literal[
    "overall",
    "pass_type",
    "mode",
    "scenario",
    "leg_count",
    "odds_band",
    "hit_probability_band",
    "competition",
    "market_mix",
    "competition_pass_type",
    "competition_scenario",
    "competition_odds_band",
    "competition_hit_probability_band",
    "pass_type_odds_band",
    "pass_type_hit_probability_band",
    "odds_probability_band",
]
type HistoricalFinalAnswerSegmentAuditStatus = Literal["generated"]

DEFAULT_AUDIT_PASS_TYPES = ("1x1", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1")
DEFAULT_AUDIT_MODES: tuple[RecommendationMode, ...] = ("single", "multiple")


class HistoricalFinalAnswerSegmentAuditOptions(BaseModel):
    side: HistoricalFinalAnswerAuditSide = "candidate"
    min_segment_sample_size: int = Field(default=2, ge=1)
    top_segment_limit: int = Field(default=12, ge=1, le=100)
    include_interaction_segments: bool = False
    odds_band_edges: tuple[float, ...] = (1.0, 1.30, 1.60, 2.0, 3.0, 5.0, 10.0)
    hit_probability_band_edges: tuple[float, ...] = (
        0.0,
        0.25,
        0.40,
        0.55,
        0.70,
        0.85,
        1.0,
    )


class HistoricalFinalAnswerSegmentMetric(BaseModel):
    segment_key: str
    segment_type: HistoricalFinalAnswerSegmentType
    segment_value: str
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    loss_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(ge=0.0)
    actual_return: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    average_expected_hit_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    average_odds_product: float | None = Field(default=None, gt=1.0)
    average_leg_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_leg_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_brier_score: float | None = Field(default=None, ge=0.0)
    average_log_loss: float | None = Field(default=None, ge=0.0)
    average_calibration_error: float | None = Field(default=None, ge=0.0)
    loss_driver_score: float = Field(ge=0.0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerSegmentAuditReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSegmentAuditStatus
    suite_key: str
    suite_status: str
    evaluation_side: HistoricalFinalAnswerAuditSide
    comparison_count: int = Field(ge=0)
    final_answer_sample_size: int = Field(ge=0)
    min_segment_sample_size: int = Field(ge=1)
    overall: HistoricalFinalAnswerSegmentMetric | None = None
    segment_count: int = Field(ge=0)
    segments: list[HistoricalFinalAnswerSegmentMetric] = Field(default_factory=list)
    loss_driver_segments: list[HistoricalFinalAnswerSegmentMetric] = Field(
        default_factory=list
    )
    best_segments: list[HistoricalFinalAnswerSegmentMetric] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass
class _SegmentAccumulator:
    segment_type: HistoricalFinalAnswerSegmentType
    segment_value: str
    sample_size: int = 0
    hit_count: int = 0
    total_stake: float = 0.0
    actual_return: float = 0.0
    profit_loss: float = 0.0
    expected_hit_probabilities: list[float] = field(default_factory=list)
    odds_products: list[float] = field(default_factory=list)
    leg_decimal_odds: list[float] = field(default_factory=list)
    leg_probabilities: list[float] = field(default_factory=list)
    brier_scores: list[float] = field(default_factory=list)
    log_losses: list[float] = field(default_factory=list)
    calibration_errors: list[float] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.segment_type}:{self.segment_value}"


def build_historical_final_answer_segment_audit_report(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalFinalAnswerSegmentAuditOptions | None = None,
) -> HistoricalFinalAnswerSegmentAuditReport:
    resolved_options = options or HistoricalFinalAnswerSegmentAuditOptions()
    accumulators: dict[str, _SegmentAccumulator] = {}
    warnings = list(suite.warnings)
    for comparison in suite.comparisons:
        result = _comparison_result(comparison, side=resolved_options.side)
        if result.final_answer is None:
            warnings.append(
                f"historical_final_answer_segment_audit:no_final_answer:{result.slice_id}"
            )
            continue
        for segment_type, segment_value in _segments_for_result(
            result,
            options=resolved_options,
        ):
            key = f"{segment_type}:{segment_value}"
            accumulator = accumulators.setdefault(
                key,
                _SegmentAccumulator(
                    segment_type=segment_type,
                    segment_value=segment_value,
                ),
            )
            _add_result_to_segment(accumulator, result)

    overall = accumulators.get("overall:all")
    overall_hit_rate = _ratio(overall.hit_count, overall.sample_size) if overall else None
    metrics = [
        _segment_metric(
            accumulator,
            overall_hit_rate=overall_hit_rate,
            min_segment_sample_size=resolved_options.min_segment_sample_size,
        )
        for accumulator in accumulators.values()
    ]
    metrics = sorted(metrics, key=lambda metric: (metric.segment_type, metric.segment_value))
    overall_metric = next(
        (metric for metric in metrics if metric.segment_key == "overall:all"),
        None,
    )
    eligible = [
        metric
        for metric in metrics
        if metric.segment_type != "overall"
        and metric.sample_size >= resolved_options.min_segment_sample_size
    ]
    loss_driver_segments = sorted(
        [metric for metric in eligible if metric.loss_driver_score > 0],
        key=lambda metric: (
            -metric.loss_driver_score,
            metric.hit_rate if metric.hit_rate is not None else 1.0,
            -metric.sample_size,
            metric.segment_key,
        ),
    )[: resolved_options.top_segment_limit]
    best_segments = sorted(
        eligible,
        key=lambda metric: (
            -(metric.hit_rate or 0.0),
            -(metric.roi or -999.0),
            -metric.sample_size,
            metric.segment_key,
        ),
    )[: resolved_options.top_segment_limit]
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_segment_audit_v3_1",
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "evaluation_side": resolved_options.side,
        "comparison_count": suite.comparison_count,
        "final_answer_sample_size": overall_metric.sample_size if overall_metric else 0,
        "min_segment_sample_size": resolved_options.min_segment_sample_size,
        "include_interaction_segments": resolved_options.include_interaction_segments,
        "segment_count": len(metrics),
        "overall_hit_rate": overall_metric.hit_rate if overall_metric else None,
        "overall_roi": overall_metric.roi if overall_metric else None,
        "top_loss_driver_segment_keys": [
            metric.segment_key for metric in loss_driver_segments
        ],
        "top_best_segment_keys": [metric.segment_key for metric in best_segments],
        "warnings": warnings,
    }
    report_key = _report_key(summary, metrics)
    return HistoricalFinalAnswerSegmentAuditReport(
        report_key=report_key,
        status="generated",
        suite_key=suite.suite_key,
        suite_status=suite.status,
        evaluation_side=resolved_options.side,
        comparison_count=suite.comparison_count,
        final_answer_sample_size=overall_metric.sample_size if overall_metric else 0,
        min_segment_sample_size=resolved_options.min_segment_sample_size,
        overall=overall_metric,
        segment_count=len(metrics),
        segments=metrics,
        loss_driver_segments=loss_driver_segments,
        best_segments=best_segments,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    backtest_options = HistoricalRecommendationBacktestOptions(
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        strategy=cast(RecommendationStrategy, args.strategy),
        unit_stake=args.unit_stake,
        max_budget=args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        require_odds=not args.no_require_odds,
        candidate_fixture_limit=args.candidate_fixture_limit,
        max_candidates_per_fixture=args.max_candidates_per_fixture,
        scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
        derive_market_context_signals=args.derive_market_context_signals,
    )
    suite = run_historical_recommendation_backtest_suite(
        loaded.slices,
        options=backtest_options,
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
    )
    report = build_historical_final_answer_segment_audit_report(
        suite,
        options=HistoricalFinalAnswerSegmentAuditOptions(
            side=cast(HistoricalFinalAnswerAuditSide, args.side),
            min_segment_sample_size=args.min_segment_sample_size,
            top_segment_limit=args.top_segment_limit,
            include_interaction_segments=args.include_interaction_segments,
        ),
    )
    if loaded.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
    if loaded.warnings:
        report.warnings.extend(loaded.warnings)
        report.summary_json["manifest_warnings"] = loaded.warnings
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


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_results: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


def _comparison_result(
    comparison: HistoricalRecommendationBacktestComparisonResult,
    *,
    side: HistoricalFinalAnswerAuditSide,
) -> HistoricalRecommendationBacktestResult:
    if side == "baseline":
        return comparison.baseline
    return comparison.candidate


def _segments_for_result(
    result: HistoricalRecommendationBacktestResult,
    *,
    options: HistoricalFinalAnswerSegmentAuditOptions,
) -> list[tuple[HistoricalFinalAnswerSegmentType, str]]:
    final_answer = result.final_answer
    if final_answer is None:
        return []
    pass_type = final_answer.scenario.pass_type
    scenario_key = final_answer.scenario.scenario_key
    odds_band = _band_label(_average_odds_product(final_answer), options.odds_band_edges)
    hit_probability_band = _band_label(
        final_answer.expected_hit_probability,
        options.hit_probability_band_edges,
    )
    competition_ids = _competition_ids(final_answer)
    segments: list[tuple[HistoricalFinalAnswerSegmentType, str]] = [
        ("overall", "all"),
        ("pass_type", pass_type),
        ("mode", final_answer.scenario.mode),
        ("scenario", scenario_key),
        ("leg_count", str(len(final_answer.selected_fixture_ids))),
        ("odds_band", odds_band),
        ("hit_probability_band", hit_probability_band),
        ("market_mix", _market_mix(final_answer)),
    ]
    for competition_id in competition_ids:
        segments.append(("competition", competition_id))
    if options.include_interaction_segments:
        for competition_id in competition_ids:
            segments.extend(
                [
                    ("competition_pass_type", f"{competition_id}:{pass_type}"),
                    ("competition_scenario", f"{competition_id}:{scenario_key}"),
                    ("competition_odds_band", f"{competition_id}:{odds_band}"),
                    (
                        "competition_hit_probability_band",
                        f"{competition_id}:{hit_probability_band}",
                    ),
                ]
            )
        segments.extend(
            [
                ("pass_type_odds_band", f"{pass_type}:{odds_band}"),
                (
                    "pass_type_hit_probability_band",
                    f"{pass_type}:{hit_probability_band}",
                ),
                ("odds_probability_band", f"{odds_band}:{hit_probability_band}"),
            ]
        )
    return segments


def _add_result_to_segment(
    accumulator: _SegmentAccumulator,
    result: HistoricalRecommendationBacktestResult,
) -> None:
    final_answer = result.final_answer
    if final_answer is None:
        return
    accumulator.sample_size += 1
    accumulator.hit_count += 1 if final_answer.actual_hit else 0
    accumulator.total_stake += final_answer.total_stake
    accumulator.actual_return += final_answer.actual_return
    accumulator.profit_loss += final_answer.profit_loss
    if final_answer.expected_hit_probability is not None:
        accumulator.expected_hit_probabilities.append(final_answer.expected_hit_probability)
    odds_product = _average_odds_product(final_answer)
    if odds_product is not None:
        accumulator.odds_products.append(odds_product)
    accumulator.leg_decimal_odds.extend(_leg_decimal_odds(final_answer))
    accumulator.leg_probabilities.extend(_leg_probabilities(final_answer))
    if final_answer.brier_score is not None:
        accumulator.brier_scores.append(final_answer.brier_score)
    if final_answer.log_loss is not None:
        accumulator.log_losses.append(final_answer.log_loss)
    if final_answer.calibration_error is not None:
        accumulator.calibration_errors.append(final_answer.calibration_error)


def _segment_metric(
    accumulator: _SegmentAccumulator,
    *,
    overall_hit_rate: float | None,
    min_segment_sample_size: int,
) -> HistoricalFinalAnswerSegmentMetric:
    hit_rate = _ratio(accumulator.hit_count, accumulator.sample_size)
    loss_count = accumulator.sample_size - accumulator.hit_count
    loss_rate = _ratio(loss_count, accumulator.sample_size)
    roi = (
        accumulator.profit_loss / accumulator.total_stake
        if accumulator.total_stake > 0
        else None
    )
    underperformance = (
        max(0.0, overall_hit_rate - hit_rate)
        if overall_hit_rate is not None and hit_rate is not None
        else 0.0
    )
    negative_roi_pressure = max(0.0, -(roi or 0.0))
    loss_driver_score = (
        underperformance * accumulator.sample_size + negative_roi_pressure
        if accumulator.sample_size >= min_segment_sample_size
        else 0.0
    )
    summary: dict[str, object] = {
        "segment_key": accumulator.key,
        "segment_type": accumulator.segment_type,
        "segment_value": accumulator.segment_value,
        "underperformance_vs_overall_hit_rate": underperformance,
        "negative_roi_pressure": negative_roi_pressure,
        "meets_min_segment_sample_size": accumulator.sample_size
        >= min_segment_sample_size,
    }
    return HistoricalFinalAnswerSegmentMetric(
        segment_key=accumulator.key,
        segment_type=accumulator.segment_type,
        segment_value=accumulator.segment_value,
        sample_size=accumulator.sample_size,
        hit_count=accumulator.hit_count,
        loss_count=loss_count,
        hit_rate=hit_rate,
        loss_rate=loss_rate,
        total_stake=accumulator.total_stake,
        actual_return=accumulator.actual_return,
        profit_loss=accumulator.profit_loss,
        roi=roi,
        average_expected_hit_probability=_average(accumulator.expected_hit_probabilities),
        average_odds_product=_average(accumulator.odds_products),
        average_leg_decimal_odds=_average(accumulator.leg_decimal_odds),
        average_leg_probability=_average(accumulator.leg_probabilities),
        average_brier_score=_average(accumulator.brier_scores),
        average_log_loss=_average(accumulator.log_losses),
        average_calibration_error=_average(accumulator.calibration_errors),
        loss_driver_score=loss_driver_score,
        summary_json=summary,
    )


def _average_odds_product(
    final_answer: HistoricalRecommendationScenarioResult,
) -> float | None:
    if final_answer.option is None:
        return None
    atomic_bets = final_answer.option.selection.evaluation.atomic_bets
    return _average([atomic_bet.odds_product for atomic_bet in atomic_bets])


def _leg_decimal_odds(final_answer: HistoricalRecommendationScenarioResult) -> list[float]:
    if final_answer.option is None:
        return []
    return [
        scored.candidate.decimal_odds
        for scored in final_answer.option.selection.selected_candidates
        if scored.candidate.decimal_odds is not None
    ]


def _leg_probabilities(final_answer: HistoricalRecommendationScenarioResult) -> list[float]:
    if final_answer.option is None:
        return []
    return [
        scored.candidate.probability
        for scored in final_answer.option.selection.selected_candidates
    ]


def _competition_ids(final_answer: HistoricalRecommendationScenarioResult) -> list[str]:
    if final_answer.option is None:
        return ["unknown"]
    competition_ids = sorted(
        {
            str(scored.candidate.metadata_json.get("competition_id"))
            for scored in final_answer.option.selection.selected_candidates
            if scored.candidate.metadata_json.get("competition_id") is not None
        }
    )
    return competition_ids or ["unknown"]


def _market_mix(final_answer: HistoricalRecommendationScenarioResult) -> str:
    if final_answer.option is None:
        return "unknown"
    market_types = sorted(
        {
            scored.candidate.market_type
            for scored in final_answer.option.selection.selected_candidates
        }
    )
    return "+".join(market_types) if market_types else "unknown"


def _band_label(value: float | None, edges: Sequence[float]) -> str:
    if value is None:
        return "unknown"
    sorted_edges = sorted(set(edges))
    if len(sorted_edges) < 2:
        return "all"
    if value < sorted_edges[0]:
        return f"<{sorted_edges[0]:.2f}"
    for lower, upper in zip(sorted_edges, sorted_edges[1:], strict=False):
        if lower <= value < upper:
            return f"{lower:.2f}-{upper:.2f}"
    return f">={sorted_edges[-1]:.2f}"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average(values: Iterable[float]) -> float | None:
    collected = list(values)
    if not collected:
        return None
    return sum(collected) / len(collected)


def _report_key(
    summary: dict[str, object],
    metrics: Sequence[HistoricalFinalAnswerSegmentMetric],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "segments": [
                {
                    "segment_key": metric.segment_key,
                    "sample_size": metric.sample_size,
                    "hit_count": metric.hit_count,
                    "profit_loss": metric.profit_loss,
                }
                for metric in metrics
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_final_answer_segment_audit:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Audit Nutmeg historical final-answer performance by segment."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", action="append", default=[], type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--side", choices=["baseline", "candidate"], default="candidate")
    parser.add_argument("--min-segment-sample-size", type=int, default=2)
    parser.add_argument("--top-segment-limit", type=int, default=12)
    parser.add_argument("--include-interaction-segments", action="store_true")
    parser.add_argument("--pass-types", default=",".join(DEFAULT_AUDIT_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_AUDIT_MODES))
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--no-require-odds", action="store_true")
    parser.add_argument("--candidate-fixture-limit", type=int, default=None)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int, default=None)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--baseline-optimizer-profile",
        choices=["heuristic", "solver"],
        default="heuristic",
    )
    parser.add_argument(
        "--candidate-optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
        )
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    manifest_slices = [
        historical_slice
        for bundle in bundles
        for historical_slice in bundle.slices
    ]
    warnings = [warning for bundle in bundles for warning in bundle.warnings]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *explicit_slices],
        manifest_results=bundles,
        warnings=warnings,
    )


def _manifest_summary(
    bundle: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(bundle.manifest_path),
        "suite_id": bundle.manifest.suite_id,
        "name": bundle.manifest.name,
        "slice_count": len(bundle.slices),
        "warnings": bundle.warnings,
    }


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
