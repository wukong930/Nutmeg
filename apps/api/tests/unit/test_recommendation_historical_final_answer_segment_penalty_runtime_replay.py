from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_final_answer_segment_penalty_runtime_replay as replay,
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


def test_segment_penalty_runtime_replay_passes_when_runtime_thresholds_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_options: list[HistoricalRecommendationBacktestOptions] = []

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        observed_options.append(resolved_options)
        return _fake_suite(
            final_answer_segment_penalty=resolved_options.final_answer_segment_penalty
        )

    monkeypatch.setattr(replay, "run_historical_recommendation_backtest_suite", fake_run)

    report = replay.build_historical_final_answer_segment_penalty_runtime_replay_report(
        [],
        rule_set=_rule_set(candidate_roi=0.04, proposed_production_enabled=True),
        options=replay.HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions(
            enable_shadow_replay=True,
            min_changed_final_answer_count=0,
            min_candidate_roi=0.0,
            require_proposed_production_enabled=True,
            require_profile_runtime_allowed=True,
        ),
    )

    assert report.status == "runtime_replay_passed"
    assert report.runtime_replay_allowed is True
    assert report.holdout_replay_allowed is True
    assert report.selected_rule_count == 1
    assert report.penalty_option_count == 2
    assert report.final_answer_hit_delta_count == 2
    assert all(check.status == "passed" for check in report.checks)
    candidate_options = observed_options[-1]
    assert candidate_options.final_answer_segment_penalty is True
    assert candidate_options.final_answer_segment_penalty_strength == 0.02
    assert candidate_options.final_answer_segment_pass_types == ("3x1",)
    assert candidate_options.final_answer_segment_modes == ("single",)
    assert candidate_options.final_answer_segment_competition_ids == ("GER_BUNDESLIGA",)
    assert candidate_options.final_answer_segment_min_competition_season_index == 4


def test_segment_penalty_runtime_replay_is_holdout_only_when_roi_floor_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        _negative_roi_fake_run,
    )

    report = replay.build_historical_final_answer_segment_penalty_runtime_replay_report(
        [],
        rule_set=_rule_set(candidate_roi=-0.015),
        options=replay.HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions(
            enable_shadow_replay=True,
            min_changed_final_answer_count=0,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_replay_passed"
    assert report.runtime_replay_allowed is False
    assert report.holdout_replay_allowed is True
    assert failed_checks == {"candidate_roi"}
    assert "final_answer_segment_penalty_runtime_replay:holdout_only" in report.warnings


def test_segment_penalty_runtime_replay_disabled_without_flag() -> None:
    report = replay.build_historical_final_answer_segment_penalty_runtime_replay_report(
        [],
        rule_set=_rule_set(candidate_roi=0.04),
    )

    assert report.status == "disabled"
    assert report.runtime_replay_allowed is False
    assert report.holdout_replay_allowed is False
    assert report.checks == []


def test_segment_penalty_runtime_replay_blocks_profit_loss_harm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        _profit_loss_harm_fake_run,
    )

    report = replay.build_historical_final_answer_segment_penalty_runtime_replay_report(
        [],
        rule_set=_rule_set(candidate_roi=0.04),
        options=replay.HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=2,
            min_changed_final_answer_count=0,
            min_penalty_option_count=2,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_replay_failed"
    assert report.final_hit_harm_count_vs_baseline == 0
    assert report.profit_loss_harm_count_vs_baseline == 1
    assert "profit_loss_harm_count_vs_baseline" in failed_checks


def test_segment_penalty_runtime_replay_loader_accepts_proposal_report(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "proposal.json"
    profile_path.write_text(
        """
{
  "proposal_profile_set_json": {
    "profile_version": "profile-from-proposal",
    "status": "holdout_only",
    "runtime_profile_proposal_allowed": false,
    "holdout_candidate_allowed": true,
    "final_answer_segment_penalty_rules": [
      {
        "rule_id": "rule-from-proposal",
        "holdout_candidate_enabled": true,
        "penalty_strength": 0.02,
        "constraints_json": {
          "final_answer_segment_pass_types": ["3x1"],
          "final_answer_segment_modes": ["single"],
          "final_answer_segment_competition_ids": ["GER_BUNDESLIGA"],
          "final_answer_segment_min_competition_season_index": 4
        }
      }
    ]
  }
}
""",
        encoding="utf-8",
    )

    rule_set = replay.load_final_answer_segment_penalty_runtime_rule_set(profile_path)

    assert rule_set.profile_version == "profile-from-proposal"
    assert rule_set.holdout_candidate_allowed is True
    assert rule_set.rules[0].rule_id == "rule-from-proposal"


def test_segment_penalty_runtime_replay_accepts_multiple_suite_manifests(
    tmp_path: Path,
) -> None:
    slice_a_path = tmp_path / "slice-a.json"
    slice_b_path = tmp_path / "slice-b.json"
    manifest_a_path = tmp_path / "manifest-a.json"
    manifest_b_path = tmp_path / "manifest-b.json"
    profile_path = tmp_path / "profile.json"
    slice_a_path.write_text(
        f"{_slice(slice_id='slice-a').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    slice_b_path.write_text(
        f"{_slice(slice_id='slice-b').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    manifest_a_path.write_text(
        _manifest_json("suite-a", slice_a_path.name),
        encoding="utf-8",
    )
    manifest_b_path.write_text(
        _manifest_json("suite-b", slice_b_path.name),
        encoding="utf-8",
    )
    profile_path.write_text(
        f"{_rule_set(candidate_roi=0.04).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = replay._parse_args(
        [
            "--suite-manifest",
            str(manifest_a_path),
            "--suite-manifest",
            str(manifest_b_path),
            "--rule-profile",
            str(profile_path),
        ]
    )
    loaded = replay._historical_slices_from_args(args)

    assert len(args.suite_manifest) == 2
    assert len(loaded.slices) == 2
    assert len(loaded.manifest_results) == 2
    assert loaded.manifest_result is None
    assert {historical_slice.metadata.slice_id for historical_slice in loaded.slices} == {
        "slice-a",
        "slice-b",
    }


def test_segment_penalty_runtime_replay_cli_options_loader_and_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        _positive_roi_fake_run,
    )
    slice_path = tmp_path / "slice.json"
    profile_path = tmp_path / "profile.json"
    output_path = tmp_path / "runtime_replay.json"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    profile_json = _rule_set(
        candidate_roi=0.04,
        proposed_production_enabled=True,
    ).model_dump_json(indent=2)
    profile_path.write_text(
        f"{profile_json}\n",
        encoding="utf-8",
    )

    args = replay._parse_args(
        [
            str(slice_path),
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--rule-ids",
            "segment-rule:test",
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
            "--min-final-answer-count",
            "30",
            "--min-changed-final-answer-count",
            "0",
            "--min-penalty-option-count",
            "2",
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
    assert options.rule_ids == ("segment-rule:test",)
    assert options.min_candidate_roi == 0.01
    assert options.max_final_hit_harm_count_vs_baseline == 2
    assert options.max_profit_loss_harm_count_vs_baseline == 3
    assert options.require_profile_runtime_allowed is True
    assert options.require_proposed_production_enabled is True

    main_args = [
        str(slice_path),
        "--rule-profile",
        str(profile_path),
        "--output-path",
        str(output_path),
        "--enable-shadow-replay",
        "--min-changed-final-answer-count",
        "0",
        "--min-penalty-option-count",
        "2",
        "--min-candidate-roi",
        "0.01",
        "--require-profile-runtime-allowed",
        "--require-proposed-production-enabled",
    ]
    replay.main(main_args)

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_replay_passed"
    assert payload["runtime_replay_allowed"] is True
    assert payload["source_rule_profile_version"] == "runtime-profile:test"


def _positive_roi_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    return _fake_suite(
        final_answer_segment_penalty=resolved_options.final_answer_segment_penalty,
    )


def _negative_roi_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    return _fake_suite(
        final_answer_segment_penalty=resolved_options.final_answer_segment_penalty,
        candidate_roi=-0.015,
        candidate_profit_loss=-0.9,
    )


def _profit_loss_harm_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    if resolved_options.final_answer_segment_penalty:
        return _suite_with_comparisons(
            "candidate-suite:profit-loss-harm",
            [
                _comparison("slice_harm", actual_hit=True, profit_loss=0.0),
                _comparison("slice_improve", actual_hit=True, profit_loss=2.0),
            ],
            final_hit_count=2,
            profit_loss=2.0,
            candidate_roi=0.04,
            penalty_option_count=2,
        )
    return _suite_with_comparisons(
        "baseline-suite:profit-loss-harm",
        [
            _comparison("slice_harm", actual_hit=True, profit_loss=1.0),
            _comparison("slice_improve", actual_hit=True, profit_loss=-1.0),
        ],
        final_hit_count=2,
        profit_loss=0.0,
        candidate_roi=0.0,
    )


def _fake_suite(
    *,
    final_answer_segment_penalty: bool,
    candidate_roi: float = 0.04,
    candidate_profit_loss: float = 2.4,
) -> HistoricalRecommendationBacktestSuiteResult:
    if final_answer_segment_penalty:
        final_hit_count = 25
        roi = candidate_roi
        profit_loss = candidate_profit_loss
        penalty_option_count = 2
        brier_score = 0.17
        log_loss = 0.45
        calibration_error = 0.08
    else:
        final_hit_count = 23
        roi = -0.08
        profit_loss = -4.8
        penalty_option_count = 0
        brier_score = 0.20
        log_loss = 0.52
        calibration_error = 0.12
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=(
            "candidate-suite:test"
            if final_answer_segment_penalty
            else "baseline-suite:test"
        ),
        status="unchanged",
        slice_count=30,
        comparison_count=30,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        summary_json={
            "candidate_final_hit_sample_size": 30,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_count / 30,
            "candidate_profit_loss": profit_loss,
            "candidate_roi": roi,
            "candidate_brier_score": brier_score,
            "candidate_log_loss": log_loss,
            "candidate_mean_calibration_error": calibration_error,
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
    candidate_roi: float,
    penalty_option_count: int = 0,
) -> HistoricalRecommendationBacktestSuiteResult:
    sample_size = len(comparisons)
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
            "candidate_roi": candidate_roi,
            "candidate_brier_score": 0.17,
            "candidate_log_loss": 0.45,
            "candidate_mean_calibration_error": 0.08,
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
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
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
        mean_calibration_error=0.08,
        brier_score=0.17,
        log_loss=0.45,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _rule_set(
    *,
    candidate_roi: float,
    proposed_production_enabled: bool = False,
) -> replay.FinalAnswerSegmentPenaltyRuntimeRuleSet:
    return replay.FinalAnswerSegmentPenaltyRuntimeRuleSet(
        profile_version="runtime-profile:test",
        status=(
            "runtime_profile_proposal_ready"
            if proposed_production_enabled
            else "holdout_only"
        ),
        runtime_profile_proposal_allowed=proposed_production_enabled,
        holdout_candidate_allowed=True,
        rules=[
            replay.FinalAnswerSegmentPenaltyRuntimeRule(
                rule_id="segment-rule:test",
                proposed_profile_version="runtime-profile:test",
                proposed_production_enabled=proposed_production_enabled,
                holdout_candidate_enabled=True,
                pass_types=["3x1"],
                modes=["single"],
                competition_ids=["GER_BUNDESLIGA"],
                min_competition_season_index=4,
                penalty_strength=0.02,
                constraints_json={
                    "final_answer_segment_penalty": True,
                    "final_answer_segment_penalty_strength": 0.02,
                    "final_answer_segment_pass_types": ["3x1"],
                    "final_answer_segment_modes": ["single"],
                    "final_answer_segment_competition_ids": ["GER_BUNDESLIGA"],
                    "final_answer_segment_min_competition_season_index": 4,
                },
            )
        ],
    )


def _manifest_json(suite_id: str, slice_path: str) -> str:
    return (
        "{\n"
        '  "manifest_version": "v1",\n'
        f'  "suite_id": "{suite_id}",\n'
        f'  "name": "{suite_id}",\n'
        '  "slices": [\n'
        f'    {{"slice_path": "{slice_path}", "enabled": true}}\n'
        "  ]\n"
        "}\n"
    )


def _slice(*, slice_id: str = "slice-runtime-test") -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Runtime replay test slice",
            competition_id="GER_BUNDESLIGA",
            season="2024-2025",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture-runtime-test",
                competition_id="GER_BUNDESLIGA",
                kickoff_time_utc=datetime(2025, 5, 2, 18, tzinfo=UTC),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=datetime(2025, 5, 1, 10, tzinfo=UTC),
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
