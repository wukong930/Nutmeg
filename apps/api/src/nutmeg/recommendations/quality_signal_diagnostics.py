from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalFixture,
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
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)

type HistoricalQualitySignalGroupType = Literal[
    "candidate_score_band",
    "component_score_band",
    "reason_code",
    "probability_band",
    "odds_band",
    "model_edge_band",
    "competition_probability_band",
    "competition_odds_band",
    "competition_model_edge_band",
]

DEFAULT_COMPONENT_NAMES: tuple[str, ...] = (
    "probability",
    "model_edge",
    "data_quality",
    "model_confidence",
    "calibration",
    "upset_protection_quality",
    "favorite_fragility",
    "upset_avoidance_penalty",
    "odds_stability",
    "volatility_penalty",
    "calibration_risk",
    "longshot_upset_risk",
    "calibrated_upset_exposure",
    "upset_signal_calibration_risk",
    "upset_signal_reliability",
)


class HistoricalQualitySignalDiagnosticOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    focus_competition_ids: tuple[str, ...] = ()
    component_names: tuple[str, ...] = DEFAULT_COMPONENT_NAMES
    min_group_selected_leg_count: int = Field(default=1, ge=1)
    derive_market_context_signals: bool = False
    include_reason_codes: bool = True
    include_basic_bands: bool = True
    include_competition_bands: bool = True


class HistoricalQualitySignalGroup(BaseModel):
    group_key: str
    group_type: HistoricalQualitySignalGroupType
    label: str
    component_name: str | None = None
    band: str | None = None
    final_answer_count: int = Field(default=0, ge=0)
    final_answer_hit_count: int = Field(default=0, ge=0)
    final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_leg_count: int = Field(default=0, ge=0)
    leg_hit_count: int = Field(default=0, ge=0)
    leg_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    missed_leg_count: int = Field(default=0, ge=0)
    total_stake: float = Field(default=0.0, ge=0.0)
    actual_return: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float | None = None
    average_candidate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_component_value: float | None = Field(default=None)
    average_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_model_edge: float | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalQualitySignalDiagnosticReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    leg_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(default=0.0, ge=0.0)
    actual_return: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float | None = None
    groups: list[HistoricalQualitySignalGroup] = Field(default_factory=list)
    top_positive_signal_groups: list[HistoricalQualitySignalGroup] = Field(
        default_factory=list
    )
    top_negative_signal_groups: list[HistoricalQualitySignalGroup] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _GroupSpec:
    group_key: str
    group_type: HistoricalQualitySignalGroupType
    label: str
    component_name: str | None = None
    band: str | None = None


@dataclass
class _GroupAccumulator:
    spec: _GroupSpec
    final_answer_count: int = 0
    final_answer_hit_count: int = 0
    selected_leg_count: int = 0
    leg_hit_count: int = 0
    total_stake: float = 0.0
    actual_return: float = 0.0
    candidate_score_sum: float = 0.0
    component_value_sum: float = 0.0
    component_value_count: int = 0
    probability_sum: float = 0.0
    decimal_odds_sum: float = 0.0
    decimal_odds_count: int = 0
    model_edge_sum: float = 0.0

    def add_final_answer(self, final_answer: HistoricalRecommendationScenarioResult) -> None:
        self.final_answer_count += 1
        self.final_answer_hit_count += int(final_answer.actual_hit)
        self.total_stake += final_answer.total_stake
        self.actual_return += final_answer.actual_return

    def add_leg(
        self,
        scored: ScoredRecommendationCandidate,
        *,
        actual_hit: bool,
        component_value: float | None,
    ) -> None:
        candidate = scored.candidate
        self.selected_leg_count += 1
        self.leg_hit_count += int(actual_hit)
        self.candidate_score_sum += scored.score
        self.probability_sum += candidate.probability
        if candidate.decimal_odds is not None:
            self.decimal_odds_sum += candidate.decimal_odds
            self.decimal_odds_count += 1
        self.model_edge_sum += candidate.effective_model_edge()
        if component_value is not None:
            self.component_value_sum += component_value
            self.component_value_count += 1

    def group(self) -> HistoricalQualitySignalGroup:
        profit_loss = self.actual_return - self.total_stake
        missed_leg_count = self.selected_leg_count - self.leg_hit_count
        return HistoricalQualitySignalGroup(
            group_key=self.spec.group_key,
            group_type=self.spec.group_type,
            label=self.spec.label,
            component_name=self.spec.component_name,
            band=self.spec.band,
            final_answer_count=self.final_answer_count,
            final_answer_hit_count=self.final_answer_hit_count,
            final_answer_hit_rate=_ratio(
                self.final_answer_hit_count,
                self.final_answer_count,
            ),
            selected_leg_count=self.selected_leg_count,
            leg_hit_count=self.leg_hit_count,
            leg_hit_rate=_ratio(self.leg_hit_count, self.selected_leg_count),
            missed_leg_count=missed_leg_count,
            total_stake=self.total_stake,
            actual_return=self.actual_return,
            profit_loss=profit_loss,
            roi=profit_loss / self.total_stake if self.total_stake > 0 else None,
            average_candidate_score=_ratio(
                self.candidate_score_sum,
                self.selected_leg_count,
            ),
            average_component_value=_ratio(
                self.component_value_sum,
                self.component_value_count,
            ),
            average_probability=_ratio(self.probability_sum, self.selected_leg_count),
            average_decimal_odds=_ratio(
                self.decimal_odds_sum,
                self.decimal_odds_count,
            ),
            average_model_edge=_ratio(self.model_edge_sum, self.selected_leg_count),
            summary_json={
                "missed_leg_rate": _ratio(missed_leg_count, self.selected_leg_count),
                "loss_per_final_answer": _ratio(
                    -profit_loss if profit_loss < 0 else 0.0,
                    self.final_answer_count,
                ),
            },
        )


def build_historical_quality_signal_diagnostic_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalQualitySignalDiagnosticOptions | None = None,
) -> HistoricalQualitySignalDiagnosticReport:
    resolved_options = options or HistoricalQualitySignalDiagnosticOptions()
    backtest_options = resolved_options.backtest_options.model_copy(
        update={
            "derive_market_context_signals": (
                resolved_options.derive_market_context_signals
            )
        }
    )
    accumulators: dict[str, _GroupAccumulator] = {}
    warnings: list[str] = []
    included_slice_ids: set[str] = set()
    included_competition_ids: set[str] = set()
    final_answer_count = 0
    final_answer_hit_count = 0
    selected_leg_count = 0
    leg_hit_count = 0
    total_stake = 0.0
    actual_return = 0.0

    for historical_slice in historical_slices:
        if not _include_competition(historical_slice, options=resolved_options):
            continue
        backtest = run_historical_recommendation_backtest(
            historical_slice,
            options=backtest_options,
        )
        warnings.extend(backtest.warnings)
        final_answer = backtest.final_answer
        if final_answer is None or final_answer.option is None:
            warnings.append(
                "quality_signal_diagnostics:no_final_answer:"
                f"{historical_slice.metadata.slice_id}"
            )
            continue
        included_slice_ids.add(historical_slice.metadata.slice_id)
        included_competition_ids.add(historical_slice.metadata.competition_id)
        final_answer_count += 1
        final_answer_hit_count += int(final_answer.actual_hit)
        total_stake += final_answer.total_stake
        actual_return += final_answer.actual_return
        fixture_by_id = {fixture.fixture_id: fixture for fixture in historical_slice.fixtures}
        final_answer_group_specs: dict[str, _GroupSpec] = {}
        for scored in final_answer.option.selection.selected_candidates:
            candidate = scored.candidate
            fixture = fixture_by_id.get(candidate.fixture_id)
            actual_hit = _candidate_matches_actual(candidate, fixture=fixture)
            selected_leg_count += 1
            leg_hit_count += int(actual_hit)
            for spec, component_value in _signal_group_specs(
                scored,
                options=resolved_options,
                competition_id=historical_slice.metadata.competition_id,
            ):
                accumulator = accumulators.setdefault(
                    spec.group_key,
                    _GroupAccumulator(spec=spec),
                )
                accumulator.add_leg(
                    scored,
                    actual_hit=actual_hit,
                    component_value=component_value,
                )
                final_answer_group_specs[spec.group_key] = spec
        for spec in final_answer_group_specs.values():
            accumulators[spec.group_key].add_final_answer(final_answer)

    groups = sorted(
        (
            accumulator.group()
            for accumulator in accumulators.values()
            if accumulator.selected_leg_count
            >= resolved_options.min_group_selected_leg_count
        ),
        key=lambda group: (group.group_type, group.group_key),
    )
    top_positive_groups = _top_positive_signal_groups(groups)
    top_negative_groups = _top_negative_signal_groups(groups)
    profit_loss = actual_return - total_stake
    summary: dict[str, object] = {
        "calculation_basis": "historical_quality_signal_diagnostics_v3_1",
        "slice_count": len(included_slice_ids),
        "competition_count": len(included_competition_ids),
        "final_answer_count": final_answer_count,
        "selected_leg_count": selected_leg_count,
        "missed_leg_count": selected_leg_count - leg_hit_count,
        "final_answer_hit_rate": _ratio(final_answer_hit_count, final_answer_count),
        "leg_hit_rate": _ratio(leg_hit_count, selected_leg_count),
        "total_stake": total_stake,
        "actual_return": actual_return,
        "profit_loss": profit_loss,
        "roi": profit_loss / total_stake if total_stake > 0 else None,
        "group_count": len(groups),
        "component_names": list(resolved_options.component_names),
        "focus_competition_ids": list(resolved_options.focus_competition_ids),
        "derive_market_context_signals": resolved_options.derive_market_context_signals,
        "include_competition_bands": resolved_options.include_competition_bands,
        "top_positive_signal_group_keys": [
            group.group_key for group in top_positive_groups
        ],
        "top_negative_signal_group_keys": [
            group.group_key for group in top_negative_groups
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalQualitySignalDiagnosticReport(
        report_key=report_key,
        status="generated",
        slice_count=len(included_slice_ids),
        competition_count=len(included_competition_ids),
        final_answer_count=final_answer_count,
        selected_leg_count=selected_leg_count,
        missed_leg_count=selected_leg_count - leg_hit_count,
        final_answer_hit_rate=_ratio(final_answer_hit_count, final_answer_count),
        leg_hit_rate=_ratio(leg_hit_count, selected_leg_count),
        total_stake=total_stake,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake if total_stake > 0 else None,
        groups=groups,
        top_positive_signal_groups=top_positive_groups,
        top_negative_signal_groups=top_negative_groups,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_quality_signal_diagnostic_report(
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


def _signal_group_specs(
    scored: ScoredRecommendationCandidate,
    *,
    options: HistoricalQualitySignalDiagnosticOptions,
    competition_id: str,
) -> list[tuple[_GroupSpec, float | None]]:
    candidate = scored.candidate
    specs: list[tuple[_GroupSpec, float | None]] = [
        (
            _GroupSpec(
                group_key=f"candidate_score_band:{_unit_band(scored.score)}",
                group_type="candidate_score_band",
                label=f"candidate score {_unit_band(scored.score)}",
                band=_unit_band(scored.score),
            ),
            scored.score,
        )
    ]
    for component_name in options.component_names:
        component_value = _component_value(scored.component_scores, component_name)
        if component_value is None:
            continue
        band = _unit_band(component_value)
        specs.append(
            (
                _GroupSpec(
                    group_key=f"component_score_band:{component_name}:{band}",
                    group_type="component_score_band",
                    label=f"{component_name} {band}",
                    component_name=component_name,
                    band=band,
                ),
                component_value,
            )
        )
    if options.include_reason_codes:
        specs.extend(
            (
                _GroupSpec(
                    group_key=f"reason_code:{reason_code}",
                    group_type="reason_code",
                    label=reason_code,
                ),
                None,
            )
            for reason_code in scored.reason_codes
        )
    if options.include_basic_bands:
        specs.extend(
            [
                (
                    _GroupSpec(
                        group_key=f"probability_band:{_unit_band(candidate.probability)}",
                        group_type="probability_band",
                        label=f"probability {_unit_band(candidate.probability)}",
                        band=_unit_band(candidate.probability),
                    ),
                    candidate.probability,
                ),
                (
                    _GroupSpec(
                        group_key=f"odds_band:{_odds_band(candidate.decimal_odds)}",
                        group_type="odds_band",
                        label=f"odds {_odds_band(candidate.decimal_odds)}",
                        band=_odds_band(candidate.decimal_odds),
                    ),
                    candidate.decimal_odds,
                ),
                (
                    _GroupSpec(
                        group_key=(
                            f"model_edge_band:"
                            f"{_model_edge_band(candidate.effective_model_edge())}"
                        ),
                        group_type="model_edge_band",
                        label=(
                            "model edge "
                            f"{_model_edge_band(candidate.effective_model_edge())}"
                        ),
                        band=_model_edge_band(candidate.effective_model_edge()),
                    ),
                    candidate.effective_model_edge(),
                ),
            ]
        )
    if options.include_competition_bands:
        probability_band = _unit_band(candidate.probability)
        odds_band = _odds_band(candidate.decimal_odds)
        model_edge_band = _model_edge_band(candidate.effective_model_edge())
        specs.extend(
            [
                (
                    _GroupSpec(
                        group_key=(
                            f"competition_probability_band:{competition_id}:"
                            f"{probability_band}"
                        ),
                        group_type="competition_probability_band",
                        label=f"{competition_id} probability {probability_band}",
                        band=probability_band,
                    ),
                    candidate.probability,
                ),
                (
                    _GroupSpec(
                        group_key=f"competition_odds_band:{competition_id}:{odds_band}",
                        group_type="competition_odds_band",
                        label=f"{competition_id} odds {odds_band}",
                        band=odds_band,
                    ),
                    candidate.decimal_odds,
                ),
                (
                    _GroupSpec(
                        group_key=(
                            f"competition_model_edge_band:{competition_id}:"
                            f"{model_edge_band}"
                        ),
                        group_type="competition_model_edge_band",
                        label=f"{competition_id} model edge {model_edge_band}",
                        band=model_edge_band,
                    ),
                    candidate.effective_model_edge(),
                ),
            ]
        )
    return specs


def _candidate_matches_actual(
    candidate: RecommendationCandidate,
    *,
    fixture: HistoricalFixture | None,
) -> bool:
    actual_outcome = (
        fixture.actual_1x2_outcome
        if fixture is not None
        else _metadata_string(candidate.metadata_json, "actual_1x2_outcome")
    )
    if candidate.market_type == "1x2":
        return candidate.outcome == actual_outcome
    return False


def _top_positive_signal_groups(
    groups: Sequence[HistoricalQualitySignalGroup],
) -> list[HistoricalQualitySignalGroup]:
    return sorted(
        groups,
        key=lambda group: (
            group.roi if group.roi is not None else -999.0,
            group.leg_hit_rate if group.leg_hit_rate is not None else -1.0,
            group.selected_leg_count,
            group.group_key,
        ),
        reverse=True,
    )[:10]


def _top_negative_signal_groups(
    groups: Sequence[HistoricalQualitySignalGroup],
) -> list[HistoricalQualitySignalGroup]:
    return sorted(
        groups,
        key=lambda group: (
            group.profit_loss,
            -group.missed_leg_count,
            group.leg_hit_rate if group.leg_hit_rate is not None else 1.0,
            group.group_key,
        ),
    )[:10]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Diagnose final-answer quality signals against historical outcomes."
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
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"], default="solver")
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
    parser.add_argument("--focus-competitions", default="")
    parser.add_argument("--component-names", default=",".join(DEFAULT_COMPONENT_NAMES))
    parser.add_argument("--min-group-selected-leg-count", type=int, default=1)
    parser.add_argument(
        "--include-reason-codes",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--include-basic-bands",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--include-competition-bands",
        action=BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalQualitySignalDiagnosticOptions:
    return HistoricalQualitySignalDiagnosticOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        focus_competition_ids=tuple(_csv(args.focus_competitions)),
        component_names=tuple(_csv(args.component_names)),
        min_group_selected_leg_count=args.min_group_selected_leg_count,
        derive_market_context_signals=args.derive_market_context_signals,
        include_reason_codes=args.include_reason_codes,
        include_basic_bands=args.include_basic_bands,
        include_competition_bands=args.include_competition_bands,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
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


def _include_competition(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalQualitySignalDiagnosticOptions,
) -> bool:
    return (
        not options.focus_competition_ids
        or historical_slice.metadata.competition_id in set(options.focus_competition_ids)
    )


def _component_value(
    component_scores: Mapping[str, float],
    component_name: str,
) -> float | None:
    value = component_scores.get(component_name)
    if isinstance(value, int | float):
        return float(value)
    return None


def _unit_band(value: float) -> str:
    if value < 0.35:
        return "very_low"
    if value < 0.50:
        return "low"
    if value < 0.65:
        return "medium"
    if value < 0.80:
        return "high"
    return "very_high"


def _odds_band(decimal_odds: float | None) -> str:
    if decimal_odds is None:
        return "odds_missing"
    if decimal_odds <= 1.35:
        return "short_price"
    if decimal_odds <= 1.80:
        return "medium_short_price"
    if decimal_odds <= 2.50:
        return "medium_price"
    if decimal_odds <= 4.00:
        return "long_price"
    return "very_long_price"


def _model_edge_band(model_edge: float) -> str:
    if model_edge < -0.05:
        return "negative_large"
    if model_edge < 0.0:
        return "negative"
    if model_edge == 0.0:
        return "neutral"
    if model_edge < 0.05:
        return "positive_small"
    return "positive"


def _metadata_string(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
    return f"historical_quality_signal_diagnostics:{digest}"
