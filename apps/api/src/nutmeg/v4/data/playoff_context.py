"""Playoff / end-of-season high-stakes match detection.

V12 W0 (2026-05-27) — First real bet (2026-05-26) hit on 2 fixtures that
turned out to be playoff/barrage matches:
  • 法甲 Saint-Étienne vs Nice  — Ligue 1 barrage de relegation
  • 德乙 Greuther Fürth vs Rot-Weiß Essen  — Relegations-Playoff zur 2.BL

The CatBoost model has **no feature** that flags "this is a playoff /
promotion / relegation barrage". It treats them as regular league fixtures
and uses recent-N-match form / Elo / xG-lite — none of which encode the
"do-or-die motivation" that shifts the actual scoreline distribution.

Pinnacle's SP **does** know (sharps adjust prices), but because vig is
baked in we can't decompose how much edge the market gives back.

**This module's job**: give the dashboard a hard-coded list of "likely
playoff date windows" per league so the UI can show a ⚠️ banner. Goal is
"raise hand for caution" not "label exactly playoff" — it's a coarse heuristic.

V13 candidate work (NOT in this module):
  P1: is_relegation_playoff / is_promotion_playoff boolean features fed
      into the training pipeline (football-data.co.uk archives do
      include playoff CSVs we'd need to mark)
  P2: per-playoff-bucket calibration (similar to V9 per-league T)
  P3: dedicated playoff-aware artifact + ROI ablation
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Optional


@dataclass(frozen=True)
class PlayoffWindow:
    """A date range during which `league` fixtures are likely playoff/barrage.

    Note: ``start`` and ``end`` are **inclusive** (both bounds).

    ``context`` is a short human-readable label (mixed CN/EN allowed,
    consumer renders it as-is in the dashboard banner).
    """
    league: str
    start: str  # ISO YYYY-MM-DD inclusive
    end: str    # ISO YYYY-MM-DD inclusive
    context: str
    # The model's specific failure mode for this window. Empirical
    # observation as of 2026-05-27: barrage matches see 0-0 or 1-0 results
    # more often than regular-season base rate; model's lambda predictions
    # don't account for this.
    model_bias_note: str = "Model not calibrated for high-stakes end-of-season fixtures."


# 2025-26 season windows (last week of May → early June for most leagues).
# Re-curate this list at each season turnover (use --year flag on V13+
# CLI to keep season-rolling; for now hard-coded).
_WINDOWS: list[PlayoffWindow] = [
    # ── French Ligue 1: barrage de relegation (16th place vs Ligue 2 3rd) ──
    PlayoffWindow(
        league="FRA_LIGUE_1",
        start="2026-05-22",
        end="2026-06-02",
        context="Ligue 1 barrage de relegation",
        model_bias_note=(
            "Barrage = single elimination with relegation/promotion stakes. "
            "Both teams play conservatively; draws + low-scoring outcomes "
            "over-represented vs model's expectation."
        ),
    ),
    # Ligue 2 has a parallel playoff slot — when Ligue 2 hosts the leg.
    PlayoffWindow(
        league="FRA_LIGUE_2",
        start="2026-05-22",
        end="2026-06-02",
        context="Ligue 2 barrage (promotion)",
    ),

    # ── German Bundesliga + 2.Bundesliga: Relegations-Playoff ──
    # Bundesliga 16th vs 2.BL 3rd OR 2.BL 16th vs 3.Liga 3rd.
    PlayoffWindow(
        league="GER_BUNDESLIGA",
        start="2026-05-22",
        end="2026-06-02",
        context="Bundesliga Relegations-Playoff",
    ),
    PlayoffWindow(
        league="GER_2_BUNDESLIGA",
        start="2026-05-22",
        end="2026-06-02",
        context="2.Bundesliga Relegations-Playoff",
    ),

    # ── English Championship: Promotion Playoff (last EPL slot, 4 teams) ──
    PlayoffWindow(
        league="ENG_CHAMPIONSHIP",
        start="2026-05-08",
        end="2026-05-31",
        context="Championship Promotion Playoff",
        model_bias_note=(
            "Single-elimination knockouts (SF home/away + Wembley final). "
            "Wembley final factor + season-end fatigue not modeled."
        ),
    ),

    # ── Spanish Segunda División: Promotion Playoff ──
    PlayoffWindow(
        league="ESP_SEGUNDA_DIVISION",
        start="2026-06-01",
        end="2026-06-20",
        context="Segunda División Promotion Playoff",
    ),

    # ── Italian Serie B: Promotion + Relegation Playoffs ──
    PlayoffWindow(
        league="ITA_SERIE_B",
        start="2026-05-15",
        end="2026-06-15",
        context="Serie B Promotion / Relegation Playoff",
    ),

    # ── Dutch Eredivisie: Europe Playoff (Conference League slots) ──
    PlayoffWindow(
        league="NED_EREDIVISIE",
        start="2026-05-15",
        end="2026-06-05",
        context="Eredivisie Europe Playoff",
    ),

    # ── Portuguese Primeira Liga: Promotion Playoff ──
    PlayoffWindow(
        league="PRT_PRIMEIRA_LIGA",
        start="2026-05-22",
        end="2026-06-08",
        context="Primeira Liga Promotion Playoff",
    ),

    # ── Belgian Pro League: Champions Playoff + Europa Playoff phase ──
    # Special case: BPL runs a "playoff round" for the entire end of the
    # season starting late March, splitting the league into Championship
    # Playoff (top 6) + Europa Playoff (mid 6) + Relegation Playoff. The
    # whole post-March window is essentially "the rules changed."
    PlayoffWindow(
        league="BEL_PRO_LEAGUE",
        start="2026-03-20",
        end="2026-06-01",
        context="Belgian Pro League Playoff Phase",
        model_bias_note=(
            "BPL post-regular-season splits into Championship/Europa/Relegation "
            "playoff brackets with halved points — entire window is structurally "
            "different from model's training assumption of regular round-robin."
        ),
    ),
]


def detect_playoff(league: str, match_date: str | _date) -> Optional[PlayoffWindow]:
    """Return the first matching ``PlayoffWindow`` for ``(league, date)``, else None.

    ``match_date`` accepts ISO ``YYYY-MM-DD`` strings or ``datetime.date``.

    Conservative semantics:
      - Only checks against hard-coded windows above.
      - Not every match in a window is actually a playoff fixture; the
        UI banner makes this clear ("likely playoff context").
      - Future ``V13 P1`` work will replace this heuristic with a feature
        directly labeled in training data, but until then the banner is
        the cheapest correct intervention.
    """
    if isinstance(match_date, _date):
        d = match_date.isoformat()
    else:
        d = str(match_date)
        # tolerate ISO-with-time
        if "T" in d:
            d = d.split("T", 1)[0]

    for w in _WINDOWS:
        if w.league == league and w.start <= d <= w.end:
            return w
    return None


def all_windows() -> list[PlayoffWindow]:
    """Return a shallow copy of all configured windows (for diagnostics)."""
    return list(_WINDOWS)
