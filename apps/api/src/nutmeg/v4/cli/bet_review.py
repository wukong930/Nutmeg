"""nutmeg-bet-review — 手工投注记录的复盘。

## 它的头条不是「你赚了多少」

在几十注的量级上,**已实现盈亏几乎全是方差**。实测形状(一份 ~60 注、12 天的记录):
净盈亏落在自举 CI 的**中间偏一点**,而那个 CI 宽达 ±40% —— 这个数的信息量约等于零。
(单注 ROI 标准差实测 ≈1.45 ⇒ 要在 95%/80% 下检出 +5% 的边需要 N≈6,600 注,
按 5 注/天 约 3.6 年。**靠结果判断自己有没有边,这条路走不通。**)

⭐ 所以本工具的头条是 **期望 vs 实得**:

    期望净盈亏   = Σ(注额 × EV)   按下注时的真实赔率 × 生产口径公允概率
    实得净盈亏   = Σ(回收 − 投入)
    差额         = 实得 − 期望     ← 这一项就是运气

**期望**在几十注上就有信息(它不含结果的方差),**实得**没有。同一份数据,
一个数能读、一个不能 —— 把两个并排印出来,是这个工具存在的唯一理由。

## 输入

一张表(`.xlsx` 或 `.csv`),表头需要:

    日期 · 联赛 · 赛事 · 投注 · 结果          （必需）
    金额 · 赔率                              （可选,但强烈建议)

- `日期` 只在每组第一行写也行(向下填充);它是**投注日**,和比赛日差一天很正常。
- `赛事` 形如 `主队-客队`(中文)。
- `投注` ∈ {主胜, 平, 客胜, 主让胜/让胜, 主让平/让平, 主让负/让负}。
- `结果` ∈ {对, 错}。
- ⭐ 有 `赔率` 就用你的,没有就从库里反推;两者都有时**并排比对**
  (差异 = 你下注时的价和我们捕获时的价之间的漂移)。

## 🚨 四条设计纪律

1. **口径同源**:去vig、让球网格、两套判闸下界,全部 import 生产模块。
   本文件里没有任何概率算法的实现。让球走 `c1=True` + 传 league(**服务口径**,
   不是 eval 口径 —— 默认参数编码了给哪条路径用)。
2. **模糊连表逐条打印**给人眼核对。「长得像」是零证据;一个错误的连表会静默
   给出错误的 SP,而下游每个数都跟着错。
3. **子切片低于 `_MIN_SLICE` 不给结论**。实测那份记录里「主让胜 +55%」建在 7 注上、
   相邻 SP 档一个 +47.6% 一个 −39.2% —— 相邻档符号相反且量级相同,是噪声的指纹。
4. **记录 vs 库里赛果逐条对账**,不一致的**列出来让人判**,不替人选一边。
   实测过一份记录:可核对的行里约 8% 与库里不一致,两个方向都有
   (有记录写输而库里说赢的)。⇒ 不一致**不等于**记录错,也可能是库里结算错。
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import difflib
import json
import random
import re
import statistics as st
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

#: 子切片低于这个注数不给 ROI 结论(只报计数)。
#: ⚠️ 单注 ROI 标准差实测 1.45 ⇒ N=20 时 ROI 的 SE 仍有 32pp。20 不是「够了」,
#: 是「低于它连形状都别看」。
_MIN_SLICE = 20

#: 模糊连表的下限(两侧相似度之和,满分 2.0)。低于它宁可不连。
_FUZZY_MIN = 1.55

#: 投注标签 → (市场, 腿索引)。⚠️ 认不出的标签**报错不静默丢**。
_BET_LEG = {
    "主胜": ("had", 0), "平": ("had", 1), "和": ("had", 1), "客胜": ("had", 2),
    "主让胜": ("hhad", 0), "让胜": ("hhad", 0),
    "主让平": ("hhad", 1), "让平": ("hhad", 1),
    "主让负": ("hhad", 2), "让负": ("hhad", 2),
}
_LEG_NAME = {("had", 0): "主胜", ("had", 1): "平局", ("had", 2): "客胜",
             ("hhad", 0): "让胜", ("hhad", 1): "让平", ("hhad", 2): "让负"}


# ── 读表 ──────────────────────────────────────────────────────────────────
def _read_xlsx(path: Path) -> list[dict]:
    """最小 xlsx 读取(zip + XML)。⛔ 不引 openpyxl —— 复盘工具不该给生产环境加依赖。"""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    z = zipfile.ZipFile(path)
    shared = ["".join(t.text or "" for t in si.iter("{%s}t" % ns["m"]))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)] \
        if "xl/sharedStrings.xml" in z.namelist() else []

    def col(ref: str) -> int:
        n = 0
        for ch in re.match(r"([A-Z]+)", ref).group(1):
            n = n * 26 + ord(ch) - 64
        return n - 1

    grid: dict[int, dict[int, object]] = {}
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter("{%s}row" % ns["m"]):
        cells: dict[int, object] = {}
        for cnode in row.findall("m:c", ns):
            v = cnode.find("m:v", ns)
            if v is None:
                val = None
            elif cnode.get("t") == "s":
                val = shared[int(v.text)]
            else:
                val = v.text
                try:
                    val = float(val) if "." in str(val) else int(val)
                except (TypeError, ValueError):
                    pass
            cells[col(cnode.get("r"))] = val
        grid[int(row.get("r"))] = cells
    if not grid:
        return []
    hdr = {i: str(v).strip() for i, v in grid[min(grid)].items() if v is not None}
    return [{hdr[i]: c.get(i) for i in hdr} for r, c in sorted(grid.items()) if r != min(grid)]


def _read(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    return _read_xlsx(path)


_EXCEL_EPOCH = dt.date(1899, 12, 30)


def _as_date(v: object) -> dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):          # Excel 序列号
        return _EXCEL_EPOCH + dt.timedelta(days=int(v))
    s = str(v).strip()[:10].replace("/", "-")
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _parse(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """→ (记录, 抱怨)。⚠️ 日期向下填充(表里常只在每组首行写)。"""
    recs, gripes, cur = [], [], None
    for i, r in enumerate(rows, start=2):
        g = {k.strip(): v for k, v in r.items() if k}
        d = _as_date(g.get("日期"))
        if d:
            cur = d
        m = str(g.get("赛事") or "").strip()
        if not m:
            continue
        bet = str(g.get("投注") or "").strip()
        if bet not in _BET_LEG:
            gripes.append(f"r{i}: 投注标签认不出 {bet!r}（{m}）")
            continue
        if "-" not in m:
            gripes.append(f"r{i}: 赛事缺分隔符 {m!r} —— 连不上库")
            continue
        res = str(g.get("结果") or "").strip()
        if res not in ("对", "错"):
            gripes.append(f"r{i}: 结果认不出 {res!r}（{m}）")
            continue
        h, a = (x.strip() for x in m.split("-", 1))
        recs.append({"row": i, "date": cur, "league": str(g.get("联赛") or "").strip(),
                     "match": m, "home_zh": h, "away_zh": a, "bet": bet,
                     "market": _BET_LEG[bet][0], "leg": _BET_LEG[bet][1], "res": res,
                     "stake_col": _num(g.get("金额")), "odds_col": _num(g.get("赔率"))})
    return recs, gripes


def _num(v):
    try:
        return float(str(v).strip()) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ── 连表 ──────────────────────────────────────────────────────────────────
def _index(db: str, lo: str, hi: str):
    import sqlite3
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    vote: dict = collections.defaultdict(dict)
    zh2en: dict[str, str] = {}
    for md, h, a, he, ae, jh, jd, ja, hc, ft in c.execute(
            "SELECT match_date,home_zh,away_zh,home_team,away_team,jc_home,jc_draw,jc_away,"
            "handicap_home,ft_outcome FROM jingcai_vote WHERE match_date BETWEEN ? AND ?", (lo, hi)):
        vote[(md, h, a)]["hhad" if hc is not None else "had"] = {
            "sp": (jh, jd, ja), "line": hc, "ft": ft, "hco": None}
        if h and he:
            zh2en[h] = he
        if a and ae:
            zh2en[a] = ae
    sp: dict = collections.defaultdict(dict)
    anchor: dict = {}
    for md, mk, h, a, jh, jd, ja, hc, ft, hco, ph, pd, pa, ou, po, pu in c.execute(
            "SELECT match_date,market,home_team,away_team,jc_home,jc_draw,jc_away,handicap_home,"
            "ft_outcome,hc_outcome,psc_home,psc_draw,psc_away,ou_line,psc_over,psc_under "
            "FROM jingcai_sp WHERE match_date BETWEEN ? AND ?", (lo, hi)):
        sp[(md, h, a)][mk] = {"sp": (jh, jd, ja), "line": hc, "ft": ft, "hco": hco}
        if ph:
            anchor[(md, h, a)] = (ph, pd, pa, po, pu, ou)
    c.close()
    return vote, sp, zh2en, anchor


def _join(recs, vote, sp, zh2en, fuzzy_min: float):
    """中文对中文优先(零词典依赖),失败再走 zh→en + `jingcai_sp`。±1 天兜底。

    ⚠️ 你的日期是**投注日**,库里是比赛日 —— 差一天很正常,所以 ±1 天是常态不是异常。
    """
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    vkeys = list(vote)
    fuzzy_log, how = [], collections.Counter()
    for r in recs:
        d0 = r["date"].isoformat() if r["date"] else ""
        r["src"] = r["key"] = None
        for off in (0, 1, -1):
            d = (r["date"] + dt.timedelta(days=off)).isoformat() if r["date"] else ""
            if (d, r["home_zh"], r["away_zh"]) in vote:
                r["src"], r["key"] = "vote", (d, r["home_zh"], r["away_zh"])
                how[f"中文精确(±{off}天)" if off else "中文精确"] += 1
                break
        if r["key"]:
            continue
        # 中文模糊(同日或 ±1 天)
        best, bs = None, 0.0
        for k in vkeys:
            if abs((dt.date.fromisoformat(k[0]) - r["date"]).days) > 1:
                continue
            s = (difflib.SequenceMatcher(None, r["home_zh"], k[1]).ratio()
                 + difflib.SequenceMatcher(None, r["away_zh"], k[2]).ratio())
            if s > bs:
                bs, best = s, k
        if best and bs >= fuzzy_min:
            r["src"], r["key"] = "vote", best
            how["中文模糊"] += 1
            fuzzy_log.append((bs, r["match"], f"{best[1]}-{best[2]}", best[0]))
            continue
        # 退到英文侧
        eh = zh2en.get(r["home_zh"]) or zh_to_canonical(r["home_zh"])
        ea = zh2en.get(r["away_zh"]) or zh_to_canonical(r["away_zh"])
        if eh and ea:
            for off in (0, 1, -1):
                d = (r["date"] + dt.timedelta(days=off)).isoformat()
                if (d, eh, ea) in sp:
                    r["src"], r["key"] = "sp", (d, eh, ea)
                    how["英文侧"] += 1
                    break
        if not r["key"]:
            how["未连上"] += 1
    return how, sorted(fuzzy_log)


def _price(recs, vote, sp, anchor, zh2en):
    """挂 SP + 生产口径 EV/evLo。⛔ 概率一律 import 生产模块,本文件不算。"""
    from nutmeg.v4.model.devig import devig_1x2
    from nutmeg.v4.model.market_handicap import (c1_leg_lower_bounds, delta_scope,
                                                 devig_over, implied_handicap_lines)
    from nutmeg.v4.model.onex_calibration import onex_leg_lower_bounds
    v2e = {}
    for (md, h, a) in vote:
        eh, ea = zh2en.get(h), zh2en.get(a)
        if eh and ea:
            v2e[(md, h, a)] = (md, eh, ea)
    lost = collections.Counter()
    for r in recs:
        r["sp"] = r["ev"] = r["evlo"] = r["P"] = None
        if not r["key"]:
            continue
        book = (vote if r["src"] == "vote" else sp).get(r["key"], {}).get(r["market"])
        if not book:
            lost[f"连上了但没有{'胜平负' if r['market']=='had' else '让球'}那张盘"] += 1
            continue
        r["line"], r["ft"], r["hco"] = book.get("line"), book.get("ft"), book.get("hco")
        r["sp_db"] = book["sp"][r["leg"]]
        # ⭐ 你自己记的赔率优先(那才是你真拿到的价);没有才用库里的
        r["sp"] = r["odds_col"] or r["sp_db"]
        if not r["sp"]:
            lost["那条腿没有 SP"] += 1
            continue
        ekey = r["key"] if r["src"] == "sp" else v2e.get(r["key"])
        A = anchor.get(ekey) if ekey else None
        if not A:
            lost["缺 Pinnacle 锚"] += 1
            continue
        fair = devig_1x2(A[0], A[1], A[2])
        if not fair:
            lost["Pinnacle 去vig 失败"] += 1
            continue
        if r["market"] == "had":
            P, LO = fair[r["leg"]], onex_leg_lower_bounds(*fair)[r["leg"]]
            r["scope"] = "1X2"
        else:
            if r["line"] is None:
                lost["让球线缺失"] += 1
                continue
            po = devig_over(A[3], A[4]) if (A[3] and A[4]) else None
            try:                       # ⚠️ c1=True + league = **服务口径**(不是 eval)
                L = implied_handicap_lines(*fair, po, ou_line=A[5] or 2.5,
                                           lines=(int(r["line"]),), c1=True, league=r["league"])
            except Exception:          # noqa: BLE001 — 网格拟合失败丢这一注,留痕
                lost["让球网格拟合失败"] += 1
                continue
            if not L:
                lost["让球网格无解"] += 1
                continue
            _, ph, pdw, pa = L[0]
            P = (ph, pdw, pa)[r["leg"]]
            LO = c1_leg_lower_bounds(int(r["line"]), ph, pdw, pa,
                                     league=r["league"])[r["leg"]]
            r["scope"] = delta_scope(r["league"])
        r["P"], r["ev"], r["evlo"] = P, P * r["sp"] - 1, min(LO, P) * r["sp"] - 1
    return lost


# ── 报告 ──────────────────────────────────────────────────────────────────
def _roi(sub, stake_of):
    s = sum(stake_of(r) for r in sub)
    b = sum(stake_of(r) * r["sp"] for r in sub if r["res"] == "对")
    return s, b, b - s, (b / s - 1 if s else 0.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="手工投注记录复盘(期望 vs 实得)")
    ap.add_argument("sheet", help="投注记录 .xlsx / .csv")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--flat", type=float, default=100.0, help="没有金额列时的均注(默认 100)")
    ap.add_argument("--exclude", action="append", default=[], help="按赛事名剔除(可多次)")
    ap.add_argument("--fuzzy-min", type=float, default=_FUZZY_MIN)
    ap.add_argument("--detail", action="store_true", help="逐注明细")
    a = ap.parse_args(argv)

    rows = _read(Path(a.sheet))
    recs, gripes = _parse(rows)
    if a.exclude:
        recs = [r for r in recs if r["match"] not in set(a.exclude)]
    if not recs:
        print("没有可用记录。"); return 1
    lo = min(r["date"] for r in recs) - dt.timedelta(days=2)
    hi = max(r["date"] for r in recs) + dt.timedelta(days=2)
    vote, sp, zh2en, anchor = _index(a.db, lo.isoformat(), hi.isoformat())
    how, fuzzy = _join(recs, vote, sp, zh2en, a.fuzzy_min)
    lost = _price(recs, vote, sp, anchor, zh2en)

    stake_of = (lambda r: r["stake_col"] or a.flat)
    priced = [r for r in recs if r["sp"]]
    evable = [r for r in recs if r["ev"] is not None]

    print("=" * 72)
    print(f"投注复盘  {min(r['date'] for r in recs)} → {max(r['date'] for r in recs)}"
          f"   {len(recs)} 注 / {len({r['date'] for r in recs})} 天")
    print("=" * 72)
    if gripes:
        print("\n⚠️ 表里读不了的行(**没被算进任何数字**):")
        for g in gripes:
            print(f"   {g}")

    print("\n【连表】")
    for k, v in how.most_common():
        print(f"   {k:16s} {v:3d}")
    for k, v in lost.most_common():
        print(f"   ⚠️ {k:14s} {v:3d}")
    print(f"   ⇒ 能算 SP {len(priced)}/{len(recs)} · 能算生产 EV {len(evable)}/{len(recs)}")
    if fuzzy:
        print("\n   模糊连表(⚠️ **请人眼核对** ——「长得像」是零证据):")
        for s, mine, theirs, d in fuzzy:
            print(f"      {s:.2f}  你写「{mine}」 → 库「{theirs}」 {d}")

    # 记录 vs 库里赛果
    dis = []
    for r in priced:
        t = r.get("ft") if r["market"] == "had" else r.get("hco")
        if t is None:
            continue
        if (r["leg"] == t) != (r["res"] == "对"):
            dis.append((r, t))
    ck = sum(1 for r in priced
             if (r.get("ft") if r["market"] == "had" else r.get("hco")) is not None)
    print(f"\n【对账】可核对 {ck} 注,不一致 {len(dis)}"
          + (f" = {len(dis)/ck*100:.1f}%" if ck else ""))
    for r, t in dis:
        print(f"   🚨 r{r['row']} {r['date']} [{r['league']}] {r['match']}"
              f" 投「{r['bet']}」记「{r['res']}」,库里赛果 = {_LEG_NAME[(r['market'], t)]}")
    if dis:
        print("   ⇒ 这些**没替你判**谁对。下面的实得盈亏按你记的算。")

    # 你记的赔率 vs 库里的
    both = [r for r in priced if r["odds_col"] and r.get("sp_db")]
    if both:
        d = [abs(r["odds_col"] - r["sp_db"]) for r in both]
        print(f"\n【赔率对照】{len(both)} 注两边都有:中位差 {st.median(d):.3f}"
              f" · 最大 {max(d):.2f}   (差=你下注时的价 vs 我们捕获时的价)")

    # ⭐ 头条
    s, b, net, roi = _roi(priced, stake_of)
    print(f"\n{'=' * 72}\n【实得】{len(priced)} 注"
          + ("(均注 %.0f)" % a.flat if not any(r["stake_col"] for r in priced) else "(用金额列)"))
    won = [r for r in priced if r["res"] == "对"]
    print(f"   投入 {s:>10,.0f}   回收 {b:>10,.0f}   净 {net:>+9,.0f}"
          f"   ROI {roi * 100:+.2f}%   命中 {len(won)}/{len(priced)}"
          f" = {len(won) / len(priced) * 100:.1f}%")
    rng = random.Random(20260903)
    boot = sorted(_roi([rng.choice(priced) for _ in priced], stake_of)[3] for _ in range(20000))
    q = (boot[500], boot[19500])
    print(f"   95% 自举 CI  [{q[0]*100:+.1f}%, {q[1]*100:+.1f}%]"
          f"  = [{q[0]*s:+,.0f}, {q[1]*s:+,.0f}]")
    print("   ⚠️ CI 有多宽,这个 ROI 的信息量就有多小。")

    if evable:
        es, eb, enet, eroi = _roi(evable, stake_of)
        exp = sum(stake_of(r) * r["ev"] for r in evable)
        print(f"\n⭐【期望 vs 实得】(能算 EV 的 {len(evable)} 注 —— **本报告唯一有信息的数**)")
        print(f"   期望净盈亏 {exp:>+9,.0f}   (EV 均值 {st.mean([r['ev'] for r in evable])*100:+.1f}%)")
        print(f"   实得净盈亏 {enet:>+9,.0f}")
        print(f"   差额       {enet - exp:>+9,.0f}   ← 运气那一部分")
        pt = sum(1 for r in evable if r["ev"] >= 0.05)
        gt = sum(1 for r in evable if r["evlo"] >= 0.05)
        print(f"\n   过 +5% 闸:点估 {pt}/{len(evable)} · **evLo(生产真正用的)"
              f" {gt}/{len(evable)}**")
        if gt == 0:
            print("   ⇒ 这些注**没有一注**是系统会让你下的。")

    # 切片:低于门槛只报计数
    print(f"\n【切片】⛔ N < {_MIN_SLICE} 的只报计数不报 ROI —— 相邻档符号相反是噪声的指纹")
    for title, keyf in (("玩法", lambda r: "胜平负" if r["market"] == "had" else "让球"),
                        ("腿型", lambda r: r["bet"]),
                        ("SP 档", lambda r: ("<2.0" if r["sp"] < 2 else "2.0–3.0"
                                             if r["sp"] < 3 else "3.0–4.5"
                                             if r["sp"] < 4.5 else "≥4.5"))):
        print(f"  按{title}:")
        for k, grp in sorted(collections.Counter(keyf(r) for r in priced).items(),
                             key=lambda x: -x[1]):
            sub = [r for r in priced if keyf(r) == k]
            ss, bb, nn, rr = _roi(sub, stake_of)
            w = sum(1 for r in sub if r["res"] == "对")
            tail = (f"净 {nn:+8,.0f}  ROI {rr*100:+7.1f}%" if len(sub) >= _MIN_SLICE
                    else f"净 {nn:+8,.0f}  ⛔ N 太小不给 ROI")
            print(f"    {k:8s} {len(sub):3d} 注  中 {w:3d}   {tail}")

    if a.detail:
        print(f"\n【逐注】")
        for r in sorted(recs, key=lambda x: (x["date"], x["match"])):
            ev = f"{r['ev']*100:+6.1f}%" if r["ev"] is not None else "   n/a"
            lo_ = f"{r['evlo']*100:+6.1f}%" if r["evlo"] is not None else "   n/a"
            spx = f"{r['sp']:5.2f}" if r["sp"] else "  -- "
            print(f"   {r['date']} [{r['league'][:6]:6s}] {r['match'][:24]:24s}"
                  f" {r['bet']:4s} SP{spx} EV{ev} evLo{lo_} {r['res']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
