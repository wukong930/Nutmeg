from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import loads
from pathlib import Path

from nutmeg.accuracy import HistoricalProbabilityCalibrationTransformOptions
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations import (
    historical_probability_calibration_profile_grid as profile_grid_module,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_artifact import (
    HistoricalProbabilityCalibrationProfileArtifactOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_grid import (
    HistoricalProbabilityCalibrationProfileGridOptions,
    _options_from_args,
    _parse_args,
    _stdout_payload,
    build_historical_probability_calibration_profile_grid_report,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionCheck,
    HistoricalProbabilityCalibrationProfileRollingAdmissionFold,
    HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
    HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_probability_calibration_profile_grid_ranks_profile_candidates() -> None:
    slices = _calibration_slices()

    report = build_historical_probability_calibration_profile_grid_report(
        slices,
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(1.0,),
            target_outcome_groups=("home_win", "draw"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            gate_options=_gate_options(),
        ),
    )

    assert report.total_grid_candidate_count == 2
    assert report.candidate_count == 2
    assert report.accepted_count == 2
    assert report.rejected_count == 0
    assert report.transform_cache_miss_count == 1
    assert report.transform_cache_hit_count == 1
    assert report.unique_transform_report_count == 1
    assert report.baseline_backtest_cache_miss_count == 1
    assert report.baseline_backtest_cache_hit_count == 1
    assert report.unique_baseline_backtest_count == 1
    assert report.elapsed_seconds >= 0.0
    assert report.candidate_elapsed_seconds >= 0.0
    assert report.slowest_candidate_index in {0, 1}
    assert report.slowest_candidate_elapsed_seconds is not None
    assert report.best_candidate is not None
    assert [candidate.rank for candidate in report.candidates] == [1, 2]
    assert {candidate.transform_cache_status for candidate in report.candidates} == {
        "hit",
        "miss",
    }
    assert len({candidate.transform_report_key for candidate in report.candidates}) == 1
    assert {candidate.baseline_backtest_cache_miss_count for candidate in report.candidates} == {
        0,
        1,
    }
    assert {candidate.baseline_backtest_cache_hit_count for candidate in report.candidates} == {
        0,
        1,
    }
    assert {tuple(candidate.target_outcomes) for candidate in report.candidates} == {
        ("home_win",),
        ("draw",),
    }


def test_probability_calibration_profile_grid_respects_candidate_window() -> None:
    report = build_historical_probability_calibration_profile_grid_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(1.0,),
            target_outcome_groups=("home_win", "draw", "away_win"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            candidate_start_index=1,
            candidate_limit=1,
            gate_options=_gate_options(),
        ),
    )

    assert report.total_grid_candidate_count == 3
    assert report.candidate_count == 1
    assert report.transform_cache_miss_count == 1
    assert report.transform_cache_hit_count == 0
    assert report.baseline_backtest_cache_miss_count == 1
    assert report.baseline_backtest_cache_hit_count == 0
    assert report.candidates[0].candidate_index == 1
    assert report.summary_json["candidate_indices"] == [1]


def test_probability_calibration_profile_grid_reuses_transform_reports_by_blend_weight() -> None:
    report = build_historical_probability_calibration_profile_grid_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(0.25, 1.0),
            target_outcome_groups=("home_win", "draw"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            gate_options=_gate_options(),
        ),
    )

    assert report.candidate_count == 4
    assert report.transform_cache_miss_count == 2
    assert report.transform_cache_hit_count == 2
    assert report.unique_transform_report_count == 2
    assert report.baseline_backtest_cache_miss_count == 1
    assert report.baseline_backtest_cache_hit_count == 3
    assert report.unique_baseline_backtest_count == 1
    assert report.summary_json["transform_cache_miss_count"] == 2
    assert report.summary_json["transform_cache_hit_count"] == 2
    assert report.summary_json["baseline_backtest_cache_miss_count"] == 1
    assert report.summary_json["baseline_backtest_cache_hit_count"] == 3
    assert report.summary_json["slowest_candidate_index"] in {0, 1, 2, 3}
    for blend_weight in (0.25, 1.0):
        blend_candidates = [
            candidate
            for candidate in report.candidates
            if candidate.blend_weight == blend_weight
        ]
        assert len(blend_candidates) == 2
        assert {candidate.transform_cache_status for candidate in blend_candidates} == {
            "hit",
            "miss",
        }
        assert len({candidate.transform_report_key for candidate in blend_candidates}) == 1


def test_probability_calibration_profile_grid_stdout_summary_is_compact() -> None:
    report = build_historical_probability_calibration_profile_grid_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(1.0,),
            target_outcome_groups=("home_win", "draw"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            gate_options=_gate_options(),
        ),
    )
    report.summary_json["suite_manifest"] = {"resolved_slice_paths": ["large.json"]}

    payload = _stdout_payload(report, summary_only=True)

    assert payload["report_key"] == report.report_key
    assert payload["accepted_count"] == report.accepted_count
    assert payload["transform_cache_hit_count"] == 1
    assert payload["transform_cache_miss_count"] == 1
    assert payload["baseline_backtest_cache_hit_count"] == 1
    assert payload["baseline_backtest_cache_miss_count"] == 1
    assert payload["unique_baseline_backtest_count"] == 1
    assert payload["elapsed_seconds"] >= 0.0
    assert payload["slowest_candidate_index"] in {0, 1}
    assert payload["best_candidate"] is not None
    assert len(payload["top_candidates"]) == 2
    assert payload["top_candidates"][0]["transform_report_key"] is not None
    assert "baseline_backtest_cache_hit_count" in payload["top_candidates"][0]
    assert payload["top_candidates"][0]["elapsed_seconds"] >= 0.0
    assert "summary_json" not in payload["top_candidates"][0]
    assert "suite_manifest" not in payload["summary_json"]


def test_probability_calibration_profile_grid_writes_progress_jsonl(
    tmp_path: Path,
) -> None:
    progress_path = tmp_path / "profile_grid_progress.jsonl"

    report = build_historical_probability_calibration_profile_grid_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(1.0,),
            target_outcome_groups=("home_win", "draw"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            progress_jsonl_path=progress_path,
            gate_options=_gate_options(),
        ),
    )

    events = [
        loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert report.candidate_count == 2
    assert [event["event"] for event in events] == [
        "grid_started",
        "candidate_started",
        "candidate_completed",
        "candidate_started",
        "candidate_completed",
        "grid_completed",
    ]
    assert events[0]["selected_candidate_count"] == 2
    assert events[-1]["report_key"] == report.report_key
    assert events[-1]["candidate_count"] == 2
    assert events[-1]["transform_cache_hit_count"] == 1
    assert events[-1]["transform_cache_miss_count"] == 1
    assert events[-1]["baseline_backtest_cache_hit_count"] == 1
    assert events[-1]["baseline_backtest_cache_miss_count"] == 1
    assert events[-1]["unique_baseline_backtest_count"] == 1
    assert events[-1]["slowest_candidate_index"] in {0, 1}
    assert events[2]["baseline_backtest_cache_miss_count"] == 1
    assert events[2]["elapsed_seconds"] >= 0.0


def test_probability_calibration_profile_grid_fold_objective_rejects_failed_fold(
    monkeypatch,
) -> None:
    def fake_rolling_admission(
        historical_slices,
        *,
        options,
    ) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
        assert historical_slices
        target_outcomes = options.artifact_options.gate_options.target_outcomes
        allowed = target_outcomes == ("home_win",)
        return _rolling_admission_report(
            allowed=allowed,
            report_key=f"fold-objective:{target_outcomes[0]}",
        )

    monkeypatch.setattr(
        profile_grid_module,
        "build_historical_probability_calibration_profile_rolling_admission_report",
        fake_rolling_admission,
    )

    report = build_historical_probability_calibration_profile_grid_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileGridOptions(
            blend_weights=(1.0,),
            target_outcome_groups=("home_win", "draw"),
            probability_bands=("0.00:1.00",),
            decimal_odds_bands=("all",),
            gate_options=_gate_options(),
            fold_objective_options=HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
                artifact_options=HistoricalProbabilityCalibrationProfileArtifactOptions(
                    gate_options=_gate_options(),
                ),
                min_active_competition_fold_count=1,
                min_active_season_cutoff_fold_count=1,
                min_active_rolling_fold_count=1,
                max_failed_fold_count=0,
            ),
        ),
    )

    assert report.accepted_count == 1
    assert report.best_candidate is not None
    assert report.best_candidate.target_outcomes == ["home_win"]
    assert report.summary_json["fold_objective_enabled"] is True
    draw_candidate = next(
        candidate for candidate in report.candidates if candidate.target_outcomes == ["draw"]
    )
    assert draw_candidate.decision == "rejected"
    assert "fold_objective:failed_fold_count" in draw_candidate.decision_reasons
    assert "fold_objective:failed_check:failed_fold_count" in (
        draw_candidate.decision_reasons
    )
    assert draw_candidate.fold_objective_status == "shadow_only"
    assert draw_candidate.fold_objective_failed_fold_count == 1
    assert draw_candidate.fold_objective_active_fold_count == 1
    assert draw_candidate.fold_objective_json["failed_fold_ids"] == [
        "rolling_window:1:2021..2023"
    ]
    payload = _stdout_payload(report, summary_only=True)
    compact_draw = next(
        candidate
        for candidate in payload["top_candidates"]
        if candidate["target_outcomes"] == ["draw"]
    )
    assert compact_draw["fold_objective_failed_fold_count"] == 1


def test_probability_calibration_profile_grid_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--grid-id",
            "calibration-profile-grid-test",
            "--blend-weights",
            "0.25,0.5",
            "--target-outcome-groups",
            "home_win,draw+away_win",
            "--probability-bands",
            "0.20:0.60,0.60:1.00",
            "--decimal-odds-bands",
            "all,1.50:3.00",
            "--candidate-start-index",
            "2",
            "--candidate-limit",
            "4",
            "--progress-jsonl-path",
            "/tmp/nutmeg_profile_grid_progress.jsonl",
            "--competition-ids",
            "ESP_LA_LIGA,ITA_SERIE_A",
            "--include-rejected-transform-competitions",
            "--holdout-season-count",
            "2",
            "--min-training-season-count",
            "3",
            "--min-validation-sample-size",
            "50",
            "--segment-mode",
            "market_odds_band",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "12",
            "--min-calibrated-probability",
            "0.02",
            "--max-calibrated-probability",
            "0.90",
            "--group-all-competitions",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "30",
            "--min-probability",
            "0.2",
            "--candidate-fixture-limit",
            "24",
            "--max-candidates-per-fixture",
            "2",
            "--final-answer-scenario-variant-count",
            "3",
            "--derive-market-context-signals",
            "--min-final-hit-sample-size",
            "20",
            "--min-final-hit-rate-delta",
            "0.01",
            "--min-final-answer-changed-count",
            "3",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "1.5",
            "--max-brier-score-delta",
            "0.03",
            "--max-log-loss-delta",
            "0.04",
            "--max-mean-calibration-error-delta",
            "0.05",
            "--enable-fold-objective",
            "--fold-min-final-hit-sample-size",
            "5",
            "--fold-min-final-hit-rate-delta",
            "-0.25",
            "--fold-min-final-answer-changed-count",
            "1",
            "--fold-min-roi-delta",
            "-0.5",
            "--fold-min-profit-loss-delta",
            "-10",
            "--fold-max-brier-score-delta",
            "0.2",
            "--fold-max-log-loss-delta",
            "0.3",
            "--fold-max-mean-calibration-error-delta",
            "0.4",
            "--fold-min-overall-adjusted-fixture-count",
            "2",
            "--fold-min-overall-bucket-count",
            "3",
            "--fold-min-adjusted-fixture-count",
            "4",
            "--fold-min-bucket-count",
            "5",
            "--fold-allow-without-profile",
            "--fold-min-active-competition-fold-count",
            "6",
            "--fold-min-active-season-cutoff-fold-count",
            "7",
            "--fold-min-active-rolling-fold-count",
            "8",
            "--fold-rolling-window-season-count",
            "9",
            "--fold-rolling-window-step",
            "2",
            "--fold-max-failed-fold-count",
            "1",
            "--fold-max-report-folds",
            "50",
            "--stdout-summary-only",
        ]
    )

    options = _options_from_args(args)

    assert options.grid_id == "calibration-profile-grid-test"
    assert options.blend_weights == (0.25, 0.5)
    assert options.target_outcome_groups == ("home_win", "draw+away_win")
    assert options.probability_bands == ("0.20:0.60", "0.60:1.00")
    assert options.decimal_odds_bands == ("all", "1.50:3.00")
    assert options.candidate_start_index == 2
    assert options.candidate_limit == 4
    assert str(options.progress_jsonl_path) == "/tmp/nutmeg_profile_grid_progress.jsonl"
    assert options.gate_options.competition_ids == ("ESP_LA_LIGA", "ITA_SERIE_A")
    assert options.gate_options.require_transform_acceptance is False
    assert options.gate_options.transform_options.holdout_season_count == 2
    assert options.gate_options.transform_options.min_training_season_count == 3
    assert options.gate_options.transform_options.min_validation_sample_size == 50
    assert options.gate_options.transform_options.segment_mode == "market_odds_band"
    assert options.gate_options.transform_options.bucket_size == 0.05
    assert options.gate_options.transform_options.min_bucket_sample_size == 12
    assert options.gate_options.transform_options.min_calibrated_probability == 0.02
    assert options.gate_options.transform_options.max_calibrated_probability == 0.90
    assert options.gate_options.transform_options.group_by_competition is False
    assert options.gate_options.backtest_options.pass_types == ("1x1", "2x1")
    assert options.gate_options.backtest_options.modes == ("single",)
    assert options.gate_options.backtest_options.optimizer_profile == "heuristic"
    assert options.gate_options.backtest_options.unit_stake == 3
    assert options.gate_options.backtest_options.max_budget == 30
    assert options.gate_options.backtest_options.min_probability == 0.2
    assert options.gate_options.backtest_options.candidate_fixture_limit == 24
    assert options.gate_options.backtest_options.max_candidates_per_fixture == 2
    assert options.gate_options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.gate_options.backtest_options.derive_market_context_signals is True
    assert options.gate_options.quality_gate_options.min_final_hit_sample_size == 20
    assert options.gate_options.quality_gate_options.min_final_hit_rate_delta == 0.01
    assert options.gate_options.quality_gate_options.min_final_answer_changed_count == 3
    assert options.gate_options.quality_gate_options.min_roi_delta == 0.02
    assert options.gate_options.quality_gate_options.min_profit_loss_delta == 1.5
    assert options.gate_options.quality_gate_options.max_brier_score_delta == 0.03
    assert options.gate_options.quality_gate_options.max_log_loss_delta == 0.04
    assert (
        options.gate_options.quality_gate_options.max_mean_calibration_error_delta
        == 0.05
    )
    assert options.fold_objective_options is not None
    assert (
        options.fold_objective_options.rolling_admission_id
        == "calibration-profile-grid-test:fold-objective"
    )
    assert options.fold_objective_options.min_overall_adjusted_fixture_count == 2
    assert options.fold_objective_options.min_overall_bucket_count == 3
    assert options.fold_objective_options.min_fold_adjusted_fixture_count == 4
    assert options.fold_objective_options.min_fold_bucket_count == 5
    assert options.fold_objective_options.require_fold_emitted_profile is False
    assert options.fold_objective_options.min_active_competition_fold_count == 6
    assert options.fold_objective_options.min_active_season_cutoff_fold_count == 7
    assert options.fold_objective_options.min_active_rolling_fold_count == 8
    assert options.fold_objective_options.rolling_window_season_count == 9
    assert options.fold_objective_options.rolling_window_step == 2
    assert options.fold_objective_options.max_failed_fold_count == 1
    assert options.fold_objective_options.max_report_folds == 50
    assert options.fold_objective_options.fold_quality_gate_options is not None
    assert (
        options.fold_objective_options.fold_quality_gate_options.min_final_hit_sample_size
        == 5
    )
    assert (
        options.fold_objective_options.fold_quality_gate_options.min_final_hit_rate_delta
        == -0.25
    )
    assert (
        options.fold_objective_options.fold_quality_gate_options.min_final_answer_changed_count
        == 1
    )
    assert options.fold_objective_options.fold_quality_gate_options.min_roi_delta == -0.5
    assert (
        options.fold_objective_options.fold_quality_gate_options.min_profit_loss_delta
        == -10
    )
    assert (
        options.fold_objective_options.fold_quality_gate_options.max_brier_score_delta
        == 0.2
    )
    assert (
        options.fold_objective_options.fold_quality_gate_options.max_log_loss_delta
        == 0.3
    )
    assert (
        options.fold_objective_options.fold_quality_gate_options.max_mean_calibration_error_delta
        == 0.4
    )
    assert args.stdout_summary_only is True


def _gate_options() -> HistoricalProbabilityCalibrationProfileGateOptions:
    return HistoricalProbabilityCalibrationProfileGateOptions(
        transform_options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            bucket_size=0.10,
            prediction_sample_limit=0,
        ),
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            optimizer_profile="solver",
            min_probability=0.05,
            max_candidates_per_fixture=3,
        ),
        quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=1,
            fail_on_suite_statuses=(),
            min_final_hit_rate_delta=None,
            max_brier_score_delta=None,
            max_log_loss_delta=None,
            max_mean_calibration_error_delta=None,
        ),
    )


def _rolling_admission_report(
    *,
    allowed: bool,
    report_key: str,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    fold = HistoricalProbabilityCalibrationProfileRollingAdmissionFold(
        fold_id="rolling_window:1:2021..2023",
        fold_type="rolling_window",
        status="passed" if allowed else "failed",
        source_slice_ids=["calibration_profile_grid_2021"],
        source_competition_ids=["TEST"],
        source_season_ids=["2021", "2022", "2023"],
        emitted_profile=allowed,
        passed_final_answer_gate=allowed,
        adjusted_fixture_count=4,
        bucket_count=1 if allowed else 0,
        selected_competition_ids=["TEST"],
        suite_status="improved" if allowed else "mixed",
        quality_gate_passed=allowed,
        final_hit_rate_delta=0.1 if allowed else 0.0,
        roi_delta=0.2 if allowed else 0.0,
        profit_loss_delta=2.0 if allowed else 0.0,
        brier_score_delta=-0.01 if allowed else 0.01,
        log_loss_delta=-0.02 if allowed else 0.02,
        mean_calibration_error_delta=-0.03 if allowed else 0.03,
        failure_reasons=[] if allowed else ["runtime_profile_not_emitted"],
        warning_codes=[] if allowed else ["unit-test-fold-failed"],
    )
    check = HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
        name="failed_fold_count",
        status="passed" if allowed else "failed",
        actual=0 if allowed else 1,
        threshold=0,
        detail="unit-test fold objective",
    )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport(
        report_key=report_key,
        status="accepted" if allowed else "shadow_only",
        candidate_profile_allowed=allowed,
        shadow_allowed=True,
        overall_fold=fold,
        fold_count=1,
        active_fold_count=1,
        failed_fold_count=0 if allowed else 1,
        active_competition_fold_count=1,
        active_season_cutoff_fold_count=1,
        active_rolling_fold_count=1,
        checks=[check],
        folds=[fold],
        warnings=(
            []
            if allowed
            else [
                "probability_calibration_profile_rolling_admission:"
                "failed_check:failed_fold_count"
            ]
        ),
        summary_json={
            "report_key": report_key,
            "status": "accepted" if allowed else "shadow_only",
        },
    )


def _calibration_slices() -> list[HistoricalRecommendationSlice]:
    return [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]


def _season_slice(
    season: str,
    day_offset: int,
    results: list[tuple[int, int]],
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"calibration_profile_grid_{season}",
            name=f"Calibration profile grid {season}",
            competition_id="TEST",
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            _fixture(
                f"{season}_{index}",
                base_time + timedelta(days=index + 1),
                home_goals,
                away_goals,
            )
            for index, (home_goals, away_goals) in enumerate(results)
        ],
    )


def _fixture(
    fixture_id: str,
    kickoff_time_utc: datetime,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff_time_utc,
        home_team_name=f"Home {fixture_id}",
        away_team_name=f"Away {fixture_id}",
        actual_home_goals=home_goals,
        actual_away_goals=away_goals,
        prediction_time_utc=kickoff_time_utc - timedelta(days=1),
        model_version="overconfident-home-v1",
        feature_version="unit-test",
        calibration_version="uncalibrated-v1",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="home_win",
                probability=0.80,
                decimal_odds=1.25,
                market_probability=0.80,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="draw",
                probability=0.10,
                decimal_odds=10.0,
                market_probability=0.10,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="away_win",
                probability=0.10,
                decimal_odds=10.0,
                market_probability=0.10,
            ),
        ],
    )
