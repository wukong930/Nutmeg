from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_probability_calibration_profile_runtime_replay import (
    ProbabilityCalibrationRuntimeProfileSet,
    load_probability_calibration_runtime_profile_set,
)


class HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions(BaseModel):
    profile_keys: tuple[str, ...] = ()
    profile_key_suffix: str = "scope_refinement"
    target_season_ids: tuple[str, ...] = ()
    excluded_season_ids: tuple[str, ...] = ()
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    min_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    max_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    preserve_runtime_flags: bool = False


class HistoricalProbabilityCalibrationProfileRuntimeRefinementReport(BaseModel):
    report_key: str
    status: str = "generated"
    source_profile_version: str
    selected_profile_key: str
    refined_profile_key: str
    refined_profile_set_json: dict[str, object] = Field(default_factory=dict)
    changed_fields_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_probability_calibration_profile_runtime_refinement_report(
    *,
    profile_set_path: Path | str,
    options: HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileRuntimeRefinementReport:
    resolved_options = (
        options or HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions()
    )
    profile_set = load_probability_calibration_runtime_profile_set(profile_set_path)
    selected_profile = _selected_profile(profile_set.profiles, options=resolved_options)
    changed_fields = _changed_fields(resolved_options)
    if not changed_fields:
        raise ValueError("Runtime refinement requires at least one scope guard")
    refined_profile_key = _refined_profile_key(
        selected_profile,
        changed_fields=changed_fields,
        suffix=resolved_options.profile_key_suffix,
    )
    refined_profile = selected_profile.model_copy(
        update={
            **changed_fields,
            "profile_key": refined_profile_key,
        }
    )
    refined_profile_set = _refined_profile_set(
        profile_set,
        refined_profile=refined_profile,
        options=resolved_options,
    )
    refined_profile_set_json = refined_profile_set.model_dump(mode="json")
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_runtime_refinement_v3_1"
        ),
        "source_profile_version": profile_set.profile_version,
        "selected_profile_key": selected_profile.profile_key,
        "refined_profile_key": refined_profile.profile_key,
        "changed_fields": changed_fields,
        "preserve_runtime_flags": resolved_options.preserve_runtime_flags,
        "runtime_profile_proposal_allowed": (
            refined_profile_set.runtime_profile_proposal_allowed
        ),
        "holdout_candidate_allowed": refined_profile_set.holdout_candidate_allowed,
        "production_recommendation_changed": (
            refined_profile_set.production_recommendation_changed
        ),
    }
    report_key = _report_key(summary, refined_profile_set_json)
    return HistoricalProbabilityCalibrationProfileRuntimeRefinementReport(
        report_key=report_key,
        source_profile_version=profile_set.profile_version,
        selected_profile_key=selected_profile.profile_key,
        refined_profile_key=refined_profile.profile_key,
        refined_profile_set_json=refined_profile_set_json,
        changed_fields_json=changed_fields,
        warnings=list(refined_profile_set.notes),
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_probability_calibration_profile_runtime_refinement_report(
        profile_set_path=args.profile_set,
        options=_options_from_args(args),
    )
    if args.profile_output_path is not None:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.refined_profile_set_json, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _selected_profile(
    profiles: Sequence[CandidateProbabilityCalibrationProfile],
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions,
) -> CandidateProbabilityCalibrationProfile:
    profile_keys = set(options.profile_keys)
    selected = [
        profile for profile in profiles if not profile_keys or profile.profile_key in profile_keys
    ]
    if not selected:
        raise ValueError("No probability calibration profile matched refinement options")
    if len(selected) > 1:
        raise ValueError("Runtime refinement expects one probability calibration profile")
    return selected[0]


def _changed_fields(
    options: HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions,
) -> dict[str, object]:
    changed_fields: dict[str, object] = {}
    if options.target_season_ids:
        changed_fields["target_season_ids"] = options.target_season_ids
    if options.excluded_season_ids:
        changed_fields["excluded_season_ids"] = options.excluded_season_ids
    if options.min_competition_season_index is not None:
        changed_fields["min_competition_season_index"] = (
            options.min_competition_season_index
        )
    if options.max_competition_season_index is not None:
        changed_fields["max_competition_season_index"] = (
            options.max_competition_season_index
        )
    if options.min_competition_season_index_by_competition_id:
        changed_fields["min_competition_season_index_by_competition_id"] = (
            dict(sorted(options.min_competition_season_index_by_competition_id.items()))
        )
    if options.max_competition_season_index_by_competition_id:
        changed_fields["max_competition_season_index_by_competition_id"] = (
            dict(sorted(options.max_competition_season_index_by_competition_id.items()))
        )
    return changed_fields


def _refined_profile_set(
    profile_set: ProbabilityCalibrationRuntimeProfileSet,
    *,
    refined_profile: CandidateProbabilityCalibrationProfile,
    options: HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions,
) -> ProbabilityCalibrationRuntimeProfileSet:
    notes = [
        *profile_set.notes,
        "probability_calibration_runtime_refinement:scope_guarded_profile_set",
        "probability_calibration_runtime_refinement:not_default_runtime_profile",
    ]
    return profile_set.model_copy(
        update={
            "profile_version": f"{profile_set.profile_version}:runtime_refinement",
            "calculation_basis": (
                "probability_calibration_profile_runtime_refinement_v3_1"
            ),
            "status": "runtime_refinement_candidate",
            "runtime_profile_proposal_allowed": (
                profile_set.runtime_profile_proposal_allowed
                if options.preserve_runtime_flags
                else False
            ),
            "production_recommendation_changed": False,
            "profiles": [refined_profile],
            "profile_proposals_json": [],
            "notes": notes,
        }
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Create a guarded runtime-refinement probability profile set."
    )
    parser.add_argument("--profile-set", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument("--profile-keys", default="")
    parser.add_argument("--profile-key-suffix", default="scope_refinement")
    parser.add_argument("--target-seasons", default="")
    parser.add_argument("--excluded-seasons", default="")
    parser.add_argument("--min-competition-season-index", type=int)
    parser.add_argument("--max-competition-season-index", type=int)
    parser.add_argument("--min-competition-season-index-by-competition", default="")
    parser.add_argument("--max-competition-season-index-by-competition", default="")
    parser.add_argument("--preserve-runtime-flags", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions:
    return HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions(
        profile_keys=tuple(_csv(args.profile_keys)),
        profile_key_suffix=args.profile_key_suffix,
        target_season_ids=tuple(_csv(args.target_seasons)),
        excluded_season_ids=tuple(_csv(args.excluded_seasons)),
        min_competition_season_index=args.min_competition_season_index,
        max_competition_season_index=args.max_competition_season_index,
        min_competition_season_index_by_competition_id=_competition_index_map(
            args.min_competition_season_index_by_competition
        ),
        max_competition_season_index_by_competition_id=_competition_index_map(
            args.max_competition_season_index_by_competition
        ),
        preserve_runtime_flags=args.preserve_runtime_flags,
    )


def _competition_index_map(value: str | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in _csv(value):
        competition_id, separator, raw_index = item.partition(":")
        if not separator or not competition_id or not raw_index.isdigit():
            raise ValueError(
                "competition season index mappings must use COMPETITION_ID:INDEX"
            )
        index = int(raw_index)
        if index < 1:
            raise ValueError("competition season index mappings must be positive")
        result[competition_id] = index
    return result


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _refined_profile_key(
    profile: CandidateProbabilityCalibrationProfile,
    *,
    changed_fields: Mapping[str, object],
    suffix: str,
) -> str:
    digest = sha256(
        dumps(
            {
                "profile_key": profile.profile_key,
                "changed_fields": changed_fields,
                "suffix": suffix,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{profile.profile_key}:runtime_refinement:{suffix}:{digest}"


def _report_key(
    summary: Mapping[str, object],
    refined_profile_set_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "refined_profile_set_json": refined_profile_set_json,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_runtime_refinement:{digest}"
