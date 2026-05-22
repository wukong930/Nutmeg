from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.config import Settings
from nutmeg.providers.fallback_odds_probe import run_sportmonks_fallback_odds_probe
from nutmeg.providers.mapping_repository import (
    ProviderEntityMappingList,
    ProviderEntityMappingRecord,
)
from nutmeg.providers.odds_coverage import OddsCoverageGapItem, OddsCoverageGapReport
from nutmeg.providers.sportmonks import SportMonksAdapter, SportMonksConfig


class FakeGapReader:
    def build_gap_report(self, **kwargs: object) -> OddsCoverageGapReport:
        return OddsCoverageGapReport(
            competition_id=str(kwargs["competition_id"]),
            competition_name="Premier League",
            provider=str(kwargs["provider"]),
            window_start_utc=datetime(2026, 5, 1, tzinfo=UTC),
            as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
            max_snapshot_lag_hours=168,
            fixture_count=2,
            gap_count=2,
            no_odds_count=2,
            stale_odds_count=0,
            provider_event_unavailable_count=2,
            missing_1x2_count=0,
            missing_handicap_count=0,
            unmapped_fixture_count=2,
            mapped_gap_count=0,
            items=[
                _gap("fd_fixture_1"),
                _gap("fd_fixture_2"),
            ],
            generated_at_utc=datetime(2026, 5, 8, tzinfo=UTC),
        )


class FakeMappingReader:
    def __init__(self, mapped_fixture_ids: set[str]) -> None:
        self.mapped_fixture_ids = mapped_fixture_ids

    def list_mappings(
        self,
        *,
        provider: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        limit: int = 100,
    ) -> ProviderEntityMappingList:
        _ = (provider, entity_type, limit)
        if canonical_entity_id not in self.mapped_fixture_ids:
            return ProviderEntityMappingList()
        return ProviderEntityMappingList(
            items=[
                ProviderEntityMappingRecord(
                    mapping_id=42,
                    provider="sportmonks",
                    entity_type="fixture",
                    provider_entity_id=f"sm_{canonical_entity_id}",
                    canonical_entity_id=str(canonical_entity_id),
                    confidence=0.97,
                    created_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
                )
            ]
        )


class FakeSportMonksOddsTransport:
    def get_json(self, path: str, query: dict[str, object]) -> object:
        assert query["api_token"] == "__redacted__"
        provider_fixture_id = path.rsplit("/", 1)[-1]
        return {
            "data": {
                "id": provider_fixture_id,
                "odds": {
                    "data": [
                        {
                            "fixture_id": provider_fixture_id,
                            "bookmaker": {"name": "Fixture Book"},
                            "market": {"name": "1X2"},
                            "label": "Home",
                            "decimal": 2.05,
                        },
                        {
                            "fixture_id": provider_fixture_id,
                            "bookmaker": {"name": "Fixture Book"},
                            "market": {"name": "1X2"},
                            "label": "Draw",
                            "decimal": 3.25,
                        },
                        {
                            "fixture_id": provider_fixture_id,
                            "bookmaker": {"name": "Fixture Book"},
                            "market": {"name": "1X2"},
                            "label": "Away",
                            "decimal": 3.4,
                        },
                    ]
                },
            }
        }


def test_sportmonks_fallback_probe_classifies_mapping_blockers() -> None:
    result = run_sportmonks_fallback_odds_probe(
        Settings(),
        competition_id="EPL",
        gap_reader=FakeGapReader(),
        mapping_reader=FakeMappingReader(mapped_fixture_ids=set()),
        as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
    )

    assert result.checked_gap_count == 2
    assert result.mapped_fallback_count == 0
    assert result.recoverable_fixture_count == 0
    assert result.items[0].status == "mapping_missing"
    assert result.items[0].recommended_action == "bootstrap_sportmonks_fixture_mapping"
    assert "sportmonks_fixture_mapping_required" in result.warnings


def test_sportmonks_fallback_probe_normalizes_live_probe_odds() -> None:
    result = run_sportmonks_fallback_odds_probe(
        Settings(sportmonks_api_key="sportmonks-secret"),
        competition_id="EPL",
        gap_reader=FakeGapReader(),
        mapping_reader=FakeMappingReader(mapped_fixture_ids={"fd_fixture_1"}),
        adapter=SportMonksAdapter(
            SportMonksConfig(api_token="sportmonks-secret"),
            transport=FakeSportMonksOddsTransport(),
        ),
        live_provider_probe=True,
        as_of_time_utc=datetime(2026, 5, 8, tzinfo=UTC),
    )

    assert result.checked_gap_count == 2
    assert result.mapped_fallback_count == 1
    assert result.probed_fixture_count == 1
    assert result.recoverable_fixture_count == 1
    assert result.normalized_odds_count == 3
    assert result.bookmaker_count == 1
    assert result.market_types == ["1x2"]
    assert result.items[0].status == "covered"
    assert result.items[0].provider_fixture_id == "sm_fd_fixture_1"
    assert result.items[1].status == "mapping_missing"
    assert "sportmonks-secret" not in result.model_dump_json()


def _gap(fixture_id: str) -> OddsCoverageGapItem:
    return OddsCoverageGapItem(
        fixture_id=fixture_id,
        competition_id="EPL",
        competition_name="Premier League",
        kickoff_time_utc=datetime(2026, 5, 10, 14, 0, tzinfo=UTC),
        home_team_name="Arsenal",
        away_team_name="Brighton",
        issue_types=["unmapped", "provider_event_unavailable", "no_odds"],
        recommended_action="try_fallback_provider_event_mapping",
        odds_snapshot_count=0,
        bookmaker_count=0,
        has_1x2=False,
        has_handicap=False,
        fresh_enough=False,
        has_provider_mapping=False,
        provider="the-odds-api",
    )
