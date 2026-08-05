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
    """
    import os

    info: list[str] = []
    alarms: list[str] = []

    art = Path(artifact_dir or os.environ.get("NUTMEG_V4_ARTIFACT_PATH")
               or "data/v4_model_cat")
    meta = art / "metadata.json"
    if meta.exists():
        trained: date | None = None
        try:
            import json
            raw = (json.loads(meta.read_text()) or {}).get("trained_at_utc")
            if raw:
                trained = date.fromisoformat(str(raw)[:10])
        except Exception:  # noqa: BLE001 — 坏 metadata 走 mtime 兜底
            pass
        if trained is None:
            # 旧格式 artifact 无 trained_at_utc(47435ce 之前)→ 文件 mtime 兜底
            trained = datetime.fromtimestamp(meta.stat().st_mtime, UTC).date()
        age = max(0, (today - trained).days)
        line = f"artifact {art.name}: 训练于 {trained} · {age}d(红线 {ARTIFACT_MAX_AGE_DAYS}d)"
        if age > ARTIFACT_MAX_AGE_DAYS:
            alarms.append(f"生产 artifact 已 {age} 天未重训 — 724 天冻结的路重演中,去装/修 retrain")
        info.append(line)
    else:
        info.append(f"artifact {art}: 不存在 — 跳过(非生产环境?生产缺盘 daemon 自己会响)")

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
    supply_info, supply_alarms = (
        ([], []) if args.no_supply else check_model_supply_chain(today))
    label_info, label_alarms = (
        ([], []) if args.no_league_labels else check_league_labels(db_path))

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
    return 1 if (crit_stale or quota_alarms or supply_alarms or label_alarms) else 0


if __name__ == "__main__":
    sys.exit(main())
