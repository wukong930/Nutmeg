from __future__ import annotations

from collections.abc import Sequence

MOCK_PROVIDER_DRY_RUN_WARNING = "mock_dry_run_sample_used:no_api_key"
MOCK_PROVIDER_DRY_RUN_TOKEN = "__nutmeg_mock_dry_run__"


def should_use_mock_provider_dry_run(
    *,
    dry_run: bool,
    enabled: bool,
    api_key: str | None,
) -> bool:
    return dry_run and enabled and not api_key


class MockFootballDataDryRunTransport:
    def __init__(self, *, competition_id: str, season: str) -> None:
        self.competition_id = competition_id
        self.season = season

    def get_json(
        self,
        path: str,
        query: dict[str, object],
        require_token: bool,
    ) -> dict[str, object]:
        return football_data_matches_payload(
            competition_id=self.competition_id,
            season=str(query.get("season") or self.season),
        )


class MockTheOddsApiDryRunTransport:
    def __init__(self, *, sport_key: str, provider_event_id: str) -> None:
        self.sport_key = sport_key
        self.provider_event_id = provider_event_id

    def get_json(self, path: str, query: dict[str, object]) -> object:
        if path == f"/sports/{self.sport_key}/odds":
            event_ids = [
                event_id
                for event_id in str(query.get("eventIds") or self.provider_event_id).split(",")
                if event_id
            ]
            return [
                the_odds_api_event_odds_payload(
                    sport_key=self.sport_key,
                    provider_event_id=event_id,
                )
                for event_id in event_ids
            ]
        return the_odds_api_event_odds_payload(
            sport_key=self.sport_key,
            provider_event_id=self.provider_event_id,
        )


class MockSportMonksDryRunTransport:
    def __init__(self, *, provider_fixture_id: str, provider_team_ids: Sequence[str]) -> None:
        self.provider_fixture_id = provider_fixture_id
        self.provider_team_ids = list(provider_team_ids)

    def get_json(self, path: str, query: dict[str, object]) -> object:
        if path.startswith("/football/fixtures/") and query.get("include") == "odds":
            provider_fixture_id = path.rsplit("/", 1)[-1] or self.provider_fixture_id
            return sportmonks_fixture_odds_payload(
                provider_fixture_id=provider_fixture_id,
            )
        if path.endswith("/lineups"):
            return sportmonks_lineups_payload(
                provider_fixture_id=self.provider_fixture_id,
                provider_team_ids=self.provider_team_ids,
            )
        filters = str(query.get("filters") or "")
        provider_team_id = filters.removeprefix("injuryTeam:")
        return sportmonks_injuries_payload(
            provider_fixture_id=self.provider_fixture_id,
            provider_team_id=provider_team_id,
        )


def football_data_matches_payload(*, competition_id: str, season: str) -> dict[str, object]:
    return {
        "filters": {"season": season},
        "resultSet": {
            "count": 1,
            "competitions": competition_id,
            "first": "2026-05-06",
            "last": "2026-05-06",
        },
        "matches": [
            {
                "id": 330299,
                "utcDate": "2026-05-06T19:00:00Z",
                "status": "SCHEDULED",
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
                "season": {"id": season, "startDate": "2025-08-01", "endDate": "2026-05-24"},
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
                "score": {"fullTime": {"home": None, "away": None}},
            }
        ],
    }


def the_odds_api_event_odds_payload(
    *,
    sport_key: str,
    provider_event_id: str,
) -> dict[str, object]:
    return {
        "id": provider_event_id,
        "sport_key": sport_key,
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
                ],
            }
        ],
    }


def sportmonks_lineups_payload(
    *,
    provider_fixture_id: str,
    provider_team_ids: Sequence[str],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for index, provider_team_id in enumerate(provider_team_ids):
        player_suffix = "10" if index == 0 else "20"
        rows.append(
            {
                "fixture_id": provider_fixture_id,
                "team_id": provider_team_id,
                "player_id": f"mock_player_{provider_team_id}_{player_suffix}",
                "player": {"name": f"Mock Player {provider_team_id} {player_suffix}"},
                "type": "confirmed starting" if index == 0 else "expected lineup",
                "position": {"name": "Goalkeeper" if index == 0 else "Forward"},
                "is_starter": index == 0,
                "probability": 68 if index != 0 else None,
                "updated_at": "2026-05-06T08:30:00Z",
            }
        )
    return {"data": rows}


def sportmonks_injuries_payload(
    *,
    provider_fixture_id: str,
    provider_team_id: str,
) -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": provider_fixture_id,
                "team_id": provider_team_id,
                "player_id": f"mock_player_{provider_team_id}_11",
                "player": {"name": f"Mock Player {provider_team_id} 11"},
                "type": {"name": "Injury"},
                "reason": {"name": "Fitness check"},
                "expected_return_date": "2026-05-20",
                "confidence": 70,
                "updated_at": "2026-05-06T08:45:00Z",
            }
        ]
    }


def sportmonks_fixture_odds_payload(*, provider_fixture_id: str) -> dict[str, object]:
    return {
        "data": {
            "id": provider_fixture_id,
            "odds": {
                "data": [
                    {
                        "fixture_id": provider_fixture_id,
                        "bookmaker": {"name": "SportMonks Mock"},
                        "market": {"name": "1X2"},
                        "label": "Home",
                        "decimal": 2.05,
                        "updated_at": "2026-05-06T08:00:00Z",
                    },
                    {
                        "fixture_id": provider_fixture_id,
                        "bookmaker": {"name": "SportMonks Mock"},
                        "market": {"name": "1X2"},
                        "label": "Draw",
                        "decimal": 3.25,
                        "updated_at": "2026-05-06T08:00:00Z",
                    },
                    {
                        "fixture_id": provider_fixture_id,
                        "bookmaker": {"name": "SportMonks Mock"},
                        "market": {"name": "1X2"},
                        "label": "Away",
                        "decimal": 3.4,
                        "updated_at": "2026-05-06T08:00:00Z",
                    },
                    {
                        "fixture_id": provider_fixture_id,
                        "bookmaker": {"name": "SportMonks Mock"},
                        "market": {"name": "Asian Handicap"},
                        "label": "Home",
                        "handicap": -0.5,
                        "decimal": 1.92,
                        "updated_at": "2026-05-06T08:02:00Z",
                    },
                    {
                        "fixture_id": provider_fixture_id,
                        "bookmaker": {"name": "SportMonks Mock"},
                        "market": {"name": "Asian Handicap"},
                        "label": "Away",
                        "handicap": 0.5,
                        "decimal": 1.94,
                        "updated_at": "2026-05-06T08:02:00Z",
                    },
                ]
            },
        }
    }
