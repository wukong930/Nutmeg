"""nutmeg-ingest-sporttery — harvest 竞彩 SP into jingcai_sp (the soft-book feed).

Pulls the current 竞彩 matches from the public sporttery uniform endpoint, maps
team names to our canonical English (so they join Pinnacle/odds_snapshots + the
settler), and writes one ``had`` + one ``hhad`` row per mappable match
(source='sporttery', protect_manual=True so it NEVER clobbers a line you
hand-priced in 市场/标准 模式). Fail-soft: a fetch failure just writes 0 rows.

Low-frequency by design — run once after the ~23:00 竞彩 freeze. Read-only; never
touches your betting account. Personal/local use only.
"""
from __future__ import annotations

import argparse
import logging

# Persistent, queryable surface for「当日未映射竞彩队名」— repo 根下,由 db_path 反推
# (data/v4_observation.db → 上两级)。桌面推送易逝(无头 launchd 里看不见)、cron
# out.log 没人读(体检 2026-07-03 P2),这个 latest 文件被 health_check.sh 主动读出。
_UNMAPPED_REPORT_RELPATH = "logs/sporttery_unmapped_latest.txt"


def summarize_unmapped(matches: list[dict]) -> dict:
    """从抓取到的竞彩场次里挑出「队名映射不到英文规范名」的场,并按联赛聚合出报警。

    这类场 ingest 会**整场丢弃**(无 EN 名 join 不了 Pinnacle、算不了 EV — 丢是对的),
    问题只在丢得**静默**:一场从「近期赛事」消失,靠人肉发现少了场(2026-07-07 欧冠
    资格赛 2/3 场即此)。纯函数,CLI 展示 + sink 持久化共用同一口径。

    返回 ``{unmapped, gone, partial, alarm_bits}``:
      - ``unmapped``: ``[{home_cn, away_cn, league_cn}]`` — 每个被丢的场
      - ``gone``:     整联赛 0 场入库的联赛名(该联赛全部未映射)
      - ``partial``:  ``["联赛 n/total"]`` — ≥2 场且过半未映射(「半坏」盲区,体检
                      2026-07-04:6/7 场丢但 1 场存活曾让整场静默报警失效)
      - ``alarm_bits``: 给桌面推送的短句(gone/partial 各一条)
    """
    from collections import Counter
    unmapped = [
        {"home_cn": m.get("home_cn"), "away_cn": m.get("away_cn"),
         "league_cn": m.get("league_cn")}
        for m in matches if not (m.get("home_en") and m.get("away_en"))
    ]
    n_all = Counter((m.get("league_cn") or "?") for m in matches)
    n_bad = Counter((u["league_cn"] or "?") for u in unmapped)
    gone = [lg for lg, n in n_bad.items() if n == n_all[lg]]
    partial = [f"{lg} {n}/{n_all[lg]}" for lg, n in n_bad.items()
               if n < n_all[lg] and n >= 2 and n * 2 >= n_all[lg]]
    alarm_bits: list[str] = []
    if gone:
        alarm_bits.append(f"整联赛丢失: {', '.join(gone)}")
    if partial:
        alarm_bits.append(f"过半丢失: {', '.join(partial)}")
    return {"unmapped": unmapped, "gone": gone, "partial": partial,
            "alarm_bits": alarm_bits}


def render_unmapped_report(summary: dict, stamp: str, n_matches: int) -> str:
    """把 ``summarize_unmapped`` 的结果渲成持久文本报告。第 2 行是给 health_check.sh
    解析的计数摘要(照 name_sentinel_latest.txt 的约定:第 2 行 = 一行式计数)。"""
    unmapped = summary["unmapped"]
    lines = [
        f"竞彩未映射队名 — {stamp}",
        f"抓取 {n_matches} 场 · 未映射 {len(unmapped)} 场 · "
        f"整联赛丢失 {len(summary['gone'])} · 过半丢失 {len(summary['partial'])}",
        "",
    ]
    if not unmapped:
        lines.append("✅ 全部映射 — 每场都拿到英文规范名,能 join Pinnacle 算 EV。")
        return "\n".join(lines)
    lines.append(
        "⚠️ 这些竞彩队名映射不到英文规范名 → 整场被丢弃(无 EN 名 join 不了 Pinnacle)。"
        "补 sporttery.py 的 _ZH_OVERRIDES(对照 gather 真实拼写):")
    for u in unmapped:
        lines.append(f"  [{u['league_cn'] or '?'}] "
                     f"{u['home_cn'] or '?'} / {u['away_cn'] or '?'}")
    if summary["gone"]:
        lines.append(f"⚠️ 整联赛丢失(0 场入库): {', '.join(summary['gone'])}")
    if summary["partial"]:
        lines.append(f"⚠️ 联赛过半丢失: {', '.join(summary['partial'])}")
    return "\n".join(lines)


def _write_unmapped_report(db_path, report: str) -> None:
    """把未映射报告写到 ``<repo>/logs/sporttery_unmapped_latest.txt``(repo 根由
    db_path 反推)。Fail-soft:写失败绝不打断 ingest。sink 层调用 ⇒ cron **和** 🎯
    刷新按钮两条路都留下持久记录(旧代码报警只在 CLI main(),按钮路完全无痕)。"""
    from pathlib import Path
    try:
        out = Path(db_path).resolve().parent.parent / _UNMAPPED_REPORT_RELPATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report + "\n", encoding="utf-8")
    except OSError:
        pass


def _push_unmapped_alarm(alarm_bits: list[str]) -> None:
    """桌面弹窗 — 即时但**易逝**的通道(无头 launchd 里常看不见)。持久通道是 sink 写的
    logs/sporttery_unmapped_latest.txt(health_check.sh 主动读),即使这条推送没人看见
    也不丢。Fail-soft。"""
    if not alarm_bits:
        return
    try:
        import subprocess
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{"; ".join(alarm_bits)} — '
             f'补 _ZH_OVERRIDES" with title "⚠️ Nutmeg 竞彩联赛丢失"'],
            check=False, capture_output=True, timeout=10)
    except Exception:  # noqa: BLE001 — alert is best-effort
        pass


def harvest_to_db(db_path, *, pool_codes: str = "had,hhad", refresh: bool = False,
                  matches: list[dict] | None = None, protect_manual: bool = True,
                  phase: str = "close", exotics: bool = False) -> dict:
    """Upsert the current 竞彩 SP into jingcai_sp (source=sporttery). Fetches if
    ``matches`` is None. Returns ``{matches, mapped, unmapped, had, hhad, crs, ttg,
    unmapped_teams, alarm_bits}``. Shared by the CLI and the 🎯 刷新竞彩 endpoint.

    As the SHARED sink it also persists「当日未映射队名」to
    logs/sporttery_unmapped_latest.txt on every real harvest — so a dropped match
    (no EN name → can't join Pinnacle → silently gone from 近期赛事) leaves a durable,
    queryable trace via BOTH the cron and the 🎯 button (health_check.sh reads it).
    The alarm used to live only in the CLI ``main()``; the button path had no signal.

    ``protect_manual``: True (default, for the unattended cron) skips any row a user
    hand-priced in 市场/标准 模式. The 🎯 button passes False — an *explicit* refresh
    means "give me the latest official SP", so it must overwrite the (often stale)
    market_mode capture; otherwise the button fetches fresh data but can't show it.

    ``exotics``: also capture 比分(crs)/总进球(ttg) outcomes → jingcai_exotic_sp
    (long-format). Off by default — only the daily exotics cron passes True. The
    pulled ``matches`` must already carry crs/ttg pools (request those pool codes)."""
    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
    if matches is None:
        from nutmeg.v4.data.sources.sporttery import fetch_lottery_matches
        matches = fetch_lottery_matches(pool_codes=pool_codes, refresh=refresh)
    mapped = [m for m in matches if m["home_en"] and m["away_en"]]
    had_w = hhad_w = crs_w = ttg_w = 0
    for m in mapped:
        common = {
            "match_date": m["match_date"], "home_team": m["home_en"],
            "away_team": m["away_en"], "league": m["league_cn"],
            "kickoff_utc": m.get("kickoff_utc"),
            "source": "sporttery", "protect_manual": protect_manual,
            "phase": phase,  # 'open' (11:00 开售) stamps jc_open_*; 'close' = 终盘 (default)
        }
        single = m.get("single") or {}   # {'had':0/1,'hhad':0/1} 竞彩 per-market 单关可投
        if m["had"]:
            jh, jd, ja = m["had"]
            had_w += int(record_jingcai_sp(
                db_path, jc_home=jh, jc_draw=jd, jc_away=ja, market="had",
                single_available=single.get("had"), **common))
        if m["hhad"]:
            jh, jd, ja, line = m["hhad"]
            hhad_w += int(record_jingcai_sp(
                db_path, jc_home=jh, jc_draw=jd, jc_away=ja, market="hhad",
                handicap_home=line, single_available=single.get("hhad"), **common))
    if exotics:
        from nutmeg.v4.observation.jingcai_exotic import record_exotic_sp
        for m in mapped:
            ex_common = {
                "match_date": m["match_date"], "home_team": m["home_en"],
                "away_team": m["away_en"], "league": m["league_cn"],
                "kickoff_utc": m.get("kickoff_utc"), "source": "sporttery",
            }
            if m.get("crs"):
                crs_w += record_exotic_sp(db_path, market="crs", outcomes=m["crs"], **ex_common)
            if m.get("ttg"):
                ttg_w += record_exotic_sp(db_path, market="ttg", outcomes=m["ttg"], **ex_common)
    # 持久化「当日未映射队名」到 logs/sporttery_unmapped_latest.txt(sink 层 ⇒ cron 和
    # 🎯 按钮两条路都留痕)。只在真抓到场次时刷新 — 抓取失败(0 场)别把上次报告洗成✅假绿;
    # 那种漏由 data_freshness「jingcai_sp 停长」另行报警。Fail-soft,绝不打断入库。
    summary = summarize_unmapped(matches)
    if matches:
        import datetime
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        _write_unmapped_report(
            db_path, render_unmapped_report(summary, stamp, len(matches)))
    return {"matches": len(matches), "mapped": len(mapped),
            "unmapped": len(summary["unmapped"]), "had": had_w, "hhad": hhad_w,
            "crs": crs_w, "ttg": ttg_w,
            "unmapped_teams": summary["unmapped"], "alarm_bits": summary["alarm_bits"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="harvest 竞彩 SP → jingcai_sp (软盘喂数)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--pool-codes", default="had,hhad", help="竞彩 pools to pull")
    ap.add_argument("--refresh", action="store_true", help="bypass the TTL cache")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written")
    ap.add_argument("--phase", choices=["open", "close"], default="close",
                    help="open=11:00 开售初盘(记 jc_open_*,set-once) | close=终盘(默认)")
    ap.add_argument("--exotics", action="store_true",
                    help="也捕获 比分(crs)+总进球(ttg) → jingcai_exotic_sp(长格式)")
    ap.add_argument("--jitter-seconds", type=int, default=0,
                    help="启动前随机等待 0..N 秒(晚间高频窗用:打散固定周期指纹)")
    ap.add_argument("--backfill-pinnacle", action="store_true",
                    help="只补历史行的捕获时 Pinnacle(psc_*/O-U)后退出,不抓取")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # 补录模式:2026-07-27 之前 cron 写的行没带捕获时 Pinnacle(它读竞彩源,
    # 手里没有 Pinnacle)⇒ 进不了 CLV 账本的选中腿计数。逐行按**该行自己的**
    # captured_at 回查,口径与新行一致(不含未来信息)。幂等,可重复跑。
    if args.backfill_pinnacle:
        from nutmeg.v4.observation.jingcai_sp import backfill_jingcai_sp_pinnacle
        filled = backfill_jingcai_sp_pinnacle(args.db)
        print(f"捕获时 Pinnacle 补录: {filled} 行")
        return 0

    # 2026-07-20 — 晚间高频窗(17:00-23:30 每 30 分)的礼貌措施:launchd 的
    # StartCalendarInterval 是**秒级精确**的,24h×N 个完美整点打点是最像机器人的
    # 特征。随机抖动把它摊成人类节奏,代价是几十秒延迟(对 30 分钟窗无影响)。
    if args.jitter_seconds > 0:
        import random
        import time as _t
        delay = random.uniform(0, args.jitter_seconds)  # noqa: S311 — 非密码学用途
        print(f"抖动等待 {delay:.0f}s(避开整点指纹)")
        _t.sleep(delay)

    from nutmeg.v4.data.sources.sporttery import fetch_lottery_matches

    pool_codes = args.pool_codes
    if args.exotics:  # ensure the fetch pulls the exotic pools too (order-preserving)
        codes = [c.strip() for c in pool_codes.split(",") if c.strip()]
        for extra in ("crs", "ttg"):
            if extra not in codes:
                codes.append(extra)
        pool_codes = ",".join(codes)
    matches = fetch_lottery_matches(pool_codes=pool_codes, refresh=args.refresh)
    print(f"竞彩抓取: {len(matches)} 场")
    if not matches:
        print("  (端点无数据或失败 — 失败软,未写入)")
        return 0

    mapped = [m for m in matches if m["home_en"] and m["away_en"]]
    summary = summarize_unmapped(matches)
    unmapped = summary["unmapped"]
    print(f"队名映射: {len(mapped)}/{len(matches)} 成功", end="")
    if unmapped:
        print(" · 未映射: " + ", ".join(
            f"{u['home_cn']}/{u['away_cn']}" for u in unmapped[:8]))
        # 整场丢弃是对的(无 EN 名 join 不了 Pinnacle、算不了 EV);报警口径在
        # summarize_unmapped:整联赛丢失 + 「半坏」过半丢失(体检 2026-07-03 韩职
        # 6/6、07-04 瑞超 6/7 的盲区 — 单场存活曾让整场静默报警失效)。
        if summary["gone"]:
            print(f"  ⚠️ 整联赛丢失(0 场入库): {', '.join(summary['gone'])} — "
                  f"补 sporttery.py _ZH_OVERRIDES(对照 gather 真实拼写)")
        if summary["partial"]:
            print(f"  ⚠️ 联赛过半丢失: {', '.join(summary['partial'])} — "
                  f"竞彩中文拼法≠字典键,补 _ZH_OVERRIDES")
        # 即时通道:桌面推送(易逝,无头 launchd 里常看不见)。持久通道:harvest_to_db
        # 写的 logs/sporttery_unmapped_latest.txt + health_check.sh — 互为兜底。
        _push_unmapped_alarm(summary["alarm_bits"])
    else:
        print()

    if args.dry_run:
        print("\n样例(将写入,英文规范名):")
        for m in mapped[:6]:
            line = (f"  {m['home_en']} vs {m['away_en']}  {m['match_date']}  "
                    f"had={m['had']}  hhad={m['hhad']}")
            if args.exotics:
                line += f"  crs={len(m.get('crs') or {})}个  ttg={len(m.get('ttg') or {})}个"
            print(line)
        print("\n(dry-run — 未写库)")
        return 0

    r = harvest_to_db(args.db, matches=matches, phase=args.phase, exotics=args.exotics)
    print(f"\n写入 jingcai_sp: 胜平负 {r['had']} · 让球 {r['hhad']}  "
          f"(source=sporttery, phase={args.phase}, 不覆盖手填)")
    if args.exotics:
        print(f"写入 jingcai_exotic_sp: 比分 {r['crs']} 行 · 总进球 {r['ttg']} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
