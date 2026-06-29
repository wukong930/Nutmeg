"""post-v9 P1#15 — Playwright E2E + axe-core WCAG audit.

Critical-path tests that exercise the dashboard in a real headless
Chromium. These complement the structural tests in
test_frontend_responsive_a11y.py + test_i18n_and_pwa.py — those
assert HTML/JS contents; these assert RUNTIME behavior.

Requires:
  uv pip install --python .venv/bin/python playwright pytest-playwright
  .venv/bin/playwright install chromium

Each test launches a uvicorn server on an ephemeral port, runs the
browser scenario, then tears down. Skipped if Playwright isn't
installed (CI without browser bins should still pass).

WCAG audit (TestAxeCoreWCAG) loads axe-core CDN script into the page,
runs axe.run(), asserts no AA-level violations.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# Skip the whole module if playwright isn't installed or browser is missing
try:
    from playwright.sync_api import sync_playwright   # noqa: F401
    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _PW_AVAILABLE,
    reason="playwright not installed (uv pip install playwright pytest-playwright)",
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    """Launch uvicorn on an ephemeral port; tear down at module end."""
    port = _free_port()
    env = {**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "apps" / "api" / "src")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "nutmeg.main:app",
         "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "error"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server to come up (poll /docs)
    import httpx
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(40):   # up to 8s
        try:
            r = httpx.get(base_url + "/docs", timeout=0.2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("uvicorn didn't start within 8s")

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def page(server):
    """Module-scoped browser page so tests reuse a single Chromium."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium browser missing: {e}; run `playwright install chromium`")
        ctx = browser.new_context(locale="en-US")   # default en for testing toggle
        page = ctx.new_page()
        yield page
        ctx.close()
        browser.close()


# ============ Critical-path E2E ====================================

class TestPageLoadsAndRenders:
    def test_dashboard_loads_with_title(self, page, server):
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        # Title element exists and is non-empty
        h1 = page.locator("h1").first
        assert h1.is_visible()
        text = h1.text_content().strip()
        assert text   # i18n applied → either Chinese or English title

    def test_all_5_tabs_render(self, page, server):
        # Top-level tabs: today / upcoming / custom (单关·串关·复式 合并) /
        # history / admin. 单关/串关/复式 are now sub-tabs inside 自定义玩法.
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        tabs = page.locator("button.tab-btn")
        assert tabs.count() == 5


class TestTabSwitching:
    def test_clicking_pool_subtab_shows_pool_panel(self, page, server):
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        # V10 W1: default landing is 今日推荐
        assert page.locator("#tab-today").is_visible()
        # 复式 is now a sub-tab inside 自定义玩法 — open the tab, then the sub-tab.
        page.locator("button[data-tab='custom']").click()
        page.locator("button[data-sub='pool']").click()
        # Pool sub-panel visible, today panel hidden
        assert page.locator("#tab-pool").is_visible()
        assert not page.locator("#tab-today").is_visible()
        # custom tab + pool sub-tab aria-selected updated
        assert page.locator("button[data-tab='custom']").get_attribute("aria-selected") == "true"
        assert page.locator("button[data-sub='pool']").get_attribute("aria-selected") == "true"
        assert page.locator("button[data-tab='today']").get_attribute("aria-selected") == "false"


class TestThemeToggle:
    """V11 P1-FE#1 — verify the theme toggle works + persists.

    Note: pytest-playwright reuses browser context across tests in a module
    by default. Each test below clears localStorage at start to ensure
    a clean dark-default starting state.
    """

    def _reset_theme(self, page, server):
        page.goto(f"{server}/api/v4/dashboard")
        page.evaluate("localStorage.removeItem('nutmeg-theme')")
        page.reload()
        page.wait_for_load_state("networkidle")

    def test_default_theme_is_dark(self, page, server):
        self._reset_theme(page, server)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "dark"
        has_dark_class = page.evaluate(
            "document.documentElement.classList.contains('dark')"
        )
        assert has_dark_class

    def test_toggle_switches_to_light(self, page, server):
        self._reset_theme(page, server)
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(50)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "light"
        # Stored in localStorage
        stored = page.evaluate("localStorage.getItem('nutmeg-theme')")
        assert stored == "light"

    def test_toggle_back_to_dark(self, page, server):
        self._reset_theme(page, server)
        page.locator("#theme-toggle").click()  # dark → light
        page.locator("#theme-toggle").click()  # light → dark
        page.wait_for_timeout(50)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme == "dark"


class TestI18nToggleRuntime:
    def test_initial_locale_from_browser(self, page, server):
        """en-US browser → init should pick en (per initLocale browser-detect)."""
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        # Header h1 should be in English variant
        h1 = page.locator("h1").first.text_content()
        # English app_title is "Nutmeg · Football Betting Helper"
        assert "Football Betting Helper" in h1

    def test_toggle_switches_to_zh_and_back(self, page, server):
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        h1_en = page.locator("h1").first.text_content().strip()
        # Click toggle (en → zh)
        page.locator("#lang-toggle").click()
        page.wait_for_timeout(100)
        h1_zh = page.locator("h1").first.text_content().strip()
        assert h1_en != h1_zh, "toggle should change h1 text"
        assert "竞彩" in h1_zh   # zh variant has 竞彩

        # Toggle button label flipped to '中' was after switching FROM zh,
        # we're currently zh so toggle label should now be 'EN'
        toggle_after = page.locator("#lang-toggle").text_content().strip()
        assert toggle_after == "EN"

        # Toggle back
        page.locator("#lang-toggle").click()
        page.wait_for_timeout(100)
        h1_en2 = page.locator("h1").first.text_content().strip()
        assert h1_en2 == h1_en


class TestPWAResources:
    def test_manifest_loads(self, page, server):
        page.goto(f"{server}/api/v4/manifest.json")
        # The page renders as JSON; just check we got 200
        assert page.url.endswith("/manifest.json")

    def test_service_worker_registers(self, page, server):
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        # Wait briefly for SW registration to happen (load event fires)
        page.wait_for_timeout(500)
        # Check SW state via JS
        registered = page.evaluate("""
            async () => {
                const reg = await navigator.serviceWorker.getRegistration('/api/v4/');
                return reg ? reg.scope : null;
            }
        """)
        # In headless Chromium SW registration should succeed
        assert registered and registered.endswith("/api/v4/")


# ============ WCAG (axe-core) audit ================================

# axe-core CDN URL (pinned to a specific version for reproducible runs)
AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


class TestAxeCoreWCAG:
    def _run_axe(self, page, server, locale="en"):
        """Inject axe-core via CDN, run it, return violations list."""
        page.goto(f"{server}/api/v4/dashboard")
        page.wait_for_load_state("networkidle")
        # If we want a specific locale, toggle first
        if locale == "zh":
            # If currently en (browser detect), toggle to zh
            current = page.locator("html").get_attribute("lang") or "en"
            if current.startswith("en"):
                page.locator("#lang-toggle").click()
                page.wait_for_timeout(100)
        try:
            page.add_script_tag(url=AXE_CDN)
        except Exception as e:
            pytest.skip(f"axe-core CDN not reachable: {e}")
        results = page.evaluate("""
            async () => {
                const r = await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
                });
                return r.violations;
            }
        """)
        return results

    def test_no_wcag_aa_violations_en(self, page, server):
        violations = self._run_axe(page, server, locale="en")
        # Format failing violations clearly so test output shows what to fix
        if violations:
            details = [
                f"  - {v['id']} ({v['impact']}): {v['description']} "
                f"(affects {len(v['nodes'])} element(s))"
                for v in violations
            ]
            msg = "WCAG AA violations found:\n" + "\n".join(details)
            pytest.fail(msg)

    def test_no_wcag_aa_violations_zh(self, page, server):
        violations = self._run_axe(page, server, locale="zh")
        if violations:
            details = [
                f"  - {v['id']} ({v['impact']}): {v['description']}"
                for v in violations
            ]
            pytest.fail("WCAG AA violations (zh locale):\n" + "\n".join(details))
