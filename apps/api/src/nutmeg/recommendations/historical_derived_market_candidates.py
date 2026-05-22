from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from os.path import relpath
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

from nutmeg.market_resolver import score_grid_to_market_probabilities
from nutmeg.modeling import build_poisson_score_grid
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMarketType

DEFAULT_HISTORICAL_DERIVED_MARKET_CANDIDATE_ID = (
    "historical-derived-market-candidates-v3.1"
)


class HistoricalDerivedMarketCandidateOptions(BaseModel):
    derivation_id: str = DEFAULT_HISTORICAL_DERIVED_MARKET_CANDIDATE_ID
    output_slice_id_suffix: str = "derived_markets_v1"
    cn_handicaps: tuple[int, ...] = (-1, 1)
    european_handicaps: tuple[int, ...] = (-1, 1)
    correct_score_top_n: int = Field(default=5, ge=0, le=20)
    max_goals: int = Field(default=8, ge=2, le=20)
    min_probability: float = Field(default=0.005, ge=0.0, le=1.0)
    market_margin: float = Field(default=0.0, ge=0.0, le=0.30)
    preserve_existing: bool = True


class HistoricalDerivedMarketCandidateReport(BaseModel):
    report_key: str
    derivation_id: str
    source_slice_id: str
    output_slice_id: str
    fixture_count: int = Field(ge=0)
    source_prediction_count: int = Field(ge=0)
    output_prediction_count: int = Field(ge=0)
    generated_prediction_count: int = Field(ge=0)
    generated_fixture_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    generated_prediction_count_by_market: dict[str, int] = Field(default_factory=dict)
    generated_fixture_count_by_market: dict[str, int] = Field(default_factory=dict)
    lambda_source_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalDerivedMarketCandidateBuildResult(BaseModel):
    historical_slice: HistoricalRecommendationSlice
    report: HistoricalDerivedMarketCandidateReport


class HistoricalDerivedMarketCandidateSuiteReport(BaseModel):
    report_key: str
    derivation_id: str
    source_suite_id: str
    output_suite_id: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    source_prediction_count: int = Field(ge=0)
    output_prediction_count: int = Field(ge=0)
    generated_prediction_count: int = Field(ge=0)
    generated_fixture_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    generated_prediction_count_by_market: dict[str, int] = Field(default_factory=dict)
    generated_fixture_count_by_market: dict[str, int] = Field(default_factory=dict)
    lambda_source_counts: dict[str, int] = Field(default_factory=dict)
    output_slice_paths: list[str] = Field(default_factory=list)
    slice_reports: list[HistoricalDerivedMarketCandidateReport] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalDerivedMarketCandidateSuiteBuildResult(BaseModel):
    manifest: HistoricalRecommendationSuiteManifest
    historical_slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    report: HistoricalDerivedMarketCandidateSuiteReport


def build_historical_derived_market_candidate_slice(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalDerivedMarketCandidateOptions | None = None,
) -> HistoricalDerivedMarketCandidateBuildResult:
    resolved_options = options or HistoricalDerivedMarketCandidateOptions()
    generated_count_by_market: Counter[str] = Counter()
    generated_fixture_by_market: Counter[str] = Counter()
    lambda_source_counts: Counter[str] = Counter()
    warnings: list[str] = []
    derived_fixtures: list[HistoricalFixture] = []
    generated_fixture_count = 0
    skipped_fixture_count = 0

    for fixture in historical_slice.fixtures:
        fixture_result = _derive_fixture_predictions(fixture, options=resolved_options)
        lambda_source_counts[fixture_result.lambda_source] += 1
        if fixture_result.warnings:
            warnings.extend(fixture_result.warnings)
        if fixture_result.generated_predictions:
            generated_fixture_count += 1
            generated_count_by_market.update(
                prediction.market_type for prediction in fixture_result.generated_predictions
            )
            generated_fixture_by_market.update(
                {
                    prediction.market_type
                    for prediction in fixture_result.generated_predictions
                }
            )
        else:
            skipped_fixture_count += 1
        derived_fixtures.append(
            fixture.model_copy(
                update={
                    "predictions": [
                        *fixture.predictions,
                        *fixture_result.generated_predictions,
                    ]
                }
            )
        )

    output_slice_id = _output_slice_id(historical_slice, options=resolved_options)
    derived_slice = historical_slice.model_copy(
        update={
            "metadata": historical_slice.metadata.model_copy(
                update={
                    "slice_id": output_slice_id,
                    "name": f"{historical_slice.metadata.name} Derived Markets",
                    "prediction_source": (
                        f"{historical_slice.metadata.prediction_source}; "
                        "shadow derived handicap/correct-score candidates"
                    ),
                    "notes": [
                        *historical_slice.metadata.notes,
                        (
                            "Shadow derived markets generated from pre-match "
                            "lambda metadata or 1X2 probability heuristic; "
                            "not provider-settled paid market odds."
                        ),
                    ],
                }
            ),
            "fixtures": derived_fixtures,
        }
    )
    source_prediction_count = sum(len(fixture.predictions) for fixture in historical_slice.fixtures)
    output_prediction_count = sum(len(fixture.predictions) for fixture in derived_fixtures)
    generated_prediction_count = output_prediction_count - source_prediction_count
    report_key = _report_key(
        historical_slice,
        output_slice_id=output_slice_id,
        options=resolved_options,
        generated_count_by_market=generated_count_by_market,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_derived_market_candidates_v3_1",
        "report_key": report_key,
        "derivation_id": resolved_options.derivation_id,
        "source_slice_id": historical_slice.metadata.slice_id,
        "output_slice_id": output_slice_id,
        "fixture_count": len(historical_slice.fixtures),
        "source_prediction_count": source_prediction_count,
        "output_prediction_count": output_prediction_count,
        "generated_prediction_count": generated_prediction_count,
        "generated_prediction_count_by_market": dict(
            sorted(generated_count_by_market.items())
        ),
        "generated_fixture_count_by_market": dict(
            sorted(generated_fixture_by_market.items())
        ),
        "lambda_source_counts": dict(sorted(lambda_source_counts.items())),
        "warnings": _dedupe_strings(warnings),
    }
    return HistoricalDerivedMarketCandidateBuildResult(
        historical_slice=derived_slice,
        report=HistoricalDerivedMarketCandidateReport(
            report_key=report_key,
            derivation_id=resolved_options.derivation_id,
            source_slice_id=historical_slice.metadata.slice_id,
            output_slice_id=output_slice_id,
            fixture_count=len(historical_slice.fixtures),
            source_prediction_count=source_prediction_count,
            output_prediction_count=output_prediction_count,
            generated_prediction_count=generated_prediction_count,
            generated_fixture_count=generated_fixture_count,
            skipped_fixture_count=skipped_fixture_count,
            generated_prediction_count_by_market=dict(
                sorted(generated_count_by_market.items())
            ),
            generated_fixture_count_by_market=dict(
                sorted(generated_fixture_by_market.items())
            ),
            lambda_source_counts=dict(sorted(lambda_source_counts.items())),
            warnings=_dedupe_strings(warnings),
            summary_json=summary,
        ),
    )


def build_historical_derived_market_candidate_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    source_suite_id: str,
    source_suite_name: str,
    output_slice_paths: Sequence[str],
    options: HistoricalDerivedMarketCandidateOptions | None = None,
) -> HistoricalDerivedMarketCandidateSuiteBuildResult:
    if len(historical_slices) != len(output_slice_paths):
        raise ValueError("historical_slices and output_slice_paths must have the same length")
    resolved_options = options or HistoricalDerivedMarketCandidateOptions()
    results = [
        build_historical_derived_market_candidate_slice(
            historical_slice,
            options=resolved_options,
        )
        for historical_slice in historical_slices
    ]
    manifest = HistoricalRecommendationSuiteManifest(
        suite_id=f"{source_suite_id}_{resolved_options.output_slice_id_suffix}",
        name=f"{source_suite_name} Derived Markets",
        description=(
            "Shadow derived handicap and correct-score candidate suite generated "
            "from frozen historical 1X2 slices."
        ),
        slices=[
            HistoricalRecommendationSuiteManifestSlice(
                slice_path=output_slice_path,
                enabled=True,
                tags=["derived-markets", "shadow"],
                notes=[
                    (
                        "Generated by "
                        "nutmeg-recommendation-historical-derived-market-candidates."
                    )
                ],
            )
            for output_slice_path in output_slice_paths
        ],
        tags=["derived-markets", "shadow"],
        notes=[
            (
                "Derived markets use model/fair probabilities for shadow replay; "
                "they are not paid provider historical market odds."
            )
        ],
    )
    report = _suite_report(
        source_suite_id=source_suite_id,
        output_suite_id=manifest.suite_id,
        output_slice_paths=output_slice_paths,
        slice_reports=[result.report for result in results],
        options=resolved_options,
    )
    return HistoricalDerivedMarketCandidateSuiteBuildResult(
        manifest=manifest,
        historical_slices=[result.historical_slice for result in results],
        report=report,
    )


class _FixtureDerivationResult(BaseModel):
    generated_predictions: list[HistoricalMarketPrediction] = Field(default_factory=list)
    lambda_source: str
    warnings: list[str] = Field(default_factory=list)


def _derive_fixture_predictions(
    fixture: HistoricalFixture,
    *,
    options: HistoricalDerivedMarketCandidateOptions,
) -> _FixtureDerivationResult:
    lambda_result = _fixture_lambdas(fixture)
    if lambda_result is None:
        return _FixtureDerivationResult(
            generated_predictions=[],
            lambda_source="unavailable",
            warnings=[
                (
                    "historical_derived_market_candidates:"
                    f"missing_lambda_or_complete_1x2:{fixture.fixture_id}"
                )
            ],
        )
    lambda_home, lambda_away, lambda_source = lambda_result
    score_grid = build_poisson_score_grid(
        fixture_id=fixture.fixture_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        max_goals=options.max_goals,
        model_version=f"{fixture.model_version}+derived-market-shadow",
        calibration_version=fixture.calibration_version or "shadow-derived-market-v3.1",
    )
    payload = score_grid_to_market_probabilities(
        score_grid,
        cn_handicaps=options.cn_handicaps,
        european_handicaps=options.european_handicaps,
        correct_score_top_n=(
            options.correct_score_top_n if options.correct_score_top_n > 0 else None
        ),
    )
    existing_keys = _existing_prediction_keys(fixture)
    generated = [
        prediction
        for prediction in _predictions_from_payload(
            fixture,
            payload=payload,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_source=lambda_source,
            options=options,
        )
        if not options.preserve_existing or _prediction_key(prediction) not in existing_keys
    ]
    return _FixtureDerivationResult(
        generated_predictions=generated,
        lambda_source=lambda_source,
        warnings=[],
    )


def _fixture_lambdas(fixture: HistoricalFixture) -> tuple[float, float, str] | None:
    metadata = fixture.metadata_json
    lambda_home = _nested_float(metadata, ("lambda_home",))
    lambda_away = _nested_float(metadata, ("lambda_away",))
    if lambda_home is None or lambda_away is None:
        lambda_home = _nested_float(metadata, ("modeling", "lambda_home"))
        lambda_away = _nested_float(metadata, ("modeling", "lambda_away"))
    if lambda_home is None or lambda_away is None:
        lambda_home = _nested_float(metadata, ("derived_score_model", "lambda_home"))
        lambda_away = _nested_float(metadata, ("derived_score_model", "lambda_away"))
    if lambda_home is not None and lambda_away is not None:
        return max(0.05, lambda_home), max(0.05, lambda_away), "fixture_metadata_lambda"

    one_x_two = _one_x_two_probabilities(fixture)
    if one_x_two is None:
        return None
    inferred_home, inferred_away = _infer_lambdas_from_1x2_probabilities(one_x_two)
    return inferred_home, inferred_away, "one_x_two_probability_shadow_heuristic"


def _one_x_two_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    values: dict[str, float] = {}
    for prediction in fixture.predictions:
        if prediction.market_type == "1x2" and prediction.outcome in {
            "home_win",
            "draw",
            "away_win",
        }:
            values[prediction.outcome] = prediction.probability
    if set(values) != {"home_win", "draw", "away_win"}:
        return None
    total = sum(values.values())
    if total <= 0:
        return None
    return {key: value / total for key, value in values.items()}


def _infer_lambdas_from_1x2_probabilities(
    probabilities: Mapping[str, float],
) -> tuple[float, float]:
    home = probabilities["home_win"]
    draw = probabilities["draw"]
    away = probabilities["away_win"]
    non_draw = max(0.0, 1.0 - draw)
    total_goals = _clamp(2.05 + non_draw * 0.72, lower=1.65, upper=3.40)
    home_share = _clamp(0.5 + (home - away) * 0.46, lower=0.18, upper=0.82)
    lambda_home = max(0.05, total_goals * home_share)
    lambda_away = max(0.05, total_goals * (1.0 - home_share))
    return lambda_home, lambda_away


def _predictions_from_payload(
    fixture: HistoricalFixture,
    *,
    payload: Mapping[str, object],
    lambda_home: float,
    lambda_away: float,
    lambda_source: str,
    options: HistoricalDerivedMarketCandidateOptions,
) -> list[HistoricalMarketPrediction]:
    predictions: list[HistoricalMarketPrediction] = []
    for key, value in payload.items():
        if key == "1x2":
            continue
        if key.startswith("cn_handicap_1x2:") and isinstance(value, dict):
            predictions.extend(
                _handicap_predictions(
                    value,
                    fixture=fixture,
                    market_type="cn_handicap_1x2",
                    line=float(key.split(":", maxsplit=1)[1]),
                    lambda_home=lambda_home,
                    lambda_away=lambda_away,
                    lambda_source=lambda_source,
                    options=options,
                )
            )
        elif key.startswith("european_handicap_1x2:") and isinstance(value, dict):
            predictions.extend(
                _handicap_predictions(
                    value,
                    fixture=fixture,
                    market_type="european_handicap_1x2",
                    line=float(key.split(":", maxsplit=1)[1]),
                    lambda_home=lambda_home,
                    lambda_away=lambda_away,
                    lambda_source=lambda_source,
                    options=options,
                )
            )
        elif key == "correct_score_top_n" and isinstance(value, list):
            predictions.extend(
                _correct_score_predictions(
                    value,
                    fixture=fixture,
                    lambda_home=lambda_home,
                    lambda_away=lambda_away,
                    lambda_source=lambda_source,
                    options=options,
                )
            )
    return predictions


def _handicap_predictions(
    probabilities: Mapping[object, object],
    *,
    fixture: HistoricalFixture,
    market_type: RecommendationMarketType,
    line: float,
    lambda_home: float,
    lambda_away: float,
    lambda_source: str,
    options: HistoricalDerivedMarketCandidateOptions,
) -> list[HistoricalMarketPrediction]:
    predictions: list[HistoricalMarketPrediction] = []
    for outcome in ("handicap_home_win", "handicap_draw", "handicap_away_win"):
        probability = _mapping_float(probabilities, outcome)
        if probability is None or probability < options.min_probability:
            continue
        predictions.append(
            _derived_prediction(
                fixture,
                market_type=market_type,
                outcome=outcome,
                probability=probability,
                line=line,
                lambda_home=lambda_home,
                lambda_away=lambda_away,
                lambda_source=lambda_source,
                options=options,
            )
        )
    return predictions


def _correct_score_predictions(
    scores: Sequence[object],
    *,
    fixture: HistoricalFixture,
    lambda_home: float,
    lambda_away: float,
    lambda_source: str,
    options: HistoricalDerivedMarketCandidateOptions,
) -> list[HistoricalMarketPrediction]:
    predictions: list[HistoricalMarketPrediction] = []
    for item in scores:
        if not isinstance(item, dict):
            continue
        probability = _mapping_float(item, "probability")
        option_key = item.get("option_key")
        if (
            probability is None
            or probability < options.min_probability
            or not isinstance(option_key, str)
        ):
            continue
        predictions.append(
            _derived_prediction(
                fixture,
                market_type="correct_score",
                outcome=option_key,
                probability=probability,
                line=None,
                lambda_home=lambda_home,
                lambda_away=lambda_away,
                lambda_source=lambda_source,
                options=options,
            )
        )
    return predictions


def _derived_prediction(
    fixture: HistoricalFixture,
    *,
    market_type: RecommendationMarketType,
    outcome: str,
    probability: float,
    line: float | None,
    lambda_home: float,
    lambda_away: float,
    lambda_source: str,
    options: HistoricalDerivedMarketCandidateOptions,
) -> HistoricalMarketPrediction:
    market_probability = min(0.999999, probability * (1.0 + options.market_margin))
    decimal_odds = max(1.01, 1.0 / market_probability)
    return HistoricalMarketPrediction(
        market_type=market_type,
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=market_probability,
        model_edge=probability - market_probability,
        data_quality_score=_source_quality(fixture, field_name="data_quality_score"),
        model_confidence_score=_source_quality(
            fixture,
            field_name="model_confidence_score",
            fallback=0.60,
        ),
        calibration_score=_source_quality(
            fixture,
            field_name="calibration_score",
            fallback=0.60,
        ),
        odds_stability_score=_source_quality(
            fixture,
            field_name="odds_stability_score",
            fallback=0.60,
        ),
        volatility_penalty=_source_quality(
            fixture,
            field_name="volatility_penalty",
            fallback=0.10,
        ),
        line=line,
        metadata_json={
            "source": "historical_derived_market_candidates",
            "derivation_id": options.derivation_id,
            "calculation_basis": "poisson_score_grid_shadow_market_derivation_v3_1",
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "lambda_source": lambda_source,
            "score_grid_max_goals": options.max_goals,
            "shadow_market_odds": "fair_odds_from_model_probability",
            "dc_compatibility": {
                "score_grid_contract": "lambda_home/lambda_away -> score_probability_grid",
                "rho": None,
            },
        },
    )


def _source_quality(
    fixture: HistoricalFixture,
    *,
    field_name: str,
    fallback: float = 70.0,
) -> float:
    values = [
        cast(float, getattr(prediction, field_name))
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
    ]
    if not values:
        return fallback
    return sum(values) / len(values)


def _existing_prediction_keys(
    fixture: HistoricalFixture,
) -> set[tuple[str, str, float | None, str | None]]:
    return {_prediction_key(prediction) for prediction in fixture.predictions}


def _prediction_key(
    prediction: HistoricalMarketPrediction,
) -> tuple[str, str, float | None, str | None]:
    line = round(prediction.line, 6) if prediction.line is not None else None
    return prediction.market_type, prediction.outcome, line, prediction.side


def _nested_float(
    mapping: Mapping[str, object],
    path: Sequence[str],
) -> float | None:
    value: object = mapping
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _mapping_float(mapping: Mapping[object, object], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _clamp(value: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _output_slice_id(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalDerivedMarketCandidateOptions,
) -> str:
    suffix = options.output_slice_id_suffix.strip("_")
    return f"{historical_slice.metadata.slice_id}_{suffix}"


def _report_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    output_slice_id: str,
    options: HistoricalDerivedMarketCandidateOptions,
    generated_count_by_market: Mapping[str, int],
) -> str:
    payload = {
        "source_slice_id": historical_slice.metadata.slice_id,
        "output_slice_id": output_slice_id,
        "options": options.model_dump(mode="json"),
        "generated_count_by_market": dict(sorted(generated_count_by_market.items())),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_derived_market_candidates:{digest}"


def _suite_report(
    *,
    source_suite_id: str,
    output_suite_id: str,
    output_slice_paths: Sequence[str],
    slice_reports: Sequence[HistoricalDerivedMarketCandidateReport],
    options: HistoricalDerivedMarketCandidateOptions,
) -> HistoricalDerivedMarketCandidateSuiteReport:
    generated_count_by_market: Counter[str] = Counter()
    generated_fixture_by_market: Counter[str] = Counter()
    lambda_source_counts: Counter[str] = Counter()
    warnings: list[str] = []
    for report in slice_reports:
        generated_count_by_market.update(report.generated_prediction_count_by_market)
        generated_fixture_by_market.update(report.generated_fixture_count_by_market)
        lambda_source_counts.update(report.lambda_source_counts)
        warnings.extend(report.warnings)
    report_key = _suite_report_key(
        source_suite_id=source_suite_id,
        output_suite_id=output_suite_id,
        output_slice_paths=output_slice_paths,
        options=options,
        generated_count_by_market=generated_count_by_market,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_derived_market_candidate_suite_v3_1",
        "report_key": report_key,
        "derivation_id": options.derivation_id,
        "source_suite_id": source_suite_id,
        "output_suite_id": output_suite_id,
        "slice_count": len(slice_reports),
        "fixture_count": sum(report.fixture_count for report in slice_reports),
        "source_prediction_count": sum(
            report.source_prediction_count for report in slice_reports
        ),
        "output_prediction_count": sum(
            report.output_prediction_count for report in slice_reports
        ),
        "generated_prediction_count": sum(
            report.generated_prediction_count for report in slice_reports
        ),
        "generated_prediction_count_by_market": dict(
            sorted(generated_count_by_market.items())
        ),
        "generated_fixture_count_by_market": dict(
            sorted(generated_fixture_by_market.items())
        ),
        "lambda_source_counts": dict(sorted(lambda_source_counts.items())),
        "output_slice_paths": list(output_slice_paths),
        "warnings": _dedupe_strings(warnings),
    }
    return HistoricalDerivedMarketCandidateSuiteReport(
        report_key=report_key,
        derivation_id=options.derivation_id,
        source_suite_id=source_suite_id,
        output_suite_id=output_suite_id,
        slice_count=len(slice_reports),
        fixture_count=sum(report.fixture_count for report in slice_reports),
        source_prediction_count=sum(
            report.source_prediction_count for report in slice_reports
        ),
        output_prediction_count=sum(
            report.output_prediction_count for report in slice_reports
        ),
        generated_prediction_count=sum(
            report.generated_prediction_count for report in slice_reports
        ),
        generated_fixture_count=sum(
            report.generated_fixture_count for report in slice_reports
        ),
        skipped_fixture_count=sum(report.skipped_fixture_count for report in slice_reports),
        generated_prediction_count_by_market=dict(
            sorted(generated_count_by_market.items())
        ),
        generated_fixture_count_by_market=dict(
            sorted(generated_fixture_by_market.items())
        ),
        lambda_source_counts=dict(sorted(lambda_source_counts.items())),
        output_slice_paths=list(output_slice_paths),
        slice_reports=list(slice_reports),
        warnings=_dedupe_strings(warnings),
        summary_json=summary,
    )


def _suite_report_key(
    *,
    source_suite_id: str,
    output_suite_id: str,
    output_slice_paths: Sequence[str],
    options: HistoricalDerivedMarketCandidateOptions,
    generated_count_by_market: Mapping[str, int],
) -> str:
    payload = {
        "source_suite_id": source_suite_id,
        "output_suite_id": output_suite_id,
        "output_slice_paths": list(output_slice_paths),
        "options": options.model_dump(mode="json"),
        "generated_count_by_market": dict(sorted(generated_count_by_market.items())),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_derived_market_candidate_suite:{digest}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.suite_manifest is not None:
        _run_suite_cli(args)
        return
    if args.slice_path is None:
        raise SystemExit("provide slice_path or --suite-manifest")
    source_slice = load_historical_recommendation_slice(args.slice_path)
    result = build_historical_derived_market_candidate_slice(
        source_slice,
        options=_options_from_args(args),
    )
    if args.output_slice_path is not None:
        args.output_slice_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_slice_path.write_text(
            f"{result.historical_slice.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    report_output = dumps(
        result.report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(f"{report_output}\n", encoding="utf-8")
    print(report_output)


def _run_suite_cli(args: Namespace) -> None:
    if args.output_slice_dir is None:
        raise SystemExit("--output-slice-dir is required with --suite-manifest")
    if args.output_suite_manifest_path is None:
        raise SystemExit("--output-suite-manifest-path is required with --suite-manifest")
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    options = _options_from_args(args)
    output_slice_dir: Path = args.output_slice_dir
    output_suite_manifest_path: Path = args.output_suite_manifest_path
    output_slice_dir.mkdir(parents=True, exist_ok=True)
    output_suite_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_slice_paths = [
        _stored_output_slice_path(
            output_slice_dir / f"{_output_slice_id(historical_slice, options=options)}.json",
            manifest_path=output_suite_manifest_path,
        )
        for historical_slice in bundle.slices
    ]
    result = build_historical_derived_market_candidate_suite(
        bundle.slices,
        source_suite_id=bundle.manifest.suite_id,
        source_suite_name=bundle.manifest.name,
        output_slice_paths=output_slice_paths,
        options=options,
    )
    for historical_slice, stored_path in zip(
        result.historical_slices,
        result.report.output_slice_paths,
        strict=True,
    ):
        output_path = (output_suite_manifest_path.parent / stored_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"{historical_slice.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    output_suite_manifest_path.write_text(
        f"{result.manifest.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    report_output = dumps(
        result.report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(f"{report_output}\n", encoding="utf-8")
    print(report_output)


def _stored_output_slice_path(output_slice_path: Path, *, manifest_path: Path) -> str:
    return relpath(output_slice_path.resolve(), start=manifest_path.parent.resolve())


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Derive shadow handicap and correct-score historical predictions "
            "from fixture lambdas or complete 1X2 probabilities."
        )
    )
    parser.add_argument("slice_path", type=Path, nargs="?")
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-slice-path", type=Path)
    parser.add_argument("--output-slice-dir", type=Path)
    parser.add_argument("--output-suite-manifest-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--derivation-id",
        default=DEFAULT_HISTORICAL_DERIVED_MARKET_CANDIDATE_ID,
    )
    parser.add_argument("--output-slice-id-suffix", default="derived_markets_v1")
    parser.add_argument("--cn-handicaps", default="-1,1")
    parser.add_argument("--european-handicaps", default="-1,1")
    parser.add_argument("--correct-score-top-n", type=int, default=5)
    parser.add_argument("--max-goals", type=int, default=8)
    parser.add_argument("--min-probability", type=float, default=0.005)
    parser.add_argument("--market-margin", type=float, default=0.0)
    parser.add_argument("--replace-existing", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalDerivedMarketCandidateOptions:
    return HistoricalDerivedMarketCandidateOptions(
        derivation_id=args.derivation_id,
        output_slice_id_suffix=args.output_slice_id_suffix,
        cn_handicaps=tuple(_csv_ints(args.cn_handicaps)),
        european_handicaps=tuple(_csv_ints(args.european_handicaps)),
        correct_score_top_n=args.correct_score_top_n,
        max_goals=args.max_goals,
        min_probability=args.min_probability,
        market_margin=args.market_margin,
        preserve_existing=not args.replace_existing,
    )


def _csv_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]
