"""SQLite store for V4 observation (live recommendation tracking).

Schema (5 tables):

  recommendation_sessions
    - One row per `recommend` call (CLI or API).
    - Stores: timestamp, bankroll, model metadata, request hash, count of fixtures.

  single_predictions
    - One row per (session, fixture).
    - Stores: home/away team, λ_h/λ_a, market probs, predicted handicap probs.

  parlay_recommendations
    - One row per output recommendation in a session.
    - Stores: rank, k_legs, stake_units, hit_probability, ev_per_unit,
              kelly_stake, full leg breakdown as JSON.

  match_outcomes
    - One row per actual match result (entered after the match).
    - Keyed by (date, league, home_team, away_team).

  settlements
    - One row per parlay_recommendation that has been settled.
    - hit_or_miss, actual_payout, profit_loss, settled_at.

Design choices:
- SQLite is plenty for daily ops volume (10-50 sessions/day × 5-15 recs each).
- WAL mode for concurrent readers (e.g., ROI report while recording).
- No ORM — raw SQL keeps the dependency surface minimal.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


SCHEMA_VERSION = 1


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_sessions (
    session_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    bankroll      REAL NOT NULL,
    model_cutoff  TEXT,
    model_trained_at TEXT,
    n_fixtures    INTEGER NOT NULL,
    n_recommendations INTEGER NOT NULL,
    request_json  TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS single_predictions (
    prediction_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL,
    match_date       TEXT NOT NULL,
    league           TEXT NOT NULL,
    home_team        TEXT NOT NULL,
    away_team        TEXT NOT NULL,
    lambda_home      REAL NOT NULL,
    lambda_away      REAL NOT NULL,
    p_home_1x2       REAL NOT NULL,
    p_draw_1x2       REAL NOT NULL,
    p_away_1x2       REAL NOT NULL,
    handicap_home    INTEGER,
    p_home_handicap  REAL,
    p_draw_handicap  REAL,
    p_away_handicap  REAL,
    FOREIGN KEY (session_id) REFERENCES recommendation_sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_single_predictions_match
    ON single_predictions(match_date, league, home_team, away_team);

CREATE TABLE IF NOT EXISTS parlay_recommendations (
    rec_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    rank              INTEGER NOT NULL,
    k_legs            INTEGER NOT NULL,
    is_compound       INTEGER NOT NULL,
    stake_units       INTEGER NOT NULL,
    kelly_stake       REAL NOT NULL,
    expected_return   REAL NOT NULL,
    hit_probability   REAL NOT NULL,
    ev_per_unit       REAL NOT NULL,
    log_growth        REAL NOT NULL,
    legs_json         TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES recommendation_sessions(session_id)
);
CREATE INDEX IF NOT EXISTS idx_parlay_session ON parlay_recommendations(session_id);

CREATE TABLE IF NOT EXISTS match_outcomes (
    outcome_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date   TEXT NOT NULL,
    league       TEXT NOT NULL,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    home_goals   INTEGER NOT NULL,
    away_goals   INTEGER NOT NULL,
    recorded_at  TEXT NOT NULL,
    UNIQUE(match_date, league, home_team, away_team)
);
CREATE INDEX IF NOT EXISTS idx_outcome_match
    ON match_outcomes(match_date, league, home_team, away_team);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_id         INTEGER NOT NULL UNIQUE,
    settled_at     TEXT NOT NULL,
    hit            INTEGER NOT NULL,   -- 1 = hit, 0 = miss, -1 = partial (复式)
    stake          REAL NOT NULL,
    actual_payout  REAL NOT NULL,
    profit_loss    REAL NOT NULL,
    details_json   TEXT,
    FOREIGN KEY (rec_id) REFERENCES parlay_recommendations(rec_id)
);
CREATE INDEX IF NOT EXISTS idx_settlements_rec ON settlements(rec_id);
"""


# --- Connection -----------------------------------------------------------

@contextmanager
def open_db(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with sensible defaults; ensure schema exists."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        _init_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )


def init_db(path: str | Path) -> None:
    """Public init function (idempotent). Creates DB + schema if missing."""
    with open_db(path):
        pass


# --- Write helpers --------------------------------------------------------

def insert_session(
    conn: sqlite3.Connection,
    *,
    bankroll: float,
    model_cutoff: Optional[str],
    model_trained_at: Optional[str],
    n_fixtures: int,
    n_recommendations: int,
    request: dict,
    metadata: dict | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO recommendation_sessions
            (created_at, bankroll, model_cutoff, model_trained_at,
             n_fixtures, n_recommendations, request_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            bankroll, model_cutoff, model_trained_at,
            n_fixtures, n_recommendations,
            json.dumps(request, ensure_ascii=False, default=str),
            json.dumps(metadata or {}, ensure_ascii=False, default=str),
        ),
    )
    return int(cur.lastrowid)


def insert_single_prediction(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    match_date: str,
    league: str,
    home_team: str,
    away_team: str,
    lambda_home: float,
    lambda_away: float,
    p_home_1x2: float,
    p_draw_1x2: float,
    p_away_1x2: float,
    handicap_home: Optional[int] = None,
    p_home_handicap: Optional[float] = None,
    p_draw_handicap: Optional[float] = None,
    p_away_handicap: Optional[float] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO single_predictions
            (session_id, match_date, league, home_team, away_team,
             lambda_home, lambda_away, p_home_1x2, p_draw_1x2, p_away_1x2,
             handicap_home, p_home_handicap, p_draw_handicap, p_away_handicap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, match_date, league, home_team, away_team,
            lambda_home, lambda_away, p_home_1x2, p_draw_1x2, p_away_1x2,
            handicap_home, p_home_handicap, p_draw_handicap, p_away_handicap,
        ),
    )
    return int(cur.lastrowid)


def insert_parlay_recommendation(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    rank: int,
    k_legs: int,
    is_compound: bool,
    stake_units: int,
    kelly_stake: float,
    expected_return: float,
    hit_probability: float,
    ev_per_unit: float,
    log_growth: float,
    legs: list[dict],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO parlay_recommendations
            (session_id, rank, k_legs, is_compound, stake_units,
             kelly_stake, expected_return, hit_probability, ev_per_unit,
             log_growth, legs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, rank, k_legs, int(is_compound), stake_units,
            kelly_stake, expected_return, hit_probability, ev_per_unit,
            log_growth, json.dumps(legs, ensure_ascii=False),
        ),
    )
    return int(cur.lastrowid)


def upsert_outcome(
    conn: sqlite3.Connection,
    *,
    match_date: str,
    league: str,
    home_team: str,
    away_team: str,
    home_goals: int,
    away_goals: int,
) -> None:
    """Insert or overwrite a match outcome."""
    conn.execute(
        """
        INSERT INTO match_outcomes
            (match_date, league, home_team, away_team,
             home_goals, away_goals, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_date, league, home_team, away_team)
        DO UPDATE SET home_goals=excluded.home_goals,
                      away_goals=excluded.away_goals,
                      recorded_at=excluded.recorded_at
        """,
        (
            match_date, league, home_team, away_team,
            home_goals, away_goals,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def insert_settlement(
    conn: sqlite3.Connection,
    *,
    rec_id: int,
    hit: int,
    stake: float,
    actual_payout: float,
    profit_loss: float,
    details: dict | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT OR REPLACE INTO settlements
            (rec_id, settled_at, hit, stake, actual_payout, profit_loss, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec_id,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            hit, stake, actual_payout, profit_loss,
            json.dumps(details or {}, ensure_ascii=False, default=str),
        ),
    )
    return int(cur.lastrowid)


# --- Read helpers --------------------------------------------------------

def list_unsettled_recommendations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all parlay recommendations that DON'T yet have a settlement."""
    cur = conn.execute(
        """
        SELECT p.*, s.created_at AS session_created_at
        FROM parlay_recommendations p
        JOIN recommendation_sessions s ON p.session_id = s.session_id
        LEFT JOIN settlements x ON p.rec_id = x.rec_id
        WHERE x.settlement_id IS NULL
        ORDER BY p.rec_id
        """
    )
    return list(cur.fetchall())


def get_outcome(
    conn: sqlite3.Connection,
    *, match_date: str, league: str, home_team: str, away_team: str,
) -> Optional[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT * FROM match_outcomes
        WHERE match_date = ? AND league = ?
          AND home_team = ? AND away_team = ?
        """,
        (match_date, league, home_team, away_team),
    )
    return cur.fetchone()
