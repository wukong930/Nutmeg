from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import loads

from nutmeg.accuracy import HistoricalProbabilityCalibrationTransformOptions
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    apply_candidate_probability_calibration_profile,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_artifact import (
    HistoricalProbabilityCalibrationProfileArtifactOptions,
    _options_from_args,
    _parse_args,
    build_historical_probability_calibration_profile_artifact_report,
    main,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateOptions,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.models import RecommendationCandidate


def test_probability_calibration_profile_artifact_emits_runtime_profile() -> None:
    report = build_historical_probability_calibration_profile_artifact_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileArtifactOptions(
            profile_mode="active",
            gate_options=_gate_options(),
        ),
    )

    assert report.emitted_profile is True
    assert report.profile is not None
    assert report.profile.mode == "active"
    assert report.profile.source_report_key == report.gate_report.report_key
    assert report.profile.target_competition_ids == ("TEST",)
    assert report.profile.blend_weight == 1.0
    assert {bucket.outcome for bucket in report.profile.buckets} == {
        "home_win",
        "draw",
        "away_win",
    }

    result = apply_candidate_probability_calibration_profile(
        [
            _candidate("runtime_a", "home_win", probability=0.80, decimal_odds=1.25),
            _candidate("runtime_a", "draw", probability=0.10, decimal_odds=10.0),
            _candidate("runtime_a", "away_win", probability=0.10, decimal_odds=10.0),
        ],
        profile=report.profile,
    )

    assert result.status == "applied"
    assert result.adjusted_candidate_count == 3
    assert sum(candidate.probability for candidate in result.candidates) == 1.0
    assert all(candidate.probability_source == "calibrated" for candidate in result.candidates)


def test_probability_calibration_profile_artifact_blocks_failed_gate_by_default() -> None:
    report = build_historical_probability_calibration_profile_artifact_report(
        _calibration_slices(),
        options=HistoricalProbabilityCalibrationProfileArtifactOptions(
            gate_options=_gate_options(
                quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                    min_final_hit_sample_size=1,
                    min_final_hit_rate_delta=1.0,
                )
            ),
        ),
    )

    assert report.emitted_profile is False
    assert report.profile is None
    assert (
        "historical_probability_calibration_profile_artifact:"
        "final_answer_gate_not_passed"
    ) in report.warning_codes


def test_probability_calibration_profile_artifact_cli_writes_report_and_profile(
    tmp_path,
    capsys,
) -> None:
    slice_paths = []
    for index, historical_slice in enumerate(_calibration_slices()):
        slice_path = tmp_path / f"slice_{index}.json"
        slice_path.write_text(
            f"{historical_slice.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        slice_paths.append(slice_path)
    output_path = tmp_path / "artifact_report.json"
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
            "--max-brier-score-delta",
            "1.0",
            "--max-log-loss-delta",
            "1.0",
            "--max-mean-calibration-error-delta",
            "1.0",
            "--allow-failed-final-answer-gate",
        ]
    )

    captured = capsys.readouterr()
    payload = loads(captured.out)
    assert payload["emitted_profile"] is True
    assert output_path.exists()
    assert profile_path.exists()
    profile_payload = loads(profile_path.read_text(encoding="utf-8"))
    assert profile_payload["mode"] == "active"
    assert profile_payload["target_competition_ids"] == ["TEST"]


def test_probability_calibration_profile_artifact_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--artifact-id",
            "artifact-test",
            "--profile-mode",
            "active",
            "--allow-failed-final-answer-gate",
            "--gate-id",
            "gate-test",
            "--target-outcomes",
            "home_win,draw",
            "--probability-min",
            "0.20",
            "--probability-max",
            "0.80",
            "--min-decimal-odds",
            "1.40",
            "--max-decimal-odds",
            "3.50",
            "--segment-mode",
            "market_odds_band",
            "--final-answer-scenario-variant-count",
            "4",
            "--min-final-answer-changed-count",
            "2",
        ]
    )

    options = _options_from_args(args)

    assert options.artifact_id == "artifact-test"
    assert options.profile_mode == "active"
    assert options.require_passed_final_answer_gate is False
    assert options.gate_options.gate_id == "gate-test"
    assert options.gate_options.target_outcomes == ("home_win", "draw")
    assert options.gate_options.probability_min == 0.20
    assert options.gate_options.probability_max == 0.80
    assert options.gate_options.min_decimal_odds == 1.40
    assert options.gate_options.max_decimal_odds == 3.50
    assert options.gate_options.transform_options.segment_mode == "market_odds_band"
    assert options.gate_options.backtest_options.final_answer_scenario_variant_count == 4
    assert options.gate_options.quality_gate_options.min_final_answer_changed_count == 2


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
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"calibration_profile_artifact_{season}",
            name=f"Calibration profile artifact {season}",
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


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        data_quality_score=90,
        model_confidence_score=0.90,
        calibration_score=0.90,
        odds_stability_score=0.90,
        metadata_json={"competition_id": "TEST"},
    )
