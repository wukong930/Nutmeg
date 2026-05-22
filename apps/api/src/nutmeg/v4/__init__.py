"""Nutmeg V4 — clean redesign of the prediction pipeline.

Design principles (see docs/V4_HANDOFF.md):

1. NO imports from legacy modules (nutmeg.modeling, nutmeg.accuracy,
   nutmeg.recommendations). V4 is built fresh.
2. Functional core, narrow IO at the edges. Models and feature builders are
   pure functions that take and return pandas DataFrames.
3. Pinnacle closing line is the hard baseline. Every model must report its
   log-loss / Brier / ECE delta vs. Pinnacle on the same walk-forward split.
4. Two-stage prediction: GBM predicts (lambda_home, lambda_away); Dixon-Coles
   gives the 9x9 score grid; markets (1X2, integer-handicap 1X2) are
   computed by integrating the grid.
5. Calibration is applied (not just reported).
"""

__all__: list[str] = []
