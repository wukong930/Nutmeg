from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads

import pytest

from nutmeg.recommendations import historical_final_answer_segment_penalty_grid as grid
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
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestLoadResult,
)


def test_segment_penalty_grid_accepts_accuracy_first_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[HistoricalRecommendationBacktestOptions] = []

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        calls.append(resolved_options)
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    report = grid.build_historical_final_answer_segment_penalty_grid_report(
        [_slice()],
        options=grid.HistoricalFinalAnswerSegmentPenaltyGridOptions(
            pass_type_groups=(("3x1",),),
            mode_groups=(("single",),),
            competition_groups=(("ESP_LA_LIGA", "GER_BUNDESLIGA"),),
            season_groups=(("2023-2024", "2024-2025"),),
            min_competition_season_index_values=(4,),
            min_hit_probability_values=(None,),
            max_average_leg_decimal_odds_values=(1.30,),
            strength_values=(0.08,),
        ),
    )

    assert report.accepted_count == 1
    assert report.best_candidate is not None
    assert report.best_candidate.status == "accepted"
    assert report.best_candidate.penalty_option_count == 3
    assert report.best_candidate.deltas_json["final_hit_count_delta"] == 1
    assert report.best_candidate.deltas_json["roi_delta"] == pytest.approx(0.15)
    assert calls[0].final_answer_segment_penalty is False
    assert calls[1].final_answer_segment_penalty is True
    assert calls[1].final_answer_segment_pass_types == ("3x1",)
    assert calls[1].final_answer_segment_modes == ("single",)
    assert calls[1].final_answer_segment_competition_ids == (
        "ESP_LA_LIGA",
        "GER_BUNDESLIGA",
    )
    assert calls[1].final_answer_segment_season_ids == ("2023-2024", "2024-2025")
    assert calls[1].final_answer_segment_min_competition_season_index == 4
    assert calls[1].final_answer_segment_penalty_strength == 0.08
    assert calls[1].final_answer_segment_max_average_leg_decimal_odds == 1.30


def test_segment_penalty_grid_rejects_candidate_below_absolute_roi_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    report = grid.build_historical_final_answer_segment_penalty_grid_report(
        [_slice()],
        options=grid.HistoricalFinalAnswerSegmentPenaltyGridOptions(
            pass_type_groups=(("3x1",),),
            mode_groups=(("single",),),
            competition_groups=(("ESP_LA_LIGA", "GER_BUNDESLIGA"),),
            strength_values=(0.08,),
            min_candidate_roi=0.0,
        ),
    )

    assert report.accepted_count == 0
    assert report.candidates[0].status == "rejected"
    assert report.candidates[0].deltas_json["candidate_roi"] == pytest.approx(-0.05)
    assert report.candidates[0].deltas_json["roi_delta"] == pytest.approx(0.15)
    assert (
        "segment_penalty:candidate_roi_below_floor"
        in report.candidates[0].reason_codes
    )
    assert (
        report.summary_json["grid"]["gate_thresholds"]["min_candidate_roi"] == 0.0
    )


def test_segment_penalty_grid_rejects_hit_regression_even_with_roi_gain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=5,
                final_hit_rate=5 / 6,
                roi=-0.12,
                profit_loss=-1.44,
                brier_score=0.20,
                log_loss=0.55,
                mean_calibration_error=0.30,
            )
        return _suite(
            "candidate",
            final_hit_count=4,
            final_hit_rate=4 / 6,
            roi=0.10,
            profit_loss=1.20,
            brier_score=0.23,
            log_loss=0.61,
            mean_calibration_error=0.38,
            penalty_option_count=4,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    report = grid.build_historical_final_answer_segment_penalty_grid_report(
        [_slice()],
        options=grid.HistoricalFinalAnswerSegmentPenaltyGridOptions(
            pass_type_groups=(("3x1",),),
            mode_groups=(("single",),),
            competition_groups=(("ESP_LA_LIGA", "GER_BUNDESLIGA"),),
            strength_values=(0.08,),
        ),
    )

    assert report.accepted_count == 0
    assert report.candidates[0].status == "rejected"
    assert "segment_penalty:final_hit_count_regressed" in report.candidates[0].reason_codes
    assert report.candidates[0].deltas_json["roi_delta"] == pytest.approx(0.22)


def test_segment_penalty_grid_rejects_local_original_harm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite_with_comparisons(
                "baseline",
                [
                    _comparison("slice_a", baseline_hit=True, candidate_hit=True),
                    _comparison(
                        "slice_b",
                        baseline_hit=False,
                        candidate_hit=False,
                        baseline_profit_loss=-2.0,
                        candidate_profit_loss=-2.0,
                    ),
                ],
                final_hit_count=1,
                profit_loss=0.0,
            )
        return _suite_with_comparisons(
            "candidate",
            [
                _comparison(
                    "slice_a",
                    baseline_hit=True,
                    candidate_hit=False,
                    baseline_profit_loss=2.0,
                    candidate_profit_loss=-2.0,
                ),
                _comparison(
                    "slice_b",
                    baseline_hit=False,
                    candidate_hit=True,
                    baseline_profit_loss=-2.0,
                    candidate_profit_loss=2.0,
                ),
            ],
            final_hit_count=1,
            profit_loss=0.0,
            penalty_option_count=2,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    strict_report = grid.build_historical_final_answer_segment_penalty_grid_report(
        [_slice()],
        options=grid.HistoricalFinalAnswerSegmentPenaltyGridOptions(
            pass_type_groups=(("3x1",),),
            mode_groups=(("single",),),
            competition_groups=(("GER_BUNDESLIGA",),),
            strength_values=(0.08,),
            require_objective_improvement=False,
        ),
    )
    relaxed_report = grid.build_historical_final_answer_segment_penalty_grid_report(
        [_slice()],
        options=grid.HistoricalFinalAnswerSegmentPenaltyGridOptions(
            pass_type_groups=(("3x1",),),
            mode_groups=(("single",),),
            competition_groups=(("GER_BUNDESLIGA",),),
            strength_values=(0.08,),
            require_objective_improvement=False,
            max_final_hit_harm_count_vs_baseline=1,
            max_profit_loss_harm_count_vs_baseline=1,
        ),
    )

    strict_candidate = strict_report.candidates[0]
    assert strict_candidate.status == "rejected"
    assert strict_candidate.final_answer_changed_count_vs_baseline == 2
    assert strict_candidate.final_hit_harm_count_vs_baseline == 1
    assert strict_candidate.profit_loss_harm_count_vs_baseline == 1
    assert (
        strict_candidate.deltas_json["final_answer_changed_count_vs_baseline"]
        == 2
    )
    assert (
        "segment_penalty:final_hit_harm_count_above_threshold"
        in strict_candidate.reason_codes
    )
    assert (
        "segment_penalty:profit_loss_harm_count_above_threshold"
        in strict_candidate.reason_codes
    )
    assert relaxed_report.candidates[0].status == "accepted"


def test_segment_penalty_grid_cli_options_loader_and_main(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "segment_penalty_grid.json"
    progress_path = tmp_path / "segment_penalty_grid.jsonl"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        assert resolved_options.final_answer_segment_min_hit_probability is None
        assert resolved_options.final_answer_segment_max_average_leg_decimal_odds is None
        assert resolved_options.final_answer_segment_season_ids == (
            "2023-2024",
            "2024-2025",
        )
        assert resolved_options.final_answer_segment_min_competition_season_index == 4
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    grid.main(
        [
            str(slice_path),
            "--output-path",
            str(output_path),
            "--pass-type-group",
            "3x1",
            "--mode-group",
            "single",
            "--competition-group",
            "ESP_LA_LIGA,GER_BUNDESLIGA",
            "--season-group",
            "2023-2024,2024-2025",
            "--min-competition-season-index-values",
            "4",
            "--min-hit-probability-values",
            "none,0.85",
            "--max-average-leg-decimal-odds-values",
            "none,1.30",
            "--strength-values",
            "0.08",
            "--min-candidate-roi",
            "-0.10",
            "--max-final-hit-harm-count-vs-baseline",
            "2",
            "--max-profit-loss-harm-count-vs-baseline",
            "3",
            "--progress-jsonl-path",
            str(progress_path),
            "--candidate-limit",
            "1",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    printed = loads(capsys.readouterr().out)
    assert payload["accepted_count"] == 1
    assert printed["report_key"] == payload["report_key"]
    assert payload["total_grid_candidate_count"] == 4
    assert payload["candidate_count"] == 1
    assert payload["best_candidate"]["pass_types"] == ["3x1"]
    assert payload["best_candidate"]["competition_ids"] == [
        "ESP_LA_LIGA",
        "GER_BUNDESLIGA",
    ]
    assert payload["best_candidate"]["season_ids"] == ["2023-2024", "2024-2025"]
    assert payload["best_candidate"]["min_competition_season_index"] == 4
    assert (
        payload["summary_json"]["grid"]["gate_thresholds"][
            "min_candidate_roi"
        ]
        == -0.10
    )
    assert (
        payload["summary_json"]["grid"]["gate_thresholds"][
            "max_final_hit_harm_count_vs_baseline"
        ]
        == 2
    )
    assert (
        payload["summary_json"]["grid"]["gate_thresholds"][
            "max_profit_loss_harm_count_vs_baseline"
        ]
        == 3
    )
    progress_events = [
        loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
    ]
    assert payload["progress_event_count"] == len(progress_events)
    assert progress_events[0]["event"] == "grid_started"
    assert progress_events[-1]["event"] == "grid_completed"


def test_segment_penalty_grid_cli_accepts_multiple_suite_manifests(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "segment_penalty_grid.json"
    manifest_a = tmp_path / "suite_a.json"
    manifest_b = tmp_path / "suite_b.json"
    manifest_a.write_text("{}", encoding="utf-8")
    manifest_b.write_text("{}", encoding="utf-8")
    loaded_paths: list[str] = []

    def fake_load_bundle(path):
        loaded_paths.append(str(path))
        suite_id = "suite_a" if path == manifest_a else "suite_b"
        return HistoricalRecommendationSuiteManifestLoadResult(
            manifest_path=path,
            manifest=HistoricalRecommendationSuiteManifest(
                suite_id=suite_id,
                name=suite_id,
                slices=[{"slice_path": f"{suite_id}.json"}],
            ),
            resolved_slice_paths=[tmp_path / f"{suite_id}.json"],
            slices=[_slice(slice_id=f"{suite_id}_slice")],
        )

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        assert [historical_slice.metadata.slice_id for historical_slice in historical_slices] == [
            "suite_a_slice",
            "suite_b_slice",
        ]
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(
        grid,
        "load_historical_recommendation_suite_manifest_bundle",
        fake_load_bundle,
    )
    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    grid.main(
        [
            "--suite-manifest",
            str(manifest_a),
            "--suite-manifest",
            str(manifest_b),
            "--output-path",
            str(output_path),
            "--pass-type-group",
            "1x1",
            "--mode-group",
            "single",
            "--competition-group",
            "ENG_CHAMPIONSHIP",
            "--min-hit-probability-values",
            "0.40",
            "--max-hit-probability-values",
            "0.55",
            "--min-odds-product-values",
            "1.60",
            "--max-odds-product-values",
            "2.00",
            "--strength-values",
            "0.02",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    printed = loads(capsys.readouterr().out)
    assert loaded_paths == [str(manifest_a), str(manifest_b)]
    assert printed["report_key"] == payload["report_key"]
    assert payload["summary_json"]["suite_manifests"][0]["suite_id"] == "suite_a"
    assert payload["summary_json"]["suite_manifests"][1]["suite_id"] == "suite_b"


def test_segment_penalty_grid_cli_reuses_candidate_checkpoint(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slice_path = tmp_path / "slice.json"
    first_output_path = tmp_path / "first_grid.json"
    second_output_path = tmp_path / "second_grid.json"
    checkpoint_path = tmp_path / "segment_penalty_candidates.jsonl"
    progress_path = tmp_path / "second_grid_progress.jsonl"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    candidate_run_count = 0

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        nonlocal candidate_run_count
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        candidate_run_count += 1
        if candidate_run_count > 1:
            raise AssertionError("checkpoint candidate should have been reused")
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    common_args = [
        str(slice_path),
        "--pass-type-group",
        "1x1",
        "--mode-group",
        "single",
        "--competition-group",
        "ENG_CHAMPIONSHIP",
        "--min-hit-probability-values",
        "0.40",
        "--max-hit-probability-values",
        "0.55",
        "--min-odds-product-values",
        "1.60",
        "--max-odds-product-values",
        "2.00",
        "--strength-values",
        "0.02",
        "--candidate-checkpoint-jsonl-path",
        str(checkpoint_path),
    ]

    grid.main([*common_args, "--output-path", str(first_output_path)])
    capsys.readouterr()
    assert candidate_run_count == 1
    assert len(checkpoint_path.read_text(encoding="utf-8").splitlines()) == 1

    grid.main(
        [
            *common_args,
            "--output-path",
            str(second_output_path),
            "--progress-jsonl-path",
            str(progress_path),
        ]
    )

    payload = loads(second_output_path.read_text(encoding="utf-8"))
    printed = loads(capsys.readouterr().out)
    progress_events = [
        loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
    ]
    assert printed["report_key"] == payload["report_key"]
    assert candidate_run_count == 1
    assert payload["candidate_count"] == 1
    assert payload["reused_candidate_count"] == 1
    assert payload["evaluated_candidate_count"] == 0
    assert payload["summary_json"]["cached_candidate_count"] == 1
    assert payload["summary_json"]["reused_candidate_count"] == 1
    assert payload["summary_json"]["evaluated_candidate_count"] == 0
    assert progress_events[3]["event"] == "candidate_reused"
    assert len(checkpoint_path.read_text(encoding="utf-8").splitlines()) == 1


def test_segment_penalty_grid_cli_reuses_baseline_cache(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slice_path = tmp_path / "slice.json"
    first_output_path = tmp_path / "first_grid.json"
    second_output_path = tmp_path / "second_grid.json"
    progress_path = tmp_path / "second_grid_progress.jsonl"
    cache_dir = tmp_path / "baseline-cache"
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    baseline_run_count = 0
    candidate_run_count = 0

    def fake_run(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
        baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic",
        candidate_optimizer_profile: HistoricalOptimizerProfile = "solver",
    ) -> HistoricalRecommendationBacktestSuiteResult:
        nonlocal baseline_run_count, candidate_run_count
        assert historical_slices
        resolved_options = options or HistoricalRecommendationBacktestOptions()
        if not resolved_options.final_answer_segment_penalty:
            baseline_run_count += 1
            if baseline_run_count > 1:
                raise AssertionError("baseline suite should have been cached")
            return _suite(
                "baseline",
                final_hit_count=4,
                final_hit_rate=4 / 6,
                roi=-0.20,
                profit_loss=-2.40,
                brier_score=0.24,
                log_loss=0.62,
                mean_calibration_error=0.36,
            )
        candidate_run_count += 1
        return _suite(
            "candidate",
            final_hit_count=5,
            final_hit_rate=5 / 6,
            roi=-0.05,
            profit_loss=-0.60,
            brier_score=0.18,
            log_loss=0.51,
            mean_calibration_error=0.24,
            penalty_option_count=3,
            final_answer_changed_count=2,
        )

    monkeypatch.setattr(grid, "run_historical_recommendation_backtest_suite", fake_run)

    common_args = [
        str(slice_path),
        "--pass-type-group",
        "1x1",
        "--mode-group",
        "single",
        "--competition-group",
        "ENG_CHAMPIONSHIP",
        "--min-hit-probability-values",
        "0.40",
        "--max-hit-probability-values",
        "0.55",
        "--min-odds-product-values",
        "1.60",
        "--max-odds-product-values",
        "2.00",
        "--strength-values",
        "0.02",
        "--baseline-cache-dir",
        str(cache_dir),
    ]

    grid.main([*common_args, "--output-path", str(first_output_path)])
    first_payload = loads(first_output_path.read_text(encoding="utf-8"))
    capsys.readouterr()
    assert baseline_run_count == 1
    assert candidate_run_count == 1
    assert first_payload["baseline_cache_status"] == "miss"
    assert first_payload["baseline_cache_written"] is True
    assert len(list(cache_dir.glob("baseline-*.json"))) == 1

    grid.main(
        [
            *common_args,
            "--output-path",
            str(second_output_path),
            "--progress-jsonl-path",
            str(progress_path),
        ]
    )

    second_payload = loads(second_output_path.read_text(encoding="utf-8"))
    printed = loads(capsys.readouterr().out)
    progress_events = [
        loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
    ]
    assert printed["report_key"] == second_payload["report_key"]
    assert baseline_run_count == 1
    assert candidate_run_count == 2
    assert second_payload["baseline_cache_status"] == "hit"
    assert second_payload["baseline_cache_written"] is False
    assert second_payload["summary_json"]["baseline_cache_status"] == "hit"
    assert progress_events[2]["event"] == "baseline_completed"
    assert progress_events[2]["cache_status"] == "hit"


def _suite(
    suite_key: str,
    *,
    final_hit_count: int,
    final_hit_rate: float,
    roi: float,
    profit_loss: float,
    brier_score: float,
    log_loss: float,
    mean_calibration_error: float,
    penalty_option_count: int = 0,
    final_answer_changed_count: int = 0,
) -> HistoricalRecommendationBacktestSuiteResult:
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=suite_key,
        status="unchanged",
        slice_count=1,
        comparison_count=1,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        summary_json={
            "candidate_final_hit_sample_size": 6,
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_rate,
            "candidate_roi": roi,
            "candidate_profit_loss": profit_loss,
            "candidate_brier_score": brier_score,
            "candidate_log_loss": log_loss,
            "candidate_mean_calibration_error": mean_calibration_error,
            "candidate_final_answer_segment_penalty_option_count": (
                penalty_option_count
            ),
            "final_answer_changed_count": final_answer_changed_count,
        },
    )


def _suite_with_comparisons(
    suite_key: str,
    comparisons: list[HistoricalRecommendationBacktestComparisonResult],
    *,
    final_hit_count: int,
    profit_loss: float,
    penalty_option_count: int = 0,
    final_answer_changed_count: int = 0,
) -> HistoricalRecommendationBacktestSuiteResult:
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=suite_key,
        status="unchanged",
        slice_count=len(comparisons),
        comparison_count=len(comparisons),
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        comparisons=comparisons,
        summary_json={
            "candidate_final_hit_sample_size": len(comparisons),
            "candidate_final_hit_count": final_hit_count,
            "candidate_final_hit_rate": final_hit_count / len(comparisons),
            "candidate_roi": 0.0,
            "candidate_profit_loss": profit_loss,
            "candidate_brier_score": 0.20,
            "candidate_log_loss": 0.55,
            "candidate_mean_calibration_error": 0.30,
            "candidate_final_answer_segment_penalty_option_count": (
                penalty_option_count
            ),
            "final_answer_changed_count": final_answer_changed_count,
        },
    )


def _comparison(
    slice_id: str,
    *,
    baseline_hit: bool,
    candidate_hit: bool,
    baseline_profit_loss: float | None = None,
    candidate_profit_loss: float | None = None,
) -> HistoricalRecommendationBacktestComparisonResult:
    baseline_result = _backtest_result(
        slice_id,
        actual_hit=baseline_hit,
        profit_loss=(
            baseline_profit_loss
            if baseline_profit_loss is not None
            else (2.0 if baseline_hit else -2.0)
        ),
    )
    candidate_result = _backtest_result(
        slice_id,
        actual_hit=candidate_hit,
        profit_loss=(
            candidate_profit_loss
            if candidate_profit_loss is not None
            else (2.0 if candidate_hit else -2.0)
        ),
    )
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{slice_id}",
        slice_id=slice_id,
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        status="unchanged",
        baseline=baseline_result,
        candidate=candidate_result,
    )


def _backtest_result(
    slice_id: str,
    *,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalRecommendationBacktestResult:
    fixture_id = f"{slice_id}_{'hit' if actual_hit else 'miss'}_fixture"
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
        backtest_key=f"backtest:{slice_id}:{actual_hit}",
        slice_id=slice_id,
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
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
        mean_calibration_error=0.30,
        brier_score=0.20,
        log_loss=0.55,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _slice(slice_id: str = "segment_penalty_grid_test_slice") -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Segment penalty grid test slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_a",
                competition_id="TEST",
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
                    )
                ],
            )
        ],
    )
