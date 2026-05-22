from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPoissonCompetitionParameterLearningResult,
    HistoricalPoissonParameterCandidate,
    HistoricalPoissonParameterLearningReport,
    HistoricalPoissonPrematchLambdaAdmissionOptions,
    HistoricalPoissonWalkForwardComparisonGroup,
    HistoricalPoissonWalkForwardMetricSet,
    build_historical_poisson_prematch_lambda_admission_report,
)
from nutmeg.accuracy import historical_poisson_prematch_lambda_admission as admission
from nutmeg.accuracy.historical_poisson_walk_forward import HistoricalPoissonLambdaMethod
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)


def test_poisson_prematch_lambda_admission_accepts_no_harm_report() -> None:
    report = build_historical_poisson_prematch_lambda_admission_report(
        _learning_report([_competition_result("GOOD_A"), _competition_result("GOOD_B")]),
        sample_readiness_report=_readiness_report(),
        options=HistoricalPoissonPrematchLambdaAdmissionOptions(
            min_validation_count=200,
            min_ready_fixture_count=200,
            min_ready_competition_count=2,
            min_ready_season_count=3,
            min_ready_competition_season_count=6,
            min_average_actual_probability_delta=0.0,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_model_allowed is True
    assert report.shadow_allowed is True
    assert report.selected_prematch_candidate_count == 2
    assert report.selected_non_prematch_candidate_count == 0
    assert report.min_selected_prematch_signal_weight == 0.01
    assert report.min_selected_market_movement_weight == 0.5
    assert all(check.status == "passed" for check in report.checks)
    assert report.decision_payload_json["default_prediction_path_changed"] is False


def test_poisson_prematch_lambda_admission_keeps_regression_shadow_only() -> None:
    report = build_historical_poisson_prematch_lambda_admission_report(
        _learning_report(
            [
                _competition_result(
                    "BAD_A",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=65,
                        brier_score=0.23,
                        log_loss=0.66,
                        actual_probability=0.51,
                        calibration_error=None,
                    ),
                    odds_movement_weight=0.0,
                ),
                _competition_result(
                    "BAD_B",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=66,
                        brier_score=0.22,
                        log_loss=0.65,
                        actual_probability=0.52,
                        calibration_error=None,
                    ),
                    odds_movement_weight=0.0,
                ),
            ],
            overall_deltas={
                "hit_rate_delta": -0.04,
                "brier_score_delta": 0.02,
                "log_loss_delta": 0.03,
                "average_actual_probability_delta": -0.02,
                "expected_calibration_error_delta": None,
            },
        ),
        sample_readiness_report=_readiness_report(),
        options=HistoricalPoissonPrematchLambdaAdmissionOptions(
            min_validation_count=200,
            min_average_actual_probability_delta=0.0,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.candidate_model_allowed is False
    assert report.shadow_allowed is True
    assert {
        "selected_prematch_signal_weight",
        "selected_market_movement_weight",
        "hit_rate_delta",
        "brier_score_delta",
        "log_loss_delta",
        "expected_calibration_error_delta",
        "average_actual_probability_delta",
        "failed_competition_no_harm_count",
    }.issubset(failed_checks)


def test_poisson_prematch_lambda_admission_blocks_non_prematch_candidate() -> None:
    report = build_historical_poisson_prematch_lambda_admission_report(
        _learning_report(
            [_competition_result("BASELINE", lambda_method="enhanced_weighted_home_away")]
        ),
        sample_readiness_report=_readiness_report(),
        options=HistoricalPoissonPrematchLambdaAdmissionOptions(
            min_validation_count=100,
            min_ready_fixture_count=100,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.selected_prematch_candidate_count == 0
    assert report.selected_non_prematch_candidate_count == 1
    assert "selected_prematch_candidate_count" in failed_checks
    assert "selected_non_prematch_candidate_count" in failed_checks


def test_poisson_prematch_lambda_admission_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "learning.json"
    readiness_path = tmp_path / "readiness.json"
    output_path = tmp_path / "admission.json"
    source_path.write_text(
        f"{_learning_report([_competition_result('GOOD')]).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    readiness_path.write_text(
        f"{_readiness_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = admission._parse_args(
        [
            str(source_path),
            "--sample-readiness-report",
            str(readiness_path),
            "--output-path",
            str(output_path),
            "--min-learned-competition-count",
            "1",
            "--min-validation-count",
            "100",
            "--min-candidate-count",
            "2",
            "--max-warning-count",
            "1",
            "--min-ready-fixture-count",
            "100",
            "--min-ready-competition-count",
            "1",
            "--min-ready-season-count",
            "2",
            "--min-ready-competition-season-count",
            "2",
            "--min-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.02",
            "--max-log-loss-delta",
            "0.03",
            "--max-expected-calibration-error-delta",
            "0.04",
            "--min-average-actual-probability-delta",
            "-0.02",
            "--max-failed-competition-no-harm-count",
            "1",
            "--min-selected-prematch-signal-weight",
            "0.005",
            "--min-selected-market-movement-weight",
            "0.25",
            "--allow-source-status-not-generated",
            "--allow-missing-sample-readiness-report",
            "--allow-sample-readiness-shadow-only",
            "--allow-non-prematch-lambda-method",
            "--allow-public-prediction-change",
            "--no-fail-process",
        ]
    )
    options = admission._options_from_args(args)

    assert options.min_learned_competition_count == 1
    assert options.min_validation_count == 100
    assert options.min_candidate_count == 2
    assert options.max_warning_count == 1
    assert options.min_ready_fixture_count == 100
    assert options.min_ready_competition_count == 1
    assert options.min_ready_season_count == 2
    assert options.min_ready_competition_season_count == 2
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_expected_calibration_error_delta == 0.04
    assert options.min_average_actual_probability_delta == -0.02
    assert options.max_failed_competition_no_harm_count == 1
    assert options.min_selected_prematch_signal_weight == 0.005
    assert options.min_selected_market_movement_weight == 0.25
    assert options.require_source_status_generated is False
    assert options.require_sample_readiness_report is False
    assert options.require_sample_ready_allowed is False
    assert options.require_prematch_lambda_method is False
    assert options.require_no_public_prediction_change is False

    admission.main(
        [
            str(source_path),
            "--sample-readiness-report",
            str(readiness_path),
            "--output-path",
            str(output_path),
            "--min-validation-count",
            "100",
            "--min-ready-fixture-count",
            "100",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["candidate_model_allowed"] is True
    assert payload["source_report_key"] == "historical_poisson_parameter_learning:test"


def _learning_report(
    competitions: list[HistoricalPoissonCompetitionParameterLearningResult],
    *,
    overall_deltas: dict[str, object] | None = None,
) -> HistoricalPoissonParameterLearningReport:
    validation_count = sum(
        competition.validation_fixture_count for competition in competitions
    )
    deltas: dict[str, object] = overall_deltas or {
        "hit_rate_delta": 0.01,
        "brier_score_delta": -0.01,
        "log_loss_delta": -0.02,
        "average_actual_probability_delta": 0.02,
        "expected_calibration_error_delta": -0.01,
    }
    return HistoricalPoissonParameterLearningReport(
        report_key="historical_poisson_parameter_learning:test",
        status="generated",
        competition_count=len(competitions),
        learned_competition_count=len(competitions),
        candidate_count=4,
        fixture_count=validation_count * 2,
        validation_count=validation_count,
        selected_candidate_counts={"poisson_prematch_signal": len(competitions)},
        overall_validation_candidate=_baseline_metric_set(validation_count),
        overall_validation_baseline=_baseline_metric_set(validation_count),
        overall_validation_deltas_json=deltas,
        competitions=competitions,
        warnings=[],
    )


def _competition_result(
    competition_id: str,
    *,
    candidate: HistoricalPoissonWalkForwardMetricSet | None = None,
    baseline: HistoricalPoissonWalkForwardMetricSet | None = None,
    lambda_method: HistoricalPoissonLambdaMethod = "prematch_feature_adjusted",
    odds_movement_weight: float = 0.5,
) -> HistoricalPoissonCompetitionParameterLearningResult:
    resolved_candidate = candidate or _metric_set(
        sample_size=120,
        hit_count=74,
        brier_score=0.19,
        log_loss=0.58,
        actual_probability=0.56,
        calibration_error=0.01,
    )
    resolved_baseline = baseline or _baseline_metric_set(resolved_candidate.sample_size)
    return HistoricalPoissonCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=["2021", "2022"],
        validation_seasons=["2023"],
        candidate_count=4,
        training_fixture_count=240,
        validation_fixture_count=resolved_candidate.sample_size,
        selected_candidate=_candidate(
            lambda_method=lambda_method,
            odds_movement_weight=odds_movement_weight,
        ),
        selected_validation=_comparison_group(
            competition_id,
            candidate=resolved_candidate,
            baseline=resolved_baseline,
        ),
        baseline_validation=resolved_baseline,
        status="learned",
        warnings=[],
    )


def _candidate(
    *,
    lambda_method: HistoricalPoissonLambdaMethod,
    odds_movement_weight: float,
) -> HistoricalPoissonParameterCandidate:
    return HistoricalPoissonParameterCandidate(
        candidate_key="poisson_prematch_signal",
        lambda_method=lambda_method,
        score_grid_family="poisson",
        draw_correction_weight=0.4,
        prematch_feature_odds_movement_weight=odds_movement_weight,
        prematch_feature_draw_risk_weight=0.0,
        max_prematch_feature_lambda_adjustment=0.02,
    )


def _comparison_group(
    competition_id: str,
    *,
    candidate: HistoricalPoissonWalkForwardMetricSet,
    baseline: HistoricalPoissonWalkForwardMetricSet,
) -> HistoricalPoissonWalkForwardComparisonGroup:
    return HistoricalPoissonWalkForwardComparisonGroup(
        group_key=f"{competition_id}|validation",
        group_type="competition_season",
        label=f"{competition_id} validation",
        competition_id=competition_id,
        season="2023",
        validation_count=candidate.sample_size,
        skipped_count=0,
        candidate=candidate,
        baseline=baseline,
        deltas_json=_deltas(candidate, baseline),
    )


def _baseline_metric_set(sample_size: int) -> HistoricalPoissonWalkForwardMetricSet:
    return _metric_set(
        sample_size=sample_size,
        hit_count=72,
        brier_score=0.20,
        log_loss=0.60,
        actual_probability=0.55,
        calibration_error=0.02,
    )


def _metric_set(
    *,
    sample_size: int,
    hit_count: int,
    brier_score: float,
    log_loss: float,
    actual_probability: float,
    calibration_error: float | None,
) -> HistoricalPoissonWalkForwardMetricSet:
    return HistoricalPoissonWalkForwardMetricSet(
        sample_size=sample_size,
        hit_count=hit_count,
        hit_rate=hit_count / sample_size,
        brier_score=brier_score,
        log_loss=log_loss,
        average_actual_probability=actual_probability,
        expected_calibration_error=calibration_error,
    )


def _deltas(
    candidate: HistoricalPoissonWalkForwardMetricSet,
    baseline: HistoricalPoissonWalkForwardMetricSet,
) -> dict[str, object]:
    return {
        "hit_rate_delta": _delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _delta(candidate.brier_score, baseline.brier_score),
        "log_loss_delta": _delta(candidate.log_loss, baseline.log_loss),
        "expected_calibration_error_delta": _delta(
            candidate.expected_calibration_error,
            baseline.expected_calibration_error,
        ),
        "average_actual_probability_delta": _delta(
            candidate.average_actual_probability,
            baseline.average_actual_probability,
        ),
    }


def _delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _readiness_report() -> HistoricalPrematchFeatureSampleReadinessReport:
    return HistoricalPrematchFeatureSampleReadinessReport(
        readiness_key="historical_prematch_feature_sample_readiness:test",
        status="accepted",
        sample_ready_allowed=True,
        shadow_allowed=True,
        readiness_id="prematch-readiness-test",
        target_profile="market_movement",
        coverage_audit_key="historical_sample_coverage_audit:test",
        source_count=1,
        evaluated_source_count=1,
        accepted_source_count=1,
        shadow_only_source_count=0,
        rejected_source_count=0,
        ready_source_ids=["source:test"],
        ready_fixture_count=240,
        ready_slice_count=6,
        ready_competition_count=2,
        ready_season_count=3,
        ready_competition_season_count=6,
        checks=[],
        sources=[],
        warnings=[],
    )
