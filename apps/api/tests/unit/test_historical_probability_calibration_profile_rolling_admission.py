from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import loads

import pytest

from nutmeg.accuracy import HistoricalProbabilityCalibrationTransformOptions
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_artifact import (
    HistoricalProbabilityCalibrationProfileArtifactOptions,
    HistoricalProbabilityCalibrationProfileArtifactReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateOptions,
    HistoricalProbabilityCalibrationProfileGateReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_probability_calibration_profile_rolling_admission_report,
    main,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_probability_calibration_profile_rolling_admission_accepts_stable_profile() -> None:
    report = build_historical_probability_calibration_profile_rolling_admission_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
            artifact_options=HistoricalProbabilityCalibrationProfileArtifactOptions(
                profile_mode="active",
                gate_options=_gate_options(),
            ),
            min_active_competition_fold_count=1,
            min_active_season_cutoff_fold_count=1,
            min_active_rolling_fold_count=1,
            rolling_window_season_count=3,
            rolling_window_step=1,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_profile_allowed is True
    assert report.shadow_allowed is True
    assert report.profile is not None
    assert report.profile.mode == "active"
    assert report.overall_fold.passed_final_answer_gate is True
    assert report.failed_fold_count == 0
    assert report.active_competition_fold_count == 1
    assert report.active_season_cutoff_fold_count == 1
    assert report.active_rolling_fold_count == 1


def test_probability_calibration_profile_rolling_admission_blocks_failed_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_probability_calibration_profile_rolling_admission."
        "build_historical_probability_calibration_profile_artifact_report",
        _fake_artifact_report,
    )

    report = build_historical_probability_calibration_profile_rolling_admission_report(
        [
            _season_slice("2021", 0, [(1, 0)], competition_id="PASS"),
            _season_slice("2022", 10, [(1, 0)], competition_id="PASS"),
            _season_slice("2023", 20, [(1, 0)], competition_id="PASS"),
            _season_slice("2021", 1, [(0, 1)], competition_id="FAIL"),
            _season_slice("2022", 11, [(0, 1)], competition_id="FAIL"),
            _season_slice("2023", 21, [(0, 1)], competition_id="FAIL"),
        ],
        options=HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
            min_active_competition_fold_count=2,
            min_active_season_cutoff_fold_count=1,
            min_active_rolling_fold_count=1,
            rolling_window_season_count=3,
            max_failed_fold_count=0,
        ),
    )

    assert report.status == "shadow_only"
    assert report.candidate_profile_allowed is False
    assert report.profile is None
    assert report.failed_fold_count == 1
    assert "competition:FAIL" in {
        fold.fold_id for fold in report.folds if fold.status == "failed"
    }
    assert any(check.name == "failed_fold_count" for check in report.checks)


def test_probability_calibration_profile_rolling_admission_uses_fold_quality_gate_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_sample_sizes: list[tuple[tuple[str, ...], int]] = []

    def fake_artifact_report(
        historical_slices: list[HistoricalRecommendationSlice],
        *,
        options: HistoricalProbabilityCalibrationProfileArtifactOptions | None = None,
    ) -> HistoricalProbabilityCalibrationProfileArtifactReport:
        assert options is not None
        competition_ids = tuple(
            sorted(
                {
                    historical_slice.metadata.competition_id
                    for historical_slice in historical_slices
                }
            )
        )
        sample_size = (
            options.gate_options.quality_gate_options.min_final_hit_sample_size
        )
        seen_sample_sizes.append((competition_ids, sample_size))
        passed = len(competition_ids) > 1 or sample_size == 1
        profile = (
            CandidateProbabilityCalibrationProfile(
                profile_key=f"profile:{','.join(competition_ids)}",
                source_report_key=f"gate:{','.join(competition_ids)}",
                mode="active",
                buckets=[
                    CandidateProbabilityCalibrationBucket(
                        competition_id=competition_id,
                        outcome="home_win",
                        bucket_start=0.0,
                        bucket_end=1.0,
                        calibrated_probability=0.60,
                        sample_size=10,
                    )
                    for competition_id in competition_ids
                ],
                target_competition_ids=competition_ids,
            )
            if passed
            else None
        )
        gate_report = HistoricalProbabilityCalibrationProfileGateReport(
            report_key=f"gate:{','.join(competition_ids)}:{sample_size}",
            status="generated",
            gate_id="fake",
            transform_report_key="transform:fake",
            selected_competition_ids=list(competition_ids) if passed else [],
            rejected_competition_ids=[] if passed else list(competition_ids),
            baseline_slice_count=len(historical_slices),
            adjusted_slice_count=len(historical_slices) if passed else 0,
            adjusted_fixture_count=len(historical_slices) if passed else 0,
            skipped_fixture_count=0,
            passed_final_answer_gate=passed,
            warnings=[] if passed else ["fake:failed"],
            summary_json={
                "aggregate_deltas_json": {
                    "final_hit_rate_delta": 0.0 if passed else -0.5,
                    "roi_delta": 0.0 if passed else -0.5,
                    "profit_loss_delta": 0.0 if passed else -2.0,
                }
            },
        )
        return HistoricalProbabilityCalibrationProfileArtifactReport(
            report_key=f"artifact:{','.join(competition_ids)}:{sample_size}",
            artifact_id="fake",
            gate_report_key=gate_report.report_key,
            emitted_profile=profile is not None,
            profile=profile,
            gate_report=gate_report,
            warning_codes=[] if passed else ["fake:failed"],
            summary_json={"fake_passed": passed},
        )

    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_probability_calibration_profile_rolling_admission."
        "build_historical_probability_calibration_profile_artifact_report",
        fake_artifact_report,
    )

    report = build_historical_probability_calibration_profile_rolling_admission_report(
        [
            _season_slice("2021", 0, [(1, 0)], competition_id="A"),
            _season_slice("2022", 10, [(1, 0)], competition_id="A"),
            _season_slice("2023", 20, [(1, 0)], competition_id="A"),
            _season_slice("2021", 1, [(0, 1)], competition_id="B"),
            _season_slice("2022", 11, [(0, 1)], competition_id="B"),
            _season_slice("2023", 21, [(0, 1)], competition_id="B"),
        ],
        options=HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
            artifact_options=HistoricalProbabilityCalibrationProfileArtifactOptions(
                gate_options=HistoricalProbabilityCalibrationProfileGateOptions(
                    quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                        min_final_hit_sample_size=20,
                    ),
                ),
            ),
            fold_quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                min_final_hit_sample_size=1,
            ),
            min_active_competition_fold_count=2,
            min_active_season_cutoff_fold_count=1,
            min_active_rolling_fold_count=1,
            rolling_window_season_count=3,
        ),
    )

    assert report.status == "accepted"
    assert report.failed_fold_count == 0
    assert (("A", "B"), 20) in seen_sample_sizes
    assert (("A",), 1) in seen_sample_sizes
    assert (("B",), 1) in seen_sample_sizes


def test_probability_calibration_profile_rolling_admission_cli_writes_profile(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slice_paths = []
    for index, historical_slice in enumerate(_calibration_slices()):
        slice_path = tmp_path / f"slice_{index}.json"
        slice_path.write_text(
            f"{historical_slice.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        slice_paths.append(slice_path)
    output_path = tmp_path / "rolling_admission.json"
    profile_path = tmp_path / "runtime_profile.json"

    main(
        [
            *(str(path) for path in slice_paths),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--profile-mode",
            "active",
            "--min-training-season-count",
            "2",
            "--min-validation-sample-size",
            "1",
            "--min-bucket-sample-size",
            "1",
            "--bucket-size",
            "0.10",
            "--pass-types",
            "1x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "solver",
            "--min-probability",
            "0.05",
            "--max-candidates-per-fixture",
            "3",
            "--min-final-hit-sample-size",
            "1",
            "--min-final-hit-rate-delta",
            "-1.0",
            "--min-roi-delta",
            "-10.0",
            "--min-profit-loss-delta",
            "-100.0",
            "--max-brier-score-delta",
            "1.0",
            "--max-log-loss-delta",
            "1.0",
            "--max-mean-calibration-error-delta",
            "1.0",
            "--fold-min-final-hit-sample-size",
            "1",
            "--fold-min-final-answer-changed-count",
            "0",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-cutoff-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--rolling-window-season-count",
            "3",
        ]
    )

    printed = loads(capsys.readouterr().out)
    payload = loads(output_path.read_text(encoding="utf-8"))
    profile_payload = loads(profile_path.read_text(encoding="utf-8"))
    assert printed["report_key"] == payload["report_key"]
    assert payload["status"] == "accepted"
    assert payload["candidate_profile_allowed"] is True
    assert profile_payload["mode"] == "active"
    assert profile_payload["target_competition_ids"] == ["TEST"]


def test_probability_calibration_profile_rolling_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--rolling-admission-id",
            "rolling-test",
            "--artifact-id",
            "artifact-test",
            "--profile-mode",
            "shadow",
            "--gate-id",
            "gate-test",
            "--segment-mode",
            "market_odds_band",
            "--final-answer-scenario-variant-count",
            "4",
            "--min-overall-adjusted-fixture-count",
            "4",
            "--min-overall-bucket-count",
            "3",
            "--min-fold-adjusted-fixture-count",
            "2",
            "--min-fold-bucket-count",
            "1",
            "--allow-fold-without-profile",
            "--min-active-competition-fold-count",
            "2",
            "--min-active-season-cutoff-fold-count",
            "3",
            "--min-active-rolling-fold-count",
            "4",
            "--rolling-window-season-count",
            "5",
            "--rolling-window-step",
            "2",
            "--max-failed-fold-count",
            "1",
            "--max-report-folds",
            "40",
            "--fold-min-final-hit-sample-size",
            "5",
            "--fold-min-final-hit-rate-delta",
            "-0.25",
            "--fold-min-final-answer-changed-count",
            "0",
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
        ]
    )

    options = _options_from_args(args)

    assert options.rolling_admission_id == "rolling-test"
    assert options.artifact_options.artifact_id == "artifact-test"
    assert options.artifact_options.profile_mode == "shadow"
    assert options.artifact_options.gate_options.gate_id == "gate-test"
    assert (
        options.artifact_options.gate_options.transform_options.segment_mode
        == "market_odds_band"
    )
    assert (
        options.artifact_options.gate_options.backtest_options.final_answer_scenario_variant_count
        == 4
    )
    assert options.admitted_profile_mode == "shadow"
    assert options.min_overall_adjusted_fixture_count == 4
    assert options.min_overall_bucket_count == 3
    assert options.min_fold_adjusted_fixture_count == 2
    assert options.min_fold_bucket_count == 1
    assert options.require_fold_emitted_profile is False
    assert options.min_active_competition_fold_count == 2
    assert options.min_active_season_cutoff_fold_count == 3
    assert options.min_active_rolling_fold_count == 4
    assert options.rolling_window_season_count == 5
    assert options.rolling_window_step == 2
    assert options.max_failed_fold_count == 1
    assert options.max_report_folds == 40
    assert options.fold_quality_gate_options is not None
    assert options.fold_quality_gate_options.min_final_hit_sample_size == 5
    assert options.fold_quality_gate_options.min_final_hit_rate_delta == -0.25
    assert options.fold_quality_gate_options.min_final_answer_changed_count == 0
    assert options.fold_quality_gate_options.min_roi_delta == -0.5
    assert options.fold_quality_gate_options.min_profit_loss_delta == -10
    assert options.fold_quality_gate_options.max_brier_score_delta == 0.2
    assert options.fold_quality_gate_options.max_log_loss_delta == 0.3
    assert options.fold_quality_gate_options.max_mean_calibration_error_delta == 0.4


def _fake_artifact_report(
    historical_slices: list[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileArtifactOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileArtifactReport:
    del options
    competition_ids = sorted(
        {historical_slice.metadata.competition_id for historical_slice in historical_slices}
    )
    passed = competition_ids != ["FAIL"]
    profile = (
        CandidateProbabilityCalibrationProfile(
            profile_key=f"profile:{','.join(competition_ids)}",
            source_report_key=f"gate:{','.join(competition_ids)}",
            mode="active",
            buckets=[
                CandidateProbabilityCalibrationBucket(
                    competition_id=competition_id,
                    outcome="home_win",
                    bucket_start=0.0,
                    bucket_end=1.0,
                    calibrated_probability=0.60,
                    sample_size=10,
                )
                for competition_id in competition_ids
            ],
            target_competition_ids=tuple(competition_ids),
        )
        if passed
        else None
    )
    gate_report = HistoricalProbabilityCalibrationProfileGateReport(
        report_key=f"gate:{','.join(competition_ids)}",
        status="generated",
        gate_id="fake",
        transform_report_key="transform:fake",
        selected_competition_ids=competition_ids if passed else [],
        rejected_competition_ids=[] if passed else competition_ids,
        baseline_slice_count=len(historical_slices),
        adjusted_slice_count=len(historical_slices) if passed else 0,
        adjusted_fixture_count=len(historical_slices) if passed else 0,
        skipped_fixture_count=0,
        passed_final_answer_gate=passed,
        warnings=[] if passed else ["fake:failed"],
        summary_json={
            "aggregate_deltas_json": {
                "final_hit_rate_delta": 0.0 if passed else -0.5,
                "roi_delta": 0.0 if passed else -0.5,
                "profit_loss_delta": 0.0 if passed else -2.0,
            }
        },
    )
    return HistoricalProbabilityCalibrationProfileArtifactReport(
        report_key=f"artifact:{','.join(competition_ids)}",
        artifact_id="fake",
        gate_report_key=gate_report.report_key,
        emitted_profile=profile is not None,
        profile=profile,
        gate_report=gate_report,
        warning_codes=[] if passed else ["fake:failed"],
        summary_json={"fake_passed": passed},
    )


def _gate_options(
    *,
    quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileGateOptions:
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
        quality_gate_options=quality_gate_options
        or HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=1,
            fail_on_suite_statuses=(),
            min_final_hit_rate_delta=None,
            max_brier_score_delta=None,
            max_log_loss_delta=None,
            max_mean_calibration_error_delta=None,
        ),
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
    *,
    competition_id: str = "TEST",
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"calibration_profile_rolling_{competition_id}_{season}",
            name=f"Calibration profile rolling {competition_id} {season}",
            competition_id=competition_id,
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            _fixture(
                f"{competition_id}_{season}_{index}",
                competition_id,
                base_time + timedelta(days=index + 1),
                home_goals,
                away_goals,
            )
            for index, (home_goals, away_goals) in enumerate(results)
        ],
    )


def _fixture(
    fixture_id: str,
    competition_id: str,
    kickoff_time_utc: datetime,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=competition_id,
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
