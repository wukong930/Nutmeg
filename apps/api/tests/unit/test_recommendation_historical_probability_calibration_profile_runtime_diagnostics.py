from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_diagnostics as diagnostics,
)
from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_replay as replay,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
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


def test_probability_calibration_runtime_diagnostics_groups_regressions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    seen_calibrated: list[bool] = []

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        del options, baseline_optimizer_profile, candidate_optimizer_profile
        calibrated = _has_calibrated_prediction(historical_slices)
        seen_calibrated.append(calibrated)
        return _fake_suite(historical_slices, calibrated=calibrated)

    monkeypatch.setattr(
        diagnostics,
        "run_historical_recommendation_backtest_suite",
        fake_run,
    )

    report = (
        diagnostics.build_historical_probability_calibration_profile_runtime_diagnostic_report(
            [
                _slice("slice-a", competition_id="TEST_A", season="2024-2025"),
                _slice("slice-b", competition_id="TEST_B", season="2025-2026"),
            ],
            profile_set_path=profile_path,
            options=diagnostics.HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions(
                profile_keys=("profile:test",),
                min_group_sample_size=1,
                top_slice_limit=5,
                top_group_limit=5,
            ),
        )
    )

    assert seen_calibrated == [False, True]
    assert report.status == "generated"
    assert report.selected_profile_key == "profile:test"
    assert report.slice_count == 2
    assert report.adjusted_fixture_count == 2
    assert report.adjusted_candidate_count == 6
    assert report.overall.final_answer_count == 3
    assert report.overall.final_answer_hit_delta_count == 1
    assert report.overall.brier_score_delta == pytest.approx(0.0333333333)
    assert report.overall.log_loss_delta == pytest.approx(0.0733333333)
    assert report.overall.mean_calibration_error_delta == pytest.approx(0.01)
    assert report.top_regression_slices[0].slice_id == "slice-a"
    assert report.top_regression_groups[0].group_key in {
        "2024-2025",
        "TEST_A",
        "TEST_A|2024-2025",
    }
    assert report.by_competition[0].competition_id == "TEST_A"
    assert report.by_competition[0].quality_regression_score == pytest.approx(0.20)
    assert report.summary_json["top_regression_slice_ids"] == ["slice-a"]


def test_probability_calibration_runtime_diagnostics_cli_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slice_path = tmp_path / "slice.json"
    profile_path = tmp_path / "profile_set.json"
    output_path = tmp_path / "diagnostics.json"
    historical_slice = _slice(
        "slice-a",
        competition_id="TEST_A",
        season="2024-2025",
    )
    slice_path.write_text(
        f"{historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        diagnostics,
        "run_historical_recommendation_backtest_suite",
        lambda historical_slices, **kwargs: _fake_suite(
            historical_slices,
            calibrated=_has_calibrated_prediction(historical_slices),
        ),
    )

    args = diagnostics._parse_args(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--pass-types",
            "1x1,3x1",
            "--modes",
            "single",
            "--unit-stake",
            "2",
            "--max-budget",
            "20",
            "--min-probability",
            "0.15",
            "--max-candidates-per-fixture",
            "3",
            "--final-answer-scenario-variant-count",
            "3",
            "--derive-market-context-signals",
            "--min-group-sample-size",
            "1",
            "--top-slice-limit",
            "5",
            "--top-group-limit",
            "5",
        ]
    )
    options = diagnostics._options_from_args(args)

    assert options.profile_keys == ("profile:test",)
    assert options.backtest_options.pass_types == ("1x1", "3x1")
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.top_slice_limit == 5
    assert options.top_group_limit == 5

    diagnostics.main(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--top-slice-limit",
            "5",
            "--top-group-limit",
            "5",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    assert payload["selected_profile_key"] == "profile:test"
    assert payload["top_regression_slices"][0]["slice_id"] == "slice-a"


def _has_calibrated_prediction(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> bool:
    return any(
        "candidate_probability_calibration_profile_key" in prediction.metadata_json
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
        for prediction in fixture.predictions
    )


def _fake_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    calibrated: bool,
) -> HistoricalRecommendationBacktestSuiteResult:
    comparisons = [
        _comparison(historical_slice.metadata.slice_id, calibrated=calibrated)
        for historical_slice in historical_slices
    ]
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key="diagnostic-suite:calibrated" if calibrated else "diagnostic-suite:baseline",
        status="unchanged",
        slice_count=len(historical_slices),
        comparison_count=len(comparisons),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
        summary_json={},
    )


def _comparison(
    slice_id: str,
    *,
    calibrated: bool,
) -> HistoricalRecommendationBacktestComparisonResult:
    result = _backtest_result(slice_id, calibrated=calibrated)
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{slice_id}:{calibrated}",
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
    calibrated: bool,
) -> HistoricalRecommendationBacktestResult:
    if slice_id == "slice-a":
        sample_size = 2
        hit_count = 2 if calibrated else 1
        total_stake = 4.0
        profit_loss = 2.0 if calibrated else -2.0
        brier_score = 0.16 if calibrated else 0.10
        log_loss = 0.42 if calibrated else 0.30
        calibration_error = 0.04 if calibrated else 0.02
        outcome = "draw" if calibrated else "home_win"
    else:
        sample_size = 1
        hit_count = 1
        total_stake = 2.0
        profit_loss = 0.0
        brier_score = 0.18 if calibrated else 0.20
        log_loss = 0.48 if calibrated else 0.50
        calibration_error = 0.02 if calibrated else 0.03
        outcome = "home_win"
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key="1x1:single",
            pass_type="1x1",
            mode="single",
        ),
        status="completed",
        selected_fixture_ids=[f"{slice_id}_fixture"],
        selected_outcomes={f"{slice_id}_fixture": [outcome]},
        total_stake=total_stake,
        actual_return=total_stake + profit_loss if profit_loss > 0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        expected_hit_probability=0.40,
        actual_hit=hit_count == sample_size,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}:{calibrated}",
        slice_id=slice_id,
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixture_count=1,
        candidate_count=3,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=final_answer,
        scenarios=[final_answer],
        final_hit_sample_size=sample_size,
        final_hit_count=hit_count,
        final_hit_rate=hit_count / sample_size,
        total_stake=total_stake,
        actual_return=total_stake + profit_loss if profit_loss > 0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake,
        mean_calibration_error=calibration_error,
        brier_score=brier_score,
        log_loss=log_loss,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _profile_set() -> replay.ProbabilityCalibrationRuntimeProfileSet:
    return replay.ProbabilityCalibrationRuntimeProfileSet(
        profile_version="profile-set:test",
        status="runtime_profile_proposal_ready",
        runtime_profile_proposal_allowed=True,
        holdout_candidate_allowed=True,
        profiles=[_profile()],
    )


def _profile() -> CandidateProbabilityCalibrationProfile:
    return CandidateProbabilityCalibrationProfile(
        profile_key="profile:test",
        source_report_key="gate:test",
        mode="active",
        segment_mode="market_odds_band",
        min_bucket_sample_size=1,
        blend_weight=1.0,
        target_competition_ids=("TEST_A", "TEST_B"),
        target_market_types=("1x2",),
        target_outcomes=("draw",),
        min_probability=0.0,
        max_probability=1.0,
        min_decimal_odds=2.25,
        max_decimal_odds=3.45,
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.35,
                calibrated_probability=0.45,
                sample_size=20,
                market_type="1x2",
            )
        ],
    )


def _slice(
    slice_id: str,
    *,
    competition_id: str,
    season: str,
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Probability calibration runtime diagnostics test slice",
            competition_id=competition_id,
            season=season,
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture",
                competition_id=competition_id,
                kickoff_time_utc=datetime(2025, 5, 2, 18, tzinfo=UTC),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=datetime(2025, 5, 1, 10, tzinfo=UTC),
                model_version="poisson-v3.1-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.45,
                        decimal_odds=2.10,
                        market_probability=1 / 2.10,
                    ),
                    HistoricalMarketPrediction(
                        outcome="draw",
                        probability=0.30,
                        decimal_odds=3.20,
                        market_probability=1 / 3.20,
                    ),
                    HistoricalMarketPrediction(
                        outcome="away_win",
                        probability=0.25,
                        decimal_odds=3.80,
                        market_probability=1 / 3.80,
                    ),
                ],
            )
        ],
    )
