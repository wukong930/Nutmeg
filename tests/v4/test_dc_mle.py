"""Tests for nutmeg.v4.model.dc_mle — MLE Dixon-Coles fit."""
import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.model.dc_mle import fit_dixon_coles, predict_lambdas


def _toy_matches(n=400, n_teams=10, seed=42):
    """Synthesize a plausible match dataset for testing the fit."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    # Latent attack/defense
    true_atk = rng.normal(0, 0.3, n_teams)
    true_def = rng.normal(0, 0.3, n_teams)
    rows = []
    base_date = pd.Timestamp("2023-01-01")
    for k in range(n):
        h, a = rng.choice(n_teams, 2, replace=False)
        log_lh = 0.25 + 0.2 + true_atk[h] - true_def[a]  # mu=0.25, ha=0.2
        log_la = 0.25 + true_atk[a] - true_def[h]
        lh = float(np.exp(log_lh))
        la = float(np.exp(log_la))
        rows.append({
            "league": "TST", "season": "2324",
            "date": base_date + pd.Timedelta(days=k),
            "home_team": teams[h], "away_team": teams[a],
            "home_goals": int(rng.poisson(lh)),
            "away_goals": int(rng.poisson(la)),
            "result_1x2": "H",  # placeholder, not used by fit
        })
    return pd.DataFrame(rows)


class TestFit:
    def test_converges_on_toy_data(self):
        df = _toy_matches()
        params = fit_dixon_coles(df, as_of=pd.Timestamp("2024-01-01"))
        assert params.converged
        assert params.train_n == len(df)

    def test_recovers_home_advantage_sign(self):
        df = _toy_matches()
        params = fit_dixon_coles(df, as_of=pd.Timestamp("2024-01-01"))
        # With more home goals than away by construction (ha=0.2), should learn positive
        assert params.home_advantage > 0

    def test_attack_defense_zero_sum(self):
        df = _toy_matches()
        params = fit_dixon_coles(df, as_of=pd.Timestamp("2024-01-01"))
        atks = np.array(list(params.attack.values()))
        defs = np.array(list(params.defense.values()))
        assert atks.sum() == pytest.approx(0.0, abs=1e-6)
        assert defs.sum() == pytest.approx(0.0, abs=1e-6)

    def test_rho_in_bounds(self):
        df = _toy_matches()
        params = fit_dixon_coles(df, as_of=pd.Timestamp("2024-01-01"))
        assert -0.18 <= params.rho <= 0.18

    def test_raises_on_empty(self):
        df = _toy_matches().iloc[:0]
        with pytest.raises(ValueError):
            fit_dixon_coles(df, as_of=pd.Timestamp("2024-01-01"))


class TestPredict:
    def test_lambda_positive(self):
        train = _toy_matches()
        params = fit_dixon_coles(train, as_of=pd.Timestamp("2024-01-01"))
        # Build fixture with known teams
        fixtures = pd.DataFrame({
            "home_team": ["T00", "T01", "T02"],
            "away_team": ["T03", "T04", "T05"],
        })
        lambdas = predict_lambdas(fixtures, params)
        assert lambdas.shape == (3, 2)
        assert (lambdas > 0).all()
        assert (lambdas < 8).all()  # sanity ceiling

    def test_unknown_team_fallback(self):
        train = _toy_matches()
        params = fit_dixon_coles(train, as_of=pd.Timestamp("2024-01-01"))
        # Unknown team should fall back to league average (not crash)
        fixtures = pd.DataFrame({
            "home_team": ["UNKNOWN_TEAM"],
            "away_team": ["ALSO_UNKNOWN"],
        })
        lambdas = predict_lambdas(fixtures, params)
        assert lambdas.shape == (1, 2)
        assert (lambdas > 0).all()
