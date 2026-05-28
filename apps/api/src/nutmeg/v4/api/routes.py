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
    PoolFixturePick,
    PoolLegResponse,
    PlayoffWarning,
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
    TodayRecommendationsDiff,
    TodayRecommendationsRequest,
    TodayRecommendationsResponse,
    TodaySummary,
    WcFixtureRecInput,
    WcRecommendationOutcome,
    WcSingleRecMatch,
    WcSingleRecRequest,
    WcSingleRecResponse,
    WcUpcomingPick,
    WcUpcomingResponse,
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


# V11 backlog #4 — Layer B: live_artifact_pointer.json redirect cache.
# When present at the base artifact dir, serving redirects to the
# Layer-B-deployed candidate dir without server restart. Mtime cache
# mirrors _load_correction(): re-reads when the pointer file changes.
_pointer_cache: dict[str, tuple[float, str | None]] = {}


def _artifact_path() -> str:
    """Resolve the effective artifact directory.

    Precedence:
      1. ``NUTMEG_V4_ARTIFACT_PATH`` env var → that path (existing V5 W11 behavior)
      2. ``live_artifact_pointer.json`` at the base dir → its target path
         (V11 backlog #4 Layer B)
      3. ``DEFAULT_ARTIFACT_PATH`` → fallback

    Layer B's pointer can redirect to ``data/v4_model_layer_b/v_2026-Q3/``;
    the redirect is mtime-cached so the next request post-deploy
    serves the new artifact without restart.
    """
    base = os.environ.get("NUTMEG_V4_ARTIFACT_PATH", DEFAULT_ARTIFACT_PATH)
    from nutmeg.v4.observation.auto_retrain import (
        LIVE_ARTIFACT_POINTER_FILENAME,
        load_artifact_pointer,
    )
    pointer_path = Path(base) / LIVE_ARTIFACT_POINTER_FILENAME
    try:
        mtime = pointer_path.stat().st_mtime
    except FileNotFoundError:
        _pointer_cache.pop(base, None)
        return base
    cached = _pointer_cache.get(base)
    if cached and cached[0] == mtime:
        return cached[1] or base
    pointer = load_artifact_pointer(base)
    if pointer is None:
        _pointer_cache[base] = (mtime, None)
        return base
    target = pointer.get("artifact_path")
    if target and Path(target).is_dir():
        _pointer_cache[base] = (mtime, target)
        return target
    _pointer_cache[base] = (mtime, None)
    return base


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
const CACHE_VERSION = 'nutmeg-v12-fe-w3-spcalc';
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


# ---------- /v4/team-logo/{slug} (V11 P1-FE#2 Day 2) -------------------

_TEAM_LOGOS_DIR = Path("data/external/team_logos")


@router.get("/team-logo/{slug}", include_in_schema=False)
def team_logo_endpoint(slug: str) -> Response:
    """Serve a cached team logo PNG.

    404 when the logo hasn't been ingested yet — the dashboard's
    ``<img onerror=...>`` then falls back to the 2-letter initials
    circle so a missing logo is never a user-visible defect.

    Slug format: lowercase + underscore (produced by ``team_slug()`` in
    ``nutmeg.v4.data.team_logos``).
    """
    # Defensive: only allow simple lowercase + underscore + digits to
    # prevent path traversal. Anything else → 404.
    import re as _re
    if not slug or not _re.fullmatch(r"[a-z0-9_]+", slug):
        raise HTTPException(status_code=404, detail="invalid slug")
    candidate = _TEAM_LOGOS_DIR / f"{slug}.png"
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="logo not cached")
    return Response(
        content=candidate.read_bytes(),
        media_type="image/png",
        # Logos rarely change — cache aggressively
        headers={"Cache-Control": "public, max-age=604800"},  # 7 days
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
        # V11 P1-FE#5 — per-rec fingerprint over its pick set
        from nutmeg.v4.observation.recommendation_version import (
            parlay_recommendation_fingerprint,
        )
        rec_resp = RecommendationResponse(
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
        )
        rec_resp.selection_fingerprint = parlay_recommendation_fingerprint(rec_resp)
        recommendations_out.append(rec_resp)

    # V11 P1-FE#5 — parlay top-level version_hash
    from nutmeg.v4.observation.recommendation_version import (
        version_hash as _vh,
        fixtures_odds_digest,
    )
    _parlay_top_hash = _vh(
        parlay_fingerprints=[r.selection_fingerprint for r in recommendations_out if r.selection_fingerprint],
        odds_digest=fixtures_odds_digest(req.fixtures),
    )
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
        version_hash=_parlay_top_hash,
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

    # V11 P1-FE#5 — stamp each ticket with its selection_fingerprint
    # so the frontend can diff against its prior view.
    from nutmeg.v4.observation.recommendation_version import (
        single_ticket_fingerprint,
        version_hash as _vh,
        fixtures_odds_digest,
    )
    tickets_out: list[SingleTicketResponse] = []
    for t in rec.selected_tickets:
        tk = SingleTicketResponse(
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
        tk.selection_fingerprint = single_ticket_fingerprint(tk)
        tickets_out.append(tk)
    _single_top_hash = _vh(
        single_fingerprints=[tk.selection_fingerprint for tk in tickets_out if tk.selection_fingerprint],
        odds_digest=fixtures_odds_digest(req.fixtures),
    )

    response = SingleRecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=len(tickets_out),
        tickets=tickets_out,
        total_stake=float(rec.total_stake),
        total_expected_return=float(rec.total_expected_return),
        version_hash=_single_top_hash,
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

    # V11 P1-FE#5 — pool tickets get per-ticket fingerprints
    from nutmeg.v4.observation.recommendation_version import (
        pool_ticket_fingerprint,
        version_hash as _vh,
        fixtures_odds_digest,
    )
    tickets_out: list[PoolTicketResponse] = []
    for t in rec.tickets:
        tk = PoolTicketResponse(
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
        tk.selection_fingerprint = pool_ticket_fingerprint(tk)
        tickets_out.append(tk)

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
        version_hash=_vh(
            pool_fingerprints=[tk.selection_fingerprint for tk in tickets_out if tk.selection_fingerprint and tk.stake > 0],
            odds_digest=fixtures_odds_digest(req.fixtures),
        ),
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

    V11 P1-FE#4 — pool option is now included by default. Strategy B
    (locked 2026-05-25 in docs/v11_p1_fe_design.md): for each fixture
    that passes the EV gate, pick the max-EV market; then build C(M, N)
    pool of size N=req.pool_n. min_ev gate + risk_preference→Kelly map
    are applied to all three pipelines (single/parlay/pool).
    """
    import datetime as _dt
    from pathlib import Path as _Path

    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
    )

    # V11 P1-FE#4 — risk dial → Kelly fraction. The explicit
    # `kelly_fraction` field acts as an override: when the caller leaves
    # it at the default 0.25 we map from risk_preference; if it's been
    # set to anything else (e.g. via the engineer CLI) we honor that.
    _RISK_TO_KELLY = {
        "conservative": 0.15,
        "balanced": 0.25,
        "aggressive": 0.40,
    }
    if abs(req.kelly_fraction - 0.25) < 1e-9:
        effective_kelly = _RISK_TO_KELLY[req.risk_preference]
    else:
        effective_kelly = req.kelly_fraction

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

    # Fetch fixtures (uses API-Football; will use cache if available).
    # V12 W0 (2026-05-28) — auto-filter fixtures that have already kicked
    # off (or are about to in next 5 min). This is what makes the morning
    # + afternoon cron waves produce different optimal sets, AND what
    # keeps the dashboard showing the *current* state (e.g., at 16:00
    # J1 matches are filtered out because they're done).
    try:
        rows, _n_calls, _n_skipped = _gather_rows(
            req.leagues,
            on_date,
            cache_dir=_Path("data/external/api_football"),
            bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False,
            refresh_odds=False,
            min_kickoff_buffer_minutes=5,
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

    # V12 W3 — model P(H/D/A) + Pinnacle odds for ALL fetched fixtures, so the
    # dashboard's 竞彩 SP calculator can compute live EV (P × 竞彩SP − 1) against
    # user-entered 竞彩 odds, not just the gate-passing tickets in `single`.
    # (One extra inference pass; acceptable for a local single-user dashboard.
    # Could be shared with the single/parlay/pool sub-calls in a later refactor.)
    single_match_predictions: list[SinglePrediction] = []
    if fixtures_fetched > 0:
        try:
            _art = get_artifact()
            if _art is not None:
                _fdf = _fixtures_to_dataframe(fixtures)
                _lambdas = predict_lambdas(_art, build_features_for_fixtures(_art, _fdf))
                _rho = float(_art.metadata.get("gbm_rho", -0.10))
                _corr = _load_correction()
                for _i, _f in enumerate(fixtures):
                    _lh, _la = _lambdas[_i]
                    _grid = score_grid(_lh, _la, rho=_rho)
                    _ph, _pd, _pa = tuple(
                        apply_correction_to_probs(np.array(grid_to_1x2(_grid)), _corr)
                    )
                    single_match_predictions.append(SinglePrediction(
                        home_team=_f.home_team, away_team=_f.away_team,
                        league=_f.league, date=_f.date,
                        lambda_home=float(_lh), lambda_away=float(_la),
                        p_home_1x2=float(_ph), p_draw_1x2=float(_pd), p_away_1x2=float(_pa),
                        psc_home=_f.psc_home, psc_draw=_f.psc_draw, psc_away=_f.psc_away,
                    ))
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: single_match_predictions pass failed",
            )
            single_match_predictions = []

    # V12 W0 (2026-05-27) — flag fixtures in known playoff/barrage windows.
    # Model has no playoff feature; dashboard renders these as ⚠️ banner.
    # See apps/api/src/nutmeg/v4/data/playoff_context.py
    from nutmeg.v4.data.playoff_context import detect_playoff

    playoff_warnings: list[PlayoffWarning] = []
    for f in fixtures:
        w = detect_playoff(f.league, f.date)
        if w is None:
            continue
        # f.date may be a datetime.date (Pydantic-parsed from ISO string);
        # coerce to ISO string for the response model.
        _date_str = f.date.isoformat() if hasattr(f.date, "isoformat") else str(f.date)
        playoff_warnings.append(PlayoffWarning(
            league=f.league,
            home_team=f.home_team,
            away_team=f.away_team,
            date=_date_str,
            context=w.context,
            model_bias_note=w.model_bias_note,
        ))

    single_resp: SingleRecommendResponse | None = None
    parlay_resp: RecommendResponse | None = None
    pool_resp: PoolRecommendResponse | None = None
    total_recs = 0
    total_stake = 0.0
    stake_weighted_ev_sum = 0.0

    if fixtures_fetched > 0 and "single" in req.include:
        try:
            single_req = SingleRecommendRequest(
                fixtures=fixtures,
                bankroll=req.bankroll,
                kelly_fraction=effective_kelly,
                record_session=req.record_session,
            )
            single_resp = recommend_single(single_req)
            # V11 P1-FE#4 — min_ev gate (single)
            if single_resp.n_recommendations > 0 and req.min_ev > 0:
                kept = [t for t in single_resp.tickets if t.ev_per_unit >= req.min_ev]
                single_resp.tickets = kept
                single_resp.n_recommendations = len(kept)
                single_resp.total_stake = float(sum(t.stake for t in kept))
                single_resp.total_expected_return = float(sum(t.expected_return for t in kept))
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
                kelly_fraction=effective_kelly,
                include_compound=False,
                record_session=req.record_session,
            )
            parlay_resp = recommend(parlay_req)
            # V11 P1-FE#4 — min_ev gate (parlay)
            if parlay_resp.n_recommendations > 0 and req.min_ev > 0:
                kept = [r for r in parlay_resp.recommendations if r.ev_per_unit >= req.min_ev]
                parlay_resp.recommendations = kept
                parlay_resp.n_recommendations = len(kept)
                parlay_resp.total_stake = float(sum(r.stake_units for r in kept))
            if parlay_resp.n_recommendations > 0:
                total_recs += parlay_resp.n_recommendations
                total_stake += parlay_resp.total_stake
                for r in parlay_resp.recommendations:
                    stake_weighted_ev_sum += r.stake_units * 1.0 * r.ev_per_unit
            else:
                parlay_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: parlay pipeline failed",
            )
            parlay_resp = None

    # V11 P1-FE#4 — pool (Strategy B: auto-pick max-EV market per fixture)
    if fixtures_fetched >= req.pool_n and "pool" in req.include:
        try:
            pool_resp = _build_today_pool(
                fixtures=fixtures,
                bankroll=req.bankroll,
                kelly_fraction=effective_kelly,
                min_ev=req.min_ev,
                pool_n=req.pool_n,
                record_session=req.record_session,
            )
            if pool_resp is not None and pool_resp.n_selected > 0:
                total_recs += pool_resp.n_selected
                total_stake += pool_resp.total_stake
                for t in pool_resp.tickets:
                    if t.stake > 0:
                        stake_weighted_ev_sum += t.stake * t.ev_per_unit
            else:
                pool_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: pool pipeline failed",
            )
            pool_resp = None

    # V11 post-ship — WC 1X2 informational block.
    # Reuses /predictions/wc internally; surfaces today's WC fixtures so
    # the user doesn't need to switch tabs to see what's on. The user
    # still goes to the 🏆 WC tab to enter handicap SP for actual
    # recommendations (which then post to /recommend/wc/single). WC is
    # purely informational here — doesn't count toward total_recs / stake.
    wc_resp: WcPredictionsResponse | None = None
    if "wc" in req.include:
        try:
            wc_resp = predictions_wc(
                date=on_date.isoformat(),
                fetch_current_odds=False,  # don't burn Odds API quota in today loop
                alpha=0.4,
            )
            if not wc_resp or wc_resp.n_fixtures == 0:
                wc_resp = None
        except HTTPException as exc:
            # 503 when WC training data / eloratings missing — degrade
            # gracefully (today endpoint shouldn't fail because WC infra
            # is incomplete; the rest still works).
            import logging
            logging.getLogger(__name__).info(
                "today-recommendations: WC block unavailable (%s)", exc.detail,
            )
            wc_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: WC block failed",
            )
            wc_resp = None

    weighted_ev = (stake_weighted_ev_sum / total_stake) if total_stake > 0 else None

    # V11 P1-FE#5 — top-level version_hash + optional diff vs prev_version.
    # Combines fingerprints from all three pipelines + the odds digest.
    from nutmeg.v4.observation.recommendation_version import (
        version_hash as _vh,
        fixtures_odds_digest,
    )
    _single_fps  = [t.selection_fingerprint for t in (single_resp.tickets if single_resp else []) if t.selection_fingerprint]
    _parlay_fps  = [r.selection_fingerprint for r in (parlay_resp.recommendations if parlay_resp else []) if r.selection_fingerprint]
    _pool_fps    = [t.selection_fingerprint for t in (pool_resp.tickets if pool_resp else []) if t.selection_fingerprint and t.stake > 0]
    _odds_digest = fixtures_odds_digest(fixtures)
    _top_hash = _vh(
        single_fingerprints=_single_fps,
        parlay_fingerprints=_parlay_fps,
        pool_fingerprints=_pool_fps,
        odds_digest=_odds_digest,
    )

    # If the client sent a prev_version and it differs, surface a diff
    # block. We can't compute added/removed server-side because the
    # client's prior fingerprint set isn't echoed back — the frontend
    # owns the per-rec diff (it has the prior set in localStorage and
    # compares against the new selection_fingerprints inline).
    # Server's role: confirm "yes, version moved" + a one-line summary.
    diff_block: TodayRecommendationsDiff | None = None
    if req.prev_version and req.prev_version != _top_hash:
        cur_set = set(_single_fps + _parlay_fps + _pool_fps)
        diff_block = TodayRecommendationsDiff(
            prev_version=req.prev_version,
            current_version=_top_hash,
            odds_changed=False,  # frontend infers from rec-level fp comparison
            added_fingerprints=sorted(cur_set),
            removed_fingerprints=[],
            summary="推荐已更新",
        )

    return TodayRecommendationsResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date=on_date.isoformat(),
        leagues=req.leagues,
        bankroll=req.bankroll,
        fixtures_fetched=fixtures_fetched,
        single=single_resp,
        parlay=parlay_resp,
        pool=pool_resp,
        wc=wc_resp,
        summary=TodaySummary(
            total_recs=total_recs,
            total_stake=total_stake,
            weighted_ev=weighted_ev,
        ),
        version_hash=_top_hash,
        diff=diff_block,
        playoff_warnings=playoff_warnings,
        single_match_predictions=single_match_predictions,
    )


# ---------- helper: today-recommendations pool builder ------------------

# V11 P1-FE#4 Strategy B (locked 2026-05-25):
#   1. Run /recommend/single on all fixtures with top_per_match=1 so each
#      fixture yields its single max-EV pick.
#   2. Filter to ev_per_unit ≥ min_ev. If fewer than pool_n remain, return None.
#   3. Convert each surviving pick → PoolFixturePick (with the pick field
#      derived from market_type + outcome).
#   4. Call recommend_pool_endpoint with N=pool_n. The pool ticket set
#      is fully enumerated (C(M, N)) inside that engine.
_OUTCOME_TO_POOL_PICK: dict[tuple[str, str], str] = {
    ("1x2", "H"):          "1x2_H",
    ("1x2", "D"):          "1x2_D",
    ("1x2", "A"):          "1x2_A",
    ("handicap_1x2", "H"): "hc_H",
    ("handicap_1x2", "D"): "hc_D",
    ("handicap_1x2", "A"): "hc_A",
}


def _build_today_pool(
    *,
    fixtures: list[FixtureOddsInput],
    bankroll: float,
    kelly_fraction: float,
    min_ev: float,
    pool_n: int,
    record_session: bool,
) -> PoolRecommendResponse | None:
    """Run Strategy B and return a PoolRecommendResponse, or None if there
    aren't enough +EV fixtures to form an N-leg pool."""
    if len(fixtures) < pool_n:
        return None

    # 1+2. Get one max-EV pick per fixture (top_per_match=1) then filter
    single_resp = recommend_single(SingleRecommendRequest(
        fixtures=fixtures,
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        top_per_match=1,
        record_session=False,  # don't double-record; today endpoint records its own intent
    ))
    if single_resp.n_recommendations < pool_n:
        return None
    picks = [t for t in single_resp.tickets if t.ev_per_unit >= min_ev]
    if len(picks) < pool_n:
        return None

    # 3. Build PoolFixturePick rows from the surviving picks.
    by_match: dict[str, FixtureOddsInput] = {
        f"{f.league}_{f.home_team}_vs_{f.away_team}": f for f in fixtures
    }
    pool_fixtures: list[PoolFixturePick] = []
    for t in picks:
        f = by_match.get(t.match_id)
        if f is None:
            continue
        pick_str = _OUTCOME_TO_POOL_PICK.get((t.market_type, t.outcome))
        if pick_str is None:
            continue
        pool_fixtures.append(PoolFixturePick(
            **f.model_dump(),
            pick=pick_str,
        ))
    if len(pool_fixtures) < pool_n:
        return None

    # 4. Pool engine — N legs across the M picks
    pool_req = PoolRecommendRequest(
        fixtures=pool_fixtures,
        n=pool_n,
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        record_session=record_session,
    )
    return recommend_pool_endpoint(pool_req)


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


# ---------- /predictions/wc-upcoming (V12 W0 — 2026-05-28) --------------

@router.get(
    "/predictions/wc-upcoming",
    response_model=WcUpcomingResponse,
    summary="V12 W0 — top-N WC single-leg picks across the next N days, sorted by hit rate",
)
def predictions_wc_upcoming(
    days: int = 5,
    top_n: int = 5,
    fetch_current_odds: bool = True,
    min_ev: float = 0.05,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
    alpha: float = 0.4,
) -> WcUpcomingResponse:
    """V12 W0 (2026-05-28) — lookahead WC picker.

    User feedback: a single day of WC has 4-6 matches, often not enough
    for combo enumeration. But across a 5-day window we have ~20-30
    matches, plenty of single-leg candidates.

    For each fixture in `[today, today + days - 1]`:
      1. Train/load NationalTeamModel
      2. Predict 1X2 probabilities (Elo + Pinnacle blend if available)
      3. Compute EV per outcome: ``model_P × SP - 1``
      4. Keep outcomes with ``ev_per_unit >= min_ev``
      5. Compute Kelly stake: ``bankroll × kelly_fraction × edge / (SP - 1)``

    Sort all surviving picks by ``hit_probability`` descending,
    return ``top_n``.

    Parameters
    ----------
    days : Look-ahead window in days (1-14, default 5). >=14 raises 422
        — anything longer is pre-tournament wishful thinking.
    top_n : Number of picks to return (1-20, default 5).
    fetch_current_odds : Pull live Pinnacle WC odds from The Odds API
        (~10 quota per request). Default True because EV needs SP.
    min_ev : EV per unit gate (default +5%, same as JINGCAI_DEFAULT).
    bankroll : Budget for Kelly sizing.
    kelly_fraction : Kelly fraction (0.15 / 0.25 / 0.40 standard).
    alpha : Blend weight (default 0.4 per V10 W1 Track B Day 3 verdict).

    Phase 1 scope (this endpoint):
      - 1X2 outcomes only (H / D / A)
      - No handicap (let user use the existing per-match Path A++ form)
      - No parlay / pool (V8 W4 cup ablation NEGATIVE — multi-leg in WC
        compounds errors; user previously locked "WC 单关 only")
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    # Validate
    if not 1 <= days <= 14:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be in [1, 14]",
        )
    if not 1 <= top_n <= 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="top_n must be in [1, 20]",
        )

    today = _dt.date.today()
    date_end = today + _dt.timedelta(days=days - 1)

    # Local imports (avoid top-level cost)
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
            detail="No eloratings snapshot found.",
        )

    # Train model once (covers all fixtures in window)
    try:
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}",
        )

    elo = load_elo_snapshot(snapshots[-1])
    season_resolved = today.year  # assume WC is in current year (2026)
    season_hosts = HOST_COUNTRIES.get(season_resolved, {})

    # Fetch all WC fixtures for the season once, then filter by date
    try:
        all_fx = fetch_fixtures_for_league_season("WC", season_resolved)
    except Exception as exc:  # noqa: BLE001
        _log.warning("WC fixture fetch failed: %s", exc)
        all_fx = []

    # Filter to date window
    window_iso_prefixes = [
        (today + _dt.timedelta(days=i)).isoformat()
        for i in range(days)
    ]
    in_window_fx = [
        f for f in all_fx
        if any(
            f.get("fixture", {}).get("date", "").startswith(p)
            for p in window_iso_prefixes
        )
    ]

    # Build Pinnacle lookup per-day if requested (each day = 1 Odds API call)
    pinnacle_lookups_by_day: dict[str, dict] = {}
    if fetch_current_odds and in_window_fx:
        for i in range(days):
            d = today + _dt.timedelta(days=i)
            try:
                pinnacle_lookups_by_day[d.isoformat()] = (
                    _build_pinnacle_lookup_for_date(d)
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Pinnacle fetch failed for %s: %s", d, exc)
                pinnacle_lookups_by_day[d.isoformat()] = {}

    # Iterate fixtures, compute single-leg picks
    picks: list[WcUpcomingPick] = []
    for fx in in_window_fx:
        iso_date = fx.get("fixture", {}).get("date", "")
        if not iso_date:
            continue
        day_key = iso_date[:10]
        day_lookup = pinnacle_lookups_by_day.get(day_key, {})

        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        pin = _pinnacle_lookup_with_aliases(home, away, day_lookup) if day_lookup else None

        try:
            raw = _predict_one_fixture(
                fx, model, elo, season_hosts, pinnacle_h2h=pin, alpha=alpha,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("predict failed for fixture %s: %s", fx.get("fixture", {}).get("id"), exc)
            continue

        # Compute days_until_kickoff
        try:
            kickoff_dt = _dt.datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            days_until = (kickoff_dt.date() - today).days
        except Exception:  # noqa: BLE001
            days_until = 0

        # Only score outcomes where Pinnacle SP exists (need SP for EV)
        if not raw.get("has_pinnacle"):
            continue

        # Build picks for each of H / D / A
        for outcome, p_key, sp_key in [
            ("H", "p_home", "psc_home"),
            ("D", "p_draw", "psc_draw"),
            ("A", "p_away", "psc_away"),
        ]:
            p = float(raw[p_key])
            sp = float(raw[sp_key])
            ev = p * sp - 1.0  # ev IS the edge here (p·SP − 1)
            if ev < min_ev:
                continue
            # Kelly fractional stake. The ev>=min_ev gate above already
            # implies ev>0; the sp<=1.0 guard covers degenerate odds.
            if sp <= 1.0 or ev <= 0:
                stake = 0.0
            else:
                kelly_full = ev / (sp - 1.0)
                stake = round(bankroll * kelly_fraction * kelly_full, 2)
            picks.append(WcUpcomingPick(
                fixture_id=raw["fixture_id"],
                kickoff_utc=raw["kickoff_utc"],
                days_until_kickoff=days_until,
                home_team=home,
                away_team=away,
                outcome=outcome,
                hit_probability=p,
                odds=sp,
                ev_per_unit=ev,
                stake=stake,
                source=raw["source"],
            ))

    # Sort by hit_probability descending, take top_n
    picks.sort(key=lambda p: p.hit_probability, reverse=True)
    top_picks = picks[:top_n]

    return WcUpcomingResponse(
        date_start=today.isoformat(),
        date_end=date_end.isoformat(),
        days=days,
        n_fixtures_scanned=len(in_window_fx),
        n_picks_after_ev_gate=len(picks),
        picks=top_picks,
        blend_alpha=alpha,
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
    )


# ---------- /recommend/wc/single (V11 post-ship — Path A++ hybrid) -------

@router.post(
    "/recommend/wc/single",
    response_model=WcSingleRecResponse,
    summary="WC integer-handicap recommendations (Path A++: 1X2 reverse-map + DC + market blend)",
)
def recommend_wc_single(req: WcSingleRecRequest) -> WcSingleRecResponse:
    """V11 post-ship — bridges NationalTeamModel (1X2) to the 竞彩 整数让球
    market via Path A++ hybrid:

      1. NationalTeamModel.predict_proba → 1X2 model probs
      2. Blend with user-provided Pinnacle 1X2 (α = req.blend_alpha)
      3. Reverse-map blended 1X2 → (λ_h, λ_a) under WC mean λ_total prior
      4. DC score grid → model handicap probs (让胜 / 让平 / 让负)
      5. Dewedge user 竞彩 SP → market handicap probs
      6. Bayesian blend model HC + market HC at α = req.blend_alpha
      7. Per-outcome EV + Kelly → ¥2-quantized stake, gated by req.min_ev

    The 1X2 blend and the handicap blend reuse the same α; this is
    intentional — both are model-vs-Pinnacle and the WC convention is 0.4.

    Returns one ``WcSingleRecMatch`` per fixture, each carrying 3 outcomes
    (H/D/A on the let-line) with diagnostics + stake. Outcomes whose EV is
    below ``req.min_ev`` are surfaced with stake=0 (kept for transparency
    on the dashboard).

    Graceful degradation
    --------------------
    - eloratings snapshot missing      → 503
    - WC training data missing         → 503
    - NationalTeamModel fit fails      → 503
    - Per-fixture errors (e.g. unknown team) → matches[].outcomes is empty
      with diagnostic fields zeroed; the rest of the request continues.
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    # Local imports — avoid top-level cost on cold start / non-WC routes.
    try:
        from nutmeg.v4.cli.wc_predict import (
            HOST_COUNTRIES,
            _train_combined_model,
        )
        from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
        from nutmeg.v4.data.wc_training_frame import load_elo_snapshot
        from nutmeg.v4.model.national_team_handicap import (
            DEFAULT_WC_LAMBDA_TOTAL,
            evaluate_handicap_market,
        )
        from nutmeg.v4.model.national_team_predict import (
            bayesian_blend,
            market_implied_probs,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC recommendation module not loadable: {exc}",
        )

    # Lottery rules — for stake quantization + cap.
    from nutmeg.v4.combo.compound_pool import quantize_stake
    from nutmeg.v4.combo.kelly import fractional_kelly_stake
    from nutmeg.v4.combo.lottery_rules import (
        JINGCAI_DEFAULT,
        cap_ticket_stake,
    )

    snapshots = sorted(
        _Path("data/external/eloratings").glob("eloratings_*.parquet")
    )
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eloratings snapshot found at data/external/eloratings/. "
                   "Run the eloratings scraper first (see v10_w1_day2_*.md).",
        )

    try:
        # Use 2018 hosts as default training-time hint (matches predictions_wc).
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}. "
                   "Run nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022",
        )

    elo = load_elo_snapshot(snapshots[-1])
    rules = JINGCAI_DEFAULT

    # Optional host-country override (e.g. 'USA' for WC 2026).
    user_hosts: dict[str, float] = {}
    if req.host_country:
        user_hosts[req.host_country] = req.host_advantage

    matches: list[WcSingleRecMatch] = []
    total_stake = 0.0
    total_expected_return = 0.0
    n_recs = 0

    for fx in req.fixtures:
        # ----- Per-fixture model 1X2 -----
        h_code = lookup_elo_code(fx.home_team)
        a_code = lookup_elo_code(fx.away_team)
        h_elo = float(elo.get(h_code, {}).get("elo", 1500.0)) if h_code else 1500.0
        a_elo = float(elo.get(a_code, {}).get("elo", 1500.0)) if a_code else 1500.0

        # Per-row host hint: if user named a host, treat fixture's home team
        # as host when its name matches the user_hosts key OR fall back to
        # season-hint convention (use_hosts lookup only if home matches).
        is_host = fx.home_team in user_hosts
        home_adv = user_hosts.get(fx.home_team, 0.0) if is_host else 0.0

        df = pd.DataFrame([{
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "home_elo": h_elo,
            "away_elo": a_elo,
            "psc_home": fx.psc_home,
            "psc_draw": fx.psc_draw,
            "psc_away": fx.psc_away,
        }])

        try:
            lgb_probs = model.predict_proba(
                df,
                host_country=fx.home_team if is_host else None,
                host_advantage=home_adv if is_host else 0.0,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "WC recommend: predict_proba failed for %s vs %s: %s",
                fx.home_team, fx.away_team, exc,
            )
            matches.append(WcSingleRecMatch(
                fixture_id=fx.fixture_id,
                home_team=fx.home_team,
                away_team=fx.away_team,
                kickoff_utc=fx.kickoff_utc,
                handicap_home=fx.handicap_home,
                p_1x2_blended=[0.0, 0.0, 0.0],
                inferred_lambda_home=0.0,
                inferred_lambda_away=0.0,
                outcomes=[],
            ))
            continue

        # ----- Blend with user-provided Pinnacle 1X2 -----
        pin_probs = market_implied_probs(
            pd.Series([fx.psc_home]),
            pd.Series([fx.psc_draw]),
            pd.Series([fx.psc_away]),
        )
        blended_1x2 = bayesian_blend(lgb_probs, pin_probs, alpha=req.blend_alpha)[0]
        p_h, p_d, p_a = float(blended_1x2[0]), float(blended_1x2[1]), float(blended_1x2[2])

        # ----- Path A++ handicap evaluation -----
        try:
            rec = evaluate_handicap_market(
                p_h, p_d, p_a,
                fx.handicap_home,
                fx.odds_handicap_H, fx.odds_handicap_D, fx.odds_handicap_A,
                blend_alpha=req.blend_alpha,
                lambda_total_prior=DEFAULT_WC_LAMBDA_TOTAL,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "WC recommend: handicap evaluation failed for %s vs %s @ HC %+d: %s",
                fx.home_team, fx.away_team, fx.handicap_home, exc,
            )
            matches.append(WcSingleRecMatch(
                fixture_id=fx.fixture_id,
                home_team=fx.home_team,
                away_team=fx.away_team,
                kickoff_utc=fx.kickoff_utc,
                handicap_home=fx.handicap_home,
                p_1x2_blended=[p_h, p_d, p_a],
                inferred_lambda_home=0.0,
                inferred_lambda_away=0.0,
                outcomes=[],
            ))
            continue

        # ----- EV gate + Kelly per outcome -----
        outcomes_out: list[WcRecommendationOutcome] = []
        labels = ("H", "D", "A")
        # Market p_market is NaN-tuple when no SP — surface as None.
        p_market_tuple: tuple[Optional[float], Optional[float], Optional[float]] = (
            None if np.isnan(rec.p_market_hc[0]) else float(rec.p_market_hc[0]),
            None if np.isnan(rec.p_market_hc[1]) else float(rec.p_market_hc[1]),
            None if np.isnan(rec.p_market_hc[2]) else float(rec.p_market_hc[2]),
        )
        for i, label in enumerate(labels):
            p_final_i = float(rec.p_final_hc[i])
            p_model_i = float(rec.p_model_hc[i])
            ev_i = float(rec.ev_per_unit[i])
            odds_i = float(rec.odds_hc[i])
            full_kelly_i = float(rec.kelly_fraction[i])

            if ev_i < req.min_ev:
                # Below EV gate — surface diagnostics, no stake.
                stake_i = 0.0
                er_i = 0.0
            else:
                kr = fractional_kelly_stake(
                    hit_probability=p_final_i,
                    ev_per_unit=ev_i,
                    bankroll=req.bankroll,
                    kelly_fraction=req.kelly_fraction,
                    max_stake_fraction=req.max_stake_fraction,
                )
                capped = cap_ticket_stake(kr.recommended_stake, rules)
                stake_i = float(quantize_stake(capped, rules.stake_unit))
                er_i = stake_i * ev_i

            if stake_i > 0:
                n_recs += 1
                total_stake += stake_i
                total_expected_return += er_i

            outcomes_out.append(WcRecommendationOutcome(
                outcome=label,
                p_final=p_final_i,
                p_model=p_model_i,
                p_market=p_market_tuple[i],
                odds=odds_i,
                ev_per_unit=ev_i,
                kelly_fraction=full_kelly_i,
                stake=stake_i,
                expected_return=er_i,
            ))

        matches.append(WcSingleRecMatch(
            fixture_id=fx.fixture_id,
            home_team=fx.home_team,
            away_team=fx.away_team,
            kickoff_utc=fx.kickoff_utc,
            handicap_home=fx.handicap_home,
            p_1x2_blended=[p_h, p_d, p_a],
            inferred_lambda_home=float(rec.inferred_lambda_home),
            inferred_lambda_away=float(rec.inferred_lambda_away),
            outcomes=outcomes_out,
        ))

    response = WcSingleRecResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=n_recs,
        matches=matches,
        total_stake=total_stake,
        total_expected_return=total_expected_return,
        blend_alpha=req.blend_alpha,
        lambda_total_prior=DEFAULT_WC_LAMBDA_TOTAL,
    )

    # V11 post-ship — A/B observation hook. Both gates required:
    # server env NUTMEG_V4_OBSERVATION_DB set + request record_session=True.
    # Only fixtures with at least one stake>0 outcome land in the DB.
    db_path = _should_record_session(req.record_session)
    if db_path and n_recs > 0:
        from nutmeg.v4.observation.recorder import record_wc_handicap_session
        try:
            record_wc_handicap_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_wc_handicap_session failed (db=%s); rec returned anyway",
                db_path,
            )
    return response
