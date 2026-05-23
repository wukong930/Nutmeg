"""Parsers for API-Football /odds payloads — V7 W1.

The /odds endpoint returns one envelope per (fixture, league):

    {
      "fixture": {"id": 123, "date": "2025-08-17T15:00:00+00:00"},
      "league":  {"id": 39, "season": 2025, ...},
      "update":  "...",
      "bookmakers": [
        {
          "id": 4, "name": "Pinnacle",
          "bets": [
            {
              "id": 1, "name": "Match Winner",
              "values": [
                {"value": "Home", "odd": "2.10"},
                {"value": "Draw", "odd": "3.40"},
                {"value": "Away", "odd": "3.50"},
              ]
            },
            ...
          ]
        },
        ...
      ]
    }

This module is pure parsing — no IO. The CLI (cli/ingest_odds.py)
calls the api_football adapter for raw payloads, then hands each
envelope here for 1X2 / O/U extraction.
"""
from __future__ import annotations

from typing import Optional


# Known API-Football bookmaker IDs (constants documented in /bookmakers).
# These are the most commonly carried books for European leagues.
PINNACLE_BOOKMAKER_ID = 4
BET365_BOOKMAKER_ID = 8
UNIBET_BOOKMAKER_ID = 16

# API-Football bet IDs (documented in /bets). The 1X2 ("Match Winner") and
# O/U 2.5 ("Goals Over/Under") IDs are stable; Asian Handicap is bet id 4.
BET_MATCH_WINNER = 1     # 1X2
BET_GOALS_OVER_UNDER = 5  # name="Goals Over/Under" (we want 2.5 line)
BET_ASIAN_HANDICAP = 4   # fractional lines (-0.5, -0.25, etc.)


# Mapping API-Football "value" labels → our outcome letters
_OUTCOME_LABEL_MAP = {
    "Home": "H",
    "Draw": "D",
    "Away": "A",
}


def _find_bookmaker(envelope: dict, bookmaker_id: int) -> Optional[dict]:
    for bm in envelope.get("bookmakers", []):
        if bm.get("id") == bookmaker_id:
            return bm
    return None


def _find_bet(bookmaker: dict, bet_id: int) -> Optional[dict]:
    for bet in bookmaker.get("bets", []):
        if bet.get("id") == bet_id:
            return bet
    return None


def extract_1x2_odds(
    envelope: dict,
    bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[dict[str, float]]:
    """Pull (H, D, A) decimal odds from one fixture's /odds envelope.

    Returns {"H": 2.10, "D": 3.40, "A": 3.50} when the requested
    bookmaker quotes Match Winner; None when:
      - bookmaker not present
      - bookmaker is present but doesn't carry Match Winner
      - any of H/D/A missing
      - any odd ≤ 1.0 (sentinel for "no quote")
    """
    bm = _find_bookmaker(envelope, bookmaker_id)
    if bm is None:
        return None
    bet = _find_bet(bm, BET_MATCH_WINNER)
    if bet is None:
        return None
    out: dict[str, float] = {}
    for entry in bet.get("values", []):
        label = entry.get("value")
        outcome = _OUTCOME_LABEL_MAP.get(label)
        if outcome is None:
            continue
        try:
            odd = float(entry.get("odd"))
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        out[outcome] = odd
    if set(out) != {"H", "D", "A"}:
        return None
    return out


def extract_over_under_25(
    envelope: dict,
    bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[tuple[float, float]]:
    """Pull (over_2.5, under_2.5) decimal odds. Returns None when missing.

    API-Football's O/U values look like:
        {"value": "Over 2.5", "odd": "2.05"}
        {"value": "Under 2.5", "odd": "1.80"}
    """
    bm = _find_bookmaker(envelope, bookmaker_id)
    if bm is None:
        return None
    bet = _find_bet(bm, BET_GOALS_OVER_UNDER)
    if bet is None:
        return None
    over: Optional[float] = None
    under: Optional[float] = None
    for entry in bet.get("values", []):
        label = entry.get("value", "")
        try:
            odd = float(entry.get("odd"))
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        if label == "Over 2.5":
            over = odd
        elif label == "Under 2.5":
            under = odd
    if over is None or under is None:
        return None
    return over, under


def fixture_envelope_to_csv_row(
    fixture_record: dict,
    odds_envelope: Optional[dict],
    league_code: str,
    *,
    sharp_bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[dict]:
    """Combine /fixtures record + /odds envelope → one CSV row dict.

    Returns None when 1X2 odds can't be resolved (we don't surface
    odds-less fixtures — `nutmeg-recommend` will reject them anyway).

    `fixture_record` shape (subset we use):
        {"fixture": {"id": ..., "date": "2025-08-17T15:00:00+00:00"},
         "teams":   {"home": {"name": "Arsenal", ...},
                     "away": {"name": "Liverpool", ...}}}

    Output row keys match what `_read_fixtures` in cli/recommend.py
    expects (date, league, home_team, away_team, psc_*, optional
    psc_over25 / psc_under25).
    """
    if odds_envelope is None:
        return None
    odds_1x2 = extract_1x2_odds(odds_envelope, sharp_bookmaker_id)
    if odds_1x2 is None:
        return None

    f = fixture_record.get("fixture", {})
    teams = fixture_record.get("teams", {})
    home = teams.get("home", {}).get("name")
    away = teams.get("away", {}).get("name")
    iso_date = f.get("date", "")
    # ISO timestamps like "2025-08-17T15:00:00+00:00" → "2025-08-17"
    date_only = iso_date[:10] if iso_date else ""

    row: dict = {
        "date": date_only,
        "league": league_code,
        "home_team": home,
        "away_team": away,
        "psc_home": odds_1x2["H"],
        "psc_draw": odds_1x2["D"],
        "psc_away": odds_1x2["A"],
    }
    ou = extract_over_under_25(odds_envelope, sharp_bookmaker_id)
    if ou is not None:
        row["psc_over25"] = ou[0]
        row["psc_under25"] = ou[1]
    return row


__all__ = [
    "PINNACLE_BOOKMAKER_ID",
    "BET365_BOOKMAKER_ID",
    "UNIBET_BOOKMAKER_ID",
    "BET_MATCH_WINNER",
    "BET_GOALS_OVER_UNDER",
    "BET_ASIAN_HANDICAP",
    "extract_1x2_odds",
    "extract_over_under_25",
    "fixture_envelope_to_csv_row",
]
