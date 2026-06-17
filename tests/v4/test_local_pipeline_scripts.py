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
                      "com.nutmeg.daily_settle",   # renamed from weekly_settle (now daily)
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

    def test_daily_settle_wires_log_rotation(self, setup_body):
        """2026-05-29: daily_settle appends `; rotate_logs.sh || true` so the
        always-on api_server daemon's logs stay bounded. Must use `;` (not
        `&&`) so rotation runs even if settle/report short-circuited."""
        assert "rotate_logs.sh" in setup_body, \
            "daily_settle must invoke scripts/rotate_logs.sh"
        # The rotation call must sit on the daily_settle command line, after
        # the settle/report chain, joined with `;` (always-run). Anchor on the
        # install_job invocation (not the header summary line that also names
        # the job).
        idx = setup_body.index('install_job "com.nutmeg.daily_settle"')
        # Capture the WHOLE daily_settle block (up to the next install_job) —
        # the command line grows as steps are appended (data_freshness sentinel,
        # etc.), so a fixed-width window would miss the trailing rotate_logs.sh.
        block = setup_body[idx:].split("\ninstall_job", 1)[0]
        assert "rotate_logs.sh" in block, \
            "rotate_logs.sh must be wired into the daily_settle job specifically"
        assert "; $REPO_ROOT/scripts/rotate_logs.sh" in block, \
            "rotation must be `;`-joined (run regardless of settle/report exit)"


class TestBackupScript:
    """体检 A2 — backup_observation_db.sh: online backup + rotation + checkpoint."""

    @pytest.fixture
    def bk(self) -> Path:
        return SCRIPTS_DIR / "backup_observation_db.sh"

    def test_exists_executable_strict(self, bk):
        assert bk.exists()
        assert bk.stat().st_mode & stat.S_IXUSR
        body = bk.read_text()
        assert body.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in body

    def test_online_backup_and_checkpoint(self, bk):
        body = bk.read_text()
        assert '".backup' in body, "must use sqlite3 .backup (online-safe), not cp"
        assert "wal_checkpoint(TRUNCATE)" in body
        assert "KEEP=7" in body, "rotation keeps 7 dailies"

    def test_covers_both_dbs(self, bk):
        body = bk.read_text()
        assert "data/v4_observation.db" in body
        assert "data/score_ev_forward.db" in body

    def test_registered_in_setup_without_or_true(self):
        setup = (SCRIPTS_DIR / "setup_local_pipeline.sh").read_text()
        assert "com.nutmeg.daily_backup" in setup
        idx = setup.index('install_job "com.nutmeg.daily_backup"')
        block = setup[idx:idx + 220]
        assert "backup_observation_db.sh" in block
        # 体检 P0-2: backup failures must NOT be masked
        assert "|| true" not in block


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


class TestRotateLogsScript:
    """2026-05-29 — scripts/rotate_logs.sh keeps launchd logs bounded.

    Deliberately NOT added to the SCRIPTS parametrize list (that would couple
    it to TestDocPresent's deployment-guide check); covered standalone here.
    """

    @pytest.fixture
    def path(self) -> Path:
        return SCRIPTS_DIR / "rotate_logs.sh"

    def test_exists_and_executable(self, path):
        assert path.exists(), "rotate_logs.sh missing"
        assert path.stat().st_mode & stat.S_IXUSR, "rotate_logs.sh not executable"

    def test_shebang_and_header(self, path):
        body = path.read_text()
        assert body.startswith("#!/usr/bin/env bash")
        assert "P1#16" in body, "missing P1#16 header reference"

    def test_strict_mode(self, path):
        # Uses `set -uo pipefail` (NOT -e: it must continue past a failed
        # tail on one file to rotate the rest).
        body = path.read_text()
        assert "set -uo pipefail" in body

    def test_only_touches_logs_launchd(self, path):
        body = path.read_text()
        assert "logs/launchd" in body
        # Must never `rm` a log file outright — copytruncate only.
        assert "rm -f \"$f\"" not in body and "rm \"$f\"" not in body

    def test_documents_copytruncate_rationale(self, path):
        """The daemon-fd reasoning is the whole point — keep it documented."""
        body = path.read_text()
        assert "copytruncate" in body
        assert "inode" in body

    def test_functional_rotation_keeps_tail(self, tmp_path):
        """End-to-end: a >max log is truncated to keep_lines, keeping the
        most-recent lines; a small log is left untouched."""
        # rotate_logs.sh derives LOG_DIR from its own location's ../logs/launchd,
        # so stage a mini repo-root layout in tmp_path.
        scripts_dir = tmp_path / "scripts"
        log_dir = tmp_path / "logs" / "launchd"
        scripts_dir.mkdir(parents=True)
        log_dir.mkdir(parents=True)
        (scripts_dir / "rotate_logs.sh").write_bytes(
            (SCRIPTS_DIR / "rotate_logs.sh").read_bytes()
        )
        (scripts_dir / "rotate_logs.sh").chmod(0o755)

        big = log_dir / "com.nutmeg.api_server.err.log"
        big.write_text("\n".join(f"line {i}" for i in range(6000)) + "\n")
        small = log_dir / "daily_odds.out.log"
        small.write_text("a\nb\n")
        big_inode_before = big.stat().st_ino

        proc = subprocess.run(
            [str(scripts_dir / "rotate_logs.sh"), "5000", "2000"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode == 0, proc.stderr

        kept = big.read_text().splitlines()
        assert len(kept) == 2000, f"expected 2000 kept lines, got {len(kept)}"
        # Tail preserved (recent lines), head dropped.
        assert kept[-1] == "line 5999"
        assert kept[0] == "line 4000"
        # copytruncate preserves the inode (daemon fd stays valid).
        assert big.stat().st_ino == big_inode_before, \
            "rotation must preserve inode (copytruncate, not mv)"
        # Small log untouched.
        assert small.read_text() == "a\nb\n"

    def test_refuses_bad_bounds(self, tmp_path):
        """keep_lines >= max_lines is a footgun → non-zero exit, no-op."""
        scripts_dir = tmp_path / "scripts"
        (tmp_path / "logs" / "launchd").mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "rotate_logs.sh").write_bytes(
            (SCRIPTS_DIR / "rotate_logs.sh").read_bytes()
        )
        (scripts_dir / "rotate_logs.sh").chmod(0o755)
        proc = subprocess.run(
            [str(scripts_dir / "rotate_logs.sh"), "2000", "5000"],
            capture_output=True, text=True, timeout=15,
        )
        assert proc.returncode != 0


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
