from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.providers.fixture_mapping_bootstrap import (
    FixtureMappingBootstrapResult,
    FixtureMappingMatchCandidate,
)
from nutmeg.providers.sportmonks.discovery import (
    SportMonksCompetitionDiscoveryCandidate,
    SportMonksCompetitionDiscoveryResult,
    SportMonksSeasonDiscoveryCandidate,
)
from nutmeg.providers.sportmonks_mapping_backfill import (
    run_sportmonks_fixture_mapping_backfill,
)


def test_sportmonks_mapping_backfill_discovers_ids_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "nutmeg.providers.sportmonks_mapping_backfill."
        "discover_sportmonks_competition_season",
        lambda settings, **kwargs: _discovery(),
    )

    def fake_bootstrap(settings: Settings, **kwargs: object) -> FixtureMappingBootstrapResult:
        calls.append(kwargs)
        return _bootstrap(kwargs)

    monkeypatch.setattr(
        "nutmeg.providers.sportmonks_mapping_backfill."
        "run_sportmonks_fixture_mapping_bootstrap",
        fake_bootstrap,
    )

    result = run_sportmonks_fixture_mapping_backfill(
        Settings(sportmonks_api_key="sportmonks-secret"),
        source_provider_competition_id="PL",
        canonical_competition_id="EPL",
        source_season="2025",
        dry_run=False,
    )

    assert result.status == "completed"
    assert result.recommended_competition_id == "8"
    assert result.recommended_season_id == "23690"
    assert result.matched_count == 1
    assert result.persisted_count == 1
    assert calls == [
        {
            "source_provider_competition_id": "PL",
            "canonical_competition_id": "EPL",
            "source_season": "2025",
            "sportmonks_competition_id": "8",
            "sportmonks_season": "23690",
            "dry_run": False,
            "kickoff_tolerance_minutes": 180,
            "min_confidence": 0.82,
            "max_provider_fixtures": 500,
        }
    ]


def test_sportmonks_mapping_backfill_skips_without_discovery_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nutmeg.providers.sportmonks_mapping_backfill."
        "discover_sportmonks_competition_season",
        lambda settings, **kwargs: SportMonksCompetitionDiscoveryResult(
            target_competition_name="Premier League",
            target_country_name="England",
            target_season="2025",
            min_competition_score=0.75,
            checked_competition_count=0,
            candidate_count=0,
            warnings=["no_sportmonks_competition_candidates"],
            generated_at_utc=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
    )

    result = run_sportmonks_fixture_mapping_backfill(Settings(), dry_run=True)

    assert result.status == "skipped"
    assert result.bootstrap is None
    assert "sportmonks_backfill_discovery_missing_recommendation" in result.warnings


def _discovery() -> SportMonksCompetitionDiscoveryResult:
    season = SportMonksSeasonDiscoveryCandidate(
        provider_season_id="23690",
        name="2025/2026",
        score=1.0,
    )
    competition = SportMonksCompetitionDiscoveryCandidate(
        provider_competition_id="8",
        name="Premier League",
        country_name="England",
        active=True,
        score=0.99,
        seasons=[season],
        recommended_season=season,
    )
    return SportMonksCompetitionDiscoveryResult(
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        min_competition_score=0.75,
        checked_competition_count=1,
        candidate_count=1,
        recommended_competition=competition,
        recommended_season=season,
        candidates=[competition],
        generated_at_utc=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
    )


def _bootstrap(kwargs: dict[str, object]) -> FixtureMappingBootstrapResult:
    return FixtureMappingBootstrapResult(
        provider_name="sportmonks",
        dry_run=bool(kwargs["dry_run"]),
        source_provider="football-data.org",
        source_competition_id=str(kwargs["source_provider_competition_id"]),
        canonical_competition_id=str(kwargs["canonical_competition_id"]),
        source_season=str(kwargs["source_season"]),
        provider_sport_key=(
            f"sportmonks:{kwargs['sportmonks_competition_id']}:"
            f"{kwargs['sportmonks_season']}"
        ),
        source_fixture_count=1,
        provider_fixture_count=1,
        provider_fixture_source="fixtures",
        matched_count=1,
        persisted_count=0 if kwargs["dry_run"] else 1,
        ambiguous_count=0,
        unmatched_provider_fixture_count=0,
        unmatched_canonical_fixture_count=0,
        min_confidence=float(kwargs["min_confidence"]),
        kickoff_tolerance_minutes=int(kwargs["kickoff_tolerance_minutes"]),
        matches=[
            FixtureMappingMatchCandidate(
                provider_name="sportmonks",
                provider_fixture_id="sm-fixture-1",
                canonical_fixture_id="fd_fixture_330299",
                confidence=1.0,
                home_team_score=1.0,
                away_team_score=1.0,
                time_delta_minutes=0.0,
            )
        ],
        generated_at_utc=datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
    )
