from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_refinement_search as search,
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
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_probability_calibration_runtime_refinement_search_accepts_movement_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    diagnostics_path = tmp_path / "diagnostics.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    diagnostics_path.write_text(
        dumps(
            {
                "top_regression_groups": [
                    {
                        "group_type": "competition_season",
                        "competition_id": "ENG_CHAMPIONSHIP",
                        "season": "2021-2022",
                    },
                    {
                        "group_type": "competition_season",
                        "competition_id": "ENG_CHAMPIONSHIP",
                        "season": "2020-2021",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        search,
        "build_historical_probability_calibration_profile_runtime_replay_report",
        _fake_replay_report,
    )

    report = (
        search.build_historical_probability_calibration_profile_runtime_refinement_search_report(
            _slices(),
            profile_set_path=profile_path,
            options=(
                search.HistoricalProbabilityCalibrationProfileRuntimeRefinementSearchOptions(
                    profile_keys=("profile:test",),
                    diagnostics_report_path=diagnostics_path,
                    max_diagnostic_guard_count=2,
                )
            ),
        )
    )

    assert report.status == "generated"
    assert report.candidate_count == 2
    assert report.accepted_count == 1
    assert report.rejected_count == 1
    assert report.best_candidate is not None
    assert report.best_candidate.decision == "accepted"
    assert report.best_candidate.spec.min_competition_season_index_by_competition_id == {
        "ENG_CHAMPIONSHIP": 2
    }
    assert report.best_candidate.changed_final_answer_count == 1
    assert report.best_candidate.brier_score_delta == pytest.approx(-0.01)
    rejected = next(
        candidate for candidate in report.candidates if candidate.decision == "rejected"
    )
    assert "changed_final_answer_count:below_threshold" in rejected.decision_reasons


def test_probability_calibration_runtime_refinement_search_cli_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "search.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    slice_path.write_text(f"{_slice('2022-2023').model_dump_json(indent=2)}\n")
    monkeypatch.setattr(
        search,
        "build_historical_probability_calibration_profile_runtime_replay_report",
        _fake_replay_report,
    )

    args = search._parse_args(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--min-competition-season-index-by-competition-candidate",
            "ENG_CHAMPIONSHIP:2",
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
            "--no-fail-process",
        ]
    )
    options = search._options_from_args(args)

    assert options.profile_keys == ("profile:test",)
    assert options.backtest_options.pass_types == ("1x1", "3x1")
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.candidate_specs[0].min_competition_season_index_by_competition_id == {
        "ENG_CHAMPIONSHIP": 2
    }

    search.main(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--min-competition-season-index-by-competition-candidate",
            "ENG_CHAMPIONSHIP:2",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    assert payload["accepted_count"] == 1
    assert payload["best_candidate"]["decision"] == "accepted"


def _fake_replay_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    profile_set: replay.ProbabilityCalibrationRuntimeProfileSet,
    options: replay.HistoricalProbabilityCalibrationProfileRuntimeReplayOptions | None = None,
) -> replay.HistoricalProbabilityCalibrationProfileRuntimeReplayReport:
    del historical_slices, options
    profile = profile_set.profiles[0]
    min_index = profile.min_competition_season_index_by_competition_id.get(
        "ENG_CHAMPIONSHIP"
    )
    accepted = min_index == 2
    return replay.HistoricalProbabilityCalibrationProfileRuntimeReplayReport(
        report_key=f"runtime-replay:test:{min_index}",
        status="runtime_replay_passed" if accepted else "shadow_replay_failed",
        runtime_replay_allowed=accepted,
        holdout_replay_allowed=accepted,
        source_profile_version=profile_set.profile_version,
        profile_count=1,
        selected_profile_count=1,
        selected_profile_key=profile.profile_key,
        adjusted_fixture_count=10,
        adjusted_candidate_count=30,
        final_answer_count=20,
        changed_final_answer_count=1 if accepted else 0,
        baseline_final_answer_hit_count=10,
        candidate_final_answer_hit_count=11 if accepted else 10,
        final_answer_hit_delta_count=1 if accepted else 0,
        final_answer_hit_rate_delta=0.05 if accepted else 0.0,
        baseline_roi=0.0,
        candidate_roi=0.10 if accepted else 0.0,
        roi_delta=0.10 if accepted else 0.0,
        profit_loss_delta=4.0 if accepted else 0.0,
        brier_score_delta=-0.01 if accepted else 0.01,
        log_loss_delta=-0.02 if accepted else 0.02,
        mean_calibration_error_delta=-0.01 if accepted else 0.01,
        checks=[],
        profile_set_json=profile_set.model_dump(mode="json"),
        selected_profile_json=profile.model_dump(mode="json"),
        summary_json={"accepted": accepted},
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
        blend_weight=0.10,
        target_competition_ids=("ENG_CHAMPIONSHIP",),
        target_market_types=("1x2",),
        target_outcomes=("draw",),
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
                competition_id="ENG_CHAMPIONSHIP",
                market_type="1x2",
            )
        ],
    )


def _slices() -> list[HistoricalRecommendationSlice]:
    return [_slice("2020-2021"), _slice("2021-2022"), _slice("2022-2023")]


def _slice(season: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"eng_{season.replace('-', '_')}_slice",
            name="Runtime refinement search test slice",
            competition_id="ENG_CHAMPIONSHIP",
            season=season,
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"eng_{season.replace('-', '_')}_fixture",
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
