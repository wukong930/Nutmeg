from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditOptions,
    HistoricalSampleCoverageAuditReport,
    HistoricalSampleCoverageSourceSummary,
    _sources_from_args,
    build_historical_sample_coverage_audit_report,
)

type HistoricalPrematchFeatureSampleReadinessStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPrematchFeatureSampleReadinessCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalPrematchFeatureSampleReadinessTarget = Literal[
    "final_answer",
    "feature_snapshot",
    "market_movement",
    "context_signal",
    "full_prematch_context",
]

DEFAULT_HISTORICAL_PREMATCH_FEATURE_SAMPLE_READINESS_ID = (
    "prematch-feature-sample-readiness-v3.1"
)

_TARGET_READINESS_KEYS: dict[HistoricalPrematchFeatureSampleReadinessTarget, str] = {
    "final_answer": "final_answer_sample_ready",
    "feature_snapshot": "feature_snapshot_ready",
    "market_movement": "market_movement_feature_ready",
    "context_signal": "context_signal_ready",
    "full_prematch_context": "full_prematch_context_ready",
}


class HistoricalPrematchFeatureSampleReadinessOptions(BaseModel):
    readiness_id: str = DEFAULT_HISTORICAL_PREMATCH_FEATURE_SAMPLE_READINESS_ID
    target_profile: HistoricalPrematchFeatureSampleReadinessTarget = "market_movement"
    min_ready_source_count: int = Field(default=1, ge=0)
    min_ready_fixture_count: int = Field(default=100, ge=0)
    min_ready_slice_count: int = Field(default=1, ge=0)
    min_ready_competition_count: int = Field(default=1, ge=0)
    min_ready_season_count: int = Field(default=1, ge=0)
    min_ready_competition_season_count: int = Field(default=1, ge=0)
    min_complete_1x2_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    min_feature_snapshot_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    min_odds_time_series_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_lineup_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_availability_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_semantic_signal_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_source_ref_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_average_feature_data_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    min_feature_data_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    max_source_warning_count: int | None = Field(default=None, ge=0)
    max_report_warning_count: int | None = Field(default=None, ge=0)


class HistoricalPrematchFeatureSampleReadinessCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureSampleReadinessCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureSampleReadinessSourceEvaluation(BaseModel):
    source_id: str
    status: HistoricalPrematchFeatureSampleReadinessStatus
    target_profile: HistoricalPrematchFeatureSampleReadinessTarget
    ready_for_target: bool
    source_path: Path | None = None
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    season_count: int = Field(ge=0)
    competition_season_count: int = Field(ge=0)
    readiness_json: dict[str, bool] = Field(default_factory=dict)
    checks: list[HistoricalPrematchFeatureSampleReadinessCheck] = (
        Field(default_factory=list)
    )
    failed_check_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage_json: dict[str, float | None] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureSampleReadinessReport(BaseModel):
    readiness_key: str
    status: HistoricalPrematchFeatureSampleReadinessStatus
    sample_ready_allowed: bool
    shadow_allowed: bool
    readiness_id: str
    target_profile: HistoricalPrematchFeatureSampleReadinessTarget
    coverage_audit_key: str
    coverage_audit_report_path: Path | None = None
    source_count: int = Field(ge=0)
    evaluated_source_count: int = Field(ge=0)
    accepted_source_count: int = Field(ge=0)
    shadow_only_source_count: int = Field(ge=0)
    rejected_source_count: int = Field(ge=0)
    ready_source_ids: list[str] = Field(default_factory=list)
    ready_fixture_count: int = Field(ge=0)
    ready_slice_count: int = Field(ge=0)
    ready_competition_count: int = Field(ge=0)
    ready_season_count: int = Field(ge=0)
    ready_competition_season_count: int = Field(ge=0)
    checks: list[HistoricalPrematchFeatureSampleReadinessCheck] = (
        Field(default_factory=list)
    )
    sources: list[HistoricalPrematchFeatureSampleReadinessSourceEvaluation] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_prematch_feature_sample_readiness_report(
    coverage_audit: HistoricalSampleCoverageAuditReport,
    *,
    options: HistoricalPrematchFeatureSampleReadinessOptions | None = None,
    coverage_audit_report_path: Path | None = None,
) -> HistoricalPrematchFeatureSampleReadinessReport:
    resolved_options = options or HistoricalPrematchFeatureSampleReadinessOptions()
    source_evaluations = [
        _evaluate_source(source, options=resolved_options)
        for source in coverage_audit.sources
    ]
    accepted_sources = [
        source for source in source_evaluations if source.status == "accepted"
    ]
    shadow_only_sources = [
        source for source in source_evaluations if source.status == "shadow_only"
    ]
    rejected_sources = [
        source for source in source_evaluations if source.status == "rejected"
    ]
    ready_competitions = {
        competition_id
        for source in accepted_sources
        for competition_id in _summary_strings(source.summary_json, "competition_ids")
    }
    ready_seasons = {
        season_id
        for source in accepted_sources
        for season_id in _summary_strings(source.summary_json, "season_ids")
    }
    ready_competition_seasons = {
        key
        for source in accepted_sources
        for key in _summary_strings(source.summary_json, "competition_season_keys")
    }
    ready_fixture_count = sum(source.fixture_count for source in accepted_sources)
    ready_slice_count = sum(source.slice_count for source in accepted_sources)
    checks = _report_checks(
        accepted_sources,
        ready_fixture_count=ready_fixture_count,
        ready_slice_count=ready_slice_count,
        ready_competition_count=len(ready_competitions),
        ready_season_count=len(ready_seasons),
        ready_competition_season_count=len(ready_competition_seasons),
        report_warning_count=len(coverage_audit.warnings),
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    if failed_checks:
        status = _non_accepted_status(source_evaluations, coverage_audit)
    else:
        status = "accepted"
    sample_ready_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = _dedupe_strings(
        [
            *coverage_audit.warnings,
            *[
                f"prematch_feature_sample_readiness:failed_check:{check.name}"
                for check in failed_checks
            ],
            *[
                f"prematch_feature_sample_readiness:source_shadow_only:{source.source_id}"
                for source in shadow_only_sources
            ],
            *[
                f"prematch_feature_sample_readiness:source_rejected:{source.source_id}"
                for source in rejected_sources
            ],
        ]
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_sample_readiness_v3_1",
        "readiness_id": resolved_options.readiness_id,
        "target_profile": resolved_options.target_profile,
        "status": status,
        "sample_ready_allowed": sample_ready_allowed,
        "shadow_allowed": shadow_allowed,
        "coverage_audit_key": coverage_audit.audit_key,
        "coverage_audit_report_path": (
            str(coverage_audit_report_path)
            if coverage_audit_report_path is not None
            else None
        ),
        "source_count": coverage_audit.source_count,
        "evaluated_source_count": len(source_evaluations),
        "accepted_source_count": len(accepted_sources),
        "shadow_only_source_count": len(shadow_only_sources),
        "rejected_source_count": len(rejected_sources),
        "ready_source_ids": [source.source_id for source in accepted_sources],
        "ready_fixture_count": ready_fixture_count,
        "ready_slice_count": ready_slice_count,
        "ready_competition_count": len(ready_competitions),
        "ready_season_count": len(ready_seasons),
        "ready_competition_season_count": len(ready_competition_seasons),
        "failed_check_names": [check.name for check in failed_checks],
        "warnings": warnings,
        "options": resolved_options.model_dump(mode="json"),
    }
    readiness_key = _readiness_key(
        summary,
        checks,
        source_evaluations,
    )
    return HistoricalPrematchFeatureSampleReadinessReport(
        readiness_key=readiness_key,
        status=status,
        sample_ready_allowed=sample_ready_allowed,
        shadow_allowed=shadow_allowed,
        readiness_id=resolved_options.readiness_id,
        target_profile=resolved_options.target_profile,
        coverage_audit_key=coverage_audit.audit_key,
        coverage_audit_report_path=coverage_audit_report_path,
        source_count=coverage_audit.source_count,
        evaluated_source_count=len(source_evaluations),
        accepted_source_count=len(accepted_sources),
        shadow_only_source_count=len(shadow_only_sources),
        rejected_source_count=len(rejected_sources),
        ready_source_ids=[source.source_id for source in accepted_sources],
        ready_fixture_count=ready_fixture_count,
        ready_slice_count=ready_slice_count,
        ready_competition_count=len(ready_competitions),
        ready_season_count=len(ready_seasons),
        ready_competition_season_count=len(ready_competition_seasons),
        checks=checks,
        sources=source_evaluations,
        warnings=warnings,
        summary_json={**summary, "readiness_key": readiness_key},
    )


def load_historical_prematch_feature_sample_readiness_report(
    path: Path | str,
) -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    coverage_audit_report_path: Path | None = args.coverage_audit_report_path
    if coverage_audit_report_path is not None:
        coverage_audit = _load_coverage_audit_report(coverage_audit_report_path)
    else:
        coverage_audit = build_historical_sample_coverage_audit_report(
            _sources_from_args(args),
            options=_coverage_audit_options_from_args(args),
        )
    report = build_historical_prematch_feature_sample_readiness_report(
        coverage_audit,
        options=_options_from_args(args),
        coverage_audit_report_path=coverage_audit_report_path,
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
    if not report.sample_ready_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _evaluate_source(
    source: HistoricalSampleCoverageSourceSummary,
    *,
    options: HistoricalPrematchFeatureSampleReadinessOptions,
) -> HistoricalPrematchFeatureSampleReadinessSourceEvaluation:
    target_readiness_key = _TARGET_READINESS_KEYS[options.target_profile]
    ready_for_target = source.readiness_json.get(target_readiness_key) is True
    checks = _source_checks(source, ready_for_target=ready_for_target, options=options)
    failed_check_names = [
        check.name for check in checks if check.status == "failed"
    ]
    if not failed_check_names:
        status: HistoricalPrematchFeatureSampleReadinessStatus = "accepted"
    elif _source_has_shadow_value(source):
        status = "shadow_only"
    else:
        status = "rejected"
    coverage_json: dict[str, float | None] = {
        "complete_1x2_coverage": source.complete_1x2_coverage,
        "feature_snapshot_coverage": source.feature_snapshot_coverage,
        "odds_time_series_coverage": source.odds_time_series_coverage,
        "lineup_coverage": source.lineup_coverage,
        "availability_coverage": source.availability_coverage,
        "semantic_signal_coverage": source.semantic_signal_coverage,
        "source_ref_coverage": source.source_ref_coverage,
        "minimum_feature_data_quality_score": source.minimum_feature_data_quality_score,
        "average_feature_data_quality_score": source.average_feature_data_quality_score,
    }
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_sample_readiness_source_v3_1"
        ),
        "source_id": source.source_id,
        "status": status,
        "target_profile": options.target_profile,
        "ready_for_target": ready_for_target,
        "slice_count": source.slice_count,
        "fixture_count": source.fixture_count,
        "competition_ids": source.competition_ids,
        "season_ids": source.season_ids,
        "competition_season_keys": source.competition_season_keys,
        "readiness": source.readiness_json,
        "coverage": coverage_json,
        "failed_check_names": failed_check_names,
        "warnings": source.warnings,
    }
    return HistoricalPrematchFeatureSampleReadinessSourceEvaluation(
        source_id=source.source_id,
        status=status,
        target_profile=options.target_profile,
        ready_for_target=ready_for_target,
        source_path=source.source_path,
        slice_count=source.slice_count,
        fixture_count=source.fixture_count,
        competition_count=len(source.competition_ids),
        season_count=len(source.season_ids),
        competition_season_count=len(source.competition_season_keys),
        readiness_json=source.readiness_json,
        checks=checks,
        failed_check_names=failed_check_names,
        warnings=source.warnings,
        coverage_json=coverage_json,
        summary_json=summary,
    )


def _source_checks(
    source: HistoricalSampleCoverageSourceSummary,
    *,
    ready_for_target: bool,
    options: HistoricalPrematchFeatureSampleReadinessOptions,
) -> list[HistoricalPrematchFeatureSampleReadinessCheck]:
    checks = [
        _boolean_check(
            name="target_readiness",
            actual=ready_for_target,
            expected=True,
            detail="source should satisfy the selected prematch feature target profile",
        ),
        _minimum_check(
            name="complete_1x2_coverage",
            actual=source.complete_1x2_coverage,
            threshold=options.min_complete_1x2_coverage,
            detail="source should have complete frozen 1X2 probabilities for replay",
        ),
    ]
    if options.target_profile != "final_answer":
        checks.extend(
            [
                _minimum_check(
                    name="feature_snapshot_coverage",
                    actual=source.feature_snapshot_coverage,
                    threshold=options.min_feature_snapshot_coverage,
                    detail="source should have frozen feature snapshots",
                ),
                _minimum_check(
                    name="source_ref_coverage",
                    actual=source.source_ref_coverage,
                    threshold=options.min_source_ref_coverage,
                    detail="source should retain provenance for prematch features",
                ),
            ]
        )
    if options.target_profile in {"market_movement", "full_prematch_context"}:
        checks.append(
            _minimum_check(
                name="odds_time_series_coverage",
                actual=source.odds_time_series_coverage,
                threshold=options.min_odds_time_series_coverage,
                detail="market-movement learning requires frozen odds time series",
            )
        )
    if options.target_profile in {"context_signal", "full_prematch_context"}:
        checks.extend(
            [
                _minimum_check(
                    name="lineup_coverage",
                    actual=source.lineup_coverage,
                    threshold=options.min_lineup_coverage,
                    detail="context-signal learning requires lineup evidence",
                ),
                _minimum_check(
                    name="availability_coverage",
                    actual=source.availability_coverage,
                    threshold=options.min_availability_coverage,
                    detail="context-signal learning requires player availability evidence",
                ),
                _minimum_check(
                    name="semantic_signal_coverage",
                    actual=source.semantic_signal_coverage,
                    threshold=options.min_semantic_signal_coverage,
                    detail="context-signal learning requires semantic prematch signals",
                ),
            ]
        )
    if options.min_average_feature_data_quality_score is not None:
        checks.append(
            _minimum_check(
                name="average_feature_data_quality_score",
                actual=source.average_feature_data_quality_score,
                threshold=options.min_average_feature_data_quality_score,
                detail="source average feature quality should meet the configured floor",
            )
        )
    if options.min_feature_data_quality_score is not None:
        checks.append(
            _minimum_check(
                name="minimum_feature_data_quality_score",
                actual=source.minimum_feature_data_quality_score,
                threshold=options.min_feature_data_quality_score,
                detail="source minimum feature quality should meet the configured floor",
            )
        )
    if options.max_source_warning_count is not None:
        checks.append(
            _maximum_check(
                name="source_warning_count",
                actual=len(source.warnings),
                threshold=options.max_source_warning_count,
                detail="source warning count should stay within the configured ceiling",
            )
        )
    return checks


def _report_checks(
    accepted_sources: Sequence[HistoricalPrematchFeatureSampleReadinessSourceEvaluation],
    *,
    ready_fixture_count: int,
    ready_slice_count: int,
    ready_competition_count: int,
    ready_season_count: int,
    ready_competition_season_count: int,
    report_warning_count: int,
    options: HistoricalPrematchFeatureSampleReadinessOptions,
) -> list[HistoricalPrematchFeatureSampleReadinessCheck]:
    checks = [
        _minimum_check(
            name="ready_source_count",
            actual=len(accepted_sources),
            threshold=options.min_ready_source_count,
            detail="readiness gate should have enough accepted coverage sources",
        ),
        _minimum_check(
            name="ready_fixture_count",
            actual=ready_fixture_count,
            threshold=options.min_ready_fixture_count,
            detail="readiness gate should have enough accepted fixtures",
        ),
        _minimum_check(
            name="ready_slice_count",
            actual=ready_slice_count,
            threshold=options.min_ready_slice_count,
            detail="readiness gate should have enough accepted frozen slices",
        ),
        _minimum_check(
            name="ready_competition_count",
            actual=ready_competition_count,
            threshold=options.min_ready_competition_count,
            detail="readiness gate should cover enough competitions",
        ),
        _minimum_check(
            name="ready_season_count",
            actual=ready_season_count,
            threshold=options.min_ready_season_count,
            detail="readiness gate should cover enough seasons",
        ),
        _minimum_check(
            name="ready_competition_season_count",
            actual=ready_competition_season_count,
            threshold=options.min_ready_competition_season_count,
            detail="readiness gate should cover enough competition-season cells",
        ),
    ]
    if options.max_report_warning_count is not None:
        checks.append(
            _maximum_check(
                name="report_warning_count",
                actual=report_warning_count,
                threshold=options.max_report_warning_count,
                detail="coverage audit report warning count should stay within the ceiling",
            )
        )
    return checks


def _non_accepted_status(
    sources: Sequence[HistoricalPrematchFeatureSampleReadinessSourceEvaluation],
    coverage_audit: HistoricalSampleCoverageAuditReport,
) -> HistoricalPrematchFeatureSampleReadinessStatus:
    if any(source.status in {"accepted", "shadow_only"} for source in sources):
        return "shadow_only"
    if any(source.feature_snapshot_count > 0 for source in coverage_audit.sources):
        return "shadow_only"
    if any(
        source.readiness_json.get("final_answer_sample_ready") is True
        for source in coverage_audit.sources
    ):
        return "shadow_only"
    return "rejected"


def _source_has_shadow_value(source: HistoricalSampleCoverageSourceSummary) -> bool:
    return (
        source.feature_snapshot_count > 0
        or source.readiness_json.get("final_answer_sample_ready") is True
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalPrematchFeatureSampleReadinessCheck:
    return HistoricalPrematchFeatureSampleReadinessCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalPrematchFeatureSampleReadinessCheck:
    if actual is None:
        return HistoricalPrematchFeatureSampleReadinessCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalPrematchFeatureSampleReadinessCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalPrematchFeatureSampleReadinessCheck:
    if actual is None:
        return HistoricalPrematchFeatureSampleReadinessCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalPrematchFeatureSampleReadinessCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _load_coverage_audit_report(path: Path) -> HistoricalSampleCoverageAuditReport:
    return HistoricalSampleCoverageAuditReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _readiness_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPrematchFeatureSampleReadinessCheck],
    sources: Sequence[HistoricalPrematchFeatureSampleReadinessSourceEvaluation],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_sample_readiness:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Gate frozen prematch feature samples before learning admission."
    )
    parser.add_argument("--coverage-audit-report-path", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--slice-path", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument(
        "--readiness-id",
        default=DEFAULT_HISTORICAL_PREMATCH_FEATURE_SAMPLE_READINESS_ID,
    )
    parser.add_argument(
        "--target-profile",
        choices=list(_TARGET_READINESS_KEYS),
        default="market_movement",
    )
    parser.add_argument("--min-ready-source-count", type=int, default=1)
    parser.add_argument("--min-ready-fixture-count", type=int, default=100)
    parser.add_argument("--min-ready-slice-count", type=int, default=1)
    parser.add_argument("--min-ready-competition-count", type=int, default=1)
    parser.add_argument("--min-ready-season-count", type=int, default=1)
    parser.add_argument("--min-ready-competition-season-count", type=int, default=1)
    parser.add_argument("--min-complete-1x2-coverage", type=float, default=1.0)
    parser.add_argument("--min-feature-snapshot-coverage", type=float, default=1.0)
    parser.add_argument("--min-odds-time-series-coverage", type=float, default=0.80)
    parser.add_argument("--min-lineup-coverage", type=float, default=0.80)
    parser.add_argument("--min-availability-coverage", type=float, default=0.80)
    parser.add_argument("--min-semantic-signal-coverage", type=float, default=0.80)
    parser.add_argument("--min-source-ref-coverage", type=float, default=0.80)
    parser.add_argument("--min-average-feature-data-quality-score", type=float)
    parser.add_argument("--min-feature-data-quality-score", type=float)
    parser.add_argument("--max-source-warning-count", type=int)
    parser.add_argument("--max-report-warning-count", type=int)
    parser.add_argument("--baseline-source-index", type=int, default=0)
    parser.add_argument("--min-final-answer-fixture-count", type=int, default=100)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if args.coverage_audit_report_path is None and not (
        args.suite_manifest or args.slice_path
    ):
        parser.error(
            "provide --coverage-audit-report-path or at least one --suite-manifest/--slice-path"
        )
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureSampleReadinessOptions:
    return HistoricalPrematchFeatureSampleReadinessOptions(
        readiness_id=args.readiness_id,
        target_profile=args.target_profile,
        min_ready_source_count=args.min_ready_source_count,
        min_ready_fixture_count=args.min_ready_fixture_count,
        min_ready_slice_count=args.min_ready_slice_count,
        min_ready_competition_count=args.min_ready_competition_count,
        min_ready_season_count=args.min_ready_season_count,
        min_ready_competition_season_count=args.min_ready_competition_season_count,
        min_complete_1x2_coverage=args.min_complete_1x2_coverage,
        min_feature_snapshot_coverage=args.min_feature_snapshot_coverage,
        min_odds_time_series_coverage=args.min_odds_time_series_coverage,
        min_lineup_coverage=args.min_lineup_coverage,
        min_availability_coverage=args.min_availability_coverage,
        min_semantic_signal_coverage=args.min_semantic_signal_coverage,
        min_source_ref_coverage=args.min_source_ref_coverage,
        min_average_feature_data_quality_score=(
            args.min_average_feature_data_quality_score
        ),
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        max_source_warning_count=args.max_source_warning_count,
        max_report_warning_count=args.max_report_warning_count,
    )


def _coverage_audit_options_from_args(
    args: Namespace,
) -> HistoricalSampleCoverageAuditOptions:
    return HistoricalSampleCoverageAuditOptions(
        baseline_source_index=args.baseline_source_index,
        min_final_answer_fixture_count=args.min_final_answer_fixture_count,
        min_feature_snapshot_coverage=args.min_feature_snapshot_coverage,
        min_odds_movement_coverage=args.min_odds_time_series_coverage,
        min_lineup_coverage=args.min_lineup_coverage,
        min_availability_coverage=args.min_availability_coverage,
        min_semantic_signal_coverage=args.min_semantic_signal_coverage,
    )


def _summary_strings(
    summary: Mapping[str, object],
    key: str,
) -> list[str]:
    value = summary.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
