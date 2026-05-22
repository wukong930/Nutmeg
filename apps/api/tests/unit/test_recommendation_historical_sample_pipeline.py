from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalRecommendationSamplePipelineBuildDefaults,
    HistoricalRecommendationSamplePipelineOptions,
    HistoricalRecommendationSuiteManifestRefreshOptions,
    load_historical_recommendation_suite_manifest_bundle,
    run_historical_recommendation_sample_pipeline,
)
from nutmeg.recommendations.historical_backtest import HistoricalRecommendationBacktestOptions
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.historical_sample_pipeline import _options_from_args, _parse_args


def test_historical_sample_pipeline_builds_registers_and_runs_gate(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)
    output_dir = tmp_path / "generated_slices"

    result = run_historical_recommendation_sample_pipeline(
        [
            Path(
                "configs/recommendations/historical_slice_inputs/"
                "euro_2024_knockout_sample.csv"
            )
        ],
        options=HistoricalRecommendationSamplePipelineOptions(
            output_dir=output_dir,
            manifest_path=manifest_path,
            build_defaults=_build_defaults(slice_id_prefix="pipeline"),
            manifest_refresh_options=HistoricalRecommendationSuiteManifestRefreshOptions(
                tags=("pipeline", "builder"),
                notes=("registered by sample pipeline",),
                write=True,
            ),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                max_budget=4.0,
            ),
            gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                min_final_hit_sample_size=2,
            ),
        ),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.build_count == 1
    assert result.builds[0].slice_id == "pipeline_euro_2024_knockout_sample"
    assert result.builds[0].output_slice_path.exists()
    assert result.manifest_refresh_result.added_count == 1
    assert result.gate_result is not None
    assert result.gate_result.passed is True
    assert result.suite_result is not None
    assert result.suite_result.slice_count == 2
    assert result.summary_json["gate_passed"] is True
    assert bundle.manifest.slices[1].tags == ["pipeline", "builder"]


def test_historical_sample_pipeline_can_skip_gate(tmp_path: Path) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)

    result = run_historical_recommendation_sample_pipeline(
        [
            Path(
                "configs/recommendations/historical_slice_inputs/"
                "euro_2024_knockout_sample.csv"
            )
        ],
        options=HistoricalRecommendationSamplePipelineOptions(
            output_dir=tmp_path / "generated_slices",
            manifest_path=manifest_path,
            build_defaults=_build_defaults(slice_id_prefix="skip_gate"),
            manifest_refresh_options=HistoricalRecommendationSuiteManifestRefreshOptions(
                write=False,
            ),
            run_gate=False,
        ),
    )

    assert result.gate_result is None
    assert result.suite_result is None
    assert result.summary_json["gate_passed"] is None
    assert result.summary_json["sample_quality_passed"] is True
    assert result.manifest_refresh_result.added_count == 1


def test_historical_sample_pipeline_blocks_manifest_write_on_quality_failure(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)
    before = manifest_path.read_text(encoding="utf-8")
    bad_csv_path = _write_incomplete_csv(tmp_path)

    result = run_historical_recommendation_sample_pipeline(
        [bad_csv_path],
        options=HistoricalRecommendationSamplePipelineOptions(
            output_dir=tmp_path / "generated_slices",
            manifest_path=manifest_path,
            build_defaults=_build_defaults(slice_id_prefix="bad_quality"),
            manifest_refresh_options=HistoricalRecommendationSuiteManifestRefreshOptions(
                write=True,
            ),
        ),
    )

    assert result.summary_json["sample_quality_passed"] is False
    assert result.summary_json["manifest_write_suppressed"] is True
    assert result.summary_json["gate_skipped_for_sample_quality"] is True
    assert result.gate_result is None
    assert result.suite_result is None
    assert result.manifest_refresh_result.summary_json["write"] is False
    assert "historical_sample_pipeline:sample_quality_failed" in result.warnings
    assert "historical_sample_pipeline:manifest_write_suppressed" in result.warnings
    assert manifest_path.read_text(encoding="utf-8") == before


def test_historical_sample_pipeline_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv",
            "--output-dir",
            "tmp/generated_slices",
            "--manifest-path",
            "tmp/suite.json",
            "--competition-id",
            "UEFA_EURO",
            "--as-of-time-utc",
            "2024-06-29T12:00:00Z",
            "--season",
            "2024",
            "--result-source",
            "unit test results",
            "--odds-source",
            "unit test odds",
            "--prediction-source",
            "unit test predictions",
            "--source-url",
            "https://example.test/results",
            "--note",
            "pipeline note",
            "--slice-id-prefix",
            "pipeline",
            "--name-prefix",
            "Pipeline",
            "--manifest-tag",
            "pipeline",
            "--manifest-note",
            "registered by pipeline",
            "--write-manifest",
            "--min-sample-fixture-count",
            "2",
            "--allow-incomplete-1x2",
            "--sample-probability-sum-tolerance",
            "0.05",
            "--require-market-probability",
            "--min-sample-data-quality-score",
            "75",
            "--allow-sample-quality-failures",
            "--pass-types",
            "2x1,4x1",
            "--modes",
            "single",
            "--max-budget",
            "12",
            "--min-final-hit-sample-size",
            "3",
            "--skip-gate",
        ]
    )

    options = _options_from_args(args)

    assert options.output_dir == Path("tmp/generated_slices")
    assert options.manifest_path == Path("tmp/suite.json")
    assert options.build_defaults.slice_id_prefix == "pipeline"
    assert options.build_defaults.name_prefix == "Pipeline"
    assert options.build_defaults.as_of_time_utc == datetime(2024, 6, 29, 12, tzinfo=UTC)
    assert options.build_defaults.source_urls == ("https://example.test/results",)
    assert options.build_defaults.notes == ("pipeline note",)
    assert options.manifest_refresh_options.tags == ("pipeline",)
    assert options.manifest_refresh_options.notes == ("registered by pipeline",)
    assert options.manifest_refresh_options.write is True
    assert options.sample_quality_options.min_fixture_count == 2
    assert options.sample_quality_options.require_1x2_complete is False
    assert options.sample_quality_options.probability_sum_tolerance == 0.05
    assert options.sample_quality_options.require_market_probability is True
    assert options.sample_quality_options.min_data_quality_score == 75
    assert options.allow_sample_quality_failures is True
    assert options.backtest_options.pass_types == ("2x1", "4x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.max_budget == 12
    assert options.gate_options.min_final_hit_sample_size == 3
    assert options.run_gate is False


def _build_defaults(
    *,
    slice_id_prefix: str,
) -> HistoricalRecommendationSamplePipelineBuildDefaults:
    return HistoricalRecommendationSamplePipelineBuildDefaults(
        competition_id="UEFA_EURO",
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
        season="2024",
        result_source="unit test results",
        odds_source="unit test odds",
        prediction_source="unit test predictions",
        source_urls=("https://example.test/results",),
        notes=("pipeline generated sample",),
        slice_id_prefix=slice_id_prefix,
        name_prefix="Pipeline",
    )


def _write_tmp_manifest(tmp_path: Path) -> Path:
    sample_slice_path = Path(
        "configs/recommendations/historical_slices/euro_2024_knockout_sample.json"
    ).resolve()
    manifest_path = tmp_path / "suite.json"
    manifest_path.write_text(
        (
            "{\n"
            '  "manifest_version": "v1",\n'
            '  "suite_id": "tmp_pipeline_suite_v1",\n'
            '  "name": "Temporary pipeline suite",\n'
            '  "slices": [\n'
            "    {\n"
            f'      "slice_path": "{sample_slice_path.as_posix()}",\n'
            '      "enabled": true,\n'
            '      "tags": ["existing"],\n'
            '      "notes": []\n'
            "    }\n"
            "  ]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_incomplete_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "incomplete_1x2.csv"
    csv_path.write_text(
        (
            "fixture_id,competition_id,kickoff_time_utc,home_team_name,away_team_name,"
            "actual_home_goals,actual_away_goals,prediction_time_utc,model_version,"
            "market_type,outcome,probability,decimal_odds,market_probability\n"
            "bad_fixture,UEFA_EURO,2024-06-29T19:00:00Z,Germany,Denmark,2,0,"
            "2024-06-29T10:00:00Z,poisson-test,1x2,home_win,0.62,1.62,0.62\n"
        ),
        encoding="utf-8",
    )
    return csv_path
