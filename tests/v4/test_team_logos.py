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
                   "renderWcMatch"):
            idx = html.index(f"function {fn}")
            body = html[idx:idx+3000]
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
