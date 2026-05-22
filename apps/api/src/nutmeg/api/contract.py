from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal, cast

from nutmeg.accuracy.mock_repository import ACTIVE_MODEL_VERSION, MockAccuracyEventRepository
from nutmeg.accuracy.repository import AccuracyRepository, AccuracySummaryService
from nutmeg.api.schemas import (
    AccuracySummaryResponse,
    CorrectScorePayload,
    FixtureFreshnessPayload,
    FixtureListItem,
    FixturePayload,
    FixturePredictionBrief,
    FixturePredictionResponse,
    KeyFactorsPayload,
    MarketComparisonSet,
    MarketProbabilityComparison,
    ModelMetadataPayload,
    ParlayLegPayload,
    ParlayRecommendRequest,
    ParlayRecommendResponse,
    ParlayTicketPayload,
    ProviderGovernanceResponse,
    ScoreGridResponse,
    TeamPayload,
    UpsetAlertPayload,
    UpsetContributionPayload,
    UpsetExplanationGroupPayload,
    UpsetListItem,
)
from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.domain.prediction import MarketProbabilityValue, PredictionSnapshot
from nutmeg.parlay import evaluate_parlay
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.governance.contracts import ProviderAuthorizationRecord
from nutmeg.providers.governance.onboarding import CompetitionOnboardingAssessment
from nutmeg.providers.governance.status import build_mock_provider_governance_snapshot
from nutmeg.providers.mock import MockFixture, get_mock_fixture, list_mock_fixtures
from nutmeg.providers.mock.data import MockTeam
from nutmeg.providers.odds_coverage import FixtureOddsCoverage

type MarketProbabilityMap = dict[str, float]
type CorrectScoreRow = dict[str, float | int | str]


def data_quality_grade(score: float) -> Literal["A", "B", "C", "D"]:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def list_fixture_items(
    snapshots: dict[str, PredictionSnapshot],
    *,
    date_filter: str | None = None,
    competition_id: str | None = None,
    odds_freshness: dict[str, FixtureOddsCoverage] | None = None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None = None,
    freshness_fallback_used: bool = False,
    freshness_messages: list[str] | None = None,
) -> list[FixtureListItem]:
    fixtures = _filter_fixtures(date_filter=date_filter, competition_id=competition_id)
    return [
        _fixture_list_item(
            fixture,
            snapshots[fixture["fixture_id"]],
            odds_freshness=odds_freshness,
            availability_freshness=availability_freshness,
            freshness_fallback_used=freshness_fallback_used,
            freshness_messages=freshness_messages or [],
        )
        for fixture in fixtures
        if fixture["fixture_id"] in snapshots
    ]


def fixture_prediction_response(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    *,
    odds_freshness: dict[str, FixtureOddsCoverage] | None = None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None = None,
    freshness_fallback_used: bool = False,
    freshness_messages: list[str] | None = None,
) -> FixturePredictionResponse:
    freshness_payload = _fixture_freshness_payload(
        fixture,
        odds_freshness=odds_freshness,
        availability_freshness=availability_freshness,
        freshness_fallback_used=freshness_fallback_used,
        freshness_messages=freshness_messages or [],
    )
    stale = _fixture_is_stale(freshness_payload)
    fixture_payload = _fixture_payload(fixture, prediction, stale=stale)
    metadata = _model_metadata(
        fixture,
        prediction,
        stale=stale,
        fallback_used=freshness_fallback_used,
        data_freshness=freshness_payload,
    )
    score_top_n = _score_top_n(prediction)
    odds_comparison = _market_comparison_sets(fixture, prediction)
    upset_alerts = _upset_alerts(fixture, prediction)
    return FixturePredictionResponse(
        fixture=fixture_payload,
        prediction_snapshot=prediction,
        score_top_n=score_top_n,
        market_predictions={
            key: value for key, value in prediction.market_probabilities.items()
        },
        odds_comparison=odds_comparison,
        upset_alerts=upset_alerts,
        explanations=KeyFactorsPayload(**fixture["key_factors"]),
        model_metadata=metadata,
        stale=stale,
        fallback_used=freshness_fallback_used,
    )


def score_grid_response(fixture_id: str, prediction: PredictionSnapshot) -> ScoreGridResponse:
    score_grid = prediction.score_grid
    return ScoreGridResponse(
        fixture_id=fixture_id,
        max_goals=score_grid.max_goals,
        grid=score_grid.grid,
        tail_mass=score_grid.tail_mass,
        lambda_home=score_grid.lambda_home,
        lambda_away=score_grid.lambda_away,
        model_version=prediction.model_version,
        calibration_version=prediction.calibration_version,
        prediction_time_utc=prediction.prediction_time_utc,
    )


def upset_list_items(snapshots: dict[str, PredictionSnapshot]) -> list[UpsetListItem]:
    items: list[UpsetListItem] = []
    for fixture in list_mock_fixtures():
        prediction = snapshots.get(fixture["fixture_id"])
        if prediction is None:
            continue
        for alert in _upset_alerts(fixture, prediction):
            items.append(
                UpsetListItem(
                    **alert.model_dump(),
                    match_label=_match_label(fixture),
                    competition_name=fixture["competition"],
                    kickoff_time_utc=fixture["kickoff_time_utc"],
                    data_quality_score=prediction.data_quality_score,
                    data_quality_grade=data_quality_grade(prediction.data_quality_score),
                    model_version=prediction.model_version,
                    prediction_time_utc=prediction.prediction_time_utc,
                )
            )
    return sorted(items, key=lambda item: item.favorite_fragility_score, reverse=True)


def parlay_recommendations(
    request: ParlayRecommendRequest,
    snapshots: dict[str, PredictionSnapshot],
    *,
    competition_readiness: list[CompetitionOnboardingAssessment] | None = None,
    odds_freshness: dict[str, FixtureOddsCoverage] | None = None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None = None,
    stale: bool = False,
    fallback_used: bool = False,
    initial_warnings: list[str] | None = None,
) -> ParlayRecommendResponse:
    tickets: list[ParlayTicketPayload] = []
    warnings = list(initial_warnings or [])
    readiness_by_competition = _readiness_by_competition(competition_readiness or [])
    if "2x1" in request.pass_types:
        eligible, reason = _candidate_fixtures_are_recommendable(
            [_fixture_or_raise("fix_epl_001"), _fixture_or_raise("fix_epl_002")],
            exclude_beta_competitions=request.exclude_beta_competitions,
            readiness_by_competition=readiness_by_competition,
            market_requirements={
                "fix_epl_001": {"1x2"},
                "fix_epl_002": {"cn_handicap_1x2"},
            },
            odds_freshness=odds_freshness,
            availability_freshness=availability_freshness,
        )
        if eligible:
            tickets.append(_balanced_two_leg_ticket(request, snapshots))
        else:
            warnings.append(f"skipped_2x1:{reason}")
    if request.allow_multiple_outcomes_per_fixture and "4x1" in request.pass_types:
        eligible, reason = _candidate_fixtures_are_recommendable(
            [
                _fixture_or_raise("fix_epl_001"),
                _fixture_or_raise("fix_epl_002"),
                _fixture_or_raise("fix_j1_001"),
            ],
            exclude_beta_competitions=request.exclude_beta_competitions,
            readiness_by_competition=readiness_by_competition,
            market_requirements={
                "fix_epl_001": {"1x2", "asian_handicap"},
                "fix_epl_002": {"cn_handicap_1x2"},
                "fix_j1_001": {"1x2"},
            },
            odds_freshness=odds_freshness,
            availability_freshness=availability_freshness,
        )
        if eligible:
            tickets.append(_multiple_upset_ticket(request, snapshots))
        else:
            warnings.append(f"skipped_4x1:{reason}")
    return ParlayRecommendResponse(
        items=tickets,
        warnings=warnings,
        stale=stale or _warnings_include_stale_data(warnings),
        fallback_used=fallback_used,
    )


def accuracy_summary_response(
    *,
    model_version: str,
    window: str,
    competition_id: str = "all",
    market: str = "all",
    repository: AccuracyRepository | None = None,
    active_model_version: str = ACTIVE_MODEL_VERSION,
) -> AccuracySummaryResponse:
    if repository is None:
        repository = MockAccuracyEventRepository(_build_mock_prediction_snapshots())
    return AccuracySummaryService(
        repository,
        active_model_version=active_model_version,
    ).build_summary(
        model_version=model_version,
        competition_id=competition_id,
        market=market,
        window=window,
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
    )


def provider_governance_response(
    *,
    persisted_competition_readiness: list[CompetitionOnboardingAssessment] | None = None,
    provider_authorizations: list[ProviderAuthorizationRecord] | None = None,
    stale: bool = False,
    fallback_used: bool = False,
) -> ProviderGovernanceResponse:
    snapshot = build_mock_provider_governance_snapshot(
        persisted_competition_readiness=persisted_competition_readiness,
        provider_authorizations=provider_authorizations,
    )
    return ProviderGovernanceResponse(
        **snapshot.model_dump(),
        stale=stale,
        fallback_used=fallback_used,
    )


def _readiness_by_competition(
    assessments: list[CompetitionOnboardingAssessment],
) -> dict[str, CompetitionOnboardingAssessment]:
    readiness: dict[str, CompetitionOnboardingAssessment] = {}
    for assessment in assessments:
        if assessment.target_stage == "beta":
            readiness[assessment.competition_id] = assessment
    for assessment in assessments:
        readiness.setdefault(assessment.competition_id, assessment)
    return readiness


def _fixture_freshness_payload(
    fixture: MockFixture,
    *,
    odds_freshness: dict[str, FixtureOddsCoverage] | None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None,
    freshness_fallback_used: bool,
    freshness_messages: list[str],
) -> FixtureFreshnessPayload | None:
    if freshness_fallback_used:
        return FixtureFreshnessPayload(
            odds_available=False,
            odds_fresh_enough=False,
            lineup_available=False,
            lineup_fresh_enough=False,
            injury_available=False,
            injury_fresh_enough=False,
            messages=freshness_messages or ["data_freshness_repository_unavailable"],
        )
    if odds_freshness is None and availability_freshness is None:
        return None

    fixture_id = fixture["fixture_id"]
    odds_coverage = odds_freshness.get(fixture_id) if odds_freshness is not None else None
    availability_coverage = (
        availability_freshness.get(fixture_id) if availability_freshness is not None else None
    )
    messages: list[str] = []
    if (
        (odds_freshness is not None and odds_coverage is None)
        or (odds_coverage is not None and not odds_coverage.has_any_odds)
    ):
        messages.append(f"odds_unavailable:{fixture_id}")
    elif odds_coverage is not None and not odds_coverage.fresh_enough:
        messages.append(f"odds_stale:{fixture_id}")

    if availability_freshness is not None and availability_coverage is None:
        messages.append(f"lineup_unavailable:{fixture_id}")
        messages.append(f"injury_unavailable:{fixture_id}")
    elif availability_coverage is not None:
        if not availability_coverage.has_lineup:
            messages.append(f"lineup_unavailable:{fixture_id}")
        elif not availability_coverage.lineup_fresh_enough:
            messages.append(f"lineup_stale:{fixture_id}")
        if not availability_coverage.has_availability:
            messages.append(f"injury_unavailable:{fixture_id}")
        elif not availability_coverage.availability_fresh_enough:
            messages.append(f"injury_stale:{fixture_id}")

    return FixtureFreshnessPayload(
        odds_available=odds_coverage.has_any_odds if odds_coverage is not None else False,
        odds_fresh_enough=odds_coverage.fresh_enough if odds_coverage is not None else False,
        odds_market_types=odds_coverage.market_types if odds_coverage is not None else [],
        odds_snapshot_time_utc=(
            odds_coverage.latest_snapshot_time_utc if odds_coverage is not None else None
        ),
        odds_snapshot_lag_hours=(
            odds_coverage.latest_snapshot_lag_hours if odds_coverage is not None else None
        ),
        lineup_available=(
            availability_coverage.has_lineup if availability_coverage is not None else False
        ),
        lineup_fresh_enough=(
            availability_coverage.lineup_fresh_enough
            if availability_coverage is not None
            else False
        ),
        lineup_snapshot_time_utc=(
            availability_coverage.latest_lineup_snapshot_time_utc
            if availability_coverage is not None
            else None
        ),
        lineup_snapshot_lag_hours=(
            availability_coverage.lineup_snapshot_lag_hours
            if availability_coverage is not None
            else None
        ),
        injury_available=(
            availability_coverage.has_availability
            if availability_coverage is not None
            else False
        ),
        injury_fresh_enough=(
            availability_coverage.availability_fresh_enough
            if availability_coverage is not None
            else False
        ),
        injury_snapshot_time_utc=(
            availability_coverage.latest_availability_snapshot_time_utc
            if availability_coverage is not None
            else None
        ),
        injury_snapshot_lag_hours=(
            availability_coverage.availability_snapshot_lag_hours
            if availability_coverage is not None
            else None
        ),
        messages=messages,
    )


def _fixture_is_stale(freshness: FixtureFreshnessPayload | None) -> bool:
    return freshness is not None and (
        not freshness.odds_available or not freshness.odds_fresh_enough
        or not freshness.lineup_available or not freshness.lineup_fresh_enough
        or not freshness.injury_available or not freshness.injury_fresh_enough
    )


def _warnings_include_stale_data(warnings: list[str]) -> bool:
    stale_markers = (
        "odds_unavailable",
        "odds_market_unavailable",
        "odds_stale",
        "odds_freshness_repository_unavailable",
        "lineup_unavailable",
        "lineup_stale",
        "injury_unavailable",
        "injury_stale",
        "availability_freshness_repository_unavailable",
        "data_freshness_repository_unavailable",
    )
    return any(any(marker in warning for marker in stale_markers) for warning in warnings)


def _filter_fixtures(
    *,
    date_filter: str | None,
    competition_id: str | None,
) -> list[MockFixture]:
    requested_date: date | None = None
    if date_filter is not None:
        requested_date = date.fromisoformat(date_filter)

    fixtures: list[MockFixture] = []
    for fixture in list_mock_fixtures():
        if competition_id is not None and fixture["competition_id"] != competition_id:
            continue
        if requested_date is not None and fixture["kickoff_time_utc"].date() != requested_date:
            continue
        fixtures.append(fixture)
    return fixtures


def _build_mock_prediction_snapshots() -> dict[str, PredictionSnapshot]:
    snapshots: dict[str, PredictionSnapshot] = {}
    for fixture in list_mock_fixtures():
        prediction = build_mock_prediction_snapshot(fixture["fixture_id"])
        if prediction is not None:
            snapshots[fixture["fixture_id"]] = prediction
    return snapshots


def _team_payload(team: MockTeam) -> TeamPayload:
    return TeamPayload(team_id=team["team_id"], name=team["name"])


def _fixture_payload(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    *,
    stale: bool = False,
) -> FixturePayload:
    return FixturePayload(
        fixture_id=fixture["fixture_id"],
        competition_id=fixture["competition_id"],
        competition_name=fixture["competition"],
        kickoff_time_utc=fixture["kickoff_time_utc"],
        home_team=_team_payload(fixture["home_team"]),
        away_team=_team_payload(fixture["away_team"]),
        status="stale" if stale else cast(Literal["scheduled", "stale", "beta"], fixture["status"]),
        data_quality_score=prediction.data_quality_score,
        data_quality_grade=data_quality_grade(prediction.data_quality_score),
    )


def _fixture_list_item(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    *,
    odds_freshness: dict[str, FixtureOddsCoverage] | None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None,
    freshness_fallback_used: bool,
    freshness_messages: list[str],
) -> FixtureListItem:
    freshness_payload = _fixture_freshness_payload(
        fixture,
        odds_freshness=odds_freshness,
        availability_freshness=availability_freshness,
        freshness_fallback_used=freshness_fallback_used,
        freshness_messages=freshness_messages,
    )
    stale = _fixture_is_stale(freshness_payload)
    badges = [alert.type for alert in _upset_alerts(fixture, prediction)]
    return FixtureListItem(
        fixture_id=fixture["fixture_id"],
        competition_id=fixture["competition_id"],
        competition=fixture["competition"],
        kickoff_time_utc=fixture["kickoff_time_utc"],
        home_team=_team_payload(fixture["home_team"]),
        away_team=_team_payload(fixture["away_team"]),
        prediction=FixturePredictionBrief(
            p_home=prediction.p_home,
            p_draw=prediction.p_draw,
            p_away=prediction.p_away,
            confidence=cast(Literal["low", "medium", "high"], fixture["confidence"]),
            model_version=prediction.model_version,
            feature_version=prediction.feature_version,
            calibration_version=prediction.calibration_version,
            prediction_time_utc=prediction.prediction_time_utc,
            data_quality_score=prediction.data_quality_score,
            stale=stale,
            fallback_used=freshness_fallback_used,
            data_freshness=freshness_payload,
        ),
        badges=badges,
    )


def _model_metadata(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    *,
    stale: bool = False,
    fallback_used: bool = False,
    data_freshness: FixtureFreshnessPayload | None = None,
) -> ModelMetadataPayload:
    return ModelMetadataPayload(
        model_version=prediction.model_version,
        feature_version=prediction.feature_version,
        calibration_version=prediction.calibration_version,
        prediction_time_utc=prediction.prediction_time_utc,
        data_quality_score=prediction.data_quality_score,
        data_quality_grade=data_quality_grade(prediction.data_quality_score),
        stale=stale,
        fallback_used=fallback_used,
        data_freshness=data_freshness,
    )


def _score_top_n(prediction: PredictionSnapshot) -> list[CorrectScorePayload]:
    raw_scores = prediction.market_probabilities.get("correct_score_top_n", [])
    score_rows = cast(list[CorrectScoreRow], raw_scores)
    return [
        CorrectScorePayload(
            home_goals=cast(int, score["home_goals"]),
            away_goals=cast(int, score["away_goals"]),
            probability=cast(float, score["probability"]),
            option_key=cast(str, score["option_key"]),
        )
        for score in score_rows
    ]


def _market_comparison_sets(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
) -> dict[str, MarketComparisonSet]:
    one_x_two = _probability_map(prediction.market_probabilities["1x2"])
    cn_key = f"cn_handicap_1x2:{fixture['cn_handicap']}"
    asian_key = f"asian_handicap:home:{fixture['asian_handicap_line']:g}"
    european_key = f"european_handicap_1x2:{fixture['european_handicap']}"
    cn = _probability_map(prediction.market_probabilities[cn_key])
    asian = _probability_map(prediction.market_probabilities[asian_key])
    european = _probability_map(prediction.market_probabilities[european_key])
    return {
        "1x2": MarketComparisonSet(
            label="1X2 胜平负",
            items=_comparison_items(
                [
                    ("主胜", "home_win"),
                    ("平局", "draw"),
                    ("客胜", "away_win"),
                ],
                model_probabilities=one_x_two,
                market_probabilities=fixture["market_1x2"],
            ),
        ),
        "cn_handicap_1x2": MarketComparisonSet(
            label=f"主队 {fixture['cn_handicap']:+d}",
            items=_comparison_items(
                [
                    ("让胜", "handicap_home_win"),
                    ("让平", "handicap_draw"),
                    ("让负", "handicap_away_win"),
                ],
                model_probabilities=cn,
                market_probabilities=fixture["market_cn_handicap_1x2"],
            ),
        ),
        "asian_handicap": MarketComparisonSet(
            label=f"主队 {fixture['asian_handicap_line']:+g}",
            items=_comparison_items(
                [
                    ("全赢", "full_win"),
                    ("半赢", "half_win"),
                    ("走水", "push"),
                    ("半输", "half_loss"),
                    ("全输", "full_loss"),
                ],
                model_probabilities=asian,
                market_probabilities={},
            ),
        ),
        "european_handicap_1x2": MarketComparisonSet(
            label=f"主队 {fixture['european_handicap']:+d}",
            items=_comparison_items(
                [
                    ("让胜", "handicap_home_win"),
                    ("让平", "handicap_draw"),
                    ("让负", "handicap_away_win"),
                ],
                model_probabilities=european,
                market_probabilities=fixture["market_european_handicap_1x2"],
            ),
        ),
    }


def _comparison_items(
    labels: list[tuple[str, str]],
    *,
    model_probabilities: MarketProbabilityMap,
    market_probabilities: MarketProbabilityMap,
) -> list[MarketProbabilityComparison]:
    gaps = {
        outcome_key: model_probabilities[outcome_key] - market_probability
        for _, outcome_key in labels
        if (market_probability := market_probabilities.get(outcome_key)) is not None
    }
    highlighted_key = max(gaps, key=lambda key: gaps[key]) if gaps else None
    return [
        MarketProbabilityComparison(
            label=label,
            outcome_key=outcome_key,
            model_probability=model_probabilities[outcome_key],
            market_probability=market_probabilities.get(outcome_key),
            probability_gap=gaps.get(outcome_key),
            highlighted=outcome_key == highlighted_key and gaps.get(outcome_key, 0.0) > 0,
        )
        for label, outcome_key in labels
    ]


def _probability_map(value: MarketProbabilityValue) -> MarketProbabilityMap:
    if not isinstance(value, dict):
        raise TypeError("market probability value is not a probability map")
    return {key: float(probability) for key, probability in value.items()}


def _upset_alerts(fixture: MockFixture, prediction: PredictionSnapshot) -> list[UpsetAlertPayload]:
    market_1x2 = fixture["market_1x2"]
    one_x_two = _probability_map(prediction.market_probabilities["1x2"])
    cn_key = f"cn_handicap_1x2:{fixture['cn_handicap']}"
    cn = _probability_map(prediction.market_probabilities[cn_key])
    cn_market = fixture["market_cn_handicap_1x2"]

    draw_gap = one_x_two["draw"] - market_1x2["draw"]
    fail_cover_gap = cn["handicap_away_win"] - cn_market["handicap_away_win"]
    if fail_cover_gap > draw_gap and fail_cover_gap > 0.01:
        return [
            _upset_alert(
                fixture,
                prediction,
                alert_type="favorite_fail_to_cover",
                label="热门输盘",
                target_outcome="让负",
                model_probability=cn["handicap_away_win"],
                market_probability=cn_market["handicap_away_win"],
                probability_gap=fail_cover_gap,
                explanations=[
                    "热门方向胜率较高，但模型认为赢盘概率不足。",
                    "一球小胜与平局分布会压低深盘表现。",
                ],
            )
        ]
    if draw_gap > 0.001:
        return [
            _upset_alert(
                fixture,
                prediction,
                alert_type="draw_overlooked",
                label="平局被低估",
                target_outcome="平局",
                model_probability=one_x_two["draw"],
                market_probability=market_1x2["draw"],
                probability_gap=draw_gap,
                explanations=[
                    "模型平局概率高于市场隐含概率。",
                    "热门方向优势存在，但一球内分布较集中。",
                ],
            )
        ]
    return []


def _upset_alert(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    *,
    alert_type: str,
    label: str,
    target_outcome: str,
    model_probability: float,
    market_probability: float,
    probability_gap: float,
    explanations: list[str],
) -> UpsetAlertPayload:
    fragility_score = _favorite_fragility_score(fixture, prediction)
    favorite, favorite_model_probability, favorite_market_probability = _favorite_context(
        fixture,
        prediction,
    )
    contributions = _upset_contributions(fixture, prediction, probability_gap)
    return UpsetAlertPayload(
        fixture_id=fixture["fixture_id"],
        type=alert_type,
        label=label,
        target_outcome=target_outcome,
        favorite=favorite,
        favorite_model_probability=favorite_model_probability,
        favorite_market_probability=favorite_market_probability,
        model_probability=model_probability,
        market_probability=market_probability,
        probability_gap=probability_gap,
        favorite_fragility_score=fragility_score,
        risk_level=_risk_level(fragility_score),
        explanations=explanations,
        contributions=contributions,
        explanation_groups=_upset_explanation_groups(
            fixture,
            alert_type=alert_type,
            explanations=explanations,
            contributions=contributions,
        ),
    )


def _favorite_context(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
) -> tuple[str, float, float]:
    one_x_two = _probability_map(prediction.market_probabilities["1x2"])
    favorite_key = max(
        fixture["market_1x2"],
        key=lambda key: fixture["market_1x2"][key],
    )
    favorite_labels = {
        "home_win": fixture["home_team"]["name"],
        "draw": "平局",
        "away_win": fixture["away_team"]["name"],
    }
    return (
        favorite_labels[favorite_key],
        one_x_two[favorite_key],
        fixture["market_1x2"][favorite_key],
    )


def _favorite_fragility_score(fixture: MockFixture, prediction: PredictionSnapshot) -> float:
    one_x_two = _probability_map(prediction.market_probabilities["1x2"])
    favorite_key = max(
        fixture["market_1x2"],
        key=lambda key: fixture["market_1x2"][key],
    )
    favorite_not_win_probability = 1.0 - one_x_two[favorite_key]
    low_score_probability = sum(
        score.probability
        for score in prediction.score_grid.iter_scores()
        if score.home_goals + score.away_goals <= 2
    )
    data_gap = 1.0 - prediction.data_quality_score / 100.0
    score = (
        0.35 * favorite_not_win_probability
        + 0.25 * one_x_two["draw"]
        + 0.20 * low_score_probability
        + 0.20 * data_gap
    )
    return max(0.0, min(1.0, score))


def _upset_contributions(
    fixture: MockFixture,
    prediction: PredictionSnapshot,
    probability_gap: float,
) -> list[UpsetContributionPayload]:
    one_x_two = _probability_map(prediction.market_probabilities["1x2"])
    favorite_key = max(
        fixture["market_1x2"],
        key=lambda key: fixture["market_1x2"][key],
    )
    cn_key = f"cn_handicap_1x2:{fixture['cn_handicap']}"
    cn = _probability_map(prediction.market_probabilities[cn_key])
    low_score_probability = sum(
        score.probability
        for score in prediction.score_grid.iter_scores()
        if score.home_goals + score.away_goals <= 2
    )
    market_overpricing = max(
        0.0,
        fixture["market_1x2"][favorite_key] - one_x_two[favorite_key],
    ) + max(0.0, probability_gap)
    data_gap = 1.0 - prediction.data_quality_score / 100.0

    return [
        UpsetContributionPayload(
            key="draw_pressure",
            label="平局压力",
            score=_contribution_score(one_x_two["draw"], scale=100.0),
            description="平局概率越高，热门方向越难形成强结论。",
        ),
        UpsetContributionPayload(
            key="handicap_depth",
            label="盘口偏深",
            score=_contribution_score(cn["handicap_away_win"], scale=100.0),
            description="让负方向概率越高，热门打穿盘口的空间越窄。",
        ),
        UpsetContributionPayload(
            key="low_score_tendency",
            label="低比分倾向",
            score=_contribution_score(low_score_probability, scale=100.0),
            description="低比分分布集中时，一球差与平局风险更敏感。",
        ),
        UpsetContributionPayload(
            key="market_overpricing",
            label="市场高估热门",
            score=_contribution_score(market_overpricing, scale=1000.0),
            description="模型与市场差异越大，越需要解释市场分歧来源。",
        ),
        UpsetContributionPayload(
            key="data_uncertainty",
            label="数据不完整",
            score=_contribution_score(data_gap, scale=100.0),
            description="数据质量越低，冷门观察越应被谨慎解读。",
        ),
    ]


def _contribution_score(value: float, *, scale: float) -> float:
    return round(max(0.0, min(100.0, value * scale)), 1)


def _upset_explanation_groups(
    fixture: MockFixture,
    *,
    alert_type: str,
    explanations: list[str],
    contributions: list[UpsetContributionPayload],
) -> list[UpsetExplanationGroupPayload]:
    key_factors = fixture["key_factors"]
    strongest = sorted(contributions, key=lambda item: item.score, reverse=True)[:3]
    return [
        UpsetExplanationGroupPayload(
            title="模型因素",
            items=explanations + key_factors.get("model", []),
        ),
        UpsetExplanationGroupPayload(
            title="市场因素",
            items=key_factors.get("market", []),
        ),
        UpsetExplanationGroupPayload(
            title="主要贡献",
            items=[
                f"{item.label}：{item.score:.1f}/100，{item.description}"
                for item in strongest
            ],
        ),
        UpsetExplanationGroupPayload(
            title="边界说明",
            items=[
                f"{alert_type} 是观察标签，不是确定结果。",
                "冷门观察需要结合数据质量、盘口和比分分布一起解释。",
            ],
        ),
    ]


def _risk_level(score: float) -> Literal["low", "medium", "medium_high", "high"]:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium_high"
    if score >= 0.30:
        return "medium"
    return "low"


def _balanced_two_leg_ticket(
    request: ParlayRecommendRequest,
    snapshots: dict[str, PredictionSnapshot],
) -> ParlayTicketPayload:
    first = _fixture_or_raise("fix_epl_001")
    second = _fixture_or_raise("fix_epl_002")
    first_probabilities = _probability_map(
        snapshots[first["fixture_id"]].market_probabilities["1x2"]
    )
    second_key = f"cn_handicap_1x2:{second['cn_handicap']}"
    second_probabilities = _probability_map(
        snapshots[second["fixture_id"]].market_probabilities[second_key]
    )
    evaluation = evaluate_parlay(
        [
            ParlayLegSelection(
                fixture_id=first["fixture_id"],
                market_type="1x2",
                outcomes=["home_win"],
                probabilities={"home_win": first_probabilities["home_win"]},
                odds={"home_win": _fair_odds(first["market_1x2"]["home_win"])},
                model_version=snapshots[first["fixture_id"]].model_version,
                data_quality_score=snapshots[first["fixture_id"]].data_quality_score,
            ),
            ParlayLegSelection(
                fixture_id=second["fixture_id"],
                market_type="cn_handicap_1x2",
                outcomes=["handicap_away_win"],
                probabilities={"handicap_away_win": second_probabilities["handicap_away_win"]},
                odds={
                    "handicap_away_win": _fair_odds(
                        second["market_cn_handicap_1x2"]["handicap_away_win"]
                    )
                },
                line=float(second["cn_handicap"]),
                model_version=snapshots[second["fixture_id"]].model_version,
                data_quality_score=snapshots[second["fixture_id"]].data_quality_score,
            ),
        ],
        pass_type="2x1",
        unit_stake=request.unit_stake,
        max_budget=request.max_budget,
    )
    return ParlayTicketPayload(
        recommendation_id="parlay_balanced_001",
        model_version=snapshots[first["fixture_id"]].model_version,
        strategy="平衡型",
        pass_type="2x1",
        is_multiple=evaluation.is_multiple,
        legs=[
            ParlayLegPayload(
                fixture_id=first["fixture_id"],
                match_label=_match_label(first),
                market="1X2",
                outcomes=["主胜"],
            ),
            ParlayLegPayload(
                fixture_id=second["fixture_id"],
                match_label=_match_label(second),
                market="让球胜平负",
                outcomes=["让负"],
            ),
        ],
        atomic_bet_count=evaluation.total_atomic_bets,
        unit_stake=evaluation.unit_stake,
        total_stake=evaluation.total_stake,
        hit_probability=evaluation.hit_probability,
        expected_payout=evaluation.expected_payout,
        ev=evaluation.expected_value,
        roi=evaluation.roi,
        risk_level=cast(Literal["low", "medium", "medium_high", "high"], evaluation.risk_level),
        risk_score=evaluation.risk_score,
        correlation_penalty=evaluation.correlation_penalty,
        rule_valid=evaluation.rule_valid,
        explanations=[
            "两个选项均来自数据质量 B 以上赛事。",
            "组合命中概率为模型独立近似结果，仍存在不确定性。",
        ],
        explanation_json=evaluation.explanation_json,
        atomic_bets=evaluation.atomic_bets,
    )


def _multiple_upset_ticket(
    request: ParlayRecommendRequest,
    snapshots: dict[str, PredictionSnapshot],
) -> ParlayTicketPayload:
    first = _fixture_or_raise("fix_epl_001")
    second = _fixture_or_raise("fix_epl_002")
    third = _fixture_or_raise("fix_j1_001")
    first_1x2 = _probability_map(snapshots[first["fixture_id"]].market_probabilities["1x2"])
    second_key = f"cn_handicap_1x2:{second['cn_handicap']}"
    second_cn = _probability_map(snapshots[second["fixture_id"]].market_probabilities[second_key])
    third_1x2 = _probability_map(snapshots[third["fixture_id"]].market_probabilities["1x2"])
    first_asian_key = f"asian_handicap:home:{first['asian_handicap_line']:g}"
    first_asian = _probability_map(
        snapshots[first["fixture_id"]].market_probabilities[first_asian_key]
    )
    evaluation = evaluate_parlay(
        [
            ParlayLegSelection(
                fixture_id=first["fixture_id"],
                market_type="1x2",
                outcomes=["draw", "away_win"],
                probabilities={"draw": first_1x2["draw"], "away_win": first_1x2["away_win"]},
                odds={
                    "draw": _fair_odds(first["market_1x2"]["draw"]),
                    "away_win": _fair_odds(first["market_1x2"]["away_win"]),
                },
                model_version=snapshots[first["fixture_id"]].model_version,
                data_quality_score=snapshots[first["fixture_id"]].data_quality_score,
            ),
            ParlayLegSelection(
                fixture_id=second["fixture_id"],
                market_type="cn_handicap_1x2",
                outcomes=["handicap_draw", "handicap_away_win"],
                probabilities={
                    "handicap_draw": second_cn["handicap_draw"],
                    "handicap_away_win": second_cn["handicap_away_win"],
                },
                odds={
                    "handicap_draw": _fair_odds(
                        second["market_cn_handicap_1x2"]["handicap_draw"]
                    ),
                    "handicap_away_win": _fair_odds(
                        second["market_cn_handicap_1x2"]["handicap_away_win"]
                    ),
                },
                line=float(second["cn_handicap"]),
                model_version=snapshots[second["fixture_id"]].model_version,
                data_quality_score=snapshots[second["fixture_id"]].data_quality_score,
            ),
            ParlayLegSelection(
                fixture_id=third["fixture_id"],
                market_type="1x2",
                outcomes=["draw"],
                probabilities={"draw": third_1x2["draw"]},
                odds={"draw": _fair_odds(third["market_1x2"]["draw"])},
                model_version=snapshots[third["fixture_id"]].model_version,
                data_quality_score=snapshots[third["fixture_id"]].data_quality_score,
            ),
            ParlayLegSelection(
                fixture_id=first["fixture_id"],
                market_type="asian_handicap",
                outcomes=["half_loss", "full_loss"],
                probabilities={
                    "half_loss": first_asian["half_loss"],
                    "full_loss": first_asian["full_loss"],
                },
                odds={"half_loss": 1.82, "full_loss": 1.82},
                line=first["asian_handicap_line"],
                side="home",
                model_version=snapshots[first["fixture_id"]].model_version,
                data_quality_score=snapshots[first["fixture_id"]].data_quality_score,
            ),
        ],
        pass_type="4x1",
        unit_stake=request.unit_stake,
        max_budget=request.max_budget,
        correlation_penalty=0.08,
    )
    return ParlayTicketPayload(
        recommendation_id="parlay_cover_002",
        model_version=snapshots[first["fixture_id"]].model_version,
        strategy="冷门观察型",
        pass_type="4x1",
        is_multiple=evaluation.is_multiple,
        legs=[
            ParlayLegPayload(
                fixture_id=first["fixture_id"],
                match_label=_match_label(first),
                market="1X2",
                outcomes=["平局", "客胜"],
            ),
            ParlayLegPayload(
                fixture_id=second["fixture_id"],
                match_label=_match_label(second),
                market="让球胜平负",
                outcomes=["让平", "让负"],
            ),
            ParlayLegPayload(
                fixture_id=third["fixture_id"],
                match_label=_match_label(third),
                market="1X2",
                outcomes=["平局"],
            ),
            ParlayLegPayload(
                fixture_id=first["fixture_id"],
                match_label=_match_label(first),
                market="亚洲让球",
                outcomes=["主队 -0.25 半输/全输方向"],
            ),
        ],
        atomic_bet_count=evaluation.total_atomic_bets,
        unit_stake=evaluation.unit_stake,
        total_stake=evaluation.total_stake,
        hit_probability=evaluation.hit_probability,
        expected_payout=evaluation.expected_payout,
        ev=evaluation.expected_value,
        roi=evaluation.roi,
        risk_level=cast(Literal["low", "medium", "medium_high", "high"], evaluation.risk_level),
        risk_score=evaluation.risk_score,
        correlation_penalty=evaluation.correlation_penalty,
        rule_valid=evaluation.rule_valid,
        explanations=[
            "复式会增加注数和总金额。",
            "包含同场不同玩法，当前规则引擎标记为不合法。",
            "该组合命中概率较低，任一单式注失误都会影响返还。",
        ],
        explanation_json=evaluation.explanation_json,
        atomic_bets=evaluation.atomic_bets,
    )


def _candidate_fixtures_are_recommendable(
    fixtures: list[MockFixture],
    *,
    exclude_beta_competitions: bool,
    readiness_by_competition: dict[str, CompetitionOnboardingAssessment],
    market_requirements: dict[str, set[str]],
    odds_freshness: dict[str, FixtureOddsCoverage] | None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None,
) -> tuple[bool, str | None]:
    if exclude_beta_competitions:
        beta_competitions = sorted(
            {
                fixture["competition_id"]
                for fixture in fixtures
                if fixture["status"] == "beta"
            }
        )
        if beta_competitions:
            return False, "beta_competition_excluded:" + ",".join(beta_competitions)
    low_quality_fixture_ids = sorted(
        fixture["fixture_id"]
        for fixture in fixtures
        if fixture["data_quality_score"] < 50.0
    )
    if low_quality_fixture_ids:
        return False, "data_quality_below_50:" + ",".join(low_quality_fixture_ids)

    competition_ids = sorted({fixture["competition_id"] for fixture in fixtures})
    readiness = [
        assessment
        for competition_id in competition_ids
        if (assessment := readiness_by_competition.get(competition_id)) is not None
    ]
    ineligible_competitions = sorted(
        assessment.competition_id
        for assessment in readiness
        if not assessment.data_quality.parlay_eligible
    )
    if ineligible_competitions:
        return False, "competition_data_quality_d:" + ",".join(ineligible_competitions)

    not_ready_competitions = sorted(
        assessment.competition_id for assessment in readiness if not assessment.beta_ready
    )
    if not_ready_competitions:
        return False, "competition_not_ready:" + ",".join(not_ready_competitions)

    stale_data_competitions = sorted(
        assessment.competition_id
        for assessment in readiness
        if assessment.data_quality.components.data_freshness < 0.5
    )
    if stale_data_competitions:
        return False, "competition_data_freshness_low:" + ",".join(stale_data_competitions)

    if odds_freshness is not None:
        missing_odds = sorted(
            fixture["fixture_id"]
            for fixture in fixtures
            if (
                coverage := odds_freshness.get(fixture["fixture_id"])
            ) is None
            or not coverage.has_any_odds
        )
        if missing_odds:
            return False, "odds_unavailable:" + ",".join(missing_odds)

        missing_markets: list[str] = []
        stale_odds: list[str] = []
        for fixture in fixtures:
            fixture_id = fixture["fixture_id"]
            coverage = odds_freshness[fixture_id]
            required_markets = market_requirements.get(fixture_id, set())
            unavailable_markets = sorted(required_markets - set(coverage.market_types))
            if unavailable_markets:
                missing_markets.append(f"{fixture_id}=" + ",".join(unavailable_markets))
            if not coverage.fresh_enough:
                stale_odds.append(fixture_id)
        if missing_markets:
            return False, "odds_market_unavailable:" + ";".join(missing_markets)
        if stale_odds:
            return False, "odds_stale:" + ",".join(sorted(stale_odds))

    if availability_freshness is not None:
        missing_lineups: list[str] = []
        for fixture in fixtures:
            fixture_id = fixture["fixture_id"]
            availability_coverage = availability_freshness.get(fixture_id)
            if availability_coverage is None or not availability_coverage.has_lineup:
                missing_lineups.append(fixture_id)
        missing_lineups = sorted(missing_lineups)
        if missing_lineups:
            return False, "lineup_unavailable:" + ",".join(missing_lineups)

        missing_injuries = sorted(
            fixture["fixture_id"]
            for fixture in fixtures
            if not availability_freshness[fixture["fixture_id"]].has_availability
        )
        if missing_injuries:
            return False, "injury_unavailable:" + ",".join(missing_injuries)

        stale_lineups = sorted(
            fixture["fixture_id"]
            for fixture in fixtures
            if not availability_freshness[fixture["fixture_id"]].lineup_fresh_enough
        )
        if stale_lineups:
            return False, "lineup_stale:" + ",".join(stale_lineups)

        stale_injuries = sorted(
            fixture["fixture_id"]
            for fixture in fixtures
            if not availability_freshness[fixture["fixture_id"]].availability_fresh_enough
        )
        if stale_injuries:
            return False, "injury_stale:" + ",".join(stale_injuries)
    return True, None


def _fixture_or_raise(fixture_id: str) -> MockFixture:
    fixture = get_mock_fixture(fixture_id)
    if fixture is None:
        raise LookupError(f"missing mock fixture {fixture_id}")
    return fixture


def _fair_odds(probability: float) -> float:
    return max(1.01, 1.0 / probability)


def _match_label(fixture: MockFixture) -> str:
    return f"{fixture['home_team']['name']} vs {fixture['away_team']['name']}"
