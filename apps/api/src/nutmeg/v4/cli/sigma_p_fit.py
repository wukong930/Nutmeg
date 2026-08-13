"""nutmeg-sigma-p-fit — σ_P(h) 分层拟合常设仪表(只读,永不 gate)。

预注册 v2.1(`docs/sigma_p_stratified_prereg_v2.1_2026-07-29.md`)§7
+ **v2.3**(`docs/sigma_p_grouping_axis_prereg_draft_2026-08-13.md`)—— 换分组轴。

## 它存在的理由

v2.1 的整个设计依赖「到了评估点会被发现」,而在本仪表建成之前**没有任何东西在数**
—— 秋季数据攒够了也不会有人知道。预注册写得再严谨,触发条件没人监测就只是一份
意向书,和体检查出的那批「静默降信噪比」的护栏是同一个失效形状。

## 测什么

σ_P(h) = 「我们手上的 Pinnacle 参考线」与「真收盘线」之间的估计误差,按距开球
小时数 h 变化。它是 `EV = P×SP−1` 里那个 P 的不确定度,乘上 SP 就是 σ_EV。

⭐ **2026-07-29 实测:σ_P 依赖人口**(国内联赛 1.26pp·h^0.206 vs 杯赛 0.76pp·h^0.246,
σ@3h 差 1.6×)。杯赛/国际赛是流动性最高的盘,线最锐、动得最少。**所以一条池化曲线
对哪一层都不对** —— 本仪表因此分层报,而不是给一个全局数。

## 口径(逐条对齐 A-1,**不许改**,改了就不可比)

近收盘锚 ≤1.5h(不满足整条轨迹丢弃)· ΔP 相对锚 · basic 归一化(**不是 WPO**)·
每轨每桶只取一条增量 · 桶内稳健 σ=1.4826×MAD · 逐腿(H/D/A)。

⚠️ **2026-08-13 v2.3 改了一处口径:轨迹的分组轴** —— (比赛, source) → (比赛)。
理由与波及面见 `load_trajectories` 的 docstring。**这条改动让本仪表的产出与
2026-07-29 之前的读数不再逐位可比**;`scripts/sigma_p_refit_floor.py` 那份
v2.0 冻结记录按旧轴跑,依然有效但**不可直接与新轴比**。

## ⚠️ 三条纪律

1. **永不 gate**:不判闸、不选注、不进 Kelly、不影响退出码。改 `FREEZE_SIGMA_COEF`
   或 `SIGMA_P` 须 owner 口令 + prereg 修订。
2. **未到评估点不做判定**(prereg §3 防 optional stopping):本仪表按周随体检跑,
   若「哪次看到显著就哪次改」= 反复看必然早晚看到一次。到点前只报进度。
3. **逐联赛表仅诊断**,不挂判据;**禁止**看完它回头改主分层(prereg §2)。

## ⚠️ 不要重构 `scripts/sigma_p_refit_floor.py` 让它 import 本模块

那个脚本是 v2.0 预注册的**执行记录**,必须冻结。让它依赖本模块 ⇒ 本模块日后一改,
那份记录声称跑过的东西就被静默改写了。重复几十行是**有意的**。
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

from nutmeg.v4.data.league_labels import (
    TRAINED_LEAGUES_CN,
    canonical_league,
    is_domestic_club_league,
)

_BUCKETS = ((0.5, 1), (1, 2), (2, 4), (4, 8), (8, 16), (16, 32), (32, 64), (64, 168))
_MIN_BUCKET_N = 20          # prereg §3:合格桶的门槛
_MIN_BUCKETS = 5            # prereg §3:至少 5 个合格桶才到评估点
_ANCHOR_MAX_H = 1.5         # prereg §3:锚必须 ≤1.5h

#: prereg v2.3 §3① —— 同一场若被记了多个 `kickoff_utc`,跨度超过这个值就整条丢弃。
#:
#: 实测(2026-08-13)最大跨度 **1.0h** ⇒ 这是**纯护栏,不是筛子**(今天丢 0 条)。
#: 它防的是上游哪天把某场的时刻写飞,而那种行会静默把整条轨迹的 h 轴平移。
_KO_SPREAD_MAX_H = 3.0

#: prereg v2.3 §3① —— 丢弃计数**必须上仪表**。护栏静默生效 = 我们又造了一个
#: 「零告警所以一定没问题」的假信号(同涓流 END 常量那一族)。
_LOAD_STATS: dict[str, int] = {"ko_spread_dropped": 0}
_LEGS = ("H", "D", "A")
_STRATA = ("国内俱乐部联赛", "杯赛/国际赛")
_DIAG_MIN_N = 60            # 逐联赛诊断表的最小比赛数(仅诊断,不挂判据)

#: prereg §3.1 的评估点门槛 —— **13 训练联赛**的合格轨迹数。
#: ⚠️ 到点评估后若判据未过,prereg §3.2 要求下次门槛**翻倍**;那时 owner 更新
#: prereg 并同步改这个数。它是有意的手动闸,不自动推进 —— 自动推进 = 无人看管的
#: 反复检验。
#:
#: ⭐ v2.3 换轴(比赛,source)→(比赛)后,这个数的**单位从轨迹变成了比赛**,而池化
#: 让 13 联赛的计数 93 → 75(**变少**)。按 1.41 条/场换算「应该」降到 ~213。
#: **⛔ 刻意不降** —— 保持 300 让换轴在数学上**不可能**把评估点提前,把
#: look-then-write 的风险钉死在保守一侧。代价是比理论上必要的严 1.41 倍,认了。
NEXT_EVAL_N = 300

#: prereg v2.3 §3③ —— **13 训练联赛的比赛日数**,与 `NEXT_EVAL_N` 取 **AND**。
#:
#: 🚨 为什么必须新增:2026-08-13 实测,13 训练联赛的 75 场合格比赛全部坐落在
#: **4 个比赛日**上(08-07/08/09/10,一个赛程轮,只覆盖 6/13 个联赛)。
#: 光数轨迹/比赛会在 ~4 周后触发,那时独立簇只有 ~16 个 —— **现行阈值在数一个
#: 几乎无信息的量**。CI 的真驱动是独立簇数,不是单元数。
#:
#: 定值依据(**先验,2026-08-13 在跑新拟合之前写死**):30 是聚类稳健推断的常规
#: 下界(簇数 <30 时 cluster-robust 方差向下偏、t 检验过度拒绝)。⚠️ 这是**惯例,
#: 不是本项目的功效计算** —— 如实标注,别当成算出来的。
#: 欧洲联赛约 3–4 个比赛日/周 ⇒ 30 簇 ≈ 8–10 周,**严格晚于**旧闸的 ~4 周。
NEXT_EVAL_CLUSTERS = 30


def _iso(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001 — 坏时间戳跳过,不该拖垮整个仪表
        return None


def load_trajectories(db_path: str | Path) -> list[dict]:
    """→ [{league, matchday, stratum, trained, points:[(h,pH,pD,pA)] 升序}];已过锚闸。

    ## 分组轴 = **(主队, 客队, 日期)**,不带 source(prereg v2.3,2026-08-13)

    线的走势是**市场的属性,不是观测者的属性**。`source` 只是「哪个 CLI/端点发起了
    这次抓取」,和线怎么动没有关系。实测 **1544/1544 组**里各 source 同一时刻记的
    价格**完全相同** ⇒「不同 source = 不同测量仪器各有噪声」不成立。

    更要命的是它和地基口径对不上:`record_row_snapshot` 的去重键**不带 source**
    (谁先抓到一次线变化谁认领),而分析却按 source 切 ⇒ 每条碎片的锚都被打洞、
    离收盘更远。实测锚中位 h **0.307 → 0.156**(池化后减半),现状因此**系统性
    低估**国内层 σ_P 约 19%。详见 `docs/odds_snapshot_dedup_vs_sigmap_measurement_
    2026-08-13.md` 与 `docs/sigma_p_grouping_axis_prereg_draft_2026-08-13.md`。

    ## 多 `kickoff_utc` 取 **max**(prereg v2.3 §3①)

    同一场可能带多个开球时刻(实测 41/1133 = 3.6%)。**不是 bug,是两个上游的两种
    语义**:Odds API `commence_time` 会在比赛延后时更新成**实际**开球,而
    API-Football `fixture.date` 是**排定**开球、从不更新。实测 41/41 单调后移
    ⇒ 取 max = 取最接近实际开球的那个;**取众数会系统性选中陈旧的排定时刻**。
    """
    _LOAD_STATS["ko_spread_dropped"] = 0        # 重置 —— 否则多次调用会累加
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            "SELECT home_team, away_team, substr(match_date,1,10) d, league, "
            "captured_at, kickoff_utc, psc_home, psc_draw, psc_away FROM odds_snapshots "
            "WHERE psc_home>1 AND psc_draw>1 AND psc_away>1 AND kickoff_utc IS NOT NULL "
            "ORDER BY home_team, away_team, d, captured_at").fetchall()
    raw: dict = defaultdict(list)
    meta: dict = {}
    kos: dict = defaultdict(list)
    for r in rows:
        ca, ko = _iso(r["captured_at"]), _iso(r["kickoff_utc"])
        if not ca or not ko:
            continue
        k = (r["home_team"], r["away_team"], r["d"])
        b = 1 / r["psc_home"] + 1 / r["psc_draw"] + 1 / r["psc_away"]   # basic 归一化
        raw[k].append((ca, (1 / r["psc_home"]) / b, (1 / r["psc_draw"]) / b,
                       (1 / r["psc_away"]) / b))
        kos[k].append(ko)
        meta[k] = r["league"]
    out = []
    for k, obs in raw.items():
        ks = kos[k]
        ko = max(ks)
        # 护栏:跨度过大 ⇒ 上游把时刻写飞了,整条丢弃(不许静默平移整条 h 轴)
        if (ko - min(ks)).total_seconds() / 3600.0 > _KO_SPREAD_MAX_H:
            _LOAD_STATS["ko_spread_dropped"] += 1
            continue
        pts = sorted([((ko - ca).total_seconds() / 3600.0, ph, pd_, pa)
                      for ca, ph, pd_, pa in obs if ca < ko])
        if not pts or pts[0][0] > _ANCHOR_MAX_H:
            continue                                    # 无近收盘锚 → 整条丢弃
        lg = meta[k]
        cn = canonical_league(lg)
        out.append({"league": cn or str(lg), "points": pts,
                    "matchday": k[2],           # 自举的聚类单元(prereg v2.3 §3⑤)
                    "stratum": _STRATA[0] if is_domestic_club_league(lg) else _STRATA[1],
                    # ⚠️ 用 canonical 后的中文比 TRAINED_LEAGUES_CN —— 那张表是中文的
                    "trained": cn in TRAINED_LEAGUES_CN})
    return out


def buckets(trajs: list[dict]) -> dict:
    """→ {leg: {(lo,hi): [(h, Δ)]}};每轨每桶只取一条增量。"""
    acc: dict = {lg: defaultdict(list) for lg in _LEGS}
    for t in trajs:
        anchor = t["points"][0]
        seen = set()
        for h, ph, pd_, pa in t["points"][1:]:
            key = next(((lo, hi) for lo, hi in _BUCKETS if lo <= h < hi), None)
            if key is None or key in seen:
                continue
            seen.add(key)
            for i, lg in enumerate(_LEGS, start=1):
                acc[lg][key].append((h, (ph, pd_, pa)[i - 1] - anchor[i]))
    return acc


def robust_sigma(xs: list[float]) -> float:
    m = st.median(xs)
    return 1.4826 * st.median([abs(x - m) for x in xs])


def bucket_points(acc_leg: dict) -> list[tuple[float, float, int]]:
    return [(st.median([h for h, _ in s]), robust_sigma([d for _, d in s]), len(s))
            for key in _BUCKETS
            if len(s := acc_leg.get(key, [])) >= _MIN_BUCKET_N]


def fit_power(pts: list[tuple[float, float, int]]) -> tuple[float, float]:
    """加权 log-log 拟合 σ = A·h^B(A-1 的做法,保持可比)。"""
    lx = [math.log(h) for h, _, _ in pts]
    ly = [math.log(max(s, 1e-9)) for _, s, _ in pts]
    ws = [float(n) for _, _, n in pts]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, lx, strict=True)) / sw
    my = sum(w * y for w, y in zip(ws, ly, strict=True)) / sw
    den = sum(w * (x - mx) ** 2 for w, x in zip(ws, lx, strict=True))
    if den <= 0:
        return float("nan"), float("nan")
    b = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, lx, ly, strict=True)) / den
    return math.exp(my - b * mx), b


def _clusters(trajs: list[dict]) -> list[list[dict]]:
    """按**比赛日**分簇 —— 自举的重采样单元(prereg v2.3 §3⑤)。"""
    acc: dict = defaultdict(list)
    for t in trajs:
        acc[t.get("matchday") or ""].append(t)
    return list(acc.values())


def _cluster_resample(clusters: list[list[dict]], rng: random.Random) -> list[dict]:
    """整天一起进出。"""
    n = len(clusters)
    return [t for _ in range(n) for t in clusters[rng.randrange(n)]]


def bootstrap_coefs(trajs: list[dict], leg: str, n_boot: int, seed: int):
    """按**比赛日簇**自举(prereg v2.3 §3⑤)。

    v2.1 按**轨迹**自举,理由是「同一场的多个桶相关,按增量自举会高估精度」——
    方向对,但**停早了一层**:2026-08-13 实测,13 训练联赛的 75 场合格比赛全部
    坐落在 **4 个比赛日**上(08-07/08/09/10,一个赛程轮)。把 75 个强相关单元
    当 75 个独立观测,报出的 CI 同样是虚的,只是没那么明显。

    ⚠️ 本改动只会让 CI **变宽**,包括支持换轴的那个 +23.7% —— 它削弱我自己的论据,
    这正是它不构成 look-then-write 后门的证明。
    """
    rng = random.Random(seed)
    cl = _clusters(trajs)
    if not cl:
        return (float("nan"), float("nan")), (float("nan"), float("nan"))
    a_s, b_s = [], []
    for _ in range(n_boot):
        samp = _cluster_resample(cl, rng)
        pts = bucket_points(buckets(samp)[leg])
        if len(pts) < 4:
            continue
        a, b = fit_power(pts)
        if a == a and b == b:            # 非 NaN
            a_s.append(a)
            b_s.append(b)
    a_s.sort()
    b_s.sort()
    q = lambda xs, p: xs[int(p * len(xs))] if xs else float("nan")  # noqa: E731
    return (q(a_s, .025), q(a_s, .975)), (q(b_s, .025), q(b_s, .975))


def _live_coef(leg: str) -> tuple[float, float]:
    """⚠️ **现读** `ev_threshold` —— 不在模块加载时快照。

    `delta_calibration` 踩过这个坑:初版把常数在 import 时求值存进元组,那样将来
    有人改了那边的值,仪表会悄悄停在旧值上,而它的全部职责就是监督那些值。
    """
    from nutmeg.v4.model.ev_threshold import FREEZE_SIGMA_COEF
    return FREEZE_SIGMA_COEF[leg]


def homogeneity_z(trajs: list[dict], leg: str, n_boot: int, seed: int) -> float:
    """prereg §4①:两层的 A 是否真的不同。自举 A 差,z = 均值/标准差。

    ⚠️ 这条**允许**「其实不用分层」这个结果 —— |z|≤2 就退回池化曲线。
    不预设分层一定对。
    """
    rng = random.Random(seed)
    d, c = ([t for t in trajs if t["stratum"] == _STRATA[0]],
            [t for t in trajs if t["stratum"] == _STRATA[1]])
    if len(d) < 40 or len(c) < 40:
        return float("nan")
    cd, cc = _clusters(d), _clusters(c)          # 层内按比赛日分簇(v2.3 §3⑤)
    diffs = []
    for _ in range(n_boot):
        sd = _cluster_resample(cd, rng)
        sc = _cluster_resample(cc, rng)
        pd_, pc = bucket_points(buckets(sd)[leg]), bucket_points(buckets(sc)[leg])
        if len(pd_) < 4 or len(pc) < 4:
            continue
        ad, ac = fit_power(pd_)[0], fit_power(pc)[0]
        if ad == ad and ac == ac:
            diffs.append(ad - ac)
    if len(diffs) < 20:
        return float("nan")
    sd_ = st.pstdev(diffs)
    return st.fmean(diffs) / sd_ if sd_ > 0 else float("nan")


def render(trajs: list[dict], *, n_boot: int, seed: int) -> str:
    o = ["# σ_P(h) 分层拟合(只读研究 · 永不 gate)", ""]
    if len(trajs) < 40:
        return "\n".join([*o, f"  (合格比赛仅 {len(trajs)} 场,样本太小)", ""])

    # ── ① 评估点进度(prereg §3)──────────────────────────────────────────
    tr = [t for t in trajs if t["trained"]]
    tr_buckets = sum(1 for _ in bucket_points(buckets(tr)["H"])) if len(tr) >= 10 else 0
    tr_cl = len(_clusters(tr))
    at_point = (len(tr) >= NEXT_EVAL_N and tr_cl >= NEXT_EVAL_CLUSTERS
                and tr_buckets >= _MIN_BUCKETS)
    dropped = _LOAD_STATS["ko_spread_dropped"]
    o += [f"合格比赛 **{len(trajs)}** 场(近收盘锚 ≤{_ANCHOR_MAX_H}h · "
          f"分组轴 = **(主队,客队,日期)**,prereg v2.3)",
          f"开球时刻跨度 >{_KO_SPREAD_MAX_H}h 而丢弃:**{dropped}** 场"
          + ("" if dropped == 0 else " ⚠️"), "",
          "## ① 评估点进度(prereg §3 · 防 optional stopping)", "",
          f"- **13 训练联赛**比赛 **{len(tr)} / {NEXT_EVAL_N}**"
          f"(还差 {max(NEXT_EVAL_N - len(tr), 0)} 场)",
          f"- **比赛日聚类 {tr_cl} / {NEXT_EVAL_CLUSTERS}**"
          f"(还差 {max(NEXT_EVAL_CLUSTERS - tr_cl, 0)} 天)"
          " ← CI 的真驱动;v2.3 §3③ 新增,与上一条取 **AND**",
          f"- 合格桶 {tr_buckets} / {_MIN_BUCKETS}",
          "- 状态:" + ("🟢 **已到评估点** — 可按 prereg §4 判定" if at_point
                        else "⏳ **未到评估点,本节以下只报不判**"),
          "", "> ⚠️ 到点前**不得**据下表改任何常数。本仪表按周随体检跑,"
          "「哪次看到显著就哪次改」= 反复检验,必然早晚看到一次。",
          "> 📌 CI 按**比赛日簇**自举(v2.3 §3⑤)—— 比按比赛自举更宽,那才是诚实的宽度。",
          ""]

    # ── ② 分层 × 逐腿(prereg §7.1)────────────────────────────────────────
    o += ["## ② 分层拟合 vs 线上值", "",
          "| 人口 | 比赛 | 腿 | A 拟合 | A 95%CI | 线上 A | | B 拟合 | B 95%CI | 线上 B | |",
          "|---|---:|---|---:|---|---:|---|---:|---|---:|---|"]
    for s in _STRATA:
        sub = [t for t in trajs if t["stratum"] == s]
        if len(sub) < 40:
            o.append(f"| {s} | {len(sub)} | — | *样本太小* | | | | | | | |")
            continue
        for leg in _LEGS:
            pts = bucket_points(buckets(sub)[leg])
            if len(pts) < 4:
                o.append(f"| {s} | {len(sub)} | {leg} | *合格桶不足* | | | | | | | |")
                continue
            a, b = fit_power(pts)
            (alo, ahi), (blo, bhi) = bootstrap_coefs(sub, leg, n_boot, seed)
            la, lb = _live_coef(leg)
            ain = "✅内" if alo <= la <= ahi else "❌外"
            bin_ = "✅内" if blo <= lb <= bhi else "❌外"
            o.append(f"| {s} | {len(sub)} | {leg} | {a * 100:.2f}pp | "
                     f"[{alo * 100:.2f}, {ahi * 100:.2f}] | {la * 100:.2f}pp | {ain} | "
                     f"{b:.3f} | [{blo:.3f}, {bhi:.3f}] | {lb:.2f} | {bin_} |")
    o += ["", "> **❌外** = 线上值落在自举区间之外(有证据它在该层上偏了);"
          "**✅内** = 差异还在噪声里,**没证据**,不改。", ""]

    # ── ③ 同源性(prereg §4①)──────────────────────────────────────────────
    z = homogeneity_z(trajs, "H", max(n_boot // 2, 100), seed)
    verdict = ("样本不足" if z != z else
               "❌ 拒绝同源 ⇒ 确认分层" if abs(z) > 2 else "✅ 拒绝不了同源 ⇒ 可退回池化曲线")
    o += ["## ③ 两层同源吗(主胜腿 A 差,自举)", "",
          f"- **z = {z:.2f}** → {verdict}",
          "", "> ⚠️ 这条**允许**「其实不用分层」的结果 —— 不预设分层一定对。"
          f"{'未到评估点,本行只报不判。' if not at_point else ''}", ""]

    # ── ④ 逐联赛诊断(prereg §2:仅诊断,不挂判据)────────────────────────
    o += [f"## ④ 逐联赛诊断(N≥{_DIAG_MIN_N} · **仅诊断,不挂判据**)", "",
          "| 联赛 | 层 | 比赛 | A主 | B主 | σ@3h |", "|---|---|---:|---:|---:|---:|"]
    any_row = False
    for lg in sorted({t["league"] for t in trajs}):
        sub = [t for t in trajs if t["league"] == lg]
        if len(sub) < _DIAG_MIN_N:
            continue
        pts = bucket_points(buckets(sub)["H"])
        if len(pts) < 4:
            continue
        a, b = fit_power(pts)
        any_row = True
        o.append(f"| {lg} | {sub[0]['stratum']} | {len(sub)} | {a * 100:.2f}pp | "
                 f"{b:.3f} | {a * 3.0 ** b:.2%} |")
    if not any_row:
        # 空表要**自解释** —— 光写「无」会被读成「数据有问题」。报出最大联赛的 N,
        # 让读者一眼看出是门槛没到、不是管线坏了。
        top = max(((lg, sum(1 for t in trajs if t["league"] == lg))
                   for lg in {t["league"] for t in trajs}), key=lambda x: x[1],
                  default=("—", 0))
        o.append(f"| (无联赛达 N≥{_DIAG_MIN_N};最大为 {top[0]} {top[1]} 条) | | | | | |")
    o += ["", "> ⚠️ **禁止**看完本表回头改主分层(prereg §2)—— 那正是预注册要防的事后挑选。",
          "", "> ⚠️ 本仪表**不判闸、不选注、不进 Kelly、不产生任何下注建议**。"
          "改 `FREEZE_SIGMA_COEF` / `SIGMA_P` 须 owner 口令 + prereg 修订"
          "(docs/sigma_p_stratified_prereg_v2.1_2026-07-29.md)。", ""]
    return "\n".join(o)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="σ_P(h) 分层拟合常设仪表(只读,永不 gate)")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--boot", type=int, default=200, help="自举次数(体检默认 200)")
    ap.add_argument("--seed", type=int, default=20260729)
    ap.add_argument("--out", default="logs/sigma_p_fit_latest.md")
    args = ap.parse_args(argv)
    text = render(load_trajectories(args.db), n_boot=args.boot, seed=args.seed)
    print(text)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        # ⭐ 同时留一份带日期的历史副本。
        #
        # 只写 `_latest.md`(每次覆盖、零历史)= δ 仪表 2026-08 踩过的坑:prereg
        # 写着「连续两周变差才回滚」,而现有产物**根本判不了「上周是多少」**。
        # 本仪表的 prereg §4 同样有跨期判据(前后半样本外更优),没有历史就是
        # 到了评估点才发现自己手上只有一个点。历史文件按日期命名、同日覆盖。
        # ⚠️ 用 removesuffix 而不是裸 `p.stem` —— 默认文件名是 `..._latest.md`,
        #    直接拼会得到 `sigma_p_fit_latest_history/`(第一版就是这么错的)。
        base = p.stem.removesuffix("_latest")
        hist = p.parent / f"{base}_history" / f"{dt.date.today():%Y-%m-%d}{p.suffix}"
        hist.parent.mkdir(parents=True, exist_ok=True)
        hist.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
