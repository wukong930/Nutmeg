from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from json import dumps
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.model_governance.promotion import ModelPromotionReview, ModelRollbackPlan

INSERT_MODEL_PROMOTION_REVIEW_QUERY = """
INSERT INTO model_promotion_reviews (
  candidate_model_version,
  baseline_model_version,
  decision,
  next_status,
  sample_size,
  metrics_json,
  reasons_json,
  rollback_plan_json
) VALUES (
  %(candidate_model_version)s,
  %(baseline_model_version)s,
  %(decision)s,
  %(next_status)s,
  %(sample_size)s,
  %(metrics_json)s::jsonb,
  %(reasons_json)s::jsonb,
  %(rollback_plan_json)s::jsonb
)
RETURNING model_promotion_review_id, created_at
"""


class ModelPromotionReviewDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""


class StoredModelPromotionReview(BaseModel):
    model_promotion_review_id: int = Field(gt=0)
    created_at_utc: datetime
    review: ModelPromotionReview
    sample_size: int = Field(ge=0)
    metrics_json: dict[str, object] = Field(default_factory=dict)
    rollback_plan: ModelRollbackPlan


class PostgresModelPromotionReviewRepository:
    def __init__(self, database: ModelPromotionReviewDatabaseExecutor) -> None:
        self.database = database

    def save_review(
        self,
        *,
        review: ModelPromotionReview,
        sample_size: int,
        metrics_json: dict[str, object],
        rollback_plan: ModelRollbackPlan,
    ) -> StoredModelPromotionReview:
        row = _required_row(
            self.database.fetch_one(
                INSERT_MODEL_PROMOTION_REVIEW_QUERY,
                {
                    "candidate_model_version": review.candidate_model_version,
                    "baseline_model_version": review.baseline_model_version,
                    "decision": review.decision,
                    "next_status": review.next_status,
                    "sample_size": sample_size,
                    "metrics_json": _json(metrics_json),
                    "reasons_json": _json(review.reasons),
                    "rollback_plan_json": _json(rollback_plan.model_dump(mode="json")),
                },
            )
        )
        return StoredModelPromotionReview(
            model_promotion_review_id=_int(row["model_promotion_review_id"]),
            created_at_utc=_datetime(row["created_at"]),
            review=review,
            sample_size=sample_size,
            metrics_json=metrics_json,
            rollback_plan=rollback_plan,
        )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected model promotion review row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")
