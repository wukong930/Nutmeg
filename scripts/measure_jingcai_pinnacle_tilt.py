"""探索性:竞彩 vs Pinnacle 的三腿定价倾斜(纯只读)。

问题 C:竞彩去vig 后的 P 相对 Pinnacle 去vig 的 P,主/平/客三腿是否有系统偏移?
  Δᵢ = 竞彩P(腿ᵢ) − PinnacleP(腿ᵢ)
  Δ > 0 → 竞彩隐含概率更高 = 赔率更短 = 对下注者更差
  Δ < 0 → 竞彩赔率相对更长 = 相对更软

口径:两侧同用 basic 归一化(比的是**相对**倾斜,同法即可;WPO 同向作用于两侧,
不改差值符号)。join = A′ 同款硬闸:close_date±1 + 精确 EN 队名 + 比分一致。

⚠️ 探索性:**禁动钱**。本脚本的输出已消耗这条切轴的分析自由度 —— 若要正式追其中
任何线索,须另立预注册假设 + 用前向数据测,不得回喂 P1/P2 确认性检验。

报告:docs/jingcai_pinnacle_tilt_2026-07-20.md
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import sqlite3
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JINGCAI_DB = f"file:{REPO}/data/v4_jingcai_history.db?mode=ro"
FD_GLOB = str(REPO / "data/historical_sources/football_data_co_uk/**/*.csv")
LEG_NAMES = ("主胜", "平局", "客胜")
MIN_LEAGUE_N = 60


def norm3(h: float, d: float, a: float) -> tuple[float, float, float]:
    """basic 归一化去 vig(三腿)。"""
    inv = (1 / h, 1 / d, 1 / a)
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def parse_fd_date(raw: str) -> dt.date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def load_football_data() -> dict:
    """{(home_lower, away_lower, date): (psc, fthg, ftag, league)} — Pinnacle 收盘。"""
    out: dict = {}
    for path in glob.glob(FD_GLOB, recursive=True):
        league = path.rsplit("/", 1)[-1][:-4]
        try:
            with open(path, encoding="latin-1") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            continue
        for row in rows:
            date = parse_fd_date(row.get("Date", "") or "")
            home = (row.get("HomeTeam") or row.get("Home") or "").strip()
            away = (row.get("AwayTeam") or row.get("Away") or "").strip()
            try:
                psc = (float(row["PSCH"]), float(row["PSCD"]), float(row["PSCA"]))
                fthg = int(float(row.get("FTHG") or row.get("HG")))
                ftag = int(float(row.get("FTAG") or row.get("AG")))
            except (KeyError, TypeError, ValueError):
                continue
            if not (date and home and away) or min(psc) <= 1:
                continue
            out[(home.lower(), away.lower(), date)] = (psc, fthg, ftag, league)
    return out


def load_jingcai_finals() -> list:
    """每场 had 的终盘(最后一次变盘)+ 赛果。"""
    conn = sqlite3.connect(JINGCAI_DB, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT match_id, home_team, away_team, close_date, home_goals, away_goals, "
            "h, d, a FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY match_id "
            "ORDER BY update_dt DESC, seq DESC) rn FROM jingcai_odds_history "
            "WHERE market='had' AND home_goals IS NOT NULL) WHERE rn=1"
        ).fetchall()
    finally:
        conn.close()


def join_rows(finals: list, fd: dict) -> tuple[dict, dict, dict, int]:
    """→ (逐腿 Δ, 逐腿 Pinnacle 校准残差, 分联赛主胜 Δ, 命中数)。"""
    diffs: dict = {0: [], 1: [], 2: []}
    pin_resid: dict = {0: [], 1: [], 2: []}
    by_league: dict = {}
    matched = 0
    for row in finals:
        try:
            base = dt.date.fromisoformat(row["close_date"])
        except (TypeError, ValueError):
            continue
        hit = None
        for offset in (0, 1, -1):
            hit = fd.get((
                (row["home_team"] or "").lower(),
                (row["away_team"] or "").lower(),
                base + dt.timedelta(days=offset),
            ))
            if hit:
                break
        if not hit:
            continue
        psc, fthg, ftag, league = hit
        if (fthg, ftag) != (int(row["home_goals"]), int(row["away_goals"])):
            continue  # 比分硬闸
        try:
            jingcai = norm3(float(row["h"]), float(row["d"]), float(row["a"]))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        pinnacle = norm3(*psc)
        matched += 1
        result = 0 if fthg > ftag else (1 if fthg == ftag else 2)
        for leg in range(3):
            diffs[leg].append(jingcai[leg] - pinnacle[leg])
            pin_resid[leg].append((1.0 if result == leg else 0.0) - pinnacle[leg])
        by_league.setdefault(league, []).append(jingcai[0] - pinnacle[0])
    return diffs, pin_resid, by_league, matched


def summarize(values: list) -> tuple[float, float, float]:
    """→ (均值, SE, t)。"""
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return mean, se, (mean / se if se else float("nan"))


def main() -> int:
    fd = load_football_data()
    diffs, pin_resid, by_league, matched = join_rows(load_jingcai_finals(), fd)
    if not matched:
        print("无命中 — 检查 football-data 档案与竞彩历史库路径")
        return 1

    print(f"═══ 竞彩去vig P − Pinnacle去vig P(N={matched:,} 场,比分硬闸)═══")
    print(f"{'腿':<6}{'均值差':>10}{'SE':>8}{'t':>8}{'中位':>9}   判读")
    for leg in range(3):
        mean, se, t = summarize(diffs[leg])
        verdict = "⚠️ 显著" if abs(t) > 3 else ("边缘" if abs(t) > 2 else "无")
        direction = "竞彩高估" if mean > 0 else "竞彩低估"
        median = statistics.median(diffs[leg])
        print(
            f"{LEG_NAMES[leg]:<6}{mean * 100:>+9.3f}pp{se * 100:>7.3f}{t:>8.1f}"
            f"{median * 100:>+8.3f}pp   {verdict} ({direction})"
        )

    print("\n═══ 对照:Pinnacle 自身校准残差(赛果频率 − PinnacleP)═══")
    print("   (功效低 — SE 比主结果大 20 倍;只能排除大幅误校准)")
    for leg in range(3):
        mean, se, t = summarize(pin_resid[leg])
        print(f"{LEG_NAMES[leg]:<6}{mean * 100:>+9.3f}pp{se * 100:>7.3f}{t:>8.1f}")

    print(f"\n═══ 主胜腿倾斜 · 分联赛(N≥{MIN_LEAGUE_N})═══")
    print("   ⚠️ 未做 FDR 校正;t≈2-3 的几条校正后可能不显著")
    for league, values in sorted(by_league.items(), key=lambda kv: -len(kv[1])):
        if len(values) < MIN_LEAGUE_N:
            continue
        mean, se, t = summarize(values)
        print(
            f"  {league:<5} N={len(values):>4}  {mean * 100:>+7.3f}pp "
            f"± {se * 100:.3f}  t={t:>5.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
