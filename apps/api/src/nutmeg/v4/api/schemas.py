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
    # V9 W3: per-request opt-in for observation recording. Both this AND
    # the server's NUTMEG_V4_OBSERVATION_DB env var must be set for a
    # session to actually land in the DB. Defaults to False so existing
    # callers don't accidentally start recording.
    record_session: bool = False


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


# ---------- /recommend/single (V8 W6) ----------

class SingleRecommendRequest(BaseModel):
    """POST /v4/recommend/single body — 单关 (single-leg) flow.

    Same fixture shape as /v4/recommend (one row per match). The server
    runs `recommend_singles` (V6 W9) against the V5 W12 default artifact
    + lottery rules, returns at most `top_per_match` recommendations per
    fixture sorted by EV desc.
    """
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1, max_length=50)
    bankroll: float = Field(1000.0, gt=0)
    top_per_match: int = Field(1, ge=1, le=3,
                                description="Max recommendations per fixture (default 1, max 3)")
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0,
                                       description="Per-ticket cap as fraction of bankroll")
    # V9 W3: see RecommendRequest.record_session
    record_session: bool = Field(False, description=
        "Opt-in observation recording. Requires NUTMEG_V4_OBSERVATION_DB "
        "env var on the server to actually persist.")


class SingleTicketResponse(BaseModel):
    match_id: str
    market_type: Literal["1x2", "handicap_1x2"]
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    ev_per_unit: float
    stake: float                  # ¥2-quantized
    raw_kelly_stake: float        # pre-quantization (diagnostic)
    expected_return: float


class SingleRecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    tickets: list[SingleTicketResponse]
    total_stake: float
    total_expected_return: float


# ---------- /recommend/pool (V8 W6) ----------

class PoolFixturePick(FixtureOddsInput):
    """Pool fixture row — same FixtureOddsInput shape plus a `pick` field.

    `pick` is the user's pre-decided outcome for that match, one of:
        "1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"
    Compound parlay then enumerates every C(M, N) ticket across those
    M picks.
    """
    pick: Literal["1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"]


class PoolRecommendRequest(BaseModel):
    """POST /v4/recommend/pool body — 复式 (M-select-N compound parlay)."""

    fixtures: list[PoolFixturePick] = Field(..., min_length=1, max_length=20)
    n: int = Field(..., ge=1, le=8,
                    description="Legs per ticket (1..8 per 竞彩 rules)")
    bankroll: float = Field(1000.0, gt=0)
    max_total_budget: Optional[float] = Field(None, gt=0,
                                               description="Optional pool-wide stake cap")
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction_per_ticket: float = Field(0.05, gt=0.0, le=1.0)
    # V9 W3: see RecommendRequest.record_session
    record_session: bool = Field(False, description=
        "Opt-in observation recording. Requires NUTMEG_V4_OBSERVATION_DB "
        "env var on the server to actually persist.")


class PoolLegResponse(BaseModel):
    """One leg of a pool ticket — like SelectionResponse but with the
    match_id + market_type baked in so the row is settleable.

    Post-V8 P1#5: previously PoolTicketResponse.legs used SelectionResponse
    which dropped match_id/market_type — the observation recorder couldn't
    write these rows in a settleable shape. PoolLegResponse closes that gap.
    """
    match_id: str
    market_type: Literal["1x2", "handicap_1x2"]
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    edge: float


class PoolTicketResponse(BaseModel):
    legs: list[PoolLegResponse]
    hit_probability: float
    combined_odds: float
    ev_per_unit: float
    stake: float                  # ¥2-quantized
    raw_kelly_stake: float
    expected_return: float


class PoolRecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    m: int                            # input pool size
    n: int                            # legs per ticket
    n_combinations: int               # = C(m, n)
    n_selected: int                   # tickets with stake > 0
    total_stake: float
    total_expected_return: float
    tickets: list[PoolTicketResponse]  # all enumerated, sorted by EV desc


# ---------- /today-recommendations (V10 W1 Track A) ----------

class TodayRecommendationsRequest(BaseModel):
    """POST /v4/today-recommendations body.

    V10 W1 Track A — the user-facing "land on the page and see
    recommendations" endpoint. Replaces the old engineer-facing flow
    that required the user to paste fixtures JSON.

    Server-side: fetches today's fixtures via api_football, runs the
    single + parlay recommend pipelines, returns a unified response.
    """

    date: Optional[str] = Field(None, description=
        "ISO YYYY-MM-DD; defaults to today (UTC).")
    leagues: list[str] = Field(
        default_factory=lambda: [
            # Top 5 European
            "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
            # Second-tier European
            "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
            "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
            # Other major European
            "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA", "BEL_PRO_LEAGUE",
            # Asia
            "JPN_J1",
        ],
        description=(
            "V4 canonical league codes (default: all 13 trained leagues). "
            "post-V11 audit (2026-05-25): expanded from EPL+La Liga to "
            "match the production model's full training coverage."
        ),
    )
    bankroll: float = Field(1000.0, gt=0,
        description="Total bankroll. Default ¥1000.")
    include: list[Literal["single", "parlay"]] = Field(
        default_factory=lambda: ["single", "parlay"],
        description="Which game types to include. Pool deferred to W2.",
    )
    # carry-over from RecommendRequest for advanced overrides
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    record_session: bool = Field(False, description=
        "Opt-in observation recording (see RecommendRequest.record_session).")


class TodaySummary(BaseModel):
    """Aggregated stats across all recommendation types."""
    total_recs: int
    total_stake: float
    weighted_ev: Optional[float] = Field(None, description=
        "Stake-weighted average EV. None if total_stake == 0.")


class TodayRecommendationsResponse(BaseModel):
    """Unified response for the V10 landing flow.

    Each game-type field is None when:
      (a) excluded via request.include, OR
      (b) the underlying engine returned 0 recommendations.

    `fixtures_fetched` reports how many fixtures the server pulled
    for the date+leagues (regardless of whether they passed the EV gate).
    """
    generated_at_utc: str
    date: str
    leagues: list[str]
    bankroll: float
    fixtures_fetched: int
    single: Optional[SingleRecommendResponse] = None
    parlay: Optional[RecommendResponse] = None
    summary: TodaySummary


# ---------- /predictions/wc (V10 W1 Track B Day 5) ----------

class WcMatchPrediction(BaseModel):
    """One WC fixture's predicted 1X2 probabilities + diagnostics.

    Mirrors the JSON shape that `nutmeg-wc-predict` CLI outputs per
    fixture. `source` is "blend(α=0.4)" when Pinnacle was available,
    "lightgbm_only" when only the model contributed.
    """
    fixture_id: int
    kickoff_utc: str
    round: Optional[str] = None
    home_team: str
    away_team: str
    home_elo: float
    away_elo: float
    elo_diff: float
    home_adv: float
    has_pinnacle: bool
    psc_home: Optional[float] = None
    psc_draw: Optional[float] = None
    psc_away: Optional[float] = None
    p_home: float
    p_draw: float
    p_away: float
    # Pure-Elo baseline for transparency (always populated)
    p_home_elo_only: float
    p_draw_elo_only: float
    p_away_elo_only: float
    source: str


class WcPredictionsResponse(BaseModel):
    """Wraps `nutmeg-wc-predict` output for the dashboard."""
    date: str
    season: int
    n_fixtures: int
    blend_alpha: float
    elo_snapshot: Optional[str] = None
    host_country_hint: dict[str, float] = Field(default_factory=dict)
    predictions: list[WcMatchPrediction]
    generated_at_utc: str


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
