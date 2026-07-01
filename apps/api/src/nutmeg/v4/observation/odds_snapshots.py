"""Append-only Pinnacle line-history snapshots (体检 A1) — the CLV foundation.

Why: the api_football JSON cache is OVERWRITTEN in place on refresh and every
observation table UPSERTs, so the system used to keep only the LATEST line per
fixture — Closing Line Value ("did the price I took beat the close?") was
impossible to compute, and "what was Pinnacle at bet time" could not be
audited after the fact.

What: one row per OBSERVED LINE STATE per fixture. Every flow that walks odds
envelopes (daily/morning ingest crons, predict-log 3×/day, the sp-calc and
市场模式 boards incl. 🔄 refresh) offers its rows via ``record_row_snapshot``;
a row is inserted only when the state actually changed — dedup against the
fixture's most recent snapshot on (prices, O/U, AH, odds_update). A refreshed
``odds_update`` with identical prices still counts as a new state: "line
re-confirmed at T" is exactly the evidence the closing-line pick needs.

APPEND-ONLY by design: no UPSERT, no overwrite, no delete. NEVER raises out of
the hot path — losing one snapshot must not break a predict cron; failures log
a warning and return False.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

# A decimal odd must exceed the stake (>1.0); the ceiling is generous — even a
# minnow's 1X2 away leg vs a giant stays well under it. This is the last-line
# backstop that keeps physically-impossible / corrupt odds out of the shared
# CLV + soft-water sink regardless of which producer emits them (2026-07-01
# audit A1: the sink accepted 1.06/…/53.96, psc=0.5, psc=−3.0). NOTE this does
# NOT reject a numerically-plausible in-play line by value alone (1.06/15/53.96
# is a valid-looking triple) — that is a distinct concern handled by the
# kickoff/commence_time guards in the closing capture, the overlay, and the
# jingcai_vote / clv readers.
_MIN_ODDS = 1.0
_MAX_ODDS = 1000.0


def _sane_odds(*vals: object) -> bool:
    """True iff every non-None value parses to a finite decimal odd in (1.0, 1000]."""
    for v in vals:
        if v is None:
            continue
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if not math.isfinite(f) or f <= _MIN_ODDS or f > _MAX_ODDS:
            return False
    return True

_DDL = """
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at    TEXT NOT NULL,           -- when WE observed it (UTC ISO)
    source         TEXT NOT NULL,           -- ingest_odds|predict_log|sp_calc|cup_market|today_rec
    fixture_id     INTEGER,
    league         TEXT NOT NULL,
    match_date     TEXT NOT NULL,
    home_team      TEXT NOT NULL,
    away_team      TEXT NOT NULL,
    kickoff_utc    TEXT,
    psc_home       REAL NOT NULL,           -- Pinnacle 1X2 (raw odds, vig included)
    psc_draw       REAL NOT NULL,
    psc_away       REAL NOT NULL,
    ou_line        REAL,
    psc_over       REAL,
    psc_under      REAL,
    asian_handicap TEXT,                    -- JSON {line: {home, away}} when quoted
    odds_update    TEXT                     -- the BOOKMAKER's own line timestamp
);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_fixture
    ON odds_snapshots (fixture_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_match
    ON odds_snapshots (match_date, league, home_team, away_team);
"""

# The dedup state: every column that constitutes "the line as quoted".
_STATE_COLS = (
    "psc_home", "psc_draw", "psc_away",
    "ou_line", "psc_over", "psc_under",
    "asian_handicap", "odds_update",
)


def ensure_odds_snapshots(conn: sqlite3.Connection) -> None:
    """Idempotent DDL — safe to call on every write."""
    conn.executescript(_DDL)


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def record_row_snapshot(
    db_path: str | Path,
    row: dict,
    *,
    fixture_id: int | None = None,
    envelope: dict | None = None,
    bookmaker_id: int | None = None,
    source: str = "gather",
) -> bool:
    """Append one line-state snapshot from an ingest_odds-style row dict.

    ``row`` is the ``fixture_envelope_to_csv_row`` output (psc_*, ou_line,
    psc_over25/psc_under25, odds_update, kickoff_utc, date/league/teams).
    ``envelope`` (optional) additionally captures the Asian-Handicap board.

    Returns True iff a NEW state row was inserted; False on skip (待开盘 row,
    unchanged state) or on ANY internal failure (logged, never raised).
    """
    try:
        psc_home = row.get("psc_home")
        psc_draw = row.get("psc_draw")
        psc_away = row.get("psc_away")
        if psc_home is None or psc_draw is None or psc_away is None:
            return False  # 待开盘 — nothing quotable to snapshot
        if not _sane_odds(psc_home, psc_draw, psc_away,
                          row.get("psc_over25"), row.get("psc_under25")):
            log.warning(
                "rejecting impossible odds %s/%s/%s (o/u %s/%s) for %s vs %s "
                "[source=%s] — physically-invalid line kept out of the CLV sink",
                psc_home, psc_draw, psc_away, row.get("psc_over25"),
                row.get("psc_under25"), row.get("home_team"),
                row.get("away_team"), source)
            return False

        ah_json: str | None = None
        if envelope is not None:
            from nutmeg.v4.data.odds_parser import (
                PINNACLE_BOOKMAKER_ID,
                extract_asian_handicap,
            )
            ah = extract_asian_handicap(
                envelope, bookmaker_id or PINNACLE_BOOKMAKER_ID)
            if ah:
                ah_json = json.dumps(ah, sort_keys=True)

        state = (
            float(psc_home), float(psc_draw), float(psc_away),
            _opt_float(row.get("ou_line")),
            _opt_float(row.get("psc_over25")), _opt_float(row.get("psc_under25")),
            ah_json, row.get("odds_update"),
        )

        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_odds_snapshots(conn)
            cols = ", ".join(_STATE_COLS)
            if fixture_id is not None:
                last = conn.execute(
                    f"SELECT {cols} FROM odds_snapshots WHERE fixture_id = ? "
                    "ORDER BY id DESC LIMIT 1", (fixture_id,)).fetchone()
            else:
                last = conn.execute(
                    f"SELECT {cols} FROM odds_snapshots WHERE match_date = ? "
                    "AND league = ? AND home_team = ? AND away_team = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (row.get("date"), row.get("league"),
                     row.get("home_team"), row.get("away_team"))).fetchone()
            if last is not None and tuple(last) == state:
                return False  # line unchanged since the previous snapshot
            conn.execute(
                "INSERT INTO odds_snapshots (captured_at, source, fixture_id, "
                "league, match_date, home_team, away_team, kickoff_utc, "
                "psc_home, psc_draw, psc_away, ou_line, psc_over, psc_under, "
                "asian_handicap, odds_update) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    source, fixture_id,
                    row.get("league"), row.get("date"),
                    row.get("home_team"), row.get("away_team"),
                    row.get("kickoff_utc") or None,
                    *state,
                ))
        return True
    except Exception:  # noqa: BLE001 — a lost snapshot must never break a cron
        log.warning(
            "odds snapshot failed for %s vs %s (db=%s)",
            row.get("home_team"), row.get("away_team"), db_path, exc_info=True)
        return False
