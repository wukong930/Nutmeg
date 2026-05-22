from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads
from pathlib import Path

import pytest

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


def test_probability_calibration_runtime_replay_passes_when_thresholds_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_calibrated = []

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
        return _fake_suite(calibrated=calibrated)

    monkeypatch.setattr(replay, "run_historical_recommendation_backtest_suite", fake_run)

    report = replay.build_historical_probability_calibration_profile_runtime_replay_report(
        [_slice()],
        profile_set=_profile_set(runtime_allowed=True),
        options=replay.HistoricalProbabilityCalibrationProfileRuntimeReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=30,
            min_changed_final_answer_count=1,
            min_adjusted_fixture_count=1,
            min_adjusted_candidate_count=3,
            min_candidate_roi=0.0,
            require_profile_runtime_allowed=True,
            require_proposed_production_enabled=True,
        ),
    )

    assert seen_calibrated == [False, True]
    assert report.status == "runtime_replay_passed"
    assert report.runtime_replay_allowed is True
    assert report.holdout_replay_allowed is True
    assert report.selected_profile_count == 1
    assert report.adjusted_fixture_count == 1
    assert report.adjusted_candidate_count == 3
    assert report.changed_final_answer_count == 1
    assert report.final_answer_hit_delta_count == 2
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.internal_strategy_label_exposed is False
    assert all(check.status != "failed" for check in report.checks)


def test_probability_calibration_runtime_replay_disabled_without_flag() -> None:
    report = replay.build_historical_probability_calibration_profile_runtime_replay_report(
        [_slice()],
        profile_set=_profile_set(runtime_allowed=True),
    )

    assert report.status == "disabled"
    assert report.runtime_replay_allowed is False
    assert report.holdout_replay_allowed is False
    assert report.checks == []


def test_probability_calibration_runtime_replay_blocks_shadow_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        lambda historical_slices, **kwargs: _fake_suite(
            calibrated=_has_calibrated_prediction(historical_slices)
        ),
    )

    report = replay.build_historical_probability_calibration_profile_runtime_replay_report(
        [_slice()],
        profile_set=_profile_set(profile=_profile(mode="shadow"), runtime_allowed=True),
        options=replay.HistoricalProbabilityCalibrationProfileRuntimeReplayOptions(
            enable_shadow_replay=True,
            min_changed_final_answer_count=0,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_replay_failed"
    assert report.runtime_replay_allowed is False
    assert "selected_profile_active" in failed_checks


def test_probability_calibration_runtime_replay_loader_accepts_proposal_report(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "proposal.json"
    profile_path.write_text(
        """
{
  "proposal_profile_set_json": {
    "profile_version": "profile-from-proposal",
    "status": "runtime_profile_proposal_ready",
    "runtime_profile_proposal_allowed": true,
    "holdout_candidate_allowed": true,
    "production_recommendation_changed": false,
    "candidate_probability_calibration_profiles": [
      {
        "profile_key": "profile-from-proposal:test",
        "mode": "active",
        "buckets": [
          {
            "outcome": "draw",
            "segment_mode": "market_odds_band",
            "bucket_start": 0.30,
            "bucket_end": 0.35,
            "calibrated_probability": 0.45,
            "sample_size": 20,
            "competition_id": "TEST_LEAGUE",
            "market_type": "1x2"
          }
        ],
        "target_competition_ids": ["TEST_LEAGUE"],
        "target_market_types": ["1x2"],
        "target_outcomes": ["draw"],
        "segment_mode": "market_odds_band",
        "min_decimal_odds": 2.25,
        "max_decimal_odds": 3.45
      }
    ]
  }
}
""",
        encoding="utf-8",
    )

    profile_set = replay.load_probability_calibration_runtime_profile_set(profile_path)

    assert profile_set.profile_version == "profile-from-proposal"
    assert profile_set.runtime_profile_proposal_allowed is True
    assert profile_set.holdout_candidate_allowed is True
    assert profile_set.profiles[0].profile_key == "profile-from-proposal:test"


def test_probability_calibration_runtime_replay_passes_season_context_to_profile() -> None:
    profile = _profile(
        min_competition_season_index_by_competition_id={"TEST_LEAGUE": 2}
    )

    replay_input = replay._calibrated_replay_input(
        [
            _season_slice("slice-runtime-2020", season="2020-2021"),
            _season_slice("slice-runtime-2021", season="2021-2022"),
        ],
        profile=profile,
    )

    assert replay_input.adjusted_fixture_count == 1
    assert replay_input.adjusted_candidate_count == 3
    first_slice, second_slice = replay_input.slices
    first_draw = next(
        prediction
        for prediction in first_slice.fixtures[0].predictions
        if prediction.outcome == "draw"
    )
    second_draw = next(
        prediction
        for prediction in second_slice.fixtures[0].predictions
        if prediction.outcome == "draw"
    )
    assert "candidate_probability_calibration_profile_key" not in first_draw.metadata_json
    assert second_draw.metadata_json["candidate_probability_calibration_profile_key"] == (
        "profile:test"
    )
    assert second_draw.metadata_json["competition_season_index"] == 2


def test_probability_calibration_runtime_replay_cli_options_loader_and_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        lambda historical_slices, **kwargs: _fake_suite(
            calibrated=_has_calibrated_prediction(historical_slices)
        ),
    )
    slice_path = tmp_path / "slice.json"
    profile_path = tmp_path / "profile_set.json"
    output_path = tmp_path / "runtime_replay.json"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    profile_path.write_text(
        f"{_profile_set(runtime_allowed=True).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = replay._parse_args(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
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
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "3",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--final-answer-scenario-variant-count",
            "3",
            "--derive-market-context-signals",
            "--min-final-answer-count",
            "30",
            "--min-changed-final-answer-count",
            "1",
            "--min-adjusted-fixture-count",
            "1",
            "--min-adjusted-candidate-count",
            "3",
            "--min-candidate-roi",
            "0.01",
            "--max-final-hit-harm-count-vs-baseline",
            "2",
            "--max-profit-loss-harm-count-vs-baseline",
            "3",
            "--require-profile-runtime-allowed",
            "--require-proposed-production-enabled",
            "--no-fail-process",
        ]
    )
    options = replay._options_from_args(args)

    assert options.enable_shadow_replay is True
    assert options.profile_keys == ("profile:test",)
    assert options.backtest_options.pass_types == ("1x1", "3x1")
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.min_candidate_roi == 0.01
    assert options.max_final_hit_harm_count_vs_baseline == 2
    assert options.max_profit_loss_harm_count_vs_baseline == 3
    assert options.require_profile_runtime_allowed is True
    assert options.require_proposed_production_enabled is True

    replay.main(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--min-changed-final-answer-count",
            "1",
            "--min-adjusted-candidate-count",
            "3",
            "--min-candidate-roi",
            "0.01",
            "--require-profile-runtime-allowed",
            "--require-proposed-production-enabled",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_replay_passed"
    assert payload["runtime_replay_allowed"] is True
    assert payload["selected_profile_key"] == "profile:test"


def _has_calibrated_prediction(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> bool:
    return any(
        "candidate_probability_calibration_profile_key" in prediction.metadata_json
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
        for prediction in fixture.predictions
    )


def _fake_suite(*, calibrated: bool) -> HistoricalRecommendationBacktestSuiteResult:
    if calibrated:
        final_hit_count = 25
        roi = 0.04
        profit_loss = 2.4
        brier_score = 0.17
        log_loss = 0.45
        calibration_error = 0.08
        comparison = _comparison(
            "slice-runtime-test",
            outcome="draw",
            actual_hit=True,
            profit_loss=1.0,
        )
    else:
        final_hit_count = 23
        roi = -0.08
        profit_loss = -4.8
        brier_score = 0.20
        log_loss = 0.52
        calibration_error = 0.12
        comparison = _comparison(
            "slice-runtime-test",
            outcome="home_win",
            actual_hit=True,
            profit_loss=0.0,
        )
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key="candidate-suite:test" if calibrated else "baseline-suite:test",
        status="unchanged",
        slice_count=30,
        comparison_count=30,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=[comparison],
        summary_json={
            "candidate_final_hit_sample_size": 30,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_count / 30,
            "candidate_profit_loss": profit_loss,
            "candidate_roi": roi,
            "candidate_brier_score": brier_score,
            "candidate_log_loss": log_loss,
            "candidate_mean_calibration_error": calibration_error,
        },
    )


def _comparison(
    slice_id: str,
    *,
    outcome: str,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalRecommendationBacktestComparisonResult:
    result = _backtest_result(
        slice_id,
        outcome=outcome,
        actual_hit=actual_hit,
        profit_loss=profit_loss,
    )
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{slice_id}:{outcome}",
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
    outcome: str,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalRecommendationBacktestResult:
    fixture_id = f"{slice_id}_fixture"
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key="1x1:single",
            pass_type="1x1",
            mode="single",
        ),
        status="completed",
        selected_fixture_ids=[fixture_id],
        selected_outcomes={fixture_id: [outcome]},
        total_stake=2.0,
        actual_return=2.0 + profit_loss if profit_loss > 0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / 2.0,
        expected_hit_probability=0.40,
        actual_hit=actual_hit,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}:{outcome}:{profit_loss}",
        slice_id=slice_id,
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixture_count=1,
        candidate_count=3,
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
        mean_calibration_error=0.08,
        brier_score=0.17,
        log_loss=0.45,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _profile_set(
    *,
    profile: CandidateProbabilityCalibrationProfile | None = None,
    runtime_allowed: bool = False,
) -> replay.ProbabilityCalibrationRuntimeProfileSet:
    return replay.ProbabilityCalibrationRuntimeProfileSet(
        profile_version="profile-set:test",
        status=(
            "runtime_profile_proposal_ready"
            if runtime_allowed
            else "holdout_only"
        ),
        runtime_profile_proposal_allowed=runtime_allowed,
        holdout_candidate_allowed=True,
        profiles=[profile or _profile()],
    )


def _profile(
    *,
    mode: str = "active",
    min_competition_season_index_by_competition_id: dict[str, int] | None = None,
) -> CandidateProbabilityCalibrationProfile:
    return CandidateProbabilityCalibrationProfile(
        profile_key="profile:test",
        source_report_key="gate:test",
        mode=mode,  # type: ignore[arg-type]
        segment_mode="market_odds_band",
        min_bucket_sample_size=1,
        blend_weight=1.0,
        target_competition_ids=("TEST_LEAGUE",),
        target_market_types=("1x2",),
        target_outcomes=("draw",),
        min_probability=0.0,
        max_probability=1.0,
        min_decimal_odds=2.25,
        max_decimal_odds=3.45,
        min_competition_season_index_by_competition_id=(
            min_competition_season_index_by_competition_id or {}
        ),
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.35,
                calibrated_probability=0.45,
                sample_size=20,
                competition_id="TEST_LEAGUE",
                market_type="1x2",
            )
        ],
    )


def _season_slice(slice_id: str, *, season: str) -> HistoricalRecommendationSlice:
    historical_slice = _slice()
    fixture = historical_slice.fixtures[0]
    return historical_slice.model_copy(
        update={
            "metadata": historical_slice.metadata.model_copy(
                update={
                    "slice_id": slice_id,
                    "season": season,
                }
            ),
            "fixtures": [
                fixture.model_copy(
                    update={
                        "fixture_id": f"{slice_id}_fixture",
                    }
                )
            ],
        }
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="slice-runtime-test",
            name="Probability calibration runtime replay test slice",
            competition_id="TEST_LEAGUE",
            season="2024-2025",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="slice-runtime-test_fixture",
                competition_id="TEST_LEAGUE",
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
