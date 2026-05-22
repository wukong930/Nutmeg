"""Settle parlay recommendations against recorded match outcomes.

For each unsettled recommendation, decide if it "hit" or "miss" based on
the actual outcomes of each leg's match:

  - 1X2 leg: hit iff actual_outcome ∈ leg.selections.outcome (复式)
             or actual_outcome == leg.selections[0].outcome (单式)
  - handicap_1x2 leg: hit iff actual_outcome_under_handicap ∈ leg.selections
             where actual_outcome_under_handicap is computed from
             (home_goals + handicap_home) vs away_goals.

Stake = stake_units × 1 unit money (we use kelly_stake / stake_units as the
unit money so that profit/loss is in real currency). If any leg's outcome
is unknown (no match_outcome row), the recommendation stays unsettled.

A 复式 ticket can have a partial hit if ONE atomic combination wins;
in that case profit = atomic combo payout - total stake.
"""
from __future__ import annotations

import json
from itertools import product
from typing import Any

from nutmeg.v4.observation.store import (
    get_outcome,
    insert_settlement,
    list_unsettled_recommendations,
)


def _outcome_1x2(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _outcome_handicap_1x2(home_goals: int, away_goals: int, handicap_home: int) -> str:
    diff = (home_goals + handicap_home) - away_goals
    if diff > 0:
        return "H"
    if diff < 0:
        return "A"
    return "D"


def _resolve_leg_atomic_outcomes(
    leg: dict, outcomes_by_match: dict[str, dict],
) -> dict[str, Any]:
    """Return which atomic outcomes (per leg) match the actual result.

    Returns dict with:
      known: bool — whether we have the actual match outcome
      actual_outcome: 'H'/'D'/'A' (or None)
      atomic_hits: list of bools, one per selection
    """
    mid = leg["match_id"]
    outcome_row = outcomes_by_match.get(mid)
    if outcome_row is None:
        return {"known": False, "actual_outcome": None, "atomic_hits": []}
    hg = outcome_row["home_goals"]
    ag = outcome_row["away_goals"]
    if leg["market_type"] == "1x2":
        actual = _outcome_1x2(hg, ag)
    else:
        # Need the handicap_home that was offered. We stored it in selections (it's not
        # actually per-selection but per-leg). Take from any prediction row with this
        # match — or fall back to looking up from single_predictions in main settle_unsettled.
        # For now, use the handicap_home recorded on the leg via leg-level handicap.
        # Caller will inject 'handicap_home' onto the leg dict before calling.
        handicap_home = leg.get("handicap_home")
        if handicap_home is None:
            return {"known": False, "actual_outcome": None, "atomic_hits": []}
        actual = _outcome_handicap_1x2(hg, ag, int(handicap_home))
    hits = [s["outcome"] == actual for s in leg["selections"]]
    return {"known": True, "actual_outcome": actual, "atomic_hits": hits}


def _match_id_to_components(match_id: str) -> tuple[str, str, str] | None:
    """Reverse the match_id format used by API ("{league}_{home}_vs_{away}")."""
    if "_vs_" not in match_id:
        return None
    left, away = match_id.rsplit("_vs_", 1)
    # league is everything up to the first _ before the home_team. Best-effort
    # heuristic: leagues are uppercase tokens; the home_team starts after the
    # league prefix (which itself may contain underscores like "ESP_LA_LIGA").
    # We use the canonical league list from our config.
    # Simpler approach: caller passes outcomes_by_match keyed by full match_id,
    # so this fallback is only used when the dict misses.
    return None


def _settle_one(
    rec_row: dict, outcomes_by_match: dict[str, dict],
) -> dict[str, Any] | None:
    """Try to settle one parlay recommendation. Returns None if any leg unknown."""
    legs = json.loads(rec_row["legs_json"])

    leg_resolutions = []
    for leg in legs:
        res = _resolve_leg_atomic_outcomes(leg, outcomes_by_match)
        if not res["known"]:
            return None
        leg_resolutions.append((leg, res))

    # Enumerate atomic combinations: each leg's hit selection (if any)
    # is the "live" pick; payout combo's net is the product of selected odds.
    # We award payout for ANY atomic combo whose all selections matched actual.
    # In a 单式 ticket each leg has 1 selection → 1 combo; either all hit or none.
    # In a 复式 ticket the leg has N selections; we sum profit across all combos
    # that hit (each combo costs 1 unit).
    stake_units = int(rec_row["stake_units"])
    kelly_stake = float(rec_row["kelly_stake"])
    if stake_units <= 0:
        return None
    unit_money = kelly_stake / stake_units

    total_payout = 0.0
    n_combos_won = 0
    n_combos_total = 0
    leg_options = []
    for leg, res in leg_resolutions:
        leg_options.append([(s, hit) for s, hit in zip(leg["selections"], res["atomic_hits"])])

    for combo in product(*leg_options):
        n_combos_total += 1
        # combo is a tuple of (selection_dict, hit_bool) per leg
        if all(hit for _, hit in combo):
            n_combos_won += 1
            odds_prod = 1.0
            for sel, _ in combo:
                odds_prod *= float(sel["odds"])
            total_payout += unit_money * odds_prod

    total_stake = unit_money * stake_units
    profit_loss = total_payout - total_stake
    hit = 1 if n_combos_won == n_combos_total else (-1 if n_combos_won > 0 else 0)

    return {
        "hit": hit,
        "stake": total_stake,
        "actual_payout": total_payout,
        "profit_loss": profit_loss,
        "details": {
            "n_combos_total": n_combos_total,
            "n_combos_won": n_combos_won,
            "leg_outcomes": [
                {
                    "match_id": leg["match_id"],
                    "actual_outcome": res["actual_outcome"],
                    "atomic_hits": res["atomic_hits"],
                }
                for leg, res in leg_resolutions
            ],
        },
    }


def settle_unsettled(conn) -> dict[str, int]:
    """Settle every unsettled recommendation whose all legs have known outcomes.

    Returns counts: {checked, settled, still_unknown, errors}.
    """
    counts = {"checked": 0, "settled": 0, "still_unknown": 0, "errors": 0}

    unsettled = list_unsettled_recommendations(conn)

    # Build a per-session lookup of (match_id -> handicap_home + outcome) using
    # single_predictions table.
    session_ids = sorted({int(r["session_id"]) for r in unsettled})
    sp_lookup: dict[int, dict[str, dict]] = {sid: {} for sid in session_ids}
    if session_ids:
        placeholder = ",".join("?" * len(session_ids))
        cur = conn.execute(
            f"""SELECT session_id, match_date, league, home_team, away_team,
                       handicap_home
                FROM single_predictions WHERE session_id IN ({placeholder})""",
            session_ids,
        )
        for row in cur.fetchall():
            mid = f"{row['league']}_{row['home_team']}_vs_{row['away_team']}"
            sp_lookup[int(row["session_id"])][mid] = {
                "match_date": row["match_date"],
                "league": row["league"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "handicap_home": row["handicap_home"],
            }

    for rec in unsettled:
        counts["checked"] += 1
        sid = int(rec["session_id"])
        legs = json.loads(rec["legs_json"])
        outcomes_by_match: dict[str, dict] = {}
        all_known = True
        # Resolve each leg: find the underlying single_prediction (to get handicap_home),
        # then look up the actual outcome.
        for leg in legs:
            mid = leg["match_id"]
            sp = sp_lookup.get(sid, {}).get(mid)
            if sp is None:
                all_known = False
                break
            outcome = get_outcome(
                conn,
                match_date=sp["match_date"],
                league=sp["league"],
                home_team=sp["home_team"],
                away_team=sp["away_team"],
            )
            if outcome is None:
                all_known = False
                break
            # Inject handicap_home onto the leg dict so _resolve_leg_atomic_outcomes can use it
            leg["handicap_home"] = sp.get("handicap_home")
            outcomes_by_match[mid] = {
                "home_goals": outcome["home_goals"],
                "away_goals": outcome["away_goals"],
            }
        if not all_known:
            counts["still_unknown"] += 1
            continue

        try:
            rec_with_resolved_legs = dict(rec)
            rec_with_resolved_legs["legs_json"] = json.dumps(legs)
            result = _settle_one(rec_with_resolved_legs, outcomes_by_match)
        except Exception:  # pragma: no cover
            counts["errors"] += 1
            continue

        if result is None:
            counts["still_unknown"] += 1
            continue
        insert_settlement(
            conn,
            rec_id=int(rec["rec_id"]),
            hit=int(result["hit"]),
            stake=float(result["stake"]),
            actual_payout=float(result["actual_payout"]),
            profit_loss=float(result["profit_loss"]),
            details=result["details"],
        )
        counts["settled"] += 1

    conn.commit()
    return counts
