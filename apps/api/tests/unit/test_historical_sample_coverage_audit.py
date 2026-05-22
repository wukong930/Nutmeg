from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import build_enriched_historical_feature_sample
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditOptions,
    _LoadedCoverageSource,
    _options_from_args,
    _parse_args,
    build_historical_sample_coverage_audit_report,
    main,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
)


def test_historical_sample_coverage_audit_classifies_sources_and_gaps() -> None:
    enriched_slice = build_enriched_historical_feature_sample().historical_slice
    core_epl = _slice_for(
        enriched_slice,
        slice_id="core_epl_2024_2025",
        competition_id="EPL",
        season="2024-2025",
        fixture_prefix="core_epl",
        keep_features=False,
    )
    core_j1 = _slice_for(
        enriched_slice,
        slice_id="core_j1_2024",
        competition_id="JPN_J1",
        season="2024",
        fixture_prefix="core_j1",
        keep_features=False,
    )
    feature_epl = _slice_for(
        enriched_slice,
        slice_id="feature_epl_2024_2025",
        competition_id="EPL",
        season="2024-2025",
        fixture_prefix="feature_epl",
        keep_features=True,
    )

    report = build_historical_sample_coverage_audit_report(
        [
            _LoadedCoverageSource(
                source_id="core_suite",
                source_type="slice_paths",
                slices=[core_epl, core_j1],
            ),
            _LoadedCoverageSource(
                source_id="feature_suite",
                source_type="slice_paths",
                slices=[feature_epl],
            ),
        ],
        options=HistoricalSampleCoverageAuditOptions(
            min_final_answer_fixture_count=2,
            min_feature_snapshot_coverage=1.0,
            min_odds_movement_coverage=0.8,
            min_lineup_coverage=0.8,
            min_availability_coverage=0.8,
            min_semantic_signal_coverage=0.8,
        ),
    )

    core_summary = report.sources[0]
    feature_summary = report.sources[1]

    assert report.source_count == 2
    assert report.fixture_count == 6
    assert core_summary.readiness_json["final_answer_sample_ready"] is True
    assert core_summary.readiness_json["feature_snapshot_ready"] is False
    assert feature_summary.readiness_json["market_movement_feature_ready"] is True
    assert feature_summary.readiness_json["context_signal_ready"] is True
    assert report.cross_source_gaps[0].source_id == "feature_suite"
    assert report.cross_source_gaps[0].missing_competition_season_keys == [
        "JPN_J1:2024"
    ]


def test_historical_sample_coverage_audit_counts_dynamic_market_candidates() -> None:
    report = build_historical_sample_coverage_audit_report(
        [
            _LoadedCoverageSource(
                source_id="mixed_market_suite",
                source_type="slice_paths",
                slices=[_mixed_market_slice()],
            )
        ],
        options=HistoricalSampleCoverageAuditOptions(
            min_final_answer_fixture_count=2,
            min_dynamic_mixed_candidate_fixture_count=1,
            min_handicap_candidate_fixture_count=1,
            min_correct_score_candidate_fixture_count=1,
            min_feature_snapshot_coverage=0.0,
        ),
    )

    summary = report.sources[0]

    assert summary.prediction_count_by_market == {
        "1x2": 6,
        "cn_handicap_1x2": 3,
        "correct_score": 1,
    }
    assert summary.fixture_count_by_market == {
        "1x2": 2,
        "cn_handicap_1x2": 1,
        "correct_score": 1,
    }
    assert summary.complete_market_fixture_count_by_market == {
        "1x2": 2,
        "cn_handicap_1x2": 1,
        "correct_score": 1,
    }
    assert summary.non_1x2_market_fixture_count == 1
    assert summary.handicap_market_fixture_count == 1
    assert summary.correct_score_market_fixture_count == 1
    assert summary.dynamic_mixed_candidate_fixture_count == 1
    assert summary.dynamic_mixed_candidate_fixture_coverage == 0.5
    assert summary.readiness_json["dynamic_mixed_candidate_ready"] is True
    assert summary.readiness_json["handicap_candidate_ready"] is True
    assert summary.readiness_json["correct_score_candidate_ready"] is True
    assert report.summary_json["dynamic_mixed_candidate_ready_source_ids"] == [
        "mixed_market_suite"
    ]


def test_historical_sample_coverage_audit_cli_writes_report(tmp_path: Path) -> None:
    enriched_slice = build_enriched_historical_feature_sample().historical_slice
    slice_path = tmp_path / "feature_slice.json"
    manifest_path = tmp_path / "feature_suite.json"
    output_path = tmp_path / "coverage_audit.json"
    slice_path.write_text(
        f"{enriched_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    manifest = HistoricalRecommendationSuiteManifest(
        suite_id="feature_suite",
        name="Feature Suite",
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
            "--min-final-answer-fixture-count",
            "2",
        ]
    )

    assert output_path.exists()
    assert "historical_sample_coverage_audit" in output_path.read_text(
        encoding="utf-8"
    )


def test_historical_sample_coverage_audit_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--suite-manifest",
            "configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json",
            "--slice-path",
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/audit.json",
            "--audit-id",
            "coverage-test",
            "--baseline-source-index",
            "1",
            "--min-final-answer-fixture-count",
            "10",
            "--min-dynamic-mixed-candidate-fixture-count",
            "2",
            "--min-handicap-candidate-fixture-count",
            "3",
            "--min-correct-score-candidate-fixture-count",
            "4",
            "--min-feature-snapshot-coverage",
            "0.9",
            "--min-odds-movement-coverage",
            "0.7",
            "--min-lineup-coverage",
            "0.6",
            "--min-availability-coverage",
            "0.5",
            "--min-semantic-signal-coverage",
            "0.4",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/audit.json")
    assert options.audit_id == "coverage-test"
    assert options.baseline_source_index == 1
    assert options.min_final_answer_fixture_count == 10
    assert options.min_dynamic_mixed_candidate_fixture_count == 2
    assert options.min_handicap_candidate_fixture_count == 3
    assert options.min_correct_score_candidate_fixture_count == 4
    assert options.min_feature_snapshot_coverage == 0.9
    assert options.min_odds_movement_coverage == 0.7
    assert options.min_lineup_coverage == 0.6
    assert options.min_availability_coverage == 0.5
    assert options.min_semantic_signal_coverage == 0.4


def _slice_for(
    template: HistoricalRecommendationSlice,
    *,
    slice_id: str,
    competition_id: str,
    season: str,
    fixture_prefix: str,
    keep_features: bool,
) -> HistoricalRecommendationSlice:
    fixtures = [
        fixture.model_copy(
            update={
                "fixture_id": f"{fixture_prefix}_{index}",
                "competition_id": competition_id,
                "feature_snapshot": fixture.feature_snapshot if keep_features else None,
            }
        )
        for index, fixture in enumerate(template.fixtures[:2], start=1)
    ]
    return template.model_copy(
        update={
            "metadata": template.metadata.model_copy(
                update={
                    "slice_id": slice_id,
                    "competition_id": competition_id,
                    "season": season,
                }
            ),
            "fixtures": fixtures,
        }
    )


def _mixed_market_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="unit_mixed_market_slice",
            name="Unit mixed market coverage slice",
            competition_id="TEST",
            season="2024",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 1, 10),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_mixed",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 2, 12),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=2,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 1, 9),
                model_version="poisson-v3.1-coverage-test",
                predictions=[
                    _prediction("1x2", "home_win"),
                    _prediction("1x2", "draw", probability=0.25),
                    _prediction("1x2", "away_win", probability=0.20),
                    _prediction("cn_handicap_1x2", "handicap_home_win"),
                    _prediction(
                        "cn_handicap_1x2",
                        "handicap_draw",
                        probability=0.25,
                    ),
                    _prediction(
                        "cn_handicap_1x2",
                        "handicap_away_win",
                        probability=0.20,
                    ),
                    _prediction("correct_score", "2-1", probability=0.18),
                ],
            ),
            HistoricalFixture(
                fixture_id="fixture_1x2_only",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 2, 14),
                home_team_name="Charlie",
                away_team_name="Delta",
                actual_home_goals=0,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 1, 9),
                model_version="poisson-v3.1-coverage-test",
                predictions=[
                    _prediction("1x2", "home_win", probability=0.30),
                    _prediction("1x2", "draw", probability=0.40),
                    _prediction("1x2", "away_win", probability=0.30),
                ],
            ),
        ],
    )


def _prediction(
    market_type: str,
    outcome: str,
    *,
    probability: float = 0.55,
) -> HistoricalMarketPrediction:
    return HistoricalMarketPrediction(
        market_type=market_type,  # type: ignore[arg-type]
        outcome=outcome,
        probability=probability,
        decimal_odds=2.0,
        market_probability=0.50,
        data_quality_score=90,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
