from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_poisson_walk_forward import (
    ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS,
    DEFAULT_POISSON_WALK_FORWARD_CALIBRATION_VERSION,
    DEFAULT_POISSON_WALK_FORWARD_FEATURE_VERSION,
    DEFAULT_POISSON_WALK_FORWARD_MODEL_VERSION,
    DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
    DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
    HistoricalPoissonWalkForwardComparisonGroup,
    HistoricalPoissonWalkForwardOptions,
    HistoricalPoissonWalkForwardReport,
    build_historical_poisson_walk_forward_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPrematchFeatureShadowComparisonStatus = Literal["generated"]

DEFAULT_PREMATCH_FEATURE_SHADOW_COMPARISON_ID = (
    "prematch-feature-shadow-comparison-v3.1"
)
DEFAULT_BASELINE_LABEL = "1x2_movement_only"
DEFAULT_CANDIDATE_LABEL = "1x2_plus_asian_handicap_movement"


class HistoricalPrematchFeatureShadowComparisonOptions(BaseModel):
    comparison_id: str = DEFAULT_PREMATCH_FEATURE_SHADOW_COMPARISON_ID
    baseline_label: str = DEFAULT_BASELINE_LABEL
    candidate_label: str = DEFAULT_CANDIDATE_LABEL
    poisson_options: HistoricalPoissonWalkForwardOptions = Field(
        default_factory=lambda: HistoricalPoissonWalkForwardOptions(
            lambda_method="prematch_feature_adjusted",
            min_prematch_feature_data_quality_score=70.0,
        )
    )
    min_validation_count: int = Field(default=1, ge=0)
    max_brier_score_regression: float = Field(default=0.0, ge=0.0)
    max_log_loss_regression: float = Field(default=0.0, ge=0.0)
    max_expected_calibration_error_regression: float = Field(default=0.0, ge=0.0)
    min_hit_rate_delta: float = -1.0


class HistoricalPrematchFeatureShadowMetricDelta(BaseModel):
    metric_name: str
    baseline_value: float | None = None
    candidate_value: float | None = None
    delta: float | None = None
    lower_is_better: bool
    improved: bool | None = None


class HistoricalPrematchFeatureShadowComparisonReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureShadowComparisonStatus
    comparison_id: str
    baseline_label: str
    candidate_label: str
    baseline_report_key: str
    candidate_report_key: str
    baseline_slice_count: int = Field(ge=0)
    candidate_slice_count: int = Field(ge=0)
    baseline_fixture_count: int = Field(ge=0)
    candidate_fixture_count: int = Field(ge=0)
    baseline_validation_count: int = Field(ge=0)
    candidate_validation_count: int = Field(ge=0)
    candidate_asian_handicap_feature_fixture_count: int = Field(ge=0)
    candidate_asian_handicap_feature_coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    passed_non_regression_gate: bool
    metric_deltas: list[HistoricalPrematchFeatureShadowMetricDelta] = (
        Field(default_factory=list)
    )
    metric_deltas_json: dict[str, object] = Field(default_factory=dict)
    baseline_overall: HistoricalPoissonWalkForwardComparisonGroup
    candidate_overall: HistoricalPoissonWalkForwardComparisonGroup
    baseline_summary_json: dict[str, object] = Field(default_factory=dict)
    candidate_summary_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_shadow_comparison_report(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    candidate_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureShadowComparisonOptions | None = None,
) -> HistoricalPrematchFeatureShadowComparisonReport:
    resolved_options = options or HistoricalPrematchFeatureShadowComparisonOptions()
    baseline_report = build_historical_poisson_walk_forward_report(
        baseline_slices,
        options=resolved_options.poisson_options,
    )
    candidate_report = build_historical_poisson_walk_forward_report(
        candidate_slices,
        options=resolved_options.poisson_options,
    )
    metric_deltas = _metric_deltas(baseline_report, candidate_report)
    metric_deltas_json = _metric_deltas_json(metric_deltas)
    ah_feature_count = _asian_handicap_feature_fixture_count(candidate_slices)
    candidate_fixture_count = sum(len(item.fixtures) for item in candidate_slices)
    ah_coverage = (
        ah_feature_count / candidate_fixture_count if candidate_fixture_count else None
    )
    warnings = _comparison_warnings(
        baseline_slices,
        candidate_slices,
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        asian_handicap_feature_fixture_count=ah_feature_count,
        options=resolved_options,
    )
    passed_gate = _passes_non_regression_gate(
        baseline_report,
        candidate_report,
        metric_deltas=metric_deltas,
        options=resolved_options,
    )
    report_key = _report_key(
        baseline_slices,
        candidate_slices,
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_shadow_comparison_v3_1",
        "report_key": report_key,
        "comparison_id": resolved_options.comparison_id,
        "baseline_label": resolved_options.baseline_label,
        "candidate_label": resolved_options.candidate_label,
        "shadow_only": True,
        "poisson_options": resolved_options.poisson_options.model_dump(mode="json"),
        "baseline_report_key": baseline_report.report_key,
        "candidate_report_key": candidate_report.report_key,
        "baseline_validation_count": baseline_report.validation_count,
        "candidate_validation_count": candidate_report.validation_count,
        "candidate_asian_handicap_feature_fixture_count": ah_feature_count,
        "candidate_asian_handicap_feature_coverage": ah_coverage,
        "passed_non_regression_gate": passed_gate,
        "metric_deltas_json": metric_deltas_json,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureShadowComparisonReport(
        report_key=report_key,
        status="generated",
        comparison_id=resolved_options.comparison_id,
        baseline_label=resolved_options.baseline_label,
        candidate_label=resolved_options.candidate_label,
        baseline_report_key=baseline_report.report_key,
        candidate_report_key=candidate_report.report_key,
        baseline_slice_count=len(baseline_slices),
        candidate_slice_count=len(candidate_slices),
        baseline_fixture_count=sum(len(item.fixtures) for item in baseline_slices),
        candidate_fixture_count=candidate_fixture_count,
        baseline_validation_count=baseline_report.validation_count,
        candidate_validation_count=candidate_report.validation_count,
        candidate_asian_handicap_feature_fixture_count=ah_feature_count,
        candidate_asian_handicap_feature_coverage=ah_coverage,
        passed_non_regression_gate=passed_gate,
        metric_deltas=metric_deltas,
        metric_deltas_json=metric_deltas_json,
        baseline_overall=baseline_report.overall,
        candidate_overall=candidate_report.overall,
        baseline_summary_json=baseline_report.summary_json,
        candidate_summary_json=candidate_report.summary_json,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    baseline_loaded = _historical_slices_from_args(
        slice_paths=args.baseline_slice_paths,
        suite_manifest=args.baseline_suite_manifest,
        include_disabled=args.include_disabled,
    )
    candidate_loaded = _historical_slices_from_args(
        slice_paths=args.candidate_slice_paths,
        suite_manifest=args.candidate_suite_manifest,
        include_disabled=args.include_disabled,
    )
    report = build_historical_prematch_feature_shadow_comparison_report(
        baseline_loaded.slices,
        candidate_loaded.slices,
        options=_options_from_args(args),
    )
    if baseline_loaded.manifest_result is not None:
        report.summary_json["baseline_suite_manifest"] = _manifest_summary(
            baseline_loaded.manifest_result
        )
    if candidate_loaded.manifest_result is not None:
        report.summary_json["candidate_suite_manifest"] = _manifest_summary(
            candidate_loaded.manifest_result
        )
    if baseline_loaded.warnings:
        report.warnings.extend(
            f"baseline:{warning}" for warning in baseline_loaded.warnings
        )
        report.summary_json["baseline_manifest_warnings"] = baseline_loaded.warnings
    if candidate_loaded.warnings:
        report.warnings.extend(
            f"candidate:{warning}" for warning in candidate_loaded.warnings
        )
        report.summary_json["candidate_manifest_warnings"] = candidate_loaded.warnings
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


def _metric_deltas(
    baseline_report: HistoricalPoissonWalkForwardReport,
    candidate_report: HistoricalPoissonWalkForwardReport,
) -> list[HistoricalPrematchFeatureShadowMetricDelta]:
    return [
        _metric_delta(
            "hit_rate",
            baseline_report.overall.candidate.hit_rate,
            candidate_report.overall.candidate.hit_rate,
            lower_is_better=False,
        ),
        _metric_delta(
            "brier_score",
            baseline_report.overall.candidate.brier_score,
            candidate_report.overall.candidate.brier_score,
            lower_is_better=True,
        ),
        _metric_delta(
            "log_loss",
            baseline_report.overall.candidate.log_loss,
            candidate_report.overall.candidate.log_loss,
            lower_is_better=True,
        ),
        _metric_delta(
            "average_actual_probability",
            baseline_report.overall.candidate.average_actual_probability,
            candidate_report.overall.candidate.average_actual_probability,
            lower_is_better=False,
        ),
        _metric_delta(
            "expected_calibration_error",
            baseline_report.overall.candidate.expected_calibration_error,
            candidate_report.overall.candidate.expected_calibration_error,
            lower_is_better=True,
        ),
    ]


def _metric_delta(
    metric_name: str,
    baseline_value: float | None,
    candidate_value: float | None,
    *,
    lower_is_better: bool,
) -> HistoricalPrematchFeatureShadowMetricDelta:
    delta = (
        candidate_value - baseline_value
        if baseline_value is not None and candidate_value is not None
        else None
    )
    improved = None
    if delta is not None:
        improved = delta < 0 if lower_is_better else delta > 0
    return HistoricalPrematchFeatureShadowMetricDelta(
        metric_name=metric_name,
        baseline_value=baseline_value,
        candidate_value=candidate_value,
        delta=delta,
        lower_is_better=lower_is_better,
        improved=improved,
    )


def _metric_deltas_json(
    metric_deltas: Sequence[HistoricalPrematchFeatureShadowMetricDelta],
) -> dict[str, object]:
    return {
        metric.metric_name: {
            "baseline_value": metric.baseline_value,
            "candidate_value": metric.candidate_value,
            "delta": metric.delta,
            "lower_is_better": metric.lower_is_better,
            "improved": metric.improved,
        }
        for metric in metric_deltas
    }


def _passes_non_regression_gate(
    baseline_report: HistoricalPoissonWalkForwardReport,
    candidate_report: HistoricalPoissonWalkForwardReport,
    *,
    metric_deltas: Sequence[HistoricalPrematchFeatureShadowMetricDelta],
    options: HistoricalPrematchFeatureShadowComparisonOptions,
) -> bool:
    if candidate_report.validation_count < options.min_validation_count:
        return False
    if baseline_report.validation_count < options.min_validation_count:
        return False
    if candidate_report.validation_count != baseline_report.validation_count:
        return False
    thresholds = {
        "brier_score": options.max_brier_score_regression,
        "log_loss": options.max_log_loss_regression,
        "expected_calibration_error": (
            options.max_expected_calibration_error_regression
        ),
    }
    for metric in metric_deltas:
        if metric.delta is None:
            continue
        if metric.metric_name == "hit_rate" and metric.delta < options.min_hit_rate_delta:
            return False
        threshold = thresholds.get(metric.metric_name)
        if threshold is not None and metric.delta > threshold:
            return False
    return True


def _comparison_warnings(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    candidate_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_report: HistoricalPoissonWalkForwardReport,
    candidate_report: HistoricalPoissonWalkForwardReport,
    asian_handicap_feature_fixture_count: int,
    options: HistoricalPrematchFeatureShadowComparisonOptions,
) -> list[str]:
    warnings: list[str] = []
    if not baseline_slices:
        warnings.append("prematch_feature_shadow_comparison:no_baseline_slices")
    if not candidate_slices:
        warnings.append("prematch_feature_shadow_comparison:no_candidate_slices")
    if _fixture_identity_set(baseline_slices) != _fixture_identity_set(candidate_slices):
        warnings.append("prematch_feature_shadow_comparison:fixture_identity_mismatch")
    if baseline_report.validation_count < options.min_validation_count:
        warnings.append("prematch_feature_shadow_comparison:baseline_validation_below_minimum")
    if candidate_report.validation_count < options.min_validation_count:
        warnings.append("prematch_feature_shadow_comparison:candidate_validation_below_minimum")
    if candidate_report.validation_count != baseline_report.validation_count:
        warnings.append("prematch_feature_shadow_comparison:validation_count_mismatch")
    if asian_handicap_feature_fixture_count == 0:
        warnings.append("prematch_feature_shadow_comparison:no_asian_handicap_features")
    if options.poisson_options.lambda_method != "prematch_feature_adjusted":
        warnings.append("prematch_feature_shadow_comparison:lambda_method_not_prematch_feature")
    return warnings


def _asian_handicap_feature_fixture_count(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    return sum(
        1
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
        if _fixture_has_asian_handicap_feature(fixture)
    )


def _fixture_has_asian_handicap_feature(fixture: HistoricalFixture) -> bool:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return False
    prematch_context = _mapping(snapshot.features_json.get("prematch_context"))
    if prematch_context is None:
        return False
    odds_movements = prematch_context.get("odds_movement")
    if not isinstance(odds_movements, list):
        return False
    return any(
        isinstance(item, Mapping) and item.get("market_type") == "asian_handicap"
        for item in odds_movements
    )


def _fixture_identity_set(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> set[str]:
    return {
        "|".join(
            [
                fixture.competition_id,
                fixture.kickoff_time_utc.isoformat(),
                fixture.home_team_name,
                fixture.away_team_name,
            ]
        )
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    }


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _report_key(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    candidate_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_report: HistoricalPoissonWalkForwardReport,
    candidate_report: HistoricalPoissonWalkForwardReport,
    options: HistoricalPrematchFeatureShadowComparisonOptions,
) -> str:
    payload = {
        "comparison_id": options.comparison_id,
        "baseline_label": options.baseline_label,
        "candidate_label": options.candidate_label,
        "baseline_slice_ids": [item.metadata.slice_id for item in baseline_slices],
        "candidate_slice_ids": [item.metadata.slice_id for item in candidate_slices],
        "baseline_report_key": baseline_report.report_key,
        "candidate_report_key": candidate_report.report_key,
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"prematch_feature_shadow_comparison:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Compare two historical prematch-feature Poisson runs, commonly "
            "1X2-only movement versus 1X2 plus Asian-handicap movement."
        )
    )
    parser.add_argument("--baseline-suite-manifest", type=Path)
    parser.add_argument("--candidate-suite-manifest", type=Path)
    parser.add_argument(
        "--baseline-slice-path",
        dest="baseline_slice_paths",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument(
        "--candidate-slice-path",
        dest="candidate_slice_paths",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--comparison-id",
        default=DEFAULT_PREMATCH_FEATURE_SHADOW_COMPARISON_ID,
    )
    parser.add_argument("--baseline-label", default=DEFAULT_BASELINE_LABEL)
    parser.add_argument("--candidate-label", default=DEFAULT_CANDIDATE_LABEL)
    parser.add_argument("--min-validation-count", type=int, default=1)
    parser.add_argument("--max-brier-score-regression", type=float, default=0.0)
    parser.add_argument("--max-log-loss-regression", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-regression",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-hit-rate-delta", type=float, default=-1.0)
    _add_poisson_option_args(parser)
    args = parser.parse_args(argv)
    if not args.baseline_slice_paths and args.baseline_suite_manifest is None:
        parser.error("provide --baseline-slice-path or --baseline-suite-manifest")
    if not args.candidate_slice_paths and args.candidate_suite_manifest is None:
        parser.error("provide --candidate-slice-path or --candidate-suite-manifest")
    return args


def _add_poisson_option_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--lambda-method",
        choices=[
            "rolling_strength",
            "enhanced_weighted_home_away",
            "shrunken_weighted_home_away",
            "hierarchical_weighted_home_away",
            "season_weighted_home_away",
            "ema_form_adjusted",
            "form_rest_adjusted",
            "prematch_feature_adjusted",
        ],
        default="prematch_feature_adjusted",
    )
    parser.add_argument(
        "--score-grid-family",
        choices=["poisson", "dixon_coles_low_score"],
        default="poisson",
    )
    parser.add_argument("--dixon-coles-rho", type=float, default=-0.05)
    parser.add_argument("--min-prior-matches", type=int, default=30)
    parser.add_argument("--min-team-matches", type=int, default=5)
    parser.add_argument("--max-training-results", type=int, default=380)
    parser.add_argument("--max-goals", type=int, default=8)
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=30)
    parser.add_argument("--recency-half-life-days", type=float)
    parser.add_argument("--home-away-split-weight", type=float, default=0.0)
    parser.add_argument(
        "--strength-shrinkage-matches",
        type=float,
        default=DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
    )
    parser.add_argument("--prior-season-weight", type=float, default=0.35)
    parser.add_argument("--draw-correction-weight", type=float, default=0.0)
    parser.add_argument("--form-window-matches", type=int, default=6)
    parser.add_argument("--ema-form-half-life-matches", type=float, default=3.0)
    parser.add_argument("--form-adjustment-weight", type=float, default=0.0)
    parser.add_argument("--rest-adjustment-weight", type=float, default=0.0)
    parser.add_argument("--rest-reference-days", type=float, default=6.0)
    parser.add_argument("--max-lambda-adjustment", type=float, default=0.25)
    parser.add_argument("--min-prematch-feature-data-quality-score", type=float, default=70.0)
    parser.add_argument("--prematch-feature-odds-movement-weight", type=float, default=0.50)
    parser.add_argument(
        "--prematch-feature-asian-handicap-movement-weight",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--prematch-feature-min-asian-handicap-probability-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-weight",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-min-asian-handicap-line-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-scale",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--prematch-feature-asian-handicap-line-movement-transform",
        choices=ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS,
        default="linear",
    )
    parser.add_argument("--prematch-feature-lineup-strength-weight", type=float, default=0.08)
    parser.add_argument("--prematch-feature-availability-risk-weight", type=float, default=0.06)
    parser.add_argument("--prematch-feature-draw-risk-weight", type=float, default=0.05)
    parser.add_argument("--prematch-feature-semantic-risk-weight", type=float, default=0.04)
    parser.add_argument(
        "--max-prematch-feature-lambda-adjustment",
        type=float,
        default=DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
    )
    parser.add_argument("--allow-missing-prematch-feature-fallback", action="store_true")
    parser.add_argument("--allow-feature-after-prediction", action="store_true")
    parser.add_argument("--allow-feature-not-before-kickoff", action="store_true")
    parser.add_argument("--model-version", default=DEFAULT_POISSON_WALK_FORWARD_MODEL_VERSION)
    parser.add_argument(
        "--feature-version",
        default=DEFAULT_POISSON_WALK_FORWARD_FEATURE_VERSION,
    )
    parser.add_argument(
        "--calibration-version",
        default=DEFAULT_POISSON_WALK_FORWARD_CALIBRATION_VERSION,
    )
    parser.add_argument("--prediction-sample-limit", type=int, default=20)


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureShadowComparisonOptions:
    return HistoricalPrematchFeatureShadowComparisonOptions(
        comparison_id=args.comparison_id,
        baseline_label=args.baseline_label,
        candidate_label=args.candidate_label,
        min_validation_count=args.min_validation_count,
        max_brier_score_regression=args.max_brier_score_regression,
        max_log_loss_regression=args.max_log_loss_regression,
        max_expected_calibration_error_regression=(
            args.max_expected_calibration_error_regression
        ),
        min_hit_rate_delta=args.min_hit_rate_delta,
        poisson_options=HistoricalPoissonWalkForwardOptions(
            lambda_method=args.lambda_method,
            score_grid_family=args.score_grid_family,
            dixon_coles_rho=args.dixon_coles_rho,
            min_prior_matches=args.min_prior_matches,
            min_team_matches=args.min_team_matches,
            max_training_results=args.max_training_results,
            max_goals=args.max_goals,
            bucket_size=args.bucket_size,
            min_bucket_sample_size=args.min_bucket_sample_size,
            recency_half_life_days=args.recency_half_life_days,
            home_away_split_weight=args.home_away_split_weight,
            strength_shrinkage_matches=args.strength_shrinkage_matches,
            prior_season_weight=args.prior_season_weight,
            draw_correction_weight=args.draw_correction_weight,
            form_window_matches=args.form_window_matches,
            ema_form_half_life_matches=args.ema_form_half_life_matches,
            form_adjustment_weight=args.form_adjustment_weight,
            rest_adjustment_weight=args.rest_adjustment_weight,
            rest_reference_days=args.rest_reference_days,
            max_lambda_adjustment=args.max_lambda_adjustment,
            min_prematch_feature_data_quality_score=(
                args.min_prematch_feature_data_quality_score
            ),
            prematch_feature_odds_movement_weight=(
                args.prematch_feature_odds_movement_weight
            ),
            prematch_feature_asian_handicap_movement_weight=(
                args.prematch_feature_asian_handicap_movement_weight
            ),
            prematch_feature_min_asian_handicap_probability_delta=(
                args.prematch_feature_min_asian_handicap_probability_delta
            ),
            prematch_feature_asian_handicap_line_movement_weight=(
                args.prematch_feature_asian_handicap_line_movement_weight
            ),
            prematch_feature_min_asian_handicap_line_delta=(
                args.prematch_feature_min_asian_handicap_line_delta
            ),
            prematch_feature_asian_handicap_line_movement_scale=(
                args.prematch_feature_asian_handicap_line_movement_scale
            ),
            prematch_feature_asian_handicap_line_movement_transform=(
                args.prematch_feature_asian_handicap_line_movement_transform
            ),
            prematch_feature_lineup_strength_weight=(
                args.prematch_feature_lineup_strength_weight
            ),
            prematch_feature_availability_risk_weight=(
                args.prematch_feature_availability_risk_weight
            ),
            prematch_feature_draw_risk_weight=args.prematch_feature_draw_risk_weight,
            prematch_feature_semantic_risk_weight=(
                args.prematch_feature_semantic_risk_weight
            ),
            max_prematch_feature_lambda_adjustment=(
                args.max_prematch_feature_lambda_adjustment
            ),
            allow_missing_prematch_feature_fallback=(
                args.allow_missing_prematch_feature_fallback
            ),
            require_feature_not_after_prediction=not args.allow_feature_after_prediction,
            require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
            model_version=args.model_version,
            feature_version=args.feature_version,
            calibration_version=args.calibration_version,
            prediction_sample_limit=args.prediction_sample_limit,
        ),
    )


def _historical_slices_from_args(
    *,
    slice_paths: Sequence[Path],
    suite_manifest: Path | None,
    include_disabled: bool,
) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            suite_manifest,
            include_disabled=include_disabled,
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }
