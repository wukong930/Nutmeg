from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads

import pytest

from nutmeg.recommendations import (
    historical_final_answer_segment_penalty_rolling_admission as admission,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_grid import (
    HistoricalFinalAnswerSegmentPenaltyCandidate,
    HistoricalFinalAnswerSegmentPenaltyGridReport,
)


def test_segment_penalty_rolling_admission_accepts_when_active_folds_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _passing_fake_run,
    )

    report = admission.build_historical_final_answer_segment_penalty_rolling_admission_report(
        [
            _slice("esp_2020", competition_id="ESP_LA_LIGA", season="2020_2021"),
            _slice("ger_2020", competition_id="GER_BUNDESLIGA", season="2020_2021"),
            _slice("esp_2021", competition_id="ESP_LA_LIGA", season="2021_2022"),
            _slice("ger_2021", competition_id="GER_BUNDESLIGA", season="2021_2022"),
            _slice("epl_2021", competition_id="EPL", season="2021_2022"),
        ],
        grid_report=_grid_report(),
        options=admission.HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(
            min_overall_final_answer_count=5,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_profile_allowed is True
    assert report.overall_fold.penalty_option_count == 4
    assert report.overall_fold.final_answer_hit_delta_count == 1
    assert report.active_competition_fold_count == 2
    assert report.active_season_fold_count == 2
    assert report.active_rolling_fold_count == 2
    assert report.failed_fold_count == 0


def test_segment_penalty_rolling_admission_shadow_only_when_fold_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _one_competition_regresses_fake_run,
    )

    report = admission.build_historical_final_answer_segment_penalty_rolling_admission_report(
        [
            _slice("esp_2020", competition_id="ESP_LA_LIGA", season="2020_2021"),
            _slice("ger_2020", competition_id="GER_BUNDESLIGA", season="2020_2021"),
            _slice("esp_2021", competition_id="ESP_LA_LIGA", season="2021_2022"),
            _slice("ger_2021", competition_id="GER_BUNDESLIGA", season="2021_2022"),
        ],
        grid_report=_grid_report(),
        options=admission.HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "shadow_only"
    assert report.candidate_profile_allowed is False
    assert report.shadow_allowed is True
    assert report.failed_fold_count >= 1
    failed_fold_ids = {fold.fold_id for fold in report.folds if fold.status == "failed"}
    assert "competition:GER_BUNDESLIGA" in failed_fold_ids
    assert any(check.name == "failed_fold_count" for check in report.checks)


def test_segment_penalty_rolling_admission_cli_options_loader_and_main(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _passing_fake_run,
    )
    grid_path = tmp_path / "segment_grid.json"
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "rolling_admission.json"
    grid_path.write_text(f"{_grid_report().model_dump_json(indent=2)}\n", encoding="utf-8")
    slice_path.write_text(
        f"{_slice('esp_2020', competition_id='ESP_LA_LIGA').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    admission.main(
        [
            str(slice_path),
            "--grid-report",
            str(grid_path),
            "--output-path",
            str(output_path),
            "--min-overall-final-answer-count",
            "1",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "0",
            "--rolling-window-slice-count",
            "1",
            "--rolling-window-step",
            "1",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    printed = loads(capsys.readouterr().out)
    assert payload["status"] == "accepted"
    assert printed["report_key"] == payload["report_key"]
    assert payload["source_grid_report_key"] == "segment-grid:test"
    assert payload["source_candidate_key"] == "segment-candidate:test"


def test_segment_penalty_rolling_admission_preserves_global_season_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_calls: list[dict[str, object]] = []

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        observed_calls.append(
            {
                "slice_ids": [
                    historical_slice.metadata.slice_id
                    for historical_slice in historical_slices
                ],
                "competition_season_index_by_slice_id": dict(
                    resolved_options.competition_season_index_by_slice_id
                ),
                "segment_penalty": resolved_options.final_answer_segment_penalty,
                "min_competition_season_index": (
                    resolved_options.final_answer_segment_min_competition_season_index
                ),
            }
        )
        return _fake_suite(
            historical_slices,
            options=options,
            target_profit_delta=1.0,
            target_hit_delta=1,
        )

    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        fake_run,
    )

    report = admission.build_historical_final_answer_segment_penalty_rolling_admission_report(
        [
            _slice("ger_2020", competition_id="GER_BUNDESLIGA", season="2020_2021"),
            _slice("ger_2021", competition_id="GER_BUNDESLIGA", season="2021_2022"),
            _slice("ger_2022", competition_id="GER_BUNDESLIGA", season="2022_2023"),
            _slice("ger_2023", competition_id="GER_BUNDESLIGA", season="2023_2024"),
        ],
        grid_report=_grid_report(
            competition_ids=("GER_BUNDESLIGA",),
            min_competition_season_index=4,
        ),
        options=admission.HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=1,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=1,
            rolling_window_step=1,
        ),
    )

    report_index_map = report.summary_json["options"]["backtest_options"][
        "competition_season_index_by_slice_id"
    ]
    assert report_index_map["ger_2020"] == 1
    assert report_index_map["ger_2023"] == 4
    assert any(
        call["slice_ids"] == ["ger_2023"]
        and call["competition_season_index_by_slice_id"]["ger_2020"] == 1
        and call["competition_season_index_by_slice_id"]["ger_2023"] == 4
        for call in observed_calls
    )
    assert any(
        call["segment_penalty"] is True
        and call["min_competition_season_index"] == 4
        for call in observed_calls
    )


def test_segment_penalty_rolling_admission_rejects_profit_loss_harm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _profit_loss_harm_fake_run,
    )

    report = admission.build_historical_final_answer_segment_penalty_rolling_admission_report(
        [
            _slice(
                "ger_harm",
                competition_id="GER_BUNDESLIGA",
                season="2023_2024",
            ),
            _slice(
                "ger_improve",
                competition_id="GER_BUNDESLIGA",
                season="2024_2025",
            ),
        ],
        grid_report=_grid_report(competition_ids=("GER_BUNDESLIGA",)),
        options=admission.HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(
            min_overall_final_answer_count=2,
            min_active_competition_fold_count=0,
            min_active_season_fold_count=0,
            min_active_rolling_fold_count=0,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.overall_fold.final_hit_harm_count_vs_baseline == 0
    assert report.overall_fold.profit_loss_harm_count_vs_baseline == 1
    assert "profit_loss_harm_count_vs_baseline_above_threshold" in (
        report.overall_fold.failure_reasons
    )
    assert "overall_profit_loss_harm_count_vs_baseline" in failed_checks


def _passing_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    return _fake_suite(
        historical_slices,
        options=options,
        target_profit_delta=1.0,
        target_hit_delta=1,
    )


def _one_competition_regresses_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    target_profit_delta = 1.0
    target_hit_delta = 1
    if (
        {historical_slice.metadata.competition_id for historical_slice in historical_slices}
        == {"GER_BUNDESLIGA"}
    ):
        target_profit_delta = -1.0
        target_hit_delta = 0
    return _fake_suite(
        historical_slices,
        options=options,
        target_profit_delta=target_profit_delta,
        target_hit_delta=target_hit_delta,
    )


def _profit_loss_harm_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    slice_ids = [historical_slice.metadata.slice_id for historical_slice in historical_slices]
    if resolved_options.final_answer_segment_penalty:
        profit_by_slice = {"ger_harm": 0.0, "ger_improve": 2.0}
        return _suite_with_comparisons(
            "candidate-suite:profit-loss-harm",
            [
                _comparison(
                    slice_id,
                    actual_hit=True,
                    profit_loss=profit_by_slice.get(slice_id, 2.0),
                )
                for slice_id in slice_ids
            ],
            final_hit_count=len(slice_ids),
            profit_loss=sum(profit_by_slice.get(slice_id, 2.0) for slice_id in slice_ids),
            penalty_option_count=len(slice_ids),
        )
    profit_by_slice = {"ger_harm": 1.0, "ger_improve": -1.0}
    return _suite_with_comparisons(
        "baseline-suite:profit-loss-harm",
        [
            _comparison(
                slice_id,
                actual_hit=True,
                profit_loss=profit_by_slice.get(slice_id, 1.0),
            )
            for slice_id in slice_ids
        ],
        final_hit_count=len(slice_ids),
        profit_loss=sum(profit_by_slice.get(slice_id, 1.0) for slice_id in slice_ids),
    )


def _fake_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None,
    target_profit_delta: float,
    target_hit_delta: int,
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    final_answer_count = len(historical_slices)
    target_slice_count = sum(
        1
        for historical_slice in historical_slices
        if historical_slice.metadata.competition_id in {"ESP_LA_LIGA", "GER_BUNDESLIGA"}
    )
    baseline_hit_count = max(0, final_answer_count - 1)
    baseline_profit = -float(final_answer_count)
    if resolved_options.final_answer_segment_penalty and target_slice_count > 0:
        final_hit_count = min(final_answer_count, baseline_hit_count + target_hit_delta)
        profit_loss = baseline_profit + target_profit_delta
        penalty_option_count = target_slice_count
        brier_score = 0.18 if target_profit_delta >= 0 else 0.24
    else:
        final_hit_count = baseline_hit_count
        profit_loss = baseline_profit
        penalty_option_count = 0
        brier_score = 0.20
    total_stake = max(1.0, final_answer_count * 2.0)
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=(
            "candidate-suite:test"
            if resolved_options.final_answer_segment_penalty
            else "baseline-suite:test"
        ),
        status="unchanged",
        slice_count=final_answer_count,
        comparison_count=final_answer_count,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        summary_json={
            "candidate_final_hit_sample_size": final_answer_count,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": (
                final_hit_count / final_answer_count if final_answer_count else None
            ),
            "candidate_profit_loss": profit_loss,
            "candidate_roi": profit_loss / total_stake,
            "candidate_brier_score": brier_score,
            "candidate_log_loss": brier_score + 0.30,
            "candidate_mean_calibration_error": brier_score,
            "candidate_final_answer_segment_penalty_option_count": (
                penalty_option_count
            ),
        },
    )


def _suite_with_comparisons(
    suite_key: str,
    comparisons: list[HistoricalRecommendationBacktestComparisonResult],
    *,
    final_hit_count: int,
    profit_loss: float,
    penalty_option_count: int = 0,
) -> HistoricalRecommendationBacktestSuiteResult:
    sample_size = len(comparisons)
    total_stake = max(1.0, sample_size * 2.0)
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=suite_key,
        status="unchanged",
        slice_count=sample_size,
        comparison_count=sample_size,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
        summary_json={
            "candidate_final_hit_sample_size": sample_size,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_count / sample_size if sample_size else None,
            "candidate_profit_loss": profit_loss,
            "candidate_roi": profit_loss / total_stake,
            "candidate_brier_score": 0.18,
            "candidate_log_loss": 0.48,
            "candidate_mean_calibration_error": 0.12,
            "candidate_final_answer_segment_penalty_option_count": (
                penalty_option_count
            ),
        },
    )


def _comparison(
    slice_id: str,
    *,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalRecommendationBacktestComparisonResult:
    result = _backtest_result(
        slice_id,
        actual_hit=actual_hit,
        profit_loss=profit_loss,
    )
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{slice_id}",
        slice_id=slice_id,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        status="unchanged",
        baseline=result,
        candidate=result,
    )


def _backtest_result(
    slice_id: str,
    *,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalRecommendationBacktestResult:
    fixture_id = f"{slice_id}_fixture"
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key="3x1:single",
            pass_type="3x1",
            mode="single",
        ),
        status="completed",
        selected_fixture_ids=[fixture_id],
        selected_outcomes={fixture_id: ["home_win"]},
        total_stake=2.0,
        actual_return=2.0 + profit_loss if profit_loss > 0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / 2.0,
        expected_hit_probability=0.70,
        actual_hit=actual_hit,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}:{profit_loss}",
        slice_id=slice_id,
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
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
        total_stake=2.0,
        actual_return=2.0 + profit_loss if profit_loss > 0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / 2.0,
        mean_calibration_error=0.12,
        brier_score=0.18,
        log_loss=0.48,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _grid_report(
    *,
    competition_ids: tuple[str, ...] = ("ESP_LA_LIGA", "GER_BUNDESLIGA"),
    min_competition_season_index: int | None = None,
) -> HistoricalFinalAnswerSegmentPenaltyGridReport:
    candidate = HistoricalFinalAnswerSegmentPenaltyCandidate(
        candidate_key="segment-candidate:test",
        status="accepted",
        pass_types=("3x1",),
        modes=("single",),
        competition_ids=competition_ids,
        min_competition_season_index=min_competition_season_index,
        strength=0.04,
        suite_key="candidate-suite:test",
        suite_status="unchanged",
        penalty_option_count=4,
        final_hit_sample_size=4,
        final_hit_count=4,
        final_hit_rate=1.0,
        roi=0.10,
        profit_loss=0.80,
    )
    return HistoricalFinalAnswerSegmentPenaltyGridReport(
        report_key="segment-grid:test",
        status="generated",
        slice_count=4,
        fixture_count=4,
        prediction_count=4,
        total_grid_candidate_count=1,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        baseline_suite_key="baseline-suite:test",
        baseline_suite_status="unchanged",
        candidates=[candidate],
        accepted_candidates=[candidate],
        best_candidate=candidate,
    )


def _slice(
    slice_id: str,
    *,
    competition_id: str,
    season: str = "2020_2021",
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=f"{slice_id} slice",
            competition_id=competition_id,
            season=season,
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture",
                competition_id=competition_id,
                kickoff_time_utc=datetime(2024, 6, 30, 18, tzinfo=UTC),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=datetime(2024, 6, 29, 10, tzinfo=UTC),
                model_version="poisson-v3.1-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.70,
                        decimal_odds=1.50,
                        market_probability=0.66,
                    )
                ],
            )
        ],
    )
