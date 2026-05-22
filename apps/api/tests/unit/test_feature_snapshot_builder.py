from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.features import (
    PrematchAvailabilityFeature,
    PrematchLineupFeature,
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    PrematchSemanticSignal,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import (
    build_fixture_feature_snapshot,
    build_structured_prematch_feature_snapshot,
)
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.mock import get_mock_fixture
from nutmeg.providers.odds_coverage import FixtureOddsCoverage


def test_feature_snapshot_keeps_mock_baseline_without_provider_coverage() -> None:
    fixture = get_mock_fixture("fix_epl_001")
    assert fixture is not None

    snapshot = build_fixture_feature_snapshot(fixture)

    assert snapshot.fixture_id == "fix_epl_001"
    assert snapshot.feature_version == "features-m1.1.0"
    assert snapshot.data_quality_score == 82.0
    assert snapshot.features_json["mock_baseline"] is True
    assert snapshot.source_snapshot_refs == {"mock_fixture": "fix_epl_001"}


def test_feature_snapshot_combines_odds_lineup_and_injury_freshness() -> None:
    fixture = get_mock_fixture("fix_epl_001")
    assert fixture is not None

    snapshot = build_fixture_feature_snapshot(
        fixture,
        odds_coverage=_odds_coverage(
            market_types=["1x2", "asian_handicap"],
            fresh_enough=True,
        ),
        availability_coverage=_availability_coverage(),
    )

    assert snapshot.data_quality_score == 95.7
    assert snapshot.features_json["data_quality"]["grade"] == "A"
    assert snapshot.features_json["coverage"]["odds"]["score"] == 1.0
    assert snapshot.features_json["coverage"]["lineup"]["fresh_enough"] is True
    assert snapshot.source_snapshot_refs["odds"]["market_types"] == [
        "1x2",
        "asian_handicap",
    ]


def test_feature_snapshot_downgrades_missing_lineup_and_injury() -> None:
    fixture = get_mock_fixture("fix_epl_001")
    assert fixture is not None

    snapshot = build_fixture_feature_snapshot(
        fixture,
        odds_coverage=_odds_coverage(
            market_types=["1x2", "asian_handicap"],
            fresh_enough=True,
        ),
        availability_coverage=_availability_coverage(
            has_lineup=False,
            has_injury=False,
        ),
    )

    assert snapshot.data_quality_score == 69.03
    assert snapshot.features_json["data_quality"]["grade"] == "C"
    assert snapshot.features_json["coverage"]["lineup"]["score"] == 0.0
    assert snapshot.features_json["coverage"]["injury"]["score"] == 0.0


def test_feature_snapshot_applies_provider_conflict_consistency_override() -> None:
    fixture = get_mock_fixture("fix_epl_001")
    assert fixture is not None

    snapshot = build_fixture_feature_snapshot(
        fixture,
        odds_coverage=_odds_coverage(
            market_types=["1x2", "asian_handicap"],
            fresh_enough=True,
        ),
        availability_coverage=_availability_coverage(),
        provider_consistency_override=0.65,
        provider_conflict_context={
            "available": True,
            "conflict_count": 1,
            "data_quality_score_delta": -3.5,
        },
    )

    assert snapshot.data_quality_score == 92.9
    assert snapshot.features_json["data_quality"]["components"]["provider_consistency"] == 0.65
    assert snapshot.features_json["coverage"]["provider_conflicts"]["conflict_count"] == 1
    assert snapshot.source_snapshot_refs["provider_conflicts"]["available"] is True


def test_structured_prematch_feature_snapshot_summarizes_real_prematch_inputs() -> None:
    snapshot = build_structured_prematch_feature_snapshot(
        fixture_id="fix_real_001",
        competition_id="EPL",
        kickoff_time_utc=datetime(2026, 5, 8, 19, 0, tzinfo=UTC),
        feature_time_utc=datetime(2026, 5, 8, 18, 0, tzinfo=UTC),
        historical_stats_completeness=0.82,
        provider_consistency=0.93,
        prematch_features=StructuredPrematchFeatureSet(
            lineup=PrematchLineupFeature(
                lineup_type="expected",
                snapshot_time_utc=datetime(2026, 5, 8, 17, 30, tzinfo=UTC),
                expected_lineup_confidence=0.82,
                starting_xi_strength=0.78,
                bench_dropoff_score=0.20,
                source="sportmonks",
                source_snapshot_ref="lineup_snapshot:44",
            ),
            availability=PrematchAvailabilityFeature(
                snapshot_time_utc=datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                unavailable_key_player_count=1,
                doubtful_key_player_count=1,
                key_player_absence_score=0.35,
                striker_absence_score=0.40,
                source="sportmonks",
                source_snapshot_ref="injury_snapshot:71",
            ),
            odds_movements=[
                PrematchOddsMovementFeature(
                    market_type="1x2",
                    outcome="home_win",
                    bookmaker_disagreement=0.08,
                    market_delay_signal=0.10,
                    points=[
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=2.10,
                            fair_probability=0.48,
                            bookmaker_count=6,
                            source="the_odds_api",
                            source_snapshot_ref="odds_snapshot:101",
                        ),
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 8, 17, 45, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=1.85,
                            fair_probability=0.55,
                            bookmaker_count=7,
                            source="the_odds_api",
                            source_snapshot_ref="odds_snapshot:119",
                        ),
                    ],
                )
            ],
            semantic_signals=[
                PrematchSemanticSignal(
                    signal_name="press_conference_injury_hint",
                    source="club_press_conference",
                    confidence=0.70,
                    evidence_text_short="Coach said the striker is unlikely to start.",
                    extracted_at_utc=datetime(2026, 5, 8, 17, 40, tzinfo=UTC),
                )
            ],
        ),
    )

    prematch_context = snapshot.features_json["prematch_context"]
    assert snapshot.feature_version == "features-v3.1-prematch-structured"
    assert snapshot.data_quality_score == 93.9
    assert snapshot.features_json["data_quality"]["grade"] == "A"
    assert prematch_context["odds_movement"][0]["opening_prob"] == 0.48
    assert prematch_context["odds_movement"][0]["current_prob"] == 0.55
    assert prematch_context["odds_movement"][0]["movement_direction"] == (
        "probability_shortened"
    )
    assert prematch_context["risk_signals"]["market_volatility_score"] == 0.35
    assert prematch_context["risk_signals"]["lineup_schedule_risk"] > 0
    assert snapshot.source_snapshot_refs["prematch"]["odds_movement"][0]["point_count"] == 2
    assert snapshot.source_snapshot_refs["prematch"]["lineup"]["source_snapshot_ref"] == (
        "lineup_snapshot:44"
    )


def test_structured_prematch_feature_snapshot_does_not_turn_missing_lineup_into_risk() -> None:
    snapshot = build_structured_prematch_feature_snapshot(
        fixture_id="fix_market_only_001",
        competition_id="EPL",
        kickoff_time_utc=datetime(2026, 5, 8, 19, 0, tzinfo=UTC),
        feature_time_utc=datetime(2026, 5, 8, 18, 55, tzinfo=UTC),
        historical_stats_completeness=0.75,
        provider_consistency=0.85,
        prematch_features=StructuredPrematchFeatureSet(
            odds_movements=[
                PrematchOddsMovementFeature(
                    market_type="1x2",
                    outcome="home_win",
                    bookmaker_disagreement=0.04,
                    points=[
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=2.10,
                            fair_probability=0.46,
                        ),
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 8, 18, 55, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=1.95,
                            fair_probability=0.50,
                        ),
                    ],
                )
            ],
        ),
    )

    prematch_context = snapshot.features_json["prematch_context"]

    assert snapshot.data_quality_score >= 70
    assert prematch_context["lineup"] is None
    assert prematch_context["availability"] is None
    assert prematch_context["risk_signals"]["lineup_schedule_risk"] == 0.0


def _odds_coverage(
    *,
    market_types: list[str],
    fresh_enough: bool,
) -> FixtureOddsCoverage:
    return FixtureOddsCoverage(
        fixture_id="fix_epl_001",
        competition_id="EPL",
        competition_name="Premier League",
        kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        odds_snapshot_count=len(market_types),
        bookmaker_count=1,
        has_any_odds=bool(market_types),
        has_1x2="1x2" in market_types,
        has_handicap="asian_handicap" in market_types,
        latest_snapshot_time_utc=datetime(2026, 5, 6, 17, 0, tzinfo=UTC),
        latest_snapshot_lag_hours=2.0,
        fresh_enough=fresh_enough,
        market_types=market_types,
    )


def _availability_coverage(
    *,
    has_lineup: bool = True,
    has_injury: bool = True,
) -> FixtureAvailabilityCoverage:
    return FixtureAvailabilityCoverage(
        fixture_id="fix_epl_001",
        competition_id="EPL",
        competition_name="Premier League",
        kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        availability_snapshot_count=1 if has_injury else 0,
        lineup_snapshot_count=1 if has_lineup else 0,
        latest_availability_snapshot_time_utc=(
            datetime(2026, 5, 6, 17, 0, tzinfo=UTC) if has_injury else None
        ),
        availability_snapshot_lag_hours=2.0 if has_injury else None,
        latest_lineup_snapshot_time_utc=(
            datetime(2026, 5, 6, 17, 0, tzinfo=UTC) if has_lineup else None
        ),
        lineup_snapshot_lag_hours=2.0 if has_lineup else None,
        has_availability=has_injury,
        has_lineup=has_lineup,
        availability_fresh_enough=has_injury,
        lineup_fresh_enough=has_lineup,
        fresh_enough=has_injury and has_lineup,
    )
