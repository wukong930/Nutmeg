from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_phase9_api_integration_flow_exists() -> None:
    test_file = read("apps/api/tests/integration/test_phase9_mvp_flow.py")

    assert "test_phase9_complete_mock_flow_from_fixture_to_accuracy" in test_file
    assert "score_grid_to_market_probabilities" in test_file
    assert "evaluate_parlay" in test_file
    assert "evaluate_and_persist_post_match_result" in test_file
    assert "test_phase9_api_flow_exposes_mvp_acceptance_markers" in test_file


def test_phase9_playwright_e2e_is_configured() -> None:
    package_json = read("apps/web/package.json")
    config = read("apps/web/playwright.config.ts")
    spec = read("apps/web/e2e/mvp-flow.spec.ts")

    assert '"e2e": "npm run build && playwright test"' in package_json
    assert "@playwright/test" in package_json
    assert "Desktop Chrome" in config
    assert "Pixel 5" in config
    assert "Nutmeg MVP acceptance flow" in spec
    assert "/dashboard" in spec
    assert "/parlays" in spec
    assert "/accuracy" in spec


def test_phase9_vps_acceptance_script_checks_api_and_pages() -> None:
    makefile = read("Makefile")
    script = read("scripts/vps-acceptance.sh")
    deploy_script = read("scripts/deploy-vps.sh")
    gitignore = read(".gitignore")

    assert "acceptance-vps" in makefile
    assert "scripts/vps-acceptance.sh" in makefile
    assert "/api/v1/fixtures" in script
    assert "/api/v1/parlays/recommend" in script
    assert "/api/v1/accuracy/summary" in script
    assert "/api/v1/providers/status" in script
    assert "phase9_acceptance_ok" in script
    assert "Provider Runtime Incidents" in script
    assert "fallback incidents" in script
    assert "active window" in script
    assert "Incident filters" in script
    assert "Runtime Incident Runbook" in script
    assert "本工具仅提供概率分析与研究参考" in script
    assert "apps/web/test-results" in deploy_script
    assert "apps/web/playwright-report" in deploy_script
    assert "test-results/" in gitignore
    assert "playwright-report/" in gitignore
