"""Multi-season walk-forward evaluation.

Re-runs run_walk_forward for several test cutoffs and stacks results into one
report. This answers: "is V4's edge over MLE DC consistent across seasons,
or did we just get lucky in 24/25?"
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

import pandas as pd

from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


DEFAULT_CUTOFFS = (
    pd.Timestamp("2022-08-01"),  # test on 22/23 season
    pd.Timestamp("2023-08-01"),  # test on 23/24 season
    pd.Timestamp("2024-08-01"),  # test on 24/25 season
)


def run_multi_season(
    df: pd.DataFrame,
    cutoffs: Sequence[pd.Timestamp] = DEFAULT_CUTOFFS,
    base_cfg: WalkForwardConfig | None = None,
) -> dict:
    """Run walk_forward at each cutoff; return dict keyed by cutoff date string."""
    seasons = []
    for cutoff in cutoffs:
        cfg = base_cfg or WalkForwardConfig()
        cfg.test_cutoff = cutoff
        result = run_walk_forward(df, cfg)
        if not result.get("per_league"):
            continue
        pooled = result["pooled"]
        seasons.append({
            "cutoff": str(cutoff.date()),
            "test_n_full": pooled.get("test_n_full"),
            "test_n_gbm": pooled.get("test_n_gbm"),
            "pinnacle":      pooled.get("pinnacle"),
            "pinnacle_gbm":  pooled.get("pinnacle_gbm"),
            "mle_dc":        pooled.get("mle_dc"),
            "mle_dc_temp":   pooled.get("mle_dc_temp"),
            "gbm_dc":        pooled.get("gbm_dc"),
            "gbm_dc_temp":   pooled.get("gbm_dc_temp"),
            "calibrators":   result.get("calibrators"),
        })
    return {"seasons": seasons, "n_seasons": len(seasons)}
