from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_runtime_replay as replay,
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


def test_selection_value_signal_runtime_replay_passes_and_maps_rule_options(
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
        del historical_slices, baseline_optimizer_profile, candidate_optimizer_profile
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        observed_options.append(resolved_options)
        return _fake_suite(
            selection_value_signal=resolved_options.final_answer_selection_value_signal
        )

    monkeypatch.setattr(replay, "run_historical_recommendation_backtest_suite", fake_run)

    report = (
        replay.build_historical_final_answer_selection_value_signal_runtime_replay_report(
            [],
            rule_set=_rule_set(proposed_production_enabled=True),
            options=replay.HistoricalFinalAnswerSelectionValueSignalRuntimeReplayOptions(
                enable_shadow_replay=True,
                min_final_answer_count=30,
                require_profile_runtime_allowed=True,
                require_proposed_production_enabled=True,
            ),
        )
    )

    assert report.status == "runtime_replay_passed"
    assert report.runtime_replay_allowed is True
    assert report.holdout_replay_allowed is True
    assert report.selected_rule_count == 1
    assert report.affected_leg_count == 1
    assert report.movement_count == 1
    assert report.positive_movement_count == 1
    assert report.harmful_movement_count == 0
    assert all(check.status == "passed" for check in report.checks)
    candidate_options = observed_options[-1]
    assert candidate_options.final_answer_selection_value_signal is True
    assert candidate_options.final_answer_selection_value_signal_strength == 0.32
    assert candidate_options.final_answer_selection_value_signal_min_decimal_odds == 2.5
    assert candidate_options.final_answer_selection_value_signal_max_decimal_odds == (
        3.3333333333333335
    )
    assert candidate_options.final_answer_selection_value_signal_score_min == 0.503
    assert candidate_options.final_answer_selection_value_signal_score_max == 0.506
    assert candidate_options.final_answer_selection_value_signal_competition_ids == (
        "ENG_CHAMPIONSHIP",
    )
    assert candidate_options.final_answer_selection_value_signal_outcomes == ("draw",)
    assert (
        candidate_options.final_answer_selection_value_signal_max_hit_probability_deficit
        == 0.02
    )


def test_selection_value_signal_runtime_replay_disabled_without_flag() -> None:
    report = (
        replay.build_historical_final_answer_selection_value_signal_runtime_replay_report(
            [],
            rule_set=_rule_set(),
        )
    )

    assert report.status == "disabled"
    assert report.runtime_replay_allowed is False
    assert report.holdout_replay_allowed is False
    assert report.checks == []


def test_selection_value_signal_runtime_replay_blocks_harmful_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        _harmful_movement_fake_run,
    )

    report = (
        replay.build_historical_final_answer_selection_value_signal_runtime_replay_report(
            [],
            rule_set=_rule_set(),
            options=replay.HistoricalFinalAnswerSelectionValueSignalRuntimeReplayOptions(
                enable_shadow_replay=True,
                min_final_answer_count=2,
            ),
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_replay_failed"
    assert report.harmful_movement_count == 1
    assert report.final_hit_harm_count_vs_baseline == 1
    assert "harmful_movement_count" in failed_checks
    assert "final_hit_harm_count_vs_baseline" in failed_checks


def test_selection_value_signal_runtime_replay_loader_accepts_proposal_report(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "proposal.json"
    profile_path.write_text(
        """
{
  "proposal_profile_set_json": {
    "proposed_profile_version": "profile-from-proposal",
    "status": "runtime_profile_proposal_ready",
    "runtime_profile_proposal_allowed": true,
    "holdout_candidate_allowed": true,
    "final_answer_selection_value_signal_rules": [
      {
        "rule_id": "rule-from-proposal",
        "proposed_production_enabled": true,
        "holdout_candidate_enabled": true,
        "competition_ids": ["ENG_CHAMPIONSHIP"],
        "outcomes": ["draw"],
        "strength": 0.32,
        "score_min": 0.503,
        "score_max": 0.506,
        "constraints_json": {
          "probability_grid_unchanged": true,
          "movement_conditioned": true
        }
      }
    ]
  }
}
""",
        encoding="utf-8",
    )

    rule_set = replay.load_final_answer_selection_value_signal_runtime_rule_set(
        profile_path
    )

    assert rule_set.profile_version == "profile-from-proposal"
    assert rule_set.runtime_profile_proposal_allowed is True
    assert rule_set.rules[0].rule_id == "rule-from-proposal"
    assert rule_set.rules[0].strength == 0.32


def test_selection_value_signal_runtime_replay_cli_options_loader_and_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay,
        "run_historical_recommendation_backtest_suite",
        _positive_fake_run,
    )
    slice_path = tmp_path / "slice.json"
    profile_path = tmp_path / "profile.json"
    output_path = tmp_path / "runtime_replay.json"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    profile_path.write_text(
        f"{_rule_set(proposed_production_enabled=True).model_dump_json(indent=2)}\n",
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
            "selection-value-rule:test",
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
            "--min-final-answer-count",
            "30",
            "--min-candidate-roi",
            "-0.5",
            "--require-profile-runtime-allowed",
            "--require-proposed-production-enabled",
            "--include-movement-diagnostics",
            "--movement-diagnostics-limit",
            "5",
            "--no-fail-process",
        ]
    )
    options = replay._options_from_args(args)

    assert options.enable_shadow_replay is True
    assert options.rule_ids == ("selection-value-rule:test",)
    assert options.min_candidate_roi == -0.5
    assert options.require_profile_runtime_allowed is True
    assert options.require_proposed_production_enabled is True
    assert options.include_movement_diagnostics is True
    assert options.movement_diagnostics_limit == 5

    replay.main(
        [
            str(slice_path),
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--min-final-answer-count",
            "30",
            "--min-candidate-roi",
            "-0.5",
            "--require-profile-runtime-allowed",
            "--require-proposed-production-enabled",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_replay_passed"
    assert payload["runtime_replay_allowed"] is True
    assert payload["source_rule_profile_version"] == "runtime-profile:test"


def _positive_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    del historical_slices, baseline_optimizer_profile, candidate_optimizer_profile
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    return _fake_suite(
        selection_value_signal=resolved_options.final_answer_selection_value_signal,
    )


def _harmful_movement_fake_run(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    del historical_slices, baseline_optimizer_profile, candidate_optimizer_profile
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    if resolved_options.final_answer_selection_value_signal:
        return _suite_with_comparisons(
            "candidate-suite:harm",
            [_comparison("slice_harm", outcome="draw", actual_hit=False, profit_loss=-1.0)],
            final_hit_count=0,
            profit_loss=-1.0,
            candidate_roi=-0.5,
            affected_leg_count=1,
        )
    return _suite_with_comparisons(
        "baseline-suite:harm",
        [
            _comparison(
                "slice_harm",
                outcome="home_win",
                actual_hit=True,
                profit_loss=1.0,
            )
        ],
        final_hit_count=1,
        profit_loss=1.0,
        candidate_roi=0.5,
    )


def _fake_suite(
    *,
    selection_value_signal: bool,
) -> HistoricalRecommendationBacktestSuiteResult:
    if selection_value_signal:
        return _suite_with_comparisons(
            "candidate-suite:test",
            [_comparison("slice_positive", outcome="draw", actual_hit=True, profit_loss=2.0)],
            final_hit_count=24,
            profit_loss=2.0,
            candidate_roi=0.04,
            affected_leg_count=1,
            brier_score=0.17,
            log_loss=0.45,
            calibration_error=0.08,
        )
    return _suite_with_comparisons(
        "baseline-suite:test",
        [
            _comparison(
                "slice_positive",
                outcome="home_win",
                actual_hit=False,
                profit_loss=-2.0,
            )
        ],
        final_hit_count=23,
        profit_loss=-4.8,
        candidate_roi=-0.08,
        brier_score=0.20,
        log_loss=0.52,
        calibration_error=0.12,
    )


def _suite_with_comparisons(
    suite_key: str,
    comparisons: list[HistoricalRecommendationBacktestComparisonResult],
    *,
    final_hit_count: int,
    profit_loss: float,
    candidate_roi: float,
    affected_leg_count: int = 0,
    brier_score: float = 0.17,
    log_loss: float = 0.45,
    calibration_error: float = 0.08,
) -> HistoricalRecommendationBacktestSuiteResult:
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=suite_key,
        status="unchanged",
        slice_count=30,
        comparison_count=len(comparisons),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
        summary_json={
            "candidate_final_hit_sample_size": 30,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_count / 30,
            "candidate_profit_loss": profit_loss,
            "candidate_roi": candidate_roi,
            "candidate_brier_score": brier_score,
            "candidate_log_loss": log_loss,
            "candidate_mean_calibration_error": calibration_error,
            "candidate_final_answer_selection_value_signal_affected_leg_count": (
                affected_leg_count
            ),
            "candidate_final_answer_selection_value_signal_guard_blocked_option_count": (
                7 if affected_leg_count else 0
            ),
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
        status="changed",
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
        expected_hit_probability=0.50,
        actual_hit=actual_hit,
        brier_score=0.20,
        log_loss=0.50,
        calibration_error=0.10,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"backtest:{slice_id}:{outcome}:{profit_loss}",
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
    proposed_production_enabled: bool = False,
) -> replay.FinalAnswerSelectionValueSignalRuntimeRuleSet:
    return replay.FinalAnswerSelectionValueSignalRuntimeRuleSet(
        profile_version="runtime-profile:test",
        status=(
            "runtime_profile_proposal_ready"
            if proposed_production_enabled
            else "holdout_only"
        ),
        runtime_profile_proposal_allowed=proposed_production_enabled,
        holdout_candidate_allowed=True,
        rules=[
            replay.FinalAnswerSelectionValueSignalRuntimeRule(
                rule_id="selection-value-rule:test",
                proposed_profile_version="runtime-profile:test",
                proposed_production_enabled=proposed_production_enabled,
                holdout_candidate_enabled=True,
                competition_ids=["ENG_CHAMPIONSHIP"],
                outcomes=["draw"],
                probability_min=0.0,
                probability_max=1.0,
                min_decimal_odds=2.5,
                max_decimal_odds=3.3333333333333335,
                score_min=0.503,
                score_max=0.506,
                strength=0.32,
                max_hit_probability_deficit=0.02,
                constraints_json={
                    "probability_grid_unchanged": True,
                    "movement_conditioned": True,
                },
            )
        ],
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="slice-runtime-test",
            name="Selection value runtime replay test slice",
            competition_id="ENG_CHAMPIONSHIP",
            season="2024-2025",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture-runtime-test",
                competition_id="ENG_CHAMPIONSHIP",
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
                ],
            )
        ],
    )
