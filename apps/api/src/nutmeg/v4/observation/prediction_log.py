"""V12 W8j — model-board prediction audit log (NO betting).

The 竞彩 observation tables (single_predictions + parlay_recommendations +
settlements) answer "did my BETS profit?" — they only exist for matches the
user actually bet on 竞彩, and they need a 竞彩 SP + stake.

This table answers a DIFFERENT question: "is the model's PREDICTION any
good?" — for ANY model-board match with a result, no bet required. Most of
the matches the user asks about are NOT on 竞彩 (竞彩 lists few games), so
prediction accuracy has to be tracked independently of ROI.

Design mirrors observation/wc_log.py (denormalized, idempotent, cron-friendly)
but for the 13 domestic model leagues and keyed by the same
(match_date, league, home, away) tuple that match_outcomes uses — so no
fixture_id plumbing is needed.

Each row stores BOTH the model's P (p_*) AND Pinnacle's raw odds (psc_*), so
the report can score the model's log-loss AND Pinnacle's de-vig log-loss on
the SAME settled matches — the only honest test of whether the model adds
anything over just following the sharp.

Re-running nutmeg-predict-log daily overwrites the prediction columns (odds
shift, the model re-scores) but NEVER clobbers a filled outcome.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable

from nutmeg.v4.observation.store import open_db

log = logging.getLogger(__name__)

# A 1X2 prediction settles on the 90-minute result (same convention as 竞彩 and
# auto_settle): a cup tie decided in ET/PEN still has a 90' draw in
# score.fulltime. FT/AET/PEN all carry a usable fulltime score.
FINISHED_STATUSES = {"FT", "AET", "PEN"}

LEAGUE_PREDICTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS league_predictions (
    match_date   TEXT NOT NULL,
    league       TEXT NOT NULL,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    recorded_at  TEXT NOT NULL,
    kickoff_utc  TEXT,
    market_mode  INTEGER NOT NULL DEFAULT 0,
    -- Model 1X2 probabilities (for market_mode rows these are the Pinnacle
    -- de-vig, NOT independent model output — the report excludes them from the
    -- model-vs-sharp comparison).
    p_home       REAL NOT NULL,
    p_draw       REAL NOT NULL,
    p_away       REAL NOT NULL,
    -- Pinnacle raw 1X2 odds (the sharp benchmark; de-vigged in the report).
    psc_home     REAL,
    psc_draw     REAL,
    psc_away     REAL,
    -- Outcome columns: filled by settle_league_predictions from the 90' score.
    home_goals   INTEGER,
    away_goals   INTEGER,
    outcome      INTEGER,        -- 0=H, 1=D, 2=A
    settled_at   TEXT,
    PRIMARY KEY (match_date, league, home_team, away_team)
)
"""


def ensure_league_predictions_table(db_path: str) -> None:
    """Create the league_predictions table if missing. Idempotent."""
    with open_db(db_path) as conn:
        conn.execute(LEAGUE_PREDICTIONS_SCHEMA)


def record_league_prediction(
    db_path: str,
    prediction: dict,
    *,
    recorded_at: dt.datetime | None = None,
) -> None:
    """Upsert one model-board prediction.

    `prediction` carries the SinglePrediction shape: home_team, away_team,
    league, date, kickoff_utc, p_home_1x2/p_draw_1x2/p_away_1x2,
    psc_home/psc_draw/psc_away, market_mode.

    Idempotent on (match_date, league, home, away): re-logging updates the
    prediction columns (model re-scored as odds shifted) but leaves any
    already-filled outcome untouched.
    """
    ts = (recorded_at or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    md = str(prediction["date"])
    with open_db(db_path) as conn:
        conn.execute(LEAGUE_PREDICTIONS_SCHEMA)
        conn.execute(
            """
            INSERT INTO league_predictions (
                match_date, league, home_team, away_team, recorded_at,
                kickoff_utc, market_mode, p_home, p_draw, p_away,
                psc_home, psc_draw, psc_away
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(match_date, league, home_team, away_team) DO UPDATE SET
                recorded_at = excluded.recorded_at,
                kickoff_utc = excluded.kickoff_utc,
                market_mode = excluded.market_mode,
                p_home = excluded.p_home,
                p_draw = excluded.p_draw,
                p_away = excluded.p_away,
                psc_home = excluded.psc_home,
                psc_draw = excluded.psc_draw,
                psc_away = excluded.psc_away
            """,
            (
                md, prediction["league"], prediction["home_team"],
                prediction["away_team"], ts, prediction.get("kickoff_utc"),
                1 if prediction.get("market_mode") else 0,
                float(prediction["p_home_1x2"]),
                float(prediction["p_draw_1x2"]),
                float(prediction["p_away_1x2"]),
                prediction.get("psc_home"), prediction.get("psc_draw"),
                prediction.get("psc_away"),
            ),
        )


def fetch_league_predictions(
    db_path: str, *, settled_only: bool = False
) -> list[dict]:
    """Return all league_predictions rows as dicts (newest first)."""
    with open_db(db_path) as conn:
        conn.execute(LEAGUE_PREDICTIONS_SCHEMA)
        where = "WHERE outcome IS NOT NULL" if settled_only else ""
        cur = conn.execute(
            f"SELECT * FROM league_predictions {where} ORDER BY match_date DESC"
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def _ft_outcome(fixture: dict) -> tuple[int, int, int] | None:
    """(home_goals, away_goals, outcome) from a finished fixture's 90' score,
    or None if the fixture isn't finished / has no usable score."""
    status = ((fixture.get("fixture") or {}).get("status") or {}).get("short")
    if status not in FINISHED_STATUSES:
        return None
    ft = (fixture.get("score") or {}).get("fulltime") or {}
    goals = fixture.get("goals") or {}
    hg = ft.get("home")
    ag = ft.get("away")
    if hg is None or ag is None:
        # 体检 Wave3 (P2) — the `goals` fallback is only safe for FT: on an
        # AET/PEN fixture `goals` is the FINAL score incl. extra time, so a
        # missing fulltime split would settle a 90'-draw cup tie as a win
        # (wrong convention — 竞彩/auto_settle score at 90'). Skip instead of
        # faking; the next settle pass retries once AF fills the split.
        if status != "FT":
            return None
        hg, ag = goals.get("home"), goals.get("away")
    if hg is None or ag is None:
        return None
    hg, ag = int(hg), int(ag)
    outcome = 0 if hg > ag else (1 if hg == ag else 2)
    return hg, ag, outcome


def settle_league_predictions(
    db_path: str,
    *,
    fetch_fixtures: Callable[[dt.date, str], list[dict]] | None = None,
    today: dt.date | None = None,
) -> int:
    """Fill the outcome columns for unsettled, kicked-off predictions.

    Groups unsettled rows by (league, match_date), fetches that day's fixtures
    once, matches by (home_team, away_team), and writes the 90' result.
    Returns the number of rows newly settled.

    `fetch_fixtures(date, league) -> list[fixture]` is injectable for tests;
    defaults to API-Football.
    """
    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date, league: str) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, league, refresh=True)

    from nutmeg.v4.data.national_alias import national_match_key

    today = today or dt.datetime.now(dt.UTC).date()
    settled = 0
    with open_db(db_path) as conn:
        conn.execute(LEAGUE_PREDICTIONS_SCHEMA)
        cur = conn.execute(
            "SELECT match_date, league, home_team, away_team "
            "FROM league_predictions WHERE outcome IS NULL"
        )
        unsettled = cur.fetchall()
        # Group by (league, date); only settle dates that are today-or-past.
        groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for md, lg, h, a in unsettled:
            try:
                d = dt.date.fromisoformat(md)
            except ValueError:
                continue
            if d > today:
                continue
            groups.setdefault((lg, md), []).append((h, a))

        ts = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        for (lg, md), pairs in groups.items():
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(md), lg)
            except Exception as exc:  # noqa: BLE001
                log.warning("settle: fetch failed for %s %s: %s", lg, md, exc)
                continue
            by_pair: dict[tuple[str, str], dict] = {}
            for fx in fixtures:
                teams = fx.get("teams") or {}
                hn = (teams.get("home") or {}).get("name")
                an = (teams.get("away") or {}).get("name")
                if hn and an:
                    # national_match_key on BOTH sides — a bare-string join here
                    # never settled 'Czech Republic' (竞彩) vs 'Czechia' (API).
                    by_pair[(national_match_key(hn), national_match_key(an))] = fx
            for h, a in pairs:
                fx = by_pair.get((national_match_key(h), national_match_key(a)))
                if fx is None:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                upd = conn.execute(
                    "UPDATE league_predictions SET home_goals=?, away_goals=?, "
                    "outcome=?, settled_at=? WHERE match_date=? AND league=? "
                    "AND home_team=? AND away_team=? AND outcome IS NULL",
                    (hg, ag, outcome, ts, md, lg, h, a),
                )
                settled += max(0, upd.rowcount)
    return settled
