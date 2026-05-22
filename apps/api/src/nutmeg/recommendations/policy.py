from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from re import search

from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationPolicyConfig,
    RecommendationSelection,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.upset_policy import (
    RecommendationUpsetSignal,
    analyze_candidate_upset_signal,
)
from nutmeg.recommendations.upset_signal_calibration import (
    assess_upset_signal_calibration,
)


def clamp_unit_interval(value: float) -> float:
    return max(0.0, min(1.0, value))


def candidate_calibration_risk(
    candidate: RecommendationCandidate,
    upset_signal: RecommendationUpsetSignal | None = None,
) -> float:
    signal = upset_signal or analyze_candidate_upset_signal(candidate)
    calibration_gap = 1.0 - candidate.calibration_score
    confidence_gap = 1.0 - candidate.model_confidence_score
    data_quality_gap = 1.0 - candidate.data_quality_score / 100.0
    instability = max(candidate.volatility_penalty, 1.0 - candidate.odds_stability_score)
    upset_pressure = max(
        signal.protection_score,
        signal.favorite_fragility_score,
        signal.avoidance_penalty,
    )
    probability_uncertainty = 1.0 - candidate.effective_probability()
    raw_risk = (
        0.42 * calibration_gap
        + 0.20 * confidence_gap
        + 0.16 * data_quality_gap
        + 0.14 * instability
        + 0.08 * upset_pressure
    )
    return clamp_unit_interval(raw_risk * (0.35 + 0.65 * probability_uncertainty))


def candidate_longshot_upset_risk(
    candidate: RecommendationCandidate,
    upset_signal: RecommendationUpsetSignal | None = None,
    *,
    calibrated_exposure: float = 0.0,
) -> float:
    if candidate.decimal_odds is None:
        return 0.0
    signal = upset_signal or analyze_candidate_upset_signal(candidate)
    long_odds_pressure = clamp_unit_interval((candidate.decimal_odds - 3.0) / 4.5)
    low_probability_pressure = clamp_unit_interval(
        (0.22 - candidate.effective_probability()) / 0.14
    )
    if long_odds_pressure <= 0 and low_probability_pressure <= 0:
        return 0.0
    upset_pressure = max(signal.protection_score, candidate.upset_protection_score)
    instability = max(candidate.volatility_penalty, 1.0 - candidate.odds_stability_score)
    calibration_pressure = 1.0 - candidate.calibration_score
    price_probability_pressure = (
        0.55 * long_odds_pressure + 0.45 * low_probability_pressure
    )
    reliability_pressure = (
        0.45 + 0.35 * calibration_pressure + 0.20 * instability
    )
    raw_risk = clamp_unit_interval(
        price_probability_pressure
        * (0.40 + 0.60 * upset_pressure)
        * reliability_pressure
    )
    exposure_discount = 1.0 - 0.70 * clamp_unit_interval(calibrated_exposure)
    return clamp_unit_interval(raw_risk * exposure_discount)


def candidate_calibrated_upset_exposure(
    candidate: RecommendationCandidate,
    upset_signal: RecommendationUpsetSignal | None = None,
    *,
    config: RecommendationPolicyConfig | None = None,
) -> float:
    if candidate.decimal_odds is None:
        return 0.0
    resolved_config = config or RecommendationPolicyConfig()
    signal = upset_signal or analyze_candidate_upset_signal(candidate)
    protection_score = max(signal.protection_score, candidate.upset_protection_score)
    if candidate.decimal_odds < 2.80 or protection_score < 0.35:
        return 0.0
    effective_probability = candidate.effective_probability()
    if effective_probability < resolved_config.upset_exposure_min_probability:
        return 0.0
    if candidate.calibration_score < resolved_config.upset_exposure_min_calibration_score:
        return 0.0
    if candidate.data_quality_score < resolved_config.upset_exposure_min_data_quality_score:
        return 0.0
    if (
        candidate.model_confidence_score
        < resolved_config.upset_exposure_min_model_confidence_score
    ):
        return 0.0
    if (
        candidate.odds_stability_score
        < resolved_config.upset_exposure_min_odds_stability_score
    ):
        return 0.0
    if (
        candidate.volatility_penalty
        > resolved_config.upset_exposure_max_volatility_penalty
    ):
        return 0.0

    probability_quality = clamp_unit_interval(
        (effective_probability - resolved_config.upset_exposure_min_probability) / 0.18
    )
    calibration_quality = clamp_unit_interval(
        (
            candidate.calibration_score
            - resolved_config.upset_exposure_min_calibration_score
        )
        / max(1.0 - resolved_config.upset_exposure_min_calibration_score, 0.01)
    )
    data_quality = clamp_unit_interval(
        (
            candidate.data_quality_score
            - resolved_config.upset_exposure_min_data_quality_score
        )
        / max(100.0 - resolved_config.upset_exposure_min_data_quality_score, 1.0)
    )
    confidence_quality = clamp_unit_interval(
        (
            candidate.model_confidence_score
            - resolved_config.upset_exposure_min_model_confidence_score
        )
        / max(1.0 - resolved_config.upset_exposure_min_model_confidence_score, 0.01)
    )
    stability_quality = clamp_unit_interval(
        (
            candidate.odds_stability_score
            - resolved_config.upset_exposure_min_odds_stability_score
        )
        / max(1.0 - resolved_config.upset_exposure_min_odds_stability_score, 0.01)
    )
    volatility_quality = clamp_unit_interval(
        (
            resolved_config.upset_exposure_max_volatility_penalty
            - candidate.volatility_penalty
        )
        / max(resolved_config.upset_exposure_max_volatility_penalty, 0.01)
    )
    odds_quality = clamp_unit_interval((candidate.decimal_odds - 2.80) / 2.20)
    return clamp_unit_interval(
        0.18 * protection_score
        + 0.17 * probability_quality
        + 0.17 * calibration_quality
        + 0.14 * data_quality
        + 0.13 * confidence_quality
        + 0.11 * stability_quality
        + 0.06 * volatility_quality
        + 0.04 * odds_quality
    )


def score_candidate(
    candidate: RecommendationCandidate,
    *,
    config: RecommendationPolicyConfig | None = None,
) -> ScoredRecommendationCandidate:
    resolved_config = config or RecommendationPolicyConfig()
    edge = candidate.effective_model_edge()
    upset_signal = analyze_candidate_upset_signal(candidate)
    calibration_risk = candidate_calibration_risk(candidate, upset_signal)
    calibrated_upset_exposure = candidate_calibrated_upset_exposure(
        candidate,
        upset_signal,
        config=resolved_config,
    )
    upset_signal_calibration = assess_upset_signal_calibration(
        candidate,
        upset_signal=upset_signal,
    )
    longshot_upset_risk = candidate_longshot_upset_risk(
        candidate,
        upset_signal,
        calibrated_exposure=calibrated_upset_exposure,
    )
    candidate_score_penalty = _metadata_unit_score(
        candidate,
        "internal_candidate_score_penalty",
    )
    effective_probability = candidate.effective_probability()
    component_scores = {
        "probability": effective_probability,
        "model_probability": candidate.raw_model_probability(),
        "calibrated_probability": (
            candidate.calibrated_probability
            if candidate.calibrated_probability is not None
            else effective_probability
        ),
        "model_edge": clamp_unit_interval(0.50 + edge * 2.0),
        "data_quality": candidate.data_quality_score / 100.0,
        "model_confidence": candidate.model_confidence_score,
        "calibration": candidate.calibration_score,
        "upset_protection": candidate.upset_protection_score,
        "upset_protection_quality": upset_signal.protection_score,
        "favorite_fragility": upset_signal.favorite_fragility_score,
        "upset_avoidance_penalty": upset_signal.avoidance_penalty,
        "upset_signal": upset_signal.signal_score,
        "odds_stability": candidate.odds_stability_score,
        "volatility_penalty": candidate.volatility_penalty,
        "calibration_risk": calibration_risk,
        "longshot_upset_risk": longshot_upset_risk,
        "calibrated_upset_exposure": calibrated_upset_exposure,
        "upset_signal_calibration_risk": upset_signal_calibration.risk_score,
        "upset_signal_reliability": upset_signal_calibration.reliability_score,
        "candidate_score_penalty": candidate_score_penalty,
    }
    raw_score = (
        resolved_config.probability_weight * component_scores["probability"]
        + resolved_config.model_edge_weight * component_scores["model_edge"]
        + resolved_config.data_quality_weight * component_scores["data_quality"]
        + resolved_config.model_confidence_weight * component_scores["model_confidence"]
        + resolved_config.calibration_weight * component_scores["calibration"]
        + resolved_config.upset_protection_weight
        * component_scores["upset_protection_quality"]
        + resolved_config.odds_stability_weight * component_scores["odds_stability"]
        - resolved_config.upset_avoidance_penalty_weight
        * component_scores["upset_avoidance_penalty"]
        - resolved_config.volatility_penalty_weight * component_scores["volatility_penalty"]
        - resolved_config.calibration_risk_penalty_weight
        * component_scores["calibration_risk"]
        - resolved_config.longshot_upset_penalty_weight
        * component_scores["longshot_upset_risk"]
        + resolved_config.calibrated_upset_exposure_weight
        * component_scores["calibrated_upset_exposure"]
        - resolved_config.upset_signal_calibration_penalty_weight
        * component_scores["upset_signal_calibration_risk"]
        - component_scores["candidate_score_penalty"]
    )
    score = clamp_unit_interval(raw_score)
    reason_codes = [
        "accuracy_first_probability_component",
        "model_edge_component",
        "data_quality_component",
    ]
    if candidate.upset_protection_score > 0:
        reason_codes.append("upset_protection_component")
    reason_codes.extend(upset_signal.reason_codes)
    if upset_signal.avoidance_penalty > 0:
        reason_codes.append("upset_avoidance_penalty_applied")
    if candidate.volatility_penalty > 0:
        reason_codes.append("volatility_penalty_applied")
    if calibration_risk >= 0.22:
        reason_codes.append("calibration_risk_penalty_applied")
    if longshot_upset_risk >= 0.20:
        reason_codes.append("longshot_upset_penalty_applied")
    if calibrated_upset_exposure >= 0.35:
        reason_codes.append("calibrated_upset_exposure_allowed")
    if candidate.probability_source == "calibrated":
        reason_codes.append("calibrated_probability_component")
    if upset_signal_calibration.risk_score >= 0.20:
        reason_codes.append("upset_signal_calibration_penalty_applied")
    reason_codes.extend(upset_signal_calibration.reason_codes)
    if candidate_score_penalty > 0:
        reason_codes.append("candidate_score_penalty_applied")
    return ScoredRecommendationCandidate(
        candidate=candidate,
        score=score,
        component_scores=component_scores,
        reason_codes=reason_codes,
    )


def build_single_focus_policy_config(
    *,
    strategy: RecommendationStrategy,
    allowed_markets: tuple[RecommendationMarketType, ...],
    min_probability: float,
    min_model_edge: float | None,
    min_data_quality_score: float,
    min_data_quality_score_by_competition_id: Mapping[str, float] | None = None,
    require_odds: bool,
    data_quality_beta_lane_enabled: bool = False,
    data_quality_beta_lane_competition_ids: tuple[str, ...] = (),
    data_quality_beta_lane_season_ids: tuple[str, ...] = (),
    data_quality_beta_lane_min_competition_season_index: int | None = None,
    data_quality_beta_lane_max_competition_season_index: int | None = None,
    data_quality_beta_lane_min_probability: float = 0.0,
    data_quality_beta_lane_max_decimal_odds: float | None = None,
    data_quality_beta_lane_min_model_edge: float | None = None,
    data_quality_beta_lane_min_model_confidence_score: float = 0.0,
    data_quality_beta_lane_min_calibration_score: float = 0.0,
    data_quality_beta_lane_min_odds_stability_score: float = 0.0,
    data_quality_beta_lane_max_volatility_penalty: float | None = None,
) -> RecommendationPolicyConfig:
    return RecommendationPolicyConfig(
        strategy=strategy,
        allowed_markets=allowed_markets,
        min_probability=min_probability,
        min_model_edge=min_model_edge,
        min_data_quality_score=min_data_quality_score,
        min_data_quality_score_by_competition_id=dict(
            min_data_quality_score_by_competition_id or {}
        ),
        require_odds_for_parlay=require_odds,
        data_quality_beta_lane_enabled=data_quality_beta_lane_enabled,
        data_quality_beta_lane_competition_ids=data_quality_beta_lane_competition_ids,
        data_quality_beta_lane_season_ids=data_quality_beta_lane_season_ids,
        data_quality_beta_lane_min_competition_season_index=(
            data_quality_beta_lane_min_competition_season_index
        ),
        data_quality_beta_lane_max_competition_season_index=(
            data_quality_beta_lane_max_competition_season_index
        ),
        data_quality_beta_lane_min_probability=data_quality_beta_lane_min_probability,
        data_quality_beta_lane_max_decimal_odds=(
            data_quality_beta_lane_max_decimal_odds
        ),
        data_quality_beta_lane_min_model_edge=data_quality_beta_lane_min_model_edge,
        data_quality_beta_lane_min_model_confidence_score=(
            data_quality_beta_lane_min_model_confidence_score
        ),
        data_quality_beta_lane_min_calibration_score=(
            data_quality_beta_lane_min_calibration_score
        ),
        data_quality_beta_lane_min_odds_stability_score=(
            data_quality_beta_lane_min_odds_stability_score
        ),
        data_quality_beta_lane_max_volatility_penalty=(
            data_quality_beta_lane_max_volatility_penalty
        ),
        probability_weight=0.38,
        model_edge_weight=0.16,
        data_quality_weight=0.20,
        model_confidence_weight=0.14,
        calibration_weight=0.10,
        upset_protection_weight=0.02,
        upset_avoidance_penalty_weight=0.20,
        odds_stability_weight=0.04,
        volatility_penalty_weight=0.16,
        calibration_risk_penalty_weight=0.16,
        longshot_upset_penalty_weight=0.20,
        calibrated_upset_exposure_weight=0.04,
        upset_signal_calibration_penalty_weight=0.14,
    )


def build_recommendation_policy_config(
    *,
    strategy: RecommendationStrategy,
    allowed_markets: tuple[RecommendationMarketType, ...],
    min_probability: float,
    min_model_edge: float | None,
    min_data_quality_score: float,
    min_data_quality_score_by_competition_id: Mapping[str, float] | None = None,
    require_odds: bool,
    data_quality_beta_lane_enabled: bool = False,
    data_quality_beta_lane_competition_ids: tuple[str, ...] = (),
    data_quality_beta_lane_season_ids: tuple[str, ...] = (),
    data_quality_beta_lane_min_competition_season_index: int | None = None,
    data_quality_beta_lane_max_competition_season_index: int | None = None,
    data_quality_beta_lane_min_probability: float = 0.0,
    data_quality_beta_lane_max_decimal_odds: float | None = None,
    data_quality_beta_lane_min_model_edge: float | None = None,
    data_quality_beta_lane_min_model_confidence_score: float = 0.0,
    data_quality_beta_lane_min_calibration_score: float = 0.0,
    data_quality_beta_lane_min_odds_stability_score: float = 0.0,
    data_quality_beta_lane_max_volatility_penalty: float | None = None,
) -> RecommendationPolicyConfig:
    if strategy == "value_first":
        return RecommendationPolicyConfig(
            strategy=strategy,
            allowed_markets=allowed_markets,
            min_probability=min_probability,
            min_model_edge=0.0 if min_model_edge is None else min_model_edge,
            min_data_quality_score=min_data_quality_score,
            min_data_quality_score_by_competition_id=dict(
                min_data_quality_score_by_competition_id or {}
            ),
            require_odds_for_parlay=require_odds,
            data_quality_beta_lane_enabled=data_quality_beta_lane_enabled,
            data_quality_beta_lane_competition_ids=(
                data_quality_beta_lane_competition_ids
            ),
            data_quality_beta_lane_season_ids=data_quality_beta_lane_season_ids,
            data_quality_beta_lane_min_competition_season_index=(
                data_quality_beta_lane_min_competition_season_index
            ),
            data_quality_beta_lane_max_competition_season_index=(
                data_quality_beta_lane_max_competition_season_index
            ),
            data_quality_beta_lane_min_probability=(
                data_quality_beta_lane_min_probability
            ),
            data_quality_beta_lane_max_decimal_odds=(
                data_quality_beta_lane_max_decimal_odds
            ),
            data_quality_beta_lane_min_model_edge=(
                data_quality_beta_lane_min_model_edge
            ),
            data_quality_beta_lane_min_model_confidence_score=(
                data_quality_beta_lane_min_model_confidence_score
            ),
            data_quality_beta_lane_min_calibration_score=(
                data_quality_beta_lane_min_calibration_score
            ),
            data_quality_beta_lane_min_odds_stability_score=(
                data_quality_beta_lane_min_odds_stability_score
            ),
            data_quality_beta_lane_max_volatility_penalty=(
                data_quality_beta_lane_max_volatility_penalty
            ),
            probability_weight=0.18,
            model_edge_weight=0.42,
            data_quality_weight=0.12,
            model_confidence_weight=0.08,
            calibration_weight=0.10,
            upset_protection_weight=0.02,
            upset_avoidance_penalty_weight=0.16,
            odds_stability_weight=0.06,
            volatility_penalty_weight=0.12,
            calibration_risk_penalty_weight=0.10,
            longshot_upset_penalty_weight=0.08,
            calibrated_upset_exposure_weight=0.07,
            upset_signal_calibration_penalty_weight=0.08,
        )
    return RecommendationPolicyConfig(
        strategy=strategy,
        allowed_markets=allowed_markets,
        min_probability=min_probability,
        min_model_edge=min_model_edge,
        min_data_quality_score=min_data_quality_score,
        min_data_quality_score_by_competition_id=dict(
            min_data_quality_score_by_competition_id or {}
        ),
        require_odds_for_parlay=require_odds,
        data_quality_beta_lane_enabled=data_quality_beta_lane_enabled,
        data_quality_beta_lane_competition_ids=data_quality_beta_lane_competition_ids,
        data_quality_beta_lane_season_ids=data_quality_beta_lane_season_ids,
        data_quality_beta_lane_min_competition_season_index=(
            data_quality_beta_lane_min_competition_season_index
        ),
        data_quality_beta_lane_max_competition_season_index=(
            data_quality_beta_lane_max_competition_season_index
        ),
        data_quality_beta_lane_min_probability=data_quality_beta_lane_min_probability,
        data_quality_beta_lane_max_decimal_odds=(
            data_quality_beta_lane_max_decimal_odds
        ),
        data_quality_beta_lane_min_model_edge=data_quality_beta_lane_min_model_edge,
        data_quality_beta_lane_min_model_confidence_score=(
            data_quality_beta_lane_min_model_confidence_score
        ),
        data_quality_beta_lane_min_calibration_score=(
            data_quality_beta_lane_min_calibration_score
        ),
        data_quality_beta_lane_min_odds_stability_score=(
            data_quality_beta_lane_min_odds_stability_score
        ),
        data_quality_beta_lane_max_volatility_penalty=(
            data_quality_beta_lane_max_volatility_penalty
        ),
    )


def build_upset_focus_policy_config(
    *,
    strategy: RecommendationStrategy,
    allowed_markets: tuple[RecommendationMarketType, ...],
    min_probability: float,
    min_model_edge: float | None,
    min_data_quality_score: float,
    min_data_quality_score_by_competition_id: Mapping[str, float] | None = None,
    require_odds: bool,
    data_quality_beta_lane_enabled: bool = False,
    data_quality_beta_lane_competition_ids: tuple[str, ...] = (),
    data_quality_beta_lane_season_ids: tuple[str, ...] = (),
    data_quality_beta_lane_min_competition_season_index: int | None = None,
    data_quality_beta_lane_max_competition_season_index: int | None = None,
    data_quality_beta_lane_min_probability: float = 0.0,
    data_quality_beta_lane_max_decimal_odds: float | None = None,
    data_quality_beta_lane_min_model_edge: float | None = None,
    data_quality_beta_lane_min_model_confidence_score: float = 0.0,
    data_quality_beta_lane_min_calibration_score: float = 0.0,
    data_quality_beta_lane_min_odds_stability_score: float = 0.0,
    data_quality_beta_lane_max_volatility_penalty: float | None = None,
) -> RecommendationPolicyConfig:
    return RecommendationPolicyConfig(
        strategy=strategy,
        allowed_markets=allowed_markets,
        min_probability=min_probability,
        min_model_edge=min_model_edge,
        min_data_quality_score=min_data_quality_score,
        min_data_quality_score_by_competition_id=dict(
            min_data_quality_score_by_competition_id or {}
        ),
        require_odds_for_parlay=require_odds,
        data_quality_beta_lane_enabled=data_quality_beta_lane_enabled,
        data_quality_beta_lane_competition_ids=data_quality_beta_lane_competition_ids,
        data_quality_beta_lane_season_ids=data_quality_beta_lane_season_ids,
        data_quality_beta_lane_min_competition_season_index=(
            data_quality_beta_lane_min_competition_season_index
        ),
        data_quality_beta_lane_max_competition_season_index=(
            data_quality_beta_lane_max_competition_season_index
        ),
        data_quality_beta_lane_min_probability=data_quality_beta_lane_min_probability,
        data_quality_beta_lane_max_decimal_odds=(
            data_quality_beta_lane_max_decimal_odds
        ),
        data_quality_beta_lane_min_model_edge=data_quality_beta_lane_min_model_edge,
        data_quality_beta_lane_min_model_confidence_score=(
            data_quality_beta_lane_min_model_confidence_score
        ),
        data_quality_beta_lane_min_calibration_score=(
            data_quality_beta_lane_min_calibration_score
        ),
        data_quality_beta_lane_min_odds_stability_score=(
            data_quality_beta_lane_min_odds_stability_score
        ),
        data_quality_beta_lane_max_volatility_penalty=(
            data_quality_beta_lane_max_volatility_penalty
        ),
        probability_weight=0.18,
        model_edge_weight=0.18,
        data_quality_weight=0.10,
        model_confidence_weight=0.08,
        calibration_weight=0.10,
        upset_protection_weight=0.42,
        upset_avoidance_penalty_weight=0.24,
        odds_stability_weight=0.04,
        volatility_penalty_weight=0.14,
        calibration_risk_penalty_weight=0.10,
        longshot_upset_penalty_weight=0.08,
        calibrated_upset_exposure_weight=0.08,
        upset_signal_calibration_penalty_weight=0.20,
    )


def rank_candidates(
    candidates: Sequence[RecommendationCandidate],
    *,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
) -> list[ScoredRecommendationCandidate]:
    resolved_config = config or RecommendationPolicyConfig()
    scored = [
        score_candidate(candidate, config=resolved_config)
        for candidate in candidates
        if _candidate_exclusion_reason(
            candidate,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
        )
        is None
    ]
    return sorted(scored, key=_scored_candidate_sort_key)


def select_best_candidate(
    candidates: Sequence[RecommendationCandidate],
    *,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
) -> ScoredRecommendationCandidate:
    ranked = rank_candidates(candidates, config=config, as_of_time_utc=as_of_time_utc)
    if not ranked:
        raise ValueError("no eligible recommendation candidates")
    return ranked[0]


def select_best_single_parlay(
    candidates: Sequence[RecommendationCandidate],
    *,
    pass_type: str,
    unit_stake: float,
    max_budget: float | None = None,
    config: RecommendationPolicyConfig | None = None,
    as_of_time_utc: datetime | None = None,
    locked_candidates: Sequence[RecommendationCandidate] = (),
) -> RecommendationSelection:
    resolved_config = config or RecommendationPolicyConfig()
    leg_count = parse_pass_type_leg_count(pass_type)
    if len(locked_candidates) > leg_count:
        raise ValueError("locked candidate count exceeds requested pass type leg count")

    selected_by_fixture: dict[str, ScoredRecommendationCandidate] = {}
    for candidate in locked_candidates:
        if candidate.fixture_id in selected_by_fixture:
            raise ValueError("locked candidates must use distinct fixtures")
        if resolved_config.require_odds_for_parlay and candidate.decimal_odds is None:
            raise ValueError("locked candidates require decimal odds for parlay selection")
        selected_by_fixture[candidate.fixture_id] = score_candidate(
            candidate,
            config=resolved_config,
        )

    excluded_count = 0
    scored_pool: list[ScoredRecommendationCandidate] = []
    for candidate in candidates:
        if candidate.fixture_id in selected_by_fixture:
            continue
        reason = _candidate_exclusion_reason(
            candidate,
            config=resolved_config,
            as_of_time_utc=as_of_time_utc,
        )
        if reason is not None:
            excluded_count += 1
            continue
        scored_pool.append(score_candidate(candidate, config=resolved_config))

    for scored in sorted(scored_pool, key=_scored_candidate_sort_key):
        if len(selected_by_fixture) >= leg_count:
            break
        fixture_id = scored.candidate.fixture_id
        if fixture_id in selected_by_fixture:
            continue
        selected_by_fixture[fixture_id] = scored

    if len(selected_by_fixture) < leg_count:
        raise ValueError("insufficient_distinct_fixture_candidates")

    selected_candidates = list(selected_by_fixture.values())
    legs = [item.candidate.to_leg_selection() for item in selected_candidates]
    evaluation = evaluate_parlay(
        legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        max_budget=max_budget,
    )
    total_score = sum(item.score for item in selected_candidates) / len(selected_candidates)
    locked_fixture_ids = [candidate.fixture_id for candidate in locked_candidates]
    explanation_json: dict[str, object] = {
        "strategy": resolved_config.strategy,
        "selection_basis": "v3_1_recommendation_policy",
        "locked_fixture_ids": locked_fixture_ids,
        "started_locked_fixture_ids": [
            candidate.fixture_id
            for candidate in locked_candidates
            if as_of_time_utc is not None and candidate.has_started(as_of_time_utc)
        ],
        "candidate_filters": {
            "min_probability": resolved_config.min_probability,
            "min_data_quality_score": resolved_config.min_data_quality_score,
            "require_odds_for_parlay": resolved_config.require_odds_for_parlay,
        },
        "notes": [
            "Locked legs are preserved as user constraints.",
            "Unstarted and unlocked candidates are ranked by the recommendation policy.",
        ],
    }
    return RecommendationSelection(
        pass_type=pass_type,
        mode="single",
        selected_candidates=selected_candidates,
        evaluation=evaluation,
        total_score=total_score,
        locked_fixture_ids=locked_fixture_ids,
        candidate_count=len(candidates) + len(locked_candidates),
        excluded_candidate_count=excluded_count,
        explanation_json=explanation_json,
    )


def parse_pass_type_leg_count(pass_type: str) -> int:
    try:
        leg_count_text, multiplier_text = pass_type.lower().split("x", maxsplit=1)
        leg_count = int(leg_count_text)
        multiplier = int(multiplier_text)
    except ValueError as exc:
        raise ValueError(f"unsupported pass_type: {pass_type}") from exc
    if multiplier != 1 or leg_count < 1 or leg_count > 8:
        raise ValueError("V3.1 recommendation policy supports 1x1 through 8x1")
    return leg_count


def _candidate_exclusion_reason(
    candidate: RecommendationCandidate,
    *,
    config: RecommendationPolicyConfig,
    as_of_time_utc: datetime | None,
) -> str | None:
    if candidate.market_type not in config.allowed_markets:
        return "market_not_allowed"
    if candidate.effective_probability() < config.min_probability:
        return "probability_too_low"
    if candidate.data_quality_score < candidate_min_data_quality_score(candidate, config):
        return "data_quality_too_low"
    if not _candidate_satisfies_data_quality_beta_lane(candidate, config):
        return "data_quality_beta_lane_rejected"
    if candidate.model_confidence_score < config.min_model_confidence_score:
        return "model_confidence_too_low"
    if candidate.calibration_score < config.min_calibration_score:
        return "calibration_too_low"
    if (
        config.min_model_edge is not None
        and candidate.effective_model_edge() < config.min_model_edge
    ):
        return "model_edge_too_low"
    if config.require_odds_for_parlay and candidate.decimal_odds is None:
        return "odds_missing"
    if as_of_time_utc is not None and candidate.has_started(as_of_time_utc):
        return "fixture_already_started"
    return None


def candidate_min_data_quality_score(
    candidate: RecommendationCandidate,
    config: RecommendationPolicyConfig,
) -> float:
    raw_competition_id = candidate.metadata_json.get("competition_id")
    if isinstance(raw_competition_id, str):
        return config.min_data_quality_score_by_competition_id.get(
            raw_competition_id,
            config.min_data_quality_score,
        )
    return config.min_data_quality_score


def _candidate_satisfies_data_quality_beta_lane(
    candidate: RecommendationCandidate,
    config: RecommendationPolicyConfig,
) -> bool:
    if not config.data_quality_beta_lane_enabled:
        return True
    raw_competition_id = candidate.metadata_json.get("competition_id")
    if not isinstance(raw_competition_id, str):
        return True
    if (
        config.data_quality_beta_lane_competition_ids
        and raw_competition_id not in set(config.data_quality_beta_lane_competition_ids)
    ):
        return True
    if not _candidate_satisfies_data_quality_beta_lane_regime(candidate, config):
        return False
    effective_threshold = candidate_min_data_quality_score(candidate, config)
    if effective_threshold >= config.min_data_quality_score:
        return True
    if candidate.data_quality_score >= config.min_data_quality_score:
        return True
    if candidate.effective_probability() < config.data_quality_beta_lane_min_probability:
        return False
    if (
        config.data_quality_beta_lane_max_decimal_odds is not None
        and (
            candidate.decimal_odds is None
            or candidate.decimal_odds > config.data_quality_beta_lane_max_decimal_odds
        )
    ):
        return False
    if (
        config.data_quality_beta_lane_min_model_edge is not None
        and candidate.effective_model_edge()
        < config.data_quality_beta_lane_min_model_edge
    ):
        return False
    if (
        candidate.model_confidence_score
        < config.data_quality_beta_lane_min_model_confidence_score
    ):
        return False
    if candidate.calibration_score < config.data_quality_beta_lane_min_calibration_score:
        return False
    if (
        candidate.odds_stability_score
        < config.data_quality_beta_lane_min_odds_stability_score
    ):
        return False
    return not (
        config.data_quality_beta_lane_max_volatility_penalty is not None
        and candidate.volatility_penalty
        > config.data_quality_beta_lane_max_volatility_penalty
    )


def _candidate_satisfies_data_quality_beta_lane_regime(
    candidate: RecommendationCandidate,
    config: RecommendationPolicyConfig,
) -> bool:
    if config.data_quality_beta_lane_season_ids:
        season_id = _candidate_season_id(candidate)
        if season_id not in set(config.data_quality_beta_lane_season_ids):
            return False
    if (
        config.data_quality_beta_lane_min_competition_season_index is None
        and config.data_quality_beta_lane_max_competition_season_index is None
    ):
        return True
    season_index = _candidate_competition_season_index(candidate)
    if season_index is None:
        return False
    if (
        config.data_quality_beta_lane_min_competition_season_index is not None
        and season_index < config.data_quality_beta_lane_min_competition_season_index
    ):
        return False
    return not (
        config.data_quality_beta_lane_max_competition_season_index is not None
        and season_index > config.data_quality_beta_lane_max_competition_season_index
    )


def _candidate_season_id(candidate: RecommendationCandidate) -> str | None:
    for key in ("season_id", "season", "source_season"):
        raw = candidate.metadata_json.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _candidate_competition_season_index(
    candidate: RecommendationCandidate,
) -> int | None:
    raw = candidate.metadata_json.get("competition_season_index")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str):
        match = search(r"\d+", raw)
        return int(match.group(0)) if match else None
    return None


def _metadata_unit_score(candidate: RecommendationCandidate, key: str) -> float:
    raw = candidate.metadata_json.get(key)
    if isinstance(raw, int | float):
        return clamp_unit_interval(float(raw))
    return 0.0


def _scored_candidate_sort_key(
    scored_candidate: ScoredRecommendationCandidate,
) -> tuple[float, float, str, str, str]:
    candidate = scored_candidate.candidate
    return (
        -scored_candidate.score,
        -candidate.probability,
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
    )
