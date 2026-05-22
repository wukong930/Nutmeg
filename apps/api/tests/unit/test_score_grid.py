from __future__ import annotations

from math import isclose

from nutmeg.modeling import build_poisson_score_grid


def test_poisson_score_grid_is_normalized() -> None:
    score_grid = build_poisson_score_grid(
        fixture_id="fix_test",
        lambda_home=1.42,
        lambda_away=1.11,
        max_goals=8,
    )

    assert score_grid.max_goals == 8
    assert score_grid.is_normalized(tolerance=1e-9)
    assert score_grid.tail_mass >= 0.0
    assert score_grid.lambda_home == 1.42
    assert score_grid.lambda_away == 1.11
    assert isclose(score_grid.probability_for(0, 0), score_grid.grid[0][0])
