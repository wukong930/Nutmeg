"""V10 W1 Track B Day 4 — tests for nutmeg-wc-predict CLI.

Most logic is covered by test_national_team_predict.py + test_wc_training_frame.py.
This file focuses on CLI integration: argument parsing, fixture-date filtering,
output JSON schema, alias-tolerant Pinnacle lookup.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "external"
_HAS_TRAINING_DATA = (
    (DATA / "cup_history" / "WC_2018.parquet").exists()
    and (DATA / "cup_history" / "WC_2022.parquet").exists()
    and (DATA / "eloratings").exists()
    and any((DATA / "eloratings").glob("eloratings_*.parquet"))
)


@pytest.mark.skipif(
    not _HAS_TRAINING_DATA,
    reason="WC 2018+2022 history + eloratings snapshot required",
)
class TestPinnacleAliasLookup:
    """The _pinnacle_lookup_with_aliases helper handles diacritic gaps."""

    def test_direct_match(self):
        from nutmeg.v4.cli.wc_predict import _pinnacle_lookup_with_aliases
        lookup = {("A", "B"): {"psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0}}
        result = _pinnacle_lookup_with_aliases("A", "B", lookup)
        assert result is not None
        assert result["psc_home"] == 2.0

    def test_home_alias(self):
        from nutmeg.v4.cli.wc_predict import _pinnacle_lookup_with_aliases
        # Türkiye in API-Football, Turkey in Odds API
        lookup = {("Turkey", "Spain"): {"psc_home": 5.0, "psc_draw": 4.0, "psc_away": 1.5}}
        result = _pinnacle_lookup_with_aliases("Türkiye", "Spain", lookup)
        assert result is not None
        assert result["psc_home"] == 5.0

    def test_away_alias(self):
        from nutmeg.v4.cli.wc_predict import _pinnacle_lookup_with_aliases
        lookup = {("Spain", "Turkey"): {"psc_home": 1.5, "psc_draw": 4.0, "psc_away": 5.0}}
        result = _pinnacle_lookup_with_aliases("Spain", "Türkiye", lookup)
        assert result is not None
        assert result["psc_away"] == 5.0

    def test_curacao_diacritic(self):
        from nutmeg.v4.cli.wc_predict import _pinnacle_lookup_with_aliases
        lookup = {("Germany", "Curacao"): {"psc_home": 1.1, "psc_draw": 10.0, "psc_away": 20.0}}
        result = _pinnacle_lookup_with_aliases("Germany", "Curaçao", lookup)
        assert result is not None
        assert result["psc_home"] == 1.1

    def test_no_match_returns_none(self):
        from nutmeg.v4.cli.wc_predict import _pinnacle_lookup_with_aliases
        lookup = {("X", "Y"): {"psc_home": 2.0}}
        assert _pinnacle_lookup_with_aliases("A", "B", lookup) is None


class TestCliArgumentParsing:
    """Argparse — fast unit tests, no network or training."""

    def test_date_required(self):
        from nutmeg.v4.cli.wc_predict import main
        with pytest.raises(SystemExit):
            main([])

    def test_invalid_date_returns_2(self):
        from nutmeg.v4.cli.wc_predict import main
        rc = main(["--date", "not-a-date"])
        assert rc == 2

    def test_default_alpha_matches_walk_forward_verdict(self):
        from nutmeg.v4.cli.wc_predict import DEFAULT_BLEND_ALPHA
        assert DEFAULT_BLEND_ALPHA == 0.4

    def test_host_countries_includes_2026(self):
        from nutmeg.v4.cli.wc_predict import HOST_COUNTRIES
        assert 2026 in HOST_COUNTRIES
        assert "USA" in HOST_COUNTRIES[2026]
        assert "Mexico" in HOST_COUNTRIES[2026]
        assert "Canada" in HOST_COUNTRIES[2026]


@pytest.mark.skipif(
    not _HAS_TRAINING_DATA,
    reason="WC 2018+2022 history + eloratings snapshot required",
)
class TestCliEndToEnd:
    """Full CLI run on a real local dataset. Mocks the API-Football
    fixture fetch so we don't hit the network."""

    def test_run_with_synthetic_fixtures(self, tmp_path):
        from nutmeg.v4.cli import wc_predict

        # Fake fixture list — Mexico vs South Africa (2026-06-11)
        fake_fixtures = [{
            "fixture": {"id": 9001, "date": "2026-06-11T19:00:00+00:00"},
            "league": {"round": "Group Stage - 1"},
            "teams": {
                "home": {"name": "Mexico"},
                "away": {"name": "South Africa"},
            },
        }, {
            # Different date → should NOT show up
            "fixture": {"id": 9002, "date": "2026-06-12T19:00:00+00:00"},
            "league": {"round": "Group Stage - 1"},
            "teams": {
                "home": {"name": "Germany"},
                "away": {"name": "Curaçao"},
            },
        }]

        out_path = tmp_path / "out.json"

        with patch(
            "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
            return_value=fake_fixtures,
        ):
            rc = wc_predict.main([
                "--date", "2026-06-11",
                "--out", str(out_path),
                "--quiet",
            ])

        assert rc == 0, "CLI should exit 0"
        body = json.loads(out_path.read_text())

        assert body["date"] == "2026-06-11"
        assert body["n_fixtures"] == 1
        assert body["season"] == 2026
        assert body["blend_alpha"] == 0.4

        pred = body["predictions"][0]
        assert pred["home_team"] == "Mexico"
        assert pred["away_team"] == "South Africa"
        # Mexico (host) should get positive home_adv
        assert pred["home_adv"] > 0
        # Mexico Elo > South Africa Elo → Mexico favored
        assert pred["p_home"] > pred["p_away"]
        # No Pinnacle fetch → source should be lightgbm_only
        assert pred["source"] == "lightgbm_only"
        # All probs sum to 1
        assert abs(pred["p_home"] + pred["p_draw"] + pred["p_away"] - 1.0) < 1e-3

    def test_no_fixtures_on_date_returns_zero_predictions(self, tmp_path):
        from nutmeg.v4.cli import wc_predict
        out_path = tmp_path / "out.json"
        with patch(
            "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
            return_value=[],
        ):
            rc = wc_predict.main([
                "--date", "2026-06-11",
                "--out", str(out_path),
                "--quiet",
            ])
        assert rc == 0
        body = json.loads(out_path.read_text())
        assert body["n_fixtures"] == 0
        assert body["predictions"] == []
