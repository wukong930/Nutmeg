from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.conflicts import (
    PostgresProviderObservationRepository,
    ProviderObservation,
)
from nutmeg.recommendations.incidents import (
    PostgresRecommendationProviderIncidentRepository,
    RecommendationProviderIncidentEventInput,
    RecommendationProviderIncidentEventRecord,
    RecommendationProviderIncidentSeverity,
)

CRITICAL_AVAILABILITY_STATUSES = {
    "injured",
    "injury",
    "out",
    "ruled_out",
    "suspended",
    "unavailable",
    "not_available",
}
WARNING_AVAILABILITY_STATUSES = {
    "doubtful",
    "ill",
    "knock",
    "questionable",
    "sick",
    "uncertain",
}
LOW_RISK_AVAILABILITY_STATUSES = {
    "available",
    "fit",
    "healthy",
    "probable",
    "ready",
}


class ProviderIncidentMappingDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read provider observations."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Write recommendation provider incident events."""


class RecommendationProviderIncidentMappingOptions(BaseModel):
    as_of_time_utc: datetime
    lookback_hours: int = Field(default=24, ge=1, le=720)
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=2_000, ge=1, le=5_000)
    critical_availability_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    odds_probability_shift_threshold: float = Field(default=0.12, ge=0.01, le=1.0)
    critical_odds_probability_shift_threshold: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
    )
    dry_run: bool = True

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class RecommendationProviderIncidentMappingResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    observation_count: int = Field(ge=0)
    mapped_incident_count: int = Field(ge=0)
    stored_incident_count: int = Field(ge=0)
    incident_events: list[RecommendationProviderIncidentEventInput] = Field(
        default_factory=list
    )
    stored_events: list[RecommendationProviderIncidentEventRecord] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


def map_provider_observations_to_recommendation_incidents(
    observations: Sequence[ProviderObservation],
    *,
    options: RecommendationProviderIncidentMappingOptions,
) -> list[RecommendationProviderIncidentEventInput]:
    ordered_observations = sorted(
        observations,
        key=lambda observation: (
            _aware_utc(observation.observed_at_utc),
            _observation_id(observation) or 0,
            observation.provider_name,
            observation.field_name,
        ),
    )
    incidents: list[RecommendationProviderIncidentEventInput] = []
    incidents.extend(
        _availability_incidents(
            ordered_observations,
            options=options,
        )
    )
    incidents.extend(_lineup_incidents(ordered_observations))
    incidents.extend(
        _odds_shift_incidents(
            ordered_observations,
            shift_threshold=options.odds_probability_shift_threshold,
            critical_shift_threshold=options.critical_odds_probability_shift_threshold,
        )
    )
    return _dedupe_incidents(incidents)


def run_recommendation_provider_incident_mapping(
    database: ProviderIncidentMappingDatabaseExecutor,
    *,
    options: RecommendationProviderIncidentMappingOptions,
    incident_repository: PostgresRecommendationProviderIncidentRepository | None = None,
    observation_repository: PostgresProviderObservationRepository | None = None,
) -> RecommendationProviderIncidentMappingResult:
    observation_reader = observation_repository or PostgresProviderObservationRepository(
        database
    )
    observations = observation_reader.list_recent(
        as_of_time_utc=options.normalized_as_of_time_utc,
        lookback_hours=options.lookback_hours,
        provider_name=options.provider_name,
        entity_type="fixture",
        canonical_entity_id=options.canonical_fixture_id,
        limit=options.limit,
    )
    incidents = map_provider_observations_to_recommendation_incidents(
        observations,
        options=options,
    )
    stored_events: list[RecommendationProviderIncidentEventRecord] = []
    if not options.dry_run and incidents:
        writer = incident_repository or PostgresRecommendationProviderIncidentRepository(
            database
        )
        stored_events = [writer.record_event(incident) for incident in incidents]
    return RecommendationProviderIncidentMappingResult(
        dry_run=options.dry_run,
        as_of_time_utc=options.normalized_as_of_time_utc,
        observation_count=len(observations),
        mapped_incident_count=len(incidents),
        stored_incident_count=len(stored_events),
        incident_events=incidents,
        stored_events=stored_events,
    )


def _availability_incidents(
    observations: Sequence[ProviderObservation],
    *,
    options: RecommendationProviderIncidentMappingOptions,
) -> list[RecommendationProviderIncidentEventInput]:
    incidents: list[RecommendationProviderIncidentEventInput] = []
    for observation in observations:
        if observation.capability != "injuries":
            continue
        if not observation.field_name.startswith("availability:"):
            continue
        if not observation.field_name.endswith(":status"):
            continue
        status = _normalized_token(observation.value)
        if status in LOW_RISK_AVAILABILITY_STATUSES:
            continue
        if status in CRITICAL_AVAILABILITY_STATUSES:
            severity: RecommendationProviderIncidentSeverity = (
                "critical"
                if observation.confidence >= options.critical_availability_confidence
                else "warning"
            )
        elif status in WARNING_AVAILABILITY_STATUSES:
            severity = "warning"
        else:
            continue

        fixture_id = observation.canonical_entity_id
        excluded_fixture_ids = [fixture_id] if severity == "critical" else []
        player_name = _optional_text(observation.metadata_json.get("player_name"))
        summary_parts = ["player availability", observation.value]
        if player_name is not None:
            summary_parts.append(player_name)
        incidents.append(
            RecommendationProviderIncidentEventInput(
                provider_incident_key=_provider_incident_key(
                    "availability",
                    observation,
                ),
                provider_name=observation.provider_name,
                fixture_id=fixture_id,
                incident_type=f"player_availability_{status}",
                severity=severity,
                event_time_utc=_aware_utc(observation.observed_at_utc),
                observed_at_utc=_aware_utc(observation.observed_at_utc),
                affects_recommendations=True,
                excluded_fixture_ids=excluded_fixture_ids,
                summary=": ".join(summary_parts),
                payload_json=_observation_payload(observation),
            )
        )
    return incidents


def _lineup_incidents(
    observations: Sequence[ProviderObservation],
) -> list[RecommendationProviderIncidentEventInput]:
    incidents: list[RecommendationProviderIncidentEventInput] = []
    for observation in observations:
        if observation.capability != "lineups":
            continue
        if not observation.field_name.startswith("lineup:"):
            continue
        lineup_type = _normalized_token(
            _optional_text(observation.metadata_json.get("lineup_type")) or ""
        )
        if lineup_type != "confirmed":
            continue
        fixture_id = observation.canonical_entity_id
        if observation.field_name.endswith(":lineup_type"):
            incidents.append(
                RecommendationProviderIncidentEventInput(
                    provider_incident_key=_provider_incident_key(
                        "lineup_confirmed",
                        observation,
                    ),
                    provider_name=observation.provider_name,
                    fixture_id=fixture_id,
                    incident_type="confirmed_lineup_published",
                    severity="info",
                    event_time_utc=_aware_utc(observation.observed_at_utc),
                    observed_at_utc=_aware_utc(observation.observed_at_utc),
                    affects_recommendations=False,
                    excluded_fixture_ids=[],
                    summary="confirmed lineup published",
                    payload_json=_observation_payload(observation),
                )
            )
        if observation.field_name.endswith(":is_starter") and _is_false(observation.value):
            player_name = _optional_text(observation.metadata_json.get("player_name"))
            incidents.append(
                RecommendationProviderIncidentEventInput(
                    provider_incident_key=_provider_incident_key(
                        "confirmed_non_starter",
                        observation,
                    ),
                    provider_name=observation.provider_name,
                    fixture_id=fixture_id,
                    incident_type="confirmed_non_starter",
                    severity="warning",
                    event_time_utc=_aware_utc(observation.observed_at_utc),
                    observed_at_utc=_aware_utc(observation.observed_at_utc),
                    affects_recommendations=True,
                    excluded_fixture_ids=[],
                    summary=(
                        f"confirmed non-starter: {player_name}"
                        if player_name
                        else "confirmed non-starter"
                    ),
                    payload_json=_observation_payload(observation),
                )
            )
    return incidents


def _odds_shift_incidents(
    observations: Sequence[ProviderObservation],
    *,
    shift_threshold: float,
    critical_shift_threshold: float,
) -> list[RecommendationProviderIncidentEventInput]:
    grouped: dict[tuple[str, str, str, str], list[ProviderObservation]] = {}
    for observation in observations:
        if observation.capability != "odds":
            continue
        if not observation.field_name.startswith("fair_probability:"):
            continue
        key = (
            observation.provider_name,
            observation.canonical_entity_id,
            observation.field_name,
            str(observation.metadata_json.get("bookmaker", "")),
        )
        grouped.setdefault(key, []).append(observation)

    incidents: list[RecommendationProviderIncidentEventInput] = []
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda observation: (
                _aware_utc(observation.observed_at_utc),
                _observation_id(observation) or 0,
            ),
        )
        if len(ordered) < 2:
            continue
        previous = ordered[-2]
        current = ordered[-1]
        previous_probability = _optional_probability(previous.value)
        current_probability = _optional_probability(current.value)
        if previous_probability is None or current_probability is None:
            continue
        delta = round(current_probability - previous_probability, 6)
        if abs(delta) < shift_threshold:
            continue
        severity: RecommendationProviderIncidentSeverity = (
            "critical" if abs(delta) >= critical_shift_threshold else "warning"
        )
        fixture_id = current.canonical_entity_id
        incidents.append(
            RecommendationProviderIncidentEventInput(
                provider_incident_key=_provider_incident_key(
                    "odds_probability_shift",
                    current,
                ),
                provider_name=current.provider_name,
                fixture_id=fixture_id,
                incident_type="odds_probability_shift",
                severity=severity,
                event_time_utc=_aware_utc(current.observed_at_utc),
                observed_at_utc=_aware_utc(current.observed_at_utc),
                affects_recommendations=True,
                excluded_fixture_ids=[fixture_id] if severity == "critical" else [],
                summary=f"odds probability shift: {delta:+.3f}",
                payload_json={
                    **_observation_payload(current),
                    "previous_provider_observation_id": _observation_id(previous),
                    "previous_value": previous.value,
                    "current_value": current.value,
                    "probability_delta": delta,
                },
            )
        )
    return incidents


def _dedupe_incidents(
    incidents: Sequence[RecommendationProviderIncidentEventInput],
) -> list[RecommendationProviderIncidentEventInput]:
    deduped: dict[str, RecommendationProviderIncidentEventInput] = {}
    for incident in incidents:
        deduped[incident.provider_incident_key] = incident
    return list(deduped.values())


def _provider_incident_key(prefix: str, observation: ProviderObservation) -> str:
    observation_id = _observation_id(observation)
    if observation_id is not None:
        return f"{prefix}:provider_observation:{observation_id}"
    payload = "|".join(
        [
            prefix,
            observation.provider_name,
            observation.capability,
            observation.canonical_entity_id,
            observation.field_name,
            observation.value,
            _aware_utc(observation.observed_at_utc).isoformat(),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:provider_observation_hash:{digest}"


def _observation_payload(observation: ProviderObservation) -> dict[str, object]:
    return {
        "provider_observation_id": _observation_id(observation),
        "provider_name": observation.provider_name,
        "capability": observation.capability,
        "entity_type": observation.entity_type,
        "canonical_entity_id": observation.canonical_entity_id,
        "provider_entity_id": observation.provider_entity_id,
        "field_name": observation.field_name,
        "value": observation.value,
        "observed_at_utc": _aware_utc(observation.observed_at_utc).isoformat(),
        "confidence": observation.confidence,
        "payload_id": observation.payload_id,
        "metadata_json": dict(observation.metadata_json),
        "source": "provider_observation_mapper",
    }


def _observation_id(observation: ProviderObservation) -> int | None:
    value = getattr(observation, "provider_observation_id", None)
    return value if isinstance(value, int) else None


def _optional_probability(value: str) -> float | None:
    try:
        probability = float(value)
    except ValueError:
        return None
    if probability < 0.0 or probability > 1.0:
        return None
    return probability


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _is_false(value: str) -> bool:
    return value.strip().lower() in {"false", "0", "no", "n"}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
