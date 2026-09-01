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

from nutmeg.v4.data.odds_source_aliases import canonical_league, canonical_team

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
    odds_update    TEXT,                    -- the BOOKMAKER's own line timestamp
    odds_source    TEXT                     -- 'odds_api' | 'api_football' — 这条价来自哪个源
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


# 老库补列(2026-07-23)。DDL 是 CREATE TABLE IF NOT EXISTS,对已存在的表加不了列,
# 所以照 crown_close_history 的幂等写法走 ALTER。老行留 NULL = 「不知道来自哪个源」,
# **不猜**:这批历史行确实无从追溯,伪造一个值比留空更坏。
_ADDED_COLUMNS = (("odds_source", "TEXT"),)


def ensure_odds_snapshots(conn: sqlite3.Connection) -> None:
    """Idempotent DDL + 列迁移 — safe to call on every write."""
    conn.executescript(_DDL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(odds_snapshots)")}
    for col, decl in _ADDED_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE odds_snapshots ADD COLUMN {col} {decl}")
            log.info("odds_snapshots: 迁移新增列 %s", col)


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


#: 正典开球时刻字面 —— UTC + `+00:00` 后缀(B 型)。
#: 选 B 不选 A(`…Z`)是因为库里 B 是多数、且 `datetime.isoformat()` 天然产 B。
_KICKOFF_CANON_SUFFIX = "+00:00"


def _norm_kickoff(v) -> str | None:
    """开球时刻 → **单一正典字面**(UTC,`YYYY-MM-DDTHH:MM:SS+00:00`)。

    ⛔ **解析失败原样返回,绝不猜。** 同 `canonical_team` 的 fail-open ——
    这里宁可留一个怪字面让哨兵
    (`test_no_kickoff_value_lacks_a_timezone_offset`)喊,
    也不要把一个我们没看懂的串编成看起来正常的时刻。

    🚨 **只影响新行。** 回填 `odds_snapshots` 是本仓红线 ⇒ 那 4,856 行 `…Z`
    字面**永久留在库里**。
    ⇒ **消费方必须永久保持格式容忍**:任何人若因为「写入侧已归一」就开始写
       `a.kickoff_utc = b.kickoff_utc`,会静默丢掉全部历史 closing 行。
       这正是本仓最贵的那一族。
    """
    if v is None or v == "":
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        # `fromisoformat` 认 B 与 C(空格分隔、`+00` 短偏移),Py≥3.11 也认 `Z`。
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s          # ⛔ 看不懂 → 原样,交给哨兵
    if d.tzinfo is None:
        # 🚨 无偏移的值是**唯一会吞腿**的形态:JS `new Date()` 按本地时区解释它
        #    (TZ=Asia/Shanghai 时早 8 小时)⇒ 未开赛被判成已开赛 ⇒ 静默剔出可投注列表。
        #    ⛔ 但**不在这里猜时区** —— 原样返回,让哨兵红。
        return s
    return d.astimezone(dt.UTC).isoformat(timespec="seconds")


def record_row_snapshot(
    db_path: str | Path,
    row: dict,
    *,
    fixture_id: int | None = None,
    envelope: dict | None = None,
    bookmaker_id: int | None = None,
    source: str = "gather",
    captured_at: str | None = None,
) -> bool:
    """Append one line-state snapshot from an ingest_odds-style row dict.

    ``row`` is the ``fixture_envelope_to_csv_row`` output (psc_*, ou_line,
    psc_over25/psc_under25, odds_update, kickoff_utc, date/league/teams).
    ``envelope`` (optional) additionally captures the Asian-Handicap board.

    ``captured_at`` — ISO 时刻,**观测发生的那一刻**(不是落盘那一刻)。默认
    None = 此刻。两类调用方必须显式传:
      ① 历史回填(2026-07-23):必须传该快照的真实时刻,否则补回来的行全戳成
         "今天",在时间轴上落错位置 —— 空洞照旧显示为空洞(数据明明已找回),
         而 CLV / 线史分析会看到几十行挤在同一秒。
      ② 🚨 **带 pre-kickoff 闸的实时采集**(2026-09-01):判闸用的时刻和落库的
         `captured_at` 必须是**同一个值**。`closing_odds` 此前让本函数在写库那
         一刻自己取 now,于是「闸看到的 now」和「戳进去的 now」之间隔了一段 δ
         (p50 0.2ms,但本函数 `busy_timeout=3000` ⇒ 最坏 3s)⇒ 2026-08-30 写出
         2 行 `captured_at > kickoff_utc`。传入判过闸的那个时刻即根除,零边界。

    Returns True iff a NEW state row was inserted; False on skip (待开盘 row,
    unchanged state) or on ANY internal failure (logged, never raised).
    """
    try:
        # ⭐ 2026-08-01 —— 队名归一,**必须在这里、在任何读取之前**。
        #
        # 两个上游对同一支队用不同英文名(API-Football 走 cup_market = 盘面;
        # Odds API 走 closing),实测 9 联赛 61 个名字只在 closing 侧出现 ⇒
        # **收盘线静默叠加不上盘面那一行**:join 不通、CLV 少数据,而日志全绿。
        #
        # 修在**唯一 sink**,不在两个生产者里各打一遍补丁(`记忆 health-check-
        # guardrails` 的 Altitude 条:修共享 sink)。表里没有的名字**原样通过**,
        # 由 `scripts/derive_odds_name_aliases.py` 探测器报出来,绝不在这里猜。
        # ⚠️ league 自己也有两套词汇(closing_odds 的 `SPORT_KEYS.get(sk, sk)`
        # 宽进写法会把原始 sport_key 落库)。**先归一联赛再查队名表**,否则
        # (联赛, 队名) 查表整个落空 —— 归一变成 no-op 而日志照样全绿。
        row = dict(row)          # 不改调用方的 dict(它还要写 CSV / 喂别的消费者)
        _lg = canonical_league(row.get("league"))
        row["league"] = _lg
        row["home_team"] = canonical_team(_lg, row.get("home_team"))
        row["away_team"] = canonical_team(_lg, row.get("away_team"))
        # 🚨 `kickoff_utc` 同一时刻有**三种字面**(2026-08-14 实测):
        #     A `2026-07-01T16:00:00Z`      ← closing(Odds API commence_time 直抄)
        #     B `2026-06-13T12:00:00+00:00` ← 其余 5 个生产者(API-Football)
        #     C `2026-06-30 21:00:00+00`    ← polymarket 侧(当前不入本表)
        # ⇒ `a.kickoff_utc = b.kickoff_utc` **永不成立**:同一 join 不带它 144,686 行、
        #   带它 **0 行**。全仓爆炸半径当时是 0,但那是**运气**不是设计
        #   —— 见 `tests/v4/test_kickoff_slot_normalisation.py` 的长注释。
        # 同 league/队名:修在**唯一 sink**,不在 6 个生产者里各打一遍补丁。
        row["kickoff_utc"] = _norm_kickoff(row.get("kickoff_utc"))

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
                "asian_handicap, odds_update, odds_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    captured_at
                    or dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    source, fixture_id,
                    row.get("league"), row.get("date"),
                    row.get("home_team"), row.get("away_team"),
                    row.get("kickoff_utc") or None,
                    *state,
                    # _apply_odds_api_overlay 打的标;没打过 = 走的 AF 镜像。
                    row.get("odds_source") or "api_football",
                ))
        return True
    except Exception:  # noqa: BLE001 — a lost snapshot must never break a cron
        log.warning(
            "odds snapshot failed for %s vs %s (db=%s)",
            row.get("home_team"), row.get("away_team"), db_path, exc_info=True)
        return False
