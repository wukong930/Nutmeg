#!/usr/bin/env python
"""竞彩历史回填 · 涓流(gentle trickle,防 403)。

每次跑跑一个小日期窗口(7 天),cursor 前进;到末尾绕回起点 → skip_existing 让 re-sweep
只补此前被节流丢的缺口(cheap)。温柔限速(sleep 2s)+ 小批,避免持续抓触发 sporttery
的 403 IP 封。装为 hourly launchd `com.nutmeg.jingcai_history_trickle`;几天覆盖 prereg §H
主窗口 2021-08→2025-07 × 13 受训联赛。覆盖齐(连续 sweep 增量≈0)后 bootout 停用。

`记忆 jingcai-fixedbonus-history-endpoint` · `docs/autumn_prereg_analysis_plan.md §H`。
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

# 中国站:清代理(净 launchd 环境或本机代理都够不着/会干扰)。同 sporttery 其它 cron。
# 2026-07-31 — 补上 ALL_PROXY/all_proxy:curl/requests 都认它们,只清 4 个在
# **本机开了全局代理**时仍会绕道。此前没炸是因为 launchd 环境本来就干净。
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

from nutmeg.v4.cli.ingest_jingcai_history import backfill  # noqa: E402

DB = "data/v4_jingcai_history.db"
# ⚠️ 2026-07-31 —— `None` = **全部联赛**,不是 `TRAINED_LEAGUES_CN`。
#
# 原来只抓 13 受训联赛(那是 prereg §H 的口径:δ 校准要 football-data 对得上)。
# 但这个档案还有第二个用途 —— 回答「某场当时什么价 / EV 多少」,而**我们买的是
# 竞彩卖的,不是我们训练的**。实测一个 7 天窗口:
#   · 2026-06-11→17(夏)  trained **0** 场 · all 31 场  ← 欧洲休赛,只抓 13 个 = 什么都没有
#   · 2026-03-01→07(赛季中) trained 70 场 · all 106 场  ← 只多 1.5×,每次多约 1 分钟
# ⇒ 维持 13 联赛会让洞从「时间形」变成「联赛形」:夏天照样空,而夏天正是竞彩
# 卖北欧/韩职/巴甲/MLS 的时候。代价小、缺口大,取全部。
# (2026-07-31 的缺口回填就是按 all 补的 50 个联赛 —— 涓流不跟上就等于当场重新裂开。)
LEAGUES = None
CURSOR = Path("data/jingcai_history_cursor.txt")
BEGIN = dt.date(2021, 8, 1)
# ⚠️ 2026-07-31 —— END **必须跟着今天走,不能是常量**。
#
# 病史:这里原本硬编码 `dt.date(2025, 7, 31)`(预注册 §H 的窗口)。涓流扫完那天
# 就再也不往前走,而观测库 `jingcai_sp` 从 2026-06-11 才开始 ⇒ 中间 **10.5 个月**
# 两边都没有,而且**没有任何东西会喊** —— 游标照常绕回起点 re-sweep,日志天天绿。
# 直到 owner 问「2026-05-30 神户那场当时 EV 多少」才发现(2,600 场 × 13 联赛全丢)。
#
# 教训:**一个"扫完历史"的任务,它的终点一旦写成常量,就在给未来挖一个静默的洞。**
# 现在 END = 今天 − LAG_DAYS(留结算时间),窗口自己长,洞不会再裂开。
LAG_DAYS = 2
WINDOW_DAYS = 7


def _end_date() -> dt.date:
    return dt.date.today() - dt.timedelta(days=LAG_DAYS)


STATUS = Path("logs/jingcai_trickle_status.jsonl")


def _write_status(**row) -> None:
    """每跑一次追加一行 —— **进度由跑的人自己报**。

    ⭐ 为什么不让体检去算:BEGIN / END / WINDOW_DAYS / 游标全在这个脚本里,
    体检那边要么 import 这个脚本(scripts/ 反向依赖包,不干净),要么**再抄一份常量**
    —— 那正是「测试替身各写一份」那个家族。让生产者报自己的状态,常数只有一处。

    ⚠️ 必须同时记 `enumerated` 和 `stored_rows`:只看 stored_rows,
    「没有东西可捞」和「没去看」长得一模一样 —— 2026-07-20 就是被这个假信号
    说服关掉了这个 job,静默丢了 10.5 个月。判据见 `data_freshness.check_jingcai_trickle`。
    """
    import json
    try:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        with STATUS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass          # 状态写不下去不该拖垮回填本身


# ── 自适应节奏(2026-08-08,owner 授权 hourly)──────────────────────────────
# plist 改成 StartInterval 3600 之后,**回填期**每小时一窗(7 天历史/次 ⇒ 168 天/天,
# 1,775 天的缺口约 11 天扫完,而不是每日 2 窗的 127 天)。
#
# ⚠️ 但 hourly 不能是永久状态 —— 整个「涓流」设计就是为了别持续锤 sporttery(403 封 IP)。
# 而「追平后记得改回来」是**人类记忆**,不是护栏:上一次正是一个「为事后选的参数」
# (END 常量)静默决定了事前,没人会为此报警。
#
# ⇒ **刹车做在脚本里**,不做在 plist 里。判据复用体检那条已经钉死的判别式:
#     stored_rows > 0            → 回填期,每小时都跑
#     enumerated>0 且 stored==0  → 追平了(去看了确实没东西)⇒ 12h 一次即可持平
#     enumerated == 0            → **被挡住了**(限流/403/空响应)⇒ 退避 6h,
#                                  继续每小时敲一个正在拒绝我们的服务器是最坏的一手
# 这样 plist 可以永久留在 hourly:节奏由「最近有没有捞到东西」自己决定,
# 绕回起点 re-sweep 时也会自动降速,不需要任何人记得改回来。
_PACE_LOOKBACK = 6
_PACE_IDLE_H = 12.0        # 追平后的最小间隔(≈ 原来的每日 2 窗)
_PACE_BLOCKED_H = 6.0      # 被挡住时的退避


def _recent_status(n: int = _PACE_LOOKBACK) -> list[dict]:
    import contextlib
    import json
    try:
        lines = STATUS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            with contextlib.suppress(ValueError):
                out.append(json.loads(line))
    return out


def _should_skip(now: dt.datetime | None = None) -> tuple[bool, str]:
    """→ (跳过吗, 理由)。没有历史 = 跑(不知道就别偷懒)。"""
    now = now or dt.datetime.now()
    rows = _recent_status()
    if not rows:
        return (False, "无历史")
    try:
        last = dt.datetime.fromisoformat(str(rows[-1]["ran_at"]))
    except (KeyError, ValueError):
        return (False, "上次时间读不出")
    gap_h = (now - last).total_seconds() / 3600.0
    enum_sum = sum(int(r.get("enumerated") or 0) for r in rows)
    stored_sum = sum(int(r.get("stored_rows") or 0) for r in rows)
    if stored_sum > 0:
        return (False, "回填期")
    need = _PACE_BLOCKED_H if enum_sum == 0 else _PACE_IDLE_H
    why = "被挡住,退避" if enum_sum == 0 else "已追平,维持期"
    if gap_h < need:
        return (True, f"{why}({gap_h:.1f}h < {need:.0f}h)")
    return (False, f"{why},间隔够了({gap_h:.1f}h)")


def main() -> int:
    skip, why = _should_skip()
    stamp0 = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if skip:
        print(f"[trickle {stamp0}] 跳过 —— {why}")
        return 0
    end = _end_date()
    try:
        cur = dt.date.fromisoformat(CURSOR.read_text().strip())
    except (OSError, ValueError):
        cur = BEGIN
    wrapped = cur > end
    if wrapped:  # 绕回起点 → re-sweep 补缺口(skip_existing = 已入库跳过,便宜)
        cur = BEGIN
    w_end = min(cur + dt.timedelta(days=WINDOW_DAYS - 1), end)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[trickle {stamp}] 窗口 {cur}→{w_end}")
    stat = backfill(DB, cur.isoformat(), w_end.isoformat(), leagues=LEAGUES,
                    sleep=2.0, limit=0, dry_run=False, skip_existing=True, chunk_days=7)
    print(f"[trickle {stamp}] {stat}")
    nxt = cur + dt.timedelta(days=WINDOW_DAYS)
    CURSOR.write_text(nxt.isoformat())
    _write_status(
        ran_at=dt.datetime.now().isoformat(timespec="seconds"),
        window_start=cur.isoformat(), window_end=w_end.isoformat(),
        cursor_next=nxt.isoformat(), begin=BEGIN.isoformat(), end=end.isoformat(),
        days_remaining=max((end - nxt).days, 0), wrapped=wrapped,
        **{k: int(stat.get(k, 0)) for k in
           ("enumerated", "in_scope", "fetched", "stored_rows", "skipped", "failed")},
        # ⭐ 2026-08-24 —— 失败的 matchId 逐场留痕。绕回起点 re-sweep 之后,
        # 拿这份列表去查库就能**精确**回答「那些缺口补上了吗」——
        # 只看 stored_rows 是间接判据:「补上了但本来就没数据」和「绕回没生效」同形。
        failed_ids=list(stat.get("failed_ids") or []),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
