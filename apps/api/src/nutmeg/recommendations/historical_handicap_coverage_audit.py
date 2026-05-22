from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationMarketType,
    RecommendationMode,
    RecommendationStrategy,
)

type HistoricalHandicapCoverageAuditStatus = Literal["generated"]
type HistoricalHandicapCoverageSourceType = Literal["suite_manifest", "slice_paths"]

DEFAULT_HISTORICAL_HANDICAP_COVERAGE_AUDIT_ID = (
    "historical-handicap-coverage-shadow-audit-v3.1"
)
HANDICAP_MARKETS: tuple[RecommendationMarketType, ...] = (
    "cn_handicap_1x2",
    "european_handicap_1x2",
)
HANDICAP_OUTCOMES = {
    "handicap_home_win",
    "handicap_draw",
    "handicap_away_win",
}


class HistoricalHandicapCoverageAuditOptions(BaseModel):
    audit_id: str = DEFAULT_HISTORICAL_HANDICAP_COVERAGE_AUDIT_ID
    baseline_allowed_markets: tuple[RecommendationMarketType, ...] = ("1x2",)
    candidate_allowed_markets: tuple[RecommendationMarketType, ...] = (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
    )
    pass_types: tuple[str, ...] = ("1x1", "2x1", "3x1", "4x1")
    modes: tuple[RecommendationMode, ...] = ("single", "multiple")
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float = Field(default=20.0, gt=0.0)
    min_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_fixture_limit: int | None = Field(default=None, ge=1)
    max_candidates_per_fixture: int = Field(default=3, ge=1, le=8)
    scenario_candidate_fixture_buffer: int | None = Field(default=None, ge=0)
    derive_market_context_signals: bool = False
    top_changed_slice_limit: int = Field(default=20, ge=0, le=200)


class HistoricalHandicapCoverageSource(BaseModel):
    source_id: str
    source_type: HistoricalHandicapCoverageSourceType
    source_path: Path | None = None
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HistoricalHandicapCoverageSourceSummary(BaseModel):
    source_id: str
    source_type: HistoricalHandicapCoverageSourceType
    source_path: Path | None = None
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    complete_1x2_fixture_count: int = Field(ge=0)
    handicap_prediction_count: int = Field(ge=0)
    eligible_handicap_prediction_count: int = Field(ge=0)
    handicap_fixture_count: int = Field(ge=0)
    complete_handicap_fixture_count: int = Field(ge=0)
    complete_handicap_line_count: int = Field(ge=0)
    complete_1x2_coverage: float | None = None
    handicap_fixture_coverage: float | None = None
    complete_handicap_fixture_coverage: float | None = None
    prediction_count_by_market: dict[str, int] = Field(default_factory=dict)
    handicap_prediction_count_by_market: dict[str, int] = Field(default_factory=dict)
    complete_handicap_line_count_by_market: dict[str, int] = Field(default_factory=dict)
    handicap_line_counts: dict[str, int] = Field(default_factory=dict)
    competition_fixture_counts: dict[str, int] = Field(default_factory=dict)
    competition_handicap_fixture_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalHandicapShadowSliceComparison(BaseModel):
    slice_id: str
    competition_id: str
    baseline_final_answer_present: bool
    candidate_final_answer_present: bool
    final_answer_changed: bool
    candidate_uses_handicap: bool
    baseline_actual_hit: bool | None = None
    candidate_actual_hit: bool | None = None
    final_hit_delta_count: int = 0
    baseline_profit_loss: float = 0.0
    candidate_profit_loss: float = 0.0
    profit_loss_delta: float = 0.0
    baseline_total_stake: float = 0.0
    candidate_total_stake: float = 0.0
    baseline_signature: str | None = None
    candidate_signature: str | None = None
    candidate_markets: list[str] = Field(default_factory=list)


class HistoricalHandicapShadowSourceSummary(BaseModel):
    source_id: str
    slice_count: int = Field(ge=0)
    baseline_final_answer_count: int = Field(ge=0)
    candidate_final_answer_count: int = Field(ge=0)
    baseline_final_hit_count: int = Field(ge=0)
    candidate_final_hit_count: int = Field(ge=0)
    final_hit_delta_count: int = 0
    baseline_total_stake: float = Field(ge=0.0)
    candidate_total_stake: float = Field(ge=0.0)
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_delta: float
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    changed_final_answer_count: int = Field(ge=0)
    candidate_handicap_final_answer_count: int = Field(ge=0)
    candidate_handicap_final_answer_hit_count: int = Field(ge=0)
    top_changed_slices: list[HistoricalHandicapShadowSliceComparison] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalHandicapCoverageAuditReport(BaseModel):
    audit_key: str
    audit_id: str
    status: HistoricalHandicapCoverageAuditStatus
    source_count: int = Field(ge=0)
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    sources: list[HistoricalHandicapCoverageSourceSummary] = Field(default_factory=list)
    shadow_summaries: list[HistoricalHandicapShadowSourceSummary] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_handicap_coverage_audit_report(
    sources: Sequence[HistoricalHandicapCoverageSource],
    *,
    options: HistoricalHandicapCoverageAuditOptions | None = None,
) -> HistoricalHandicapCoverageAuditReport:
    resolved_options = options or HistoricalHandicapCoverageAuditOptions()
    source_summaries = [_source_summary(source) for source in sources]
    shadow_summaries = [
        _shadow_summary(source, coverage=coverage, options=resolved_options)
        for source, coverage in zip(sources, source_summaries, strict=True)
    ]
    warnings = _audit_warnings(
        source_summaries,
        shadow_summaries,
    )
    audit_key = _audit_key(source_summaries, shadow_summaries, options=resolved_options)
    summary: dict[str, object] = {
        "calculation_basis": "historical_handicap_coverage_shadow_audit_v3_1",
        "audit_key": audit_key,
        "audit_id": resolved_options.audit_id,
        "status": "generated",
        "source_count": len(source_summaries),
        "slice_count": sum(source.slice_count for source in source_summaries),
        "fixture_count": sum(source.fixture_count for source in source_summaries),
        "handicap_prediction_count": sum(
            source.handicap_prediction_count for source in source_summaries
        ),
        "handicap_fixture_count": sum(
            source.handicap_fixture_count for source in source_summaries
        ),
        "complete_handicap_fixture_count": sum(
            source.complete_handicap_fixture_count for source in source_summaries
        ),
        "changed_final_answer_count": sum(
            shadow.changed_final_answer_count for shadow in shadow_summaries
        ),
        "candidate_handicap_final_answer_count": sum(
            shadow.candidate_handicap_final_answer_count
            for shadow in shadow_summaries
        ),
        "final_hit_delta_count": sum(
            shadow.final_hit_delta_count for shadow in shadow_summaries
        ),
        "profit_loss_delta": sum(
            shadow.profit_loss_delta for shadow in shadow_summaries
        ),
        "warnings": warnings,
    }
    return HistoricalHandicapCoverageAuditReport(
        audit_key=audit_key,
        audit_id=resolved_options.audit_id,
        status="generated",
        source_count=len(source_summaries),
        slice_count=sum(source.slice_count for source in source_summaries),
        fixture_count=sum(source.fixture_count for source in source_summaries),
        sources=source_summaries,
        shadow_summaries=shadow_summaries,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_handicap_coverage_audit_report(
        _sources_from_args(args),
        options=_options_from_args(args),
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


def _source_summary(
    source: HistoricalHandicapCoverageSource,
) -> HistoricalHandicapCoverageSourceSummary:
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in source.slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in source.slices
        for fixture in historical_slice.fixtures
    )
    prediction_count_by_market: Counter[str] = Counter()
    handicap_prediction_count_by_market: Counter[str] = Counter()
    complete_handicap_line_count_by_market: Counter[str] = Counter()
    handicap_line_counts: Counter[str] = Counter()
    competition_fixture_counts: Counter[str] = Counter()
    competition_handicap_fixture_counts: Counter[str] = Counter()
    complete_1x2_fixture_count = 0
    handicap_fixture_count = 0
    complete_handicap_fixture_count = 0
    complete_handicap_line_count = 0
    eligible_handicap_prediction_count = 0

    for historical_slice in source.slices:
        for fixture in historical_slice.fixtures:
            competition_fixture_counts[fixture.competition_id] += 1
            if _has_complete_1x2_market(fixture):
                complete_1x2_fixture_count += 1
            fixture_has_handicap = False
            fixture_complete_handicap = False
            complete_line_keys = _complete_handicap_line_keys(fixture)
            complete_handicap_line_count += len(complete_line_keys)
            for market_type, _line, _side in complete_line_keys:
                complete_handicap_line_count_by_market[market_type] += 1
            for prediction in fixture.predictions:
                prediction_count_by_market[prediction.market_type] += 1
                if prediction.market_type not in HANDICAP_MARKETS:
                    continue
                fixture_has_handicap = True
                handicap_prediction_count_by_market[prediction.market_type] += 1
                line_key = _handicap_line_key(
                    prediction.market_type,
                    prediction.line,
                    prediction.side,
                )
                handicap_line_counts[line_key] += 1
                if _eligible_handicap_prediction(prediction):
                    eligible_handicap_prediction_count += 1
            if fixture_has_handicap:
                handicap_fixture_count += 1
                competition_handicap_fixture_counts[fixture.competition_id] += 1
            if complete_line_keys:
                fixture_complete_handicap = True
            if fixture_complete_handicap:
                complete_handicap_fixture_count += 1

    warnings = _source_coverage_warnings(
        source,
        fixture_count=fixture_count,
        handicap_prediction_count=sum(handicap_prediction_count_by_market.values()),
        complete_handicap_fixture_count=complete_handicap_fixture_count,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_handicap_coverage_source_summary_v3_1",
        "source_id": source.source_id,
        "source_type": source.source_type,
        "source_path": str(source.source_path) if source.source_path is not None else None,
        "slice_count": len(source.slices),
        "fixture_count": fixture_count,
        "handicap_prediction_count": sum(handicap_prediction_count_by_market.values()),
        "handicap_fixture_coverage": _ratio(handicap_fixture_count, fixture_count),
        "complete_handicap_fixture_coverage": _ratio(
            complete_handicap_fixture_count,
            fixture_count,
        ),
        "warnings": warnings,
    }
    return HistoricalHandicapCoverageSourceSummary(
        source_id=source.source_id,
        source_type=source.source_type,
        source_path=source.source_path,
        slice_count=len(source.slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        complete_1x2_fixture_count=complete_1x2_fixture_count,
        handicap_prediction_count=sum(handicap_prediction_count_by_market.values()),
        eligible_handicap_prediction_count=eligible_handicap_prediction_count,
        handicap_fixture_count=handicap_fixture_count,
        complete_handicap_fixture_count=complete_handicap_fixture_count,
        complete_handicap_line_count=complete_handicap_line_count,
        complete_1x2_coverage=_ratio(complete_1x2_fixture_count, fixture_count),
        handicap_fixture_coverage=_ratio(handicap_fixture_count, fixture_count),
        complete_handicap_fixture_coverage=_ratio(
            complete_handicap_fixture_count,
            fixture_count,
        ),
        prediction_count_by_market=dict(sorted(prediction_count_by_market.items())),
        handicap_prediction_count_by_market=dict(
            sorted(handicap_prediction_count_by_market.items())
        ),
        complete_handicap_line_count_by_market=dict(
            sorted(complete_handicap_line_count_by_market.items())
        ),
        handicap_line_counts=dict(sorted(handicap_line_counts.items())),
        competition_fixture_counts=dict(sorted(competition_fixture_counts.items())),
        competition_handicap_fixture_counts=dict(
            sorted(competition_handicap_fixture_counts.items())
        ),
        warnings=warnings,
        summary_json=summary,
    )


def _shadow_summary(
    source: HistoricalHandicapCoverageSource,
    *,
    coverage: HistoricalHandicapCoverageSourceSummary,
    options: HistoricalHandicapCoverageAuditOptions,
) -> HistoricalHandicapShadowSourceSummary:
    baseline_options = _backtest_options(
        options,
        allowed_markets=options.baseline_allowed_markets,
    )
    candidate_options = _backtest_options(
        options,
        allowed_markets=options.candidate_allowed_markets,
    )
    comparisons: list[HistoricalHandicapShadowSliceComparison] = []
    for historical_slice in source.slices:
        baseline = run_historical_recommendation_backtest(
            historical_slice,
            options=baseline_options,
        )
        candidate = run_historical_recommendation_backtest(
            historical_slice,
            options=candidate_options,
        )
        comparisons.append(_slice_shadow_comparison(historical_slice, baseline, candidate))

    baseline_total_stake = sum(item.baseline_total_stake for item in comparisons)
    candidate_total_stake = sum(item.candidate_total_stake for item in comparisons)
    baseline_profit_loss = sum(item.baseline_profit_loss for item in comparisons)
    candidate_profit_loss = sum(item.candidate_profit_loss for item in comparisons)
    changed = [item for item in comparisons if item.final_answer_changed]
    handicap_answers = [item for item in comparisons if item.candidate_uses_handicap]
    warnings = _shadow_warnings(
        coverage,
        changed_final_answer_count=len(changed),
        candidate_handicap_final_answer_count=len(handicap_answers),
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_handicap_shadow_backtest_summary_v3_1",
        "source_id": source.source_id,
        "slice_count": len(source.slices),
        "baseline_allowed_markets": list(options.baseline_allowed_markets),
        "candidate_allowed_markets": list(options.candidate_allowed_markets),
        "changed_final_answer_count": len(changed),
        "candidate_handicap_final_answer_count": len(handicap_answers),
        "final_hit_delta_count": sum(item.final_hit_delta_count for item in comparisons),
        "profit_loss_delta": candidate_profit_loss - baseline_profit_loss,
        "warnings": warnings,
    }
    return HistoricalHandicapShadowSourceSummary(
        source_id=source.source_id,
        slice_count=len(source.slices),
        baseline_final_answer_count=sum(
            1 for item in comparisons if item.baseline_final_answer_present
        ),
        candidate_final_answer_count=sum(
            1 for item in comparisons if item.candidate_final_answer_present
        ),
        baseline_final_hit_count=sum(
            1 for item in comparisons if item.baseline_actual_hit is True
        ),
        candidate_final_hit_count=sum(
            1 for item in comparisons if item.candidate_actual_hit is True
        ),
        final_hit_delta_count=sum(item.final_hit_delta_count for item in comparisons),
        baseline_total_stake=baseline_total_stake,
        candidate_total_stake=candidate_total_stake,
        baseline_profit_loss=baseline_profit_loss,
        candidate_profit_loss=candidate_profit_loss,
        profit_loss_delta=candidate_profit_loss - baseline_profit_loss,
        baseline_roi=_float_ratio(baseline_profit_loss, baseline_total_stake),
        candidate_roi=_float_ratio(candidate_profit_loss, candidate_total_stake),
        roi_delta=_optional_delta(
            _float_ratio(candidate_profit_loss, candidate_total_stake),
            _float_ratio(baseline_profit_loss, baseline_total_stake),
        ),
        changed_final_answer_count=len(changed),
        candidate_handicap_final_answer_count=len(handicap_answers),
        candidate_handicap_final_answer_hit_count=sum(
            1 for item in handicap_answers if item.candidate_actual_hit is True
        ),
        top_changed_slices=[
            *changed[: options.top_changed_slice_limit],
            *[
                item
                for item in handicap_answers
                if item not in changed
            ][: max(0, options.top_changed_slice_limit - len(changed))],
        ],
        warnings=warnings,
        summary_json=summary,
    )


def _slice_shadow_comparison(
    historical_slice: HistoricalRecommendationSlice,
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
) -> HistoricalHandicapShadowSliceComparison:
    baseline_signature = _final_answer_signature(baseline)
    candidate_signature = _final_answer_signature(candidate)
    baseline_hit = _final_answer_hit(baseline)
    candidate_hit = _final_answer_hit(candidate)
    candidate_markets = _final_answer_markets(candidate)
    return HistoricalHandicapShadowSliceComparison(
        slice_id=historical_slice.metadata.slice_id,
        competition_id=historical_slice.metadata.competition_id,
        baseline_final_answer_present=baseline.final_answer is not None,
        candidate_final_answer_present=candidate.final_answer is not None,
        final_answer_changed=baseline_signature != candidate_signature,
        candidate_uses_handicap=any(market in HANDICAP_MARKETS for market in candidate_markets),
        baseline_actual_hit=baseline_hit,
        candidate_actual_hit=candidate_hit,
        final_hit_delta_count=int(candidate_hit is True) - int(baseline_hit is True),
        baseline_profit_loss=baseline.profit_loss,
        candidate_profit_loss=candidate.profit_loss,
        profit_loss_delta=candidate.profit_loss - baseline.profit_loss,
        baseline_total_stake=baseline.total_stake,
        candidate_total_stake=candidate.total_stake,
        baseline_signature=baseline_signature,
        candidate_signature=candidate_signature,
        candidate_markets=sorted(candidate_markets),
    )


def _backtest_options(
    options: HistoricalHandicapCoverageAuditOptions,
    *,
    allowed_markets: tuple[RecommendationMarketType, ...],
) -> HistoricalRecommendationBacktestOptions:
    return HistoricalRecommendationBacktestOptions(
        pass_types=options.pass_types,
        modes=options.modes,
        strategy=options.strategy,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        min_probability=options.min_probability,
        min_data_quality_score=options.min_data_quality_score,
        allowed_markets=allowed_markets,
        candidate_fixture_limit=options.candidate_fixture_limit,
        max_candidates_per_fixture=options.max_candidates_per_fixture,
        scenario_candidate_fixture_buffer=options.scenario_candidate_fixture_buffer,
        derive_market_context_signals=options.derive_market_context_signals,
        optimizer_profile="solver",
    )


def _final_answer_signature(result: HistoricalRecommendationBacktestResult) -> str | None:
    final_answer = result.final_answer
    if final_answer is None or final_answer.option is None:
        return None
    parts: list[str] = []
    for item in final_answer.option.selection.selected_candidates:
        candidate = item.candidate
        parts.append(
            ":".join(
                [
                    candidate.fixture_id,
                    candidate.market_type,
                    _line_text(candidate.line),
                    candidate.side or "",
                    candidate.outcome,
                ]
            )
        )
    return "|".join(sorted(parts))


def _final_answer_markets(
    result: HistoricalRecommendationBacktestResult,
) -> set[RecommendationMarketType]:
    final_answer = result.final_answer
    if final_answer is None or final_answer.option is None:
        return set()
    return {
        item.candidate.market_type
        for item in final_answer.option.selection.selected_candidates
    }


def _final_answer_hit(result: HistoricalRecommendationBacktestResult) -> bool | None:
    if result.final_answer is None:
        return None
    return result.final_answer.actual_hit


def _has_complete_1x2_market(fixture: HistoricalFixture) -> bool:
    outcomes = {
        prediction.outcome
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
    }
    return {"home_win", "draw", "away_win"}.issubset(outcomes)


def _complete_handicap_line_keys(
    fixture: HistoricalFixture,
) -> set[tuple[RecommendationMarketType, float | None, str | None]]:
    grouped: dict[tuple[RecommendationMarketType, float | None, str | None], set[str]] = {}
    for prediction in fixture.predictions:
        if prediction.market_type not in HANDICAP_MARKETS:
            continue
        key = (prediction.market_type, prediction.line, prediction.side)
        grouped.setdefault(key, set()).add(prediction.outcome)
    return {
        key
        for key, outcomes in grouped.items()
        if HANDICAP_OUTCOMES.issubset(outcomes)
    }


def _eligible_handicap_prediction(prediction: HistoricalMarketPrediction) -> bool:
    return (
        prediction.market_type in HANDICAP_MARKETS
        and prediction.outcome in HANDICAP_OUTCOMES
        and _integer_line(prediction.line)
        and prediction.decimal_odds > 1.0
    )


def _integer_line(line: object) -> bool:
    if not isinstance(line, int | float) or isinstance(line, bool):
        return False
    return abs(float(line) - round(float(line))) <= 1e-9


def _handicap_line_key(
    market_type: str,
    line: float | None,
    side: str | None,
) -> str:
    return f"{market_type}:{_line_text(line)}:{side or ''}"


def _line_text(line: float | None) -> str:
    if line is None:
        return "none"
    return f"{line:g}"


def _source_coverage_warnings(
    source: HistoricalHandicapCoverageSource,
    *,
    fixture_count: int,
    handicap_prediction_count: int,
    complete_handicap_fixture_count: int,
) -> list[str]:
    warnings = list(source.warnings)
    if fixture_count <= 0:
        warnings.append("handicap_coverage:source_has_no_fixtures")
    if handicap_prediction_count <= 0:
        warnings.append("handicap_coverage:no_handicap_predictions")
    if complete_handicap_fixture_count <= 0:
        warnings.append("handicap_coverage:no_complete_handicap_markets")
    return _dedupe(warnings)


def _shadow_warnings(
    coverage: HistoricalHandicapCoverageSourceSummary,
    *,
    changed_final_answer_count: int,
    candidate_handicap_final_answer_count: int,
) -> list[str]:
    warnings: list[str] = []
    if coverage.handicap_prediction_count <= 0:
        warnings.append("handicap_shadow:no_handicap_candidates_available")
    if changed_final_answer_count <= 0:
        warnings.append("handicap_shadow:no_final_answer_changes")
    if candidate_handicap_final_answer_count <= 0:
        warnings.append("handicap_shadow:no_handicap_final_answers")
    return warnings


def _audit_warnings(
    source_summaries: Sequence[HistoricalHandicapCoverageSourceSummary],
    shadow_summaries: Sequence[HistoricalHandicapShadowSourceSummary],
) -> list[str]:
    warnings: list[str] = []
    if not source_summaries:
        warnings.append("handicap_coverage:no_sources")
    for source in source_summaries:
        warnings.extend(source.warnings)
    for shadow in shadow_summaries:
        warnings.extend(shadow.warnings)
    return _dedupe(warnings)


def _sources_from_args(args: Namespace) -> list[HistoricalHandicapCoverageSource]:
    sources: list[HistoricalHandicapCoverageSource] = []
    for manifest_path in args.suite_manifest:
        bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)
        sources.append(_source_from_manifest(bundle))
    if args.slice_path:
        slices = [
            load_historical_recommendation_slice(slice_path)
            for slice_path in args.slice_path
        ]
        source_id = "standalone_slices"
        if len(slices) == 1:
            source_id = slices[0].metadata.slice_id
        sources.append(
            HistoricalHandicapCoverageSource(
                source_id=source_id,
                source_type="slice_paths",
                slices=slices,
            )
        )
    return sources


def _source_from_manifest(
    bundle: HistoricalRecommendationSuiteManifestLoadResult,
) -> HistoricalHandicapCoverageSource:
    return HistoricalHandicapCoverageSource(
        source_id=bundle.manifest.suite_id,
        source_type="suite_manifest",
        source_path=bundle.manifest_path,
        slices=bundle.slices,
        warnings=bundle.warnings,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Audit handicap candidate coverage and shadow final-answer impact."
    )
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--slice-path", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--audit-id", default=DEFAULT_HISTORICAL_HANDICAP_COVERAGE_AUDIT_ID)
    parser.add_argument("--baseline-allowed-markets", default="1x2")
    parser.add_argument(
        "--candidate-allowed-markets",
        default="1x2,cn_handicap_1x2,european_handicap_1x2",
    )
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--top-changed-slice-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.suite_manifest and not args.slice_path:
        parser.error("provide at least one --suite-manifest or --slice-path")
    return args


def _options_from_args(args: Namespace) -> HistoricalHandicapCoverageAuditOptions:
    return HistoricalHandicapCoverageAuditOptions(
        audit_id=args.audit_id,
        baseline_allowed_markets=_market_tuple(args.baseline_allowed_markets),
        candidate_allowed_markets=_market_tuple(args.candidate_allowed_markets),
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        strategy=cast(RecommendationStrategy, args.strategy),
        unit_stake=args.unit_stake,
        max_budget=args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        candidate_fixture_limit=args.candidate_fixture_limit,
        max_candidates_per_fixture=args.max_candidates_per_fixture,
        scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
        derive_market_context_signals=args.derive_market_context_signals,
        top_changed_slice_limit=args.top_changed_slice_limit,
    )


def _market_tuple(value: str) -> tuple[RecommendationMarketType, ...]:
    markets: list[RecommendationMarketType] = []
    valid = {"1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"}
    for item in _csv(value):
        if item not in valid:
            raise ValueError(f"unsupported recommendation market type: {item}")
        markets.append(cast(RecommendationMarketType, item))
    return tuple(markets)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _float_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _audit_key(
    source_summaries: Sequence[HistoricalHandicapCoverageSourceSummary],
    shadow_summaries: Sequence[HistoricalHandicapShadowSourceSummary],
    *,
    options: HistoricalHandicapCoverageAuditOptions,
) -> str:
    payload = dumps(
        {
            "audit_id": options.audit_id,
            "baseline_allowed_markets": options.baseline_allowed_markets,
            "candidate_allowed_markets": options.candidate_allowed_markets,
            "pass_types": options.pass_types,
            "modes": options.modes,
            "source_ids": [source.source_id for source in source_summaries],
            "coverage": [source.summary_json for source in source_summaries],
            "shadow": [shadow.summary_json for shadow in shadow_summaries],
        },
        sort_keys=True,
    )
    return f"historical_handicap_coverage_shadow:{sha256(payload.encode()).hexdigest()[:16]}"
