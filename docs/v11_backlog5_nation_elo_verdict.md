# V11 Backlog #5 — National-team Elo Integration Verdict

> Closes the original audit Gap 3: *"V8 W7 ship 了 68 国 Elo 数据层 + ingest
> CLI, 但 build_elo_features 当前对 WC / Euro / Copa America 行 fallback 到
> 'unknown team' (1500 默认)."*

## TL;DR

⚪ **TIE on the league test set** — wiring `nation_state` through the
walk-forward harness produces identical numbers to the prior cup
ablation, because the test set is domestic-league fixtures and
nation-Elo only affects national-team-cup *training rows* that never
appear in the test.

The integration is now **fully end-to-end** at every layer of the stack
(feature builder → walk-forward → CLI). Future re-tests on a
national-team-cup test set (WC 2026 walk-forward, EURO 2024 holdouts)
will be a one-flag change.

## What was missing before this patch

Per `docs/post_v9_p1_12_national_elo_integration.md`, the integration
was wired at:

- ✅ `seed_elo_value` → accepts `nation_state` + `is_national_team_league`
- ✅ `build_elo_features` → passes both correctly
- ✅ `build_feature_frame` → threads `nation_state` through
- ✅ `nutmeg-train --nation-elo-cache-dir` → CLI flag exists

**But the multi-fold ablation harness (`WalkForwardConfig`,
`cup_ablation`) didn't expose `nation_state`.** So even when the cup
ablation ran with `cross_league_seed=True`, the national-team-cup
rows in the training pool still fell back to 1500 — the very thing
P1#4 was meant to fix in feature-builder code but never made it to
the ablation pathway.

## What this patch ships

| Layer | Change |
|---|---|
| `WalkForwardConfig` | new `nation_state` field (default `None`) |
| `run_walk_forward` | threads `nation_state` to `build_feature_frame` |
| `nutmeg-cup-ablation` | new `--nation-elo-cache-dir` flag; builds lookup once + passes through |
| `tests/v4/test_walk_forward_nation_elo.py` | 6 structural tests |

## Verdict on the test set

Ran the cup ablation **with** `--nation-elo-cache-dir
data/external/clubelo_national` (68 nation parquets, V8 W7 + P1#10
ingest):

```
| cutoff     | mode     | n_test | log_loss | Δ vs baseline | hit-rate |
|------------|----------|-------:|---------:|--------------:|---------:|
| 2024-04-01 | baseline | 4,968  | 1.0008   | +0.0000       | 0.5064   |
| 2024-04-01 | cup_full | 4,976  | 1.0008   | -0.0000       | 0.5020   |
| 2024-07-01 | baseline | 4,331  | 0.9987   | +0.0000       | 0.5073   |
| 2024-07-01 | cup_full | 4,339  | 0.9975   | -0.0011       | 0.5098   |
```

**Identical numbers** to the prior cup-only ablation
(`docs/v11_cup_ablation_20260526.md`). Per V6 W6 methodology this is
still 1/2 folds passing the ship gate, same negative verdict as cup
ablation alone.

## Why this is expected (not a failure)

The test set is **domestic-league fixtures** (EPL / La Liga / Serie A
/ Bundesliga / Ligue 1). Nation Elo lookup only affects:

1. `state["WC"]["Brazil"]` initialization — Brazil's Elo seeded from
   clubelo's per-nation history instead of 1500
2. `state["EURO"]["France"]`, etc.

But the GBM learns probabilities for *league fixtures*. The training
loss surface sees ~5000 domestic rows + ~205 resolved cup-club rows
(no national-team rows under the current `--cup-leagues UCL,UEL`
config). Even if we expanded to `--cup-leagues WC,EURO,COPA_AMERICA`,
the national-team rows would still be:

- ~128 WC matches per cycle × 2 cycles = 256
- ~51 EURO matches per cycle × 2 cycles = 102
- ~30 Copa America × 2 = 60

→ ~400 national-team rows on a ~5400-row training pool = 7.4%. Same
ballpark as the cup-club share. **Same null effect on domestic
predictions, expected.**

## When nation_state DOES matter (not tested here)

The infrastructure ships ready for two future use cases:

1. **WC 2026 walk-forward with a national-team test set.** The V10 W1
   Track B path already trains a dedicated `NationalTeamModel` with
   its own Elo snapshot mechanism — that's a parallel code path that
   doesn't go through `build_elo_features`. If we ever want to unify
   the two (one CatBoost artifact trained on UNION of league + cup +
   national-team rows, predicting both domains), the `nation_state`
   plumbing is now ready.

2. **Cup-aware artifact extension to national-team competitions.**
   Currently `nutmeg-cup-ablation --cup-leagues` defaults to `UCL,UEL`
   (club competitions). If we added `WC,EURO,COPA_AMERICA` to the
   training UNION + tested on those competitions, the per-nation
   priors would matter. This is a future ablation, not in scope here.

## What does NOT change

- **Production CatBoost artifact** stays as V5 W12 default. Not
  retrained.
- **WC 2026 predict path** unchanged. It uses `build_wc_training_frame`
  + per-season Elo snapshots independently of `nation_state`.
- **Today recommendations** behavior unchanged. Domestic predictions
  see no nation Elo (they never did and shouldn't).

## Closes

- Original V11 audit Gap 3 ("National-team Elo 没有接入模型") — **now**
  fully integrated at every layer; the prior P1#12 only wired the
  feature-builder layer, this patch closes the ablation-harness layer.
- V8 W7's open follow-up "model integration" — see post-v9 P1#12 +
  this patch together.

## Files

- `apps/api/src/nutmeg/v4/eval/walk_forward.py` — new `nation_state`
  field on `WalkForwardConfig`
- `apps/api/src/nutmeg/v4/cli/cup_ablation.py` — new
  `--nation-elo-cache-dir` flag + `nation_state` parameter on
  `run_one_fold`
- `tests/v4/test_walk_forward_nation_elo.py` — 6 structural tests
- `docs/v11_nation_elo_ablation_20260526.md` — auto-generated card
  showing the (expected) zero delta on league test
- `docs/v11_backlog5_nation_elo_verdict.md` — this doc
