"""nutmeg-vig-split — 竞彩把那 12.9% 的抽水**分到哪条腿上**?常设仪表(只读,永不 gate)。

## 起因(2026-07-28)

算天狼星 vs 哥德堡那场时撞见:竞彩 booksum 1.1287(总抽水 12.9%),但**几乎全压在
主胜一条腿上** —— 竞彩隐含 76.3% vs Pinnacle 公允 63.9%,差 12.4pp;而平局/客胜
只差 0.3pp / 0.1pp,近乎无水。

横扫 262 场后确认这不是个案:

    腿位   Pinnacle公允   竞彩隐含   该腿抽水   占总抽水
    热门      54.2%      61.9%    +7.77pp     60%
    居中      25.6%      28.2%    +2.57pp     20%
    冷门      20.2%      22.8%    +2.59pp     20%

**买热门的成本是买居中/冷门的 3 倍。** ±2SE 仅 0.21–0.35pp,俱乐部(+7.29)与
大赛(+8.43)独立同形。这与 `retail-vote-deeptail-softwater`(反散户=最软腿)是
同一件事的两面 —— 散户买热门,竞彩就在热门上收钱 —— 但**这次是在 1X2 上、用干净的
Pinnacle 锚测的**,不依赖任何让球重构。

## ⚠️ 它**不创造** edge

`EV = P × SP − 1` 已经完整反映了实际 SP,所以抽水重的腿本来就显示为差 EV。
本仪表的作用是**说明结构**:哪条腿在结构上够不着闸,以及**哪个联赛的分配方式不同**
—— 后者才是值得挖的地方。

## 为什么只做 1X2

1X2 的 P 是 Pinnacle 三元组**直接去vig**,没有重构层。让球的 P 要从 1X2+O/U 反推
比分网格(`_hhad_cover_p`),那条路上的「抽水」会**混进我们自己的网格误差** ——
测出来的东西说不清是竞彩定价还是我们建模。故本仪表**只测 1X2**,这是口径洁癖不是偷懒。

## 多重检验

按联赛筛「谁的分配不一样」= 同时检验 10+ 个假设。复用 `clv_gate` 的
cluster-robust t + BHY-FDR(与 CLV 闸门同一套),**不许**看着最极端的联赛下结论。

只读,不写库,不产生下注建议,**永不影响退出码**。
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
from pathlib import Path

from nutmeg.v4.cli.clv_ledger import _devig3
from nutmeg.v4.data.league_labels import canonical_league, is_domestic_club_league
from nutmeg.v4.model.clv_gate import bhy_reject, mean_clv_test

_RANKS = ("热门", "居中", "冷门")
_GATE = 0.05          # 与线上判闸同一个数,仅用于统计「过闸率」,不做任何判断


def load(db_path: str | Path) -> list[dict]:
    """每场 1X2 → 三腿的 (腿位, 该腿抽水, 公允P, 竞彩SP, EV)。"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            "SELECT match_date, league, jc_home, jc_draw, jc_away, "
            "psc_home, psc_draw, psc_away FROM jingcai_sp "
            "WHERE market='had' AND psc_home IS NOT NULL").fetchall()
    out = []
    for r in rows:
        fair = _devig3(r["psc_home"], r["psc_draw"], r["psc_away"])
        sp = (r["jc_home"], r["jc_draw"], r["jc_away"])
        if not fair or any(not x or x <= 1 for x in sp):
            continue
        order = sorted(range(3), key=lambda i: -fair[i])
        rank = {order[0]: "热门", order[1]: "居中", order[2]: "冷门"}
        legs = [{"rank": rank[i], "vig": 1 / sp[i] - fair[i], "fair": fair[i],
                 "sp": sp[i], "ev": fair[i] * sp[i] - 1} for i in range(3)]
        out.append({"date": str(r["match_date"])[:10], "league": canonical_league(r["league"]),
                    "club": is_domestic_club_league(r["league"]),
                    "booksum": sum(1 / x for x in sp), "legs": legs})
    return out


def by_rank(matches: list[dict]) -> list[dict]:
    out = []
    for k in _RANKS:
        v = [lg["vig"] for m in matches for lg in m["legs"] if lg["rank"] == k]
        d = [m["date"] for m in matches for lg in m["legs"] if lg["rank"] == k]
        f = [lg["fair"] for m in matches for lg in m["legs"] if lg["rank"] == k]
        q = [1 / lg["sp"] for m in matches for lg in m["legs"] if lg["rank"] == k]
        ev = [lg["ev"] for m in matches for lg in m["legs"] if lg["rank"] == k]
        if not v:
            continue
        t = mean_clv_test(v, d)
        out.append({"rank": k, "n": len(v), "vig": st.fmean(v), "fair": st.fmean(f),
                    "q": st.fmean(q), "se": (abs(t.mean / t.t) if t.t else float("nan")),
                    "ev_med": st.median(ev),
                    "pass": sum(1 for x in ev if x >= _GATE) / len(ev)})
    return out


#: 会下注的腿位。⚠️ **热门不在内** —— 它承担 60% 的抽水、过闸率仅 0.4%,
#: 我们实际上永远不会买它。按它筛联赛等于在测一个与决策无关的量。
_BETTABLE = ("居中", "冷门")


def by_league(matches: list[dict], *, min_n: int = 20) -> list[dict]:
    """各联赛**会下注的腿**(居中+冷门)的抽水,是否比全局**更便宜**。

    ⚠️ 方向很重要,我第一版设反了:筛「热门更贵」既选错了腿(热门我们不买),
    也选错了方向(贵不是我们要找的)。**抽水越低 ⇒ +EV 的空间越大**,所以单边
    检验的是 `该联赛 − 全局 < 0`。

    ⭐ **实测下来这是个「再分配」而非「折扣」的量**:8 个联赛的 booksum 全部落在
    1.1290–1.1294(总抽水恒 12.9%,方差近乎为零)—— 竞彩的总margin 是个**行政常数**
    (与 `jingcai-market-microstructure`「admin 固定赔率」一致)。变的只有**分配**:
    热门腿占总抽水从 48%(芬超)到 73%(欧罗巴)。所以「可投腿更便宜」= 那个联赛把
    更多抽水压去了热门腿,**不是**竞彩在那里少收钱。表里带 booksum 列就是为了让这条
    不被误读 —— 若哪天 booksum 真的分化了,那是另一回事,得单独看。

    ⚠️ 同时问 10+ 个联赛 = 多重检验。走 BHY-FDR(与 CLV 闸门同一套),
    **不许**挑最极端那个联赛下结论。
    ⚠️ 抽水低 ≠ 软。也可能只是那个市场更有效、竞彩定得更紧
    (见 `jingcai-selection-function-measured`:竞彩系统性只上架厚水场)。
    本节给的是**下一步该挖哪里**,不是「这个联赛能赚钱」。
    """
    def bet_vig(ms):
        return ([lg["vig"] for m in ms for lg in m["legs"] if lg["rank"] in _BETTABLE],
                [m["date"] for m in ms for lg in m["legs"] if lg["rank"] in _BETTABLE])
    glob = st.fmean(bet_vig(matches)[0])
    rows = []
    for lgname in sorted({m["league"] for m in matches}):
        sub = [m for m in matches if m["league"] == lgname]
        v, d = bet_vig(sub)
        if len(v) < min_n:
            continue
        fav = [lg["vig"] for m in sub for lg in m["legs"] if lg["rank"] == "热门"]
        tot = [sum(lg["vig"] for lg in m["legs"]) for m in sub]
        # 单边检验「更便宜」⇒ 取负号喂给 mean_clv_test(它检验 mean > 0)
        t = mean_clv_test([glob - x for x in v], d)
        rows.append({"league": lgname, "n": len(v), "vig": st.fmean(v),
                     "fav": st.fmean(fav) if fav else float("nan"),
                     "booksum": st.fmean(m["booksum"] for m in sub),
                     # 热门腿吃掉总抽水的多少 —— 总抽水恒定时,**这才是真正在变的量**
                     "fav_share": (st.fmean(fav) / st.fmean(tot)) if fav else float("nan"),
                     "dev": st.fmean(v) - glob, "t": t.t, "p": t.p,
                     "clusters": t.n_clusters})
    ps = [r["p"] for r in rows if r["p"] is not None]
    if ps:
        rej = bhy_reject(ps)
        it = iter(rej)
        for r in rows:
            r["fdr"] = next(it) if r["p"] is not None else False
    return sorted(rows, key=lambda r: -r["dev"])


def render(matches: list[dict], *, min_n: int = 20) -> str:
    o = ["# 竞彩抽水分配(只读研究 · 永不 gate)", ""]
    if not matches:
        return "\n".join([*o, "  (无可用 1X2 捕获行)", ""])
    bs = st.median(m["booksum"] for m in matches)
    o += [f"N = **{len(matches)} 场** 1X2 · 竞彩 booksum 中位 {bs:.4f}(总抽水 {bs - 1:.2%})", "",
          "## ① 那 12.9% 分到哪条腿上", "",
          "| 腿位 | N | Pinnacle 公允 | 竞彩隐含 | **该腿抽水** | 占总抽水 | 聚类SE "
          "| EV 中位 | 过 +5% 闸 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    rk = by_rank(matches)
    tot = sum(r["vig"] for r in rk) or 1.0
    for r in rk:
        o.append(f"| {r['rank']} | {r['n']} | {r['fair']:.1%} | {r['q']:.1%} | "
                 f"**{r['vig']:+.2%}** | {r['vig'] / tot:.0%} | {r['se'] * 100:.2f}pp | "
                 f"{r['ev_med']:+.1%} | {r['pass']:.1%} |")
    o += ["", "## ② 分人口", "",
          "| 人口 | N | 热门 | 居中 | 冷门 |", "|---|---:|---:|---:|---:|"]
    for lab, sub in (("俱乐部联赛", [m for m in matches if m["club"]]),
                     ("大赛/杯赛", [m for m in matches if not m["club"]])):
        if len(sub) < 30:
            continue
        cells = {r["rank"]: r["vig"] for r in by_rank(sub)}
        o.append(f"| {lab} | {len(sub)} | " +
                 " | ".join(f"{cells.get(k, float('nan')):+.2%}" for k in _RANKS) + " |")
    lg = sorted(by_league(matches, min_n=min_n), key=lambda r: r["dev"])
    o += ["", f"## ③ 各联赛把这 12.9% **分配**得一样吗?"
          f"(会下注的腿 N≥{min_n},单边检验「更便宜」,BHY-FDR 跨联赛)", "",
          "| 联赛 | N | 簇 | booksum | 可投腿抽水 | 偏离全局 | 热门抽水 | 热门占比 "
          "| t | p | 过FDR |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in lg:
        tp = (f"{r['t']:.2f} | {r['p']:.3f}" if r["t"] is not None else "— | —")
        o.append(f"| {r['league']} | {r['n']} | {r['clusters']} | {r['booksum']:.4f} | "
                 f"{r['vig']:+.2%} | **{r['dev']:+.2%}** | {r['fav']:+.2%} | "
                 f"{r['fav_share']:.0%} | {tp} | "
                 f"{'✅ 更便宜' if r.get('fdr') else '否'} |")
    if not lg:
        o.append(f"| (无联赛达 N≥{min_n}) | | | | | | | | | | |")
    if lg:
        bs_lo, bs_hi = min(r["booksum"] for r in lg), max(r["booksum"] for r in lg)
        sh_lo, sh_hi = min(r["fav_share"] for r in lg), max(r["fav_share"] for r in lg)
        o += ["", f"> ⭐ **booksum 跨联赛 {bs_lo:.4f}–{bs_hi:.4f}(几乎不动),热门占比却是 "
              f"{sh_lo:.0%}–{sh_hi:.0%}。** 竞彩的总 margin 是个**行政常数**,联赛之间",
              "> 差的是**怎么分**,不是**收多少**。所以「可投腿更便宜」= 那个联赛把更多抽水",
              "> 压去了热门腿,**不是**竞彩在那里少收钱。"]
    o += ["", "> ⚠️ **抽水低 ≠ 软。** 也可能只是那个市场更有效、竞彩定得更紧",
          "> (`jingcai-selection-function-measured`:竞彩系统性只上架厚水场)。",
          "> 本节说的是**下一步该挖哪里**,不是「这个联赛能赚钱」。"]
    o += ["", "> ⚠️ **本仪表不创造 edge**:`EV = P×SP−1` 已完整反映实际 SP,抽水重的腿",
          "> 本来就显示为差 EV。它说明的是**结构** —— 哪条腿够不着闸,以及**哪个联赛的",
          "> 分配方式不同**(后者才值得挖)。**永不 gate,不改任何门槛。**",
          "",
          "> ⚠️ 只测 1X2:让球的 P 要从 1X2+O/U 反推比分网格,那条路上的「抽水」会混进",
          "> 我们自己的网格误差,说不清是竞彩定价还是我们建模。", ""]
    return "\n".join(o)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="竞彩抽水分配常设仪表(只读,永不 gate)")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--min-n", type=int, default=20, help="联赛切片的最小腿数")
    ap.add_argument("--out", default="logs/vig_split_latest.md")
    args = ap.parse_args(argv)
    text = render(load(args.db), min_n=args.min_n)
    print(text)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
