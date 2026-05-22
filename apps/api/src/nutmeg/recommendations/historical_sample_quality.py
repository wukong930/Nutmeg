from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalRecommendationSampleQualityCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalRecommendationSampleQualityStatus = Literal["passed", "failed"]

DEFAULT_REQUIRED_1X2_OUTCOMES = ("home_win", "draw", "away_win")


class HistoricalRecommendationSampleQualityOptions(BaseModel):
    min_fixture_count: int = Field(default=1, ge=0)
    require_unique_fixture_ids: bool = True
    require_unique_kickoff_matchups: bool = True
    require_prediction_not_after_as_of: bool = True
    require_kickoff_after_as_of: bool = True
    require_1x2_complete: bool = True
    required_1x2_outcomes: tuple[str, ...] = DEFAULT_REQUIRED_1X2_OUTCOMES
    probability_sum_tolerance: float = Field(default=0.02, ge=0.0)
    require_decimal_odds: bool = True
    require_market_probability: bool = False
    min_data_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)


class HistoricalRecommendationSampleQualityCheck(BaseModel):
    name: str
    status: HistoricalRecommendationSampleQualityCheckStatus
    actual: float | int | str | None = None
    threshold: float | int | str | None = None
    detail: str


class HistoricalRecommendationSampleQualityResult(BaseModel):
    sample_key: str
    slice_id: str
    status: HistoricalRecommendationSampleQualityStatus
    passed: bool
    checks: list[HistoricalRecommendationSampleQualityCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationSampleQualitySuiteResult(BaseModel):
    status: HistoricalRecommendationSampleQualityStatus
    passed: bool
    slice_count: int = Field(ge=0)
    results: list[HistoricalRecommendationSampleQualityResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def evaluate_historical_recommendation_sample_quality(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationSampleQualityOptions | None = None,
) -> HistoricalRecommendationSampleQualityResult:
    resolved_options = options or HistoricalRecommendationSampleQualityOptions()
    diagnostics = _sample_quality_diagnostics(
        historical_slice,
        options=resolved_options,
    )
    checks = _sample_quality_checks(
        historical_slice,
        options=resolved_options,
        diagnostics=diagnostics,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: HistoricalRecommendationSampleQualityStatus = (
        "passed" if passed else "failed"
    )
    warnings = [
        f"historical_sample_quality:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary = {
        "calculation_basis": "historical_recommendation_sample_quality_v3_1",
        "slice_id": historical_slice.metadata.slice_id,
        "status": status,
        "passed": passed,
        "fixture_count": len(historical_slice.fixtures),
        "prediction_count": sum(
            len(fixture.predictions) for fixture in historical_slice.fixtures
        ),
        "duplicate_fixture_id_count": len(diagnostics.duplicate_fixture_ids),
        "duplicate_kickoff_matchup_count": len(diagnostics.duplicate_kickoff_matchups),
        "prediction_after_as_of_count": len(diagnostics.prediction_after_as_of_fixture_ids),
        "kickoff_not_after_as_of_count": len(
            diagnostics.kickoff_not_after_as_of_fixture_ids
        ),
        "complete_1x2_fixture_count": diagnostics.complete_1x2_fixture_count,
        "missing_1x2_fixture_ids": diagnostics.missing_1x2_fixture_ids,
        "unexpected_1x2_outcome_count": diagnostics.unexpected_1x2_outcome_count,
        "max_1x2_probability_sum_error": diagnostics.max_1x2_probability_sum_error,
        "decimal_odds_missing_count": diagnostics.decimal_odds_missing_count,
        "market_probability_missing_count": diagnostics.market_probability_missing_count,
        "minimum_data_quality_score": diagnostics.minimum_data_quality_score,
        "failed_checks": [check.name for check in failed_checks],
        "warnings": warnings,
    }
    return HistoricalRecommendationSampleQualityResult(
        sample_key=_sample_key(historical_slice, options=resolved_options),
        slice_id=historical_slice.metadata.slice_id,
        status=status,
        passed=passed,
        checks=checks,
        warnings=warnings,
        summary_json=summary,
    )


def evaluate_historical_recommendation_sample_quality_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationSampleQualityOptions | None = None,
) -> HistoricalRecommendationSampleQualitySuiteResult:
    results = [
        evaluate_historical_recommendation_sample_quality(
            historical_slice,
            options=options,
        )
        for historical_slice in historical_slices
    ]
    passed = all(result.passed for result in results)
    status: HistoricalRecommendationSampleQualityStatus = (
        "passed" if passed else "failed"
    )
    warnings = [
        warning for result in results for warning in result.warnings
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_recommendation_sample_quality_suite_v3_1",
        "status": status,
        "passed": passed,
        "slice_count": len(historical_slices),
        "passed_slice_count": sum(1 for result in results if result.passed),
        "failed_slice_count": sum(1 for result in results if not result.passed),
        "failed_slice_ids": [result.slice_id for result in results if not result.passed],
        "warnings": warnings,
    }
    return HistoricalRecommendationSampleQualitySuiteResult(
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
        bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
        historical_slices = [*bundle.slices, *historical_slices]
    result = evaluate_historical_recommendation_sample_quality_suite(
        historical_slices,
        options=_options_from_args(args),
    )
    print(
        dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


class _SampleQualityDiagnostics(BaseModel):
    duplicate_fixture_ids: list[str] = Field(default_factory=list)
    duplicate_kickoff_matchups: list[str] = Field(default_factory=list)
    prediction_after_as_of_fixture_ids: list[str] = Field(default_factory=list)
    kickoff_not_after_as_of_fixture_ids: list[str] = Field(default_factory=list)
    complete_1x2_fixture_count: int = Field(ge=0)
    missing_1x2_fixture_ids: list[str] = Field(default_factory=list)
    unexpected_1x2_outcome_count: int = Field(ge=0)
    max_1x2_probability_sum_error: float = Field(ge=0.0)
    decimal_odds_missing_count: int = Field(ge=0)
    market_probability_missing_count: int = Field(ge=0)
    minimum_data_quality_score: float | None = None


def _sample_quality_diagnostics(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationSampleQualityOptions,
) -> _SampleQualityDiagnostics:
    fixture_ids = [fixture.fixture_id for fixture in historical_slice.fixtures]
    duplicate_fixture_ids = _duplicates(fixture_ids)
    duplicate_kickoff_matchups = _duplicates(
        [
            "|".join(
                [
                    _aware_utc(fixture.kickoff_time_utc).isoformat(),
                    fixture.home_team_name.strip().casefold(),
                    fixture.away_team_name.strip().casefold(),
                ]
            )
            for fixture in historical_slice.fixtures
        ]
    )
    prediction_after_as_of = [
        fixture.fixture_id
        for fixture in historical_slice.fixtures
        if _aware_utc(fixture.prediction_time_utc)
        > _aware_utc(historical_slice.as_of_time_utc)
    ]
    kickoff_not_after_as_of = [
        fixture.fixture_id
        for fixture in historical_slice.fixtures
        if _aware_utc(fixture.kickoff_time_utc)
        <= _aware_utc(historical_slice.as_of_time_utc)
    ]
    complete_1x2_count = 0
    missing_1x2_fixture_ids: list[str] = []
    unexpected_1x2_outcome_count = 0
    max_probability_sum_error = 0.0
    decimal_odds_missing_count = 0
    market_probability_missing_count = 0
    data_quality_scores: list[float] = []
    required_outcomes = set(options.required_1x2_outcomes)
    for fixture in historical_slice.fixtures:
        one_x_two_predictions = [
            prediction
            for prediction in fixture.predictions
            if prediction.market_type == "1x2"
        ]
        outcomes = {prediction.outcome for prediction in one_x_two_predictions}
        if required_outcomes.issubset(outcomes):
            complete_1x2_count += 1
        else:
            missing_1x2_fixture_ids.append(fixture.fixture_id)
        unexpected_1x2_outcome_count += len(outcomes - required_outcomes)
        if one_x_two_predictions:
            probability_sum = sum(
                prediction.probability for prediction in one_x_two_predictions
            )
            max_probability_sum_error = max(
                max_probability_sum_error,
                abs(probability_sum - 1.0),
            )
        for prediction in fixture.predictions:
            if prediction.decimal_odds <= 1.0:
                decimal_odds_missing_count += 1
            if prediction.market_probability is None:
                market_probability_missing_count += 1
            data_quality_scores.append(prediction.data_quality_score)
    return _SampleQualityDiagnostics(
        duplicate_fixture_ids=duplicate_fixture_ids,
        duplicate_kickoff_matchups=duplicate_kickoff_matchups,
        prediction_after_as_of_fixture_ids=prediction_after_as_of,
        kickoff_not_after_as_of_fixture_ids=kickoff_not_after_as_of,
        complete_1x2_fixture_count=complete_1x2_count,
        missing_1x2_fixture_ids=missing_1x2_fixture_ids,
        unexpected_1x2_outcome_count=unexpected_1x2_outcome_count,
        max_1x2_probability_sum_error=max_probability_sum_error,
        decimal_odds_missing_count=decimal_odds_missing_count,
        market_probability_missing_count=market_probability_missing_count,
        minimum_data_quality_score=min(data_quality_scores) if data_quality_scores else None,
    )


def _sample_quality_checks(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationSampleQualityOptions,
    diagnostics: _SampleQualityDiagnostics,
) -> list[HistoricalRecommendationSampleQualityCheck]:
    return [
        _check_minimum(
            name="fixture_count",
            actual=len(historical_slice.fixtures),
            threshold=options.min_fixture_count,
            detail="sample should contain enough fixtures",
        ),
        _check_optional_maximum(
            name="duplicate_fixture_id_count",
            actual=len(diagnostics.duplicate_fixture_ids),
            threshold=0 if options.require_unique_fixture_ids else None,
            detail="fixture IDs should be unique inside a sample slice",
        ),
        _check_optional_maximum(
            name="duplicate_kickoff_matchup_count",
            actual=len(diagnostics.duplicate_kickoff_matchups),
            threshold=0 if options.require_unique_kickoff_matchups else None,
            detail="same kickoff/home/away matchup should not be repeated",
        ),
        _check_optional_maximum(
            name="prediction_after_as_of_count",
            actual=len(diagnostics.prediction_after_as_of_fixture_ids),
            threshold=0 if options.require_prediction_not_after_as_of else None,
            detail="prediction timestamps should be at or before as-of time",
        ),
        _check_optional_maximum(
            name="kickoff_not_after_as_of_count",
            actual=len(diagnostics.kickoff_not_after_as_of_fixture_ids),
            threshold=0 if options.require_kickoff_after_as_of else None,
            detail="fixture kickoff timestamps should be after as-of time",
        ),
        _check_optional_minimum(
            name="complete_1x2_fixture_count",
            actual=diagnostics.complete_1x2_fixture_count,
            threshold=(
                len(historical_slice.fixtures)
                if options.require_1x2_complete
                else None
            ),
            detail="every fixture should include home/draw/away 1X2 outcomes",
        ),
        _check_optional_maximum(
            name="unexpected_1x2_outcome_count",
            actual=diagnostics.unexpected_1x2_outcome_count,
            threshold=0 if options.require_1x2_complete else None,
            detail="1X2 predictions should not include unexpected outcomes",
        ),
        _check_optional_maximum(
            name="max_1x2_probability_sum_error",
            actual=diagnostics.max_1x2_probability_sum_error,
            threshold=(
                options.probability_sum_tolerance
                if options.require_1x2_complete
                else None
            ),
            detail="1X2 probability sums should stay within tolerance",
        ),
        _check_optional_maximum(
            name="decimal_odds_missing_count",
            actual=diagnostics.decimal_odds_missing_count,
            threshold=0 if options.require_decimal_odds else None,
            detail="all predictions should include valid decimal odds",
        ),
        _check_optional_maximum(
            name="market_probability_missing_count",
            actual=diagnostics.market_probability_missing_count,
            threshold=0 if options.require_market_probability else None,
            detail="all predictions should include market implied probability when required",
        ),
        _check_optional_minimum(
            name="minimum_data_quality_score",
            actual=diagnostics.minimum_data_quality_score,
            threshold=options.min_data_quality_score,
            detail="minimum prediction data quality should meet the configured floor",
        ),
    ]


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Evaluate frozen historical recommendation sample quality."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, default=None)
    parser.add_argument("--min-fixture-count", type=int, default=1)
    parser.add_argument("--allow-duplicate-fixture-ids", action="store_true")
    parser.add_argument("--allow-duplicate-kickoff-matchups", action="store_true")
    parser.add_argument("--allow-prediction-after-as-of", action="store_true")
    parser.add_argument("--allow-kickoff-not-after-as-of", action="store_true")
    parser.add_argument("--allow-incomplete-1x2", action="store_true")
    parser.add_argument("--probability-sum-tolerance", type=float, default=0.02)
    parser.add_argument("--allow-missing-decimal-odds", action="store_true")
    parser.add_argument("--require-market-probability", action="store_true")
    parser.add_argument("--min-data-quality-score", type=float, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalRecommendationSampleQualityOptions:
    return HistoricalRecommendationSampleQualityOptions(
        min_fixture_count=args.min_fixture_count,
        require_unique_fixture_ids=not args.allow_duplicate_fixture_ids,
        require_unique_kickoff_matchups=not args.allow_duplicate_kickoff_matchups,
        require_prediction_not_after_as_of=not args.allow_prediction_after_as_of,
        require_kickoff_after_as_of=not args.allow_kickoff_not_after_as_of,
        require_1x2_complete=not args.allow_incomplete_1x2,
        probability_sum_tolerance=args.probability_sum_tolerance,
        require_decimal_odds=not args.allow_missing_decimal_odds,
        require_market_probability=args.require_market_probability,
        min_data_quality_score=args.min_data_quality_score,
    )


def _check_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalRecommendationSampleQualityCheck:
    return HistoricalRecommendationSampleQualityCheck(
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
) -> HistoricalRecommendationSampleQualityCheck:
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
) -> HistoricalRecommendationSampleQualityCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalRecommendationSampleQualityCheck(
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
) -> HistoricalRecommendationSampleQualityCheck:
    return HistoricalRecommendationSampleQualityCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _sample_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationSampleQualityOptions,
) -> str:
    payload = "|".join(
        [
            historical_slice.metadata.slice_id,
            historical_slice.as_of_time_utc.isoformat(),
            str(options.min_fixture_count),
            str(options.require_1x2_complete),
            str(options.probability_sum_tolerance),
            str(options.require_market_probability),
            str(options.min_data_quality_score),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_recommendation_sample_quality:{historical_slice.metadata.slice_id}:{digest}"


def _duplicates(values: Sequence[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
