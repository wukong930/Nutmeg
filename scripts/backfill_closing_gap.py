"""补回 `odds_snapshots[closing]` 的历史空洞 — 走 Odds API **历史快照**端点。

病史(2026-07-23):Odds API 配额 07-13 耗尽 → 收盘锚断 9 天 → 07-22 换 key 当天补上
→ 新鲜度哨兵立刻转绿(最后 0d),身后 9 天的洞没人看见。data_freshness 的内部空洞
检查现在会报它;本脚本负责**把洞填上**。

⚠️ **要花钱**:历史端点是常规请求的 10 倍计价(还要乘 markets×regions)。跑之前
先看 `--dry-run`(不发一个请求,只打印会拉哪些快照 + 估算额度)。

⚠️ **绝不写 in-play 线**:请求时刻 T 的快照里,已开球的比赛给的是 LIVE 赔率
(领先方 → 1.06/53.96 那种退化线)。把它记成「收盘」会毒死 CLV 账本和软水扫描
(2026-07-01 真出过一次幻影 +87% EV)。所以只写 **kickoff ∈ (T, T+WINDOW]** 的场次
—— 既排除已开球的,也排除还早得很、这条线根本不是它收盘价的场次。

口径与实盘一致:Pinnacle-STRICT(没有 Pinnacle 报价就跳过,绝不用软书顶替 sharp
先验)、markets=h2h,totals、regions=eu —— 与 `capture_closing_pinnacle` 同参,
免得补回来的行和 cron 写的行不是一个口径。

用法:
  .venv/bin/python scripts/backfill_closing_gap.py --dry-run
  .venv/bin/python scripts/backfill_closing_gap.py --from 2026-07-13 --to 2026-07-21
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

import httpx

from nutmeg.v4.data.league_labels import league_filter_variants
from nutmeg.v4.data.sources.odds_api import (
    SPORT_KEYS,
    _extract_h2h,
    _extract_totals,
    fetch_historical_snapshot,
)
from nutmeg.v4.observation.odds_snapshots import record_row_snapshot

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "v4_observation.db"

# 中文标签 → sport_key。⚠️ 这里**曾经**有一份手维护的中文→代码字典(8 条),注释
# 写着「league_labels._EN_TO_CN 只覆盖前者,这里补全后者」—— 后来 _EN_TO_CN 长全了,
# 这份副本却停在原地。2026-08-30 实测:那 8 条它全都重复,而它**漏了**西甲/日职/
# 意甲/英超/德甲/法乙/葡超/英冠 —— 正好是训练联赛。后果不是报错,是 `sk=None`
# ⇒ `continue` ⇒ **静静跳过 38% 的可拉人口(248/646 行)**,和「没有数据」同形。
# ⇒ 改为从 `league_filter_variants` 展开(由 _EN_TO_CN 推导,不可能再掉队)。
#   两轨通吃:传中文缩写或 V4 EN 代码,都拿到同一个 sport_key。
def _sport_key(label: str | None) -> str | None:
    """任一轨的联赛写法 → Odds API sport_key;认不出返回 None(调用方静默跳过)。"""
    if not label:
        return None
    for v in sorted(league_filter_variants({label})):
        if v in SPORT_KEYS:
            return SPORT_KEYS[v]
    return None

# 只写「快照时刻之后这么久内开球」的场次 —— 见模块头那条 in-play 铁律。
WINDOW_MIN = 30
LEAD_MIN = 5          # 快照取开球前 5 分钟(要的是收盘价,不是赛前很久的价)


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quota_remaining(key: str) -> int | None:
    """免费端点 /v4/sports 的响应头带 credit 计数器 —— 用它做前后差值算真实花费。"""
    try:
        r = httpx.get("https://api.the-odds-api.com/v4/sports/",
                      params={"apiKey": key}, timeout=10)
        v = r.headers.get("x-requests-remaining")
        return int(float(v)) if v is not None else None
    except Exception:  # noqa: BLE001 — 探针失败不该拦住回填
        return None


def plan(day_from: str, day_to: str) -> dict[tuple[str, str], list[dict]]:
    """→ {(sport_key, 快照ISO): [该快照要落的场次]}。以竞彩上架过的场次为准 ——
    我们只需要会用到的锚,不必把整个联赛的历史都拉回来。"""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT DISTINCT league, home_team, away_team, match_date, kickoff_utc "
            "FROM jingcai_sp WHERE market='had' AND kickoff_utc >= ? AND kickoff_utc < ? "
            "AND kickoff_utc IS NOT NULL ORDER BY kickoff_utc",
            (day_from, (dt.date.fromisoformat(day_to) + dt.timedelta(days=1)).isoformat()),
        ).fetchall()
    finally:
        conn.close()
    out: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        sk = _sport_key(r["league"])
        if not sk:
            continue          # 没有 sport_key 的联赛拉不到,静静跳过(汇总里会显示)
        try:
            ko = dt.datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            continue
        snap = _iso(ko - dt.timedelta(minutes=LEAD_MIN))
        out.setdefault((sk, snap), []).append(
            {"league": code, "home": r["home_team"], "away": r["away_team"],
             "date": r["match_date"], "kickoff": ko})
    return out


def harvest(sport_key: str, snap_iso: str, *, db: Path, dry: bool) -> tuple[int, int]:
    """拉一张快照 → 写入窗口内的场次。→ (写入行数, 因已开球/超窗跳过的场次数)。"""
    body = fetch_historical_snapshot(
        sport_key, snap_iso, regions="eu", markets="h2h,totals")
    stamp = body.get("timestamp") or snap_iso
    t0 = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    written = skipped = 0
    for e in body.get("data") or []:
        home, away = e.get("home_team"), e.get("away_team")
        ct = e.get("commence_time")
        if not (home and away and ct):
            continue
        try:
            ko = dt.datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except ValueError:
            continue
        # 铁律:只要 (T, T+WINDOW]。ko<=T ⇒ 已开球 = LIVE 线,写进去就是投毒。
        if not (t0 < ko <= t0 + dt.timedelta(minutes=WINDOW_MIN)):
            skipped += 1
            continue
        pin = next((b for b in e.get("bookmakers", [])
                    if (b.get("key") or "").lower() == "pinnacle"), None)
        if not pin:
            continue          # Pinnacle-STRICT:不拿软书顶 sharp 先验
        h2h = _extract_h2h(pin)
        teams = (h2h or {}).get("teams", {})
        ph, pa = teams.get(home), teams.get(away)
        if h2h is None or ph is None or pa is None:
            continue
        tot = _extract_totals(pin) or (None, None, None)
        row = {
            "date": ct[:10], "league": sport_key,
            "home_team": home, "away_team": away,
            "psc_home": ph, "psc_draw": h2h["draw"], "psc_away": pa,
            "ou_line": tot[0], "psc_over25": tot[1], "psc_under25": tot[2],
            "odds_update": pin.get("last_update"), "kickoff_utc": ct,
            "odds_source": "odds_api",      # 历史端点也是 OA
        }
        if dry:
            written += 1
        else:
            # ⚠️ captured_at 必须是**快照的真实时刻**,不是现在。默认(now)会把补回来
            # 的行全戳成今天:空洞照旧显示为空洞(数据明明已找回),线史分析还会看到
            # 几十行挤在同一秒。2026-07-23 第一版就是这么错的,重跑修正。
            written += int(record_row_snapshot(
                db, row, source="closing",
                captured_at=t0.isoformat(timespec="seconds")))
    return written, skipped


def main(argv: list[str] | None = None) -> int:
    import os

    p = argparse.ArgumentParser(description="回填 closing 收盘锚的历史空洞")
    p.add_argument("--from", dest="day_from", default="2026-07-13")
    p.add_argument("--to", dest="day_to", default="2026-07-21")
    p.add_argument("--dry-run", action="store_true",
                   help="不发请求、不写库,只打印计划与额度估算")
    p.add_argument("--db", default=str(DB))
    args = p.parse_args(argv)

    tasks = plan(args.day_from, args.day_to)
    n_match = sum(len(v) for v in tasks.values())
    print(f"窗口 {args.day_from} → {args.day_to}:{n_match} 场竞彩上架过的比赛 "
          f"→ {len(tasks)} 张历史快照")
    by_sk: dict[str, int] = {}
    for (sk, _), v in tasks.items():
        by_sk[sk] = by_sk.get(sk, 0) + len(v)
    for sk, n in sorted(by_sk.items(), key=lambda x: -x[1]):
        print(f"    {sk:<40}{n:>3} 场")
    if args.dry_run:
        print(f"\n[dry-run] 未发任何请求。单价未知(仓库注释说 10,官方口径应为 "
              f"10×markets×regions=20)⇒ 预计 {len(tasks) * 10}–{len(tasks) * 20} 额度。")
        return 0

    key = os.environ.get("NUTMEG_ODDS_API_KEY")
    before = _quota_remaining(key) if key else None
    print(f"\n开跑前剩余 credit: {before if before is not None else '(探针失败)'}")

    tot_w = tot_s = fails = 0
    unit_reported = False
    for i, ((sk, snap), matches) in enumerate(sorted(tasks.items()), 1):
        try:
            w, s = harvest(sk, snap, db=Path(args.db), dry=False)
        except Exception as exc:  # noqa: BLE001 — 单张失败不该终止整轮
            fails += 1
            print(f"  [{i:>2}/{len(tasks)}] ✗ {sk} @ {snap}: "
                  f"{type(exc).__name__}: {exc}")
            continue
        tot_w += w
        tot_s += s
        print(f"  [{i:>2}/{len(tasks)}] {sk:<38} {snap}  写 {w:>2} 行"
              f"(窗外跳过 {s})  目标 {len(matches)} 场")
        # 第一张拉完立刻报真实单价 —— 别让「按估算跑完」变成事后才知道花了多少。
        if not unit_reported and before is not None:
            after1 = _quota_remaining(key)
            if after1 is not None:
                print(f"       ↳ 实测单价 = {before - after1} 额度/张 "
                      f"⇒ 本轮预计共 {(before - after1) * len(tasks)}")
                unit_reported = True

    after = _quota_remaining(key) if key else None
    print(f"\n写入 {tot_w} 行 · 窗外跳过 {tot_s} 场 · 失败 {fails} 张")
    if before is not None and after is not None:
        print(f"剩余 credit: {before} → {after}(本轮实花 {before - after})")
    return 1 if fails and not tot_w else 0


if __name__ == "__main__":
    raise SystemExit(main())
