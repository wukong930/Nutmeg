from __future__ import annotations

from nutmeg.model_governance import (
    ModelPromotionInput,
    ModelRollbackSignal,
    evaluate_model_promotion,
    evaluate_model_rollback,
)


def test_model_promotion_requires_accuracy_calibration_and_market_evidence() -> None:
    review = evaluate_model_promotion(
        ModelPromotionInput(
            candidate_model_version="poisson-m1.1.0",
            baseline_model_version="poisson-m1.0.0",
            sample_size=600,
            overall_log_loss_delta=-0.01,
            overall_brier_delta=-0.005,
            calibration_error_delta=-0.002,
            core_market_improvement=True,
            upset_precision_at_k_delta=-0.005,
            handicap_performance_delta=0.001,
            low_sample_competition_drift=False,
        )
    )

    assert review.decision == "shadow_candidate"
    assert review.next_status == "shadow"
    assert review.reasons == ["candidate_passed_first_promotion_gate"]


def test_model_promotion_keeps_experiment_when_metrics_degrade() -> None:
    review = evaluate_model_promotion(
        ModelPromotionInput(
            candidate_model_version="poisson-m1.1.0",
            baseline_model_version="poisson-m1.0.0",
            sample_size=120,
            overall_log_loss_delta=0.02,
            overall_brier_delta=0.01,
            calibration_error_delta=0.01,
            core_market_improvement=False,
            upset_precision_at_k_delta=-0.04,
            handicap_performance_delta=-0.03,
            low_sample_competition_drift=True,
        )
    )

    assert review.decision == "keep_experiment"
    assert review.next_status == "experiment"
    assert "sample_size_below_minimum" in review.reasons
    assert "overall_log_loss_worse" in review.reasons
    assert "low_sample_competition_drift" in review.reasons


def test_model_rollback_plan_contains_documented_steps() -> None:
    plan = evaluate_model_rollback(
        ModelRollbackSignal(
            active_model_version="poisson-m1.1.0",
            previous_stable_model_version="poisson-m1.0.0",
            online_log_loss_delta=0.08,
            provider_incident_active=True,
            score_grid_normalization_error_count=2,
        )
    )

    assert plan.should_rollback is True
    assert plan.target_model_version == "poisson-m1.0.0"
    assert "online_log_loss_exceeded_threshold" in plan.reasons
    assert plan.steps == [
        "point_active_model_version_to_previous_stable",
        "pause_candidate_publication",
        "mark_impacted_predictions",
        "generate_incident_report",
    ]


def test_model_rollback_is_not_triggered_without_signals() -> None:
    plan = evaluate_model_rollback(
        ModelRollbackSignal(
            active_model_version="poisson-m1.0.0",
            previous_stable_model_version="poisson-m0.9.4",
        )
    )

    assert plan.should_rollback is False
    assert plan.target_model_version is None
    assert plan.reasons == []
