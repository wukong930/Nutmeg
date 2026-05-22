from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_market_movement_segment_gate_accepts_positive_shadow_candidate() -> None:
    report = build_historical_market_movement_segment_gate_report(
        [_away_movement_slice()],
        options=HistoricalMarketMovementSegmentGateOptions(
            segment_group_keys=("competition_outcome:TEST:away_win",),
            movement_weight=1.0,
            max_probability_shift=0.20,
            backtest_options=_backtest_options(),
            quality_gate_options=_permissive_quality_gate_options(),
        ),
    )

    assert report.candidate_count == 1
    assert report.accepted_count == 1
    assert report.best_candidate is not None
    assert report.best_candidate.segment_group_key == "competition_outcome:TEST:away_win"
    assert report.best_candidate.decision == "accepted"
    assert report.best_candidate.adjusted_fixture_count == 3
    assert report.best_candidate.adjusted_prediction_count == 9
    assert report.best_candidate.single_match_deltas_json["hit_rate_delta"] == 1.0
    assert report.best_candidate.single_match_deltas_json["brier_score_delta"] < 0.0
    assert report.best_candidate.single_match_deltas_json["log_loss_delta"] < 0.0
    assert report.best_candidate.summary_json["shadow_only"] is True
    assert report.summary_json["shadow_only"] is True


def test_market_movement_segment_gate_rejects_when_single_match_gate_is_too_strict() -> None:
    report = build_historical_market_movement_segment_gate_report(
        [_away_movement_slice()],
        options=HistoricalMarketMovementSegmentGateOptions(
            segment_group_keys=("competition_outcome:TEST:away_win",),
            movement_weight=1.0,
            max_probability_shift=0.20,
            max_single_match_brier_delta=-1.0,
            backtest_options=_backtest_options(),
            quality_gate_options=_permissive_quality_gate_options(),
        ),
    )

    assert report.candidate_count == 1
    assert report.accepted_count == 0
    assert report.best_candidate is not None
    assert report.best_candidate.decision == "rejected"
    assert "single_match:brier_score_delta" in report.best_candidate.decision_reasons
    assert "market_movement_segment_gate:no_accepted_candidate" in report.warnings


def test_market_movement_segment_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/"
            "football_data_co_uk_market_features_multi/"
            "football_data_co_uk_epl_2024_2025_market_features_v1.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/"
            "football_data_co_uk_market_feature_multi_season_suite.json",
            "--diagnostics-report-path",
            "configs/recommendations/historical_reports/"
            "football_data_co_uk_market_movement_signal_diagnostics_v1.json",
            "--output-path",
            "tmp/market-movement-segment-gate.json",
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
            "accuracy_first",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.10",
            "--min-data-quality-score",
            "60",
            "--max-outcomes-per-fixture",
            "1",
            "--candidate-fixture-limit",
            "8",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "3",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "solver",
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
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.gate_id == "segment-gate-test"
    assert options.segment_group_keys == (
        "competition_outcome:EPL:away_win",
        "delta_band:0.03:0.06",
    )
    assert options.top_positive_segment_limit == 7
    assert options.min_segment_sample_size == 12
    assert options.max_segment_brier_delta == -0.01
    assert options.max_segment_log_loss_delta == -0.02
    assert options.max_segment_calibration_error_delta == 0.03
    assert options.min_segment_closing_improved_rate == 0.55
    assert options.movement_weight == 0.75
    assert options.max_probability_shift == 0.12
    assert options.min_single_match_sample_size == 9
    assert options.min_single_match_hit_rate_delta == 0.01
    assert options.max_single_match_brier_delta == -0.001
    assert options.max_single_match_log_loss_delta == -0.002
    assert options.diagnostics_options.min_abs_probability_delta == 0.02
    assert options.diagnostics_options.movement_direction_epsilon == 0.004
    assert options.diagnostics_options.delta_bands == (
        "0.00:0.02",
        "0.02:0.05",
        "0.05:",
    )
    assert options.diagnostics_options.opening_probability_bands == (
        "0.00:0.30",
        "0.30:0.60",
        "0.60:1.00",
    )
    assert options.diagnostics_options.min_group_sample_size == 5
    assert options.diagnostics_options.include_competition_groups is False
    assert options.diagnostics_options.observation_sample_limit == 7
    assert options.backtest_options.pass_types == ("1x1", "2x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 18
    assert options.backtest_options.min_probability == 0.10
    assert options.backtest_options.min_data_quality_score == 60
    assert options.backtest_options.max_outcomes_per_fixture == 1
    assert options.backtest_options.candidate_fixture_limit == 8
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.optimizer_profile == "solver"
    assert options.quality_gate_options.min_slice_count == 2
    assert options.quality_gate_options.min_comparison_count == 2
    assert options.quality_gate_options.min_final_hit_sample_size == 2
    assert options.quality_gate_options.min_candidate_final_hit_rate == 0.51
    assert options.quality_gate_options.min_candidate_roi == -0.25
    assert options.quality_gate_options.fail_on_suite_statuses == ("regressed",)
    assert options.quality_gate_options.min_final_hit_rate_delta == 0.02
    assert options.quality_gate_options.min_roi_delta == 0.03
    assert options.quality_gate_options.min_profit_loss_delta == 1.5
    assert options.quality_gate_options.max_brier_score_delta == -0.001
    assert options.quality_gate_options.max_log_loss_delta == -0.002
    assert options.quality_gate_options.max_mean_calibration_error_delta == 0.01
    assert options.quality_gate_options.min_final_answer_changed_count == 1
    assert options.quality_gate_options.max_warning_count == 4


def _backtest_options() -> HistoricalRecommendationBacktestOptions:
    return HistoricalRecommendationBacktestOptions(
        pass_types=("1x1",),
        modes=("single",),
        min_probability=0.05,
        max_outcomes_per_fixture=1,
        max_candidates_per_fixture=1,
        optimizer_profile="solver",
    )


def _permissive_quality_gate_options() -> HistoricalRecommendationSuiteQualityGateOptions:
    return HistoricalRecommendationSuiteQualityGateOptions(
        min_slice_count=1,
        min_comparison_count=1,
        min_final_hit_sample_size=0,
        fail_on_suite_statuses=(),
        min_final_hit_rate_delta=None,
        max_brier_score_delta=None,
        max_log_loss_delta=None,
        max_mean_calibration_error_delta=None,
    )


def _away_movement_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="market_movement_segment_gate_unit_slice",
            name="Market movement segment gate unit slice",
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
        model_version="market-movement-segment-gate-test",
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
