"""nutmeg-clv-ledger — settlement-INDEPENDENT soft-water (CLV) ledger.

The staleness map (``jingcai_staleness``) waits for the RESULT to show realized
ROI — so it only sees the handful of settled matches. But **CLV (竞彩 SP vs
Pinnacle's CLOSE) needs no result**: the close is known at kickoff. This ledger
pairs every captured 竞彩 SP with Pinnacle's closing line, computes per-leg
``CLV = P(close de-vig) × 竞彩SP − 1`` over the WHOLE distribution, and breaks it
down by tier × leg-rank × market — so it accrues ~6× faster than the settled
map (every offered match is a data point, not every settled one).

The headline the validation timeline turns on: the mean CLV of the **selected**
leg (the EV≥5% pick our filter makes AT CAPTURE), sliced **per league** and run
through the upgraded gate — a cluster-robust t-test + BHY-FDR across the league
family + a warn/confirm split (``nutmeg.v4.model.clv_gate``), NOT the old
``N≥15/38`` counter (a count is not a significance test, and screening 13 leagues
for the softest is multiple testing). Selection is on capture-time EV (no
look-ahead); CLV is measured vs the close — so a positive selected-CLV is a real
signal, not a circular artifact. No ``ft_outcome`` is touched.

honest scope: 让球 (hhad) legs are in the distribution (close-side reverse-fit,
no result needed) but the SELECTED counter is 1X2-only for now — hhad selection
needs the capture-time O/U, which ``jingcai_sp`` does not yet store.

Name-join tripwire: a join MISS is split into name-suspect (Pinnacle has the
fixture same-day under a different spelling → an alias gap that silently drops
soft-water rows) vs genuine no-quote, so an autumn team-name break self-announces
in the report instead of hiding inside one ``no_close`` count. Fixing the alias
table itself stays autumn-gated — it must be built against the MEASURED 竞彩-source
spellings, not guessed ones (see [[cross-source-team-name-mismatch]]).
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from pathlib import Path

from nutmeg.v4.cli.jingcai_staleness import _devig3, _pinn_close
from nutmeg.v4.data.league_labels import canonical_league
from nutmeg.v4.model.clv_gate import (
    CONFIRM_MIN_N,
    CONFIRM_T,
    WARN_MIN_N,
    evaluate,
    pooled_test,
)

_MIN_EV = 0.05
_HAD = ("主胜", "平局", "客胜")
_HC = ("让胜", "让平", "让负")


def _tier(p: float) -> str:
    """EV reliability tier by P (cuts 0.15/0.25/0.67/0.77 — ev_tier_calibration). The
    old 0.20 '高估区/overpriced' cut was RETIRED 2026-06-26 (an n=323 phantom; −0.21pp
    on a 28k WPO recheck) → [0.15,0.25) folds into 边缘/edge."""
    if p < 0.15:
        return "cold (P<15%)"
    if p < 0.25:
        return "边缘 (15–25%)"
    if p <= 0.67:
        return "甜区 (25–67%)"
    if p <= 0.77:
        return "边缘 (67–77%)"
    return "chalk (>77%)"


def _hhad_cover_p(close: tuple, line) -> tuple | None:
    """(让胜,让平,让负) cover P at the 竞彩 handicap line from Pinnacle's CLOSE
    1X2 + O/U — settlement-free (no goals needed)."""
    if line is None:
        return None
    fair = _devig3(close[0], close[1], close[2])
    if fair is None:
        return None
    from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
    p_over = devig_over(close[3], close[4]) if (close[3] and close[4]) else None
    ou_line = close[5] if close[5] is not None else 2.5
    try:
        lines = implied_handicap_lines(
            fair[0], fair[1], fair[2], p_over, ou_line=ou_line, lines=(int(line),))
    except Exception:  # noqa: BLE001 — a fit failure just drops this row
        return None
    if not lines:
        return None
    _, ph, pd_, pa = lines[0]
    return (ph, pd_, pa)


def _norm(s: str | None) -> str:
    """Accent-fold + casefold for loose team-name comparison (Türkiye≈Turkey)."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").casefold().strip()


def _same_day_name_overlap(conn: sqlite3.Connection, d: dict) -> bool:
    """A join MISS where Pinnacle has a same-day fixture sharing ≥1 (normalized)
    team name with this row → the fixture is almost certainly present under a
    different spelling (a name-synonym break, fixable with an alias), NOT a
    genuine missing quote. Mirrors ``name_sentinel``'s mismatch-vs-not-covered
    split, but for the jingcai_sp↔odds_snapshots join the CLV ledger turns on.
    (We only reach here after the exact (date, home, away) join already failed,
    so a shared name necessarily means the OTHER side is spelt differently.)"""
    want = {_norm(d["home_team"]), _norm(d["away_team"])}
    want.discard("")
    rows = conn.execute(
        "SELECT home_team, away_team FROM odds_snapshots WHERE match_date=?",
        (d["match_date"],)).fetchall()
    return any(_norm(r["home_team"]) in want or _norm(r["away_team"]) in want
               for r in rows)


def compute_ledger(db_path: str, *, min_ev: float = _MIN_EV) -> dict:
    """Per-leg CLV (vs Pinnacle close) over ALL captured 竞彩 SP — settled or not.
    Returns legs (each tagged tier/rank/market) + the selected-leg (1X2) subset."""
    from nutmeg.v4.observation.jingcai_sp import ensure_jingcai_sp_table

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        # tolerate a fresh DB with no odds_snapshots yet — canonical DDL so it
        # never drifts (the hand-copied one lacked kickoff_utc, breaking the
        # 体检 B2 pre-kickoff guard).
        from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots
        ensure_odds_snapshots(conn)
        raw = conn.execute(
            "SELECT match_date, home_team, away_team, fixture_id, league, market, "
            "captured_at, jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, "
            "handicap_home, psc_over, psc_under, ou_line "
            "FROM jingcai_sp").fetchall()
        # one observation per (match, market): the FRESHEST 竞彩 SP capture
        latest: dict[tuple, dict] = {}
        for r in raw:
            d = dict(r)
            k = (d["match_date"], d["home_team"], d["away_team"], d["market"] or "had")
            if k not in latest or (d["captured_at"] or "") >= (latest[k]["captured_at"] or ""):
                latest[k] = d

        legs: list[dict] = []
        selected: list[dict] = []
        # split a join MISS by cause so an autumn name-break self-announces instead
        # of hiding in one undifferentiated no_close count:
        miss_name: list[dict] = []   # Pinnacle has the fixture under another spelling
        miss_quote = 0               # genuinely no same-day Pinnacle quote
        miss_devig = 0               # close found but de-vig failed (bad odds, not a name)
        for d in latest.values():
            close = _pinn_close(conn, d)
            if close is None:
                if _same_day_name_overlap(conn, d):
                    miss_name.append({"date": d["match_date"], "league": d["league"],
                                      "home": d["home_team"], "away": d["away_team"]})
                else:
                    miss_quote += 1
                continue
            market = d["market"] or "had"
            jc = (d["jc_home"], d["jc_draw"], d["jc_away"])
            if market == "hhad":
                p_close, labels = _hhad_cover_p(close, d["handicap_home"]), _HC
            else:
                p_close, labels = _devig3(close[0], close[1], close[2]), _HAD
            if p_close is None:
                miss_devig += 1
                continue
            order = sorted(range(3), key=lambda i: -p_close[i])
            rankname = {order[0]: "热门", order[1]: "居中", order[2]: "冷门"}
            for i in range(3):
                sp = jc[i]
                if not sp or sp <= 1:
                    continue
                legs.append({
                    "clv": p_close[i] * float(sp) - 1.0, "p": p_close[i],
                    "tier": _tier(p_close[i]), "rank": rankname[i],
                    "pos": labels[i], "market": market,
                })
            # selected leg: pick argmax CAPTURE-time EV (no look-ahead), record CLV vs
            # the close. had → de-vig capture 1X2; hhad → reverse-fit capture cover-P
            # from capture 1X2 + O/U (psc_over/under; falls back to default total if a
            # pre-O/U-storage row lacks them).
            if market == "hhad":
                cap = _hhad_cover_p((d["psc_home"], d["psc_draw"], d["psc_away"],
                                     d["psc_over"], d["psc_under"], d["ou_line"]),
                                    d["handicap_home"])
            else:
                cap = _devig3(d["psc_home"], d["psc_draw"], d["psc_away"])
            if cap:
                evs = [cap[i] * float(jc[i]) - 1.0 if (jc[i] and jc[i] > 1) else -9.0
                       for i in range(3)]
                j = max(range(3), key=lambda i: evs[i])
                if evs[j] >= min_ev:
                    selected.append({
                        # canonical label: sporttery CN-abbrev + market_mode EN-code
                        # writers must land in ONE gate group (体检 2026-07-02)
                        "clv": p_close[j] * float(jc[j]) - 1.0, "cap_ev": evs[j],
                        "pos": labels[j], "market": market,
                        "league": canonical_league(d["league"]),
                        "date": d["match_date"],
                        "match": f'{d["home_team"]} vs {d["away_team"]}',
                    })
        return {"legs": legs, "selected": selected,
                "no_close": len(miss_name) + miss_quote + miss_devig,
                "miss_name": miss_name, "miss_quote": miss_quote,
                "miss_devig": miss_devig, "n_matches": len(latest)}


def _agg(items: list[dict]) -> tuple[int, float, int]:
    """(n, mean CLV, #legs that beat the close)."""
    if not items:
        return 0, 0.0, 0
    cl = [x["clv"] for x in items]
    return len(cl), st.fmean(cl), sum(1 for c in cl if c > 0)


def render(report: dict, min_ev: float = _MIN_EV) -> str:
    legs, sel = report["legs"], report["selected"]
    out: list[str] = []
    out.append("=" * 66)
    out.append("CLV 账本 — 软盘 vs Pinnacle 收盘(不依赖结算)")
    out.append("=" * 66)
    nm = report.get("miss_name", [])
    out.append(
        f"配对比赛: {report['n_matches']}  ·  无收盘线: {report['no_close']}"
        f"(名字疑似不配 {len(nm)} / 真没报价 {report.get('miss_quote', 0)}"
        f" / 去vig失败 {report.get('miss_devig', 0)})  ·  总腿数: {len(legs)}")
    if nm:
        out.append("  ⚠️ 队名 join 哨兵 — 同日 Pinnacle 有该队却没配上(疑似别名缺失, 该补 alias):")
        for m in nm[:8]:
            out.append(f"      [{m['league'] or '?'}] {m['date']} {m['home']} v {m['away']}")
        if len(nm) > 8:
            out.append(f"      … 共 {len(nm)} 条")
    if not legs:
        out.append("\n  还没有可配对的(竞彩 SP × Pinnacle 收盘)—— 攒着,每开一场就长一条。")
        return "\n".join(out)
    n, mean, beat = _agg(legs)
    out.append(f"\n【整体】平均 CLV {mean*100:+.1f}%  ·  打败收盘 {beat}/{n}"
               f"  ← 这就是那堵抽水墙(平均腿)")

    def _section(title: str, key: str, order: list[str] | None = None):
        groups: dict[str, list] = defaultdict(list)
        for L in legs:
            groups[L[key]].append(L)
        out.append(f"\n按{title}:")
        keys = order or sorted(groups)
        for k in keys:
            if k not in groups:
                continue
            n, mean, beat = _agg(groups[k])
            out.append(f"  {k:16} {n:3} 腿 · 平均 CLV {mean*100:+5.1f}% · 打败收盘 {beat}/{n}")

    _section("EV 可靠性分级", "tier",
             ["chalk (>77%)", "甜区 (25–67%)", "边缘 (67–77%)", "边缘 (20–25%)",
              "高估区 (15–20%)", "cold (P<15%)"])
    _section("腿排名", "rank", ["热门", "居中", "冷门"])
    _section("玩法", "market", ["had", "hhad"])

    out.append("\n" + "-" * 66)
    n, mean, beat = _agg(sel)
    out.append(
        f"【选中腿】(1X2 + 让球 · 下注时 EV≥{min_ev:.0%} · 无前视):"
        f"  N={n}  ·  平均 CLV {mean*100:+.1f}%" if n else
        "【选中腿】(1X2 + 让球 · 下注时 EV≥5%):  N=0 —— 还没攒到一条 +EV 选中腿")
    if n:
        out.append(f"  打败收盘 {beat}/{n}")

    # 闸门(升级): t 检验 + BHY-FDR 跨联赛 + 预警/确认两层 —— 取代旧的 N≥15/38 计数器。
    # (一个计数不是显著性检验;按 13 联赛挑「最软」= 多重检验, p=0.05 必造假阳。)
    per_league: dict[str, dict] = defaultdict(lambda: {"values": [], "clusters": []})
    for s in sel:
        per_league[s["league"]]["values"].append(s["clv"])
        per_league[s["league"]]["clusters"].append(s["date"])
    out.append("")
    out.append(
        f"【软水闸门 · 升级】t 检验 + BHY-FDR 跨联赛 + 两层"
        f"(预警 N≥{WARN_MIN_N} / 确认 t≥{CONFIRM_T:g}·过FDR·N≥{CONFIRM_MIN_N})")
    out.append("  口径: CLV 按比赛日聚类(防同轮相关高估 t) · 单边检验 mean>0 · BHY 控假阳比例")
    if not per_league:
        out.append("  还没有 +EV 选中腿 → 无联赛可检验(空仓继续攒, 这是诚实状态)。")
    else:
        verdicts = evaluate(dict(per_league))
        zh = {"confirm": "✅ 确认", "warn": "⚠️ 预警", "—": "—"}
        out.append(f"  {'联赛':<12}{'N':>4}{'簇':>4}{'CLV':>9}{'t':>7}{'p':>8}{'FDR':>5} 层")
        for v in verdicts:
            tt = f"{v.t:.2f}" if v.t is not None else "n/a"
            pp = f"{v.p:.3f}" if v.p is not None else "n/a"
            fdr = "过" if v.fdr_pass else ("否" if v.in_family else "·")
            out.append(
                f"  {v.league:<12}{v.n:>4}{v.n_clusters:>4}{v.mean*100:>+8.1f}%"
                f"{tt:>7}{pp:>8}{fdr:>5}  {zh[v.layer]}")
        pooled = pooled_test(dict(per_league))
        if pooled.t is not None:
            out.append(
                f"  {'合并·仅参考':<12}{pooled.n:>4}{pooled.n_clusters:>4}"
                f"{pooled.mean*100:>+8.1f}%{pooled.t:>7.2f}{pooled.p:>8.3f}"
                f"{'·':>5}  (忽略多重检验, 仅 sanity)")
        conf = [v.league for v in verdicts if v.layer == "confirm"]
        warn = [v.league for v in verdicts if v.layer == "warn"]
        if conf:
            out.append(f"  → 确认有边(可动手): {', '.join(conf)}")
        elif warn:
            out.append(f"  → 仅预警(观察, 别下注): {', '.join(warn)} —— 未达统计确认。")
        else:
            out.append("  → 无联赛达预警门槛 —— 继续空仓攒数据。")

    out.append("\n  诚实: 选中按「下注时 EV」选、CLV 对「收盘」量 → 无前视偏差, 正的才算真信号。")
    out.append("        预警≠确认: 真边在 672 注都可能 p≈0.09 → 确认要 N 到几百 + t≥2.8 + 过 FDR。")
    out.append("        让球(hhad)选中腿用捕获时 1X2+O/U 反推; 旧行无存 O/U 时退化用默认总进球。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="CLV 账本 — 软盘 vs Pinnacle 收盘(不依赖结算,验证软水边)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--min-ev", type=float, default=_MIN_EV, help="选中腿 EV 阈值")
    ap.add_argument("--out", default="logs/clv_ledger_latest.md",
                    help="也写一份 markdown(空字符串=不写)")
    args = ap.parse_args(argv)

    text = render(compute_ledger(args.db, min_ev=args.min_ev), args.min_ev)
    print(text)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("```\n" + text + "\n```\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
