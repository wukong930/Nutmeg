from __future__ import annotations

from datetime import date

import pytest

from nutmeg.accuracy import compare_model_versions_stub
from nutmeg.domain.accuracy import BacktestRunSchema, DateWindow, ModelVersionMetrics


def test_model_version_comparison_stub_promotes_when_core_metrics_do_not_worsen() -> None:
    comparison = compare_model_versions_stub(
        candidate_metrics=ModelVersionMetrics(
            model_version="candidate",
            sample_size=120,
            log_loss=0.92,
            brier_score=0.18,
        ),
        baseline_metrics=ModelVersionMetrics(
            model_version="baseline",
            sample_size=120,
            log_loss=0.98,
            brier_score=0.20,
        ),
    )

    assert comparison.decision_stub == "promote_candidate"
    assert "candidate_log_loss_not_worse" in comparison.reasons
    assert "candidate_brier_not_worse" in comparison.reasons


def test_model_version_comparison_stub_requires_review_for_low_sample_size() -> None:
    comparison = compare_model_versions_stub(
        candidate_metrics=ModelVersionMetrics(
            model_version="candidate",
            sample_size=12,
            log_loss=0.80,
            brier_score=0.16,
        ),
        baseline_metrics=ModelVersionMetrics(
            model_version="baseline",
            sample_size=120,
            log_loss=0.90,
            brier_score=0.18,
        ),
    )

    assert comparison.decision_stub == "needs_review"
    assert "candidate_sample_size_low" in comparison.reasons


def test_backtest_run_schema_validates_walk_forward_mode() -> None:
    schema = BacktestRunSchema(
        mode="walk_forward",
        model_version="poisson-test",
        train_window=DateWindow(start_date=date(2022, 1, 1), end_date=date(2023, 1, 1)),
        validation_window=DateWindow(start_date=date(2023, 1, 2), end_date=date(2024, 1, 1)),
        test_window=DateWindow(start_date=date(2024, 1, 2), end_date=date(2025, 1, 1)),
        competitions=["EPL"],
    )

    assert schema.mode == "walk_forward"
    assert schema.as_of_time is None


def test_backtest_run_schema_requires_as_of_time_label() -> None:
    with pytest.raises(ValueError, match="as_of_time"):
        BacktestRunSchema(
            mode="as_of_time",
            model_version="poisson-test",
            test_window=DateWindow(start_date=date(2024, 1, 2), end_date=date(2025, 1, 1)),
        )
