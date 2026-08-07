"""δ₁ₓ₂ —— Pinnacle WPO 去vig 的 1X2 P 在**竞彩会下注人口**上的校准偏差。

口径钉在 `docs/onex_delta_prereg_v1.0_2026-08-08.md`(先于本脚本提交)。
**改这里就是改那份预注册的口径。**

**只读**:不写任何库、不接判闸、不产生下注建议。

为什么即使 δ̂=0 也有产出:下界 = p + δ̂ − k·SE,SE 永不为零。见 prereg §1。

用法:
    python scripts/onex_delta_calibration.py                # 主分析 + 全部次分析
    python scripts/onex_delta_calibration.py --out FILE     # 同时落带日期的报告
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import math
import sqlite3

from nutmeg.utils.team_canonical import (
    CUP_TEAM_ALIASES,
    TEAM_ALIASES,
    normalize_name,
)
from nutmeg.v4.model.devig import devig_1x2

DB = "data/v4_jingcai_history.db"
FD = "data/historical_sources/football_data_co_uk/**/*.csv"
K_SE = 2.0                      # 与 model.market_handicap._C1_SE_K 一致,不另立
OUTCOMES = ("主胜", "平局", "客胜")

# 竞彩侧存 API-Football 全称("Manchester United"),football-data 用缩写
# ("Man United")。别名表是 {规范化全称 → fd 缩写},两边都过一遍即收敛到缩写。
_ALIAS = dict(CUP_TEAM_ALIASES)
for _d in TEAM_ALIASES.values():
    _ALIAS.update(_d)


def key(name: str | None) -> str:
    k = normalize_name(name or "")
    v = _ALIAS.get(k)
    return normalize_name(v) if v else k


def _iso(d: str) -> str | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_fd() -> dict[tuple[str, str, str], tuple]:
    """(主, 客, 日期) → (P_wpo 三元组, 主进球, 客进球)。WPO,**不是** basic。"""
    out: dict[tuple[str, str, str], tuple] = {}
    for f in glob.glob(FD, recursive=True):
        with open(f, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for r in csv.DictReader(fh):
                if not (r.get("PSCH") and r.get("HomeTeam") and r.get("Date")):
                    continue
                iso = _iso(r["Date"])
                if not iso:
                    continue
                try:
                    p = devig_1x2(float(r["PSCH"]), float(r["PSCD"]), float(r["PSCA"]))
                    gh, ga = int(r["FTHG"]), int(r["FTAG"])
                except (TypeError, ValueError, KeyError):
                    continue
                if not p:
                    continue
                out[(key(r["HomeTeam"]), key(r["AwayTeam"]), iso)] = (tuple(p), gh, ga)
    return out


def build(fd: dict) -> tuple[list[dict], dict[str, int]]:
    """竞彩侧驱动。返回每场一条记录 + 各道闸的拒绝计数。"""
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows, rej = [], collections.Counter()
    q = ("SELECT match_id, home_team, away_team, close_date, league_cn, "
         "home_goals, away_goals, single_available FROM jingcai_odds_history "
         "WHERE market='had' AND home_goals IS NOT NULL AND home_team IS NOT NULL "
         "GROUP BY match_id")
    for mid, h, a, d, lg, gh, ga, single in c.execute(q):
        base = dt.date.fromisoformat(d)
        hit = None
        for off in (0, -1, 1):          # 精确日优先,再放宽 ±1(时区/投注日错位)
            hit = fd.get((key(h), key(a), (base + dt.timedelta(days=off)).isoformat()))
            if hit:
                break
        if not hit:
            rej["无 PSC 对应"] += 1
            continue
        p, fgh, fga = hit
        # ── 比分硬闸 —— 两源比分不一致 = 这个 join 是错的,不是数据脏。
        #    δ 那次同源性检验用的同一道闸(当时拒绝率 0.00%)。
        if (fgh, fga) != (gh, ga):
            rej["比分硬闸拒绝"] += 1
            continue
        gd = gh - ga
        rows.append({"day": d, "mid": mid, "league": lg, "p": p,
                     "y": (1 if gd > 0 else 0, 1 if gd == 0 else 0, 1 if gd < 0 else 0),
                     "single": single})
    return rows, rej


def clustered(diffs: list[tuple[str, float]]) -> tuple[float, float, int, int]:
    """按聚类变量求均值与 cluster-robust SE → (δ̂, SE, N, 簇数)。

    Var(δ̂) = (G/(G−1)) · (1/N²) · Σ_g (Σ_{i∈g}(d_i − δ̂))²
    朴素二项 SE 会低估 —— 同日多场共享联赛/轮次冲击。
    """
    n = len(diffs)
    if n < 2:
        return (0.0, 0.0, n, 0)
    mean = sum(d for _, d in diffs) / n
    by: dict[str, float] = collections.defaultdict(float)
    for g, d in diffs:
        by[g] += d - mean
    G = len(by)
    if G < 2:
        return (mean, 0.0, n, G)
    var = (G / (G - 1)) * sum(v * v for v in by.values()) / (n * n)
    return (mean, math.sqrt(var), n, G)


def deltas(rows: list[dict]) -> list[tuple[float, float, int, int]]:
    return [clustered([(r["day"], r["y"][i] - r["p"][i]) for r in rows])
            for i in range(3)]


def fmt(label: str, d: float, se: float, n: int, g: int) -> str:
    t = d / se if se else float("nan")
    lo = d - K_SE * se
    return (f"  {label:<14}δ̂ {d * 100:>+6.2f}pp  ±SE {se * 100:>4.2f}  "
            f"t {t:>+5.2f}   下界修正 {lo * 100:>+6.2f}pp   N={n} · {g} 个比赛日")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()

    L: list[str] = []
    def say(s: str = "") -> None:
        L.append(s)
        print(s)

    fd = load_fd()
    rows, rej = build(fd)
    say("=" * 78)
    say("δ₁ₓ₂ —— Pinnacle WPO 去vig 1X2 P 的校准偏差 · 竞彩已结算人口")
    say("口径:docs/onex_delta_prereg_v1.0_2026-08-08.md")
    say("=" * 78)
    say(f"football-data PSC 索引 {len(fd)} 场 · 入样 {len(rows)} 场 · "
        f"{len({r['day'] for r in rows})} 个竞彩比赛日")
    tot = len(rows) + sum(rej.values())
    for k, v in rej.most_common():
        say(f"  拒绝 · {k}: {v} ({v / tot:.1%})")
    if not rows:
        say("⛔ 入样为空 —— 不报数。")
        return

    say("\n【主分析】守恒:三个 δ̂ 之和恒 = 0(同一批比赛,Σy=ΣP=1)")
    main_d = deltas(rows)
    for o, (d, se, n, g) in zip(OUTCOMES, main_d, strict=True):
        say(fmt(o, d, se, n, g))
    say(f"  守恒校验 Σδ̂ = {sum(d for d, *_ in main_d) * 100:+.4f}pp(应为 0)")

    say("\n【次①·按 P 十分位】δ 若随 P 变 ⇒ 常数形式作废(prereg §6)")
    legs = [(r["day"], r["p"][i], r["y"][i]) for r in rows for i in range(3)]
    legs.sort(key=lambda x: x[1])
    B = 10
    step = len(legs) / B
    say(f"  {'P 区间':<16}{'N':>6}{'δ̂':>9}{'SE':>7}{'t':>7}")
    for b in range(B):
        seg = legs[int(b * step):int((b + 1) * step)]
        d, se, n, _ = clustered([(g, y - p) for g, p, y in seg])
        say(f"  [{seg[0][1]:.3f},{seg[-1][1]:.3f}]{n:>7}{d * 100:>+8.2f}pp"
            f"{se * 100:>7.2f}{(d / se if se else 0):>+7.2f}")

    # 眼睛看十分位看不出「有没有趋势」—— 必须回归。
    n_l = len(legs)
    xb = sum(x for _, x, _ in legs) / n_l
    yb = sum(y - x for _, x, y in legs) / n_l
    sxx = sum((x - xb) ** 2 for _, x, _ in legs)
    beta = sum((x - xb) * ((y - x) - yb) for _, x, y in legs) / sxx
    acc: dict[str, float] = collections.defaultdict(float)
    for g, x, y in legs:
        acc[g] += (x - xb) * ((y - x) - yb - beta * (x - xb))
    G = len(acc)
    se_b = math.sqrt((G / (G - 1)) * sum(v * v for v in acc.values())) / sxx
    say(f"  形式检验(d 对 P 回归,按比赛日聚类): β = {beta:+.4f} ±{se_b:.4f} "
        f"t = {beta / se_b:+.2f}")
    say(f"    β>0 = WPO 之后仍低估热门/高估冷门。跨 P 全域端到端 "
        f"{beta * 0.84 * 100:+.2f}pp。|t|<2 ⇒ 常数形式存活(prereg §6)")

    say("\n【次②·半分稳定性】按日期中位切两半")
    mid = sorted({r["day"] for r in rows})[len({r["day"] for r in rows}) // 2]
    for lbl, sub in (("前半 <" + mid, [r for r in rows if r["day"] < mid]),
                     ("后半 ≥" + mid, [r for r in rows if r["day"] >= mid])):
        say(f"  {lbl}")
        for o, (d, se, n, g) in zip(OUTCOMES, deltas(sub), strict=True):
            say(fmt("  " + o, d, se, n, g))

    say("\n【次③·逐联赛异质性】")
    by_lg = collections.defaultdict(list)
    for r in rows:
        by_lg[r["league"]].append(r)
    say(f"  {'联赛':<10}{'N':>6}   主胜 δ̂        平局 δ̂        客胜 δ̂")
    for lg, sub in sorted(by_lg.items(), key=lambda x: -len(x[1])):
        if len(sub) < 100:
            continue
        ds = deltas(sub)
        cells = "  ".join(f"{d * 100:>+6.2f}±{se * 100:<4.2f}" for d, se, _, _ in ds)
        say(f"  {lg:<10}{len(sub):>6}   {cells}")

    # 逐联赛「看着有大有小」不构成异质 —— 必须算 Q。
    subs = {k: v for k, v in by_lg.items() if len(v) >= 100}
    say("  形式检验 Cochran's Q(同质 ⇒ 常数形式合法):")
    for i, o in enumerate(OUTCOMES):
        est = [(d, s) for d, s, _, _ in
               (clustered([(r["day"], r["y"][i] - r["p"][i]) for r in v])
                for v in subs.values()) if s > 0]
        w = [1 / (s * s) for _, s in est]
        mu = sum(wi * d for wi, (d, _) in zip(w, est, strict=True)) / sum(w)
        Q = sum(wi * (d - mu) ** 2 for wi, (d, _) in zip(w, est, strict=True))
        df = len(est) - 1
        z = ((Q / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
        p_val = 0.5 * math.erfc(z / math.sqrt(2))
        i2 = max(0.0, (Q - df) / Q) * 100 if Q > 0 else 0.0
        say(f"    {o}  Q={Q:5.2f} df={df} p≈{p_val:.3f} I²={i2:4.1f}%  "
            f"{'⚠️ 异质,常数形式作废' if p_val < 0.10 else '✅ 拒绝不了同质'}")

    say("\n【次④·可单关子集】(实际最常下的那一半)")
    for o, (d, se, n, g) in zip(OUTCOMES, deltas([r for r in rows if r["single"]]), strict=True):
        say(fmt(o, d, se, n, g))

    say("\n【下界:两种口径】prereg §6 —— δ̂ 不显著时点估不动,只收下界")
    for o, (d, se, _, _) in zip(OUTCOMES, main_d, strict=True):
        say(f"  {o}  含点估 lo = p {(d - K_SE * se) * 100:+.2f}pp   |   "
            f"点估收缩到 0  lo = p {-K_SE * se * 100:+.2f}pp")
    say("  ⭐ 推荐后者:δ̂ 不显著时把它带进下界,会让**正的噪声**去放松判闸")
    say("     (客胜 δ̂=+0.47 就会把下界从 −1.11 松到 −0.64)。与「+2 线不出点估」同一立场。")

    say("\n【空包弹】null 结果和脚本坏掉长得一模一样 ⇒ 必须先证明它能红")
    for inj in (0.02, -0.03):
        poisoned = [{**r, "p": (r["p"][0] + inj, r["p"][1], r["p"][2] - inj)}
                    for r in rows]
        got = deltas(poisoned)[0][0] - main_d[0][0]
        say(f"  注入主胜 {inj * 100:+.1f}pp → δ̂_主 变 {got * 100:+.3f}pp  "
            f"{'✅' if abs(got + inj) < 1e-9 else '❌ 估计量坏了,以上全部作废'}")
    for i, o in enumerate(OUTCOMES):
        _, se, n, _ = clustered([(r["day"], r["y"][i] - r["p"][i]) for r in rows])
        dd = [r["y"][i] - r["p"][i] for r in rows]
        m = sum(dd) / n
        naive = math.sqrt(sum((x - m) ** 2 for x in dd) / (n * (n - 1)))
        say(f"  {o} 聚类 SE {se * 100:.3f} vs 朴素 {naive * 100:.3f}(比值 "
            f"{se / naive:.3f})  {'✅' if se >= naive * 0.999 else '❌ 聚类实现有问题'}")

    say("\n" + "=" * 78)
    say("⚠️ 本测量的三条已知偏倚(prereg §5),读数时必须带着:")
    say("  1. PSC 是**收盘**价 —— 比我们下注时看到的线更准 ⇒ δ̂ 可能偏小、SE 偏窄。")
    say("     陈旧度由 freeze-gap 单独定价,两项不许合并。")
    say("  2. football-data 的 Pinnacle 死于 2026-01-14 ⇒ 之后的竞彩场次全部不在样本内。")
    say("  3. 适用范围**仅限 13 个欧洲训练联赛**。日职/杯赛/北欧/韩职/美职")
    say("     整个联赛 0 覆盖,不许外推(prereg §3)。")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
