from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.competition_profiles import (
    DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
    load_competition_recommendation_profile_set,
)

type CompetitionProfilePromotionStatus = Literal["promoted", "dry_run", "blocked"]


class CompetitionProfilePromotionOptions(BaseModel):
    promoted_profile_version: str = "v3_1_competition_profile_promotion"
    require_production_ready: bool = True
    require_training_pool_allowed: bool = True
    allow_overwrite_existing: bool = False
    dry_run: bool = False


class CompetitionProfilePromotionReport(BaseModel):
    report_key: str
    status: CompetitionProfilePromotionStatus
    promoted_profile_version: str
    source_profile_version: str | None = None
    proposal_report_key: str | None = None
    admission_report_key: str | None = None
    promoted_competition_ids: list[str] = Field(default_factory=list)
    promoted_profile_count: int = Field(ge=0)
    profile_count: int = Field(ge=0)
    production_recommendation_allowed: bool
    training_pool_allowed: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    promoted_profile_set_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_competition_profile_promotion_report(
    *,
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
    proposal_report: Mapping[str, object],
    options: CompetitionProfilePromotionOptions | None = None,
) -> CompetitionProfilePromotionReport:
    resolved_options = options or CompetitionProfilePromotionOptions()
    current_profiles = _profile_set(current_profile_set)
    proposal_summary = _summary(proposal_report)
    proposal_report_key = _string(proposal_report.get("report_key")) or _string(
        proposal_summary.get("report_key")
    )
    admission_report_key = _string(proposal_report.get("admission_report_key")) or _string(
        proposal_summary.get("admission_report_key")
    )
    proposal_status = _string(proposal_report.get("status")) or _string(
        proposal_summary.get("status")
    )
    production_allowed = _bool(
        proposal_report.get("production_recommendation_allowed"),
        fallback=_bool(proposal_summary.get("production_recommendation_allowed")),
    )
    training_allowed = _bool(
        proposal_report.get("training_pool_allowed"),
        fallback=_bool(proposal_summary.get("training_pool_allowed")),
    )
    proposal_items = _mapping_list(proposal_report.get("proposals"))

    blockers = _promotion_blockers(
        proposal_status=proposal_status,
        production_allowed=production_allowed,
        training_allowed=training_allowed,
        proposal_items=proposal_items,
        options=resolved_options,
    )
    promoted_profile_set = current_profiles
    promoted_competition_ids: list[str] = []
    if not blockers:
        promoted_profile_set, promoted_competition_ids, merge_blockers = _merge_profiles(
            current_profiles,
            proposal_items=proposal_items,
            proposal_report_key=proposal_report_key,
            admission_report_key=admission_report_key,
            options=resolved_options,
        )
        blockers.extend(merge_blockers)
    if blockers:
        promoted_profile_set = current_profiles

    status: CompetitionProfilePromotionStatus
    if blockers:
        status = "blocked"
    elif resolved_options.dry_run:
        status = "dry_run"
    else:
        status = "promoted"

    promoted_profile_set_json = promoted_profile_set.model_dump(mode="json")
    summary: dict[str, object] = {
        "calculation_basis": "competition_profile_promotion_v3_1",
        "status": status,
        "promoted_profile_version": resolved_options.promoted_profile_version,
        "source_profile_version": current_profiles.profile_version,
        "proposal_report_key": proposal_report_key,
        "proposal_status": proposal_status,
        "admission_report_key": admission_report_key,
        "production_recommendation_allowed": production_allowed,
        "training_pool_allowed": training_allowed,
        "promoted_competition_ids": promoted_competition_ids,
        "promoted_profile_count": len(promoted_competition_ids),
        "profile_count": len(promoted_profile_set.profiles),
        "blockers": blockers,
        "warnings": [],
        "dry_run": resolved_options.dry_run,
        "allow_overwrite_existing": resolved_options.allow_overwrite_existing,
    }
    report_key = _report_key(summary, promoted_profile_set_json)
    return CompetitionProfilePromotionReport(
        report_key=report_key,
        status=status,
        promoted_profile_version=resolved_options.promoted_profile_version,
        source_profile_version=current_profiles.profile_version,
        proposal_report_key=proposal_report_key,
        admission_report_key=admission_report_key,
        promoted_competition_ids=promoted_competition_ids,
        promoted_profile_count=len(promoted_competition_ids),
        profile_count=len(promoted_profile_set.profiles),
        production_recommendation_allowed=production_allowed,
        training_pool_allowed=training_allowed,
        blockers=blockers,
        warnings=[],
        promoted_profile_set_json=promoted_profile_set_json,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    options = _options_from_args(args)
    if args.profile_output_path is None:
        options = options.model_copy(update={"dry_run": True})
    report = build_competition_profile_promotion_report(
        current_profile_set=load_competition_recommendation_profile_set(
            args.current_profile_path
        ),
        proposal_report=_load_json(args.profile_proposal_report),
        options=options,
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if report.status == "promoted" and args.profile_output_path is not None:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.promoted_profile_set_json, indent=2, sort_keys=False)}\n",
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _promotion_blockers(
    *,
    proposal_status: str | None,
    production_allowed: bool,
    training_allowed: bool,
    proposal_items: Sequence[Mapping[str, object]],
    options: CompetitionProfilePromotionOptions,
) -> list[str]:
    blockers: list[str] = []
    if options.require_production_ready and proposal_status != "production_ready":
        blockers.append("profile_proposal_not_production_ready")
    if not production_allowed:
        blockers.append("profile_proposal_production_not_allowed")
    if options.require_training_pool_allowed and not training_allowed:
        blockers.append("profile_proposal_training_pool_not_allowed")
    if not proposal_items:
        blockers.append("profile_proposal_has_no_profiles")
    for item in proposal_items:
        if not _bool(item.get("production_recommendation_allowed")):
            competition_id = _string(item.get("competition_id")) or "unknown"
            blockers.append(
                f"profile_proposal_item_not_production_allowed:{competition_id}"
            )
    return _unique(blockers)


def _merge_profiles(
    current_profile_set: CompetitionRecommendationProfileSet,
    *,
    proposal_items: Sequence[Mapping[str, object]],
    proposal_report_key: str | None,
    admission_report_key: str | None,
    options: CompetitionProfilePromotionOptions,
) -> tuple[CompetitionRecommendationProfileSet, list[str], list[str]]:
    existing_profiles = list(current_profile_set.profiles)
    index_by_competition = {
        profile.competition_id: index for index, profile in enumerate(existing_profiles)
    }
    promoted_competition_ids: list[str] = []
    blockers: list[str] = []
    for item in proposal_items:
        competition_id = _required_string(item.get("competition_id"), "competition_id")
        adjustments = _float_mapping(item.get("final_answer_score_adjustments"))
        if not adjustments:
            blockers.append(f"profile_proposal_empty_adjustments:{competition_id}")
            continue
        min_sample_size = max(1, _int(item.get("min_historical_final_hit_sample_size")))
        source_report_key = _string(item.get("source_report_key")) or proposal_report_key
        existing_index = index_by_competition.get(competition_id)
        if existing_index is None:
            existing_profiles.append(
                CompetitionRecommendationProfile(
                    competition_id=competition_id,
                    final_answer_score_adjustments=dict(adjustments),
                    min_historical_final_hit_sample_size=min_sample_size,
                    source_report_key=source_report_key,
                    notes=_promotion_notes(
                        existing_notes=[],
                        proposal_report_key=proposal_report_key,
                        admission_report_key=admission_report_key,
                    ),
                )
            )
            index_by_competition[competition_id] = len(existing_profiles) - 1
            promoted_competition_ids.append(competition_id)
            continue
        existing = existing_profiles[existing_index]
        merged_adjustments = dict(existing.final_answer_score_adjustments)
        for scenario_key, value in adjustments.items():
            existing_value = merged_adjustments.get(scenario_key)
            if (
                existing_value is not None
                and abs(existing_value - value) > 1e-12
                and not options.allow_overwrite_existing
            ):
                blockers.append(
                    f"profile_adjustment_conflict:{competition_id}:{scenario_key}"
                )
                continue
            merged_adjustments[scenario_key] = value
        existing_profiles[existing_index] = existing.model_copy(
            update={
                "final_answer_score_adjustments": merged_adjustments,
                "min_historical_final_hit_sample_size": max(
                    existing.min_historical_final_hit_sample_size,
                    min_sample_size,
                ),
                "source_report_key": source_report_key or existing.source_report_key,
                "notes": _promotion_notes(
                    existing_notes=existing.notes,
                    proposal_report_key=proposal_report_key,
                    admission_report_key=admission_report_key,
                ),
            }
        )
        promoted_competition_ids.append(competition_id)
    if blockers:
        return current_profile_set, [], _unique(blockers)
    promoted_profiles = sorted(existing_profiles, key=lambda profile: profile.competition_id)
    promoted_profile_set = CompetitionRecommendationProfileSet(
        profile_version=options.promoted_profile_version,
        calculation_basis="competition_profile_promotion_v3_1",
        profiles=promoted_profiles,
        notes=_unique(
            [
                *current_profile_set.notes,
                (
                    "Profiles are data-driven arbitration adjustments, not "
                    "user-facing strategy labels."
                ),
                (
                    "Expanded A-league profile adjustments promoted only after "
                    "production admission passed."
                ),
                f"proposal_report_key={proposal_report_key}",
                f"admission_report_key={admission_report_key}",
            ]
        ),
    )
    return promoted_profile_set, _unique(promoted_competition_ids), []


def _promotion_notes(
    *,
    existing_notes: Sequence[str],
    proposal_report_key: str | None,
    admission_report_key: str | None,
) -> list[str]:
    return _unique(
        [
            *existing_notes,
            "Promoted from production-ready competition profile proposal.",
            "Internal final-answer arbitration adjustment; not user-facing strategy text.",
            f"proposal_report_key={proposal_report_key}",
            f"admission_report_key={admission_report_key}",
        ]
    )


def _profile_set(
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
) -> CompetitionRecommendationProfileSet:
    if isinstance(current_profile_set, CompetitionRecommendationProfileSet):
        return current_profile_set
    return CompetitionRecommendationProfileSet.model_validate(current_profile_set)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Promote a production-ready competition profile proposal into a profile set."
    )
    parser.add_argument(
        "--current-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--profile-proposal-report", type=Path, required=True)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--promoted-profile-version",
        default="v3_1_competition_profile_promotion",
    )
    parser.add_argument("--allow-overwrite-existing", action="store_true")
    parser.add_argument("--allow-without-training-pool", action="store_true")
    parser.add_argument("--allow-non-production-ready", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> CompetitionProfilePromotionOptions:
    return CompetitionProfilePromotionOptions(
        promoted_profile_version=args.promoted_profile_version,
        require_production_ready=not args.allow_non_production_ready,
        require_training_pool_allowed=not args.allow_without_training_pool,
        allow_overwrite_existing=args.allow_overwrite_existing,
        dry_run=args.dry_run,
    )


def _load_json(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _report_key(
    summary: Mapping[str, object],
    promoted_profile_set_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "promoted_profile_set_json": promoted_profile_set_json,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"competition_profile_promotion:{digest}"


def _summary(report: Mapping[str, object]) -> dict[str, object]:
    raw_summary = report.get("summary_json")
    if isinstance(raw_summary, dict):
        return dict(raw_summary)
    return {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _float_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): float(raw_value)
        for key, raw_value in value.items()
        if isinstance(raw_value, int | float)
    }


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_string(value: object, field_name: str) -> str:
    result = _string(value)
    if result is None:
        raise ValueError(f"missing required profile promotion field: {field_name}")
    return result


def _bool(value: object, *, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return fallback


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values
