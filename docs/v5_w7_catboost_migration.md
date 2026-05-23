# V5 W7 — CatBoost production migration

_Migrates the production training/inference path from LightGBM to CatBoost.
Background: W6 ablation showed CatBoost single model beats LightGBM by -0.0033
log-loss across all three multi-season folds; ensemble stacker did not work.
This week makes that improvement available in the actual `nutmeg-train` /
`nutmeg-recommend` / `nutmeg-api` paths._

## Architectural changes

**V4Artifact** (apps/api/src/nutmeg/v4/model/persist.py):

- New field `model_type: str = "lightgbm"` — discriminator stored in metadata.json
- New field `cat_features: list[str] = []` — categorical column names CatBoost
  uses; empty for LightGBM
- `booster_home/away` field type loosened to `object` (was `lgb.Booster`)
  so it can hold a `catboost.CatBoostRegressor` too

**save_artifact** writes the right binary format:
- LightGBM → `booster_home.txt` / `booster_away.txt` (legacy)
- CatBoost  → `booster_home.cbm` / `booster_away.cbm` (binary)
- metadata.json gains `model_type` + `cat_features` keys

**load_artifact** reads metadata.json first, then dispatches the appropriate
deserializer. CatBoost is imported lazily so deployments that only need
LightGBM don't pay the catboost import cost (~250 ms).

**predict_lambdas** dispatches on `artifact.model_type`:
- CatBoost path: passes the DataFrame (with categorical columns coerced to
  string) directly to CatBoost. CatBoost handles missing values natively.
- LightGBM path: numpy array (legacy fast path).
Both clip lambdas to [0.05, 8.0] before returning.

**train.py** gains `--model {lgb,cat}`:
- Default is still `lgb` for now (conservative — existing scripts unchanged)
- `--model cat` adds `league` to feature columns + passes it as a CatBoost
  categorical, then writes the artifact with `model_type=catboost`

## Compatibility

- Old `data/v4_model/` directories (with only `.txt` boosters and no `model_type`
  in metadata.json) still load: `meta.get("model_type", "lightgbm")` defaults
  to the legacy backend.
- `recommend.py` and `/api/v4/recommend` endpoints work with either backend
  unchanged — they just call `load_artifact()` + `predict_lambdas()`.
- The /api/v4/dashboard.html is backend-agnostic.

## Verification

Production train + recommend round-trip on real data:

```
$ nutmeg-train --model cat --cutoff 2024-08-01 --out data/v4_model_cat
Training CatBoost-λ (Poisson × 2; league as categorical) ...
  best_iter home=161, away=117
Fitting temperature calibrator on validation pool ...
  fitted T = 0.900 (nll: 0.9760 → 0.9749)
Capturing team state at cutoff ...
  381 (league, team) pairs across 13 leagues
Artifact saved to: data/v4_model_cat
Total elapsed: 6.7s
```

Side-by-side lambda predictions on the 8-match demo fixture set (CatBoost vs
LightGBM, same cutoff = 2024-08-01):

| Match | cat λh | lgb λh | cat λa | lgb λa |
|-------|-------:|-------:|-------:|-------:|
| Arsenal vs Liverpool | 1.230 | 1.240 | 1.375 | 1.421 |
| Real Madrid vs Getafe | 2.274 | 2.276 | 0.788 | 0.802 |
| Inter vs Fiorentina | 1.703 | 1.704 | 0.973 | 1.013 |
| Bayern Munich vs Koln | **3.251** | 2.936 | 0.774 | 0.887 |
| Paris SG vs Nice | 2.213 | 2.388 | 0.779 | 0.937 |
| Ajax vs AZ Alkmaar | 1.752 | 1.781 | 1.113 | 1.127 |
| Porto vs Benfica | 1.542 | 1.659 | 0.962 | 1.234 |
| Leeds vs Burnley | 1.555 | 1.958 | 1.054 | 1.160 |

Note how CatBoost gives stronger home λ for Bayern vs the rest of EPL/Ligue 1
(reflecting Bundesliga league-level scoring) — exactly the league-categorical
learning we wanted.

Tests: 231/231 (227 + 4 new CatBoost e2e). The CatBoost e2e class trains a
fresh artifact + reloads + predicts in subprocess, mirroring the LightGBM
test class exactly.

## Why default is still --model lgb

Conservatism. The CatBoost path is fully working and tested, but flipping
the default would silently change every prod artifact retrained by automation.
Switching the default is a one-line change (default="lgb" → "cat" in
train.py:argparse) once we're confident:

1. The artifact size (CatBoost ~200 KB on disk vs LightGBM ~80 KB) doesn't
   cause issues in the deployment pipeline
2. The inference latency increase is acceptable (CatBoost ~5 ms vs LightGBM
   ~1 ms per batch in micro-benchmarks)
3. The W8 observation loop confirms the W6 backtest numbers hold up in
   real-time betting context

Recommend keeping default=lgb for the W8 observation period; flip in W9 if
no surprises emerge.

## Next: W8

With CatBoost available as an opt-in production option, W8 = real-bet
observation loop work proceeds against either backend. Plan to run lgb and
cat artifacts side-by-side for at least 4 weeks of real fixtures and compare
realized ROI.
