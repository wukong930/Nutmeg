"""Per-league temperature calibration with global fallback.

V5 W9 — different leagues' GBM outputs have different calibration shifts:
EPL closing-line markets are sharper, J1 closing-line markets are noisier,
small-sample leagues like Eredivisie / Primeira benefit from less aggressive
sharpening. A single global T (W4 default) splits the difference and is
sub-optimal for every league individually.

Strategy:
- For each league with ≥ ``min_samples`` validation samples (default 800),
  fit a dedicated T via the same scalar minimizer as the global calibrator.
- For leagues with fewer samples (J1 routinely has 0 GBM-eligible at fold
  boundaries; smaller leagues like Eredivisie may dip below 800), fall back
  to a global T fit on the pooled validation set.

The trade-off vs unconditional global T:
- Pro: per-league captures real distribution differences (~0.0002-0.0005
  log-loss improvement per league in W9 ablation)
- Con: one extra parameter per qualifying league → small overfit risk on
  val. Mitigation: 800-sample threshold ensures each fit sees enough data.

This module is INDEPENDENT of the global TemperatureCalibrator implementation
in temperature.py so the two can coexist; walk_forward decides per-test which
calibrator to apply.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nutmeg.v4.calibration.temperature import (
    TemperatureCalibrator,
    fit_temperature_1x2,
)


DEFAULT_MIN_SAMPLES_PER_LEAGUE = 800


@dataclass
class PerLeagueTemperatureCalibrator:
    """Holds one TemperatureCalibrator per "large-enough" league plus a global
    fallback. Predict() routes each row to its league's T (or global T if not
    found / below threshold).

    Attributes:
        per_league: dict mapping league code → calibrator for that league
        global_calibrator: fallback calibrator fit on pooled validation
        min_samples: the threshold used at fit time (recorded for traceability)
    """

    per_league: dict[str, TemperatureCalibrator]
    global_calibrator: TemperatureCalibrator
    min_samples: int = DEFAULT_MIN_SAMPLES_PER_LEAGUE
    # League → sample count at fit time; useful for diagnostics + ablation
    fit_sample_counts: dict[str, int] = field(default_factory=dict)

    def predict(
        self, raw_probs: np.ndarray, leagues: np.ndarray | list[str]
    ) -> np.ndarray:
        """Apply per-league or global T to each row based on ``leagues[i]``."""
        leagues_arr = np.asarray(leagues)
        if len(leagues_arr) != raw_probs.shape[0]:
            raise ValueError(
                f"leagues length {len(leagues_arr)} != raw_probs rows {raw_probs.shape[0]}"
            )
        out = np.empty_like(raw_probs, dtype=float)
        # Group by league for efficient batching: applying T to a slice at once
        # is much faster than row-by-row, even though both run in O(N) time.
        unique_leagues = np.unique(leagues_arr)
        for lg in unique_leagues:
            mask = leagues_arr == lg
            cal = self.per_league.get(str(lg), self.global_calibrator)
            out[mask] = cal.predict(raw_probs[mask])
        return out

    def __call__(
        self, raw_probs: np.ndarray, leagues: np.ndarray | list[str]
    ) -> np.ndarray:
        return self.predict(raw_probs, leagues)

    def summary(self) -> dict[str, object]:
        """Markdown-friendly summary of which leagues got their own T."""
        rows = []
        for lg, cal in sorted(self.per_league.items()):
            rows.append({
                "league": lg,
                "T": round(cal.T, 4),
                "n": self.fit_sample_counts.get(lg, cal.n_train),
                "nll_before": round(cal.nll_before, 4),
                "nll_after": round(cal.nll_after, 4),
            })
        return {
            "min_samples": self.min_samples,
            "global_T": round(self.global_calibrator.T, 4),
            "global_n": self.global_calibrator.n_train,
            "per_league_rows": rows,
        }


def fit_per_league_temperature(
    val_probs: np.ndarray,
    val_labels,
    val_leagues: np.ndarray | list[str],
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES_PER_LEAGUE,
    t_bounds: tuple[float, float] = (0.3, 5.0),
) -> PerLeagueTemperatureCalibrator:
    """Fit per-league T where the league has ≥ ``min_samples`` validation rows;
    otherwise fall back to a global T fit on the pooled set.

    Args:
        val_probs: (N, 3) raw probabilities from GBM-λ + DC for the val window
        val_labels: (N,) array of {'H','D','A'} or {0,1,2}
        val_leagues: (N,) array of league codes per row
        min_samples: per-league fit only runs when count ≥ this many

    The global calibrator is ALWAYS fit (even when every league has enough
    samples) so prediction-time routing has a safe fallback for unseen leagues.
    """
    val_leagues_arr = np.asarray(val_leagues)
    if len(val_leagues_arr) != val_probs.shape[0]:
        raise ValueError(
            f"val_leagues length {len(val_leagues_arr)} != val_probs rows {val_probs.shape[0]}"
        )

    # Always fit the global fallback first.
    global_cal = fit_temperature_1x2(val_probs, val_labels, t_bounds=t_bounds)

    per_league: dict[str, TemperatureCalibrator] = {}
    sample_counts: dict[str, int] = {}
    unique_leagues = np.unique(val_leagues_arr)
    labels_arr = np.asarray(val_labels)
    for lg in unique_leagues:
        mask = val_leagues_arr == lg
        n = int(mask.sum())
        sample_counts[str(lg)] = n
        if n < min_samples:
            continue
        try:
            cal = fit_temperature_1x2(
                val_probs[mask], labels_arr[mask], t_bounds=t_bounds
            )
        except ValueError:
            # fit_temperature_1x2 raises if < 30 samples; min_samples >= 800
            # so we shouldn't hit this, but be defensive
            continue
        per_league[str(lg)] = cal

    return PerLeagueTemperatureCalibrator(
        per_league=per_league,
        global_calibrator=global_cal,
        min_samples=min_samples,
        fit_sample_counts=sample_counts,
    )
