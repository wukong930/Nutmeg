from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.providers.football_data_org import (
    FootballDataOrgAdapter,
    FootballDataOrgAdapterError,
    FootballDataOrgConfig,
    ProviderCapabilityNotSupported,
    normalize_competition,
    normalize_match,
)


class FakeFootballDataTransport:
    def __init__(self, payloads: dict[str, dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict[str, object], bool]] = []

    def get_json(
        self,
        path: str,
        query: dict[str, object],
        require_token: bool,
    ) -> dict[str, object]:
        self.calls.append((path, query, require_token))
        return self.payloads[path]


def test_football_data_adapter_fetches_competition_matches_with_documented_filters() -> None:
    transport = FakeFootballDataTransport(
        {
            "/competitions/PL/matches": {
                "matches": [_match_payload()],
            }
        }
    )
    adapter = FootballDataOrgAdapter(transport=transport)

    payload = adapter.fetch_competition_matches(
        "PL",
        season="2025",
        date_from="2026-05-01",
        date_to="2026-05-06",
        status="FINISHED",
        matchday=34,
    )

    assert len(payload["matches"]) == 1
    assert transport.calls == [
        (
            "/competitions/PL/matches",
            {
                "season": "2025",
                "dateFrom": "2026-05-01",
                "dateTo": "2026-05-06",
                "status": "FINISHED",
                "matchday": 34,
            },
            True,
        )
    ]


def test_football_data_adapter_requires_token_for_match_requests_without_fake_transport() -> None:
    adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=None,
            api_token_env_var="NUTMEG_TEST_MISSING_FOOTBALL_DATA_TOKEN",
        )
    )

    with pytest.raises(FootballDataOrgAdapterError, match="API token is required"):
        adapter.fetch_fixture_detail("330299")


def test_football_data_adapter_marks_absent_capabilities_as_unsupported() -> None:
    adapter = FootballDataOrgAdapter(transport=FakeFootballDataTransport({}))

    with pytest.raises(ProviderCapabilityNotSupported, match="does not expose odds"):
        adapter.fetch_odds("330299")
    with pytest.raises(ProviderCapabilityNotSupported, match="does not expose lineups"):
        adapter.fetch_lineups("330299")


def test_football_data_normalizes_competition_and_finished_match() -> None:
    competition = normalize_competition(
        {
            "id": 2021,
            "name": "Premier League",
            "code": "PL",
            "type": "LEAGUE",
            "area": {"name": "England"},
        }
    )
    fixture = normalize_match(_match_payload())

    assert competition.provider_entity_id == "2021"
    assert competition.canonical_hint == "PL"
    assert competition.country == "England"
    assert fixture.provider_entity_id == "330299"
    assert fixture.competition_provider_id == "2021"
    assert fixture.competition_code == "PL"
    assert fixture.kickoff_time_utc == datetime(2026, 5, 6, 19, 0, tzinfo=UTC)
    assert fixture.status == "finished"
    assert fixture.home_team.provider_entity_id == "57"
    assert fixture.away_team.canonical_hint == "LIV"
    assert fixture.result is not None
    assert fixture.result.home_goals == 2
    assert fixture.result.away_goals == 1
    assert fixture.result.result_1x2 == "home_win"


def _match_payload() -> dict[str, object]:
    return {
        "id": 330299,
        "utcDate": "2026-05-06T19:00:00Z",
        "status": "FINISHED",
        "matchday": 34,
        "stage": "REGULAR_SEASON",
        "group": None,
        "venue": "Emirates Stadium",
        "competition": {
            "id": 2021,
            "name": "Premier League",
            "code": "PL",
            "type": "LEAGUE",
        },
        "season": {"id": 2025, "startDate": "2025-08-01", "endDate": "2026-05-24"},
        "homeTeam": {
            "id": 57,
            "name": "Arsenal FC",
            "shortName": "Arsenal",
            "tla": "ARS",
        },
        "awayTeam": {
            "id": 64,
            "name": "Liverpool FC",
            "shortName": "Liverpool",
            "tla": "LIV",
        },
        "score": {
            "fullTime": {
                "home": 2,
                "away": 1,
            }
        },
    }
