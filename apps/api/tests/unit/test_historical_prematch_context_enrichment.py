from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.domain.features import (
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_feature_completeness import (
    HistoricalFeatureCompletenessOptions,
)
from nutmeg.recommendations.historical_prematch_context_enrichment import (
    HistoricalPrematchContextEnrichmentOptions,
    _completeness_options_from_args,
    _load_availability_csv,
    _load_lineup_csv,
    _load_semantic_csv,
    _options_from_args,
    _parse_args,
    enrich_historical_slice_with_frozen_prematch_context,
)


def test_prematch_context_enrichment_merges_lineup_availability_and_news(
    tmp_path: Path,
) -> None:
    input_slice = _base_slice_with_odds_movement()
    lineup_csv, availability_csv, semantic_csv = _context_csvs(tmp_path)

    result = enrich_historical_slice_with_frozen_prematch_context(
        input_slice,
        options=HistoricalPrematchContextEnrichmentOptions(
            slice_id="ctx_enriched_slice",
            name="Context enriched slice",
            historical_stats_completeness=0.82,
            provider_consistency=0.92,
        ),
        lineup_rows=_load_lineup_csv(lineup_csv),
        availability_rows=_load_availability_csv(availability_csv),
        semantic_rows=_load_semantic_csv(semantic_csv),
        completeness_options=HistoricalFeatureCompletenessOptions(
            min_fixture_count=1,
            min_feature_snapshot_coverage=1.0,
            min_lineup_coverage=1.0,
            min_availability_coverage=1.0,
            min_odds_movement_coverage=1.0,
            min_semantic_signal_coverage=1.0,
            min_source_ref_coverage=1.0,
            min_average_feature_data_quality_score=70.0,
            min_feature_data_quality_score=70.0,
        ),
    )

    fixture = result.historical_slice.fixtures[0]
    assert result.completeness_result.passed is True
    assert result.enriched_fixture_count == 1
    assert result.lineup_row_count == 1
    assert result.availability_row_count == 1
    assert result.semantic_row_count == 1
    assert result.warnings == []
    assert fixture.feature_version == "features-v3.1-frozen-prematch-context"
    assert fixture.feature_snapshot is not None
    prematch_context = fixture.feature_snapshot.features_json["prematch_context"]
    assert prematch_context["lineup"]["lineup_type"] == "confirmed"
    assert prematch_context["availability"]["key_player_absence_score"] == 0.42
    assert prematch_context["odds_movement"][0]["current_prob"] == 0.54
    assert prematch_context["semantic_signals"][0]["signal_name"] == (
        "press_conference_injury_hint"
    )
    assert fixture.feature_snapshot.source_snapshot_refs["prematch"]["lineup"][
        "source_snapshot_ref"
    ] == "lineup:fixture_ctx_001"

    backtest = run_historical_recommendation_backtest(
        result.historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            max_budget=2.0,
        ),
    )
    assert backtest.final_answer is not None
    assert backtest.completed_count == 1


def test_prematch_context_enrichment_warns_on_unknown_fixture(
    tmp_path: Path,
) -> None:
    input_slice = _base_slice_with_odds_movement()
    lineup_csv, availability_csv, semantic_csv = _context_csvs(tmp_path)
    with lineup_csv.open("a", encoding="utf-8") as handle:
        handle.write(
            "unknown_fixture,2026-05-08T09:00:00Z,expected,0.60,0.70,0.20,"
            "unit-test,lineup:unknown,{}\n"
        )

    result = enrich_historical_slice_with_frozen_prematch_context(
        input_slice,
        lineup_rows=_load_lineup_csv(lineup_csv),
        availability_rows=_load_availability_csv(availability_csv),
        semantic_rows=_load_semantic_csv(semantic_csv),
    )

    assert result.enriched_fixture_count == 1
    assert (
        "prematch_context_enrichment:unknown_lineup_fixture:unknown_fixture:row_3"
        in result.warnings
    )


def test_prematch_context_enrichment_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--lineup-csv",
            "tmp/lineup.csv",
            "--availability-csv",
            "tmp/availability.csv",
            "--semantic-csv",
            "tmp/semantic.csv",
            "--output-path",
            "tmp/enriched.json",
            "--completeness-output-path",
            "tmp/completeness.json",
            "--suite-manifest-output-path",
            "tmp/suite.json",
            "--slice-id",
            "slice-cli",
            "--name",
            "Slice CLI",
            "--feature-version",
            "features-cli",
            "--fixture-reliability",
            "0.91",
            "--historical-stats-completeness",
            "0.82",
            "--provider-consistency",
            "0.88",
            "--drop-existing-lineup",
            "--drop-existing-availability",
            "--drop-existing-odds-movement",
            "--drop-existing-semantic-signals",
            "--note",
            "unit note",
            "--min-fixture-count",
            "2",
            "--min-feature-snapshot-coverage",
            "0.90",
            "--min-lineup-coverage",
            "0.80",
            "--min-availability-coverage",
            "0.70",
            "--min-odds-movement-coverage",
            "0.60",
            "--min-semantic-signal-coverage",
            "0.50",
            "--min-source-ref-coverage",
            "0.40",
            "--min-average-feature-data-quality-score",
            "72",
            "--min-feature-data-quality-score",
            "65",
            "--allow-missing-prematch-context",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
        ]
    )

    options = _options_from_args(args)
    completeness_options = _completeness_options_from_args(args)

    assert options.slice_id == "slice-cli"
    assert options.name == "Slice CLI"
    assert options.feature_version == "features-cli"
    assert options.fixture_reliability == 0.91
    assert options.historical_stats_completeness == 0.82
    assert options.provider_consistency == 0.88
    assert options.preserve_existing_lineup is False
    assert options.preserve_existing_availability is False
    assert options.preserve_existing_odds_movement is False
    assert options.preserve_existing_semantic_signals is False
    assert options.append_note == "unit note"
    assert completeness_options.min_fixture_count == 2
    assert completeness_options.min_feature_snapshot_coverage == 0.90
    assert completeness_options.min_lineup_coverage == 0.80
    assert completeness_options.min_availability_coverage == 0.70
    assert completeness_options.min_odds_movement_coverage == 0.60
    assert completeness_options.min_semantic_signal_coverage == 0.50
    assert completeness_options.min_source_ref_coverage == 0.40
    assert completeness_options.min_average_feature_data_quality_score == 72
    assert completeness_options.min_feature_data_quality_score == 65
    assert completeness_options.require_prematch_context is False
    assert completeness_options.require_feature_not_after_prediction is False
    assert completeness_options.require_feature_before_kickoff is False


def _base_slice_with_odds_movement() -> HistoricalRecommendationSlice:
    fixture = HistoricalFixture(
        fixture_id="fixture_ctx_001",
        competition_id="EPL",
        kickoff_time_utc=datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
        home_team_name="Alpha",
        away_team_name="Bravo",
        actual_home_goals=2,
        actual_away_goals=0,
        prediction_time_utc=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        model_version="model-v1",
        feature_version="features-odds-only",
        calibration_version="calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.54,
                decimal_odds=1.90,
                market_probability=0.52,
                model_edge=0.02,
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.26,
                decimal_odds=3.60,
                market_probability=0.28,
                model_edge=-0.02,
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.20,
                decimal_odds=4.80,
                market_probability=0.20,
                model_edge=0.00,
            ),
        ],
        feature_snapshot=build_structured_prematch_feature_snapshot(
            fixture_id="fixture_ctx_001",
            competition_id="EPL",
            kickoff_time_utc=datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
            feature_time_utc=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
            prematch_features=StructuredPrematchFeatureSet(
                odds_movements=[
                    PrematchOddsMovementFeature(
                        market_type="1x2",
                        outcome="home_win",
                        bookmaker_disagreement=0.04,
                        points=[
                            PrematchOddsMovementPoint(
                                snapshot_time_utc=datetime(
                                    2026,
                                    5,
                                    8,
                                    6,
                                    0,
                                    tzinfo=UTC,
                                ),
                                market_type="1x2",
                                outcome="home_win",
                                decimal_odds=2.05,
                                fair_probability=0.49,
                                source="odds-unit-test",
                                source_snapshot_ref="odds:fixture_ctx_001:open",
                            ),
                            PrematchOddsMovementPoint(
                                snapshot_time_utc=datetime(
                                    2026,
                                    5,
                                    8,
                                    9,
                                    45,
                                    tzinfo=UTC,
                                ),
                                market_type="1x2",
                                outcome="home_win",
                                decimal_odds=1.90,
                                fair_probability=0.54,
                                source="odds-unit-test",
                                source_snapshot_ref="odds:fixture_ctx_001:current",
                            ),
                        ],
                    )
                ]
            ),
        ),
    )
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="ctx_base_slice",
            name="Context base slice",
            competition_id="EPL",
            season="2025-2026",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        fixtures=[fixture],
    )


def _context_csvs(tmp_path: Path) -> tuple[Path, Path, Path]:
    lineup_csv = tmp_path / "lineup.csv"
    lineup_csv.write_text(
        "\n".join(
            [
                "fixture_id,snapshot_time_utc,lineup_type,expected_lineup_confidence,"
                "starting_xi_strength,bench_dropoff_score,source,source_snapshot_ref,"
                "metadata_json",
                "fixture_ctx_001,2026-05-08T09:00:00Z,confirmed,0.92,0.88,0.10,"
                "unit-test,lineup:fixture_ctx_001,{}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    availability_csv = tmp_path / "availability.csv"
    availability_csv.write_text(
        "\n".join(
            [
                "fixture_id,snapshot_time_utc,unavailable_key_player_count,"
                "doubtful_key_player_count,key_player_absence_score,"
                "defender_absence_score,goalkeeper_absence_score,striker_absence_score,"
                "source,source_snapshot_ref,metadata_json",
                "fixture_ctx_001,2026-05-08T08:00:00Z,1,1,0.42,0.10,0.00,0.45,"
                "unit-test,availability:fixture_ctx_001,{}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    semantic_csv = tmp_path / "semantic.csv"
    semantic_csv.write_text(
        "\n".join(
            [
                "fixture_id,signal_name,source,confidence,evidence_text_short,"
                "extracted_at_utc,metadata_json",
                "fixture_ctx_001,press_conference_injury_hint,unit-test,0.74,"
                "Coach confirmed a key striker is doubtful.,2026-05-08T09:30:00Z,{}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return lineup_csv, availability_csv, semantic_csv
