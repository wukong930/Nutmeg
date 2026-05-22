from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type ScientificBaselineGateStatus = Literal["passed", "failed"]
type ScientificBaselineGateCheckStatus = Literal["passed", "failed"]

DEFAULT_SCIENTIFIC_BASELINE_MANIFEST_PATH = Path(
    "configs/recommendations/baselines/baseline_v3_1_locked_2026_05_21.json"
)


class ScientificBaselineEvidenceRequirement(BaseModel):
    name: str = Field(min_length=1)
    path: Path
    required_top_level: dict[str, object] = Field(default_factory=dict)
    required_summary: dict[str, object] = Field(default_factory=dict)
    top_level_minimums: dict[str, float] = Field(default_factory=dict)
    summary_minimums: dict[str, float] = Field(default_factory=dict)
    top_level_maximums: dict[str, float] = Field(default_factory=dict)
    summary_maximums: dict[str, float] = Field(default_factory=dict)
    top_level_list_minimum_lengths: dict[str, int] = Field(default_factory=dict)
    summary_list_minimum_lengths: dict[str, int] = Field(default_factory=dict)
    require_empty_top_level_lists: tuple[str, ...] = ()
    require_empty_summary_lists: tuple[str, ...] = ()


class ScientificBaselineManifest(BaseModel):
    baseline_id: str = Field(min_length=1)
    calculation_basis: str = Field(min_length=1)
    status: str = Field(min_length=1)
    rules: list[str] = Field(default_factory=list)
    evidence: list[ScientificBaselineEvidenceRequirement] = Field(default_factory=list)


class ScientificBaselineGateCheck(BaseModel):
    name: str
    status: ScientificBaselineGateCheckStatus
    actual: object = None
    threshold: object = None
    detail: str


class ScientificBaselineEvidenceResult(BaseModel):
    name: str
    path: Path
    present: bool
    checks: list[ScientificBaselineGateCheck] = Field(default_factory=list)


class ScientificBaselineGateReport(BaseModel):
    report_key: str
    baseline_id: str
    status: ScientificBaselineGateStatus
    passed: bool
    manifest_path: Path
    evidence_count: int = Field(ge=0)
    failed_check_count: int = Field(ge=0)
    evidence_results: list[ScientificBaselineEvidenceResult] = Field(
        default_factory=list
    )
    checks: list[ScientificBaselineGateCheck] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_scientific_baseline_manifest(path: Path | str) -> ScientificBaselineManifest:
    return ScientificBaselineManifest.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def run_scientific_baseline_gate(
    manifest_path: Path | str = DEFAULT_SCIENTIFIC_BASELINE_MANIFEST_PATH,
) -> ScientificBaselineGateReport:
    resolved_manifest_path = Path(manifest_path)
    manifest = load_scientific_baseline_manifest(resolved_manifest_path)
    evidence_results = [
        _evaluate_evidence(requirement, manifest_path=resolved_manifest_path)
        for requirement in manifest.evidence
    ]
    checks = [
        check for evidence_result in evidence_results for check in evidence_result.checks
    ]
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: ScientificBaselineGateStatus = "passed" if passed else "failed"
    report_key = _report_key(manifest, checks)
    summary = {
        "report_key": report_key,
        "baseline_id": manifest.baseline_id,
        "status": status,
        "passed": passed,
        "manifest_path": str(resolved_manifest_path),
        "evidence_count": len(evidence_results),
        "failed_check_count": len(failed_checks),
        "failed_checks": [check.name for check in failed_checks],
        "calculation_basis": "scientific_baseline_gate_v3_2",
    }
    return ScientificBaselineGateReport(
        report_key=report_key,
        baseline_id=manifest.baseline_id,
        status=status,
        passed=passed,
        manifest_path=resolved_manifest_path,
        evidence_count=len(evidence_results),
        failed_check_count=len(failed_checks),
        evidence_results=evidence_results,
        checks=checks,
        summary_json=summary,
    )


def _evaluate_evidence(
    requirement: ScientificBaselineEvidenceRequirement,
    *,
    manifest_path: Path,
) -> ScientificBaselineEvidenceResult:
    report_path = _resolve_report_path(requirement.path, manifest_path=manifest_path)
    checks: list[ScientificBaselineGateCheck] = []
    if not report_path.exists():
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{requirement.name}:report_present",
                status="failed",
                actual=False,
                threshold=True,
                detail="locked baseline evidence report must exist",
            )
        )
        return ScientificBaselineEvidenceResult(
            name=requirement.name,
            path=report_path,
            present=False,
            checks=checks,
        )

    payload = _load_json_mapping(report_path)
    summary = _mapping_value(payload.get("summary_json"))
    checks.append(
        ScientificBaselineGateCheck(
            name=f"{requirement.name}:report_present",
            status="passed",
            actual=True,
            threshold=True,
            detail="locked baseline evidence report exists",
        )
    )
    checks.extend(
        _required_value_checks(
            requirement.required_top_level,
            source=payload,
            prefix=requirement.name,
            source_name="top_level",
        )
    )
    checks.extend(
        _required_value_checks(
            requirement.required_summary,
            source=summary,
            prefix=requirement.name,
            source_name="summary",
        )
    )
    checks.extend(
        _minimum_checks(
            requirement.top_level_minimums,
            source=payload,
            prefix=requirement.name,
            source_name="top_level",
        )
    )
    checks.extend(
        _minimum_checks(
            requirement.summary_minimums,
            source=summary,
            prefix=requirement.name,
            source_name="summary",
        )
    )
    checks.extend(
        _maximum_checks(
            requirement.top_level_maximums,
            source=payload,
            prefix=requirement.name,
            source_name="top_level",
        )
    )
    checks.extend(
        _maximum_checks(
            requirement.summary_maximums,
            source=summary,
            prefix=requirement.name,
            source_name="summary",
        )
    )
    checks.extend(
        _list_minimum_length_checks(
            requirement.top_level_list_minimum_lengths,
            source=payload,
            prefix=requirement.name,
            source_name="top_level",
        )
    )
    checks.extend(
        _list_minimum_length_checks(
            requirement.summary_list_minimum_lengths,
            source=summary,
            prefix=requirement.name,
            source_name="summary",
        )
    )
    checks.extend(
        _empty_list_checks(
            requirement.require_empty_top_level_lists,
            source=payload,
            prefix=requirement.name,
            source_name="top_level",
        )
    )
    checks.extend(
        _empty_list_checks(
            requirement.require_empty_summary_lists,
            source=summary,
            prefix=requirement.name,
            source_name="summary",
        )
    )
    return ScientificBaselineEvidenceResult(
        name=requirement.name,
        path=report_path,
        present=True,
        checks=checks,
    )


def _required_value_checks(
    expected_values: Mapping[str, object],
    *,
    source: Mapping[str, object],
    prefix: str,
    source_name: str,
) -> list[ScientificBaselineGateCheck]:
    checks: list[ScientificBaselineGateCheck] = []
    for key, expected in expected_values.items():
        actual = source.get(key)
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{prefix}:{source_name}:{key}:equals",
                status="passed" if actual == expected else "failed",
                actual=actual,
                threshold=expected,
                detail=f"{source_name} field {key} should match the locked baseline",
            )
        )
    return checks


def _minimum_checks(
    minimums: Mapping[str, float],
    *,
    source: Mapping[str, object],
    prefix: str,
    source_name: str,
) -> list[ScientificBaselineGateCheck]:
    checks: list[ScientificBaselineGateCheck] = []
    for key, threshold in minimums.items():
        actual = _number(source.get(key))
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{prefix}:{source_name}:{key}:minimum",
                status=(
                    "passed"
                    if actual is not None and actual >= float(threshold)
                    else "failed"
                ),
                actual=actual,
                threshold=threshold,
                detail=f"{source_name} field {key} should not fall below baseline",
            )
        )
    return checks


def _maximum_checks(
    maximums: Mapping[str, float],
    *,
    source: Mapping[str, object],
    prefix: str,
    source_name: str,
) -> list[ScientificBaselineGateCheck]:
    checks: list[ScientificBaselineGateCheck] = []
    for key, threshold in maximums.items():
        actual = _number(source.get(key))
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{prefix}:{source_name}:{key}:maximum",
                status=(
                    "passed"
                    if actual is not None and actual <= float(threshold)
                    else "failed"
                ),
                actual=actual,
                threshold=threshold,
                detail=f"{source_name} field {key} should not exceed baseline limit",
            )
        )
    return checks


def _list_minimum_length_checks(
    minimum_lengths: Mapping[str, int],
    *,
    source: Mapping[str, object],
    prefix: str,
    source_name: str,
) -> list[ScientificBaselineGateCheck]:
    checks: list[ScientificBaselineGateCheck] = []
    for key, threshold in minimum_lengths.items():
        actual = _sequence_length(source.get(key))
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{prefix}:{source_name}:{key}:minimum_length",
                status="passed" if actual >= threshold else "failed",
                actual=actual,
                threshold=threshold,
                detail=f"{source_name} list {key} should retain enough evidence",
            )
        )
    return checks


def _empty_list_checks(
    keys: Sequence[str],
    *,
    source: Mapping[str, object],
    prefix: str,
    source_name: str,
) -> list[ScientificBaselineGateCheck]:
    checks: list[ScientificBaselineGateCheck] = []
    for key in keys:
        actual = _sequence_length(source.get(key))
        checks.append(
            ScientificBaselineGateCheck(
                name=f"{prefix}:{source_name}:{key}:empty",
                status="passed" if actual == 0 else "failed",
                actual=actual,
                threshold=0,
                detail=f"{source_name} list {key} should remain empty",
            )
        )
    return checks


def _resolve_report_path(path: Path, *, manifest_path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return manifest_path.parent / path


def _load_json_mapping(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    return _mapping_value(payload)


def _mapping_value(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _sequence_length(value: object) -> int:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return 0


def _report_key(
    manifest: ScientificBaselineManifest,
    checks: Sequence[ScientificBaselineGateCheck],
) -> str:
    payload = {
        "baseline_id": manifest.baseline_id,
        "evidence": [
            evidence.model_dump(mode="json", exclude_none=True)
            for evidence in manifest.evidence
        ],
        "checks": [check.model_dump(mode="json") for check in checks],
    }
    digest = sha256(dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"scientific_baseline_gate:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Validate the locked Nutmeg V3.2 scientific execution baseline."
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=DEFAULT_SCIENTIFIC_BASELINE_MANIFEST_PATH,
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = run_scientific_baseline_gate(args.manifest_path)
    payload = f"{report.model_dump_json(indent=2)}\n"
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
