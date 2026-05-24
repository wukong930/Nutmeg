"""post-v9 P1#11 — structural sanity for monthly-token-check.yml.

This is a defensive test: catches YAML syntax breaks + missing critical
fields. The workflow can only be E2E-tested in actual GitHub Actions
(it needs the NUTMEG_API_FOOTBALL_KEY repo secret), so we just
validate static structure here.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WF_PATH = REPO_ROOT / ".github" / "workflows" / "monthly-token-check.yml"


@pytest.fixture(scope="module")
def workflow():
    assert WF_PATH.exists(), f"workflow file missing: {WF_PATH}"
    with WF_PATH.open() as f:
        return yaml.safe_load(f)


def test_workflow_has_name(workflow):
    assert workflow.get("name")


def test_workflow_schedule_first_of_month_09utc(workflow):
    # `on` is a YAML reserved key that becomes True boolean in some parsers.
    # PyYAML's safe_load keeps it as the string "on" by default.
    on_block = workflow.get(True) or workflow.get("on")
    assert on_block is not None
    schedule = on_block.get("schedule")
    assert schedule is not None
    # cron line should be "0 9 1 * *" (09:00 UTC on the 1st)
    cron_lines = [s.get("cron") for s in schedule]
    assert "0 9 1 * *" in cron_lines


def test_workflow_has_manual_dispatch(workflow):
    on_block = workflow.get(True) or workflow.get("on")
    assert "workflow_dispatch" in on_block


def test_workflow_uses_secret_not_inline_key(workflow):
    """Secret must be referenced via ${{ secrets.* }}, not hard-coded."""
    text = WF_PATH.read_text()
    assert "${{ secrets.NUTMEG_API_FOOTBALL_KEY }}" in text
    # Cheap key-leak check: 32-char hex string is the API key shape
    import re
    hex_keys = re.findall(r"\b[0-9a-f]{32}\b", text)
    assert not hex_keys, f"possible inline API key in workflow: {hex_keys}"


def test_workflow_probes_status_endpoint(workflow):
    """The whole point of the workflow is to hit /status; ensure it does."""
    text = WF_PATH.read_text()
    assert "/status" in text
    assert "v3.football.api-sports.io" in text


def test_workflow_surfaces_rotation_reminder(workflow):
    """V6 W8 advisory reminder must appear in the workflow notices."""
    text = WF_PATH.read_text()
    assert "rotate" in text.lower()
    # Plain user-action instruction must be present so the notice is actionable
    assert "gh secret set" in text
