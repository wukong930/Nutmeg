"""AUDIT FIX (D1 / R5) — Layer A self-calibration deploy path.

The V12 audit found Layer A was a *silent no-op in production*: the weekly
calibration cron (and the documented manual deploy step) wrote
``live_T_correction.json`` into ``data/v4_model`` — the LightGBM default dir —
while serving reads corrections from ``NUTMEG_V4_ARTIFACT_PATH`` (= the CatBoost
``data/v4_model_cat`` in .env). Different dir, not a symlink → the correction
fit, passed the gate, journaled, and reported "no restart needed", but serving
read None and applied identity T=1.0 forever. The auto-rollback safety net
pointed at the same wrong dir, so it was dead too.

The 24 existing auto_calibration tests could NOT catch this: every one writes
and reads the correction in the SAME tmp dir, so the env≠deploy-dir mismatch was
a structural blind spot (audit R5). These two tests close it:

  1. serving reads corrections ONLY from its configured artifact dir, so a
     deploy to any other dir is provably a no-op (the D1 bug, reproduced);
  2. the shipped weekly-calibration cron deploys to the dir serving actually
     reads, locked by string so a revert to ``data/v4_model`` fails CI.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nutmeg.v4.observation.auto_calibration import LIVE_T_CORRECTION_FILENAME

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_correction_only_read_from_serving_artifact_dir(tmp_path, monkeypatch):
    """Reproduce D1: a correction deployed to a dir other than
    NUTMEG_V4_ARTIFACT_PATH is invisible to serving (identity T); deploying to
    the serving dir takes effect."""
    import nutmeg.v4.api.routes as routes

    serving_dir = tmp_path / "v4_model_cat"   # what NUTMEG_V4_ARTIFACT_PATH points at
    deploy_dir = tmp_path / "v4_model"        # the stale dir the cron used
    serving_dir.mkdir()
    deploy_dir.mkdir()
    payload = json.dumps({"T": 1.4, "previous_T": 1.0})

    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(serving_dir))
    routes._correction_cache.clear()
    routes._pointer_cache.clear()

    # Deploy to the WRONG dir → serving sees nothing (this is the D1 no-op).
    (deploy_dir / LIVE_T_CORRECTION_FILENAME).write_text(payload)
    assert routes._load_correction() is None

    # Deploy to the SERVING dir → serving picks it up on the next request.
    (serving_dir / LIVE_T_CORRECTION_FILENAME).write_text(payload)
    routes._correction_cache.clear()
    corr = routes._load_correction()
    assert corr is not None
    assert corr["T"] == 1.4


def test_setup_script_deploys_to_serving_artifact_dir():
    """The weekly calibration cron must deploy to the dir serving reads
    (data/v4_model_cat), not the stale data/v4_model. Locks the D1 fix at the
    actual mismatch site."""
    script = (_REPO_ROOT / "scripts" / "setup_local_pipeline.sh").read_text()
    m = re.search(r'ARTIFACT_DIR="\$REPO_ROOT/(data/[^"]+)"', script)
    assert m, "could not find calibration ARTIFACT_DIR in setup_local_pipeline.sh"
    assert m.group(1) == "data/v4_model_cat", (
        f"weekly calibration deploys to {m.group(1)!r}, but serving reads "
        "data/v4_model_cat (NUTMEG_V4_ARTIFACT_PATH) — Layer A would be a silent "
        "no-op (audit D1)"
    )
    # The deploy flag must reference that dir.
    assert "--deploy-artifact $ARTIFACT_DIR" in script


def test_operator_guide_deploys_to_serving_artifact_dir():
    """The operator-facing deploy guide must not tell users to --deploy-artifact
    data/v4_model (the silent-no-op dir)."""
    guide = (_REPO_ROOT / "docs" / "local_deployment_guide.md").read_text()
    assert "--deploy-artifact data/v4_model\n" not in guide
    assert "--deploy-artifact data/v4_model`" not in guide
    assert "--deploy-artifact data/v4_model " not in guide
    assert "--deploy-artifact data/v4_model_cat" in guide


def test_weekly_report_filenames_use_iso_year():
    """AUDIT FIX (D5): weekly report filenames use the ISO week number (%V),
    which MUST pair with the ISO year (%G), not the calendar year (%Y).
    Otherwise e.g. Sun 2027-01-03 (ISO 2026-W53) is filed as 2027-W53 and a
    2027 run with the same %V can overwrite the prior year's evidence."""
    script = (_REPO_ROOT / "scripts" / "setup_local_pipeline.sh").read_text()
    assert "%Y-W%V" not in script, "ISO week (%V) must pair with ISO year (%G)"
    assert "%G-W%V" in script
