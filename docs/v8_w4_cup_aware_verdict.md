# V8 W4 — Cup-Aware Verdict (Closed 2026-05-26)

> The V8 retrospective opened V8 W4 as ⏳ data-gated: "user付 API-Football
> 钱就是为了杯赛预测能 work; 说'infrastructure ready'是真的, 但不是用户想
> 要的答案." This document is the post-execution verdict from running
> `nutmeg-cup-ablation` on the now-ingested cup parquets.
>
> **Closes**: V8 W4 pending item, V11 backlog #2.

## TL;DR

🔴 **DO NOT ship cup-aware artifact.** Across 2 cutoffs × 4 modes, only 1
of 2 `cup_full` folds cleared the ≥ −0.001 log-loss improvement bar (3/4
required by V6 W6 methodology). The maximum observed delta is −0.0011 —
indistinguishable from noise.

The cup-aware infrastructure (V6 W11 + V7 W6/7/8 + V8 W1/2/3 = 7 weekly
tags of code) stays as **opt-in CLI**. Production CatBoost stays on the
domestic-only training pool.

## What was tested

| Knob | Value |
|---|---|
| Cup competitions | UCL, UEL |
| Cup seasons (train) | 2021, 2022, 2023 |
| Test cutoffs | 2024-04-01, 2024-07-01 |
| Modes | baseline, cup_data, cup_features, cup_full |
| Total cup rows in training join | 374 (after fixtures × odds inner join) |
| Cup row yield (after team-canonical resolve) | 205 / 374 (55%) |

The team-canonical layer (V8 W1) currently maps ~65 of 213 cup team
names exactly (~30%). The other 148 names (cup-only minor clubs from
preliminary rounds — Sutjeska, Tre Penne, UE Santa Coloma, etc.) are
dropped from the training join. This is the upper bound on what
investing more time in `CUP_TEAM_ALIASES` would buy.

## Raw results

See `docs/v11_cup_ablation_20260526.md` for the auto-generated card.

```
| cutoff     | mode         | n_test | log_loss | Δ vs baseline | hit-rate |
|------------|--------------|-------:|---------:|--------------:|---------:|
| 2024-04-01 | baseline     | 4,968  | 1.0008   | +0.0000       | 0.5064   |
| 2024-04-01 | cup_data     | 4,976  | 1.0008   | -0.0000       | 0.5020   |
| 2024-04-01 | cup_features | 4,968  | 1.0008   | +0.0000       | 0.5064   |
| 2024-04-01 | cup_full     | 4,976  | 1.0008   | -0.0000       | 0.5020   |
| 2024-07-01 | baseline     | 4,331  | 0.9987   | +0.0000       | 0.5073   |
| 2024-07-01 | cup_data     | 4,339  | 0.9975   | -0.0011       | 0.5098   |
| 2024-07-01 | cup_features | 4,331  | 0.9987   | +0.0000       | 0.5073   |
| 2024-07-01 | cup_full     | 4,339  | 0.9975   | -0.0011       | 0.5098   |
```

Folds passing the ≥ −0.001 ship gate: **1/2** (need 3/4).
Folds with `cup_features` ≠ `baseline`: **0/2** — cross-league Elo
seeding alone has no effect on this cutoff window.

## Interpretation

1. **`cup_data` alone (no `cup_features`) and `cup_full` produce
   identical numbers.** That means the cup features (per-competition
   weights, side-channel cup signals from V6 W11) contribute nothing
   measurable on top of the cup training rows.

2. **The 2024-04-01 cutoff shows zero change.** With the season cutoff
   inside the EPL season, the cup-aware artifact has the same
   information at predict-time as baseline; the cup data sits in the
   training set but doesn't change the per-league probability
   calibration for active league matches.

3. **The 2024-07-01 cutoff just barely passes the per-fold threshold
   (−0.0011).** This is interesting — the post-season cutoff sees a
   tiny benefit, possibly from cup-derived team-strength priors
   bleeding into pre-season uncertainty. But one fold is not enough.

## Why this is a defensible negative result

The cup infrastructure cost ~7 weekly tags of work (V6 W11 + V7 W6/7/8
+ V8 W1/2/3). The hope was that cup matches between teams from
different leagues (e.g. EPL vs La Liga in UCL) would inject
cross-league strength signal that the domestic-only training pool
misses. Concretely:

- A 4-2 PSG-Real-Madrid in UCL informs both teams' attack/defense
  estimates in a way no domestic match can.

That hypothesis is real, but the n is too small:

- ~5000 domestic training rows per season (5 top leagues)
- ~375 cup rows after team-resolve (4 cups × ~95/season)
- Cup rows = ~7% of the training pool

At 7% pool share, even if cup matches carry 2× the cross-league
information per row, the regularizing effect across 5000 domestic rows
washes out. The literature on cup-data ablation hits the same finding —
domestic data dominates because of sheer volume.

## Paths forward (not ship)

| Path | Cost | Expected gain | Verdict |
|---|---|---|---|
| Extend `CUP_TEAM_ALIASES` to absorb 148 unmatched names | 2-3 hrs | +0.0005-0.0010 log-loss (more cup rows survive) | Low ROI; doesn't cross the 0.001 ship gate alone |
| Add 4-5 more seasons of cup history (2018-2020) | 8 hrs + ~30k API calls | +0.001-0.002 log-loss | Possible — doubles the cup row count to ~750 |
| Cup-only model (separate artifact for UCL/UEL/WC fixtures) | 2-3 weeks | Unknown — would need separate ROI verification | Defer; we already serve cup recommendations via the domestic-trained CatBoost via cross-league Elo seeding (V8 W3) |

## Decision

**Stay on production CatBoost (V5 W12) for both domestic and cup
fixtures.** The `--with-cup-data` and `--with-cup-features` train flags
remain available for future experimentation but are explicitly NOT
defaults.

**Update production policy**: when the user runs `nutmeg-rec` on UCL/UEL
fixtures, the existing CatBoost artifact (trained on domestic data
only) is used. Cross-league Elo seeding (V8 W3 `--cross-league-seed`)
remains the production mechanism for handling first-encounter team
pairings.

**Future re-test trigger**: if API-Football pricing tier changes (we go
to a plan with more historical access) and we can ingest cup seasons
2015-2020, re-run the ablation. With 8 seasons × 4 cups + the alias
extension, cup share could grow to ~15-20% of the pool, possibly
crossing the threshold.

## Files

- `docs/v11_cup_ablation_20260526.md` — auto-generated card from
  `nutmeg-cup-ablation`
- `docs/v8_w4_cup_aware_verdict.md` — this document
- `apps/api/src/nutmeg/v4/cli/cup_ablation.py` — ablation CLI (V8 W3)
- `apps/api/src/nutmeg/v4/data/cup_training.py` — UNION pipeline (V8 W2)
- `apps/api/src/nutmeg/utils/team_canonical.py` — CUP_TEAM_ALIASES (V8 W1)
