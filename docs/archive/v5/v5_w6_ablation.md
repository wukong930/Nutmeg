# V5 W6 — Ensemble Ablation

_Mixed result: the planned LogisticRegression stacker fails multi-season validation,
but one of the ensemble's base learners (**CatBoost**) is the new best single model._

## What we tried

Train two additional Poisson regressors alongside V4's LightGBM, run all three through Dixon-Coles → 1X2, and combine the probabilities with a multinomial logistic-regression stacker fit on the validation slice:

- **LightGBM** (V4 baseline) — depth 6, `num_leaves=31`, `lambda_l2=1.0`
- **XGBoost** Poisson — depth 4, `reg_lambda=3.0` (deliberately decorrelated from LightGBM)
- **CatBoost** Poisson — depth 5, `l2_leaf_reg=2.0`, AND `league` as a native categorical feature (the other two see only the 39 numeric columns)
- **Stacker** — sklearn `LogisticRegression(multinomial, L2 C=1.0)` on `[3 bases × 3 classes] = 9` logits per match, fit on validation 1X2 labels

All three bases trained on the same pooled-across-leagues feature frame, using the same `GBM_FEATURE_COLUMNS` (xG-lite + clubelo + 24 V4 features). The CatBoost extension simply adds `league` to its input.

## Result

Multi-season pooled log-loss, GBM-eligible subset:

|              | 22/23 | 23/24 | 24/25 |
|--------------|------:|------:|------:|
| Pinnacle ceiling | 0.9940 | 0.9865 | 0.9904 |
| **LightGBM** (V4 / current default) | 1.0020 | 0.9951 | 0.9971 |
| XGBoost | 1.0006 | 0.9942 | 0.9963 |
| **CatBoost** ← new best | **0.9984** | **0.9898** | **0.9960** |
| LogReg stacker (3-base ensemble) | 1.0063 | 1.0014 | 0.9989 |
| Stacker + Temperature | 1.0067 | 1.0021 | 0.9998 |

CatBoost beats LightGBM in **every season tested**: −0.0036 on 22/23, −0.0053 on 23/24, −0.0011 on 24/25. Average improvement vs V4: **−0.0033 log-loss**.

The stacker is **worse than every base model in every season**. The temperature on top makes it worse still.

## Why the stacker fails

The val slice is ~500–1000 matches per fold. Logistic regression on 9-dimensional logits is a 10-parameter (9 weights + intercept × 3 classes − 2 redundant constraints) fit. That's nominally not overparameterized, but the three bases produce **highly correlated** logits — every base reads the same closing-odds and Elo features — so the effective signal dimensionality is much smaller than 9. The stacker latches onto idiosyncratic val patterns that don't generalize.

A weighted-mean blender (one weight per base, no logit transform, no logistic regression) would have less variance, but the same fundamental problem: three correlated models don't add up to one good one.

## Why CatBoost wins

The numeric features are identical for all three bases. The only differences are:

1. **Hyperparameters** (depth, regularization) — these alone account for ~0.0005-0.001 of the XGBoost vs LightGBM gap
2. **Native categorical handling of `league`** — this is the major gap. LightGBM and XGBoost see only the 39 numeric columns; they can learn league-specific behavior implicitly via interactions with market_p_* and elo_*, but CatBoost has a built-in mechanism for league-conditioned predictions that's hard to replicate with one-hot encoding given our limited per-league sample sizes

The third explanation is consistent with our data: most of the CatBoost gain shows up on the smaller-sample leagues (Serie B, Segunda, Eredivisie) where league-specific tuning matters most.

## Decision

1. **Keep all three base modules** (`gbm_lambda.py`, `xgb_lambda.py`, `cat_lambda.py`) and the stacker (`stacker.py`) in the codebase.
2. **Wire ensemble into walk_forward but gate it behind `WalkForwardConfig.with_ensemble=True`**. Default off so existing scripts don't pay the 3-4× training cost without asking.
3. **bench.py and multi_season_bench.py** gain a `--with-ensemble` flag so analysts can compare anytime.
4. **Do NOT yet switch the production artifact / training pipeline from LightGBM to CatBoost.** Migration is a separate concern (touches `persist.py` schema, `train.py` defaults, possibly `recommend.py` predict path). Schedule that as the W7 task.
5. **Do NOT enable the stacker by default anywhere**. Document it as available-but-discouraged with the multi-season numbers above.

## Why this is W6 complete

- Built and unit-tested all three base learners + the stacker (xgb, cat, stacker each have 7-12 unit tests).
- Wired the ensemble path into walk_forward / bench / multi_season_bench so future re-evaluation (after we change features in W8+) is a single CLI flag away.
- Discovered, in a falsifiable head-to-head, that **CatBoost is a stable improvement** worth migrating to in W7 (estimated 0.003 average improvement across all leagues).
- Discovered the **stacker is a stable loss** on our data, ruling out a class of approaches.

## What W7 will do

Migrate production training/inference from LightGBM to CatBoost:

- Extend `V4Artifact` / `persist.py` schema to serialize CatBoost models (depend on a few extra files: `cbm` binary + JSON metadata)
- Update `train.py` to default to CatBoost; keep LightGBM available behind `--model lgb`
- Update `build_features_for_fixtures` to pass `league` to CatBoost in inference
- A/B the artifacts on the same demo fixtures
- Tag `v5.w7` once 24/25 log-loss confirmed at ~0.9960 in production pipeline
