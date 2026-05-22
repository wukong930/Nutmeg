from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    build_historical_prematch_feature_asian_handicap_role_admission_report,
    load_historical_prematch_feature_asian_handicap_role_admission_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_role_admission import (
    _options_from_args,
    _parse_args,
    main,
)


def test_asian_handicap_role_admission_accepts_line_aware_shadow_candidate() -> None:
    source_report = _role_search_report()

    report = build_historical_prematch_feature_asian_handicap_role_admission_report(
        [source_report],
        options=HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions(
            admission_id="ah-role-admission-test",
            min_validation_count=100,
            min_selected_line_movement_weight=0.01,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_model_allowed is True
    assert report.shadow_allowed is True
    assert report.default_path_isolated is True
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.selected_candidate_id == source_report.best_accepted_candidate.candidate_id
    assert report.folds[0].status == "passed"


def test_asian_handicap_role_admission_shadows_when_extra_report_fails() -> None:
    accepted_report = _role_search_report(role_search_id="accepted")
    failed_report = _role_search_report(
        role_search_id="failed",
        accepted_nonzero_candidate_count=0,
        best_accepted_candidate=None,
    )

    report = build_historical_prematch_feature_asian_handicap_role_admission_report(
        [accepted_report, failed_report],
        options=HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions(
            min_source_report_count=2,
            min_accepted_report_count=1,
            max_failed_report_count=0,
        ),
    )

    assert report.status == "shadow_only"
    assert report.candidate_model_allowed is False
    assert report.shadow_allowed is True
    assert report.failed_report_count == 1
    assert "asian_handicap_role_admission:failed_check:failed_report_count" in (
        report.warnings
    )


def test_asian_handicap_role_admission_cli_writes_report(tmp_path: Path) -> None:
    source_path = tmp_path / "role_search.json"
    output_path = tmp_path / "admission.json"
    source_path.write_text(
        f"{_role_search_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--source-role-search-report",
            str(source_path),
            "--admission-id",
            "ah-role-admission-cli-test",
            "--output-path",
            str(output_path),
        ]
    )

    loaded = load_historical_prematch_feature_asian_handicap_role_admission_report(
        output_path
    )
    assert loaded.status == "accepted"
    assert loaded.admission_id == "ah-role-admission-cli-test"


def test_asian_handicap_role_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--source-role-search-report",
            "role_search.json",
            "--admission-id",
            "ah-role-admission-args-test",
            "--min-source-report-count",
            "2",
            "--min-accepted-report-count",
            "2",
            "--max-failed-report-count",
            "1",
            "--min-candidate-count",
            "32",
            "--min-accepted-nonzero-candidate-count",
            "2",
            "--min-validation-count",
            "80",
            "--min-selected-effective-weight",
            "0.02",
            "--min-selected-line-movement-weight",
            "0.03",
            "--min-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.02",
            "--max-expected-calibration-error-delta",
            "0.03",
            "--min-average-actual-probability-delta",
            "-0.04",
            "--max-warning-count",
            "3",
            "--allow-source-not-generated",
            "--allow-source-not-shadow-only",
            "--allow-selected-candidate-not-accepted",
            "--allow-default-path-not-isolated",
            "--allow-production-change",
            "--allow-public-response-change",
        ]
    )

    options = _options_from_args(args)

    assert options.admission_id == "ah-role-admission-args-test"
    assert options.min_source_report_count == 2
    assert options.min_accepted_report_count == 2
    assert options.max_failed_report_count == 1
    assert options.min_candidate_count == 32
    assert options.min_accepted_nonzero_candidate_count == 2
    assert options.min_validation_count == 80
    assert options.min_selected_effective_weight == 0.02
    assert options.min_selected_line_movement_weight == 0.03
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_expected_calibration_error_delta == 0.03
    assert options.min_average_actual_probability_delta == -0.04
    assert options.max_warning_count == 3
    assert options.require_source_status_generated is False
    assert options.require_source_shadow_only is False
    assert options.require_selected_candidate_accepted is False
    assert options.require_default_path_isolated is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False


def _role_search_report(
    *,
    role_search_id: str = "ah-line-aware-role-search-test",
    accepted_nonzero_candidate_count: int = 1,
    best_accepted_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None
    | object = ...,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    candidate = (
        _accepted_candidate()
        if best_accepted_candidate is ...
        else best_accepted_candidate
    )
    fallback_candidate = _accepted_candidate(status="control_passed")
    best_candidate = candidate or fallback_candidate
    return HistoricalPrematchFeatureAsianHandicapRoleSearchReport(
        report_key=f"prematch_feature_asian_handicap_role_search:{role_search_id}",
        status="generated",
        role_search_id=role_search_id,
        baseline_label="baseline",
        candidate_label="candidate",
        baseline_slice_count=25,
        candidate_slice_count=25,
        baseline_fixture_count=600,
        candidate_fixture_count=600,
        candidate_count=64,
        accepted_nonzero_candidate_count=accepted_nonzero_candidate_count,
        control_passed_candidate_count=4,
        watchlist_candidate_count=46,
        best_candidate=best_candidate,
        best_accepted_candidate=candidate,
        best_effective_candidate=candidate,
        best_control_candidate=fallback_candidate,
        candidates=[best_candidate],
        warnings=[],
        summary_json={
            "shadow_only": True,
            "candidate_count": 64,
            "accepted_nonzero_candidate_count": accepted_nonzero_candidate_count,
        },
    )


def _accepted_candidate(
    *,
    status: str = "accepted",
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate:
    return HistoricalPrematchFeatureAsianHandicapRoleCandidate(
        rank=1,
        candidate_id=f"candidate:{status}",
        status=status,
        comparison_report_key=f"comparison:{status}",
        baseline_report_key="baseline:report",
        candidate_report_key="candidate:report",
        asian_handicap_movement_weight=0.05 if status == "accepted" else 0.0,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05 if status == "accepted" else 0.0,
        min_asian_handicap_line_delta=0.0,
        asian_handicap_line_movement_scale=2.0,
        effective_asian_handicap_role=status == "accepted",
        baseline_validation_count=236,
        candidate_validation_count=236,
        candidate_asian_handicap_feature_coverage=1.0,
        passed_non_regression_gate=status == "accepted",
        ranking_score=-0.001,
        metric_deltas_json={
            "hit_rate": {"delta": 0.0},
            "brier_score": {"delta": -0.00002},
            "log_loss": {"delta": -0.00001},
            "expected_calibration_error": {"delta": -0.001},
            "average_actual_probability": {"delta": -0.000001},
        },
        warnings=[],
        summary_json={"status": status},
    )
