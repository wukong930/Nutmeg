# The Odds API — unused-market evaluation (2026-06-11)

Measure-first audit of which Pinnacle markets The Odds API exposes that we **don't
use**, and whether they add information beyond our 1X2 + O/U Dixon-Coles grid fit.
Sample: World Cup fixtures, pre-tournament, Pinnacle `eu` region.

## Verdict: all three unused markets are REDUNDANT — nothing to build

| Market | Grid vs Pinnacle gap | Verdict |
|---|---|---|
| `team_totals` (per-team scoring) | **0.55pp** | 🟢 redundant — grid already reproduces it |
| `alternate_totals` (full O/U ladder) | ≤ **1.5pp** | 🟢 redundant — single O/U line already pins the total curve |
| `alternate_spreads` (full AH ladder) | **0.95pp** (true half-lines) | 🟢 redundant — grid already reproduces it |

The grid fit from 1X2 + the main O/U line already reproduces every one of these. This is
consistent with the whole project's finding: Pinnacle's markets are mutually coherent and
Dixon-Coles already captures them. Don't fit to any of this extra data.

## ⚠️ Lesson — the "4pp WC handicap anomaly" was a MEASUREMENT BUG

A first pass reported a ~4.1pp WC Asian-Handicap gap and a long chase followed (claimed it
was real margin info, a "Dixon-Coles wall", tried an AH-into-fit, ran NB and max-entropy
diagnostics). **It was all a bug in the eval, not a real signal.**

Two mistakes, compounding:

1. **Wrong half-line filter.** `(L*2) % 2` is truthy for QUARTER lines too (−2.25 → −4.5,
   `% 2 == 1.5`), so quarter lines (−2.25, −1.75, −1.25, −0.75, −0.25) were treated as half
   lines. Correct test for a TRUE half line: `L*2` is an odd **integer**.
2. **Wrong cover function on quarters.** `dc_home_cover_prob(grid, L)` is half-line only
   (strict `margin + L > 0`), so on a quarter line it evaluates the CEILING (−2.25 → P(margin
   ≥ 3), i.e. the −2.5 value) while the market de-vig is the Asian split (avg of −2.0 and
   −2.5). That ~half-line mismatch manufactured a **5.63pp artifact** on quarter lines.

The reported "4.08pp" was the mix (156 true half-lines @ 0.95pp + 317 quarter lines @
5.63pp). On true half-lines alone the gap is **0.95pp** — redundant, same as clubs.

The downstream "DC wall (3.66pp)", "NB can't beat it (3.81pp)", and "max-entropy floor
(3.62pp)" results were all re-measuring the SAME artifact (quarter lines compared against a
half-line cover function), not a real incoherence.

**Engineering rule for any future AH-vs-grid comparison:** filter to true half-lines
(`L*2` odd integer) and/or use a quarter-capable Asian cover (the handicap analogue of
`asian_total_over_prob`); never compare `dc_home_cover_prob` against a de-vig'd quarter line.

## What actually shipped

Nothing model-side. The AH-into-fit engine change was built, measured (it didn't help —
because there was no real gap), and **reverted**. `market_handicap.py` is unchanged from
HEAD. The win here is process: measure-first + revert-before-ship caught a plausible-looking
phantom before any of it reached production.

(Earlier-shipped, real wins this run: odds_snapshots CLV foundation, The Odds API fresher
Pinnacle line, settlement orphan-rescue, raw-Pinnacle-line display.)
