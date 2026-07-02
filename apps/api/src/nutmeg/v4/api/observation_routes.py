"""V4 observation API endpoints (read + write to the SQLite store).

These are separate from the core /v4/recommend route because the
observation DB is optional (a deployment may run without it).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field

from nutmeg.v4.observation import (
    open_db,
    settle_unsettled,
    upsert_outcome,
)
from nutmeg.v4.observation.live_vs_backtest import (
    LIVE_BACKTEST_TOLERANCE_PCT_POINTS,
    compute_gap,
    slice_live_settled,
)
from nutmeg.v4.observation.roi import (
    calibration_buckets,
    compute_headline,
    group_by_k_legs,
    group_by_league,
    weekly_pl,
)

router = APIRouter(prefix="/v4/observation", tags=["v4-observation"])


DEFAULT_DB_PATH = "data/v4_observation.db"


def _db_path() -> str:
    return os.environ.get("NUTMEG_V4_OBSERVATION_DB", DEFAULT_DB_PATH)


def _db_exists() -> bool:
    return Path(_db_path()).exists()


# ----- Schemas -----------------------------------------------------------

class ObservationHealthResponse(BaseModel):
    status: str
    db_path: str
    db_exists: bool
    n_sessions: int = 0
    n_recommendations: int = 0
    n_outcomes: int = 0
    n_settled: int = 0
    n_unsettled: int = 0


class ROIHeadline(BaseModel):
    n_settled: int
    n_hit: int
    n_partial: int
    n_miss: int
    total_stake: float
    total_payout: float
    profit_loss: float
    roi: float
    avg_hit_p_predicted: float
    actual_hit_rate: float


class ROIByKLegs(BaseModel):
    k_legs: int
    n: int
    n_hit: int
    stake: float
    payout: float
    pl: float
    avg_hit_p: float | None = None


class ROIByLeague(BaseModel):
    league: str
    n: int
    n_hit: int
    hit_rate: float
    stake: float
    payout: float
    pl: float
    roi: float


class ROICalibrationBucket(BaseModel):
    bin_lo: float
    bin_hi: float
    n: int
    avg_predicted: float
    actual_hit_rate: float


class ROIWeeklyEntry(BaseModel):
    week: str
    n: int
    stake: float
    pl: float
    cumulative_pl: float
    roi: float


class ROIResponse(BaseModel):
    headline: ROIHeadline
    by_k_legs: list[ROIByKLegs]
    by_league: list[ROIByLeague]
    calibration: list[ROICalibrationBucket]
    weekly: list[ROIWeeklyEntry]


class SessionSummary(BaseModel):
    session_id: int
    created_at: str
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    model_cutoff: str | None = None


class SessionsResponse(BaseModel):
    n: int
    sessions: list[SessionSummary]


class LatestSessionResponse(BaseModel):
    """post-v9 P1#8: lightweight read-back so dashboard can confirm
    'did my last POST actually persist?'. Returns None if observation
    DB is empty or doesn't exist — that's the only valid `recorded=False`
    signal. Don't conflate with 'env disabled' (caller already knows env)."""
    recorded: bool
    session: SessionSummary | None = None


class OutcomeInput(BaseModel):
    match_date: date
    league: str = Field(..., min_length=1)
    home_team: str = Field(..., min_length=1)
    away_team: str = Field(..., min_length=1)
    home_goals: int = Field(..., ge=0, le=30)
    away_goals: int = Field(..., ge=0, le=30)


class OutcomesBatchRequest(BaseModel):
    outcomes: list[OutcomeInput] = Field(..., min_length=1, max_length=100)


class OutcomesBatchResponse(BaseModel):
    n_recorded: int
    settle_counts: dict[str, Any]


# ----- Endpoints ---------------------------------------------------------

@router.get("/health", response_model=ObservationHealthResponse)
def health() -> ObservationHealthResponse:
    db = _db_path()
    if not _db_exists():
        return ObservationHealthResponse(
            status="empty", db_path=db, db_exists=False,
        )
    with open_db(db) as conn:
        n_sessions = conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
        n_recs = conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0]
        n_outcomes = conn.execute("SELECT COUNT(*) FROM match_outcomes").fetchone()[0]
        n_settled = conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
        n_unsettled = n_recs - n_settled
    return ObservationHealthResponse(
        status="ok",
        db_path=db,
        db_exists=True,
        n_sessions=n_sessions,
        n_recommendations=n_recs,
        n_outcomes=n_outcomes,
        n_settled=n_settled,
        n_unsettled=n_unsettled,
    )


@router.get("/roi", response_model=ROIResponse)
def roi(n_bins: int = 5) -> ROIResponse:
    if not _db_exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Observation DB not found at {_db_path()}",
        )
    with open_db(_db_path()) as conn:
        h = compute_headline(conn)
        by_k = group_by_k_legs(conn)
        by_lg = group_by_league(conn)
        cal = calibration_buckets(conn, n_bins=n_bins)
        weekly = weekly_pl(conn)
    return ROIResponse(
        headline=ROIHeadline(
            n_settled=h.n_settled, n_hit=h.n_hit, n_partial=h.n_partial, n_miss=h.n_miss,
            total_stake=h.total_stake, total_payout=h.total_payout,
            profit_loss=h.profit_loss, roi=h.roi,
            avg_hit_p_predicted=h.avg_hit_p_predicted,
            actual_hit_rate=h.actual_hit_rate,
        ),
        by_k_legs=[
            ROIByKLegs(
                k_legs=int(r["k_legs"]), n=int(r["n"]),
                n_hit=int(r["n_hit"] or 0), stake=float(r["stake"]),
                payout=float(r["payout"]), pl=float(r["pl"]),
                avg_hit_p=float(r["avg_hit_p"]) if r["avg_hit_p"] is not None else None,
            )
            for r in by_k
        ],
        by_league=[ROIByLeague(**r) for r in by_lg],
        calibration=[ROICalibrationBucket(**r) for r in cal],
        weekly=[ROIWeeklyEntry(**r) for r in weekly],
    )


@router.get("/sessions", response_model=SessionsResponse)
def list_sessions(limit: int = 20) -> SessionsResponse:
    if not _db_exists():
        return SessionsResponse(n=0, sessions=[])
    with open_db(_db_path()) as conn:
        rows = conn.execute(
            """SELECT session_id, created_at, bankroll, n_fixtures,
                       n_recommendations, model_cutoff
                FROM recommendation_sessions
                ORDER BY session_id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return SessionsResponse(
        n=len(rows),
        sessions=[SessionSummary(**dict(r)) for r in rows],
    )


@router.get("/sessions/latest", response_model=LatestSessionResponse)
def latest_session() -> LatestSessionResponse:
    """post-v9 P1#8: read-back endpoint for dashboard write confirmation.

    Returns `recorded=True` + the most recent session if the observation
    DB exists and has rows; `recorded=False` + `session=None` otherwise.
    Dashboard JS calls this immediately after a successful recommend
    POST to confirm the write actually landed (vs the request flag being
    set but the server env disabled, in which case session_id won't
    advance — the dashboard compares before/after to know)."""
    if not _db_exists():
        return LatestSessionResponse(recorded=False, session=None)
    with open_db(_db_path()) as conn:
        row = conn.execute(
            """SELECT session_id, created_at, bankroll, n_fixtures,
                       n_recommendations, model_cutoff
                FROM recommendation_sessions
                ORDER BY session_id DESC LIMIT 1""",
        ).fetchone()
    if row is None:
        return LatestSessionResponse(recorded=False, session=None)
    return LatestSessionResponse(
        recorded=True,
        session=SessionSummary(**dict(row)),
    )


# ----- /v4/observation/recommendations-history (V11 P1-FE#3) ----------------

class HistoryLeg(BaseModel):
    """One leg inside a recommendation. Carries match info + the picked outcome
    so the frontend can render `home logo vs away logo · 主胜 @ 1.85` without
    additional lookups."""
    match_id: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    league: str | None = None
    match_date: str | None = None
    market_type: str | None = None
    outcome: str | None = None
    odds: float | None = None


class HistoryRecommendation(BaseModel):
    """One row from `parlay_recommendations` joined with optional settlement.

    `outcome` is the user-facing rollup:
      - "hit"       → settled + hit=1
      - "miss"      → settled + hit=0
      - "partial"   → settled + hit=-1 (复式 partial)
      - "pending"   → no settlement yet
    """
    rec_id: int
    session_id: int
    rank: int
    k_legs: int
    is_compound: bool
    stake_units: float
    hit_probability: float
    ev_per_unit: float
    legs: list[HistoryLeg]
    # Derived from settlements
    outcome: Literal["hit", "miss", "partial", "pending"]
    profit_loss: float | None = None
    settled_at: str | None = None


class HistoryDayGroup(BaseModel):
    """Recommendations grouped by their session's CREATED-on date (UTC).

    The created date is what the user remembers ("我昨天下的注"); we don't
    group by the match's date because cross-day parlays would split awkwardly.
    """
    date: str  # ISO YYYY-MM-DD (UTC of session.created_at)
    n_recommendations: int
    n_hit: int
    n_miss: int
    n_partial: int
    n_pending: int
    recommendations: list[HistoryRecommendation]


class HistoryStats(BaseModel):
    """Top-level rollup across the requested window.

    Per design doc: no cumulative ROI (intentional — keeps the user focused
    on hit-rate vs ROI noise). Profit/loss is exposed only at the per-rec
    level for transparency."""
    n_recommendations: int
    n_hit: int
    n_miss: int
    n_partial: int
    n_pending: int
    hit_rate: float | None = Field(None, description=
        "n_hit / (n_hit + n_miss + n_partial). None when nothing settled yet.")


class HistoryResponse(BaseModel):
    days: list[HistoryDayGroup]
    stats: HistoryStats


def _outcome_label(hit: int | None) -> Literal["hit", "miss", "partial", "pending"]:
    """Map the settlements.hit tinyint to a frontend-friendly label."""
    if hit is None:
        return "pending"
    if hit == 1:
        return "hit"
    if hit == 0:
        return "miss"
    return "partial"  # -1


def _parse_legs_json(
    raw: str | None,
    session_meta: dict[str, dict[str, Any]] | None = None,
) -> list[HistoryLeg]:
    """Be liberal in what we accept — older rows may have slightly different
    leg shapes. Return [] on any parse error so the UI never crashes.

    ``session_meta`` maps ``match_id`` → ``{league, match_date, home_team,
    away_team}`` from the SAME session's ``single_predictions`` bridge rows
    (built by the caller). It supplies league / match_date / clean team names
    that the leg JSON itself does not carry.
    """
    session_meta = session_meta or {}
    if not raw:
        return []
    try:
        import json as _json
        data = _json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    out: list[HistoryLeg] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        # parlay_recommendations.legs_json shape (from recorder.py /
        # record_parlay_session):
        #   {match_id, market_type, selections: [{outcome, odds, ...}]}
        # The picked side + its odds live in selections[0] — NOT at the top
        # level (V12 W6 bug: this projection read d["outcome"]/d["odds"],
        # which are absent, so every history leg rendered null outcome/odds).
        # league / match_date are not in the leg JSON at all; recover them
        # from the session's single_predictions bridge rows.
        match_id = d.get("match_id")
        meta = session_meta.get(match_id, {}) if isinstance(match_id, str) else {}
        home = d.get("home_team") or meta.get("home_team")
        away = d.get("away_team") or meta.get("away_team")
        league = d.get("league") or meta.get("league")
        match_date = d.get("match_date") or meta.get("match_date")
        # Picked outcome + odds: prefer a top-level value (future-proof) then
        # fall back to the first selection (the current recorder shape).
        sels = d.get("selections")
        sel0 = (
            sels[0]
            if isinstance(sels, list) and sels and isinstance(sels[0], dict)
            else {}
        )
        outcome = d.get("outcome")
        if outcome is None:
            outcome = sel0.get("outcome")
        odds = d.get("odds")
        if odds is None:
            odds = sel0.get("odds")
        # Last-resort: parse match_id "league_home_vs_away" for any field the
        # bridge map didn't supply (older rows / missing bridge). The greedy
        # league prefix backtracks at the first lowercase/space in the home
        # team; it must include digits (FRA_LIGUE_1, GER_2_BUNDESLIGA — V12 W0
        # bug: regex was [A-Z_]+_ which stopped at the digit).
        if (not home or not away or not league) and \
                isinstance(match_id, str) and "_vs_" in match_id:
            import re as _re
            m = _re.match(r"^([A-Z0-9_]+)_(.+)_vs_(.+)$", match_id)
            if m:
                league = league or m.group(1)
                home = home or m.group(2)
                away = away or m.group(3)
        out.append(HistoryLeg(
            match_id=match_id,
            home_team=home,
            away_team=away,
            league=league,
            match_date=match_date,
            market_type=d.get("market_type"),
            outcome=outcome,
            odds=float(odds) if isinstance(odds, (int, float)) else None,
        ))
    return out


@router.get(
    "/recommendations-history",
    response_model=HistoryResponse,
    summary="V11 P1-FE#3 — per-day recommendation history with outcomes",
)
def recommendations_history(days: int = 30) -> HistoryResponse:
    """Return the last ``days`` of recommendations grouped by session-created
    date, with each recommendation tagged ``hit/miss/partial/pending`` based
    on the settlements table.

    Empty DB → ``{ days: [], stats: <zeros> }`` (never 404 — the UI just
    shows the empty state). Older sessions outside the window are simply
    excluded.
    """
    if days < 1:
        days = 1
    if days > 365:
        days = 365  # safety cap

    empty_stats = HistoryStats(
        n_recommendations=0, n_hit=0, n_miss=0, n_partial=0, n_pending=0,
        hit_rate=None,
    )
    if not _db_exists():
        return HistoryResponse(days=[], stats=empty_stats)

    cutoff_utc = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")

    with open_db(_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT p.rec_id, p.session_id, p.rank, p.k_legs, p.is_compound,
                   p.stake_units, p.hit_probability, p.ev_per_unit, p.legs_json,
                   r.created_at AS session_created_at,
                   s.hit AS s_hit, s.profit_loss AS s_pl, s.settled_at AS s_settled_at
            FROM parlay_recommendations p
            JOIN recommendation_sessions r ON p.session_id = r.session_id
            LEFT JOIN settlements s ON p.rec_id = s.rec_id
            WHERE r.created_at >= ?
            ORDER BY r.created_at DESC, p.rank ASC
            """,
            (cutoff_utc,),
        ).fetchall()
        # Bridge metadata: each leg's league / match_date / clean team names
        # live in single_predictions (keyed exactly like settlement.py:
        # f"{league}_{home}_vs_{away}"), NOT in the leg JSON. Scope by
        # session_id so a fixture key recurring across seasons can't bleed a
        # stale date into an unrelated leg.
        bridge_rows = conn.execute(
            "SELECT session_id, league, match_date, home_team, away_team "
            "FROM single_predictions"
        ).fetchall()

    # session_id → { match_id → {league, match_date, home_team, away_team} }
    meta_by_session: dict[int, dict[str, dict[str, Any]]] = {}
    for b in bridge_rows:
        mid = f"{b['league']}_{b['home_team']}_vs_{b['away_team']}"
        (
            meta_by_session
            .setdefault(int(b["session_id"]), {})
            .setdefault(mid, {
                "league": b["league"],
                "match_date": b["match_date"],
                "home_team": b["home_team"],
                "away_team": b["away_team"],
            })
        )

    # Group by date (UTC) — derive YYYY-MM-DD from session_created_at
    groups: dict[str, list[HistoryRecommendation]] = {}
    counters = {"hit": 0, "miss": 0, "partial": 0, "pending": 0}
    for row in rows:
        d = (row["session_created_at"] or "")[:10] or "unknown"
        hit_raw = row["s_hit"]
        # In SQLite, LEFT JOIN missing → None; record hit=None means pending
        outcome = _outcome_label(hit_raw if hit_raw is not None else None)
        counters[outcome] += 1
        rec = HistoryRecommendation(
            rec_id=int(row["rec_id"]),
            session_id=int(row["session_id"]),
            rank=int(row["rank"]),
            k_legs=int(row["k_legs"]),
            is_compound=bool(row["is_compound"]),
            stake_units=float(row["stake_units"]),
            hit_probability=float(row["hit_probability"]),
            ev_per_unit=float(row["ev_per_unit"]),
            legs=_parse_legs_json(
                row["legs_json"],
                meta_by_session.get(int(row["session_id"]), {}),
            ),
            outcome=outcome,
            profit_loss=float(row["s_pl"]) if row["s_pl"] is not None else None,
            settled_at=row["s_settled_at"],
        )
        groups.setdefault(d, []).append(rec)

    # Build response — days descending (most recent first; rows already sorted)
    day_blocks: list[HistoryDayGroup] = []
    for d, recs in groups.items():
        per = {"hit": 0, "miss": 0, "partial": 0, "pending": 0}
        for r in recs:
            per[r.outcome] += 1
        day_blocks.append(HistoryDayGroup(
            date=d,
            n_recommendations=len(recs),
            n_hit=per["hit"],
            n_miss=per["miss"],
            n_partial=per["partial"],
            n_pending=per["pending"],
            recommendations=recs,
        ))
    # Already in DESC order from SQL — keep stable
    day_blocks.sort(key=lambda b: b.date, reverse=True)

    n_settled = counters["hit"] + counters["miss"] + counters["partial"]
    hit_rate = (counters["hit"] / n_settled) if n_settled > 0 else None
    stats = HistoryStats(
        n_recommendations=sum(counters.values()),
        n_hit=counters["hit"],
        n_miss=counters["miss"],
        n_partial=counters["partial"],
        n_pending=counters["pending"],
        hit_rate=hit_rate,
    )
    return HistoryResponse(days=day_blocks, stats=stats)


@router.post("/outcomes", response_model=OutcomesBatchResponse)
def post_outcomes(req: Annotated[OutcomesBatchRequest, Body(...)]) -> OutcomesBatchResponse:
    db = _db_path()
    n = 0
    with open_db(db) as conn:
        for o in req.outcomes:
            upsert_outcome(
                conn,
                match_date=str(o.match_date),
                league=o.league,
                home_team=o.home_team,
                away_team=o.away_team,
                home_goals=o.home_goals,
                away_goals=o.away_goals,
            )
            n += 1
        counts = settle_unsettled(conn)
    return OutcomesBatchResponse(n_recorded=n, settle_counts=counts)


# ----- /v4/observation/live-vs-backtest (V5 W11) -----------------------------

class LiveVsBacktestResponse(BaseModel):
    """Read-only summary mirroring `nutmeg.v4.observation.live_vs_backtest.GapReport`.

    The backtest comparison side is OPTIONAL — providing a backtest pooled
    summary requires running a full walk_forward, which is expensive in an
    HTTP path. The dashboard can pass the most recently tracked experiment's
    pooled.json via the query body to compare; the bare endpoint just returns
    the live slice.
    """

    weeks: int
    snapshot_phase: str | None = None
    model_arm: str | None = None
    tolerance_pp: float
    over_tolerance: bool
    live: dict[str, Any]
    backtest: dict[str, Any] | None = None
    roi_gap_pp: float | None = None
    hit_rate_gap_pp: float | None = None


@router.get(
    "/live-vs-backtest",
    response_model=LiveVsBacktestResponse,
    summary="Live ROI / hit-rate vs (optional) backtest reference, last N weeks",
)
def live_vs_backtest_route(
    weeks: int = 4,
    snapshot_phase: str | None = None,
    model_arm: Literal["all", "lineup_aware", "lineup_free"] | None = None,
    tolerance_pp: float = LIVE_BACKTEST_TOLERANCE_PCT_POINTS,
) -> LiveVsBacktestResponse:
    """GET-only endpoint (read live DB; no backtest run inline).

    For backtest comparison use the `nutmeg-live-vs-backtest` CLI which can
    afford to run walk_forward; HTTP clients should poll this endpoint for
    the live slice and run the diff offline.

    ``tolerance_pp`` defaults to LIVE_BACKTEST_TOLERANCE_PCT_POINTS (5.0).
    Set higher (~50pp) for cross-source noise-floor checks; see P1#22 doc.
    """
    if tolerance_pp < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tolerance_pp must be >= 0",
        )
    db = _db_path()
    if not _db_exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"observation DB not found at {db}",
        )
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(weeks=weeks)
    with open_db(db) as conn:
        live = slice_live_settled(
            conn,
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            snapshot_phase=snapshot_phase,
            model_arm=model_arm,
        )
    report = compute_gap(live, None, tolerance_pp=tolerance_pp)  # no backtest from HTTP
    return LiveVsBacktestResponse(
        weeks=weeks,
        snapshot_phase=snapshot_phase,
        model_arm=model_arm,
        tolerance_pp=tolerance_pp,
        over_tolerance=report.over_tolerance,
        live={
            "n_sessions": live.n_sessions,
            "n_settled": live.n_settled,
            "n_hit": live.n_hit,
            "n_partial": live.n_partial,
            "n_miss": live.n_miss,
            "total_stake": live.total_stake,
            "total_payout": live.total_payout,
            "profit_loss": live.profit_loss,
            "roi": live.roi,
            "avg_hit_p_predicted": live.avg_hit_p_predicted,
            "actual_hit_rate": live.actual_hit_rate,
        },
        backtest=None,
        roi_gap_pp=report.roi_gap_pp,
        hit_rate_gap_pp=report.hit_rate_gap_pp,
    )


# ----- Prediction scoreboard (V12 W8j) -----------------------------------

class PredictionScoreboardResponse(BaseModel):
    """Model-board prediction accuracy (non-竞彩) + Layer A calibration status.

    Powers the dashboard 自我体检 card. Read-only. `prediction` mirrors
    nutmeg-predict-report's numbers; `calibration` reflects the last
    auto-calibration run (or nulls if Layer A hasn't acted yet)."""
    db_exists: bool
    prediction: dict[str, Any]
    calibration: dict[str, Any]


@router.get("/prediction-scoreboard", response_model=PredictionScoreboardResponse)
def prediction_scoreboard() -> PredictionScoreboardResponse:
    """Model-board prediction hit-rate / calibration / vs-Pinnacle + the latest
    Layer A calibration verdict. Honest by construction: hit-rate ships next to
    the Pinnacle baseline + the model-vs-sharp log-loss delta."""
    from nutmeg.v4.cli.predict_report import scoreboard
    from nutmeg.v4.observation.auto_calibration import fetch_latest_journal_entry
    from nutmeg.v4.observation.prediction_log import fetch_league_predictions

    empty_cal: dict[str, Any] = {
        "last_run_at": None, "applied": None, "current_t": None,
        "proposed_t": None, "reason": None, "n_samples": None,
    }
    if not _db_exists():
        return PredictionScoreboardResponse(
            db_exists=False, prediction=scoreboard([]), calibration=empty_cal,
        )
    db = _db_path()
    try:
        rows = fetch_league_predictions(db)
    except Exception:  # noqa: BLE001
        rows = []
    pred = scoreboard(rows)
    cal = dict(empty_cal)
    try:
        j = fetch_latest_journal_entry(db)
        if j:
            cal = {
                "last_run_at": j.get("recorded_at"),
                "applied": bool(j.get("decision")),
                "current_t": j.get("current_T"),
                "proposed_t": j.get("proposed_T"),
                "reason": j.get("reason"),
                "n_samples": (j.get("n_train") or 0) + (j.get("n_holdout") or 0),
            }
    except Exception:  # noqa: BLE001
        pass
    return PredictionScoreboardResponse(db_exists=True, prediction=pred, calibration=cal)


# ---------- /polymarket-board (Polymarket 错价研究看板 · READ-ONLY) ----------
# Serves the accumulated polymarket_gaps rows (cron-populated) as per-match cards:
# 胜平负 / 让球 / 大小球 legs (fair q vs Polymarket ask + EV + tier) plus, for a
# modelled match, the model↔Pinnacle↔Polymarket triangulation. NOT a betting
# venue (Polymarket blocks China; +EV carries risk, not arbitrage).
_PM_TIER_RANK = {"excluded": 0, "low": 1, "medium": 2, "high": 3}
_PM_ML = ("HOME_WIN", "DRAW", "AWAY_WIN")
_PM_DISCLAIMER = (
    "只读研究 / 交叉校验,非下注 venue(Polymarket 封中国);+EV 含风险,非无风险套利;"
    "公允 P = Pinnacle 去vig(与竞彩板同源)。"
)


def _pm_leg(r: dict) -> dict:
    """One polymarket_gaps row → a compact board leg."""
    return {
        "outcome_spec": r["outcome_spec"],
        "line": r.get("line"),
        "q_fair": round(r["q_fair"], 4),
        "poly_ask": round(r["poly_ask"], 4),
        "poly_mid": round(r["poly_mid"], 4) if r.get("poly_mid") is not None else None,
        "ev": round(r["ev"], 4),
        "edge_direction": r.get("edge_direction"),
        "confidence_tier": r["confidence_tier"],
        "reasons": json.loads(r["reasons"]) if r.get("reasons") else [],
        "depth_usd": r.get("depth_usd"),
        "freshness_hours": r.get("freshness_hours"),
        "outcome_hit": r.get("outcome_hit"),   # settled result (None until kickoff)
    }


def _pm_kickoff_past(kickoff_utc: str | None, now: datetime) -> bool:
    """True if the match has already kicked off → hide it from the LIVE board (a
    kicked-off / finished match is no longer an actionable pre-match mispricing).
    Its rows stay in the DB for the by-tier hit-rate 复盘. Fail-open: an unknown or
    unparseable kickoff keeps the card (never silently drop on bad data)."""
    if not kickoff_utc:
        return False
    try:
        naive = kickoff_utc.strip()[:19].replace("T", " ")  # "YYYY-MM-DD HH:MM:SS"
        ko = datetime.strptime(naive, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return False
    return ko <= now


def _assemble_polymarket_board(db: str) -> list[dict]:
    from nutmeg.v4.observation.polymarket_gaps import fetch_polymarket_gaps
    from nutmeg.v4.observation.polymarket_model_overlay import (
        fetch_model_1x2,
        triangulate,
    )

    by_fx: dict[int, list[dict]] = {}
    for r in fetch_polymarket_gaps(db):
        by_fx.setdefault(r["fixture_id"], []).append(r)

    now = datetime.now(UTC)
    matches: list[dict] = []
    for fid, legs in by_fx.items():
        first = legs[0]
        if _pm_kickoff_past(first.get("kickoff_utc"), now):
            continue  # 已开赛/已结束 → 不进实时错价板(行仍留库供结算复盘)
        ml = {r["outcome_spec"]: r for r in legs if r["outcome_spec"] in _PM_ML}
        moneyline = [_pm_leg(ml[s]) for s in _PM_ML if s in ml]
        handicap = sorted(
            (_pm_leg(r) for r in legs if r["outcome_spec"].startswith("HANDICAP")),
            key=lambda x: (x["outcome_spec"], x["line"] if x["line"] is not None else 0.0))
        totals = sorted(
            (_pm_leg(r) for r in legs if r["outcome_spec"] in ("OVER", "UNDER")),
            key=lambda x: (x["line"] if x["line"] is not None else 0.0, x["outcome_spec"]))

        tri = None
        if all(s in ml for s in _PM_ML):
            pinn = (ml["HOME_WIN"]["q_fair"], ml["DRAW"]["q_fair"], ml["AWAY_WIN"]["q_fair"])
            poly = {"H": ml["HOME_WIN"]["poly_ask"], "D": ml["DRAW"]["poly_ask"],
                    "A": ml["AWAY_WIN"]["poly_ask"]}
            model = fetch_model_1x2(
                db, fixture_id=fid, match_date=first.get("match_date"),
                home_team=first.get("home_team"), away_team=first.get("away_team"))
            t = triangulate(pinn, poly, model)
            tri = {
                "model_1x2": [round(x, 4) for x in t.model_1x2] if t.model_1x2 else None,
                "model_argmax": t.model_argmax, "pinnacle_argmax": t.pinnacle_argmax,
                "polymarket_argmax": t.polymarket_argmax,
                "consensus_vs_poly_diverge": t.consensus_vs_poly_diverge,
                "flip_backer": t.flip_backer, "all_three_agree": t.all_three_agree,
            }

        all_legs = moneyline + handicap + totals
        top_tier = max((g["confidence_tier"] for g in all_legs),
                       key=lambda tt: _PM_TIER_RANK.get(tt, 0), default=None)
        best_ev = max((g["ev"] for g in all_legs if g["confidence_tier"] != "excluded"),
                      default=None)
        matches.append({
            "fixture_id": fid, "league": first.get("league"),
            "home_team": first.get("home_team"), "away_team": first.get("away_team"),
            "match_date": first.get("match_date"), "kickoff_utc": first.get("kickoff_utc"),
            "recorded_at": first.get("recorded_at"),
            "moneyline": moneyline, "handicap": handicap, "totals": totals,
            "triangulation": tri, "top_tier": top_tier, "best_ev": best_ev,
            "has_diverge": bool(tri and tri["consensus_vs_poly_diverge"]),
        })

    # research-first ordering: divergence cards, then best tier, then kickoff.
    matches.sort(key=lambda m: (
        not m["has_diverge"], -_PM_TIER_RANK.get(m["top_tier"], 0), m.get("kickoff_utc") or ""))
    return matches


@router.get("/polymarket-board")
def polymarket_board() -> dict:
    """READ-ONLY Polymarket 错价研究看板. Accumulated gaps grouped per match into
    胜平负 / 让球 / 大小球 + model↔Pinnacle↔Polymarket triangulation. Empty DB →
    empty board (not 404). NEVER a betting instrument."""
    if not _db_exists():
        return {"db_exists": False, "matches": [], "count": 0, "disclaimer": _PM_DISCLAIMER}
    try:
        board = _assemble_polymarket_board(_db_path())
    except Exception:  # noqa: BLE001 — a bad read must return an empty board, not a 500
        board = []
    return {"db_exists": True, "matches": board, "count": len(board),
            "disclaimer": _PM_DISCLAIMER}
