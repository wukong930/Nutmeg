from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayEvaluation, ParlayLegSelection

type RecommendationMarketType = Literal[
    "1x2",
    "cn_handicap_1x2",
    "european_handicap_1x2",
    "correct_score",
]
type RecommendationMode = Literal["single", "multiple"]
type RecommendationStrategy = Literal[
    "accuracy_first",
    "value_first",
    "upset_protection",
    "budget_constrained",
]
type RecommendationProbabilitySource = Literal["model", "calibrated"]


class RecommendationCandidate(BaseModel):
    fixture_id: str
    market_type: RecommendationMarketType
    outcome: str
    probability: float = Field(ge=0.0, le=1.0)
    model_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_source: RecommendationProbabilitySource = "model"
    decimal_odds: float | None = Field(default=None, gt=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    model_edge: float | None = None
    data_quality_score: float = Field(default=75.0, ge=0.0, le=100.0)
    model_confidence_score: float = Field(default=0.50, ge=0.0, le=1.0)
    calibration_score: float = Field(default=0.50, ge=0.0, le=1.0)
    upset_protection_score: float = Field(default=0.0, ge=0.0, le=1.0)
    odds_stability_score: float = Field(default=0.50, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    line: float | None = None
    side: str | None = None
    candidate_id: str | None = None
    model_version: str | None = None
    prediction_snapshot_id: int | None = Field(default=None, gt=0)
    prediction_time_utc: datetime | None = None
    kickoff_time_utc: datetime | None = None
    correlation_key: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)

    def normalized_kickoff_time_utc(self) -> datetime | None:
        if self.kickoff_time_utc is None:
            return None
        if self.kickoff_time_utc.tzinfo is None:
            return self.kickoff_time_utc.replace(tzinfo=UTC)
        return self.kickoff_time_utc.astimezone(UTC)

    def has_started(self, as_of_time_utc: datetime) -> bool:
        kickoff_time = self.normalized_kickoff_time_utc()
        if kickoff_time is None:
            return False
        if as_of_time_utc.tzinfo is None:
            normalized_as_of = as_of_time_utc.replace(tzinfo=UTC)
        else:
            normalized_as_of = as_of_time_utc.astimezone(UTC)
        return kickoff_time <= normalized_as_of

    def effective_market_probability(self) -> float | None:
        if self.market_probability is not None:
            return self.market_probability
        if self.decimal_odds is None:
            return None
        return 1.0 / self.decimal_odds

    def raw_model_probability(self) -> float:
        if self.model_probability is not None:
            return self.model_probability
        raw_probability = self.metadata_json.get("model_probability")
        if (
            self.probability_source == "calibrated"
            and isinstance(raw_probability, int | float)
            and not isinstance(raw_probability, bool)
        ):
            return float(raw_probability)
        return self.probability

    def effective_probability(self) -> float:
        if self.probability_source == "calibrated" and self.calibrated_probability is not None:
            return self.calibrated_probability
        return self.probability

    def effective_model_edge(self) -> float:
        if self.model_edge is not None:
            return self.model_edge
        market_probability = self.effective_market_probability()
        if market_probability is None:
            return 0.0
        return self.effective_probability() - market_probability

    def to_leg_selection(self) -> ParlayLegSelection:
        if self.decimal_odds is None:
            raise ValueError("decimal_odds is required for parlay leg selection")
        probability = self.effective_probability()
        return ParlayLegSelection(
            fixture_id=self.fixture_id,
            market_type=self.market_type,
            outcomes=[self.outcome],
            probabilities={self.outcome: probability},
            odds={self.outcome: self.decimal_odds},
            line=self.line,
            side=self.side,
            model_version=self.model_version,
            prediction_snapshot_id=self.prediction_snapshot_id,
            correlation_key=self.correlation_key,
            data_quality_score=self.data_quality_score,
        )


class RecommendationPolicyConfig(BaseModel):
    strategy: RecommendationStrategy = "accuracy_first"
    allowed_markets: tuple[RecommendationMarketType, ...] = (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
        "correct_score",
    )
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    min_data_quality_score_by_competition_id: dict[str, float] = Field(
        default_factory=dict
    )
    min_model_confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    min_calibration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    require_odds_for_parlay: bool = True
    data_quality_beta_lane_enabled: bool = False
    data_quality_beta_lane_competition_ids: tuple[str, ...] = ()
    data_quality_beta_lane_season_ids: tuple[str, ...] = ()
    data_quality_beta_lane_min_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    data_quality_beta_lane_max_competition_season_index: int | None = Field(
        default=None,
        ge=1,
    )
    data_quality_beta_lane_min_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    data_quality_beta_lane_max_decimal_odds: float | None = Field(default=None, gt=1.0)
    data_quality_beta_lane_min_model_edge: float | None = None
    data_quality_beta_lane_min_model_confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_min_calibration_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_min_odds_stability_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    data_quality_beta_lane_max_volatility_penalty: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    probability_weight: float = Field(default=0.35, ge=0.0)
    model_edge_weight: float = Field(default=0.20, ge=0.0)
    data_quality_weight: float = Field(default=0.15, ge=0.0)
    model_confidence_weight: float = Field(default=0.15, ge=0.0)
    calibration_weight: float = Field(default=0.10, ge=0.0)
    upset_protection_weight: float = Field(default=0.05, ge=0.0)
    upset_avoidance_penalty_weight: float = Field(default=0.14, ge=0.0)
    odds_stability_weight: float = Field(default=0.05, ge=0.0)
    volatility_penalty_weight: float = Field(default=0.10, ge=0.0)
    calibration_risk_penalty_weight: float = Field(default=0.12, ge=0.0)
    longshot_upset_penalty_weight: float = Field(default=0.16, ge=0.0)
    calibrated_upset_exposure_weight: float = Field(default=0.05, ge=0.0)
    upset_signal_calibration_penalty_weight: float = Field(default=0.12, ge=0.0)
    upset_exposure_min_probability: float = Field(default=0.18, ge=0.0, le=1.0)
    upset_exposure_min_calibration_score: float = Field(default=0.82, ge=0.0, le=1.0)
    upset_exposure_min_data_quality_score: float = Field(default=85.0, ge=0.0, le=100.0)
    upset_exposure_min_model_confidence_score: float = Field(default=0.78, ge=0.0, le=1.0)
    upset_exposure_min_odds_stability_score: float = Field(default=0.58, ge=0.0, le=1.0)
    upset_exposure_max_volatility_penalty: float = Field(default=0.12, ge=0.0, le=1.0)


class ScoredRecommendationCandidate(BaseModel):
    candidate: RecommendationCandidate
    score: float = Field(ge=0.0, le=1.0)
    component_scores: dict[str, float] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)


class RecommendationSelection(BaseModel):
    pass_type: str
    mode: RecommendationMode
    selected_candidates: list[ScoredRecommendationCandidate]
    evaluation: ParlayEvaluation
    total_score: float = Field(ge=0.0, le=1.0)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    excluded_candidate_count: int = Field(ge=0)
    explanation_json: dict[str, object] = Field(default_factory=dict)

    @property
    def fixture_ids(self) -> list[str]:
        fixture_ids: list[str] = []
        seen_fixture_ids: set[str] = set()
        for item in self.selected_candidates:
            if item.candidate.fixture_id in seen_fixture_ids:
                continue
            fixture_ids.append(item.candidate.fixture_id)
            seen_fixture_ids.add(item.candidate.fixture_id)
        return fixture_ids
