from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type CompetitionProfileEvidenceMetricSource = Literal["scenario", "final_answer"]
type CompetitionProfileEvidenceDecisionStatus = Literal[
    "candidate_accepted",
    "baseline_retained",
    "insufficient_baseline",
]


class HistoricalCompetitionProfileEvidenceOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_scenario_keys_by_competition: dict[str, str] = Field(default_factory=dict)
    min_sample_size: int = Field(default=3, ge=1)
    min_hit_count_delta: int = Field(default=0, ge=0)
    min_roi_delta: float = Field(default=0.0, ge=0.0)
    min_profit_loss_delta: float = Field(default=0.0, ge=0.0)
    require_full_candidate_coverage: bool = True
    suggested_score_adjustment: float = Field(default=0.10, ge=0.0, le=0.25)


class HistoricalCompetitionProfileScenarioMetric(BaseModel):
    metric_key: str
    competition_id: str
    scenario_key: str
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    source: CompetitionProfileEvidenceMetricSource
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(ge=0.0)
    actual_return: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    final_answer_count: int = Field(default=0, ge=0)


class HistoricalCompetitionProfileEvidenceDecision(BaseModel):
    competition_id: str
    status: CompetitionProfileEvidenceDecisionStatus
    baseline_metric: HistoricalCompetitionProfileScenarioMetric | None = None
    selected_metric: HistoricalCompetitionProfileScenarioMetric | None = None
    rejected_top_roi_metric: HistoricalCompetitionProfileScenarioMetric | None = None
    recommended_scenario_key: str | None = None
    suggested_score_adjustment: float | None = None
    hit_count_delta: int | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    reason_codes: list[str] = Field(default_factory=list)


class HistoricalCompetitionProfileEvidenceReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    backtest_count: int = Field(ge=0)
    scenario_metrics: list[HistoricalCompetitionProfileScenarioMetric] = Field(
        default_factory=list
    )
    baseline_metrics: list[HistoricalCompetitionProfileScenarioMetric] = Field(
        default_factory=list
    )
    decisions: list[HistoricalCompetitionProfileEvidenceDecision] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass
class _MetricAccumulator:
    competition_id: str
    scenario_key: str
    pass_type: str | None
    mode: RecommendationMode | None
    source: CompetitionProfileEvidenceMetricSource
    sample_size: int = 0
    hit_count: int = 0
    total_stake: float = 0.0
    actual_return: float = 0.0
    brier_weighted_sum: float = 0.0
    brier_weight: int = 0
    log_loss_weighted_sum: float = 0.0
    log_loss_weight: int = 0
    calibration_weighted_sum: float = 0.0
    calibration_weight: int = 0
    scenario_counts: Counter[str] = field(default_factory=Counter)
    final_answer_count: int = 0

    def add(self, result: HistoricalRecommendationScenarioResult) -> None:
        self.sample_size += 1
        self.hit_count += int(result.actual_hit)
        self.total_stake += result.total_stake
        self.actual_return += result.actual_return
        self.scenario_counts[result.scenario.scenario_key] += 1
        if self.source == "final_answer":
            self.final_answer_count += 1
        if result.brier_score is not None:
            self.brier_weight += 1
            self.brier_weighted_sum += result.brier_score
        if result.log_loss is not None:
            self.log_loss_weight += 1
            self.log_loss_weighted_sum += result.log_loss
        if result.calibration_error is not None:
            self.calibration_weight += 1
            self.calibration_weighted_sum += result.calibration_error

    def metric(self) -> HistoricalCompetitionProfileScenarioMetric:
        profit_loss = self.actual_return - self.total_stake
        return HistoricalCompetitionProfileScenarioMetric(
            metric_key=_metric_key(
                self.competition_id,
                self.scenario_key,
                source=self.source,
            ),
            competition_id=self.competition_id,
            scenario_key=self.scenario_key,
            pass_type=self.pass_type,
            mode=self.mode,
            source=self.source,
            sample_size=self.sample_size,
            hit_count=self.hit_count,
            hit_rate=_ratio(self.hit_count, self.sample_size),
            total_stake=self.total_stake,
            actual_return=self.actual_return,
            profit_loss=profit_loss,
            roi=profit_loss / self.total_stake if self.total_stake > 0 else None,
            brier_score=_weighted_mean(self.brier_weighted_sum, self.brier_weight),
            log_loss=_weighted_mean(self.log_loss_weighted_sum, self.log_loss_weight),
            mean_calibration_error=_weighted_mean(
                self.calibration_weighted_sum,
                self.calibration_weight,
            ),
            scenario_counts=dict(sorted(self.scenario_counts.items())),
            final_answer_count=self.final_answer_count,
        )


def build_historical_competition_profile_evidence_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalCompetitionProfileEvidenceOptions | None = None,
) -> HistoricalCompetitionProfileEvidenceReport:
    resolved_options = options or HistoricalCompetitionProfileEvidenceOptions()
    scenario_accumulators: dict[tuple[str, str], _MetricAccumulator] = {}
    final_answer_accumulators: dict[str, _MetricAccumulator] = {}
    warnings: list[str] = []

    for historical_slice in historical_slices:
        backtest = run_historical_recommendation_backtest(
            historical_slice,
            options=resolved_options.backtest_options,
        )
        competition_id = historical_slice.metadata.competition_id
        warnings.extend(backtest.warnings)
        if backtest.final_answer is not None:
            final_answer_accumulators.setdefault(
                competition_id,
                _MetricAccumulator(
                    competition_id=competition_id,
                    scenario_key="current_final_answer",
                    pass_type=None,
                    mode=None,
                    source="final_answer",
                ),
            ).add(backtest.final_answer)
        for scenario_result in backtest.scenarios:
            if scenario_result.status != "completed":
                continue
            key = (competition_id, scenario_result.scenario.scenario_key)
            scenario_accumulators.setdefault(
                key,
                _MetricAccumulator(
                    competition_id=competition_id,
                    scenario_key=scenario_result.scenario.scenario_key,
                    pass_type=scenario_result.scenario.pass_type,
                    mode=scenario_result.scenario.mode,
                    source="scenario",
                ),
            ).add(scenario_result)

    scenario_metrics = sorted(
        (accumulator.metric() for accumulator in scenario_accumulators.values()),
        key=lambda metric: (metric.competition_id, metric.scenario_key),
    )
    baseline_metrics = sorted(
        (accumulator.metric() for accumulator in final_answer_accumulators.values()),
        key=lambda metric: metric.competition_id,
    )
    decisions = _profile_decisions(
        scenario_metrics,
        baseline_metrics=baseline_metrics,
        options=resolved_options,
    )
    competitions = sorted(
        {
            historical_slice.metadata.competition_id
            for historical_slice in historical_slices
        }
    )
    summary = _report_summary(
        historical_slices,
        scenario_metrics=scenario_metrics,
        baseline_metrics=baseline_metrics,
        decisions=decisions,
        warnings=warnings,
        options=resolved_options,
    )
    report_key = _report_key(summary, historical_slices)
    return HistoricalCompetitionProfileEvidenceReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        competition_count=len(competitions),
        backtest_count=len(historical_slices),
        scenario_metrics=scenario_metrics,
        baseline_metrics=baseline_metrics,
        decisions=decisions,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_competition_profile_evidence_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
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


def _profile_decisions(
    scenario_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    *,
    baseline_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    options: HistoricalCompetitionProfileEvidenceOptions,
) -> list[HistoricalCompetitionProfileEvidenceDecision]:
    scenario_metrics_by_competition: dict[
        str,
        list[HistoricalCompetitionProfileScenarioMetric],
    ] = defaultdict(list)
    for metric in scenario_metrics:
        scenario_metrics_by_competition[metric.competition_id].append(metric)
    final_baseline_by_competition = {
        metric.competition_id: metric for metric in baseline_metrics
    }
    competition_ids = sorted(
        set(scenario_metrics_by_competition) | set(final_baseline_by_competition)
    )
    return [
        _profile_decision(
            competition_id,
            scenario_metrics=scenario_metrics_by_competition[competition_id],
            final_baseline=final_baseline_by_competition.get(competition_id),
            options=options,
        )
        for competition_id in competition_ids
    ]


def _profile_decision(
    competition_id: str,
    *,
    scenario_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    final_baseline: HistoricalCompetitionProfileScenarioMetric | None,
    options: HistoricalCompetitionProfileEvidenceOptions,
) -> HistoricalCompetitionProfileEvidenceDecision:
    baseline = _baseline_metric(
        competition_id,
        scenario_metrics=scenario_metrics,
        final_baseline=final_baseline,
        options=options,
    )
    if baseline is None:
        return HistoricalCompetitionProfileEvidenceDecision(
            competition_id=competition_id,
            status="insufficient_baseline",
            reason_codes=["competition_profile_evidence:no_baseline_metric"],
        )
    if baseline.sample_size < options.min_sample_size:
        return HistoricalCompetitionProfileEvidenceDecision(
            competition_id=competition_id,
            status="insufficient_baseline",
            baseline_metric=baseline,
            reason_codes=["competition_profile_evidence:baseline_sample_too_small"],
        )

    baseline_equivalent_keys = _baseline_equivalent_scenario_keys(baseline)
    candidates = [
        metric
        for metric in scenario_metrics
        if metric.scenario_key not in baseline_equivalent_keys
    ]
    accepted_candidates = [
        metric
        for metric in candidates
        if _candidate_preserves_accuracy_and_improves_return(
            metric,
            baseline=baseline,
            options=options,
        )
    ]
    rejected_top_roi_metric = _top_roi_metric(candidates)
    if accepted_candidates:
        selected = sorted(
            accepted_candidates,
            key=lambda metric: _accepted_candidate_sort_key(metric, baseline=baseline),
            reverse=True,
        )[0]
        return HistoricalCompetitionProfileEvidenceDecision(
            competition_id=competition_id,
            status="candidate_accepted",
            baseline_metric=baseline,
            selected_metric=selected,
            rejected_top_roi_metric=(
                rejected_top_roi_metric
                if rejected_top_roi_metric is not None
                and rejected_top_roi_metric.scenario_key != selected.scenario_key
                else None
            ),
            recommended_scenario_key=selected.scenario_key,
            suggested_score_adjustment=options.suggested_score_adjustment,
            hit_count_delta=selected.hit_count - baseline.hit_count,
            roi_delta=_optional_delta(selected.roi, baseline.roi),
            profit_loss_delta=selected.profit_loss - baseline.profit_loss,
            reason_codes=[
                "competition_profile_evidence:hit_count_preserved",
                "competition_profile_evidence:roi_improved",
                "competition_profile_evidence:profit_loss_improved",
            ],
        )

    reason_codes = ["competition_profile_evidence:baseline_retained"]
    if rejected_top_roi_metric is None:
        reason_codes.append("competition_profile_evidence:no_replacement_candidate")
    else:
        reason_codes.extend(
            _rejection_reason_codes(
                rejected_top_roi_metric,
                baseline=baseline,
                options=options,
                prefix="competition_profile_evidence:top_roi_candidate",
            )
        )
    return HistoricalCompetitionProfileEvidenceDecision(
        competition_id=competition_id,
        status="baseline_retained",
        baseline_metric=baseline,
        selected_metric=baseline,
        rejected_top_roi_metric=rejected_top_roi_metric,
        recommended_scenario_key=_dominant_scenario_key(baseline),
        hit_count_delta=0,
        roi_delta=0.0,
        profit_loss_delta=0.0,
        reason_codes=reason_codes,
    )


def _baseline_metric(
    competition_id: str,
    *,
    scenario_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    final_baseline: HistoricalCompetitionProfileScenarioMetric | None,
    options: HistoricalCompetitionProfileEvidenceOptions,
) -> HistoricalCompetitionProfileScenarioMetric | None:
    configured_scenario_key = options.baseline_scenario_keys_by_competition.get(
        competition_id
    )
    if configured_scenario_key is None:
        return final_baseline
    for metric in scenario_metrics:
        if metric.scenario_key == configured_scenario_key:
            return metric
    return None


def _candidate_preserves_accuracy_and_improves_return(
    metric: HistoricalCompetitionProfileScenarioMetric,
    *,
    baseline: HistoricalCompetitionProfileScenarioMetric,
    options: HistoricalCompetitionProfileEvidenceOptions,
) -> bool:
    if metric.sample_size < options.min_sample_size:
        return False
    if (
        options.require_full_candidate_coverage
        and metric.sample_size != baseline.sample_size
    ):
        return False
    if metric.hit_count - baseline.hit_count < options.min_hit_count_delta:
        return False
    roi_delta = _optional_delta(metric.roi, baseline.roi)
    if roi_delta is None or roi_delta <= options.min_roi_delta:
        return False
    return metric.profit_loss - baseline.profit_loss > options.min_profit_loss_delta


def _rejection_reason_codes(
    metric: HistoricalCompetitionProfileScenarioMetric,
    *,
    baseline: HistoricalCompetitionProfileScenarioMetric,
    options: HistoricalCompetitionProfileEvidenceOptions,
    prefix: str,
) -> list[str]:
    reason_codes: list[str] = []
    if metric.sample_size < options.min_sample_size:
        reason_codes.append(f"{prefix}_sample_too_small")
    if (
        options.require_full_candidate_coverage
        and metric.sample_size != baseline.sample_size
    ):
        reason_codes.append(f"{prefix}_partial_coverage")
    if metric.hit_count - baseline.hit_count < options.min_hit_count_delta:
        reason_codes.append(f"{prefix}_reduced_hit_count")
    roi_delta = _optional_delta(metric.roi, baseline.roi)
    if roi_delta is None or roi_delta <= options.min_roi_delta:
        reason_codes.append(f"{prefix}_roi_not_improved")
    if metric.profit_loss - baseline.profit_loss <= options.min_profit_loss_delta:
        reason_codes.append(f"{prefix}_profit_loss_not_improved")
    return reason_codes


def _accepted_candidate_sort_key(
    metric: HistoricalCompetitionProfileScenarioMetric,
    *,
    baseline: HistoricalCompetitionProfileScenarioMetric,
) -> tuple[int, float, float, float, int, str]:
    return (
        metric.hit_count - baseline.hit_count,
        _optional_delta(metric.roi, baseline.roi) or 0.0,
        metric.profit_loss - baseline.profit_loss,
        metric.hit_rate or 0.0,
        metric.sample_size,
        metric.scenario_key,
    )


def _top_roi_metric(
    metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
) -> HistoricalCompetitionProfileScenarioMetric | None:
    if not metrics:
        return None
    return sorted(
        metrics,
        key=lambda metric: (
            metric.roi if metric.roi is not None else -999999.0,
            metric.profit_loss,
            metric.hit_count,
            metric.scenario_key,
        ),
        reverse=True,
    )[0]


def _baseline_equivalent_scenario_keys(
    baseline: HistoricalCompetitionProfileScenarioMetric,
) -> set[str]:
    if baseline.source == "scenario":
        return {baseline.scenario_key}
    if len(baseline.scenario_counts) == 1:
        return set(baseline.scenario_counts)
    return set()


def _dominant_scenario_key(
    metric: HistoricalCompetitionProfileScenarioMetric,
) -> str:
    if not metric.scenario_counts:
        return metric.scenario_key
    return sorted(
        metric.scenario_counts.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )[0][0]


def _report_summary(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    scenario_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    baseline_metrics: Sequence[HistoricalCompetitionProfileScenarioMetric],
    decisions: Sequence[HistoricalCompetitionProfileEvidenceDecision],
    warnings: Sequence[str],
    options: HistoricalCompetitionProfileEvidenceOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_competition_profile_evidence_v3_1",
        "slice_count": len(historical_slices),
        "competition_count": len({item.metadata.competition_id for item in historical_slices}),
        "scenario_metric_count": len(scenario_metrics),
        "baseline_metric_count": len(baseline_metrics),
        "accepted_count": sum(
            1 for decision in decisions if decision.status == "candidate_accepted"
        ),
        "retained_count": sum(
            1 for decision in decisions if decision.status == "baseline_retained"
        ),
        "insufficient_baseline_count": sum(
            1
            for decision in decisions
            if decision.status == "insufficient_baseline"
        ),
        "accepted_profile_adjustments": {
            decision.competition_id: {
                "scenario_key": decision.recommended_scenario_key,
                "suggested_score_adjustment": decision.suggested_score_adjustment,
            }
            for decision in decisions
            if decision.status == "candidate_accepted"
        },
        "negative_baseline_roi_competitions": [
            metric.competition_id
            for metric in baseline_metrics
            if metric.roi is not None and metric.roi < 0.0
        ],
        "pass_types": list(options.backtest_options.pass_types),
        "modes": list(options.backtest_options.modes),
        "optimizer_profile": options.backtest_options.optimizer_profile,
        "unit_stake": options.backtest_options.unit_stake,
        "max_budget": options.backtest_options.max_budget,
        "min_sample_size": options.min_sample_size,
        "min_hit_count_delta": options.min_hit_count_delta,
        "min_roi_delta": options.min_roi_delta,
        "min_profit_loss_delta": options.min_profit_loss_delta,
        "require_full_candidate_coverage": options.require_full_candidate_coverage,
        "baseline_scenario_keys_by_competition": (
            options.baseline_scenario_keys_by_competition
        ),
        "warning_count": len(warnings),
        "warning_counts": dict(sorted(Counter(warnings).items())),
        "warnings": list(warnings),
    }


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "slice_ids": [
                    historical_slice.metadata.slice_id
                    for historical_slice in historical_slices
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_competition_profile_evidence:{digest}"


def _metric_key(
    competition_id: str,
    scenario_key: str,
    *,
    source: CompetitionProfileEvidenceMetricSource,
) -> str:
    return f"{source}:{competition_id}:{scenario_key}"


def _weighted_mean(weighted_sum: float, weight: int) -> float | None:
    return weighted_sum / weight if weight > 0 else None


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Build evidence for league-specific final-answer profile updates."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_HISTORICAL_BACKTEST_MODES))
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
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--short-price-negative-edge-guardrail", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--short-price-negative-edge-min-probability",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--short-price-negative-edge-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument("--short-price-negative-edge-soft-penalty", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-strength",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-competitions",
        default="",
    )
    parser.add_argument("--baseline-scenario", action="append", default=[])
    parser.add_argument("--min-sample-size", type=int, default=3)
    parser.add_argument("--min-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--allow-partial-candidate-coverage", action="store_true")
    parser.add_argument("--suggested-score-adjustment", type=float, default=0.10)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalCompetitionProfileEvidenceOptions:
    return HistoricalCompetitionProfileEvidenceOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=_csv_tuple(args.pass_types),
            modes=tuple(
                cast(RecommendationMode, mode)
                for mode in _csv_tuple(args.modes)
            ),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            optimizer_profile=cast(
                HistoricalOptimizerProfile,
                args.optimizer_profile,
            ),
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
            short_price_negative_edge_guardrail=(
                args.short_price_negative_edge_guardrail
            ),
            short_price_negative_edge_max_decimal_odds=(
                args.short_price_negative_edge_max_decimal_odds
            ),
            short_price_negative_edge_min_probability=(
                args.short_price_negative_edge_min_probability
            ),
            short_price_negative_edge_max_model_edge=(
                args.short_price_negative_edge_max_model_edge
            ),
            short_price_negative_edge_soft_penalty=(
                args.short_price_negative_edge_soft_penalty
            ),
            short_price_negative_edge_soft_penalty_strength=(
                args.short_price_negative_edge_soft_penalty_strength
            ),
            short_price_negative_edge_soft_penalty_competition_ids=_csv_tuple(
                args.short_price_negative_edge_soft_penalty_competitions
            ),
        ),
        baseline_scenario_keys_by_competition=_baseline_scenarios_from_args(
            args.baseline_scenario
        ),
        min_sample_size=args.min_sample_size,
        min_hit_count_delta=args.min_hit_count_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        require_full_candidate_coverage=not args.allow_partial_candidate_coverage,
        suggested_score_adjustment=args.suggested_score_adjustment,
    )


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _baseline_scenarios_from_args(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        competition_id, separator, scenario_key = value.partition("=")
        if not separator or not competition_id.strip() or not scenario_key.strip():
            raise ValueError(
                "--baseline-scenario must use COMPETITION_ID=scenario_key format"
            )
        result[competition_id.strip()] = scenario_key.strip()
    return result


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            resolved_slice_paths=list(args.slice_paths),
            slices=explicit_slices,
        )
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    return _LoadedHistoricalSlices(
        slices=[*bundle.slices, *explicit_slices],
        resolved_slice_paths=[*bundle.resolved_slice_paths, *args.slice_paths],
        manifest_result=bundle,
        warnings=bundle.warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }
