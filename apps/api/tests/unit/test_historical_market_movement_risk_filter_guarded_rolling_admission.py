from __future__ import annotations

from datetime import UTC, datetime
from json import loads
from types import SimpleNamespace
from typing import Literal

from pytest import MonkeyPatch

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_guarded_rolling_admission import (  # noqa: E501
    HistoricalMarketMovementRiskFilterGuardedAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_risk_filter_guarded_admission_report,
    main,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_rolling_admission import (
    HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_scope_refinement import (
    HistoricalMarketMovementRiskFilterBlockedScope,
    HistoricalMarketMovementRiskFilterScopeRefinementReport,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateReport,
)


def test_guarded_admission_skips_fully_guarded_failed_fold(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _fake_gate_builder(monkeypatch, season_cutoff_decision="rejected")
    report = build_historical_market_movement_risk_filter_guarded_admission_report(
        [_slice("guard_slice", "2023-2024")],
        scope_refinement_report=_scope_refinement_report(with_blocked_scope=True),
        options=_guarded_options(),
    )

    assert calls.count == 3
    assert report.status == "accepted"
    assert report.guarded_risk_filter_allowed is True
    assert report.failed_fold_count == 0
    assert report.guarded_skipped_fold_count == 1
    assert report.removed_candidate_count == 1
    assert report.folds[1].guarded_skip is True
    assert report.folds[1].fold.fold_id == "season_cutoff:2023-2024"


def test_guarded_admission_shadows_without_matching_guard(
    monkeypatch: MonkeyPatch,
) -> None:
    _fake_gate_builder(monkeypatch, season_cutoff_decision="rejected")
    report = build_historical_market_movement_risk_filter_guarded_admission_report(
        [_slice("guard_slice", "2023-2024")],
        scope_refinement_report=_scope_refinement_report(with_blocked_scope=False),
        options=_guarded_options(),
    )

    assert report.status == "shadow_only"
    assert report.guarded_risk_filter_allowed is False
    assert report.failed_fold_count == 1
    assert report.guarded_skipped_fold_count == 0
    assert report.removed_candidate_count == 0


def test_guarded_admission_cli_writes_report(
    tmp_path,
    capsys,
    monkeypatch: MonkeyPatch,
) -> None:
    _fake_gate_builder(monkeypatch, season_cutoff_decision="rejected")
    historical_slice = _slice("guard_slice", "2023-2024")
    scope_report = _scope_refinement_report(with_blocked_scope=True)
    slice_path = tmp_path / "slice.json"
    scope_path = tmp_path / "scope.json"
    output_path = tmp_path / "guarded.json"
    slice_path.write_text(
        f"{historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    scope_path.write_text(
        f"{scope_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(slice_path),
            "--scope-refinement-report-path",
            str(scope_path),
            "--rolling-window-season-count",
            "2",
            "--min-active-season-cutoff-fold-count",
            "0",
            "--min-active-rolling-fold-count",
            "0",
            "--output-path",
            str(output_path),
        ]
    )

    printed = loads(capsys.readouterr().out)
    payload = loads(output_path.read_text(encoding="utf-8"))
    assert printed["report_key"] == payload["report_key"]
    assert payload["status"] == "accepted"
    assert payload["guarded_skipped_fold_count"] == 1


def test_guarded_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/"
            "football_data_co_uk_market_features_multi/"
            "football_data_co_uk_epl_2024_2025_market_features_v1.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/"
            "football_data_co_uk_market_feature_multi_season_suite.json",
            "--scope-refinement-report-path",
            "tmp/scope.json",
            "--sample-readiness-report-path",
            "tmp/sample.json",
            "--output-path",
            "tmp/guarded.json",
            "--guarded-admission-id",
            "guarded-test",
            "--min-overall-candidate-count",
            "2",
            "--min-overall-accepted-count",
            "2",
            "--min-overall-adjusted-fixture-count",
            "10",
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
            "--no-use-scope-refinement-gate-options",
            "--no-apply-failed-scope-guards",
            "--no-apply-block-actions-globally",
            "--no-skip-fully-guarded-non-overall-folds",
        ]
    )

    options = _options_from_args(args)

    assert options.admission_id == "guarded-test"
    assert options.sample_readiness_report_path is not None
    assert str(options.sample_readiness_report_path).endswith("sample.json")
    assert options.require_sample_readiness is True
    assert options.require_sample_ready_allowed is False
    assert options.use_scope_refinement_gate_options is False
    assert options.apply_failed_scope_guards is False
    assert options.apply_block_actions_globally is False
    assert options.skip_fully_guarded_non_overall_folds is False
    assert options.max_report_folds == 40
    rolling_options = options.rolling_options
    assert rolling_options.min_overall_candidate_count == 2
    assert rolling_options.min_overall_accepted_count == 2
    assert rolling_options.min_overall_adjusted_fixture_count == 10
    assert rolling_options.min_fold_slice_count == 2
    assert rolling_options.min_fold_fixture_count == 8
    assert rolling_options.min_fold_candidate_count == 2
    assert rolling_options.min_fold_accepted_count == 1
    assert rolling_options.min_fold_adjusted_fixture_count == 5
    assert rolling_options.max_failed_fold_count == 1
    assert rolling_options.min_active_competition_fold_count == 2
    assert rolling_options.min_active_season_cutoff_fold_count == 3
    assert rolling_options.min_active_rolling_fold_count == 4
    assert rolling_options.rolling_window_season_count == 5
    assert rolling_options.rolling_window_step == 2


class _CallCounter:
    count = 0


def _fake_gate_builder(
    monkeypatch: MonkeyPatch,
    *,
    season_cutoff_decision: Literal["accepted", "rejected"],
) -> _CallCounter:
    calls = _CallCounter()

    def fake_segment_gate_report(
        slices,
        *,
        options,
    ) -> HistoricalMarketMovementSegmentGateReport:
        calls.count += 1
        decision: Literal["accepted", "rejected"] = (
            season_cutoff_decision if calls.count == 3 else "accepted"
        )
        return _segment_gate_report(_candidate(decision=decision))

    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_market_movement_risk_filter_guarded_rolling_admission."
        "build_historical_market_movement_segment_gate_report",
        fake_segment_gate_report,
    )
    return calls


def _guarded_options() -> HistoricalMarketMovementRiskFilterGuardedAdmissionOptions:
    rolling_options = HistoricalMarketMovementRiskFilterRollingAdmissionOptions(
        rolling_window_season_count=2,
        min_active_season_cutoff_fold_count=0,
        min_active_rolling_fold_count=0,
    )
    return HistoricalMarketMovementRiskFilterGuardedAdmissionOptions(
        rolling_options=rolling_options,
        use_scope_refinement_gate_options=False,
    )


def _scope_refinement_report(
    *,
    with_blocked_scope: bool,
) -> HistoricalMarketMovementRiskFilterScopeRefinementReport:
    blocked_scopes = [
        HistoricalMarketMovementRiskFilterBlockedScope(
            segment_group_key="delta_band:0.03:0.06",
            segment_group_type="delta_band",
            segment_label="Abs probability delta 0.03:0.06",
            fold_id="season_cutoff:2023-2024",
            fold_type="season_cutoff",
            source_competition_ids=["TEST"],
            source_season_ids=["2023-2024"],
            candidate_id="candidate:rejected",
            failure_reasons=["quality_gate_not_passed"],
            brier_score_delta=0.01,
            log_loss_delta=0.02,
            final_hit_rate_delta=0.0,
        )
    ] if with_blocked_scope else []
    return HistoricalMarketMovementRiskFilterScopeRefinementReport(
        report_key="historical_market_movement_risk_filter_scope_refinement:test",
        status="guarded_scope_required" if with_blocked_scope else "stable_scope_found",
        refinement_id="scope-refinement-test",
        rolling_admission_report_key=(
            "historical_market_movement_risk_filter_rolling_admission:test"
        ),
        rolling_admission_status="shadow_only",
        rolling_risk_filter_allowed=False,
        rolling_shadow_allowed=True,
        source_failed_fold_count=1 if with_blocked_scope else 0,
        analyzed_fold_count=2,
        scope_candidate_count=1,
        stable_scope_count=0,
        guarded_scope_count=1 if with_blocked_scope else 0,
        blocked_scope_count=0,
        insufficient_scope_count=0,
        blocked_guard_count=len(blocked_scopes),
        scopes=[],
        evaluations=[],
        blocked_scopes=blocked_scopes,
        warnings=[],
        summary_json={
            "options": _guarded_options().rolling_options.model_dump(mode="json")
        },
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
        quality_gate=SimpleNamespace(passed=decision == "accepted"),
        passed_final_answer_gate=decision == "accepted",
        final_answer_deltas_json={
            "final_hit_rate_delta": 0.0,
            "brier_score_delta": -0.01 if decision == "accepted" else 0.01,
            "log_loss_delta": -0.02 if decision == "accepted" else 0.02,
            "mean_calibration_error_delta": -0.01 if decision == "accepted" else 0.01,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
        },
        summary_json={"decision": decision},
    )


def _slice(slice_id: str, season: str) -> HistoricalRecommendationSlice:
    kickoff = datetime(2024, 8, 1, 12, tzinfo=UTC)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id="TEST",
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=kickoff,
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture",
                competition_id="TEST",
                kickoff_time_utc=kickoff,
                home_team_name="Home",
                away_team_name="Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=kickoff,
                model_version="guarded-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.60,
                        decimal_odds=1.80,
                    )
                ],
            )
        ],
    )
