from __future__ import annotations

from datetime import UTC, datetime
from json import loads

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.model_governance import ModelPromotionReview, ModelRollbackPlan
from nutmeg.model_governance.promotion_repository import (
    INSERT_MODEL_PROMOTION_REVIEW_QUERY,
    PostgresModelPromotionReviewRepository,
)


class FakeModelPromotionReviewDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return {
            "model_promotion_review_id": 91,
            "created_at": datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        }


def test_model_promotion_review_repository_persists_gate_artifacts() -> None:
    database = FakeModelPromotionReviewDatabase()
    repository = PostgresModelPromotionReviewRepository(database)
    review = ModelPromotionReview(
        candidate_model_version="dc-v1.5-candidate",
        baseline_model_version="poisson-m1.1.0",
        decision="keep_experiment",
        next_status="experiment",
        reasons=["candidate_calibration_unavailable"],
    )
    rollback_plan = ModelRollbackPlan(
        should_rollback=False,
        reasons=[],
        steps=[],
    )

    stored = repository.save_review(
        review=review,
        sample_size=120,
        metrics_json={"overall_log_loss_delta": -0.01},
        rollback_plan=rollback_plan,
    )

    query, params = database.fetch_one_calls[0]
    assert query == INSERT_MODEL_PROMOTION_REVIEW_QUERY
    assert params["candidate_model_version"] == "dc-v1.5-candidate"
    assert params["decision"] == "keep_experiment"
    assert params["next_status"] == "experiment"
    assert params["sample_size"] == 120
    assert loads(str(params["metrics_json"])) == {"overall_log_loss_delta": -0.01}
    assert loads(str(params["reasons_json"])) == ["candidate_calibration_unavailable"]
    assert loads(str(params["rollback_plan_json"])) == {
        "should_rollback": False,
        "target_model_version": None,
        "reasons": [],
        "steps": [],
    }
    assert stored.model_promotion_review_id == 91
    assert stored.review == review
    assert stored.rollback_plan == rollback_plan
