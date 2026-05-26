"""Regression test for the post-V11 audit (2026-05-26) cron model_type bug.

Background
----------
``nutmeg.v4.cli.recommend`` records a session into the observation DB
when ``--record-to <path>`` is set. Before the audit fix, the response
payload it built did NOT include ``model_type`` inside the ``model``
dict, so ``recorder.record_session`` defaulted to ``"lightgbm"`` —
silently mis-tagging every production cron session (production model
is V6 W7 lineup-aware *CatBoost*).

This test runs the CLI end-to-end with the real production artifact
and verifies the resulting ``recommendation_sessions.model_type``
matches what the artifact's ``model_type.txt`` says. Gated on the
artifact + demo CSV being present (matches existing test_e2e.py
skipif convention).

Why a dedicated test file:
  - The bug surfaced only at runtime + only when --record-to was used.
    No prior unit test exercised that code path.
  - A literal-string assertion on recommend.py's source ("model_type"
    appears in the response dict) would also catch the regression,
    but the e2e variant doubles as a smoke test for the full cron
    pipeline (Job 2 of setup_local_pipeline.sh).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model_cat_lineups"
DEMO_FIXTURES = REPO_ROOT / "data" / "demo" / "today_fixtures.csv"


def _artifact_model_type() -> str | None:
    """Read the artifact's declared model_type. Returns None if missing.

    The artifact stores model_type in metadata.json (V5 W7 convention).
    """
    import json
    meta = ARTIFACT_PATH / "metadata.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text())
    except Exception:
        return None
    # metadata.json wraps under a top-level "metadata" key in some
    # artifacts and is flat in others.
    if "model_type" in data:
        return data["model_type"]
    if "metadata" in data and isinstance(data["metadata"], dict):
        return data["metadata"].get("model_type")
    return None


@pytest.mark.skipif(
    not ARTIFACT_PATH.exists() or not DEMO_FIXTURES.exists(),
    reason="needs production artifact (data/v4_model_cat_lineups) + demo CSV",
)
class TestRecommendCliRecordsModelType:
    """The cron-equivalent invocation must tag the session with the
    correct artifact model_type so `nutmeg-ab-report --model-type X`
    finds the rows it should."""

    def test_session_model_type_matches_artifact(self, tmp_path):
        """End-to-end: run the CLI with --record-to, inspect the DB row."""
        expected_model_type = _artifact_model_type()
        assert expected_model_type is not None, (
            "demo artifact metadata.json missing model_type — set it"
            " before running this test"
        )

        db = tmp_path / "obs.db"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "apps" / "api" / "src")
        result = subprocess.run(
            [
                sys.executable, "-m", "nutmeg.v4.cli.recommend",
                "--fixtures", str(DEMO_FIXTURES),
                "--model", str(ARTIFACT_PATH),
                "--record-to", str(db),
                "--out", str(tmp_path / "rec.md"),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"recommend CLI failed: stdout={result.stdout[-500:]} "
            f"stderr={result.stderr[-500:]}"
        )
        assert db.exists(), "recommend --record-to didn't create the DB"

        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT model_type FROM recommendation_sessions"
            ).fetchall()
        assert len(rows) == 1, f"expected 1 session row, got {len(rows)}"
        recorded = rows[0][0]
        assert recorded == expected_model_type, (
            f"session model_type mismatch — artifact says "
            f"{expected_model_type!r} but DB recorded {recorded!r}. "
            f"This is the post-V11 audit cron bug — re-check "
            f"apps/api/src/nutmeg/v4/cli/recommend.py response_dict."
        )


# ---- Source-level guard (runs even without artifact) ----

class TestRecommendCliSourceGuard:
    """A lighter check that asserts the source includes the model_type
    literal inside the response dict. Runs everywhere — guards against
    a regression where someone removes the field again."""

    def test_source_includes_model_type_in_response_dict(self):
        src = (REPO_ROOT / "apps" / "api" / "src" / "nutmeg" / "v4"
               / "cli" / "recommend.py").read_text()
        # The response_dict literal must contain "model_type" as a key
        # in the "model" sub-dict. Search loosely; reject if missing.
        assert '"model_type"' in src, (
            'recommend.py response_dict missing the "model_type" key — '
            'see post-V11 audit notes. Without it, recorder.py defaults '
            'to "lightgbm" and tags every cron session incorrectly.'
        )
        # Belt-and-suspenders: confirm it's inside the model dict block,
        # not just a stray string elsewhere
        i = src.find('response_dict = {')
        j = src.find('"recommendations": recommendations_json', i)
        assert i > 0 and j > i, "response_dict literal not found"
        block = src[i:j]
        assert '"model_type"' in block, (
            '"model_type" is in recommend.py but NOT inside response_dict — '
            'it must live inside the "model" sub-dict so recorder.py sees it.'
        )
