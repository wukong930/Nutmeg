from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalFixture,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    _candidates_from_fixtures,
    _compress_candidate_pool,
    _eligible_fixtures,
    _scenario_candidate_pool,
    _settle_selection,
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
    RecommendationSelection,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.policy import build_recommendation_policy_config, rank_candidates

type HistoricalMarginalReplacementDecision = Literal[
    "actual_improved",
    "actual_unchanged",
    "actual_regressed",
]


class HistoricalCandidateReplacementSimulation(BaseModel):
    replacement_rank: int = Field(ge=1)
    replacement_fixture_id: str
    replacement_market_type: str
    replacement_outcome: str
    replacement_probability: float = Field(ge=0.0, le=1.0)
    replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    replacement_model_edge: float
    replacement_score: float = Field(ge=0.0, le=1.0)
    replacement_quality_score: float = Field(ge=0.0, le=1.0)
    replacement_leg_actual_hit: bool
    simulated_actual_hit: bool
    simulated_actual_return: float = Field(ge=0.0)
    simulated_profit_loss: float
    simulated_hit_probability: float = Field(ge=0.0, le=1.0)
    simulated_roi: float
    simulated_risk_score: float = Field(ge=0.0, le=1.0)
    actual_return_delta: float
    profit_loss_delta: float
    hit_probability_delta: float
    roi_delta: float
    risk_score_delta: float
    decision: HistoricalMarginalReplacementDecision


class HistoricalCandidateMarginalAuditItem(BaseModel):
    item_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: RecommendationMode
    final_answer_actual_hit: bool
    selected_fixture_id: str
    selected_market_type: str
    selected_outcome: str
    selected_probability: float = Field(ge=0.0, le=1.0)
    selected_decimal_odds: float | None = Field(default=None, gt=1.0)
    selected_model_edge: float
    selected_score: float = Field(ge=0.0, le=1.0)
    selected_reason_codes: list[str] = Field(default_factory=list)
    leg_actual_hit: bool
    original_actual_return: float = Field(ge=0.0)
    original_profit_loss: float
    original_hit_probability: float = Field(ge=0.0, le=1.0)
    original_roi: float
    original_risk_score: float = Field(ge=0.0, le=1.0)
    replacement_count: int = Field(default=0, ge=0)
    model_top_replacement: HistoricalCandidateReplacementSimulation | None = None
    actual_best_replacement: HistoricalCandidateReplacementSimulation | None = None
    replacement_candidates: list[HistoricalCandidateReplacementSimulation] = Field(
        default_factory=list
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalCandidateMarginalAuditOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    focus_competition_ids: tuple[str, ...] = ()
    max_replacement_candidates_per_leg: int = Field(default=5, ge=1, le=30)
    same_market_type_only: bool = True
    derive_market_context_signals: bool = False
    target_probability_min: float | None = Field(default=None, ge=0.0, le=1.0)
    target_probability_max: float | None = Field(default=None, ge=0.0, le=1.0)
    target_min_decimal_odds: float | None = Field(default=None, gt=1.0)
    target_max_decimal_odds: float | None = Field(default=None, gt=1.0)
    target_max_model_edge: float | None = None
    missed_legs_only: bool = False


class HistoricalCandidateMarginalAuditReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    replacement_simulation_count: int = Field(ge=0)
    actual_replacement_opportunity_count: int = Field(ge=0)
    model_top_replacement_count: int = Field(ge=0)
    model_top_actual_improvement_count: int = Field(ge=0)
    model_top_actual_harm_count: int = Field(ge=0)
    average_model_top_profit_loss_delta: float | None = None
    average_model_top_hit_probability_delta: float | None = None
    average_actual_best_profit_loss_delta: float | None = None
    items: list[HistoricalCandidateMarginalAuditItem] = Field(default_factory=list)
    top_actual_replacement_opportunities: list[HistoricalCandidateMarginalAuditItem] = (
        Field(default_factory=list)
    )
    top_model_replacement_opportunities: list[HistoricalCandidateMarginalAuditItem] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    manifest_results: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _ScenarioContext:
    final_answer: HistoricalRecommendationScenarioResult
    scored_pool: list[ScoredRecommendationCandidate]
    fixture_by_id: dict[str, HistoricalFixture]
    backtest_options: HistoricalRecommendationBacktestOptions


def build_historical_candidate_marginal_audit_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalCandidateMarginalAuditOptions | None = None,
) -> HistoricalCandidateMarginalAuditReport:
    resolved_options = options or HistoricalCandidateMarginalAuditOptions()
    backtest_options = resolved_options.backtest_options.model_copy(
        update={
            "derive_market_context_signals": (
                resolved_options.derive_market_context_signals
            )
        }
    )
    warnings: list[str] = []
    included_slice_ids: set[str] = set()
    included_competition_ids: set[str] = set()
    final_answer_count = 0
    examined_selected_leg_count = 0
    items: list[HistoricalCandidateMarginalAuditItem] = []

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
                "candidate_marginal_audit:no_final_answer:"
                f"{historical_slice.metadata.slice_id}"
            )
            continue
        included_slice_ids.add(historical_slice.metadata.slice_id)
        included_competition_ids.add(historical_slice.metadata.competition_id)
        final_answer_count += 1
        context = _scenario_context(
            historical_slice,
            final_answer=final_answer,
            backtest_options=backtest_options,
        )
        for scored in final_answer.option.selection.selected_candidates:
            examined_selected_leg_count += 1
            fixture = context.fixture_by_id.get(scored.candidate.fixture_id)
            leg_actual_hit = _candidate_matches_actual(scored.candidate, fixture=fixture)
            if not _selected_leg_matches_target_filter(
                scored,
                leg_actual_hit=leg_actual_hit,
                options=resolved_options,
            ):
                continue
            items.append(
                _audit_item_for_selected_leg(
                    historical_slice,
                    selected=scored,
                    context=context,
                    options=resolved_options,
                )
            )

    top_actual_opportunities = _top_actual_replacement_opportunities(items)
    top_model_opportunities = _top_model_replacement_opportunities(items)
    model_top_replacements = [
        item.model_top_replacement
        for item in items
        if item.model_top_replacement is not None
    ]
    actual_best_replacements = [
        item.actual_best_replacement
        for item in items
        if item.actual_best_replacement is not None
    ]
    replacement_simulation_count = sum(item.replacement_count for item in items)
    actual_replacement_opportunity_count = sum(
        1
        for item in items
        if item.actual_best_replacement is not None
        and item.actual_best_replacement.profit_loss_delta > 0
    )
    model_top_actual_improvement_count = sum(
        1
        for replacement in model_top_replacements
        if replacement.profit_loss_delta > 0
    )
    model_top_actual_harm_count = sum(
        1
        for replacement in model_top_replacements
        if replacement.profit_loss_delta < 0
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_candidate_marginal_audit_v3_1",
        "slice_count": len(included_slice_ids),
        "competition_count": len(included_competition_ids),
        "final_answer_count": final_answer_count,
        "examined_selected_leg_count": examined_selected_leg_count,
        "selected_leg_count": len(items),
        "missed_leg_count": sum(1 for item in items if not item.leg_actual_hit),
        "replacement_simulation_count": replacement_simulation_count,
        "actual_replacement_opportunity_count": actual_replacement_opportunity_count,
        "model_top_replacement_count": len(model_top_replacements),
        "model_top_actual_improvement_count": model_top_actual_improvement_count,
        "model_top_actual_harm_count": model_top_actual_harm_count,
        "average_model_top_profit_loss_delta": _average(
            replacement.profit_loss_delta for replacement in model_top_replacements
        ),
        "average_model_top_hit_probability_delta": _average(
            replacement.hit_probability_delta for replacement in model_top_replacements
        ),
        "average_actual_best_profit_loss_delta": _average(
            replacement.profit_loss_delta for replacement in actual_best_replacements
        ),
        "focus_competition_ids": list(resolved_options.focus_competition_ids),
        "max_replacement_candidates_per_leg": (
            resolved_options.max_replacement_candidates_per_leg
        ),
        "same_market_type_only": resolved_options.same_market_type_only,
        "derive_market_context_signals": resolved_options.derive_market_context_signals,
        "target_filter": {
            "probability_min": resolved_options.target_probability_min,
            "probability_max": resolved_options.target_probability_max,
            "min_decimal_odds": resolved_options.target_min_decimal_odds,
            "max_decimal_odds": resolved_options.target_max_decimal_odds,
            "max_model_edge": resolved_options.target_max_model_edge,
            "missed_legs_only": resolved_options.missed_legs_only,
        },
        "top_actual_replacement_item_keys": [
            item.item_key for item in top_actual_opportunities
        ],
        "top_model_replacement_item_keys": [
            item.item_key for item in top_model_opportunities
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalCandidateMarginalAuditReport(
        report_key=report_key,
        status="generated",
        slice_count=len(included_slice_ids),
        competition_count=len(included_competition_ids),
        final_answer_count=final_answer_count,
        selected_leg_count=len(items),
        missed_leg_count=sum(1 for item in items if not item.leg_actual_hit),
        replacement_simulation_count=replacement_simulation_count,
        actual_replacement_opportunity_count=actual_replacement_opportunity_count,
        model_top_replacement_count=len(model_top_replacements),
        model_top_actual_improvement_count=model_top_actual_improvement_count,
        model_top_actual_harm_count=model_top_actual_harm_count,
        average_model_top_profit_loss_delta=cast(
            float | None,
            summary["average_model_top_profit_loss_delta"],
        ),
        average_model_top_hit_probability_delta=cast(
            float | None,
            summary["average_model_top_hit_probability_delta"],
        ),
        average_actual_best_profit_loss_delta=cast(
            float | None,
            summary["average_actual_best_profit_loss_delta"],
        ),
        items=items,
        top_actual_replacement_opportunities=top_actual_opportunities,
        top_model_replacement_opportunities=top_model_opportunities,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_candidate_marginal_audit_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded_slices.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
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


def _scenario_context(
    historical_slice: HistoricalRecommendationSlice,
    *,
    final_answer: HistoricalRecommendationScenarioResult,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> _ScenarioContext:
    fixtures = _eligible_fixtures(historical_slice)
    all_candidates = _candidates_from_fixtures(
        fixtures,
        derive_market_context_signals=backtest_options.derive_market_context_signals,
        short_price_negative_edge_guardrail=(
            backtest_options.short_price_negative_edge_guardrail
        ),
        short_price_negative_edge_max_decimal_odds=(
            backtest_options.short_price_negative_edge_max_decimal_odds
        ),
        short_price_negative_edge_min_probability=(
            backtest_options.short_price_negative_edge_min_probability
        ),
        short_price_negative_edge_max_model_edge=(
            backtest_options.short_price_negative_edge_max_model_edge
        ),
        short_price_negative_edge_soft_penalty=(
            backtest_options.short_price_negative_edge_soft_penalty
        ),
        short_price_negative_edge_soft_penalty_strength=(
            backtest_options.short_price_negative_edge_soft_penalty_strength
        ),
        short_price_negative_edge_soft_penalty_competition_ids=(
            backtest_options.short_price_negative_edge_soft_penalty_competition_ids
        ),
    )
    policy_config = build_recommendation_policy_config(
        strategy=backtest_options.strategy,
        allowed_markets=backtest_options.allowed_markets,
        min_probability=backtest_options.min_probability,
        min_model_edge=backtest_options.min_model_edge,
        min_data_quality_score=backtest_options.min_data_quality_score,
        require_odds=backtest_options.require_odds,
    )
    candidates = _compress_candidate_pool(
        all_candidates,
        options=backtest_options,
        policy_config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    scenario_candidates = _scenario_candidate_pool(
        candidates,
        scenario=final_answer.scenario,
        options=backtest_options,
        policy_config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    scored_pool = rank_candidates(
        scenario_candidates,
        config=policy_config,
        as_of_time_utc=historical_slice.as_of_time_utc,
    )
    return _ScenarioContext(
        final_answer=final_answer,
        scored_pool=scored_pool,
        fixture_by_id={fixture.fixture_id: fixture for fixture in fixtures},
        backtest_options=backtest_options,
    )


def _audit_item_for_selected_leg(
    historical_slice: HistoricalRecommendationSlice,
    *,
    selected: ScoredRecommendationCandidate,
    context: _ScenarioContext,
    options: HistoricalCandidateMarginalAuditOptions,
) -> HistoricalCandidateMarginalAuditItem:
    final_answer = context.final_answer
    candidate = selected.candidate
    fixture = context.fixture_by_id.get(candidate.fixture_id)
    leg_actual_hit = _candidate_matches_actual(candidate, fixture=fixture)
    replacements = _replacement_simulations_for_selected_leg(
        selected,
        context=context,
        options=options,
    )
    model_top_replacement = _model_top_replacement(replacements)
    actual_best_replacement = _actual_best_replacement(replacements)
    item_key = _item_key(historical_slice, final_answer=final_answer, selected=selected)
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id=historical_slice.metadata.slice_id,
        competition_id=historical_slice.metadata.competition_id,
        final_answer_scenario_key=final_answer.scenario.scenario_key,
        pass_type=final_answer.scenario.pass_type,
        mode=final_answer.scenario.mode,
        final_answer_actual_hit=final_answer.actual_hit,
        selected_fixture_id=candidate.fixture_id,
        selected_market_type=candidate.market_type,
        selected_outcome=candidate.outcome,
        selected_probability=candidate.probability,
        selected_decimal_odds=candidate.decimal_odds,
        selected_model_edge=candidate.effective_model_edge(),
        selected_score=selected.score,
        selected_reason_codes=selected.reason_codes,
        leg_actual_hit=leg_actual_hit,
        original_actual_return=final_answer.actual_return,
        original_profit_loss=final_answer.profit_loss,
        original_hit_probability=(
            final_answer.expected_hit_probability
            if final_answer.expected_hit_probability is not None
            else 0.0
        ),
        original_roi=final_answer.roi,
        original_risk_score=final_answer.option.selection.evaluation.risk_score
        if final_answer.option is not None
        else 0.0,
        replacement_count=len(replacements),
        model_top_replacement=model_top_replacement,
        actual_best_replacement=actual_best_replacement,
        replacement_candidates=replacements,
        summary_json={
            "has_actual_replacement_opportunity": (
                actual_best_replacement is not None
                and actual_best_replacement.profit_loss_delta > 0
            ),
            "model_top_improves_actual": (
                model_top_replacement is not None
                and model_top_replacement.profit_loss_delta > 0
            ),
            "model_top_harms_actual": (
                model_top_replacement is not None
                and model_top_replacement.profit_loss_delta < 0
            ),
        },
    )


def _replacement_simulations_for_selected_leg(
    selected: ScoredRecommendationCandidate,
    *,
    context: _ScenarioContext,
    options: HistoricalCandidateMarginalAuditOptions,
) -> list[HistoricalCandidateReplacementSimulation]:
    final_answer = context.final_answer
    if final_answer.option is None:
        return []
    selected_scored = final_answer.option.selection.selected_candidates
    replacement_candidates = _replacement_candidates_for_selected_leg(
        selected,
        selected_scored=selected_scored,
        scored_pool=context.scored_pool,
        options=options,
    )
    simulations: list[HistoricalCandidateReplacementSimulation] = []
    for replacement_rank, replacement in enumerate(replacement_candidates, start=1):
        simulation = _simulate_replacement(
            selected,
            replacement=replacement,
            replacement_rank=replacement_rank,
            selected_scored=selected_scored,
            context=context,
        )
        if simulation is not None:
            simulations.append(simulation)
    return simulations


def _replacement_candidates_for_selected_leg(
    selected: ScoredRecommendationCandidate,
    *,
    selected_scored: Sequence[ScoredRecommendationCandidate],
    scored_pool: Sequence[ScoredRecommendationCandidate],
    options: HistoricalCandidateMarginalAuditOptions,
) -> list[ScoredRecommendationCandidate]:
    removed_key = _candidate_identity(selected.candidate)
    selected_without_removed = [
        item
        for item in selected_scored
        if _candidate_identity(item.candidate) != removed_key
    ]
    selected_keys_without_removed = {
        _candidate_identity(item.candidate) for item in selected_without_removed
    }
    selected_fixture_ids_without_removed = {
        item.candidate.fixture_id for item in selected_without_removed
    }
    replacements: list[ScoredRecommendationCandidate] = []
    for scored in scored_pool:
        candidate = scored.candidate
        candidate_key = _candidate_identity(candidate)
        if candidate_key == removed_key:
            continue
        if candidate_key in selected_keys_without_removed:
            continue
        if candidate.decimal_odds is None:
            continue
        if options.same_market_type_only and (
            candidate.market_type != selected.candidate.market_type
        ):
            continue
        if candidate.fixture_id in selected_fixture_ids_without_removed:
            continue
        replacements.append(scored)
        if len(replacements) >= options.max_replacement_candidates_per_leg:
            break
    return replacements


def _simulate_replacement(
    selected: ScoredRecommendationCandidate,
    *,
    replacement: ScoredRecommendationCandidate,
    replacement_rank: int,
    selected_scored: Sequence[ScoredRecommendationCandidate],
    context: _ScenarioContext,
) -> HistoricalCandidateReplacementSimulation | None:
    final_answer = context.final_answer
    replaced_scored = [
        replacement
        if _candidate_identity(item.candidate) == _candidate_identity(selected.candidate)
        else item
        for item in selected_scored
    ]
    legs = _legs_from_scored_candidates(replaced_scored)
    if not legs:
        return None
    evaluation = evaluate_parlay(
        legs,
        pass_type=final_answer.scenario.pass_type,
        unit_stake=context.backtest_options.unit_stake,
        max_budget=context.backtest_options.max_budget,
    )
    if not evaluation.rule_valid:
        return None
    selection = RecommendationSelection(
        pass_type=final_answer.scenario.pass_type,
        mode=final_answer.scenario.mode,
        selected_candidates=list(replaced_scored),
        evaluation=evaluation,
        total_score=_average(item.score for item in replaced_scored) or 0.0,
        candidate_count=len(context.scored_pool),
        excluded_candidate_count=0,
        explanation_json={
            "calculation_basis": "historical_candidate_marginal_replacement_v3_1",
            "removed_fixture_id": selected.candidate.fixture_id,
            "removed_outcome": selected.candidate.outcome,
            "replacement_fixture_id": replacement.candidate.fixture_id,
            "replacement_outcome": replacement.candidate.outcome,
        },
    )
    settlement = _settle_selection(selection, fixture_by_id=context.fixture_by_id)
    replacement_leg_actual_hit = _candidate_matches_actual(
        replacement.candidate,
        fixture=context.fixture_by_id.get(replacement.candidate.fixture_id),
    )
    quality_score = _replacement_quality_score(selection)
    profit_loss_delta = settlement.profit_loss - final_answer.profit_loss
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=replacement_rank,
        replacement_fixture_id=replacement.candidate.fixture_id,
        replacement_market_type=replacement.candidate.market_type,
        replacement_outcome=replacement.candidate.outcome,
        replacement_probability=replacement.candidate.probability,
        replacement_decimal_odds=replacement.candidate.decimal_odds,
        replacement_model_edge=replacement.candidate.effective_model_edge(),
        replacement_score=replacement.score,
        replacement_quality_score=quality_score,
        replacement_leg_actual_hit=replacement_leg_actual_hit,
        simulated_actual_hit=settlement.actual_hit,
        simulated_actual_return=settlement.actual_return,
        simulated_profit_loss=settlement.profit_loss,
        simulated_hit_probability=evaluation.hit_probability,
        simulated_roi=evaluation.roi,
        simulated_risk_score=evaluation.risk_score,
        actual_return_delta=settlement.actual_return - final_answer.actual_return,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=(
            evaluation.hit_probability
            - (
                final_answer.expected_hit_probability
                if final_answer.expected_hit_probability is not None
                else 0.0
            )
        ),
        roi_delta=evaluation.roi - final_answer.roi,
        risk_score_delta=evaluation.risk_score
        - final_answer.option.selection.evaluation.risk_score
        if final_answer.option is not None
        else evaluation.risk_score,
        decision=_replacement_decision(profit_loss_delta),
    )


def _legs_from_scored_candidates(
    scored_candidates: Sequence[ScoredRecommendationCandidate],
) -> list[ParlayLegSelection]:
    grouped: dict[
        tuple[str, str, float | None, str | None],
        list[ScoredRecommendationCandidate],
    ] = {}
    for scored in scored_candidates:
        candidate = scored.candidate
        grouped.setdefault(
            (candidate.fixture_id, candidate.market_type, candidate.line, candidate.side),
            [],
        ).append(scored)

    legs: list[ParlayLegSelection] = []
    for group in grouped.values():
        first = group[0].candidate
        outcomes: list[str] = []
        probabilities: dict[str, float] = {}
        odds: dict[str, float] = {}
        for scored in group:
            candidate = scored.candidate
            if candidate.decimal_odds is None:
                continue
            if candidate.outcome in probabilities:
                continue
            outcomes.append(candidate.outcome)
            probabilities[candidate.outcome] = candidate.probability
            odds[candidate.outcome] = candidate.decimal_odds
        if outcomes:
            legs.append(
                ParlayLegSelection(
                    fixture_id=first.fixture_id,
                    market_type=first.market_type,
                    outcomes=outcomes,
                    probabilities=probabilities,
                    odds=odds,
                    line=first.line,
                    side=first.side,
                    model_version=first.model_version,
                    prediction_snapshot_id=first.prediction_snapshot_id,
                    correlation_key=first.correlation_key,
                    data_quality_score=first.data_quality_score,
                )
            )
    return legs


def _replacement_quality_score(selection: RecommendationSelection) -> float:
    evaluation = selection.evaluation
    average_score = _average(item.score for item in selection.selected_candidates) or 0.0
    average_data_quality = (
        _average(
            item.candidate.data_quality_score for item in selection.selected_candidates
        )
        or 0.0
    )
    roi_component = _clamp(0.50 + evaluation.roi / 2.0)
    risk_component = 1.0 - evaluation.risk_score
    return _clamp(
        0.36 * evaluation.hit_probability
        + 0.24 * roi_component
        + 0.15 * average_score
        + 0.15 * risk_component
        + 0.10 * (average_data_quality / 100.0)
    )


def _model_top_replacement(
    replacements: Sequence[HistoricalCandidateReplacementSimulation],
) -> HistoricalCandidateReplacementSimulation | None:
    if not replacements:
        return None
    return max(
        replacements,
        key=lambda replacement: (
            replacement.replacement_quality_score,
            replacement.simulated_hit_probability,
            replacement.simulated_roi,
            -replacement.simulated_risk_score,
            -replacement.replacement_rank,
        ),
    )


def _actual_best_replacement(
    replacements: Sequence[HistoricalCandidateReplacementSimulation],
) -> HistoricalCandidateReplacementSimulation | None:
    if not replacements:
        return None
    return max(
        replacements,
        key=lambda replacement: (
            replacement.profit_loss_delta,
            replacement.actual_return_delta,
            replacement.simulated_actual_hit,
            replacement.hit_probability_delta,
            -replacement.replacement_rank,
        ),
    )


def _top_actual_replacement_opportunities(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
) -> list[HistoricalCandidateMarginalAuditItem]:
    return sorted(
        (
            item
            for item in items
            if item.actual_best_replacement is not None
            and item.actual_best_replacement.profit_loss_delta > 0
        ),
        key=lambda item: (
            item.actual_best_replacement.profit_loss_delta
            if item.actual_best_replacement is not None
            else -999.0,
            item.actual_best_replacement.hit_probability_delta
            if item.actual_best_replacement is not None
            else -999.0,
            item.item_key,
        ),
        reverse=True,
    )[:20]


def _top_model_replacement_opportunities(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
) -> list[HistoricalCandidateMarginalAuditItem]:
    return sorted(
        (
            item
            for item in items
            if item.model_top_replacement is not None
            and item.model_top_replacement.profit_loss_delta > 0
        ),
        key=lambda item: (
            item.model_top_replacement.profit_loss_delta
            if item.model_top_replacement is not None
            else -999.0,
            item.model_top_replacement.replacement_quality_score
            if item.model_top_replacement is not None
            else -999.0,
            item.item_key,
        ),
        reverse=True,
    )[:20]


def _candidate_matches_actual(
    candidate: RecommendationCandidate,
    *,
    fixture: HistoricalFixture | None,
) -> bool:
    if fixture is None:
        return False
    if candidate.market_type == "1x2":
        return candidate.outcome == fixture.actual_1x2_outcome
    if candidate.market_type == "correct_score":
        return candidate.outcome == f"{fixture.actual_home_goals}-{fixture.actual_away_goals}"
    return False


def _replacement_decision(profit_loss_delta: float) -> HistoricalMarginalReplacementDecision:
    if profit_loss_delta > 0:
        return "actual_improved"
    if profit_loss_delta < 0:
        return "actual_regressed"
    return "actual_unchanged"


def _candidate_identity(
    candidate: RecommendationCandidate,
) -> tuple[str, str, str, float | None, str | None]:
    return (
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
        candidate.line,
        candidate.side,
    )


def _item_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    final_answer: HistoricalRecommendationScenarioResult,
    selected: ScoredRecommendationCandidate,
) -> str:
    payload = "|".join(
        [
            historical_slice.metadata.slice_id,
            final_answer.scenario.scenario_key,
            selected.candidate.fixture_id,
            selected.candidate.market_type,
            selected.candidate.outcome,
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"candidate_marginal:{historical_slice.metadata.slice_id}:{digest}"


def _report_key(
    summary: dict[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    slice_payload = ";".join(
        f"{historical_slice.metadata.slice_id}@{historical_slice.as_of_time_utc.isoformat()}"
        for historical_slice in historical_slices
    )
    payload = dumps(
        {
            "summary": summary,
            "slices": slice_payload,
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_candidate_marginal_audit:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Audit selected final-answer legs with marginal replacement simulations."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", action="append", default=[], type=Path)
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
    parser.add_argument("--max-replacement-candidates-per-leg", type=int, default=5)
    parser.add_argument(
        "--same-market-type-only",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--target-probability-min", type=float)
    parser.add_argument("--target-probability-max", type=float)
    parser.add_argument("--target-min-decimal-odds", type=float)
    parser.add_argument("--target-max-decimal-odds", type=float)
    parser.add_argument("--target-max-model-edge", type=float)
    parser.add_argument("--missed-legs-only", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalCandidateMarginalAuditOptions:
    return HistoricalCandidateMarginalAuditOptions(
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
        max_replacement_candidates_per_leg=args.max_replacement_candidates_per_leg,
        same_market_type_only=args.same_market_type_only,
        derive_market_context_signals=args.derive_market_context_signals,
        target_probability_min=args.target_probability_min,
        target_probability_max=args.target_probability_max,
        target_min_decimal_odds=args.target_min_decimal_odds,
        target_max_decimal_odds=args.target_max_decimal_odds,
        target_max_model_edge=args.target_max_model_edge,
        missed_legs_only=args.missed_legs_only,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    manifest_slices = [
        historical_slice
        for bundle in bundles
        for historical_slice in bundle.slices
    ]
    resolved_slice_paths = [
        slice_path
        for bundle in bundles
        for slice_path in bundle.resolved_slice_paths
    ]
    warnings = [warning for bundle in bundles for warning in bundle.warnings]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *explicit_slices],
        resolved_slice_paths=[*resolved_slice_paths, *args.slice_paths],
        manifest_result=bundles[0] if len(bundles) == 1 else None,
        manifest_results=bundles,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.manifest.slices),
        "resolved_slice_count": len(manifest_result.resolved_slice_paths),
        "warnings": manifest_result.warnings,
    }


def _include_competition(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalCandidateMarginalAuditOptions,
) -> bool:
    if not options.focus_competition_ids:
        return True
    return historical_slice.metadata.competition_id in options.focus_competition_ids


def _selected_leg_matches_target_filter(
    scored: ScoredRecommendationCandidate,
    *,
    leg_actual_hit: bool,
    options: HistoricalCandidateMarginalAuditOptions,
) -> bool:
    candidate = scored.candidate
    if options.missed_legs_only and leg_actual_hit:
        return False
    if (
        options.target_probability_min is not None
        and candidate.probability < options.target_probability_min
    ):
        return False
    if (
        options.target_probability_max is not None
        and candidate.probability >= options.target_probability_max
    ):
        return False
    if options.target_min_decimal_odds is not None and (
        candidate.decimal_odds is None
        or candidate.decimal_odds < options.target_min_decimal_odds
    ):
        return False
    if (
        options.target_max_decimal_odds is not None
        and candidate.decimal_odds is not None
        and candidate.decimal_odds > options.target_max_decimal_odds
    ):
        return False
    return not (
        options.target_max_model_edge is not None
        and candidate.effective_model_edge() >= options.target_max_model_edge
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _average(values: Iterable[float | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
