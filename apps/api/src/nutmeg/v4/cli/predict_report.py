"""nutmeg-predict-report — V12 W8j.

Scores SETTLED model-board predictions (from nutmeg-predict-log) and answers
"is the model's prediction actually any good?" — independent of 竞彩 betting.

Honest framing is baked in. Raw hit-rate is seductive but weak: a model looks
"accurate" just by picking favorites (favorites win ~half the time, and the
sharp already knew). So the report foregrounds the two metrics that actually
validate a probabilistic model:

  1. Calibration — do the 30%-picks happen ~30% of the time? (Brier)
  2. vs Pinnacle — does the model's log-loss beat the sharp's de-vig log-loss
     on the SAME matches, and on the matches where the two DISAGREE, who's
     right more often? This is the only test of whether the model adds
     anything over just following Pinnacle.

Examples:

    nutmeg-predict-report --db data/v4_observation.db
    nutmeg-predict-report --db data/v4_observation.db --league ESP_SEGUNDA_DIVISION
    nutmeg-predict-report --out docs/weekly/predict_report_$(date +%F).md
"""
from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

from nutmeg.v4.observation.prediction_log import fetch_league_predictions

log = logging.getLogger("nutmeg-predict-report")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_EPS = 1e-9
_LABELS = ("主胜", "平局", "客胜")


def _devig(h, d, a):
    if not (h and d and a):
        return None
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv]


def _model_p(r):
    return [r["p_home"], r["p_draw"], r["p_away"]]


def _pin_p(r):
    return _devig(r.get("psc_home"), r.get("psc_draw"), r.get("psc_away"))


def _log_loss(rows, getp):
    tot, n = 0.0, 0
    for r in rows:
        p = getp(r)
        if p is None:
            continue
        pa = max(_EPS, min(1.0 - _EPS, p[r["outcome"]]))
        tot += -math.log(pa)
        n += 1
    return (tot / n if n else float("nan")), n


def _brier(rows, getp):
    tot, n = 0.0, 0
    for r in rows:
        p = getp(r)
        if p is None:
            continue
        y = [0.0, 0.0, 0.0]
        y[r["outcome"]] = 1.0
        tot += sum((p[i] - y[i]) ** 2 for i in range(3))
        n += 1
    return (tot / n if n else float("nan")), n


def _hits(rows, getp):
    h, n = 0, 0
    for r in rows:
        p = getp(r)
        if p is None:
            continue
        if max(range(3), key=lambda i: p[i]) == r["outcome"]:
            h += 1
        n += 1
    return h, n


def _pct(x):
    return f"{x * 100:.1f}%" if x == x else "—"  # x!=x → NaN


def build_report(rows: list[dict]) -> str:
    settled = [r for r in rows if r.get("outcome") is not None]
    out: list[str] = ["# 模型盘预测命中率报告 (非竞彩 · 纯预测验证)\n"]
    if not settled:
        out.append("_尚无已结算的预测。先跑 `nutmeg-predict-log` 攒几天,"
                    "赛后自动结算后再来。_\n")
        return "\n".join(out)

    n = len(settled)
    mh, _ = _hits(settled, _model_p)
    mll, _ = _log_loss(settled, _model_p)
    mbr, _ = _brier(settled, _model_p)
    # Pinnacle baseline only over rows that carry a Pinnacle line.
    pin_rows = [r for r in settled if _pin_p(r) is not None]
    ph, pn = _hits(pin_rows, _pin_p)
    pll, _ = _log_loss(pin_rows, _pin_p)
    pbr, _ = _brier(pin_rows, _pin_p)

    out.append(f"已结算 **{n}** 场 (其中 {pn} 场有 Pinnacle 对照)。\n")
    out.append("## 命中率(看着爽,但会被热门拉高,别只看它)")
    out.append(f"- **模型命中率: {_pct(mh / n)}** ({mh}/{n})")
    if pn:
        out.append(f"- 同场 Pinnacle 热门命中率: {_pct(ph / pn)} ({ph}/{pn})"
                    " ← 模型要赢过这条才算有用")
    out.append("")
    out.append("## 校准(真正衡量预测质量,越低越好)")
    out.append(f"- 模型 log-loss: **{mll:.4f}** · Brier: {mbr:.4f}")
    if pn:
        out.append(f"- Pinnacle log-loss: **{pll:.4f}** · Brier: {pbr:.4f}")
        delta = mll - pll
        verdict = ("模型 ≈ 或不如 sharp(意料之中,别信模型的小背离)"
                   if delta >= -0.002 else "模型这批罕见地赢了 sharp(样本要够大才算数)")
        out.append(f"- **Δlog-loss (模型−Pinnacle): {delta:+.4f}** → {verdict}")
    out.append("")

    # Disagreement analysis — the only place the model can prove an edge.
    dis = []
    for r in pin_rows:
        if max(range(3), key=lambda i: _model_p(r)[i]) != \
           max(range(3), key=lambda i: _pin_p(r)[i]):
            dis.append(r)
    out.append("## 模型 vs Pinnacle 分歧场(模型能否证明自己的唯一战场)")
    if not dis:
        out.append("- 本批模型与 sharp **没有分歧**(都选同一个最可能结果)——"
                    "命中率几乎等于跟着 sharp 走,模型没贡献额外信息。")
    else:
        dmh, _ = _hits(dis, _model_p)
        dph, _ = _hits(dis, _pin_p)
        out.append(f"- 分歧 **{len(dis)}** 场:模型选对 {dmh}/{len(dis)} "
                    f"({_pct(dmh / len(dis))}) vs Pinnacle 选对 {dph}/{len(dis)} "
                    f"({_pct(dph / len(dis))})")
        out.append("- " + ("模型在分歧场更准 → 也许有微弱 edge(继续攒样本)"
                           if dmh > dph else
                           "Pinnacle 在分歧场更准 → 模型的背离是噪声,别下注它"))
    out.append("")

    out.append("## 逐场(最近 20)")
    out.append("| 日期 | 比赛 | 模型选 | 实际 | ✓ |")
    out.append("|---|---|---|---|---|")
    for r in settled[:20]:
        mp = _model_p(r)
        pick = max(range(3), key=lambda i: mp[i])
        ok = "✓" if pick == r["outcome"] else "✗"
        score = f'{r.get("home_goals","?")}-{r.get("away_goals","?")}'
        out.append(f'| {r["match_date"]} | {r["home_team"]} vs {r["away_team"]}'
                   f' | {_LABELS[pick]} {mp[pick] * 100:.0f}% '
                   f'| {_LABELS[r["outcome"]]} {score} | {ok} |')
    out.append("")
    out.append("> 诚实提醒:模型回测只有 Pinnacle ~93% 的水平,**大概率结论是"
               "「模型≈sharp、没额外 edge」**——但这本身就值钱,它告诉你别太信"
               "模型 vs 市场的那些小背离。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report model-board prediction accuracy")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--league", default=None, help="Filter to one league code")
    ap.add_argument("--out", default=None, help="Write markdown here (else stdout)")
    args = ap.parse_args(argv)

    rows = fetch_league_predictions(args.db)
    if args.league:
        rows = [r for r in rows if r["league"] == args.league]
    md = build_report(rows)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        log.info("wrote %s", args.out)
    else:
        print(md)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
