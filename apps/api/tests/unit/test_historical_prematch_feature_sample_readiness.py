from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessOptions,
    _coverage_audit_options_from_args,
    _options_from_args,
    _parse_args,
    build_historical_prematch_feature_sample_readiness_report,
    load_historical_prematch_feature_sample_readiness_report,
    main,
)
from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditReport,
    HistoricalSampleCoverageSourceSummary,
)


def test_prematch_feature_sample_readiness_accepts_market_movement_source() -> None:
    report = build_historical_prematch_feature_sample_readiness_report(
        _coverage_audit_report(
            sources=[
                _source_summary(
                    source_id="market_feature_suite",
                    fixture_count=600,
                    slice_count=25,
                    competition_ids=["EPL", "ESP_LA_LIGA", "JPN_J1"],
                    season_ids=["2022-2023", "2023-2024"],
                    competition_season_keys=[
                        "EPL:2022-2023",
                        "ESP_LA_LIGA:2023-2024",
                        "JPN_J1:2024",
                    ],
                    feature_snapshot_count=600,
                    odds_time_series_feature_count=560,
                    source_ref_count=600,
                    readiness_json={
                        "final_answer_sample_ready": True,
                        "feature_snapshot_ready": True,
                        "market_movement_feature_ready": True,
                        "context_signal_ready": False,
                        "full_prematch_context_ready": False,
                    },
                )
            ]
        ),
        options=HistoricalPrematchFeatureSampleReadinessOptions(
            target_profile="market_movement",
            min_ready_fixture_count=500,
            min_ready_competition_count=3,
            min_ready_season_count=2,
            min_ready_competition_season_count=3,
            min_source_ref_coverage=1.0,
        ),
    )

    assert report.status == "accepted"
    assert report.sample_ready_allowed is True
    assert report.shadow_allowed is True
    assert report.ready_source_ids == ["market_feature_suite"]
    assert report.ready_fixture_count == 600
    assert report.ready_competition_count == 3
    assert report.sources[0].failed_check_names == []


def test_prematch_feature_sample_readiness_shadows_market_source_for_full_context() -> None:
    report = build_historical_prematch_feature_sample_readiness_report(
        _coverage_audit_report(
            sources=[
                _source_summary(
                    source_id="market_only_suite",
                    fixture_count=240,
                    feature_snapshot_count=240,
                    odds_time_series_feature_count=220,
                    source_ref_count=240,
                    lineup_feature_count=0,
                    availability_feature_count=0,
                    semantic_signal_feature_count=0,
                    readiness_json={
                        "final_answer_sample_ready": True,
                        "feature_snapshot_ready": True,
                        "market_movement_feature_ready": True,
                        "context_signal_ready": False,
                        "full_prematch_context_ready": False,
                    },
                )
            ]
        ),
        options=HistoricalPrematchFeatureSampleReadinessOptions(
            target_profile="full_prematch_context",
            min_ready_fixture_count=100,
            min_ready_competition_count=1,
            min_ready_season_count=1,
            min_ready_competition_season_count=1,
        ),
    )

    failed_names = set(report.sources[0].failed_check_names)

    assert report.status == "shadow_only"
    assert report.sample_ready_allowed is False
    assert report.shadow_allowed is True
    assert "target_readiness" in failed_names
    assert "lineup_coverage" in failed_names
    assert "availability_coverage" in failed_names
    assert "semantic_signal_coverage" in failed_names
    assert "ready_source_count" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_prematch_feature_sample_readiness_rejects_empty_source() -> None:
    report = build_historical_prematch_feature_sample_readiness_report(
        _coverage_audit_report(
            sources=[
                _source_summary(
                    source_id="empty_source",
                    fixture_count=0,
                    complete_1x2_fixture_count=0,
                    feature_snapshot_count=0,
                    odds_time_series_feature_count=0,
                    source_ref_count=0,
                    readiness_json={
                        "final_answer_sample_ready": False,
                        "feature_snapshot_ready": False,
                        "market_movement_feature_ready": False,
                        "context_signal_ready": False,
                        "full_prematch_context_ready": False,
                    },
                )
            ]
        ),
        options=HistoricalPrematchFeatureSampleReadinessOptions(
            target_profile="market_movement",
            min_ready_fixture_count=1,
        ),
    )

    assert report.status == "rejected"
    assert report.sample_ready_allowed is False
    assert report.shadow_allowed is False
    assert report.sources[0].status == "rejected"


def test_prematch_feature_sample_readiness_loads_and_cli_writes_report(
    tmp_path: Path,
    capsys,
) -> None:
    coverage_report = _coverage_audit_report(
        sources=[
            _source_summary(
                source_id="market_feature_suite",
                fixture_count=120,
                slice_count=5,
                feature_snapshot_count=120,
                odds_time_series_feature_count=110,
                source_ref_count=120,
                readiness_json={
                    "final_answer_sample_ready": True,
                    "feature_snapshot_ready": True,
                    "market_movement_feature_ready": True,
                    "context_signal_ready": False,
                    "full_prematch_context_ready": False,
                },
            )
        ]
    )
    coverage_path = tmp_path / "coverage_audit.json"
    output_path = tmp_path / "sample_readiness.json"
    coverage_path.write_text(
        f"{coverage_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--coverage-audit-report-path",
            str(coverage_path),
            "--output-path",
            str(output_path),
            "--target-profile",
            "market_movement",
            "--min-ready-fixture-count",
            "100",
            "--min-source-ref-coverage",
            "1.0",
        ]
    )

    printed = loads(capsys.readouterr().out)
    loaded = load_historical_prematch_feature_sample_readiness_report(output_path)

    assert output_path.exists()
    assert printed["readiness_key"] == loaded.readiness_key
    assert loaded.status == "accepted"
    assert loaded.coverage_audit_report_path == coverage_path


def test_prematch_feature_sample_readiness_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--coverage-audit-report-path",
            "tmp/coverage.json",
            "--output-path",
            "tmp/readiness.json",
            "--readiness-id",
            "sample-readiness-test",
            "--target-profile",
            "full_prematch_context",
            "--min-ready-source-count",
            "2",
            "--min-ready-fixture-count",
            "500",
            "--min-ready-slice-count",
            "4",
            "--min-ready-competition-count",
            "3",
            "--min-ready-season-count",
            "2",
            "--min-ready-competition-season-count",
            "5",
            "--min-complete-1x2-coverage",
            "0.99",
            "--min-feature-snapshot-coverage",
            "0.98",
            "--min-odds-time-series-coverage",
            "0.75",
            "--min-lineup-coverage",
            "0.65",
            "--min-availability-coverage",
            "0.55",
            "--min-semantic-signal-coverage",
            "0.45",
            "--min-source-ref-coverage",
            "0.85",
            "--min-average-feature-data-quality-score",
            "70",
            "--min-feature-data-quality-score",
            "50",
            "--max-source-warning-count",
            "2",
            "--max-report-warning-count",
            "3",
            "--baseline-source-index",
            "1",
            "--min-final-answer-fixture-count",
            "10",
        ]
    )

    options = _options_from_args(args)
    coverage_options = _coverage_audit_options_from_args(args)

    assert args.output_path == Path("tmp/readiness.json")
    assert options.readiness_id == "sample-readiness-test"
    assert options.target_profile == "full_prematch_context"
    assert options.min_ready_source_count == 2
    assert options.min_ready_fixture_count == 500
    assert options.min_ready_slice_count == 4
    assert options.min_ready_competition_count == 3
    assert options.min_ready_season_count == 2
    assert options.min_ready_competition_season_count == 5
    assert options.min_complete_1x2_coverage == 0.99
    assert options.min_feature_snapshot_coverage == 0.98
    assert options.min_odds_time_series_coverage == 0.75
    assert options.min_lineup_coverage == 0.65
    assert options.min_availability_coverage == 0.55
    assert options.min_semantic_signal_coverage == 0.45
    assert options.min_source_ref_coverage == 0.85
    assert options.min_average_feature_data_quality_score == 70
    assert options.min_feature_data_quality_score == 50
    assert options.max_source_warning_count == 2
    assert options.max_report_warning_count == 3
    assert coverage_options.baseline_source_index == 1
    assert coverage_options.min_final_answer_fixture_count == 10


def _coverage_audit_report(
    *,
    sources: list[HistoricalSampleCoverageSourceSummary],
) -> HistoricalSampleCoverageAuditReport:
    return HistoricalSampleCoverageAuditReport(
        audit_key="historical_sample_coverage_audit:test",
        audit_id="coverage-test",
        status="generated",
        source_count=len(sources),
        slice_count=sum(source.slice_count for source in sources),
        fixture_count=sum(source.fixture_count for source in sources),
        sources=sources,
        cross_source_gaps=[],
        warnings=[],
        summary_json={
            "calculation_basis": "historical_sample_coverage_audit_v3_1",
            "source_ids": [source.source_id for source in sources],
        },
    )


def _source_summary(
    *,
    source_id: str,
    fixture_count: int,
    slice_count: int = 1,
    competition_ids: list[str] | None = None,
    season_ids: list[str] | None = None,
    competition_season_keys: list[str] | None = None,
    complete_1x2_fixture_count: int | None = None,
    feature_snapshot_count: int = 0,
    prematch_context_count: int | None = None,
    lineup_feature_count: int | None = None,
    availability_feature_count: int | None = None,
    odds_movement_feature_count: int | None = None,
    odds_time_series_feature_count: int = 0,
    semantic_signal_feature_count: int | None = None,
    source_ref_count: int = 0,
    readiness_json: dict[str, bool] | None = None,
) -> HistoricalSampleCoverageSourceSummary:
    resolved_competitions = competition_ids or ["EPL"]
    resolved_seasons = season_ids or ["2024-2025"]
    resolved_competition_seasons = competition_season_keys or ["EPL:2024-2025"]
    resolved_complete_1x2_count = (
        complete_1x2_fixture_count
        if complete_1x2_fixture_count is not None
        else fixture_count
    )
    resolved_prematch_context_count = (
        prematch_context_count
        if prematch_context_count is not None
        else feature_snapshot_count
    )
    resolved_lineup_count = (
        lineup_feature_count
        if lineup_feature_count is not None
        else feature_snapshot_count
    )
    resolved_availability_count = (
        availability_feature_count
        if availability_feature_count is not None
        else feature_snapshot_count
    )
    resolved_odds_movement_count = (
        odds_movement_feature_count
        if odds_movement_feature_count is not None
        else odds_time_series_feature_count
    )
    resolved_semantic_count = (
        semantic_signal_feature_count
        if semantic_signal_feature_count is not None
        else feature_snapshot_count
    )
    return HistoricalSampleCoverageSourceSummary(
        source_id=source_id,
        source_type="slice_paths",
        source_path=None,
        slice_count=slice_count,
        fixture_count=fixture_count,
        complete_1x2_fixture_count=resolved_complete_1x2_count,
        feature_snapshot_count=feature_snapshot_count,
        prematch_context_count=resolved_prematch_context_count,
        lineup_feature_count=resolved_lineup_count,
        availability_feature_count=resolved_availability_count,
        odds_movement_feature_count=resolved_odds_movement_count,
        odds_time_series_feature_count=odds_time_series_feature_count,
        semantic_signal_feature_count=resolved_semantic_count,
        source_ref_count=source_ref_count,
        feature_snapshot_coverage=_coverage(feature_snapshot_count, fixture_count),
        complete_1x2_coverage=_coverage(resolved_complete_1x2_count, fixture_count),
        prematch_context_coverage=_coverage(
            resolved_prematch_context_count,
            fixture_count,
        ),
        lineup_coverage=_coverage(resolved_lineup_count, fixture_count),
        availability_coverage=_coverage(resolved_availability_count, fixture_count),
        odds_movement_coverage=_coverage(
            resolved_odds_movement_count,
            fixture_count,
        ),
        odds_time_series_coverage=_coverage(
            odds_time_series_feature_count,
            fixture_count,
        ),
        semantic_signal_coverage=_coverage(resolved_semantic_count, fixture_count),
        source_ref_coverage=_coverage(source_ref_count, fixture_count),
        minimum_feature_data_quality_score=80.0 if feature_snapshot_count else None,
        average_feature_data_quality_score=82.0 if feature_snapshot_count else None,
        competition_ids=resolved_competitions,
        season_ids=resolved_seasons,
        competition_season_keys=resolved_competition_seasons,
        competition_fixture_counts={
            competition_id: fixture_count for competition_id in resolved_competitions
        },
        season_fixture_counts={season_id: fixture_count for season_id in resolved_seasons},
        readiness_json=readiness_json or {},
        warnings=[],
        summary_json={
            "competition_ids": resolved_competitions,
            "season_ids": resolved_seasons,
            "competition_season_keys": resolved_competition_seasons,
        },
    )


def _coverage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator
