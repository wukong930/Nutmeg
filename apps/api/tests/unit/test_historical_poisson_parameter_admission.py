from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPoissonCompetitionParameterLearningResult,
    HistoricalPoissonParameterAdmissionOptions,
    HistoricalPoissonParameterCandidate,
    HistoricalPoissonParameterLearningReport,
    HistoricalPoissonWalkForwardComparisonGroup,
    HistoricalPoissonWalkForwardMetricSet,
    build_historical_poisson_parameter_admission_report,
)
from nutmeg.accuracy import historical_poisson_parameter_admission as admission


def test_poisson_parameter_admission_accepts_no_harm_learning_report() -> None:
    report = build_historical_poisson_parameter_admission_report(
        _learning_report(
            validation_count=240,
            deltas={
                "hit_rate_delta": 0.01,
                "brier_score_delta": -0.01,
                "log_loss_delta": -0.02,
                "expected_calibration_error_delta": -0.01,
                "average_actual_probability_delta": 0.02,
            },
        ),
        options=HistoricalPoissonParameterAdmissionOptions(
            min_validation_count=200,
            min_average_actual_probability_delta=0.0,
        ),
    )

    assert report.status == "accepted"
    assert report.candidate_model_allowed is True
    assert report.shadow_allowed is True
    assert all(check.status == "passed" for check in report.checks)
    assert report.decision_payload_json["default_prediction_path_changed"] is False


def test_poisson_parameter_admission_keeps_regression_shadow_only() -> None:
    report = build_historical_poisson_parameter_admission_report(
        _learning_report(
            validation_count=240,
            deltas={
                "hit_rate_delta": -0.01,
                "brier_score_delta": 0.02,
                "log_loss_delta": 0.03,
                "expected_calibration_error_delta": 0.01,
                "average_actual_probability_delta": -0.01,
            },
        ),
        options=HistoricalPoissonParameterAdmissionOptions(
            min_validation_count=200,
            min_average_actual_probability_delta=0.0,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.candidate_model_allowed is False
    assert report.shadow_allowed is True
    assert {
        "hit_rate_delta",
        "brier_score_delta",
        "log_loss_delta",
        "expected_calibration_error_delta",
        "average_actual_probability_delta",
        "failed_competition_no_harm_count",
    }.issubset(failed_checks)


def test_poisson_parameter_admission_rejects_insufficient_validation() -> None:
    report = build_historical_poisson_parameter_admission_report(
        _learning_report(validation_count=20),
        options=HistoricalPoissonParameterAdmissionOptions(min_validation_count=100),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.candidate_model_allowed is False
    assert report.shadow_allowed is False
    assert failed_checks == {"validation_count"}


def test_poisson_parameter_admission_blocks_market_anchor_only_candidate() -> None:
    report = build_historical_poisson_parameter_admission_report(
        _learning_report(
            validation_count=240,
            deltas={
                "hit_rate_delta": 0.0,
                "brier_score_delta": 0.0,
                "log_loss_delta": 0.0,
                "expected_calibration_error_delta": 0.0,
                "average_actual_probability_delta": 0.0,
            },
            market_anchor_weight=1.0,
        ),
        options=HistoricalPoissonParameterAdmissionOptions(min_validation_count=200),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.candidate_model_allowed is False
    assert report.shadow_allowed is True
    assert failed_checks == {"selected_model_signal_weight"}
    assert report.min_selected_model_signal_weight == 0.0
    assert report.average_selected_model_signal_weight == 0.0


def test_poisson_parameter_admission_cli_options_loader_and_main(tmp_path: Path) -> None:
    source_path = tmp_path / "learning.json"
    output_path = tmp_path / "admission.json"
    source_path.write_text(
        f"{_learning_report(validation_count=240).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = admission._parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-learned-competition-count",
            "2",
            "--min-validation-count",
            "200",
            "--min-candidate-count",
            "3",
            "--max-warning-count",
            "1",
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
            "2",
            "--min-selected-model-signal-weight",
            "0.10",
            "--allow-source-status-not-generated",
            "--allow-public-prediction-change",
            "--no-fail-process",
        ]
    )
    options = admission._options_from_args(args)

    assert options.min_learned_competition_count == 2
    assert options.min_validation_count == 200
    assert options.min_candidate_count == 3
    assert options.max_warning_count == 1
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_expected_calibration_error_delta == 0.04
    assert options.min_average_actual_probability_delta == -0.02
    assert options.max_failed_competition_no_harm_count == 2
    assert options.min_selected_model_signal_weight == 0.10
    assert options.require_source_status_generated is False
    assert options.require_no_public_prediction_change is False

    admission.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-validation-count",
            "200",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["candidate_model_allowed"] is True
    assert payload["source_report_key"] == "historical_poisson_parameter_learning:test"


def _learning_report(
    *,
    validation_count: int,
    deltas: dict[str, float] | None = None,
    market_anchor_weight: float = 0.0,
) -> HistoricalPoissonParameterLearningReport:
    resolved_deltas = deltas or {
        "hit_rate_delta": 0.01,
        "brier_score_delta": -0.01,
        "log_loss_delta": -0.02,
        "expected_calibration_error_delta": -0.01,
        "average_actual_probability_delta": 0.02,
    }
    return HistoricalPoissonParameterLearningReport(
        report_key="historical_poisson_parameter_learning:test",
        status="generated",
        competition_count=2,
        learned_competition_count=2,
        candidate_count=4,
        fixture_count=320,
        validation_count=validation_count,
        selected_candidate_counts={"poisson_draw_0_4": 2},
        overall_validation_candidate=_metric_set(validation_count),
        overall_validation_baseline=_metric_set(validation_count),
        overall_validation_deltas_json=resolved_deltas,
        competitions=[
            _competition_result(
                "TEST_A",
                validation_count // 2,
                resolved_deltas,
                market_anchor_weight=market_anchor_weight,
            ),
            _competition_result(
                "TEST_B",
                validation_count // 2,
                resolved_deltas,
                market_anchor_weight=market_anchor_weight,
            ),
        ],
        warnings=[],
        summary_json={
            "calculation_basis": "historical_poisson_parameter_learning_v3_1",
            "report_key": "historical_poisson_parameter_learning:test",
            "validation_count": validation_count,
            "overall_validation_deltas_json": resolved_deltas,
        },
    )


def _competition_result(
    competition_id: str,
    validation_count: int,
    deltas: dict[str, float],
    *,
    market_anchor_weight: float,
) -> HistoricalPoissonCompetitionParameterLearningResult:
    return HistoricalPoissonCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=["2021", "2022"],
        validation_seasons=["2023"],
        candidate_count=4,
        training_fixture_count=120,
        validation_fixture_count=validation_count,
        selected_candidate=_candidate(market_anchor_weight=market_anchor_weight),
        selected_validation=_comparison_group(competition_id, validation_count, deltas),
        status="learned",
        warnings=[],
    )


def _candidate(*, market_anchor_weight: float) -> HistoricalPoissonParameterCandidate:
    return HistoricalPoissonParameterCandidate(
        candidate_key=(
            "poisson_draw_0_4"
            if market_anchor_weight == 0
            else f"poisson_draw_0_4_marketanchor_{market_anchor_weight}"
        ),
        lambda_method="enhanced_weighted_home_away",
        score_grid_family="poisson",
        draw_correction_weight=0.4,
        market_anchor_weight=market_anchor_weight,
    )


def _comparison_group(
    competition_id: str,
    validation_count: int,
    deltas: dict[str, float],
) -> HistoricalPoissonWalkForwardComparisonGroup:
    return HistoricalPoissonWalkForwardComparisonGroup(
        group_key=f"{competition_id}|validation",
        group_type="competition_season",
        label=f"{competition_id} validation",
        competition_id=competition_id,
        season="2023",
        validation_count=validation_count,
        skipped_count=0,
        candidate=_metric_set(validation_count),
        baseline=_metric_set(validation_count),
        deltas_json=deltas,
    )


def _metric_set(sample_size: int) -> HistoricalPoissonWalkForwardMetricSet:
    return HistoricalPoissonWalkForwardMetricSet(
        sample_size=sample_size,
        hit_count=sample_size,
        hit_rate=1.0,
        brier_score=0.20,
        log_loss=0.60,
        average_actual_probability=0.55,
        expected_calibration_error=0.02,
    )
