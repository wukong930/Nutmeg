from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.providers.sportmonks import (
    SportMonksAdapter,
    SportMonksConfig,
    normalize_injuries,
    normalize_lineups,
    normalize_odds,
)


class FakeSportMonksTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_json(self, path: str, query: dict[str, object]) -> object:
        self.calls.append((path, query))
        if path.endswith("/lineups"):
            return _lineup_payload()
        return _injury_payload()


def test_sportmonks_adapter_redacts_token_for_transport_calls() -> None:
    transport = FakeSportMonksTransport()
    adapter = SportMonksAdapter(
        SportMonksConfig(api_token="test-token"),
        transport=transport,
    )

    rows = adapter.fetch_lineups("fixture_123")

    assert len(rows) == 2
    assert transport.calls[0][0] == "/football/fixtures/fixture_123/lineups"
    assert transport.calls[0][1]["api_token"] == "__redacted__"
    assert "test-token" not in str(transport.calls)


def test_sportmonks_lineup_normalizer_handles_expected_and_confirmed_rows() -> None:
    rows = normalize_lineups(
        _lineup_payload(),
        provider_fixture_id="fixture_123",
        snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
    )

    assert len(rows) == 2
    assert rows[0].provider_fixture_id == "fixture_123"
    assert rows[0].provider_team_id == "team_1"
    assert rows[0].provider_player_id == "player_10"
    assert rows[0].lineup_type == "confirmed"
    assert rows[0].is_starter is True
    assert rows[1].lineup_type == "expected"
    assert rows[1].probability_start == 0.62


def test_sportmonks_injury_normalizer_maps_injury_and_suspension_status() -> None:
    rows = normalize_injuries(
        _injury_payload(),
        provider_team_id="team_1",
        provider_fixture_id="fixture_123",
        snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
    )

    assert [row.status for row in rows] == ["injured", "suspended"]
    assert rows[0].expected_return_date is not None
    assert rows[0].expected_return_date.isoformat() == "2026-05-20"
    assert rows[0].source_confidence == 0.8
    assert rows[1].reason == "Suspension"


def test_sportmonks_odds_normalizer_maps_1x2_and_handicap_rows() -> None:
    rows = normalize_odds(
        _odds_payload(),
        provider_fixture_id="fixture_123",
        snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
    )

    assert len(rows) == 5
    assert {row.provider for row in rows} == {"sportmonks"}
    assert {row.market_type for row in rows} == {"1x2", "asian_handicap"}
    assert {row.outcome for row in rows if row.market_type == "1x2"} == {
        "home_win",
        "draw",
        "away_win",
    }
    handicap_rows = [row for row in rows if row.market_type == "asian_handicap"]
    assert {row.side for row in handicap_rows} == {"home", "away"}
    assert {row.line for row in handicap_rows} == {-0.5, 0.5}
    assert all(row.fair_probability is not None for row in rows)


def _lineup_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_10",
                "player": {"name": "Home Goalkeeper"},
                "type": "confirmed starting",
                "position": {"name": "Goalkeeper"},
                "is_starter": True,
                "updated_at": "2026-05-06T08:30:00Z",
            },
            {
                "fixture_id": "fixture_123",
                "team_id": "team_2",
                "player_id": "player_20",
                "player": {"display_name": "Away Forward"},
                "type": "expected lineup",
                "position": "Forward",
                "probability": 62,
            },
        ]
    }


def _injury_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_11",
                "player": {"name": "Home Defender"},
                "type": {"name": "Injury"},
                "reason": {"name": "Hamstring"},
                "expected_return_date": "2026-05-20",
                "confidence": 80,
                "updated_at": "2026-05-06T08:45:00Z",
            },
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_12",
                "player_name": "Home Midfielder",
                "status": "suspended",
                "reason": "Suspension",
            },
        ]
    }


def _odds_payload() -> dict[str, object]:
    return {
        "data": {
            "id": "fixture_123",
            "odds": {
                "data": [
                    {
                        "fixture_id": "fixture_123",
                        "bookmaker": {"name": "Fixture Book"},
                        "market": {"name": "1X2"},
                        "label": "Home",
                        "decimal": 2.1,
                    },
                    {
                        "fixture_id": "fixture_123",
                        "bookmaker": {"name": "Fixture Book"},
                        "market": {"name": "1X2"},
                        "label": "Draw",
                        "decimal": 3.2,
                    },
                    {
                        "fixture_id": "fixture_123",
                        "bookmaker": {"name": "Fixture Book"},
                        "market": {"name": "1X2"},
                        "label": "Away",
                        "decimal": 3.4,
                    },
                    {
                        "fixture_id": "fixture_123",
                        "bookmaker": {"name": "Fixture Book"},
                        "market": {"name": "Asian Handicap"},
                        "label": "Home",
                        "handicap": -0.5,
                        "decimal": 1.91,
                    },
                    {
                        "fixture_id": "fixture_123",
                        "bookmaker": {"name": "Fixture Book"},
                        "market": {"name": "Asian Handicap"},
                        "label": "Away",
                        "handicap": 0.5,
                        "decimal": 1.93,
                    },
                ]
            },
        }
    }
