"""Pydantic schemas for v4 API request/response.

These are the EXTERNAL contract — any change here is a breaking API change.
Internal data classes (MatchInput, Selection, Parlay) are separate and
can evolve freely.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- Request body ----------

class FixtureOddsInput(BaseModel):
    """One match in a daily recommendation request."""
    date: date
    league: str = Field(..., description="Canonical league code, e.g. 'EPL', 'ESP_LA_LIGA'")
    home_team: str = Field(..., description="Must match training-set team spelling")
    away_team: str

    # Required: model needs these to construct market features
    psc_home: float = Field(..., gt=1.0, description="Pinnacle (or sharp) closing 1X2 home odds")
    psc_draw: float = Field(..., gt=1.0)
    psc_away: float = Field(..., gt=1.0)

    # Lottery odds (what the player actually bets at). Default to Pinnacle if absent.
    odds_1x2_H: Optional[float] = Field(None, gt=1.0)
    odds_1x2_D: Optional[float] = Field(None, gt=1.0)
    odds_1x2_A: Optional[float] = Field(None, gt=1.0)

    # China integer handicap
    handicap_home: Optional[int] = Field(None, ge=-5, le=5, description="China integer handicap")
    odds_handicap_H: Optional[float] = Field(None, gt=1.0)
    odds_handicap_D: Optional[float] = Field(None, gt=1.0)
    odds_handicap_A: Optional[float] = Field(None, gt=1.0)

    # Optional extra market signals (features only, never bet)
    psc_over25: Optional[float] = Field(None, gt=1.0)
    psc_under25: Optional[float] = Field(None, gt=1.0)
    ahch: Optional[float] = Field(None, description="European Asian handicap closing line")


class RecommendRequest(BaseModel):
    """POST /v4/recommend body."""
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1, max_length=50)
    bankroll: float = Field(1000.0, gt=0)
    top_n: int = Field(10, ge=1, le=50)
    k_min: int = Field(2, ge=2, le=8)
    k_max: int = Field(8, ge=2, le=8)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0)
    include_compound: bool = Field(False, description="Enumerate 复式 legs")
    # V5 W11: optional snapshot_phase carried through to observation recorder
    # when --record-to / X-Record-DB is set on the server. Values come from
    # SNAPSHOT_PHASES in nutmeg.v4.observation.store; defaults to "closing"
    # (legacy V4 behavior).
    snapshot_phase: Literal["pre_close", "closing", "post_close"] = "closing"


# ---------- Response body ----------

class SinglePrediction(BaseModel):
    home_team: str
    away_team: str
    league: str
    date: date
    lambda_home: float
    lambda_away: float
    p_home_1x2: float
    p_draw_1x2: float
    p_away_1x2: float
    # Optional handicap probs (present only when handicap_home was provided)
    handicap_home: Optional[int] = None
    p_home_handicap: Optional[float] = None
    p_draw_handicap: Optional[float] = None
    p_away_handicap: Optional[float] = None


class SelectionResponse(BaseModel):
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    edge: float


class LegResponse(BaseModel):
    match_id: str
    market_type: Literal["1x2", "handicap_1x2"]
    selections: list[SelectionResponse]


class RecommendationResponse(BaseModel):
    rank: int
    k_legs: int = Field(..., ge=2, le=8)
    is_compound: bool
    stake_units: int
    kelly_recommended_stake: float
    kelly_capped_fraction: float
    expected_return: float
    hit_probability: float
    ev_per_unit: float
    log_growth: float
    legs: list[LegResponse]


class ModelInfo(BaseModel):
    trained_at_utc: Optional[str] = None
    training_cutoff: Optional[str] = None
    n_train: Optional[int] = None
    gbm_rho: Optional[float] = None
    temperature_T: Optional[float] = None
    # V5 W7 + W11: backend identity so callers (dashboard, observation recorder)
    # can label data with which artifact produced it.
    model_type: Optional[str] = "lightgbm"
    cat_features: Optional[list[str]] = None


class RecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    single_match_predictions: list[SinglePrediction]
    recommendations: list[RecommendationResponse]


# ---------- Health ----------

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    artifact_loaded: bool
    artifact_path: Optional[str] = None
    trained_at_utc: Optional[str] = None
    training_cutoff: Optional[str] = None
    n_teams: Optional[int] = None
    n_leagues: Optional[int] = None
    # V5 W11: surface the active backend in health so dashboards can show
    # whether the running server is on `lightgbm` (V4 default) or `catboost`
    # (W7 opt-in).
    model_type: Optional[str] = "lightgbm"
    detail: Optional[str] = None


# ---------- /predictions/upcoming (V5 W11) ----------

class UpcomingPredictionsRequest(BaseModel):
    """Lightweight body for the predictions/upcoming endpoint.

    Same shape as RecommendRequest but without bankroll / Kelly knobs —
    callers (dashboard, scheduled cron, mobile app) just want the model's
    probability output, not parlay recommendations.
    """

    fixtures: list[FixtureOddsInput]


class UpcomingPredictionsResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    n_fixtures: int
    predictions: list[SinglePrediction]


# ---------- /rules (V6 W10) ----------

class LotteryRulesResponse(BaseModel):
    """Snapshot of the currently active LotteryRules.

    Returned by GET /api/v4/rules so the dashboard / external tools can
    surface accurate, in-sync rule constants (¥2 unit, ¥20k cap, 31.5%
    vig, 5% EV threshold) without hard-coding them client-side. Changes
    in `combo.lottery_rules.JINGCAI_DEFAULT` propagate automatically.
    """

    stake_unit: float = Field(..., description="最小投注单位 (¥)")
    max_ticket_stake: float = Field(..., description="单注最高金额 (¥)")
    max_period_stake: float = Field(..., description="单期累计上限 (¥)")
    min_parlay_legs: int = Field(..., description="混合过关最少串关数")
    max_legs_per_ticket: int = Field(..., description="混合过关最多串关数")
    payout_ratio: float = Field(..., description="平均派奖率 (e.g. 0.685)")
    vig: float = Field(..., description="庄家抽水率 = 1 - payout_ratio")
    min_ev_per_unit: float = Field(..., description="推荐门槛: 单位投注最小 EV")
    min_hit_probability: float = Field(..., description="推荐门槛: 最小命中率")
    label: str = Field(default="中国体彩 · 竞彩足球",
                       description="规则集名称 (供 UI 展示)")
