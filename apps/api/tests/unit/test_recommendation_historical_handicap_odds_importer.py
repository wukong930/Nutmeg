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
    build_historical_handicap_coverage_audit_report,
)
from nutmeg.recommendations.historical_handicap_odds_importer import (
    HistoricalHandicapOddsImportOptions,
    _options_from_args,
    _parse_args,
    enrich_historical_slice_with_handicap_odds_csv,
    main,
)


def test_handicap_odds_importer_enriches_slice_with_complete_integer_line(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "handicap_odds.csv"
    csv_path.write_text(
        "\n".join(
            [
                "fixture_id,market_type,line,outcome,decimal_odds,probability,"
                "provider,bookmaker,snapshot_time_utc",
                "fixture_1,cn_handicap_1x2,-1,home,4.20,0.18,fixture-book,book-a,"
                "2026-05-08T08:00:00Z",
                "fixture_1,cn_handicap_1x2,-1,draw,3.30,0.57,fixture-book,book-a,"
                "2026-05-08T08:00:00Z",
                "fixture_1,cn_handicap_1x2,-1,away,1.90,0.25,fixture-book,book-a,"
                "2026-05-08T08:00:00Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = enrich_historical_slice_with_handicap_odds_csv(
        _slice(),
        csv_path,
        options=HistoricalHandicapOddsImportOptions(source_label="unit-test-handicap"),
    )

    fixture = result.slice.fixtures[0]
    handicap_predictions = [
        prediction
        for prediction in fixture.predictions
        if prediction.market_type == "cn_handicap_1x2"
    ]
    assert result.imported_line_count == 1
    assert result.imported_prediction_count == 3
    assert result.warnings == []
    assert {prediction.outcome for prediction in handicap_predictions} == {
        "handicap_home_win",
        "handicap_draw",
        "handicap_away_win",
    }
    assert {prediction.line for prediction in handicap_predictions} == {-1.0}
    assert handicap_predictions[1].metadata_json["source"] == "unit-test-handicap"
    assert handicap_predictions[1].metadata_json["probability_source"] == (
        "explicit_probability"
    )

    audit = build_historical_handicap_coverage_audit_report(
        [
            HistoricalHandicapCoverageSource(
                source_id="unit-test",
                source_type="slice_paths",
                slices=[result.slice],
            )
        ],
        options=HistoricalHandicapCoverageAuditOptions(
            pass_types=("1x1",),
            modes=("single",),
            candidate_allowed_markets=("1x2", "cn_handicap_1x2"),
        ),
    )
    assert audit.sources[0].handicap_prediction_count == 3
    assert audit.sources[0].complete_handicap_fixture_count == 1
    assert audit.shadow_summaries[0].candidate_handicap_final_answer_count == 1


def test_handicap_odds_importer_skips_incomplete_required_line(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "incomplete_handicap_odds.csv"
    csv_path.write_text(
        "\n".join(
            [
                "fixture_id,market_type,line,outcome,decimal_odds",
                "fixture_1,european_handicap_1x2,1,home,1.70",
                "fixture_1,european_handicap_1x2,1,away,4.40",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = enrich_historical_slice_with_handicap_odds_csv(_slice(), csv_path)

    assert result.imported_line_count == 0
    assert result.imported_prediction_count == 0
    assert result.skipped_line_count == 1
    assert "handicap_odds_import:skipped_incomplete_line:fixture_1:european_handicap_1x2:1" in (
        result.warnings
    )
    assert all(
        prediction.market_type == "1x2"
        for prediction in result.slice.fixtures[0].predictions
    )


def test_handicap_odds_importer_cli_writes_enriched_slice(
    tmp_path: Path,
) -> None:
    base_slice_path = tmp_path / "base_slice.json"
    csv_path = tmp_path / "handicap_odds.csv"
    output_path = tmp_path / "enriched_slice.json"
    base_slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    csv_path.write_text(
        "\n".join(
            [
                "fixture_id,market_type,line,outcome,decimal_odds",
                "fixture_1,cn_handicap_1x2,1,home,1.75",
                "fixture_1,cn_handicap_1x2,1,draw,3.60",
                "fixture_1,cn_handicap_1x2,1,away,4.20",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            str(base_slice_path),
            str(csv_path),
            "--output-path",
            str(output_path),
            "--source-label",
            "cli-test",
            "--allowed-market-types",
            "cn_handicap_1x2",
        ]
    )
    options = _options_from_args(args)

    assert options.source_label == "cli-test"
    assert options.allowed_market_types == ("cn_handicap_1x2",)

    main(
        [
            str(base_slice_path),
            str(csv_path),
            "--output-path",
            str(output_path),
            "--source-label",
            "cli-test",
            "--allowed-market-types",
            "cn_handicap_1x2",
        ]
    )

    assert output_path.exists()
    enriched = HistoricalRecommendationSlice.model_validate_json(
        output_path.read_text(encoding="utf-8")
    )
    assert len(enriched.fixtures[0].predictions) == 6
    assert enriched.fixtures[0].predictions[-1].metadata_json["source"] == "cli-test"


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="handicap_import_unit_slice",
            name="Handicap import unit slice",
            competition_id="EPL",
            season="2025-2026",
            result_source="unit-test result",
            odds_source="unit-test 1x2 odds",
            prediction_source="unit-test probabilities",
        ),
        as_of_time_utc=datetime(2026, 5, 8, 8, 0, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_1",
                competition_id="EPL",
                kickoff_time_utc=datetime(2026, 5, 8, 19, 0, tzinfo=UTC),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=2,
                actual_away_goals=1,
                prediction_time_utc=datetime(2026, 5, 8, 8, 0, tzinfo=UTC),
                model_version="unit-test-model",
                feature_version="unit-test-feature",
                calibration_version="unit-test-calibration",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.46,
                        decimal_odds=2.05,
                        market_probability=0.48,
                        data_quality_score=82.0,
                    ),
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="draw",
                        probability=0.27,
                        decimal_odds=3.40,
                        market_probability=0.29,
                        data_quality_score=82.0,
                    ),
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="away_win",
                        probability=0.27,
                        decimal_odds=3.70,
                        market_probability=0.27,
                        data_quality_score=82.0,
                    ),
                ],
            )
        ],
    )
