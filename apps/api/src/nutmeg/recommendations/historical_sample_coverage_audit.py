from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_feature_completeness import (
    HistoricalFeatureCompletenessOptions,
    evaluate_historical_feature_completeness,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMarketType

type HistoricalSampleCoverageAuditStatus = Literal["generated"]
type HistoricalSampleCoverageSourceType = Literal["suite_manifest", "slice_paths"]

DEFAULT_HISTORICAL_SAMPLE_COVERAGE_AUDIT_ID = (
    "historical-sample-coverage-audit-v3.1"
)
MARKET_TYPES: tuple[RecommendationMarketType, ...] = (
    "1x2",
    "cn_handicap_1x2",
    "european_handicap_1x2",
    "correct_score",
)
HANDICAP_MARKETS: tuple[RecommendationMarketType, ...] = (
    "cn_handicap_1x2",
    "european_handicap_1x2",
)
COMPLETE_MARKET_OUTCOMES: dict[RecommendationMarketType, set[str]] = {
    "1x2": {"home_win", "draw", "away_win"},
    "cn_handicap_1x2": {
        "handicap_home_win",
        "handicap_draw",
        "handicap_away_win",
    },
    "european_handicap_1x2": {
        "handicap_home_win",
        "handicap_draw",
        "handicap_away_win",
    },
    "correct_score": set(),
}


class HistoricalSampleCoverageAuditOptions(BaseModel):
    audit_id: str = DEFAULT_HISTORICAL_SAMPLE_COVERAGE_AUDIT_ID
    baseline_source_index: int = Field(default=0, ge=0)
    min_final_answer_fixture_count: int = Field(default=100, ge=1)
    min_dynamic_mixed_candidate_fixture_count: int = Field(default=1, ge=0)
    min_handicap_candidate_fixture_count: int = Field(default=0, ge=0)
    min_correct_score_candidate_fixture_count: int = Field(default=0, ge=0)
    min_feature_snapshot_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    min_odds_movement_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_lineup_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_availability_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_semantic_signal_coverage: float = Field(default=0.80, ge=0.0, le=1.0)


class HistoricalSampleCoverageSourceSummary(BaseModel):
    source_id: str
    source_type: HistoricalSampleCoverageSourceType
    source_path: Path | None = None
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(default=0, ge=0)
    complete_1x2_fixture_count: int = Field(ge=0)
    non_1x2_market_fixture_count: int = Field(default=0, ge=0)
    handicap_market_fixture_count: int = Field(default=0, ge=0)
    correct_score_market_fixture_count: int = Field(default=0, ge=0)
    dynamic_mixed_candidate_fixture_count: int = Field(default=0, ge=0)
    prediction_count_by_market: dict[str, int] = Field(default_factory=dict)
    fixture_count_by_market: dict[str, int] = Field(default_factory=dict)
    complete_market_fixture_count_by_market: dict[str, int] = Field(
        default_factory=dict
    )
    feature_snapshot_count: int = Field(ge=0)
    prematch_context_count: int = Field(ge=0)
    lineup_feature_count: int = Field(ge=0)
    availability_feature_count: int = Field(ge=0)
    odds_movement_feature_count: int = Field(ge=0)
    odds_time_series_feature_count: int = Field(ge=0)
    semantic_signal_feature_count: int = Field(ge=0)
    source_ref_count: int = Field(ge=0)
    feature_snapshot_coverage: float = Field(ge=0.0, le=1.0)
    complete_1x2_coverage: float = Field(ge=0.0, le=1.0)
    non_1x2_market_fixture_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    handicap_market_fixture_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    correct_score_market_fixture_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    dynamic_mixed_candidate_fixture_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    prematch_context_coverage: float = Field(ge=0.0, le=1.0)
    lineup_coverage: float = Field(ge=0.0, le=1.0)
    availability_coverage: float = Field(ge=0.0, le=1.0)
    odds_movement_coverage: float = Field(ge=0.0, le=1.0)
    odds_time_series_coverage: float = Field(ge=0.0, le=1.0)
    semantic_signal_coverage: float = Field(ge=0.0, le=1.0)
    source_ref_coverage: float = Field(ge=0.0, le=1.0)
    minimum_feature_data_quality_score: float | None = None
    average_feature_data_quality_score: float | None = None
    competition_ids: list[str] = Field(default_factory=list)
    season_ids: list[str] = Field(default_factory=list)
    competition_season_keys: list[str] = Field(default_factory=list)
    competition_fixture_counts: dict[str, int] = Field(default_factory=dict)
    season_fixture_counts: dict[str, int] = Field(default_factory=dict)
    readiness_json: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalSampleCoverageCrossSourceGap(BaseModel):
    source_id: str
    missing_competition_season_keys: list[str] = Field(default_factory=list)
    missing_competition_ids: list[str] = Field(default_factory=list)
    missing_season_ids: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalSampleCoverageAuditReport(BaseModel):
    audit_key: str
    audit_id: str
    status: HistoricalSampleCoverageAuditStatus
    source_count: int = Field(ge=0)
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    sources: list[HistoricalSampleCoverageSourceSummary] = Field(default_factory=list)
    cross_source_gaps: list[HistoricalSampleCoverageCrossSourceGap] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedCoverageSource(BaseModel):
    source_id: str
    source_type: HistoricalSampleCoverageSourceType
    source_path: Path | None = None
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_historical_sample_coverage_audit_report(
    sources: Sequence[_LoadedCoverageSource],
    *,
    options: HistoricalSampleCoverageAuditOptions | None = None,
) -> HistoricalSampleCoverageAuditReport:
    resolved_options = options or HistoricalSampleCoverageAuditOptions()
    summaries = [
        _source_summary(source, options=resolved_options) for source in sources
    ]
    warnings = _audit_warnings(summaries, options=resolved_options)
    cross_source_gaps = _cross_source_gaps(summaries, options=resolved_options)
    audit_key = _audit_key(summaries, options=resolved_options)
    summary: dict[str, object] = {
        "calculation_basis": "historical_sample_coverage_audit_v3_1",
        "audit_key": audit_key,
        "audit_id": resolved_options.audit_id,
        "status": "generated",
        "source_count": len(summaries),
        "slice_count": sum(source.slice_count for source in summaries),
        "fixture_count": sum(source.fixture_count for source in summaries),
        "baseline_source_index": resolved_options.baseline_source_index,
        "source_ids": [source.source_id for source in summaries],
        "final_answer_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("final_answer_sample_ready") is True
        ],
        "market_feature_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("market_movement_feature_ready") is True
        ],
        "dynamic_mixed_candidate_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("dynamic_mixed_candidate_ready") is True
        ],
        "handicap_candidate_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("handicap_candidate_ready") is True
        ],
        "correct_score_candidate_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("correct_score_candidate_ready") is True
        ],
        "context_signal_ready_source_ids": [
            source.source_id
            for source in summaries
            if source.readiness_json.get("context_signal_ready") is True
        ],
        "warnings": warnings,
    }
    return HistoricalSampleCoverageAuditReport(
        audit_key=audit_key,
        audit_id=resolved_options.audit_id,
        status="generated",
        source_count=len(summaries),
        slice_count=sum(source.slice_count for source in summaries),
        fixture_count=sum(source.fixture_count for source in summaries),
        sources=summaries,
        cross_source_gaps=cross_source_gaps,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    sources = _sources_from_args(args)
    report = build_historical_sample_coverage_audit_report(
        sources,
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
    source: _LoadedCoverageSource,
    *,
    options: HistoricalSampleCoverageAuditOptions,
) -> HistoricalSampleCoverageSourceSummary:
    fixture_count = sum(len(item.fixtures) for item in source.slices)
    completeness_summaries = [
        evaluate_historical_feature_completeness(
            historical_slice,
            options=HistoricalFeatureCompletenessOptions(
                min_fixture_count=0,
                min_feature_snapshot_coverage=0.0,
                min_lineup_coverage=0.0,
                min_availability_coverage=0.0,
                min_odds_movement_coverage=0.0,
                min_semantic_signal_coverage=0.0,
                min_source_ref_coverage=0.0,
                require_prematch_context=False,
            ),
        ).summary_json
        for historical_slice in source.slices
    ]
    feature_snapshot_count = _sum_summary_int(
        completeness_summaries,
        "feature_snapshot_count",
    )
    prematch_context_count = _sum_summary_int(
        completeness_summaries,
        "prematch_context_count",
    )
    lineup_feature_count = _sum_summary_int(
        completeness_summaries,
        "lineup_feature_count",
    )
    availability_feature_count = _sum_summary_int(
        completeness_summaries,
        "availability_feature_count",
    )
    odds_movement_feature_count = _sum_summary_int(
        completeness_summaries,
        "odds_movement_feature_count",
    )
    odds_time_series_feature_count = _odds_time_series_feature_count(source.slices)
    semantic_signal_feature_count = _sum_summary_int(
        completeness_summaries,
        "semantic_signal_feature_count",
    )
    source_ref_count = _sum_summary_int(completeness_summaries, "source_ref_count")
    feature_quality_scores = _feature_quality_scores(source.slices)
    prediction_count = _prediction_count(source.slices)
    prediction_count_by_market = _prediction_count_by_market(source.slices)
    fixture_count_by_market = _fixture_count_by_market(source.slices)
    complete_market_fixture_count_by_market = (
        _complete_market_fixture_count_by_market(source.slices)
    )
    non_1x2_market_fixture_count = _non_1x2_market_fixture_count(source.slices)
    handicap_market_fixture_count = _handicap_market_fixture_count(source.slices)
    correct_score_market_fixture_count = _correct_score_market_fixture_count(
        source.slices
    )
    dynamic_mixed_candidate_fixture_count = (
        _dynamic_mixed_candidate_fixture_count(source.slices)
    )
    complete_1x2_fixture_count = sum(
        1
        for historical_slice in source.slices
        for fixture in historical_slice.fixtures
        if _has_complete_1x2_market(fixture)
    )
    competition_fixture_counts = _fixture_count_by_competition(source.slices)
    season_fixture_counts = _fixture_count_by_season(source.slices)
    competition_season_keys = _competition_season_keys(source.slices)
    readiness = _readiness(
        fixture_count=fixture_count,
        feature_snapshot_coverage=_coverage(feature_snapshot_count, fixture_count),
        lineup_coverage=_coverage(lineup_feature_count, fixture_count),
        availability_coverage=_coverage(availability_feature_count, fixture_count),
        odds_movement_coverage=_coverage(odds_movement_feature_count, fixture_count),
        odds_time_series_coverage=_coverage(
            odds_time_series_feature_count,
            fixture_count,
        ),
        dynamic_mixed_candidate_fixture_count=(
            dynamic_mixed_candidate_fixture_count
        ),
        handicap_market_fixture_count=handicap_market_fixture_count,
        correct_score_market_fixture_count=correct_score_market_fixture_count,
        semantic_signal_coverage=_coverage(
            semantic_signal_feature_count,
            fixture_count,
        ),
        complete_1x2_coverage=_coverage(complete_1x2_fixture_count, fixture_count),
        options=options,
    )
    warnings = _source_warnings(
        source,
        fixture_count=fixture_count,
        readiness=readiness,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_sample_coverage_source_audit_v3_1",
        "source_id": source.source_id,
        "source_type": source.source_type,
        "source_path": str(source.source_path) if source.source_path is not None else None,
        "slice_count": len(source.slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "prediction_count_by_market": dict(sorted(prediction_count_by_market.items())),
        "fixture_count_by_market": dict(sorted(fixture_count_by_market.items())),
        "complete_market_fixture_count_by_market": dict(
            sorted(complete_market_fixture_count_by_market.items())
        ),
        "non_1x2_market_fixture_count": non_1x2_market_fixture_count,
        "handicap_market_fixture_count": handicap_market_fixture_count,
        "correct_score_market_fixture_count": correct_score_market_fixture_count,
        "dynamic_mixed_candidate_fixture_count": (
            dynamic_mixed_candidate_fixture_count
        ),
        "competition_count": len(competition_fixture_counts),
        "season_count": len(season_fixture_counts),
        "competition_season_count": len(competition_season_keys),
        "readiness": readiness,
        "warnings": warnings,
    }
    return HistoricalSampleCoverageSourceSummary(
        source_id=source.source_id,
        source_type=source.source_type,
        source_path=source.source_path,
        slice_count=len(source.slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        complete_1x2_fixture_count=complete_1x2_fixture_count,
        non_1x2_market_fixture_count=non_1x2_market_fixture_count,
        handicap_market_fixture_count=handicap_market_fixture_count,
        correct_score_market_fixture_count=correct_score_market_fixture_count,
        dynamic_mixed_candidate_fixture_count=dynamic_mixed_candidate_fixture_count,
        prediction_count_by_market=dict(sorted(prediction_count_by_market.items())),
        fixture_count_by_market=dict(sorted(fixture_count_by_market.items())),
        complete_market_fixture_count_by_market=dict(
            sorted(complete_market_fixture_count_by_market.items())
        ),
        feature_snapshot_count=feature_snapshot_count,
        prematch_context_count=prematch_context_count,
        lineup_feature_count=lineup_feature_count,
        availability_feature_count=availability_feature_count,
        odds_movement_feature_count=odds_movement_feature_count,
        odds_time_series_feature_count=odds_time_series_feature_count,
        semantic_signal_feature_count=semantic_signal_feature_count,
        source_ref_count=source_ref_count,
        feature_snapshot_coverage=_coverage(feature_snapshot_count, fixture_count),
        complete_1x2_coverage=_coverage(complete_1x2_fixture_count, fixture_count),
        non_1x2_market_fixture_coverage=_coverage(
            non_1x2_market_fixture_count,
            fixture_count,
        ),
        handicap_market_fixture_coverage=_coverage(
            handicap_market_fixture_count,
            fixture_count,
        ),
        correct_score_market_fixture_coverage=_coverage(
            correct_score_market_fixture_count,
            fixture_count,
        ),
        dynamic_mixed_candidate_fixture_coverage=_coverage(
            dynamic_mixed_candidate_fixture_count,
            fixture_count,
        ),
        prematch_context_coverage=_coverage(prematch_context_count, fixture_count),
        lineup_coverage=_coverage(lineup_feature_count, fixture_count),
        availability_coverage=_coverage(availability_feature_count, fixture_count),
        odds_movement_coverage=_coverage(odds_movement_feature_count, fixture_count),
        odds_time_series_coverage=_coverage(
            odds_time_series_feature_count,
            fixture_count,
        ),
        semantic_signal_coverage=_coverage(
            semantic_signal_feature_count,
            fixture_count,
        ),
        source_ref_coverage=_coverage(source_ref_count, fixture_count),
        minimum_feature_data_quality_score=(
            min(feature_quality_scores) if feature_quality_scores else None
        ),
        average_feature_data_quality_score=(
            sum(feature_quality_scores) / len(feature_quality_scores)
            if feature_quality_scores
            else None
        ),
        competition_ids=sorted(competition_fixture_counts),
        season_ids=sorted(season_fixture_counts),
        competition_season_keys=competition_season_keys,
        competition_fixture_counts=dict(sorted(competition_fixture_counts.items())),
        season_fixture_counts=dict(sorted(season_fixture_counts.items())),
        readiness_json=readiness,
        warnings=warnings,
        summary_json=summary,
    )


def _cross_source_gaps(
    summaries: Sequence[HistoricalSampleCoverageSourceSummary],
    *,
    options: HistoricalSampleCoverageAuditOptions,
) -> list[HistoricalSampleCoverageCrossSourceGap]:
    if not summaries:
        return []
    if options.baseline_source_index >= len(summaries):
        return []
    baseline = summaries[options.baseline_source_index]
    baseline_keys = {
        _normalized_competition_season_key(key)
        for key in baseline.competition_season_keys
    }
    baseline_competitions = {
        _normalized_competition_id(competition_id)
        for competition_id in baseline.competition_ids
    }
    baseline_seasons = set(baseline.season_ids)
    gaps: list[HistoricalSampleCoverageCrossSourceGap] = []
    for index, summary in enumerate(summaries):
        if index == options.baseline_source_index:
            continue
        source_keys = {
            _normalized_competition_season_key(key)
            for key in summary.competition_season_keys
        }
        source_competitions = {
            _normalized_competition_id(competition_id)
            for competition_id in summary.competition_ids
        }
        missing_keys = sorted(baseline_keys - source_keys)
        missing_competitions = sorted(baseline_competitions - source_competitions)
        missing_seasons = sorted(baseline_seasons - set(summary.season_ids))
        if not missing_keys and not missing_competitions and not missing_seasons:
            continue
        gaps.append(
            HistoricalSampleCoverageCrossSourceGap(
                source_id=summary.source_id,
                missing_competition_season_keys=missing_keys,
                missing_competition_ids=missing_competitions,
                missing_season_ids=missing_seasons,
                summary_json={
                    "calculation_basis": (
                        "historical_sample_coverage_cross_source_gap_v3_1"
                    ),
                    "baseline_source_id": baseline.source_id,
                    "source_id": summary.source_id,
                    "missing_competition_season_count": len(missing_keys),
                    "missing_competition_count": len(missing_competitions),
                    "missing_season_count": len(missing_seasons),
                },
            )
        )
    return gaps


def _normalized_competition_season_key(key: str) -> str:
    raw_competition_id, separator, season = key.partition(":")
    if not separator:
        return _normalized_competition_id(key)
    return f"{_normalized_competition_id(raw_competition_id)}:{season}"


def _normalized_competition_id(competition_id: str) -> str:
    return {
        "BUNDESLIGA": "GER_BUNDESLIGA",
        "LA_LIGA": "ESP_LA_LIGA",
        "LIGUE_1": "FRA_LIGUE_1",
        "SERIE_A": "ITA_SERIE_A",
    }.get(competition_id, competition_id)


def _readiness(
    *,
    fixture_count: int,
    feature_snapshot_coverage: float,
    lineup_coverage: float,
    availability_coverage: float,
    odds_movement_coverage: float,
    odds_time_series_coverage: float,
    dynamic_mixed_candidate_fixture_count: int,
    handicap_market_fixture_count: int,
    correct_score_market_fixture_count: int,
    semantic_signal_coverage: float,
    complete_1x2_coverage: float,
    options: HistoricalSampleCoverageAuditOptions,
) -> dict[str, bool]:
    feature_snapshot_ready = (
        feature_snapshot_coverage >= options.min_feature_snapshot_coverage
    )
    market_movement_ready = (
        feature_snapshot_ready
        and odds_time_series_coverage >= options.min_odds_movement_coverage
    )
    context_signal_ready = (
        feature_snapshot_ready
        and lineup_coverage >= options.min_lineup_coverage
        and availability_coverage >= options.min_availability_coverage
        and semantic_signal_coverage >= options.min_semantic_signal_coverage
    )
    final_answer_sample_ready = (
        fixture_count >= options.min_final_answer_fixture_count
        and complete_1x2_coverage >= 1.0
    )
    dynamic_mixed_candidate_ready = (
        final_answer_sample_ready
        and dynamic_mixed_candidate_fixture_count
        >= options.min_dynamic_mixed_candidate_fixture_count
        and dynamic_mixed_candidate_fixture_count > 0
    )
    return {
        "final_answer_sample_ready": final_answer_sample_ready,
        "dynamic_mixed_candidate_ready": dynamic_mixed_candidate_ready,
        "handicap_candidate_ready": (
            final_answer_sample_ready
            and handicap_market_fixture_count
            >= options.min_handicap_candidate_fixture_count
            and handicap_market_fixture_count > 0
        ),
        "correct_score_candidate_ready": (
            final_answer_sample_ready
            and correct_score_market_fixture_count
            >= options.min_correct_score_candidate_fixture_count
            and correct_score_market_fixture_count > 0
        ),
        "feature_snapshot_ready": feature_snapshot_ready,
        "market_movement_feature_ready": market_movement_ready,
        "context_signal_ready": context_signal_ready,
        "full_prematch_context_ready": market_movement_ready and context_signal_ready,
    }


def _source_warnings(
    source: _LoadedCoverageSource,
    *,
    fixture_count: int,
    readiness: Mapping[str, bool],
) -> list[str]:
    warnings = list(source.warnings)
    if fixture_count <= 0:
        warnings.append("historical_sample_coverage:source_has_no_fixtures")
    if not readiness.get("final_answer_sample_ready", False):
        warnings.append("historical_sample_coverage:final_answer_sample_not_ready")
    if not readiness.get("dynamic_mixed_candidate_ready", False):
        warnings.append("historical_sample_coverage:dynamic_mixed_candidate_not_ready")
    if not readiness.get("handicap_candidate_ready", False):
        warnings.append("historical_sample_coverage:handicap_candidate_not_ready")
    if not readiness.get("correct_score_candidate_ready", False):
        warnings.append("historical_sample_coverage:correct_score_candidate_not_ready")
    if not readiness.get("feature_snapshot_ready", False):
        warnings.append("historical_sample_coverage:feature_snapshot_not_ready")
    if not readiness.get("market_movement_feature_ready", False):
        warnings.append("historical_sample_coverage:market_movement_not_ready")
    if not readiness.get("context_signal_ready", False):
        warnings.append("historical_sample_coverage:context_signal_not_ready")
    return _dedupe_strings(warnings)


def _audit_warnings(
    summaries: Sequence[HistoricalSampleCoverageSourceSummary],
    *,
    options: HistoricalSampleCoverageAuditOptions,
) -> list[str]:
    warnings: list[str] = []
    if not summaries:
        warnings.append("historical_sample_coverage:no_sources")
    if options.baseline_source_index >= len(summaries):
        warnings.append("historical_sample_coverage:baseline_source_index_out_of_range")
    for summary in summaries:
        warnings.extend(summary.warnings)
    return _dedupe_strings(warnings)


def _sources_from_args(args: Namespace) -> list[_LoadedCoverageSource]:
    sources: list[_LoadedCoverageSource] = []
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
            _LoadedCoverageSource(
                source_id=source_id,
                source_type="slice_paths",
                source_path=None,
                slices=slices,
            )
        )
    return sources


def _source_from_manifest(
    bundle: HistoricalRecommendationSuiteManifestLoadResult,
) -> _LoadedCoverageSource:
    return _LoadedCoverageSource(
        source_id=bundle.manifest.suite_id,
        source_type="suite_manifest",
        source_path=bundle.manifest_path,
        slices=bundle.slices,
        warnings=bundle.warnings,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Audit frozen historical sample coverage for Nutmeg quality gates."
    )
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--slice-path", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--audit-id", default=DEFAULT_HISTORICAL_SAMPLE_COVERAGE_AUDIT_ID)
    parser.add_argument("--baseline-source-index", type=int, default=0)
    parser.add_argument("--min-final-answer-fixture-count", type=int, default=100)
    parser.add_argument("--min-dynamic-mixed-candidate-fixture-count", type=int, default=1)
    parser.add_argument("--min-handicap-candidate-fixture-count", type=int, default=0)
    parser.add_argument("--min-correct-score-candidate-fixture-count", type=int, default=0)
    parser.add_argument("--min-feature-snapshot-coverage", type=float, default=1.0)
    parser.add_argument("--min-odds-movement-coverage", type=float, default=0.80)
    parser.add_argument("--min-lineup-coverage", type=float, default=0.80)
    parser.add_argument("--min-availability-coverage", type=float, default=0.80)
    parser.add_argument("--min-semantic-signal-coverage", type=float, default=0.80)
    args = parser.parse_args(argv)
    if not args.suite_manifest and not args.slice_path:
        parser.error("provide at least one --suite-manifest or --slice-path")
    return args


def _options_from_args(args: Namespace) -> HistoricalSampleCoverageAuditOptions:
    return HistoricalSampleCoverageAuditOptions(
        audit_id=args.audit_id,
        baseline_source_index=args.baseline_source_index,
        min_final_answer_fixture_count=args.min_final_answer_fixture_count,
        min_dynamic_mixed_candidate_fixture_count=(
            args.min_dynamic_mixed_candidate_fixture_count
        ),
        min_handicap_candidate_fixture_count=args.min_handicap_candidate_fixture_count,
        min_correct_score_candidate_fixture_count=(
            args.min_correct_score_candidate_fixture_count
        ),
        min_feature_snapshot_coverage=args.min_feature_snapshot_coverage,
        min_odds_movement_coverage=args.min_odds_movement_coverage,
        min_lineup_coverage=args.min_lineup_coverage,
        min_availability_coverage=args.min_availability_coverage,
        min_semantic_signal_coverage=args.min_semantic_signal_coverage,
    )


def _has_complete_1x2_market(fixture: HistoricalFixture) -> bool:
    outcomes = {
        prediction.outcome
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
    }
    return {"home_win", "draw", "away_win"}.issubset(outcomes)


def _prediction_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        len(fixture.predictions)
        for historical_slice in slices
        for fixture in historical_slice.fixtures
    )


def _prediction_count_by_market(
    slices: Sequence[HistoricalRecommendationSlice],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for historical_slice in slices:
        for fixture in historical_slice.fixtures:
            for prediction in fixture.predictions:
                counts[prediction.market_type] += 1
    return counts


def _fixture_count_by_market(
    slices: Sequence[HistoricalRecommendationSlice],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for historical_slice in slices:
        for fixture in historical_slice.fixtures:
            fixture_markets = {prediction.market_type for prediction in fixture.predictions}
            counts.update(fixture_markets)
    return counts


def _complete_market_fixture_count_by_market(
    slices: Sequence[HistoricalRecommendationSlice],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for historical_slice in slices:
        for fixture in historical_slice.fixtures:
            for market_type in MARKET_TYPES:
                if _has_complete_market(fixture, market_type):
                    counts[market_type] += 1
    return counts


def _non_1x2_market_fixture_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        1
        for historical_slice in slices
        for fixture in historical_slice.fixtures
        if any(prediction.market_type != "1x2" for prediction in fixture.predictions)
    )


def _handicap_market_fixture_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        1
        for historical_slice in slices
        for fixture in historical_slice.fixtures
        if any(prediction.market_type in HANDICAP_MARKETS for prediction in fixture.predictions)
    )


def _correct_score_market_fixture_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        1
        for historical_slice in slices
        for fixture in historical_slice.fixtures
        if any(prediction.market_type == "correct_score" for prediction in fixture.predictions)
    )


def _dynamic_mixed_candidate_fixture_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        1
        for historical_slice in slices
        for fixture in historical_slice.fixtures
        if _has_complete_1x2_market(fixture)
        and any(prediction.market_type != "1x2" for prediction in fixture.predictions)
    )


def _has_complete_market(
    fixture: HistoricalFixture,
    market_type: RecommendationMarketType,
) -> bool:
    outcomes = {
        prediction.outcome
        for prediction in fixture.predictions
        if prediction.market_type == market_type
    }
    required = COMPLETE_MARKET_OUTCOMES[market_type]
    if not required:
        return bool(outcomes)
    return required.issubset(outcomes)


def _feature_quality_scores(
    slices: Sequence[HistoricalRecommendationSlice],
) -> list[float]:
    return [
        fixture.feature_snapshot.data_quality_score
        for historical_slice in slices
        for fixture in historical_slice.fixtures
        if fixture.feature_snapshot is not None
    ]


def _odds_time_series_feature_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    count = 0
    for historical_slice in slices:
        for fixture in historical_slice.fixtures:
            prematch_context = _prematch_context(fixture)
            if prematch_context is None:
                continue
            odds_movements = prematch_context.get("odds_movement")
            if not isinstance(odds_movements, list):
                continue
            if any(_odds_movement_has_time_series(item) for item in odds_movements):
                count += 1
    return count


def _prematch_context(fixture: HistoricalFixture) -> Mapping[str, object] | None:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return None
    raw_context = snapshot.features_json.get("prematch_context")
    if isinstance(raw_context, dict):
        return raw_context
    return None


def _odds_movement_has_time_series(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    point_count = item.get("point_count")
    if isinstance(point_count, bool):
        return False
    if isinstance(point_count, int | float):
        return point_count >= 2
    points = item.get("points")
    return isinstance(points, list) and len(points) >= 2


def _fixture_count_by_competition(
    slices: Sequence[HistoricalRecommendationSlice],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for historical_slice in slices:
        for fixture in historical_slice.fixtures:
            counts[fixture.competition_id] += 1
    return counts


def _fixture_count_by_season(
    slices: Sequence[HistoricalRecommendationSlice],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for historical_slice in slices:
        season = historical_slice.metadata.season or "unknown"
        counts[season] += len(historical_slice.fixtures)
    return counts


def _competition_season_keys(
    slices: Sequence[HistoricalRecommendationSlice],
) -> list[str]:
    keys = {
        (
            f"{historical_slice.metadata.competition_id}:"
            f"{historical_slice.metadata.season or 'unknown'}"
        )
        for historical_slice in slices
    }
    return sorted(keys)


def _sum_summary_int(
    summaries: Sequence[Mapping[str, object]],
    key: str,
) -> int:
    total = 0
    for summary in summaries:
        value = summary.get(key, 0)
        if isinstance(value, bool):
            raise ValueError(f"expected integer summary value for {key}")
        if isinstance(value, int):
            total += value
        elif isinstance(value, float):
            total += int(value)
        else:
            total += int(str(value))
    return total


def _coverage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator


def _audit_key(
    summaries: Sequence[HistoricalSampleCoverageSourceSummary],
    *,
    options: HistoricalSampleCoverageAuditOptions,
) -> str:
    payload = {
        "options": options.model_dump(mode="json"),
        "sources": [
            {
                "source_id": summary.source_id,
                "slice_count": summary.slice_count,
                "fixture_count": summary.fixture_count,
                "competition_season_keys": summary.competition_season_keys,
                "readiness": summary.readiness_json,
            }
            for summary in summaries
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_sample_coverage_audit:{digest}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
