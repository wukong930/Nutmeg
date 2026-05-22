from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import build_football_data_co_uk_prematch_feature_sample
from nutmeg.recommendations.football_data_co_uk_feature_sample import (
    DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID,
    FootballDataCoUkPrematchFeatureBatchOptions,
    FootballDataCoUkPrematchFeatureSampleOptions,
    _batch_options_from_args,
    _options_from_args,
    _parse_args,
    _parse_batch_args,
    batch_main,
    build_football_data_co_uk_prematch_feature_batch,
    main,
)
from nutmeg.recommendations.historical_backtest import (
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_feature_completeness import (
    HistoricalFeatureCompletenessResult,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)


def test_football_data_co_uk_feature_sample_builds_market_movement_snapshots(
    tmp_path: Path,
) -> None:
    csv_path = _sample_csv(tmp_path)

    result = build_football_data_co_uk_prematch_feature_sample(
        csv_path,
        options=FootballDataCoUkPrematchFeatureSampleOptions(max_rows=2),
    )
    historical_slice = result.historical_slice
    first_fixture = historical_slice.fixtures[0]
    assert first_fixture.feature_snapshot is not None

    prematch_context = first_fixture.feature_snapshot.features_json["prematch_context"]
    home_movement = prematch_context["odds_movement"][0]

    assert historical_slice.metadata.slice_id == DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID
    assert len(historical_slice.fixtures) == 2
    assert result.completeness_result.passed is True
    assert result.completeness_result.summary_json["odds_movement_coverage"] == 1.0
    assert result.completeness_result.summary_json["semantic_signal_coverage"] == 0.0
    assert first_fixture.prediction_time_utc < first_fixture.kickoff_time_utc
    assert home_movement["outcome"] == "home_win"
    assert home_movement["movement_direction"] == "probability_shortened"
    assert prematch_context["lineup"] is None
    assert prematch_context["availability"] is None
    assert prematch_context["risk_signals"]["lineup_schedule_risk"] == 0.0
    assert first_fixture.metadata_json["selected_odds_pair"] == "Avg->AvgC"
    assert abs(sum(prediction.probability for prediction in first_fixture.predictions) - 1) < 1e-9


def test_football_data_co_uk_feature_sample_can_include_asian_handicap_movements(
    tmp_path: Path,
) -> None:
    csv_path = _sample_csv(tmp_path)

    result = build_football_data_co_uk_prematch_feature_sample(
        csv_path,
        options=FootballDataCoUkPrematchFeatureSampleOptions(
            max_rows=2,
            include_asian_handicap_features=True,
        ),
    )
    first_fixture = result.historical_slice.fixtures[0]
    assert first_fixture.feature_snapshot is not None

    prematch_context = first_fixture.feature_snapshot.features_json["prematch_context"]
    asian_movements = [
        movement
        for movement in prematch_context["odds_movement"]
        if movement["market_type"] == "asian_handicap"
    ]

    assert result.summary_json["include_asian_handicap_features"] is True
    assert result.summary_json["asian_handicap_feature_fixture_count"] == 2
    assert first_fixture.metadata_json["asian_handicap_available"] is True
    assert prematch_context["metadata_json"]["asian_handicap_available"] is True
    assert [movement["outcome"] for movement in asian_movements] == [
        "home_cover",
        "away_cover",
    ]
    assert asian_movements[0]["metadata_json"]["opening_line"] == -0.5
    assert asian_movements[0]["metadata_json"]["closing_line"] == -0.75
    assert asian_movements[0]["metadata_json"]["line_changed"] is True


def test_football_data_co_uk_feature_sample_builds_closing_only_j1_snapshots(
    tmp_path: Path,
) -> None:
    csv_path = _worldwide_closing_only_csv(tmp_path)

    result = build_football_data_co_uk_prematch_feature_sample(
        csv_path,
        options=FootballDataCoUkPrematchFeatureSampleOptions(
            slice_id="football_data_co_uk_jpn_j1_2022_closing_only_features_v1",
            name="Football-Data.co.uk J1 2022 closing-only feature sample",
            competition_id="JPN_J1",
            season="2022",
            max_rows=2,
            feature_source_kind="closing_only",
            source_seasons=("2022",),
        ),
    )
    historical_slice = result.historical_slice
    first_fixture = historical_slice.fixtures[0]
    assert first_fixture.feature_snapshot is not None

    prematch_context = first_fixture.feature_snapshot.features_json["prematch_context"]
    home_movement = prematch_context["odds_movement"][0]

    assert len(historical_slice.fixtures) == 2
    assert result.completeness_result.passed is True
    assert first_fixture.metadata_json["feature_source_kind"] == "closing_only"
    assert first_fixture.metadata_json["selected_odds_pair"] == "AvgC:closing_only"
    assert first_fixture.predictions[0].metadata_json["baseline_probability_source"] == (
        "closing_no_vig_probability"
    )
    assert home_movement["point_count"] == 1
    assert home_movement["metadata_json"]["source_kind"] == "closing_only"
    assert home_movement["metadata_json"]["movement_available"] is False


def test_football_data_co_uk_feature_sample_can_use_slice_start_prediction_time(
    tmp_path: Path,
) -> None:
    csv_path = _worldwide_closing_only_csv(tmp_path)

    result = build_football_data_co_uk_prematch_feature_sample(
        csv_path,
        options=FootballDataCoUkPrematchFeatureSampleOptions(
            competition_id="JPN_J1",
            season="2022",
            max_rows=2,
            feature_source_kind="closing_only",
            source_seasons=("2022",),
            prediction_time_policy="slice_start",
        ),
    )
    historical_slice = result.historical_slice
    prediction_times = {
        fixture.prediction_time_utc for fixture in historical_slice.fixtures
    }

    assert len(historical_slice.fixtures) == 2
    assert len(prediction_times) == 1
    assert historical_slice.as_of_time_utc == next(iter(prediction_times))
    assert all(
        fixture.kickoff_time_utc > historical_slice.as_of_time_utc
        for fixture in historical_slice.fixtures
    )
    assert result.summary_json["prediction_time_policy"] == "slice_start"
    assert any("Slice-start prediction time" in note for note in historical_slice.metadata.notes)


def test_football_data_co_uk_feature_sample_cli_writes_artifacts(
    tmp_path: Path,
) -> None:
    csv_path = _sample_csv(tmp_path)
    output_path = tmp_path / "fdcuk_feature_sample.json"
    completeness_path = tmp_path / "fdcuk_feature_completeness.json"
    manifest_path = tmp_path / "fdcuk_feature_suite.json"

    main(
        [
            str(csv_path),
            "--output-path",
            str(output_path),
            "--completeness-output-path",
            str(completeness_path),
            "--suite-manifest-output-path",
            str(manifest_path),
            "--max-rows",
            "2",
        ]
    )

    historical_slice = load_historical_recommendation_slice(output_path)
    completeness = HistoricalFeatureCompletenessResult.model_validate_json(
        completeness_path.read_text(encoding="utf-8")
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert historical_slice.metadata.slice_id == DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID
    assert completeness.passed is True
    assert bundle.manifest.suite_id == "football_data_co_uk_market_feature_sample_suite_v1"
    assert bundle.slices[0].metadata.slice_id == DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID
    assert loads(manifest_path.read_text(encoding="utf-8"))["slices"][0][
        "slice_path"
    ] == "fdcuk_feature_sample.json"


def test_football_data_co_uk_feature_batch_writes_multi_slice_suite(
    tmp_path: Path,
) -> None:
    epl_csv_path = _sample_csv(tmp_path / "europe" / "2425")
    la_liga_csv_path = _sample_csv(tmp_path / "europe" / "2425", file_name="SP1.csv")
    output_dir = tmp_path / "slices"
    completeness_dir = tmp_path / "reports"
    manifest_path = tmp_path / "football_data_co_uk_feature_suite.json"

    result = build_football_data_co_uk_prematch_feature_batch(
        [epl_csv_path, la_liga_csv_path],
        output_dir=output_dir,
        completeness_output_dir=completeness_dir,
        suite_manifest_path=manifest_path,
        options=FootballDataCoUkPrematchFeatureBatchOptions(max_rows_per_slice=2),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.summary_json["slice_count"] == 2
    assert result.summary_json["fixture_count"] == 4
    assert result.summary_json["failed_input_count"] == 0
    assert result.manifest.suite_id == "football_data_co_uk_market_feature_multi_season_suite_v1"
    assert {slice_item.metadata.competition_id for slice_item in bundle.slices} == {
        "EPL",
        "LA_LIGA",
    }
    assert {slice_item.metadata.season for slice_item in bundle.slices} == {
        "2024-2025",
    }
    assert loads(manifest_path.read_text(encoding="utf-8"))["slices"][0][
        "slice_path"
    ].startswith("slices/football_data_co_uk_")


def test_football_data_co_uk_feature_batch_recognizes_expanded_a_league_codes(
    tmp_path: Path,
) -> None:
    input_paths = [
        _sample_csv(tmp_path / "europe" / "2425", file_name=file_name)
        for file_name in ("N1.csv", "P1.csv", "E1.csv", "D2.csv", "I2.csv", "SP2.csv", "F2.csv")
    ]
    output_dir = tmp_path / "expanded_slices"
    completeness_dir = tmp_path / "expanded_reports"
    manifest_path = tmp_path / "expanded_suite.json"

    result = build_football_data_co_uk_prematch_feature_batch(
        input_paths,
        output_dir=output_dir,
        completeness_output_dir=completeness_dir,
        suite_manifest_path=manifest_path,
        options=FootballDataCoUkPrematchFeatureBatchOptions(max_rows_per_slice=1),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.summary_json["slice_count"] == 7
    assert result.summary_json["failed_input_count"] == 0
    assert {slice_item.metadata.competition_id for slice_item in bundle.slices} == {
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
        "NED_EREDIVISIE",
        "PRT_PRIMEIRA_LIGA",
    }
    assert {
        "football_data_co_uk_ned_eredivisie_2024_2025_market_features_v1",
        "football_data_co_uk_prt_primeira_liga_2024_2025_market_features_v1",
        "football_data_co_uk_eng_championship_2024_2025_market_features_v1",
    }.issubset({slice_item.metadata.slice_id for slice_item in bundle.slices})


def test_football_data_co_uk_feature_batch_cli_writes_suite(tmp_path: Path) -> None:
    epl_csv_path = _sample_csv(tmp_path / "europe" / "2425")
    bundesliga_csv_path = _sample_csv(tmp_path / "europe" / "2324", file_name="D1.csv")
    output_dir = tmp_path / "batch_slices"
    completeness_dir = tmp_path / "batch_reports"
    manifest_path = tmp_path / "batch_suite.json"

    batch_main(
        [
            str(epl_csv_path),
            str(bundesliga_csv_path),
            "--output-dir",
            str(output_dir),
            "--completeness-output-dir",
            str(completeness_dir),
            "--suite-manifest-output-path",
            str(manifest_path),
            "--max-rows-per-slice",
            "2",
        ]
    )

    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert len(bundle.slices) == 2
    assert {
        slice_item.metadata.slice_id for slice_item in bundle.slices
    } == {
        "football_data_co_uk_epl_2024_2025_market_features_v1",
        "football_data_co_uk_bundesliga_2023_2024_market_features_v1",
    }


def test_football_data_co_uk_feature_batch_writes_closing_only_source_seasons(
    tmp_path: Path,
) -> None:
    csv_path = _worldwide_closing_only_csv(tmp_path)
    output_dir = tmp_path / "j1_slices"
    completeness_dir = tmp_path / "j1_reports"
    manifest_path = tmp_path / "j1_suite.json"

    result = build_football_data_co_uk_prematch_feature_batch(
        [csv_path],
        output_dir=output_dir,
        completeness_output_dir=completeness_dir,
        suite_manifest_path=manifest_path,
        options=FootballDataCoUkPrematchFeatureBatchOptions(
            suite_id="j1_closing_only_suite",
            name="J1 closing-only suite",
            max_rows_per_slice=1,
            min_feature_data_quality_score=55.0,
            feature_source_kind="closing_only",
            source_seasons=("2021", "2022"),
        ),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.summary_json["slice_count"] == 2
    assert result.summary_json["feature_source_kind"] == "closing_only"
    assert {slice_item.metadata.season for slice_item in bundle.slices} == {
        "2021",
        "2022",
    }
    assert {
        slice_item.metadata.slice_id for slice_item in bundle.slices
    } == {
        "football_data_co_uk_jpn_j1_2021_closing_only_features_v1",
        "football_data_co_uk_jpn_j1_2022_closing_only_features_v1",
    }


def test_football_data_co_uk_feature_sample_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "data/historical_sources/football_data_co_uk/europe/2425/E0.csv",
            "--slice-id",
            "custom_fdcuk_feature_slice",
            "--name",
            "Custom FDCUK Feature Slice",
            "--competition-id",
            "CUSTOM",
            "--season",
            "2025",
            "--max-rows",
            "8",
            "--prediction-lead-minutes",
            "15",
            "--opening-snapshot-lead-days",
            "3",
            "--model-version",
            "model-test",
            "--feature-version",
            "feature-test",
            "--calibration-version",
            "calibration-test",
            "--feature-source-kind",
            "closing_only",
            "--prediction-time-policy",
            "slice_start",
            "--include-asian-handicap-features",
            "--source-season",
            "2024",
            "--min-feature-data-quality-score",
            "65",
        ]
    )

    options = _options_from_args(args)

    assert options.slice_id == "custom_fdcuk_feature_slice"
    assert options.name == "Custom FDCUK Feature Slice"
    assert options.competition_id == "CUSTOM"
    assert options.season == "2025"
    assert options.max_rows == 8
    assert options.prediction_lead_minutes == 15
    assert options.opening_snapshot_lead_days == 3
    assert options.model_version == "model-test"
    assert options.feature_version == "feature-test"
    assert options.calibration_version == "calibration-test"
    assert options.feature_source_kind == "closing_only"
    assert options.prediction_time_policy == "slice_start"
    assert options.include_asian_handicap_features is True
    assert options.source_seasons == ("2024",)


def test_football_data_co_uk_feature_batch_cli_args_map_to_options() -> None:
    args = _parse_batch_args(
        [
            "data/historical_sources/football_data_co_uk/europe/2425/E0.csv",
            "--output-dir",
            "tmp/slices",
            "--completeness-output-dir",
            "tmp/reports",
            "--suite-manifest-output-path",
            "tmp/suite.json",
            "--suite-id",
            "custom_suite",
            "--name",
            "Custom Suite",
            "--max-rows-per-slice",
            "5",
            "--prediction-lead-minutes",
            "12",
            "--opening-snapshot-lead-days",
            "4",
            "--model-version",
            "model-test",
            "--feature-version",
            "feature-test",
            "--calibration-version",
            "calibration-test",
            "--feature-source-kind",
            "closing_only",
            "--prediction-time-policy",
            "slice_start",
            "--include-asian-handicap-features",
            "--source-season",
            "2021",
            "--source-season",
            "2022",
            "--min-feature-data-quality-score",
            "68",
        ]
    )

    options = _batch_options_from_args(args)

    assert options.suite_id == "custom_suite"
    assert options.name == "Custom Suite"
    assert options.max_rows_per_slice == 5
    assert options.prediction_lead_minutes == 12
    assert options.opening_snapshot_lead_days == 4
    assert options.model_version == "model-test"
    assert options.feature_version == "feature-test"
    assert options.calibration_version == "calibration-test"
    assert options.feature_source_kind == "closing_only"
    assert options.prediction_time_policy == "slice_start"
    assert options.include_asian_handicap_features is True
    assert options.source_seasons == ("2021", "2022")
    assert options.min_feature_data_quality_score == 68


def _sample_csv(tmp_path: Path, *, file_name: str = "E0.csv") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / file_name
    csv_path.write_text(
        "\n".join(
            [
                "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,AvgH,AvgD,AvgA,"
                "AvgCH,AvgCD,AvgCA,AHh,AvgAHH,AvgAHA,AHCh,AvgCAHH,AvgCAHA",
                "E0,16/08/2024,20:00,Alpha,Bravo,2,0,H,2.00,3.40,4.20,"
                "1.80,3.55,4.80,-0.5,1.95,1.90,-0.75,1.88,2.02",
                "E0,17/08/2024,15:00,Charlie,Delta,1,1,D,2.50,3.10,2.90,"
                "2.70,3.00,2.75,0.25,1.91,1.93,0.0,1.87,2.05",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path


def _worldwide_closing_only_csv(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "JPN.csv"
    csv_path.write_text(
        "\n".join(
            [
                (
                    "Country,League,Season,Date,Time,Home,Away,HG,AG,Res,"
                    "AvgCH,AvgCD,AvgCA,MaxCH,MaxCD,MaxCA"
                ),
                (
                    "Japan,J1 League,2021,26/02/2021,10:00,"
                    "Kawasaki Frontale,Yokohama F Marinos,2,0,H,"
                    "1.72,3.95,4.70,1.78,4.00,4.90"
                ),
                (
                    "Japan,J1 League,2022,18/02/2022,10:00,"
                    "Kawasaki Frontale,FC Tokyo,1,0,H,"
                    "1.80,3.65,4.60,1.82,3.70,4.80"
                ),
                (
                    "Japan,J1 League,2022,19/02/2022,06:00,"
                    "Gamba Osaka,Kashima Antlers,1,3,A,"
                    "3.05,3.30,2.32,3.10,3.40,2.40"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path
