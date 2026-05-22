from __future__ import annotations

from pytest import approx, raises

from nutmeg.providers.the_odds_api import (
    TheOddsApiAdapter,
    TheOddsApiAdapterError,
    TheOddsApiConfig,
    normalize_event_odds,
)


class FakeOddsTransport:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_json(self, path: str, query: dict[str, object]) -> object:
        self.calls.append((path, query))
        return self.payload


def test_the_odds_api_adapter_fetches_event_odds_with_documented_params() -> None:
    transport = FakeOddsTransport(_event_payload())
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=transport,
    )

    payload = adapter.fetch_event_odds(
        sport_key="soccer_epl",
        event_id="event_123",
        regions="eu",
        markets="h2h,spreads",
        bookmakers="pinnacle",
    )

    assert payload["id"] == "event_123"
    assert transport.calls == [
        (
            "/sports/soccer_epl/events/event_123/odds",
            {
                "regions": "eu",
                "markets": "h2h,spreads",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
                "bookmakers": "pinnacle",
                "apiKey": "__redacted__",
            },
        )
    ]


def test_the_odds_api_adapter_fetches_sport_events_for_mapping_bootstrap() -> None:
    transport = FakeOddsTransport(
        [
            {
                "id": "event_123",
                "sport_key": "soccer_epl",
                "home_team": "Arsenal",
                "away_team": "Liverpool",
                "commence_time": "2026-05-06T19:00:00Z",
            }
        ]
    )
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=transport,
    )

    payload = adapter.fetch_sport_events(
        sport_key="soccer_epl",
        commence_time_from="2026-05-01T00:00:00Z",
        commence_time_to="2026-05-31T23:59:59Z",
    )

    assert payload[0]["id"] == "event_123"
    assert transport.calls == [
        (
            "/sports/soccer_epl/events",
            {
                "dateFormat": "iso",
                "commenceTimeFrom": "2026-05-01T00:00:00Z",
                "commenceTimeTo": "2026-05-31T23:59:59Z",
                "apiKey": "__redacted__",
            },
        )
    ]


def test_the_odds_api_adapter_requires_api_key_without_fake_key() -> None:
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key=None, api_key_env_var="NUTMEG_TEST_MISSING_ODDS_TOKEN")
    )

    with raises(TheOddsApiAdapterError, match="API key is required"):
        adapter.fetch_event_odds(
            sport_key="soccer_epl",
            event_id="event_123",
            regions="eu",
        )


def test_the_odds_api_normalizes_h2h_spreads_and_totals() -> None:
    snapshots = normalize_event_odds(_event_payload())

    assert len(snapshots) == 7
    h2h = [snapshot for snapshot in snapshots if snapshot.market_type == "1x2"]
    spreads = [snapshot for snapshot in snapshots if snapshot.market_type == "asian_handicap"]
    totals = [snapshot for snapshot in snapshots if snapshot.market_type == "totals"]

    assert {snapshot.outcome for snapshot in h2h} == {"home_win", "draw", "away_win"}
    assert {snapshot.side for snapshot in spreads} == {"home", "away"}
    assert {snapshot.outcome for snapshot in totals} == {"over", "under"}
    assert h2h[0].snapshot_time_utc.isoformat() == "2026-05-06T08:00:00+00:00"
    assert sum(snapshot.fair_probability or 0 for snapshot in h2h) == approx(1.0)
    assert sum(snapshot.fair_probability or 0 for snapshot in spreads) == approx(1.0)
    assert all(
        snapshot.raw_implied_probability == approx(1 / snapshot.decimal_odds)
        for snapshot in snapshots
    )
    assert all(snapshot.overround is not None for snapshot in snapshots)


def _event_payload() -> dict[str, object]:
    return {
        "id": "event_123",
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-05-06T19:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2026-05-06T07:58:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-05-06T08:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Liverpool", "price": 3.4},
                        ],
                    },
                    {
                        "key": "spreads",
                        "last_update": "2026-05-06T08:01:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.91, "point": -0.5},
                            {"name": "Liverpool", "price": 1.93, "point": 0.5},
                        ],
                    },
                    {
                        "key": "totals",
                        "last_update": "2026-05-06T08:02:00Z",
                        "outcomes": [
                            {"name": "Over", "price": 1.88, "point": 2.5},
                            {"name": "Under", "price": 2.0, "point": 2.5},
                        ],
                    },
                ],
            }
        ],
    }
