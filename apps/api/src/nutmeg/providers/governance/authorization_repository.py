from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from json import loads
from typing import Protocol, cast

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.contracts import (
    ProviderAuthorizationRecord,
    ProviderAuthorizationStatus,
    ProviderCapability,
)

LIST_PROVIDER_AUTHORIZATIONS_QUERY = """
SELECT
  provider_name,
  status,
  capabilities_json,
  terms_checked_at_utc,
  commercial_use_allowed,
  retention_allowed,
  allowed_use,
  rate_limit,
  historical_data_allowed,
  redistribution_allowed,
  terms_url,
  last_reviewed_at,
  next_review_due_at,
  owner,
  api_key_env_var,
  notes
FROM provider_authorizations
ORDER BY provider_name ASC
"""


class ProviderAuthorizationDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only provider authorization query."""


class PostgresProviderAuthorizationRepository:
    def __init__(self, database: ProviderAuthorizationDatabaseExecutor) -> None:
        self.database = database

    def list_authorizations(self) -> list[ProviderAuthorizationRecord]:
        rows = self.database.fetch_all(LIST_PROVIDER_AUTHORIZATIONS_QUERY, {})
        return [_authorization_from_row(row) for row in rows]


def _authorization_from_row(row: DatabaseRow) -> ProviderAuthorizationRecord:
    return ProviderAuthorizationRecord(
        provider_name=str(row["provider_name"]),
        status=cast(ProviderAuthorizationStatus, str(row["status"])),
        capabilities=tuple(
            cast(ProviderCapability, capability)
            for capability in _string_list(row["capabilities_json"])
        ),
        terms_checked_at_utc=_optional_datetime(row["terms_checked_at_utc"]),
        commercial_use_allowed=bool(row["commercial_use_allowed"]),
        retention_allowed=bool(row["retention_allowed"]),
        allowed_use=str(row.get("allowed_use") or "research_and_development"),
        rate_limit=_optional_text(row.get("rate_limit")),
        historical_data_allowed=bool(row.get("historical_data_allowed")),
        redistribution_allowed=bool(row.get("redistribution_allowed")),
        terms_url=_optional_text(row.get("terms_url")),
        last_reviewed_at=_optional_datetime(row.get("last_reviewed_at")),
        next_review_due_at=_optional_datetime(row.get("next_review_due_at")),
        owner=str(row.get("owner") or "nutmeg-ops"),
        api_key_env_var=_optional_text(row["api_key_env_var"]),
        notes=str(row["notes"] or ""),
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        parsed = loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
