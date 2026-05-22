from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.conflicts import (
    LIST_PROVIDER_OBSERVATIONS_QUERY,
    ProviderObservation,
    StoredProviderObservation,
)
from nutmeg.recommendations import (
    RecommendationProviderIncidentMappingOptions,
    map_provider_observations_to_recommendation_incidents,
    run_recommendation_provider_incident_mapping,
)
from nutmeg.recommendations.incidents import (
    INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY,
)


class FakeProviderIncidentMappingDatabase:
    def __init__(self, observation_rows: Sequence[DatabaseRow]) -> None:
        self.observation_rows = list(observation_rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_OBSERVATIONS_QUERY:
            return self.observation_rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY:
            return {
                **params,
                "recommendation_provider_incident_event_id": 901,
                "created_at": _dt(2026, 5, 1, 11),
                "updated_at": _dt(2026, 5, 1, 11),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_maps_critical_availability_observation_to_fixture_exclusion() -> None:
    observations = [
        _observation(
            provider_observation_id=101,
            capability="injuries",
            fixture_id="fix_a",
            field_name="availability:home:player_9:status",
            value="injured",
            metadata_json={
                "player_name": "Forward A",
                "canonical_team_id": "home",
            },
            confidence=0.92,
        )
    ]

    incidents = map_provider_observations_to_recommendation_incidents(
        observations,
        options=_options(),
    )

    assert len(incidents) == 1
    assert incidents[0].provider_incident_key == "availability:provider_observation:101"
    assert incidents[0].incident_type == "player_availability_injured"
    assert incidents[0].severity == "critical"
    assert incidents[0].fixture_id == "fix_a"
    assert incidents[0].excluded_fixture_ids == ["fix_a"]
    assert incidents[0].payload_json["provider_observation_id"] == 101


def test_maps_confirmed_non_starter_without_hard_fixture_exclusion() -> None:
    observations = [
        _observation(
            provider_observation_id=201,
            capability="lineups",
            fixture_id="fix_b",
            field_name="lineup:away:player_7:is_starter",
            value="false",
            metadata_json={
                "lineup_type": "confirmed",
                "player_name": "Winger B",
            },
        )
    ]

    incidents = map_provider_observations_to_recommendation_incidents(
        observations,
        options=_options(),
    )

    assert len(incidents) == 1
    assert incidents[0].provider_incident_key == (
        "confirmed_non_starter:provider_observation:201"
    )
    assert incidents[0].incident_type == "confirmed_non_starter"
    assert incidents[0].severity == "warning"
    assert incidents[0].affects_recommendations is True
    assert incidents[0].excluded_fixture_ids == []


def test_maps_odds_probability_shift_from_recent_observation_pair() -> None:
    observations = [
        _observation(
            provider_observation_id=301,
            capability="odds",
            fixture_id="fix_c",
            field_name="fair_probability:1x2:none:none:home_win",
            value="0.410000",
            observed_at_utc=_dt(2026, 5, 1, 9),
            metadata_json={"bookmaker": "consensus", "decimal_odds": 2.30},
        ),
        _observation(
            provider_observation_id=302,
            capability="odds",
            fixture_id="fix_c",
            field_name="fair_probability:1x2:none:none:home_win",
            value="0.690000",
            observed_at_utc=_dt(2026, 5, 1, 10),
            metadata_json={"bookmaker": "consensus", "decimal_odds": 1.45},
        ),
    ]

    incidents = map_provider_observations_to_recommendation_incidents(
        observations,
        options=_options(),
    )

    assert len(incidents) == 1
    assert incidents[0].provider_incident_key == (
        "odds_probability_shift:provider_observation:302"
    )
    assert incidents[0].incident_type == "odds_probability_shift"
    assert incidents[0].severity == "critical"
    assert incidents[0].excluded_fixture_ids == ["fix_c"]
    assert incidents[0].payload_json["probability_delta"] == 0.28


def test_incident_mapping_runner_reads_observations_and_writes_when_not_dry_run() -> None:
    database = FakeProviderIncidentMappingDatabase(
        [
            _observation_row(
                401,
                capability="injuries",
                fixture_id="fix_a",
                field_name="availability:home:player_9:status",
                value="suspended",
                confidence=1.0,
            )
        ]
    )

    result = run_recommendation_provider_incident_mapping(
        database,
        options=_options(dry_run=False),
    )

    assert result.observation_count == 1
    assert result.mapped_incident_count == 1
    assert result.stored_incident_count == 1
    assert result.stored_events[0].incident_type == "player_availability_suspended"
    assert database.fetch_all_calls[0][0] == LIST_PROVIDER_OBSERVATIONS_QUERY
    assert database.fetch_all_calls[0][1]["entity_type"] == "fixture"
    assert database.fetch_one_calls[0][0] == (
        INSERT_RECOMMENDATION_PROVIDER_INCIDENT_EVENT_QUERY
    )


def _observation(
    *,
    provider_observation_id: int,
    capability: str,
    fixture_id: str,
    field_name: str,
    value: str,
    observed_at_utc: datetime | None = None,
    metadata_json: dict[str, object] | None = None,
    confidence: float = 1.0,
) -> ProviderObservation:
    return StoredProviderObservation(
        provider_observation_id=provider_observation_id,
        provider_name="sportmonks" if capability != "odds" else "the-odds-api",
        capability=capability,
        entity_type="fixture",
        canonical_entity_id=fixture_id,
        provider_entity_id=f"provider-{fixture_id}",
        field_name=field_name,
        value=value,
        observed_at_utc=observed_at_utc or _dt(2026, 5, 1, 10),
        confidence=confidence,
        payload_id=51,
        metadata_json=metadata_json or {},
        created_at_utc=observed_at_utc or _dt(2026, 5, 1, 10),
    )


def _observation_row(
    provider_observation_id: int,
    *,
    capability: str,
    fixture_id: str,
    field_name: str,
    value: str,
    confidence: float,
) -> DatabaseRow:
    return {
        "provider_observation_id": provider_observation_id,
        "provider_name": "sportmonks",
        "capability": capability,
        "entity_type": "fixture",
        "canonical_entity_id": fixture_id,
        "provider_entity_id": f"provider-{fixture_id}",
        "field_name": field_name,
        "observed_value": value,
        "observed_at_utc": _dt(2026, 5, 1, 10),
        "confidence": confidence,
        "payload_id": 51,
        "metadata_json": {"player_name": "Midfielder A"},
        "created_at": _dt(2026, 5, 1, 10),
    }


def _options(*, dry_run: bool = True) -> RecommendationProviderIncidentMappingOptions:
    return RecommendationProviderIncidentMappingOptions(
        as_of_time_utc=_dt(2026, 5, 1, 11),
        lookback_hours=24,
        dry_run=dry_run,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
