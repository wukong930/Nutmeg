from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import loads
from typing import Literal

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_rolling_admission import (
    HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_risk_filter_rolling_admission_report,
    main,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentGateOptions,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_market_movement_risk_filter_rolling_admission_accepts_stable_segment() -> None:
    report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [_away_movement_slice()],
        options=_admission_options(),
        sample_readiness_report=_sample_readiness_report(),
    )

    assert report.status == "accepted"
    assert report.risk_filter_allowed is True
    assert report.shadow_allowed is True
    assert report.sample_readiness_status == "accepted"
    assert report.overall_fold.passed_segment_gate is True
    assert report.overall_fold.accepted_count == 1
    assert report.overall_fold.adjusted_fixture_count == 3
    assert report.failed_fold_count == 0
    assert report.active_competition_fold_count == 1
    assert report.active_season_cutoff_fold_count == 1
    assert report.active_rolling_fold_count == 1


def test_market_movement_risk_filter_rolling_admission_shadows_when_fold_coverage_is_thin() -> None:
    report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [_away_movement_slice()],
        options=_admission_options(min_active_competition_fold_count=2),
        sample_readiness_report=_sample_readiness_report(),
    )

    assert report.status == "shadow_only"
    assert report.risk_filter_allowed is False
    assert report.shadow_allowed is True
    assert "active_competition_fold_count" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_market_movement_risk_filter_rolling_admission_shadows_when_sample_is_not_ready() -> None:
    report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [_away_movement_slice()],
        options=_admission_options(require_sample_readiness=True),
        sample_readiness_report=_sample_readiness_report(
            status="shadow_only",
            sample_ready_allowed=False,
            shadow_allowed=True,
        ),
    )

    assert report.status == "shadow_only"
    assert report.risk_filter_allowed is False
    assert report.shadow_allowed is True
    assert report.sample_readiness_status == "shadow_only"
    assert "market_movement_sample_readiness_accepted" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_market_movement_risk_filter_rolling_admission_rejects_when_overall_gate_fails() -> None:
    report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [_away_movement_slice()],
        options=_admission_options(segment_group_keys=("missing:segment",)),
        sample_readiness_report=_sample_readiness_report(),
    )

    assert report.status == "rejected"
    assert report.risk_filter_allowed is False
    assert report.shadow_allowed is False
    assert report.overall_fold.passed_segment_gate is False
    assert report.overall_fold.accepted_count == 0
    assert "overall_segment_gate_passed" in {
        check.name for check in report.checks if check.status == "failed"
    }


def test_market_movement_risk_filter_rolling_admission_cli_writes_report(
    tmp_path,
    capsys,
) -> None:
    historical_slice = _away_movement_slice()
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "rolling_admission.json"
    sample_readiness_path = tmp_path / "sample_readiness.json"
    slice_path.write_text(
        f"{historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    sample_readiness_path.write_text(
        f"{_sample_readiness_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(slice_path),
            "--sample-readiness-report-path",
            str(sample_readiness_path),
            "--require-sample-readiness",
            "--segment-group-keys",
            "competition_outcome:TEST:away_win",
            "--movement-weight",
            "1.0",
            "--max-probability-shift",
            "0.20",
            "--pass-types",
            "1x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "solver",
            "--unit-stake",
            "2",
            "--max-budget",
            "4",
            "--fail-on-suite-statuses",
            "",
            "--min-final-hit-rate-delta",
            "-1.0",
            "--max-brier-score-delta",
            "1.0",
            "--max-log-loss-delta",
            "1.0",
            "--max-mean-calibration-error-delta",
            "1.0",
            "--rolling-window-season-count",
            "1",
            "--output-path",
            str(output_path),
        ]
    )

    printed = loads(capsys.readouterr().out)
    payload = loads(output_path.read_text(encoding="utf-8"))
    assert printed["report_key"] == payload["report_key"]
    assert payload["status"] == "accepted"
    assert payload["risk_filter_allowed"] is True
    assert payload["sample_readiness_status"] == "accepted"


def test_market_movement_risk_filter_rolling_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/"
            "football_data_co_uk_market_features_multi/"
            "football_data_co_uk_epl_2024_2025_market_features_v1.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/"
            "football_data_co_uk_market_feature_multi_season_suite.json",
            "--segment-gate-report-path",
            "tmp/segment_gate.json",
            "--sample-readiness-report-path",
            "tmp/sample_readiness.json",
            "--output-path",
            "tmp/rolling.json",
            "--rolling-admission-id",
            "risk-filter-admission-test",
            "--gate-id",
            "segment-gate-test",
            "--segment-group-keys",
            "competition_outcome:EPL:away_win,delta_band:0.03:0.06",
            "--top-positive-segment-limit",
            "7",
            "--min-segment-sample-size",
            "12",
            "--max-segment-brier-delta",
            "-0.01",
            "--max-segment-log-loss-delta",
            "-0.02",
            "--max-segment-calibration-error-delta",
            "0.03",
            "--min-segment-closing-improved-rate",
            "0.55",
            "--movement-weight",
            "0.75",
            "--max-probability-shift",
            "0.12",
            "--min-single-match-sample-size",
            "9",
            "--min-single-match-hit-rate-delta",
            "0.01",
            "--max-single-match-brier-delta",
            "-0.001",
            "--max-single-match-log-loss-delta",
            "-0.002",
            "--min-abs-probability-delta",
            "0.02",
            "--movement-direction-epsilon",
            "0.004",
            "--delta-bands",
            "0.00:0.02,0.02:0.05,0.05:",
            "--opening-probability-bands",
            "0.00:0.30,0.30:0.60,0.60:1.00",
            "--min-diagnostics-group-sample-size",
            "5",
            "--no-include-competition-groups",
            "--observation-sample-limit",
            "7",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--unit-stake",
            "5",
            "--max-budget",
            "30",
            "--min-probability",
            "0.22",
            "--min-data-quality-score",
            "72",
            "--candidate-fixture-limit",
            "8",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "1",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "heuristic",
            "--min-slice-count",
            "2",
            "--min-comparison-count",
            "2",
            "--min-final-hit-sample-size",
            "2",
            "--min-candidate-final-hit-rate",
            "0.51",
            "--min-candidate-roi",
            "-0.25",
            "--fail-on-suite-statuses",
            "regressed",
            "--min-final-hit-rate-delta",
            "0.02",
            "--min-roi-delta",
            "0.03",
            "--min-profit-loss-delta",
            "1.5",
            "--max-brier-score-delta",
            "-0.001",
            "--max-log-loss-delta",
            "-0.002",
            "--max-mean-calibration-error-delta",
            "0.01",
            "--min-final-answer-changed-count",
            "1",
            "--max-warning-count",
            "4",
            "--min-overall-candidate-count",
            "4",
            "--min-overall-accepted-count",
            "3",
            "--min-overall-adjusted-fixture-count",
            "11",
            "--no-require-overall-best-candidate-accepted",
            "--min-fold-slice-count",
            "2",
            "--min-fold-fixture-count",
            "8",
            "--min-fold-candidate-count",
            "2",
            "--min-fold-accepted-count",
            "1",
            "--min-fold-adjusted-fixture-count",
            "5",
            "--no-require-fold-best-candidate-accepted",
            "--max-failed-fold-count",
            "1",
            "--min-active-competition-fold-count",
            "2",
            "--min-active-season-cutoff-fold-count",
            "3",
            "--min-active-rolling-fold-count",
            "4",
            "--rolling-window-season-count",
            "5",
            "--rolling-window-step",
            "2",
            "--max-report-folds",
            "40",
            "--require-sample-readiness",
            "--allow-sample-readiness-shadow-only",
        ]
    )

    options = _options_from_args(args)
    segment_options = options.segment_gate_options

    assert options.admission_id == "risk-filter-admission-test"
    assert options.sample_readiness_report_path is not None
    assert str(options.sample_readiness_report_path).endswith("sample_readiness.json")
    assert options.require_sample_readiness is True
    assert options.require_sample_ready_allowed is False
    assert segment_options.gate_id == "segment-gate-test"
    assert segment_options.segment_group_keys == (
        "competition_outcome:EPL:away_win",
        "delta_band:0.03:0.06",
    )
    assert segment_options.top_positive_segment_limit == 7
    assert segment_options.min_segment_sample_size == 12
    assert segment_options.max_segment_brier_delta == -0.01
    assert segment_options.max_segment_log_loss_delta == -0.02
    assert segment_options.max_segment_calibration_error_delta == 0.03
    assert segment_options.min_segment_closing_improved_rate == 0.55
    assert segment_options.movement_weight == 0.75
    assert segment_options.max_probability_shift == 0.12
    assert segment_options.min_single_match_sample_size == 9
    assert segment_options.min_single_match_hit_rate_delta == 0.01
    assert segment_options.max_single_match_brier_delta == -0.001
    assert segment_options.max_single_match_log_loss_delta == -0.002
    assert segment_options.diagnostics_options.min_abs_probability_delta == 0.02
    assert segment_options.diagnostics_options.movement_direction_epsilon == 0.004
    assert segment_options.diagnostics_options.delta_bands == (
        "0.00:0.02",
        "0.02:0.05",
        "0.05:",
    )
    assert segment_options.diagnostics_options.opening_probability_bands == (
        "0.00:0.30",
        "0.30:0.60",
        "0.60:1.00",
    )
    assert segment_options.diagnostics_options.min_group_sample_size == 5
    assert segment_options.diagnostics_options.include_competition_groups is False
    assert segment_options.diagnostics_options.observation_sample_limit == 7
    assert segment_options.backtest_options.pass_types == ("1x1", "2x1")
    assert segment_options.backtest_options.modes == ("single",)
    assert segment_options.backtest_options.strategy == "value_first"
    assert segment_options.backtest_options.unit_stake == 5
    assert segment_options.backtest_options.max_budget == 30
    assert segment_options.backtest_options.min_probability == 0.22
    assert segment_options.backtest_options.min_data_quality_score == 72
    assert segment_options.backtest_options.candidate_fixture_limit == 8
    assert segment_options.backtest_options.max_candidates_per_fixture == 2
    assert segment_options.backtest_options.scenario_candidate_fixture_buffer == 1
    assert segment_options.backtest_options.derive_market_context_signals is True
    assert segment_options.backtest_options.optimizer_profile == "heuristic"
    assert segment_options.quality_gate_options.min_slice_count == 2
    assert segment_options.quality_gate_options.min_comparison_count == 2
    assert segment_options.quality_gate_options.min_final_hit_sample_size == 2
    assert segment_options.quality_gate_options.min_candidate_final_hit_rate == 0.51
    assert segment_options.quality_gate_options.min_candidate_roi == -0.25
    assert segment_options.quality_gate_options.fail_on_suite_statuses == ("regressed",)
    assert segment_options.quality_gate_options.min_final_hit_rate_delta == 0.02
    assert segment_options.quality_gate_options.min_roi_delta == 0.03
    assert segment_options.quality_gate_options.min_profit_loss_delta == 1.5
    assert segment_options.quality_gate_options.max_brier_score_delta == -0.001
    assert segment_options.quality_gate_options.max_log_loss_delta == -0.002
    assert (
        segment_options.quality_gate_options.max_mean_calibration_error_delta == 0.01
    )
    assert segment_options.quality_gate_options.min_final_answer_changed_count == 1
    assert segment_options.quality_gate_options.max_warning_count == 4
    assert options.min_overall_candidate_count == 4
    assert options.min_overall_accepted_count == 3
    assert options.min_overall_adjusted_fixture_count == 11
    assert options.require_overall_best_candidate_accepted is False
    assert options.min_fold_slice_count == 2
    assert options.min_fold_fixture_count == 8
    assert options.min_fold_candidate_count == 2
    assert options.min_fold_accepted_count == 1
    assert options.min_fold_adjusted_fixture_count == 5
    assert options.require_fold_best_candidate_accepted is False
    assert options.max_failed_fold_count == 1
    assert options.min_active_competition_fold_count == 2
    assert options.min_active_season_cutoff_fold_count == 3
    assert options.min_active_rolling_fold_count == 4
    assert options.rolling_window_season_count == 5
    assert options.rolling_window_step == 2
    assert options.max_report_folds == 40


def _admission_options(
    *,
    segment_group_keys: tuple[str, ...] = ("competition_outcome:TEST:away_win",),
    min_active_competition_fold_count: int = 1,
    require_sample_readiness: bool = False,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionOptions:
    return HistoricalMarketMovementRiskFilterRollingAdmissionOptions(
        require_sample_readiness=require_sample_readiness,
        segment_gate_options=HistoricalMarketMovementSegmentGateOptions(
            segment_group_keys=segment_group_keys,
            movement_weight=1.0,
            max_probability_shift=0.20,
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                min_probability=0.05,
                max_outcomes_per_fixture=1,
                max_candidates_per_fixture=1,
                unit_stake=2.0,
                max_budget=4.0,
                optimizer_profile="solver",
            ),
            quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                min_slice_count=1,
                min_comparison_count=1,
                min_final_hit_sample_size=0,
                fail_on_suite_statuses=(),
                min_final_hit_rate_delta=-1.0,
                max_brier_score_delta=None,
                max_log_loss_delta=None,
                max_mean_calibration_error_delta=None,
            ),
        ),
        min_active_competition_fold_count=min_active_competition_fold_count,
        rolling_window_season_count=1,
    )


def _sample_readiness_report(
    *,
    status: Literal["accepted", "shadow_only", "rejected"] = "accepted",
    sample_ready_allowed: bool = True,
    shadow_allowed: bool = True,
) -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport(
        readiness_key="historical_prematch_feature_sample_readiness:test",
        status=status,
        sample_ready_allowed=sample_ready_allowed,
        shadow_allowed=shadow_allowed,
        readiness_id="sample-readiness-test",
        target_profile="market_movement",
        coverage_audit_key="historical_sample_coverage_audit:test",
        source_count=1,
        evaluated_source_count=1,
        accepted_source_count=1 if status == "accepted" else 0,
        shadow_only_source_count=1 if status == "shadow_only" else 0,
        rejected_source_count=1 if status == "rejected" else 0,
        ready_source_ids=["market_feature_suite"] if status == "accepted" else [],
        ready_fixture_count=600 if status == "accepted" else 0,
        ready_slice_count=25 if status == "accepted" else 0,
        ready_competition_count=3 if status == "accepted" else 0,
        ready_season_count=2 if status == "accepted" else 0,
        ready_competition_season_count=3 if status == "accepted" else 0,
        checks=[],
        sources=[],
        warnings=[],
        summary_json={"status": status},
    )


def _away_movement_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="market_movement_risk_filter_unit_slice",
            name="Market movement risk filter unit slice",
            competition_id="TEST",
            season="2024-2025",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=_dt(2024, 8, 1, 12),
        fixtures=[
            _fixture("fixture_1", day_offset=1),
            _fixture("fixture_2", day_offset=2),
            _fixture("fixture_3", day_offset=3),
        ],
    )


def _fixture(fixture_id: str, *, day_offset: int) -> HistoricalFixture:
    kickoff = _dt(2024, 8, 1, 12) + timedelta(days=day_offset)
    opening = (0.43, 0.27, 0.30)
    closing = (0.34, 0.21, 0.45)
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff,
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=0,
        actual_away_goals=1,
        prediction_time_utc=kickoff - timedelta(days=1),
        model_version="market-movement-risk-filter-test",
        feature_version="market-movement-feature-test",
        calibration_version="uncalibrated",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome=outcome,
                probability=probability,
                decimal_odds=1.0 / probability,
                market_probability=probability,
            )
            for outcome, probability in zip(
                ("home_win", "draw", "away_win"),
                opening,
                strict=True,
            )
        ],
        feature_snapshot=FeatureSnapshot(
            fixture_id=fixture_id,
            feature_time_utc=kickoff - timedelta(days=1),
            feature_version="market-movement-feature-test",
            data_quality_score=80.0,
            features_json={
                "prematch_context": {
                    "odds_movement": [
                        _movement(outcome, opening_probability, closing_probability)
                        for outcome, opening_probability, closing_probability in zip(
                            ("home_win", "draw", "away_win"),
                            opening,
                            closing,
                            strict=True,
                        )
                    ]
                }
            },
            source_snapshot_refs={"prematch": {"odds_movement": [fixture_id]}},
        ),
    )


def _movement(
    outcome: str,
    opening_probability: float,
    closing_probability: float,
) -> dict[str, object]:
    return {
        "market_type": "1x2",
        "outcome": outcome,
        "opening_prob": opening_probability,
        "current_prob": closing_probability,
        "probability_delta": closing_probability - opening_probability,
        "opening_decimal_odds": 1.0 / opening_probability,
        "current_decimal_odds": 1.0 / closing_probability,
        "points": [
            {"source_snapshot_ref": f"{outcome}:open"},
            {"source_snapshot_ref": f"{outcome}:close"},
        ],
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
