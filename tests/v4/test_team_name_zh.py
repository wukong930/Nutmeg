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
        """V11 P1-FE#7: 14 leagues × ~20 teams (+ aliases) ⇒ ≥ 300 entries."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        assert len(TEAM_NAME_ZH) >= 300, (
            f"only {len(TEAM_NAME_ZH)} entries — 14 leagues need ~300+"
        )

    def test_all_values_are_chinese(self):
        """Sanity: every value must contain Han characters."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        han_re = re.compile(r"[一-鿿]")
        for k, v in TEAM_NAME_ZH.items():
            assert han_re.search(v), f"value for {k!r} has no Han chars: {v!r}"


# ---------- per-league coverage -----------------------------------------

class TestCoverageByLeague:
    def test_all_14_leagues_present(self):
        """V11 P1-FE#7: every trained league has a coverage entry."""
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        expected = (
            # P1-FE#2 top-5
            "EPL", "ESP_LA_LIGA", "ITA_SERIE_A",
            "GER_BUNDESLIGA", "FRA_LIGUE_1",
            # P1-FE#7 the rest
            "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
            "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
            "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
            "BEL_PRO_LEAGUE", "JPN_J1",
            "TOTAL",
        )
        for league in expected:
            assert league in cov, f"missing {league} from coverage report"

    def test_each_league_has_16_plus_teams(self):
        """Smallest top-flight in scope is 比甲 = 16; everything else ≥ 18."""
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        # We allow variant aliases (e.g. PSG ↔ Paris SG) which often push
        # entries higher than the strict roster size.
        for league in (
            "EPL", "ESP_LA_LIGA", "ITA_SERIE_A",
            "GER_BUNDESLIGA", "FRA_LIGUE_1",
            "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
            "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
            "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
            "BEL_PRO_LEAGUE", "JPN_J1",
        ):
            assert cov[league] >= 16, f"{league} has only {cov[league]} entries"

    def test_total_at_most_equals_sum(self):
        """TOTAL ≤ league_sum: a canonical name shared across leagues
        (e.g. Köln promoted/relegated between Bundesliga + 2.Bundesliga)
        contributes only once to TEAM_NAME_ZH but counts twice in the
        per-league dicts. We assert TOTAL is at most the sum, never more."""
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        league_sum = sum(v for k, v in cov.items() if k != "TOTAL")
        assert cov["TOTAL"] <= league_sum, (
            f"TOTAL ({cov['TOTAL']}) > league sum ({league_sum}) — impossible"
        )
        # And the gap shouldn't be more than ~10 (a few legit cross-league
        # canonical-name duplicates from promotion/relegation).
        assert (league_sum - cov["TOTAL"]) <= 10, (
            f"TOTAL trails sum by {league_sum - cov['TOTAL']} — too many duplicates"
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


class TestP1FE7NewLeagues:
    """V11 P1-FE#7 — one canonical pick per newly-added league."""

    def test_championship_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Leeds") == "利兹联"
        assert lookup_zh("Burnley") == "伯恩利"

    def test_segunda_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Levante") == "莱万特"
        assert lookup_zh("Elche") == "埃尔切"

    def test_serie_b_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Sassuolo") == "萨索洛"
        assert lookup_zh("Palermo") == "巴勒莫"

    def test_2_bundesliga_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Hamburg") == "汉堡"
        assert lookup_zh("Schalke 04") == "沙尔克 04"

    def test_ligue_2_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Lorient") == "洛里昂"
        assert lookup_zh("Metz") == "梅斯"

    def test_eredivisie_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Ajax") == "阿贾克斯"
        assert lookup_zh("PSV") == "埃因霍温"
        assert lookup_zh("Feyenoord") == "费耶诺德"

    def test_primeira_liga_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Porto") == "波尔图"
        assert lookup_zh("Benfica") == "本菲卡"
        assert lookup_zh("Sporting CP") == "葡萄牙体育"

    def test_bel_pro_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Club Brugge") == "布鲁日"
        assert lookup_zh("Anderlecht") == "安德莱赫特"

    def test_j1_pick(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Vissel Kobe") == "神户胜利船"
        assert lookup_zh("Kawasaki Frontale") == "川崎前锋"
        assert lookup_zh("Urawa Red Diamonds") == "浦和红钻"

    def test_alias_variants_resolve(self):
        """V11 P1-FE#7: a few common spelling variants from the
        team_canonical alias map should also resolve."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        # English ↔ German form
        assert lookup_zh("Cologne") == lookup_zh("Koln") == "科隆"
        # Different short forms
        assert lookup_zh("Hamburger SV") == lookup_zh("Hamburg") == "汉堡"
        # Initials ↔ full
        assert lookup_zh("PSV") == lookup_zh("PSV Eindhoven") == "埃因霍温"


class TestV12W7CupAndVariants:
    """V12 W7 — gaps found by scanning cached API-Football fixtures for the
    names the API actually returns (short J1 names, league variants, cup clubs).
    Triggered by the live '神户胜利船 vs Kashima' half-translated card."""

    def test_j1_short_names(self):
        """API returns short J1 names the dict only had under full names."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Kashima") == "鹿岛鹿角"          # was "Kashima Antlers"
        assert lookup_zh("Urawa") == "浦和红钻"
        assert lookup_zh("V-varen Nagasaki") == "V法伦长崎"
        assert lookup_zh("Shimizu S-pulse") == "清水心跳"
        assert lookup_zh("Fagiano Okayama") == "冈山绿雉"

    def test_core_league_api_variants(self):
        """API spellings the canonical dict didn't key (and _zhFold can't
        bridge: AS / VfL / Hellas / München / Utd / Athletic Club)."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("AS Roma") == "罗马"
        assert lookup_zh("Hellas Verona") == "维罗纳"
        assert lookup_zh("VfL Wolfsburg") == "沃尔夫斯堡"
        assert lookup_zh("Sheffield Utd") == "谢菲尔德联"
        assert lookup_zh("Athletic Club") == "毕尔巴鄂竞技"  # Athletic Bilbao
        assert lookup_zh("Bayern München") == "拜仁慕尼黑"

    def test_cup_clubs_and_euro_nations(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Galatasaray") == "加拉塔萨雷"
        assert lookup_zh("Celtic") == "凯尔特人"
        assert lookup_zh("Shakhtar Donetsk") == "顿涅茨克矿工"
        assert lookup_zh("Kosovo") == "科索沃"  # WC/Euro qualifier nation

    def test_crvena_zvezda_not_paris_red_star(self):
        """Trap guard: the dict's 'Red Star' is Paris Red Star (巴黎红星).
        Crvena Zvezda is Belgrade Red Star — must NOT collide."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("FK Crvena Zvezda") == "贝尔格莱德红星"
        assert lookup_zh("Red Star") == "巴黎红星"  # unchanged


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
                   "_evLegCard"):
            idx = html.index(f"function {fn}")
            # Look in the next 4000 chars (renderTodaySingle grew with the V12
            # W8i inline 竞彩 SP row + W8k prediction body before the header).
            body = html[idx:idx+4000]
            assert "zhTeam(" in body, f"{fn} doesn't call zhTeam"

    def test_team_zh_endpoint_url_used(self, html):
        """Dashboard JS must call the new endpoint."""
        assert "/team-name-zh" in html
