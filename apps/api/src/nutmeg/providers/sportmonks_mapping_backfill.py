from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.config import Settings
from nutmeg.providers.fixture_mapping_bootstrap import (
    FixtureMappingBootstrapResult,
    run_sportmonks_fixture_mapping_bootstrap,
)
from nutmeg.providers.sportmonks.discovery import (
    SportMonksCompetitionDiscoveryResult,
    discover_sportmonks_competition_season,
)

SportMonksMappingBackfillStatus = Literal["skipped", "dry_run", "completed"]


class SportMonksFixtureMappingBackfillResult(BaseModel):
    provider_name: str = "sportmonks"
    status: SportMonksMappingBackfillStatus
    dry_run: bool
    target_competition_name: str
    target_country_name: str | None = None
    target_season: str
    source_provider_competition_id: str
    canonical_competition_id: str
    source_season: str
    recommended_competition_id: str | None = None
    recommended_season_id: str | None = None
    matched_count: int = Field(default=0, ge=0)
    persisted_count: int = Field(default=0, ge=0)
    ambiguous_count: int = Field(default=0, ge=0)
    provider_fixture_count: int = Field(default=0, ge=0)
    unmatched_canonical_fixture_count: int = Field(default=0, ge=0)
    discovery: SportMonksCompetitionDiscoveryResult
    bootstrap: FixtureMappingBootstrapResult | None = None
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime


def run_sportmonks_fixture_mapping_backfill(
    settings: Settings,
    *,
    source_provider_competition_id: str = "PL",
    canonical_competition_id: str = "EPL",
    source_season: str = "2025",
    target_competition_name: str = "Premier League",
    target_country_name: str | None = "England",
    target_season: str | None = None,
    max_competition_candidates: int = 5,
    max_season_candidates: int = 6,
    min_competition_score: float = 0.75,
    kickoff_tolerance_minutes: int = 180,
    min_confidence: float = 0.82,
    max_provider_fixtures: int = 500,
    dry_run: bool = True,
) -> SportMonksFixtureMappingBackfillResult:
    effective_target_season = target_season or source_season
    discovery = discover_sportmonks_competition_season(
        settings,
        target_competition_name=target_competition_name,
        target_country_name=target_country_name,
        target_season=effective_target_season,
        max_competition_candidates=max_competition_candidates,
        max_season_candidates=max_season_candidates,
        min_competition_score=min_competition_score,
    )
    warnings = list(discovery.warnings)
    recommended_competition = discovery.recommended_competition
    recommended_season = discovery.recommended_season
    if recommended_competition is None or recommended_season is None:
        warnings.append("sportmonks_backfill_discovery_missing_recommendation")
        return SportMonksFixtureMappingBackfillResult(
            status="skipped",
            dry_run=dry_run,
            target_competition_name=target_competition_name,
            target_country_name=target_country_name,
            target_season=effective_target_season,
            source_provider_competition_id=source_provider_competition_id,
            canonical_competition_id=canonical_competition_id,
            source_season=source_season,
            discovery=discovery,
            warnings=list(dict.fromkeys(warnings)),
            generated_at_utc=datetime.now(UTC),
        )

    bootstrap = run_sportmonks_fixture_mapping_bootstrap(
        settings,
        source_provider_competition_id=source_provider_competition_id,
        canonical_competition_id=canonical_competition_id,
        source_season=source_season,
        sportmonks_competition_id=recommended_competition.provider_competition_id,
        sportmonks_season=recommended_season.provider_season_id,
        dry_run=dry_run,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        min_confidence=min_confidence,
        max_provider_fixtures=max_provider_fixtures,
    )
    warnings.extend(f"bootstrap:{warning}" for warning in bootstrap.warnings)
    if not dry_run and bootstrap.persisted_count == 0:
        warnings.append("sportmonks_backfill_no_mappings_persisted")

    return SportMonksFixtureMappingBackfillResult(
        status="dry_run" if dry_run else "completed",
        dry_run=dry_run,
        target_competition_name=target_competition_name,
        target_country_name=target_country_name,
        target_season=effective_target_season,
        source_provider_competition_id=source_provider_competition_id,
        canonical_competition_id=canonical_competition_id,
        source_season=source_season,
        recommended_competition_id=recommended_competition.provider_competition_id,
        recommended_season_id=recommended_season.provider_season_id,
        matched_count=bootstrap.matched_count,
        persisted_count=bootstrap.persisted_count,
        ambiguous_count=bootstrap.ambiguous_count,
        provider_fixture_count=bootstrap.provider_fixture_count,
        unmatched_canonical_fixture_count=bootstrap.unmatched_canonical_fixture_count,
        discovery=discovery,
        bootstrap=bootstrap,
        warnings=list(dict.fromkeys(warnings)),
        generated_at_utc=datetime.now(UTC),
    )
