"""Tests for nutmeg.v4.data.ingest schema."""
import pandas as pd

from nutmeg.v4.data import load_all_matches
from nutmeg.v4.data.schema import MATCH_COLUMNS


class TestIngest:
    def test_schema_columns(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        # All canonical columns present
        for col in MATCH_COLUMNS:
            assert col in df.columns, f"missing column: {col}"

    def test_nonempty(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        assert len(df) > 10_000  # we know there's ~27k

    def test_goals_are_int(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        assert df["home_goals"].dtype.kind == "i"
        assert df["away_goals"].dtype.kind == "i"
        assert (df["home_goals"] >= 0).all()
        assert (df["away_goals"] >= 0).all()

    def test_result_consistent_with_goals(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        # Verify FTR derived from FTHG/FTAG
        match = df.dropna(subset=["result_1x2"]).copy()
        # For rows where we have result, it should match home_goals vs away_goals
        # (Some rare data quality cases may differ, allow 1% mismatch)
        derived = (match.home_goals > match.away_goals).map({True: "H", False: ""}) \
                + (match.home_goals < match.away_goals).map({True: "A", False: ""}) \
                + (match.home_goals == match.away_goals).map({True: "D", False: ""})
        matches = (match["result_1x2"] == derived).mean()
        assert matches > 0.98, f"only {matches:.3f} of rows have FTR matching goals"

    def test_date_parsed(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        assert pd.api.types.is_datetime64_any_dtype(df["date"])
        # Reasonable date range (sport data)
        assert df["date"].min() > pd.Timestamp("2010-01-01")
        assert df["date"].max() < pd.Timestamp("2030-01-01")

    def test_pinnacle_coverage_high(self):
        df = load_all_matches("data/historical_sources/football_data_co_uk")
        coverage = df["psc_home"].notna().mean()
        assert coverage > 0.85, f"Pinnacle coverage only {coverage:.3f}"
