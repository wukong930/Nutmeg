from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from json import dumps, loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.mapping_repository import ProviderEntityMappingRecord

type ProviderMappingReviewIssueType = Literal[
    "low_confidence",
    "same_provider_canonical_collision",
    "stale_mapping",
]
type ProviderMappingReviewSeverity = Literal["info", "warning", "critical"]

INSERT_PROVIDER_MAPPING_REVIEW_RUN_QUERY = """
INSERT INTO provider_mapping_review_runs (
  provider,
  entity_type,
  canonical_entity_id,
  low_confidence_threshold,
  stale_after_days,
  checked_mapping_count,
  issue_count,
  critical_count,
  warning_count,
  info_count,
  issues_json,
  requested_by,
  metadata_json
) VALUES (
  %(provider)s,
  %(entity_type)s,
  %(canonical_entity_id)s,
  %(low_confidence_threshold)s,
  %(stale_after_days)s,
  %(checked_mapping_count)s,
  %(issue_count)s,
  %(critical_count)s,
  %(warning_count)s,
  %(info_count)s,
  %(issues_json)s::jsonb,
  %(requested_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_mapping_review_run_id,
  provider,
  entity_type,
  canonical_entity_id,
  low_confidence_threshold,
  stale_after_days,
  checked_mapping_count,
  issue_count,
  critical_count,
  warning_count,
  info_count,
  issues_json,
  requested_by,
  created_at,
  metadata_json
"""

LIST_PROVIDER_MAPPING_REVIEW_RUNS_QUERY = """
SELECT
  provider_mapping_review_run_id,
  provider,
  entity_type,
  canonical_entity_id,
  low_confidence_threshold,
  stale_after_days,
  checked_mapping_count,
  issue_count,
  critical_count,
  warning_count,
  info_count,
  issues_json,
  requested_by,
  created_at,
  metadata_json
FROM provider_mapping_review_runs
ORDER BY created_at DESC, provider_mapping_review_run_id DESC
LIMIT %(limit)s
"""


class ProviderMappingReviewDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only review query."""


class ProviderMappingReviewOptions(BaseModel):
    low_confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    stale_after_days: int = Field(default=180, ge=1, le=3650)
    as_of_time_utc: datetime


class ProviderMappingReviewIssue(BaseModel):
    issue_id: str
    issue_type: ProviderMappingReviewIssueType
    severity: ProviderMappingReviewSeverity
    provider: str
    entity_type: str
    canonical_entity_id: str
    provider_entity_ids: list[str] = Field(default_factory=list)
    mapping_ids: list[int] = Field(default_factory=list)
    confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    latest_updated_at_utc: datetime | None = None
    reasons: list[str] = Field(default_factory=list)
    recommended_action: str


class ProviderMappingReviewResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    checked_mapping_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    issues: list[ProviderMappingReviewIssue] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderMappingReviewRunRecord(BaseModel):
    provider_mapping_review_run_id: int = Field(gt=0)
    provider: str | None = None
    entity_type: str | None = None
    canonical_entity_id: str | None = None
    low_confidence_threshold: float = Field(ge=0.0, le=1.0)
    stale_after_days: int = Field(ge=1)
    checked_mapping_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    issues: list[ProviderMappingReviewIssue] = Field(default_factory=list)
    requested_by: str | None = None
    created_at_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PostgresProviderMappingReviewRunRepository:
    def __init__(self, database: ProviderMappingReviewDatabase) -> None:
        self.database = database

    def save_review(
        self,
        *,
        result: ProviderMappingReviewResult,
        provider: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        requested_by: str | None = None,
    ) -> ProviderMappingReviewRunRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PROVIDER_MAPPING_REVIEW_RUN_QUERY,
                {
                    "provider": provider,
                    "entity_type": entity_type,
                    "canonical_entity_id": canonical_entity_id,
                    "low_confidence_threshold": _float(
                        result.metadata_json["low_confidence_threshold"]
                    ),
                    "stale_after_days": _int(result.metadata_json["stale_after_days"]),
                    "checked_mapping_count": result.checked_mapping_count,
                    "issue_count": result.issue_count,
                    "critical_count": result.critical_count,
                    "warning_count": result.warning_count,
                    "info_count": result.info_count,
                    "issues_json": _json(
                        [issue.model_dump(mode="json") for issue in result.issues]
                    ),
                    "requested_by": requested_by,
                    "metadata_json": _json(result.metadata_json),
                },
            )
        )
        return _run_record_from_row(row)

    def list_latest(self, *, limit: int = 10) -> list[ProviderMappingReviewRunRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_MAPPING_REVIEW_RUNS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_run_record_from_row(row) for row in rows]


def review_provider_entity_mappings(
    mappings: Sequence[ProviderEntityMappingRecord],
    *,
    options: ProviderMappingReviewOptions,
    dry_run: bool = True,
) -> ProviderMappingReviewResult:
    normalized_as_of = _aware_utc(options.as_of_time_utc)
    issues = [
        *_low_confidence_issues(mappings, options=options),
        *_canonical_collision_issues(mappings),
        *_stale_mapping_issues(mappings, options=options),
    ]
    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            _severity_rank(issue.severity),
            issue.issue_type,
            issue.provider,
            issue.entity_type,
            issue.canonical_entity_id,
        ),
    )
    critical_count = sum(1 for issue in sorted_issues if issue.severity == "critical")
    warning_count = sum(1 for issue in sorted_issues if issue.severity == "warning")
    info_count = sum(1 for issue in sorted_issues if issue.severity == "info")

    return ProviderMappingReviewResult(
        dry_run=dry_run,
        as_of_time_utc=normalized_as_of,
        checked_mapping_count=len(mappings),
        issue_count=len(sorted_issues),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        issues=sorted_issues,
        metadata_json={
            "low_confidence_threshold": options.low_confidence_threshold,
            "stale_after_days": options.stale_after_days,
            "review_policy": "provider_mapping_manual_review_v1",
        },
    )


def _low_confidence_issues(
    mappings: Sequence[ProviderEntityMappingRecord],
    *,
    options: ProviderMappingReviewOptions,
) -> list[ProviderMappingReviewIssue]:
    issues: list[ProviderMappingReviewIssue] = []
    for mapping in mappings:
        if mapping.confidence >= options.low_confidence_threshold:
            continue
        severity: ProviderMappingReviewSeverity = (
            "critical" if mapping.confidence < 0.5 else "warning"
        )
        issues.append(
            _issue(
                issue_type="low_confidence",
                severity=severity,
                provider=mapping.provider,
                entity_type=mapping.entity_type,
                canonical_entity_id=mapping.canonical_entity_id,
                provider_entity_ids=[mapping.provider_entity_id],
                mapping_ids=[mapping.mapping_id],
                confidence_min=mapping.confidence,
                latest_updated_at_utc=mapping.updated_at_utc,
                reasons=[
                    f"confidence_below_{options.low_confidence_threshold:.2f}",
                ],
                recommended_action="review_provider_entity_match",
            )
        )
    return issues


def _canonical_collision_issues(
    mappings: Sequence[ProviderEntityMappingRecord],
) -> list[ProviderMappingReviewIssue]:
    grouped: dict[tuple[str, str, str], list[ProviderEntityMappingRecord]] = {}
    for mapping in mappings:
        key = (mapping.provider, mapping.entity_type, mapping.canonical_entity_id)
        grouped.setdefault(key, []).append(mapping)

    issues: list[ProviderMappingReviewIssue] = []
    for (provider, entity_type, canonical_entity_id), records in grouped.items():
        provider_entity_ids = sorted({record.provider_entity_id for record in records})
        if len(provider_entity_ids) <= 1:
            continue
        severity: ProviderMappingReviewSeverity = (
            "warning" if entity_type in {"team", "player"} else "critical"
        )
        issues.append(
            _issue(
                issue_type="same_provider_canonical_collision",
                severity=severity,
                provider=provider,
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
                provider_entity_ids=provider_entity_ids,
                mapping_ids=sorted(record.mapping_id for record in records),
                confidence_min=min(record.confidence for record in records),
                latest_updated_at_utc=max(record.updated_at_utc for record in records),
                reasons=["multiple_provider_ids_for_same_canonical_entity"],
                recommended_action="confirm_or_split_canonical_mapping",
            )
        )
    return issues


def _stale_mapping_issues(
    mappings: Sequence[ProviderEntityMappingRecord],
    *,
    options: ProviderMappingReviewOptions,
) -> list[ProviderMappingReviewIssue]:
    cutoff = _aware_utc(options.as_of_time_utc) - timedelta(days=options.stale_after_days)
    issues: list[ProviderMappingReviewIssue] = []
    for mapping in mappings:
        if mapping.updated_at_utc >= cutoff:
            continue
        issues.append(
            _issue(
                issue_type="stale_mapping",
                severity="info",
                provider=mapping.provider,
                entity_type=mapping.entity_type,
                canonical_entity_id=mapping.canonical_entity_id,
                provider_entity_ids=[mapping.provider_entity_id],
                mapping_ids=[mapping.mapping_id],
                confidence_min=mapping.confidence,
                latest_updated_at_utc=mapping.updated_at_utc,
                reasons=[f"mapping_stale_over_{options.stale_after_days}_days"],
                recommended_action="refresh_mapping_evidence_before_production_use",
            )
        )
    return issues


def _issue(
    *,
    issue_type: ProviderMappingReviewIssueType,
    severity: ProviderMappingReviewSeverity,
    provider: str,
    entity_type: str,
    canonical_entity_id: str,
    provider_entity_ids: list[str],
    mapping_ids: list[int],
    confidence_min: float | None,
    latest_updated_at_utc: datetime | None,
    reasons: list[str],
    recommended_action: str,
) -> ProviderMappingReviewIssue:
    return ProviderMappingReviewIssue(
        issue_id=_issue_id(
            issue_type=issue_type,
            provider=provider,
            entity_type=entity_type,
            canonical_entity_id=canonical_entity_id,
            provider_entity_ids=provider_entity_ids,
            mapping_ids=mapping_ids,
        ),
        issue_type=issue_type,
        severity=severity,
        provider=provider,
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
        provider_entity_ids=provider_entity_ids,
        mapping_ids=mapping_ids,
        confidence_min=confidence_min,
        latest_updated_at_utc=(
            _aware_utc(latest_updated_at_utc) if latest_updated_at_utc is not None else None
        ),
        reasons=reasons,
        recommended_action=recommended_action,
    )


def _issue_id(
    *,
    issue_type: str,
    provider: str,
    entity_type: str,
    canonical_entity_id: str,
    provider_entity_ids: Sequence[str],
    mapping_ids: Sequence[int],
) -> str:
    seed = "|".join(
        [
            issue_type,
            provider,
            entity_type,
            canonical_entity_id,
            ",".join(sorted(provider_entity_ids)),
            ",".join(str(mapping_id) for mapping_id in sorted(mapping_ids)),
        ]
    )
    return sha1(seed.encode("utf-8")).hexdigest()[:16]


def _severity_rank(severity: ProviderMappingReviewSeverity) -> int:
    return {"critical": 0, "warning": 1, "info": 2}[severity]


def _run_record_from_row(row: DatabaseRow) -> ProviderMappingReviewRunRecord:
    return ProviderMappingReviewRunRecord(
        provider_mapping_review_run_id=_int(row["provider_mapping_review_run_id"]),
        provider=_optional_str(row["provider"]),
        entity_type=_optional_str(row["entity_type"]),
        canonical_entity_id=_optional_str(row["canonical_entity_id"]),
        low_confidence_threshold=_float(row["low_confidence_threshold"]),
        stale_after_days=_int(row["stale_after_days"]),
        checked_mapping_count=_int(row["checked_mapping_count"]),
        issue_count=_int(row["issue_count"]),
        critical_count=_int(row["critical_count"]),
        warning_count=_int(row["warning_count"]),
        info_count=_int(row["info_count"]),
        issues=_issue_list(row["issues_json"]),
        requested_by=_optional_str(row["requested_by"]),
        created_at_utc=_datetime(row["created_at"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_json(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _issue_list(value: object) -> list[ProviderMappingReviewIssue]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        return []
    return [
        ProviderMappingReviewIssue.model_validate(item)
        for item in parsed
        if isinstance(item, Mapping)
    ]


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


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))
