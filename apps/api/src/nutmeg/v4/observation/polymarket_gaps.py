"""Polymarket mispricing-gap log (READ-ONLY measurement, NO betting).

Persists detected gaps over time so we can answer, weeks later, the only honest
question about this experiment: **were the high-confidence gaps actually real,
and did the favorite-flip guard remove the losers?** Each row stores our fair
``q``, the Polymarket ask, the EV, the confidence tier + reasons, and (filled
after kickoff) whether the bought YES would have resolved true — so a report can
score realized hit-rate by tier.

Covers 胜平负 (HOME_WIN/DRAW/AWAY_WIN), 让球 (HANDICAP_HOME/AWAY + line) and 大小球
(OVER/UNDER + line) — one row per (match, spec, line). ``line`` is stored NOT
NULL with a ``_NO_LINE`` sentinel for moneyline so it can sit in the primary key
(SQLite treats NULLs as distinct, which would break the upsert dedup).

Design mirrors observation/prediction_log.py (denormalized, idempotent,
cron-friendly). NOTHING here places an order — it only records what was observed.

🚨 入库闸 · 盘中价拒写(2026-09-02)
病情:实测 9,074 行里 **1,294 行(14.3%)的 ``recorded_at`` 晚于 ``kickoff_utc``**
—— 拿的是**盘中**价。已结算子集(任何回测的人口)更糟:1,279/6,283 = **20.4%**。
``confidence_tier`` 一条都挡不住(tier='high' 里 280/3,936 = 7.1%,reasons 全空):
它量的是 **Pinnacle 报价的陈旧度**(``freshness_hours``),不是「离开球还有多久」。

两处伤害,第二处才是真出血:
  ① 复盘被毒。``ev = q_fair/poly_ask − 1`` 拿一条**赛前** Pinnacle 线去比一个
     **盘中** ask —— 那不是错价测量,是范畴错误。一颗进球后的 0.98 会伪装成
     +19.7% 的名义 EV(实测:剔掉盘中价后 tier=high & ev≥5% 的已实现 ROI 从
     −1.00% 掉到 **−7.38%**,「+19.7% 预测」原本就是这么来的)。
  ② **好行被覆盖。** PK 不含 ``recorded_at`` + ``ON CONFLICT DO UPDATE`` ⇒ 开球后
     那次 cron 会把 T−3h 那条**合法赛前观测**原地冲掉。forward-only 的东西冲掉
     就没了。⇒ 所以这道闸是**拒写**不是**打标**:拒写才能把好行留在原地。

⚠️ 容差 = 0,与 ``jingcai_sp`` 的 +15min 宽限**故意相反**(见该模块闸 2):那里挡的是
「冻结 SP 开球后不可能再变」,15 分钟只吸收名义开球偏差;这里挡的是「盘中价不是赛前
错价」,而开球后 15 分钟内完全可能已经进球 —— 正宽限会把最毒的那批行放进来。

⛔ 存量的 1,294 行**不动**(本次只堵新增)。消费方要干净人口,自己卡
``recorded_at < kickoff_utc``。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable

from nutmeg.v4.observation.prediction_log import _ft_outcome
from nutmeg.v4.observation.store import open_db

log = logging.getLogger(__name__)

__all__ = [
    "ensure_polymarket_gaps_table",
    "record_polymarket_gap",
    "fetch_polymarket_gaps",
    "settle_polymarket_gaps",
]

# Moneyline has no line; a NOT NULL sentinel lets `line` live in the PK (a NULL in
# a PK column is treated as distinct by SQLite → the upsert would never dedup).
# Real lines are half-integers within ±8.5, so -100.0 can never collide.
_NO_LINE = -100.0

#: 盘中价拒写的容差(秒)。0 = 开球即拒 —— 见模块头「⚠️ 容差 = 0」那段。
_INPLAY_GRACE_S = 0


def _is_inplay(kickoff_utc: object, observed: dt.datetime) -> bool:
    """观测时刻 ``observed`` 是否已到/过开球?

    kickoff 缺失或不可解析 → False(**fail-open**:一个坏时刻不该静默吃掉整批采集,
    而落进来的行仍带得走 ``kickoff_utc``,消费方还能自己判)。

    ⚠️ 判据用的是**传进来的观测时刻**而不是 ``now()``:写进 ``recorded_at`` 的就是
    这个值,判闸的瞬间与落库的瞬间因此**恒等** —— closing_odds 那次赛前/赛后竞态
    (闸读一次钟、写又读一次钟)就是这么来的。
    """
    if not kickoff_utc:
        return False
    try:
        ko = dt.datetime.fromisoformat(str(kickoff_utc).strip())
    except (ValueError, TypeError):
        return False
    if ko.tzinfo is None:  # 库里 155 行是裸时刻;按 UTC 读(全表其余行都带 +00)
        ko = ko.replace(tzinfo=dt.UTC)
    return observed >= ko + dt.timedelta(seconds=_INPLAY_GRACE_S)

POLYMARKET_GAPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS polymarket_gaps (
    match_date       TEXT NOT NULL,
    fixture_id       INTEGER NOT NULL,
    outcome_spec     TEXT NOT NULL,        -- 胜平负 | HANDICAP_HOME/AWAY | OVER | UNDER
    line             REAL NOT NULL DEFAULT -100.0,  -- 让球/大小球 line; -100 = moneyline
    recorded_at      TEXT NOT NULL,
    league           TEXT,
    home_team        TEXT,
    away_team        TEXT,
    kickoff_utc      TEXT,
    series_slug      TEXT,
    event_slug       TEXT,
    yes_token        TEXT,
    -- the measurement: our fair P vs the Polymarket ask, the gap, confidence.
    q_fair           REAL NOT NULL,        -- Pinnacle de-vig fair probability
    poly_ask         REAL NOT NULL,        -- actionable cost to buy the YES
    poly_mid         REAL,
    ev               REAL NOT NULL,        -- q/ask − 1 (+EV carries RISK, not arb)
    edge_direction   TEXT,                 -- buy_yes | no_edge
    confidence_tier  TEXT NOT NULL,        -- excluded | low | medium | high
    reasons          TEXT,                 -- JSON list of tier reasons
    depth_usd        REAL,
    freshness_hours  REAL,
    match_method     TEXT,
    match_confidence REAL,
    -- settle-later: filled from the 90' score after kickoff.
    home_goals       INTEGER,
    away_goals       INTEGER,
    outcome          INTEGER,              -- 0=H,1=D,2=A (the actual result)
    outcome_hit      INTEGER,              -- 1 iff the bought YES resolved true
    settled_at       TEXT,
    PRIMARY KEY (match_date, fixture_id, outcome_spec, line)
)
"""


def _yes_resolves(spec: str, line: float | None, hg: int, ag: int) -> int | None:
    """1 iff the bought YES of ``spec`` (at ``line``) resolves true given the 90'
    score, 0 if it loses, None for an unknown spec. Half-lines ⇒ no push."""
    margin = hg - ag
    total = hg + ag
    if spec == "HOME_WIN":
        return 1 if margin > 0 else 0
    if spec == "DRAW":
        return 1 if margin == 0 else 0
    if spec == "AWAY_WIN":
        return 1 if margin < 0 else 0
    if line is None:
        return None
    if spec == "HANDICAP_HOME":
        return 1 if margin + line > 0 else 0   # home covers `line`
    if spec == "HANDICAP_AWAY":
        return 1 if -margin + line > 0 else 0   # away covers `line`
    if spec == "OVER":
        return 1 if total > line else 0
    if spec == "UNDER":
        return 1 if total < line else 0
    return None


def ensure_polymarket_gaps_table(db_path: str) -> None:
    """Create the table if missing; migrate the pre-让球 schema (no ``line`` column,
    3-col PK) in place, preserving existing moneyline rows (line ← sentinel).
    Idempotent."""
    with open_db(db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(polymarket_gaps)")]
        if not cols:
            conn.execute(POLYMARKET_GAPS_SCHEMA)
            return
        if "line" in cols:
            return
        # Old schema → rebuild with `line` + 4-col PK, carrying rows over.
        old_cols = ", ".join(cols)
        conn.executescript(
            "BEGIN;"
            "ALTER TABLE polymarket_gaps RENAME TO _polymarket_gaps_old;"
            + POLYMARKET_GAPS_SCHEMA + ";"
            + f"INSERT INTO polymarket_gaps ({old_cols}, line) "
              f"SELECT {old_cols}, {_NO_LINE} FROM _polymarket_gaps_old;"
              "DROP TABLE _polymarket_gaps_old;"
              "COMMIT;"
        )
        log.info("polymarket_gaps migrated to line-aware schema (%d cols carried)", len(cols))


def _as_dict(gap: object) -> dict:
    if isinstance(gap, dict):
        return gap
    return {
        "fixture_id": gap.fixture_id, "league": gap.league,
        "home_team": gap.home_team, "away_team": gap.away_team,
        "match_date": gap.match_date, "kickoff_utc": gap.kickoff_utc,
        "series_slug": gap.series_slug, "event_slug": gap.event_slug,
        "yes_token": gap.yes_token, "outcome_spec": gap.outcome_spec,
        "line": gap.line, "q_fair": gap.q_fair, "poly_ask": gap.poly_ask,
        "poly_mid": gap.poly_mid, "ev": gap.ev, "edge_direction": gap.edge_direction,
        "confidence_tier": gap.confidence_tier, "reasons": gap.reasons,
        "depth_usd": gap.depth_usd, "freshness_hours": gap.freshness_hours,
        "match_method": gap.match_method, "match_confidence": gap.match_confidence,
    }


def record_polymarket_gap(
    db_path: str, gap: object, *, recorded_at: dt.datetime | None = None
) -> bool:
    """Upsert one detected gap (a polymarket_gap.Gap or an equivalent dict).

    Idempotent on (match_date, fixture_id, outcome_spec, line): re-logging refreshes
    the price/EV/tier columns (prices move) but leaves a filled outcome intact.

    → True 表示写了;**False = 盘中价拒写**(观测时刻已到/过开球,见模块头)。拒写
    的行不会覆盖同键上那条合法的赛前观测 —— 这正是拒写而非打标的理由。
    """
    g = _as_dict(gap)
    observed = recorded_at or dt.datetime.now(dt.UTC)
    if _is_inplay(g.get("kickoff_utc"), observed):
        log.warning(
            "拒写盘中价:fixture=%s %s line=%s observed=%s kickoff=%s — "
            "赛前错价日志不收开球后报价(也不许它覆盖同键的赛前行)",
            g.get("fixture_id"), g.get("outcome_spec"), g.get("line"),
            observed.isoformat(timespec="seconds"), g.get("kickoff_utc"),
        )
        return False
    ts = observed.isoformat(timespec="seconds")
    reasons = g.get("reasons")
    reasons_json = json.dumps(reasons, ensure_ascii=False) if reasons is not None else None
    line = float(g["line"]) if g.get("line") is not None else _NO_LINE
    ensure_polymarket_gaps_table(db_path)  # own connection (migration-aware); never nest
    with open_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO polymarket_gaps (
                match_date, fixture_id, outcome_spec, line, recorded_at, league,
                home_team, away_team, kickoff_utc, series_slug, event_slug,
                yes_token, q_fair, poly_ask, poly_mid, ev, edge_direction,
                confidence_tier, reasons, depth_usd, freshness_hours,
                match_method, match_confidence
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(match_date, fixture_id, outcome_spec, line) DO UPDATE SET
                recorded_at = excluded.recorded_at,
                league = excluded.league,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                kickoff_utc = excluded.kickoff_utc,
                series_slug = excluded.series_slug,
                event_slug = excluded.event_slug,
                yes_token = excluded.yes_token,
                q_fair = excluded.q_fair,
                poly_ask = excluded.poly_ask,
                poly_mid = excluded.poly_mid,
                ev = excluded.ev,
                edge_direction = excluded.edge_direction,
                confidence_tier = excluded.confidence_tier,
                reasons = excluded.reasons,
                depth_usd = excluded.depth_usd,
                freshness_hours = excluded.freshness_hours,
                match_method = excluded.match_method,
                match_confidence = excluded.match_confidence
            """,
            (
                str(g["match_date"]), int(g["fixture_id"]), g["outcome_spec"], line, ts,
                g.get("league"), g.get("home_team"), g.get("away_team"),
                g.get("kickoff_utc"), g.get("series_slug"), g.get("event_slug"),
                g.get("yes_token"), float(g["q_fair"]), float(g["poly_ask"]),
                g.get("poly_mid"), float(g["ev"]), g.get("edge_direction"),
                g["confidence_tier"], reasons_json, g.get("depth_usd"),
                g.get("freshness_hours"), g.get("match_method"),
                g.get("match_confidence"),
            ),
        )
    return True


def fetch_polymarket_gaps(db_path: str, *, settled_only: bool = False) -> list[dict]:
    """Return all polymarket_gaps rows as dicts (newest match first). The moneyline
    ``line`` sentinel is surfaced as None."""
    ensure_polymarket_gaps_table(db_path)
    with open_db(db_path) as conn:
        where = "WHERE outcome IS NOT NULL" if settled_only else ""
        cur = conn.execute(
            f"SELECT * FROM polymarket_gaps {where} "
            "ORDER BY match_date DESC, ev DESC"
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    for r in rows:
        if r.get("line") == _NO_LINE:
            r["line"] = None
    return rows


def settle_polymarket_gaps(
    db_path: str,
    *,
    fetch_fixtures: Callable[[dt.date], list[dict]] | None = None,
    today: dt.date | None = None,
) -> int:
    """Fill the outcome columns for unsettled, kicked-off gaps from the 90' score.

    Groups unsettled rows by match_date, fetches that day's fixtures once, indexes
    by fixture_id, and writes (home_goals, away_goals, outcome, outcome_hit).
    ``outcome_hit`` = 1 iff the bought YES of that (spec, line) resolved true.
    ``fetch_fixtures(date) -> list[fixture]`` is injectable for tests.
    Returns the number of rows newly settled.
    """
    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    ensure_polymarket_gaps_table(db_path)
    settled = 0
    with open_db(db_path) as conn:
        cur = conn.execute(
            "SELECT match_date, fixture_id, outcome_spec, line FROM polymarket_gaps "
            "WHERE outcome IS NULL"
        )
        unsettled = cur.fetchall()
        groups: dict[str, list[tuple[int, str, float]]] = {}
        for md, fid, spec, line in unsettled:
            try:
                d = dt.date.fromisoformat(md)
            except (ValueError, TypeError):
                continue
            if d > today:
                continue
            groups.setdefault(md, []).append((fid, spec, line))

        ts = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        for md, items in groups.items():
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(md))
            except Exception as exc:  # noqa: BLE001
                log.warning("polymarket settle: fetch failed for %s: %s", md, exc)
                continue
            by_id: dict[int, dict] = {}
            for fx in fixtures:
                fid = (fx.get("fixture") or {}).get("id")
                if fid is not None:
                    by_id[int(fid)] = fx
            for fid, spec, line in items:
                fx = by_id.get(int(fid))
                if fx is None:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                real_line = None if line == _NO_LINE else line
                hit = _yes_resolves(spec, real_line, hg, ag)
                if hit is None:
                    continue
                upd = conn.execute(
                    "UPDATE polymarket_gaps SET home_goals=?, away_goals=?, "
                    "outcome=?, outcome_hit=?, settled_at=? "
                    "WHERE match_date=? AND fixture_id=? AND outcome_spec=? AND line=? "
                    "AND outcome IS NULL",
                    (hg, ag, outcome, hit, ts, md, fid, spec, line),
                )
                settled += max(0, upd.rowcount)
    return settled
