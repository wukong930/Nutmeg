from __future__ import annotations

from json import dumps
from pathlib import Path

from nutmeg.recommendations.scientific_baseline_gate import (
    DEFAULT_SCIENTIFIC_BASELINE_MANIFEST_PATH,
    run_scientific_baseline_gate,
)


def test_scientific_baseline_gate_passes_locked_manifest() -> None:
    result = run_scientific_baseline_gate(DEFAULT_SCIENTIFIC_BASELINE_MANIFEST_PATH)

    assert result.passed is True
    assert result.status == "passed"
    assert result.baseline_id == "baseline_v3_1_locked_2026_05_21"
    assert result.evidence_count == 4
    assert result.failed_check_count == 0
    assert result.summary_json["failed_checks"] == []


def test_scientific_baseline_gate_blocks_missing_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "baseline.json"
    manifest.write_text(
        dumps(
            {
                "baseline_id": "test_baseline",
                "calculation_basis": "unit_test",
                "status": "locked",
                "evidence": [
                    {
                        "name": "missing_report",
                        "path": str(tmp_path / "missing.json"),
                        "required_top_level": {"status": "passed"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_scientific_baseline_gate(manifest)

    assert result.passed is False
    assert result.failed_check_count == 1
    assert result.checks[0].name == "missing_report:report_present"


def test_scientific_baseline_gate_blocks_threshold_regression(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        dumps(
            {
                "status": "passed",
                "passed": True,
                "candidate_final_hit_rate": 0.49,
                "failed_checks": [],
                "summary_json": {"dynamic_profiles": [{"profile_key": "a"}]},
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "baseline.json"
    manifest.write_text(
        dumps(
            {
                "baseline_id": "test_baseline",
                "calculation_basis": "unit_test",
                "status": "locked",
                "evidence": [
                    {
                        "name": "weak_report",
                        "path": str(report),
                        "required_top_level": {"status": "passed", "passed": True},
                        "top_level_minimums": {"candidate_final_hit_rate": 0.5},
                        "summary_list_minimum_lengths": {"dynamic_profiles": 2},
                        "require_empty_top_level_lists": ["failed_checks"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_scientific_baseline_gate(manifest)
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert failed_checks == {
        "weak_report:top_level:candidate_final_hit_rate:minimum",
        "weak_report:summary:dynamic_profiles:minimum_length",
    }
