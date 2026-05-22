from __future__ import annotations

from datetime import UTC, datetime, timedelta
from json import loads
from types import SimpleNamespace
from typing import Literal

from pytest import MonkeyPatch

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
    HistoricalMarketMovementRiskFilterFold,
    HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    HistoricalMarketMovementRiskFilterRollingAdmissionReport,
    build_historical_market_movement_risk_filter_rolling_admission_report,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_scope_refinement import (
    HistoricalMarketMovementRiskFilterScopeRefinementOptions,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_risk_filter_scope_refinement_report,
    main,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateOptions,
    HistoricalMarketMovementSegmentGateReport,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_market_movement_risk_filter_scope_refinement_reports_no_failed_folds() -> None:
    historical_slice = _away_movement_slice()
    rolling_report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [historical_slice],
        options=_admission_options(),
        sample_readiness_report=_sample_readiness_report(),
    )

    report = build_historical_market_movement_risk_filter_scope_refinement_report(
        [historical_slice],
        rolling_admission_report=rolling_report,
        options=HistoricalMarketMovementRiskFilterScopeRefinementOptions(
            segment_gate_options=_segment_gate_options(),
        ),
    )

    assert report.status == "no_failed_folds"
    assert report.source_failed_fold_count == 0
    assert report.scope_candidate_count >= 1
    assert report.blocked_guard_count == 0


def test_market_movement_risk_filter_scope_refinement_guards_failed_scope(
    monkeypatch: MonkeyPatch,
) -> None:
    historical_slices = [
        _minimal_slice("pass_slice", "TEST", "2022-2023"),
        _minimal_slice("fail_slice", "TEST", "2023-2024"),
    ]
    rolling_report = _rolling_report(
        folds=[
            _fold("competition:TEST", "competition", "passed", ["pass_slice"]),
            _fold("season_cutoff:2023-2024", "season_cutoff", "failed", ["fail_slice"]),
        ],
        failed_fold_count=1,
    )

    def fake_segment_gate_report(
        slices,
        *,
        options,
    ) -> HistoricalMarketMovementSegmentGateReport:
        slice_ids = {historical_slice.metadata.slice_id for historical_slice in slices}
        if "fail_slice" in slice_ids:
            return _segment_gate_report(
                _candidate(
                    decision="rejected",
                    quality_passed=False,
                    brier_score_delta=0.01,
                    log_loss_delta=0.02,
                    final_hit_rate_delta=0.0,
                )
            )
        return _segment_gate_report(_candidate(decision="accepted"))

    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_market_movement_risk_filter_scope_refinement."
        "build_historical_market_movement_segment_gate_report",
        fake_segment_gate_report,
    )

    report = build_historical_market_movement_risk_filter_scope_refinement_report(
        historical_slices,
        rolling_admission_report=rolling_report,
    )

    assert report.status == "guarded_scope_required"
    assert report.guarded_scope_count == 1
    assert report.blocked_guard_count == 1
    assert report.best_scope is not None
    assert report.best_scope.recommended_action == "guard_failed_scopes"
    assert report.blocked_scopes[0].fold_id == "season_cutoff:2023-2024"
    assert report.blocked_scopes[0].segment_group_key == "delta_band:0.03:0.06"


def test_market_movement_risk_filter_scope_refinement_cli_writes_report(
    tmp_path,
    capsys,
) -> None:
    historical_slice = _away_movement_slice()
    rolling_report = build_historical_market_movement_risk_filter_rolling_admission_report(
        [historical_slice],
        options=_admission_options(),
        sample_readiness_report=_sample_readiness_report(),
    )
    slice_path = tmp_path / "slice.json"
    rolling_path = tmp_path / "rolling.json"
    output_path = tmp_path / "scope_refinement.json"
    slice_path.write_text(
        f"{historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rolling_path.write_text(
        f"{rolling_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(slice_path),
            "--rolling-admission-report-path",
            str(rolling_path),
            "--output-path",
            str(output_path),
        ]
    )

    printed = loads(capsys.readouterr().out)
    payload = loads(output_path.read_text(encoding="utf-8"))
    assert printed["report_key"] == payload["report_key"]
    assert payload["status"] == "no_failed_folds"
    assert payload["rolling_admission_report_key"] == rolling_report.report_key


def test_market_movement_risk_filter_scope_refinement_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/"
            "football_data_co_uk_market_features_multi/"
            "football_data_co_uk_epl_2024_2025_market_features_v1.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/"
            "football_data_co_uk_market_feature_multi_season_suite.json",
            "--rolling-admission-report-path",
            "tmp/rolling.json",
            "--output-path",
            "tmp/scope.json",
            "--refinement-id",
            "scope-refinement-test",
            "--no-include-overall-fold",
            "--no-include-passed-folds",
            "--target-failed-fold-ids",
            "season_cutoff:2023-2024,rolling_window:2:2021-2022..2023-2024",
            "--min-segment-evaluation-count",
            "2",
            "--min-segment-accepted-count",
            "2",
            "--max-segment-rejected-count-for-stable",
            "1",
            "--max-failed-scope-count-for-stable",
            "1",
            "--min-final-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.02",
            "--max-log-loss-delta",
            "0.03",
            "--max-mean-calibration-error-delta",
            "0.04",
            "--max-report-candidates",
            "20",
            "--max-report-evaluations",
            "30",
            "--no-use-rolling-report-gate-options",
        ]
    )

    options = _options_from_args(args)

    assert options.refinement_id == "scope-refinement-test"
    assert options.include_overall_fold is False
    assert options.include_passed_folds is False
    assert options.target_failed_fold_ids == (
        "season_cutoff:2023-2024",
        "rolling_window:2:2021-2022..2023-2024",
    )
    assert options.min_segment_evaluation_count == 2
    assert options.min_segment_accepted_count == 2
    assert options.max_segment_rejected_count_for_stable == 1
    assert options.max_failed_scope_count_for_stable == 1
    assert options.min_final_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_mean_calibration_error_delta == 0.04
    assert options.max_report_candidates == 20
    assert options.max_report_evaluations == 30
    assert options.use_rolling_report_gate_options is False


def _admission_options() -> HistoricalMarketMovementRiskFilterRollingAdmissionOptions:
    return HistoricalMarketMovementRiskFilterRollingAdmissionOptions(
        require_sample_readiness=False,
        segment_gate_options=_segment_gate_options(),
        rolling_window_season_count=1,
    )


def _segment_gate_options() -> HistoricalMarketMovementSegmentGateOptions:
    return HistoricalMarketMovementSegmentGateOptions(
        segment_group_keys=("competition_outcome:TEST:away_win",),
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
    )


def _sample_readiness_report() -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport(
        readiness_key="historical_prematch_feature_sample_readiness:test",
        status="accepted",
        sample_ready_allowed=True,
        shadow_allowed=True,
        readiness_id="sample-readiness-test",
        target_profile="market_movement",
        coverage_audit_key="historical_sample_coverage_audit:test",
        source_count=1,
        evaluated_source_count=1,
        accepted_source_count=1,
        shadow_only_source_count=0,
        rejected_source_count=0,
        ready_source_ids=["market_feature_suite"],
        ready_fixture_count=600,
        ready_slice_count=25,
        ready_competition_count=3,
        ready_season_count=2,
        ready_competition_season_count=3,
        checks=[],
        sources=[],
        warnings=[],
        summary_json={"status": "accepted"},
    )


def _rolling_report(
    *,
    folds: list[HistoricalMarketMovementRiskFilterFold],
    failed_fold_count: int,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionReport:
    return HistoricalMarketMovementRiskFilterRollingAdmissionReport(
        report_key="historical_market_movement_risk_filter_rolling_admission:test",
        status="shadow_only" if failed_fold_count else "accepted",
        risk_filter_allowed=failed_fold_count == 0,
        shadow_allowed=True,
        source_segment_gate_report_key="historical_market_movement_segment_gate:test",
        overall_fold=folds[0],
        fold_count=len(folds),
        active_fold_count=len(folds),
        failed_fold_count=failed_fold_count,
        active_competition_fold_count=sum(
            1 for fold in folds if fold.fold_type == "competition"
        ),
        active_season_cutoff_fold_count=sum(
            1 for fold in folds if fold.fold_type == "season_cutoff"
        ),
        active_rolling_fold_count=sum(
            1 for fold in folds if fold.fold_type == "rolling_window"
        ),
        checks=[],
        folds=folds,
        warnings=[],
        summary_json={
            "options": _admission_options().model_dump(mode="json"),
        },
    )


def _fold(
    fold_id: str,
    fold_type: str,
    status: Literal["passed", "failed"],
    slice_ids: list[str],
) -> HistoricalMarketMovementRiskFilterFold:
    return HistoricalMarketMovementRiskFilterFold(
        fold_id=fold_id,
        fold_type=fold_type,  # type: ignore[arg-type]
        status=status,
        source_slice_ids=slice_ids,
        source_competition_ids=["TEST"],
        source_season_ids=["2023-2024"],
        passed_segment_gate=status == "passed",
        candidate_count=1,
        accepted_count=1 if status == "passed" else 0,
        adjusted_fixture_count=3,
        adjusted_prediction_count=9,
        failure_reasons=[] if status == "passed" else ["accepted_count_below_threshold"],
    )


def _segment_gate_report(
    candidate: HistoricalMarketMovementSegmentCandidate,
) -> HistoricalMarketMovementSegmentGateReport:
    accepted_count = 1 if candidate.decision == "accepted" else 0
    return HistoricalMarketMovementSegmentGateReport.model_construct(
        report_key=f"historical_market_movement_segment_gate:{candidate.decision}",
        status="generated",
        gate_id="segment-gate-test",
        diagnostics_report_key="diagnostics:test",
        slice_count=1,
        fixture_count=3,
        diagnostics_observation_count=9,
        candidate_count=1,
        accepted_count=accepted_count,
        rejected_count=1 - accepted_count,
        best_candidate=candidate,
        candidates=[candidate],
        warnings=[],
        summary_json={"candidate_decision": candidate.decision},
    )


def _candidate(
    *,
    decision: Literal["accepted", "rejected"],
    quality_passed: bool = True,
    brier_score_delta: float = -0.01,
    log_loss_delta: float = -0.02,
    final_hit_rate_delta: float = 0.0,
) -> HistoricalMarketMovementSegmentCandidate:
    return HistoricalMarketMovementSegmentCandidate.model_construct(
        rank=1,
        candidate_id=f"candidate:{decision}",
        segment_group_key="delta_band:0.03:0.06",
        segment_group_type="delta_band",
        segment_label="Abs probability delta 0.03:0.06",
        decision=decision,
        decision_reasons=[] if decision == "accepted" else ["quality_gate:failed"],
        segment_sample_count=20,
        adjusted_fixture_count=3,
        adjusted_prediction_count=9,
        single_match_sample_count=3,
        single_match_deltas_json={
            "hit_rate_delta": 0.0,
            "brier_score_delta": -0.01,
            "log_loss_delta": -0.02,
        },
        passed_single_match_gate=decision == "accepted",
        suite=SimpleNamespace(status="improved" if decision == "accepted" else "regressed"),
        quality_gate=SimpleNamespace(passed=quality_passed),
        passed_final_answer_gate=decision == "accepted",
        final_answer_deltas_json={
            "final_hit_rate_delta": final_hit_rate_delta,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": log_loss_delta,
            "mean_calibration_error_delta": brier_score_delta,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
        },
        summary_json={"decision": decision},
    )


def _minimal_slice(
    slice_id: str,
    competition_id: str,
    season: str,
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice.model_construct(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id=competition_id,
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=_dt(2024, 8, 1, 12),
        fixtures=[object()],
    )


def _away_movement_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="market_movement_scope_refinement_unit_slice",
            name="Market movement scope refinement unit slice",
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
        model_version="market-movement-scope-refinement-test",
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
