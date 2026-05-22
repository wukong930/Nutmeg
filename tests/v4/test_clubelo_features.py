"""Tests for nutmeg.v4.features.clubelo_features."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from nutmeg.v4.features.clubelo_features import (
    CLUBELO_FEATURE_COLUMNS,
    CLUBELO_HOME_ADVANTAGE,
    CLUBELO_PLACEHOLDER,
    CLUBELO_SCALE,
    build_clubelo_features,
    load_clubelo_history,
)


@pytest.fixture
def fixtures() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "league": "EPL",
                "home_team": "Arsenal",
                "away_team": "Liverpool",
                "date": pd.Timestamp("2024-12-15"),
                "home_goals": 2,
                "away_goals": 1,
            },
            {
                "league": "EPL",
                "home_team": "UnknownTeam",
                "away_team": "Arsenal",
                "date": pd.Timestamp("2024-12-22"),
                "home_goals": 0,
                "away_goals": 3,
            },
        ]
    )


@pytest.fixture
def history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_canonical": "Arsenal",
                "clubelo_slug": "Arsenal",
                "country": "ENG",
                "elo": 1975.0,
                "from_date": dt.date(2024, 12, 12),
                "to_date": dt.date(2024, 12, 19),
            },
            {
                "team_canonical": "Arsenal",
                "clubelo_slug": "Arsenal",
                "country": "ENG",
                "elo": 1985.0,
                "from_date": dt.date(2024, 12, 20),
                "to_date": dt.date(2024, 12, 26),
            },
            {
                "team_canonical": "Liverpool",
                "clubelo_slug": "Liverpool",
                "country": "ENG",
                "elo": 1990.0,
                "from_date": dt.date(2024, 12, 12),
                "to_date": dt.date(2024, 12, 22),
            },
        ]
    )


class TestBuildClubeloFeatures:
    def test_all_columns_added(self, fixtures: pd.DataFrame, history: pd.DataFrame) -> None:
        out = build_clubelo_features(fixtures, history=history)
        for col in CLUBELO_FEATURE_COLUMNS:
            assert col in out.columns

    def test_resolves_dates_within_interval(
        self, fixtures: pd.DataFrame, history: pd.DataFrame
    ) -> None:
        out = build_clubelo_features(fixtures, history=history)
        # Row 0: Arsenal on 2024-12-15 → ELO 1975 (first interval covers it)
        assert out["clubelo_home"].iloc[0] == 1975.0
        # Liverpool on 2024-12-15 → ELO 1990
        assert out["clubelo_away"].iloc[0] == 1990.0
        # Row 1: Arsenal on 2024-12-22 → ELO 1985 (second interval)
        assert out["clubelo_away"].iloc[1] == 1985.0

    def test_unknown_team_uses_placeholder(
        self, fixtures: pd.DataFrame, history: pd.DataFrame
    ) -> None:
        out = build_clubelo_features(fixtures, history=history)
        # Row 1: home="UnknownTeam" — not in history → placeholder
        assert out["clubelo_home"].iloc[1] == CLUBELO_PLACEHOLDER
        # And the flag should be 0
        assert out["clubelo_available"].iloc[1] == 0

    def test_available_flag_when_both_resolved(
        self, fixtures: pd.DataFrame, history: pd.DataFrame
    ) -> None:
        out = build_clubelo_features(fixtures, history=history)
        # Row 0: both Arsenal + Liverpool resolved → available=1
        assert out["clubelo_available"].iloc[0] == 1

    def test_diff_and_p_home_consistent(
        self, fixtures: pd.DataFrame, history: pd.DataFrame
    ) -> None:
        out = build_clubelo_features(fixtures, history=history)
        # Row 0: 1975 - 1990 = -15. P_home with HA=70 → sigmoid((-15+70)/400)
        # ~= 1 / (1 + 10^(-55/400)) ~= 0.5786
        assert out["clubelo_diff"].iloc[0] == pytest.approx(-15.0)
        expected = 1.0 / (1.0 + 10 ** (-((-15.0 + CLUBELO_HOME_ADVANTAGE) / CLUBELO_SCALE)))
        assert out["clubelo_p_home"].iloc[0] == pytest.approx(expected, rel=1e-6)

    def test_empty_history_all_placeholder(self, fixtures: pd.DataFrame) -> None:
        empty = pd.DataFrame(
            {c: pd.Series(dtype="object") for c in ["team_canonical", "clubelo_slug", "country"]}
            | {c: pd.Series(dtype="float64") for c in ["elo"]}
            | {c: pd.Series(dtype="object") for c in ["from_date", "to_date"]}
        )
        out = build_clubelo_features(fixtures, history=empty)
        assert (out["clubelo_home"] == CLUBELO_PLACEHOLDER).all()
        assert (out["clubelo_away"] == CLUBELO_PLACEHOLDER).all()
        assert (out["clubelo_available"] == 0).all()
        # diff = 0, p_home with HA shift = sigmoid(70/400) > 0.5
        assert (out["clubelo_diff"] == 0).all()
        assert (out["clubelo_p_home"] > 0.5).all()

    def test_date_outside_history_uses_placeholder(self, history: pd.DataFrame) -> None:
        # Arsenal exists in history but not at this date (between intervals or before)
        fixt = pd.DataFrame(
            [
                {
                    "league": "EPL",
                    "home_team": "Arsenal",
                    "away_team": "Liverpool",
                    "date": pd.Timestamp("2024-12-10"),  # before Arsenal's intervals
                    "home_goals": 0,
                    "away_goals": 0,
                }
            ]
        )
        out = build_clubelo_features(fixt, history=history)
        assert out["clubelo_home"].iloc[0] == CLUBELO_PLACEHOLDER
        assert out["clubelo_available"].iloc[0] == 0


class TestLoadClubeloHistory:
    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        # Path that doesn't exist
        ghost = tmp_path / "definitely-does-not-exist"
        df = load_clubelo_history(ghost)
        assert df.empty
        assert "team_canonical" in df.columns

    def test_skips_empty_parquets(self, tmp_path: Path, history: pd.DataFrame) -> None:
        # One real history + one empty parquet
        (tmp_path / "Arsenal.parquet").write_bytes(b"")  # corrupt → should skip silently
        good = tmp_path / "Liverpool.parquet"
        history[history["team_canonical"] == "Liverpool"].to_parquet(good, index=False)
        df = load_clubelo_history(tmp_path)
        # Only Liverpool rows survived
        assert (df["team_canonical"] == "Liverpool").all()
        assert len(df) == 1

    def test_loads_multiple_parquets_into_long_frame(
        self, tmp_path: Path, history: pd.DataFrame
    ) -> None:
        history[history["team_canonical"] == "Arsenal"].to_parquet(
            tmp_path / "Arsenal.parquet", index=False
        )
        history[history["team_canonical"] == "Liverpool"].to_parquet(
            tmp_path / "Liverpool.parquet", index=False
        )
        df = load_clubelo_history(tmp_path)
        # Both teams present
        assert set(df["team_canonical"].unique()) == {"Arsenal", "Liverpool"}
        assert len(df) == 3
