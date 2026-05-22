from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.mapping_review import (
    ProviderMappingReviewIssue,
    ProviderMappingReviewResult,
)

type ProviderConflictType = Literal[
    "provider_mapping_conflict",
    "provider_observation_conflict",
]
type ProviderConflictSeverity = Literal["info", "warning", "critical"]
type ProviderConflictStatus = Literal["open", "resolved", "ignored"]

INSERT_PROVIDER_CONFLICT_EVENT_QUERY = """
INSERT INTO provider_conflict_events (
  source_review_run_id,
  conflict_type,
  severity,
  entity_type,
  canonical_entity_id,
  provider_names_json,
  provider_entity_ids_json,
  trusted_provider,
  resolution_status,
  data_quality_score_delta,
  evidence_json,
  recommended_action,
  requested_by
) VALUES (
  %(source_review_run_id)s,
  %(conflict_type)s,
  %(severity)s,
  %(entity_type)s,
  %(canonical_entity_id)s,
  %(provider_names_json)s::jsonb,
  %(provider_entity_ids_json)s::jsonb,
  %(trusted_provider)s,
  %(resolution_status)s,
  %(data_quality_score_delta)s,
  %(evidence_json)s::jsonb,
  %(recommended_action)s,
  %(requested_by)s
)
RETURNING
  provider_conflict_event_id,
  source_review_run_id,
  conflict_type,
  severity,
  entity_type,
  canonical_entity_id,
  provider_names_json,
  provider_entity_ids_json,
  trusted_provider,
  resolution_status,
  data_quality_score_delta,
  evidence_json,
  recommended_action,
  requested_by,
  created_at,
  resolved_at
"""

LIST_PROVIDER_CONFLICT_EVENTS_QUERY = """
SELECT
  provider_conflict_event_id,
  source_review_run_id,
  conflict_type,
  severity,
  entity_type,
  canonical_entity_id,
  provider_names_json,
  provider_entity_ids_json,
  trusted_provider,
  resolution_status,
  data_quality_score_delta,
  evidence_json,
  recommended_action,
  requested_by,
  created_at,
  resolved_at
FROM provider_conflict_events
WHERE (%(status)s::text IS NULL OR resolution_status = %(status)s::text)
ORDER BY created_at DESC, provider_conflict_event_id DESC
LIMIT %(limit)s
"""

FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY = """
SELECT
  provider_conflict_event_id,
  source_review_run_id,
  conflict_type,
  severity,
  entity_type,
  canonical_entity_id,
  provider_names_json,
  provider_entity_ids_json,
  trusted_provider,
  resolution_status,
  data_quality_score_delta,
  evidence_json,
  recommended_action,
  requested_by,
  created_at,
  resolved_at
FROM provider_conflict_events
WHERE resolution_status = 'open'
  AND conflict_type = %(conflict_type)s
  AND entity_type = %(entity_type)s
  AND canonical_entity_id = %(canonical_entity_id)s
  AND provider_names_json = %(provider_names_json)s::jsonb
  AND provider_entity_ids_json = %(provider_entity_ids_json)s::jsonb
  AND (evidence_json ->> 'source_issue_id') IS NOT DISTINCT FROM %(source_issue_id)s
  AND (evidence_json ->> 'capability') IS NOT DISTINCT FROM %(capability)s
  AND (evidence_json ->> 'field_name') IS NOT DISTINCT FROM %(field_name)s
ORDER BY created_at DESC, provider_conflict_event_id DESC
LIMIT 1
"""

LIST_PROVIDER_CONFLICT_QUALITY_IMPACTS_QUERY = """
SELECT
  canonical_entity_id,
  COUNT(*) AS conflict_count,
  SUM(data_quality_score_delta) AS data_quality_score_delta,
  MAX(created_at) AS latest_conflict_at
FROM provider_conflict_events
WHERE resolution_status = 'open'
  AND entity_type = 'fixture'
  AND canonical_entity_id = ANY(%(fixture_ids)s::text[])
GROUP BY canonical_entity_id
"""

INSERT_PROVIDER_OBSERVATION_QUERY = """
INSERT INTO provider_observations (
  provider_name,
  capability,
  entity_type,
  canonical_entity_id,
  provider_entity_id,
  field_name,
  observed_value,
  observed_at_utc,
  confidence,
  payload_id,
  metadata_json
) VALUES (
  %(provider_name)s,
  %(capability)s,
  %(entity_type)s,
  %(canonical_entity_id)s,
  %(provider_entity_id)s,
  %(field_name)s,
  %(observed_value)s,
  %(observed_at_utc)s,
  %(confidence)s,
  %(payload_id)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_observation_id,
  provider_name,
  capability,
  entity_type,
  canonical_entity_id,
  provider_entity_id,
  field_name,
  observed_value,
  observed_at_utc,
  confidence,
  payload_id,
  metadata_json,
  created_at
"""

LIST_PROVIDER_OBSERVATIONS_QUERY = """
SELECT
  provider_observation_id,
  provider_name,
  capability,
  entity_type,
  canonical_entity_id,
  provider_entity_id,
  field_name,
  observed_value,
  observed_at_utc,
  confidence,
  payload_id,
  metadata_json,
  created_at
FROM provider_observations
WHERE observed_at_utc <= %(as_of_time_utc)s
  AND observed_at_utc >= %(window_start_utc)s
  AND (%(provider_name)s::text IS NULL OR provider_name = %(provider_name)s::text)
  AND (%(capability)s::text IS NULL OR capability = %(capability)s::text)
  AND (%(entity_type)s::text IS NULL OR entity_type = %(entity_type)s::text)
  AND (
    %(canonical_entity_id)s::text IS NULL
    OR canonical_entity_id = %(canonical_entity_id)s::text
  )
ORDER BY observed_at_utc DESC, provider_observation_id DESC
LIMIT %(limit)s
"""

UPDATE_PROVIDER_CONFLICT_RESOLUTION_QUERY = """
UPDATE provider_conflict_events
SET
  resolution_status = %(resolution_status)s,
  resolved_at = CASE
    WHEN %(resolution_status)s = 'open' THEN NULL
    ELSE now()
  END,
  evidence_json = evidence_json || %(resolution_metadata_json)s::jsonb
WHERE provider_conflict_event_id = %(provider_conflict_event_id)s
RETURNING
  provider_conflict_event_id,
  source_review_run_id,
  conflict_type,
  severity,
  entity_type,
  canonical_entity_id,
  provider_names_json,
  provider_entity_ids_json,
  trusted_provider,
  resolution_status,
  data_quality_score_delta,
  evidence_json,
  recommended_action,
  requested_by,
  created_at,
  resolved_at
"""


class ProviderConflictDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only provider conflict query."""


class TrustedProviderPriority(BaseModel):
    provider_name: str
    capability: str
    priority_rank: int = Field(ge=1)
    reason: str


class ProviderObservation(BaseModel):
    provider_name: str
    capability: str
    entity_type: str
    canonical_entity_id: str
    field_name: str
    value: str
    observed_at_utc: datetime
    provider_entity_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    payload_id: int | None = Field(default=None, gt=0)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class StoredProviderObservation(ProviderObservation):
    provider_observation_id: int = Field(gt=0)
    created_at_utc: datetime


class ProviderConflictEventDraft(BaseModel):
    source_issue_id: str | None = None
    conflict_type: ProviderConflictType
    severity: ProviderConflictSeverity
    entity_type: str
    canonical_entity_id: str
    provider_names: list[str] = Field(default_factory=list)
    provider_entity_ids: list[str] = Field(default_factory=list)
    trusted_provider: str | None = None
    data_quality_score_delta: float = Field(le=0.0, ge=-100.0)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    recommended_action: str


class ProviderConflictEventRecord(ProviderConflictEventDraft):
    provider_conflict_event_id: int = Field(gt=0)
    source_review_run_id: int | None = None
    resolution_status: ProviderConflictStatus = "open"
    requested_by: str | None = None
    created_at_utc: datetime
    resolved_at_utc: datetime | None = None


class ProviderConflictQualityImpact(BaseModel):
    fixture_id: str
    conflict_count: int = Field(ge=0)
    data_quality_score_delta: float = Field(le=0.0, ge=-100.0)
    provider_consistency_score: float = Field(ge=0.0, le=1.0)
    latest_conflict_at_utc: datetime | None = None


class ProviderConflictEvaluationResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    source_review_run_id: int | None = None
    checked_issue_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    provider_consistency_after_conflicts: float = Field(ge=0.0, le=1.0)
    data_quality_score_delta: float = Field(le=0.0, ge=-100.0)
    trusted_priorities: list[TrustedProviderPriority] = Field(default_factory=list)
    events: list[ProviderConflictEventDraft] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PostgresProviderConflictEventRepository:
    def __init__(self, database: ProviderConflictDatabase) -> None:
        self.database = database

    def save_events(
        self,
        *,
        result: ProviderConflictEvaluationResult,
        requested_by: str | None = None,
    ) -> list[ProviderConflictEventRecord]:
        records: list[ProviderConflictEventRecord] = []
        for event in result.events:
            provider_names_json = _json(event.provider_names)
            provider_entity_ids_json = _json(event.provider_entity_ids)
            evidence = {"source_issue_id": event.source_issue_id, **event.evidence_json}
            existing = self._find_open_event(
                event=event,
                provider_names_json=provider_names_json,
                provider_entity_ids_json=provider_entity_ids_json,
                evidence=evidence,
            )
            if existing is not None:
                records.append(existing)
                continue
            row = _required_row(
                self.database.fetch_one(
                    INSERT_PROVIDER_CONFLICT_EVENT_QUERY,
                    {
                        "source_review_run_id": result.source_review_run_id,
                        "conflict_type": event.conflict_type,
                        "severity": event.severity,
                        "entity_type": event.entity_type,
                        "canonical_entity_id": event.canonical_entity_id,
                        "provider_names_json": provider_names_json,
                        "provider_entity_ids_json": provider_entity_ids_json,
                        "trusted_provider": event.trusted_provider,
                        "resolution_status": "open",
                        "data_quality_score_delta": event.data_quality_score_delta,
                        "evidence_json": _json(evidence),
                        "recommended_action": event.recommended_action,
                        "requested_by": requested_by,
                    },
                )
            )
            records.append(_event_record_from_row(row))
        return records

    def _find_open_event(
        self,
        *,
        event: ProviderConflictEventDraft,
        provider_names_json: str,
        provider_entity_ids_json: str,
        evidence: Mapping[str, object],
    ) -> ProviderConflictEventRecord | None:
        row = self.database.fetch_one(
            FIND_OPEN_PROVIDER_CONFLICT_EVENT_QUERY,
            {
                "conflict_type": event.conflict_type,
                "entity_type": event.entity_type,
                "canonical_entity_id": event.canonical_entity_id,
                "provider_names_json": provider_names_json,
                "provider_entity_ids_json": provider_entity_ids_json,
                "source_issue_id": _optional_str(evidence.get("source_issue_id")),
                "capability": _optional_str(evidence.get("capability")),
                "field_name": _optional_str(evidence.get("field_name")),
            },
        )
        return _event_record_from_row(row) if row is not None else None

    def list_latest(
        self,
        *,
        status: ProviderConflictStatus | None = None,
        limit: int = 20,
    ) -> list[ProviderConflictEventRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_CONFLICT_EVENTS_QUERY,
            {"status": status, "limit": max(1, min(limit, 100))},
        )
        return [_event_record_from_row(row) for row in rows]

    def list_quality_impacts(
        self,
        *,
        fixture_ids: Sequence[str],
    ) -> dict[str, ProviderConflictQualityImpact]:
        normalized_fixture_ids = list(dict.fromkeys(fixture_ids))
        if not normalized_fixture_ids:
            return {}
        rows = self.database.fetch_all(
            LIST_PROVIDER_CONFLICT_QUALITY_IMPACTS_QUERY,
            {"fixture_ids": normalized_fixture_ids},
        )
        return {
            impact.fixture_id: impact
            for impact in (_quality_impact_from_row(row) for row in rows)
        }

    def update_resolution_status(
        self,
        *,
        provider_conflict_event_id: int,
        resolution_status: ProviderConflictStatus,
        requested_by: str | None = None,
        resolution_note: str | None = None,
    ) -> ProviderConflictEventRecord | None:
        metadata: dict[str, object] = {
            "resolution_updated_by": requested_by,
            "resolution_status": resolution_status,
        }
        if resolution_note is not None:
            metadata["resolution_note"] = resolution_note
        row = self.database.fetch_one(
            UPDATE_PROVIDER_CONFLICT_RESOLUTION_QUERY,
            {
                "provider_conflict_event_id": provider_conflict_event_id,
                "resolution_status": resolution_status,
                "resolution_metadata_json": _json(metadata),
            },
        )
        return _event_record_from_row(row) if row is not None else None


class PostgresProviderObservationRepository:
    def __init__(self, database: ProviderConflictDatabase) -> None:
        self.database = database

    def save_observations(
        self,
        observations: Sequence[ProviderObservation],
    ) -> list[StoredProviderObservation]:
        records: list[StoredProviderObservation] = []
        for observation in observations:
            row = _required_row(
                self.database.fetch_one(
                    INSERT_PROVIDER_OBSERVATION_QUERY,
                    {
                        "provider_name": observation.provider_name,
                        "capability": observation.capability,
                        "entity_type": observation.entity_type,
                        "canonical_entity_id": observation.canonical_entity_id,
                        "provider_entity_id": observation.provider_entity_id,
                        "field_name": observation.field_name,
                        "observed_value": observation.value,
                        "observed_at_utc": _aware_utc(observation.observed_at_utc),
                        "confidence": observation.confidence,
                        "payload_id": observation.payload_id,
                        "metadata_json": _json(observation.metadata_json),
                    },
                )
            )
            records.append(_stored_observation_from_row(row))
        return records

    def list_recent(
        self,
        *,
        as_of_time_utc: datetime,
        lookback_hours: int = 168,
        provider_name: str | None = None,
        capability: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        limit: int = 2_000,
    ) -> list[ProviderObservation]:
        normalized_as_of = _aware_utc(as_of_time_utc)
        rows = self.database.fetch_all(
            LIST_PROVIDER_OBSERVATIONS_QUERY,
            {
                "as_of_time_utc": normalized_as_of,
                "window_start_utc": normalized_as_of - _hours(lookback_hours),
                "provider_name": provider_name,
                "capability": capability,
                "entity_type": entity_type,
                "canonical_entity_id": canonical_entity_id,
                "limit": max(1, min(limit, 5_000)),
            },
        )
        return [_stored_observation_from_row(row) for row in rows]


def default_trusted_provider_priorities() -> list[TrustedProviderPriority]:
    return [
        TrustedProviderPriority(
            provider_name="football-data.org",
            capability="fixtures",
            priority_rank=10,
            reason="primary_schedule_result_reference",
        ),
        TrustedProviderPriority(
            provider_name="football-data.org",
            capability="results",
            priority_rank=10,
            reason="primary_schedule_result_reference",
        ),
        TrustedProviderPriority(
            provider_name="the-odds-api",
            capability="odds",
            priority_rank=10,
            reason="primary_odds_reference",
        ),
        TrustedProviderPriority(
            provider_name="sportmonks",
            capability="lineups",
            priority_rank=10,
            reason="primary_lineup_availability_reference",
        ),
        TrustedProviderPriority(
            provider_name="sportmonks",
            capability="injuries",
            priority_rank=10,
            reason="primary_lineup_availability_reference",
        ),
        TrustedProviderPriority(
            provider_name="sportmonks",
            capability="team_stats",
            priority_rank=10,
            reason="primary_stats_reference",
        ),
        TrustedProviderPriority(
            provider_name="football-data.org",
            capability="mapping",
            priority_rank=10,
            reason="fixture_mapping_reference",
        ),
        TrustedProviderPriority(
            provider_name="sportmonks",
            capability="mapping",
            priority_rank=20,
            reason="secondary_mapping_reference",
        ),
        TrustedProviderPriority(
            provider_name="the-odds-api",
            capability="mapping",
            priority_rank=30,
            reason="odds_event_mapping_reference",
        ),
        TrustedProviderPriority(
            provider_name="mock-local",
            capability="mapping",
            priority_rank=99,
            reason="development_only_mapping_reference",
        ),
    ]


def evaluate_mapping_review_conflicts(
    review: ProviderMappingReviewResult,
    *,
    dry_run: bool = True,
    source_review_run_id: int | None = None,
    trusted_priorities: Sequence[TrustedProviderPriority] | None = None,
) -> ProviderConflictEvaluationResult:
    priorities = list(trusted_priorities or default_trusted_provider_priorities())
    events = [
        event
        for issue in review.issues
        if (event := _event_from_mapping_review_issue(issue, priorities=priorities))
        is not None
    ]
    return _evaluation_result(
        events,
        dry_run=dry_run,
        as_of_time_utc=review.as_of_time_utc,
        checked_issue_count=review.issue_count,
        source_review_run_id=source_review_run_id,
        trusted_priorities=priorities,
        metadata_json={
            "source": "provider_mapping_review",
            "review_policy": review.metadata_json.get("review_policy"),
            "quality_policy": "provider_conflict_quality_penalty_v1",
        },
    )


def detect_provider_observation_conflicts(
    observations: Sequence[ProviderObservation],
    *,
    trusted_priorities: Sequence[TrustedProviderPriority] | None = None,
) -> list[ProviderConflictEventDraft]:
    priorities = list(trusted_priorities or default_trusted_provider_priorities())
    grouped: dict[tuple[str, str, str, str], list[ProviderObservation]] = {}
    for observation in observations:
        key = (
            observation.capability,
            observation.entity_type,
            observation.canonical_entity_id,
            observation.field_name,
        )
        grouped.setdefault(key, []).append(observation)

    events: list[ProviderConflictEventDraft] = []
    for (capability, entity_type, canonical_entity_id, field_name), records in grouped.items():
        values = {record.value for record in records}
        if len(values) <= 1:
            continue
        provider_names = sorted({record.provider_name for record in records})
        if len(provider_names) <= 1:
            continue
        provider_entity_ids = sorted(
            {
                record.provider_entity_id
                for record in records
                if record.provider_entity_id is not None
            }
        )
        severity: ProviderConflictSeverity = (
            "critical" if capability == "results" else "warning"
        )
        events.append(
            ProviderConflictEventDraft(
                source_issue_id=None,
                conflict_type="provider_observation_conflict",
                severity=severity,
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
                provider_names=provider_names,
                provider_entity_ids=provider_entity_ids,
                trusted_provider=_trusted_provider(
                    provider_names,
                    capability=capability,
                    priorities=priorities,
                ),
                data_quality_score_delta=_quality_delta_for_severity(severity),
                evidence_json={
                    "capability": capability,
                    "field_name": field_name,
                    "values_by_provider": {
                        record.provider_name: record.value for record in records
                    },
                    "observed_at_utc": [
                        _aware_utc(record.observed_at_utc).isoformat()
                        for record in records
                    ],
                },
                recommended_action="review_trusted_provider_priority_and_source_payloads",
            )
        )
    return sorted(
        events,
        key=lambda event: (
            _severity_rank(event.severity),
            event.entity_type,
            event.canonical_entity_id,
            event.conflict_type,
        ),
    )


def evaluate_observation_conflicts(
    observations: Sequence[ProviderObservation],
    *,
    dry_run: bool = True,
    as_of_time_utc: datetime,
    trusted_priorities: Sequence[TrustedProviderPriority] | None = None,
) -> ProviderConflictEvaluationResult:
    priorities = list(trusted_priorities or default_trusted_provider_priorities())
    events = detect_provider_observation_conflicts(
        observations,
        trusted_priorities=priorities,
    )
    return _evaluation_result(
        events,
        dry_run=dry_run,
        as_of_time_utc=as_of_time_utc,
        checked_issue_count=len(observations),
        trusted_priorities=priorities,
        metadata_json={
            "source": "provider_observation_conflict_detector",
            "quality_policy": "provider_conflict_quality_penalty_v1",
        },
    )


def evaluate_provider_conflict_events(
    events: Sequence[ProviderConflictEventDraft],
    *,
    dry_run: bool = True,
    as_of_time_utc: datetime,
    checked_issue_count: int = 0,
    trusted_priorities: Sequence[TrustedProviderPriority] | None = None,
    source_review_run_id: int | None = None,
    metadata_json: dict[str, object] | None = None,
) -> ProviderConflictEvaluationResult:
    priorities = list(trusted_priorities or default_trusted_provider_priorities())
    return _evaluation_result(
        events,
        dry_run=dry_run,
        as_of_time_utc=as_of_time_utc,
        checked_issue_count=checked_issue_count,
        source_review_run_id=source_review_run_id,
        trusted_priorities=priorities,
        metadata_json=metadata_json
        or {
            "source": "provider_conflict_event_evaluator",
            "quality_policy": "provider_conflict_quality_penalty_v1",
        },
    )


def _event_from_mapping_review_issue(
    issue: ProviderMappingReviewIssue,
    *,
    priorities: Sequence[TrustedProviderPriority],
) -> ProviderConflictEventDraft | None:
    if issue.issue_type == "stale_mapping":
        return None
    provider_names = [issue.provider]
    return ProviderConflictEventDraft(
        source_issue_id=issue.issue_id,
        conflict_type="provider_mapping_conflict",
        severity=issue.severity,
        entity_type=issue.entity_type,
        canonical_entity_id=issue.canonical_entity_id,
        provider_names=provider_names,
        provider_entity_ids=issue.provider_entity_ids,
        trusted_provider=_trusted_provider(
            provider_names,
            capability="mapping",
            priorities=priorities,
        ),
        data_quality_score_delta=_quality_delta_for_severity(issue.severity),
        evidence_json={
            "mapping_issue_type": issue.issue_type,
            "mapping_ids": issue.mapping_ids,
            "confidence_min": issue.confidence_min,
            "latest_updated_at_utc": (
                issue.latest_updated_at_utc.isoformat()
                if issue.latest_updated_at_utc is not None
                else None
            ),
            "reasons": issue.reasons,
        },
        recommended_action=issue.recommended_action,
    )


def _evaluation_result(
    events: Sequence[ProviderConflictEventDraft],
    *,
    dry_run: bool,
    as_of_time_utc: datetime,
    checked_issue_count: int,
    trusted_priorities: Sequence[TrustedProviderPriority],
    metadata_json: dict[str, object],
    source_review_run_id: int | None = None,
) -> ProviderConflictEvaluationResult:
    sorted_events = sorted(
        events,
        key=lambda event: (
            _severity_rank(event.severity),
            event.entity_type,
            event.canonical_entity_id,
            event.conflict_type,
            event.trusted_provider or "",
        ),
    )
    critical_count = sum(1 for event in sorted_events if event.severity == "critical")
    warning_count = sum(1 for event in sorted_events if event.severity == "warning")
    info_count = sum(1 for event in sorted_events if event.severity == "info")
    score_delta = max(
        -10.0,
        round(sum(event.data_quality_score_delta for event in sorted_events), 2),
    )
    provider_consistency = round(max(0.0, min(1.0, 1.0 + score_delta / 10.0)), 4)
    return ProviderConflictEvaluationResult(
        dry_run=dry_run,
        as_of_time_utc=_aware_utc(as_of_time_utc),
        source_review_run_id=source_review_run_id,
        checked_issue_count=checked_issue_count,
        conflict_count=len(sorted_events),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        provider_consistency_after_conflicts=provider_consistency,
        data_quality_score_delta=score_delta,
        trusted_priorities=list(trusted_priorities),
        events=list(sorted_events),
        metadata_json=metadata_json,
    )


def _trusted_provider(
    provider_names: Sequence[str],
    *,
    capability: str,
    priorities: Sequence[TrustedProviderPriority],
) -> str | None:
    if not provider_names:
        return None
    ranks = {
        (priority.provider_name, priority.capability): priority.priority_rank
        for priority in priorities
    }
    return sorted(
        provider_names,
        key=lambda provider: (ranks.get((provider, capability), 10_000), provider),
    )[0]


def _quality_delta_for_severity(severity: ProviderConflictSeverity) -> float:
    if severity == "critical":
        return -3.5
    if severity == "warning":
        return -1.5
    return -0.5


def _severity_rank(severity: ProviderConflictSeverity) -> int:
    return {"critical": 0, "warning": 1, "info": 2}[severity]


def _event_record_from_row(row: DatabaseRow) -> ProviderConflictEventRecord:
    return ProviderConflictEventRecord(
        provider_conflict_event_id=_int(row["provider_conflict_event_id"]),
        source_review_run_id=_optional_int(row["source_review_run_id"]),
        source_issue_id=_optional_str(_object_mapping(row["evidence_json"]).get("source_issue_id")),
        conflict_type=cast(ProviderConflictType, str(row["conflict_type"])),
        severity=cast(ProviderConflictSeverity, str(row["severity"])),
        entity_type=str(row["entity_type"]),
        canonical_entity_id=str(row["canonical_entity_id"]),
        provider_names=_string_list(row["provider_names_json"]),
        provider_entity_ids=_string_list(row["provider_entity_ids_json"]),
        trusted_provider=_optional_str(row["trusted_provider"]),
        resolution_status=cast(ProviderConflictStatus, str(row["resolution_status"])),
        data_quality_score_delta=_float(row["data_quality_score_delta"]),
        evidence_json=_object_mapping(row["evidence_json"]),
        recommended_action=str(row["recommended_action"]),
        requested_by=_optional_str(row["requested_by"]),
        created_at_utc=_datetime(row["created_at"]),
        resolved_at_utc=(
            _datetime(row["resolved_at"]) if row["resolved_at"] is not None else None
        ),
    )


def _stored_observation_from_row(row: DatabaseRow) -> StoredProviderObservation:
    return StoredProviderObservation(
        provider_observation_id=_int(row["provider_observation_id"]),
        provider_name=str(row["provider_name"]),
        capability=str(row["capability"]),
        entity_type=str(row["entity_type"]),
        canonical_entity_id=str(row["canonical_entity_id"]),
        provider_entity_id=_optional_str(row["provider_entity_id"]),
        field_name=str(row["field_name"]),
        value=str(row["observed_value"]),
        observed_at_utc=_datetime(row["observed_at_utc"]),
        confidence=_float(row["confidence"]),
        payload_id=_optional_int(row["payload_id"]),
        metadata_json=_object_mapping(row["metadata_json"]),
        created_at_utc=_datetime(row["created_at"]),
    )


def _quality_impact_from_row(row: DatabaseRow) -> ProviderConflictQualityImpact:
    score_delta = max(-10.0, min(0.0, _float(row["data_quality_score_delta"])))
    return ProviderConflictQualityImpact(
        fixture_id=str(row["canonical_entity_id"]),
        conflict_count=_int(row["conflict_count"]),
        data_quality_score_delta=score_delta,
        provider_consistency_score=round(max(0.0, min(1.0, 1.0 + score_delta / 10.0)), 4),
        latest_conflict_at_utc=(
            _datetime(row["latest_conflict_at"])
            if row["latest_conflict_at"] is not None
            else None
        ),
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


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if not isinstance(parsed, Mapping):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _string_list(value: object) -> list[str]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


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


def _hours(value: int) -> timedelta:
    return timedelta(hours=max(1, min(value, 24 * 365)))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


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
