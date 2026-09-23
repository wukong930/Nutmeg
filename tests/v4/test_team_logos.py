"""V11 P1-FE#2 Day 2 — tests for team logo cache + serve endpoint + slug helper.

Tests don't depend on actual logo PNGs being downloaded — they:
1. Exercise the `team_slug` + `logo_path` Python helpers (pure functions)
2. Confirm the endpoint returns 404 when no logo cached (the expected
   default state in CI / fresh checkouts)
3. Confirm 200 + image/png when a real PNG is staged in a tmp dir
4. Validate dashboard JS wiring (teamLogo helper + render integration)
5. Validate the CLI module imports clean
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


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


# ---------- team_slug + logo_path helpers --------------------------------

class TestTeamSlug:
    def test_basic_cases(self):
        from nutmeg.v4.data.team_logos import team_slug
        assert team_slug("Arsenal") == "arsenal"
        assert team_slug("Real Madrid") == "real_madrid"
        assert team_slug("AC Milan") == "ac_milan"
        assert team_slug("Bayern Munich") == "bayern_munich"
        assert team_slug("Paris SG") == "paris_sg"

    def test_strips_punctuation(self):
        from nutmeg.v4.data.team_logos import team_slug
        # Hyphens, periods, leading/trailing spaces → underscore-collapsed
        assert team_slug("Saint-Etienne") == "saint_etienne"
        assert team_slug("St. Pauli") == "st_pauli"
        assert team_slug("  West Ham  ") == "west_ham"

    def test_handles_empty(self):
        from nutmeg.v4.data.team_logos import team_slug
        assert team_slug("") == ""
        assert team_slug(None) == ""  # type: ignore[arg-type]

    def test_collapses_repeated_separators(self):
        from nutmeg.v4.data.team_logos import team_slug
        assert team_slug("A   B") == "a_b"
        assert team_slug("--Foo!!") == "foo"


class TestLogoPath:
    def test_returns_path_in_cache_dir(self, tmp_path):
        from nutmeg.v4.data.team_logos import logo_path
        p = logo_path("Arsenal", cache_dir=tmp_path)
        assert p == tmp_path / "arsenal.png"

    def test_default_cache_dir(self):
        from nutmeg.v4.data.team_logos import LOGO_CACHE_DIR, logo_path
        p = logo_path("Arsenal")
        assert p == LOGO_CACHE_DIR / "arsenal.png"

    def test_logo_exists_false_when_missing(self, tmp_path):
        from nutmeg.v4.data.team_logos import logo_exists
        assert logo_exists("Arsenal", cache_dir=tmp_path) is False

    def test_logo_exists_true_when_present(self, tmp_path):
        from nutmeg.v4.data.team_logos import logo_exists, logo_path
        (logo_path("Arsenal", cache_dir=tmp_path)).write_bytes(b"\x89PNG\r\n")
        assert logo_exists("Arsenal", cache_dir=tmp_path) is True


# ---------- /api/v4/team-logo/{slug} endpoint ----------------------------

class TestTeamLogoEndpoint:
    def test_unknown_slug_returns_404(self, client):
        r = client.get("/api/v4/team-logo/team_that_definitely_does_not_exist_xyz123")
        assert r.status_code == 404

    def test_invalid_slug_returns_404(self, client):
        """Path traversal / weird chars should not 200."""
        for bad in ("../passwd", "Arsenal", "weird;chars", "with spaces"):
            r = client.get(f"/api/v4/team-logo/{bad}")
            # 404 from either Pydantic / our slug regex / file not found
            assert r.status_code in (404, 405, 422), f"bad slug {bad!r} returned {r.status_code}"

    def test_existing_logo_returns_png(self, tmp_path, monkeypatch):
        """Stage a fake PNG and confirm the endpoint serves it."""
        from nutmeg.v4.api import routes as routes_mod
        # Point _TEAM_LOGOS_DIR to our tmp dir
        monkeypatch.setattr(routes_mod, "_TEAM_LOGOS_DIR", tmp_path)
        (tmp_path / "arsenal.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")

        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        c = TestClient(app)
        r = c.get("/api/v4/team-logo/arsenal")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content.startswith(b"\x89PNG")
        # Aggressive caching for static logos
        assert "max-age" in r.headers.get("cache-control", "")


# ---------- Dashboard JS wiring -----------------------------------------

class TestDashboardLogoWiring:
    def test_team_logo_helper_defined(self, html):
        assert "function teamLogo(name)" in html

    def test_team_slug_helper_defined(self, html):
        assert "function teamSlug(name)" in html

    def test_team_initials_helper_defined(self, html):
        assert "function teamInitials(name)" in html

    def test_logo_url_uses_endpoint(self, html):
        """teamLogo() must build URL from /team-logo/{slug}."""
        assert "/team-logo/" in html

    def test_onerror_fallback_present(self, html):
        """Image must hide on 404 so the initials circle remains."""
        idx = html.index("function teamLogo")
        body = html[idx:idx+1500]
        assert "onerror" in body
        assert "this.style.display" in body

    def test_initials_helper_uses_zh_when_locale_zh(self, html):
        """When zh locale + team is in TEAM_ZH_DICT, initials should
        come from the Chinese name (e.g. 阿森 from 阿森纳)."""
        idx = html.index("function teamInitials")
        body = html[idx:idx+500]
        assert "TEAM_ZH_DICT" in body

    def test_css_team_logo_classes_defined(self, html):
        """Initials-circle CSS + 8-color palette."""
        assert ".team-logo {" in html
        # All 8 palette classes
        for i in range(8):
            assert f".tl-c{i} " in html, f"missing .tl-c{i} palette class"

    def test_team_logo_used_in_renders(self, html):
        """All 5 render functions should call teamLogo()."""
        for fn in ("renderTodaySingle", "renderRecommendations",
                   "renderSingleRecommendations", "renderPoolRecommendations",
                   "_evLegCard"):
            idx = html.index(f"function {fn}")
            # Window 4000 (was 3000): renderTodaySingle grew with the V12 W8m
            # 3-tier confidence badge, pushing the teamLogo() call further down.
            body = html[idx:idx+5200]
            assert "teamLogo(" in body, f"{fn} doesn't call teamLogo"


# ---------- CLI module imports cleanly ----------------------------------

class TestIngestCLIScaffold:
    def test_module_imports(self):
        """CLI module is importable + exposes main()."""
        from nutmeg.v4.cli import ingest_team_logos
        assert callable(ingest_team_logos.main)

    def test_pyproject_registered(self):
        """Console script is registered in pyproject.toml."""
        pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        assert "nutmeg-ingest-team-logos" in pyproject

    def test_help_works(self, capsys):
        """--help renders without crashing (arg parsing wired up)."""
        from nutmeg.v4.cli import ingest_team_logos
        with pytest.raises(SystemExit) as exc:
            ingest_team_logos.main(["--help"])
        assert exc.value.code == 0


# ---------- --from-fixture-cache (2026-08-04) ---------------------------
#
# 病史:`/teams?league=<杯赛>` 只给正赛名单。UCL 2026 实测 36 队,而资格赛的
# `Olympiakos Piraeus` / `Sparta Praha` 已经在盘面上却不在那 36 里 ⇒ 按 /teams
# 补队徽每年都会漏一批,症状是「有的队没圆标」——没人会当 bug 报。
# 修法是改从**已缓存的 /fixtures** 取(每行带 teams.*.logo,覆盖实际出场的人)。

class TestFromFixtureCache:
    def _fixture_cache(self, root, teams):
        """写一个嵌套的 _fixtures 缓存;嵌套是故意的 —— 真实缓存分子目录。"""
        d = root / "_fixtures" / "2026"
        d.mkdir(parents=True)
        (d / "f.json").write_text(json.dumps([
            {"teams": {"home": {"name": h, "logo": f"https://x/{h}.png"},
                       "away": {"name": a, "logo": f"https://x/{a}.png"}}}
            for h, a in teams
        ]))
        return root

    def _obs_db(self, path, names):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE odds_snapshots (home_team TEXT, away_team TEXT)")
        conn.executemany("INSERT INTO odds_snapshots VALUES (?, ?)",
                         [(n, n) for n in names])
        conn.commit()
        conn.close()

    def _run(self, tmp_path, monkeypatch, *, teams, pop, extra=()):
        """跑一次 --from-fixture-cache,返回**实际被下载的队名**。"""
        from nutmeg.v4.cli import ingest_team_logos as m
        api = self._fixture_cache(tmp_path / "api", teams)
        db = tmp_path / "obs.db"
        self._obs_db(db, pop)
        got = []

        def fake_dl(url, dest, **kw):
            got.append(dest.stem)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x89PNG")
            return True

        monkeypatch.setattr(m, "_download_logo", fake_dl)
        rc = m.main(["--from-fixture-cache", "--api-cache-dir", str(api),
                     "--observation-db", str(db), "--out-dir", str(tmp_path / "logos"),
                     "--throttle-ms", "0", *extra])
        assert rc == 0
        return got

    def test_downloads_only_the_bettable_population(self, tmp_path, monkeypatch):
        """⚠️ 这条是本模式的**安全闸**,不是锦上添花。

        实测 fixtures 缓存里 8,374 支队、其中 7,405 支本地没 PNG —— 不过滤就是
        把一整个下载器对着无关的低级别球队跑。人口取「上过盘面的队名」,
        和本项目「统计量只在会下注的人口上算」同一条纪律。
        """
        got = self._run(
            tmp_path, monkeypatch,
            teams=[("Sparta Praha", "Slavia Praha"), ("Nobody FC", "Nobody Utd")],
            pop=["Sparta Praha", "Slavia Praha"],
        )
        assert sorted(got) == ["slavia_praha", "sparta_praha"]
        assert "nobody_fc" not in got, "缓存里有但没上过盘面的队被下载了 —— 过滤没接上"

    def test_skips_national_teams(self, tmp_path, monkeypatch):
        """国家队走国旗 emoji(`_NATION_FLAG`),下 PNG 是白费带宽。"""
        got = self._run(
            tmp_path, monkeypatch,
            teams=[("Brazil", "Argentina"), ("Sparta Praha", "Koper")],
            pop=["Brazil", "Argentina", "Sparta Praha", "Koper"],
        )
        assert sorted(got) == ["koper", "sparta_praha"]

    def test_nested_and_broken_cache_files(self, tmp_path, monkeypatch):
        """坏掉的缓存文件不许打断整趟扫描 —— 半个 JSON 只该少一批,不该少全部。"""
        from nutmeg.v4.cli import ingest_team_logos as m
        api = self._fixture_cache(tmp_path / "api", [("Koper", "Bravo")])
        (api / "_fixtures" / "broken.json").write_text("{not json")
        urls = m._logo_urls_from_fixture_cache(api)
        assert set(urls) == {"Koper", "Bravo"}

    def test_league_and_season_still_required_without_the_flag(self, tmp_path):
        """放宽 required=True 之后,**旧用法必须照样被拦**。

        不加这条的话「忘了带 --league」会静默变成一趟什么都不做的成功运行 ——
        又一个「抓了空集也叫成功」。
        """
        from nutmeg.v4.cli import ingest_team_logos as m
        for argv in ([], ["--league", "EPL"], ["--season", "2026"]):
            with pytest.raises(SystemExit) as exc:
                m.main(argv)
            assert exc.value.code != 0, f"{argv} 应该被 argparse 拦下"

    def test_missing_db_is_not_fatal(self, tmp_path):
        """新 checkout 没有观测库。返回空人口 = 什么都不下,而不是崩。"""
        from nutmeg.v4.cli import ingest_team_logos as m
        assert m._bettable_team_names(tmp_path / "nope.db") == set()


class TestFlagTableIsTheAuthorityForSkipping:
    """🏳️ 2026-09-21 —— 「哪些队不该下队徽」的判据必须是**决定渲染的那张表**。

    ## 病史

    `ingest_team_logos` 原来用 `lookup_elo_code(name) is not None` 认国家队。
    那张 Elo 表对**所有年龄组/女足变体**都返回 None ⇒ 实测会给 `China W` /
    `Qatar U23` / `Philippines W` 等 **13 支国家队**下 PNG。
    面板 `teamLogo()` 是**国旗优先**,所以不会显示错 —— 但那些是死文件,
    而且下一个照着这条判据判的人会判错。

    ## 🚨 三种 Python 侧补丁全都不完整(量过,不是猜)

    942 支可投注人口、真值取「面板真的会渲成国旗的 62 支」:

        ① `lookup_elo_code(name)`            漏 13
        ② + 剥 `U23`/`W` 后缀再查 Elo        漏 7
        ③ `name in _NATIONAL_TEAMS`          漏 13
        ④ ②③ 并用                            漏 3

    全都因为引用**手工维护、会滞后**的表(`Korea DPR` / `Kyrgyz Republic` /
    `Philippines` 这些拼法就不在 Elo 表里)。
    ⇒ 直接读 `dashboard.html` 的 `_NATION_FLAG`,**按构造不可能漂**。
    同 [[syntactic-proxy-for-semantic-property]] 的「发现判据引用另一张不全的表」。
    """

    def _node_flags(self) -> dict:
        """真值:用 node 的 `JSON.parse` 解同一段 JS。"""
        import json as J
        import subprocess
        js = (REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text()
        i = js.index("const _NATION_FLAG = {"); j = js.index("function teamLogo(name)")
        r = subprocess.run(["node", "-e", js[i:j] + "\nconsole.log(JSON.stringify(_NATION_FLAG));"],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:1500]
        return J.loads(r.stdout)

    def test_the_python_parser_agrees_with_node(self) -> None:
        """⭐ 承重:正则解析必须和 JS 引擎**逐条相等**。

        块里有注释行(带引号的中文注释),裸正则会把注释当条目 ——
        所以实现是「先逐行剥 `//` 再正则」。这条就是那句话的验收。
        """
        from nutmeg.v4.data.team_logos import flag_table
        truth = self._node_flags()
        got = flag_table()
        assert len(truth) > 100, f"人口非平凡:node 只解出 {len(truth)} 条"
        assert got == truth, (
            f"Python 解析与 node 不一致:多 {sorted(set(got) - set(truth))[:5]} · "
            f"少 {sorted(set(truth) - set(got))[:5]}")

    def test_comment_stripping_is_exercised_by_a_synthetic_block(self, tmp_path: Path) -> None:
        """🚨 「剥注释」这条路径**真实内容碰不到** —— 所以用合成夹具打它。

        变异检验实测:把 `line.split("//")[0]` 拿掉,所有测试**照样全绿**。
        原因是当前块里的中文注释不含 `"键": "值"` 这种形状,剥不剥同一个结果。
        ⇒ 那条防御没被验证过。这条夹具在注释里塞一个**长得像条目**的串,
           不剥就会多解出一条。
        """
        from nutmeg.v4.data.team_logos import flag_table
        fake = tmp_path / "d.html"
        fake.write_text(
            'const _NATION_FLAG = {\n'
            '  "Real": "\U0001F1E8\U0001F1F3",\n'
            '  // 注释里有个长得像条目的东西: "Ghost": "\U0001F3F4"\n'
            '};\nfunction teamLogo(name) {}\n', encoding="utf-8")
        got = flag_table(fake)
        assert got == {"Real": "\U0001F1E8\U0001F1F3"}, (
            f"注释被当成条目解进来了:{got} —— `//` 剥离失效")

    def test_the_real_block_does_contain_comments(self) -> None:
        """⚠️ 非平凡性:真实块里确实有注释(否则上面那条防御是纯装饰)。"""
        js = (REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text()
        i = js.index("const _NATION_FLAG = {"); j = js.index("function teamLogo(name)")
        n = sum(1 for line in js[i:j].splitlines() if "//" in line)
        assert n >= 5, f"块内只有 {n} 行注释"

    def test_the_old_predicate_really_had_a_gap(self) -> None:
        """⭐ 本类的**实证**:旧判据(Elo 表)在真实人口上确实漏国家队。

        ⚠️ 我第一版写的是「新判据的跳过集 ⊇ 渲染集」—— 那是**空洞断言**:
           两边都是 `n in flag_table()`,差集恒空。新判据的正确性是**按构造**的
           (它读的就是决定渲染的那张表),不该假装成一个发现。
           可测的是**旧判据坏在哪**,以及坏到什么程度 —— 就是这条。
        """
        from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
        from nutmeg.v4.data.team_logos import flag_table
        db = REPO_ROOT / "data/v4_observation.db"
        if not db.exists():
            pytest.skip("没有观测库")
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "_itl", REPO_ROOT / "apps/api/src/nutmeg/v4/cli/ingest_team_logos.py")
        mod = importlib.util.module_from_spec(spec); sys.modules["_itl"] = mod
        spec.loader.exec_module(mod)
        pop = mod._bettable_team_names(db)
        assert len(pop) >= 500, f"人口非平凡:只有 {len(pop)} 支"
        flags = flag_table()
        rendered = {n for n in pop if n in flags}
        assert len(rendered) >= 40, f"人口非平凡:只有 {len(rendered)} 支会渲成国旗"
        old_gap = sorted(rendered - {n for n in pop if lookup_elo_code(n) is not None})
        assert old_gap, (
            "旧判据(Elo 表)已经没有缺口了 —— 那本类的理由要重查,"
            "可能是 Elo 表补全了")
        # 缺口的**形状**(2026-09-23 重做诊断):
        # 原诊断是「缺的全是年龄组/女足变体」—— 被欧国联上盘证伪:Greece / Kosovo /
        # Republic of Ireland 进了人口,也在缺口里。病因是 Elo 表**按构造**只收世界杯圈
        # (模块 docstring:WC 2026 的 48 队 + WC 2022,61 个键)。
        # ⇒ 新诊断:缺口 = 变体 ∪ **Elo 表里根本没有**的成年国家队。
        #    可证伪的那一半:非变体名字必须是**真缺**,不能是拼法对不上
        #    (那是另一种病,修法是补别名,不是换判据)。
        import re
        from nutmeg.v4.data.national_team_name_to_elo import TEAM_NAME_TO_ELO_CODE
        from nutmeg.v4.data.sources.odds_api import _norm_team
        odd = [n for n in old_gap if not re.search(r"\s(U\d\d|W)$", n)]
        elo_keys = {_norm_team(k) for k in TEAM_NAME_TO_ELO_CODE}
        assert len(elo_keys) >= 40, "人口非平凡"
        spelling = [n for n in odd if _norm_team(n) in elo_keys]
        assert not spelling, f"这些是拼法对不上而不是真缺,病因诊断要重做:{spelling}"

    def test_the_cli_actually_consults_the_flag_table(self, monkeypatch) -> None:
        """🚨 承重:把判据**行为上**钉死在那张表上。

        前一版判据内联在 `main()` 里,没有任何测试盯得住它 ——
        改回 `lookup_elo_code` 不会红。抽成 `skip_as_national` 之后这条才打得到。
        做法:把 `flag_table` 换成一张假表,跳过集必须**跟着变**。
        """
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "_itl2", REPO_ROOT / "apps/api/src/nutmeg/v4/cli/ingest_team_logos.py")
        mod = importlib.util.module_from_spec(spec); sys.modules["_itl2"] = mod
        spec.loader.exec_module(mod)
        names = ["Wigan", "China W", "Qatar U23", "Aston Villa U21"]
        monkeypatch.setattr(mod, "flag_table", lambda: {"Wigan": "🏴"})
        assert mod.skip_as_national(names) == {"Wigan"}, (
            "判据没有真的去读 flag_table —— 换了表结果却没变")
        monkeypatch.setattr(mod, "flag_table", lambda: {})
        assert mod.skip_as_national(names) == set()

    def test_clubs_are_not_skipped(self) -> None:
        """🚨 反向守卫:判据不能宽到把俱乐部也跳掉(那就没队徽可下了)。"""
        from nutmeg.v4.data.team_logos import renders_as_flag
        from nutmeg.v4.data.team_logos import flag_table
        t = flag_table()
        for club in ("Wigan", "Blackpool", "Aston Villa U21", "Liverpool U21", "Notts County"):
            assert not renders_as_flag(club, table=t), f"{club} 被当成国家队了"

    def test_it_is_fail_closed_when_the_dashboard_is_missing(self, tmp_path: Path) -> None:
        """⛔ 读不到就抛,**不许 fail-soft**。

        静默返回空表 ⇒ 过滤变 no-op,症状是「多了一堆没人看的 PNG」,没人会报。
        """
        from nutmeg.v4.data.team_logos import flag_table
        with pytest.raises((FileNotFoundError, OSError)):
            flag_table(tmp_path / "nope.html")

