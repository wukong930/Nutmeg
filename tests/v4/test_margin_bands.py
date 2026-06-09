"""净胜球分组 (margin-band) readout — pure-grid logic."""
from __future__ import annotations

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_margin_bands,
    score_grid,
)


class TestMarginBands:
    def test_sums_to_one(self):
        bands = grid_to_margin_bands(score_grid(1.6, 1.2, rho=-0.1))
        assert abs(sum(b["p"] for b in bands) - 1.0) < 1e-12

    def test_reconciles_with_1x2(self):
        g = score_grid(1.7, 1.1, rho=-0.1)
        bands = grid_to_margin_bands(g)
        home = sum(b["p"] for b in bands if b["margin"] > 0)
        draw = sum(b["p"] for b in bands if b["margin"] == 0)
        away = sum(b["p"] for b in bands if b["margin"] < 0)
        ph, pd, pa = grid_to_1x2(g)
        assert abs(home - ph) < 1e-12
        assert abs(draw - pd) < 1e-12
        assert abs(away - pa) < 1e-12

    def test_ordered_home_to_away(self):
        bands = grid_to_margin_bands(score_grid(1.5, 1.5))
        margins = [b["margin"] for b in bands]
        assert margins == sorted(margins, reverse=True)

    def test_low_lambda_draw_band_is_largest(self):
        bands = grid_to_margin_bands(score_grid(0.4, 0.4))
        draw = next(b for b in bands if b["margin"] == 0)
        assert draw["p"] == max(b["p"] for b in bands)

    def test_tail_folds_big_margins(self):
        g = score_grid(3.0, 0.5, rho=-0.1)
        bands = grid_to_margin_bands(g, tail=2)
        top = bands[0]
        assert top["margin"] == 2 and top["is_tail"] is True
        # the +2 tail's prob == P(home wins by >= 2)
        n = g.shape[0]
        exp = sum(float(g[i, j]) for i in range(n) for j in range(n) if i - j >= 2)
        assert abs(top["p"] - exp) < 1e-12

    def test_scores_within_band_sorted(self):
        for b in grid_to_margin_bands(score_grid(2.0, 0.6)):
            ps = [p for _, _, p in b["scores"]]
            assert ps == sorted(ps, reverse=True)
