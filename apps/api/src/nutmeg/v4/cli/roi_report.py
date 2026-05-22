"""V4 ROI report CLI.

Usage:
    python -m nutmeg.v4.cli.roi_report --db data/v4_observation.db [--out report.md]

Reads all settled recommendations from the observation DB and produces a
Markdown report covering: headline ROI, breakdown by k-legs, by league,
calibration buckets, and weekly cumulative P/L.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from nutmeg.v4.observation.roi import (
    calibration_buckets,
    compute_headline,
    group_by_k_legs,
    group_by_league,
    weekly_pl,
)
from nutmeg.v4.observation.store import open_db


def _fmt_pct(x: float, decimals: int = 1) -> str:
    return f"{x * 100:.{decimals}f}%"


def _fmt_money(x: float) -> str:
    return f"¥{x:,.2f}"


def format_report(conn) -> str:
    h = compute_headline(conn)
    lines: list[str] = []
    lines.append("# V4 实战 ROI 报告")
    lines.append("")
    lines.append("_Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "_")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    if h.n_settled == 0:
        lines.append("**还没有任何已结算的推荐。** 先用 `nutmeg.v4.cli.record_outcome` 录入比赛结果。")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"- 已结算推荐数:   **{h.n_settled}**")
    lines.append(f"- 命中:            {h.n_hit}   (其中复式部分命中: {h.n_partial})")
    lines.append(f"- 未命中:          {h.n_miss}")
    lines.append(f"- 总投入:          {_fmt_money(h.total_stake)}")
    lines.append(f"- 总回收:          {_fmt_money(h.total_payout)}")
    lines.append(f"- **净盈亏**:      **{_fmt_money(h.profit_loss)}**")
    lines.append(f"- **ROI**:         **{_fmt_pct(h.roi, 2)}**")
    lines.append(f"- 模型预测平均命中率: {_fmt_pct(h.avg_hit_p_predicted, 1)}")
    lines.append(f"- 实际平均命中率:     {_fmt_pct(h.actual_hit_rate, 1)}")
    cal_gap = h.actual_hit_rate - h.avg_hit_p_predicted
    lines.append(f"- 校准偏差（实际 − 预测）: {cal_gap:+.4f} （正值表示模型保守、低估命中率）")
    lines.append("")

    # By k-legs
    by_k = group_by_k_legs(conn)
    if by_k:
        lines.append("## 按串关大小分组")
        lines.append("")
        lines.append("| k 串 1 | 推荐数 | 命中数 | 命中率 | 投入 | 回收 | 净盈亏 | ROI | 模型预测命中率 |")
        lines.append("|-------:|------:|------:|------:|----:|----:|------:|----:|--------------:|")
        for r in by_k:
            n = r["n"]
            n_hit = r["n_hit"] or 0
            lines.append(
                f"| {r['k_legs']} | {n} | {n_hit} | {_fmt_pct(n_hit / n if n else 0)} | "
                f"{_fmt_money(r['stake'])} | {_fmt_money(r['payout'])} | "
                f"{_fmt_money(r['pl'])} | {_fmt_pct(r['pl'] / r['stake'] if r['stake'] else 0, 1)} | "
                f"{_fmt_pct(r['avg_hit_p'])} |"
            )
        lines.append("")

    # By league
    by_lg = group_by_league(conn)
    if by_lg:
        lines.append("## 按联赛分组（按主联赛 = 串关首腿所在联赛）")
        lines.append("")
        lines.append("| 联赛 | 推荐数 | 命中数 | 命中率 | 投入 | 净盈亏 | ROI |")
        lines.append("|------|------:|------:|------:|----:|------:|----:|")
        for r in by_lg:
            lines.append(
                f"| {r['league']} | {r['n']} | {r['n_hit']} | "
                f"{_fmt_pct(r['hit_rate'])} | "
                f"{_fmt_money(r['stake'])} | {_fmt_money(r['pl'])} | {_fmt_pct(r['roi'], 1)} |"
            )
        lines.append("")

    # Calibration
    cal = calibration_buckets(conn, n_bins=5)
    if cal:
        lines.append("## 校准（预测命中率 vs 实际命中率）")
        lines.append("")
        lines.append("| 预测命中率区间 | 样本数 | 平均预测 | 实际命中率 | 偏差 |")
        lines.append("|---------------|------:|--------:|----------:|----:|")
        for b in cal:
            lines.append(
                f"| {_fmt_pct(b['bin_lo'], 0)}–{_fmt_pct(b['bin_hi'], 0)} | {b['n']} | "
                f"{_fmt_pct(b['avg_predicted'])} | {_fmt_pct(b['actual_hit_rate'])} | "
                f"{b['actual_hit_rate'] - b['avg_predicted']:+.3f} |"
            )
        lines.append("")
        lines.append("校准偏差应该接近 0。持续负值（实际 < 预测）= 模型过于乐观；")
        lines.append("持续正值 = 模型保守。任一方向 > 0.05 都值得调查。")
        lines.append("")

    # Weekly
    weekly = weekly_pl(conn)
    if weekly and len(weekly) >= 1:
        lines.append("## 按周累计盈亏")
        lines.append("")
        lines.append("| 周次 | 推荐数 | 投入 | 本周净盈亏 | 累计净盈亏 | 本周 ROI |")
        lines.append("|-----|------:|----:|----------:|----------:|--------:|")
        for w in weekly:
            lines.append(
                f"| {w['week']} | {w['n']} | {_fmt_money(w['stake'])} | "
                f"{_fmt_money(w['pl'])} | {_fmt_money(w['cumulative_pl'])} | "
                f"{_fmt_pct(w['roi'], 1)} |"
            )
        lines.append("")

    lines.append("## 解读指南")
    lines.append("")
    lines.append("- **样本量 < 50 时所有数字不稳定**——一两个长尾命中能让 ROI 翻倍或翻负。")
    lines.append("- **真实信号**通常需要 200+ 个已结算推荐才能从噪声里出现。这是 4-8 周实战观察的合理时长。")
    lines.append("- 如果\"模型预测命中率\"和\"实际命中率\"长期偏差 > 5 个百分点，模型校准有问题（需要重训）。")
    lines.append("- 如果不同联赛 ROI 差异巨大（>30%），说明模型在某些联赛失灵——可以考虑只在 ROI 正的联赛下注。")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V4 ROI report")
    parser.add_argument("--db", default="data/v4_observation.db")
    parser.add_argument("--out", default=None, help="Output path (default: stdout)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"ERROR: observation DB not found: {args.db}", file=sys.stderr)
        print("       Run `python -m nutmeg.v4.cli.recommend --record-to <db>` first.", file=sys.stderr)
        return 1

    with open_db(args.db) as conn:
        report = format_report(conn)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
