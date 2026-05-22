from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from json import dumps
from os.path import relpath
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)


class HistoricalRecommendationSuiteManifestSlice(BaseModel):
    slice_path: str = Field(min_length=1)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalRecommendationSuiteManifest(BaseModel):
    manifest_version: str = "v1"
    suite_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    slices: list[HistoricalRecommendationSuiteManifestSlice] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalRecommendationSuiteManifestLoadResult(BaseModel):
    manifest_path: Path
    manifest: HistoricalRecommendationSuiteManifest
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HistoricalRecommendationSuiteManifestRefreshOptions(BaseModel):
    enabled: bool = True
    tags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    write: bool = False


class HistoricalRecommendationSuiteManifestRefreshResult(BaseModel):
    manifest_path: Path
    manifest: HistoricalRecommendationSuiteManifest
    added_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    registered_slice_ids: list[str] = Field(default_factory=list)
    registered_slice_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_recommendation_suite_manifest(
    path: Path | str,
) -> HistoricalRecommendationSuiteManifest:
    manifest_path = Path(path)
    return HistoricalRecommendationSuiteManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )


def resolve_historical_recommendation_suite_manifest_slice_paths(
    manifest: HistoricalRecommendationSuiteManifest,
    *,
    manifest_path: Path | str,
    include_disabled: bool = False,
) -> list[Path]:
    resolved_paths: list[Path] = []
    base_dir = Path(manifest_path).parent
    for slice_entry in manifest.slices:
        if not slice_entry.enabled and not include_disabled:
            continue
        raw_path = Path(slice_entry.slice_path)
        resolved_paths.append(
            raw_path if raw_path.is_absolute() else (base_dir / raw_path).resolve()
        )
    return resolved_paths


def load_historical_recommendation_suite_manifest_bundle(
    path: Path | str,
    *,
    include_disabled: bool = False,
) -> HistoricalRecommendationSuiteManifestLoadResult:
    manifest_path = Path(path)
    manifest = load_historical_recommendation_suite_manifest(manifest_path)
    resolved_paths = resolve_historical_recommendation_suite_manifest_slice_paths(
        manifest,
        manifest_path=manifest_path,
        include_disabled=include_disabled,
    )
    slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in resolved_paths
    ]
    warnings = _manifest_warnings(
        manifest,
        resolved_slice_paths=resolved_paths,
        slices=slices,
    )
    return HistoricalRecommendationSuiteManifestLoadResult(
        manifest_path=manifest_path,
        manifest=manifest,
        resolved_slice_paths=resolved_paths,
        slices=slices,
        warnings=warnings,
    )


def refresh_historical_recommendation_suite_manifest(
    manifest_path: Path | str,
    *,
    slice_paths: Sequence[Path | str],
    options: HistoricalRecommendationSuiteManifestRefreshOptions | None = None,
) -> HistoricalRecommendationSuiteManifestRefreshResult:
    resolved_options = options or HistoricalRecommendationSuiteManifestRefreshOptions()
    manifest_path = Path(manifest_path).resolve()
    manifest = load_historical_recommendation_suite_manifest(manifest_path)
    base_dir = manifest_path.parent
    added_count = 0
    updated_count = 0
    unchanged_count = 0
    registered_slice_ids: list[str] = []
    registered_slice_paths: list[str] = []
    for slice_path in slice_paths:
        resolved_slice_path = _resolve_slice_path(slice_path, base_dir=Path.cwd())
        historical_slice = load_historical_recommendation_slice(resolved_slice_path)
        stored_slice_path = _stored_slice_path(
            resolved_slice_path,
            manifest_base_dir=base_dir,
        )
        entry = HistoricalRecommendationSuiteManifestSlice(
            slice_path=stored_slice_path,
            enabled=resolved_options.enabled,
            tags=list(resolved_options.tags),
            notes=list(resolved_options.notes),
        )
        existing_index = _matching_manifest_entry_index(
            manifest,
            manifest_path=manifest_path,
            slice_id=historical_slice.metadata.slice_id,
            resolved_slice_path=resolved_slice_path,
        )
        if existing_index is None:
            manifest.slices.append(entry)
            added_count += 1
        else:
            existing = manifest.slices[existing_index]
            merged = existing.model_copy(
                update={
                    "slice_path": entry.slice_path,
                    "enabled": entry.enabled,
                    "tags": _merge_unique(existing.tags, entry.tags),
                    "notes": _merge_unique(existing.notes, entry.notes),
                }
            )
            if merged == existing:
                unchanged_count += 1
            else:
                manifest.slices[existing_index] = merged
                updated_count += 1
        registered_slice_ids.append(historical_slice.metadata.slice_id)
        registered_slice_paths.append(stored_slice_path)

    validation = _manifest_validation_from_model(
        manifest,
        manifest_path=manifest_path,
    )
    warnings = validation.warnings
    if resolved_options.write:
        manifest_path.write_text(
            f"{_manifest_json(manifest)}\n",
            encoding="utf-8",
        )
    summary: dict[str, object] = {
        "calculation_basis": "historical_recommendation_suite_manifest_refresh_v3_1",
        "manifest_path": str(manifest_path),
        "suite_id": manifest.suite_id,
        "write": resolved_options.write,
        "added_count": added_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "registered_slice_ids": registered_slice_ids,
        "registered_slice_paths": registered_slice_paths,
        "manifest_slice_count": len(manifest.slices),
        "warnings": warnings,
    }
    return HistoricalRecommendationSuiteManifestRefreshResult(
        manifest_path=manifest_path,
        manifest=manifest,
        added_count=added_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        registered_slice_ids=registered_slice_ids,
        registered_slice_paths=registered_slice_paths,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = refresh_historical_recommendation_suite_manifest(
        args.manifest_path,
        slice_paths=args.slice_paths,
        options=_options_from_args(args),
    )
    print(
        dumps(
            {
                **result.summary_json,
                "manifest": result.manifest.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _manifest_warnings(
    manifest: HistoricalRecommendationSuiteManifest,
    *,
    resolved_slice_paths: list[Path],
    slices: list[HistoricalRecommendationSlice],
) -> list[str]:
    warnings: list[str] = []
    if not resolved_slice_paths:
        warnings.append("historical_suite_manifest:no_enabled_slices")
    duplicate_slice_ids = _duplicate_values(
        [historical_slice.metadata.slice_id for historical_slice in slices]
    )
    for slice_id in duplicate_slice_ids:
        warnings.append(f"historical_suite_manifest:duplicate_slice_id:{slice_id}")
    enabled_count = sum(1 for slice_entry in manifest.slices if slice_entry.enabled)
    if enabled_count < len(manifest.slices):
        warnings.append("historical_suite_manifest:disabled_slices_skipped")
    return warnings


def _manifest_validation_from_model(
    manifest: HistoricalRecommendationSuiteManifest,
    *,
    manifest_path: Path,
) -> HistoricalRecommendationSuiteManifestLoadResult:
    resolved_paths = resolve_historical_recommendation_suite_manifest_slice_paths(
        manifest,
        manifest_path=manifest_path,
    )
    slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in resolved_paths
    ]
    warnings = _manifest_warnings(
        manifest,
        resolved_slice_paths=resolved_paths,
        slices=slices,
    )
    return HistoricalRecommendationSuiteManifestLoadResult(
        manifest_path=manifest_path,
        manifest=manifest,
        resolved_slice_paths=resolved_paths,
        slices=slices,
        warnings=warnings,
    )


def _matching_manifest_entry_index(
    manifest: HistoricalRecommendationSuiteManifest,
    *,
    manifest_path: Path,
    slice_id: str,
    resolved_slice_path: Path,
) -> int | None:
    all_paths = resolve_historical_recommendation_suite_manifest_slice_paths(
        manifest,
        manifest_path=manifest_path,
        include_disabled=True,
    )
    for index, existing_path in enumerate(all_paths):
        if existing_path == resolved_slice_path:
            return index
        existing_slice = load_historical_recommendation_slice(existing_path)
        if existing_slice.metadata.slice_id == slice_id:
            return index
    return None


def _stored_slice_path(slice_path: Path, *, manifest_base_dir: Path) -> str:
    return Path(relpath(slice_path, manifest_base_dir)).as_posix()


def _resolve_slice_path(path: Path | str, *, base_dir: Path) -> Path:
    raw_path = Path(path)
    return raw_path if raw_path.is_absolute() else (base_dir / raw_path).resolve()


def _merge_unique(existing: Sequence[str], incoming: Sequence[str]) -> list[str]:
    merged: list[str] = []
    for value in [*existing, *incoming]:
        if value not in merged:
            merged.append(value)
    return merged


def _manifest_json(manifest: HistoricalRecommendationSuiteManifest) -> str:
    return dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Validate and refresh a Nutmeg historical suite manifest."
    )
    parser.add_argument("manifest_path", type=Path)
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalRecommendationSuiteManifestRefreshOptions:
    return HistoricalRecommendationSuiteManifestRefreshOptions(
        enabled=not args.disabled,
        tags=tuple(args.tag),
        notes=tuple(args.note),
        write=args.write,
    )


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
