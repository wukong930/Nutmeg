from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
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
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalFeatureCompletenessCheckStatus = Literal["passed", "failed", "skipped"]
type HistoricalFeatureCompletenessStatus = Literal["passed", "failed"]


class HistoricalFeatureCompletenessOptions(BaseModel):
    min_fixture_count: int = Field(default=1, ge=0)
    min_feature_snapshot_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    min_lineup_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    min_availability_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    min_odds_movement_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    min_semantic_signal_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    min_source_ref_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
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
    require_prematch_context: bool = True
    require_feature_not_after_prediction: bool = True
    require_feature_before_kickoff: bool = True


class HistoricalFeatureCompletenessCheck(BaseModel):
    name: str
    status: HistoricalFeatureCompletenessCheckStatus
    actual: float | int | str | None = None
    threshold: float | int | str | None = None
    detail: str


class HistoricalFeatureCompletenessResult(BaseModel):
    completeness_key: str
    slice_id: str
    status: HistoricalFeatureCompletenessStatus
    passed: bool
    checks: list[HistoricalFeatureCompletenessCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFeatureCompletenessSuiteResult(BaseModel):
    status: HistoricalFeatureCompletenessStatus
    passed: bool
    slice_count: int = Field(ge=0)
    results: list[HistoricalFeatureCompletenessResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _HistoricalFeatureCompletenessDiagnostics(BaseModel):
    fixture_count: int = Field(ge=0)
    feature_snapshot_count: int = Field(ge=0)
    prematch_context_count: int = Field(ge=0)
    lineup_feature_count: int = Field(ge=0)
    availability_feature_count: int = Field(ge=0)
    odds_movement_feature_count: int = Field(ge=0)
    semantic_signal_feature_count: int = Field(ge=0)
    source_ref_count: int = Field(ge=0)
    feature_after_prediction_fixture_ids: list[str] = Field(default_factory=list)
    feature_not_before_kickoff_fixture_ids: list[str] = Field(default_factory=list)
    missing_prematch_context_fixture_ids: list[str] = Field(default_factory=list)
    minimum_feature_data_quality_score: float | None = None
    average_feature_data_quality_score: float | None = None

    @property
    def feature_snapshot_coverage(self) -> float:
        return _coverage(self.feature_snapshot_count, self.fixture_count)

    @property
    def prematch_context_coverage(self) -> float:
        return _coverage(self.prematch_context_count, self.fixture_count)

    @property
    def lineup_coverage(self) -> float:
        return _coverage(self.lineup_feature_count, self.fixture_count)

    @property
    def availability_coverage(self) -> float:
        return _coverage(self.availability_feature_count, self.fixture_count)

    @property
    def odds_movement_coverage(self) -> float:
        return _coverage(self.odds_movement_feature_count, self.fixture_count)

    @property
    def semantic_signal_coverage(self) -> float:
        return _coverage(self.semantic_signal_feature_count, self.fixture_count)

    @property
    def source_ref_coverage(self) -> float:
        return _coverage(self.source_ref_count, self.fixture_count)


def evaluate_historical_feature_completeness(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalFeatureCompletenessOptions | None = None,
) -> HistoricalFeatureCompletenessResult:
    resolved_options = options or HistoricalFeatureCompletenessOptions()
    diagnostics = _feature_completeness_diagnostics(historical_slice)
    checks = _feature_completeness_checks(
        historical_slice,
        diagnostics=diagnostics,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: HistoricalFeatureCompletenessStatus = "passed" if passed else "failed"
    warnings = [
        f"historical_feature_completeness:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary = _summary(
        historical_slice,
        diagnostics=diagnostics,
        checks=checks,
        options=resolved_options,
        status=status,
        passed=passed,
        warnings=warnings,
    )
    return HistoricalFeatureCompletenessResult(
        completeness_key=_completeness_key(
            historical_slice,
            options=resolved_options,
        ),
        slice_id=historical_slice.metadata.slice_id,
        status=status,
        passed=passed,
        checks=checks,
        warnings=warnings,
        summary_json=summary,
    )


def evaluate_historical_feature_completeness_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFeatureCompletenessOptions | None = None,
) -> HistoricalFeatureCompletenessSuiteResult:
    results = [
        evaluate_historical_feature_completeness(
            historical_slice,
            options=options,
        )
        for historical_slice in historical_slices
    ]
    passed = all(result.passed for result in results)
    status: HistoricalFeatureCompletenessStatus = "passed" if passed else "failed"
    warnings = [warning for result in results for warning in result.warnings]
    fixture_count = sum(_summary_int(result, "fixture_count") for result in results)
    feature_snapshot_count = sum(
        _summary_int(result, "feature_snapshot_count") for result in results
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_feature_completeness_suite_v3_1",
        "status": status,
        "passed": passed,
        "slice_count": len(historical_slices),
        "passed_slice_count": sum(1 for result in results if result.passed),
        "failed_slice_count": sum(1 for result in results if not result.passed),
        "failed_slice_ids": [result.slice_id for result in results if not result.passed],
        "fixture_count": fixture_count,
        "feature_snapshot_count": feature_snapshot_count,
        "warnings": warnings,
    }
    summary["feature_snapshot_coverage"] = _coverage(feature_snapshot_count, fixture_count)
    return HistoricalFeatureCompletenessSuiteResult(
        status=status,
        passed=passed,
        slice_count=len(historical_slices),
        results=results,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is not None:
        bundle = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*bundle.slices, *historical_slices]
    result = evaluate_historical_feature_completeness_suite(
        historical_slices,
        options=_options_from_args(args),
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


def _feature_completeness_diagnostics(
    historical_slice: HistoricalRecommendationSlice,
) -> _HistoricalFeatureCompletenessDiagnostics:
    feature_data_quality_scores: list[float] = []
    feature_snapshot_count = 0
    prematch_context_count = 0
    lineup_feature_count = 0
    availability_feature_count = 0
    odds_movement_feature_count = 0
    semantic_signal_feature_count = 0
    source_ref_count = 0
    feature_after_prediction_fixture_ids: list[str] = []
    feature_not_before_kickoff_fixture_ids: list[str] = []
    missing_prematch_context_fixture_ids: list[str] = []
    for fixture in historical_slice.fixtures:
        snapshot = fixture.feature_snapshot
        if snapshot is None:
            missing_prematch_context_fixture_ids.append(fixture.fixture_id)
            continue
        feature_snapshot_count += 1
        feature_data_quality_scores.append(snapshot.data_quality_score)
        if _aware_utc(snapshot.feature_time_utc) > _aware_utc(fixture.prediction_time_utc):
            feature_after_prediction_fixture_ids.append(fixture.fixture_id)
        if _aware_utc(snapshot.feature_time_utc) >= _aware_utc(fixture.kickoff_time_utc):
            feature_not_before_kickoff_fixture_ids.append(fixture.fixture_id)
        prematch_context = _prematch_context(fixture)
        if prematch_context is None:
            missing_prematch_context_fixture_ids.append(fixture.fixture_id)
            continue
        prematch_context_count += 1
        if prematch_context.get("lineup") is not None:
            lineup_feature_count += 1
        if prematch_context.get("availability") is not None:
            availability_feature_count += 1
        if _list_has_items(prematch_context.get("odds_movement")):
            odds_movement_feature_count += 1
        if _list_has_items(prematch_context.get("semantic_signals")):
            semantic_signal_feature_count += 1
        if _has_prematch_source_refs(fixture):
            source_ref_count += 1
    return _HistoricalFeatureCompletenessDiagnostics(
        fixture_count=len(historical_slice.fixtures),
        feature_snapshot_count=feature_snapshot_count,
        prematch_context_count=prematch_context_count,
        lineup_feature_count=lineup_feature_count,
        availability_feature_count=availability_feature_count,
        odds_movement_feature_count=odds_movement_feature_count,
        semantic_signal_feature_count=semantic_signal_feature_count,
        source_ref_count=source_ref_count,
        feature_after_prediction_fixture_ids=feature_after_prediction_fixture_ids,
        feature_not_before_kickoff_fixture_ids=feature_not_before_kickoff_fixture_ids,
        missing_prematch_context_fixture_ids=missing_prematch_context_fixture_ids,
        minimum_feature_data_quality_score=(
            min(feature_data_quality_scores) if feature_data_quality_scores else None
        ),
        average_feature_data_quality_score=(
            sum(feature_data_quality_scores) / len(feature_data_quality_scores)
            if feature_data_quality_scores
            else None
        ),
    )


def _feature_completeness_checks(
    historical_slice: HistoricalRecommendationSlice,
    *,
    diagnostics: _HistoricalFeatureCompletenessDiagnostics,
    options: HistoricalFeatureCompletenessOptions,
) -> list[HistoricalFeatureCompletenessCheck]:
    return [
        _check_minimum(
            name="fixture_count",
            actual=len(historical_slice.fixtures),
            threshold=options.min_fixture_count,
            detail="historical feature completeness needs enough fixtures",
        ),
        _check_minimum(
            name="feature_snapshot_coverage",
            actual=diagnostics.feature_snapshot_coverage,
            threshold=options.min_feature_snapshot_coverage,
            detail="fixtures should carry structured FeatureSnapshot payloads",
        ),
        _check_optional_minimum(
            name="prematch_context_coverage",
            actual=diagnostics.prematch_context_coverage,
            threshold=1.0 if options.require_prematch_context else None,
            detail="feature snapshots should include prematch_context payloads",
        ),
        _check_minimum(
            name="lineup_coverage",
            actual=diagnostics.lineup_coverage,
            threshold=options.min_lineup_coverage,
            detail="fixtures should include expected or confirmed lineup features",
        ),
        _check_minimum(
            name="availability_coverage",
            actual=diagnostics.availability_coverage,
            threshold=options.min_availability_coverage,
            detail="fixtures should include injury/suspension availability features",
        ),
        _check_minimum(
            name="odds_movement_coverage",
            actual=diagnostics.odds_movement_coverage,
            threshold=options.min_odds_movement_coverage,
            detail="fixtures should include pre-match odds movement time series",
        ),
        _check_minimum(
            name="semantic_signal_coverage",
            actual=diagnostics.semantic_signal_coverage,
            threshold=options.min_semantic_signal_coverage,
            detail="fixtures should include structured semantic/news signals when required",
        ),
        _check_minimum(
            name="source_ref_coverage",
            actual=diagnostics.source_ref_coverage,
            threshold=options.min_source_ref_coverage,
            detail="fixtures should keep source refs for feature auditability",
        ),
        _check_optional_maximum(
            name="feature_after_prediction_count",
            actual=len(diagnostics.feature_after_prediction_fixture_ids),
            threshold=0 if options.require_feature_not_after_prediction else None,
            detail="feature snapshot time should not be after prediction time",
        ),
        _check_optional_maximum(
            name="feature_not_before_kickoff_count",
            actual=len(diagnostics.feature_not_before_kickoff_fixture_ids),
            threshold=0 if options.require_feature_before_kickoff else None,
            detail="feature snapshot time should stay before kickoff",
        ),
        _check_optional_minimum(
            name="average_feature_data_quality_score",
            actual=diagnostics.average_feature_data_quality_score,
            threshold=options.min_average_feature_data_quality_score,
            detail="average feature data-quality score should meet the configured floor",
        ),
        _check_optional_minimum(
            name="minimum_feature_data_quality_score",
            actual=diagnostics.minimum_feature_data_quality_score,
            threshold=options.min_feature_data_quality_score,
            detail="minimum feature data-quality score should meet the configured floor",
        ),
    ]


def _summary(
    historical_slice: HistoricalRecommendationSlice,
    *,
    diagnostics: _HistoricalFeatureCompletenessDiagnostics,
    checks: Sequence[HistoricalFeatureCompletenessCheck],
    options: HistoricalFeatureCompletenessOptions,
    status: HistoricalFeatureCompletenessStatus,
    passed: bool,
    warnings: list[str],
) -> dict[str, object]:
    failed_checks = [check.name for check in checks if check.status == "failed"]
    return {
        "calculation_basis": "historical_feature_completeness_v3_1",
        "slice_id": historical_slice.metadata.slice_id,
        "status": status,
        "passed": passed,
        "fixture_count": diagnostics.fixture_count,
        "feature_snapshot_count": diagnostics.feature_snapshot_count,
        "feature_snapshot_coverage": diagnostics.feature_snapshot_coverage,
        "prematch_context_count": diagnostics.prematch_context_count,
        "prematch_context_coverage": diagnostics.prematch_context_coverage,
        "lineup_feature_count": diagnostics.lineup_feature_count,
        "lineup_coverage": diagnostics.lineup_coverage,
        "availability_feature_count": diagnostics.availability_feature_count,
        "availability_coverage": diagnostics.availability_coverage,
        "odds_movement_feature_count": diagnostics.odds_movement_feature_count,
        "odds_movement_coverage": diagnostics.odds_movement_coverage,
        "semantic_signal_feature_count": diagnostics.semantic_signal_feature_count,
        "semantic_signal_coverage": diagnostics.semantic_signal_coverage,
        "source_ref_count": diagnostics.source_ref_count,
        "source_ref_coverage": diagnostics.source_ref_coverage,
        "feature_after_prediction_fixture_ids": (
            diagnostics.feature_after_prediction_fixture_ids
        ),
        "feature_not_before_kickoff_fixture_ids": (
            diagnostics.feature_not_before_kickoff_fixture_ids
        ),
        "missing_prematch_context_fixture_ids": (
            diagnostics.missing_prematch_context_fixture_ids
        ),
        "minimum_feature_data_quality_score": (
            diagnostics.minimum_feature_data_quality_score
        ),
        "average_feature_data_quality_score": (
            diagnostics.average_feature_data_quality_score
        ),
        "failed_checks": failed_checks,
        "warnings": warnings,
        "options": options.model_dump(mode="json"),
    }


def _summary_int(
    result: HistoricalFeatureCompletenessResult,
    key: str,
) -> int:
    value = result.summary_json.get(key)
    if isinstance(value, bool):
        raise ValueError(f"expected integer summary value for {key}")
    if isinstance(value, int):
        return value
    return int(str(value))


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Evaluate structured pre-match feature completeness for historical slices."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, default=None)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--min-fixture-count", type=int, default=1)
    parser.add_argument("--min-feature-snapshot-coverage", type=float, default=1.0)
    parser.add_argument("--min-lineup-coverage", type=float, default=0.0)
    parser.add_argument("--min-availability-coverage", type=float, default=0.0)
    parser.add_argument("--min-odds-movement-coverage", type=float, default=0.0)
    parser.add_argument("--min-semantic-signal-coverage", type=float, default=0.0)
    parser.add_argument("--min-source-ref-coverage", type=float, default=0.0)
    parser.add_argument("--min-average-feature-data-quality-score", type=float)
    parser.add_argument("--min-feature-data-quality-score", type=float)
    parser.add_argument("--allow-missing-prematch-context", action="store_true")
    parser.add_argument("--allow-feature-after-prediction", action="store_true")
    parser.add_argument("--allow-feature-not-before-kickoff", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalFeatureCompletenessOptions:
    return HistoricalFeatureCompletenessOptions(
        min_fixture_count=args.min_fixture_count,
        min_feature_snapshot_coverage=args.min_feature_snapshot_coverage,
        min_lineup_coverage=args.min_lineup_coverage,
        min_availability_coverage=args.min_availability_coverage,
        min_odds_movement_coverage=args.min_odds_movement_coverage,
        min_semantic_signal_coverage=args.min_semantic_signal_coverage,
        min_source_ref_coverage=args.min_source_ref_coverage,
        min_average_feature_data_quality_score=(
            args.min_average_feature_data_quality_score
        ),
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        require_prematch_context=not args.allow_missing_prematch_context,
        require_feature_not_after_prediction=not args.allow_feature_after_prediction,
        require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
    )


def _prematch_context(fixture: HistoricalFixture) -> dict[str, object] | None:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return None
    raw_context = snapshot.features_json.get("prematch_context")
    if isinstance(raw_context, dict):
        return raw_context
    return None


def _has_prematch_source_refs(fixture: HistoricalFixture) -> bool:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return False
    raw_ref = snapshot.source_snapshot_refs.get("prematch")
    if not isinstance(raw_ref, dict):
        return False
    return any(value for value in raw_ref.values())


def _list_has_items(value: object) -> bool:
    return isinstance(value, list) and bool(value)


def _check_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalFeatureCompletenessCheck:
    return HistoricalFeatureCompletenessCheck(
        name=name,
        status=(
            "passed" if actual is not None and actual >= float(threshold) else "failed"
        ),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalFeatureCompletenessCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return _check_minimum(
        name=name,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_maximum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalFeatureCompletenessCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalFeatureCompletenessCheck(
        name=name,
        status=(
            "passed" if actual is not None and actual <= float(threshold) else "failed"
        ),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | None,
    detail: str,
) -> HistoricalFeatureCompletenessCheck:
    return HistoricalFeatureCompletenessCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _completeness_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalFeatureCompletenessOptions,
) -> str:
    payload = {
        "slice_id": historical_slice.metadata.slice_id,
        "as_of_time_utc": historical_slice.as_of_time_utc.isoformat(),
        "fixture_count": len(historical_slice.fixtures),
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_feature_completeness:{historical_slice.metadata.slice_id}:{digest}"


def _coverage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
