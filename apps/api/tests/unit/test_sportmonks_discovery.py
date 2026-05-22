from __future__ import annotations

from nutmeg.config import Settings
from nutmeg.providers.sportmonks.discovery import (
    discover_sportmonks_competition_season,
)


class FakeSportMonksDiscoveryAdapter:
    def __init__(self) -> None:
        self.competition_calls: list[bool] = []
        self.season_calls: list[str] = []

    def fetch_competitions(
        self,
        *,
        include_country: bool = False,
    ) -> list[dict[str, object]]:
        self.competition_calls.append(include_country)
        return [
            {
                "id": 8,
                "name": "Premier League",
                "country": {"name": "England"},
                "active": True,
                "type": "domestic",
            },
            {
                "id": 271,
                "name": "Superliga",
                "country": {"name": "Denmark"},
                "active": True,
                "type": "domestic",
            },
            {
                "id": 1204,
                "name": "Premier League",
                "country": {"name": "Armenia"},
                "active": True,
                "type": "domestic",
            },
        ]

    def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]:
        self.season_calls.append(competition_id)
        if competition_id == "8":
            return [
                {
                    "id": 23690,
                    "name": "2025/2026",
                    "league_id": 8,
                    "is_current": True,
                    "finished": False,
                    "starting_at": "2025-08-15",
                    "ending_at": "2026-05-24",
                },
                {
                    "id": 21646,
                    "name": "2024/2025",
                    "league_id": 8,
                    "is_current": False,
                    "finished": True,
                    "starting_at": "2024-08-16",
                    "ending_at": "2025-05-25",
                },
            ]
        return [
            {
                "id": f"{competition_id}-season",
                "name": "2025/2026",
                "league_id": competition_id,
                "is_current": True,
                "finished": False,
                "starting_at": "2025-07-01",
            }
        ]


def test_sportmonks_discovery_recommends_epl_league_and_season() -> None:
    adapter = FakeSportMonksDiscoveryAdapter()

    result = discover_sportmonks_competition_season(
        Settings(sportmonks_api_key="sportmonks-secret"),
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        adapter=adapter,
    )

    assert adapter.competition_calls == [True]
    assert adapter.season_calls[0] == "8"
    assert result.checked_competition_count == 3
    assert result.recommended_competition is not None
    assert result.recommended_competition.provider_competition_id == "8"
    assert result.recommended_competition.country_name == "England"
    assert result.recommended_season is not None
    assert result.recommended_season.provider_season_id == "23690"
    assert result.recommended_season.name == "2025/2026"
    assert result.warnings == []


def test_sportmonks_discovery_keeps_candidates_without_seasons() -> None:
    class NoSeasonAdapter(FakeSportMonksDiscoveryAdapter):
        def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]:
            self.season_calls.append(competition_id)
            return []

    adapter = NoSeasonAdapter()

    result = discover_sportmonks_competition_season(
        Settings(sportmonks_api_key="sportmonks-secret"),
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        adapter=adapter,
        max_competition_candidates=1,
    )

    assert result.recommended_competition is not None
    assert result.recommended_competition.provider_competition_id == "8"
    assert result.recommended_season is None
    assert "no_sportmonks_season_candidate_for_recommendation" in result.warnings
