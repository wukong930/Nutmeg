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
            # stake_units = ¥ stake / ¥2 minimum (always whole)
            stake_units = int(stake // 2.0) if stake > 0 else 0
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
            stake_units = int(stake // 2.0)
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
