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
from fastapi.responses import HTMLResponse, Response

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
    TodayRecommendationsRequest,
    TodayRecommendationsResponse,
    TodaySummary,
    UpcomingPredictionsRequest,
    UpcomingPredictionsResponse,
    WcMatchPrediction,
    WcPredictionsResponse,
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
from nutmeg.v4.observation.auto_calibration import (
    LIVE_T_CORRECTION_FILENAME,
    apply_correction_to_probs,
    load_artifact_correction,
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


# ---------- Live T-correction loader (V10 W2 Day 3) ---------------------
# Per-request load with mtime cache invalidation. The file ships from
# `nutmeg-auto-calibration --apply --deploy-artifact <art_dir>`; serving
# applies it as a final post-hoc temperature pass on 1X2 / handicap probs.
# Missing file → None → identity passthrough (existing V4-V9 behavior).
_correction_cache: dict[str, tuple[float, dict | None]] = {}


def _load_correction() -> dict | None:
    """Return the cached `live_T_correction.json` content (or None).

    Re-reads from disk when the file mtime changes (so a fresh
    `--deploy-artifact` takes effect on the next request without a
    server restart). Returns None when the file is missing, empty,
    or unparseable.
    """
    art_dir = _artifact_path()
    path = Path(art_dir) / LIVE_T_CORRECTION_FILENAME
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _correction_cache.pop(art_dir, None)
        return None
    cached = _correction_cache.get(art_dir)
    if cached and cached[0] == mtime:
        return cached[1]
    correction = load_artifact_correction(art_dir)
    _correction_cache[art_dir] = (mtime, correction)
    return correction


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


# ---------- /v4/manifest.json + /v4/sw.js + /v4/icon.svg (P1#14 PWA) ----

@router.get("/manifest.json", include_in_schema=False)
def manifest() -> Response:
    """post-v9 P1#14: PWA manifest so the dashboard can be installed
    as a standalone web app on mobile (Android Chrome / iOS Safari
    "Add to Home Screen"). Minimal: name, icons, theme color,
    display mode, start URL."""
    import json as _json
    body = {
        "name": "Nutmeg Football Betting Helper",
        "short_name": "Nutmeg",
        "description": "China sports lottery football betting recommendations",
        "start_url": "/api/v4/dashboard",
        "scope": "/api/v4/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#f9fafb",
        "theme_color": "#4f46e5",
        "icons": [
            {"src": "/api/v4/icon.svg",
             "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
        ],
        "lang": "zh-CN",
        "categories": ["sports", "finance"],
    }
    return Response(
        content=_json.dumps(body, ensure_ascii=False, indent=2),
        media_type="application/manifest+json",
    )


@router.get("/icon.svg", include_in_schema=False)
def app_icon() -> Response:
    """SVG app icon (works at any size, low byte count, no PNG generation)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">'
        '<rect width="192" height="192" rx="38" fill="#4f46e5"/>'
        # Soccer ball stylization: white circle + dark pentagon hint
        '<circle cx="96" cy="96" r="56" fill="#ffffff"/>'
        '<polygon points="96,58 122,75 112,108 80,108 70,75" fill="#1f2937"/>'
        # "N" wordmark for Nutmeg, lower-right
        '<text x="96" y="172" text-anchor="middle" '
        'font-family="-apple-system,BlinkMacSystemFont,sans-serif" '
        'font-size="20" font-weight="700" fill="#ffffff">Nutmeg</text>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    """post-v9 P1#14: minimal service worker.

    Strategy: cache-first for the dashboard shell + manifest + icon,
    network-first (with cache fallback) for everything else. This
    gives offline-launch capability for the dashboard UI; API endpoints
    will still fail offline (intentional — predictions need fresh data).

    Versioned cache name forces refresh when dashboard.html ships an
    update; bump CACHE_VERSION below when shell-cached files change.
    """
    sw_js = """
// Bumped 2026-05-25 V11 P1-FE#1 — forces SW to re-fetch dashboard.html
// after design-system refresh. The activate handler below deletes any
// cache named differently from this constant, so the next page load
// auto-purges the old shell + grabs the new HTML.
const CACHE_VERSION = 'nutmeg-v4-fe-zh';
const SHELL_URLS = [
  '/api/v4/dashboard',
  '/api/v4/manifest.json',
  '/api/v4/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Cache-first for shell URLs
  if (SHELL_URLS.some((u) => url.pathname === u || url.pathname.endsWith(u))) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request).then((resp) => {
        const respClone = resp.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, respClone));
        return resp;
      }).catch(() => cached))
    );
    return;
  }
  // Network-first for everything else (API calls etc.)
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
""".lstrip()
    return Response(content=sw_js, media_type="application/javascript")


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


# ---------- /v4/team-name-zh (V11 P1-FE#2) ------------------------------

@router.get("/team-name-zh", include_in_schema=False)
def team_name_zh_endpoint() -> Response:
    """Return Chinese name dict for ~100 top-5 European league teams.

    Dashboard fetches this once at init and stores it as ``TEAM_ZH_DICT``.
    When ``locale == 'zh'`` the frontend calls ``zhTeam(name)`` to swap
    English → Chinese in match cards. Unknown teams fall through unchanged.

    Static — cached aggressively (1 day).
    """
    import json as _json
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    return Response(
        content=_json.dumps(TEAM_NAME_ZH, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="k_max must be >= k_min",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    # Per-fixture predictions
    single_preds = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
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
            hph, hpd, hpa = tuple(
                apply_correction_to_probs(
                    np.array(grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)),
                    correction,
                )
            )
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
        correction=correction,
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
    correction = _load_correction()

    predictions = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
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
            hph, hpd, hpa = tuple(
                apply_correction_to_probs(
                    np.array(grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)),
                    correction,
                )
            )
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
    correction = _load_correction()

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
        correction=correction,
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
    *,
    correction: dict | None = None,
) -> Optional[Selection]:
    """Convert one (fixture row, pick) → one Selection for the compound pool.

    Mirrors the CLI's `_row_to_selection` in cli/recommend_pool.py but
    consumes a typed `pick` string instead of a CSV cell.

    V10 W2 Day 3 — applies the live post-T correction (if any) to the
    1X2 / handicap_1x2 probability tuple before extracting the chosen
    outcome's probability.
    """
    grid = score_grid(float(lh), float(la), rho=gbm_rho)
    match_id = f"{row['league']}_{row['home_team']}_vs_{row['away_team']}"
    market_type, outcome = _POOL_PICK_MAP[pick]

    if market_type == "1x2":
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"row {match_id}: pick={pick} requires handicap_home to be set",
        )
    handicap_home = int(row["handicap_home"])
    hp_h, hp_d, hp_a = tuple(
        apply_correction_to_probs(
            np.array(grid_to_handicap_1x2(grid, handicap_home=handicap_home)),
            correction,
        )
    )
    prob = {"H": hp_h, "D": hp_d, "A": hp_a}[outcome]
    odds_col = f"odds_handicap_{outcome}"
    odds = row.get(odds_col)
    if odds is None or pd.isna(odds):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"n={req.n} but only {m} fixtures in pool",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    selections: list[Selection] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        sel = _pick_to_selection(
            row, lambdas[i, 0], lambdas[i, 1], gbm_rho,
            req.fixtures[i].pick,
            correction=correction,
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


# ---------- /today-recommendations (V10 W1 Track A) ----------

def _fixture_rows_to_inputs(rows: list[dict]) -> list[FixtureOddsInput]:
    """Convert ingest_odds CSV-row dicts to FixtureOddsInput pydantic objects.

    Drops rows missing required psc_* (closing odds) — those can't be
    scored. Logs the drop count for observability.
    """
    out: list[FixtureOddsInput] = []
    for r in rows:
        try:
            # ingest_odds returns numeric fields as either floats or ""
            # (when bookmaker didn't quote that market). FixtureOddsInput
            # validates `> 1.0`; empty string fails. So we coerce + skip.
            def _f(key: str, default=None):
                v = r.get(key)
                if v is None or v == "":
                    return default
                return float(v)

            psc_h = _f("psc_home")
            psc_d = _f("psc_draw")
            psc_a = _f("psc_away")
            if psc_h is None or psc_d is None or psc_a is None:
                continue

            out.append(FixtureOddsInput(
                date=r["date"],
                league=r["league"],
                home_team=r["home_team"],
                away_team=r["away_team"],
                psc_home=psc_h,
                psc_draw=psc_d,
                psc_away=psc_a,
                odds_1x2_H=_f("odds_1x2_H"),
                odds_1x2_D=_f("odds_1x2_D"),
                odds_1x2_A=_f("odds_1x2_A"),
                handicap_home=int(r["handicap_home"]) if r.get("handicap_home") not in (None, "") else None,
                odds_handicap_H=_f("odds_handicap_H"),
                odds_handicap_D=_f("odds_handicap_D"),
                odds_handicap_A=_f("odds_handicap_A"),
                psc_over25=_f("psc_over25"),
                psc_under25=_f("psc_under25"),
            ))
        except Exception:  # noqa: BLE001
            # Tolerate per-row failures — better to return partial recs
            # than to 500 the whole endpoint
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: dropped fixture row %r",
                {k: r.get(k) for k in ("date", "league", "home_team", "away_team")},
            )
    return out


@router.post(
    "/today-recommendations",
    response_model=TodayRecommendationsResponse,
    summary="Unified daily recommendation flow: auto-fetch fixtures + run single + parlay",
)
def today_recommendations(req: TodayRecommendationsRequest) -> TodayRecommendationsResponse:
    """V10 W1 Track A — the user-facing "land on the page" endpoint.

    Reuses existing endpoint functions (`recommend`, `recommend_single`)
    internally; no new ML logic. Server-side fetches fixtures via
    `nutmeg.v4.cli.ingest_odds._gather_rows` (V7 W1).

    Returns None for any included game type that produced 0 recommendations
    or whose pipeline raised — UI renders "no recommendations today" rather
    than throwing a 500.

    Pool intentionally NOT included for V10 W1: it requires per-fixture
    `pick` selection which needs a separate auto-pick policy decision.
    Deferred to W2.
    """
    import datetime as _dt
    from pathlib import Path as _Path

    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
    )

    # Resolve date
    if req.date is None:
        on_date = _dt.date.today()
    else:
        try:
            on_date = _dt.date.fromisoformat(req.date)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"date must be ISO YYYY-MM-DD: {exc}",
            )

    # Fetch fixtures (uses API-Football; will use cache if available)
    try:
        rows, _n_calls, _n_skipped = _gather_rows(
            req.leagues,
            on_date,
            cache_dir=_Path("data/external/api_football"),
            bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False,
            refresh_odds=False,
        )
    except Exception as exc:  # noqa: BLE001
        # API-Football errors (rate limit, network, missing key) → return
        # empty response with clear summary, not 500. Caller sees
        # fixtures_fetched=0 and can show "no data today / API issue".
        import logging
        logging.getLogger(__name__).warning(
            "today-recommendations fixture fetch failed: %s", exc,
        )
        rows = []

    fixtures = _fixture_rows_to_inputs(rows)
    fixtures_fetched = len(fixtures)

    single_resp: SingleRecommendResponse | None = None
    parlay_resp: RecommendResponse | None = None
    total_recs = 0
    total_stake = 0.0
    stake_weighted_ev_sum = 0.0

    if fixtures_fetched > 0 and "single" in req.include:
        try:
            single_req = SingleRecommendRequest(
                fixtures=fixtures,
                bankroll=req.bankroll,
                kelly_fraction=req.kelly_fraction,
                record_session=req.record_session,
            )
            single_resp = recommend_single(single_req)
            if single_resp.n_recommendations > 0:
                total_recs += single_resp.n_recommendations
                total_stake += single_resp.total_stake
                # Sum EV-weighted-by-stake for the weighted_ev computation
                for t in single_resp.tickets:
                    stake_weighted_ev_sum += t.stake * t.ev_per_unit
            else:
                single_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: single pipeline failed",
            )
            single_resp = None

    if fixtures_fetched >= 2 and "parlay" in req.include:
        try:
            parlay_req = RecommendRequest(
                fixtures=fixtures,
                bankroll=req.bankroll,
                top_n=10,
                k_min=2,
                k_max=min(8, fixtures_fetched),
                min_hit_probability=req.min_hit_probability,
                min_kelly_stake=req.min_kelly_stake,
                kelly_fraction=req.kelly_fraction,
                include_compound=False,
                record_session=req.record_session,
            )
            parlay_resp = recommend(parlay_req)
            if parlay_resp.n_recommendations > 0:
                total_recs += parlay_resp.n_recommendations
                total_stake += parlay_resp.total_stake
                for r in parlay_resp.recommendations:
                    stake_weighted_ev_sum += r.stake_units * 1.0 * r.ev_per_unit  # stake_units is in ¥ for parlays
            else:
                parlay_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: parlay pipeline failed",
            )
            parlay_resp = None

    weighted_ev = (stake_weighted_ev_sum / total_stake) if total_stake > 0 else None

    return TodayRecommendationsResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date=on_date.isoformat(),
        leagues=req.leagues,
        bankroll=req.bankroll,
        fixtures_fetched=fixtures_fetched,
        single=single_resp,
        parlay=parlay_resp,
        summary=TodaySummary(
            total_recs=total_recs,
            total_stake=total_stake,
            weighted_ev=weighted_ev,
        ),
    )


# ---------- /predictions/wc (V10 W1 Track B Day 5) ----------

@router.get(
    "/predictions/wc",
    response_model=WcPredictionsResponse,
    summary="Daily WC 1X2 predictions (LightGBM + Pinnacle blend per Day 3 verdict)",
)
def predictions_wc(
    date: str | None = None,
    fetch_current_odds: bool = False,
    alpha: float = 0.4,
    season: int | None = None,
) -> WcPredictionsResponse:
    """V10 W1 Track B Day 5 — HTTP wrapper around the `nutmeg-wc-predict`
    CLI logic. Used by the dashboard "🏆 WC 2026" tab.

    Parameters
    ----------
    date : YYYY-MM-DD. Default today (UTC).
    fetch_current_odds : if True, pulls Pinnacle from The Odds API
        (costs ~10 quota per request); if False, model-only output.
    alpha : blend weight LightGBM × Pinnacle (default 0.4 per Day 3
        walk-forward).
    season : WC season year (default derived from date.year).

    Graceful degradation
    --------------------
    - Missing training data → 503
    - No fixtures on date → 200 with predictions=[] and n_fixtures=0
    - API-Football error → 200 with empty predictions (logged)
    - Odds API error → 200, fall back to lightgbm_only
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    if date is None:
        on_date = _dt.date.today()
    else:
        try:
            on_date = _dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"date must be ISO YYYY-MM-DD: {exc}",
            )

    season_resolved = season or on_date.year

    # Local imports (avoid top-level cost in tests / other endpoints)
    try:
        from nutmeg.v4.cli.wc_predict import (
            HOST_COUNTRIES,
            _build_pinnacle_lookup_for_date,
            _pinnacle_lookup_with_aliases,
            _predict_one_fixture,
            _train_combined_model,
        )
        from nutmeg.v4.data.sources.api_football import (
            fetch_fixtures_for_league_season,
        )
        from nutmeg.v4.data.wc_training_frame import load_elo_snapshot
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC prediction module not loadable: {exc}",
        )

    snapshots = sorted(_Path("data/external/eloratings").glob("eloratings_*.parquet"))
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eloratings snapshot found at data/external/eloratings/. "
                   "Run the eloratings scraper first (see v10_w1_day2_*.md).",
        )

    # Training data needed
    try:
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}. "
                   "Run nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022",
        )

    elo = load_elo_snapshot(snapshots[-1])

    try:
        all_fx = fetch_fixtures_for_league_season("WC", season_resolved)
    except Exception as exc:  # noqa: BLE001
        _log.warning("WC fixture fetch failed: %s", exc)
        all_fx = []

    on_iso = on_date.isoformat()
    today_fx = [f for f in all_fx if f.get("fixture", {}).get("date", "").startswith(on_iso)]

    pinnacle_lookup = {}
    if fetch_current_odds and today_fx:
        try:
            pinnacle_lookup = _build_pinnacle_lookup_for_date(on_date)
        except Exception as exc:  # noqa: BLE001
            _log.warning("WC pinnacle fetch failed: %s", exc)

    season_hosts = HOST_COUNTRIES.get(season_resolved, {})
    preds: list[WcMatchPrediction] = []
    for fx in today_fx:
        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        pin = _pinnacle_lookup_with_aliases(home, away, pinnacle_lookup)
        raw = _predict_one_fixture(
            fx, model, elo, season_hosts, pinnacle_h2h=pin, alpha=alpha,
        )
        preds.append(WcMatchPrediction(**raw))

    return WcPredictionsResponse(
        date=on_iso,
        season=season_resolved,
        n_fixtures=len(preds),
        blend_alpha=alpha,
        elo_snapshot=snapshots[-1].name,
        host_country_hint=season_hosts,
        predictions=preds,
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
    )
