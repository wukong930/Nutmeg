"""V10 W4 Day 1 — WC predictions audit log.

Records every WC prediction the system produces (CLI or endpoint),
then settles them when match outcomes arrive. The result is a single
queryable table of (prediction → actual) pairs that powers:

  - `nutmeg-wc-report` (W4 Day 2) — hit-rate, log-loss, ROI
  - Layer A's weekly_calibration_check — once enough WC pairs land
    in the journal, the existing auto-calibration code reads them
    via the same JOIN pattern as the domestic recommend → settle flow
  - V11 retrospective — answers "did the model work on WC 2026?"

The table is intentionally separate from `single_predictions` because:
  1. WC predictions don't go through a recommendation_session (no
     bankroll / stake / parlay context)
  2. The schema is denormalized — Elo + odds inlined for one-stop
     replay without joining external parquet snapshots
  3. We want WC to evolve independently of the domestic schema

Designed to be cron-friendly: idempotent on (fixture_id) — repeated
record_wc_prediction calls with the same fixture overwrite the prior
row, not append. (We re-run nutmeg-wc-predict daily as odds shift;
only the most recent T-0 prediction matters for hit-rate scoring.)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nutmeg.v4.observation.store import open_db, upsert_outcome


log = logging.getLogger(__name__)


WC_PREDICTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS wc_predictions (
    fixture_id      INTEGER PRIMARY KEY,
    recorded_at     TEXT NOT NULL,
    season          INTEGER NOT NULL,
    match_date      TEXT NOT NULL,
    kickoff_utc     TEXT,
    round           TEXT,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_elo        REAL,
    away_elo        REAL,
    home_adv        REAL,
    p_home          REAL NOT NULL,
    p_draw          REAL NOT NULL,
    p_away          REAL NOT NULL,
    -- Optional Pinnacle blend inputs (None until odds open)
    psc_home        REAL,
    psc_draw        REAL,
    psc_away        REAL,
    source          TEXT NOT NULL,  -- 'lightgbm_only' | 'blended'
    blend_alpha     REAL,
    -- Outcome columns: filled by nutmeg-wc-settle when API-Football
    -- returns the FT score. NULL until then.
    home_goals      INTEGER,
    away_goals      INTEGER,
    outcome         INTEGER,        -- 0=H, 1=D, 2=A
    settled_at      TEXT,
    -- Free-form extras (e.g., host_country_hint, elo_snapshot path)
    extras_json     TEXT
)
"""


@dataclass
class WcPredictionRow:
    """Lightweight container for one row out of the wc_predictions table.

    Used by the report CLI + (eventually) Layer A. Mirrors the schema
    columns 1:1 — the dataclass exists so callers can autocomplete
    field names instead of fishing through dict keys.
    """
    fixture_id: int
    recorded_at: str
    season: int
    match_date: str
    kickoff_utc: str | None
    round: str | None
    home_team: str
    away_team: str
    home_elo: float | None
    away_elo: float | None
    home_adv: float | None
    p_home: float
    p_draw: float
    p_away: float
    psc_home: float | None
    psc_draw: float | None
    psc_away: float | None
    source: str
    blend_alpha: float | None
    home_goals: int | None
    away_goals: int | None
    outcome: int | None
    settled_at: str | None
    extras_json: str | None


def ensure_wc_predictions_table(db_path: Path | str) -> None:
    """Create the wc_predictions table if missing. Idempotent."""
    with open_db(db_path) as conn:
        conn.execute(WC_PREDICTIONS_SCHEMA)


def record_wc_prediction(
    db_path: Path | str,
    prediction: dict,
    *,
    season: int,
    recorded_at: dt.datetime | None = None,
) -> int:
    """Upsert one wc prediction row keyed by fixture_id.

    ``prediction`` is one entry from the `WcPredictionsResponse.predictions`
    list (or the equivalent CLI JSON output). Repeated calls with the
    same fixture_id REPLACE the prior row — the daily cron re-runs the
    predict CLI and we want the freshest snapshot, not duplicates.

    Returns the fixture_id (which is also the primary key).
    """
    ensure_wc_predictions_table(db_path)
    if recorded_at is None:
        recorded_at = dt.datetime.now(dt.UTC).replace(microsecond=0)

    extras = {
        k: v for k, v in prediction.items()
        if k not in {
            "fixture_id", "kickoff_utc", "round", "home_team", "away_team",
            "home_elo", "away_elo", "home_adv",
            "p_home", "p_draw", "p_away",
            "p_home_elo_only", "p_draw_elo_only", "p_away_elo_only",
            "psc_home", "psc_draw", "psc_away",
            "has_pinnacle", "source", "blend_alpha",
        }
    }

    with open_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO wc_predictions (
                fixture_id, recorded_at, season, match_date, kickoff_utc,
                round, home_team, away_team,
                home_elo, away_elo, home_adv,
                p_home, p_draw, p_away,
                psc_home, psc_draw, psc_away,
                source, blend_alpha, extras_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                recorded_at = excluded.recorded_at,
                kickoff_utc = excluded.kickoff_utc,
                round       = excluded.round,
                home_elo    = excluded.home_elo,
                away_elo    = excluded.away_elo,
                home_adv    = excluded.home_adv,
                p_home      = excluded.p_home,
                p_draw      = excluded.p_draw,
                p_away      = excluded.p_away,
                psc_home    = excluded.psc_home,
                psc_draw    = excluded.psc_draw,
                psc_away    = excluded.psc_away,
                source      = excluded.source,
                blend_alpha = excluded.blend_alpha,
                extras_json = excluded.extras_json
            """,
            (
                int(prediction["fixture_id"]),
                recorded_at.isoformat(),
                season,
                _date_from_kickoff(prediction.get("kickoff_utc")),
                prediction.get("kickoff_utc"),
                prediction.get("round"),
                prediction["home_team"],
                prediction["away_team"],
                prediction.get("home_elo"),
                prediction.get("away_elo"),
                prediction.get("home_adv"),
                float(prediction["p_home"]),
                float(prediction["p_draw"]),
                float(prediction["p_away"]),
                prediction.get("psc_home"),
                prediction.get("psc_draw"),
                prediction.get("psc_away"),
                prediction["source"],
                prediction.get("blend_alpha"),
                json.dumps(extras, default=str) if extras else None,
            ),
        )
        return int(prediction["fixture_id"])


def _date_from_kickoff(kickoff_iso: str | None) -> str:
    """Extract YYYY-MM-DD from a kickoff timestamp like
    `2026-06-11T19:00:00+00:00`. Empty/None → empty string."""
    if not kickoff_iso:
        return ""
    return str(kickoff_iso)[:10]


def settle_wc_prediction(
    db_path: Path | str,
    fixture_id: int,
    *,
    home_goals: int,
    away_goals: int,
    settled_at: dt.datetime | None = None,
) -> bool:
    """Fill the outcome columns on one wc_predictions row.

    Returns True if a row was updated; False if no row exists for that
    fixture_id (settle was called for a fixture we never predicted).
    Idempotent — re-settling a fixture overwrites previous outcome
    columns (useful for correcting bad initial settle calls).

    V11 post-ship — dual-writes to ``match_outcomes`` with
    ``league="WC"`` so the regular ``settle_unsettled`` pipeline can
    close out WC handicap recommendations recorded via
    ``record_wc_handicap_session`` (Path A++ 让球). Without this bridge
    the recs stayed in "still_unknown" indefinitely because the WC arm
    only wrote to its own ``wc_predictions`` table. The dual-write is
    idempotent — `upsert_outcome` ON CONFLICT updates in-place.
    """
    ensure_wc_predictions_table(db_path)
    if settled_at is None:
        settled_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    if home_goals > away_goals:
        outcome = 0
    elif home_goals == away_goals:
        outcome = 1
    else:
        outcome = 2
    with open_db(db_path) as conn:
        cur = conn.execute(
            """
            UPDATE wc_predictions
               SET home_goals = ?, away_goals = ?, outcome = ?, settled_at = ?
             WHERE fixture_id = ?
            """,
            (home_goals, away_goals, outcome, settled_at.isoformat(), fixture_id),
        )
        updated = cur.rowcount > 0
        if updated:
            # Pull the (match_date, home, away) pinned at prediction time
            # and mirror into match_outcomes so WC-league handicap recs
            # can settle through the regular pipeline. Use match_date
            # (date-only) since match_outcomes is keyed by date.
            row = conn.execute(
                """SELECT match_date, home_team, away_team
                     FROM wc_predictions
                    WHERE fixture_id = ?""",
                (fixture_id,),
            ).fetchone()
            if row is not None and row["home_team"] and row["away_team"]:
                try:
                    upsert_outcome(
                        conn,
                        match_date=str(row["match_date"]),
                        league="WC",
                        home_team=str(row["home_team"]),
                        away_team=str(row["away_team"]),
                        home_goals=int(home_goals),
                        away_goals=int(away_goals),
                    )
                except Exception:  # noqa: BLE001
                    # Mirror failure should not break the wc_predictions
                    # update — log + continue. The regular auto-settle
                    # pipeline picks up the gap on the next run.
                    log.warning(
                        "wc settle mirror to match_outcomes failed for "
                        "fixture_id=%s (%s vs %s)",
                        fixture_id, row["home_team"], row["away_team"],
                        exc_info=True,
                    )
        return updated


def fetch_wc_predictions(
    db_path: Path | str,
    *,
    season: int | None = None,
    settled_only: bool = False,
) -> list[dict[str, Any]]:
    """Read predictions back out for the report CLI.

    Returns rows ordered by kickoff_utc. Each row is a plain dict
    matching the schema columns (lighter than the dataclass).
    """
    ensure_wc_predictions_table(db_path)
    sql = "SELECT * FROM wc_predictions"
    params: list[Any] = []
    where: list[str] = []
    if season is not None:
        where.append("season = ?")
        params.append(season)
    if settled_only:
        where.append("outcome IS NOT NULL")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY kickoff_utc ASC, fixture_id ASC"
    with open_db(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


__all__ = [
    "WC_PREDICTIONS_SCHEMA",
    "WcPredictionRow",
    "ensure_wc_predictions_table",
    "record_wc_prediction",
    "settle_wc_prediction",
    "fetch_wc_predictions",
]
