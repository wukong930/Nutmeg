from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_derived_market_candidates import (
    HistoricalDerivedMarketCandidateOptions,
    _options_from_args,
    _parse_args,
    build_historical_derived_market_candidate_slice,
    main,
)
from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditOptions,
    _LoadedCoverageSource,
    build_historical_sample_coverage_audit_report,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
    load_historical_recommendation_suite_manifest,
)


def test_derived_market_candidates_add_handicap_and_correct_score_predictions() -> None:
    result = build_historical_derived_market_candidate_slice(
        _base_slice(),
        options=HistoricalDerivedMarketCandidateOptions(
            cn_handicaps=(-1,),
            european_handicaps=(1,),
            correct_score_top_n=2,
            min_probability=0.0,
        ),
    )

    fixture = result.historical_slice.fixtures[0]
    generated_markets = [
        prediction.market_type
        for prediction in fixture.predictions
        if prediction.metadata_json.get("source")
        == "historical_derived_market_candidates"
    ]

    assert result.report.generated_prediction_count_by_market == {
        "cn_handicap_1x2": 3,
        "correct_score": 2,
        "european_handicap_1x2": 3,
    }
    assert result.report.lambda_source_counts == {
        "one_x_two_probability_shadow_heuristic": 1
    }
    assert generated_markets.count("cn_handicap_1x2") == 3
    assert generated_markets.count("european_handicap_1x2") == 3
    assert generated_markets.count("correct_score") == 2
    assert fixture.predictions[-1].metadata_json["dc_compatibility"] == {
        "score_grid_contract": "lambda_home/lambda_away -> score_probability_grid",
        "rho": None,
    }


def test_derived_market_candidates_make_historical_slice_dynamic_market_ready() -> None:
    result = build_historical_derived_market_candidate_slice(
        _base_slice(),
        options=HistoricalDerivedMarketCandidateOptions(
            cn_handicaps=(-1,),
            european_handicaps=(),
            correct_score_top_n=1,
        ),
    )

    audit = build_historical_sample_coverage_audit_report(
        [
            _LoadedCoverageSource(
                source_id="derived_slice",
                source_type="slice_paths",
                slices=[result.historical_slice],
            )
        ],
        options=HistoricalSampleCoverageAuditOptions(
            min_final_answer_fixture_count=1,
            min_dynamic_mixed_candidate_fixture_count=1,
            min_handicap_candidate_fixture_count=1,
            min_correct_score_candidate_fixture_count=1,
            min_feature_snapshot_coverage=0.0,
        ),
    )

    summary = audit.sources[0]

    assert summary.dynamic_mixed_candidate_fixture_count == 1
    assert summary.handicap_market_fixture_count == 1
    assert summary.correct_score_market_fixture_count == 1
    assert summary.readiness_json["dynamic_mixed_candidate_ready"] is True
    assert summary.readiness_json["handicap_candidate_ready"] is True
    assert summary.readiness_json["correct_score_candidate_ready"] is True


def test_derived_market_candidates_can_feed_historical_backtest_candidates() -> None:
    result = build_historical_derived_market_candidate_slice(
        _base_slice(),
        options=HistoricalDerivedMarketCandidateOptions(
            cn_handicaps=(-1,),
            european_handicaps=(),
            correct_score_top_n=1,
        ),
    )

    backtest = run_historical_recommendation_backtest(
        result.historical_slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            allowed_markets=("1x2", "cn_handicap_1x2", "correct_score"),
            min_probability=0.0,
            min_data_quality_score=0.0,
            max_candidates_per_fixture=8,
        ),
    )

    assert backtest.candidate_count > 3
    assert backtest.summary_json["eligible_candidate_count"] > 3
    assert backtest.final_answer is not None


def test_derived_market_candidates_cli_writes_slice_and_report(tmp_path: Path) -> None:
    source_path = tmp_path / "source.json"
    output_slice_path = tmp_path / "derived.json"
    report_path = tmp_path / "report.json"
    source_path.write_text(f"{_base_slice().model_dump_json(indent=2)}\n", encoding="utf-8")

    main(
        [
            str(source_path),
            "--output-slice-path",
            str(output_slice_path),
            "--report-output-path",
            str(report_path),
            "--cn-handicaps=-1",
            "--european-handicaps",
            "",
            "--correct-score-top-n",
            "1",
        ]
    )

    derived_slice = load_historical_recommendation_slice(output_slice_path)

    assert output_slice_path.exists()
    assert report_path.exists()
    assert derived_slice.metadata.slice_id.endswith("derived_markets_v1")
    assert "historical_derived_market_candidates" in report_path.read_text(
        encoding="utf-8"
    )


def test_derived_market_candidates_cli_writes_suite_manifest(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    manifest_path = tmp_path / "source_suite.json"
    output_slice_dir = tmp_path / "derived_slices"
    output_manifest_path = tmp_path / "derived_suite.json"
    report_path = tmp_path / "suite_report.json"
    first_path.write_text(f"{_base_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    second_slice = _base_slice().model_copy(
        update={
            "metadata": _base_slice().metadata.model_copy(
                update={"slice_id": "unit_derived_market_source_two"}
            )
        }
    )
    second_path.write_text(f"{second_slice.model_dump_json(indent=2)}\n", encoding="utf-8")
    manifest = HistoricalRecommendationSuiteManifest(
        suite_id="unit_source_suite",
        name="Unit source suite",
        slices=[
            HistoricalRecommendationSuiteManifestSlice(slice_path=first_path.name),
            HistoricalRecommendationSuiteManifestSlice(slice_path=second_path.name),
        ],
    )
    manifest_path.write_text(f"{manifest.model_dump_json(indent=2)}\n", encoding="utf-8")

    main(
        [
            "--suite-manifest",
            str(manifest_path),
            "--output-slice-dir",
            str(output_slice_dir),
            "--output-suite-manifest-path",
            str(output_manifest_path),
            "--report-output-path",
            str(report_path),
            "--cn-handicaps=-1",
            "--european-handicaps",
            "",
            "--correct-score-top-n",
            "1",
        ]
    )

    output_manifest = load_historical_recommendation_suite_manifest(output_manifest_path)
    report_text = report_path.read_text(encoding="utf-8")

    assert output_manifest.suite_id == "unit_source_suite_derived_markets_v1"
    assert len(output_manifest.slices) == 2
    assert all("derived_slices" in entry.slice_path for entry in output_manifest.slices)
    assert len(list(output_slice_dir.glob("*.json"))) == 2
    assert "historical_derived_market_candidate_suite" in report_text


def test_derived_market_candidates_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-slice-path",
            "tmp/derived.json",
            "--report-output-path",
            "tmp/report.json",
            "--derivation-id",
            "unit-derived",
            "--output-slice-id-suffix",
            "shadow_v1",
            "--cn-handicaps=-1,1",
            "--european-handicaps",
            "0",
            "--correct-score-top-n",
            "3",
            "--max-goals",
            "7",
            "--min-probability",
            "0.02",
            "--market-margin",
            "0.05",
            "--replace-existing",
        ]
    )

    options = _options_from_args(args)

    assert args.output_slice_path == Path("tmp/derived.json")
    assert args.report_output_path == Path("tmp/report.json")
    assert options.derivation_id == "unit-derived"
    assert options.output_slice_id_suffix == "shadow_v1"
    assert options.cn_handicaps == (-1, 1)
    assert options.european_handicaps == (0,)
    assert options.correct_score_top_n == 3
    assert options.max_goals == 7
    assert options.min_probability == 0.02
    assert options.market_margin == 0.05
    assert options.preserve_existing is False


def _base_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="unit_derived_market_source",
            name="Unit derived market source",
            competition_id="TEST",
            season="2024",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test 1x2 predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 1, 10),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_a",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 2, 12),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=2,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 1, 9),
                model_version="poisson-v3.1-derived-test",
                predictions=[
                    _prediction("home_win", 0.54),
                    _prediction("draw", 0.26),
                    _prediction("away_win", 0.20),
                ],
            )
        ],
    )


def _prediction(outcome: str, probability: float) -> HistoricalMarketPrediction:
    return HistoricalMarketPrediction(
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=1.0 / probability,
        market_probability=probability,
        data_quality_score=90,
        model_confidence_score=0.80,
        calibration_score=0.78,
        odds_stability_score=0.75,
        volatility_penalty=0.08,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
