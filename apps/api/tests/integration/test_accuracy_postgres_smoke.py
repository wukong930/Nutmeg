from __future__ import annotations

import os
from pathlib import Path

import pytest

from nutmeg.accuracy.postgres_smoke import run_accuracy_postgres_smoke


@pytest.mark.skipif(
    os.getenv("NUTMEG_RUN_POSTGRES_SMOKE") != "1",
    reason="set NUTMEG_RUN_POSTGRES_SMOKE=1 to run live Postgres smoke",
)
def test_accuracy_postgres_smoke_against_live_database() -> None:
    result = run_accuracy_postgres_smoke(
        database_url=os.getenv(
            "NUTMEG_DATABASE_URL",
            "postgresql://nutmeg:nutmeg@localhost:5432/nutmeg",
        ),
        migration_dir=Path("db/migrations"),
        reset=True,
    )

    assert result.loop_run.fixture_count == 3
    assert len(result.loop_run.evaluation_ids) == 3
    assert result.loop_run.calibration_observation_count == 9
    assert result.summary_sample_size == 3
    assert result.one_x_two_sample_size == 3
    assert result.calibration_bucket_count > 0
    assert result.model_comparison_count == 1
