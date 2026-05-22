from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalFinalAnswerLossDiagnosticGroup,
    HistoricalFinalAnswerLossDiagnosticOptions,
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    build_historical_final_answer_loss_diagnostic_report,
)
from nutmeg.recommendations.historical_loss_diagnostics import (
    _historical_slices_from_args,
    _options_from_args,
    _parse_args,
)


def test_historical_loss_diagnostics_stratifies_missed_final_answer_legs() -> None:
    historical_slice = _loss_slice()

    report = build_historical_final_answer_loss_diagnostic_report(
        [historical_slice],
        options=HistoricalFinalAnswerLossDiagnosticOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=4.0,
                min_data_quality_score=80.0,
            ),
            derive_market_context_signals=True,
        ),
    )

    competition_group = _group(report.groups, "competition", "LOSS_TEST")
    odds_group = _group(report.groups, "odds_band", "LOSS_TEST:odds_1_36_1_60")
    miss_reason_group = _group(
        report.groups,
        "miss_reason",
        "LOSS_TEST:favorite_draw_failure",
    )
    correlation_group = _group(
        report.groups,
        "correlation_exposure",
        "LOSS_TEST:correlation_exposure_2",
    )
    fragility_group = _group(
        report.groups,
        "favorite_fragility_band",
        "LOSS_TEST:fragility_0_28_0_44",
    )

    assert report.final_answer_count == 1
    assert report.selected_leg_count == 2
    assert report.missed_leg_count == 1
    assert report.negative_roi_competitions == ["LOSS_TEST"]
    assert competition_group.final_answer_hit_count == 0
    assert competition_group.roi == -1.0
    assert odds_group.selected_leg_count == 2
    assert odds_group.missed_leg_count == 1
    assert miss_reason_group.missed_leg_count == 1
    assert correlation_group.max_correlation_exposure == 2
    assert fragility_group.selected_leg_count == 2
    assert report.top_loss_groups[0].competition_id == "LOSS_TEST"
    assert report.top_missed_leg_groups[0].missed_leg_count >= 1


def test_historical_loss_diagnostics_can_filter_to_negative_roi_groups() -> None:
    loss_slice = _loss_slice()
    positive_slice = _loss_slice(
        slice_id="positive_slice",
        competition_id="POSITIVE_TEST",
        actual_outcomes=("home_win", "home_win"),
    )

    report = build_historical_final_answer_loss_diagnostic_report(
        [loss_slice, positive_slice],
        options=HistoricalFinalAnswerLossDiagnosticOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=4.0,
                min_data_quality_score=80.0,
            ),
            include_positive_roi_competitions=False,
            derive_market_context_signals=True,
        ),
    )

    assert report.negative_roi_competitions == ["LOSS_TEST"]
    assert {group.competition_id for group in report.groups} == {"LOSS_TEST"}


def test_historical_loss_diagnostics_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/loss-diagnostics.json",
            "--pass-types",
            "2x1,5x1",
            "--modes",
            "single",
            "--strategy",
            "upset_protection",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.24",
            "--min-data-quality-score",
            "72",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.45",
            "--candidate-fixture-limit",
            "40",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "5",
            "--derive-market-context-signals",
            "--short-price-negative-edge-guardrail",
            "--short-price-negative-edge-max-decimal-odds",
            "1.42",
            "--short-price-negative-edge-min-probability",
            "0.72",
            "--short-price-negative-edge-max-model-edge",
            "-0.02",
            "--short-price-negative-edge-soft-penalty",
            "--short-price-negative-edge-soft-penalty-strength",
            "0.8",
            "--short-price-negative-edge-soft-penalty-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--focus-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--negative-roi-only",
            "--min-group-sample-size",
            "2",
            "--fragile-favorite-threshold",
            "0.32",
            "--short-price-odds-threshold",
            "1.55",
            "--high-probability-threshold",
            "0.68",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/loss-diagnostics.json")
    assert options.backtest_options.pass_types == ("2x1", "5x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "upset_protection"
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 18
    assert options.backtest_options.min_probability == 0.24
    assert options.backtest_options.min_data_quality_score == 72
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.45
    assert options.backtest_options.candidate_fixture_limit == 40
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 5
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.short_price_negative_edge_guardrail is True
    assert options.backtest_options.short_price_negative_edge_max_decimal_odds == 1.42
    assert options.backtest_options.short_price_negative_edge_min_probability == 0.72
    assert options.backtest_options.short_price_negative_edge_max_model_edge == -0.02
    assert options.backtest_options.short_price_negative_edge_soft_penalty is True
    assert options.backtest_options.short_price_negative_edge_soft_penalty_strength == 0.8
    assert options.backtest_options.short_price_negative_edge_soft_penalty_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert options.derive_market_context_signals is True
    assert options.focus_competition_ids == ("ESP_LA_LIGA", "JPN_J1")
    assert options.include_positive_roi_competitions is False
    assert options.min_group_sample_size == 2
    assert options.fragile_favorite_threshold == 0.32
    assert options.short_price_odds_threshold == 1.55
    assert options.high_probability_threshold == 0.68


def test_historical_loss_diagnostics_accepts_multiple_suite_manifests(
    tmp_path: Path,
) -> None:
    first_slice_path = tmp_path / "first_slice.json"
    second_slice_path = tmp_path / "second_slice.json"
    first_slice_path.write_text(
        _loss_slice(slice_id="first_slice", competition_id="FIRST_TEST").model_dump_json(
            indent=2
        ),
        encoding="utf-8",
    )
    second_slice_path.write_text(
        _loss_slice(
            slice_id="second_slice",
            competition_id="SECOND_TEST",
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    first_manifest_path = tmp_path / "first_manifest.json"
    second_manifest_path = tmp_path / "second_manifest.json"
    first_manifest_path.write_text(
        _manifest_json(
            suite_id="first_suite",
            slice_path=first_slice_path.name,
        ),
        encoding="utf-8",
    )
    second_manifest_path.write_text(
        _manifest_json(
            suite_id="second_suite",
            slice_path=second_slice_path.name,
        ),
        encoding="utf-8",
    )

    loaded = _historical_slices_from_args(
        _parse_args(
            [
                "--suite-manifest",
                str(first_manifest_path),
                "--suite-manifest",
                str(second_manifest_path),
            ]
        )
    )

    assert [historical_slice.metadata.slice_id for historical_slice in loaded.slices] == [
        "first_slice",
        "second_slice",
    ]
    assert len(loaded.manifest_results) == 2
    assert loaded.manifest_result is None
    assert [bundle.manifest.suite_id for bundle in loaded.manifest_results] == [
        "first_suite",
        "second_suite",
    ]


def _group(
    groups: list[HistoricalFinalAnswerLossDiagnosticGroup],
    group_type: str,
    group_key: str,
) -> HistoricalFinalAnswerLossDiagnosticGroup:
    for group in groups:
        if group.group_type == group_type and group.group_key == group_key:
            return group
    raise AssertionError(f"group not found: {group_type} {group_key}")


def _loss_slice(
    *,
    slice_id: str = "loss_slice",
    competition_id: str = "LOSS_TEST",
    actual_outcomes: tuple[str, str] = ("home_win", "draw"),
) -> HistoricalRecommendationSlice:
    as_of_time = datetime(2026, 1, 1, 8, tzinfo=UTC)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id=competition_id,
            season="2025-2026",
            result_source="deterministic_test_fixture",
            odds_source="deterministic_test_fixture",
            prediction_source="deterministic_test_fixture",
        ),
        as_of_time_utc=as_of_time,
        fixtures=[
            _fixture(
                index=index,
                competition_id=competition_id,
                prediction_time=as_of_time,
                actual_outcome=actual_outcome,
            )
            for index, actual_outcome in enumerate(actual_outcomes)
        ],
    )


def _manifest_json(*, suite_id: str, slice_path: str) -> str:
    return (
        "{"
        f'"suite_id":"{suite_id}",'
        f'"name":"{suite_id}",'
        f'"slices":[{{"slice_path":"{slice_path}"}}]'
        "}"
    )


def _fixture(
    *,
    index: int,
    competition_id: str,
    prediction_time: datetime,
    actual_outcome: str,
) -> HistoricalFixture:
    actual_home_goals = 2 if actual_outcome == "home_win" else 1
    actual_away_goals = 0 if actual_outcome == "home_win" else 1
    return HistoricalFixture(
        fixture_id=f"{competition_id.lower()}_{index}",
        competition_id=competition_id,
        kickoff_time_utc=prediction_time + timedelta(days=index + 1),
        home_team_name="Repeat Favorite",
        away_team_name=f"Away {index}",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=prediction_time,
        model_version="test-model-v1",
        feature_version="test-features-v1",
        calibration_version="test-calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.70 - index * 0.01,
                decimal_odds=1.45,
                market_probability=1 / 1.45,
                model_edge=0.08,
                data_quality_score=95.0,
                model_confidence_score=0.90,
                calibration_score=0.90,
                odds_stability_score=0.90,
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.20,
                decimal_odds=4.00,
                market_probability=1 / 4.00,
                model_edge=-0.05,
                data_quality_score=95.0,
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.10 + index * 0.01,
                decimal_odds=7.00,
                market_probability=1 / 7.00,
                model_edge=-0.04,
                data_quality_score=95.0,
            ),
        ],
    )
