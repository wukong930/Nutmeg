from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_bucket_search as bucket_search,
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


def test_probability_calibration_runtime_bucket_search_generates_specs_from_diagnostics(
    tmp_path: Path,
) -> None:
    diagnostics_path = tmp_path / "diagnostics.json"
    diagnostics_path.write_text(
        dumps(_diagnostics_payload(), indent=2),
        encoding="utf-8",
    )

    specs = bucket_search._candidate_specs(
        _profile(),
        options=bucket_search.HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions(
            diagnostics_report_path=diagnostics_path,
            blend_weights=(0.05,),
            bucket_scope_modes=("season", "single_bucket"),
            bucket_outcomes=("draw",),
        ),
    )

    assert len(specs) == 3
    assert {spec.scope_mode for spec in specs} == {"season", "single_bucket"}
    assert {spec.target_season_ids for spec in specs} == {("2021-2022",)}
    assert all(spec.target_competition_ids == ("ENG_CHAMPIONSHIP",) for spec in specs)
    assert sum(1 for spec in specs if spec.scope_mode == "single_bucket") == 2
    assert all(spec.source_group_key == "ENG_CHAMPIONSHIP|2021-2022" for spec in specs)


def test_probability_calibration_runtime_bucket_search_accepts_selection_bucket(
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
        dumps(_diagnostics_payload(), indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        bucket_search,
        "build_historical_probability_calibration_profile_runtime_replay_report",
        _fake_replay_report,
    )

    report = (
        bucket_search.build_historical_probability_calibration_profile_runtime_bucket_search_report(
            [_slice()],
            profile_set_path=profile_path,
            options=bucket_search.HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions(
                profile_keys=("profile:test",),
                diagnostics_report_path=diagnostics_path,
                blend_weights=(0.05, 0.10),
                bucket_scope_modes=("season", "single_bucket"),
                bucket_outcomes=("draw",),
            ),
        )
    )

    assert report.status == "generated"
    assert report.candidate_count == 6
    assert report.accepted_count == 1
    assert report.rejected_count == 5
    assert report.best_candidate is not None
    assert report.best_candidate.spec.scope_mode == "single_bucket"
    assert report.best_candidate.spec.blend_weight == 0.10
    assert report.best_candidate.bucket_count == 1
    assert report.best_candidate.final_answer_hit_delta_count == 1
    assert report.best_candidate.brier_score_delta == pytest.approx(-0.01)
    rejected_reasons = {
        reason
        for candidate in report.candidates
        if candidate.decision == "rejected"
        for reason in candidate.decision_reasons
    }
    assert "changed_final_answer_count:below_threshold" in rejected_reasons
    assert "brier_score_delta:above_threshold" in rejected_reasons


def test_probability_calibration_runtime_bucket_search_cli_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    diagnostics_path = tmp_path / "diagnostics.json"
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "bucket_search.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    diagnostics_path.write_text(
        dumps(_diagnostics_payload(), indent=2),
        encoding="utf-8",
    )
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    monkeypatch.setattr(
        bucket_search,
        "build_historical_probability_calibration_profile_runtime_replay_report",
        _fake_replay_report,
    )

    args = bucket_search._parse_args(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--diagnostics-report",
            str(diagnostics_path),
            "--blend-weights",
            "0.10",
            "--bucket-scope-modes",
            "single_bucket",
            "--bucket-outcomes",
            "draw",
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
    options = bucket_search._options_from_args(args)

    assert options.profile_keys == ("profile:test",)
    assert options.blend_weights == (0.10,)
    assert options.bucket_scope_modes == ("single_bucket",)
    assert options.bucket_outcomes == ("draw",)
    assert options.backtest_options.pass_types == ("1x1", "3x1")
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True

    bucket_search.main(
        [
            str(slice_path),
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-keys",
            "profile:test",
            "--diagnostics-report",
            str(diagnostics_path),
            "--blend-weights",
            "0.10",
            "--bucket-scope-modes",
            "single_bucket",
            "--bucket-outcomes",
            "draw",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    assert payload["accepted_count"] == 1
    assert payload["best_candidate"]["spec"]["scope_mode"] == "single_bucket"


def _fake_replay_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    profile_set: replay.ProbabilityCalibrationRuntimeProfileSet,
    options: replay.HistoricalProbabilityCalibrationProfileRuntimeReplayOptions | None = None,
) -> replay.HistoricalProbabilityCalibrationProfileRuntimeReplayReport:
    del historical_slices, options
    profile = profile_set.profiles[0]
    bucket_starts = {bucket.bucket_start for bucket in profile.buckets}
    accepted = (
        len(profile.buckets) == 1
        and 0.30 in bucket_starts
        and profile.blend_weight == 0.10
    )
    no_movement = len(profile.buckets) == 1 and 0.20 in bucket_starts
    changed_count = 0 if no_movement else 1
    brier_delta = -0.01 if accepted else 0.01
    log_loss_delta = -0.02 if accepted else 0.02
    ece_delta = -0.01 if accepted else 0.01
    return replay.HistoricalProbabilityCalibrationProfileRuntimeReplayReport(
        report_key=f"runtime-replay:test:{profile.profile_key}",
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
        changed_final_answer_count=changed_count,
        baseline_final_answer_hit_count=10,
        candidate_final_answer_hit_count=11 if accepted else 10,
        final_answer_hit_delta_count=1 if accepted else 0,
        final_answer_hit_rate_delta=0.05 if accepted else 0.0,
        baseline_roi=0.0,
        candidate_roi=0.10 if accepted else 0.0,
        roi_delta=0.10 if accepted else 0.0,
        profit_loss_delta=4.0 if accepted else 0.0,
        brier_score_delta=brier_delta,
        log_loss_delta=log_loss_delta,
        mean_calibration_error_delta=ece_delta,
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
                bucket_start=0.20,
                bucket_end=0.30,
                calibrated_probability=0.28,
                sample_size=20,
                competition_id="ENG_CHAMPIONSHIP",
                market_type="1x2",
            ),
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.40,
                calibrated_probability=0.45,
                sample_size=20,
                competition_id="ENG_CHAMPIONSHIP",
                market_type="1x2",
            ),
            CandidateProbabilityCalibrationBucket(
                outcome="home_win",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.40,
                calibrated_probability=0.33,
                sample_size=20,
                competition_id="ENG_CHAMPIONSHIP",
                market_type="1x2",
            ),
        ],
    )


def _diagnostics_payload() -> dict[str, object]:
    return {
        "report_key": "diagnostics:test",
        "top_regression_groups": [
            {
                "group_key": "ENG_CHAMPIONSHIP|2021-2022",
                "group_type": "competition_season",
                "competition_id": "ENG_CHAMPIONSHIP",
                "season": "2021-2022",
                "changed_final_answer_count": 1,
                "final_answer_hit_delta_count": 1,
                "profit_loss_delta": 4.0,
                "quality_regression_score": 0.5,
            },
            {
                "group_key": "ENG_CHAMPIONSHIP|2020-2021",
                "group_type": "competition_season",
                "competition_id": "ENG_CHAMPIONSHIP",
                "season": "2020-2021",
                "changed_final_answer_count": 1,
                "final_answer_hit_delta_count": 0,
                "profit_loss_delta": 0.0,
                "quality_regression_score": 0.4,
            },
        ],
    }


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="eng_2021_2022_slice",
            name="Runtime bucket search test slice",
            competition_id="ENG_CHAMPIONSHIP",
            season="2021-2022",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="eng_2021_2022_fixture",
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
