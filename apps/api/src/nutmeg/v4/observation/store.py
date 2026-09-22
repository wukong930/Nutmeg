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


SCHEMA_VERSION = 3  # v3 made single_predictions λ / p_1x2 nullable (2026-09-22)


# Valid snapshot_phase values. "closing" is the legacy default used everywhere
# pre-W8; "pre_close" is for ≥60-min-before-kickoff snapshots; "post_close"
# is a snapshot taken AFTER closing line is published (rare; for diagnostics).
SNAPSHOT_PHASES = ("pre_close", "closing", "post_close")


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
    metadata_json TEXT,
    -- V5 W8 additions: capture which snapshot phase this session represents
    -- (pre_close = 60 min before kickoff; closing = at closing line publish;
    -- post_close = diagnostic snapshot after closing). Most legacy rows are
    -- "closing" — the migration backfills NULLs to that.
    snapshot_phase TEXT DEFAULT 'closing',
    -- Which model backend produced these recommendations (W7)
    model_type    TEXT DEFAULT 'lightgbm',
    -- 2026-07-23 — 本次下注所依据的 Pinnacle 价**出处**:
    --   'odds_api' | 'api_football' | 'manual' | 'mixed' | NULL(不知道)
    -- 为什么要:owner 在 OA 没覆盖的赛事上手填 Pinnacle(欧战资格战等),手填值
    -- 会随 📌 记一笔原样落账,而此前**没有任何字段能把它和抓来的价区分开** ——
    -- 手填若是陈旧价或手滑打错,台账会静默记下一个虚构价,事后谁也查不出来。
    -- NULL 一律留 NULL(老行、以及请求里没带该字段的),**不回填猜测值**。
    odds_source   TEXT
);

CREATE TABLE IF NOT EXISTS single_predictions (
    prediction_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL,
    match_date       TEXT NOT NULL,
    league           TEXT NOT NULL,
    home_team        TEXT NOT NULL,
    away_team        TEXT NOT NULL,
    -- ⛔ 2026-09-22:这五列从 NOT NULL 改成**可空**。
    -- 起因:非模型会话(manual_bet / market_handicap)本来就没有 λ 和模型 1X2,
    -- 而 NOT NULL 逼着写入方编一个 `0.0` —— 那是个**长得完全合法的数**,
    -- 任何按 λ 聚合的计算都会被它静默拉低(`AVG(lambda_home)` 不会报错)。
    -- ⭐ 同本文件 `odds_source` 那条的理由:没有可推断的值就留 NULL,
    --    **诚实地说「不知道」**,而不是填一个看起来像数据的东西。
    lambda_home      REAL,
    lambda_away      REAL,
    p_home_1x2       REAL,
    p_draw_1x2       REAL,
    p_away_1x2       REAL,
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
    # Migration: add snapshot_phase + model_type to pre-W8 v1 DBs that already
    # exist on disk. SQLite is forgiving here — ALTER TABLE ADD COLUMN is
    # idempotent if the column doesn't exist, but raises if it does, so we
    # check first via PRAGMA.
    cur = conn.execute("PRAGMA table_info(recommendation_sessions)")
    cols = {row["name"] for row in cur.fetchall()}
    if "snapshot_phase" not in cols:
        conn.execute(
            "ALTER TABLE recommendation_sessions ADD COLUMN snapshot_phase TEXT DEFAULT 'closing'"
        )
        conn.execute(
            "UPDATE recommendation_sessions SET snapshot_phase = 'closing' "
            "WHERE snapshot_phase IS NULL"
        )
    if "model_type" not in cols:
        conn.execute(
            "ALTER TABLE recommendation_sessions ADD COLUMN model_type TEXT DEFAULT 'lightgbm'"
        )
        conn.execute(
            "UPDATE recommendation_sessions SET model_type = 'lightgbm' "
            "WHERE model_type IS NULL"
        )
    # 2026-07-23 — 盘口来源溯源。⚠️ 与上面两条不同:**不做任何 UPDATE 回填**。
    # snapshot_phase/model_type 有可推断的历史默认值('closing'/'lightgbm'),
    # odds_source 没有 —— 已记的注确实无从追溯,给它填个 'api_football' 就是
    # 在造假。老行永远留 NULL = 诚实地说「不知道」。
    if "odds_source" not in cols:
        conn.execute("ALTER TABLE recommendation_sessions ADD COLUMN odds_source TEXT")
    _migrate_nullable_lambdas(conn)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _migrate_nullable_lambdas(conn: sqlite3.Connection) -> None:
    """v2 → v3:把 `single_predictions` 的 λ / p_1x2 从 NOT NULL 改成可空,并回填。

    SQLite 不能 `ALTER TABLE ... DROP NOT NULL`,只能重建表。幂等:先查
    `PRAGMA table_info` 的 notnull 标志,已经可空就直接返回。

    回填两类**编出来的**值(判据都是「模型不可能产出这个」):
      · `λ <= 0`        —— `score_grid` 对非正 λ 直接抛,模型行不可能是它
      · 三个 p_1x2 全 0 —— 合法的 1X2 三元组和为 1

    ⛔ **不碰 `user_directional_combo` 那类手填但为正的 λ**:它们是用户真实录入的
       数,不是缺失值。区分「谁是模型行」的判据永远是 `model_type`,
       **不是 `λ > 0`** —— 后者已被实际证伪(库里有 λ=1.31/1.89 的手填行,
       两位小数是它的指纹)。
    """
    cur = conn.execute("PRAGMA table_info(single_predictions)")
    info = {r["name"]: r["notnull"] for r in cur.fetchall()}
    if not info:                       # 表还没建(全新库),SCHEMA_SQL 已经是可空版
        return
    if not info.get("lambda_home", 0):  # 已经可空
        return
    # ⚠️ 必须先结掉**外面的隐式事务**:`_init_schema` 上游可能刚跑过 ALTER,
    #    Python sqlite3 会为它开一个隐式事务,此时再 `BEGIN` 直接
    #    `cannot start a transaction within a transaction`。
    #    (副本演练时没触发 —— 那次列已存在、ALTER 分支没走。夹具比真库更严。)
    prev_isolation = conn.isolation_level
    conn.commit()
    conn.isolation_level = None          # 自管事务
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("""
            CREATE TABLE single_predictions_v3 (
                prediction_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       INTEGER NOT NULL,
                match_date       TEXT NOT NULL,
                league           TEXT NOT NULL,
                home_team        TEXT NOT NULL,
                away_team        TEXT NOT NULL,
                lambda_home      REAL,
                lambda_away      REAL,
                p_home_1x2       REAL,
                p_draw_1x2       REAL,
                p_away_1x2       REAL,
                handicap_home    INTEGER,
                p_home_handicap  REAL,
                p_draw_handicap  REAL,
                p_away_handicap  REAL,
                FOREIGN KEY (session_id) REFERENCES recommendation_sessions(session_id)
            )""")
        conn.execute("""
            INSERT INTO single_predictions_v3
            SELECT prediction_id, session_id, match_date, league, home_team, away_team,
                   CASE WHEN lambda_home > 0 THEN lambda_home END,
                   CASE WHEN lambda_away > 0 THEN lambda_away END,
                   CASE WHEN p_home_1x2 = 0 AND p_draw_1x2 = 0 AND p_away_1x2 = 0
                        THEN NULL ELSE p_home_1x2 END,
                   CASE WHEN p_home_1x2 = 0 AND p_draw_1x2 = 0 AND p_away_1x2 = 0
                        THEN NULL ELSE p_draw_1x2 END,
                   CASE WHEN p_home_1x2 = 0 AND p_draw_1x2 = 0 AND p_away_1x2 = 0
                        THEN NULL ELSE p_away_1x2 END,
                   handicap_home, p_home_handicap, p_draw_handicap, p_away_handicap
            FROM single_predictions""")
        n_old = conn.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0]
        n_new = conn.execute("SELECT COUNT(*) FROM single_predictions_v3").fetchone()[0]
        # 🚨 行数守卫:重建丢行是不可逆的,宁可整个回滚
        if n_old != n_new:
            conn.execute("ROLLBACK")
            raise RuntimeError(f"single_predictions 重建行数不符:{n_old} → {n_new},已回滚")
        conn.execute("DROP TABLE single_predictions")
        conn.execute("ALTER TABLE single_predictions_v3 RENAME TO single_predictions")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_single_predictions_match "
                     "ON single_predictions(match_date, league, home_team, away_team)")
        conn.execute("COMMIT")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.isolation_level = prev_isolation


def init_db(path: str | Path) -> None:
    """Public init function (idempotent). Creates DB + schema if missing."""
    with open_db(path):
        pass


# --- Write helpers --------------------------------------------------------

def _request_odds_source(request: dict) -> Optional[str]:
    """从请求里读出这次下注所依据的 Pinnacle 价的出处。

    在**共享 sink** 里做,而不是让五个 recorder 各自传参 —— 加新 recorder 时会自动
    带上,不会漏(旧教训:逐生产者打补丁的东西迟早有人忘)。

    两种请求形状都认:
      · fixtures 列表(/recommend、/recommend/single)—— 每场各带各的 odds_source
      · 扁平字段(/recommend/market-handicap)—— 手填 Pinnacle 走的就是这条

    返回 'manual' / 'odds_api' / 'api_football' / 'mixed' / None。
    ⚠️ 全部缺失 → None(不知道),**绝不默认成 'api_football'** —— 那等于把
    「没告诉我」伪装成「我查过了」,正是这一整列想防的事。
    """
    if not isinstance(request, dict):
        return None
    srcs: set[str] = set()
    fx = request.get("fixtures")
    if isinstance(fx, list):
        for f in fx:
            if isinstance(f, dict) and f.get("odds_source"):
                srcs.add(str(f["odds_source"]))
    elif request.get("odds_source"):
        srcs.add(str(request["odds_source"]))
    if not srcs:
        return None
    # 一次 session 里混了多个源(批量 gather:OA 覆盖的场次叠了 overlay、其余留 AF)
    # → 'mixed'。硬挑一个当代表会让后续切片悄悄算错。
    return srcs.pop() if len(srcs) == 1 else "mixed"


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
    snapshot_phase: str = "closing",
    model_type: str = "lightgbm",
) -> int:
    if snapshot_phase not in SNAPSHOT_PHASES:
        raise ValueError(
            f"snapshot_phase must be one of {SNAPSHOT_PHASES}, got {snapshot_phase!r}"
        )
    cur = conn.execute(
        """
        INSERT INTO recommendation_sessions
            (created_at, bankroll, model_cutoff, model_trained_at,
             n_fixtures, n_recommendations, request_json, metadata_json,
             snapshot_phase, model_type, odds_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            bankroll, model_cutoff, model_trained_at,
            n_fixtures, n_recommendations,
            json.dumps(request, ensure_ascii=False, default=str),
            json.dumps(metadata or {}, ensure_ascii=False, default=str),
            snapshot_phase, model_type, _request_odds_source(request),
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
    lambda_home: float | None,
    lambda_away: float | None,
    p_home_1x2: float | None,
    p_draw_1x2: float | None,
    p_away_1x2: float | None,
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
