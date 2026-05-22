from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type ProviderAuthorizationReviewStatus = Literal[
    "approved",
    "research_only",
    "needs_review",
    "blocked",
]

UPSERT_PROVIDER_AUTHORIZATION_REVIEW_QUERY = """
WITH review_record AS (
  INSERT INTO provider_authorization_reviews (
    provider_name,
    review_reference,
    review_status,
    reviewed_by,
    reviewed_at,
    terms_url,
    terms_version_hash,
    allowed_use,
    commercial_use_allowed,
    retention_allowed,
    historical_data_allowed,
    redistribution_allowed,
    rate_limit,
    next_review_due_at,
    evidence_json,
    notes
  ) VALUES (
    %(provider_name)s,
    %(review_reference)s,
    %(review_status)s,
    %(reviewed_by)s,
    %(reviewed_at)s,
    %(terms_url)s,
    %(terms_version_hash)s,
    %(allowed_use)s,
    %(commercial_use_allowed)s,
    %(retention_allowed)s,
    %(historical_data_allowed)s,
    %(redistribution_allowed)s,
    %(rate_limit)s,
    %(next_review_due_at)s,
    %(evidence_json)s::jsonb,
    %(notes)s
  )
  ON CONFLICT (provider_name, review_reference)
  DO UPDATE SET
    review_status = EXCLUDED.review_status,
    reviewed_by = EXCLUDED.reviewed_by,
    reviewed_at = EXCLUDED.reviewed_at,
    terms_url = EXCLUDED.terms_url,
    terms_version_hash = EXCLUDED.terms_version_hash,
    allowed_use = EXCLUDED.allowed_use,
    commercial_use_allowed = EXCLUDED.commercial_use_allowed,
    retention_allowed = EXCLUDED.retention_allowed,
    historical_data_allowed = EXCLUDED.historical_data_allowed,
    redistribution_allowed = EXCLUDED.redistribution_allowed,
    rate_limit = EXCLUDED.rate_limit,
    next_review_due_at = EXCLUDED.next_review_due_at,
    evidence_json = EXCLUDED.evidence_json,
    notes = EXCLUDED.notes
  RETURNING
    provider_authorization_review_id,
    provider_name,
    review_reference,
    review_status,
    reviewed_by,
    reviewed_at,
    terms_url,
    terms_version_hash,
    allowed_use,
    commercial_use_allowed,
    retention_allowed,
    historical_data_allowed,
    redistribution_allowed,
    rate_limit,
    next_review_due_at,
    evidence_json,
    notes,
    created_at
),
authorization_update AS (
  UPDATE provider_authorizations authorizations
  SET
    status = CASE
      WHEN review_record.review_status = 'blocked' THEN 'blocked'
      WHEN review_record.review_status = 'research_only' THEN 'research_only'
      WHEN review_record.review_status = 'approved'
        AND review_record.commercial_use_allowed
        AND review_record.retention_allowed THEN 'active'
      WHEN review_record.review_status = 'approved' THEN 'research_only'
      ELSE 'pending_review'
    END,
    terms_checked_at_utc = review_record.reviewed_at,
    last_reviewed_at = review_record.reviewed_at,
    next_review_due_at = review_record.next_review_due_at,
    commercial_use_allowed = review_record.commercial_use_allowed,
    retention_allowed = review_record.retention_allowed,
    allowed_use = review_record.allowed_use,
    rate_limit = review_record.rate_limit,
    historical_data_allowed = review_record.historical_data_allowed,
    redistribution_allowed = review_record.redistribution_allowed,
    terms_url = review_record.terms_url,
    owner = %(owner)s,
    notes = review_record.notes,
    updated_at = now()
  FROM review_record
  WHERE authorizations.provider_name = review_record.provider_name
  RETURNING authorizations.provider_name
)
SELECT
  provider_authorization_review_id,
  provider_name,
  review_reference,
  review_status,
  reviewed_by,
  reviewed_at,
  terms_url,
  terms_version_hash,
  allowed_use,
  commercial_use_allowed,
  retention_allowed,
  historical_data_allowed,
  redistribution_allowed,
  rate_limit,
  next_review_due_at,
  evidence_json,
  notes,
  created_at
FROM review_record
"""

LIST_PROVIDER_AUTHORIZATION_REVIEWS_QUERY = """
SELECT
  provider_authorization_review_id,
  provider_name,
  review_reference,
  review_status,
  reviewed_by,
  reviewed_at,
  terms_url,
  terms_version_hash,
  allowed_use,
  commercial_use_allowed,
  retention_allowed,
  historical_data_allowed,
  redistribution_allowed,
  rate_limit,
  next_review_due_at,
  evidence_json,
  notes,
  created_at
FROM provider_authorization_reviews
ORDER BY reviewed_at DESC, provider_authorization_review_id DESC
LIMIT %(limit)s
"""


class ProviderAuthorizationReviewDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class ProviderAuthorizationReviewInput(BaseModel):
    provider_name: str = Field(min_length=1)
    review_reference: str = Field(min_length=1, max_length=120)
    review_status: ProviderAuthorizationReviewStatus
    reviewed_by: str = Field(default="nutmeg-ops", min_length=1, max_length=120)
    reviewed_at: datetime | None = None
    terms_url: str | None = Field(default=None, max_length=500)
    terms_version_hash: str | None = Field(default=None, max_length=160)
    allowed_use: str = Field(min_length=1, max_length=240)
    commercial_use_allowed: bool = False
    retention_allowed: bool = False
    historical_data_allowed: bool = False
    redistribution_allowed: bool = False
    rate_limit: str | None = Field(default=None, max_length=240)
    next_review_due_at: datetime | None = None
    owner: str = Field(default="nutmeg-ops", min_length=1, max_length=120)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=1_000)


class ProviderAuthorizationReviewRecord(BaseModel):
    provider_authorization_review_id: int = Field(gt=0)
    provider_name: str
    review_reference: str
    review_status: ProviderAuthorizationReviewStatus
    reviewed_by: str
    reviewed_at: datetime
    terms_url: str | None = None
    terms_version_hash: str | None = None
    allowed_use: str
    commercial_use_allowed: bool
    retention_allowed: bool
    historical_data_allowed: bool
    redistribution_allowed: bool
    rate_limit: str | None = None
    next_review_due_at: datetime | None = None
    evidence_json: dict[str, object] = Field(default_factory=dict)
    notes: str = ""
    created_at: datetime


class PostgresProviderAuthorizationReviewRepository:
    def __init__(self, database: ProviderAuthorizationReviewDatabase) -> None:
        self.database = database

    def record_review(
        self,
        review: ProviderAuthorizationReviewInput,
    ) -> ProviderAuthorizationReviewRecord:
        reviewed_at = review.reviewed_at or datetime.now(tz=UTC)
        row = self.database.fetch_one(
            UPSERT_PROVIDER_AUTHORIZATION_REVIEW_QUERY,
            {
                "provider_name": review.provider_name,
                "review_reference": review.review_reference,
                "review_status": review.review_status,
                "reviewed_by": review.reviewed_by,
                "reviewed_at": reviewed_at,
                "terms_url": review.terms_url,
                "terms_version_hash": review.terms_version_hash,
                "allowed_use": review.allowed_use,
                "commercial_use_allowed": review.commercial_use_allowed,
                "retention_allowed": review.retention_allowed,
                "historical_data_allowed": review.historical_data_allowed,
                "redistribution_allowed": review.redistribution_allowed,
                "rate_limit": review.rate_limit,
                "next_review_due_at": review.next_review_due_at,
                "owner": review.owner,
                "evidence_json": _json(review.evidence_json),
                "notes": review.notes,
            },
        )
        if row is None:
            raise ValueError("expected provider authorization review RETURNING row")
        return _review_record_from_row(row)

    def list_latest(
        self,
        *,
        limit: int = 20,
    ) -> list[ProviderAuthorizationReviewRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_AUTHORIZATION_REVIEWS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_review_record_from_row(row) for row in rows]


def _review_record_from_row(row: DatabaseRow) -> ProviderAuthorizationReviewRecord:
    return ProviderAuthorizationReviewRecord(
        provider_authorization_review_id=_int(
            row["provider_authorization_review_id"]
        ),
        provider_name=str(row["provider_name"]),
        review_reference=str(row["review_reference"]),
        review_status=_review_status(row["review_status"]),
        reviewed_by=str(row["reviewed_by"]),
        reviewed_at=_datetime(row["reviewed_at"]),
        terms_url=_optional_str(row["terms_url"]),
        terms_version_hash=_optional_str(row["terms_version_hash"]),
        allowed_use=str(row["allowed_use"]),
        commercial_use_allowed=bool(row["commercial_use_allowed"]),
        retention_allowed=bool(row["retention_allowed"]),
        historical_data_allowed=bool(row["historical_data_allowed"]),
        redistribution_allowed=bool(row["redistribution_allowed"]),
        rate_limit=_optional_str(row["rate_limit"]),
        next_review_due_at=_optional_datetime(row["next_review_due_at"]),
        evidence_json=_object_mapping(row["evidence_json"]),
        notes=str(row["notes"] or ""),
        created_at=_datetime(row["created_at"]),
    )


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_json(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _review_status(value: object) -> ProviderAuthorizationReviewStatus:
    status = str(value)
    if status not in {"approved", "research_only", "needs_review", "blocked"}:
        raise ValueError(f"unsupported provider authorization review status: {status}")
    return cast(ProviderAuthorizationReviewStatus, status)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value))
