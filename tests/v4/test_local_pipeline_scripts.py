"""post-v9 P1#16 — local-deployment pipeline scripts.

Structural tests for the 4 shell scripts in scripts/. These verify:
- Scripts exist + are executable
- Each has a usage/description header
- setup_local_pipeline.sh writes the 3 expected plists
- health_check.sh runs without errors (even in unhealthy state — it
  returns exit 1 then but doesn't crash)
- All scripts reference the right paths (.venv, .env, data/)

These complement the actual launchd integration (which we can't
test in CI without invoking launchctl — that requires user keychain
access). Structural correctness is what we can verify automatically.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


SCRIPTS = [
    "health_check.sh",
    "setup_local_pipeline.sh",
    "teardown_local_pipeline.sh",
    "run_local_server.sh",
]


@pytest.mark.parametrize("name", SCRIPTS)
class TestScriptStructure:
    def test_exists(self, name):
        assert (SCRIPTS_DIR / name).exists(), f"{name} missing"

    def test_executable(self, name):
        path = SCRIPTS_DIR / name
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{name} not executable (chmod +x missing)"

    def test_has_shebang(self, name):
        body = (SCRIPTS_DIR / name).read_text()
        assert body.startswith("#!/usr/bin/env bash"), f"{name} missing bash shebang"

    def test_has_description(self, name):
        body = (SCRIPTS_DIR / name).read_text()
        # Each script should reference P1#16 in its header docstring
        assert "P1#16" in body, f"{name} missing P1#16 reference in header"

    def test_uses_set_strict_mode(self, name):
        """All scripts use `set -e` or similar so failures don't silently pass."""
        body = (SCRIPTS_DIR / name).read_text()
        # Either -euo pipefail (preferred) or -uo (health_check uses without -e
        # because it wants to print all checks even when one fails)
        head = body.split("\n", 30)[:30]
        assert any("set -" in line and ("euo" in line or "uo pipefail" in line)
                   for line in head), f"{name} missing strict mode (set -e/u/o)"


class TestSetupScriptContent:
    @pytest.fixture
    def setup_body(self) -> str:
        return (SCRIPTS_DIR / "setup_local_pipeline.sh").read_text()

    def test_installs_named_jobs(self, setup_body):
        # post-v9 P1#24: added com.nutmeg.weekly_gate (4th job)
        for label in ("com.nutmeg.daily_odds",
                      "com.nutmeg.daily_recommend",
                      "com.nutmeg.weekly_settle",
                      "com.nutmeg.weekly_gate"):
            assert label in setup_body, f"setup missing job label: {label}"

    def test_uses_launchctl_bootstrap(self, setup_body):
        # Modern launchd API: bootout + bootstrap (not the older load/unload)
        assert "launchctl bootstrap" in setup_body
        assert "launchctl bootout" in setup_body

    def test_writes_to_user_launchagents(self, setup_body):
        assert "$HOME/Library/LaunchAgents" in setup_body

    def test_writes_logs_to_logs_launchd(self, setup_body):
        assert "logs/launchd" in setup_body

    def test_reads_env_for_api_key(self, setup_body):
        # Jobs must source .env so NUTMEG_API_FOOTBALL_KEY is set
        assert "source .env" in setup_body
        # The key value must NOT be injected directly into the plist via
        # EnvironmentVariables (which would persist on disk). The plist may
        # mention the var name in comments — that's a docstring reference.
        # The actual anti-pattern would be `<string>$NUTMEG_API_FOOTBALL_KEY</string>`
        # inside an EnvironmentVariables dict.
        bad = "<string>${NUTMEG_API_FOOTBALL_KEY}</string>"
        bad2 = "<string>$NUTMEG_API_FOOTBALL_KEY</string>"
        assert bad not in setup_body and bad2 not in setup_body, \
            "API key value must NOT be inlined in plist; source from .env at run time"

    def test_macos_only_guard(self, setup_body):
        assert "Darwin" in setup_body, "setup should refuse to run on non-macOS"


class TestHealthCheckScriptContent:
    @pytest.fixture
    def hc_body(self) -> str:
        return (SCRIPTS_DIR / "health_check.sh").read_text()

    def test_checks_all_five_sections(self, hc_body):
        # Header sections from the design
        for section in ("API key", "launchd jobs", "Cup odds",
                        "Observation DB", "Disk usage"):
            assert section in hc_body, f"missing section header: {section}"

    def test_checks_v10_trigger_thresholds(self, hc_body):
        # Path A threshold + lineup ROI threshold
        assert "250" in hc_body, "cup ablation trigger threshold (250 rows) missing"
        assert "60" in hc_body, "lineup ROI trigger threshold (60 settlements) missing"

    def test_safe_to_run_anytime(self, hc_body):
        # Should NOT mutate state. Look for no obvious mutating calls.
        # (cd into repo is OK; we just don't want rm/mkdir/launchctl commands
        # in the health check)
        assert "launchctl bootstrap" not in hc_body
        assert "launchctl bootout" not in hc_body


class TestRunLocalServerScriptContent:
    @pytest.fixture
    def srv_body(self) -> str:
        return (SCRIPTS_DIR / "run_local_server.sh").read_text()

    def test_uses_uvicorn(self, srv_body):
        assert ".venv/bin/uvicorn nutmeg.main:app" in srv_body

    def test_supports_lan_binding(self, srv_body):
        assert '"lan"' in srv_body
        assert '0.0.0.0' in srv_body

    def test_sources_env(self, srv_body):
        assert "source .env" in srv_body


class TestHealthCheckRunsSuccessfully:
    """Actually execute the health check (it returns exit 1 when pipeline
    isn't set up, but should NOT crash on bash errors)."""

    def test_health_check_runs_without_crash(self):
        proc = subprocess.run(
            [str(SCRIPTS_DIR / "health_check.sh")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        # Exit code 0 (healthy) or 1 (not healthy) are both acceptable —
        # the script must NOT crash with bash syntax errors (which would
        # produce a different exit code)
        assert proc.returncode in (0, 1), (
            f"health_check.sh crashed with exit={proc.returncode}\n"
            f"stdout: {proc.stdout[-400:]}\nstderr: {proc.stderr[-400:]}"
        )

    def test_health_check_emits_expected_sections(self):
        proc = subprocess.run(
            [str(SCRIPTS_DIR / "health_check.sh")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = proc.stdout
        for section in ("API key", "launchd jobs", "Cup odds",
                        "Observation DB", "Summary"):
            assert section in out, f"section missing from output: {section}"


class TestDocPresent:
    def test_local_deployment_guide_exists(self):
        guide = REPO_ROOT / "docs" / "local_deployment_guide.md"
        assert guide.exists()
        body = guide.read_text()
        # Doc should reference all 4 scripts
        for name in SCRIPTS:
            assert name in body, f"guide doesn't mention {name}"
        # Doc should explain V10 trigger thresholds
        assert "250" in body
        assert "60" in body
