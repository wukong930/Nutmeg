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
    # V12 W4 — ISO kickoff time (with tz) from the odds cache, threaded through
    # to SinglePrediction so the 近期赛事 cards can show + sort by time.
    kickoff_utc: str | None = None

    # Required: model needs these to construct market features
    psc_home: float = Field(..., gt=1.0, description="Pinnacle (or sharp) closing 1X2 home odds")
    psc_draw: float = Field(..., gt=1.0)
    psc_away: float = Field(..., gt=1.0)

    # 竞彩 lottery odds (what the player actually bets at). If absent, the
    # outcome is NOT bettable — do NOT substitute Pinnacle (psc_*). Pinnacle is
    # the sharp benchmark, not a betting venue; EV against it is model-vs-sharp
    # noise (the EV-vs-Pinnacle bug). Selection builders raise when these are
    # missing (audit B2/D3; was previously "Default to Pinnacle if absent").
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
    # V14 — Asian total line the psc_over25/under25 are quoted AT (often 2.25 for
    # J1, not 2.5). Lets the 竞彩盘 anchor the market-reverse λ for cup/J1 to the
    # real line instead of assuming 2.5. None → server defaults 2.5.
    ou_line: Optional[float] = Field(None, gt=0.0)
    ahch: Optional[float] = Field(None, description="European Asian handicap closing line")
    # V14 — real Pinnacle Asian Handicap board as a JSON string ({line: {home,
    # away}}); the server de-vigs it for the 让球胜平负 prediction (DC fallback
    # when absent). JSON-encoded so it survives the pandas/pydantic round-trip.
    asian_handicap: Optional[str] = None


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

class HandicapLineProb(BaseModel):
    """V12 W3 — model P(让胜/让平/让负) for one integer handicap line,
    derived from the same Dixon-Coles score grid. The 竞彩 SP calculator
    looks up the line matching the user's 竞彩 让球线 and computes live EV
    client-side (no server round-trip)."""
    line: int  # handicap_home: −1 = 主队让1球, +1 = 主队受让1球
    p_home: float
    p_draw: float
    p_away: float


class AsianHandicapLineProb(BaseModel):
    """V14 — INTERNATIONAL Asian Handicap (half-line, 2-way: cover / not, NO
    push). Distinct from HandicapLineProb (竞彩 integer 3-way). ``line`` is the
    home handicap (−0.5 = 主队让半球 ⇒ home must win; +1.5 = 主受让1.5 …).
    ``source`` = ``"mkt"`` when de-vigged from a real Pinnacle AH quote, ``"dc"``
    when read off the Dixon-Coles grid (fallback). For the 让球胜平负 prediction
    display (国际盘 + 市场模式), for future Polymarket comparison."""
    line: float
    p_home: float   # P(home covers)
    p_away: float   # P(away covers) = 1 − p_home (half-line, no push)
    source: str = "dc"


class ScoreCell(BaseModel):
    """One exact scoreline (home:away) with its probability."""
    home: int
    away: int
    p: float


class MarginBand(BaseModel):
    """V14 — one goal-margin (home−away) band for the 净胜球分组 READ tool.

    A readout of the same Dixon-Coles grid — NOT a new signal (a 1500-fixture
    eval showed feeding the Asian Handicap INTO the λ fit adds ~0 info: the grid
    already reproduces the AH curve to ~1.5pp). It helps pick a coherent CLUSTER
    of scorelines given the 让球 line. ``margin`` is signed home−away; ``is_tail``
    flags the folded ±N+ buckets; ``scores`` are the top exact scorelines in it."""
    margin: int
    is_tail: bool
    p: float
    scores: list[ScoreCell] = Field(default_factory=list)


class SinglePrediction(BaseModel):
    home_team: str
    away_team: str
    league: str
    date: date
    # V12 W4 — ISO kickoff time (with tz) when known, so the 近期赛事 cards can
    # show date+time and sort chronologically within a league. Optional: the
    # odds cache row may omit it; the client falls back to `date`.
    kickoff_utc: str | None = None
    lambda_home: float
    lambda_away: float
    p_home_1x2: float
    p_draw_1x2: float
    p_away_1x2: float
    # V12 W3 — Pinnacle closing odds echoed back so the dashboard's 竞彩 SP
    # calculator can pre-fill inputs and show the 竞彩-vs-Pinnacle soft-line
    # gap. Optional: not every prediction path carries them (e.g. WC).
    psc_home: float | None = None
    psc_draw: float | None = None
    psc_away: float | None = None
    # V12 W8 — Pinnacle over/under 2.5 echo, present in 市场模式. The dashboard
    # sends these back to /recommend/market-handicap so the server recomputes
    # the market-implied 让球 P (double-anchored on 1X2 + O/U) authoritatively
    # before recording — no trusting a client-sent probability.
    psc_over25: float | None = None
    psc_under25: float | None = None
    # V14 — when API-Football last refreshed this Pinnacle snapshot (ISO). The
    # 市场模式 card shows the age so a stale de-vig prior isn't trusted near
    # kickoff (API-Football mirrors Pinnacle only every few hours).
    odds_update: str | None = None
    # Optional handicap probs (present only when handicap_home was provided)
    handicap_home: Optional[int] = None
    p_home_handicap: Optional[float] = None
    p_draw_handicap: Optional[float] = None
    p_away_handicap: Optional[float] = None
    # V12 W3 — model handicap P across integer lines (−3..+3) so the 竞彩 SP
    # calculator computes live 让球 EV for any 竞彩 让球线 without a round-trip.
    # Empty when not computed (e.g. WC predictions).
    handicap_lines: list[HandicapLineProb] = Field(default_factory=list)
    # V14 — INTERNATIONAL Asian Handicap (half-line, 2-way) for the 让球胜平负
    # PREDICTION: real Pinnacle AH de-vig where quoted, DC-grid cover-prob
    # fallback otherwise. NOT the 竞彩 integer market (that's handicap_lines).
    asian_handicap_lines: list[AsianHandicapLineProb] = Field(default_factory=list)
    # V12 W7 — 杯赛市场模式: when True, p_*_1x2 are NOT model output — they are
    # the Pinnacle de-vig fair probabilities (the model is out-of-distribution
    # for cups, so we lean 100% on the sharp market). lambda_* are 0. The UI
    # labels these "市场模式·Pinnacle 公允价".
    # V12 W8 — handicap_lines ARE now populated for market mode too: a
    # Dixon-Coles goal grid reverse-fitted to the de-vig 1X2 + Pinnacle O/U
    # gives market-implied 让球 P (validated vs Pinnacle's own AH ~1pp). So the
    # market-mode card prices 竞彩 让球 SP live, not just 胜平负.
    market_mode: bool = False
    # V14 — sharp-flip guard: True when Pinnacle's de-vig favourite DISAGREES
    # with the other sharp books (Betfair + SBOBET) in the SAME /odds envelope.
    # Empirically Pinnacle's line is much worse on these (~10pp hit-rate drop,
    # log-loss 1.07 vs 0.97), so the card downgrades the EV reliability tag to
    # ⚠️ "sharp 分歧" — our Pinnacle-based EV is built on a suspect line there.
    sharp_flip: bool = False
    # V14 — 净胜球分组 (goal-margin bands): same DC grid, grouped by margin with
    # the top scorelines per band, so the card can show a coherent score CLUSTER
    # for the chosen 让球 line. READOUT, not a +EV signal (AH-into-fit was a wash).
    margin_bands: list[MarginBand] = Field(default_factory=list)


class PendingFixture(BaseModel):
    """V12 W6 — an upcoming fixture whose Pinnacle 1X2 line has NOT opened yet.

    The model treats Pinnacle (psc) as a STRONG feature — empirically, without
    it the served λ/P shifts materially (the favorite can flip), so a psc-free
    probability would be unreliable. Rather than surface a misleading P/EV, the
    近期赛事 tab lists these as '待开盘' cards so the user still sees the full
    slate; each is auto-promoted into `predictions` (full calc) once Pinnacle
    opens that line."""
    home_team: str
    away_team: str
    league: str
    date: date
    kickoff_utc: str | None = None
    reason: str = "pinnacle_not_open"


class SpCalcResponse(BaseModel):
    """V12 W3 — data for the 近期赛事 tab's 竞彩 SP calculator: model output
    for every fixture across a multi-day window (default 3 days). Each
    prediction carries 1X2 P + Pinnacle odds + handicap-line P so the client
    computes live 竞彩 EV. Separate from /today-recommendations (the auto
    'best recommendation' surface), to avoid mixing the two."""
    generated_at_utc: str
    date_start: str
    date_end: str
    days: int
    fixtures_fetched: int
    predictions: list[SinglePrediction] = Field(default_factory=list)
    # V12 W6 — upcoming fixtures with no Pinnacle line yet (model P would be
    # unreliable without its psc feature). Listed as 待开盘 in the UI, NOT
    # scored. Auto-promoted to `predictions` once Pinnacle opens that line.
    pending_fixtures: list[PendingFixture] = Field(default_factory=list)


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
    # V11 P1-FE#5 — deterministic fingerprint of the picks (sorted
    # match_id+market+outcome tuples). Frontend uses this to detect
    # "this specific recommendation's picks changed" so it can render
    # an "已更新" badge next to it. Computed server-side.
    selection_fingerprint: str | None = Field(None, description=
        "12-char SHA1 prefix of sorted (match_id, market_type, outcome) tuples")


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
    # V11 P1-FE#5 — top-level version hash for parlay output.
    version_hash: str | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


# ---------- /v4/recommend/parlay (V12 W5 — hand-picked 串关) ----------

class ParlayLegInput(BaseModel):
    """One hand-picked leg of a 竞彩 parlay, from the 近期赛事 calculator.

    Carries the fixture identity (so the server can recompute the model P and
    the leg is settleable) + the user's pick + the 竞彩 SP for this leg.
    """
    date: date
    league: str
    home_team: str
    away_team: str
    kickoff_utc: str | None = None
    market_type: Literal["1x2", "handicap"] = "1x2"
    outcome: Literal["H", "D", "A"]
    # Required when market_type == "handicap" (China integer handicap line).
    handicap_home: int | None = Field(None, ge=-5, le=5)
    # The 竞彩 SP the user is betting this leg into.
    sp: float = Field(..., gt=1.0, description="竞彩 SP for this leg")
    # Pinnacle closing odds (a model feature; the 近期赛事 cards carry these).
    # Fall back to `sp` server-side if absent so the leg can still be scored.
    psc_home: float | None = Field(None, gt=1.0)
    psc_draw: float | None = Field(None, gt=1.0)
    psc_away: float | None = Field(None, gt=1.0)


class ParlayLegEcho(BaseModel):
    """Server-recomputed view of one leg (model P is authoritative)."""
    match_id: str
    league: str
    market_type: str
    outcome: str
    handicap_home: int | None = None
    sp: float
    model_p: float


class ParlayRecordRequest(BaseModel):
    """V12 W5 — compute (and optionally record) a HAND-PICKED 竞彩 串关.

    Unlike /recommend (engine auto-generates combos), this scores the exact
    legs the user selected: server recomputes each leg's model P → parlay hit
    P = ∏P, parlay odds = ∏ 竞彩 SP, EV, fractional Kelly stake (same kelly.py
    + lottery_rules pipeline as 单关/复式 so stakes are consistent). Distinct
    matches only; 2–8 legs (混合过关).
    """
    legs: list[ParlayLegInput] = Field(..., min_length=2, max_length=8)
    bankroll: float = Field(..., gt=0)
    kelly_fraction: float = Field(0.25, ge=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0)
    record_session: bool = False


class ParlayRecordResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    legs: list[ParlayLegEcho]
    k_legs: int
    hit_probability: float       # ∏ model_p
    odds: float                  # ∏ sp (竞彩 parlay payout multiplier)
    ev_per_unit: float           # hit_probability * odds - 1
    raw_kelly_stake: float       # pre-quantization
    stake: float                 # ¥2-quantized, ticket-capped
    passes_gate: bool            # meets JINGCAI thresholds (hit% + EV)
    recorded: bool
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False
    # Per-leg full predictions (match identity + 1X2 P + handicap_home for the
    # picked line). Recorded into single_predictions so V4 settlement can
    # bridge each leg's match_id → match_outcome (it keys off this table).
    single_match_predictions: list[SinglePrediction] = Field(default_factory=list)


class ManualBetRequest(BaseModel):
    """Post-V13 — record ONE user-chosen bet ("记此注").

    Records EXACTLY the outcome + real stake the user placed (NOT the model's
    best pick), INCLUDING −EV — the observation DB is the user's real betting
    history so ROI is honest. Settlement-compatible (see record_manual_bet).
    """
    league: str
    date: str
    home_team: str
    away_team: str
    market_type: Literal["1x2", "handicap"] = "1x2"
    handicap_home: int | None = None
    outcome: Literal["H", "D", "A"]
    odds: float = Field(..., gt=1.0)             # the 竞彩 SP for the picked outcome
    probability: float = Field(0.0, ge=0.0, le=1.0)  # model P (for EV display)
    stake: float = Field(..., gt=0.0)            # real money the user bet
    bankroll: float = Field(1000.0, gt=0)
    record_session: bool = False


class ManualBetResponse(BaseModel):
    recorded: bool
    ev: float
    outcome: str
    stake: float
    session_id: int | None = None


class JingcaiRecommendRequest(BaseModel):
    """V12 W5 — 竞彩盘口推荐: run single + parlay + pool over the fixtures the
    user filled with 竞彩 SP (+ 让球) in 近期赛事.

    Same engine as /today-recommendations, but each fixture's ``odds_1x2`` /
    ``odds_handicap_*`` (= the 竞彩 SP the user typed) drive the EV instead of
    Pinnacle. Model P still uses psc (Pinnacle) as a feature. The caller should
    only include fixtures it actually filled 竞彩 odds for — fixtures missing
    ``odds_1x2`` would fall back to Pinnacle inside the engine, which is NOT the
    竞彩 frame. Returns a TodayRecommendationsResponse (the 💴 竞彩 board)."""
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1)
    bankroll: float = Field(1000.0, gt=0)
    include: list[Literal["single", "parlay", "pool"]] = Field(
        default_factory=lambda: ["single", "parlay", "pool"])
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    min_ev: float = Field(0.05, ge=-0.20, le=0.50)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    pool_n: int = Field(3, ge=2, le=8)
    record_session: bool = False


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
    # V12 W7 — match identity so the 今日推荐 single board renders
    # "home vs away · league · date" directly (it reads these fields, unlike
    # the parlay/history renderers which parse match_id). Without them the
    # card showed "VS · undefined · undefined". Optional for back-compat.
    league: str | None = None
    date: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    market_type: Literal["1x2", "handicap_1x2"]
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    ev_per_unit: float
    stake: float                  # ¥2-quantized
    raw_kelly_stake: float        # pre-quantization (diagnostic)
    expected_return: float
    # V12 W8i — Pinnacle inputs echoed so the 今日推荐 card can record THIS pick
    # at the user's 竞彩 SP. The record endpoints recompute model P from these
    # (server never trusts a client-sent P); psc_over/under + handicap_home let
    # a 让球 pick re-derive its grid via /recommend/market-handicap. All optional
    # for back-compat (None when the source fixture lacked them).
    psc_home: float | None = None
    psc_draw: float | None = None
    psc_away: float | None = None
    psc_over25: float | None = None
    psc_under25: float | None = None
    handicap_home: int | None = None
    # V14 — market-reverse 让球 board (−3..+3) carried onto the prediction ticket
    # so the 今日推荐 boards can show a 让球胜平负 prediction with a line selector
    # (non-竞彩 / Pinnacle-de-vig handicap rule). Same shape the cup-market preds use.
    handicap_lines: list[HandicapLineProb] = Field(default_factory=list)
    # V14 — international Asian Handicap (half-line, 2-way) board for the 让球
    # PREDICTION display. Real Pinnacle de-vig where quoted, DC fallback else.
    asian_handicap_lines: list[AsianHandicapLineProb] = Field(default_factory=list)
    # V11 P1-FE#5 — per-ticket fingerprint (12 chars). One single
    # ticket = a single (match_id, market, outcome) triple, so the
    # fingerprint identifies exactly that pick.
    selection_fingerprint: str | None = None


class SingleRecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    tickets: list[SingleTicketResponse]
    total_stake: float
    total_expected_return: float
    # V11 P1-FE#5 — same versioning treatment as parlays/pool.
    version_hash: str | None = Field(None, description=
        "12-char SHA1 prefix covering this response's picks. Frontend compares "
        "to its last-seen hash to detect when recs need a refresh.")
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


# ---------- /recommend/market-handicap (V12 W8 — 市场模式让球追踪) ----------

class MarketHandicapRequest(BaseModel):
    """POST /v4/recommend/market-handicap — record one 市场模式 让球 pick (J1 /
    cup) for tracking.

    The server RECOMPUTES the market-implied 让球 P from the Pinnacle inputs
    (de-vig 1X2 + O/U at ``ou_line``) — it never trusts a client-sent
    probability. For each outcome carrying a 竞彩 SP it computes EV, picks the
    highest-EV leg, and (when record_session=True AND the server DB gate is on)
    records it tagged model_type=market_handicap so AB/ROI reports slice it
    apart from model bets."""
    league: str
    date: date
    home_team: str
    away_team: str
    psc_home: float
    psc_draw: float
    psc_away: float
    psc_over25: float | None = None
    psc_under25: float | None = None
    # Asian total line the over/under prices are quoted AT. Pinnacle's main J1
    # total is often a quarter line (2.25 / 2.75), not 2.5; the server anchors
    # λ_total to THIS line (push counted as half). Treating a 2.25 line as 2.5
    # biases λ_total ~+0.22 goals. Default 2.5 keeps existing callers unchanged;
    # the over/under value is simply the price at ou_line.
    ou_line: float = Field(2.5, gt=0.0)
    handicap_home: int
    odds_handicap_H: float | None = None
    odds_handicap_D: float | None = None
    odds_handicap_A: float | None = None
    bankroll: float = 1000.0
    kelly_fraction: float = 0.25
    record_session: bool = False


class MarketHandicapResponse(BaseModel):
    league: str
    date: date
    home_team: str
    away_team: str
    handicap_home: int
    # market-implied P(让胜/让平/让负) for this line, order [H, D, A]
    market_implied_p: list[float]
    fair_odds: list[float]
    # EV/unit vs the supplied 竞彩 SP; None for outcomes with no SP given
    ev_per_unit: list[float | None]
    best_outcome: str | None = None  # "H"|"D"|"A" — highest-EV leg with a SP
    best_ev: float | None = None
    best_stake: float | None = None
    recorded: bool = False
    session_id: int | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False
    # V14 — 净胜球分组 for the reverse-calc card (same grid, READ tool not signal)
    margin_bands: list[MarginBand] = Field(default_factory=list)


class MarketRepriceRequest(BaseModel):
    """V14 — POST /v4/recommend/market-reprice. Re-price ONE 市场模式 card from
    a LIVE Pinnacle line the user typed by hand (API-Football mirrors Pinnacle
    only every few hours, so the auto-fed line can trail Pinnacle.com near
    kickoff). Pure compute: de-vig the 1X2 + reverse-fit the 让球 board exactly
    as the auto card does — NO recording, NO DB. The dashboard then swaps these
    P's into the card so display / 让球线 selector / EV / 📌 all use the live
    line. Reuses the validated implied_handicap_lines path (not a JS re-impl)."""
    psc_home: float
    psc_draw: float
    psc_away: float
    psc_over25: float | None = None
    psc_under25: float | None = None
    ou_line: float = Field(2.5, gt=0.0)


class MarketRepriceResponse(BaseModel):
    # de-vig fair 1X2 (multiplicative), order [home, draw, away]
    p_home_1x2: float
    p_draw_1x2: float
    p_away_1x2: float
    # market-implied 让球 board across integer lines (same shape the card holds)
    handicap_lines: list[HandicapLineProb]
    # 1X2 overround the user's typed odds imply — a sanity check the dashboard
    # surfaces so a fat-finger (e.g. swapped 主/客) shows an off vig.
    overround: float


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
    # V11 P1-FE#5 — per-ticket fingerprint over its leg set.
    selection_fingerprint: str | None = None


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
    # V11 P1-FE#5 — top-level pool version hash.
    version_hash: str | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


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
            # V12 W7 — JPN_J1 removed from the MODEL-scored board: it's
            # out-of-distribution (European-trained model; ~13pp off the sharp
            # J1 line). J1 is now served via market mode (Pinnacle de-vig).
        ],
        description=(
            "V4 canonical league codes (default: all 13 trained leagues). "
            "post-V11 audit (2026-05-25): expanded from EPL+La Liga to "
            "match the production model's full training coverage."
        ),
    )
    bankroll: float = Field(1000.0, gt=0,
        description="Total bankroll. Default ¥1000.")
    include: list[Literal["single", "parlay", "pool", "wc"]] = Field(
        default_factory=lambda: ["single", "parlay", "pool", "wc"],
        description=(
            "Which game types to include. V11 P1-FE#4: pool added; "
            "V11 post-ship: 'wc' added — when on a date with WC fixtures, "
            "surfaces today's WC 1X2 predictions as a side block "
            "(no auto-handicap; user enters SP in the WC tab to get 让球 "
            "recommendations). 'wc' is informational only — it doesn't "
            "contribute to total_recs / total_stake / weighted_ev."
        ),
    )
    # V11 P1-FE#4 — UI-facing risk + EV sliders. risk_preference is the
    # high-level dial; it maps to a kelly_fraction (0.15 / 0.25 / 0.40).
    # min_ev is the EV gate; recommendations below this are dropped.
    risk_preference: Literal["conservative", "balanced", "aggressive"] = Field(
        "balanced",
        description=(
            "User-facing risk dial. Maps to internal Kelly fraction: "
            "保守=0.15, 中=0.25, 激进=0.40. Explicit `kelly_fraction` "
            "overrides this when set non-default."
        ),
    )
    min_ev: float = Field(
        0.05,
        ge=-0.20,
        le=0.50,
        description=(
            "Minimum EV-per-unit threshold; recommendations with "
            "ev < min_ev are dropped. Default +5% matches the original "
            "JINGCAI_DEFAULT.min_ev_per_unit. UI offers -5% / 0% / +5% / +10%."
        ),
    )
    # carry-over from RecommendRequest for advanced overrides
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    record_session: bool = Field(False, description=
        "Opt-in observation recording (see RecommendRequest.record_session).")
    # V12 W3 — on-demand fresh-odds pull. Normal polls read the cron-cached
    # Pinnacle odds (cheap). When the 竞彩 SP calculator's 🔄 刷新盘口 button
    # is pressed, the client sets this True so the server re-fetches odds
    # live (refresh_odds=True in _gather_rows) — capturing near-kickoff
    # Pinnacle for the model's market feature. A handful of calls per press;
    # well within the daily budget. Fixtures stay cached (only odds drift).
    refresh_odds: bool = Field(False, description=
        "Bypass the odds cache and pull live Pinnacle odds for this request.")
    # V11 P1-FE#4 — pool sizing (when "pool" in include)
    pool_n: int = Field(
        3,
        ge=2,
        le=8,
        description=(
            "N legs per pool ticket (M-select-N). Default 3 (most popular). "
            "Pool generation only runs when at least N matches pass the EV gate."
        ),
    )
    # V11 P1-FE#5 — when set, the server compares the new response's
    # version_hash against this one; if different, it includes a `diff`
    # field describing which picks changed. The frontend supplies its
    # last-known hash via this param.
    prev_version: str | None = Field(
        None,
        description=(
            "Caller's last-known version_hash. When provided and the new "
            "hash differs, the response carries a `diff` block (added "
            "fingerprints / removed fingerprints / odds_changed flag)."
        ),
        min_length=8,
        max_length=64,
    )


class TodaySummary(BaseModel):
    """Aggregated stats across all recommendation types."""
    total_recs: int
    total_stake: float
    weighted_ev: Optional[float] = Field(None, description=
        "Stake-weighted average EV. None if total_stake == 0.")


class PlayoffWarning(BaseModel):
    """V12 W0 — one fixture flagged as likely playoff/barrage context.

    The model has no playoff feature; SP buyers (Pinnacle sharps) do
    price-adjust but we can't decompose vig. Dashboard renders these as
    a ⚠️ banner so the user knows model output is uncalibrated for
    end-of-season high-stakes fixtures.
    """
    league: str = Field(..., description="V4 canonical league code, e.g. FRA_LIGUE_1")
    home_team: str
    away_team: str
    date: str = Field(..., description="ISO YYYY-MM-DD")
    context: str = Field(..., description=(
        "Short human-readable label, e.g. 'Ligue 1 barrage de relegation'."
    ))
    model_bias_note: str = Field(..., description=(
        "Why the model is wrong-for-this-context — surfaced in banner tooltip."
    ))


class TodayRecommendationsDiff(BaseModel):
    """V11 P1-FE#5 — describes what changed vs the caller's prev_version.

    The frontend uses this to:
      - Show "推荐已更新" banner with a short summary
      - Add a 已更新 badge next to each rec whose selection_fingerprint
        is in `added_fingerprints` but not in the caller's prior set

    All lists are sorted for stable diffs.
    """
    prev_version: str = Field(..., description="echoed from the request")
    current_version: str
    odds_changed: bool = Field(False, description=
        "True when the fixture odds digest differs even though picks are stable.")
    # Selection fingerprints present in the current response but NOT in
    # the caller's previous one (i.e. newly recommended picks).
    added_fingerprints: list[str] = Field(default_factory=list)
    # Fingerprints that were in prev but no longer present (picks dropped).
    removed_fingerprints: list[str] = Field(default_factory=list)
    # Human-readable summary for the banner — server-generated so zh/en
    # is consistent regardless of locale toggle state.
    summary: str = Field(..., description=
        "One-line summary, e.g. '2 picks changed' / 'odds moved on 1 leg'")


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
    # V11 P1-FE#4 — third option in the today landing tab.
    # Strategy B (locked 2026-05-25): filter fixtures to ev_per_unit ≥ min_ev,
    # pick max-EV market per match, generate C(M, N) pool of N-selections.
    pool: Optional[PoolRecommendResponse] = None
    # V11 post-ship — WC 1X2 model predictions for the same date.
    # Surfaced informationally; doesn't contribute to total_recs/stake/ev
    # (no handicap → no EV computation possible until user enters SP in the
    # WC tab). Frontend renders this as a "🏆 WC 板块" with a CTA that
    # deep-links to the WC tab. None when no WC fixtures or "wc" excluded.
    wc: Optional[WcPredictionsResponse] = None
    summary: TodaySummary
    # V11 P1-FE#5 — top-level version hash covering single + parlay + pool
    # picks + the fixture odds digest. Frontend polls every 30s and shows
    # a "推荐已更新" banner when this changes.
    version_hash: str | None = Field(None, description=
        "12-char SHA1 prefix. Stable as long as picks and odds don't change.")
    # When the client passes `prev_version` and the hash differs, the
    # server fills in a diff describing what changed (per-rec changed
    # selection_fingerprints + odds_changed flag).
    diff: Optional["TodayRecommendationsDiff"] = None
    # V12 W0 (2026-05-27) — fixtures detected as falling within a known
    # playoff / barrage / end-of-season high-stakes window. Model has no
    # feature for this; banner alerts the user. See data/playoff_context.py.
    # Empty list when no fixtures hit a window — banner stays hidden.
    playoff_warnings: list[PlayoffWarning] = Field(
        default_factory=list,
        description=(
            "Fixtures in a known playoff/barrage date window. Coarse "
            "hard-coded heuristic — V13 P1 will replace with a real "
            "training feature."
        ),
    )
    # V12 W3 — model P(H/D/A) + Pinnacle odds for EVERY fetched fixture
    # (not just the gate-passing ones in `single`), so the dashboard's
    # 竞彩 SP calculator can compute live EV against user-entered 竞彩 SP.
    # Probabilities are market-agnostic (Pinnacle-informed); the client
    # multiplies P by the user's 竞彩 SP for EV. Empty when no fixtures.
    single_match_predictions: list[SinglePrediction] = Field(default_factory=list)


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


# ---------- /predictions/wc-upcoming (V12 W0 — 2026-05-28) ------------

class WcUpcomingPick(BaseModel):
    """One single-leg pick across the lookahead date window.

    Format intentionally mirrors `SingleTicketResponse` for league
    matches so the dashboard render helpers can be reused — but the
    underlying model is the WC-specific Elo+Pinnacle blend
    (NationalTeamModel α=0.4), not CatBoost.

    Only 1X2 outcomes here; the existing Path A++ handicap form
    handles 让球 on a per-match basis (the lookahead is a "show me
    the best NEXT few days" feature, not an enumeration of every
    market).
    """
    fixture_id: int
    kickoff_utc: str        # ISO with timezone
    days_until_kickoff: int  # 0 = today, 1 = tomorrow, etc.
    home_team: str
    away_team: str
    outcome: str = Field(..., description="'H' / 'D' / 'A' — 1X2 selection")
    hit_probability: float
    odds: float = Field(..., description="Pinnacle decimal odds")
    ev_per_unit: float
    stake: float = Field(..., description="Kelly-sized recommended stake (¥)")
    source: str = Field(..., description="'blend(α=0.4)' or 'lightgbm_only'")


class WcUpcomingResponse(BaseModel):
    """Top-N WC single-leg picks across the next N days, sorted by
    hit_probability descending. See `predictions_wc_upcoming` endpoint."""
    date_start: str        # ISO YYYY-MM-DD (today)
    date_end: str          # ISO YYYY-MM-DD (today + days - 1)
    days: int
    n_fixtures_scanned: int
    n_picks_after_ev_gate: int
    picks: list[WcUpcomingPick]
    blend_alpha: float
    generated_at_utc: str


# ---------- /recommend/wc/single (V11 post-ship — Path A++ hybrid) ----

class WcFixtureRecInput(BaseModel):
    """One WC fixture for the multi-market recommendation endpoint.

    Inputs the user provides per fixture:
    - Identity + Pinnacle 1X2 (for NationalTeamModel reverse-mapping)
    - 让球 line + 竞彩 SP odds (the actual bet market)

    All three handicap odds fields must be present together; if any
    is missing, the endpoint falls back to pure-model handicap probs
    (no Bayesian blend).
    """
    fixture_id: int
    home_team: str = Field(..., min_length=1)
    away_team: str = Field(..., min_length=1)
    kickoff_utc: str
    # Pinnacle 1X2 — model reverse-map input (REQUIRED for path A++)
    psc_home: float = Field(..., gt=1.0)
    psc_draw: float = Field(..., gt=1.0)
    psc_away: float = Field(..., gt=1.0)
    # 竞彩 整数让球 line + SP odds — the actual bet market
    handicap_home: int = Field(..., ge=-5, le=5,
        description="主队 让球数 (正 = 主队 受让, 负 = 主队 让球)")
    odds_handicap_H: float = Field(..., gt=1.0)
    odds_handicap_D: float = Field(..., gt=1.0)
    odds_handicap_A: float = Field(..., gt=1.0)


class WcSingleRecRequest(BaseModel):
    """POST /v4/recommend/wc/single body.

    Path A++ hybrid: runs NationalTeamModel for 1X2, reverse-maps to
    (λ_h, λ_a) under a WC-mean total-goals prior, computes model-side
    handicap probs via DC grid, blends with market-implied (dewedged)
    handicap probs at alpha=0.4 (matching the 1X2 blend convention).

    Returns one recommendation per fixture per market: 让球胜 / 让球平 /
    让球负 are scored independently; the server filters to outcomes with
    EV ≥ ``min_ev``.
    """
    fixtures: list[WcFixtureRecInput] = Field(..., min_length=1, max_length=20)
    bankroll: float = Field(1000.0, gt=0)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0,
        description="Per-ticket cap as fraction of bankroll")
    min_ev: float = Field(0.05, ge=-0.20, le=0.50,
        description="EV-per-unit floor; outcomes below this are dropped")
    blend_alpha: float = Field(0.4, ge=0.0, le=1.0,
        description="Model weight in the model+market handicap blend "
        "(0=pure market, 1=pure model; default 0.4 matches WC 1X2 blend)")
    host_country: Optional[str] = Field(None,
        description="Optional 3-letter code (e.g. 'USA' for WC 2026 host) "
        "passed to NationalTeamModel for host-advantage")
    host_advantage: float = Field(50.0,
        description="Elo points added for host country")
    # V11 post-ship — A/B observation hook (mirrors single/parlay/pool).
    # Two gates required for a real write: server NUTMEG_V4_OBSERVATION_DB
    # env var + this request flag. Recorded outcomes settle via the regular
    # auto-settle pipeline once a WC match outcome lands in match_outcomes.
    record_session: bool = Field(False,
        description="Opt-in observation recording for A/B / ROI tracking. "
        "Server-side recording also requires NUTMEG_V4_OBSERVATION_DB env.")


class WcRecommendationOutcome(BaseModel):
    """One row in WcSingleRecResponse.recommendations — the engine
    surfaces up to 3 outcomes per fixture (让胜, 让平, 让负); only the
    ones passing min_ev get a non-zero stake."""
    outcome: Literal["H", "D", "A"]
    p_final: float = Field(..., description="Final blended probability")
    p_model: float = Field(..., description="Model-only (DC reverse-mapped)")
    p_market: Optional[float] = Field(None,
        description="Market-implied (dewedged from SP). None if SP missing.")
    odds: float
    ev_per_unit: float
    kelly_fraction: float = Field(..., description="Full Kelly fraction "
        "(server applies kelly_fraction × kelly_fraction_param × bankroll)")
    stake: float = Field(..., description="¥2-quantized recommended stake")
    expected_return: float


class WcSingleRecMatch(BaseModel):
    """One fixture in the WC recommendation output."""
    fixture_id: int
    home_team: str
    away_team: str
    kickoff_utc: str
    handicap_home: int
    # Surfaced for transparency / diagnostics
    p_1x2_blended: list[float] = Field(..., description="The blended 1X2 from "
        "wc_predict (model + Pinnacle); the reverse-map input")
    inferred_lambda_home: float = Field(..., description="λ̂_h from 1X2 reverse-map")
    inferred_lambda_away: float = Field(..., description="λ̂_a from 1X2 reverse-map")
    # The 3 让球 outcomes — those with stake > 0 are the recommendations
    outcomes: list[WcRecommendationOutcome]


class WcSingleRecResponse(BaseModel):
    generated_at_utc: str
    bankroll: float
    n_fixtures: int
    n_recommendations: int = Field(..., description=
        "Outcomes with stake > 0 across all fixtures")
    matches: list[WcSingleRecMatch]
    total_stake: float
    total_expected_return: float
    blend_alpha: float
    lambda_total_prior: float = Field(..., description=
        "Total-goals prior used for the 1X2 → λ reverse-map (WC mean ~2.6)")


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
