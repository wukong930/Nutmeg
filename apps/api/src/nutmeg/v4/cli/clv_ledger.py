"""nutmeg-clv-ledger — settlement-INDEPENDENT soft-water (CLV) ledger.

The staleness map (``jingcai_staleness``) waits for the RESULT to show realized
ROI — so it only sees the handful of settled matches. But **CLV (竞彩 SP vs
Pinnacle's CLOSE) needs no result**: the close is known at kickoff. This ledger
pairs every captured 竞彩 SP with Pinnacle's closing line, computes per-leg
``CLV = P(close de-vig) × 竞彩SP − 1`` over the WHOLE distribution, and breaks it
down by tier × leg-rank × market — so it accrues ~6× faster than the settled
map (every offered match is a data point, not every settled one).

The headline the validation timeline turns on: the mean CLV of the **selected**
leg (the EV≥5% pick our filter makes AT CAPTURE) + N, tracked toward the ~15–40
legs needed to read the edge. Selection is on capture-time EV (no look-ahead);
CLV is measured vs the close — so a positive selected-CLV is a real signal, not
a circular artifact. No ``ft_outcome`` is touched.

honest scope: 让球 (hhad) legs are in the distribution (close-side reverse-fit,
no result needed) but the SELECTED counter is 1X2-only for now — hhad selection
needs the capture-time O/U, which ``jingcai_sp`` does not yet store.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

from nutmeg.v4.cli.jingcai_staleness import _devig3, _pinn_close

_MIN_EV = 0.05
_HAD = ("主胜", "平局", "客胜")
_HC = ("让胜", "让平", "让负")
# validation targets from the power calc (σ≈6.6%/leg): N to detect a given edge
_TARGETS = ((15, "+5%"), (38, "+3%"))


def _tier(p: float) -> str:
    """EV reliability tier by P (cuts 0.15/0.20/0.25/0.67/0.77 — ev_tier_calibration)."""
    if p < 0.15:
        return "cold (P<15%)"
    if p < 0.20:
        return "高估区 (15–20%)"
    if p < 0.25:
        return "边缘 (20–25%)"
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


def compute_ledger(db_path: str, *, min_ev: float = _MIN_EV) -> dict:
    """Per-leg CLV (vs Pinnacle close) over ALL captured 竞彩 SP — settled or not.
    Returns legs (each tagged tier/rank/market) + the selected-leg (1X2) subset."""
    from nutmeg.v4.observation.jingcai_sp import ensure_jingcai_sp_table

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        conn.execute(  # tolerate a fresh DB with no odds_snapshots yet
            "CREATE TABLE IF NOT EXISTS odds_snapshots (id INTEGER PRIMARY KEY, "
            "captured_at TEXT, fixture_id INTEGER, match_date TEXT, home_team TEXT, "
            "away_team TEXT, psc_home REAL, psc_draw REAL, psc_away REAL, "
            "psc_over REAL, psc_under REAL, ou_line REAL)")
        raw = conn.execute(
            "SELECT match_date, home_team, away_team, fixture_id, market, captured_at, "
            "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, handicap_home "
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
        no_close = 0
        for d in latest.values():
            close = _pinn_close(conn, d)
            if close is None:
                no_close += 1
                continue
            market = d["market"] or "had"
            jc = (d["jc_home"], d["jc_draw"], d["jc_away"])
            if market == "hhad":
                p_close, labels = _hhad_cover_p(close, d["handicap_home"]), _HC
            else:
                p_close, labels = _devig3(close[0], close[1], close[2]), _HAD
            if p_close is None:
                no_close += 1
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
            # selected leg — 1X2 only: pick argmax CAPTURE-time EV (no look-ahead),
            # then record its CLV vs the close.
            if market == "had":
                cap = _devig3(d["psc_home"], d["psc_draw"], d["psc_away"])
                if cap:
                    evs = [cap[i] * float(jc[i]) - 1.0 if (jc[i] and jc[i] > 1) else -9.0
                           for i in range(3)]
                    j = max(range(3), key=lambda i: evs[i])
                    if evs[j] >= min_ev:
                        selected.append({
                            "clv": p_close[j] * float(jc[j]) - 1.0, "cap_ev": evs[j],
                            "pos": labels[j], "match": f'{d["home_team"]} vs {d["away_team"]}',
                        })
        return {"legs": legs, "selected": selected, "no_close": no_close,
                "n_matches": len(latest)}


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
    out.append(f"配对比赛: {report['n_matches']}  ·  无收盘线(跳过): {report['no_close']}  "
               f"·  总腿数: {len(legs)}")
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
    out.append(f"【验证计数器】选中腿(1X2 · 下注时 EV≥{min_ev:.0%} · 无前视):"
               f"  N={n}  ·  平均 CLV {mean*100:+.1f}%" if n else
               "【验证计数器】选中腿(1X2 · 下注时 EV≥5%):  N=0 —— 还没攒到一条 +EV 选中腿")
    if n:
        out.append("  打败收盘 " + f"{beat}/{n}")
    for tgt, edge in _TARGETS:
        bar = "█" * min(n, tgt) + "░" * max(0, tgt - n)
        status = "✅ 够了" if n >= tgt else f"还差 {tgt - n}"
        out.append(f"  验证 {edge} 边(需 {tgt:>2}): [{bar}] {n}/{tgt}  {status}")
    out.append("\n  诚实: 选中按「下注时 EV」选、CLV 对「收盘」量 → 无前视偏差,正的才算真信号。")
    out.append("        让球(hhad)选中腿待 jingcai_sp 存下捕获时 O/U 后接入;现仅入分布。")
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
