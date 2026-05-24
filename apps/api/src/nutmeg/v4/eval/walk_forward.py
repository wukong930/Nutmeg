"""Walk-forward evaluation with time-strict splits.

Pass 1: per-league fit + predict for MLE DC; per-league predict for GBM (after pooled GBM train)
Pass 2: pool validation samples → fit global temperature → apply to test
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nutmeg.v4.calibration import fit_temperature_1x2
from nutmeg.v4.calibration.per_league import fit_per_league_temperature
from nutmeg.v4.eval.baselines import pinnacle_baseline, uniform_baseline
from nutmeg.v4.eval.metrics import summary
from nutmeg.v4.features import GBM_FEATURE_COLUMNS, build_feature_frame
from nutmeg.v4.model.cat_lambda import fit_cat_lambda
from nutmeg.v4.model.dc_mle import fit_dixon_coles, predict_lambdas
from nutmeg.v4.model.dixon_coles import lambdas_to_1x2_array
from nutmeg.v4.model.gbm_lambda import fit_gbm_lambda
from nutmeg.v4.model.stacker import fit_stacker
from nutmeg.v4.model.xgb_lambda import fit_xgb_lambda


@dataclass
class WalkForwardConfig:
    train_window_days: int = 540
    validation_window_days: int = 90
    test_cutoff: pd.Timestamp = pd.Timestamp("2024-08-01")
    test_horizon_days: int = 400
    leagues: tuple[str, ...] = (
        "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
        "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
        "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
        "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA", "JPN_J1",
    )
    min_train_matches: int = 100
    gbm_rho: float = -0.10   # tau correction for DC after GBM lambdas
    # V5 W6: when True, also train XGBoost + CatBoost bases + stacker.
    # The extra training adds ~30-60s per fold.
    with_ensemble: bool = False
    # V8 W3: pass-through to build_feature_frame for cup-data ablation.
    # cup_history_df adds the 5 W11 side-channel cup feature cols;
    # cross_league_seed lets cup-row Elo/form draw on the team's
    # domestic-league history (the right setting when training with
    # --with-cup-data UNION rows).
    cup_history_df: pd.DataFrame | None = None
    cross_league_seed: bool = False


def _three_way_split(df: pd.DataFrame, cfg: WalkForwardConfig, league: str):
    league_df = df[df.league == league]
    val_start = cfg.test_cutoff - pd.Timedelta(days=cfg.validation_window_days)
    train_start = cfg.test_cutoff - pd.Timedelta(days=cfg.train_window_days)
    test_end = cfg.test_cutoff + pd.Timedelta(days=cfg.test_horizon_days)
    train = league_df[(league_df.date >= train_start) & (league_df.date < val_start)].copy()
    val = league_df[(league_df.date >= val_start) & (league_df.date < cfg.test_cutoff)].copy()
    test = league_df[(league_df.date >= cfg.test_cutoff) & (league_df.date < test_end)].copy()
    return train, val, test


def _mle_dc_fit_predict(train, fixtures, cutoff):
    params = fit_dixon_coles(train, as_of=cutoff)
    if len(fixtures) == 0:
        return np.empty((0, 3)), params
    lambdas = predict_lambdas(fixtures, params)
    probs = lambdas_to_1x2_array(lambdas, rho=params.rho)
    return probs, params


def run_walk_forward(df: pd.DataFrame, cfg: WalkForwardConfig | None = None) -> dict:
    """Run benchmark for Pinnacle / uniform / MLE DC / MLE DC + Temp / GBM-λ + DC / GBM-λ + DC + Temp."""
    cfg = cfg or WalkForwardConfig()

    # ---- Build features ONCE on full df (no leakage; pure per-row transforms /
    # rolling state that walks forward in time) ----
    feats = build_feature_frame(
        df,
        cup_history_df=cfg.cup_history_df,
        cross_league_seed=cfg.cross_league_seed,
    )

    # ---- Per-league MLE DC (legacy comparison) ----
    per_league_data = []
    for league in cfg.leagues:
        train, val, test = _three_way_split(feats, cfg, league)
        if len(train) < cfg.min_train_matches or len(test) == 0:
            continue
        test = test[test.psc_home.notna()].copy()
        if len(test) == 0:
            continue

        probs_mle_test, _ = _mle_dc_fit_predict(train, test, cfg.test_cutoff)
        probs_mle_val = np.empty((0, 3))
        if len(val) > 0:
            probs_mle_val, _ = _mle_dc_fit_predict(train, val, cfg.test_cutoff)

        per_league_data.append({
            "league": league,
            "train": train,
            "val": val,
            "test": test,
            "probs_mle_val": probs_mle_val,
            "probs_mle_test": probs_mle_test,
        })

    if not per_league_data:
        return {"per_league": [], "pooled": {}}

    # ---- Pooled GBM-λ across ALL leagues (one model) ----
    train_pool = pd.concat([d["train"] for d in per_league_data], ignore_index=True)
    val_pool = pd.concat([d["val"] for d in per_league_data if len(d["val"]) > 0], ignore_index=True)
    train_pool = train_pool[train_pool.psc_home.notna()].copy()
    val_pool = val_pool[val_pool.psc_home.notna()].copy()
    gbm = fit_gbm_lambda(train_pool, val_pool, feature_cols=GBM_FEATURE_COLUMNS)

    # ---- V5 W6 ensemble: also train XGBoost + CatBoost on same pool ----
    xgb_model = None
    cat_model = None
    if cfg.with_ensemble:
        xgb_model = fit_xgb_lambda(train_pool, val_pool, feature_cols=GBM_FEATURE_COLUMNS)
        # CatBoost gets `league` as a categorical feature in addition to the
        # numeric GBM_FEATURE_COLUMNS — keeps the base meaningfully different.
        cat_feature_cols = list(GBM_FEATURE_COLUMNS) + ["league"]
        cat_model = fit_cat_lambda(
            train_pool, val_pool, feature_cols=cat_feature_cols, cat_features=["league"],
        )

    # Apply GBM to each league's val+test
    for d in per_league_data:
        test_clean = d["test"].dropna(subset=GBM_FEATURE_COLUMNS).copy()
        val_clean = d["val"].dropna(subset=GBM_FEATURE_COLUMNS).copy()
        if len(test_clean) == 0:
            d["probs_gbm_test"] = np.empty((0, 3))
            d["probs_gbm_val"] = np.empty((0, 3))
            d["test_gbm_aligned"] = test_clean
            d["val_gbm_aligned"] = val_clean
            continue
        lambdas_test = gbm.predict(test_clean)
        d["probs_gbm_test"] = lambdas_to_1x2_array(lambdas_test, rho=cfg.gbm_rho)
        d["test_gbm_aligned"] = test_clean
        if len(val_clean) > 0:
            lambdas_val = gbm.predict(val_clean)
            d["probs_gbm_val"] = lambdas_to_1x2_array(lambdas_val, rho=cfg.gbm_rho)
        else:
            d["probs_gbm_val"] = np.empty((0, 3))
        d["val_gbm_aligned"] = val_clean

        # V5 W6: predict with xgb + cat on the same clean rows
        if cfg.with_ensemble and xgb_model is not None and cat_model is not None:
            lam_xgb_t = xgb_model.predict(test_clean)
            d["probs_xgb_test"] = lambdas_to_1x2_array(lam_xgb_t, rho=cfg.gbm_rho)
            lam_cat_t = cat_model.predict(test_clean)
            d["probs_cat_test"] = lambdas_to_1x2_array(lam_cat_t, rho=cfg.gbm_rho)
            if len(val_clean) > 0:
                d["probs_xgb_val"] = lambdas_to_1x2_array(
                    xgb_model.predict(val_clean), rho=cfg.gbm_rho
                )
                d["probs_cat_val"] = lambdas_to_1x2_array(
                    cat_model.predict(val_clean), rho=cfg.gbm_rho
                )
            else:
                d["probs_xgb_val"] = np.empty((0, 3))
                d["probs_cat_val"] = np.empty((0, 3))

    # ---- Fit global temperature on validation predictions (one calibrator per model) ----
    # MLE-DC calibrator
    mle_val_probs = np.vstack([d["probs_mle_val"] for d in per_league_data if len(d["probs_mle_val"]) > 0])
    mle_val_labels = np.concatenate([d["val"].result_1x2.values for d in per_league_data if len(d["probs_mle_val"]) > 0])
    cal_mle = fit_temperature_1x2(mle_val_probs, mle_val_labels) if len(mle_val_probs) >= 100 else None

    # GBM calibrator
    gbm_val_probs = np.vstack([d["probs_gbm_val"] for d in per_league_data if len(d["probs_gbm_val"]) > 0])
    gbm_val_labels = np.concatenate([
        d["val_gbm_aligned"].result_1x2.values for d in per_league_data if len(d["probs_gbm_val"]) > 0
    ])
    # V5 W9: also concatenate the league per row so per-league T can be fit
    gbm_val_leagues = np.concatenate([
        np.array([d["league"]] * len(d["probs_gbm_val"]))
        for d in per_league_data if len(d["probs_gbm_val"]) > 0
    ]) if any(len(d["probs_gbm_val"]) > 0 for d in per_league_data) else np.array([])
    cal_gbm = fit_temperature_1x2(gbm_val_probs, gbm_val_labels) if len(gbm_val_probs) >= 100 else None
    cal_gbm_pl = (
        # The 90-day val window in WalkForwardConfig leaves ~30-50 GBM-eligible
        # matches per league — far below the 800-sample theoretical threshold.
        # We lower to 30 (the same minimum used by fit_temperature_1x2 itself)
        # so per-league T runs against ALL leagues with any val data; the
        # cfg.validation_window_days could be raised in production for richer
        # per-league fits, but for bench parity we keep the 90-day window.
        fit_per_league_temperature(
            gbm_val_probs, gbm_val_labels, gbm_val_leagues, min_samples=30
        )
        if len(gbm_val_probs) >= 100 else None
    )

    # V5 W6 ensemble calibrators (stacker fits on val OOF, then temperature on val ensemble probs)
    stacker = None
    cal_ensemble = None
    if cfg.with_ensemble:
        xgb_val_probs = np.vstack(
            [d.get("probs_xgb_val", np.empty((0, 3))) for d in per_league_data
             if len(d.get("probs_xgb_val", np.empty((0, 3)))) > 0]
        )
        cat_val_probs = np.vstack(
            [d.get("probs_cat_val", np.empty((0, 3))) for d in per_league_data
             if len(d.get("probs_cat_val", np.empty((0, 3)))) > 0]
        )
        # All three base predictions must align on the same set of val rows
        # (we used val_gbm_aligned for all three above, so this holds)
        if (
            len(gbm_val_probs) >= 100
            and len(xgb_val_probs) == len(gbm_val_probs)
            and len(cat_val_probs) == len(gbm_val_probs)
        ):
            stacker = fit_stacker(
                [gbm_val_probs, xgb_val_probs, cat_val_probs], gbm_val_labels
            )
            # Use stacker on the same val data to fit ensemble temperature
            ens_val_probs = stacker.predict(
                [gbm_val_probs, xgb_val_probs, cat_val_probs]
            )
            cal_ensemble = fit_temperature_1x2(ens_val_probs, gbm_val_labels)

    # ---- Build report ----
    per_league = []
    all_pin, all_uni = [], []
    all_mle, all_mle_t = [], []
    all_gbm, all_gbm_t = [], []
    all_gbm_pl_t = []   # V5 W9: per-league temperature
    all_xgb, all_cat = [], []
    all_ens, all_ens_t = [], []
    all_y_full, all_y_gbm = [], []

    for d in per_league_data:
        test = d["test"]
        test_gbm = d["test_gbm_aligned"]
        y_full = test.result_1x2.values
        y_gbm = test_gbm.result_1x2.values

        pin = pinnacle_baseline(test)
        uni = uniform_baseline(len(test))
        probs_mle = d["probs_mle_test"]
        probs_mle_t = cal_mle.predict(probs_mle) if cal_mle is not None else probs_mle
        probs_gbm = d["probs_gbm_test"]
        probs_gbm_t = cal_gbm.predict(probs_gbm) if (cal_gbm is not None and len(probs_gbm) > 0) else probs_gbm
        # V5 W9: per-league T applied to this league's test slice
        probs_gbm_pl_t = (
            cal_gbm_pl.predict(probs_gbm, [d["league"]] * len(probs_gbm))
            if (cal_gbm_pl is not None and len(probs_gbm) > 0)
            else probs_gbm
        )

        # Pinnacle on the GBM-aligned subset (for apples-to-apples GBM vs Pinnacle)
        pin_gbm = pinnacle_baseline(test_gbm)

        # V5 W6 ensemble — only when feature flag on AND we have all three bases
        probs_xgb = d.get("probs_xgb_test")
        probs_cat = d.get("probs_cat_test")
        probs_ens = None
        probs_ens_t = None
        if (
            cfg.with_ensemble
            and stacker is not None
            and probs_xgb is not None
            and probs_cat is not None
            and len(probs_gbm) > 0
        ):
            probs_ens = stacker.predict([probs_gbm, probs_xgb, probs_cat])
            probs_ens_t = (
                cal_ensemble.predict(probs_ens) if cal_ensemble is not None else probs_ens
            )

        league_row = {
            "league": d["league"],
            "test_n": len(test),
            "test_n_gbm": len(test_gbm),
            "pinnacle":      summary(pin, y_full),
            "pinnacle_gbm":  summary(pin_gbm, y_gbm) if len(test_gbm) > 0 else None,
            "uniform":       summary(uni, y_full),
            "mle_dc":        summary(probs_mle, y_full),
            "mle_dc_temp":   summary(probs_mle_t, y_full) if cal_mle else None,
            "gbm_dc":        summary(probs_gbm, y_gbm) if len(probs_gbm) > 0 else None,
            "gbm_dc_temp":   summary(probs_gbm_t, y_gbm) if (cal_gbm and len(probs_gbm) > 0) else None,
            "gbm_dc_pl_temp": summary(probs_gbm_pl_t, y_gbm) if (cal_gbm_pl and len(probs_gbm) > 0) else None,
        }
        if cfg.with_ensemble:
            league_row["xgb_dc"] = summary(probs_xgb, y_gbm) if (probs_xgb is not None and len(probs_xgb) > 0) else None
            league_row["cat_dc"] = summary(probs_cat, y_gbm) if (probs_cat is not None and len(probs_cat) > 0) else None
            league_row["ensemble"] = summary(probs_ens, y_gbm) if probs_ens is not None else None
            league_row["ensemble_temp"] = summary(probs_ens_t, y_gbm) if probs_ens_t is not None else None
        per_league.append(league_row)

        all_pin.append(pin); all_uni.append(uni)
        all_mle.append(probs_mle); all_mle_t.append(probs_mle_t)
        all_y_full.append(y_full)
        if len(test_gbm) > 0:
            all_gbm.append(probs_gbm); all_gbm_t.append(probs_gbm_t)
            if cal_gbm_pl is not None:
                all_gbm_pl_t.append(probs_gbm_pl_t)
            all_y_gbm.append(y_gbm)
            if cfg.with_ensemble and probs_xgb is not None and probs_cat is not None:
                all_xgb.append(probs_xgb)
                all_cat.append(probs_cat)
                if probs_ens is not None:
                    all_ens.append(probs_ens)
                if probs_ens_t is not None:
                    all_ens_t.append(probs_ens_t)

    pooled_pin = np.vstack(all_pin); pooled_y_full = np.concatenate(all_y_full)
    pooled_uni = np.vstack(all_uni)
    pooled_mle = np.vstack(all_mle); pooled_mle_t = np.vstack(all_mle_t)
    pooled_gbm = np.vstack(all_gbm) if all_gbm else np.empty((0,3))
    pooled_gbm_t = np.vstack(all_gbm_t) if all_gbm_t else np.empty((0,3))
    pooled_gbm_pl_t = np.vstack(all_gbm_pl_t) if all_gbm_pl_t else np.empty((0,3))
    pooled_xgb = np.vstack(all_xgb) if all_xgb else np.empty((0,3))
    pooled_cat = np.vstack(all_cat) if all_cat else np.empty((0,3))
    pooled_ens = np.vstack(all_ens) if all_ens else np.empty((0,3))
    pooled_ens_t = np.vstack(all_ens_t) if all_ens_t else np.empty((0,3))
    pooled_y_gbm = np.concatenate(all_y_gbm) if all_y_gbm else np.array([])
    # Pinnacle on GBM-aligned subset
    pinnacle_gbm = pinnacle_baseline(
        pd.concat([d["test_gbm_aligned"] for d in per_league_data], ignore_index=True)
    )

    pooled = {
        "test_n_full":   int(len(pooled_y_full)),
        "test_n_gbm":    int(len(pooled_y_gbm)),
        "pinnacle":      summary(pooled_pin, pooled_y_full),
        "pinnacle_gbm":  summary(pinnacle_gbm, pooled_y_gbm) if len(pooled_y_gbm) > 0 else None,
        "uniform":       summary(pooled_uni, pooled_y_full),
        "mle_dc":        summary(pooled_mle, pooled_y_full),
        "mle_dc_temp":   summary(pooled_mle_t, pooled_y_full) if cal_mle else None,
        "gbm_dc":        summary(pooled_gbm, pooled_y_gbm) if len(pooled_y_gbm) > 0 else None,
        "gbm_dc_temp":   summary(pooled_gbm_t, pooled_y_gbm) if (cal_gbm and len(pooled_y_gbm) > 0) else None,
        "gbm_dc_pl_temp": summary(pooled_gbm_pl_t, pooled_y_gbm) if (cal_gbm_pl and len(pooled_y_gbm) > 0) else None,
    }
    if cfg.with_ensemble and len(pooled_y_gbm) > 0:
        pooled["xgb_dc"] = summary(pooled_xgb, pooled_y_gbm) if len(pooled_xgb) > 0 else None
        pooled["cat_dc"] = summary(pooled_cat, pooled_y_gbm) if len(pooled_cat) > 0 else None
        pooled["ensemble"] = summary(pooled_ens, pooled_y_gbm) if len(pooled_ens) > 0 else None
        pooled["ensemble_temp"] = summary(pooled_ens_t, pooled_y_gbm) if len(pooled_ens_t) > 0 else None

    return {
        "per_league": per_league,
        "pooled": pooled,
        "calibrators": {
            "mle_T": cal_mle.T if cal_mle else None,
            "gbm_T": cal_gbm.T if cal_gbm else None,
            "ensemble_T": cal_ensemble.T if cal_ensemble else None,
            "gbm_pl_summary": cal_gbm_pl.summary() if cal_gbm_pl else None,
        },
        "cfg": {
            "train_window_days": cfg.train_window_days,
            "validation_window_days": cfg.validation_window_days,
            "test_cutoff": str(cfg.test_cutoff.date()),
            "test_horizon_days": cfg.test_horizon_days,
            "gbm_rho": cfg.gbm_rho,
        },
    }
