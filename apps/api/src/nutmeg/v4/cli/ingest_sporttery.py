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
import json
import logging

# Persistent, queryable surface for「当日未映射竞彩队名」— repo 根下,由 db_path 反推
# (data/v4_observation.db → 上两级)。桌面推送易逝(无头 launchd 里看不见)、cron
# out.log 没人读(体检 2026-07-03 P2),这个 latest 文件被 health_check.sh 主动读出。
_UNMAPPED_REPORT_RELPATH = "logs/sporttery_unmapped_latest.txt"
_UNMAPPED_HISTORY_RELPATH = "logs/sporttery_unmapped_history.jsonl"


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


def _append_unmapped_history(db_path, summary: dict, matches: list[dict],
                             stamp_utc: str, phase: str, trigger: str,
                             had_w: int, hhad_w: int) -> None:
    """把每次 harvest 的**名字解析**缺口追加到 `logs/sporttery_unmapped_history.jsonl`。

    ⭐ **为什么不是「把 _latest 按日期存一份副本」。** 那是 δ 校准仪表踩过的坑的
    *半个* 修法:有历史了,但仍只有**分子**。`_latest` 记「哪几场没映射上」,
    三个月的分子攒起来**算不出率** —— 那几天竞彩上架了多少场、哪些联赛,没人记。

    🚨 **分母必须以「比赛」为单位,不是「轮次」。** 一天跑 ~16 轮,而一场比赛
    在售 1–3.3 天(实测:世界杯 3.29 天 vs 欧罗巴 1.00 天)⇒ 裸计数被**在售时长
    加权**,逐联赛放大 16–54×。审查实测:90 天模拟里按裸 `bad` 排「先补哪个联赛」
    **12 个联赛错位 8.9 个、top-1 在 5/20 个种子里翻掉**。所以另落一份
    ``matches_seen``:全部在售场次的 ``[联赛, match_date, match_num]`` 身份,
    让消费方**自己跨轮去重**。⛔ 只落「按比赛去重的计数」没用 —— 单条记录内去重
    与不去重**完全相同**(一轮里同一场不出现两次),膨胀只在跨轮求和时发生。
    ⚠️ ``(联赛, 日期)`` **不是唯一键**(实测 54.7% 的格子装不止一场,最多 16)
    ⇒ 去重键**必须**带 `match_num`,少了它照样排错。

    🚨 **`side` 不能省。** 一场未映射通常只坏一侧,另一侧被连坐:审查实测
    被点名的 116 个队名里 **74 个(64%)本身映射得好好的**,逐队计数中位虚高 ×32。
    ⛔ 「读的时候拿词典再筛一遍」是**假补救**:词典近乎纯增(近 20 个提交 +145/−3),
    用窗口末的词典去筛会把真发生过的缺口筛成 0。

    ⚠️⚠️ **这份记录测的是「名字解不解得出」,不是「盘面上有没有价」。**
    分子来自 `summarize_unmapped`,它**从不碰赔率**(见 `routes.py` 该端点 docstring:
    「解不出 ≠ 整场丢弃」「(N/M) 不能读成另外 M−N 场都在盘面上」)。实测 07-21~08-20
    的 291 场「名字解出来了」里 **10 场(3.4%)盘面零行**(巴西杯 7/7 等)。
    ⇒ 曲线变绿**不等于**窟窿变小。落 ``had_w``/``hhad_w`` 是为了至少能分出
    「名字解出来了」和「行真的落库了」——**但那仍不是「有没有价」。**

    ⚠️ **只覆盖实时源。** 竞彩走势档案(`jingcai_odds_history`)是另一套更短的写法
    (实测四个实时写法在档案里出现 0 次)⇒ 档案侧缺口(2026-08-20:比赛级 26.8%)
    与这份历史**互不可推**。两条链,两个分母。

    ⭐ **jsonl 而非每日一文件**:一天多轮(open ×2 + evening ×13 + exotics + 🎯 按钮),
    轮间差异本身是信号(竞彩分批上架)。append-only ⇒ 任何一次写都不抹掉先前观测。
    ``n_matches == 0`` **也落一行** —— 那样才能把「抓到 0 场」与「根本没跑 / 写失败」
    分开(四态同形是审查确认的真缺陷)。

    Fail-soft,但**留痕**:写失败记一条 warning(旧版静默 `pass`,而这个文件
    今天还没有任何读者 ⇒ 静默失败会永远看不见)。
    """
    from collections import Counter
    from pathlib import Path
    try:
        n_all = Counter((m.get("league_cn") or "?") for m in matches)
        n_bad = Counter((u["league_cn"] or "?") for u in summary["unmapped"])
        # ⭐ 全部在售场次的**身份** —— 跨轮聚合唯一的把手。
        # ⚠️ 只落 by_league 的计数是不够的:单条记录里去重与不去重**完全相同**,
        #    膨胀只在**跨轮求和**时发生 ⇒ 消费方必须能自己去重,而去重需要身份。
        #    只落未映射那些的身份(names)则只能去重**分子**,分母照样塌。
        seen = [[m.get("league_cn") or "?", m.get("match_date"), m.get("match_num")]
                for m in matches]
        names = []
        for m in matches:
            if m.get("home_en") and m.get("away_en"):
                continue
            lg = m.get("league_cn") or "?"
            side = ("" if m.get("home_en") else "h") + ("" if m.get("away_en") else "a")
            names.append([m.get("home_cn"), m.get("away_cn"), lg,
                          m.get("match_date"), m.get("match_num"), side])
        rec = {
            "t": stamp_utc,
            "phase": phase,          # jingcai_sp 写入语义:open 盖 jc_open_*,close 盖终盘
            "trigger": trigger,      # 谁触发的:cron 各槽位 vs 🎯 按钮 —— phase 分不出
            "n_matches": len(matches),
            "n_unmapped": len(summary["unmapped"]),
            "rows_written": {"had": had_w, "hhad": hhad_w},
            # 裸计数(按轮次)—— 只用于同一轮内部,⛔ 跨轮求和会被在售时长加权
            "by_league": {lg: {"n": n, "bad": n_bad.get(lg, 0)} for lg, n in n_all.items()},
            # ⭐ [league_cn, match_date, match_num] × 全部在售场次 —— 跨轮去重的把手。
            # 分母和分子共用同一套键(names 的第 3-5 项),所以两边都能去重。
            "matches_seen": seen,
            "gone": summary["gone"],
            "partial": summary["partial"],
            # [home_cn, away_cn, league_cn, match_date, match_num, side] — side 指**坏的是哪侧**
            "names": names,
        }
        out = Path(db_path).resolve().parent.parent / _UNMAPPED_HISTORY_RELPATH
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        # ⛔ 别退回静默 pass:这份数据**结构上无法回溯**(见 docstring),
        # 而它今天还没有任何读者 ⇒ 静默失败 = 永久空洞且无人知晓。
        logging.getLogger(__name__).warning(
            "未映射历史写入失败(%s: %s)—— 这一轮的观测永久丢失", type(exc).__name__, exc)


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
                  phase: str = "close", exotics: bool = False,
                  trigger: str = "cli") -> dict:
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
    import datetime
    if matches:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        _write_unmapped_report(
            db_path, render_unmapped_report(summary, stamp, len(matches)))
    # 2026-08-20 —— 同一份 summary 再落一条 append-only 历史(带**按比赛去重**的分母)。
    # `_latest` 只有当下一帧,判不了「缺口在变好还是变坏」;而实时侧的缺口**结构上
    # 无法回溯**(走势档案是另一套写法)⇒ 只能从今天开始前向积累。
    # ⚠️ 与 `_latest` 不同:**0 场也写**。`_latest` 不刷新是为了不洗成 ✅ 假绿;
    #    而历史要的是相反的东西 —— 记下「这一轮跑了、结果是 0 场」,
    #    否则「抓到 0 场 / cron 没跑 / 写失败 / 开关关掉」四态在文件上完全同形。
    _append_unmapped_history(
        db_path, summary, matches,
        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        phase, trigger, had_w, hhad_w)
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

    r = harvest_to_db(args.db, matches=matches, phase=args.phase,
                      exotics=args.exotics, trigger="cron")
    print(f"\n写入 jingcai_sp: 胜平负 {r['had']} · 让球 {r['hhad']}  "
          f"(source=sporttery, phase={args.phase}, 不覆盖手填)")
    if args.exotics:
        print(f"写入 jingcai_exotic_sp: 比分 {r['crs']} 行 · 总进球 {r['ttg']} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
