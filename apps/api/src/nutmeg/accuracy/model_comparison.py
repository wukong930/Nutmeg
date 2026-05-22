from __future__ import annotations

from typing import Literal

from nutmeg.domain.accuracy import ModelComparisonStub, ModelVersionMetrics


def compare_model_versions_stub(
    *,
    candidate_metrics: ModelVersionMetrics,
    baseline_metrics: ModelVersionMetrics,
) -> ModelComparisonStub:
    reasons: list[str] = []
    decision: Literal["promote_candidate", "keep_baseline", "needs_review"]
    candidate_better_or_equal_log_loss = candidate_metrics.log_loss <= baseline_metrics.log_loss
    candidate_better_or_equal_brier = (
        candidate_metrics.brier_score <= baseline_metrics.brier_score
    )

    if candidate_better_or_equal_log_loss:
        reasons.append("candidate_log_loss_not_worse")
    else:
        reasons.append("candidate_log_loss_worse")

    if candidate_better_or_equal_brier:
        reasons.append("candidate_brier_not_worse")
    else:
        reasons.append("candidate_brier_worse")

    if candidate_metrics.sample_size < 30:
        decision = "needs_review"
        reasons.append("candidate_sample_size_low")
    elif candidate_better_or_equal_log_loss and candidate_better_or_equal_brier:
        decision = "promote_candidate"
    else:
        decision = "keep_baseline"

    return ModelComparisonStub(
        candidate_model_version=candidate_metrics.model_version,
        baseline_model_version=baseline_metrics.model_version,
        candidate_metrics=candidate_metrics,
        baseline_metrics=baseline_metrics,
        decision_stub=decision,
        reasons=reasons,
    )
