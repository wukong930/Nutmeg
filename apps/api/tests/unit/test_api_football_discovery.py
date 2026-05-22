from __future__ import annotations

from nutmeg.config import Settings
from nutmeg.providers.api_football.adapter import ApiFootballPlanLimitError
from nutmeg.providers.api_football.discovery import (
    discover_api_football_competition_season,
)


class FakeApiFootballDiscoveryAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def fetch_leagues(
        self,
        *,
        country: str | None = None,
        season: str | None = None,
        search: str | None = None,
        current: bool | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "country": country,
                "season": season,
                "search": search,
                "current": current,
            }
        )
        return [
            {
                "league": {"id": 39, "name": "Premier League", "type": "League"},
                "country": {"name": "England", "code": "GB"},
                "seasons": [
                    {
                        "year": 2025,
                        "start": "2025-08-15",
                        "end": "2026-05-24",
                        "current": True,
                        "coverage": {"fixtures": {"events": True}},
                    },
                    {
                        "year": 2024,
                        "start": "2024-08-16",
                        "end": "2025-05-25",
                        "current": False,
                    },
                ],
            },
            {
                "league": {"id": 40, "name": "Championship", "type": "League"},
                "country": {"name": "England", "code": "GB"},
                "seasons": [{"year": 2025, "current": True}],
            },
        ]


def test_api_football_discovery_recommends_epl_league_and_season() -> None:
    adapter = FakeApiFootballDiscoveryAdapter()

    result = discover_api_football_competition_season(
        Settings(api_football_api_key="api-football-secret"),
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        adapter=adapter,
    )

    assert adapter.calls == [
        {
            "country": None,
            "season": None,
            "search": "Premier League",
            "current": None,
        }
    ]
    assert result.checked_competition_count == 2
    assert result.recommended_competition is not None
    assert result.recommended_competition.provider_competition_id == "39"
    assert result.recommended_season is not None
    assert result.recommended_season.provider_season_id == "2025"
    assert result.warnings == []


def test_api_football_discovery_refuses_low_confidence_recommendation() -> None:
    class ScotlandOnlyAdapter(FakeApiFootballDiscoveryAdapter):
        def fetch_leagues(
            self,
            *,
            country: str | None = None,
            season: str | None = None,
            search: str | None = None,
            current: bool | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append(
                {
                    "country": country,
                    "season": season,
                    "search": search,
                    "current": current,
                }
            )
            return [
                {
                    "league": {"id": 501, "name": "Premiership", "type": "League"},
                    "country": {"name": "Scotland", "code": "GB"},
                    "seasons": [{"year": 2025, "current": True}],
                }
            ]

    result = discover_api_football_competition_season(
        Settings(api_football_api_key="api-football-secret"),
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        adapter=ScotlandOnlyAdapter(),
    )

    assert result.recommended_competition is None
    assert result.recommended_season is None
    assert "no_api_football_competition_above_confidence_threshold" in result.warnings


def test_api_football_discovery_reports_plan_limited_target_season() -> None:
    class PlanLimitedAdapter(FakeApiFootballDiscoveryAdapter):
        def fetch_leagues(
            self,
            *,
            country: str | None = None,
            season: str | None = None,
            search: str | None = None,
            current: bool | None = None,
        ) -> list[dict[str, object]]:
            self.calls.append(
                {
                    "country": country,
                    "season": season,
                    "search": search,
                    "current": current,
                }
            )
            raise ApiFootballPlanLimitError(
                {"plan": "Free plans do not have access to this season."}
            )

    result = discover_api_football_competition_season(
        Settings(api_football_api_key="api-football-secret"),
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        adapter=PlanLimitedAdapter(),
    )

    assert result.checked_competition_count == 0
    assert result.candidate_count == 0
    assert result.recommended_competition is None
    assert result.recommended_season is None
    assert result.warnings == ["api_football_plan_limited_for_target_season"]
