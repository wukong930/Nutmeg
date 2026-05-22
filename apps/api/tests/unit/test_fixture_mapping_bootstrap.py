from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.providers.fixture_mapping_bootstrap import (
    CanonicalFixtureMappingCandidate,
    FixtureMappingBootstrapResult,
    ProviderFixtureMappingCandidate,
    build_fixture_mapping_matches,
    run_api_football_fixture_mapping_bootstrap,
    run_sportmonks_fixture_mapping_bootstrap,
    run_the_odds_api_fixture_mapping_bootstrap,
)
from nutmeg.providers.football_data_org.normalizer import (
    NormalizedFixture,
    NormalizedTeam,
)
from nutmeg.providers.mapping_repository import ProviderEntityMappingUpsert
from nutmeg.providers.sync import FootballDataFixtureFetchResult


class FakeMappingWriter:
    def __init__(self) -> None:
        self.mappings: list[ProviderEntityMappingUpsert] = []

    def upsert_mappings(
        self,
        mappings: Sequence[ProviderEntityMappingUpsert],
    ) -> list[int]:
        self.mappings.extend(mappings)
        return [900 + index for index, _mapping in enumerate(mappings, start=1)]


def test_fixture_mapping_bootstrap_matches_epl_team_aliases_and_kickoff() -> None:
    matches = build_fixture_mapping_matches(
        canonical_fixtures=[
            CanonicalFixtureMappingCandidate(
                canonical_fixture_id="fd_fixture_1",
                provider_fixture_id="1",
                home_team_name="Wolverhampton Wanderers FC",
                away_team_name="Tottenham Hotspur FC",
                kickoff_time_utc=datetime(2026, 5, 9, 14, tzinfo=UTC),
                status="scheduled",
            )
        ],
        provider_fixtures=[
            ProviderFixtureMappingCandidate(
                provider_name="the-odds-api",
                provider_fixture_id="event-1",
                home_team_name="Wolves",
                away_team_name="Spurs",
                kickoff_time_utc=datetime(2026, 5, 9, 14, tzinfo=UTC),
            )
        ],
    )

    assert len(matches) == 1
    assert matches[0].canonical_fixture_id == "fd_fixture_1"
    assert matches[0].confidence == 1.0
    assert matches[0].ambiguous is False


def test_fixture_mapping_bootstrap_rejects_low_confidence_candidate() -> None:
    matches = build_fixture_mapping_matches(
        canonical_fixtures=[
            CanonicalFixtureMappingCandidate(
                canonical_fixture_id="fd_fixture_1",
                provider_fixture_id="1",
                home_team_name="Liverpool FC",
                away_team_name="Chelsea FC",
                kickoff_time_utc=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
                status="scheduled",
            )
        ],
        provider_fixtures=[
            ProviderFixtureMappingCandidate(
                provider_name="the-odds-api",
                provider_fixture_id="event-1",
                home_team_name="Arsenal",
                away_team_name="Everton",
                kickoff_time_utc=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
            )
        ],
        min_confidence=0.82,
    )

    assert matches == []


def test_the_odds_api_fixture_mapping_bootstrap_persists_unambiguous_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = FakeMappingWriter()
    event_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.fetch_normalized_football_data_fixtures",
        lambda *, adapter, competition_id, season: FootballDataFixtureFetchResult(
            endpoint="/competitions/PL/matches",
            request_params={"season": season},
            fixtures=[
                _fixture(
                    provider_entity_id="330299",
                    home_name="Liverpool FC",
                    away_name="Chelsea FC",
                    kickoff=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.TheOddsApiAdapter.fetch_sport_events",
        lambda self, **kwargs: _record_event_fetch(event_calls, kwargs),
    )

    result = run_the_odds_api_fixture_mapping_bootstrap(
        Settings(
            football_data_api_key="football-secret",
            the_odds_api_key="odds-secret",
        ),
        provider_competition_id="PL",
        canonical_competition_id="EPL",
        season="2025",
        sport_key="soccer_epl",
        regions="eu",
        markets="h2h",
        bookmakers=None,
        dry_run=False,
        mapping_writer=writer,
    )

    assert isinstance(result, FixtureMappingBootstrapResult)
    assert result.matched_count == 1
    assert result.persisted_count == 1
    assert result.provider_fixture_source == "events"
    assert result.unmatched_canonical_fixture_count == 0
    assert event_calls == [
        {
            "sport_key": "soccer_epl",
            "date_format": "iso",
            "commence_time_from": "2026-05-09T08:30:00Z",
            "commence_time_to": "2026-05-09T14:30:00Z",
        }
    ]
    assert result.matches[0].persisted_mapping_id == 901
    assert writer.mappings == [
        ProviderEntityMappingUpsert(
            provider="the-odds-api",
            entity_type="fixture",
            provider_entity_id="event-1",
            canonical_entity_id="fd_fixture_330299",
            confidence=1.0,
        )
    ]


def test_sportmonks_fixture_mapping_bootstrap_persists_unambiguous_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = FakeMappingWriter()
    fixture_calls: list[dict[str, str]] = []

    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.fetch_normalized_football_data_fixtures",
        lambda *, adapter, competition_id, season: FootballDataFixtureFetchResult(
            endpoint="/competitions/PL/matches",
            request_params={"season": season},
            fixtures=[
                _fixture(
                    provider_entity_id="330299",
                    home_name="Liverpool FC",
                    away_name="Chelsea FC",
                    kickoff=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.SportMonksAdapter.fetch_fixtures",
        lambda self, competition_id, season: _record_sportmonks_fixture_fetch(
            fixture_calls,
            competition_id,
            season,
        ),
    )

    result = run_sportmonks_fixture_mapping_bootstrap(
        Settings(
            football_data_api_key="football-secret",
            sportmonks_api_key="sportmonks-secret",
        ),
        source_provider_competition_id="PL",
        canonical_competition_id="EPL",
        source_season="2025",
        sportmonks_competition_id="8",
        sportmonks_season="23690",
        dry_run=False,
        mapping_writer=writer,
    )

    assert isinstance(result, FixtureMappingBootstrapResult)
    assert fixture_calls == [{"competition_id": "8", "season": "23690"}]
    assert result.provider_name == "sportmonks"
    assert result.provider_sport_key == "sportmonks:8:23690"
    assert result.provider_fixture_source == "fixtures"
    assert result.matched_count == 1
    assert result.persisted_count == 1
    assert result.unmatched_canonical_fixture_count == 0
    assert result.matches[0].persisted_mapping_id == 901
    assert writer.mappings == [
        ProviderEntityMappingUpsert(
            provider="sportmonks",
            entity_type="fixture",
            provider_entity_id="sm-fixture-1",
            canonical_entity_id="fd_fixture_330299",
            confidence=1.0,
        )
    ]


def test_api_football_fixture_mapping_bootstrap_persists_unambiguous_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = FakeMappingWriter()
    fixture_calls: list[dict[str, str]] = []

    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.fetch_normalized_football_data_fixtures",
        lambda *, adapter, competition_id, season: FootballDataFixtureFetchResult(
            endpoint="/competitions/PL/matches",
            request_params={"season": season},
            fixtures=[
                _fixture(
                    provider_entity_id="330299",
                    home_name="Liverpool FC",
                    away_name="Chelsea FC",
                    kickoff=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "nutmeg.providers.fixture_mapping_bootstrap.ApiFootballAdapter.fetch_fixtures",
        lambda self, *, league_id, season: _record_api_football_fixture_fetch(
            fixture_calls,
            league_id,
            season,
        ),
    )

    result = run_api_football_fixture_mapping_bootstrap(
        Settings(
            football_data_api_key="football-secret",
            api_football_api_key="api-football-secret",
        ),
        source_provider_competition_id="PL",
        canonical_competition_id="EPL",
        source_season="2025",
        api_football_league_id="39",
        api_football_season="2025",
        dry_run=False,
        mapping_writer=writer,
    )

    assert isinstance(result, FixtureMappingBootstrapResult)
    assert fixture_calls == [{"league_id": "39", "season": "2025"}]
    assert result.provider_name == "api-football"
    assert result.provider_sport_key == "api-football:39:2025"
    assert result.provider_fixture_source == "fixtures"
    assert result.matched_count == 1
    assert result.persisted_count == 1
    assert result.unmatched_canonical_fixture_count == 0
    assert result.matches[0].persisted_mapping_id == 901
    assert writer.mappings == [
        ProviderEntityMappingUpsert(
            provider="api-football",
            entity_type="fixture",
            provider_entity_id="api-fixture-1",
            canonical_entity_id="fd_fixture_330299",
            confidence=1.0,
        )
    ]


def _record_event_fetch(
    calls: list[dict[str, object]],
    kwargs: dict[str, object],
) -> list[dict[str, object]]:
    calls.append(kwargs)
    return [
        {
            "id": "event-1",
            "sport_key": "soccer_epl",
            "sport_title": "EPL",
            "home_team": "Liverpool",
            "away_team": "Chelsea",
            "commence_time": "2026-05-09T11:30:00Z",
            "bookmakers": [],
        }
    ]


def _record_sportmonks_fixture_fetch(
    calls: list[dict[str, str]],
    competition_id: str,
    season: str,
) -> list[dict[str, object]]:
    calls.append({"competition_id": competition_id, "season": season})
    return [
        {
            "id": "sm-fixture-1",
            "league_id": competition_id,
            "season_id": season,
            "starting_at": "2026-05-09T11:30:00Z",
            "participants": [
                {"name": "Liverpool", "meta": {"location": "home"}},
                {"name": "Chelsea", "meta": {"location": "away"}},
            ],
        }
    ]


def _record_api_football_fixture_fetch(
    calls: list[dict[str, str]],
    league_id: str,
    season: str,
) -> list[dict[str, object]]:
    calls.append({"league_id": league_id, "season": season})
    return [
        {
            "fixture": {
                "id": "api-fixture-1",
                "date": "2026-05-09T11:30:00Z",
            },
            "league": {"id": league_id, "season": int(season)},
            "teams": {
                "home": {"id": 40, "name": "Liverpool"},
                "away": {"id": 49, "name": "Chelsea"},
            },
        }
    ]


def _fixture(
    *,
    provider_entity_id: str,
    home_name: str,
    away_name: str,
    kickoff: datetime,
) -> NormalizedFixture:
    return NormalizedFixture(
        provider_entity_id=provider_entity_id,
        competition_provider_id="PL",
        competition_code="PL",
        competition_name="Premier League",
        kickoff_time_utc=kickoff,
        status="scheduled",
        home_team=NormalizedTeam(
            provider_entity_id="57",
            canonical_hint="LIV",
            name=home_name,
        ),
        away_team=NormalizedTeam(
            provider_entity_id="61",
            canonical_hint="CHE",
            name=away_name,
        ),
        raw_status="SCHEDULED",
    )
