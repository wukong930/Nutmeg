from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    HistoricalMarketMovementRiskFilterRuntimeActivationReport,
    load_historical_market_movement_risk_filter_runtime_activation_report,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
    load_historical_prematch_feature_sample_readiness_report,
)
from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditReport,
)

if TYPE_CHECKING:
    from nutmeg.recommendations import (
        historical_market_movement_runtime_activation_segment_replay_batch_gate as _batch_gate,
    )

    HistoricalSegmentReplayBatchGateReport = (
        _batch_gate.HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport
    )
else:
    HistoricalSegmentReplayBatchGateReport = Any

type HistoricalMarketMovementRuntimeActivationSampleExpansionStatus = Literal[
    "sample_expansion_ready",
    "shadow_only",
    "blocked",
]
type HistoricalMarketMovementRuntimeActivationSampleExpansionCheckStatus = Literal[
    "passed",
    "failed",
    "watchlist",
    "skipped",
]
type HistoricalMarketMovementRuntimeActivationSampleExpansionSourceType = Literal[
    "sample_readiness",
    "coverage_audit",
]

DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SAMPLE_EXPANSION_ID = (
    "market-movement-runtime-activation-sample-expansion-v3.2"
)


class HistoricalMarketMovementRuntimeActivationSampleExpansionOptions(BaseModel):
    expansion_id: str = DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SAMPLE_EXPANSION_ID
    min_readiness_report_count: int = Field(default=1, ge=0)
    min_ready_source_count: int = Field(default=1, ge=0)
    min_ready_fixture_count: int = Field(default=500, ge=0)
    min_ready_slice_count: int = Field(default=25, ge=0)
    min_ready_competition_count: int = Field(default=5, ge=0)
    min_ready_season_count: int = Field(default=5, ge=0)
    min_ready_competition_season_count: int = Field(default=25, ge=0)
    min_combined_fixture_count: int = Field(default=500, ge=0)
    min_combined_slice_count: int = Field(default=25, ge=0)
    min_combined_competition_count: int = Field(default=5, ge=0)
    min_combined_season_count: int = Field(default=5, ge=0)
    min_combined_competition_season_count: int = Field(default=25, ge=0)
    min_supplemental_source_count_for_promotion: int = Field(default=1, ge=0)
    min_supplemental_fixture_count_for_promotion: int = Field(default=500, ge=0)
    min_supplemental_slice_count_for_promotion: int = Field(default=25, ge=0)
    min_selected_segment_competition_count: int = Field(default=1, ge=0)
    min_selected_segment_competition_season_count: int = Field(default=1, ge=0)
    min_selected_segment_count_for_promotion: int = Field(default=2, ge=0)
    min_segment_replay_batch_gate_count_for_promotion: int = Field(
        default=0,
        ge=0,
    )
    min_segment_replay_batch_ready_count_for_promotion: int = Field(
        default=0,
        ge=0,
    )
    min_adjusted_fixture_count: int = Field(default=100, ge=0)
    min_adjusted_prediction_count: int = Field(default=300, ge=0)
    min_adjusted_to_combined_fixture_ratio_for_promotion: float | None = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
    )
    require_activation_ready: bool = True
    require_readiness_sample_ready: bool = True
    require_no_default_profile_write: bool = True
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRuntimeActivationSampleExpansionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalMarketMovementRuntimeActivationSampleExpansionSource(BaseModel):
    source_id: str
    source_type: HistoricalMarketMovementRuntimeActivationSampleExpansionSourceType
    source_path: Path | None = None
    source_report_key: str | None = None
    sample_ready_allowed: bool
    market_movement_feature_ready: bool
    fixture_count: int = Field(ge=0)
    slice_count: int = Field(ge=0)
    competition_ids: list[str] = Field(default_factory=list)
    season_ids: list[str] = Field(default_factory=list)
    competition_season_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRuntimeActivationSampleExpansionReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRuntimeActivationSampleExpansionStatus
    passed: bool
    promotion_ready: bool
    expansion_id: str
    source_activation_report_key: str
    activation_status: str
    activation_ready: bool
    selected_segment_group_keys: list[str] = Field(default_factory=list)
    selected_segment_competition_ids: list[str] = Field(default_factory=list)
    selected_segment_competition_count: int = Field(ge=0)
    selected_segment_competition_season_count: int = Field(ge=0)
    readiness_report_count: int = Field(ge=0)
    coverage_audit_report_count: int = Field(ge=0)
    ready_source_count: int = Field(ge=0)
    supplemental_source_count: int = Field(ge=0)
    ready_fixture_count: int = Field(ge=0)
    ready_slice_count: int = Field(ge=0)
    ready_competition_count: int = Field(ge=0)
    ready_season_count: int = Field(ge=0)
    ready_competition_season_count: int = Field(ge=0)
    supplemental_fixture_count: int = Field(ge=0)
    supplemental_slice_count: int = Field(ge=0)
    combined_fixture_count: int = Field(ge=0)
    combined_slice_count: int = Field(ge=0)
    combined_competition_count: int = Field(ge=0)
    combined_season_count: int = Field(ge=0)
    combined_competition_season_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(ge=0)
    adjusted_prediction_count: int = Field(ge=0)
    adjusted_to_combined_fixture_ratio: float | None = None
    segment_replay_batch_gate_count: int = Field(default=0, ge=0)
    segment_replay_batch_ready_count: int = Field(default=0, ge=0)
    segment_replay_batch_adjusted_fixture_count: int = Field(default=0, ge=0)
    segment_replay_batch_adjusted_prediction_count: int = Field(default=0, ge=0)
    segment_replay_batch_segment_group_keys: list[str] = Field(default_factory=list)
    segment_replay_batch_report_keys: list[str] = Field(default_factory=list)
    effective_segment_group_keys: list[str] = Field(default_factory=list)
    effective_segment_count: int = Field(default=0, ge=0)
    effective_adjusted_fixture_count: int = Field(default=0, ge=0)
    effective_adjusted_prediction_count: int = Field(default=0, ge=0)
    effective_adjusted_to_combined_fixture_ratio: float | None = None
    default_profile_written: bool = False
    default_recommendation_path_changed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalMarketMovementRuntimeActivationSampleExpansionCheck] = (
        Field(default_factory=list)
    )
    sources: list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource] = (
        Field(default_factory=list)
    )
    blockers: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_market_movement_runtime_activation_sample_expansion_report(
    activation: HistoricalMarketMovementRiskFilterRuntimeActivationReport,
    *,
    sample_readiness_reports: Sequence[
        HistoricalPrematchFeatureSampleReadinessReport
    ] = (),
    coverage_audit_reports: Sequence[HistoricalSampleCoverageAuditReport] = (),
    segment_replay_batch_gate_reports: Sequence[HistoricalSegmentReplayBatchGateReport] = (),
    options: (
        HistoricalMarketMovementRuntimeActivationSampleExpansionOptions | None
    ) = None,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionReport:
    resolved_options = (
        options or HistoricalMarketMovementRuntimeActivationSampleExpansionOptions()
    )
    readiness_sources = [
        source
        for report in sample_readiness_reports
        for source in _sources_from_readiness_report(report)
    ]
    coverage_sources = [
        source
        for report in coverage_audit_reports
        for source in _sources_from_coverage_audit_report(report)
    ]
    combined_sources = _dedupe_sources([*readiness_sources, *coverage_sources])
    readiness_source_ids = {source.source_id for source in readiness_sources}
    supplemental_sources = [
        source
        for source in coverage_sources
        if source.source_id not in readiness_source_ids
    ]
    selected_competition_ids = _selected_segment_competition_ids(
        activation.selected_segment_group_keys
    )
    selected_competition_seasons = {
        competition_season_key
        for source in combined_sources
        for competition_season_key in source.competition_season_keys
        if _competition_from_competition_season_key(competition_season_key)
        in selected_competition_ids
    }
    readiness_competitions = {
        competition_id
        for source in readiness_sources
        for competition_id in source.competition_ids
    }
    readiness_seasons = {
        season_id for source in readiness_sources for season_id in source.season_ids
    }
    readiness_competition_seasons = {
        key for source in readiness_sources for key in source.competition_season_keys
    }
    combined_competitions = {
        competition_id
        for source in combined_sources
        for competition_id in source.competition_ids
    }
    combined_seasons = {
        season_id for source in combined_sources for season_id in source.season_ids
    }
    combined_competition_seasons = {
        key for source in combined_sources for key in source.competition_season_keys
    }
    adjusted_ratio = _ratio(
        activation.adjusted_fixture_count,
        sum(source.fixture_count for source in combined_sources),
    )
    ready_segment_replay_batch_gate_reports = [
        report
        for report in segment_replay_batch_gate_reports
        if report.passed and report.runtime_replay_batch_ready
    ]
    segment_replay_batch_segment_group_keys = _dedupe_strings(
        [
            segment_group_key
            for report in ready_segment_replay_batch_gate_reports
            for segment_group_key in report.replayed_segment_group_keys
        ]
    )
    segment_replay_batch_report_keys = _dedupe_strings(
        [report.report_key for report in segment_replay_batch_gate_reports]
    )
    segment_replay_batch_adjusted_fixture_count = sum(
        report.total_adjusted_fixture_count
        for report in ready_segment_replay_batch_gate_reports
    )
    segment_replay_batch_adjusted_prediction_count = sum(
        report.total_adjusted_prediction_count
        for report in ready_segment_replay_batch_gate_reports
    )
    effective_segment_group_keys = _dedupe_strings(
        [
            *activation.selected_segment_group_keys,
            *segment_replay_batch_segment_group_keys,
        ]
    )
    effective_adjusted_fixture_count = max(
        activation.adjusted_fixture_count,
        segment_replay_batch_adjusted_fixture_count,
    )
    effective_adjusted_prediction_count = max(
        activation.adjusted_prediction_count,
        segment_replay_batch_adjusted_prediction_count,
    )
    effective_adjusted_ratio = _ratio(
        effective_adjusted_fixture_count,
        sum(source.fixture_count for source in combined_sources),
    )
    default_recommendation_path_changed = (
        activation.default_recommendation_path_changed
        or any(
            report.default_recommendation_path_changed
            for report in segment_replay_batch_gate_reports
        )
    )
    production_recommendation_changed = (
        activation.production_recommendation_changed
        or any(
            report.production_recommendation_changed
            for report in segment_replay_batch_gate_reports
        )
    )
    public_response_changed = activation.public_response_changed or any(
        report.public_response_changed for report in segment_replay_batch_gate_reports
    )
    checks = _checks(
        activation=activation,
        readiness_reports=sample_readiness_reports,
        readiness_sources=readiness_sources,
        supplemental_sources=supplemental_sources,
        combined_sources=combined_sources,
        segment_replay_batch_gate_reports=segment_replay_batch_gate_reports,
        segment_replay_batch_ready_count=len(ready_segment_replay_batch_gate_reports),
        readiness_competitions=readiness_competitions,
        readiness_seasons=readiness_seasons,
        readiness_competition_seasons=readiness_competition_seasons,
        combined_competitions=combined_competitions,
        combined_seasons=combined_seasons,
        combined_competition_seasons=combined_competition_seasons,
        selected_competition_ids=selected_competition_ids,
        selected_competition_seasons=selected_competition_seasons,
        effective_segment_group_keys=effective_segment_group_keys,
        effective_adjusted_fixture_count=effective_adjusted_fixture_count,
        effective_adjusted_prediction_count=effective_adjusted_prediction_count,
        effective_adjusted_ratio=effective_adjusted_ratio,
        default_recommendation_path_changed=default_recommendation_path_changed,
        production_recommendation_changed=production_recommendation_changed,
        public_response_changed=public_response_changed,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    watchlist = [check.name for check in checks if check.status == "watchlist"]
    passed = not blockers
    promotion_ready = passed and not watchlist
    status: HistoricalMarketMovementRuntimeActivationSampleExpansionStatus
    if blockers:
        status = "blocked"
    elif watchlist:
        status = "shadow_only"
    else:
        status = "sample_expansion_ready"
    warnings = [
        *[f"market_movement_activation_sample_expansion:failed:{name}" for name in blockers],
        *[
            f"market_movement_activation_sample_expansion:watchlist:{name}"
            for name in watchlist
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_runtime_activation_sample_expansion_v3_2"
        ),
        "expansion_id": resolved_options.expansion_id,
        "status": status,
        "passed": passed,
        "promotion_ready": promotion_ready,
        "source_activation_report_key": activation.report_key,
        "activation_status": activation.status,
        "activation_ready": activation.staged_activation_ready,
        "selected_segment_group_keys": activation.selected_segment_group_keys,
        "selected_segment_competition_ids": selected_competition_ids,
        "selected_segment_competition_count": len(selected_competition_ids),
        "selected_segment_competition_season_count": len(selected_competition_seasons),
        "readiness_report_count": len(sample_readiness_reports),
        "coverage_audit_report_count": len(coverage_audit_reports),
        "ready_source_count": len(readiness_sources),
        "supplemental_source_count": len(supplemental_sources),
        "ready_fixture_count": sum(source.fixture_count for source in readiness_sources),
        "ready_slice_count": sum(source.slice_count for source in readiness_sources),
        "ready_competition_count": len(readiness_competitions),
        "ready_season_count": len(readiness_seasons),
        "ready_competition_season_count": len(readiness_competition_seasons),
        "supplemental_fixture_count": sum(
            source.fixture_count for source in supplemental_sources
        ),
        "supplemental_slice_count": sum(
            source.slice_count for source in supplemental_sources
        ),
        "combined_fixture_count": sum(
            source.fixture_count for source in combined_sources
        ),
        "combined_slice_count": sum(source.slice_count for source in combined_sources),
        "combined_competition_count": len(combined_competitions),
        "combined_season_count": len(combined_seasons),
        "combined_competition_season_count": len(combined_competition_seasons),
        "adjusted_fixture_count": activation.adjusted_fixture_count,
        "adjusted_prediction_count": activation.adjusted_prediction_count,
        "adjusted_to_combined_fixture_ratio": adjusted_ratio,
        "segment_replay_batch_gate_count": len(segment_replay_batch_gate_reports),
        "segment_replay_batch_ready_count": len(
            ready_segment_replay_batch_gate_reports
        ),
        "segment_replay_batch_adjusted_fixture_count": (
            segment_replay_batch_adjusted_fixture_count
        ),
        "segment_replay_batch_adjusted_prediction_count": (
            segment_replay_batch_adjusted_prediction_count
        ),
        "segment_replay_batch_segment_group_keys": (
            segment_replay_batch_segment_group_keys
        ),
        "segment_replay_batch_report_keys": segment_replay_batch_report_keys,
        "effective_segment_group_keys": effective_segment_group_keys,
        "effective_segment_count": len(effective_segment_group_keys),
        "effective_adjusted_fixture_count": effective_adjusted_fixture_count,
        "effective_adjusted_prediction_count": effective_adjusted_prediction_count,
        "effective_adjusted_to_combined_fixture_ratio": effective_adjusted_ratio,
        "default_profile_written": activation.default_profile_written,
        "default_recommendation_path_changed": (
            default_recommendation_path_changed
        ),
        "production_recommendation_changed": production_recommendation_changed,
        "public_response_changed": public_response_changed,
        "source_ids": [source.source_id for source in combined_sources],
        "supplemental_source_ids": [
            source.source_id for source in supplemental_sources
        ],
        "blockers": blockers,
        "watchlist": watchlist,
        "warnings": warnings,
        "options": resolved_options.model_dump(mode="json"),
    }
    report_key = _report_key(summary, checks, combined_sources)
    return HistoricalMarketMovementRuntimeActivationSampleExpansionReport(
        report_key=report_key,
        status=status,
        passed=passed,
        promotion_ready=promotion_ready,
        expansion_id=resolved_options.expansion_id,
        source_activation_report_key=activation.report_key,
        activation_status=activation.status,
        activation_ready=activation.staged_activation_ready,
        selected_segment_group_keys=activation.selected_segment_group_keys,
        selected_segment_competition_ids=selected_competition_ids,
        selected_segment_competition_count=len(selected_competition_ids),
        selected_segment_competition_season_count=len(selected_competition_seasons),
        readiness_report_count=len(sample_readiness_reports),
        coverage_audit_report_count=len(coverage_audit_reports),
        ready_source_count=len(readiness_sources),
        supplemental_source_count=len(supplemental_sources),
        ready_fixture_count=sum(source.fixture_count for source in readiness_sources),
        ready_slice_count=sum(source.slice_count for source in readiness_sources),
        ready_competition_count=len(readiness_competitions),
        ready_season_count=len(readiness_seasons),
        ready_competition_season_count=len(readiness_competition_seasons),
        supplemental_fixture_count=sum(
            source.fixture_count for source in supplemental_sources
        ),
        supplemental_slice_count=sum(
            source.slice_count for source in supplemental_sources
        ),
        combined_fixture_count=sum(source.fixture_count for source in combined_sources),
        combined_slice_count=sum(source.slice_count for source in combined_sources),
        combined_competition_count=len(combined_competitions),
        combined_season_count=len(combined_seasons),
        combined_competition_season_count=len(combined_competition_seasons),
        adjusted_fixture_count=activation.adjusted_fixture_count,
        adjusted_prediction_count=activation.adjusted_prediction_count,
        adjusted_to_combined_fixture_ratio=adjusted_ratio,
        segment_replay_batch_gate_count=len(segment_replay_batch_gate_reports),
        segment_replay_batch_ready_count=len(ready_segment_replay_batch_gate_reports),
        segment_replay_batch_adjusted_fixture_count=(
            segment_replay_batch_adjusted_fixture_count
        ),
        segment_replay_batch_adjusted_prediction_count=(
            segment_replay_batch_adjusted_prediction_count
        ),
        segment_replay_batch_segment_group_keys=segment_replay_batch_segment_group_keys,
        segment_replay_batch_report_keys=segment_replay_batch_report_keys,
        effective_segment_group_keys=effective_segment_group_keys,
        effective_segment_count=len(effective_segment_group_keys),
        effective_adjusted_fixture_count=effective_adjusted_fixture_count,
        effective_adjusted_prediction_count=effective_adjusted_prediction_count,
        effective_adjusted_to_combined_fixture_ratio=effective_adjusted_ratio,
        default_profile_written=activation.default_profile_written,
        default_recommendation_path_changed=(
            default_recommendation_path_changed
        ),
        production_recommendation_changed=production_recommendation_changed,
        public_response_changed=public_response_changed,
        checks=checks,
        sources=combined_sources,
        blockers=blockers,
        watchlist=watchlist,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_runtime_activation_sample_expansion_report(
    path: Path | str,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionReport:
    return HistoricalMarketMovementRuntimeActivationSampleExpansionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_market_movement_runtime_activation_sample_expansion_report(
        load_historical_market_movement_risk_filter_runtime_activation_report(
            args.activation_report
        ),
        sample_readiness_reports=[
            load_historical_prematch_feature_sample_readiness_report(path)
            for path in args.sample_readiness_report
        ],
        coverage_audit_reports=[
            _load_coverage_audit_report(path) for path in args.coverage_audit_report
        ],
        segment_replay_batch_gate_reports=[
            _load_segment_replay_batch_gate_report(path)
            for path in args.segment_replay_batch_gate_report
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


def _sources_from_readiness_report(
    report: HistoricalPrematchFeatureSampleReadinessReport,
) -> list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource]:
    sources: list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource] = []
    for source in report.sources:
        if source.status != "accepted":
            continue
        sources.append(
            HistoricalMarketMovementRuntimeActivationSampleExpansionSource(
                source_id=source.source_id,
                source_type="sample_readiness",
                source_path=source.source_path,
                source_report_key=report.readiness_key,
                sample_ready_allowed=report.sample_ready_allowed,
                market_movement_feature_ready=(
                    source.readiness_json.get("market_movement_feature_ready") is True
                ),
                fixture_count=source.fixture_count,
                slice_count=source.slice_count,
                competition_ids=_summary_strings(
                    source.summary_json,
                    "competition_ids",
                ),
                season_ids=_summary_strings(source.summary_json, "season_ids"),
                competition_season_keys=_summary_strings(
                    source.summary_json,
                    "competition_season_keys",
                ),
                warnings=source.warnings,
                summary_json=source.summary_json,
            )
        )
    return sources


def _sources_from_coverage_audit_report(
    report: HistoricalSampleCoverageAuditReport,
) -> list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource]:
    sources: list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource] = []
    for source in report.sources:
        market_feature_ready = (
            source.readiness_json.get("market_movement_feature_ready") is True
        )
        if not market_feature_ready:
            continue
        sources.append(
            HistoricalMarketMovementRuntimeActivationSampleExpansionSource(
                source_id=source.source_id,
                source_type="coverage_audit",
                source_path=source.source_path,
                source_report_key=report.audit_key,
                sample_ready_allowed=market_feature_ready,
                market_movement_feature_ready=market_feature_ready,
                fixture_count=source.fixture_count,
                slice_count=source.slice_count,
                competition_ids=source.competition_ids,
                season_ids=source.season_ids,
                competition_season_keys=source.competition_season_keys,
                warnings=source.warnings,
                summary_json=source.summary_json,
            )
        )
    return sources


def _checks(
    *,
    activation: HistoricalMarketMovementRiskFilterRuntimeActivationReport,
    readiness_reports: Sequence[HistoricalPrematchFeatureSampleReadinessReport],
    readiness_sources: Sequence[
        HistoricalMarketMovementRuntimeActivationSampleExpansionSource
    ],
    supplemental_sources: Sequence[
        HistoricalMarketMovementRuntimeActivationSampleExpansionSource
    ],
    combined_sources: Sequence[HistoricalMarketMovementRuntimeActivationSampleExpansionSource],
    segment_replay_batch_gate_reports: Sequence[HistoricalSegmentReplayBatchGateReport],
    segment_replay_batch_ready_count: int,
    readiness_competitions: set[str],
    readiness_seasons: set[str],
    readiness_competition_seasons: set[str],
    combined_competitions: set[str],
    combined_seasons: set[str],
    combined_competition_seasons: set[str],
    selected_competition_ids: Sequence[str],
    selected_competition_seasons: set[str],
    effective_segment_group_keys: Sequence[str],
    effective_adjusted_fixture_count: int,
    effective_adjusted_prediction_count: int,
    effective_adjusted_ratio: float | None,
    default_recommendation_path_changed: bool,
    production_recommendation_changed: bool,
    public_response_changed: bool,
    options: HistoricalMarketMovementRuntimeActivationSampleExpansionOptions,
) -> list[HistoricalMarketMovementRuntimeActivationSampleExpansionCheck]:
    return [
        _required_bool_check(
            name="activation_ready",
            actual=activation.staged_activation_ready,
            required=options.require_activation_ready,
            detail="activation preflight should already be staged-ready",
        ),
        _required_bool_check(
            name="activation_not_blocked",
            actual=activation.status != "blocked" and not activation.blockers,
            required=options.require_activation_ready,
            detail="activation preflight should have no blockers",
        ),
        _required_bool_check(
            name="no_default_profile_write",
            actual=not activation.default_profile_written,
            required=options.require_no_default_profile_write,
            detail="sample expansion should not write default profiles",
        ),
        _required_bool_check(
            name="no_default_path_change",
            actual=not default_recommendation_path_changed,
            required=options.require_no_default_path_change,
            detail="sample expansion should not change default recommendations",
        ),
        _required_bool_check(
            name="no_production_change",
            actual=not production_recommendation_changed,
            required=options.require_no_production_change,
            detail="sample expansion should not change production recommendations",
        ),
        _required_bool_check(
            name="no_public_response_change",
            actual=not public_response_changed,
            required=options.require_no_public_response_change,
            detail="sample expansion should not change public responses",
        ),
        _minimum_check(
            name="readiness_report_count",
            actual=len(readiness_reports),
            threshold=options.min_readiness_report_count,
            detail="sample expansion should include frozen sample readiness evidence",
        ),
        _required_bool_check(
            name="readiness_reports_sample_ready",
            actual=all(report.sample_ready_allowed for report in readiness_reports),
            required=options.require_readiness_sample_ready,
            detail="attached readiness reports should be sample-ready",
        ),
        _minimum_check(
            name="ready_source_count",
            actual=len(readiness_sources),
            threshold=options.min_ready_source_count,
            detail="readiness evidence should expose enough accepted sources",
        ),
        _minimum_check(
            name="ready_fixture_count",
            actual=sum(source.fixture_count for source in readiness_sources),
            threshold=options.min_ready_fixture_count,
            detail="readiness evidence should cover enough frozen fixtures",
        ),
        _minimum_check(
            name="ready_slice_count",
            actual=sum(source.slice_count for source in readiness_sources),
            threshold=options.min_ready_slice_count,
            detail="readiness evidence should cover enough frozen slices",
        ),
        _minimum_check(
            name="ready_competition_count",
            actual=len(readiness_competitions),
            threshold=options.min_ready_competition_count,
            detail="readiness evidence should cover enough competitions",
        ),
        _minimum_check(
            name="ready_season_count",
            actual=len(readiness_seasons),
            threshold=options.min_ready_season_count,
            detail="readiness evidence should cover enough seasons",
        ),
        _minimum_check(
            name="ready_competition_season_count",
            actual=len(readiness_competition_seasons),
            threshold=options.min_ready_competition_season_count,
            detail="readiness evidence should cover enough competition-season cells",
        ),
        _minimum_check(
            name="combined_fixture_count",
            actual=sum(source.fixture_count for source in combined_sources),
            threshold=options.min_combined_fixture_count,
            detail="combined sample evidence should cover enough frozen fixtures",
        ),
        _minimum_check(
            name="combined_slice_count",
            actual=sum(source.slice_count for source in combined_sources),
            threshold=options.min_combined_slice_count,
            detail="combined sample evidence should cover enough frozen slices",
        ),
        _minimum_check(
            name="combined_competition_count",
            actual=len(combined_competitions),
            threshold=options.min_combined_competition_count,
            detail="combined sample evidence should broaden competition coverage",
        ),
        _minimum_check(
            name="combined_season_count",
            actual=len(combined_seasons),
            threshold=options.min_combined_season_count,
            detail="combined sample evidence should preserve season coverage",
        ),
        _minimum_check(
            name="combined_competition_season_count",
            actual=len(combined_competition_seasons),
            threshold=options.min_combined_competition_season_count,
            detail="combined sample evidence should cover enough competition-season cells",
        ),
        _minimum_check(
            name="selected_segment_competition_count",
            actual=len(selected_competition_ids),
            threshold=options.min_selected_segment_competition_count,
            detail="selected activation segments should map to competitions",
        ),
        _minimum_check(
            name="selected_segment_competition_season_count",
            actual=len(selected_competition_seasons),
            threshold=options.min_selected_segment_competition_season_count,
            detail="selected activation competitions should exist in frozen samples",
        ),
        _minimum_check(
            name="adjusted_fixture_count",
            actual=effective_adjusted_fixture_count,
            threshold=options.min_adjusted_fixture_count,
            detail="activation or supplemental replay should adjust enough fixtures",
        ),
        _minimum_check(
            name="adjusted_prediction_count",
            actual=effective_adjusted_prediction_count,
            threshold=options.min_adjusted_prediction_count,
            detail="activation or supplemental replay should adjust enough predictions",
        ),
        _required_bool_check(
            name="segment_replay_batch_gates_ready",
            actual=all(
                report.passed and report.runtime_replay_batch_ready
                for report in segment_replay_batch_gate_reports
            ),
            required=bool(segment_replay_batch_gate_reports),
            detail="attached segment replay batch gates should be passed and runtime-ready",
        ),
        _watchlist_minimum_check(
            name="segment_replay_batch_gate_count_for_promotion",
            actual=len(segment_replay_batch_gate_reports),
            threshold=options.min_segment_replay_batch_gate_count_for_promotion,
            detail="promotion can require supplemental segment replay batch evidence",
        ),
        _watchlist_minimum_check(
            name="segment_replay_batch_ready_count_for_promotion",
            actual=segment_replay_batch_ready_count,
            threshold=options.min_segment_replay_batch_ready_count_for_promotion,
            detail="promotion can require runtime-ready segment replay batch evidence",
        ),
        _watchlist_minimum_check(
            name="supplemental_source_count",
            actual=len(supplemental_sources),
            threshold=options.min_supplemental_source_count_for_promotion,
            detail="promotion should include supplemental frozen sources",
        ),
        _watchlist_minimum_check(
            name="supplemental_fixture_count",
            actual=sum(source.fixture_count for source in supplemental_sources),
            threshold=options.min_supplemental_fixture_count_for_promotion,
            detail="promotion should include enough supplemental fixtures",
        ),
        _watchlist_minimum_check(
            name="supplemental_slice_count",
            actual=sum(source.slice_count for source in supplemental_sources),
            threshold=options.min_supplemental_slice_count_for_promotion,
            detail="promotion should include enough supplemental slices",
        ),
        _watchlist_minimum_check(
            name="selected_segment_count_for_promotion",
            actual=len(effective_segment_group_keys),
            threshold=options.min_selected_segment_count_for_promotion,
            detail=(
                "promotion should avoid relying on a single activation segment "
                "after supplemental replay evidence is included"
            ),
        ),
        _optional_watchlist_minimum_check(
            name="adjusted_to_combined_fixture_ratio_for_promotion",
            actual=effective_adjusted_ratio,
            threshold=options.min_adjusted_to_combined_fixture_ratio_for_promotion,
            detail="promotion should replay a meaningful share of combined samples",
        ),
    ]


def _dedupe_sources(
    sources: Sequence[HistoricalMarketMovementRuntimeActivationSampleExpansionSource],
) -> list[HistoricalMarketMovementRuntimeActivationSampleExpansionSource]:
    deduped: dict[str, HistoricalMarketMovementRuntimeActivationSampleExpansionSource] = {}
    for source in sources:
        deduped.setdefault(source.source_id, source)
    return list(deduped.values())


def _selected_segment_competition_ids(
    selected_segment_group_keys: Sequence[str],
) -> list[str]:
    return _dedupe_strings(
        [
            parts[1]
            for key in selected_segment_group_keys
            for parts in [key.split(":")]
            if len(parts) >= 2 and parts[0] == "competition_outcome"
        ]
    )


def _competition_from_competition_season_key(value: str) -> str:
    return value.split(":", 1)[0]


def _summary_strings(summary: Mapping[str, object], key: str) -> list[str]:
    value = summary.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionCheck:
    if not required:
        return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=True,
            detail=detail,
        )
    return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionCheck:
    return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _watchlist_minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionCheck:
    return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "watchlist",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_watchlist_minimum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float | None,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionCheck:
    if threshold is None:
        return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return HistoricalMarketMovementRuntimeActivationSampleExpansionCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "watchlist",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalMarketMovementRuntimeActivationSampleExpansionCheck],
    sources: Sequence[HistoricalMarketMovementRuntimeActivationSampleExpansionSource],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "sources": [source.model_dump(mode="json") for source in sources],
        },
        default=str,
        sort_keys=True,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_market_movement_runtime_activation_sample_expansion:{digest}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _load_coverage_audit_report(path: Path | str) -> HistoricalSampleCoverageAuditReport:
    return HistoricalSampleCoverageAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _load_segment_replay_batch_gate_report(
    path: Path | str,
) -> HistoricalSegmentReplayBatchGateReport:
    from nutmeg.recommendations import (
        historical_market_movement_runtime_activation_segment_replay_batch_gate as batch_gate,
    )

    loader = (
        batch_gate.load_historical_market_movement_runtime_activation_segment_replay_batch_gate_report
    )
    return loader(path)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Gate market-movement runtime activation against reusable frozen "
            "sample expansion evidence."
        )
    )
    parser.add_argument("--activation-report", type=Path, required=True)
    parser.add_argument(
        "--sample-readiness-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--coverage-audit-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--segment-replay-batch-gate-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--min-ready-fixture-count", type=int, default=500)
    parser.add_argument("--min-ready-slice-count", type=int, default=25)
    parser.add_argument("--min-ready-competition-count", type=int, default=5)
    parser.add_argument("--min-ready-season-count", type=int, default=5)
    parser.add_argument(
        "--min-ready-competition-season-count",
        type=int,
        default=25,
    )
    parser.add_argument("--min-combined-fixture-count", type=int, default=500)
    parser.add_argument("--min-combined-slice-count", type=int, default=25)
    parser.add_argument("--min-combined-competition-count", type=int, default=5)
    parser.add_argument("--min-combined-season-count", type=int, default=5)
    parser.add_argument(
        "--min-combined-competition-season-count",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--min-supplemental-source-count-for-promotion",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-supplemental-fixture-count-for-promotion",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--min-supplemental-slice-count-for-promotion",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--min-selected-segment-count-for-promotion",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--min-segment-replay-batch-gate-count-for-promotion",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-segment-replay-batch-ready-count-for-promotion",
        type=int,
        default=0,
    )
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=100)
    parser.add_argument("--min-adjusted-prediction-count", type=int, default=300)
    parser.add_argument(
        "--min-adjusted-to-combined-fixture-ratio-for-promotion",
        type=float,
        default=0.05,
    )
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRuntimeActivationSampleExpansionOptions:
    return HistoricalMarketMovementRuntimeActivationSampleExpansionOptions(
        min_ready_fixture_count=args.min_ready_fixture_count,
        min_ready_slice_count=args.min_ready_slice_count,
        min_ready_competition_count=args.min_ready_competition_count,
        min_ready_season_count=args.min_ready_season_count,
        min_ready_competition_season_count=(
            args.min_ready_competition_season_count
        ),
        min_combined_fixture_count=args.min_combined_fixture_count,
        min_combined_slice_count=args.min_combined_slice_count,
        min_combined_competition_count=args.min_combined_competition_count,
        min_combined_season_count=args.min_combined_season_count,
        min_combined_competition_season_count=(
            args.min_combined_competition_season_count
        ),
        min_supplemental_source_count_for_promotion=(
            args.min_supplemental_source_count_for_promotion
        ),
        min_supplemental_fixture_count_for_promotion=(
            args.min_supplemental_fixture_count_for_promotion
        ),
        min_supplemental_slice_count_for_promotion=(
            args.min_supplemental_slice_count_for_promotion
        ),
        min_selected_segment_count_for_promotion=(
            args.min_selected_segment_count_for_promotion
        ),
        min_segment_replay_batch_gate_count_for_promotion=(
            args.min_segment_replay_batch_gate_count_for_promotion
        ),
        min_segment_replay_batch_ready_count_for_promotion=(
            args.min_segment_replay_batch_ready_count_for_promotion
        ),
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        min_adjusted_prediction_count=args.min_adjusted_prediction_count,
        min_adjusted_to_combined_fixture_ratio_for_promotion=(
            args.min_adjusted_to_combined_fixture_ratio_for_promotion
        ),
    )
