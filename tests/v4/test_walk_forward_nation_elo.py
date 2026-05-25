"""V11 backlog #5 — tests for nation_state passthrough in walk-forward.

Before this patch:
  - WalkForwardConfig had no nation_state field
  - cup_ablation CLI had no --nation-elo-cache-dir flag
  - National-team-cup fixtures (WC, EURO, COPA_AMERICA) in the training
    pool got 1500 Elo default

After this patch:
  - WalkForwardConfig.nation_state plumbs through to build_feature_frame
    → build_elo_features → seed_elo_value
  - cup_ablation accepts --nation-elo-cache-dir and builds the lookup
  - When mode opts into cross_league_seed, national-team-cup rows get
    real per-nation Elo seeds

These are structural tests — they don't run a full walk-forward (too
slow for the unit suite) but exercise the config + CLI integration
points.
"""
from __future__ import annotations

import pytest


class TestWalkForwardConfigField:
    def test_nation_state_field_present(self):
        from nutmeg.v4.eval.walk_forward import WalkForwardConfig
        cfg = WalkForwardConfig()
        assert hasattr(cfg, "nation_state")
        assert cfg.nation_state is None  # default

    def test_nation_state_accepts_dict(self):
        from nutmeg.v4.eval.walk_forward import WalkForwardConfig
        cfg = WalkForwardConfig(nation_state={"BRA": 1950.0, "ARG": 1940.0})
        assert cfg.nation_state["BRA"] == 1950.0


class TestRunWalkForwardWiring:
    """Stub the underlying build_feature_frame call to confirm
    nation_state is being threaded through, without paying the
    real walk-forward cost."""

    def test_nation_state_passed_to_build_feature_frame(self, monkeypatch):
        import pandas as pd
        from nutmeg.v4.eval import walk_forward as wf

        seen = {}

        def fake_build(df, *, cup_history_df, cross_league_seed, nation_state):
            seen["nation_state"] = nation_state
            # Return a properly-shaped (but empty) frame so the per-league
            # iteration short-circuits without exploding on missing cols.
            return pd.DataFrame(columns=[
                "date", "league", "home_team", "away_team",
                "home_goals", "away_goals", "psc_home", "psc_draw", "psc_away",
            ])

        monkeypatch.setattr(wf, "build_feature_frame", fake_build)
        cfg = wf.WalkForwardConfig(
            test_cutoff=pd.Timestamp("2024-08-01"),
            nation_state={"BRA": 1950.0},
        )
        empty = pd.DataFrame(columns=[
            "date", "league", "home_team", "away_team",
            "home_goals", "away_goals",
        ])
        wf.run_walk_forward(empty, cfg)
        assert seen["nation_state"] == {"BRA": 1950.0}


class TestCupAblationCliFlag:
    def test_help_lists_nation_elo_flag(self, capsys):
        from nutmeg.v4.cli import cup_ablation as ca
        with pytest.raises(SystemExit) as exc:
            ca.main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--nation-elo-cache-dir" in out

    def test_run_one_fold_accepts_nation_state(self):
        """run_one_fold's signature must accept nation_state= kwarg."""
        from nutmeg.v4.cli.cup_ablation import run_one_fold
        import inspect
        sig = inspect.signature(run_one_fold)
        assert "nation_state" in sig.parameters
        # Should have a None default
        assert sig.parameters["nation_state"].default is None


class TestAblationReportArtifact:
    """The nation-elo ablation card produced by the V11 backlog #5
    investigation should exist on disk after we ran the comparison."""

    def test_report_exists(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parents[2]
        report = repo / "docs" / "v11_nation_elo_ablation_20260526.md"
        assert report.exists()

    def test_report_has_baseline_and_cup_full(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parents[2]
        report = (repo / "docs" / "v11_nation_elo_ablation_20260526.md").read_text()
        assert "baseline" in report
        assert "cup_full" in report
        assert "Ship gate" in report
