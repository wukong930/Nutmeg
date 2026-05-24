"""V4 FastAPI routes.

Endpoints:
  GET  /v4/health    — artifact load status, model metadata
  POST /v4/recommend — fixtures (JSON) → predictions + recommendations

Artifact loading is LAZY (first request triggers load) so the app starts
fast even when artifact is on slow disk; subsequent requests reuse the
cached LoadedModel.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from nutmeg.v4.api.schemas import (
    FixtureOddsInput,
    HealthResponse,
    LegResponse,
    LotteryRulesResponse,
    ModelInfo,
    PoolLegResponse,
    PoolRecommendRequest,
    PoolRecommendResponse,
    PoolTicketResponse,
    RecommendRequest,
    RecommendResponse,
    RecommendationResponse,
    SelectionResponse,
    SingleRecommendRequest,
    SingleRecommendResponse,
    SinglePrediction,
    SingleTicketResponse,
    UpcomingPredictionsRequest,
    UpcomingPredictionsResponse,
)
from nutmeg.v4.combo import MatchInput, recommend_combinations
from nutmeg.v4.combo.compound_pool import recommend_pool
from nutmeg.v4.combo.lottery_rules import JINGCAI_DEFAULT
from nutmeg.v4.combo.selections import Selection
from nutmeg.v4.combo.single_match import recommend_singles
from nutmeg.v4.model.dixon_coles import grid_to_1x2, grid_to_handicap_1x2, score_grid
from nutmeg.v4.model.persist import (
    V4Artifact,
    build_features_for_fixtures,
    load_artifact,
    predict_lambdas,
)


router = APIRouter(prefix="/v4", tags=["v4"])


# ---------- Artifact loader (lazy + thread-safe) ------------------------

DEFAULT_ARTIFACT_PATH = "data/v4_model"
_artifact_cache: dict[str, V4Artifact] = {}
_load_lock = Lock()


def _artifact_path() -> str:
    return os.environ.get("NUTMEG_V4_ARTIFACT_PATH", DEFAULT_ARTIFACT_PATH)


def _observation_db_path() -> Optional[str]:
    """Post-V8 P1#5 — env-var that turns on session recording capability.

    Set NUTMEG_V4_OBSERVATION_DB=data/v4_observation.db to ALLOW the
    /recommend* endpoints to record sessions. V9 W3: this is now the
    server-side enable gate; the request must ALSO have
    `record_session=True` for an actual write to happen. Unset → no
    recording regardless of request flag (existing V4 W8 + V8 W6
    behavior).
    """
    return os.environ.get("NUTMEG_V4_OBSERVATION_DB")


def _should_record_session(req_record_flag: bool) -> Optional[str]:
    """V9 W3 — return the observation DB path iff both gates are satisfied.

    Both gates required:
      1. Server: NUTMEG_V4_OBSERVATION_DB is set
      2. Request: record_session=True

    Returns the DB path string when both hold, None otherwise. Callers
    use the result as a truthiness check + the path to pass into the
    recorder.
    """
    if not req_record_flag:
        return None
    return _observation_db_path()


def get_artifact() -> Optional[V4Artifact]:
    """Returns the loaded artifact, or None if path doesn't exist."""
    path = _artifact_path()
    if path in _artifact_cache:
        return _artifact_cache[path]
    if not Path(path).exists():
        return None
    with _load_lock:
        if path not in _artifact_cache:
            _artifact_cache[path] = load_artifact(path)
        return _artifact_cache[path]


def clear_artifact_cache() -> None:
    """Used by tests to force reload."""
    _artifact_cache.clear()


# ---------- /v4/health ---------------------------------------------------

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    path = _artifact_path()
    art = get_artifact()
    if art is None:
        return HealthResponse(
            status="degraded",
            artifact_loaded=False,
            artifact_path=path,
            detail=f"artifact not found at {path}; run `python -m nutmeg.v4.cli.train`",
        )
    n_teams = sum(len(teams) for teams in art.team_state.values())
    return HealthResponse(
        status="ok",
        artifact_loaded=True,
        artifact_path=path,
        trained_at_utc=art.metadata.get("trained_at_utc"),
        training_cutoff=art.metadata.get("training_cutoff"),
        n_teams=n_teams,
        n_leagues=len(art.team_state),
        model_type=art.model_type,
    )




# ---------- /v4/dashboard (web UI) ---------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Serve the single-file vanilla-JS dashboard."""
    html_path = _STATIC_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail="dashboard.html not bundled with package")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ---------- /v4/rules (V6 W10) -------------------------------------------

@router.get("/rules", response_model=LotteryRulesResponse)
def rules() -> LotteryRulesResponse:
    """Return the currently active 竞彩 LotteryRules constants.

    The dashboard fetches this on load so rule-display text (¥2 起投,
    ¥20k 上限, 派奖率 68.5%, EV 门槛 5%) stays in lockstep with the
    server's actual enforcement logic. Single source of truth lives in
    `nutmeg.v4.combo.lottery_rules.JINGCAI_DEFAULT`.
    """
    r = JINGCAI_DEFAULT
    return LotteryRulesResponse(
        stake_unit=r.stake_unit,
        max_ticket_stake=r.max_ticket_stake,
        max_period_stake=r.max_period_stake,
        min_parlay_legs=r.min_parlay_legs,
        max_legs_per_ticket=r.max_legs_per_ticket,
        payout_ratio=r.payout_ratio,
        vig=r.vig,
        min_ev_per_unit=r.min_ev_per_unit,
        min_hit_probability=r.min_hit_probability,
    )


# ---------- /v4/recommend -----------------------------------------------

def _fixtures_to_dataframe(fixtures: list[FixtureOddsInput]) -> pd.DataFrame:
    """Convert API input to the DataFrame shape the model expects."""
    rows = []
    for f in fixtures:
        rows.append({
            "date": pd.Timestamp(f.date),
            "league": f.league,
            "home_team": f.home_team,
            "away_team": f.away_team,
            "psc_home": f.psc_home,
            "psc_draw": f.psc_draw,
            "psc_away": f.psc_away,
            "psc_over25": f.psc_over25,
            "psc_under25": f.psc_under25,
            "ahch": f.ahch,
            "handicap_home": f.handicap_home,
            "odds_1x2_H": f.odds_1x2_H,
            "odds_1x2_D": f.odds_1x2_D,
            "odds_1x2_A": f.odds_1x2_A,
            "odds_handicap_H": f.odds_handicap_H,
            "odds_handicap_D": f.odds_handicap_D,
            "odds_handicap_A": f.odds_handicap_A,
        })
    return pd.DataFrame(rows)


def _fixture_to_match_input(row: pd.Series, lh: float, la: float, gbm_rho: float) -> Optional[MatchInput]:
    """Build MatchInput, defaulting to PSC odds if lottery-specific odds are missing."""
    # 1X2 market — fall back to PSC if no lottery odds
    o_h = row.get("odds_1x2_H") if not pd.isna(row.get("odds_1x2_H")) else row["psc_home"]
    o_d = row.get("odds_1x2_D") if not pd.isna(row.get("odds_1x2_D")) else row["psc_draw"]
    o_a = row.get("odds_1x2_A") if not pd.isna(row.get("odds_1x2_A")) else row["psc_away"]
    odds_1x2 = {"H": float(o_h), "D": float(o_d), "A": float(o_a)}

    # Handicap market (only when both handicap_home and odds_handicap_* are present)
    odds_hc = None
    handicap = None
    if not pd.isna(row.get("handicap_home")):
        handicap = int(row["handicap_home"])
        ho_h = row.get("odds_handicap_H")
        ho_d = row.get("odds_handicap_D")
        ho_a = row.get("odds_handicap_A")
        if not (pd.isna(ho_h) or pd.isna(ho_d) or pd.isna(ho_a)):
            odds_hc = {"H": float(ho_h), "D": float(ho_d), "A": float(ho_a)}

    return MatchInput(
        match_id=f"{row['league']}_{row['home_team']}_vs_{row['away_team']}",
        lambda_home=float(lh),
        lambda_away=float(la),
        rho=gbm_rho,
        handicap_home=handicap if odds_hc else None,
        odds_1x2=odds_1x2,
        odds_handicap_1x2=odds_hc,
    )


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    if req.k_max < req.k_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="k_max must be >= k_min",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))

    # Per-fixture predictions
    single_preds = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = grid_to_1x2(grid)
        pred = SinglePrediction(
            home_team=f.home_team,
            away_team=f.away_team,
            league=f.league,
            date=f.date,
            lambda_home=float(lh),
            lambda_away=float(la),
            p_home_1x2=float(ph),
            p_draw_1x2=float(pd_),
            p_away_1x2=float(pa),
        )
        if f.handicap_home is not None:
            hph, hpd, hpa = grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)
            pred.handicap_home = f.handicap_home
            pred.p_home_handicap = float(hph)
            pred.p_draw_handicap = float(hpd)
            pred.p_away_handicap = float(hpa)
        single_preds.append(pred)

    # Combo recommendations
    inputs: list[MatchInput] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        mi = _fixture_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            inputs.append(mi)

    recs = recommend_combinations(
        inputs,
        bankroll=req.bankroll,
        k_min=req.k_min,
        k_max=req.k_max,
        top_n_recommendations=req.top_n,
        min_hit_probability=req.min_hit_probability,
        min_kelly_stake=req.min_kelly_stake,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction=req.max_stake_fraction,
        include_compound=req.include_compound,
    )

    recommendations_out = []
    for r in recs:
        p = r.parlay
        legs_out = []
        for leg in p.legs:
            legs_out.append(LegResponse(
                match_id=leg.match_id,
                market_type=leg.market_type,
                selections=[
                    SelectionResponse(
                        outcome=s.outcome,
                        odds=float(s.odds),
                        probability=float(s.probability),
                        edge=float(s.edge),
                    )
                    for s in leg.selections
                ],
            ))
        recommendations_out.append(RecommendationResponse(
            rank=r.rank,
            k_legs=p.k,
            is_compound=p.is_compound,
            stake_units=r.stake_units,
            kelly_recommended_stake=float(r.kelly.recommended_stake),
            kelly_capped_fraction=float(r.kelly.capped_kelly),
            expected_return=float(r.kelly.expected_return),
            hit_probability=float(p.hit_probability),
            ev_per_unit=float(p.ev_per_unit),
            log_growth=float(r.kelly_log_growth),
            legs=legs_out,
        ))

    response = RecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=ModelInfo(
            trained_at_utc=art.metadata.get("trained_at_utc"),
            training_cutoff=art.metadata.get("training_cutoff"),
            n_train=art.metadata.get("n_train"),
            gbm_rho=gbm_rho,
            temperature_T=art.temperature_T,
            model_type=art.model_type,
            cat_features=art.cat_features,
        ),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=len(recommendations_out),
        single_match_predictions=single_preds,
        recommendations=recommendations_out,
    )

    # V9 W3: 串关 (parlay) auto-record path — both env AND request flag required.
    # Previously this endpoint never recorded (the dashboard's checkbox was
    # a no-op since V5 W11). The CLI's `--record-to` (V5 W8) still works
    # independently for command-line workflows.
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation import record_session as _record
        try:
            _record(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
                snapshot_phase=req.snapshot_phase,
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
    return response


# ---------- /v4/predictions/upcoming (V5 W11) ----------

@router.post("/predictions/upcoming", response_model=UpcomingPredictionsResponse)
def predictions_upcoming(req: UpcomingPredictionsRequest) -> UpcomingPredictionsResponse:
    """Lightweight prediction-only endpoint.

    Same input shape as /recommend, but returns ONLY per-fixture lambdas +
    1X2 + (optional) handicap probabilities — no Kelly, no parlay
    enumeration. Suitable for cheap "show me tomorrow's predictions" calls
    from the dashboard or external integrations.
    """
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    if not req.fixtures:
        # Empty input is semantically valid for this endpoint — return empty
        # predictions list with the same model_info envelope.
        return UpcomingPredictionsResponse(
            generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            model=ModelInfo(
                trained_at_utc=art.metadata.get("trained_at_utc"),
                training_cutoff=art.metadata.get("training_cutoff"),
                n_train=art.metadata.get("n_train"),
                gbm_rho=float(art.metadata.get("gbm_rho", -0.10)),
                temperature_T=art.temperature_T,
                model_type=art.model_type,
                cat_features=art.cat_features,
            ),
            n_fixtures=0,
            predictions=[],
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))

    predictions = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = grid_to_1x2(grid)
        pred = SinglePrediction(
            home_team=f.home_team,
            away_team=f.away_team,
            league=f.league,
            date=f.date,
            lambda_home=float(lh),
            lambda_away=float(la),
            p_home_1x2=float(ph),
            p_draw_1x2=float(pd_),
            p_away_1x2=float(pa),
        )
        if f.handicap_home is not None:
            hph, hpd, hpa = grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)
            pred.handicap_home = f.handicap_home
            pred.p_home_handicap = float(hph)
            pred.p_draw_handicap = float(hpd)
            pred.p_away_handicap = float(hpa)
        predictions.append(pred)

    return UpcomingPredictionsResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=ModelInfo(
            trained_at_utc=art.metadata.get("trained_at_utc"),
            training_cutoff=art.metadata.get("training_cutoff"),
            n_train=art.metadata.get("n_train"),
            gbm_rho=gbm_rho,
            temperature_T=art.temperature_T,
            model_type=art.model_type,
            cat_features=art.cat_features,
        ),
        n_fixtures=len(req.fixtures),
        predictions=predictions,
    )


# ---------- /v4/recommend/single (V8 W6) ----------

def _model_info_from_artifact(art) -> ModelInfo:
    return ModelInfo(
        trained_at_utc=art.metadata.get("trained_at_utc"),
        training_cutoff=art.metadata.get("training_cutoff"),
        n_train=art.metadata.get("n_train"),
        gbm_rho=float(art.metadata.get("gbm_rho", -0.10)),
        temperature_T=art.temperature_T,
        model_type=art.model_type,
        cat_features=art.cat_features,
    )


@router.post("/recommend/single", response_model=SingleRecommendResponse)
def recommend_single(req: SingleRecommendRequest) -> SingleRecommendResponse:
    """V8 W6 — 单关 (single-leg) recommendations via the V6 W9 engine."""
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))

    matches: list[MatchInput] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        mi = _fixture_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            matches.append(mi)

    rec = recommend_singles(
        matches,
        bankroll=req.bankroll,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction_per_ticket=req.max_stake_fraction,
        top_per_match=req.top_per_match,
    )

    tickets_out = [
        SingleTicketResponse(
            match_id=t.selection.match_id,
            market_type=t.selection.market_type,
            outcome=t.selection.outcome,
            odds=float(t.selection.odds),
            probability=float(t.selection.probability),
            ev_per_unit=float(t.ev_per_unit),
            stake=float(t.stake),
            raw_kelly_stake=float(t.raw_kelly_stake),
            expected_return=float(t.expected_return),
        )
        for t in rec.selected_tickets
    ]

    response = SingleRecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=len(tickets_out),
        tickets=tickets_out,
        total_stake=float(rec.total_stake),
        total_expected_return=float(rec.total_expected_return),
    )

    # V9 W3: record when both gates pass (server env + request flag).
    # Post-V8 P1#5 originally auto-recorded on env alone; V9 W3 adds the
    # request-side opt-in so the dashboard's per-session checkbox controls
    # whether a given response lands in the DB.
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation.recorder import record_single_session
        try:
            record_single_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_single_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
    return response


# ---------- /v4/recommend/pool (V8 W6) ----------

# Map the PoolFixturePick `pick` field to a (market_type, outcome) tuple
_POOL_PICK_MAP: dict[str, tuple[str, str]] = {
    "1x2_H": ("1x2", "H"),
    "1x2_D": ("1x2", "D"),
    "1x2_A": ("1x2", "A"),
    "hc_H":  ("handicap_1x2", "H"),
    "hc_D":  ("handicap_1x2", "D"),
    "hc_A":  ("handicap_1x2", "A"),
}


def _pick_to_selection(
    row: pd.Series,
    lh: float,
    la: float,
    gbm_rho: float,
    pick: str,
) -> Optional[Selection]:
    """Convert one (fixture row, pick) → one Selection for the compound pool.

    Mirrors the CLI's `_row_to_selection` in cli/recommend_pool.py but
    consumes a typed `pick` string instead of a CSV cell.
    """
    grid = score_grid(float(lh), float(la), rho=gbm_rho)
    match_id = f"{row['league']}_{row['home_team']}_vs_{row['away_team']}"
    market_type, outcome = _POOL_PICK_MAP[pick]

    if market_type == "1x2":
        ph, pd_, pa = grid_to_1x2(grid)
        prob = {"H": ph, "D": pd_, "A": pa}[outcome]
        odds_col = f"odds_1x2_{outcome}"
        odds = row.get(odds_col)
        if odds is None or pd.isna(odds):
            psc_col = {
                "H": "psc_home", "D": "psc_draw", "A": "psc_away",
            }[outcome]
            odds = row[psc_col]
        return Selection(
            match_id=match_id, market_type="1x2", outcome=outcome,
            probability=float(prob), odds=float(odds),
        )

    # handicap_1x2
    if pd.isna(row.get("handicap_home")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"row {match_id}: pick={pick} requires handicap_home to be set",
        )
    handicap_home = int(row["handicap_home"])
    hp_h, hp_d, hp_a = grid_to_handicap_1x2(grid, handicap_home=handicap_home)
    prob = {"H": hp_h, "D": hp_d, "A": hp_a}[outcome]
    odds_col = f"odds_handicap_{outcome}"
    odds = row.get(odds_col)
    if odds is None or pd.isna(odds):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"row {match_id}: pick={pick} but odds_handicap_{outcome} missing",
        )
    return Selection(
        match_id=match_id, market_type="handicap_1x2", outcome=outcome,
        probability=float(prob), odds=float(odds),
    )


@router.post("/recommend/pool", response_model=PoolRecommendResponse)
def recommend_pool_endpoint(req: PoolRecommendRequest) -> PoolRecommendResponse:
    """V8 W6 — 复式 (M-select-N compound parlay) via the V6 W3 engine."""
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )
    m = len(req.fixtures)
    if req.n > m:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"n={req.n} but only {m} fixtures in pool",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))

    selections: list[Selection] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        sel = _pick_to_selection(
            row, lambdas[i, 0], lambdas[i, 1], gbm_rho,
            req.fixtures[i].pick,
        )
        if sel is not None:
            selections.append(sel)

    rec = recommend_pool(
        selections, n=req.n,
        bankroll=req.bankroll,
        max_total_budget=req.max_total_budget,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction_per_ticket=req.max_stake_fraction_per_ticket,
    )

    tickets_out = [
        PoolTicketResponse(
            legs=[
                PoolLegResponse(
                    match_id=leg.match_id,
                    market_type=leg.market_type,
                    outcome=leg.outcome,
                    odds=float(leg.odds),
                    probability=float(leg.probability),
                    edge=float(leg.edge),
                )
                for leg in t.legs
            ],
            hit_probability=float(t.hit_probability),
            combined_odds=float(t.combined_odds),
            ev_per_unit=float(t.ev_per_unit),
            stake=float(t.stake),
            raw_kelly_stake=float(t.raw_kelly_stake),
            expected_return=float(t.expected_return),
        )
        for t in rec.tickets  # all candidates, EV desc
    ]

    response = PoolRecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        m=rec.m,
        n=rec.n,
        n_combinations=rec.n_combinations,
        n_selected=len(rec.selected_tickets),
        total_stake=float(rec.total_stake),
        total_expected_return=float(rec.total_expected_return),
        tickets=tickets_out,
    )

    # V9 W3: record when both gates pass (server env + request flag).
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation.recorder import record_pool_session
        try:
            record_pool_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_pool_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
    return response
