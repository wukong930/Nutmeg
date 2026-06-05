"""Record a recommend session into the observation DB.

Four entry points:
- `record_session` — V4 / V6 W8 串关 (parlay) response shape
- `record_single_session` — V8 W6 单关 (single-leg) response shape
                            (Post-V8 P1#5)
- `record_pool_session` — V8 W6 复式 (compound pool) response shape
                          (Post-V8 P1#5)
- `record_wc_handicap_session` — V11 post-ship Path A++ WC 让球 shape

All four write to the same `recommendation_sessions` / `parlay_recommendations`
schema so V6 W8's `nutmeg-ab-report` and V4's `nutmeg-roi-report` see them
uniformly. Single tickets land as `k_legs=1, is_compound=False`; pool tickets
land as `k_legs=N, is_compound=True`. WC handicap tickets land per-outcome
as `k_legs=1, is_compound=False` with `league="WC"` so settlement picks them
up once a WC match outcome lands in `match_outcomes`.

⚠️ CRITICAL: ``stake_units`` semantics (2026-05-27 first-real-bet trap)
=======================================================================
``stake_units`` is the number of **atomic combinations** in the ticket,
NOT a Chinese-lottery multiplier (倍数). Hand-rolled response payloads
fed into ``record_session`` get this wrong on first try — including
the project author on the first real bet recorded into prod (2026-05-27).

Settlement (V4 W8) computes:
    unit_money    = kelly_stake / stake_units
    total_stake   = unit_money × stake_units  = kelly_stake  (always)
    total_payout  = n_winning_combos × unit_money × odds_product

Examples:

  ┌──────────────────────────────┬─────────────┬──────────────┬─────────┐
  │ Ticket                       │ stake_units │ kelly_stake  │ Real ¥  │
  ├──────────────────────────────┼─────────────┼──────────────┼─────────┤
  │ 单式 1 leg, ¥2               │     1       │      2.0     │  ¥2     │
  │ 单式 2 串 1, ¥2              │     1       │      2.0     │  ¥2     │
  │ 单式 2 串 1, **500 倍**      │     1       │   1000.0     │ ¥1000   │
  │ 复式 1 leg × 3 内选, ¥6      │     3       │      6.0     │  ¥6     │
  │ 复式 3 串 1, 2×2×2 = 8       │     8       │     16.0     │  ¥16    │
  └──────────────────────────────┴─────────────┴──────────────┴─────────┘

For 单式 with 倍数 multiplier: keep ``stake_units=1`` and put the full
real-money amount in ``kelly_stake``. The combo engine (combo/enumerate.py
``stake_units = product(leg.num_combinations())``) does this correctly for
auto-generated recommendations; the trap is only for manual recordings.

WRONG (fell into this 2026-05-27):
    stake_units = 500   # ← treating it as 倍数
    kelly_stake = 1000.0
    # unit_money = 2  →  payout = 2 × odds  ❌ pays 1/500 of real
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from nutmeg.v4.observation.store import (
    insert_parlay_recommendation,
    insert_session,
    insert_single_prediction,
    open_db,
)


def record_session(
    db_path: str | Path,
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """Write one recommend session to SQLite. Returns the session_id.

    `request` should be a dict equivalent to RecommendRequest (or what the
    CLI saw); `response` should be the recommend response dict (RecommendResponse).
    Both come straight from the API serialization layer.

    ``snapshot_phase`` defaults to "closing" (the legacy V4 behavior — recording
    at recommendation generation time which is usually shortly before kickoff).
    Set to "pre_close" when running a ≥60-min-before-kickoff capture, and
    "post_close" for after-the-fact diagnostic snapshots. See W8 docs.
    """
    model_info = response.get("model", {}) or {}
    model_type = model_info.get("model_type", "lightgbm")
    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=float(response.get("bankroll", 0.0)),
            model_cutoff=model_info.get("training_cutoff"),
            model_trained_at=model_info.get("trained_at_utc"),
            n_fixtures=int(response.get("n_fixtures", 0)),
            n_recommendations=int(response.get("n_recommendations", 0)),
            request=request,
            metadata={"model": model_info, "generated_at_utc": response.get("generated_at_utc")},
            snapshot_phase=snapshot_phase,
            model_type=model_type,
        )
        for p in response.get("single_match_predictions", []):
            insert_single_prediction(
                conn,
                session_id,
                match_date=str(p["date"]),
                league=p["league"],
                home_team=p["home_team"],
                away_team=p["away_team"],
                lambda_home=float(p["lambda_home"]),
                lambda_away=float(p["lambda_away"]),
                p_home_1x2=float(p["p_home_1x2"]),
                p_draw_1x2=float(p["p_draw_1x2"]),
                p_away_1x2=float(p["p_away_1x2"]),
                handicap_home=p.get("handicap_home"),
                p_home_handicap=p.get("p_home_handicap"),
                p_draw_handicap=p.get("p_draw_handicap"),
                p_away_handicap=p.get("p_away_handicap"),
            )
        for r in response.get("recommendations", []):
            insert_parlay_recommendation(
                conn,
                session_id,
                rank=int(r["rank"]),
                k_legs=int(r["k_legs"]),
                is_compound=bool(r["is_compound"]),
                stake_units=int(r["stake_units"]),
                kelly_stake=float(r["kelly_recommended_stake"]),
                expected_return=float(r["expected_return"]),
                hit_probability=float(r["hit_probability"]),
                ev_per_unit=float(r["ev_per_unit"]),
                log_growth=float(r["log_growth"]),
                legs=r["legs"],
            )
        return session_id


# ---------- Post-V8 P1#5: 单关 + 复式 session recorders ------------------

def record_single_session(
    db_path: str | Path,
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """Write a V8 W6 SingleRecommendResponse to the observation DB.

    Each ticket lands as one `parlay_recommendations` row with
    `k_legs=1, is_compound=False`. The leg's structure mirrors the V4
    串关 leg-json shape so V4 settlement (`_outcome_1x2` /
    `_outcome_handicap_1x2`) works without any change.

    `request` is the JSON-serializable SingleRecommendRequest dict;
    `response` is the SingleRecommendResponse dict.
    """
    model_info = response.get("model", {}) or {}
    model_type = model_info.get("model_type", "catboost")
    bankroll = float(response.get("bankroll", 0.0))

    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=bankroll,
            model_cutoff=model_info.get("training_cutoff"),
            model_trained_at=model_info.get("trained_at_utc"),
            n_fixtures=int(response.get("n_fixtures", 0)),
            n_recommendations=int(response.get("n_recommendations", 0)),
            request=request,
            metadata={
                "model": model_info,
                "generated_at_utc": response.get("generated_at_utc"),
                # P1#5: tag the session shape so AB reports can slice
                "session_kind": "single",
            },
            snapshot_phase=snapshot_phase,
            model_type=model_type,
        )
        for rank, ticket in enumerate(response.get("tickets", []), start=1):
            # Translate SingleTicketResponse → V4 leg-json shape
            leg = {
                "match_id":    ticket["match_id"],
                "market_type": ticket["market_type"],
                "selections": [{
                    "outcome":     ticket["outcome"],
                    "odds":        float(ticket["odds"]),
                    "probability": float(ticket["probability"]),
                    "edge":        float(ticket["ev_per_unit"]),
                }],
            }
            stake = float(ticket["stake"])
            # AUDIT FIX (B1): a 单关 ticket = exactly 1 atomic combo (1 leg, 1
            # selection) → stake_units MUST be 1 (= settlement's n_combos_total).
            # The old `int(stake//2)` (倍数) made unit_money = kelly_stake/(stake/2)
            # = ¥2, so a winning payout was unit_money×odds = 2×odds instead of
            # stake×odds — silently shrinking EVERY win by ~stake/2 while losses
            # stayed correct (total_stake = unit_money×stake_units = kelly_stake).
            stake_units = 1 if stake > 0 else 0
            insert_parlay_recommendation(
                conn,
                session_id,
                rank=rank,
                k_legs=1,
                is_compound=False,
                stake_units=stake_units,
                kelly_stake=stake,
                expected_return=float(ticket["expected_return"]),
                hit_probability=float(ticket["probability"]),
                ev_per_unit=float(ticket["ev_per_unit"]),
                log_growth=0.0,  # single-leg has no compounding log-growth
                legs=[leg],
            )
        return session_id


def record_parlay_session(
    db_path: str | Path,
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """V12 W5 — write a HAND-PICKED 串关 (ParlayRecordResponse) to the DB.

    Lands as ONE `parlay_recommendations` row (`k_legs=N, is_compound=False`),
    with each leg in the V4 串关 leg-json shape so V4 settlement
    (`_outcome_1x2` / `_outcome_handicap_1x2`) handles it identically to an
    engine-generated 单式 parlay. The leg's ``market_type`` is normalized to
    the settlement vocabulary (``handicap`` → ``handicap_1x2``) and handicap
    legs carry a leg-level ``handicap_home``.

    `request` is the JSON-serializable ParlayRecordRequest dict; `response`
    is the ParlayRecordResponse dict.
    """
    model_info = response.get("model", {}) or {}
    model_type = model_info.get("model_type", "catboost")
    bankroll = float(response.get("bankroll", 0.0))
    stake = float(response.get("stake", 0.0))

    legs: list[dict[str, Any]] = []
    for le in response.get("legs", []):
        market_type = "handicap_1x2" if le.get("market_type") == "handicap" else "1x2"
        sp = float(le["sp"])
        p = float(le["model_p"])
        leg: dict[str, Any] = {
            "match_id":    le["match_id"],
            "market_type": market_type,
            "selections": [{
                "outcome":     le["outcome"],
                "odds":        sp,
                "probability": p,
                "edge":        p - 1.0 / sp,
            }],
        }
        if le.get("handicap_home") is not None:
            leg["handicap_home"] = int(le["handicap_home"])
        legs.append(leg)

    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=bankroll,
            model_cutoff=model_info.get("training_cutoff"),
            model_trained_at=model_info.get("trained_at_utc"),
            n_fixtures=int(response.get("k_legs", len(legs))),
            n_recommendations=1,
            request=request,
            metadata={
                "model": model_info,
                "generated_at_utc": response.get("generated_at_utc"),
                "session_kind": "parlay",
            },
            snapshot_phase=snapshot_phase,
            model_type=model_type,
        )
        # Bridge rows: V4 settlement maps each leg's match_id → outcome via
        # single_predictions (keyed {league}_{home}_vs_{away}) and reads the
        # leg's handicap_home from here. Record one per leg's match.
        for p in response.get("single_match_predictions", []):
            insert_single_prediction(
                conn,
                session_id,
                match_date=str(p["date"]),
                league=p["league"],
                home_team=p["home_team"],
                away_team=p["away_team"],
                lambda_home=float(p["lambda_home"]),
                lambda_away=float(p["lambda_away"]),
                p_home_1x2=float(p["p_home_1x2"]),
                p_draw_1x2=float(p["p_draw_1x2"]),
                p_away_1x2=float(p["p_away_1x2"]),
                handicap_home=p.get("handicap_home"),
                p_home_handicap=p.get("p_home_handicap"),
                p_draw_handicap=p.get("p_draw_handicap"),
                p_away_handicap=p.get("p_away_handicap"),
            )
        insert_parlay_recommendation(
            conn,
            session_id,
            rank=1,
            k_legs=int(response.get("k_legs", len(legs))),
            is_compound=False,
            # AUDIT FIX (B1): a 串关 ticket = 1 atomic combo (all legs must hit)
            # → stake_units MUST be 1, not int(stake//2). See single-board note.
            stake_units=1 if stake > 0 else 0,
            kelly_stake=stake,
            expected_return=stake * float(response.get("ev_per_unit", 0.0)),
            hit_probability=float(response.get("hit_probability", 0.0)),
            ev_per_unit=float(response.get("ev_per_unit", 0.0)),
            log_growth=0.0,
            legs=legs,
        )
        return session_id


def record_wc_handicap_session(
    db_path: str | Path,
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """V11 post-ship — record a Path A++ WC handicap recommendation session.

    Each fixture's outcomes with ``stake > 0`` land as one
    ``parlay_recommendations`` row with ``k_legs=1, is_compound=False``.
    The leg ``match_id`` follows the ``"WC_<home>_vs_<away>"`` convention
    so the regular ``settle_unsettled`` pipeline picks it up once a
    ``match_outcomes`` row with ``league="WC"`` lands.

    Per-fixture ``single_predictions`` rows are also inserted (one per
    fixture, NOT per outcome) so the settler can resolve handicap_home
    from the leg's match_id lookup — same shape as `record_single_session`.

    Returns the session_id.
    """
    bankroll = float(response.get("bankroll", 0.0))
    blend_alpha = float(response.get("blend_alpha", 0.4))
    lambda_total_prior = float(response.get("lambda_total_prior", 2.6))
    n_recs = int(response.get("n_recommendations", 0))
    n_fixtures = int(response.get("n_fixtures", 0))

    # Build a minimal "model_info" so AB-report can slice by model_type.
    model_info = {
        "model_type": "national_team_handicap",
        "trained_at_utc": None,  # WC model retrains every request; not pinned
        "training_cutoff": None,
        "blend_alpha": blend_alpha,
        "lambda_total_prior": lambda_total_prior,
    }

    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=bankroll,
            model_cutoff=None,
            model_trained_at=None,
            n_fixtures=n_fixtures,
            n_recommendations=n_recs,
            request=request,
            metadata={
                "model": model_info,
                "generated_at_utc": response.get("generated_at_utc"),
                # Tag the session shape so reports can filter
                "session_kind": "wc_handicap",
                "blend_alpha": blend_alpha,
                "lambda_total_prior": lambda_total_prior,
            },
            snapshot_phase=snapshot_phase,
            model_type="national_team_handicap",
        )

        rank = 0
        for match in response.get("matches", []) or []:
            # ``kickoff_utc`` is ISO "YYYY-MM-DDTHH:MM:SS+TZ" — settle
            # reads match_date as the date portion of kickoff.
            kickoff = str(match.get("kickoff_utc", "") or "")
            match_date = kickoff[:10] if len(kickoff) >= 10 else ""
            home = str(match["home_team"])
            away = str(match["away_team"])
            handicap_home = int(match["handicap_home"])
            p_h, p_d, p_a = (
                float(match["p_1x2_blended"][0]),
                float(match["p_1x2_blended"][1]),
                float(match["p_1x2_blended"][2]),
            )
            # One single_prediction row per fixture (handicap_home pinned)
            insert_single_prediction(
                conn,
                session_id,
                match_date=match_date,
                league="WC",
                home_team=home,
                away_team=away,
                lambda_home=float(match.get("inferred_lambda_home", 0.0)),
                lambda_away=float(match.get("inferred_lambda_away", 0.0)),
                p_home_1x2=p_h,
                p_draw_1x2=p_d,
                p_away_1x2=p_a,
                handicap_home=handicap_home,
                p_home_handicap=float(match["outcomes"][0]["p_final"]),
                p_draw_handicap=float(match["outcomes"][1]["p_final"]),
                p_away_handicap=float(match["outcomes"][2]["p_final"]),
            )

            # One parlay_recommendations row per outcome with stake > 0
            match_id = f"WC_{home}_vs_{away}"
            for outcome in match.get("outcomes", []) or []:
                stake = float(outcome.get("stake", 0.0))
                if stake <= 0:
                    continue
                rank += 1
                leg = {
                    "match_id": match_id,
                    "market_type": "handicap_1x2",
                    "selections": [{
                        "outcome": outcome["outcome"],
                        "odds": float(outcome["odds"]),
                        "probability": float(outcome["p_final"]),
                        "edge": float(outcome["ev_per_unit"]),
                    }],
                }
                # ``stake_units`` follows the V4 convention: "number of
                # atomic combinations" (单式 = 1, 复式 = product of
                # selections per leg). A WC handicap pick is always 单式
                # (1 selection × 1 leg). The actual money stake lives in
                # ``kelly_stake``; settlement computes unit_money =
                # kelly_stake / stake_units = stake, so payout =
                # stake × odds — exactly what we want.
                stake_units = 1
                insert_parlay_recommendation(
                    conn,
                    session_id,
                    rank=rank,
                    k_legs=1,
                    is_compound=False,
                    stake_units=stake_units,
                    kelly_stake=stake,
                    expected_return=float(outcome["expected_return"]),
                    hit_probability=float(outcome["p_final"]),
                    ev_per_unit=float(outcome["ev_per_unit"]),
                    log_growth=0.0,
                    legs=[leg],
                )
        return session_id


def record_manual_bet(
    db_path: str | Path,
    *,
    bet: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """Record ONE user-chosen bet — the "记此注" path (Post-V13).

    Unlike the /recommend* endpoints (which record the MODEL's best +EV pick),
    this records EXACTLY the outcome + real stake the user actually placed,
    INCLUDING −EV: the observation DB is meant to track the user's real betting
    history so ROI is honest, not just the recommendations.

    Settlement-compatible by construction (mirrors record_wc_handicap_session):
    writes one ``single_predictions`` row (so ``settle_unsettled`` can resolve
    match_date + handicap_home from the match_id lookup) + one
    ``parlay_recommendations`` row with ``k_legs=1, is_compound=False,
    stake_units=1``; the real money lives in ``kelly_stake`` so payout =
    stake × odds (the 2026-05-27 stake_units trap — see module docstring).

    ``bet`` keys: league, match_date, home_team, away_team,
    market_type ("1x2" | "handicap"), handicap_home (int | None),
    outcome ("H"/"D"/"A"), odds (float, the 竞彩 SP), probability (float, model
    P, for EV), stake (float, real money), bankroll (float, optional).
    """
    league = str(bet["league"])
    match_date = str(bet["match_date"])
    home = str(bet["home_team"])
    away = str(bet["away_team"])
    is_hc = bet.get("market_type") == "handicap"
    handicap_home = (
        int(bet["handicap_home"])
        if is_hc and bet.get("handicap_home") is not None else None
    )
    outcome = str(bet["outcome"])
    odds = float(bet["odds"])
    p = float(bet.get("probability") or 0.0)
    stake = float(bet["stake"])
    if stake <= 0:
        raise ValueError("manual bet stake must be > 0")
    ev = p * odds - 1.0  # may be NEGATIVE — recorded anyway, on purpose

    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=float(bet.get("bankroll", 0.0)),
            model_cutoff=None,
            model_trained_at=None,
            n_fixtures=1,
            n_recommendations=1,
            request=bet,
            metadata={"session_kind": "manual_bet",
                      "model": {"model_type": "manual"}},
            snapshot_phase=snapshot_phase,
            model_type="manual",
        )
        # single_predictions row → settler resolves match_date + handicap_home.
        insert_single_prediction(
            conn, session_id,
            match_date=match_date, league=league,
            home_team=home, away_team=away,
            lambda_home=0.0, lambda_away=0.0,
            p_home_1x2=0.0, p_draw_1x2=0.0, p_away_1x2=0.0,
            handicap_home=handicap_home,
            p_home_handicap=(p if is_hc and outcome == "H" else None),
            p_draw_handicap=(p if is_hc and outcome == "D" else None),
            p_away_handicap=(p if is_hc and outcome == "A" else None),
        )
        leg = {
            "match_id": f"{league}_{home}_vs_{away}",
            "market_type": "handicap_1x2" if is_hc else "1x2",
            "selections": [{"outcome": outcome, "odds": odds,
                            "probability": p, "edge": ev}],
        }
        insert_parlay_recommendation(
            conn, session_id,
            rank=1, k_legs=1, is_compound=False,
            stake_units=1, kelly_stake=stake,
            expected_return=stake * p * odds,
            hit_probability=p, ev_per_unit=ev, log_growth=0.0,
            legs=[leg],
        )
        return session_id


_HC_IDX = {"H": 0, "D": 1, "A": 2}


def record_market_handicap_session(
    db_path: str | Path,
    *,
    league: str,
    match_date: str,
    home_team: str,
    away_team: str,
    handicap_home: int,
    p_handicap: tuple[float, float, float],
    p_1x2: tuple[float, float, float] | None,
    pick_outcome: str,
    pick_odds: float,
    pick_ev: float,
    pick_stake: float,
    pick_expected_return: float,
    bankroll: float,
    psc_1x2: tuple[float, float, float] | None = None,
    request: dict[str, Any] | None = None,
    snapshot_phase: str = "closing",
) -> int:
    """V12 W8 — record one 市场模式 让球 pick (J1 / cup) for tracking.

    The probability is the MARKET-IMPLIED handicap P (Dixon-Coles fit to the
    de-vig Pinnacle 1X2 + O/U), NOT the model — the model is OOD for these
    competitions. Tagged ``model_type="market_handicap"`` so AB/ROI reports
    slice it apart from model bets.

    Shape mirrors ``record_wc_handicap_session``: one ``single_predictions``
    row (handicap_home + handicap P pinned) + one ``parlay_recommendations``
    row (k_legs=1) with ``match_id="{league}_{home}_vs_{away}"`` so the regular
    ``settle_unsettled`` pipeline picks it up once the result lands. Returns
    the session_id.
    """
    if pick_outcome not in _HC_IDX:
        raise ValueError(f"pick_outcome must be H/D/A, got {pick_outcome!r}")
    p_pick = float(p_handicap[_HC_IDX[pick_outcome]])
    ph1, pd1, pa1 = (p_1x2 if p_1x2 is not None else (0.0, 0.0, 0.0))
    with open_db(db_path) as conn:
        session_id = insert_session(
            conn,
            bankroll=bankroll,
            model_cutoff=None,
            model_trained_at=None,
            n_fixtures=1,
            n_recommendations=1,
            request=request or {},
            metadata={
                "session_kind": "market_handicap",
                "model": {"model_type": "market_handicap"},
                "psc_1x2": list(psc_1x2) if psc_1x2 else None,
            },
            snapshot_phase=snapshot_phase,
            model_type="market_handicap",
        )
        insert_single_prediction(
            conn,
            session_id,
            match_date=match_date,
            league=league,
            home_team=home_team,
            away_team=away_team,
            lambda_home=0.0,
            lambda_away=0.0,
            p_home_1x2=float(ph1),
            p_draw_1x2=float(pd1),
            p_away_1x2=float(pa1),
            handicap_home=int(handicap_home),
            p_home_handicap=float(p_handicap[0]),
            p_draw_handicap=float(p_handicap[1]),
            p_away_handicap=float(p_handicap[2]),
        )
        leg = {
            "match_id": f"{league}_{home_team}_vs_{away_team}",
            "market_type": "handicap_1x2",
            "selections": [{
                "outcome": pick_outcome,
                "odds": float(pick_odds),
                "probability": p_pick,
                "edge": float(pick_ev),
            }],
        }
        insert_parlay_recommendation(
            conn,
            session_id,
            rank=1,
            k_legs=1,
            is_compound=False,
            stake_units=1,
            kelly_stake=float(pick_stake),
            expected_return=float(pick_expected_return),
            hit_probability=p_pick,
            ev_per_unit=float(pick_ev),
            log_growth=0.0,
            legs=[leg],
        )
        return session_id


def record_pool_session(
    db_path: str | Path,
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    snapshot_phase: str = "closing",
) -> int:
    """Write a V8 W6 PoolRecommendResponse to the observation DB.

    Each ticket lands as one `parlay_recommendations` row with
    `k_legs=N, is_compound=True`. Only tickets with `stake > 0` are
    recorded (zero-stake tickets are diagnostic-only and would clog
    settlement). The leg structure uses the V8 P1#5 PoolLegResponse
    (match_id + market_type included) so V4 settlement works directly.
    """
    model_info = response.get("model", {}) or {}
    model_type = model_info.get("model_type", "catboost")
    bankroll = float(response.get("bankroll", 0.0))

    with open_db(db_path) as conn:
        # n_recommendations = selected (stake > 0); n_fixtures = m (pool size)
        n_selected = int(response.get("n_selected", 0))
        session_id = insert_session(
            conn,
            bankroll=bankroll,
            model_cutoff=model_info.get("training_cutoff"),
            model_trained_at=model_info.get("trained_at_utc"),
            n_fixtures=int(response.get("m", 0)),
            n_recommendations=n_selected,
            request=request,
            metadata={
                "model": model_info,
                "generated_at_utc": response.get("generated_at_utc"),
                "session_kind": "pool",
                "pool_n": int(response.get("n", 0)),
                "pool_n_combinations": int(response.get("n_combinations", 0)),
            },
            snapshot_phase=snapshot_phase,
            model_type=model_type,
        )
        rank = 0
        for ticket in response.get("tickets", []):
            stake = float(ticket.get("stake", 0.0))
            if stake <= 0:
                continue  # skip diagnostic zero-stake tickets
            rank += 1
            legs_json = [
                {
                    "match_id":    leg["match_id"],
                    "market_type": leg["market_type"],
                    "selections": [{
                        "outcome":     leg["outcome"],
                        "odds":        float(leg["odds"]),
                        "probability": float(leg["probability"]),
                        "edge":        float(leg.get("edge", 0.0)),
                    }],
                }
                for leg in ticket["legs"]
            ]
            # AUDIT FIX (C2): each 复式 sub-ticket = 1 atomic combo
            # (single-selection legs) → stake_units MUST be 1, not int(stake//2)
            # (same shrink-every-win bug as the 单关/串关 recorders).
            stake_units = 1 if stake > 0 else 0
            insert_parlay_recommendation(
                conn,
                session_id,
                rank=rank,
                k_legs=len(legs_json),
                is_compound=True,
                stake_units=stake_units,
                kelly_stake=stake,
                expected_return=float(ticket["expected_return"]),
                hit_probability=float(ticket["hit_probability"]),
                ev_per_unit=float(ticket["ev_per_unit"]),
                log_growth=0.0,  # pool's log-growth is per-ticket; sum is the rec
                legs=legs_json,
            )
        return session_id
