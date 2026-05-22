from __future__ import annotations

from collections.abc import Sequence
from json import dumps, loads
from pathlib import Path
from types import SimpleNamespace

import pytest

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_guarded_rolling_admission import (  # noqa: E501
    HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    HistoricalMarketMovementRiskFilterGuardedFold,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_rolling_admission import (
    HistoricalMarketMovementRiskFilterFold,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_proposal import (
    HistoricalMarketMovementRiskFilterRuntimeProposalOptions,
    build_historical_market_movement_risk_filter_runtime_proposal_report,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_proposal import (
    _options_from_args as proposal_options_from_args,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_proposal import (
    _parse_args as proposal_parse_args,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_proposal import (
    main as proposal_main,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    HistoricalMarketMovementRiskFilterRuntimeReplayOptions,
    build_historical_market_movement_risk_filter_runtime_replay_report,
    load_market_movement_risk_filter_runtime_rule_set,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    _options_from_args as replay_options_from_args,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    _parse_args as replay_parse_args,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    main as replay_main,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateReport,
)


def test_runtime_proposal_ready_from_guarded_admission() -> None:
    report = build_historical_market_movement_risk_filter_runtime_proposal_report(
        _guarded_admission_report()
    )

    assert report.status == "runtime_shadow_proposal_ready"
    assert report.runtime_shadow_proposal_allowed is True
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert all(check.status == "passed" for check in report.checks)
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is False
    assert report.proposal_rule.holdout_candidate_enabled is True
    assert report.proposal_rule.shadow_replay_enabled is True
    assert report.proposal_rule.segment_group_keys == [
        "competition_outcome:LA_LIGA:home_win"
    ]
    assert report.proposal_profile_set_json["default_recommendation_path_changed"] is False
    assert report.proposal_profile_set_json["market_movement_risk_filter_rules"]


def test_runtime_proposal_holdout_only_when_coverage_fails() -> None:
    report = build_historical_market_movement_risk_filter_runtime_proposal_report(
        _guarded_admission_report(),
        options=HistoricalMarketMovementRiskFilterRuntimeProposalOptions(
            min_adjusted_fixture_count=999
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.runtime_shadow_proposal_allowed is False
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert report.proposal_rule is not None
    assert report.proposal_rule.shadow_replay_enabled is False
    assert failed_checks == {"adjusted_fixture_count"}


def test_runtime_proposal_blocks_globally_blocked_selected_segment() -> None:
    report = build_historical_market_movement_risk_filter_runtime_proposal_report(
        _guarded_admission_report(
            global_blocked_segment_group_keys=[
                "competition_outcome:LA_LIGA:home_win"
            ]
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.proposal_count == 0
    assert "selected_segment_not_globally_blocked" in failed_checks


def test_runtime_proposal_cli_writes_profile(tmp_path: Path) -> None:
    source_path = tmp_path / "guarded.json"
    output_path = tmp_path / "proposal.json"
    profile_path = tmp_path / "profile.json"
    source_path.write_text(
        f"{_guarded_admission_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = proposal_parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--proposal-id",
            "market-movement-rule:test",
            "--proposed-profile-version",
            "market-movement-profile:test",
            "--min-adjusted-fixture-count",
            "10",
            "--min-adjusted-prediction-count",
            "20",
            "--min-active-fold-count",
            "2",
            "--max-failed-fold-count",
            "0",
            "--no-fail-process",
        ]
    )
    options = proposal_options_from_args(args)

    assert options.proposal_id == "market-movement-rule:test"
    assert options.proposed_profile_version == "market-movement-profile:test"
    assert options.min_adjusted_fixture_count == 10
    assert options.min_adjusted_prediction_count == 20
    assert options.min_active_fold_count == 2

    proposal_main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--proposal-id",
            "market-movement-rule:test",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile = loads(profile_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_shadow_proposal_ready"
    assert profile["market_movement_risk_filter_rules"][0]["rule_id"] == (
        "market-movement-rule:test"
    )


def test_runtime_replay_passes_with_selected_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_options = []

    def fake_gate(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options,
    ) -> HistoricalMarketMovementSegmentGateReport:
        del historical_slices
        observed_options.append(options)
        return _segment_gate_report(_segment_candidate())

    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_market_movement_risk_filter_runtime_replay."
        "build_historical_market_movement_segment_gate_report",
        fake_gate,
    )

    report = build_historical_market_movement_risk_filter_runtime_replay_report(
        [],
        rule_set=load_market_movement_risk_filter_runtime_rule_set(
            _profile_path_from_report(monkeypatch),
            enable_shadow_replay=True,
        ),
        options=HistoricalMarketMovementRiskFilterRuntimeReplayOptions(
            enable_shadow_replay=True,
            require_profile_runtime_shadow_allowed=True,
        ),
    )

    assert report.status == "runtime_shadow_replay_passed"
    assert report.runtime_shadow_replay_allowed is True
    assert report.holdout_replay_allowed is True
    assert report.selected_segment_group_key == "competition_outcome:LA_LIGA:home_win"
    assert report.adjusted_fixture_count == 120
    assert all(check.status in {"passed", "skipped"} for check in report.checks)
    assert observed_options[0].segment_group_keys == (
        "competition_outcome:LA_LIGA:home_win",
    )
    assert observed_options[0].movement_weight == 0.4


def test_runtime_replay_disabled_without_flag() -> None:
    report = build_historical_market_movement_risk_filter_runtime_replay_report(
        [],
        rule_set=_runtime_rule_set(),
    )

    assert report.status == "disabled"
    assert report.runtime_shadow_replay_allowed is False
    assert report.checks == []


def test_runtime_replay_fails_harmful_probability_quality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gate(
        historical_slices: Sequence[HistoricalRecommendationSlice],
        *,
        options,
    ) -> HistoricalMarketMovementSegmentGateReport:
        del historical_slices, options
        return _segment_gate_report(
            _segment_candidate(brier_score_delta=0.01, log_loss_delta=0.02)
        )

    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_market_movement_risk_filter_runtime_replay."
        "build_historical_market_movement_segment_gate_report",
        fake_gate,
    )

    report = build_historical_market_movement_risk_filter_runtime_replay_report(
        [],
        rule_set=_runtime_rule_set(),
        options=HistoricalMarketMovementRiskFilterRuntimeReplayOptions(
            enable_shadow_replay=True
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_replay_failed"
    assert "brier_score_delta" in failed_checks
    assert "log_loss_delta" in failed_checks


def test_runtime_replay_cli_options_and_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nutmeg.recommendations."
        "historical_market_movement_risk_filter_runtime_replay."
        "build_historical_market_movement_segment_gate_report",
        lambda historical_slices, *, options: _segment_gate_report(
            _segment_candidate()
        ),
    )
    profile_path = tmp_path / "profile.json"
    output_path = tmp_path / "replay.json"
    slice_path = tmp_path / "slice.json"
    profile_path.write_text(
        f"{_runtime_rule_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    slice_path.write_text(
        """
{
  "metadata": {
    "slice_id": "slice:test",
    "name": "slice test",
    "competition_id": "TEST",
    "season": "2024-2025",
    "result_source": "unit-test",
    "odds_source": "unit-test",
    "prediction_source": "unit-test"
  },
  "as_of_time_utc": "2025-05-01T00:00:00Z",
  "fixtures": [
    {
      "fixture_id": "fixture:test",
      "competition_id": "TEST",
      "kickoff_time_utc": "2025-05-01T12:00:00Z",
      "home_team_name": "Home",
      "away_team_name": "Away",
      "actual_home_goals": 1,
      "actual_away_goals": 0,
      "prediction_time_utc": "2025-05-01T00:00:00Z",
      "model_version": "unit-test",
      "predictions": [
        {
          "market_type": "1x2",
          "outcome": "home_win",
          "probability": 0.6,
          "decimal_odds": 1.8
        }
      ]
    }
  ]
}
""",
        encoding="utf-8",
    )

    args = replay_parse_args(
        [
            str(slice_path),
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--rule-ids",
            "market-movement-rule:test",
            "--pass-types",
            "1x1,3x1",
            "--modes",
            "single",
            "--strategy",
            "accuracy_first",
            "--unit-stake",
            "2",
            "--max-budget",
            "20",
            "--optimizer-profile",
            "solver",
            "--require-profile-runtime-shadow-allowed",
            "--no-fail-process",
        ]
    )
    options = replay_options_from_args(args)

    assert options.enable_shadow_replay is True
    assert options.rule_ids == ("market-movement-rule:test",)
    assert options.override_pass_types == ("1x1", "3x1")
    assert options.override_modes == ("single",)
    assert options.require_profile_runtime_shadow_allowed is True

    replay_main(
        [
            str(slice_path),
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--require-profile-runtime-shadow-allowed",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_shadow_replay_passed"
    assert payload["source_rule_profile_version"] == (
        "v3_2_market_movement_risk_filter_runtime_shadow_candidate"
    )


def _guarded_admission_report(
    *,
    global_blocked_segment_group_keys: list[str] | None = None,
) -> HistoricalMarketMovementRiskFilterGuardedAdmissionReport:
    fold = HistoricalMarketMovementRiskFilterFold.model_construct(
        fold_id="overall:all",
        fold_type="overall",
        status="passed",
        source_slice_ids=["slice:test"],
        source_competition_ids=["LA_LIGA"],
        source_season_ids=["2024-2025"],
        segment_gate_report_key="segment-gate:guarded",
        passed_segment_gate=True,
        candidate_count=4,
        accepted_count=1,
        adjusted_fixture_count=120,
        adjusted_prediction_count=360,
        best_candidate_id="candidate:market-movement",
        best_segment_group_key="competition_outcome:LA_LIGA:home_win",
        best_segment_group_type="competition_outcome",
        best_segment_label="LA_LIGA home_win",
        best_decision="accepted",
        best_passed_single_match_gate=True,
        best_passed_final_answer_gate=True,
        best_quality_gate_passed=True,
        best_suite_status="completed",
        single_match_hit_rate_delta=0.0,
        single_match_brier_score_delta=-0.001,
        single_match_log_loss_delta=-0.002,
        final_hit_rate_delta=0.0,
        roi_delta=0.0,
        profit_loss_delta=0.0,
        brier_score_delta=-0.001,
        log_loss_delta=-0.002,
        mean_calibration_error_delta=-0.003,
        failure_reasons=[],
        warning_codes=[],
        summary_json={},
    )
    guarded_fold = HistoricalMarketMovementRiskFilterGuardedFold.model_construct(
        fold=fold,
        original_segment_gate_report_key="segment-gate:source",
        guarded_segment_gate_report_key="segment-gate:guarded",
        original_candidate_count=5,
        guarded_candidate_count=4,
        removed_candidate_count=1,
        removed_segment_group_keys=["competition:LIGUE_1"],
        removed_candidate_ids=["candidate:guarded"],
        guard_reasons_by_segment_group_key={
            "competition:LIGUE_1": ["global_blocked_segment_group_key"]
        },
        guarded_skip=False,
        summary_json={},
    )
    return HistoricalMarketMovementRiskFilterGuardedAdmissionReport.model_construct(
        report_key="guarded-admission:test",
        status="accepted",
        guarded_risk_filter_allowed=True,
        shadow_allowed=True,
        production_recommendation_changed=False,
        scope_refinement_report_key="scope-refinement:test",
        scope_refinement_status="guarded_scope_required",
        sample_readiness_report_path=None,
        sample_readiness_key="sample-readiness:test",
        sample_readiness_status="accepted",
        sample_ready_allowed=True,
        sample_readiness_shadow_allowed=True,
        overall_fold=fold,
        guarded_overall_fold=guarded_fold,
        fold_count=4,
        active_fold_count=4,
        guarded_skipped_fold_count=0,
        failed_fold_count=0,
        active_competition_fold_count=1,
        active_season_cutoff_fold_count=1,
        active_rolling_fold_count=1,
        removed_candidate_count=1,
        global_blocked_segment_group_keys=global_blocked_segment_group_keys or [],
        exact_guard_scope_count=1,
        checks=[],
        folds=[],
        warnings=[],
        summary_json={
            "rolling_options": {
                "segment_gate_options": {
                    "gate_id": "segment-gate:test",
                    "movement_weight": 0.4,
                    "max_probability_shift": 0.05,
                }
            }
        },
    )


def _runtime_rule_set():
    proposal = build_historical_market_movement_risk_filter_runtime_proposal_report(
        _guarded_admission_report()
    )
    return load_market_movement_risk_filter_runtime_rule_set(
        _profile_path_from_json(proposal.proposal_profile_set_json),
        enable_shadow_replay=True,
    )


def _profile_path_from_report(monkeypatch: pytest.MonkeyPatch) -> Path:
    del monkeypatch
    proposal = build_historical_market_movement_risk_filter_runtime_proposal_report(
        _guarded_admission_report()
    )
    return _profile_path_from_json(proposal.proposal_profile_set_json)


def _profile_path_from_json(payload: dict[str, object]) -> Path:
    path = Path("/tmp/nutmeg_market_movement_runtime_profile_unit.json")
    path.write_text(f"{dumps(loads(dumps(payload)), indent=2)}\n", encoding="utf-8")
    return path


def _segment_gate_report(
    candidate: HistoricalMarketMovementSegmentCandidate,
) -> HistoricalMarketMovementSegmentGateReport:
    return HistoricalMarketMovementSegmentGateReport.model_construct(
        report_key="segment-gate:runtime-replay",
        status="generated",
        gate_id="segment-gate:test",
        diagnostics_report_key="diagnostics:test",
        slice_count=1,
        fixture_count=120,
        diagnostics_observation_count=360,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        best_candidate=candidate,
        candidates=[candidate],
        warnings=[],
        summary_json={"best_segment_group_key": candidate.segment_group_key},
    )


def _segment_candidate(
    *,
    brier_score_delta: float = -0.001,
    log_loss_delta: float = -0.002,
) -> HistoricalMarketMovementSegmentCandidate:
    return HistoricalMarketMovementSegmentCandidate.model_construct(
        rank=1,
        candidate_id="candidate:market-movement",
        segment_group_key="competition_outcome:LA_LIGA:home_win",
        segment_group_type="competition_outcome",
        segment_label="LA_LIGA home_win",
        decision="accepted",
        decision_reasons=["segment_gate:accepted"],
        segment_sample_count=120,
        segment_brier_score_delta=-0.001,
        segment_log_loss_delta=-0.002,
        segment_calibration_error_delta=-0.003,
        adjusted_fixture_count=120,
        adjusted_prediction_count=360,
        single_match_sample_count=120,
        single_match_deltas_json={
            "hit_rate_delta": 0.0,
            "brier_score_delta": -0.001,
            "log_loss_delta": -0.002,
        },
        passed_single_match_gate=True,
        suite=SimpleNamespace(status="completed"),
        quality_gate=SimpleNamespace(passed=True),
        passed_final_answer_gate=True,
        final_answer_deltas_json={
            "final_hit_rate_delta": 0.0,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": log_loss_delta,
            "mean_calibration_error_delta": -0.003,
        },
        summary_json={},
    )
