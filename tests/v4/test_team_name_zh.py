"""V11 P1-FE#2 — tests for Chinese team name dict + lookup_zh helper."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = (
    REPO_ROOT / "apps" / "api" / "src" / "nutmeg" / "v4"
    / "api" / "static" / "dashboard.html"
)


@pytest.fixture(scope="module")
def client():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.fixture(scope="module")
def html(client):
    r = client.get("/api/v4/dashboard")
    assert r.status_code == 200
    return r.text


# ---------- Static dict shape -------------------------------------------

class TestDictShape:
    def test_module_exports(self):
        from nutmeg.v4.data import team_name_zh as mod
        assert hasattr(mod, "TEAM_NAME_ZH")
        assert hasattr(mod, "lookup_zh")
        assert hasattr(mod, "coverage_by_league")

    def test_dict_is_dict_str_str(self):
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        assert isinstance(TEAM_NAME_ZH, dict)
        for k, v in TEAM_NAME_ZH.items():
            assert isinstance(k, str)
            assert isinstance(v, str)
            assert k.strip() == k
            assert v.strip() == v

    def test_dict_size_floor(self):
        """We promised top-5 leagues × ~20 teams = ≥ 90 entries."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        assert len(TEAM_NAME_ZH) >= 90, (
            f"only {len(TEAM_NAME_ZH)} entries — top-5 leagues need ~90+"
        )

    def test_all_values_are_chinese(self):
        """Sanity: every value must contain Han characters."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        han_re = re.compile(r"[一-鿿]")
        for k, v in TEAM_NAME_ZH.items():
            assert han_re.search(v), f"value for {k!r} has no Han chars: {v!r}"


# ---------- per-league coverage -----------------------------------------

class TestCoverageByLeague:
    def test_top5_leagues_all_present(self):
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        for league in ("EPL", "ESP_LA_LIGA", "ITA_SERIE_A",
                       "GER_BUNDESLIGA", "FRA_LIGUE_1", "TOTAL"):
            assert league in cov, f"missing {league} from coverage report"

    def test_each_league_has_18_plus_teams(self):
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        # Bundesliga + Ligue 1 are 18-team leagues; others 20.
        # We allow variant aliases which can push some entries higher.
        for league in ("EPL", "ESP_LA_LIGA", "ITA_SERIE_A",
                       "GER_BUNDESLIGA", "FRA_LIGUE_1"):
            assert cov[league] >= 18, f"{league} has only {cov[league]} entries"

    def test_total_matches_sum(self):
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        league_sum = sum(v for k, v in cov.items() if k != "TOTAL")
        assert cov["TOTAL"] == league_sum, (
            f"TOTAL ({cov['TOTAL']}) ≠ league sum ({league_sum})"
        )


# ---------- lookup_zh() ---------------------------------------------------

class TestLookupZh:
    def test_known_team_returns_chinese(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Arsenal") == "阿森纳"
        assert lookup_zh("Real Madrid") == "皇家马德里"
        assert lookup_zh("Bayern Munich") == "拜仁慕尼黑"
        assert lookup_zh("Inter") == "国际米兰"
        assert lookup_zh("Paris SG") == "巴黎圣日耳曼"

    def test_unknown_team_passes_through(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Random FC 1234") == "Random FC 1234"
        assert lookup_zh("Some Cup Team") == "Some Cup Team"

    def test_empty_input_returns_empty(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("") == ""
        assert lookup_zh(None) == ""  # type: ignore[arg-type]

    def test_canonical_variants(self):
        """Common spellings that survive canonical normalization
        should also resolve. (Manchester City vs Man City etc.)"""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Man City") == "曼城"
        assert lookup_zh("Manchester City") == "曼城"
        assert lookup_zh("Paris SG") == "巴黎圣日耳曼"
        assert lookup_zh("PSG") == "巴黎圣日耳曼"


# ---------- Specific league entries (smoke test per league) -------------

class TestPerLeagueSmokeTest:
    """One pick per league to verify the dict is correctly assembled."""

    def test_epl_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Liverpool") == "利物浦"
        assert lookup_zh("Tottenham") == "热刺"

    def test_la_liga_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Barcelona") == "巴塞罗那"
        assert lookup_zh("Atletico Madrid") == "马德里竞技"

    def test_serie_a_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Juventus") == "尤文图斯"
        assert lookup_zh("AC Milan") == "AC米兰"

    def test_bundesliga_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Borussia Dortmund") == "多特蒙德"
        assert lookup_zh("RB Leipzig") == "莱比锡红牛"

    def test_ligue_1_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Marseille") == "马赛"
        assert lookup_zh("Monaco") == "摩纳哥"


# ---------- /api/v4/team-name-zh endpoint --------------------------------

class TestTeamNameZhEndpoint:
    def test_returns_200(self, client):
        r = client.get("/api/v4/team-name-zh")
        assert r.status_code == 200

    def test_returns_json(self, client):
        r = client.get("/api/v4/team-name-zh")
        assert "json" in r.headers["content-type"]
        body = r.json()
        assert isinstance(body, dict)

    def test_matches_python_dict(self, client):
        """API response must be identical to the Python TEAM_NAME_ZH dict."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        r = client.get("/api/v4/team-name-zh")
        assert r.json() == TEAM_NAME_ZH

    def test_cache_header_set(self, client):
        """Dict is static — cache aggressively."""
        r = client.get("/api/v4/team-name-zh")
        assert "max-age" in r.headers.get("cache-control", "")

    def test_returns_chinese_names(self, client):
        body = client.get("/api/v4/team-name-zh").json()
        # spot check a few
        assert body.get("Arsenal") == "阿森纳"
        assert body.get("Real Madrid") == "皇家马德里"
        assert body.get("Bayern Munich") == "拜仁慕尼黑"


# ---------- Dashboard wiring -------------------------------------------

class TestDashboardWiring:
    def test_zh_team_helper_defined(self, html):
        """`zhTeam(name)` JS helper exists."""
        assert "function zhTeam(name)" in html

    def test_team_zh_dict_var_declared(self, html):
        assert "let TEAM_ZH_DICT" in html

    def test_dict_fetched_at_init(self, html):
        assert "function loadTeamZhDict()" in html
        # init code calls loadTeamZhDict before/around today-load
        assert "loadTeamZhDict()" in html

    def test_setLocale_triggers_rerender(self, html):
        """When user toggles locale, the today tab re-renders so team
        names actually swap."""
        idx = html.index("function setLocale(loc)")
        block = html[idx:idx+600]
        assert "loadTodayRecommendations" in block

    def test_zhTeam_used_in_renders(self, html):
        """All 5 render functions must call zhTeam at least once."""
        # Each render function should reference zhTeam somewhere
        for fn in ("renderTodaySingle", "renderRecommendations",
                   "renderSingleRecommendations", "renderPoolRecommendations",
                   "renderWcMatch"):
            idx = html.index(f"function {fn}")
            # Look in the next 3000 chars (enough for any render fn body)
            body = html[idx:idx+3000]
            assert "zhTeam(" in body, f"{fn} doesn't call zhTeam"

    def test_team_zh_endpoint_url_used(self, html):
        """Dashboard JS must call the new endpoint."""
        assert "/team-name-zh" in html
