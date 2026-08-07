"""1X2 腿加下界收缩后,**每场 argmax 到底翻不翻**、翻了之后赚不赚。

回答的是 owner 2026-08-08 的问题:「串关的筛选腿标准是不是更严格了?」
—— 串关池**不设地板**,所以没有腿被排除;变的只有**同一场里谁当选**。
本脚本就量这件事。

口径与 δ₁ₓ₂ 同源(`docs/onex_delta_prereg_v1.0_2026-08-08.md`),并**复现服务端
那条让球链路**:devig_over → implied_handicap_lines(c1=True) → c1_leg_lower_bounds
(routes.py `_model_board_handicap_lines`)。改服务端不改这里 = 这份结论作废。

**只读**。
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import itertools
import math
import sqlite3
import statistics as st

from onex_delta_calibration import key

from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.market_handicap import (
    c1_leg_lower_bounds,
    devig_over,
    implied_handicap_lines,
)

DB = "data/v4_jingcai_history.db"
FD = "data/historical_sources/football_data_co_uk/**/*.csv"
SHRINK = 0.0116          # k·SE = 2 × 0.0058(δ₁ₓ₂ 实测)


def _iso(d: str) -> str | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_fd() -> dict:
    out = {}
    for f in glob.glob(FD, recursive=True):
        with open(f, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for r in csv.DictReader(fh):
                iso = _iso(r.get("Date") or "")
                if not (iso and r.get("PSCH") and r.get("HomeTeam")):
                    continue
                try:
                    p = devig_1x2(float(r["PSCH"]), float(r["PSCD"]), float(r["PSCA"]))
                    gh, ga = int(r["FTHG"]), int(r["FTAG"])
                except (TypeError, ValueError, KeyError):
                    continue
                if not p:
                    continue
                po = None
                try:
                    po = devig_over(float(r["PC>2.5"]), float(r["PC<2.5"]))
                except (TypeError, ValueError, KeyError):
                    po = None
                out[(key(r["HomeTeam"]), key(r["AwayTeam"]), iso)] = (tuple(p), po, gh, ga)
    return out


def _roi(v: list[dict]) -> tuple[int, float, float]:
    if not v:
        return (0, 0.0, 0.0)
    r = [x["sp"] if x["win"] else 0.0 for x in v]
    sd = st.stdev(r) if len(v) > 1 else 0.0
    return (len(v), st.fmean(r) - 1.0, 2 * sd / math.sqrt(len(v)))


def main() -> None:
    fd = load_fd()
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    had, hhad = {}, {}
    for mid, h, d, a, _gl, hg, ag, day, ht, at in c.execute(
            "SELECT match_id,h,d,a,goal_line,home_goals,away_goals,close_date,"
            "home_team,away_team FROM jingcai_odds_history WHERE market='had' "
            "ORDER BY match_id, seq"):
        had[mid] = (h, d, a, hg, ag, day, ht, at)
    for mid, h, d, a, gl in c.execute(
            "SELECT match_id,h,d,a,goal_line FROM jingcai_odds_history "
            "WHERE market='hhad' ORDER BY match_id, seq"):
        hhad[mid] = (h, d, a, gl)

    matches, rej = [], collections.Counter()
    probe = []
    for mid, (h1, d1, a1, hg, ag, day, ht, at) in had.items():
        if hg is None or ht is None or mid not in hhad:
            rej["无让球盘/未结算"] += 1
            continue
        base = dt.date.fromisoformat(day)
        hit = None
        for off in (0, -1, 1):
            hit = fd.get((key(ht), key(at), (base + dt.timedelta(days=off)).isoformat()))
            if hit:
                break
        if not hit:
            rej["无 PSC"] += 1
            continue
        p, p_over, fgh, fga = hit
        if (fgh, fga) != (hg, ag):
            rej["比分硬闸"] += 1
            continue
        h2, d2, a2, gl = hhad[mid]
        if gl is None:
            rej["让球线缺失"] += 1
            continue
        try:
            lines = implied_handicap_lines(p[0], p[1], p[2], p_over, ou_line=2.5, c1=True)
        except Exception:  # noqa: BLE001
            rej["网格拟合失败"] += 1
            continue
        row = next((x for x in lines if int(x[0]) == int(gl)), None)
        if row is None:
            rej["该让球线不在网格内"] += 1
            continue
        _, ph, pd_, pa = row
        lo = c1_leg_lower_bounds(int(gl), ph, pd_, pa)
        gd, cov = hg - ag, hg - ag + int(gl)
        legs = []
        for i, (pp, sp_) in enumerate(zip(p, (h1, d1, a1), strict=True)):
            if sp_ and sp_ > 1:
                legs.append({"kind": "1x2", "p": pp, "lo": pp, "sp": sp_,
                             "win": (gd > 0, gd == 0, gd < 0)[i]})
        for i, (pp, ll, sp_) in enumerate(zip((ph, pd_, pa), lo, (h2, d2, a2), strict=True)):
            if sp_ and sp_ > 1:
                legs.append({"kind": "hc", "p": pp, "lo": ll, "sp": sp_,
                             "win": (cov > 0, cov == 0, cov < 0)[i]})
        if len(legs) < 2:
            rej["腿不足"] += 1
            continue
        probe.append((int(gl), p[0], ph))
        matches.append({"mid": mid, "day": day, "legs": legs})

    print("=" * 76)
    print("1X2 下界收缩后:每场 argmax 翻不翻 · 翻了赚不赚")
    print("复现服务端让球链路(devig_over → implied_handicap_lines c1=True → c1_leg_lower_bounds)")
    print("=" * 76)
    print(f"入样 {len(matches)} 场 / {len({m['day'] for m in matches})} 个竞彩比赛日")
    for k, v in rej.most_common():
        print(f"  拒绝 · {k}: {v}")

    # 探针:让球线方向必须对 —— gl=−1(主队让1球)时 P(让胜) 必 < P(主胜)
    bad = [1 for gl, p1, ph in probe if gl == -1 and ph >= p1]
    print(f"\n【方向探针】gl=−1 的 {sum(1 for gl,_,_ in probe if gl==-1)} 场里,"
          f"P(让胜) ≥ P(主胜) 的有 {len(bad)} 场 "
          f"{'✅ 让球线方向正确' if not bad else '❌ 符号约定反了,以下全部作废'}")

    def pick(m, shrink):
        best = None
        for lg in m["legs"]:
            lo = lg["lo"] - (shrink if lg["kind"] == "1x2" else 0.0)
            e = lo * lg["sp"] - 1
            if best is None or e > best[0]:
                best = (e, lg)
        return best

    flips = kinds_before = kinds_after = 0
    old_pick, new_pick, flipped_old, flipped_new = [], [], [], []
    for m in matches:
        eo, lo_ = pick(m, 0.0)
        en, ln = pick(m, SHRINK)
        old_pick.append({"sp": lo_["sp"], "win": lo_["win"], "ev": eo})
        new_pick.append({"sp": ln["sp"], "win": ln["win"], "ev": en})
        kinds_before += lo_["kind"] == "1x2"
        kinds_after += ln["kind"] == "1x2"
        if lo_ is not ln:
            flips += 1
            flipped_old.append({"sp": lo_["sp"], "win": lo_["win"]})
            flipped_new.append({"sp": ln["sp"], "win": ln["win"]})

    n = len(matches)
    print(f"\n【翻转率】{flips} / {n} = {flips / n:.1%} 的比赛换了当选腿")
    print(f"  当选腿是 1X2 的比例:  收缩前 {kinds_before / n:.1%} → 收缩后 {kinds_after / n:.1%}"
          f"  (让球腿多拿走 {(kinds_before - kinds_after) / n:.1%} 的场次)")

    # 为什么翻这么多 —— 两类腿的 evLo 本来就几乎打平
    gaps = sorted(
        max(x["lo"] * x["sp"] - 1 for x in m["legs"] if x["kind"] == "1x2")
        - max(x["lo"] * x["sp"] - 1 for x in m["legs"] if x["kind"] == "hc")
        for m in matches
        if any(x["kind"] == "1x2" for x in m["legs"])
        and any(x["kind"] == "hc" for x in m["legs"]))
    def _q(f: float) -> float:
        return gaps[int(f * (len(gaps) - 1))]
    band = sum(1 for g in gaps if abs(g) <= SHRINK * 2.5) / len(gaps)
    print("\n【为什么翻这么多】最优 1X2 腿 − 最优让球腿 的 evLo 差:")
    print(f"  中位 {_q(.5) * 100:+.2f}pp · 四分位 [{_q(.25) * 100:+.2f}, "
          f"{_q(.75) * 100:+.2f}]pp · |差|≤收缩量×典型SP({SHRINK * 2.5 * 100:.1f}pp) "
          f"占 {band:.1%}")
    print("  ⇒ 秤本来就几乎是平的,推一下就大面积翻 —— 不是收缩量大。")

    print("\n【每场 argmax 单腿结算】—— 串关的原子单位")
    for lbl, v in (("收缩前", old_pick), ("收缩后", new_pick)):
        n2, r, se = _roi(v)
        print(f"  {lbl}  N={n2}  ROI {r:>+7.2%}  ±2SE {se * 100:>4.1f}pp")
    print("  ⚠️ 上面两行**不许直接相减** —— 它们是同一批比赛的两种选法,"
          "独立 ±2SE 会把差的误差算得太大。看下面的配对检验。")

    # ⭐ 配对检验:新旧作用在**同一批比赛**上,61.5% 的场次选法完全相同 ⇒
    #    配对差的方差远小于两条独立 ROI 之差。不配对就是浪费掉全部功效。
    def _ret(lg: dict) -> float:
        return lg["sp"] if lg["win"] else 0.0
    diffs = [(m["day"], _ret(pick(m, SHRINK)[1]) - _ret(pick(m, 0.0)[1]))
             for m in matches]
    nz = sum(1 for _, x in diffs if x != 0)
    mean = sum(x for _, x in diffs) / n
    acc: dict[str, float] = collections.defaultdict(float)
    for g, x in diffs:
        acc[g] += x - mean
    G = len(acc)
    se_p = math.sqrt((G / (G - 1)) * sum(v * v for v in acc.values())) / n
    print(f"\n  ★ 配对 ΔROI = {mean * 100:+.2f}pp  ±SE {se_p * 100:.2f}  "
          f"t = {mean / se_p:+.2f}   ({n} 场 / {G} 个比赛日)")
    print(f"     其中 {nz} 场({nz / n:.1%})收益真的不同;其余翻转落在同赢同输的腿上。")

    print("\n【串关层:每日 ∏(1+evLo) 最优组合】")
    byday = collections.defaultdict(list)
    for m in matches:
        byday[m["day"]].append(m)
    for k in (2, 3):
        for lbl, shrink in (("收缩前", 0.0), ("收缩后", SHRINK)):
            tickets = []
            for day_ms in byday.values():
                pool = [pick(m, shrink) for m in day_ms]
                if len(pool) < k:
                    continue
                best = max(itertools.combinations(pool, k),
                           key=lambda cb: math.prod(1 + e for e, _ in cb))
                tickets.append({"sp": math.prod(lg["sp"] for _, lg in best),
                                "win": all(lg["win"] for _, lg in best)})
            n2, r, se = _roi(tickets)
            print(f"  {k} 串 · {lbl}  N={n2}  ROI {r:>+7.2%}  ±2SE {se * 100:>5.1f}pp")

    print("\n" + "=" * 76)
    print("⚠️ 与 δ₁ₓ₂ 测量共享全部偏倚(收盘价 / 2026-01-14 截止 / 仅欧洲联赛)。")
    print("⚠️ 这里的让球 P 用的是**收盘** Pinnacle 反推,实盘用的是更旧的线。")


if __name__ == "__main__":
    main()
