"""nutmeg-sharp-consensus-eval — V14.

Read-only evaluation of the sharp-book consensus (Pinnacle + Betfair + SBOBET)
over our CACHED API-Football /odds, joined to known results. Answers, honestly:

  1. Coverage  — how many fixtures carry 1/2/3 of the sharps?
  2. Agreement — how often do the present sharps agree on the favourite, and how
                 far apart are they (max P spread)? how often does Pinnacle FLIP
                 vs the other sharps?
  3. Divergence— does the consensus fair P actually differ from Pinnacle-alone,
                 or is Pinnacle alone already the consensus?
  4. Calibration (the real test) — log-loss / Brier / hit-rate of each predictor
                 (pinnacle, betfair, sbobet, consensus) on settled fixtures, both
                 on each one's own coverage AND head-to-head on the common subset.
                 + does the favorite-flip guard fire on fixtures where Pinnacle is
                 actually MORE wrong (i.e. is the guard worth anything)?

If the consensus is NOT better calibrated than Pinnacle alone, the honest verdict
is "Pinnacle alone suffices; keep the second/third book only as a staleness guard".

    nutmeg-sharp-consensus-eval                 # print + write docs report
    nutmeg-sharp-consensus-eval --no-write      # print only
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import logging
import math
from collections import Counter
from pathlib import Path

from nutmeg.v4.model.sharp_consensus import (
    consensus,
    per_book_fair,
)

log = logging.getLogger("sharp-consensus-eval")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_OUTCOMES = ("H", "D", "A")
_FINISHED = {"FT", "AET", "PEN"}


def _resp(d) -> list:
    return d if isinstance(d, list) else (d.get("response", []) if isinstance(d, dict) else [])


def _load_results(fixtures_dir: Path) -> dict[int, int]:
    """fixture_id → outcome (0=H,1=D,2=A) from finished fixtures, 90' score."""
    out: dict[int, int] = {}
    for f in glob.glob(str(fixtures_dir / "*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
        except Exception:  # noqa: BLE001, S110
            continue
        for r in _resp(data):
            fb = r.get("fixture") or {}
            if (fb.get("status") or {}).get("short") not in _FINISHED:
                continue
            fid = fb.get("id")
            # 90' score (score.fulltime), falling back to final goals
            ft = (r.get("score") or {}).get("fulltime") or {}
            g = r.get("goals") or {}
            hg = ft.get("home") if ft.get("home") is not None else g.get("home")
            ag = ft.get("away") if ft.get("away") is not None else g.get("away")
            if fid is None or hg is None or ag is None:
                continue
            out[int(fid)] = 0 if hg > ag else (1 if hg == ag else 2)
    return out


def _iter_odds(odds_dir: Path):
    """Yield (fixture_id, envelope) for envelopes that carry any bookmaker."""
    for f in glob.glob(str(odds_dir / "*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
        except Exception:  # noqa: BLE001, S110
            continue
        for r in _resp(data):
            if not r.get("bookmakers"):
                continue
            fid = (r.get("fixture") or {}).get("id") or r.get("id")
            if fid is not None:
                yield int(fid), r


def _logloss(p: dict[str, float], outcome: int) -> float:
    return -math.log(max(p[_OUTCOMES[outcome]], 1e-9))


def _brier(p: dict[str, float], outcome: int) -> float:
    return sum((p[_OUTCOMES[i]] - (1.0 if i == outcome else 0.0)) ** 2 for i in range(3))


def _hit(p: dict[str, float], outcome: int) -> bool:
    return max(range(3), key=lambda i: p[_OUTCOMES[i]]) == outcome


def _score(samples: list[tuple[dict[str, float], int]]) -> dict[str, float]:
    """samples = list of (fair_P, outcome) → {n, log_loss, brier, hit_rate}."""
    n = len(samples)
    if n == 0:
        return {"n": 0, "log_loss": float("nan"), "brier": float("nan"), "hit_rate": float("nan")}
    return {
        "n": n,
        "log_loss": sum(_logloss(p, o) for p, o in samples) / n,
        "brier": sum(_brier(p, o) for p, o in samples) / n,
        "hit_rate": sum(_hit(p, o) for p, o in samples) / n,
    }


def build_report(rows: list[dict], results: dict[int, int]) -> str:
    """rows = [{fid, by_book, cons(Consensus)}]; returns a Markdown report."""
    n_total = len(rows)
    cov = Counter(r["cons"].n_books for r in rows)
    multi = [r for r in rows if r["cons"].n_books >= 2]
    agree = sum(1 for r in multi if r["cons"].argmax_agree)
    flips = sum(1 for r in multi if r["cons"].pinnacle_flip)
    spreads = sorted(r["cons"].max_spread for r in multi)

    def _pct(x: float) -> str:
        return "—" if not spreads else f"{x*100:.1f}pp"

    md: list[str] = []
    md.append("# Sharp 共识评估 (Pinnacle + Betfair + SBOBET)\n")
    md.append("只读测量,基于已缓存的 API-Football /odds(同一信封内的多家盘口,零额外 API 调用)。\n")

    md.append("## 1. 覆盖率\n")
    md.append(f"- 有盘口的 fixture: **{n_total}**\n")
    for n in (3, 2, 1, 0):
        md.append(f"  - 含 {n} 家 sharp: {cov.get(n, 0)} ({cov.get(n,0)/max(n_total,1)*100:.0f}%)\n")  # noqa: E501

    md.append("\n## 2. 一致性 (≥2 家 sharp 的 fixture)\n")
    if multi:
        md.append(f"- 样本: {len(multi)}\n")
        md.append(f"- **argmax(热门)一致率: {agree/len(multi)*100:.1f}%**\n")
        mid = spreads[len(spreads)//2]
        p90 = spreads[int(len(spreads)*0.9)]
        md.append(f"- sharp 间最大概率价差: 中位 {_pct(mid)} · 90 分位 {_pct(p90)}\n")
        md.append(f"- **Pinnacle 与其它 sharp 翻转(favorite-flip): {flips} 场 ({flips/len(multi)*100:.1f}%)**\n")  # noqa: E501
    else:
        md.append("- (无 ≥2 家 sharp 的 fixture)\n")

    # divergence consensus vs pinnacle-alone
    dvg = [r for r in rows if "pinnacle" in r["by_book"] and r["cons"].consensus]
    if dvg:
        diffs = [sum(abs(r["cons"].consensus[k] - r["by_book"]["pinnacle"][k]) for k in _OUTCOMES) / 3  # noqa: E501
                 for r in dvg]
        argdiff = sum(1 for r in dvg
                      if max(_OUTCOMES, key=lambda k: r["cons"].consensus[k])
                      != max(_OUTCOMES, key=lambda k: r["by_book"]["pinnacle"][k]))
        md.append("\n## 3. 共识 vs 仅 Pinnacle\n")
        md.append(f"- 平均每结果概率差: **{sum(diffs)/len(diffs)*100:.2f}pp**\n")
        md.append(f"- 共识与 Pinnacle 的 argmax 不同: {argdiff} 场 ({argdiff/len(dvg)*100:.1f}%)\n")

    # calibration
    md.append("\n## 4. 校准 (对已结算赛果)\n")
    preds = {
        "pinnacle": lambda r: r["by_book"].get("pinnacle"),
        "betfair": lambda r: r["by_book"].get("betfair"),
        "sbobet": lambda r: r["by_book"].get("sbobet"),
        "consensus": lambda r: r["cons"].consensus,
    }
    settled = [r for r in rows if r["fid"] in results]
    md.append(f"- 可对赛果的 fixture: **{len(settled)}**\n")
    md.append("\n### 4a. 各预测器(自身覆盖范围)\n")
    md.append("| 预测器 | n | log-loss↓ | Brier↓ | 命中率↑ |\n|---|---|---|---|---|\n")
    for name, fn in preds.items():
        s = _score([(fn(r), results[r["fid"]]) for r in settled if fn(r)])
        md.append(f"| {name} | {s['n']} | {s['log_loss']:.4f} | {s['brier']:.4f} | {s['hit_rate']*100:.1f}% |\n")  # noqa: E501

    # head-to-head on the common subset (all 3 sharps present + result)
    common = [r for r in settled if r["cons"].n_books == 3]
    md.append(f"\n### 4b. 同口径对比 (3 家齐全 + 有赛果, n={len(common)})\n")
    md.append("| 预测器 | log-loss↓ | Brier↓ | 命中率↑ |\n|---|---|---|---|\n")
    for name, fn in preds.items():
        s = _score([(fn(r), results[r["fid"]]) for r in common if fn(r)])
        md.append(f"| {name} | {s['log_loss']:.4f} | {s['brier']:.4f} | {s['hit_rate']*100:.1f}% |\n")  # noqa: E501

    # guard validation: is Pinnacle worse on flip fixtures?
    flip_settled = [r for r in settled if r["cons"].pinnacle_flip and r["by_book"].get("pinnacle")]
    noflip_settled = [r for r in settled
                      if r["cons"].n_books >= 2 and not r["cons"].pinnacle_flip
                      and r["by_book"].get("pinnacle")]
    md.append("\n### 4c. 翻转守卫是否抓到了更差的 Pinnacle 线?\n")
    sf = _score([(r["by_book"]["pinnacle"], results[r["fid"]]) for r in flip_settled])
    sn = _score([(r["by_book"]["pinnacle"], results[r["fid"]]) for r in noflip_settled])
    md.append("| Pinnacle 子集 | n | log-loss↓ | 命中率↑ |\n|---|---|---|---|\n")
    md.append(f"| 翻转(被守卫标记) | {sf['n']} | {sf['log_loss']:.4f} | {sf['hit_rate']*100:.1f}% |\n")  # noqa: E501
    md.append(f"| 未翻转 | {sn['n']} | {sn['log_loss']:.4f} | {sn['hit_rate']*100:.1f}% |\n")
    md.append("\n> 守卫有效 ⟺ 翻转子集的 Pinnacle log-loss 明显更高(线更差),"
              "说明分歧确实标出了不可信的 Pinnacle 线。\n")
    return "".join(md)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the sharp-book consensus vs Pinnacle-alone")
    ap.add_argument("--cache-dir", default="data/external/api_football")
    ap.add_argument("--out-dir", default="docs")
    ap.add_argument("--no-write", action="store_true", help="Print only, don't write the report")
    args = ap.parse_args(argv)

    cache = Path(args.cache_dir)
    log.info("loading results …")
    results = _load_results(cache / "_fixtures")
    log.info("loaded %d finished fixtures", len(results))

    rows: list[dict] = []
    for fid, env in _iter_odds(cache / "_odds"):
        by = per_book_fair(env)
        if not by:
            continue
        rows.append({"fid": fid, "by_book": by, "cons": consensus(by)})
    log.info("processed %d fixtures with ≥1 sharp book", len(rows))

    report = build_report(rows, results)
    print("\n" + report)
    if not args.no_write:
        out = Path(args.out_dir) / f"sharp_consensus_eval_{dt.date.today().isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        log.info("wrote %s", out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
