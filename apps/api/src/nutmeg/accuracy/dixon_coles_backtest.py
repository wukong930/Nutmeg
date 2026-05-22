from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from pydantic import BaseModel

from nutmeg.accuracy.model_comparison import compare_model_versions_stub
from nutmeg.domain.accuracy import (
    BacktestRunSchema,
    DateWindow,
    ModelComparisonStub,
    ModelVersionMetrics,
    StoredBacktestRun,
    StoredModelComparisonReport,
)
from nutmeg.modeling.dixon_coles_training import DixonColesTrainingReport


class BacktestWriteRepository(Protocol):
    def save_backtest_run(
        self,
        backtest_run: BacktestRunSchema,
        *,
        metrics_json: dict[str, object],
        calibration_json: dict[str, object] | None = None,
        report_uri: str | None = None,
    ) -> StoredBacktestRun:
        """Persist a model backtest run."""

    def save_model_comparison_report(
        self,
        comparison: ModelComparisonStub,
    ) -> StoredModelComparisonReport:
        """Persist a candidate-vs-baseline comparison report."""


class StoredDixonColesBacktestArtifacts(BaseModel):
    backtest_run: StoredBacktestRun
    model_comparison_report: StoredModelComparisonReport


def backtest_run_from_dixon_coles_training_report(
    report: DixonColesTrainingReport,
) -> BacktestRunSchema:
    train_end_date = (report.validation_start_utc - timedelta(days=1)).date()
    validation_window = DateWindow(
        start_date=report.validation_start_utc.date(),
        end_date=report.validation_end_utc.date(),
    )
    return BacktestRunSchema(
        mode="walk_forward",
        model_version=report.model_version,
        train_window=DateWindow(
            start_date=report.train_start_utc.date(),
            end_date=train_end_date,
        ),
        validation_window=validation_window,
        test_window=validation_window,
        competitions=report.competition_ids,
        notes_json={
            "source": "dixon_coles_training_report",
            "validation_used_as_test_window": True,
            "selected_rho": report.selected_rho,
            "time_decay_xi": report.time_decay_xi,
            "score_grid_regression_passed": report.score_grid_regression_passed,
            "warnings": report.warnings,
        },
    )


def metrics_json_from_dixon_coles_training_report(
    report: DixonColesTrainingReport,
) -> dict[str, object]:
    return {
        **report.metrics_json,
        "metric_basis": "score_probability_negative_weighted_log_likelihood",
        "as_of_time_utc": report.as_of_time_utc.isoformat(),
        "train_start_utc": report.train_start_utc.isoformat(),
        "validation_start_utc": report.validation_start_utc.isoformat(),
        "validation_end_utc": report.validation_end_utc.isoformat(),
        "fitted_parameters": report.fitted_parameters.model_dump(mode="json"),
    }


def calibration_json_from_dixon_coles_training_report(
    report: DixonColesTrainingReport,
) -> dict[str, object]:
    return {
        "calibration_status": "not_fitted",
        "calibration_required_before_promotion": True,
        "model_version": report.model_version,
    }


def model_metrics_from_dixon_coles_training_report(
    report: DixonColesTrainingReport,
    *,
    brier_score: float | None = None,
    ece: float | None = None,
) -> ModelVersionMetrics:
    brier_available = brier_score is not None
    return ModelVersionMetrics(
        model_version=report.model_version,
        sample_size=report.validation_sample_size,
        log_loss=report.validation_negative_weighted_log_likelihood,
        brier_score=brier_score if brier_score is not None else 0.0,
        ece=ece,
        metrics_json={
            **metrics_json_from_dixon_coles_training_report(report),
            "log_loss_basis": "actual_score_probability",
            "brier_score_available": brier_available,
            "ece_available": ece is not None,
        },
    )


def compare_dixon_coles_training_report_to_baseline(
    report: DixonColesTrainingReport,
    *,
    baseline_metrics: ModelVersionMetrics,
    candidate_brier_score: float | None = None,
    candidate_ece: float | None = None,
) -> ModelComparisonStub:
    candidate_metrics = model_metrics_from_dixon_coles_training_report(
        report,
        brier_score=(
            candidate_brier_score
            if candidate_brier_score is not None
            else baseline_metrics.brier_score
        ),
        ece=candidate_ece,
    )
    comparison = compare_model_versions_stub(
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
    )

    reasons = list(comparison.reasons)
    decision = comparison.decision_stub
    if candidate_brier_score is None:
        decision = "needs_review"
        reasons.append("candidate_brier_unavailable")
    if candidate_ece is None:
        decision = "needs_review"
        reasons.append("candidate_calibration_unavailable")
    if not report.score_grid_regression_passed:
        decision = "needs_review"
        reasons.append("score_grid_regression_failed")
    if report.warnings:
        reasons.append("candidate_training_warnings_present")

    return comparison.model_copy(
        update={
            "decision_stub": decision,
            "reasons": list(dict.fromkeys(reasons)),
        }
    )


def persist_dixon_coles_training_backtest(
    repository: BacktestWriteRepository,
    *,
    report: DixonColesTrainingReport,
    baseline_metrics: ModelVersionMetrics,
    candidate_brier_score: float | None = None,
    candidate_ece: float | None = None,
    extra_metrics_json: dict[str, object] | None = None,
    calibration_json: dict[str, object] | None = None,
    report_uri: str | None = None,
) -> StoredDixonColesBacktestArtifacts:
    metrics_json = {
        **metrics_json_from_dixon_coles_training_report(report),
        **(extra_metrics_json or {}),
    }
    backtest_run = repository.save_backtest_run(
        backtest_run_from_dixon_coles_training_report(report),
        metrics_json=metrics_json,
        calibration_json=(
            calibration_json
            if calibration_json is not None
            else calibration_json_from_dixon_coles_training_report(report)
        ),
        report_uri=report_uri,
    )
    comparison = compare_dixon_coles_training_report_to_baseline(
        report,
        baseline_metrics=baseline_metrics,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
    )
    model_comparison_report = repository.save_model_comparison_report(comparison)
    return StoredDixonColesBacktestArtifacts(
        backtest_run=backtest_run,
        model_comparison_report=model_comparison_report,
    )
