"""Markdown report for multi-season walk-forward."""
from __future__ import annotations

from datetime import datetime, timezone


def _fmt(x, fmt=".4f"):
    if x is None:
        return "—"
    return format(x, fmt)


def _ll(d):
    return None if d is None else d.get("log_loss")


def _hr(d):
    return None if d is None else d.get("hit_rate")


def _ece(d):
    return None if d is None else d.get("ece")


def format_multi_season(result: dict) -> str:
    seasons = result.get("seasons", [])
    if not seasons:
        return "# V4 多季对比卡\n\n(no results)\n"

    lines = []
    lines.append("# V4 多季 Walk-Forward 对比")
    lines.append("")
    lines.append("_Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "_")
    lines.append("")
    lines.append("评估 V4 GBM-λ + DC 在不同测试赛季上的表现，验证"
                 "**模型优势是否稳定**还是只在某一季偶然好。")
    lines.append("")

    # Log-loss table
    lines.append("## Log-loss 对比")
    lines.append("")
    lines.append("| Test cutoff | n_full | n_gbm | Pinnacle (GBM子集) | V4 MLE+Temp | V4 GBM+Temp | GBM Δ vs Pin | 信号捕获率 |")
    lines.append("|------------:|-------:|------:|-------------------:|------------:|------------:|-------------:|----------:|")
    for s in seasons:
        pg = _ll(s.get("pinnacle_gbm"))
        pf = _ll(s.get("pinnacle"))
        mt = _ll(s.get("mle_dc_temp"))
        gt = _ll(s.get("gbm_dc_temp"))
        if pg is None or gt is None:
            continue
        gap = gt - pg
        uniform_baseline = 1.0986
        total = uniform_baseline - pg
        pct = (1 - gap / total) * 100 if total > 0 else 0
        lines.append(
            f"| {s['cutoff']} | {s['test_n_full']:>5} | {s['test_n_gbm']:>5} | "
            f"{_fmt(pg)} | {_fmt(mt)} | **{_fmt(gt)}** | "
            f"{gap:+.4f} | **{pct:.1f}%** |"
        )
    lines.append("")

    # Hit rate
    lines.append("## 命中率对比")
    lines.append("")
    lines.append("| Test cutoff | Pinnacle hit | V4 GBM+Temp hit | Δ |")
    lines.append("|------------:|-------------:|----------------:|--:|")
    for s in seasons:
        pin_hr = _hr(s.get("pinnacle_gbm"))
        gbm_hr = _hr(s.get("gbm_dc_temp"))
        if pin_hr is None or gbm_hr is None:
            continue
        lines.append(
            f"| {s['cutoff']} | {pin_hr:.3f} | {gbm_hr:.3f} | {gbm_hr-pin_hr:+.3f} |"
        )
    lines.append("")

    # ECE
    lines.append("## 校准（ECE）对比")
    lines.append("")
    lines.append("| Test cutoff | Pinnacle ECE | V4 GBM+Temp ECE |")
    lines.append("|------------:|-------------:|----------------:|")
    for s in seasons:
        pin_e = _ece(s.get("pinnacle_gbm"))
        gbm_e = _ece(s.get("gbm_dc_temp"))
        if pin_e is None or gbm_e is None:
            continue
        lines.append(f"| {s['cutoff']} | {pin_e:.4f} | {gbm_e:.4f} |")
    lines.append("")

    lines.append("## 解读")
    lines.append("")
    lines.append("- 若 **GBM Δ vs Pinnacle** 在所有季都接近 0（如 +0.005~+0.012），说明 V4 优势稳定。")
    lines.append("- 若 GBM Δ 在某一季显著恶化（>0.02），说明那一季有结构性变化（联赛重组、新球队、规则变化）需要调研。")
    lines.append("- **信号捕获率** > 85% 在每一季：模型已经接近 Pinnacle 上限。")
    lines.append("- 模型完全没\"过拟合\"24/25：每一季用各自的 train slice 独立训练。")
    return "\n".join(lines)
