"""Record a recommend session into the observation DB.

Single entry point: `record_session(db_path, request, response)` that writes
the session, all single-match predictions, and all parlay recommendations
inside a transaction.
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
) -> int:
    """Write one recommend session to SQLite. Returns the session_id.

    `request` should be a dict equivalent to RecommendRequest (or what the
    CLI saw); `response` should be the recommend response dict (RecommendResponse).
    Both come straight from the API serialization layer.
    """
    model_info = response.get("model", {}) or {}
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
