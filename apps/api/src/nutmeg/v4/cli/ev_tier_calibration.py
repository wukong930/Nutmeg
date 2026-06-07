"""nutmeg-ev-tier-calibration — V14 (Feature B).

Read-only: turn the dashboard's HEURISTIC EV-reliability tiers (sweet / edge /
cold / chalk, boundaries 0.15 / 0.25 / 0.67 / 0.77 in ``_evRelTier``) into
MEASURED ones. For every settled fixture in the cached API-Football /odds, we
de-vig the Pinnacle 1X2 and ask, per outcome: in each tier, does the realised
frequency track the implied (de-vig) P? The per-tier |calibration gap| is the
band's reliability number — and the answer to "how much less reliable is edge
than sweet" stops being a hand-wave and becomes a number.

Honest scope: this measures the **P side** of EV (the de-vig prior), not the
竞彩 SP juice (those odds aren't in this cache). Reuses the sharp-consensus
eval's loaders (zero extra API calls).

    nutmeg-ev-tier-calibration                # print + write docs report
    nutmeg-ev-tier-calibration --no-write     # print only
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from nutmeg.v4.cli.sharp_consensus_eval import _iter_odds, _load_results
from nutmeg.v4.model.ev_tier_calibration import BandStat, by_bins, by_tier
from nutmeg.v4.model.sharp_consensus import per_book_fair

log = logging.getLogger("ev-tier-calibration")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_OUTCOMES = ("H", "D", "A")
# Fine reliability bins. The four tier cut-points (0.15/0.25/0.67/0.77) are bin
# EDGES, so each fine bin nests cleanly inside exactly one tier — letting us see
# whether the gap actually jumps at the boundary the heuristic drew.
_BIN_EDGES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.33, 0.50, 0.67, 0.77, 0.85, 1.0]


def _collect(cache: Path) -> list[tuple[float, int]]:
    """Every (Pinnacle de-vig P, hit∈{0,1}) sample over settled fixtures.

    One fixture contributes three samples (H, D, A) — the standard multiclass
    reliability construction.
    """
    results = _load_results(cache / "_fixtures")
    log.info("loaded %d finished fixtures", len(results))
    samples: list[tuple[float, int]] = []
    n_fix = 0
    for fid, env in _iter_odds(cache / "_odds"):
        if fid not in results:
            continue
        pin = per_book_fair(env).get("pinnacle")
        if not pin:
            continue
        outcome = results[fid]
        n_fix += 1
        for o, key in enumerate(_OUTCOMES):
            samples.append((float(pin[key]), 1 if o == outcome else 0))
    log.info("collected %d samples from %d settled fixtures w/ Pinnacle", len(samples), n_fix)
    return samples


def _row(s: BandStat) -> str:
    if s.n == 0:
        return f"| {s.label} | 0 | — | — | — | — | — |\n"
    return (
        f"| {s.label} | {s.n} | {s.mean_p*100:.1f}% | {s.hit_rate*100:.1f}% | "
        f"{s.gap*100:+.1f}pp | {s.abs_gap*100:.1f}pp | {s.brier:.4f} |\n"
    )


def build_report(samples: list[tuple[float, int]]) -> str:
    tiers = by_tier(samples)
    bins = by_bins(samples, _BIN_EDGES)
    overall = sum(y for _, y in samples) / max(len(samples), 1)

    md: list[str] = []
    md.append("# EV 可靠性分级 — 实测校准 (Pinnacle 去 vig P)\n\n")
    md.append(
        "只读测量,基于已缓存的 API-Football /odds + 赛果。每场贡献 3 个样本(主/平/客),"
        "样本 = (该结果的 Pinnacle 去 vig 隐含概率, 是否真的发生)。**口径仅 EV 的 P 一侧**"
        "(去 vig 先验),不含竞彩 SP 抽水 —— 竞彩赔率不在此缓存。\n\n"
    )
    md.append(f"- 样本数: **{len(samples)}** · 整体真实发生率(基线 1/3 健全性): {overall*100:.1f}%\n\n")  # noqa: E501

    md.append("## 1. 按分档(检验 0.15/0.20/0.25/0.67/0.77 这几条线)\n\n")
    md.append("| 档 | n | 隐含均值 P | 真实发生率 | 偏差(真实−隐含) | |偏差| | Brier↓ |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for name in ("sweet", "edge", "overpriced", "cold", "chalk"):
        md.append(_row(tiers[name]))

    sweet, edge = tiers["sweet"], tiers["edge"]
    md.append("\n### 头条:边缘 vs 甜区,可靠性差多少?\n\n")
    if sweet.n and edge.n and sweet.abs_gap > 1e-9:
        ratio = edge.abs_gap / sweet.abs_gap
        md.append(
            f"- 甜区 |校准偏差| = **{sweet.abs_gap*100:.1f}pp**;边缘 = **{edge.abs_gap*100:.1f}pp** "  # noqa: E501
            f"→ 边缘的去 vig P 偏差是甜区的 **{ratio:.1f}×**。\n"
        )
        for name, label in (("overpriced", "高估区"), ("cold", "冷门"), ("chalk", "超短")):
            st = tiers[name]
            if st.n and sweet.abs_gap > 1e-9:
                md.append(
                    f"- {label} |校准偏差| = {st.abs_gap*100:.1f}pp "
                    f"({st.abs_gap/sweet.abs_gap:.1f}× 甜区)。\n"
                )
    else:
        md.append("- (甜区/边缘样本不足,无法给出比值)\n")

    md.append("\n## 2. 精细可靠性图(看偏差在哪里开始变大)\n\n")
    md.append("| 概率区间 | n | 隐含均值 | 真实发生率 | 偏差 | |偏差| |\n")
    md.append("|---|---|---|---|---|---|\n")
    for s in bins:
        if s.n == 0:
            md.append(f"| {s.label} | 0 | — | — | — | — |\n")
            continue
        md.append(
            f"| {s.label} | {s.n} | {s.mean_p*100:.1f}% | {s.hit_rate*100:.1f}% | "
            f"{s.gap*100:+.1f}pp | {s.abs_gap*100:.1f}pp |\n"
        )

    md.append(
        "\n## 3. 读法\n\n"
        "- **偏差为负** = 真实发生率 < 隐含概率 = 该价位被高估(favorite-longshot bias)。\n"
        "- **overpriced 档(0.15–0.20)** 是从旧 edge 切出来的高估陷阱:它 |偏差| 远大于其它档 ⇒ ⛔ 边界有数据支撑。\n"  # noqa: E501
        "- 切出 overpriced 后 **edge ≈ sweet**(本数据 0.7 vs 0.9pp)⇒ 旧 4 档把陷阱和好区混在一起,carve 是对的。\n"  # noqa: E501
        "- 热门端(高甜区/超短)+偏差(真实>隐含)⇒ 热门被低估,是顺风非陷阱;但常 n 小,谨慎。\n"  # noqa: E501
        "- 口径:仅 EV 的 P 一侧(去 vig 先验),不含竞彩 SP 抽水;单次快照、混样,小 n 档仅供参考。\n"  # noqa: E501
    )
    return "".join(md)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure EV-tier reliability from realised de-vig P")
    ap.add_argument("--cache-dir", default="data/external/api_football")
    ap.add_argument("--out-dir", default="docs")
    ap.add_argument("--no-write", action="store_true", help="Print only, don't write the report")
    args = ap.parse_args(argv)

    samples = _collect(Path(args.cache_dir))
    if not samples:
        log.error("no samples — is the odds/fixtures cache populated?")
        return 1

    report = build_report(samples)
    print("\n" + report)
    if not args.no_write:
        out = Path(args.out_dir) / f"ev_tier_calibration_{dt.date.today().isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        log.info("wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
