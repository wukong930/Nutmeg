from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_handicap_coverage_audit import (
    HistoricalHandicapCoverageAuditOptions,
    HistoricalHandicapCoverageSource,
    _options_from_args,
    _parse_args,
    build_historical_handicap_coverage_audit_report,
    main,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
)


def test_handicap_coverage_audit_counts_shadow_final_answer_gain() -> None:
    report = build_historical_handicap_coverage_audit_report(
        [
            HistoricalHandicapCoverageSource(
                source_id="unit_handicap_source",
                source_type="slice_paths",
                slices=[_slice_with_handicap_candidate()],
            )
        ],
        options=HistoricalHandicapCoverageAuditOptions(
            pass_types=("1x1",),
            modes=("single",),
            min_probability=0.10,
            min_data_quality_score=50.0,
            top_changed_slice_limit=5,
        ),
    )

    coverage = report.sources[0]
    shadow = report.shadow_summaries[0]

    assert coverage.handicap_prediction_count == 1
    assert coverage.eligible_handicap_prediction_count == 1
    assert coverage.handicap_fixture_count == 1
    assert coverage.complete_handicap_fixture_count == 0
    assert shadow.changed_final_answer_count == 1
    assert shadow.candidate_handicap_final_answer_count == 1
    assert shadow.final_hit_delta_count == 1
    assert shadow.profit_loss_delta == 3.4
    assert shadow.top_changed_slices[0].candidate_markets == ["cn_handicap_1x2"]
    assert report.summary_json["candidate_handicap_final_answer_count"] == 1


def test_handicap_coverage_audit_reports_missing_handicap_candidates() -> None:
    report = build_historical_handicap_coverage_audit_report(
        [
            HistoricalHandicapCoverageSource(
                source_id="unit_1x2_only_source",
                source_type="slice_paths",
                slices=[_slice_without_handicap_candidate()],
            )
        ],
        options=HistoricalHandicapCoverageAuditOptions(
            pass_types=("1x1",),
            modes=("single",),
            min_probability=0.10,
        ),
    )

    assert report.sources[0].handicap_prediction_count == 0
    assert "handicap_coverage:no_handicap_predictions" in report.warnings
    assert "handicap_shadow:no_handicap_candidates_available" in report.warnings
    assert report.shadow_summaries[0].changed_final_answer_count == 0


def test_handicap_coverage_audit_cli_writes_report(tmp_path: Path) -> None:
    slice_path = tmp_path / "slice.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "handicap_audit.json"
    slice_path.write_text(
        f"{_slice_with_handicap_candidate().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    manifest = HistoricalRecommendationSuiteManifest(
        suite_id="unit_handicap_suite",
        name="Unit handicap suite",
        slices=[
            HistoricalRecommendationSuiteManifestSlice(
                slice_path=slice_path.name,
                enabled=True,
            )
        ],
    )
    manifest_path.write_text(
        f"{manifest.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--suite-manifest",
            str(manifest_path),
            "--output-path",
            str(output_path),
            "--pass-types",
            "1x1",
            "--modes",
            "single",
            "--min-probability",
            "0.10",
        ]
    )

    assert output_path.exists()
    assert "historical_handicap_coverage_shadow_audit" in output_path.read_text(
        encoding="utf-8"
    )


def test_handicap_coverage_audit_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--slice-path",
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/handicap-audit.json",
            "--audit-id",
            "unit-handicap-audit",
            "--baseline-allowed-markets",
            "1x2",
            "--candidate-allowed-markets",
            "1x2,cn_handicap_1x2,european_handicap_1x2",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--candidate-fixture-limit",
            "6",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "1",
            "--derive-market-context-signals",
            "--top-changed-slice-limit",
            "7",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/handicap-audit.json")
    assert options.audit_id == "unit-handicap-audit"
    assert options.candidate_allowed_markets == (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
    )
    assert options.pass_types == ("1x1", "2x1")
    assert options.modes == ("single",)
    assert options.unit_stake == 3
    assert options.max_budget == 12
    assert options.candidate_fixture_limit == 6
    assert options.max_candidates_per_fixture == 2
    assert options.scenario_candidate_fixture_buffer == 1
    assert options.derive_market_context_signals is True
    assert options.top_changed_slice_limit == 7


def _slice_with_handicap_candidate() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata("unit_handicap_shadow_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_a",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=0,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-handicap-audit-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.60,
                        decimal_odds=1.50,
                        market_probability=1 / 1.50,
                        data_quality_score=90,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                    ),
                    HistoricalMarketPrediction(
                        market_type="cn_handicap_1x2",
                        outcome="handicap_away_win",
                        probability=0.72,
                        decimal_odds=1.70,
                        market_probability=1 / 1.70,
                        data_quality_score=90,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                        line=-1.0,
                    ),
                ],
            )
        ],
    )


def _slice_without_handicap_candidate() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=_metadata("unit_1x2_only_shadow_slice"),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_b",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Charlie",
                away_team_name="Delta",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-handicap-audit-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.62,
                        decimal_odds=1.50,
                        market_probability=1 / 1.50,
                        data_quality_score=90,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                    )
                ],
            )
        ],
    )


def _metadata(slice_id: str) -> HistoricalRecommendationSliceMetadata:
    return HistoricalRecommendationSliceMetadata(
        slice_id=slice_id,
        name="Unit handicap audit slice",
        competition_id="TEST",
        result_source="unit test final scores",
        odds_source="unit test odds",
        prediction_source="unit test predictions",
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
