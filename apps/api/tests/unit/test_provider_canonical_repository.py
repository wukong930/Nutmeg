from __future__ import annotations

from typing import Any

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.canonical_repository import (
    PostgresFootballDataCanonicalRepository,
    canonical_season_id,
    football_data_canonical_id,
)
from nutmeg.providers.football_data_org import normalize_match


class FakeCanonicalDatabase:
    def __init__(self) -> None:
        self.queries: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.queries.append((query, params))
        if "provider_entity_mappings" in query:
            return {"mapping_id": len(self.queries)}
        if "competitions" in query:
            return {"competition_id": params["competition_id"]}
        if "seasons" in query:
            return {"season_id": params["season_id"]}
        if "teams" in query:
            return {"team_id": params["team_id"]}
        if "fixtures" in query:
            return {"fixture_id": params["fixture_id"]}
        if "results" in query:
            return {"fixture_id": params["fixture_id"]}
        raise AssertionError(f"unexpected query: {query}")


def test_football_data_canonical_repository_upserts_mapping_fixture_and_result() -> None:
    database = FakeCanonicalDatabase()
    repository = PostgresFootballDataCanonicalRepository(database)
    fixture = normalize_match(_finished_match())

    summary = repository.upsert_fixtures(
        [fixture],
        canonical_competition_id="EPL",
        season="2025",
        provider_competition_id="PL",
    )

    assert summary.competitions == 1
    assert summary.seasons == 1
    assert summary.teams == 2
    assert summary.fixtures == 1
    assert summary.results == 1
    assert summary.provider_mappings == 6
    assert summary.canonical_fixture_ids == ["fd_fixture_330299"]

    all_params = [params for _, params in database.queries]
    assert any(params.get("competition_id") == "EPL" for params in all_params)
    assert any(
        params.get("season_id") == canonical_season_id("EPL", "2025")
        for params in all_params
    )
    assert any(
        params.get("team_id") == football_data_canonical_id("team", "57")
        for params in all_params
    )
    assert any(params.get("fixture_id") == "fd_fixture_330299" for params in all_params)
    assert any(params.get("result_1x2") == "home_win" for params in all_params)
    assert any(
        params.get("provider_entity_id") == "PL"
        and params.get("canonical_entity_id") == "EPL"
        for params in all_params
    )


def _finished_match() -> dict[str, Any]:
    return {
        "id": 330299,
        "utcDate": "2026-05-06T19:00:00Z",
        "status": "FINISHED",
        "matchday": 34,
        "stage": "REGULAR_SEASON",
        "group": None,
        "venue": "Emirates Stadium",
        "competition": {"id": 2021, "code": "PL", "name": "Premier League"},
        "season": {"id": 2025, "startDate": "2025-08-15", "endDate": "2026-05-24"},
        "homeTeam": {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS"},
        "awayTeam": {"id": 64, "name": "Liverpool FC", "shortName": "Liverpool", "tla": "LIV"},
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
