"""nutmeg-data-freshness — capture-table leak sentinel.

The data-accumulation crons capture POINT-IN-TIME data that is gone forever if a
run is missed — a Pinnacle line or a 竞彩 SP at time *T* cannot be re-fetched
later (settle jobs can `--refresh`; capture jobs cannot). This sentinel flags any
capture table that has stopped growing within its expected cadence, so a
silently-dead cron (cf. `daily_wc_settle`, dead 3 weeks before it was noticed by
accident) is caught within a day.

Two classes of table:

  • CAPTURE tables — written by a cron on a schedule. Stalling = a leak.
      - odds_snapshots / jingcai_sp / vote / exotic / closing / polymarket /
        score_ev are CRITICAL (forward-only foundations) → a stale one exits
        non-zero.
      - league_predictions / wc_predictions are WARN (seasonal: summer break /
        only during the tournament) → flagged but never fail the gate.

  • USER-ACTIVITY tables — written only when the user records a bet / uses a tab.
    Staleness reflects the user being 空仓, NOT a leak → reported, never gated.

体检 2026-07-03 P0-1 — sub-stream awareness: a table written by SEVERAL crons
hides a dead one behind the live ones' `max()` (odds_snapshots stayed green while
the `source='closing'` anchor could die unseen). Entries therefore carry an
optional WHERE filter + display name, and sister forward-only DBs in the same
data dir (score_ev_forward.db) are probed too.

体检 2026-07-03 P0-2 — heartbeat: every run touches `<db dir>/.data_freshness_heartbeat`.
The vote-capture cron (independent launchd job) alarms if that file goes >26h
stale — mutual watching, so the alarm chain itself dying no longer means silence
(the wc_settle-dead-3-weeks failure mode).

`--porcelain` emits TSV (STATUS<TAB>name<TAB>…) for scripts (health_check.sh).
Exit 0 = all CRITICAL capture streams fresh; 1 = at least one CRITICAL is stale.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# (table, ts_col, max_stale_days, critical, 说明, where, 显示名)
#   where — 子流过滤 (None = 整表)。同表多 writer 时必须用它切开,否则活着的
#           writer 的 max() 会把死掉的子流顶成绿的 (P0-1 的病根)。
#   显示名 — None = 用表名;子流用 "table[tag]" 以免与整表条目撞键。
CAPTURE_TABLES: list[tuple[str, str, int, bool, str, str | None, str | None]] = [
    ("odds_snapshots", "captured_at", 2, True,
     "Pinnacle 线史 (CLV 地基)", None, None),
    ("odds_snapshots", "captured_at", 2, True,
     "Pinnacle 收盘锚 (closing 子流; --sports auto 随赛程自选联赛)",
     "source='closing'", "odds_snapshots[closing]"),
    ("jingcai_sp", "captured_at", 2, True, "竞彩 SP 捕获 (软水)", None, None),
    ("jingcai_sp", "opened_at", 2, True,
     "竞彩 初盘 SP (jc_open 子流, 开→收位移)",
     "opened_at IS NOT NULL", "jingcai_sp[open]"),
    # 2026-07-25 — 竞彩线史 (append-only)。jingcai_sp 是 UPSERT 只留最新,
    # 这条流才是冻结缺口/临停售调价的前向地基。它死了 = 我们又回到「13 次抓、
    # 1 次留」,而且**没有任何别的表能发现** (jingcai_sp 照常绿)。
    ("jingcai_sp_snapshots", "captured_at", 2, True,
     "竞彩 SP 线史 (append-only; 冻结缺口地基)", None, None),
    ("jingcai_exotic_sp", "captured_at", 2, True,
     "竞彩 比分/总进球 SP (秋季测量地基)", None, None),
    ("jingcai_vote", "captured_at", 2, True, "竞彩 散户支持比例 (软水)", None, None),
    ("polymarket_gaps", "recorded_at", 3, True,
     "Polymarket 缺口 (proxy 依赖, 3 窗/天)", None, None),
    ("league_predictions", "recorded_at", 4, False, "模型盘预测日志 (夏歇宽松)", None, None),
    ("wc_predictions", "recorded_at", 3, False, "WC 模型预测 (仅赛会期)", None, None),
    # 2026-08-12 — 盘面反事实快照。⭐ 它必须进哨兵,理由和上面竞彩线史一模一样:
    # 这是 **point-in-time**、**forward-only** 的流,cron 死掉那几天补不回来,
    # 而**没有任何别的表能发现** —— jingcai_sp / odds_snapshots 都由各自的 cron
    # 独立喂,照常绿。上线前审查把这条列为 high:「四条报警通道全绿」。
    #
    # 用 provenance 而不是 leg 表:空盘面的日子 leg 表**本来就该**是 0 行
    # (夏休期 sp-calc 真的返回 0 场),拿它当心跳会在正确的日子假红;
    # provenance 则是「跑过就有一行」,正是心跳该有的语义。
    ("snapshot_provenance", "created_at", 2, True,
     "盘面快照心跳 (forward-only; 断了补不回来)", None, None),
]

# 别库前向捕获 — db 文件与主观测库同目录。文件缺失 = 写它的 cron 生态整体死
# (或路径漂移) → 按 critical stale 报,绝不静默跳过。
# (db 文件名, table, ts_col, max_stale_days, critical, 说明)
SISTER_CAPTURE_TABLES: list[tuple[str, str, str, int, bool, str]] = [
    ("score_ev_forward.db", "score_ev_flags", "captured_at", 2, True,
     "比分/总进球 EV 前向记录 (score_ev_forward.db 别库)"),
]

HEARTBEAT_FILENAME = ".data_freshness_heartbeat"

# 体检 2026-07-23 — 内部空洞:上面那套只问「最后一次写入距今几天」,对**中间**的
# 洞结构性失明。真实剧本:Odds API 配额 07-13 耗尽,closing 子流断 9 天,07-22 换 key
# 后当天补上 → 哨兵立刻转绿(最后 0d),而身后 9 天的洞永远没人看见。
# 采集是 point-in-time 的,洞不会自己长回来,只会在 CLV/训练锚的样本里静默少一截。
#
# 阈值 3 天是**实测**的,不是拍的(2026-07-23 在 8 条流的近 30 天历史上跑):
#   ≥1 天 → 命中 6 处,其中 5 处是良性 1-2 天空档(那天真没球/cron 错峰)= 噪声
#   ≥3 天 → 命中 1 处,正是那次真实断供,零误报
# 连续 3 天全世界一场可采的球都没有,不合理 —— 所以 3 天以上必是故障。
GAP_LOOKBACK_DAYS = 30   # 只看近 30 天:愈合的旧疤该滚出视野,留着就成了长明红灯
MIN_GAP_DAYS = 3

# Reported for context only — never gated (user-activity driven).
USER_TABLES: list[tuple[str, str]] = [
    ("recommendation_sessions", "created_at"),
    ("single_predictions", "match_date"),
    ("settlements", "settled_at"),
    ("match_outcomes", "recorded_at"),
]


@dataclass
class TableStatus:
    table: str  # display name (子流 = "table[tag]")
    rows: int
    last_day: str | None
    days_stale: int | None  # None = empty / unparseable
    max_days: int
    critical: bool
    note: str
    # 内部空洞 [(起, 止, 天数), …] — 近 GAP_LOOKBACK_DAYS 天内 ≥MIN_GAP_DAYS 的断档。
    # **不进 stale**:洞里的数据已经永久丢了,补不回来,天天红灯只会训练出忽视。
    # 它的职责是「别让洞藏在绿灯背后」,不是拦门。
    gaps: list[tuple[str, str, int]] = field(default_factory=list)

    @property
    def stale(self) -> bool:
        return self.days_stale is None or self.days_stale > self.max_days


def _row_count(conn: sqlite3.Connection, table: str, where: str | None = None) -> int | None:
    """None if the table does not exist."""
    q = f"SELECT count(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    try:
        return conn.execute(q).fetchone()[0]
    except sqlite3.OperationalError:
        return None


def _last_day(
    conn: sqlite3.Connection, table: str, col: str, where: str | None = None
) -> str | None:
    """Most-recent calendar day in `col`, handling ISO-text or epoch ints."""
    cond = f"{col} IS NOT NULL" + (f" AND ({where})" if where else "")
    v = conn.execute(
        f"SELECT {col} FROM {table} WHERE {cond} LIMIT 1"
    ).fetchone()
    if v is None:
        return None
    if isinstance(v[0], (int, float)) and v[0] > 1e9:
        expr = f"date({col},'unixepoch')"
    else:
        expr = f"substr(CAST({col} AS TEXT),1,10)"
    return conn.execute(
        f"SELECT max({expr}) FROM {table} WHERE {cond}"
    ).fetchone()[0]


def _days_stale(last_day: str | None, today: date) -> int | None:
    if not last_day:
        return None
    try:
        return (today - date.fromisoformat(last_day[:10])).days
    except ValueError:
        return None


def _interior_gaps(
    conn: sqlite3.Connection, table: str, col: str, where: str | None, today: date,
    *, lookback: int = GAP_LOOKBACK_DAYS, min_gap: int = MIN_GAP_DAYS,
) -> list[tuple[str, str, int]]:
    """近 ``lookback`` 天内 ≥``min_gap`` 天的连续断档 → [(起, 止, 天数), …]。

    只看**内部**空洞:扫描起点取 max(该流首日, today−lookback),所以一条刚开张的流
    不会把「它还没出生的那段」报成洞。末尾未结束的断档也算(那是「现在正断着」,
    与 days_stale 说的是同一件事,但这里给出它断了多久)。"""
    cond = f"{col} IS NOT NULL" + (f" AND ({where})" if where else "")
    try:
        rows = conn.execute(
            f"SELECT DISTINCT substr(CAST({col} AS TEXT),1,10) FROM {table} WHERE {cond}"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    days: set[date] = set()
    for (v,) in rows:
        try:
            days.add(date.fromisoformat(str(v)[:10]))
        except (TypeError, ValueError):
            continue          # epoch 整数列或脏值 → 跳过,不装懂
    if not days:
        return []
    cur = max(min(days), today - timedelta(days=lookback))
    gaps: list[tuple[str, str, int]] = []
    run: list[date] = []
    while cur <= today:
        if cur in days:
            if len(run) >= min_gap:
                gaps.append((run[0].isoformat(), run[-1].isoformat(), len(run)))
            run = []
        else:
            run.append(cur)
        cur += timedelta(days=1)
    if len(run) >= min_gap:
        gaps.append((run[0].isoformat(), run[-1].isoformat(), len(run)))
    return gaps


def _probe(
    conn: sqlite3.Connection, name: str, table: str, col: str,
    maxd: int, crit: bool, note: str, where: str | None, today: date,
) -> TableStatus:
    n = _row_count(conn, table, where)
    if n is None:  # table missing entirely
        return TableStatus(name, 0, None, None, maxd, crit, note)
    last = _last_day(conn, table, col, where) if n else None
    # 只对 CRITICAL 流查空洞。非 critical 的那两条(league_predictions / wc_predictions)
    # 本就是**季节性**的 —— 夏歇、非赛会期不写数据是设计如此,不是故障。
    # (2026-07-23 实测:不加这条限制,wc_predictions 立刻报两个假洞。)
    gaps = _interior_gaps(conn, table, col, where, today) if (n and crit) else []
    return TableStatus(name, n, last, _days_stale(last, today), maxd, crit, note, gaps)


def check_freshness(
    db_path: str | Path, *, today: date | None = None
) -> list[TableStatus]:
    """One TableStatus per CAPTURE stream (declared order), main DB then sisters."""
    today = today or date.today()
    conn = sqlite3.connect(str(db_path))
    try:
        out: list[TableStatus] = []
        for table, col, maxd, crit, note, where, name in CAPTURE_TABLES:
            out.append(_probe(conn, name or table, table, col, maxd, crit, note,
                              where, today))
    finally:
        conn.close()
    for db_file, table, col, maxd, crit, note in SISTER_CAPTURE_TABLES:
        sef = Path(db_path).parent / db_file
        if not sef.exists():
            out.append(TableStatus(table, 0, None, None, maxd, crit, note))
            continue
        sconn = sqlite3.connect(str(sef))
        try:
            out.append(_probe(sconn, table, table, col, maxd, crit, note, None, today))
        finally:
            sconn.close()
    return out


def check_api_quota() -> tuple[list[str], list[str]]:
    """体检 Wave3 (P1#13) — quota-exhaustion alarm. Both feeds have PULL-only
    panels; hitting the cap means the fresher-line overlay/closing anchor
    silently fall back to stale mirrors (EV cards quietly go wrong). Probe the
    FREE endpoints (AF /status; OA /sports, whose response headers carry the
    credit counters).

    Returns ``(alarms, probe_failures)``. 体检 W1 2026-07-15 — 探针失败以前被
    `pass` 吞成「无报警」= 哨兵自盲:恢复 odds cron 后全靠这个探针确认配额,探针
    瞎了必须可见。失败**不**冒充配额报警(瞬时网络抖动 ≠ 配额红线,不走 exit-1
    推送),但进报告/porcelain 留痕,连续出现人眼能看到。
    Fail-soft + key-gated: no keys in env (tests, offline) → no probe, no alarm."""
    import os

    alarms: list[str] = []
    probe_failures: list[str] = []
    af_key = os.environ.get("NUTMEG_API_FOOTBALL_KEY")
    if af_key:
        try:
            import httpx
            r = httpx.get("https://v3.football.api-sports.io/status",
                          headers={"x-apisports-key": af_key}, timeout=6)
            req = ((r.json() or {}).get("response") or {}).get("requests") or {}
            cur, lim = req.get("current"), req.get("limit_day")
            if cur is not None and lim and float(cur) / float(lim) >= 0.9:
                alarms.append(
                    f"AF 日配额 {cur}/{lim} (≥90%) — 耗尽后叠加静默回落陈旧线")
        except Exception as exc:  # noqa: BLE001 — probe failure ≠ quota alarm
            probe_failures.append(f"AF 配额探针失败: {type(exc).__name__}: {exc}")
    oa_key = os.environ.get("NUTMEG_ODDS_API_KEY")
    if oa_key:
        try:
            import httpx
            r = httpx.get("https://api.the-odds-api.com/v4/sports/",
                          params={"apiKey": oa_key}, timeout=6)
            rem = r.headers.get("x-requests-remaining")
            if rem is not None and float(rem) < 50:
                alarms.append(
                    f"Odds API 剩余 credit {rem} (<50) — 收盘锚/鲜线将断供")
        except Exception as exc:  # noqa: BLE001
            probe_failures.append(f"Odds API 配额探针失败: {type(exc).__name__}: {exc}")
    return alarms, probe_failures


# 体检 W1 2026-07-15(D1 冻结不报警)— 生产 artifact 曾冻 724 天无人知:哨兵只看
# 采集表,从不看模型供应链。年龄红线 120 天:秋季 retrain cron 落地后永远碰不到;
# cron 没装(D1 家族的真实剧本)则 11 月准时响 = 正确的兜底。
ARTIFACT_MAX_AGE_DAYS = 120
SOURCE_TREE_MAX_AGE_DAYS = 120

#: 「源树里有多少场比赛是 artifact 从没见过的」的报警线。
#:
#: ⭐ 为什么另立一个数,而不是靠上面两个天数(2026-08-05 owner 问「Elo 会不会
#: 自动更新」时挖出来的):上面两个量的都是**代理** ——
#:
#:   · artifact 年龄  = 「多久没重训」,但休赛期不重训是**对的**;
#:   · 源树 CSV mtime = 「多久没进新文件」,而它可以被**手动放一次文件**清零。
#:
#: 秋天这两个代理会同时说谎:8 月手动更新一次 CSV ⇒ mtime 变绿、报警闭嘴,
#: 而 artifact 仍然没吸收那批比赛。**刷新输入把关于输出的报警说服了。**
#: 本探针直接数「date > training_cutoff 的行数」,touch 文件动不了它。
#:
#: 阈值取一个联赛一轮的量级:13 个训练联赛 × 每轮约 8-10 场 ≈ 100+/轮,所以
#: 200 ≈ 落后两轮。低于它多半是零星补录,不值得为它重训一次。
UNABSORBED_MATCHES_ALARM = 200


def _training_cutoff(artifact_dir: Path) -> str | None:
    """artifact 训练截止日(``metadata.metadata.training_cutoff``),取不到给 None。

    ⚠️ 这个键嵌在 ``metadata.json`` 的 ``metadata`` 子字典里,不是顶层 —— 顶层
    只有 feature_columns / elo_* / model_type。写成顶层会永远拿到 None,而
    「拿不到 cutoff」和「没有新比赛」在报告里长得一样(都不报警)⇒ 静默失效。
    """
    meta = artifact_dir / "metadata.json"
    if not meta.exists():
        return None
    try:
        import json
        raw = json.loads(meta.read_text()) or {}
    except Exception:  # noqa: BLE001 — 坏 metadata 不该炸掉整个体检
        return None
    cutoff = (raw.get("metadata") or {}).get("training_cutoff")
    return str(cutoff)[:10] if cutoff else None


def _serving_artifact(artifact_dir: str | Path | None = None) -> tuple[Path, Path]:
    """``(base, effective)`` —— effective 就是**服务真的会加载的那个目录**。

    ## 为什么这里必须跟指针(2026-08-07 审查)

    原来这里只解析到 base(env 或兜底值)就停了,而 serving 走
    ``routes._resolve_artifact()`` **会**跟 ``live_artifact_pointer.json``。
    Layer B 一部署,两边量的就是两个不同的目录,双向都失效 —— 实测复现过:

      · **假红** — base 停在 2025-06(Layer B 下这是**正常**的回滚落点),
        指针目标是 6 天前的新盘。服务侧正确,探针却喊「432 天未重训」。
      · **假绿(更坏的那半)** — base 刚重训过,指针却指向一个 432 天的旧盘。
        服务侧正在喂那个旧盘,探针报「6d」并返回**零告警**。

    724 天冻结事故的疫苗,恰恰在 Layer B 生效时整个失灵。

    ⛔ 不许在这里第三次手写「读指针 JSON → 看目标存不存在」。本仓已经因为
    「同一件事三个地方各写一份」栽过(见 `routes.py` 的 `EXPECTED_SERVING_ARTIFACT`
    注释:换盘要改 9 处)。指针解析只有一个权威实现,直接借:
    ``observation.auto_retrain.resolve_effective_artifact_path``(纯函数,
    不需要起 FastAPI;`routes._resolve_artifact()` 是它加了一层 mtime 缓存的
    同一套规则,`tests/v4/test_supply_chain_follows_layer_b.py` 钉住两者等价)。

    base 侧仍读 ``NUTMEG_V4_ARTIFACT_PATH`` + 字面量兜底,而不是 import
    ``routes``:这个 CLI 是采集哨兵的 cron 入口,不该为了拿一个常量把 FastAPI
    整棵依赖树拖进来(它挂了 = 哨兵整个哑掉)。那个字面量由
    ``test_artifact_identity_guard.py::TestArtifactLiteralsAgree`` 逐值钉死,
    漏改会红 —— 它是换盘清单的第 7 项。
    """
    import os

    from nutmeg.v4.observation.auto_retrain import resolve_effective_artifact_path

    base = Path(artifact_dir or os.environ.get("NUTMEG_V4_ARTIFACT_PATH")
                or "data/v4_model_cat")
    return base, Path(resolve_effective_artifact_path(base))


#: `_artifact_age_reading()` 第二格的两个取值 —— 这个年龄是**哪个日期**。
#: 报告里必须能分辨,否则「读到了训练日期」和「读不到、退到文件日期」长成同一句话。
_TRAINED = "trained"
_MTIME = "mtime"


def _artifact_age_reading(artifact_dir: Path) -> tuple[date, str] | None:
    """``(日历日, _TRAINED | _MTIME)``,或 ``None`` = 「这里没有盘」。

    **三态,一个都不许合并**(本仓反复栽的就是「分不出没有和没去看」):

      · ``None``        — 没有 ``metadata.json``。既不是新也不是旧,是**空**。
      · ``_TRAINED``    — 读到了 ``trained_at_utc``,这是真的训练日期。
      · ``_MTIME``      — 盘在,但读不出训练日期(`47435ce` 之前的旧格式)⇒ 退到
                          文件 mtime。**调用方必须把「退了」写进输出**:mtime 只会
                          把陈旧盘报得更年轻,是这条红线最怕的方向。

    ## 为什么 `_MTIME` 以前是默认路径(2026-08-07 实测)

    `model/persist.py::save_artifact()` 写的 ``metadata.json`` 是**嵌套**的 ——
    训练 metadata 在 ``"metadata"`` 键下面,顶层只有 feature_columns / elo_* /
    model_type。这里原来只读顶层 ⇒ 恒 None ⇒ **每个生产盘都走了 mtime 兜底**:

      · ``data/v4_model_cat``  顶层 None,嵌套 ``2026-07-15T06:19:12+00:00``
      · ``data/v4_model``      顶层 None,嵌套 ``2026-05-22T06:17:04+00:00``

    它不报错,只把年龄报得偏乐观。盘上现成的例子:
    ``v4_model_cat.bak-20260715T135746-pre-clubelo-retrain`` 训练于 2026-05-23、
    被 ``cp -r`` 出来后 mtime=2026-07-15,**少算 53 天**。rsync / 备份还原同理 ——
    任何一次搬运都能把陈旧盘刷成「刚训好」,而这正是这条红线要守的东西。
    同文件的 `_training_cutoff()` 读对了(docstring 还专门警告过这个坑),偏偏
    年龄这条没有。

    ⛔ 日期解析不在这里重写第三份。``observation.auto_retrain`` 里
    ``artifact_trained_at``(嵌套优先/顶层兜底)+ ``parse_trained_at``
    (tz-aware,不裸切 ``[:10]`` —— 带偏移的时间戳切字符串会差一天)就是权威实现,
    并且已经有 `test_auto_retrain.py::TestTrainedAtReader` 钉着。
    """
    meta = artifact_dir / "metadata.json"
    if not meta.exists():
        return None
    from nutmeg.v4.observation.auto_retrain import (
        artifact_trained_at,
        parse_trained_at,
    )
    parsed = parse_trained_at(artifact_trained_at(artifact_dir))
    if parsed is not None:
        return parsed.astimezone(UTC).date(), _TRAINED
    return datetime.fromtimestamp(meta.stat().st_mtime, UTC).date(), _MTIME


def _count_matches_after(sources_dir: Path, cutoff: str) -> int | None:
    """源树里日期严格晚于 ``cutoff`` 的比赛行数;读不了给 None(≠0)。

    ⚠️ **None 和 0 必须分开**:0 = 「去看了,确实没有」(休赛期的正确答案),
    None = 「没看成」。把读失败折成 0 就是又一次「分不出没有和没去看」。
    """
    try:
        import pandas as pd

        from nutmeg.v4.data.ingest import load_all_matches
        df = load_all_matches(sources_dir)
        if df.empty:
            return 0
        dates = pd.to_datetime(df["date"], errors="coerce")
        return int((dates > pd.Timestamp(cutoff)).sum())
    except Exception:  # noqa: BLE001 — 探针坏了要说出来,不能装作「没有新数据」
        return None


def check_model_supply_chain(
    today: date,
    *,
    artifact_dir: str | Path | None = None,
    sources_dir: str | Path = "data/historical_sources/football_data_co_uk",
    external_dir: str | Path = "data/external",
) -> tuple[list[str], list[str]]:
    """模型供应链探针:artifact 年龄 / 训练源树年龄 / 空 parquet 计数。

    Returns ``(info_lines, alarms)``。缺目录 = 跳过(CI/测试环境无 data/,report
    不 alarm);存在才查。空 parquet 只报数不报警(clubelo 日职空文件属正常,
    当前基线 ~121/459 — 突增才值得人看,那是趋势判断,交给读报告的人)。

    ⭐ 年龄和 cutoff 量的都是 **serving 真的会加载的那个盘**(跟 Layer B 指针),
    不是 base —— 为什么见 `_serving_artifact()`;年龄取的是**训练日期**不是文件
    日期 —— 为什么见 `_artifact_age_reading()`。两个洞是同一次审查里翻出来的:
    一个量错了目录,一个量错了日期。

    ⚠️ **告警文案是实现细节,别拿它当接口。** 每条关于某个 artifact 的告警都
    带着那个盘的**路径**,测试要挑出「关于哪个盘」的告警请按路径过滤。以前的
    写法是 ``"未重训" in a`` —— 实测把措辞一改,该红的红了,而那条「不该响时
    不响」的用例**恒绿**(过滤器返回空 = 断言空集,永远成立)。
    """
    info: list[str] = []
    alarms: list[str] = []

    from nutmeg.v4.observation.auto_retrain import same_artifact_dir

    base, art = _serving_artifact(artifact_dir)
    # ⚠️ 不是 `str(art) != str(base)`。`.env` 写相对路径而 run_local_server.sh 导出
    # 绝对路径,两者指同一个目录 —— 字符串比较会把「没重定向」读成「重定向了」,
    # 于是同一份报告同时打印「432d 告警」和「NOTE base 不告警」两行自相矛盾的话。
    # routes.py 的 /health 早就为这个理由留了 `_same_dir`(现在两边同一个实现)。
    redirected = not same_artifact_dir(art, base)
    if redirected:
        info.append(f"Layer B 指针生效: {base} → {art} — 以下年龄量的是生效盘")

    reading = _artifact_age_reading(art)
    if reading is None:
        if redirected:
            # `resolve_effective_artifact_path` 只在 `is_dir()` 时才重定向 ⇒ 这个
            # 目录**存在**,只是没有 metadata.json = 半途失败的部署(训练目录建好、
            # 盘还没落全就写了指针)。以前这里走的是「不存在 — 跳过」那条 info:
            # 服务正在加载它,年龄红线整个跳过,base 又被降级成 NOTE ⇒ **零告警**,
            # 而同样场景下没有指针时是**会**告警的。静默失效的第三种写法。
            alarms.append(
                f"Layer B 指针目标 {art} 存在但没有 metadata.json — 半途失败的部署?"
                f"服务正在加载它,而年龄红线量不到它 = 724 天那条线现在没人守")
        elif art.is_dir():
            info.append(
                f"artifact {art}: 目录在但没有 metadata.json — 跳过年龄检查(读不出日期)")
        else:
            info.append(f"artifact {art}: 不存在 — 跳过(非生产环境?生产缺盘 daemon 自己会响)")
    else:
        trained, how = reading
        age = (today - trained).days
        label = "训练于" if how == _TRAINED else "文件日期"
        line = f"artifact {art.name}: {label} {trained} · {age}d(红线 {ARTIFACT_MAX_AGE_DAYS}d)"
        if how == _MTIME:
            # 「读不到」必须长得和「训练于」不一样 —— 以前两者显示成同一句
            # 「训练于 X」,报告里没有任何字能让人看出这个年龄是文件日期。
            line += (" ⚠️ metadata.json 里读不到 trained_at_utc,这是 **metadata.json 的"
                     "文件修改日期,不是训练日期** —— rsync/cp -r/备份还原都会把它刷新,"
                     "只会把陈旧盘报得更年轻")
        info.append(line)
        if age < 0:
            # ⚠️ 原来这里是 `max(0, …)`。夹成 0 的后果不是「显示成 0d」,是年龄
            # **永远** 0d、**永远**零告警 —— 一个坏时钟或一次手改 metadata 就能把
            # 这条红线彻底关掉,而基线在同一个盘上是会喊 949d 的。未来日期本身
            # 就是故障,要说出来。
            alarms.append(
                f"artifact {art} 的{label}是 {trained},在**未来** {-age} 天 — "
                f"钟或 metadata 坏了;修好之前 {ARTIFACT_MAX_AGE_DAYS}d 红线是瞎的")
        elif age > ARTIFACT_MAX_AGE_DAYS:
            alarms.append(
                f"生产 artifact 已 {age} 天未重训({art})"
                f" — 724 天冻结的路重演中,去装/修 retrain"
                + (" (年龄取自 metadata.json 文件日期,非训练日期 —— 真实训练日只会更早)"
                   if how == _MTIME else ""))

    if redirected:
        # 📌 决定(2026-08-07,owner 拍板):base 的**陈旧本身**只进 info;真正告警的
        # 判据是「**出注那条路仍在加载 base**」。两件事必须分开:
        #
        #   · 陈旧不告警 —— Layer B 部署后 base 停在旧盘是**设计如此**(它就是
        #     rollback 的落点,`remove_artifact_pointer()` 一删指针就回到它)。拿它
        #     告警 = 每天一条永远为真的红,而老误报的护栏最后会被人删掉,连带真
        #     信号一起没了(见「语法代理测语义属性」那三次)。
        #   · 但也不能不报 —— 回滚是一次 `rm` 的距离,读报告的人有权先知道
        #     「万一回滚,落点有多旧」。省掉这一行等于把回滚风险藏起来。
        #   · 真正该响的那件事(2026-08-07 实读确认):`com.nutmeg.{morning,daily}_recommend`
        #     的命令行里**没有 `--model`** ⇒ 出注 cron 吃 `cli/recommend.py` 的
        #     argparse 默认值 = **base**;`load_artifact()` 不读 env、不读指针;
        #     `do_deploy` 从不刷新 base。⇒ 第一次 Layer B deploy 之后,面板/health
        #     吃新盘,而**注单吃 base,且 base 再没人刷新**。见记忆
        #     `serving-artifact-vs-betting-artifact`。
        #
        # ⛔ 在 `cli/recommend.py` 改走同一套解析之前不要把这条简化掉。它的前提由
        #    `test_supply_chain_follows_layer_b.py::TestTheBettingPathPremise` 钉着 ——
        #    前提一旦不成立那条测试会红,那才是删这条告警的信号。
        b_reading = _artifact_age_reading(base)
        if b_reading is None:
            info.append(
                f"NOTE base {base}: 读不出年龄(没有 metadata.json)— 回滚落点,不告警")
        else:
            b_trained, b_how = b_reading
            b_age = (today - b_trained).days
            b_label = "训练于" if b_how == _TRAINED else "文件日期"
            info.append(
                f"NOTE base {base.name}: {b_label} {b_trained} · {b_age}d"
                f" — Layer B 下 base 陈旧属正常,这是回滚的落点;陈旧本身不告警")
            if b_age > ARTIFACT_MAX_AGE_DAYS:
                alarms.append(
                    f"出注 cron 仍在加载 base({base}),而它已 {b_age} 天未重训 —"
                    f" recommend.py 不读 env 也不跟 Layer B 指针,面板吃生效盘、"
                    f"注单吃 base;要么重训 base,要么让 recommend 走同一套解析")

    src = Path(sources_dir)
    if src.exists():
        newest: float | None = None
        for f in src.rglob("*.csv"):
            m = f.stat().st_mtime
            newest = m if newest is None else max(newest, m)
        if newest is None:
            alarms.append(f"训练源树 {src} 存在但没有任何 CSV — 训练无粮")
        else:
            nd = datetime.fromtimestamp(newest, UTC).date()
            age = max(0, (today - nd).days)
            info.append(f"训练源树: 最新 CSV {nd} · {age}d(红线 {SOURCE_TREE_MAX_AGE_DAYS}d)")
            if age > SOURCE_TREE_MAX_AGE_DAYS:
                alarms.append(f"football-data 源树 {age} 天没进新数据 — ingest 断供,重训会空转")

        # ⭐ 未吸收比赛数 —— 直接量语义,不靠 mtime 代理(见 UNABSORBED_MATCHES_ALARM)。
        # ⚠️ `art` 是**生效盘**(跟过指针),不是 base —— 同一个洞的第二个出口:
        # cutoff 读 base 的话,Layer B 指向一个 cutoff 更旧的盘时积压会被整个藏掉。
        cutoff = _training_cutoff(art)
        if cutoff is None:
            info.append("未吸收比赛: 跳过 — artifact metadata 里没有 training_cutoff")
        else:
            n_new = _count_matches_after(src, cutoff)
            if n_new is None:
                info.append("未吸收比赛: 探针失败(源树读不了)— 非报警,连续出现修探针")
            else:
                info.append(
                    f"未吸收比赛: {n_new} 场晚于 cutoff {cutoff}"
                    f"(红线 {UNABSORBED_MATCHES_ALARM};休赛期为 0 属正常)")
                if n_new > UNABSORBED_MATCHES_ALARM:
                    alarms.append(
                        f"源树里有 {n_new} 场比赛晚于训练 cutoff {cutoff},artifact 从没见过它们"
                        f" — 重训现在能真的买到东西了(不是「artifact 老了」,是「它落后了」)")
    else:
        info.append(f"训练源树 {src}: 不存在 — 跳过")

    ext = Path(external_dir)
    if ext.exists():
        try:
            import pyarrow.parquet as pq
            total = empty = 0
            for f in ext.rglob("*.parquet"):
                total += 1
                try:
                    if pq.ParquetFile(f).metadata.num_rows == 0:
                        empty += 1
                except Exception:  # noqa: BLE001 — 读不了按空计(保守方向)
                    empty += 1
            info.append(
                f"外部特征 parquet: 空 {empty}/{total}(基线 ~121/459;突增查 clubelo 自毁类)")
        except Exception as exc:  # noqa: BLE001 — pyarrow 缺失等,报出来别装瞎
            info.append(f"外部 parquet 探针失败: {type(exc).__name__}(非报警,连续出现修探针)")

    return info, alarms


#: 已知会同时收到两轨写入的表(cron 写竞彩中文缩写 / 面板 记一笔 写 V4 EN 代码)。
#: 别写成「扫全库所有 league 列」—— 那会把 `polymarket_gaps` 这种**本来就该**
#: 两轨并存(EN=外盘联赛 33 种,中文=竞彩侧 2 种,规范化后零重叠)的表也拖进来报警。
_LEAGUE_TRACK_TABLES: tuple[tuple[str, str], ...] = (
    ("jingcai_sp", "league"),
    ("jingcai_sp_snapshots", "league"),
)


def check_jingcai_trickle(
    status_path: str | Path = "logs/jingcai_trickle_status.jsonl",
    *,
    now: datetime | None = None,
    lookback: int = 7,
) -> tuple[list[str], list[str]]:
    """竞彩历史涓流进度 —— 回答「它扫完了吗」,而且**能区分「没有」和「没去看」**。

    ⭐⭐ 这条探针的全部理由是一次真实事故:2026-07-20 我们看到「连续 56 轮零新增」,
    判定「覆盖齐了」,**主动退休了这个 job**。而那个零是脚本里 END 写成常量导致的
    **数学必然**,不是覆盖齐 —— 结果静默丢了 10.5 个月 / 4,751 场,日志天天绿,
    直到 owner 问一场具体比赛的历史 EV 才暴露。

    ⇒ **判据必须同时看 `stored_rows` 和 `enumerated`**:
      · `enumerated > 0` 且 `stored_rows == 0`  → 真·扫完了(去看了,确实没东西)
      · `enumerated == 0`                        → **没去看**(限流/403/空响应)——
        它长得和「扫完了」一模一样,但结论相反。**这种必须报警。**

    进度与 ETA 都由**跑的人自己写的状态行**算(`jingcai_history_trickle._write_status`)
    —— BEGIN/END/WINDOW_DAYS 全在那个脚本里,这里再抄一份就是「各写一份常量」。
    ETA 用**实测**推进速度(最近 lookback 行跨的历史天数 ÷ 跨的日历天数),
    不假设 cron 频率 —— 频率改了这里不用跟着改,而且改错了这里会看得出来。

    Returns ``(info_lines, alarms)``。文件不存在但 `logs/` 存在 = job 装了没跑过 ⇒ 报警;
    整个 `logs/` 都没有 = CI/测试环境 ⇒ 跳过不报警。
    """
    import json

    now = now or datetime.now()
    path = Path(status_path)
    info: list[str] = []
    alarms: list[str] = []

    if not path.exists():
        if not path.parent.exists():
            return ([f"NOTE 无 {path.parent}/ — 跳过涓流进度(CI/测试环境)"], [])
        return ([], [
            f"竞彩历史涓流没有任何状态行({path}) — job 可能装了但从没成功跑过。"
            f"⛔ 别把「没有状态」读成「没在跑因为跑完了」,那正是 2026-07-20 那次事故的形状"
        ])

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    if not rows:
        return ([], ["竞彩历史涓流状态文件是空的 — 同上,不是「跑完了」"])

    last = rows[-1]
    recent = rows[-lookback:]
    try:
        ran = datetime.fromisoformat(str(last["ran_at"]))
    except (KeyError, ValueError):
        return ([], ["涓流状态行没有可解析的 ran_at — 探针读不了它自己的输入"])

    age_h = (now - ran).total_seconds() / 3600.0
    remaining = int(last.get("days_remaining") or 0)
    enum_sum = sum(int(r.get("enumerated") or 0) for r in recent)
    stored_sum = sum(int(r.get("stored_rows") or 0) for r in recent)
    fail_sum = sum(int(r.get("failed") or 0) for r in recent)

    # 实测推进速度 → ETA(不假设 cron 频率)
    eta = ""
    if len(recent) >= 2:
        try:
            d0 = datetime.fromisoformat(str(recent[0]["ran_at"]))
            hist = (date.fromisoformat(str(last["cursor_next"]))
                    - date.fromisoformat(str(recent[0]["cursor_next"]))).days
            wall = max((ran - d0).total_seconds() / 86400.0, 1e-9)
            if hist > 0:
                rate = hist / wall
                eta = f" · 实测 {rate:.0f} 天历史/天 ⇒ ETA ≈ {remaining / rate:.0f} 天"
        except (KeyError, ValueError):
            pass

    info.append(
        f"竞彩涓流 游标 {last.get('cursor_next')} → 终点 {last.get('end')} · "
        f"剩 {remaining} 天历史{eta}"
    )
    info.append(
        f"  最近 {len(recent)} 轮:枚举 {enum_sum} · 新增 {stored_sum} 行 · 失败 {fail_sum} · "
        f"上次 {age_h:.1f}h 前"
    )

    if age_h > 48:
        alarms.append(
            f"竞彩历史涓流 {age_h / 24:.1f} 天没跑 — 回填停了,而缺口不会自己合上"
        )
    # ⭐ 核心判据:两个零长得一样,结论相反
    if enum_sum == 0:
        alarms.append(
            f"竞彩涓流最近 {len(recent)} 轮**枚举到 0 场** — 这是「没去看」不是「没东西」"
            f"(限流/403/空响应)。⛔ 别读成「扫完了」—— 2026-07-20 就是这么丢的 4,751 场"
        )
    elif stored_sum == 0 and remaining == 0:
        info.append(
            "  ✅ 枚举>0 且连续零新增且游标已到终点 = **真的扫完了**,可以考虑退休它"
        )
    if fail_sum > enum_sum * 0.2 and enum_sum:
        alarms.append(
            f"竞彩涓流最近 {len(recent)} 轮失败 {fail_sum}/{enum_sum} — 可能被限流"
        )
    return (info, alarms)


def check_league_labels(db_path: str | Path) -> tuple[list[str], list[str]]:
    """联赛标签双轨探针(2026-08-05)。

    `league_labels` 模块开头就描述了这个病(一个联赛两种写法 ⇒ 被劈成两组,
    per-league N 稀释、CLV 闸的 FDR 家族凭空多一个成员),`classify_league` 的
    docstring 也写着 unknown「必须被报出来」—— 但**没有任何地方在报**。
    这里把那个早就设计好、从未接线的警报接上。

    两种警报语义不同,别混:
      · split   已经在发生的稀释 ⇒ 跑 `nutmeg-backfill-league-labels` 并归一轨
      · unknown 标签表落后于现实 ⇒ 照证据往 `_EN_TO_CN`/`_CN_SYNONYM` 补一行
        (⛔ 不许猜中文缩写:补错的映射会把两个联赛静默合并,比缺一行坏得多)

    缺库/缺表 = 跳过(CI 无 data/),不 alarm。
    """
    from nutmeg.v4.data.league_labels import audit_label_tracks

    info: list[str] = []
    alarms: list[str] = []
    p = Path(db_path)
    if not p.exists():
        return [f"联赛标签探针: {p} 不存在 — 跳过"], []
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        for table, col in _LEAGUE_TRACK_TABLES:
            try:
                labels = [r[0] for r in conn.execute(
                    f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL")]
            except sqlite3.Error:
                info.append(f"{table}.{col}: 表不存在 — 跳过")
                continue
            a = audit_label_tracks(labels)
            info.append(f"{table}.{col}: {len(labels)} 种写法 · "
                        f"劈开 {len(a['split'])} · 未知 {len(a['unknown'])}")
            for cn, variants in a["split"]:
                alarms.append(
                    f"{table}.{col} 联赛「{cn}」被劈成 {len(variants)} 种写法 "
                    f"{variants} — 按联赛分组会算成两组;跑 "
                    f"`python -m nutmeg.v4.cli.backfill_league_labels --apply`")
                    # ⚠️ 写模块形式而不是 `nutmeg-backfill-league-labels`:入口点在
                    # pyproject 里注册了,但要重装 editable 才会出现在 .venv/bin
                    # (本机 venv 里没有 pip,装不了)。报警指向一个跑不了的命令,
                    # 和这轮刚修掉的「tooltip 指着不存在的控件」是同一类毛病。
            if a["unknown"]:
                alarms.append(
                    f"{table}.{col} 有标签表不认识的联赛 {a['unknown']} — "
                    f"它们会掉出 P3 等按人口的计数(丹超那个活例);"
                    f"照证据补进 league_labels(⛔ 别猜中文缩写)")
    finally:
        conn.close()
    return info, alarms


def write_heartbeat(db_path: str | Path) -> None:
    """Touch `<db dir>/.data_freshness_heartbeat` — proof the sentinel ran.
    Fail-soft: a heartbeat failure must never break the freshness report."""
    try:
        hb = Path(db_path).resolve().parent / HEARTBEAT_FILENAME
        hb.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    except OSError:
        print(f"⚠ 心跳文件写入失败: {hb}", file=sys.stderr)


def _user_rows(db_path: str | Path, today: date) -> list[tuple[str, int, str | None, int | None]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = []
        for table, col in USER_TABLES:
            n = _row_count(conn, table)
            if n is None:
                continue
            last = _last_day(conn, table, col) if n else None
            rows.append((table, n, last, _days_stale(last, today)))
        return rows
    finally:
        conn.close()


def render(statuses: list[TableStatus], db_path: str | Path, today: date) -> str:
    lines = [f"# 捕获表新鲜度哨兵 (today={today})", ""]
    bad = [s for s in statuses if s.stale and s.critical]
    warn = [s for s in statuses if s.stale and not s.critical]
    holed = [s for s in statuses if s.gaps]
    for s in statuses:
        mark = "✓" if not s.stale else ("✗" if s.critical else "⚠")
        age = "空/缺表" if s.days_stale is None else f"{s.days_stale}d"
        within = f"(≤{s.max_days}d)"
        tag = "CRIT" if s.critical else "warn"
        lines.append(
            f"  {mark} {s.table:<24} {s.rows:>6} 行 · 最后 {s.last_day or '—':<10} "
            f"· {age:>7} {within} [{tag}] {s.note}"
        )
        # 洞挂在它自己那行下面 —— 「最后 0d」的绿灯与「身后有个 9 天洞」必须同屏,
        # 分开放两处 = 又给了只看一处的机会。
        for g0, g1, n in s.gaps:
            lines.append(f"      ⚠ 内部空洞 {g0} → {g1}({n} 天,采集是 point-in-time,补不回来)")
    lines += ["", "  — 用户行为表(空仓即僵,不门控)—"]
    for table, n, last, ds in _user_rows(db_path, today):
        age = "—" if ds is None else f"{ds}d 前"
        lines.append(f"  · {table:<24} {n:>6} 行 · 最后 {last or '—':<10} · {age}")
    lines += [""]
    if bad:
        names = ", ".join(s.table for s in bad)
        lines.append(f"判定: ✗ STALE — critical 捕获流停长: {names}")
        lines.append("  → 某个捕获 cron 多半静默死了。`launchctl print` 查它真在跑没;")
        lines.append("    用产出物/数据验证,别信 log mtime。")
    elif warn:
        lines.append(f"判定: ⚠ 季节性捕获表偏旧(不致命): {', '.join(s.table for s in warn)}")
    else:
        lines.append("判定: ✓ 所有捕获流都在按节奏入库,无漏。")
    if holed:
        lines.append(
            f"  ⚠ 但近 {GAP_LOOKBACK_DAYS} 天有内部空洞: "
            f"{', '.join(s.table for s in holed)} —— 「最后 0d」只说明**现在**没断,"
            "洞里那几天的线已经永久没了。用它的数据做 CLV/训练锚时记得样本少了一截。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="捕获表漏数据哨兵 — 某个捕获流停止增长即报警"
    )
    p.add_argument("--db", default="data/v4_observation.db", help="观测库路径")
    p.add_argument("--today", default=None, help="覆盖今天 (YYYY-MM-DD, 测试用)")
    p.add_argument(
        "--porcelain", action="store_true",
        help="TSV 输出 (STATUS<TAB>name<TAB>rows<TAB>last<TAB>days<TAB>crit<TAB>note) 供脚本解析",
    )
    p.add_argument("--out", default=None, help="把人类报告写到文件 (cron 用)")
    p.add_argument("--no-quota", action="store_true",
                   help="跳过 AF/OA 配额探针 (默认: env 里有 key 才探,fail-soft)")
    p.add_argument("--no-supply", action="store_true",
                   help="跳过模型供应链探针 (artifact/源树/parquet;缺目录本就自动跳过)")
    p.add_argument("--no-league-labels", action="store_true",
                   help="跳过联赛标签双轨探针 (劈开的写法 / 标签表不认识的联赛)")
    p.add_argument("--no-trickle", action="store_true",
                   help="跳过竞彩历史涓流进度探针 (回填进度 / 零新增真假判据)")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ 观测库不存在: {db_path}", file=sys.stderr)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()

    statuses = check_freshness(db_path, today=today)
    # Heartbeat even when stale — it means "the sentinel RAN", not "all green";
    # the vote-cron watchdog alarms on ITS absence (P0-2 mutual watching).
    write_heartbeat(db_path)
    crit_stale = [s for s in statuses if s.stale and s.critical]
    quota_alarms, probe_fails = ([], []) if args.no_quota else check_api_quota()
    # ⚠️ 2026-08-07:这条**必须**兜住异常。心跳在上面第 598 行就写掉了,而心跳的
    # 语义是「哨兵跑过」——  探针在这里抛一个异常,整份报告(采集表新鲜度、配额、
    # 标签)全丢、退出码是个 traceback,而 vote-cron 看门狗看到的是一条**新鲜的
    # 心跳**,判定「哨兵健在」。同函数里 pandas/pyarrow 的 import 都有 try/except,
    # 唯独这条没有 —— 而本次接进来的 `observation.auto_retrain` 会拖 numpy,正是
    # 这条路上第一个真实会抛的东西:我们自己把它点亮了。
    # 探针自己坏了要**大声说**,不能装成「供应链没问题」(零 info 零 alarm 在报告
    # 里长得和「一切正常」一模一样)。所以走 alarms —— 它同乘非零退出。
    supply_info: list[str] = []
    supply_alarms: list[str] = []
    if not args.no_supply:
        try:
            supply_info, supply_alarms = check_model_supply_chain(today)
        except Exception as exc:  # noqa: BLE001 — 探针坏了不该拖垮整份报告
            supply_alarms = [
                f"模型供应链探针自己炸了: {type(exc).__name__}: {exc}"
                f" — artifact 年龄/源树/未吸收比赛这一整块**没有被检查**,"
                f"别把这份报告的其余部分当成供应链体检通过"
            ]
    label_info, label_alarms = (
        ([], []) if args.no_league_labels else check_league_labels(db_path))
    # 涓流进度 —— 同 supply 的处理:探针炸了走 alarms,不能装成「没问题」
    trickle_info: list[str] = []
    trickle_alarms: list[str] = []
    if not args.no_trickle:
        try:
            trickle_info, trickle_alarms = check_jingcai_trickle()
        except Exception as exc:  # noqa: BLE001
            trickle_alarms = [
                f"竞彩涓流探针自己炸了: {type(exc).__name__}: {exc}"
                f" — 回填进度**没有被检查**,别据此判断它扫完没扫完"
            ]

    if args.porcelain:
        for s in statuses:
            status = "OK" if not s.stale else ("STALE" if s.critical else "OLD")
            print(
                f"{status}\t{s.table}\t{s.rows}\t{s.last_day or '-'}\t"
                f"{'-' if s.days_stale is None else s.days_stale}\t"
                f"{int(s.critical)}\t{s.note}"
            )
            # 独立 GAP 行 —— health_check.sh 只认前缀,不必改它的 OK/STALE 解析。
            for g0, g1, n in s.gaps:
                print(f"GAP\t{s.table}\t{g0}\t{g1}\t{n}")
        for q in quota_alarms:
            print(f"QUOTA\t{q}")
        for q in probe_fails:
            print(f"QPROBE-FAIL\t{q}")
        for q in supply_info:
            print(f"SUPPLY\t{q}")
        for q in supply_alarms:
            print(f"SUPPLY-STALE\t{q}")
        for q in label_info:
            print(f"LEAGUE-LABEL\t{q}")
        for q in label_alarms:
            print(f"LEAGUE-LABEL-SPLIT\t{q}")
        for q in trickle_info:
            print(f"TRICKLE\t{q}")
        for q in trickle_alarms:
            print(f"TRICKLE-STUCK\t{q}")
    else:
        report = render(statuses, db_path, today)
        if supply_info or supply_alarms:
            report += "\n\n  — 模型供应链(体检 W1:哨兵以前只看采集表)—"
            report += "".join(f"\n  · {q}" for q in supply_info)
            report += "".join(f"\n  ✗ {q}" for q in supply_alarms)
        if label_info or label_alarms:
            report += "\n\n  — 联赛标签双轨(2026-08-05:模块早就描述了这个病,却没人在报)—"
            report += "".join(f"\n  · {q}" for q in label_info)
            report += "".join(f"\n  ✗ {q}" for q in label_alarms)
        if trickle_info or trickle_alarms:
            report += "\n\n  — 竞彩历史涓流(2026-08-08:上次它「扫完了」是假信号,丢了 4,751 场)—"
            report += "".join(f"\n  · {q}" for q in trickle_info)
            report += "".join(f"\n  ✗ {q}" for q in trickle_alarms)
        if quota_alarms:
            report += "\n" + "\n".join(f"⚠️ 配额: {q}" for q in quota_alarms)
        if probe_fails:
            report += "\n" + "\n".join(
                f"⚠️ 探针: {q}(非配额报警;连续出现=探针本身坏了,修它)"
                for q in probe_fails)
        print(report)
        if args.out:
            Path(args.out).write_text(report + "\n", encoding="utf-8")

    # Quota exhaustion rides the SAME non-zero exit as a stale capture table →
    # the daily_settle chain's osascript push fires for it too (P1#13: the
    # pull-only panels meant a burned-out key was discovered days later).
    # 体检 W1:模型供应链报警(artifact/源树超龄)同乘 — D1 冻结类必须响。
    # 2026-08-05:联赛标签劈开/未知**同乘**这条非零退出 —— 它损坏的是「按联赛
    # 分人口」这件事本身(P3 计数、CLV 闸的 FDR 家族),和捕获表停更一样值得人看。
    # 2026-08-08:涓流报警**同乘**这条非零退出 —— 它守的是「回填停了」和
    # 「零新增是假信号」两件事,而两者都曾经静默地丢掉几千场数据。
    return 1 if (crit_stale or quota_alarms or supply_alarms or label_alarms
                 or trickle_alarms) else 0


if __name__ == "__main__":
    sys.exit(main())
