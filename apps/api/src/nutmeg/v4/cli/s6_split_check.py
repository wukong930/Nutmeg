"""nutmeg-s6-split-check — the pre-registered S6 让球切分偏差复现 test.

Reads own odds+fixtures cache (zero API calls), replicates the DISCOVERY recipe
byte-for-byte (Pinnacle 1X2 WPO de-vig + real ou_line → DC grid → |h|=1 triple,
only where both adjacent pure half-lines are quoted), and runs the frozen S6
residual tests (``nutmeg.v4.model.split_bias``).

Frozen 2026-07-05 so the autumn read is reproducible, not fitted after the fact.
The confirmatory window is ``--since 2026-08-01`` (default); running it TODAY
prints N=0 real samples — that's correct (no autumn data yet) and still proves
the machinery runs + self-checks. ``--include-discovery`` drops the window to
re-run on ≤2026-07 data: that REPRODUCES the finding (让胜 over ~2.7pp / 让平
under ~2.7pp) as a lock check — it is NOT a valid S6 read (same regime the
correction came from; the prereg forbids counting it).

The final C1 deploy gate is the S-family BHY-FDR across S1–S6 (needs the other
S tests), NOT this one p-value — this CLI reports S6's own t/p + the symbol-
consistency + anchor checks as the per-test inputs to that family decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from nutmeg.v4.cli.sharp_consensus_eval import _iter_odds, _resp
from nutmeg.v4.data.odds_parser import (
    extract_1x2_odds,
    extract_asian_handicap,
    extract_over_under,
)
from nutmeg.v4.model.clv_gate import CONFIRM_T
from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.market_handicap import (
    devig_asian_handicap_line,
    devig_over,
    fit_lambdas,
    score_grid,
)
from nutmeg.v4.model.split_bias import (
    S6_DELTA,
    S6_LINES,
    S6_WINDOW_START,
    S6Sample,
    grid_triple,
    is_pure_half,
    margin_pmf,
    s6_result,
    settle_handicap,
)

_FINISHED = {"FT", "AET", "PEN"}


def _load_results(fixtures_dir: Path) -> dict[int, tuple[str, int, int]]:
    """fixture_id → (match_date, home_goals, away_goals) for finished matches,
    90' score (score.fulltime, falling back to final goals)."""
    out: dict[int, tuple[str, int, int]] = {}
    for f in fixtures_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        for r in _resp(data):
            fb = r.get("fixture") or {}
            if (fb.get("status") or {}).get("short") not in _FINISHED:
                continue
            fid = fb.get("id")
            ft = (r.get("score") or {}).get("fulltime") or {}
            g = r.get("goals") or {}
            hg = ft.get("home") if ft.get("home") is not None else g.get("home")
            ag = ft.get("away") if ft.get("away") is not None else g.get("away")
            date = (fb.get("date") or "")[:10]
            if fid is None or hg is None or ag is None or not date:
                continue
            out[int(fid)] = (date, int(hg), int(ag))
    return out


def collect_samples(cache_dir: Path, since: str) -> list[S6Sample]:
    """Replicate the discovery recipe over the cache, windowed to ``since``.

    Only |h|=1 integer lines where BOTH adjacent pure half-lines (h∓0.5) are
    cleanly 2-way quoted are kept (the finding's exact sample definition).
    """
    results = _load_results(cache_dir / "_fixtures")
    samples: list[S6Sample] = []
    for fid, env in _iter_odds(cache_dir / "_odds"):
        if fid not in results:
            continue
        date, hg, ag = results[fid]
        if date < since:
            continue
        odds = extract_1x2_odds(env)
        ah = extract_asian_handicap(env)
        if not odds or not ah:
            continue
        half = set()
        for ln, d in ah.items():
            if is_pure_half(ln) and devig_asian_handicap_line(d.get("home"), d.get("away")):
                half.add(round(ln * 2) / 2)
        usable = [h for h in S6_LINES if (h - 0.5) in half and (h + 0.5) in half]
        if not usable:
            continue
        fair = devig_1x2(odds["H"], odds["D"], odds["A"])
        if not fair:
            continue
        ou = extract_over_under(env)
        p_over = devig_over(ou[1], ou[2]) if ou else None
        ou_line = float(ou[0]) if ou else 2.5
        try:
            lh, la = fit_lambdas(fair[0], fair[1], fair[2], p_over, ou_line=ou_line)
            pmf = margin_pmf(score_grid(lh, la))
        except Exception:  # noqa: BLE001
            continue
        for h in usable:
            pw, pd, pl = grid_triple(pmf, h)
            samples.append(S6Sample(date, fid, h, pw, pd, pl,
                                    settle_handicap(hg, ag, h)))
    return samples


def _fmt(mt) -> str:
    t = f"{mt.t:+.2f}" if mt.t is not None else "  —"
    p = f"{mt.p:.4f}" if mt.p is not None else "  —"
    return f"mean {mt.mean*100:+5.2f}pp · t {t} · p {p}"


def run(cache_dir: Path, since: str) -> int:
    samples = collect_samples(cache_dir, since)
    r = s6_result(samples)
    print(f"S6 让球切分偏差复现 · 窗口 ≥{since} · |h|=1 · δ(C1)={S6_DELTA}")
    print(f"样本(场×线): {r.n} · 比赛日(聚类): {r.n_days}\n")
    if r.n == 0:
        print("N=0 — 窗口内暂无数据。机器运转正常;秋季数据到达后自动累积。")
        print("(自检:可加 --include-discovery 在发现期数据上复现结论——仅锁工具,不算 S6。)")
        return 0
    print(f"{'':10}{'让胜':>10}{'让平':>10}{'让负':>10}")
    print(f"网格均值  {r.grid_win*100:9.1f}%{r.grid_draw*100:9.1f}%{r.grid_lose*100:9.1f}%")
    print(f"实际频率  {r.real_win*100:9.1f}%{r.real_draw*100:9.1f}%{r.real_lose*100:9.1f}%")
    print("\n残差检验(1{结果}−P网格,比赛日聚类稳健 t):")
    print(f"  让平(主检 H1>0):  {_fmt(r.draw_test)}")
    print(f"  让胜(预期镜像<0):  {_fmt(r.win_test)}")
    print(f"  让负(锚,预期≈0):  {_fmt(r.lose_test)}")
    print("\n判读(S6 单项;最终 C1 部署闸=S-family BHY-FDR 跨 S1–S6):")
    print(f"  符号一致(让平>0 且 让胜<0): {'✓' if r.symbol_consistent else '✗'}")
    print(f"  锚完好(让负无异动):        {'✓' if r.anchor_intact else '✗ 让负漂移!'}")
    sig = '✓' if r.draw_significant else '✗ 未达(family FDR 另算)'
    print(f"  让平单项显著(t≥{CONFIRM_T}):     {sig}")
    print(f"\n次级诊断 · C1 修正后 3 路 log-loss Δ: {r.corrected_logloss_delta:+.4f}"
          f" ({'修正更好' if r.corrected_logloss_delta < 0 else '修正无益/更差'})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S6 让球切分偏差复现(预注册)")
    ap.add_argument("--since", default=S6_WINDOW_START,
                    help=f"确认性窗口起点(默认冻结值 {S6_WINDOW_START})")
    ap.add_argument("--cache-dir", default="data/external/api_football",
                    help="API-Football 缓存目录(含 _odds / _fixtures)")
    ap.add_argument("--include-discovery", action="store_true",
                    help="放宽到 ≤2026-07 发现期数据复现结论(仅锁工具,非有效 S6)")
    args = ap.parse_args(argv)
    since = "1900-01-01" if args.include_discovery else args.since
    if args.include_discovery:
        print("⚠️ --include-discovery:发现期数据,同 regime,非有效 S6 读数(只锁工具)\n")
    return run(Path(args.cache_dir), since)


if __name__ == "__main__":
    raise SystemExit(main())
