"""AUDIT FIX (B3) — the model-board scoreboard must exclude playoff/barrage
rows.

Those rows have their served 1X2 blended 70% toward Pinnacle inside
``_calc_predictions`` (the model has no playoff feature), so they are NOT a
pure model output. If they entered the model-vs-sharp comparison they would
flatter the model's log-loss and could never show up as a 'disagreement' —
exactly the kind of "looks fine, scores the wrong thing" bug the V12 audit was
hunting. predict_report re-detects them at read time and drops them.
"""
from __future__ import annotations

from nutmeg.v4.cli.predict_report import build_report, scoreboard


def _row(league: str, date: str, outcome: int) -> dict:
    return {
        "match_date": date,
        "league": league,
        "home_team": "H",
        "away_team": "A",
        "p_home": 0.5,
        "p_draw": 0.3,
        "p_away": 0.2,
        "psc_home": 2.0,
        "psc_draw": 3.4,
        "psc_away": 3.6,
        "home_goals": 1,
        "away_goals": 0,
        "outcome": outcome,
    }


def test_scoreboard_excludes_playoff_blended():
    # ESP_SEGUNDA_DIVISION on 2026-06-03 falls inside a hard-coded playoff
    # window (playoff_context._WINDOWS); ESP_LA_LIGA never does.
    rows = [
        _row("ESP_LA_LIGA", "2026-06-03", 0),           # pure model → counts
        _row("ESP_SEGUNDA_DIVISION", "2026-06-03", 0),  # blended → excluded
    ]
    sb = scoreboard(rows)
    assert sb["n_market_blended_excluded"] == 1
    assert sb["n_settled"] == 1


def test_build_report_excludes_and_notes_playoff_blended():
    rows = [
        _row("ESP_LA_LIGA", "2026-06-03", 0),
        _row("ESP_SEGUNDA_DIVISION", "2026-06-03", 0),
    ]
    md = build_report(rows)
    assert "已结算 **1** 场" in md          # only the pure-model row scored
    assert "已排除 1 场 playoff" in md       # honest note, not a silent drop


def test_pure_model_rows_untouched():
    rows = [
        _row("ESP_LA_LIGA", "2026-06-03", 0),
        _row("EPL", "2026-06-03", 1),
    ]
    sb = scoreboard(rows)
    assert sb["n_market_blended_excluded"] == 0
    assert sb["n_settled"] == 2
