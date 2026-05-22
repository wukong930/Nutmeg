from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads

import pytest

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations import (
    competition_data_quality_beta_lane_rolling_admission as admission,
)
from nutmeg.recommendations.competition_data_quality_beta_lane_grid import (
    HistoricalCompetitionDataQualityBetaLaneCandidate,
    HistoricalCompetitionDataQualityBetaLaneGridReport,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
)


def test_beta_lane_rolling_admission_accepts_when_active_folds_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _passing_fake_run,
    )

    report = admission.build_historical_competition_data_quality_beta_lane_rolling_admission_report(
        [
            _slice("ita_b_2021", competition_id="ITA_SERIE_B", season="2021_2022"),
            _slice("epl_2021", competition_id="EPL", season="2021_2022"),
            _slice("ita_b_2022", competition_id="ITA_SERIE_B", season="2022_2023"),
            _slice("epl_2022", competition_id="EPL", season="2022_2023"),
        ],
        grid_report=_grid_report(),
        options=admission.HistoricalCompetitionDataQualityBetaLaneRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_profile_allowed is True
    assert report.overall_fold.beta_lane_prediction_count == 2
    assert report.overall_fold.probability_repair_candidate_count == 2
    assert report.overall_fold.probability_repair_final_answer_selected_candidate_count == 2
    assert report.overall_fold.final_answer_hit_delta_count == 1
    assert report.active_competition_fold_count == 1
    assert report.active_season_fold_count == 2
    assert report.active_rolling_fold_count == 2
    assert report.failed_fold_count == 0


def test_beta_lane_rolling_admission_shadow_only_when_active_fold_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _one_season_regresses_fake_run,
    )

    report = admission.build_historical_competition_data_quality_beta_lane_rolling_admission_report(
        [
            _slice("ita_b_2021", competition_id="ITA_SERIE_B", season="2021_2022"),
            _slice("epl_2021", competition_id="EPL", season="2021_2022"),
            _slice("ita_b_2022", competition_id="ITA_SERIE_B", season="2022_2023"),
            _slice("epl_2022", competition_id="EPL", season="2022_2023"),
        ],
        grid_report=_grid_report(),
        options=admission.HistoricalCompetitionDataQualityBetaLaneRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_active_competition_fold_count=1,
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
    assert "season:2022_2023" in failed_fold_ids
    assert any(check.name == "failed_fold_count" for check in report.checks)


def test_beta_lane_rolling_admission_rejects_when_overall_gate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _overall_regresses_fake_run,
    )

    report = admission.build_historical_competition_data_quality_beta_lane_rolling_admission_report(
        [
            _slice("ita_b_2021", competition_id="ITA_SERIE_B", season="2021_2022"),
            _slice("ita_b_2022", competition_id="ITA_SERIE_B", season="2022_2023"),
        ],
        grid_report=_grid_report(),
        options=admission.HistoricalCompetitionDataQualityBetaLaneRollingAdmissionOptions(
            min_overall_final_answer_count=2,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=0,
            min_active_rolling_fold_count=0,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "rejected"
    assert report.candidate_profile_allowed is False
    assert any(check.name == "overall_gate_passed" for check in report.checks)


def test_beta_lane_rolling_admission_limits_candidate_to_season_regime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _passing_fake_run,
    )

    report = admission.build_historical_competition_data_quality_beta_lane_rolling_admission_report(
        [
            _slice("ita_b_2021", competition_id="ITA_SERIE_B", season="2021_2022"),
            _slice("ita_b_2022", competition_id="ITA_SERIE_B", season="2022_2023"),
            _slice("epl_2022", competition_id="EPL", season="2022_2023"),
        ],
        grid_report=_grid_report(
            season_ids=("2022_2023",),
            min_competition_season_index=2,
            max_competition_season_index=2,
            beta_lane_prediction_count=1,
            beta_lane_fixture_count=1,
        ),
        options=admission.HistoricalCompetitionDataQualityBetaLaneRollingAdmissionOptions(
            min_overall_final_answer_count=3,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=1,
            min_active_rolling_fold_count=0,
            rolling_window_slice_count=2,
            rolling_window_step=1,
        ),
    )

    assert report.status == "accepted"
    assert report.overall_fold.beta_lane_prediction_count == 1
    assert report.overall_fold.probability_repair_candidate_count == 1
    assert (
        report.overall_fold.probability_repair_final_answer_selected_candidate_count
        == 1
    )
    assert report.active_season_fold_count == 1


def test_beta_lane_rolling_admission_cli_options_loader_and_main(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        admission,
        "run_historical_recommendation_backtest_suite",
        _passing_fake_run,
    )
    grid_path = tmp_path / "beta_lane_grid.json"
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "rolling_admission.json"
    grid_path.write_text(f"{_grid_report().model_dump_json(indent=2)}\n", encoding="utf-8")
    slice_path.write_text(
        f"{_slice('ita_b_2021', competition_id='ITA_SERIE_B').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    admission.main(
        [
            str(slice_path),
            "--grid-report",
            str(grid_path),
            "--output-path",
            str(output_path),
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "heuristic",
            "--baseline-min-data-quality-score",
            "82",
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
    assert payload["source_grid_report_key"] == "beta-lane-grid:test"
    assert payload["source_candidate_key"] == "beta-lane-candidate:test"
    assert payload["summary_json"]["options"]["optimizer_profile"] == "heuristic"
    assert payload["summary_json"]["options"]["baseline_min_data_quality_score"] == 82


def _passing_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "solver",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    return _fake_suite(
        historical_slices,
        options=options,
        target_profit_delta=1.0,
        target_hit_delta=1,
    )


def _one_season_regresses_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "solver",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    seasons = {historical_slice.metadata.season for historical_slice in historical_slices}
    target_profit_delta = -1.0 if seasons == {"2022_2023"} else 1.0
    target_hit_delta = 0 if seasons == {"2022_2023"} else 1
    return _fake_suite(
        historical_slices,
        options=options,
        target_profit_delta=target_profit_delta,
        target_hit_delta=target_hit_delta,
    )


def _overall_regresses_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "solver",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    return _fake_suite(
        historical_slices,
        options=options,
        target_profit_delta=-1.0,
        target_hit_delta=0,
    )


def _fake_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None,
    target_profit_delta: float,
    target_hit_delta: int,
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    beta_lane_enabled = resolved_options.data_quality_beta_lane_enabled
    final_answer_count = len(historical_slices)
    target_slice_count = sum(
        1
        for historical_slice in historical_slices
        if _slice_beta_lane_applies(historical_slice, options=resolved_options)
    )
    baseline_hit_count = max(0, final_answer_count - 1)
    if beta_lane_enabled and target_slice_count > 0:
        final_hit_count = min(final_answer_count, baseline_hit_count + target_hit_delta)
        profit_loss = -float(final_answer_count) + target_profit_delta
        brier_score = 0.18 if target_profit_delta >= 0 else 0.24
    else:
        final_hit_count = baseline_hit_count
        profit_loss = -float(final_answer_count)
        brier_score = 0.20
    total_stake = max(1.0, final_answer_count * 2.0)
    comparisons = [
        _comparison(
            historical_slice,
            actual_hit=index < final_hit_count,
            options=resolved_options,
        )
        for index, historical_slice in enumerate(historical_slices)
    ]
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key="candidate-suite:test" if beta_lane_enabled else "baseline-suite:test",
        status="unchanged",
        slice_count=final_answer_count,
        comparison_count=final_answer_count,
        baseline_optimizer_profile="solver",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
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
        },
    )


def _slice_beta_lane_applies(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> bool:
    if not options.data_quality_beta_lane_enabled:
        return False
    if (
        options.data_quality_beta_lane_competition_ids
        and historical_slice.metadata.competition_id
        not in set(options.data_quality_beta_lane_competition_ids)
    ):
        return False
    if (
        options.data_quality_beta_lane_season_ids
        and historical_slice.metadata.season
        not in set(options.data_quality_beta_lane_season_ids)
    ):
        return False
    minimum = options.data_quality_beta_lane_min_competition_season_index
    maximum = options.data_quality_beta_lane_max_competition_season_index
    if minimum is None and maximum is None:
        return True
    season_index = options.competition_season_index_by_slice_id.get(
        historical_slice.metadata.slice_id
    )
    if season_index is None:
        return False
    if minimum is not None and season_index < minimum:
        return False
    return not (maximum is not None and season_index > maximum)


def _comparison(
    historical_slice: HistoricalRecommendationSlice,
    *,
    actual_hit: bool,
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestComparisonResult:
    result = _backtest_result(
        historical_slice,
        actual_hit=actual_hit,
        options=options,
    )
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{historical_slice.metadata.slice_id}",
        slice_id=historical_slice.metadata.slice_id,
        baseline_optimizer_profile="solver",
        candidate_optimizer_profile="solver",
        status="unchanged",
        baseline=result,
        candidate=result,
    )


def _backtest_result(
    historical_slice: HistoricalRecommendationSlice,
    *,
    actual_hit: bool,
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestResult:
    beta_lane_enabled = options.data_quality_beta_lane_enabled
    repair_count = 1 if _slice_beta_lane_applies(historical_slice, options=options) else 0
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{historical_slice.metadata.slice_id}",
        slice_id=historical_slice.metadata.slice_id,
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
        fixture_count=1,
        candidate_count=1,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=HistoricalRecommendationScenarioResult(
            scenario=HistoricalRecommendationScenario(
                scenario_key=(
                    "beta-lane-scenario:test"
                    if beta_lane_enabled
                    else "baseline-scenario:test"
                ),
                pass_type="1x1",
                mode="single",
            ),
            status="completed",
            selected_fixture_ids=[f"{historical_slice.metadata.slice_id}_fixture"],
            selected_outcomes={
                f"{historical_slice.metadata.slice_id}_fixture": ["home_win"]
            },
            actual_hit=actual_hit,
        ),
        final_hit_sample_size=1,
        final_hit_count=1 if actual_hit else 0,
        final_hit_rate=1.0 if actual_hit else 0.0,
        total_stake=2.0,
        actual_return=3.0 if actual_hit else 0.0,
        profit_loss=1.0 if actual_hit else -2.0,
        roi=0.5 if actual_hit else -1.0,
        upset_opportunity_count=0,
        upset_capture_count=0,
        summary_json={
            "data_quality_beta_lane_probability_repair_candidate_count": repair_count,
            "data_quality_beta_lane_probability_repair_candidate_pool_count": repair_count,
            (
                "data_quality_beta_lane_probability_repair_"
                "final_answer_selected_candidate_count"
            ): repair_count,
        },
    )


def _grid_report(
    *,
    season_ids: tuple[str, ...] = (),
    min_competition_season_index: int | None = None,
    max_competition_season_index: int | None = None,
    beta_lane_prediction_count: int = 2,
    beta_lane_fixture_count: int = 2,
) -> HistoricalCompetitionDataQualityBetaLaneGridReport:
    return _grid_report_with_candidate(
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        beta_lane_prediction_count=beta_lane_prediction_count,
        beta_lane_fixture_count=beta_lane_fixture_count,
    )


def _grid_report_with_candidate(
    *,
    season_ids: tuple[str, ...] = (),
    min_competition_season_index: int | None = None,
    max_competition_season_index: int | None = None,
    beta_lane_prediction_count: int = 2,
    beta_lane_fixture_count: int = 2,
) -> HistoricalCompetitionDataQualityBetaLaneGridReport:
    candidate = HistoricalCompetitionDataQualityBetaLaneCandidate(
        candidate_key="beta-lane-candidate:test",
        status="accepted",
        competition_id="ITA_SERIE_B",
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        beta_min_data_quality_score=70,
        min_probability=0.50,
        max_decimal_odds=2.80,
        min_model_edge=-0.05,
        min_model_confidence_score=0.66,
        min_calibration_score=0.70,
        min_odds_stability_score=0.95,
        max_volatility_penalty=0.05,
        probability_repair_strength=1.0,
        probability_repair_max_delta=0.22,
        probability_repair_min_market_probability_delta=0.01,
        probability_repair_extra_uplift=0.10,
        probability_repair_data_quality_gap_weight=0.04,
        probability_repair_max_probability=0.98,
        beta_lane_prediction_count=beta_lane_prediction_count,
        beta_lane_fixture_count=beta_lane_fixture_count,
        probability_repair_candidate_count=2,
        probability_repair_candidate_pool_count=2,
        probability_repair_final_answer_selected_candidate_count=2,
        final_answer_changed_count=2,
        baseline_final_hit_sample_size=4,
        candidate_final_hit_sample_size=4,
        final_hit_sample_size_delta=0,
        baseline_final_hit_count=3,
        candidate_final_hit_count=4,
        baseline_profit_loss=-4.0,
        candidate_profit_loss=-3.0,
    )
    return HistoricalCompetitionDataQualityBetaLaneGridReport(
        report_key="beta-lane-grid:test",
        status="generated",
        slice_count=4,
        fixture_count=4,
        prediction_count=4,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        candidates=[candidate],
        accepted_candidates=[candidate],
        best_candidate=candidate,
    )


def _slice(
    slice_id: str,
    *,
    competition_id: str,
    season: str = "2021_2022",
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
                        model_edge=0.04,
                        model_confidence_score=0.70,
                        calibration_score=0.74,
                        odds_stability_score=0.97,
                        volatility_penalty=0.02,
                        data_quality_score=75,
                    )
                ],
            )
        ],
    )
