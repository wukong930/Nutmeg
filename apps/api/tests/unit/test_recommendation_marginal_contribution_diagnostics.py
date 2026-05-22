from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditOptions,
    _historical_slices_from_args,
    _options_from_args,
    _parse_args,
    build_historical_candidate_marginal_audit_report,
)


def test_marginal_audit_detects_actual_replacement_opportunity() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "selected_safe",
                probability=0.90,
                decimal_odds=1.15,
                model_edge=0.02,
                actual_home_goals=2,
                actual_away_goals=0,
            ),
            _fixture(
                "selected_miss",
                probability=0.86,
                decimal_odds=1.18,
                model_edge=0.01,
                actual_home_goals=1,
                actual_away_goals=1,
            ),
            _fixture(
                "replacement_hit",
                probability=0.68,
                decimal_odds=1.55,
                model_edge=0.03,
                actual_home_goals=1,
                actual_away_goals=0,
            ),
        ],
    )

    report = build_historical_candidate_marginal_audit_report(
        [historical_slice],
        options=HistoricalCandidateMarginalAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                optimizer_profile="heuristic",
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            max_replacement_candidates_per_leg=3,
        ),
    )

    assert report.final_answer_count == 1
    assert report.selected_leg_count == 2
    assert report.missed_leg_count == 1
    assert report.actual_replacement_opportunity_count == 1
    losing_item = next(
        item for item in report.items if item.selected_fixture_id == "selected_miss"
    )
    assert losing_item.leg_actual_hit is False
    assert losing_item.actual_best_replacement is not None
    assert losing_item.actual_best_replacement.replacement_fixture_id == "replacement_hit"
    assert losing_item.actual_best_replacement.profit_loss_delta > 0
    assert report.top_actual_replacement_opportunities[0].item_key == losing_item.item_key


def test_marginal_audit_can_filter_competitions() -> None:
    report = build_historical_candidate_marginal_audit_report(
        [
            HistoricalRecommendationSlice(
                metadata=_metadata(competition_id="TEST"),
                as_of_time_utc=_dt(2024, 6, 29, 12),
                fixtures=[
                    _fixture(
                        "fixture_a",
                        probability=0.90,
                        decimal_odds=1.15,
                        model_edge=0.02,
                        actual_home_goals=2,
                        actual_away_goals=0,
                    )
                ],
            )
        ],
        options=HistoricalCandidateMarginalAuditOptions(
            focus_competition_ids=("OTHER",),
        ),
    )

    assert report.slice_count == 0
    assert report.final_answer_count == 0
    assert report.items == []


def test_marginal_audit_can_focus_loss_driver_selected_legs() -> None:
    historical_slice = HistoricalRecommendationSlice(
        metadata=_metadata(),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "selected_safe",
                probability=0.90,
                decimal_odds=1.15,
                model_edge=0.02,
                actual_home_goals=2,
                actual_away_goals=0,
            ),
            _fixture(
                "targeted_miss",
                probability=0.86,
                decimal_odds=1.18,
                model_edge=0.01,
                actual_home_goals=1,
                actual_away_goals=1,
            ),
            _fixture(
                "replacement_hit",
                probability=0.68,
                decimal_odds=1.55,
                model_edge=0.03,
                actual_home_goals=1,
                actual_away_goals=0,
            ),
        ],
    )

    report = build_historical_candidate_marginal_audit_report(
        [historical_slice],
        options=HistoricalCandidateMarginalAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                optimizer_profile="heuristic",
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            target_probability_min=0.80,
            target_probability_max=0.90,
            target_max_decimal_odds=1.19,
            target_max_model_edge=0.015,
            missed_legs_only=True,
        ),
    )

    assert report.summary_json["examined_selected_leg_count"] == 2
    assert report.selected_leg_count == 1
    assert report.missed_leg_count == 1
    assert report.items[0].selected_fixture_id == "targeted_miss"
    assert report.summary_json["target_filter"] == {
        "probability_min": 0.8,
        "probability_max": 0.9,
        "min_decimal_odds": None,
        "max_decimal_odds": 1.19,
        "max_model_edge": 0.015,
        "missed_legs_only": True,
    }


def test_marginal_audit_cli_options_map_to_backtest_options() -> None:
    args = _parse_args(
        [
            "--suite-manifest",
            "suite.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "2",
            "--max-budget",
            "64",
            "--min-data-quality-score",
            "80",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--focus-competitions",
            "ENG_PREMIER_LEAGUE,JPN_J1",
            "--max-replacement-candidates-per-leg",
            "7",
            "--target-probability-min",
            "0.45",
            "--target-probability-max",
            "0.55",
            "--target-min-decimal-odds",
            "1.75",
            "--target-max-decimal-odds",
            "2.30",
            "--target-max-model-edge",
            "-0.02",
            "--missed-legs-only",
            "--no-same-market-type-only",
        ]
    )

    options = _options_from_args(args)

    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.max_budget == 64
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.derive_market_context_signals is True
    assert options.focus_competition_ids == ("ENG_PREMIER_LEAGUE", "JPN_J1")
    assert options.max_replacement_candidates_per_leg == 7
    assert options.target_probability_min == 0.45
    assert options.target_probability_max == 0.55
    assert options.target_min_decimal_odds == 1.75
    assert options.target_max_decimal_odds == 2.30
    assert options.target_max_model_edge == -0.02
    assert options.missed_legs_only is True
    assert options.same_market_type_only is False


def test_marginal_audit_accepts_multiple_suite_manifests(tmp_path: Path) -> None:
    first_slice_path = tmp_path / "first_slice.json"
    second_slice_path = tmp_path / "second_slice.json"
    first_slice_path.write_text(
        HistoricalRecommendationSlice(
            metadata=_metadata(slice_id="first_slice", competition_id="FIRST_TEST"),
            as_of_time_utc=_dt(2024, 6, 29, 12),
            fixtures=[
                _fixture(
                    "first_fixture",
                    probability=0.90,
                    decimal_odds=1.15,
                    model_edge=0.02,
                    actual_home_goals=2,
                    actual_away_goals=0,
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    second_slice_path.write_text(
        HistoricalRecommendationSlice(
            metadata=_metadata(slice_id="second_slice", competition_id="SECOND_TEST"),
            as_of_time_utc=_dt(2024, 6, 29, 12),
            fixtures=[
                _fixture(
                    "second_fixture",
                    probability=0.90,
                    decimal_odds=1.15,
                    model_edge=0.02,
                    actual_home_goals=2,
                    actual_away_goals=0,
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    first_manifest_path = tmp_path / "first_manifest.json"
    second_manifest_path = tmp_path / "second_manifest.json"
    first_manifest_path.write_text(
        _manifest_json(suite_id="first_suite", slice_path=first_slice_path.name),
        encoding="utf-8",
    )
    second_manifest_path.write_text(
        _manifest_json(suite_id="second_suite", slice_path=second_slice_path.name),
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
    assert loaded.manifest_result is None
    assert [bundle.manifest.suite_id for bundle in loaded.manifest_results] == [
        "first_suite",
        "second_suite",
    ]
    assert loaded.warnings == []


def _metadata(
    *,
    slice_id: str = "unit_test_marginal_audit_slice",
    competition_id: str = "TEST",
) -> HistoricalRecommendationSliceMetadata:
    return HistoricalRecommendationSliceMetadata(
        slice_id=slice_id,
        name="Unit test marginal audit slice",
        competition_id=competition_id,
        result_source="unit test final scores",
        odds_source="unit test odds",
        prediction_source="unit test predictions",
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
    fixture_id: str,
    *,
    probability: float,
    decimal_odds: float,
    model_edge: float,
    actual_home_goals: int,
    actual_away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-marginal-audit-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=model_edge,
                data_quality_score=90,
                model_confidence_score=0.88,
                calibration_score=0.86,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
