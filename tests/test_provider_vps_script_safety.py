from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_token_vps_helpers_do_not_use_check_output() -> None:
    scripts_dir = ROOT / "scripts"
    script_paths = sorted(scripts_dir.glob("vps-provider-*.sh")) + [
        scripts_dir / "provider-runtime-monitoring-local.sh"
    ]

    admin_scripts = [
        path
        for path in script_paths
        if "ADMIN_TOKEN" in path.read_text(encoding="utf-8")
    ]

    assert admin_scripts
    for path in admin_scripts:
        text = path.read_text(encoding="utf-8")
        assert "subprocess.check_output" not in text, path.name
        if path.name == "provider-runtime-monitoring-local.sh":
            assert "subprocess.run" in text
            assert "[redacted]" in text
            assert "/ops/provider-runs" in text
        else:
            assert "provider_request_helpers" in text, path.name
            assert "record_provider_ops_run" in text, path.name
        assert "provider-ops-run-history.sh" in text, path.name
        assert "nutmeg_provider_ops_install_failure_trap" in text, path.name


def test_provider_request_helper_redacts_secret_text() -> None:
    helper_path = ROOT / "scripts/provider_request_helpers.py"
    spec = importlib.util.spec_from_file_location(
        "provider_request_helpers",
        helper_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.safe_text("curl failed with token-value", ["token-value"]) == (
        "curl failed with [redacted]"
    )


def test_provider_request_helper_defines_run_history_recorder() -> None:
    helper = (ROOT / "scripts/provider_request_helpers.py").read_text(
        encoding="utf-8"
    )
    shell_helper = (ROOT / "scripts/provider-ops-run-history.sh").read_text(
        encoding="utf-8"
    )

    assert "def record_provider_ops_run" in helper
    assert "record-run" in helper
    assert "utc-now" in helper
    assert '"/ops/provider-runs"' in helper
    assert "provider_ops_run_history_record_failed" in helper
    assert "nutmeg_provider_ops_record_shell_failure" in shell_helper
    assert "failure_capture" in shell_helper
