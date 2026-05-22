from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_probability_calibration_profile_grid import (
    HistoricalProbabilityCalibrationProfileGridCandidate,
    HistoricalProbabilityCalibrationProfileGridReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_production_proposal import (
    _options_from_args,
    _parse_args,
    build_historical_probability_calibration_profile_production_proposal_report,
    load_candidate_probability_calibration_profile,
    load_historical_probability_calibration_profile_grid_report,
    load_historical_probability_calibration_profile_rolling_admission_report,
    main,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionFold,
    HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
)


def test_probability_calibration_profile_production_proposal_ready() -> None:
    report = build_historical_probability_calibration_profile_production_proposal_report(
        _grid_report(),
        _rolling_admission_report(),
        candidate_profile=_profile(),
    )

    assert report.status == "runtime_profile_proposal_ready"
    assert report.runtime_profile_proposal_allowed is True
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert all(check.status == "passed" for check in report.checks)
    assert report.proposal_profile is not None
    assert report.proposal_profile.proposed_production_enabled is True
    assert report.proposal_profile.holdout_candidate_enabled is True
    assert report.proposal_profile.profile_key == "profile:test"
    assert report.proposal_profile.target_outcomes == ["draw"]
    assert report.proposal_profile.evidence_json["final_answer_changed_count"] == 2
    assert report.proposal_profile.source_report_keys["grid"] == "profile-grid:test"
    assert (
        "disable_if_default_profile_write_is_not_explicitly_approved"
        in report.proposal_profile.rollback_conditions
    )
    assert report.proposal_profile_set_json[
        "candidate_probability_calibration_profiles"
    ][0]["profile_key"] == "profile:test"


def test_probability_calibration_profile_production_proposal_holdout_only_when_roi_fails() -> None:
    report = build_historical_probability_calibration_profile_production_proposal_report(
        _grid_report(roi_delta=-0.01),
        _rolling_admission_report(roi_delta=-0.01),
        candidate_profile=_profile(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is True
    assert failed_checks == {"roi_delta"}
    assert report.proposal_profile is not None
    assert report.proposal_profile.proposed_production_enabled is False
    assert (
        "probability_calibration_profile_production_proposal:holdout_only"
        in report.warnings
    )


def test_probability_calibration_profile_production_proposal_blocks_shadow_profile() -> None:
    shadow_profile = _profile(mode="shadow")
    report = build_historical_probability_calibration_profile_production_proposal_report(
        _grid_report(),
        _rolling_admission_report(profile=shadow_profile),
        candidate_profile=shadow_profile,
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "candidate_profile_mode" in failed_checks
    assert report.proposal_profile is None


def test_probability_calibration_profile_proposal_blocks_missing_fold_objective() -> None:
    report = build_historical_probability_calibration_profile_production_proposal_report(
        _grid_report(include_fold_objective=False),
        _rolling_admission_report(),
        candidate_profile=_profile(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "grid_candidate_fold_objective_status" in failed_checks
    assert "grid_candidate_fold_objective_allowed" in failed_checks
    assert report.proposal_profile is None


def test_probability_calibration_profile_production_proposal_blocks_mismatch() -> None:
    report = build_historical_probability_calibration_profile_production_proposal_report(
        _grid_report(),
        _rolling_admission_report(profile=_profile(max_decimal_odds=3.40)),
        candidate_profile=_profile(max_decimal_odds=3.40),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "profile_matches_grid_candidate" in failed_checks
    assert report.proposal_profile is None


def test_probability_calibration_profile_production_proposal_cli_options_and_main(
    tmp_path: Path,
) -> None:
    grid_path = tmp_path / "grid.json"
    rolling_path = tmp_path / "rolling.json"
    candidate_profile_path = tmp_path / "candidate_profile.json"
    output_path = tmp_path / "proposal.json"
    profile_set_path = tmp_path / "profile_set.json"
    grid_path.write_text(
        f"{_grid_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rolling_path.write_text(
        f"{_rolling_admission_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    candidate_profile_path.write_text(
        f"{_profile().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--grid-report",
            str(grid_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--candidate-profile",
            str(candidate_profile_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_set_path),
            "--proposal-id",
            "custom-proposal",
            "--proposed-profile-version",
            "custom-profile-version",
            "--min-overall-adjusted-fixture-count",
            "20",
            "--min-overall-bucket-count",
            "2",
            "--min-profile-bucket-count",
            "1",
            "--min-final-answer-changed-count",
            "2",
            "--min-final-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "1.0",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.02",
            "--max-mean-calibration-error-delta",
            "0.03",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-cutoff-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--max-failed-fold-count",
            "0",
            "--allow-rejected-grid-candidate",
            "--allow-unaccepted-candidate-fold-objective",
            "--allow-unaccepted-rolling-admission",
            "--allow-shadow-only-candidate-profile",
            "--allow-non-active-profile",
            "--allow-source-key-mismatch",
            "--allow-profile-candidate-mismatch",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.proposal_id == "custom-proposal"
    assert options.proposed_profile_version == "custom-profile-version"
    assert options.min_overall_adjusted_fixture_count == 20
    assert options.min_overall_bucket_count == 2
    assert options.min_profile_bucket_count == 1
    assert options.min_final_answer_changed_count == 2
    assert options.min_final_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 1.0
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_mean_calibration_error_delta == 0.03
    assert options.require_grid_candidate_accepted is False
    assert options.require_candidate_fold_objective_accepted is False
    assert options.require_rolling_admission_accepted is False
    assert options.require_candidate_profile_allowed is False
    assert options.require_active_profile is False
    assert options.require_source_key_linkage is False
    assert options.require_profile_candidate_match is False
    assert load_historical_probability_calibration_profile_grid_report(
        grid_path
    ).report_key == "profile-grid:test"
    assert load_historical_probability_calibration_profile_rolling_admission_report(
        rolling_path
    ).report_key == "profile-rolling:test"
    assert load_candidate_probability_calibration_profile(
        candidate_profile_path
    ).profile_key == "profile:test"

    main(
        [
            "--grid-report",
            str(grid_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--candidate-profile",
            str(candidate_profile_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_set_path),
            "--min-final-answer-changed-count",
            "2",
            "--min-roi-delta",
            "0.02",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile_set = loads(profile_set_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_profile_proposal_ready"
    assert payload["runtime_profile_proposal_allowed"] is True
    assert profile_set["candidate_probability_calibration_profiles"][0][
        "profile_key"
    ] == "profile:test"


def _grid_report(
    *,
    roi_delta: float = 0.05,
    include_fold_objective: bool = True,
) -> HistoricalProbabilityCalibrationProfileGridReport:
    candidate = _candidate(
        roi_delta=roi_delta,
        include_fold_objective=include_fold_objective,
    )
    return HistoricalProbabilityCalibrationProfileGridReport(
        report_key="profile-grid:test",
        status="generated",
        grid_id="profile-grid-test",
        slice_count=6,
        fixture_count=60,
        total_grid_candidate_count=1,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        candidates=[candidate],
        accepted_candidates=[candidate],
        best_candidate=candidate,
    )


def _candidate(
    *,
    roi_delta: float = 0.05,
    include_fold_objective: bool = True,
) -> HistoricalProbabilityCalibrationProfileGridCandidate:
    fold_fields = (
        {
            "fold_objective_report_key": "profile-rolling:test",
            "fold_objective_status": "accepted",
            "fold_objective_candidate_profile_allowed": True,
            "fold_objective_failed_fold_count": 0,
            "fold_objective_active_competition_fold_count": 1,
            "fold_objective_active_season_cutoff_fold_count": 1,
            "fold_objective_active_rolling_fold_count": 1,
        }
        if include_fold_objective
        else {}
    )
    return HistoricalProbabilityCalibrationProfileGridCandidate(
        candidate_key="profile-candidate:test",
        rank=1,
        candidate_index=0,
        decision="accepted",
        target_outcomes=["draw"],
        probability_min=0.0,
        probability_max=1.0,
        min_decimal_odds=2.25,
        max_decimal_odds=3.45,
        blend_weight=0.10,
        gate_report_key="grid-gate:test",
        adjusted_fixture_count=40,
        skipped_fixture_count=0,
        passed_final_answer_gate=True,
        deltas_json={
            "final_answer_changed_count": 2,
            "final_hit_rate_delta": 0.04,
            "roi_delta": roi_delta,
            "profit_loss_delta": 5.0,
            "brier_score_delta": -0.01,
            "log_loss_delta": -0.02,
            "mean_calibration_error_delta": -0.03,
        },
        **fold_fields,
    )


def _rolling_admission_report(
    *,
    roi_delta: float = 0.05,
    profile: CandidateProbabilityCalibrationProfile | None = None,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    resolved_profile = profile or _profile()
    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport(
        report_key="profile-rolling:test",
        status="accepted",
        candidate_profile_allowed=True,
        shadow_allowed=True,
        source_artifact_report_key="artifact:test",
        source_gate_report_key="gate:test",
        profile=resolved_profile,
        overall_fold=HistoricalProbabilityCalibrationProfileRollingAdmissionFold(
            fold_id="overall:all",
            fold_type="overall",
            status="passed",
            source_slice_ids=["slice-1"],
            source_competition_ids=["TEST_LEAGUE"],
            source_season_ids=["2022-2023"],
            artifact_report_key="artifact:test",
            gate_report_key="gate:test",
            emitted_profile=True,
            passed_final_answer_gate=True,
            adjusted_fixture_count=40,
            bucket_count=1,
            selected_competition_ids=["TEST_LEAGUE"],
            final_hit_rate_delta=0.04,
            roi_delta=roi_delta,
            profit_loss_delta=5.0,
            brier_score_delta=-0.01,
            log_loss_delta=-0.02,
            mean_calibration_error_delta=-0.03,
        ),
        fold_count=3,
        active_fold_count=3,
        failed_fold_count=0,
        active_competition_fold_count=1,
        active_season_cutoff_fold_count=1,
        active_rolling_fold_count=1,
        checks=[],
        folds=[],
    )


def _profile(
    *,
    mode: str = "active",
    max_decimal_odds: float = 3.45,
) -> CandidateProbabilityCalibrationProfile:
    return CandidateProbabilityCalibrationProfile(
        profile_key="profile:test",
        source_report_key="gate:test",
        mode=mode,  # type: ignore[arg-type]
        segment_mode="market_odds_band",
        min_bucket_sample_size=10,
        blend_weight=0.10,
        target_competition_ids=("TEST_LEAGUE",),
        target_market_types=("1x2",),
        target_outcomes=("draw",),
        min_probability=0.0,
        max_probability=1.0,
        min_decimal_odds=2.25,
        max_decimal_odds=max_decimal_odds,
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.20,
                bucket_end=0.30,
                calibrated_probability=0.28,
                sample_size=20,
                competition_id="TEST_LEAGUE",
                market_type="1x2",
            )
        ],
    )
