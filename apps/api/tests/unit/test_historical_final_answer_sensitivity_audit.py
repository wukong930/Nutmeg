from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations.global_planner import RecommendationGlobalPlanOption
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
)
from nutmeg.recommendations.historical_final_answer_sensitivity_audit import (
    HistoricalFinalAnswerSensitivityAuditOptions,
    build_historical_final_answer_sensitivity_audit_report,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)


def test_final_answer_sensitivity_audit_identifies_actionable_runner_up() -> None:
    suite = _suite(
        winner_actual_hit=False,
        runner_up_actual_hit=True,
    )

    report = build_historical_final_answer_sensitivity_audit_report(
        suite,
        options=HistoricalFinalAnswerSensitivityAuditOptions(
            max_near_miss_score_gap=0.03,
        ),
    )

    item = report.top_near_misses[0]

    assert report.runner_up_count == 1
    assert report.runner_up_coverage_rate == 1.0
    assert report.near_miss_count == 1
    assert report.near_miss_rate == 1.0
    assert report.actionable_near_miss_count == 1
    assert report.actionable_near_miss_rate == 1.0
    assert report.runner_up_higher_hit_probability_count == 1
    assert report.winner_loss_runner_up_hit_count == 1
    assert report.diagnostic_codes == []
    assert item.runner_up_hit_probability_delta > 0
    assert item.final_answer_signature_changed is True
    assert "near_miss_score_gap" in item.reason_codes
    assert "runner_up_higher_hit_probability" in item.reason_codes
    assert "winner_lost_runner_up_hit" in item.reason_codes


def _suite(
    *,
    winner_actual_hit: bool,
    runner_up_actual_hit: bool,
) -> HistoricalRecommendationBacktestSuiteResult:
    winner = _scenario_result(
        "winner",
        fixture_id="fixture_a",
        planner_score=0.80,
        hit_probability=0.50,
        roi=0.10,
        actual_hit=winner_actual_hit,
        actual_return=0.0 if not winner_actual_hit else 2.20,
    )
    runner_up = _scenario_result(
        "runner_up",
        fixture_id="fixture_b",
        planner_score=0.70,
        hit_probability=0.55,
        roi=0.10,
        actual_hit=runner_up_actual_hit,
        actual_return=2.20 if runner_up_actual_hit else 0.0,
    )
    result = HistoricalRecommendationBacktestResult(
        backtest_key="backtest:test",
        slice_id="slice_a",
        as_of_time_utc=datetime(2024, 8, 1, tzinfo=UTC),
        fixture_count=2,
        candidate_count=2,
        scenario_count=2,
        completed_count=2,
        failed_count=0,
        final_answer=winner,
        scenarios=[winner, runner_up],
        final_hit_sample_size=1,
        final_hit_count=1 if winner_actual_hit else 0,
        final_hit_rate=1.0 if winner_actual_hit else 0.0,
        total_stake=winner.total_stake,
        actual_return=winner.actual_return,
        profit_loss=winner.profit_loss,
        roi=winner.roi,
        upset_opportunity_count=0,
        upset_capture_count=0,
    )
    comparison = HistoricalRecommendationBacktestComparisonResult(
        comparison_key="comparison:test",
        slice_id="slice_a",
        baseline_optimizer_profile="solver",
        candidate_optimizer_profile="solver",
        status="same",
        baseline=result,
        candidate=result,
    )
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key="suite:test",
        status="same",
        slice_count=1,
        comparison_count=1,
        baseline_optimizer_profile="solver",
        candidate_optimizer_profile="solver",
        comparisons=[comparison],
    )


def _scenario_result(
    scenario_key: str,
    *,
    fixture_id: str,
    planner_score: float,
    hit_probability: float,
    roi: float,
    actual_hit: bool,
    actual_return: float,
) -> HistoricalRecommendationScenarioResult:
    total_stake = 2.0
    profit_loss = actual_return - total_stake
    option = RecommendationGlobalPlanOption(
        option_key=f"option:{scenario_key}",
        option_type="single_parlay",
        pass_type="1x1",
        mode="single",
        planner_score=planner_score,
        within_budget=True,
        selection=RecommendationSelection(
            pass_type="1x1",
            mode="single",
            selected_candidates=[
                ScoredRecommendationCandidate(
                    candidate=RecommendationCandidate(
                        fixture_id=fixture_id,
                        market_type="1x2",
                        outcome="home_win",
                        probability=hit_probability,
                        decimal_odds=2.20,
                        market_probability=1 / 2.20,
                        data_quality_score=90,
                        model_confidence_score=0.90,
                        calibration_score=0.90,
                        odds_stability_score=0.90,
                    ),
                    score=0.70,
                )
            ],
            evaluation=ParlayEvaluation(
                pass_type="1x1",
                unit_stake=2.0,
                total_atomic_bets=1,
                total_stake=total_stake,
                hit_probability=hit_probability,
                expected_payout=2.0 * 2.20 * hit_probability,
                expected_value=2.0 * 2.20 * hit_probability - 2.0,
                roi=roi,
                risk_score=1.0 - hit_probability,
                rule_valid=True,
            ),
            total_score=planner_score,
            candidate_count=1,
            excluded_candidate_count=0,
        ),
    )
    return HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key=scenario_key,
            pass_type="1x1",
            mode="single",
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
        option=option,
    )
