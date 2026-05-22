from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.domain.features import (
    FeatureSnapshot,
    PrematchAvailabilityFeature,
    PrematchLineupFeature,
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    PrematchSemanticSignal,
    StructuredPrematchFeatureSet,
)
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.governance.quality import DataQualityInputs, score_data_quality
from nutmeg.providers.mock import MockFixture
from nutmeg.providers.odds_coverage import FixtureOddsCoverage


def build_fixture_feature_snapshot(
    fixture: MockFixture,
    *,
    feature_time_utc: datetime | None = None,
    feature_version: str = "features-m1.1.0",
    odds_coverage: FixtureOddsCoverage | None = None,
    availability_coverage: FixtureAvailabilityCoverage | None = None,
    provider_consistency_override: float | None = None,
    provider_conflict_context: dict[str, object] | None = None,
) -> FeatureSnapshot:
    normalized_feature_time = _aware_utc(
        feature_time_utc or fixture["prediction_time_utc"]
    )
    if odds_coverage is None and availability_coverage is None:
        return _mock_baseline_feature_snapshot(
            fixture,
            feature_time_utc=normalized_feature_time,
            feature_version=feature_version,
        )

    odds_component = _odds_coverage_component(odds_coverage)
    lineup_component = _snapshot_component(
        available=availability_coverage.has_lineup if availability_coverage else False,
        fresh_enough=(
            availability_coverage.lineup_fresh_enough if availability_coverage else False
        ),
    )
    injury_component = _snapshot_component(
        available=(
            availability_coverage.has_availability if availability_coverage else False
        ),
        fresh_enough=(
            availability_coverage.availability_fresh_enough
            if availability_coverage
            else False
        ),
    )
    odds_freshness = _snapshot_component(
        available=odds_coverage.has_any_odds if odds_coverage else False,
        fresh_enough=odds_coverage.fresh_enough if odds_coverage else False,
    )
    data_quality_inputs = DataQualityInputs(
        fixture_reliability=_fixture_reliability(fixture),
        odds_coverage=odds_component,
        lineup_injury_coverage=round((lineup_component + injury_component) / 2, 4),
        historical_stats_completeness=_historical_stats_completeness(fixture),
        provider_consistency=(
            _bounded_component(provider_consistency_override)
            if provider_consistency_override is not None
            else _provider_consistency(fixture)
        ),
        data_freshness=round(
            (odds_freshness + lineup_component + injury_component) / 3,
            4,
        ),
    )
    data_quality = score_data_quality(data_quality_inputs)
    source_snapshot_refs: dict[str, object] = {
        "odds": _odds_source_refs(odds_coverage),
        "lineup": _lineup_source_refs(availability_coverage),
        "injury": _injury_source_refs(availability_coverage),
        "provider_conflicts": provider_conflict_context or {"available": False},
    }
    return FeatureSnapshot(
        fixture_id=fixture["fixture_id"],
        feature_time_utc=normalized_feature_time,
        feature_version=feature_version,
        features_json={
            "competition_id": fixture["competition_id"],
            "kickoff_time_utc": fixture["kickoff_time_utc"].isoformat(),
            "as_of_time_guard": {
                "feature_time_utc": normalized_feature_time.isoformat(),
                "feature_before_kickoff": normalized_feature_time
                <= fixture["kickoff_time_utc"],
            },
            "data_quality": {
                "score": data_quality.score,
                "grade": data_quality.grade,
                "components": data_quality_inputs.model_dump(mode="json"),
                "messages": data_quality.messages,
            },
            "coverage": {
                "odds": {
                    "score": odds_component,
                    "market_types": odds_coverage.market_types
                    if odds_coverage is not None
                    else [],
                    "has_1x2": odds_coverage.has_1x2
                    if odds_coverage is not None
                    else False,
                    "has_handicap": odds_coverage.has_handicap
                    if odds_coverage is not None
                    else False,
                },
                "lineup": {
                    "score": lineup_component,
                    "available": availability_coverage.has_lineup
                    if availability_coverage is not None
                    else False,
                    "fresh_enough": availability_coverage.lineup_fresh_enough
                    if availability_coverage is not None
                    else False,
                },
                "injury": {
                    "score": injury_component,
                    "available": availability_coverage.has_availability
                    if availability_coverage is not None
                    else False,
                    "fresh_enough": availability_coverage.availability_fresh_enough
                    if availability_coverage is not None
                    else False,
                },
                "provider_conflicts": provider_conflict_context or {"available": False},
            },
        },
        source_snapshot_refs=source_snapshot_refs,
        data_quality_score=data_quality.score,
    )


def build_structured_prematch_feature_snapshot(
    *,
    fixture_id: str,
    competition_id: str,
    kickoff_time_utc: datetime,
    feature_time_utc: datetime,
    prematch_features: StructuredPrematchFeatureSet,
    feature_version: str = "features-v3.1-prematch-structured",
    fixture_reliability: float = 1.0,
    historical_stats_completeness: float = 0.65,
    provider_consistency: float = 0.75,
) -> FeatureSnapshot:
    normalized_feature_time = _aware_utc(feature_time_utc)
    normalized_kickoff_time = _aware_utc(kickoff_time_utc)
    odds_component = _structured_odds_component(prematch_features.odds_movements)
    lineup_component = _structured_lineup_component(prematch_features.lineup)
    availability_component = _structured_availability_component(
        prematch_features.availability
    )
    data_quality_inputs = DataQualityInputs(
        fixture_reliability=_bounded_component(fixture_reliability),
        odds_coverage=odds_component,
        lineup_injury_coverage=round(
            (lineup_component + availability_component) / 2,
            4,
        ),
        historical_stats_completeness=_bounded_component(
            historical_stats_completeness
        ),
        provider_consistency=_bounded_component(provider_consistency),
        data_freshness=_structured_data_freshness(
            prematch_features,
            feature_time_utc=normalized_feature_time,
        ),
    )
    data_quality = score_data_quality(data_quality_inputs)
    odds_movement = [
        _odds_movement_summary(movement)
        for movement in prematch_features.odds_movements
    ]
    risk_signals = _prematch_risk_signals(
        prematch_features,
        odds_movement=odds_movement,
    )
    return FeatureSnapshot(
        fixture_id=fixture_id,
        feature_time_utc=normalized_feature_time,
        feature_version=feature_version,
        features_json={
            "competition_id": competition_id,
            "kickoff_time_utc": normalized_kickoff_time.isoformat(),
            "as_of_time_guard": {
                "feature_time_utc": normalized_feature_time.isoformat(),
                "feature_before_kickoff": normalized_feature_time
                <= normalized_kickoff_time,
            },
            "prematch_context": {
                "lineup": _optional_model_dump(prematch_features.lineup),
                "availability": _optional_model_dump(
                    prematch_features.availability
                ),
                "odds_movement": odds_movement,
                "semantic_signals": [
                    signal.model_dump(mode="json")
                    for signal in prematch_features.semantic_signals
                ],
                "risk_signals": risk_signals,
                "metadata_json": prematch_features.metadata_json,
            },
            "data_quality": {
                "score": data_quality.score,
                "grade": data_quality.grade,
                "components": data_quality_inputs.model_dump(mode="json"),
                "messages": data_quality.messages,
            },
        },
        source_snapshot_refs={
            "prematch": _structured_source_refs(prematch_features),
        },
        data_quality_score=data_quality.score,
    )


def _mock_baseline_feature_snapshot(
    fixture: MockFixture,
    *,
    feature_time_utc: datetime,
    feature_version: str,
) -> FeatureSnapshot:
    score = fixture["data_quality_score"]
    return FeatureSnapshot(
        fixture_id=fixture["fixture_id"],
        feature_time_utc=feature_time_utc,
        feature_version=feature_version,
        features_json={
            "competition_id": fixture["competition_id"],
            "kickoff_time_utc": fixture["kickoff_time_utc"].isoformat(),
            "mock_baseline": True,
            "data_quality": {
                "score": score,
                "grade": _grade(score),
                "components": {},
                "messages": ["mock fixture baseline quality retained"],
            },
        },
        source_snapshot_refs={"mock_fixture": fixture["fixture_id"]},
        data_quality_score=score,
    )


def _odds_coverage_component(odds_coverage: FixtureOddsCoverage | None) -> float:
    if odds_coverage is None or not odds_coverage.has_any_odds:
        return 0.0
    score = 0.5
    if odds_coverage.has_1x2:
        score += 0.25
    if odds_coverage.has_handicap:
        score += 0.25
    if not odds_coverage.fresh_enough:
        score *= 0.5
    return round(score, 4)


def _snapshot_component(*, available: bool, fresh_enough: bool) -> float:
    if fresh_enough:
        return 1.0
    if available:
        return 0.5
    return 0.0


def _bounded_component(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _fixture_reliability(fixture: MockFixture) -> float:
    if fixture["status"] in {"scheduled", "beta"}:
        return 1.0
    if fixture["status"] == "stale":
        return 0.6
    return 0.9


def _historical_stats_completeness(fixture: MockFixture) -> float:
    if fixture["competition_id"] == "EPL":
        return 0.82
    if fixture["competition_id"] == "JPN_J1":
        return 0.58
    return 0.65


def _provider_consistency(fixture: MockFixture) -> float:
    if fixture["competition_id"] == "EPL":
        return 0.93
    if fixture["competition_id"] == "JPN_J1":
        return 0.76
    return 0.75


def _odds_source_refs(odds_coverage: FixtureOddsCoverage | None) -> dict[str, object]:
    if odds_coverage is None:
        return {"available": False}
    return {
        "available": odds_coverage.has_any_odds,
        "fresh_enough": odds_coverage.fresh_enough,
        "snapshot_count": odds_coverage.odds_snapshot_count,
        "latest_snapshot_time_utc": _optional_datetime(
            odds_coverage.latest_snapshot_time_utc
        ),
        "latest_snapshot_lag_hours": odds_coverage.latest_snapshot_lag_hours,
        "market_types": odds_coverage.market_types,
        "bookmaker_count": odds_coverage.bookmaker_count,
    }


def _lineup_source_refs(
    availability_coverage: FixtureAvailabilityCoverage | None,
) -> dict[str, object]:
    if availability_coverage is None:
        return {"available": False}
    return {
        "available": availability_coverage.has_lineup,
        "fresh_enough": availability_coverage.lineup_fresh_enough,
        "snapshot_count": availability_coverage.lineup_snapshot_count,
        "latest_snapshot_time_utc": _optional_datetime(
            availability_coverage.latest_lineup_snapshot_time_utc
        ),
        "latest_snapshot_lag_hours": availability_coverage.lineup_snapshot_lag_hours,
    }


def _injury_source_refs(
    availability_coverage: FixtureAvailabilityCoverage | None,
) -> dict[str, object]:
    if availability_coverage is None:
        return {"available": False}
    return {
        "available": availability_coverage.has_availability,
        "fresh_enough": availability_coverage.availability_fresh_enough,
        "snapshot_count": availability_coverage.availability_snapshot_count,
        "latest_snapshot_time_utc": _optional_datetime(
            availability_coverage.latest_availability_snapshot_time_utc
        ),
        "latest_snapshot_lag_hours": (
            availability_coverage.availability_snapshot_lag_hours
        ),
    }


def _structured_odds_component(
    movements: list[PrematchOddsMovementFeature],
) -> float:
    if not movements:
        return 0.0
    best_score = 0.0
    for movement in movements:
        point_count = len(movement.points)
        if point_count == 0:
            continue
        score = 0.55
        if point_count >= 2:
            score += 0.25
        if any(point.fair_probability is not None for point in movement.points):
            score += 0.10
        if movement.bookmaker_disagreement is not None:
            score += 0.10
        best_score = max(best_score, score)
    return _bounded_component(best_score)


def _structured_lineup_component(lineup: PrematchLineupFeature | None) -> float:
    if lineup is None:
        return 0.0
    if lineup.lineup_type == "confirmed":
        return max(0.90, lineup.expected_lineup_confidence or 0.0)
    if lineup.expected_lineup_confidence is not None:
        return _bounded_component(lineup.expected_lineup_confidence)
    return 0.50


def _structured_availability_component(
    availability: PrematchAvailabilityFeature | None,
) -> float:
    if availability is None:
        return 0.0
    if availability.snapshot_time_utc is None:
        return 0.50
    return 1.0


def _structured_data_freshness(
    prematch_features: StructuredPrematchFeatureSet,
    *,
    feature_time_utc: datetime,
) -> float:
    freshness_values: list[float] = []
    if prematch_features.lineup is not None:
        freshness_values.append(
            _snapshot_freshness(
                prematch_features.lineup.snapshot_time_utc,
                feature_time_utc=feature_time_utc,
            )
        )
    if prematch_features.availability is not None:
        freshness_values.append(
            _snapshot_freshness(
                prematch_features.availability.snapshot_time_utc,
                feature_time_utc=feature_time_utc,
            )
        )
    for movement in prematch_features.odds_movements:
        latest_point = _latest_odds_point(movement.points)
        freshness_values.append(
            _snapshot_freshness(
                latest_point.snapshot_time_utc if latest_point is not None else None,
                feature_time_utc=feature_time_utc,
            )
        )
    for signal in prematch_features.semantic_signals:
        freshness_values.append(
            _snapshot_freshness(
                signal.extracted_at_utc,
                feature_time_utc=feature_time_utc,
            )
        )
    if not freshness_values:
        return 0.0
    return round(sum(freshness_values) / len(freshness_values), 4)


def _snapshot_freshness(
    snapshot_time_utc: datetime | None,
    *,
    feature_time_utc: datetime,
) -> float:
    if snapshot_time_utc is None:
        return 0.0
    lag_hours = max(
        0.0,
        (_aware_utc(feature_time_utc) - _aware_utc(snapshot_time_utc)).total_seconds()
        / 3600,
    )
    if lag_hours <= 6:
        return 1.0
    if lag_hours <= 24:
        return 0.75
    if lag_hours <= 72:
        return 0.40
    return 0.20


def _odds_movement_summary(
    movement: PrematchOddsMovementFeature,
) -> dict[str, object]:
    points = sorted(
        movement.points,
        key=lambda point: (_aware_utc(point.snapshot_time_utc), point.source or ""),
    )
    first = points[0] if points else None
    latest = points[-1] if points else None
    probability_delta = _optional_delta(
        latest.fair_probability if latest is not None else None,
        first.fair_probability if first is not None else None,
    )
    odds_delta = _optional_delta(
        latest.decimal_odds if latest is not None else None,
        first.decimal_odds if first is not None else None,
    )
    probability_values = [
        point.fair_probability
        for point in points
        if point.fair_probability is not None
    ]
    probability_range = (
        max(probability_values) - min(probability_values)
        if probability_values
        else None
    )
    return {
        "market_type": movement.market_type,
        "outcome": movement.outcome,
        "point_count": len(points),
        "opening_prob": first.fair_probability if first is not None else None,
        "current_prob": latest.fair_probability if latest is not None else None,
        "probability_delta": probability_delta,
        "opening_decimal_odds": first.decimal_odds if first is not None else None,
        "current_decimal_odds": latest.decimal_odds if latest is not None else None,
        "decimal_odds_delta": odds_delta,
        "movement_direction": _movement_direction(
            probability_delta=probability_delta,
            odds_delta=odds_delta,
        ),
        "probability_range": probability_range,
        "bookmaker_disagreement": movement.bookmaker_disagreement,
        "exchange_liquidity": movement.exchange_liquidity,
        "market_delay_signal": movement.market_delay_signal,
        "points": [point.model_dump(mode="json") for point in points],
        "metadata_json": movement.metadata_json,
    }


def _latest_odds_point(
    points: list[PrematchOddsMovementPoint],
) -> PrematchOddsMovementPoint | None:
    if not points:
        return None
    return max(points, key=lambda point: _aware_utc(point.snapshot_time_utc))


def _movement_direction(
    *,
    probability_delta: float | None,
    odds_delta: float | None,
) -> str:
    if probability_delta is not None:
        if probability_delta > 0.01:
            return "probability_shortened"
        if probability_delta < -0.01:
            return "probability_drifted"
    if odds_delta is not None:
        if odds_delta < -0.05:
            return "odds_shortened"
        if odds_delta > 0.05:
            return "odds_drifted"
    return "flat"


def _prematch_risk_signals(
    prematch_features: StructuredPrematchFeatureSet,
    *,
    odds_movement: list[dict[str, object]],
) -> dict[str, object]:
    lineup_risk = _lineup_schedule_risk(prematch_features)
    market_volatility = _market_volatility_score(odds_movement)
    semantic_pressure_signals = [
        signal
        for signal in prematch_features.semantic_signals
        if signal.signal_name
        in {
            "relegation_pressure",
            "title_race_pressure",
            "european_qualification_pressure",
            "is_derby",
        }
    ]
    return {
        "lineup_schedule_risk": lineup_risk,
        "market_volatility_score": market_volatility,
        "semantic_pressure_signal_count": len(semantic_pressure_signals),
        "semantic_pressure_max_confidence": max(
            (signal.confidence for signal in semantic_pressure_signals),
            default=0.0,
        ),
    }


def _lineup_schedule_risk(
    prematch_features: StructuredPrematchFeatureSet,
) -> float:
    lineup = prematch_features.lineup
    availability = prematch_features.availability
    semantic_risk = max(
        (
            signal.confidence
            for signal in prematch_features.semantic_signals
            if signal.signal_name
            in {
                "rotation_hint",
                "press_conference_injury_hint",
                "manager_change_recently",
            }
        ),
        default=0.0,
    )
    if lineup is None and availability is None and semantic_risk == 0:
        return 0.0
    lineup_confidence_gap = (
        1.0 - lineup.expected_lineup_confidence
        if lineup is not None and lineup.expected_lineup_confidence is not None
        else 0.0
    )
    absence_score = 0.0
    if availability is not None:
        absence_score = max(
            availability.key_player_absence_score,
            availability.defender_absence_score,
            availability.goalkeeper_absence_score,
            availability.striker_absence_score,
        )
    return _bounded_component(
        0.45 * lineup_confidence_gap + 0.35 * absence_score + 0.20 * semantic_risk
    )


def _market_volatility_score(odds_movement: list[dict[str, object]]) -> float:
    volatility_values = [
        abs(probability_delta)
        for item in odds_movement
        if (probability_delta := _optional_float_value(item.get("probability_delta")))
        is not None
    ]
    if not volatility_values:
        return 0.0
    return _bounded_component(max(volatility_values) / 0.20)


def _optional_float_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _structured_source_refs(
    prematch_features: StructuredPrematchFeatureSet,
) -> dict[str, object]:
    return {
        "lineup": _lineup_structured_source_ref(prematch_features.lineup),
        "availability": _availability_structured_source_ref(
            prematch_features.availability
        ),
        "odds_movement": [
            _odds_movement_source_ref(movement)
            for movement in prematch_features.odds_movements
        ],
        "semantic_signals": [
            {
                "signal_name": signal.signal_name,
                "source": signal.source,
                "extracted_at_utc": signal.extracted_at_utc.isoformat(),
            }
            for signal in prematch_features.semantic_signals
        ],
    }


def _lineup_structured_source_ref(
    lineup: PrematchLineupFeature | None,
) -> dict[str, object]:
    if lineup is None:
        return {"available": False}
    return {
        "available": True,
        "lineup_type": lineup.lineup_type,
        "source": lineup.source,
        "source_snapshot_ref": lineup.source_snapshot_ref,
        "snapshot_time_utc": _optional_datetime(lineup.snapshot_time_utc),
    }


def _availability_structured_source_ref(
    availability: PrematchAvailabilityFeature | None,
) -> dict[str, object]:
    if availability is None:
        return {"available": False}
    return {
        "available": True,
        "source": availability.source,
        "source_snapshot_ref": availability.source_snapshot_ref,
        "snapshot_time_utc": _optional_datetime(availability.snapshot_time_utc),
    }


def _odds_movement_source_ref(
    movement: PrematchOddsMovementFeature,
) -> dict[str, object]:
    return {
        "market_type": movement.market_type,
        "outcome": movement.outcome,
        "point_count": len(movement.points),
        "sources": sorted({point.source for point in movement.points if point.source}),
        "snapshot_refs": [
            point.source_snapshot_ref
            for point in movement.points
            if point.source_snapshot_ref is not None
        ],
    }


def _optional_model_dump(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(
        value,
        (
            PrematchLineupFeature,
            PrematchAvailabilityFeature,
            PrematchSemanticSignal,
        ),
    ):
        return value.model_dump(mode="json")
    raise TypeError(f"unsupported prematch feature model: {type(value)!r}")


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value).isoformat()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"
