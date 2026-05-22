from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations import (
    HistoricalRecommendationSliceBuildOptions,
    HistoricalRecommendationSuiteManifestRefreshOptions,
    build_historical_recommendation_slice_from_csv,
    load_historical_recommendation_suite_manifest_bundle,
    refresh_historical_recommendation_suite_manifest,
    resolve_historical_recommendation_suite_manifest_slice_paths,
)


def test_historical_suite_manifest_loads_enabled_slice_paths() -> None:
    manifest_path = Path(
        "configs/recommendations/historical_suites/euro_2024_knockout_suite.json"
    )

    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert bundle.manifest.suite_id == "euro_2024_knockout_suite_v1"
    assert bundle.manifest_path == manifest_path
    assert len(bundle.resolved_slice_paths) == 1
    assert bundle.resolved_slice_paths[0].name == "euro_2024_knockout_sample.json"
    assert bundle.slices[0].metadata.slice_id == "euro_2024_knockout_sample_v1"
    assert bundle.warnings == []


def test_historical_suite_manifest_loads_upset_stress_suite() -> None:
    manifest_path = Path(
        "configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json"
    )

    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert bundle.manifest.suite_id == "euro_2024_upset_stress_suite_v1"
    assert len(bundle.resolved_slice_paths) == 1
    assert bundle.resolved_slice_paths[0].name == "euro_2024_group_upset_sample.json"
    assert bundle.slices[0].metadata.slice_id == "euro_2024_group_upset_sample_v1"
    assert "upset_pressure" in bundle.manifest.tags
    assert bundle.warnings == []


def test_historical_suite_manifest_resolves_paths_relative_to_manifest() -> None:
    manifest_path = Path(
        "configs/recommendations/historical_suites/euro_2024_knockout_suite.json"
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    resolved_paths = resolve_historical_recommendation_suite_manifest_slice_paths(
        bundle.manifest,
        manifest_path=manifest_path,
    )

    assert resolved_paths == bundle.resolved_slice_paths
    assert resolved_paths[0].is_absolute()
    assert resolved_paths[0].exists()


def test_historical_suite_manifest_refresh_dry_run_does_not_write(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)
    generated_slice_path = _write_builder_slice(tmp_path, slice_id="refresh_dry_run_slice")
    before = manifest_path.read_text(encoding="utf-8")

    result = refresh_historical_recommendation_suite_manifest(
        manifest_path,
        slice_paths=[generated_slice_path],
        options=HistoricalRecommendationSuiteManifestRefreshOptions(
            tags=("builder",),
            notes=("dry-run registration",),
            write=False,
        ),
    )

    assert result.added_count == 1
    assert result.updated_count == 0
    assert result.unchanged_count == 0
    assert result.registered_slice_ids == ["refresh_dry_run_slice"]
    assert result.registered_slice_paths == ["refresh_dry_run_slice.json"]
    assert result.warnings == []
    assert manifest_path.read_text(encoding="utf-8") == before


def test_historical_suite_manifest_refresh_writes_registered_slice(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)
    generated_slice_path = _write_builder_slice(tmp_path, slice_id="refresh_write_slice")

    result = refresh_historical_recommendation_suite_manifest(
        manifest_path,
        slice_paths=[generated_slice_path],
        options=HistoricalRecommendationSuiteManifestRefreshOptions(
            tags=("builder", "euro_2024"),
            notes=("registered from generated slice",),
            write=True,
        ),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.added_count == 1
    assert result.summary_json["write"] is True
    assert len(bundle.manifest.slices) == 2
    assert bundle.manifest.slices[1].slice_path == "refresh_write_slice.json"
    assert bundle.manifest.slices[1].tags == ["builder", "euro_2024"]
    assert bundle.slices[1].metadata.slice_id == "refresh_write_slice"
    assert bundle.warnings == []


def test_historical_suite_manifest_refresh_updates_existing_slice_entry(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tmp_manifest(tmp_path)
    generated_slice_path = _write_builder_slice(tmp_path, slice_id="refresh_update_slice")
    refresh_historical_recommendation_suite_manifest(
        manifest_path,
        slice_paths=[generated_slice_path],
        options=HistoricalRecommendationSuiteManifestRefreshOptions(
            tags=("builder",),
            write=True,
        ),
    )

    result = refresh_historical_recommendation_suite_manifest(
        manifest_path,
        slice_paths=[generated_slice_path],
        options=HistoricalRecommendationSuiteManifestRefreshOptions(
            tags=("quality_gate",),
            notes=("second pass",),
            write=True,
        ),
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert result.added_count == 0
    assert result.updated_count == 1
    assert result.unchanged_count == 0
    assert bundle.manifest.slices[1].tags == ["builder", "quality_gate"]
    assert bundle.manifest.slices[1].notes == ["second pass"]


def _write_tmp_manifest(tmp_path: Path) -> Path:
    sample_slice_path = Path(
        "configs/recommendations/historical_slices/euro_2024_knockout_sample.json"
    ).resolve()
    manifest_path = tmp_path / "suite.json"
    manifest_path.write_text(
        (
            "{\n"
            '  "manifest_version": "v1",\n'
            '  "suite_id": "tmp_suite_v1",\n'
            '  "name": "Temporary suite",\n'
            '  "slices": [\n'
            "    {\n"
            f'      "slice_path": "{sample_slice_path.as_posix()}",\n'
            '      "enabled": true,\n'
            '      "tags": ["existing"],\n'
            '      "notes": []\n'
            "    }\n"
            "  ]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_builder_slice(tmp_path: Path, *, slice_id: str) -> Path:
    build_result = build_historical_recommendation_slice_from_csv(
        Path("configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv"),
        options=HistoricalRecommendationSliceBuildOptions(
            slice_id=slice_id,
            name="Temporary generated builder slice",
            competition_id="UEFA_EURO",
            as_of_time_utc="2024-06-29T12:00:00Z",
            season="2024",
            result_source="unit test results",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
    )
    slice_path = tmp_path / f"{slice_id}.json"
    slice_path.write_text(build_result.slice.model_dump_json(indent=2), encoding="utf-8")
    return slice_path
