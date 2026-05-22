from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps, loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.lifecycle_backtest import (
    PrematchRecommendationBacktestCheckpoint,
)

type RecommendationProviderIncidentSeverity = Literal[
    "info",
    "warning",
    "critical",
]
type RecommendationProviderIncidentStatus = Literal[
    "open",
    "acknowledged",
    "resolved",
    "ignored",
]

INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY = """
INSERT INTO recommendation_provider_incident_events (
  provider_incident_key,
  provider_name,
  provider_runtime_incident_report_id,
  fixture_id,
  competition_id,
  incident_type,
  severity,
  event_time_utc,
  observed_at_utc,
  status,
  affects_recommendations,
  excluded_fixture_ids_json,
  summary,
  payload_json
) VALUES (
  %(provider_incident_key)s,
  %(provider_name)s,
  %(provider_runtime_incident_report_id)s,
  %(fixture_id)s,
  %(competition_id)s,
  %(incident_type)s,
  %(severity)s,
  %(event_time_utc)s,
  %(observed_at_utc)s,
  %(status)s,
  %(affects_recommendations)s,
  %(excluded_fixture_ids_json)s::jsonb,
  %(summary)s,
  %(payload_json)s::jsonb
)
ON CONFLICT (provider_incident_key) DO UPDATE
SET
  provider_name = EXCLUDED.provider_name,
  provider_runtime_incident_report_id = EXCLUDED.provider_runtime_incident_report_id,
  fixture_id = EXCLUDED.fixture_id,
  competition_id = EXCLUDED.competition_id,
  incident_type = EXCLUDED.incident_type,
  severity = EXCLUDED.severity,
  event_time_utc = EXCLUDED.event_time_utc,
  observed_at_utc = EXCLUDED.observed_at_utc,
  status = EXCLUDED.status,
  affects_recommendations = EXCLUDED.affects_recommendations,
  excluded_fixture_ids_json = EXCLUDED.excluded_fixture_ids_json,
  summary = EXCLUDED.summary,
  payload_json = EXCLUDED.payload_json,
  updated_at = now()
RETURNING
  recommendation_provider_incident_event_id,
  provider_incident_key,
  provider_name,
  provider_runtime_incident_report_id,
  fixture_id,
  competition_id,
  incident_type,
  severity,
  event_time_utc,
  observed_at_utc,
  status,
  affects_recommendations,
  excluded_fixture_ids_json,
  summary,
  payload_json,
  created_at,
  updated_at
"""

LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY = """
SELECT
  recommendation_provider_incident_event_id,
  provider_incident_key,
  provider_name,
  provider_runtime_incident_report_id,
  fixture_id,
  competition_id,
  incident_type,
  severity,
  event_time_utc,
  observed_at_utc,
  status,
  affects_recommendations,
  excluded_fixture_ids_json,
  summary,
  payload_json,
  created_at,
  updated_at
FROM recommendation_provider_incident_events
WHERE event_time_utc >= %(window_start_utc)s
  AND event_time_utc <= %(window_end_utc)s
  AND (%(status)s::text IS NULL OR status = %(status)s::text)
  AND (
    %(only_affecting_recommendations)s = false
    OR affects_recommendations IS TRUE
  )
  AND (%(competition_id)s::text IS NULL OR competition_id = %(competition_id)s::text)
  AND (
    %(fixture_ids)s::text[] IS NULL
    OR fixture_id = ANY(%(fixture_ids)s::text[])
    OR excluded_fixture_ids_json ?| %(fixture_ids)s::text[]
  )
ORDER BY event_time_utc ASC, recommendation_provider_incident_event_id ASC
LIMIT %(limit)s
"""


class RecommendationProviderIncidentDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation provider incident event rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Write and return one recommendation provider incident event row."""


class RecommendationProviderIncidentEventInput(BaseModel):
    provider_incident_key: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    provider_runtime_incident_report_id: int | None = Field(default=None, gt=0)
    fixture_id: str | None = Field(default=None, min_length=1)
    competition_id: str | None = Field(default=None, min_length=1)
    incident_type: str = Field(min_length=1)
    severity: RecommendationProviderIncidentSeverity = "warning"
    event_time_utc: datetime
    observed_at_utc: datetime
    status: RecommendationProviderIncidentStatus = "open"
    affects_recommendations: bool = True
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    payload_json: dict[str, object] = Field(default_factory=dict)


class RecommendationProviderIncidentEventRecord(BaseModel):
    recommendation_provider_incident_event_id: int = Field(gt=0)
    provider_incident_key: str
    provider_name: str
    provider_runtime_incident_report_id: int | None = None
    fixture_id: str | None = None
    competition_id: str | None = None
    incident_type: str
    severity: RecommendationProviderIncidentSeverity
    event_time_utc: datetime
    observed_at_utc: datetime
    status: RecommendationProviderIncidentStatus
    affects_recommendations: bool
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    payload_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    def active_at(self, as_of_time_utc: datetime) -> bool:
        if not self.affects_recommendations:
            return False
        if self.status not in {"open", "acknowledged"}:
            return False
        return _aware_utc(self.event_time_utc) <= _aware_utc(as_of_time_utc)

    def affected_fixture_ids(self) -> list[str]:
        return _dedupe_strings(
            [
                *(self.excluded_fixture_ids),
                *([self.fixture_id] if self.fixture_id is not None else []),
            ]
        )


class RecommendationProviderIncidentQueryOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    status: RecommendationProviderIncidentStatus | None = None
    only_affecting_recommendations: bool = True
    fixture_ids: tuple[str, ...] = ()
    competition_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=500, ge=1, le=5_000)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)


class PostgresRecommendationProviderIncidentRepository:
    def __init__(self, database: RecommendationProviderIncidentDatabaseExecutor) -> None:
        self.database = database

    def record_event(
        self,
        event: RecommendationProviderIncidentEventInput,
    ) -> RecommendationProviderIncidentEventRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY,
                _incident_event_params(event),
            )
        )
        return _incident_event_from_row(row)

    def list_events(
        self,
        *,
        options: RecommendationProviderIncidentQueryOptions,
    ) -> list[RecommendationProviderIncidentEventRecord]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_PROVIDER_INCIDENT_EVENTS_QUERY,
            {
                "window_start_utc": options.normalized_window_start_utc,
                "window_end_utc": options.normalized_window_end_utc,
                "status": options.status,
                "only_affecting_recommendations": (
                    options.only_affecting_recommendations
                ),
                "fixture_ids": list(options.fixture_ids) or None,
                "competition_id": options.competition_id,
                "limit": options.limit,
            },
        )
        return [_incident_event_from_row(row) for row in rows]


def apply_provider_incidents_to_backtest_checkpoints(
    checkpoints: Sequence[PrematchRecommendationBacktestCheckpoint],
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
) -> list[PrematchRecommendationBacktestCheckpoint]:
    return [
        checkpoint.model_copy(
            update={
                "excluded_fixture_ids": _dedupe_strings(
                    [
                        *checkpoint.excluded_fixture_ids,
                        *_active_incident_fixture_ids(
                            incidents,
                            as_of_time_utc=checkpoint.as_of_time_utc,
                        ),
                    ]
                ),
                "incident_notes": {
                    **checkpoint.incident_notes,
                    **_active_incident_notes(
                        incidents,
                        as_of_time_utc=checkpoint.as_of_time_utc,
                    ),
                },
                "metadata_json": {
                    **checkpoint.metadata_json,
                    "provider_incident_event_keys": [
                        event.provider_incident_key
                        for event in incidents
                        if event.active_at(checkpoint.as_of_time_utc)
                    ],
                },
            }
        )
        for checkpoint in checkpoints
    ]


def _active_incident_fixture_ids(
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
    *,
    as_of_time_utc: datetime,
) -> list[str]:
    fixture_ids: list[str] = []
    for event in incidents:
        if not event.active_at(as_of_time_utc):
            continue
        fixture_ids.extend(event.affected_fixture_ids())
    return _dedupe_strings(fixture_ids)


def _active_incident_notes(
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
    *,
    as_of_time_utc: datetime,
) -> dict[str, str]:
    notes: dict[str, str] = {}
    for event in incidents:
        if not event.active_at(as_of_time_utc):
            continue
        summary = event.summary or event.incident_type
        for fixture_id in event.affected_fixture_ids():
            notes[fixture_id] = summary
    return notes


def _incident_event_params(event: RecommendationProviderIncidentEventInput) -> QueryParams:
    return {
        "provider_incident_key": event.provider_incident_key,
        "provider_name": event.provider_name,
        "provider_runtime_incident_report_id": (
            event.provider_runtime_incident_report_id
        ),
        "fixture_id": event.fixture_id,
        "competition_id": event.competition_id,
        "incident_type": event.incident_type,
        "severity": event.severity,
        "event_time_utc": _aware_utc(event.event_time_utc),
        "observed_at_utc": _aware_utc(event.observed_at_utc),
        "status": event.status,
        "affects_recommendations": event.affects_recommendations,
        "excluded_fixture_ids_json": _json(_dedupe_strings(event.excluded_fixture_ids)),
        "summary": event.summary,
        "payload_json": _json(event.payload_json),
    }


def _incident_event_from_row(
    row: DatabaseRow,
) -> RecommendationProviderIncidentEventRecord:
    return RecommendationProviderIncidentEventRecord(
        recommendation_provider_incident_event_id=_int(
            row["recommendation_provider_incident_event_id"]
        ),
        provider_incident_key=str(row["provider_incident_key"]),
        provider_name=str(row["provider_name"]),
        provider_runtime_incident_report_id=_optional_int(
            row.get("provider_runtime_incident_report_id")
        ),
        fixture_id=_optional_str(row.get("fixture_id")),
        competition_id=_optional_str(row.get("competition_id")),
        incident_type=str(row["incident_type"]),
        severity=_severity(row["severity"]),
        event_time_utc=_datetime(row["event_time_utc"]),
        observed_at_utc=_datetime(row["observed_at_utc"]),
        status=_status(row["status"]),
        affects_recommendations=_bool(row["affects_recommendations"]),
        excluded_fixture_ids=_string_list(row.get("excluded_fixture_ids_json")),
        summary=_optional_str(row.get("summary")),
        payload_json=_json_object(row.get("payload_json")),
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
    )


def _severity(value: object) -> RecommendationProviderIncidentSeverity:
    text = str(value)
    if text not in {"info", "warning", "critical"}:
        raise ValueError(f"unsupported recommendation provider incident severity: {text}")
    return text  # type: ignore[return-value]


def _status(value: object) -> RecommendationProviderIncidentStatus:
    text = str(value)
    if text not in {"open", "acknowledged", "resolved", "ignored"}:
        raise ValueError(f"unsupported recommendation provider incident status: {text}")
    return text  # type: ignore[return-value]


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, dict):
            return dict(loaded)
        raise ValueError("expected JSON object")
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"expected JSON object, got {type(value).__name__}")


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, list):
            return list(loaded)
        raise ValueError("expected JSON array")
    if isinstance(value, list | tuple):
        return list(value)
    raise ValueError(f"expected JSON array, got {type(value).__name__}")


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_array(value)]


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "t", "yes", "y"}
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f"expected boolean value, got {type(value).__name__}")
