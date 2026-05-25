"""V11 Phase 0 — tests for the stadium_features skeleton.

Validates the pure-function API + the vectorized builder on synthetic
venue data. The actual venue registry (data/external/stadiums.parquet)
doesn't exist yet — it's a Branch B W2 deliverable. These tests don't
require it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.features.stadium_features import (
    KNOWN_HIGH_ALTITUDE_VENUES,
    OUTPUT_COLUMNS,
    StadiumInfo,
    altitude_modifier,
    build_stadium_features,
    capacity_quantile,
    haversine_km,
    load_venue_registry,
    lookup_altitude,
    travel_distance_km,
)


# ---------- altitude_modifier curve ----------------------------------------

class TestAltitudeModifier:
    def test_sea_level_is_identity(self):
        assert altitude_modifier(0) == 1.00
        assert altitude_modifier(50) == 1.00
        assert altitude_modifier(500) == 1.00
        assert altitude_modifier(999) == 1.00

    def test_below_1000m_is_identity(self):
        assert altitude_modifier(800) == 1.00

    def test_at_1000m_starts_ramp(self):
        # Exactly 1000m: ramp not yet started
        assert altitude_modifier(1000) == pytest.approx(1.00)

    def test_2000m_returns_1_05(self):
        assert altitude_modifier(2000) == pytest.approx(1.05)

    def test_3000m_returns_1_08(self):
        assert altitude_modifier(3000) == pytest.approx(1.08)

    def test_high_altitude_capped_at_1_10(self):
        # La Paz at 3640m
        result = altitude_modifier(3640)
        assert 1.08 < result <= 1.10
        # Way past the cap
        assert altitude_modifier(5000) == 1.10
        assert altitude_modifier(8848) == 1.10  # Everest

    def test_none_returns_identity(self):
        assert altitude_modifier(None) == 1.00

    def test_nan_returns_identity(self):
        assert altitude_modifier(float("nan")) == 1.00

    def test_negative_returns_identity(self):
        # Dead Sea, etc.
        assert altitude_modifier(-50) == 1.00

    def test_monotonic_in_meaningful_range(self):
        """Curve should be monotonically non-decreasing above 1000m."""
        alts = [1000, 1500, 2000, 2500, 3000, 3500, 4000]
        mods = [altitude_modifier(a) for a in alts]
        for i in range(len(mods) - 1):
            assert mods[i] <= mods[i + 1], (
                f"non-monotonic at {alts[i]}→{alts[i+1]}: {mods[i]} > {mods[i+1]}"
            )


# ---------- lookup_altitude (curated table) --------------------------------

class TestLookupAltitude:
    def test_known_high_altitude_hits(self):
        assert lookup_altitude("Hernando Siles") == 3640.0
        assert lookup_altitude("Azteca") == 2240.0

    def test_unknown_returns_none(self):
        assert lookup_altitude("Some Random Stadium FC") is None
        assert lookup_altitude("") is None

    def test_case_insensitive_fuzzy(self):
        # "wembley" should match "Wembley"
        assert lookup_altitude("wembley") == 16.0
        # Extra suffix in parens should be ignored
        assert lookup_altitude("Azteca (Mexico City)") == 2240.0


# ---------- haversine_km ---------------------------------------------------

class TestHaversine:
    def test_zero_distance(self):
        assert haversine_km(0, 0, 0, 0) == 0.0

    def test_london_to_paris(self):
        # London ~ 51.5074N, -0.1278E; Paris ~ 48.8566N, 2.3522E
        d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        # Real-world distance is ~344 km
        assert 340 < d < 350

    def test_antipodes(self):
        # Two opposite points: should be ~half Earth's circumference
        d = haversine_km(0, 0, 0, 180)
        assert 19000 < d < 21000

    def test_symmetric(self):
        d1 = haversine_km(40, -74, 51, -0.1)
        d2 = haversine_km(51, -0.1, 40, -74)
        assert d1 == pytest.approx(d2)


# ---------- travel_distance_km ---------------------------------------------

class TestTravelDistance:
    def test_returns_none_when_either_venue_lacks_coords(self):
        v1 = StadiumInfo(venue_id=1, name="A", lat=40.0, lon=-74.0)
        v2 = StadiumInfo(venue_id=2, name="B")  # no lat/lon
        assert travel_distance_km(v1, v2) is None
        assert travel_distance_km(v2, v1) is None

    def test_returns_none_when_either_venue_none(self):
        v1 = StadiumInfo(venue_id=1, name="A", lat=40.0, lon=-74.0)
        assert travel_distance_km(v1, None) is None
        assert travel_distance_km(None, v1) is None

    def test_computes_distance_when_both_have_coords(self):
        v_london = StadiumInfo(venue_id=1, name="L", lat=51.5074, lon=-0.1278)
        v_paris = StadiumInfo(venue_id=2, name="P", lat=48.8566, lon=2.3522)
        d = travel_distance_km(v_london, v_paris)
        assert 340 < d < 350


# ---------- capacity_quantile ----------------------------------------------

class TestCapacityQuantile:
    def test_top_capacity(self):
        caps = [20000, 30000, 40000, 50000, 90000]
        assert capacity_quantile(90000, caps) == 1.0

    def test_bottom_capacity(self):
        caps = [20000, 30000, 40000, 50000, 90000]
        assert capacity_quantile(20000, caps) == 0.2

    def test_unknown_capacity_returns_nan(self):
        assert np.isnan(capacity_quantile(None, [10000, 50000]))

    def test_empty_league_returns_nan(self):
        assert np.isnan(capacity_quantile(40000, []))

    def test_middle_capacity(self):
        caps = [10000, 20000, 30000, 40000, 50000]
        # 30000 = 3rd of 5, so quantile = 0.6
        assert capacity_quantile(30000, caps) == 0.6


# ---------- build_stadium_features (vectorized) ----------------------------

class TestBuildStadiumFeatures:
    def _make_df(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_output_columns_present(self):
        df = self._make_df([
            {"home_venue_id": "v1", "away_team_prior_venue_id": "v2", "league": "EPL"},
        ])
        out = build_stadium_features(df, venue_registry={})
        for col in OUTPUT_COLUMNS:
            assert col in out.columns

    def test_empty_registry_returns_defaults(self):
        df = self._make_df([
            {"home_venue_id": "v1", "away_team_prior_venue_id": "v2", "league": "EPL"},
        ])
        out = build_stadium_features(df, venue_registry={})
        # Altitude unknown → NaN; modifier 1.0 default; capacity 0 default
        assert np.isnan(out.iloc[0]["stadium_altitude_m"])
        assert out.iloc[0]["stadium_altitude_modifier"] == 1.0
        assert out.iloc[0]["stadium_capacity"] == 0
        assert out.iloc[0]["stadium_is_artificial_turf"] == 0

    def test_high_altitude_venue_gets_modifier(self):
        df = self._make_df([
            {"home_venue_id": "v_lapaz", "away_team_prior_venue_id": "v_buenos", "league": "BOL"},
        ])
        registry = {
            "v_lapaz": StadiumInfo(
                venue_id="v_lapaz", name="Hernando Siles",
                lat=-16.5, lon=-68.15, altitude_m=3640, capacity=42000,
            ),
            "v_buenos": StadiumInfo(
                venue_id="v_buenos", name="Monumental",
                lat=-34.55, lon=-58.45, altitude_m=65, capacity=70000,
            ),
        }
        out = build_stadium_features(df, venue_registry=registry)
        assert out.iloc[0]["stadium_altitude_m"] == 3640
        # Capped at 1.10
        assert out.iloc[0]["stadium_altitude_modifier"] == pytest.approx(1.10, abs=0.01)
        # Travel distance ~2400km
        assert 2200 < out.iloc[0]["stadium_travel_km"] < 2600

    def test_artificial_turf_flag(self):
        df = self._make_df([
            {"home_venue_id": "v_turf", "league": "USL"},
        ])
        registry = {
            "v_turf": StadiumInfo(
                venue_id="v_turf", name="Turf Stadium", surface="artificial",
            ),
        }
        out = build_stadium_features(df, venue_registry=registry)
        assert out.iloc[0]["stadium_is_artificial_turf"] == 1

    def test_falls_back_to_curated_altitude_when_registry_lacks_it(self):
        # Registry has the venue but altitude is None
        df = self._make_df([
            {"home_venue_id": "v_aztec", "league": "MEX"},
        ])
        registry = {
            "v_aztec": StadiumInfo(
                venue_id="v_aztec", name="Azteca",  # known altitude in curated table
            ),
        }
        out = build_stadium_features(df, venue_registry=registry)
        assert out.iloc[0]["stadium_altitude_m"] == 2240.0
        assert out.iloc[0]["stadium_altitude_modifier"] > 1.05

    def test_capacity_quantile_per_league(self):
        df = self._make_df([
            {"home_venue_id": "v_big", "league": "EPL"},
            {"home_venue_id": "v_small", "league": "EPL"},
        ])
        registry = {
            "v_big": StadiumInfo(venue_id="v_big", name="A", capacity=80000),
            "v_small": StadiumInfo(venue_id="v_small", name="B", capacity=25000),
        }
        league_caps = {"EPL": [25000, 35000, 45000, 60000, 80000]}
        out = build_stadium_features(df, venue_registry=registry, league_capacities=league_caps)
        assert out.iloc[0]["stadium_capacity_quantile"] == 1.0  # 80k is top
        assert out.iloc[1]["stadium_capacity_quantile"] == 0.2  # 25k is bottom


# ---------- load_venue_registry --------------------------------------------

class TestLoadVenueRegistry:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        assert load_venue_registry(tmp_path / "nope.parquet") == {}

    def test_corrupt_file_returns_empty_dict(self, tmp_path: Path):
        bad = tmp_path / "bad.parquet"
        bad.write_text("not a parquet file")
        assert load_venue_registry(bad) == {}

    def test_loads_valid_parquet(self, tmp_path: Path):
        # Write a minimal parquet
        df = pd.DataFrame([
            {"venue_id": "v1", "name": "X", "city": "London",
             "country": "England", "altitude_m": 16.0, "capacity": 90000,
             "lat": 51.55, "lon": -0.28, "surface": "grass"},
        ])
        path = tmp_path / "stadiums.parquet"
        df.to_parquet(path)
        reg = load_venue_registry(path)
        assert "v1" in reg
        assert reg["v1"].name == "X"
        assert reg["v1"].capacity == 90000


# ---------- Curated table is reasonable ------------------------------------

class TestCuratedTable:
    def test_high_altitude_known_venues_in_table(self):
        # Sanity: well-known high-altitude stadiums should be in the curated dict
        assert "Hernando Siles" in KNOWN_HIGH_ALTITUDE_VENUES  # La Paz
        assert "Atahualpa" in KNOWN_HIGH_ALTITUDE_VENUES        # Quito
        assert "Azteca" in KNOWN_HIGH_ALTITUDE_VENUES           # Mexico City

    def test_curated_altitudes_in_reasonable_range(self):
        for name, alt in KNOWN_HIGH_ALTITUDE_VENUES.items():
            # No stadium should be below Dead Sea (-430m) or above Everest base camp (5000m)
            assert -50 <= alt <= 5000, f"{name}: {alt}m looks wrong"
