from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations.global_planner import RecommendationGlobalPlanOption
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_budget_stability_audit import (
    HistoricalBudgetStabilityAuditOptions,
    _options_from_args,
    _parse_args,
    build_historical_budget_stability_audit_report,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)


def test_budget_stability_audit_detects_harmful_low_budget_change() -> None:
    report = build_historical_budget_stability_audit_report(
        [_slice("slice_a"), _slice("slice_b")],
        options=HistoricalBudgetStabilityAuditOptions(
            budgets=(10.0, 20.0),
            reference_budget=20.0,
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1", "2x1"),
                modes=("single", "multiple"),
                unit_stake=2.0,
                max_budget=20.0,
            ),
        ),
        backtest_runner=_fake_budget_runner,
    )

    low_budget_run = next(run for run in report.budget_runs if run.budget == 10.0)
    low_budget_summary = next(
        summary for summary in report.comparison_summaries if summary.budget == 10.0
    )
    top_change = report.top_changes[0]

    assert report.slice_count == 2
    assert report.reference_budget == 20.0
    assert report.changed_slice_count == 1
    assert report.harmful_change_count == 1
    assert report.beneficial_change_count == 0
    assert low_budget_run.final_answer_count == 2
    assert low_budget_run.final_hit_rate == 0.5
    assert low_budget_run.budget_adjusted_final_answer_count == 1
    assert low_budget_run.heavy_budget_adjusted_final_answer_count == 1
    assert low_budget_summary.comparable_count == 2
    assert low_budget_summary.signature_changed_count == 1
    assert low_budget_summary.hit_delta_count == -1
    assert low_budget_summary.harmful_change_count == 1
    assert low_budget_summary.budget_adjusted_change_count == 1
    assert top_change.slice_id == "slice_a"
    assert top_change.signature_changed is True
    assert top_change.hit_delta == -1
    assert top_change.profit_loss_delta < 0
    assert top_change.budget_adjustment_quality == 0.30
    assert "budget_lower_than_reference" in top_change.reason_codes
    assert "budget_harmed_hit" in top_change.reason_codes
    assert "budget_adjustment_applied" in top_change.reason_codes
    assert "heavy_budget_adjustment" in top_change.reason_codes


def test_budget_stability_audit_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--suite-manifest",
            "suite.json",
            "--budgets",
            "6,10,20",
            "--reference-budget",
            "20",
            "--pass-types",
            "1x1,6x1",
            "--modes",
            "single",
            "--unit-stake",
            "3",
            "--candidate-fixture-limit",
            "9",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "3",
            "--derive-market-context-signals",
            "--heavy-budget-adjustment-quality-threshold",
            "0.4",
        ]
    )
    options = _options_from_args(args)

    assert options.budgets == (6.0, 10.0, 20.0)
    assert options.reference_budget == 20.0
    assert options.heavy_budget_adjustment_quality_threshold == 0.4
    assert options.backtest_options.pass_types == ("1x1", "6x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.unit_stake == 3.0
    assert options.backtest_options.max_budget == 20.0
    assert options.backtest_options.candidate_fixture_limit == 9
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 3
    assert options.backtest_options.derive_market_context_signals is True


def _fake_budget_runner(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestResult:
    if historical_slice.metadata.slice_id == "slice_a" and options.max_budget < 20.0:
        return _result(
            "slice_a",
            scenario_key="low_budget_multiple",
            fixture_id="fixture_a_low",
            pass_type="2x1",
            mode="multiple",
            hit_probability=0.58,
            actual_hit=False,
            actual_return=0.0,
            budget_adjustment={
                "strategy": "prune_lowest_marginal_unlocked_options",
                "original_total_stake": 18.0,
                "optimized_total_stake": 2.0,
                "original_total_atomic_bets": 9,
                "optimized_total_atomic_bets": 1,
                "original_quality_score": 0.82,
                "optimized_quality_score": 0.30,
                "within_budget": True,
            },
        )
    if historical_slice.metadata.slice_id == "slice_a":
        return _result(
            "slice_a",
            scenario_key="reference_single",
            fixture_id="fixture_a_ref",
            pass_type="1x1",
            mode="single",
            hit_probability=0.64,
            actual_hit=True,
            actual_return=4.40,
        )
    return _result(
        historical_slice.metadata.slice_id,
        scenario_key="stable_single",
        fixture_id=f"{historical_slice.metadata.slice_id}_stable",
        pass_type="1x1",
        mode="single",
        hit_probability=0.68,
        actual_hit=True,
        actual_return=3.20,
    )


def _slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id="ENG-PREM",
            season="2024-2025",
            result_source="fixture",
            odds_source="fixture",
            prediction_source="fixture",
        ),
        as_of_time_utc=datetime(2024, 8, 1, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture",
                competition_id="ENG-PREM",
                kickoff_time_utc=datetime(2024, 8, 2, tzinfo=UTC),
                home_team_name="Home",
                away_team_name="Away",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=datetime(2024, 8, 1, tzinfo=UTC),
                model_version="test-model",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.65,
                        decimal_odds=1.80,
                    )
                ],
            )
        ],
    )


def _result(
    slice_id: str,
    *,
    scenario_key: str,
    fixture_id: str,
    pass_type: str,
    mode: RecommendationMode,
    hit_probability: float,
    actual_hit: bool,
    actual_return: float,
    budget_adjustment: dict[str, object] | None = None,
) -> HistoricalRecommendationBacktestResult:
    total_stake = 2.0
    profit_loss = actual_return - total_stake
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key=scenario_key,
            pass_type=pass_type,
            mode=mode,
        ),
        status="completed",
        selected_fixture_ids=[fixture_id],
        selected_outcomes={fixture_id: ["home_win"]},
        total_stake=total_stake,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        expected_hit_probability=hit_probability,
        actual_hit=actual_hit,
        option=_option(
            scenario_key,
            fixture_id=fixture_id,
            pass_type=pass_type,
            mode=mode,
            hit_probability=hit_probability,
            budget_adjustment=budget_adjustment,
        ),
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}:{scenario_key}",
        slice_id=slice_id,
        as_of_time_utc=datetime(2024, 8, 1, tzinfo=UTC),
        fixture_count=1,
        candidate_count=1,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=final_answer,
        scenarios=[final_answer],
        final_hit_sample_size=1,
        final_hit_count=1 if actual_hit else 0,
        final_hit_rate=1.0 if actual_hit else 0.0,
        total_stake=total_stake,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        upset_opportunity_count=0,
        upset_capture_count=0,
    )


def _option(
    option_key: str,
    *,
    fixture_id: str,
    pass_type: str,
    mode: RecommendationMode,
    hit_probability: float,
    budget_adjustment: dict[str, object] | None,
) -> RecommendationGlobalPlanOption:
    total_stake = 2.0
    selection = RecommendationSelection(
        pass_type=pass_type,
        mode=mode,
        selected_candidates=[
            ScoredRecommendationCandidate(
                candidate=RecommendationCandidate(
                    fixture_id=fixture_id,
                    market_type="1x2",
                    outcome="home_win",
                    probability=hit_probability,
                    decimal_odds=2.20,
                    market_probability=1 / 2.20,
                    data_quality_score=90.0,
                    model_confidence_score=0.85,
                    calibration_score=0.85,
                    odds_stability_score=0.80,
                ),
                score=0.75,
            )
        ],
        evaluation=ParlayEvaluation(
            pass_type=pass_type,
            is_multiple=mode == "multiple",
            unit_stake=2.0,
            total_atomic_bets=1,
            total_stake=total_stake,
            hit_probability=hit_probability,
            expected_payout=total_stake * 2.20 * hit_probability,
            expected_value=total_stake * 2.20 * hit_probability - total_stake,
            roi=0.10,
            risk_score=1.0 - hit_probability,
            rule_valid=True,
        ),
        total_score=0.75,
        candidate_count=1,
        excluded_candidate_count=0,
        explanation_json=(
            {"budget_adjustment": budget_adjustment}
            if budget_adjustment is not None
            else {}
        ),
    )
    return RecommendationGlobalPlanOption(
        option_key=f"option:{option_key}",
        option_type="multiple_parlay" if mode == "multiple" else "single_parlay",
        pass_type=pass_type,
        mode=mode,
        planner_score=0.75,
        within_budget=True,
        selection=selection,
    )
