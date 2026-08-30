"""竞彩 SP staleness observations — the soft-book half of the edge map.

Why: EV = P(true) × 竞彩SP − 1, and the only place edge can live is where 竞彩's
FROZEN SP (the lottery stops updating ~23:00 daily) drifts from Pinnacle's LIVE
fair as news/money keep moving the sharp line to kickoff. ``odds_snapshots``
already captures the Pinnacle trajectory (open→close); this table captures the
OTHER half — the 竞彩 SP the user prices a match at — so the gap (and whether
betting it actually wins) can be measured on the right axis.

Capture is SILENT and UPSERT-LATEST keyed on (match_date, home, away, market):
the user re-prices a match many times before kickoff to verify, so each capture
OVERWRITES — the table always holds the canonical (latest = nearest-kickoff) 竞彩
line, auto-solving the "填很多次" duplication. Settle-later columns hold the
result and are NEVER clobbered by a re-capture. NEVER raises out of the capture
path: a lost observation must not break the user's live EV view.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import sqlite3

from nutmeg.v4.data.league_labels import canonical_league
from pathlib import Path

log = logging.getLogger(__name__)

# ── 捕获端 sanity 闸(2026-07-19 RCA:周六212 SJK vs KuPS 的 hhad a 腿官方终盘
# 5.25 被手滑成 7.25,经 market_mode 静默捕获写成「终盘」,protect_manual 又让它
# 免疫后续 cron = 永生;面板让球 EV 假 +71%(真 +24%)。横扫 2026-07 已结算 164 可
# 比行:官方 sporttery 通道 0 损坏,损坏 5/5 全在 market_mode 手填。
# docs/jingcai_sp_capture_integrity_2026-07-19.md)──────────────────────────
#
# 闸 1 · booksum(Σ1/odds)带:竞彩管理员 vig 实测铁桶 — 2024-25 官方档案 15,959
# 场终盘 booksum ∈ [1.125, 1.140],2026-07 现值 373 行 ∈ [1.127, 1.130]。官方变盘
# 前后 booksum 恒定,而单腿脏值/跨变盘混拼必然把它拉出带(7.25 → 1.077)。带宽
# [1.10, 1.15] 对上述全部官方数据零误报,仍容时代漂移;若竞彩哪天真把 vig 挪出带,
# 捕获集体拒写 → jingcai_sp 停更 → data_freshness 哨兵响 = 响亮失败,不是静默污染。
# ⚠ 曾考虑「与前值突变」闸,实测否决:合法 open→终盘单腿漂移最大 2.04×(>40% 的
# 41/16k 场),幅度上与手滑不可分;booksum 才是判别不变量,勿回退成突变闸。
_BOOKSUM_MIN, _BOOKSUM_MAX = 1.10, 1.15
# 闸 2 · 开球后手填拒写(仅 market_mode 源):冻结 SP 开球后不可能再变,开球后的
# 手填框值只会是 what-if/误触(SJK 案写于开球 62 min 后)。官方 sporttery 源不受
# 此闸 — calculator 端点本就只列在售(未开球)场次。容差 15 min 吸收名义开球偏差。
_POST_KICKOFF_GRACE_S = 15 * 60


def _sane_booksum(h: float, d: float, a: float) -> float | None:
    """三腿合法(1<x≤1000,同 sporttery._odds3 的物理闸)时返回 booksum,否则 None。"""
    if not all(math.isfinite(x) and 1.0 < x <= 1000.0 for x in (h, d, a)):
        return None
    return 1.0 / h + 1.0 / d + 1.0 / a


def _past_kickoff(kickoff_utc: str | None, *, grace_s: int = _POST_KICKOFF_GRACE_S) -> bool:
    """now > kickoff+grace?(kickoff 未知/不可解析 → False = fail-open,手填新场仍可行)"""
    if not kickoff_utc:
        return False
    try:
        ko = dt.datetime.fromisoformat(str(kickoff_utc))
    except ValueError:
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=dt.UTC)
    return dt.datetime.now(dt.UTC) > ko + dt.timedelta(seconds=grace_s)


# ── 捕获时 Pinnacle 补录(2026-07-27)────────────────────────────────────────
# 病情:写本表 86% 行的 cron(cli/ingest_sporttery)读的是竞彩自己的源,手里
# 根本没有 Pinnacle ⇒ 那些行 psc_* 全空,永远进不了 CLV 账本的**选中腿**计数
# (选中腿要用捕获时 EV 挑)。实测填充率:竞彩 cron 32/469 = 7%,面板 68/68 = 100%。
# 而这条线一直躺在 odds_snapshots 里。修在 **sink** 而不是逐生产者打补丁,
# 以后新增的捕获路径自动带上(体检 altitude 惯例)。
_PINN_AT_CAPTURE_COLS = ("psc_home", "psc_draw", "psc_away",
                         "ou_line", "psc_over", "psc_under")


def _pinnacle_at_capture(
    conn: sqlite3.Connection,
    *,
    match_date: str,
    home_team: str,
    away_team: str,
    as_of: str,
) -> tuple | None:
    """Pinnacle 在 ``as_of``(竞彩捕获那一刻)的线,按 _PINN_AT_CAPTURE_COLS 顺序返回。

    两道闸都是**承重**的:

    1. ``captured_at <= as_of`` —— **绝不取更晚的快照**。账本的选中腿之所以用
       捕获时 EV 来挑,就是为了让「选择」不含未来信息;把今晚的 Pinnacle 钉到
       今早的竞彩捕获上,选择就看见了收盘线已经包含的信息,selected-CLV 会从
       「测量」退化成**循环论证**。这一闸实测只掉 2/433 行,几乎不要钱。
    2. 非盘中 —— 领先方的滚球线(1.06/…/53.96)曾经污染过姊妹表一次
       (Mexico-Ecuador,体检 B1)。kickoff_utc 为空(2026-07 前的旧行)无从判断,
       按 fail-open 保留。

    join 键用 (home, away, 日期±1),**不是 fixture_id**(cron 路径该列全空,见
    上方 DDL 注释);两侧队名都已过同一套 canonical EN,实测命中 99%。
    """
    d0 = str(match_date)[:10]
    return conn.execute(
        f"SELECT {', '.join(_PINN_AT_CAPTURE_COLS)} FROM odds_snapshots "
        "WHERE home_team = ? AND away_team = ? "
        "AND psc_home > 1 AND psc_draw > 1 AND psc_away > 1 "
        "AND substr(match_date, 1, 10) BETWEEN date(?, '-1 day') AND date(?, '+1 day') "
        "AND captured_at <= ? "
        "AND (kickoff_utc IS NULL OR captured_at < kickoff_utc) "
        "ORDER BY captured_at DESC LIMIT 1",
        (home_team, away_team, d0, d0, as_of)).fetchone()


_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_sp (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at  TEXT NOT NULL,          -- when WE logged the 竞彩 SP (UTC ISO)
    source       TEXT NOT NULL,          -- market_mode | manual | ...
    -- ⚠️ fixture_id 目前**实际全空**(2026-07-22 实测 467/467 NULL)。不是 bug:
    -- 身份键是下面的 UNIQUE(不含它),而写绝大多数行的 cron 路径
    -- (cli/ingest_sporttery.py)输入是竞彩官方数据 —— 中文队名+赔率+日期,
    -- 里面根本没有 API-Football 的 fixture_id。只有面板手填路径(api/routes.py)
    -- 会传。**别拿这一列当 join 键**:join 上去只会静默得到空集(我踩过一次)。
    -- 要关联 odds_snapshots 请用 (home_team, away_team, 日期±1),两侧队名都已过
    -- zh_to_canonical / gather 的同一套 canonical EN。
    fixture_id   INTEGER,
    -- league:**新写入一律是规范形**(竞彩中文缩写),2026-08-30 起在捕获处归一。
    -- 历史上这里是双轨的(cron 写 '芬超',面板写 'FIN_VEIKKAUSLIIGA'),后果是
    -- 按 league 分组会把同一联赛拆成两行(实测芬超 33 + 11)。当时留着没改,
    -- 理由是「等真有下游要 per-league 聚合时一并定」—— 结果 25 天里靠回填清了
    -- 4 次(08-05/08-13/08-24/08-30),每轮再生 3-8 个写法。⇒ 改在写入侧。
    -- ⚠️ 读取方**仍然必须**过 `canonical_league`:存量老行还是双轨的,而且
    --    `WHERE league IN (…)` 跑在取行之前 —— 那要用 `league_filter_variants`。
    -- 不影响 EV(EV 只走队名 join + 赔率)。
    league       TEXT,
    match_date   TEXT NOT NULL,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    kickoff_utc  TEXT,
    market       TEXT NOT NULL DEFAULT 'had',   -- had(1X2) | hhad(让球) | ttg ...
    handicap_home INTEGER,   -- 竞彩 让球线 (DC: −1=主队让1球); NULL for 'had'
    single_available INTEGER,   -- 竞彩 单关可投标记 (1=可单关 / 0=仅过关); PER-MARKET (pool-level)
    -- 竞彩 SP (the frozen lottery line the user is pricing against)
    jc_home      REAL, jc_draw REAL, jc_away REAL,
    -- Pinnacle raw at capture time (vig included) — 竞彩 vs Pinnacle-at-capture
    psc_home     REAL, psc_draw REAL, psc_away REAL,
    ou_line      REAL, psc_over REAL, psc_under REAL,   -- capture-time O/U (hhad CLV reverse-fit)
    -- 初盘 (11:00 开售) 竞彩 SP — set ONCE, preserved across the latest=终盘 overwrites
    -- (lets us measure 竞彩's own line movement open→freeze; jc_* stays the canonical 终盘)
    jc_open_home REAL, jc_open_draw REAL, jc_open_away REAL, opened_at TEXT,
    -- settle-later (filled by settle_jingcai_sp; never clobbered on re-capture)
    -- ⚠️ `ft_outcome` **永远是原始 1X2 结果**(0 主胜 / 1 平 / 2 客胜),与 `market` 无关。
    -- 对让球行它是**真值但不是你要的那个**:列名/类型/值域三样都长得像能直接拿来算
    -- 让球命中率,真那么用实测 404 行里 217 行(53.7%)结论是反的。让球结果看 `hc_outcome`。
    home_goals   INTEGER, away_goals INTEGER, ft_outcome INTEGER, settled_at TEXT,
    -- 让球后的结果(0 让胜 / 1 让平 / 2 让负)—— **只对 market='hhad' 的行有值**。
    -- 由 `market_handicap.handicap_outcome()` 唯一产出;别在别处重算(2026-08-10 收口)。
    hc_outcome   INTEGER,
    UNIQUE(match_date, home_team, away_team, market)
);
CREATE INDEX IF NOT EXISTS idx_jingcai_sp_unsettled
    ON jingcai_sp (settled_at, match_date);
"""


def ensure_jingcai_sp_table(conn: sqlite3.Connection) -> None:
    """Idempotent DDL — safe to call on every write. Includes a forward
    migration: a table created before 让球 support lacks handicap_home, and
    CREATE TABLE IF NOT EXISTS won't add it."""
    conn.executescript(_DDL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jingcai_sp)")}
    if "handicap_home" not in cols:
        conn.execute("ALTER TABLE jingcai_sp ADD COLUMN handicap_home INTEGER")
    for _c in ("psc_over", "psc_under"):   # capture-time O/U — added for hhad CLV reverse-fit
        if _c not in cols:
            conn.execute(f"ALTER TABLE jingcai_sp ADD COLUMN {_c} REAL")
    for _c in ("jc_open_home", "jc_open_draw", "jc_open_away"):  # 初盘 SP (line-movement)
        if _c not in cols:
            conn.execute(f"ALTER TABLE jingcai_sp ADD COLUMN {_c} REAL")
    if "opened_at" not in cols:
        conn.execute("ALTER TABLE jingcai_sp ADD COLUMN opened_at TEXT")
    if "single_available" not in cols:   # 竞彩 单关可投标记 (per-market, forward-only)
        conn.execute("ALTER TABLE jingcai_sp ADD COLUMN single_available INTEGER")
    if "hc_outcome" not in cols:   # 让球后结果 —— 2026-08-10 补,见 _DDL 里那段注释
        conn.execute("ALTER TABLE jingcai_sp ADD COLUMN hc_outcome INTEGER")


def record_jingcai_sp(
    db_path: str | Path,
    *,
    match_date: str,
    home_team: str,
    away_team: str,
    jc_home: float | None = None,
    jc_draw: float | None = None,
    jc_away: float | None = None,
    psc_home: float | None = None,
    psc_draw: float | None = None,
    psc_away: float | None = None,
    ou_line: float | None = None,
    psc_over: float | None = None,
    psc_under: float | None = None,
    fixture_id: int | None = None,
    league: str | None = None,
    kickoff_utc: str | None = None,
    market: str = "had",
    handicap_home: int | None = None,
    single_available: int | None = None,
    source: str = "market_mode",
    protect_manual: bool = False,
    phase: str = "close",
) -> bool:
    """Upsert ONE canonical 竞彩 SP observation for (match_date, home, away,
    market). A re-capture overwrites the line (latest = canonical) but preserves
    any settle-later result. Requires the 竞彩 1X2 triple — returns False (no-op)
    if it is absent, or on ANY internal failure (logged, never raised).

    ``phase='open'`` additionally stamps the 开售 (11:00) 初盘 into ``jc_open_*``
    (+ ``opened_at``), set ONCE and preserved across the latest=终盘 overwrites, so
    竞彩's own open→freeze line movement can be measured. ``jc_*`` always stays the
    canonical 终盘. ``phase='close'`` (default) leaves ``jc_open_*`` untouched.

    两道捕获端 sanity 闸(2026-07-19 RCA,见模块头):booksum ∉ [1.10, 1.15] 拒写
    (所有源);market_mode 源在开球 15 min 后拒写。拒写 = False + warning 日志。"""
    try:
        if jc_home is None or jc_draw is None or jc_away is None:
            return False  # no 竞彩 line to log
        if not (match_date and home_team and away_team):
            return False
        # 联赛标签归一(2026-08-30)—— 两个写入方两套词汇:sporttery cron 写竞彩
        # 中文缩写(西甲/日职),面板「记一笔」写 V4 EN 代码(ESP_LA_LIGA/JPN_J1)。
        # 在**写入侧**归一,而不是靠事后回填:回填只清存量,25 天里已经清了 4 次
        # (08-05 / 08-13 / 08-24 / 08-30),每轮再生 3-8 个写法 —— 那是跑步机不是修复。
        # ⚠️ 必须带真值闸:`canonical_league(None)` 返回 '(未标联赛)' 而**不是** None。
        #    无闸套用会把「不知道联赛」写成一个字面量占位串,并让下方
        #    `COALESCE(excluded.league, ...)` 拿这个占位串覆盖掉已存的真联赛 ——
        #    把「没去看」写成「看过了」,正是本仓反复出现的那类静默污染。
        # 认不出的标签原样透传(fail-open)⇒ data_freshness 的 unknown 检查照常生效。
        if league:
            league = canonical_league(league)
        # 闸 1 — booksum 带(见模块头):单腿脏值/混拼在这里被拒,官方合法盘全通过。
        booksum = _sane_booksum(float(jc_home), float(jc_draw), float(jc_away))
        if booksum is None or not (_BOOKSUM_MIN <= booksum <= _BOOKSUM_MAX):
            log.warning(
                "jingcai_sp REJECT (booksum %s ∉ [%.2f, %.2f]): %s vs %s %s "
                "jc=%s/%s/%s source=%s — 单腿脏值/混拼嫌疑,不入库",
                f"{booksum:.4f}" if booksum is not None else "n/a",
                _BOOKSUM_MIN, _BOOKSUM_MAX, home_team, away_team, market,
                jc_home, jc_draw, jc_away, source)
            return False
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        # 初盘:仅 phase=='open' 记开售 SP;set-once(下方 COALESCE),之后被终盘覆盖也不丢。
        _open = phase == "open"
        o_h = float(jc_home) if _open else None
        o_d = float(jc_draw) if _open else None
        o_a = float(jc_away) if _open else None
        o_at = now if _open else None
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_sp_table(conn)
            ex = conn.execute(
                "SELECT source, kickoff_utc FROM jingcai_sp WHERE match_date=? "
                "AND home_team=? AND away_team=? AND market=?",
                (match_date, home_team, away_team, market)).fetchone()
            # 闸 2 — 开球后 market_mode 拒写(见模块头)。kickoff 取请求值,缺则用
            # 行内已存的(官方 harvest 填过);两处都没有 → fail-open(手填新场)。
            if source == "market_mode" and _past_kickoff(
                    kickoff_utc or (ex[1] if ex else None)):
                log.warning(
                    "jingcai_sp REJECT (post-kickoff market_mode): %s vs %s %s "
                    "jc=%s/%s/%s kickoff=%s — 开球后手填不可信,不覆盖冻结线",
                    home_team, away_team, market, jc_home, jc_draw, jc_away,
                    kickoff_utc or (ex[1] if ex else None))
                return False
            # ── 线史快照(2026-07-25)——「13 次抓、1 次留」的修复 ────────────
            # 挂在两道闸**之后**(脏值走不到这里),但在 protect_manual 分支
            # **之前**:你手填过的场次,cron 依然观测到了竞彩的真实报价 —— 那正是
            # 冻结缺口要的移动数据,不该因为「不覆盖你的手填」就连观测一起丢。
            # append-only + 线态去重,所以加密采样不会让表爆炸。失败不影响本次 upsert。
            from nutmeg.v4.observation.jingcai_sp_snapshots import (
                record_jingcai_sp_snapshot,
            )
            record_jingcai_sp_snapshot(
                db_path, match_date=match_date, home_team=home_team,
                away_team=away_team, market=market,
                jc_home=float(jc_home), jc_draw=float(jc_draw),
                jc_away=float(jc_away), league=league,
                kickoff_utc=kickoff_utc or (ex[1] if ex else None),
                handicap_home=handicap_home, booksum=booksum, source=source)

            if protect_manual and ex and ex[0] == "market_mode":
                # 体检 Wave3 (P2) — the manual-line protection used to ALSO
                # swallow the 初盘 stamp: if the user hand-priced a match
                # before the 11:00 开售 cron ran, jc_open_* was never set
                # (forward-only → the open→freeze movement lost for good).
                # The 初盘 is a pure capture, not a line the user owns —
                # stamp it set-once WITHOUT touching jc_*/psc_*.
                if _open:
                    conn.execute(
                        "UPDATE jingcai_sp SET "
                        "jc_open_home=COALESCE(jc_open_home, ?), "
                        "jc_open_draw=COALESCE(jc_open_draw, ?), "
                        "jc_open_away=COALESCE(jc_open_away, ?), "
                        "opened_at=COALESCE(opened_at, ?) "
                        "WHERE match_date=? AND home_team=? AND away_team=? "
                        "AND market=?",
                        (o_h, o_d, o_a, o_at,
                         match_date, home_team, away_team, market),
                    )
                    return True
                return False  # user's hand-priced line is canonical; don't clobber
            # ── 捕获时 Pinnacle 补录(见 _pinnacle_at_capture)────────────────
            # 三组**各自独立**补:调用方给了的一律不动 —— 面板传来的 psc_* 正是
            # 用户定价时看着的那条线,比事后查表更权威。只填空缺。
            # (补上的 O/U 与调用方给的 1X2 可能来自不同时刻,但比旧行 hhad 反推
            #  退化用「默认总进球」准得多 —— 那是当前 82% 让球行的处境。)
            # 整段 fail-soft:odds_snapshots 不存在/异常都只跳过补录,绝不让一次
            # 竞彩捕获因此丢失(本模块契约:NEVER raises out of the capture path)。
            if psc_home is None or ou_line is None or psc_over is None:
                try:
                    _co = _pinnacle_at_capture(
                        conn, match_date=match_date, home_team=home_team,
                        away_team=away_team, as_of=now)
                except sqlite3.Error:
                    _co = None
                    log.debug("capture-time Pinnacle co-record skipped", exc_info=True)
                if _co:
                    if psc_home is None:
                        psc_home, psc_draw, psc_away = _co[0], _co[1], _co[2]
                    if ou_line is None:
                        ou_line = _co[3]
                    if psc_over is None:
                        psc_over, psc_under = _co[4], _co[5]
            conn.execute(
                "INSERT INTO jingcai_sp (captured_at, source, fixture_id, league, "
                "match_date, home_team, away_team, kickoff_utc, market, handicap_home, "
                "single_available, "
                "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, ou_line, "
                "psc_over, psc_under, jc_open_home, jc_open_draw, jc_open_away, opened_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_date, home_team, away_team, market) DO UPDATE SET "
                "captured_at=excluded.captured_at, source=excluded.source, "
                "fixture_id=COALESCE(excluded.fixture_id, jingcai_sp.fixture_id), "
                "league=COALESCE(excluded.league, jingcai_sp.league), "
                "kickoff_utc=COALESCE(excluded.kickoff_utc, jingcai_sp.kickoff_utc), "
                # 体检 W1 2026-07-15 — 以前直写:不带让球线的再捕(手填 re-pin/HAD 路)
                # 会把已存的线抹成 NULL(同表 psc_*/jc_open_* Wave3 都加了,漏了这列;
                # 姊妹表 vote 的同列有)。新非空值照常覆盖。
                "handicap_home=COALESCE(excluded.handicap_home, jingcai_sp.handicap_home), "
                # 单关标记:latest 覆盖 (终盘=canonical);None 再捕 (手填 re-pin 不带) 不清旧值
                "single_available=COALESCE(excluded.single_available, "
                "jingcai_sp.single_available), "
                "jc_home=excluded.jc_home, jc_draw=excluded.jc_draw, jc_away=excluded.jc_away, "
                # 体检 Wave3 (P2) — a re-capture WITHOUT a Pinnacle reading must
                # not NULL-out the stored Pinnacle-at-capture (manual re-pin of
                # the 竞彩 SP has no psc_*; the old unconditional overwrite
                # erased the sharp anchor). Present values still overwrite
                # (latest capture = freshest line).
                "psc_home=COALESCE(excluded.psc_home, jingcai_sp.psc_home), "
                "psc_draw=COALESCE(excluded.psc_draw, jingcai_sp.psc_draw), "
                "psc_away=COALESCE(excluded.psc_away, jingcai_sp.psc_away), "
                "ou_line=COALESCE(excluded.ou_line, jingcai_sp.ou_line), "
                "psc_over=COALESCE(excluded.psc_over, jingcai_sp.psc_over), "
                "psc_under=COALESCE(excluded.psc_under, jingcai_sp.psc_under), "
                # 初盘 set-once:只在还没记过开售盘时填,终盘(phase='close')传 NULL 不覆盖。
                "jc_open_home=COALESCE(jingcai_sp.jc_open_home, excluded.jc_open_home), "
                "jc_open_draw=COALESCE(jingcai_sp.jc_open_draw, excluded.jc_open_draw), "
                "jc_open_away=COALESCE(jingcai_sp.jc_open_away, excluded.jc_open_away), "
                "opened_at=COALESCE(jingcai_sp.opened_at, excluded.opened_at)",
                (
                    now, source, fixture_id, league, match_date, home_team,
                    away_team, kickoff_utc, market,
                    int(handicap_home) if handicap_home is not None else None,
                    int(single_available) if single_available is not None else None,
                    float(jc_home), float(jc_draw), float(jc_away),
                    _f(psc_home), _f(psc_draw), _f(psc_away), _f(ou_line),
                    _f(psc_over), _f(psc_under),
                    o_h, o_d, o_a, o_at,
                ),
            )
        return True
    except Exception:  # noqa: BLE001 — a lost observation must never break the EV view
        log.warning("jingcai_sp capture failed for %s vs %s (db=%s)",
                    home_team, away_team, db_path, exc_info=True)
        return False


def backfill_jingcai_sp_pinnacle(db_path: str | Path) -> int:
    """给 sink 补录上线**之前**写下的行补捕获时 Pinnacle,返回补上的行数。

    关键:每一行都用**它自己的 captured_at** 去查 ``_pinnacle_at_capture``,不是
    用最新快照 —— 所以回填出来的行与「当时就带着补录写下的行」在口径上完全等价,
    同样不含未来信息。混口径会让账本的选中腿一半干净一半带 look-ahead,那比不补
    更坏(说不清哪些数能用)。

    幂等:只写 NULL 列(SQL 侧 COALESCE + 只捞有空缺的行),重复跑不改已有值。
    Fail-soft:任何异常都只记日志返回已补数,绝不抛。
    """
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_sp_table(conn)
            rows = conn.execute(
                "SELECT id, match_date, home_team, away_team, captured_at "
                "FROM jingcai_sp WHERE psc_home IS NULL OR ou_line IS NULL "
                "OR psc_over IS NULL").fetchall()
            filled = 0
            for rid, mdate, home, away, cap_at in rows:
                co = _pinnacle_at_capture(
                    conn, match_date=mdate, home_team=home,
                    away_team=away, as_of=cap_at or "")
                if not co:
                    continue
                conn.execute(
                    "UPDATE jingcai_sp SET "
                    + ", ".join(f"{c}=COALESCE({c}, ?)" for c in _PINN_AT_CAPTURE_COLS)
                    + " WHERE id = ?",
                    (*co, rid))
                filled += 1
            return filled
    except Exception:  # noqa: BLE001 — 补录是 best-effort,不该让调用方挂掉
        log.warning("backfill_jingcai_sp_pinnacle failed (db=%s)", db_path, exc_info=True)
        return 0


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_jingcai_sp(db_path: str | Path, *, settled: bool | None = None) -> list[dict]:
    """All observations as dicts; ``settled`` filters on result presence."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        q = "SELECT * FROM jingcai_sp"
        if settled is True:
            q += " WHERE settled_at IS NOT NULL"
        elif settled is False:
            q += " WHERE settled_at IS NULL"
        q += " ORDER BY match_date, home_team"
        return [dict(r) for r in conn.execute(q).fetchall()]


def fetch_sp_lookup(
    db_path: str | Path, *, market: str = "had"
) -> dict[tuple[str, str, str], tuple]:
    """``{(match_date, home_team, away_team): (jc_home, jc_draw, jc_away, source,
    handicap_home, captured_at, single_available)}`` for one market — lets the dashboard cards PRE-FILL
    their 竞彩 SP boxes from the line on file (your market_mode hand-price, else the
    sporttery auto-harvest). ``handicap_home`` is the 让球 line (None for the 1X2 'had'
    market). ``captured_at`` = 该行最后一次捕获时刻(upsert-latest)——2026-07-20 起
    穿到前端做竞彩价年龄标:EV = P(t₁)×SP(t₂),竞彩侧的 t₂ 必须可见,否则旧价会
    静默美化/隐藏 EV(埃尔夫斯堡/库奥皮奥两案)。

    ``single_available`` = 竞彩给不给这场开**单关**(2026-07-25 接前端)。抓了很久
    却一直没人消费:实测**只有 17% 的场次可单关**,且高度集中 —— 韩职 29% / 瑞超
    21% / 挪超 13%,而 欧罗巴·芬超·欧冠·巴甲·美职 **0/59 全零**。不显示它,
    甜区榜就可能把一条你**物理上买不了**的腿排在第一。
    1=可单关,0=只能串,None=未知(前端不渲染徽章,**不猜**)。

    Best-effort: returns ``{}`` on any failure so a card render never breaks."""
    out: dict[tuple[str, str, str], tuple] = {}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            ensure_jingcai_sp_table(conn)
            rows = conn.execute(
                "SELECT match_date, home_team, away_team, jc_home, jc_draw, jc_away, "
                "source, handicap_home, captured_at, single_available FROM jingcai_sp WHERE market=?",
                (market,),
            ).fetchall()
        for r in rows:
            out[(r[0], r[1], r[2])] = (r[3], r[4], r[5], r[6], r[7], r[8], r[9])
    except sqlite3.Error:
        logging.getLogger(__name__).warning("fetch_sp_lookup failed", exc_info=True)
    return out


def settle_jingcai_sp(
    db_path: str | Path,
    *,
    fetch_fixtures=None,
    today: dt.date | None = None,
) -> int:
    """Fill results for unsettled observations whose match_date is today-or-past.

    Mirrors ``settle_league_predictions`` but groups by DATE only (竞彩 spans many
    leagues, so we pull the whole day's fixtures and match by team), writing the
    90' FT score + outcome (0 home / 1 draw / 2 away). ``fetch_fixtures(date)``
    takes a ``date`` object and is injectable for tests; the default pulls all of
    that day's API-Football fixtures. Returns the number of rows newly settled."""
    from nutmeg.v4.data.national_alias import national_match_key
    from nutmeg.v4.model.market_handicap import handicap_outcome
    from nutmeg.v4.observation.prediction_log import _ft_outcome

    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        rows = conn.execute(
            "SELECT id, match_date, home_team, away_team, market, handicap_home "
            "FROM jingcai_sp WHERE settled_at IS NULL ORDER BY match_date").fetchall()
        if not rows:
            return 0
        by_date: dict[str, list[sqlite3.Row]] = {}
        for r in rows:
            try:
                d = dt.date.fromisoformat(r["match_date"])
            except ValueError:
                continue
            if d > today:  # not kicked off yet
                continue
            by_date.setdefault(r["match_date"], []).append(r)

        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        settled = 0
        for date_str, drows in by_date.items():
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(date_str)) or []
            except Exception:  # noqa: BLE001 — one bad day must not abort the rest
                log.warning("settle_jingcai_sp: fetch failed for %s", date_str, exc_info=True)
                continue
            index: dict[tuple[str, str], dict | None] = {}
            for fx in fixtures:
                teams = (fx.get("teams") or {})
                h = national_match_key((teams.get("home") or {}).get("name", ""))
                a = national_match_key((teams.get("away") or {}).get("name", ""))
                if not (h and a):
                    continue
                key = (h, a)
                if key in index:
                    # 体检 D2 — ≥2 distinct fixtures share a normalized name on this
                    # date → ambiguous; poison the key to None so a wrong 90' score
                    # is never attributed (last-write-wins would have guessed).
                    prev = index[key]
                    fid = (fx.get("fixture") or {}).get("id")
                    if prev is None or (prev.get("fixture") or {}).get("id") != fid:
                        index[key] = None
                else:
                    index[key] = fx
            for r in drows:
                fx = index.get(
                    (national_match_key(r["home_team"]), national_match_key(r["away_team"])))
                if not fx:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                # 让球行额外落 `hc_outcome`。⚠️ 这里**曾经只写 ft_outcome**(原始 1X2),
                # 而那个值对让球行是「真值但不是你要的那个」—— 2026-08-10 复盘时
                # 实测 404 行里 217 行(53.7%)会被读反。⛔ 别在这里手算,调唯一那份。
                hc = (handicap_outcome(hg, ag, r["handicap_home"])
                      if (r["market"] or "") == "hhad" else None)
                conn.execute(
                    "UPDATE jingcai_sp SET home_goals=?, away_goals=?, ft_outcome=?, "
                    "hc_outcome=?, settled_at=? WHERE id=?",
                    (hg, ag, outcome, hc, now, r["id"]))
                settled += 1
        return settled
