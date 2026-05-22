from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    FootballDataCoUkImportOptions,
    HistoricalRecommendationSampleQualityOptions,
    build_historical_recommendation_slice_from_football_data_co_uk_csv,
    evaluate_historical_recommendation_sample_quality,
    run_football_data_co_uk_batch_import,
)
from nutmeg.recommendations.football_data_co_uk_importer import _options_from_args, _parse_args


def test_football_data_co_uk_importer_builds_market_implied_slice(
    tmp_path: Path,
) -> None:
    csv_path = _write_football_data_csv(tmp_path)

    result = build_historical_recommendation_slice_from_football_data_co_uk_csv(
        csv_path,
        options=_import_options(),
    )

    assert result.row_count == 3
    assert result.fixture_count == 2
    assert result.prediction_count == 6
    assert result.skipped_row_count == 1
    assert result.selected_odds_prefix_counts == {"AvgC": 2}
    assert result.slice.metadata.slice_id == "football_data_co_uk_epl_2023_2024_e0"
    assert result.slice.as_of_time_utc == datetime(2023, 8, 10, 12, tzinfo=UTC)
    assert result.slice.fixtures[0].fixture_id == (
        "fdcuk_epl_2023_2024_2023_08_11_burnley_man_city"
    )
    assert result.slice.fixtures[0].actual_1x2_outcome == "away_win"
    assert result.slice.fixtures[0].metadata_json["selected_odds_prefix"] == "AvgC"
    assert (
        "football_data_co_uk_import:row_4:missing_1x2_odds"
        in result.warnings
    )

    first_predictions = result.slice.fixtures[0].predictions
    assert [prediction.outcome for prediction in first_predictions] == [
        "home_win",
        "draw",
        "away_win",
    ]
    assert sum(prediction.probability for prediction in first_predictions) == pytest.approx(1)
    assert first_predictions[0].decimal_odds == 8.0
    assert first_predictions[0].market_probability == pytest.approx(0.125)
    assert first_predictions[0].metadata_json["target_outcome"] == "home_win"
    assert first_predictions[2].metadata_json["selected_odds_prefix"] == "AvgC"


def test_football_data_co_uk_importer_slice_passes_sample_quality(
    tmp_path: Path,
) -> None:
    result = build_historical_recommendation_slice_from_football_data_co_uk_csv(
        _write_football_data_csv(tmp_path),
        options=_import_options(),
    )

    quality = evaluate_historical_recommendation_sample_quality(
        result.slice,
        options=HistoricalRecommendationSampleQualityOptions(
            min_fixture_count=2,
            require_market_probability=True,
            min_data_quality_score=80,
        ),
    )

    assert quality.passed is True
    assert quality.summary_json["complete_1x2_fixture_count"] == 2


def test_football_data_co_uk_importer_supports_worldwide_csv_shape_and_season_filter(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "JPN.csv"
    csv_path.write_text(
        (
            "Country,League,Season,Date,Time,Home,Away,HG,AG,Res,"
            "AvgCH,AvgCD,AvgCA,B365CH,B365CD,B36CA\n"
            "Japan,J1 League,2021,26/02/2021,10:00,Kawasaki Frontale,Yokohama F Marinos,"
            "2,0,H,1.72,3.95,4.70,1.70,4.00,4.80\n"
            "Japan,J1 League,2022,18/02/2022,10:00,Kawasaki Frontale,FC Tokyo,"
            "1,0,H,1.80,3.65,4.60,1.78,3.70,4.65\n"
        ),
        encoding="utf-8",
    )

    result = build_historical_recommendation_slice_from_football_data_co_uk_csv(
        csv_path,
        options=FootballDataCoUkImportOptions(
            competition_id="JPN_J1",
            as_of_time_utc=datetime(2022, 1, 1, tzinfo=UTC),
            season="2022",
            source_seasons=("2022",),
        ),
    )

    assert result.row_count == 2
    assert result.fixture_count == 1
    assert result.skipped_row_count == 1
    assert result.slice.fixtures[0].fixture_id == (
        "fdcuk_jpn_j1_2022_2022_02_18_kawasaki_frontale_fc_tokyo"
    )
    assert result.slice.fixtures[0].metadata_json["source_division"] == "J1 League"
    assert result.slice.fixtures[0].metadata_json["source_season"] == "2022"
    assert result.slice.fixtures[0].predictions[2].decimal_odds == 4.6


def test_football_data_co_uk_batch_import_writes_generated_slice(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "generated_slices"

    result = run_football_data_co_uk_batch_import(
        [_write_football_data_csv(tmp_path)],
        options=_import_options(),
        output_dir=output_dir,
    )

    assert result.import_count == 1
    assert result.fixture_count == 2
    assert result.output_slice_paths == [
        output_dir / "football_data_co_uk_epl_2023_2024_e0.json"
    ]
    assert result.output_slice_paths[0].exists()
    assert "Burnley" in result.output_slice_paths[0].read_text(encoding="utf-8")


def test_football_data_co_uk_importer_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "E0.csv",
            "--output-dir",
            "tmp/generated_slices",
            "--manifest-path",
            "tmp/suite.json",
            "--write-manifest",
            "--manifest-tag",
            "football-data-co-uk",
            "--manifest-note",
            "bulk historical import",
            "--competition-id",
            "EPL",
            "--as-of-time-utc",
            "2023-08-10T12:00:00Z",
            "--season",
            "2023-2024",
            "--slice-id-prefix",
            "fdcuk",
            "--name-prefix",
            "Imported",
            "--source-url",
            "https://example.test/E0.csv",
            "--note",
            "unit import",
            "--odds-prefix",
            "AvgC",
            "--odds-prefix",
            "B365C",
            "--data-quality-score",
            "84",
            "--max-rows",
            "100",
            "--source-season",
            "2021",
            "--source-season",
            "2022",
        ]
    )

    options = _options_from_args(args)

    assert args.output_dir == Path("tmp/generated_slices")
    assert args.manifest_path == Path("tmp/suite.json")
    assert args.write_manifest is True
    assert args.manifest_tag == ["football-data-co-uk"]
    assert args.manifest_note == ["bulk historical import"]
    assert options.competition_id == "EPL"
    assert options.as_of_time_utc == datetime(2023, 8, 10, 12, tzinfo=UTC)
    assert options.season == "2023-2024"
    assert options.slice_id_prefix == "fdcuk"
    assert options.name_prefix == "Imported"
    assert options.source_urls == ("https://example.test/E0.csv",)
    assert options.notes == ("unit import",)
    assert options.odds_prefix_priority == ("AvgC", "B365C")
    assert options.data_quality_score == 84
    assert options.max_rows == 100
    assert options.source_seasons == ("2021", "2022")


def _import_options() -> FootballDataCoUkImportOptions:
    return FootballDataCoUkImportOptions(
        competition_id="EPL",
        as_of_time_utc=datetime(2023, 8, 10, 12, tzinfo=UTC),
        season="2023-2024",
    )


def _write_football_data_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "E0.csv"
    csv_path.write_text(
        (
            "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
            "AvgCH,AvgCD,AvgCA,B365CH,B365CD,B365CA\n"
            "E0,11/08/2023,20:00,Burnley,Man City,0,3,A,"
            "8.00,5.20,1.36,8.50,5.00,1.35\n"
            "E0,12/08/2023,12:30,Arsenal,Nott'm Forest,2,1,H,"
            "1.25,6.10,11.00,1.22,6.50,12.00\n"
            "E0,12/08/2023,15:00,Bournemouth,West Ham,1,1,D,"
            ",,,,,,\n"
        ),
        encoding="utf-8",
    )
    return csv_path
