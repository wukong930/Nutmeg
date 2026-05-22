from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPoissonCompetitionParameterLearningResult,
    HistoricalPoissonParameterCandidate,
    HistoricalPoissonParameterLearningReport,
    HistoricalPoissonSegmentedAdmissionOptions,
    HistoricalPoissonWalkForwardComparisonGroup,
    HistoricalPoissonWalkForwardMetricSet,
    build_historical_poisson_segmented_admission_report,
)
from nutmeg.accuracy import historical_poisson_segmented_admission as segmented


def test_poisson_segmented_admission_accepts_local_no_harm_competition() -> None:
    report = build_historical_poisson_segmented_admission_report(
        _learning_report(
            [
                _competition_result(
                    "GOOD",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=74,
                        brier_score=0.19,
                        log_loss=0.58,
                        actual_probability=0.56,
                        calibration_error=0.01,
                    ),
                    baseline=_baseline_metric_set(120),
                    market_anchor_weight=0.50,
                ),
                _competition_result(
                    "BAD",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=68,
                        brier_score=0.22,
                        log_loss=0.64,
                        actual_probability=0.52,
                        calibration_error=0.04,
                    ),
                    baseline=_baseline_metric_set(120),
                    market_anchor_weight=0.50,
                ),
            ]
        ),
        options=HistoricalPoissonSegmentedAdmissionOptions(
            min_source_validation_count=200,
            min_competition_validation_count=100,
            min_admitted_validation_count=100,
        ),
    )
    decision_by_competition = {
        decision.competition_id: decision for decision in report.decisions
    }

    assert report.status == "accepted"
    assert report.segmented_candidate_model_allowed is True
    assert report.shadow_allowed is True
    assert report.admitted_competition_count == 1
    assert report.fallback_competition_count == 1
    assert report.admitted_validation_count == 120
    assert report.segmented_deltas_json["hit_rate_delta"] is not None
    assert report.segmented_deltas_json["hit_rate_delta"] > 0
    assert report.segmented_deltas_json["brier_score_delta"] < 0
    assert decision_by_competition["GOOD"].status == "admitted"
    assert decision_by_competition["BAD"].status == "baseline_fallback"
    assert "brier_score_delta_above_ceiling" in decision_by_competition["BAD"].reasons
    assert report.decision_payload_json["default_prediction_path_changed"] is False


def test_poisson_segmented_admission_keeps_no_local_signal_shadow_only() -> None:
    report = build_historical_poisson_segmented_admission_report(
        _learning_report(
            [
                _competition_result(
                    "BAD_A",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=68,
                        brier_score=0.22,
                        log_loss=0.64,
                        actual_probability=0.52,
                        calibration_error=0.04,
                    ),
                    baseline=_baseline_metric_set(120),
                    market_anchor_weight=0.50,
                ),
                _competition_result(
                    "BAD_B",
                    candidate=_metric_set(
                        sample_size=120,
                        hit_count=69,
                        brier_score=0.21,
                        log_loss=0.63,
                        actual_probability=0.53,
                        calibration_error=0.03,
                    ),
                    baseline=_baseline_metric_set(120),
                    market_anchor_weight=0.50,
                ),
            ]
        ),
        options=HistoricalPoissonSegmentedAdmissionOptions(
            min_source_validation_count=200,
            min_competition_validation_count=100,
            min_admitted_validation_count=100,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.segmented_candidate_model_allowed is False
    assert report.shadow_allowed is True
    assert report.admitted_competition_count == 0
    assert failed_checks == {"admitted_competition_count", "admitted_validation_count"}


def test_poisson_segmented_admission_cli_options_loader_and_main(tmp_path: Path) -> None:
    source_path = tmp_path / "learning.json"
    output_path = tmp_path / "segmented.json"
    source_path.write_text(
        f"{_learning_report([_competition_result('GOOD')]).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = segmented._parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-source-learned-competition-count",
            "1",
            "--min-source-validation-count",
            "100",
            "--min-source-candidate-count",
            "2",
            "--max-source-warning-count",
            "1",
            "--min-competition-validation-count",
            "80",
            "--min-admitted-competition-count",
            "1",
            "--min-admitted-validation-count",
            "80",
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
            "--min-selected-model-signal-weight",
            "0.10",
            "--allow-source-status-not-generated",
            "--allow-segmented-harm",
            "--allow-public-prediction-change",
            "--no-fail-process",
        ]
    )
    options = segmented._options_from_args(args)

    assert options.min_source_learned_competition_count == 1
    assert options.min_source_validation_count == 100
    assert options.min_source_candidate_count == 2
    assert options.max_source_warning_count == 1
    assert options.min_competition_validation_count == 80
    assert options.min_admitted_competition_count == 1
    assert options.min_admitted_validation_count == 80
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_expected_calibration_error_delta == 0.04
    assert options.min_average_actual_probability_delta == -0.02
    assert options.min_selected_model_signal_weight == 0.10
    assert options.require_source_status_generated is False
    assert options.require_segmented_no_harm is False
    assert options.require_no_public_prediction_change is False

    segmented.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-source-validation-count",
            "100",
            "--min-competition-validation-count",
            "80",
            "--min-admitted-validation-count",
            "80",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["segmented_candidate_model_allowed"] is True
    assert payload["source_report_key"] == "historical_poisson_parameter_learning:test"


def _learning_report(
    competitions: list[HistoricalPoissonCompetitionParameterLearningResult],
) -> HistoricalPoissonParameterLearningReport:
    validation_count = sum(
        competition.validation_fixture_count for competition in competitions
    )
    return HistoricalPoissonParameterLearningReport(
        report_key="historical_poisson_parameter_learning:test",
        status="generated",
        competition_count=len(competitions),
        learned_competition_count=len(competitions),
        candidate_count=4,
        fixture_count=validation_count * 2,
        validation_count=validation_count,
        selected_candidate_counts={"poisson_draw_0_4_marketanchor_0_5": len(competitions)},
        overall_validation_candidate=_baseline_metric_set(validation_count),
        overall_validation_baseline=_baseline_metric_set(validation_count),
        overall_validation_deltas_json={},
        competitions=competitions,
        warnings=[],
    )


def _competition_result(
    competition_id: str,
    *,
    candidate: HistoricalPoissonWalkForwardMetricSet | None = None,
    baseline: HistoricalPoissonWalkForwardMetricSet | None = None,
    market_anchor_weight: float = 0.50,
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
        selected_candidate=_candidate(market_anchor_weight=market_anchor_weight),
        selected_validation=_comparison_group(
            competition_id,
            candidate=resolved_candidate,
            baseline=resolved_baseline,
        ),
        baseline_validation=resolved_baseline,
        status="learned",
        warnings=[],
    )


def _candidate(*, market_anchor_weight: float) -> HistoricalPoissonParameterCandidate:
    return HistoricalPoissonParameterCandidate(
        candidate_key="poisson_draw_0_4_marketanchor_0_5",
        lambda_method="enhanced_weighted_home_away",
        score_grid_family="poisson",
        draw_correction_weight=0.4,
        market_anchor_weight=market_anchor_weight,
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
    calibration_error: float,
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
) -> dict[str, float | None]:
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
