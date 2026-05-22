from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.parlay import AtomicBet, AtomicLeg, ParlayEvaluation
from nutmeg.recommendations.global_planner import RecommendationGlobalPlanOption
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
)
from nutmeg.recommendations.historical_final_answer_segment_audit import (
    HistoricalFinalAnswerSegmentAuditOptions,
    HistoricalFinalAnswerSegmentMetric,
    build_historical_final_answer_segment_audit_report,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)


def test_final_answer_segment_audit_identifies_loss_driver_segments() -> None:
    suite = _suite(
        [
            _comparison(
                slice_id="slice_short_loss",
                pass_type="1x1",
                mode="single",
                actual_hit=False,
                competition_id="EPL",
                odds_product=1.25,
                expected_hit_probability=0.72,
            ),
            _comparison(
                slice_id="slice_medium_hit",
                pass_type="2x1",
                mode="single",
                actual_hit=True,
                competition_id="JPN_J1",
                odds_product=2.40,
                expected_hit_probability=0.42,
            ),
        ]
    )

    report = build_historical_final_answer_segment_audit_report(
        suite,
        options=HistoricalFinalAnswerSegmentAuditOptions(
            min_segment_sample_size=1,
            top_segment_limit=5,
        ),
    )

    assert report.overall is not None
    assert report.overall.sample_size == 2
    assert report.overall.hit_count == 1
    assert report.overall.hit_rate == 0.5
    loss_driver_keys = {segment.segment_key for segment in report.loss_driver_segments}
    assert "pass_type:1x1" in loss_driver_keys
    assert "competition:EPL" in loss_driver_keys
    assert "odds_band:1.00-1.30" in loss_driver_keys
    pass_type_segment = _segment(report.segments, "pass_type:1x1")
    assert pass_type_segment.loss_count == 1
    assert pass_type_segment.roi == -1.0
    assert report.summary_json["top_loss_driver_segment_keys"]


def test_final_answer_segment_audit_respects_min_sample_size_for_drivers() -> None:
    suite = _suite(
        [
            _comparison(
                slice_id="slice_loss",
                pass_type="1x1",
                mode="single",
                actual_hit=False,
                competition_id="EPL",
                odds_product=1.25,
                expected_hit_probability=0.72,
            )
        ]
    )

    report = build_historical_final_answer_segment_audit_report(
        suite,
        options=HistoricalFinalAnswerSegmentAuditOptions(min_segment_sample_size=2),
    )

    assert report.overall is not None
    assert report.overall.sample_size == 1
    assert report.loss_driver_segments == []
    pass_type_segment = _segment(report.segments, "pass_type:1x1")
    assert pass_type_segment.summary_json["meets_min_segment_sample_size"] is False


def test_final_answer_segment_audit_can_include_interaction_segments() -> None:
    suite = _suite(
        [
            _comparison(
                slice_id="slice_short_loss",
                pass_type="1x1",
                mode="single",
                actual_hit=False,
                competition_id="EPL",
                odds_product=1.25,
                expected_hit_probability=0.72,
            ),
            _comparison(
                slice_id="slice_medium_hit",
                pass_type="2x1",
                mode="single",
                actual_hit=True,
                competition_id="JPN_J1",
                odds_product=2.40,
                expected_hit_probability=0.42,
            ),
        ]
    )

    report = build_historical_final_answer_segment_audit_report(
        suite,
        options=HistoricalFinalAnswerSegmentAuditOptions(
            min_segment_sample_size=1,
            include_interaction_segments=True,
        ),
    )

    assert report.summary_json["include_interaction_segments"] is True
    assert _segment(report.segments, "competition_pass_type:EPL:1x1").loss_count == 1
    assert _segment(report.segments, "competition_odds_band:EPL:1.00-1.30").roi == -1.0
    assert (
        _segment(report.segments, "pass_type_hit_probability_band:1x1:0.70-0.85")
        .loss_count
        == 1
    )
    loss_driver_keys = {segment.segment_key for segment in report.loss_driver_segments}
    assert "competition_pass_type:EPL:1x1" in loss_driver_keys


def test_final_answer_segment_audit_can_read_baseline_side() -> None:
    suite = _suite(
        [
            _comparison(
                slice_id="slice_candidate_loss_baseline_hit",
                pass_type="1x1",
                mode="single",
                actual_hit=False,
                competition_id="EPL",
                odds_product=1.25,
                expected_hit_probability=0.72,
                baseline_actual_hit=True,
                baseline_competition_id="ITA_SERIE_A",
            )
        ]
    )

    report = build_historical_final_answer_segment_audit_report(
        suite,
        options=HistoricalFinalAnswerSegmentAuditOptions(
            side="baseline",
            min_segment_sample_size=1,
        ),
    )

    assert report.evaluation_side == "baseline"
    assert report.overall is not None
    assert report.overall.hit_count == 1
    assert _segment(report.segments, "competition:ITA_SERIE_A").hit_count == 1


def _segment(
    segments: list[HistoricalFinalAnswerSegmentMetric],
    key: str,
) -> HistoricalFinalAnswerSegmentMetric:
    for segment in segments:
        if segment.segment_key == key:
            return segment
    raise AssertionError(f"missing segment {key}")


def _suite(
    comparisons: list[HistoricalRecommendationBacktestComparisonResult],
) -> HistoricalRecommendationBacktestSuiteResult:
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key="historical_backtest_suite:segment-audit-test",
        status="mixed",
        slice_count=len(comparisons),
        comparison_count=len(comparisons),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
        aggregate_deltas_json={},
        warnings=[],
        summary_json={},
    )


def _comparison(
    *,
    slice_id: str,
    pass_type: str,
    mode: RecommendationMode,
    actual_hit: bool,
    competition_id: str,
    odds_product: float,
    expected_hit_probability: float,
    baseline_actual_hit: bool | None = None,
    baseline_competition_id: str | None = None,
) -> HistoricalRecommendationBacktestComparisonResult:
    candidate = _backtest_result(
        slice_id=slice_id,
        pass_type=pass_type,
        mode=mode,
        actual_hit=actual_hit,
        competition_id=competition_id,
        odds_product=odds_product,
        expected_hit_probability=expected_hit_probability,
    )
    baseline = _backtest_result(
        slice_id=f"{slice_id}_baseline",
        pass_type=pass_type,
        mode=mode,
        actual_hit=baseline_actual_hit if baseline_actual_hit is not None else actual_hit,
        competition_id=baseline_competition_id or competition_id,
        odds_product=odds_product,
        expected_hit_probability=expected_hit_probability,
    )
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{slice_id}",
        slice_id=slice_id,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        status="unchanged",
        baseline=baseline,
        candidate=candidate,
        deltas_json={},
        summary_json={},
    )


def _backtest_result(
    *,
    slice_id: str,
    pass_type: str,
    mode: RecommendationMode,
    actual_hit: bool,
    competition_id: str,
    odds_product: float,
    expected_hit_probability: float,
) -> HistoricalRecommendationBacktestResult:
    final_answer = _scenario_result(
        pass_type=pass_type,
        mode=mode,
        actual_hit=actual_hit,
        competition_id=competition_id,
        odds_product=odds_product,
        expected_hit_probability=expected_hit_probability,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}",
        slice_id=slice_id,
        as_of_time_utc=_dt(),
        fixture_count=len(final_answer.selected_fixture_ids),
        candidate_count=len(final_answer.selected_fixture_ids),
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=final_answer,
        scenarios=[final_answer],
        final_hit_sample_size=1,
        final_hit_count=1 if actual_hit else 0,
        final_hit_rate=1.0 if actual_hit else 0.0,
        total_stake=final_answer.total_stake,
        actual_return=final_answer.actual_return,
        profit_loss=final_answer.profit_loss,
        roi=final_answer.roi,
        mean_calibration_error=final_answer.calibration_error,
        brier_score=final_answer.brier_score,
        log_loss=final_answer.log_loss,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=None,
        warnings=[],
        summary_json={},
    )


def _scenario_result(
    *,
    pass_type: str,
    mode: RecommendationMode,
    actual_hit: bool,
    competition_id: str,
    odds_product: float,
    expected_hit_probability: float,
) -> HistoricalRecommendationScenarioResult:
    selected_candidates = [
        _scored_candidate(
            fixture_id=f"{competition_id}_{index}",
            competition_id=competition_id,
            decimal_odds=odds_product ** (1 / max(_leg_count(pass_type), 1)),
            probability=expected_hit_probability ** (1 / max(_leg_count(pass_type), 1)),
        )
        for index in range(_leg_count(pass_type))
    ]
    atomic_bet = AtomicBet(
        legs=[
            AtomicLeg(
                fixture_id=scored.candidate.fixture_id,
                market_type=scored.candidate.market_type,
                outcome=scored.candidate.outcome,
                probability=scored.candidate.probability,
                odds=scored.candidate.decimal_odds or 2.0,
            )
            for scored in selected_candidates
        ],
        stake=2.0,
        probability=expected_hit_probability,
        odds_product=odds_product,
        expected_payout=2.0 * odds_product * expected_hit_probability,
        expected_value=2.0 * odds_product * expected_hit_probability - 2.0,
        roi=odds_product * expected_hit_probability - 1.0,
    )
    actual_return = 2.0 * odds_product if actual_hit else 0.0
    evaluation = ParlayEvaluation(
        pass_type=pass_type,
        is_multiple=mode == "multiple",
        unit_stake=2.0,
        multiplier=1,
        total_atomic_bets=1,
        total_stake=2.0,
        hit_probability=expected_hit_probability,
        expected_payout=atomic_bet.expected_payout,
        expected_value=atomic_bet.expected_value,
        roi=atomic_bet.roi,
        atomic_bets=[atomic_bet],
    )
    selection = RecommendationSelection(
        pass_type=pass_type,
        mode=mode,
        selected_candidates=selected_candidates,
        evaluation=evaluation,
        total_score=0.70,
        candidate_count=len(selected_candidates),
        excluded_candidate_count=0,
    )
    option = RecommendationGlobalPlanOption(
        option_key=f"historical:{pass_type}:{mode}",
        option_type="single_parlay" if pass_type != "1x1" else "standalone_single",
        pass_type=pass_type,
        mode=mode,
        planner_score=0.70,
        within_budget=True,
        selection=selection,
    )
    return HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key=f"{pass_type}:{mode}",
            pass_type=pass_type,
            mode=mode,
        ),
        status="completed",
        selected_fixture_ids=selection.fixture_ids,
        selected_outcomes={
            scored.candidate.fixture_id: [scored.candidate.outcome]
            for scored in selected_candidates
        },
        total_stake=2.0,
        actual_return=actual_return,
        profit_loss=actual_return - 2.0,
        roi=(actual_return - 2.0) / 2.0,
        expected_hit_probability=expected_hit_probability,
        actual_hit=actual_hit,
        calibration_error=abs(expected_hit_probability - float(actual_hit)),
        brier_score=(expected_hit_probability - float(actual_hit)) ** 2,
        log_loss=0.2,
        option=option,
    )


def _scored_candidate(
    *,
    fixture_id: str,
    competition_id: str,
    decimal_odds: float,
    probability: float,
) -> ScoredRecommendationCandidate:
    return ScoredRecommendationCandidate(
        candidate=RecommendationCandidate(
            fixture_id=fixture_id,
            market_type="1x2",
            outcome="home_win",
            probability=probability,
            decimal_odds=decimal_odds,
            metadata_json={"competition_id": competition_id},
        ),
        score=0.70,
    )


def _leg_count(pass_type: str) -> int:
    return int(pass_type.split("x", maxsplit=1)[0])


def _dt() -> datetime:
    return datetime(2026, 5, 15, 0, tzinfo=UTC)
