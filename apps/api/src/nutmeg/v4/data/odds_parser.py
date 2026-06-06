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

import json
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


def extract_asian_handicap(
    envelope: dict,
    bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[dict[float, dict[str, float]]]:
    """``{line: {"home": odd, "away": odd}}`` for the sharp book's Asian Handicap.

    API-Football labels the two sides of one line with the SAME (home-handicap)
    value, e.g. for the −0.5 line::

        {"value": "Home -0.5", "odd": "2.31"}   # home gives 0.5 (must win)
        {"value": "Away -0.5", "odd": "1.58"}   # away +0.5 (win or draw)

    so ``{line: {"home", "away"}}`` pairs them up. ``line`` is the HOME handicap
    (DC convention). Only complete 2-way lines are returned; None when the book
    quotes no Asian Handicap at all. This is the INTERNATIONAL half/quarter-line
    handicap (NOT the 竞彩 integer market) — used for the 让球 prediction display.
    """
    bm = _find_bookmaker(envelope, bookmaker_id)
    if bm is None:
        return None
    bet = _find_bet(bm, BET_ASIAN_HANDICAP)
    if bet is None:
        return None
    board: dict[float, dict[str, float]] = {}
    for entry in bet.get("values", []):
        label = entry.get("value", "")
        try:
            odd = float(entry.get("odd"))
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        if label.startswith("Home "):
            side, num = "home", label[5:]
        elif label.startswith("Away "):
            side, num = "away", label[5:]
        else:
            continue
        try:
            line = float(num)
        except ValueError:
            continue
        board.setdefault(line, {})[side] = odd
    complete = {ln: v for ln, v in board.items() if "home" in v and "away" in v}
    return complete or None


def _ou_ladder(bet: dict) -> dict[float, dict]:
    """``{line: {"over": odd, "under": odd}}`` from a Goals Over/Under bet.

    API-Football labels look like ``"Over 2.25"`` / ``"Under 2.5"``; Pinnacle
    exposes the full quarter-line ladder (1.5, 1.75, 2.0, 2.25, 2.5, 2.75, …).
    """
    ladder: dict[float, dict] = {}
    for entry in bet.get("values", []):
        label = entry.get("value", "")
        try:
            odd = float(entry.get("odd"))
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        if label.startswith("Over "):
            side, num = "over", label[5:]
        elif label.startswith("Under "):
            side, num = "under", label[6:]
        else:
            continue
        try:
            line = float(num)
        except ValueError:
            continue
        ladder.setdefault(line, {})[side] = odd
    return ladder


def extract_over_under(
    envelope: dict,
    bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[tuple[float, float, float]]:
    """Pull ``(line, over, under)`` for the sharp book's MAIN total line.

    Prefers the 2.5 line — so ``psc_over25``/``psc_under25`` and the validated
    market-reverse serving path stay byte-identical whenever it's quoted. Falls
    back to the most-balanced complete pair (smallest ``|1/over − 1/under|`` —
    the line the book centres its money on) when 2.5 is absent. On a quarter
    total (2.25 / 2.75) that pivot is the sharpest anchor; proven on real
    Pinnacle ladders to imply the same λ_total as the 2.5 line to <0.1pp, so the
    fallback only ADDS coverage for fixtures that lack a 2.5 line — it never
    moves a fixture that already had one.

    Returns None when the book quotes no complete Over/Under pair.
    """
    bm = _find_bookmaker(envelope, bookmaker_id)
    if bm is None:
        return None
    bet = _find_bet(bm, BET_GOALS_OVER_UNDER)
    if bet is None:
        return None
    complete = {
        ln: d for ln, d in _ou_ladder(bet).items()
        if "over" in d and "under" in d
    }
    if not complete:
        return None
    if 2.5 in complete:
        d = complete[2.5]
        return 2.5, d["over"], d["under"]
    line = min(
        complete,
        key=lambda ln: abs(1.0 / complete[ln]["over"] - 1.0 / complete[ln]["under"]),
    )
    d = complete[line]
    return line, d["over"], d["under"]


def fixture_envelope_to_csv_row(
    fixture_record: dict,
    odds_envelope: Optional[dict],
    league_code: str,
    *,
    sharp_bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
    require_1x2_odds: bool = True,
) -> Optional[dict]:
    """Combine /fixtures record + /odds envelope → one CSV row dict.

    Returns None when 1X2 odds can't be resolved AND ``require_1x2_odds`` is
    True (the default — `nutmeg-recommend` and the 国际盘口 board reject
    odds-less fixtures anyway).

    Pass ``require_1x2_odds=False`` (V12 W6 — 近期赛事 tab) to still emit the
    row with ``psc_*`` = None when Pinnacle hasn't opened a line. The model
    treats psc as a strong feature, so such a fixture is surfaced as '待开盘'
    (NOT scored) rather than fed a misleading psc-free probability.

    `fixture_record` shape (subset we use):
        {"fixture": {"id": ..., "date": "2025-08-17T15:00:00+00:00"},
         "teams":   {"home": {"name": "Arsenal", ...},
                     "away": {"name": "Liverpool", ...}}}

    Output row keys match what `_read_fixtures` in cli/recommend.py
    expects (date, league, home_team, away_team, psc_*, optional
    psc_over25 / psc_under25).
    """
    odds_1x2 = (
        extract_1x2_odds(odds_envelope, sharp_bookmaker_id)
        if odds_envelope is not None else None
    )
    if odds_1x2 is None and require_1x2_odds:
        return None

    f = fixture_record.get("fixture", {})
    teams = fixture_record.get("teams", {})
    home = teams.get("home", {}).get("name")
    away = teams.get("away", {}).get("name")
    iso_date = f.get("date", "")
    # ISO timestamps like "2025-08-17T15:00:00+00:00" → "2025-08-17"
    date_only = iso_date[:10] if iso_date else ""
    # V12 W0 (2026-05-28) — kickoff_utc + status_short let downstream
    # filter out already-kicked-off fixtures (J1 has 12:00 weekend
    # kickoffs that would otherwise leak into the 14:00 cron output
    # with stale Pinnacle SP from before the match started).
    status_short = f.get("status", {}).get("short", "")

    row: dict = {
        "date": date_only,
        "league": league_code,
        "home_team": home,
        "away_team": away,
        # psc_* are None when Pinnacle hasn't quoted (only reachable with
        # require_1x2_odds=False — the 待开盘 path).
        "psc_home": odds_1x2["H"] if odds_1x2 else None,
        "psc_draw": odds_1x2["D"] if odds_1x2 else None,
        "psc_away": odds_1x2["A"] if odds_1x2 else None,
        "kickoff_utc": iso_date,    # full ISO with TZ
        "status_short": status_short,  # NS / IN_PLAY / FT / etc.
        # When API-Football last refreshed this odds snapshot. API-Football
        # mirrors Pinnacle only periodically (hours), so the de-vig prior can
        # trail Pinnacle.com — the 市场模式 card surfaces this age so a stale
        # line isn't trusted near kickoff (and nudges to the manual calc).
        "odds_update": (odds_envelope.get("update") if odds_envelope is not None else None),
    }
    if odds_envelope is not None:
        ou = extract_over_under_25(odds_envelope, sharp_bookmaker_id)
        if ou is not None:
            # 2.5 quoted — keep the model's "over 2.5" feature pure + the
            # validated reverse path unchanged.
            row["psc_over25"] = ou[0]
            row["psc_under25"] = ou[1]
            row["ou_line"] = 2.5
        else:
            # 2.5 absent (thin / Asian-only book) — fall back to the main line
            # so the market-reverse 让球 still has an O/U anchor instead of
            # degrading to a 1X2-only fit. ou_line tells the server which line
            # these prices belong to (quarter lines handled correctly).
            main = extract_over_under(odds_envelope, sharp_bookmaker_id)
            if main is not None:
                line, over, under = main
                row["psc_over25"] = over
                row["psc_under25"] = under
                row["ou_line"] = line
        # V14 — real Pinnacle Asian Handicap (international half/quarter lines)
        # for the 让球胜平负 PREDICTION. Carried as a JSON string ({line: {home,
        # away}}) so it survives both the FixtureOddsInput pydantic hop and a
        # pandas column; the server de-vigs it (DC-grid fallback when absent).
        ah = extract_asian_handicap(odds_envelope, sharp_bookmaker_id)
        if ah:
            row["asian_handicap"] = json.dumps({str(k): v for k, v in ah.items()})
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
    "extract_over_under",
    "extract_asian_handicap",
    "fixture_envelope_to_csv_row",
]
