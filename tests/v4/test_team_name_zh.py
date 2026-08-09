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
            body = html[idx:idx+5200]
            assert "zhTeam(" in body, f"{fn} doesn't call zhTeam"

    def test_team_zh_endpoint_url_used(self, html):
        """Dashboard JS must call the new endpoint."""
        assert "/team-name-zh" in html


# ---------- 2026-07-05 — ALL-CAPS anomaly class fix (PAU/GO Ahead/RED Star) ----

class TestAllCapsAnomalyFix:
    def test_red_star_fc_93_explicit_entry(self):
        """AF 2026-27 Ligue 2 spelling 'Red Star FC 93' — the 'FC 93' suffix is
        unreachable by case-fold or _zhFold, so it needs an explicit key."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Red Star FC 93") == "巴黎红星"

    def test_dict_has_no_case_only_collisions(self):
        """Safety proof for the frontend's case-insensitive zhTeam fallback:
        no two dict keys may differ ONLY by case (else lowercasing would pick a
        nondeterministic Chinese name). This invariant MUST hold for the
        fallback to be collision-free."""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        by_lower: dict[str, set[str]] = {}
        for k, v in TEAM_NAME_ZH.items():
            by_lower.setdefault(k.lower(), set()).add(v)
        collisions = {k: v for k, v in by_lower.items() if len(v) > 1}
        assert not collisions, f"case-only collisions break the fallback: {collisions}"

    def test_frontend_zhTeam_has_case_insensitive_fallback(self, html):
        """dashboard.html must build the lowercased index + use it as the last
        resort in zhTeam (kills the AF ALL-CAPS anomaly without per-team aliases)."""
        assert "TEAM_ZH_LOWER" in html
        assert "_rebuildTeamZhLower" in html
        idx = html.index("function zhTeam(name)")
        body = html[idx:idx + 1400]
        assert "TEAM_ZH_LOWER[name.toLowerCase()]" in body


# ---------- 2026-07-05 — Polymarket cross-check board teams (NWSL + Brazil) ----

class TestPolymarketBoardTeams:
    def test_nwsl_and_brazil_resolve(self):
        """Teams the Polymarket board surfaced as raw-English must now translate
        (they were the 'nothing changed' report — on the PM tab, not the betting
        boards)."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Angel City W") == "天使城女足"
        assert lookup_zh("Seattle Reign FC W") == "西雅图君临女足"
        assert lookup_zh("Ceara") == "塞阿拉"
        assert lookup_zh("Vila Nova") == "维拉诺瓦"

    def test_block_counted_in_coverage(self):
        """The new block must be registered in coverage_by_league or the
        TOTAL≤sum invariant silently breaks (prior regression)."""
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        assert "POLYMARKET_BOARD" in cov
        assert cov["POLYMARKET_BOARD"] >= 12


# ---------- 2026-07-05 — UEFA Q1 small-nation champions (待开盘常客) -----------

class TestUEFAQualifiers:
    def test_qualifier_teams_resolve(self):
        """The UEFA Q1 minnows that fill 近期赛事→待开盘 each July must translate
        (accents & AF spelling variants unreachable by case/fold)."""
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("Dečić") == "德契奇"
        assert lookup_zh("Rīgas FS") == "里加RFS"
        assert lookup_zh("Vllaznia Shkodër") == "弗拉兹尼亚"
        assert lookup_zh("St Joseph S Fc") == "圣约瑟夫"
        assert lookup_zh("HNK Hajduk Split") == "哈伊杜克"

    def test_block_counted_in_coverage(self):
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        cov = coverage_by_league()
        assert cov.get("UEFA_QUALIFIERS", 0) >= 48


# ---------- 2026-08-06 — AF 真实拼法别名 ---------------------------------

class TestAFSpellingAliases:
    """盘面/收盘线走 AF 原始拼法,词典只有清洗过的短名 ⇒ 前端显示英文。这一块把两侧接上。

    ⚠️ 这里原来写着「`nutmeg-harvest-team-zh` 的『结构上限』就是这个集合」——**假的**。
    工具的 `new_key_ceiling` 用语义尺子(`KnownTeams`),而这 25 条全是词典**已有
    球队**的另一种拼法 ⇒ 它在改动前后都打印「上限 0」(实测 939 键 → 0,964 键 → 0)。
    25 = 精确键口径的 26 减掉故意不要的 `Kyoto Sanga FC`。别照这句去跑 CLI 找「25」。
    """

    def test_af_spellings_resolve(self):
        from nutmeg.v4.data.team_name_zh import lookup_zh
        assert lookup_zh("SC Freiburg") == "弗赖堡"
        assert lookup_zh("VfL Bochum") == "波鸿"
        assert lookup_zh("1. FC Köln") == "科隆"
        # 重音兄弟键 —— 跟词典的「杜塞尔多夫」,不是竞彩的「杜塞多夫」
        assert lookup_zh("Fortuna Düsseldorf") == "杜塞尔多夫"
        assert lookup_zh("Shimizu S-Pulse") == "清水心跳"

    def test_the_two_entries_that_split_a_club_in_two_stay_fixed(self):
        """🚨 回归条 —— 首版这两条行尾写着「词典完全没有这支队」,**都是假的**:
        词典 407 行有 `Almere City: 阿尔梅勒城`、521 行有 `Kyoto Sanga: 京都不死鸟`。
        它们于是给同一支队造了第二个中文名 —— 正是这一块声称要治的病。

        · Almere:盘面实测只用 `Almere City FC` ⇒ 键留着,中文改成词典写法。
        · Kyoto:盘面实测 `Kyoto Sanga FC` 出现 0 次(只有 `Kyoto Sanga`)⇒ 整条删,
          留着只会把 `_ZH_OVERRIDES['京都']` 这个死 join 目标伪装成活的,并让前端
          `_enTeamForSettle` 从 known=false 翻成 true(静默关掉结算警告)。
        """
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH, lookup_zh
        assert lookup_zh("Almere City FC") == lookup_zh("Almere City") == "阿尔梅勒城"
        assert "Kyoto Sanga FC" not in TEAM_NAME_ZH
        assert lookup_zh("Kyoto Sanga") == "京都不死鸟"
        # 「京都」不再是任何键的值 ⇒ zh→en 反查落空 ⇒ 手工记账那条警告回来了。
        assert "京都" not in set(TEAM_NAME_ZH.values())

    def test_both_spellings_of_a_club_show_the_same_name(self):
        """这才是这一块存在的理由 —— 同一支队不能因上游拼法不同显示成两个名字。
        逐条按 `_EN_OVERRIDES`(短名 → AF 拼法)配对,不是挑几个样本。"""
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES
        from nutmeg.v4.data.team_name_zh import _AF_SPELLING_ALIASES_2026_08 as AF
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH, lookup_zh
        pairs = [(short, af) for short, af in _EN_OVERRIDES.items()
                 if af in AF and short in TEAM_NAME_ZH]
        assert len(pairs) >= 20, f"配对只剩 {len(pairs)} 对 —— _EN_OVERRIDES 变了?"
        for short, af in pairs:
            assert lookup_zh(short) == lookup_zh(af), (
                f"{short!r} 显示「{lookup_zh(short)}」但 {af!r} 显示「{lookup_zh(af)}」"
                " —— 同一支队两个名字,正是这一块要修的病")

    def test_no_entry_was_transliterated_and_dict_spelling_wins(self):
        """⭐ 两条红线一起钉住:

        ① 「绝不瞎猜队名」—— 每条中文都必须能从已有条目溯源;
        ② 词典已有这支队时**必须逐字取词典写法** —— 这一块全是别名键,取竞彩
           写法就会让同一支队显示成两个名字。

        ⚠️ 「同一支队」用的是**运行时那把尺子** `harvest_team_zh.KnownTeams`
        (`_EN_OVERRIDES` 反查 + `_affix_core` 折叠:大小写 / 重音 / 法定形式记号 /
        成立年份),不是本文件里另写一份。

        这条曾经的 fold 只折大小写+重音,比真正决定显示的那把弱:`SC Freiburg`
        对 `Freiburg`、`FC Schalke 04` 对 `Schalke` 都判不出「词典已有这支队」,
        于是 `if from_dict:` 那条「必须取词典写法」的分支整个跳过 —— 两条错别名
        (Almere / Kyoto)就是从那个缺口漏过去的。**护栏比它守的东西弱,等于没有。**
        """
        from nutmeg.v4.cli.harvest_team_zh import KnownTeams
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES
        from nutmeg.v4.data.team_name_zh import _AF_SPELLING_ALIASES_2026_08 as AF
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH

        base = {k: v for k, v in TEAM_NAME_ZH.items() if k not in AF}
        kt = KnownTeams(base, _EN_OVERRIDES)

        unsourced = []
        for en, zh in AF.items():
            hit = kt.lookup(en)
            if hit is None:
                unsourced.append(en)
                continue
            assert zh in hit.zhs, (
                f"{en!r} 写的中文是「{zh}」,但词典里同一支队({hit.how})写作 "
                f"{list(hit.zhs)} —— 别名键必须逐字跟词典,否则同一支队两个名字")
        assert not unsourced, (
            f"这些别名溯源不到词典里的任何一支队:{unsourced} —— 音译猜名是红线;"
            "确实是新队的话该写进对应联赛块,不该混在别名块里")

    def test_reverse_map_round_trips_for_every_chinese_name(self):
        """⭐ 别名遮蔽护栏(Waalwijk 2026-08-05 / 汉堡·PSV·科隆 07-04 同型):
        加别名键会往 `_ZH_TO_EN` 的 setdefault 里塞东西,一旦某个中文名反查到的
        英文名对应着**另一个**中文名,竞彩行就会静默 join 不上收盘线 —— 行照写、
        join 永死,只有人去看盘面才发现。2026-08-06 实测 0/808 违例,钉住。"""
        from nutmeg.v4.data.sources.sporttery import zh_to_canonical
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        bad = {zh: en for zh in set(TEAM_NAME_ZH.values())
               if (en := zh_to_canonical(zh)) and TEAM_NAME_ZH.get(en) != zh}
        assert not bad, f"中文名反查后对不回自己({len(bad)} 条):{list(bad.items())[:5]}"

    def test_block_counted_in_coverage(self):
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        assert coverage_by_league().get("AF_SPELLING_ALIASES", 0) == 25

    def test_no_club_in_the_whole_dict_carries_two_chinese_names(self):
        """⭐ 全词典级不变量,不只是这一块 —— 用运行时那把折叠尺子把所有键分组,
        一组里出现两个中文名就是「同一支队两个名字」。

        清单是**跑出来的**,不是推的:2026-08-06 实测只有 1 组,而且它是折叠尺子
        故意偏松的已知副作用(`Vitoria SC` = 葡超吉马良斯 vs `Vitoria` = 巴甲维多利亚,
        真是两支队)。名单变了 ⇒ 要么有人加了分裂条目,要么两支队被并到了一起,
        两种都得有人解释。
        """
        from nutmeg.v4.cli.harvest_team_zh import fold_key
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH

        known_split = {
            "vitoria": "折叠尺子偏松:Vitoria SC(葡超)和 Vitoria(巴甲)是两支队",
            # 2026-08-09 第二组,**和上面一模一样的形状**:
            # `Barcelona SC` = 厄瓜多尔瓜亚基尔的巴塞罗那(解放者杯,竞彩写「瓜亚基尔」),
            # `Barcelona`    = 西甲那个(竞彩写「巴塞罗那」)。**两支真实存在的不同球队**,
            # 剥掉 SC 之后折叠键撞在一起。
            # ⛔ 不许「把两边对齐」—— 对齐就是把厄瓜多尔的队并进巴萨,那才是真中毒。
            # 保护来自**池按联赛切**:实测同池两支时精确匹配先命中(各归各的);
            # 解放者杯的池里根本没有西甲巴萨。
            # ⭐ 竞彩把它叫「瓜亚基尔」(城市名)而不是「巴塞罗那」—— 这条映射是
            #   比分锚定拿到的,任何按英文翻译的做法都会在这里出灾难性错误。
            "barcelona": "折叠尺子偏松:Barcelona SC(厄瓜多尔)和 Barcelona(西甲)是两支队",
        }
        groups: dict[str, dict[str, list[str]]] = {}
        for k, v in TEAM_NAME_ZH.items():
            f = fold_key(k)
            if f:
                groups.setdefault(f, {}).setdefault(v, []).append(k)
        split = {f: d for f, d in groups.items() if len(d) > 1}
        new = {f: d for f, d in split.items() if f not in known_split}
        assert not new, (
            "同一支队出现了两个中文名:\n  "
            + "\n  ".join(f"{f}: {d}" for f, d in sorted(new.items())))
        assert set(split) == set(known_split), (
            f"已知的分裂组消失了(两侧靠拢了?)—— 更新清单:{set(known_split) - set(split)}")
