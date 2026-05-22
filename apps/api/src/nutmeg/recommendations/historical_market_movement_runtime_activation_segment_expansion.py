from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import sub
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    DEFAULT_ROLLBACK_CONDITIONS,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_scope_refinement import (
    HistoricalMarketMovementRiskFilterScopeCandidate,
    HistoricalMarketMovementRiskFilterScopeRefinementReport,
    load_historical_market_movement_risk_filter_scope_refinement_report,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_sample_expansion import (
    HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
    load_historical_market_movement_runtime_activation_sample_expansion_report,
)

type HistoricalMarketMovementRuntimeActivationSegmentExpansionStatus = Literal[
    "runtime_replay_expansion_ready",
    "watchlist",
    "blocked",
]
type HistoricalMarketMovementRuntimeActivationSegmentExpansionCheckStatus = Literal[
    "passed",
    "failed",
    "watchlist",
    "skipped",
]

DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_EXPANSION_ID = (
    "market-movement-runtime-activation-segment-expansion-v3.2"
)
DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_EXPANSION_PROFILE_VERSION = (
    "v3_2_market_movement_runtime_activation_segment_expansion_candidate"
)


class HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions(BaseModel):
    expansion_id: str = DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_EXPANSION_ID
    profile_version: str = (
        DEFAULT_MARKET_MOVEMENT_RUNTIME_ACTIVATION_SEGMENT_EXPANSION_PROFILE_VERSION
    )
    rule_id_prefix: str = "market_movement_runtime_segment_expansion"
    max_selected_candidate_count: int = Field(default=4, ge=1, le=32)
    min_selected_candidate_count: int = Field(default=1, ge=0)
    min_stable_scope_count: int = Field(default=1, ge=0)
    min_candidate_adjusted_fixture_count: int = Field(default=100, ge=0)
    min_candidate_adjusted_prediction_count: int = Field(default=300, ge=0)
    min_total_adjusted_fixture_count: int = Field(default=300, ge=0)
    min_total_adjusted_prediction_count: int = Field(default=900, ge=0)
    min_candidate_competition_count: int = Field(default=1, ge=0)
    min_total_competition_count: int = Field(default=2, ge=0)
    min_final_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    require_sample_expansion_passed: bool = True
    require_scope_refinement_shadow_allowed: bool = True
    exclude_already_selected_segments: bool = True
    require_no_default_profile_write: bool = True
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_sample_expansion_promotion_ready_for_production: bool = True


class HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRuntimeActivationSegmentExpansionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate(BaseModel):
    rule_id: str
    segment_group_key: str
    segment_group_type: str
    segment_label: str
    source_status: str
    recommended_action: str
    source_adjusted_fixture_count: int = Field(ge=0)
    source_adjusted_prediction_count: int = Field(ge=0)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    best_final_hit_rate_delta: float | None = None
    best_brier_score_delta: float | None = None
    best_log_loss_delta: float | None = None
    average_brier_score_delta: float | None = None
    average_log_loss_delta: float | None = None
    already_selected: bool = False
    selected_for_runtime_replay: bool
    rule_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRuntimeActivationSegmentExpansionReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRuntimeActivationSegmentExpansionStatus
    passed: bool
    runtime_replay_expansion_ready: bool
    production_promotion_ready: bool
    expansion_id: str
    source_sample_expansion_report_key: str
    source_scope_refinement_report_key: str
    source_activation_report_key: str
    sample_expansion_status: str
    sample_expansion_passed: bool
    sample_expansion_promotion_ready: bool
    scope_refinement_status: str
    stable_scope_count: int = Field(ge=0)
    selected_candidate_count: int = Field(ge=0)
    selected_segment_group_keys: list[str] = Field(default_factory=list)
    existing_segment_group_keys: list[str] = Field(default_factory=list)
    total_adjusted_fixture_count: int = Field(ge=0)
    total_adjusted_prediction_count: int = Field(ge=0)
    total_competition_count: int = Field(ge=0)
    total_season_count: int = Field(ge=0)
    combined_sample_fixture_count: int = Field(ge=0)
    adjusted_to_combined_fixture_ratio: float | None = None
    default_profile_written: bool = False
    default_recommendation_path_changed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    profile_json: dict[str, object] = Field(default_factory=dict)
    candidates: list[
        HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate
    ] = Field(default_factory=list)
    checks: list[HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck] = (
        Field(default_factory=list)
    )
    blockers: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_market_movement_runtime_activation_segment_expansion_report(
    sample_expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
    *,
    scope_refinement: HistoricalMarketMovementRiskFilterScopeRefinementReport,
    options: (
        HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions | None
    ) = None,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionReport:
    resolved_options = (
        options or HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions()
    )
    existing_segment_keys = set(sample_expansion.selected_segment_group_keys)
    eligible_candidates = _eligible_candidates(
        scope_refinement.scopes,
        existing_segment_keys=existing_segment_keys,
        options=resolved_options,
    )
    selected_candidates = eligible_candidates[: resolved_options.max_selected_candidate_count]
    selected_candidate_keys = {
        candidate.segment_group_key for candidate in selected_candidates
    }
    candidate_models = [
        _candidate_model(
            candidate,
            selected_for_runtime_replay=(
                candidate.segment_group_key in selected_candidate_keys
            ),
            existing_segment_keys=existing_segment_keys,
            options=resolved_options,
        )
        for candidate in eligible_candidates[: resolved_options.max_selected_candidate_count]
    ]
    selected_models = [
        candidate for candidate in candidate_models if candidate.selected_for_runtime_replay
    ]
    total_competitions = {
        competition_id
        for candidate in selected_models
        for competition_id in candidate.source_competition_ids
    }
    total_seasons = {
        season_id
        for candidate in selected_models
        for season_id in candidate.source_season_ids
    }
    total_adjusted_fixture_count = sum(
        candidate.source_adjusted_fixture_count for candidate in selected_models
    )
    total_adjusted_prediction_count = sum(
        candidate.source_adjusted_prediction_count for candidate in selected_models
    )
    adjusted_ratio = _ratio(
        total_adjusted_fixture_count,
        sample_expansion.combined_fixture_count,
    )
    profile_json = _profile_json(
        selected_models,
        sample_expansion=sample_expansion,
        scope_refinement=scope_refinement,
        options=resolved_options,
    )
    checks = _checks(
        sample_expansion=sample_expansion,
        scope_refinement=scope_refinement,
        selected_models=selected_models,
        total_adjusted_fixture_count=total_adjusted_fixture_count,
        total_adjusted_prediction_count=total_adjusted_prediction_count,
        total_competition_count=len(total_competitions),
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    watchlist = [check.name for check in checks if check.status == "watchlist"]
    passed = not blockers
    runtime_replay_expansion_ready = passed and bool(selected_models)
    production_promotion_ready = (
        runtime_replay_expansion_ready
        and sample_expansion.promotion_ready
        and "sample_expansion_promotion_ready_for_production" not in watchlist
    )
    if blockers:
        status: HistoricalMarketMovementRuntimeActivationSegmentExpansionStatus = (
            "blocked"
        )
    elif watchlist:
        status = "watchlist"
    else:
        status = "runtime_replay_expansion_ready"
    warnings = [
        *[
            f"market_movement_activation_segment_expansion:failed:{name}"
            for name in blockers
        ],
        *[
            f"market_movement_activation_segment_expansion:watchlist:{name}"
            for name in watchlist
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_runtime_activation_segment_expansion_v3_2"
        ),
        "expansion_id": resolved_options.expansion_id,
        "status": status,
        "passed": passed,
        "runtime_replay_expansion_ready": runtime_replay_expansion_ready,
        "production_promotion_ready": production_promotion_ready,
        "source_sample_expansion_report_key": sample_expansion.report_key,
        "source_scope_refinement_report_key": scope_refinement.report_key,
        "source_activation_report_key": sample_expansion.source_activation_report_key,
        "sample_expansion_status": sample_expansion.status,
        "sample_expansion_passed": sample_expansion.passed,
        "sample_expansion_promotion_ready": sample_expansion.promotion_ready,
        "scope_refinement_status": scope_refinement.status,
        "stable_scope_count": scope_refinement.stable_scope_count,
        "eligible_candidate_count": len(eligible_candidates),
        "selected_candidate_count": len(selected_models),
        "selected_segment_group_keys": [
            candidate.segment_group_key for candidate in selected_models
        ],
        "selected_rule_ids": [candidate.rule_id for candidate in selected_models],
        "existing_segment_group_keys": list(sample_expansion.selected_segment_group_keys),
        "total_adjusted_fixture_count": total_adjusted_fixture_count,
        "total_adjusted_prediction_count": total_adjusted_prediction_count,
        "total_competition_count": len(total_competitions),
        "total_season_count": len(total_seasons),
        "combined_sample_fixture_count": sample_expansion.combined_fixture_count,
        "adjusted_to_combined_fixture_ratio": adjusted_ratio,
        "default_profile_written": False,
        "default_recommendation_path_changed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "blockers": blockers,
        "watchlist": watchlist,
        "warnings": warnings,
        "options": resolved_options.model_dump(mode="json"),
    }
    report_key = _report_key(summary, candidate_models, checks, profile_json)
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionReport(
        report_key=report_key,
        status=status,
        passed=passed,
        runtime_replay_expansion_ready=runtime_replay_expansion_ready,
        production_promotion_ready=production_promotion_ready,
        expansion_id=resolved_options.expansion_id,
        source_sample_expansion_report_key=sample_expansion.report_key,
        source_scope_refinement_report_key=scope_refinement.report_key,
        source_activation_report_key=sample_expansion.source_activation_report_key,
        sample_expansion_status=sample_expansion.status,
        sample_expansion_passed=sample_expansion.passed,
        sample_expansion_promotion_ready=sample_expansion.promotion_ready,
        scope_refinement_status=scope_refinement.status,
        stable_scope_count=scope_refinement.stable_scope_count,
        selected_candidate_count=len(selected_models),
        selected_segment_group_keys=[
            candidate.segment_group_key for candidate in selected_models
        ],
        existing_segment_group_keys=list(sample_expansion.selected_segment_group_keys),
        total_adjusted_fixture_count=total_adjusted_fixture_count,
        total_adjusted_prediction_count=total_adjusted_prediction_count,
        total_competition_count=len(total_competitions),
        total_season_count=len(total_seasons),
        combined_sample_fixture_count=sample_expansion.combined_fixture_count,
        adjusted_to_combined_fixture_ratio=adjusted_ratio,
        profile_json=profile_json,
        candidates=candidate_models,
        checks=checks,
        blockers=blockers,
        watchlist=watchlist,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_runtime_activation_segment_expansion_report(
    path: Path | str,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionReport:
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_market_movement_runtime_activation_segment_expansion_report(
        load_historical_market_movement_runtime_activation_sample_expansion_report(
            args.sample_expansion_report
        ),
        scope_refinement=load_historical_market_movement_risk_filter_scope_refinement_report(
            args.scope_refinement_report
        ),
        options=_options_from_args(args),
    )
    if args.profile_output_path is not None and report.runtime_replay_expansion_ready:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.profile_json, ensure_ascii=False, indent=2)}\n",
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _eligible_candidates(
    scopes: Sequence[HistoricalMarketMovementRiskFilterScopeCandidate],
    *,
    existing_segment_keys: set[str],
    options: HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions,
) -> list[HistoricalMarketMovementRiskFilterScopeCandidate]:
    candidates = [
        scope
        for scope in scopes
        if scope.status == "stable_shadow_candidate"
        and scope.recommended_action == "keep_shadow"
        and (
            not options.exclude_already_selected_segments
            or scope.segment_group_key not in existing_segment_keys
        )
        and scope.total_adjusted_fixture_count
        >= options.min_candidate_adjusted_fixture_count
        and scope.total_adjusted_prediction_count
        >= options.min_candidate_adjusted_prediction_count
        and len(scope.source_competition_ids) >= options.min_candidate_competition_count
        and _optional_minimum(
            scope.best_final_hit_rate_delta,
            options.min_final_hit_rate_delta,
        )
        and _optional_maximum(scope.best_brier_score_delta, options.max_brier_score_delta)
        and _optional_maximum(scope.best_log_loss_delta, options.max_log_loss_delta)
    ]
    return sorted(candidates, key=_candidate_sort_key, reverse=True)


def _candidate_model(
    candidate: HistoricalMarketMovementRiskFilterScopeCandidate,
    *,
    selected_for_runtime_replay: bool,
    existing_segment_keys: set[str],
    options: HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate:
    rule_id = _rule_id(candidate.segment_group_key, prefix=options.rule_id_prefix)
    summary: dict[str, object] = {
        "segment_group_key": candidate.segment_group_key,
        "source_status": candidate.status,
        "recommended_action": candidate.recommended_action,
        "source_adjusted_fixture_count": candidate.total_adjusted_fixture_count,
        "source_adjusted_prediction_count": candidate.total_adjusted_prediction_count,
        "source_competition_ids": candidate.source_competition_ids,
        "source_season_ids": candidate.source_season_ids,
        "best_final_hit_rate_delta": candidate.best_final_hit_rate_delta,
        "best_brier_score_delta": candidate.best_brier_score_delta,
        "best_log_loss_delta": candidate.best_log_loss_delta,
        "selected_for_runtime_replay": selected_for_runtime_replay,
    }
    rule_json = _rule_json(
        candidate,
        rule_id=rule_id,
        profile_version=options.profile_version,
    )
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate(
        rule_id=rule_id,
        segment_group_key=candidate.segment_group_key,
        segment_group_type=candidate.segment_group_type,
        segment_label=candidate.segment_label,
        source_status=candidate.status,
        recommended_action=candidate.recommended_action,
        source_adjusted_fixture_count=candidate.total_adjusted_fixture_count,
        source_adjusted_prediction_count=candidate.total_adjusted_prediction_count,
        source_competition_ids=candidate.source_competition_ids,
        source_season_ids=candidate.source_season_ids,
        best_final_hit_rate_delta=candidate.best_final_hit_rate_delta,
        best_brier_score_delta=candidate.best_brier_score_delta,
        best_log_loss_delta=candidate.best_log_loss_delta,
        average_brier_score_delta=candidate.average_brier_score_delta,
        average_log_loss_delta=candidate.average_log_loss_delta,
        already_selected=candidate.segment_group_key in existing_segment_keys,
        selected_for_runtime_replay=selected_for_runtime_replay,
        rule_json=rule_json,
        summary_json=summary,
    )


def _profile_json(
    selected_candidates: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate
    ],
    *,
    sample_expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
    scope_refinement: HistoricalMarketMovementRiskFilterScopeRefinementReport,
    options: HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions,
) -> dict[str, object]:
    rules = [candidate.rule_json for candidate in selected_candidates]
    return {
        "calculation_basis": (
            "historical_market_movement_runtime_activation_segment_expansion_profile_v3_2"
        ),
        "profile_version": options.profile_version,
        "staged_only": True,
        "shadow_replay_enabled": True,
        "runtime_shadow_proposal_allowed": True,
        "runtime_profile_proposal_allowed": True,
        "holdout_candidate_allowed": True,
        "default_profile_write_requested": False,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": False,
        "public_response_changed": False,
        "source_sample_expansion_report_key": sample_expansion.report_key,
        "source_scope_refinement_report_key": scope_refinement.report_key,
        "source_activation_report_key": sample_expansion.source_activation_report_key,
        "market_movement_risk_filter_rules": rules,
        "rules": rules,
        "notes": [
            "Segment expansion candidate profile for shadow replay only.",
            "Not written to the default profile and not production-enabled.",
        ],
    }


def _rule_json(
    candidate: HistoricalMarketMovementRiskFilterScopeCandidate,
    *,
    rule_id: str,
    profile_version: str,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "proposed_profile_version": profile_version,
        "proposed_production_enabled": False,
        "holdout_candidate_enabled": True,
        "shadow_replay_enabled": True,
        "production_recommendation_changed": False,
        "segment_group_keys": [candidate.segment_group_key],
        "movement_weight": 0.50,
        "max_probability_shift": 0.08,
        "source_guarded_admission_report_key": "segment_expansion_from_scope_refinement",
        "source_segment_gate_report_key": candidate.best_candidate_id,
        "source_guarded_segment_gate_report_key": None,
        "source_candidate_id": candidate.best_candidate_id,
        "constraints_json": {
            "segment_gate_options": {
                "segment_group_keys": [candidate.segment_group_key],
                "movement_weight": 0.50,
                "max_probability_shift": 0.08,
            }
        },
        "evidence_json": candidate.summary_json,
        "source_report_keys": {
            "scope_refinement": candidate.best_candidate_id or candidate.segment_group_key
        },
        "rollback_conditions": list(DEFAULT_ROLLBACK_CONDITIONS),
        "notes": [
            "Generated from stable scope refinement as a direct runtime replay candidate."
        ],
    }


def _checks(
    *,
    sample_expansion: HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
    scope_refinement: HistoricalMarketMovementRiskFilterScopeRefinementReport,
    selected_models: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate
    ],
    total_adjusted_fixture_count: int,
    total_adjusted_prediction_count: int,
    total_competition_count: int,
    options: HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions,
) -> list[HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck]:
    return [
        _required_bool_check(
            name="sample_expansion_passed",
            actual=sample_expansion.passed,
            required=options.require_sample_expansion_passed,
            detail="source sample expansion gate should pass",
        ),
        _required_bool_check(
            name="sample_expansion_not_blocked",
            actual=sample_expansion.status != "blocked",
            required=options.require_sample_expansion_passed,
            detail="source sample expansion gate should not be blocked",
        ),
        _watchlist_bool_check(
            name="sample_expansion_promotion_ready_for_production",
            actual=sample_expansion.promotion_ready,
            required=options.require_sample_expansion_promotion_ready_for_production,
            detail="production promotion should wait for sample expansion promotion readiness",
        ),
        _required_bool_check(
            name="scope_refinement_shadow_allowed",
            actual=scope_refinement.rolling_shadow_allowed,
            required=options.require_scope_refinement_shadow_allowed,
            detail="scope refinement should remain shadow-allowed",
        ),
        _minimum_check(
            name="stable_scope_count",
            actual=scope_refinement.stable_scope_count,
            threshold=options.min_stable_scope_count,
            detail="scope refinement should expose stable scope candidates",
        ),
        _minimum_check(
            name="selected_candidate_count",
            actual=len(selected_models),
            threshold=options.min_selected_candidate_count,
            detail="segment expansion should select candidates for runtime replay",
        ),
        _minimum_check(
            name="total_adjusted_fixture_count",
            actual=total_adjusted_fixture_count,
            threshold=options.min_total_adjusted_fixture_count,
            detail="selected segment candidates should cover enough adjusted fixtures",
        ),
        _minimum_check(
            name="total_adjusted_prediction_count",
            actual=total_adjusted_prediction_count,
            threshold=options.min_total_adjusted_prediction_count,
            detail="selected segment candidates should cover enough adjusted predictions",
        ),
        _minimum_check(
            name="total_competition_count",
            actual=total_competition_count,
            threshold=options.min_total_competition_count,
            detail="selected segment candidates should broaden competition coverage",
        ),
        _required_bool_check(
            name="no_default_profile_write",
            actual=not sample_expansion.default_profile_written,
            required=options.require_no_default_profile_write,
            detail="segment expansion should not write default profiles",
        ),
        _required_bool_check(
            name="no_default_path_change",
            actual=not sample_expansion.default_recommendation_path_changed,
            required=options.require_no_default_path_change,
            detail="segment expansion should not change default recommendations",
        ),
        _required_bool_check(
            name="no_production_change",
            actual=not sample_expansion.production_recommendation_changed,
            required=options.require_no_production_change,
            detail="segment expansion should not change production recommendations",
        ),
        _required_bool_check(
            name="no_public_response_change",
            actual=not sample_expansion.public_response_changed,
            required=options.require_no_public_response_change,
            detail="segment expansion should not change public responses",
        ),
    ]


def _candidate_sort_key(
    candidate: HistoricalMarketMovementRiskFilterScopeCandidate,
) -> tuple[int, int, float, float, float]:
    brier_gain = -(candidate.best_brier_score_delta or 0.0)
    log_loss_gain = -(candidate.best_log_loss_delta or 0.0)
    hit_delta = candidate.best_final_hit_rate_delta or 0.0
    return (
        len(candidate.source_competition_ids),
        candidate.total_adjusted_fixture_count,
        brier_gain,
        log_loss_gain,
        hit_delta,
    )


def _optional_minimum(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value >= threshold


def _optional_maximum(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value <= threshold


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck:
    if not required:
        return HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=True,
            detail=detail,
        )
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _watchlist_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck:
    if not required:
        return HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=True,
            detail=detail,
        )
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(
        name=name,
        status="passed" if actual else "watchlist",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck:
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _rule_id(segment_group_key: str, *, prefix: str) -> str:
    slug = sub(r"[^a-zA-Z0-9]+", "_", segment_group_key).strip("_").lower()
    return f"{prefix}_{slug}_v1"


def _report_key(
    summary: Mapping[str, object],
    candidates: Sequence[
        HistoricalMarketMovementRuntimeActivationSegmentExpansionCandidate
    ],
    checks: Sequence[HistoricalMarketMovementRuntimeActivationSegmentExpansionCheck],
    profile_json: Mapping[str, object],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "checks": [check.model_dump(mode="json") for check in checks],
            "profile_json": profile_json,
        },
        sort_keys=True,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_market_movement_runtime_activation_segment_expansion:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build direct shadow-replay segment candidates for the staged "
            "market-movement runtime activation lane."
        )
    )
    parser.add_argument("--sample-expansion-report", type=Path, required=True)
    parser.add_argument("--scope-refinement-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument("--max-selected-candidate-count", type=int, default=4)
    parser.add_argument("--min-selected-candidate-count", type=int, default=1)
    parser.add_argument("--min-candidate-adjusted-fixture-count", type=int, default=100)
    parser.add_argument(
        "--min-candidate-adjusted-prediction-count",
        type=int,
        default=300,
    )
    parser.add_argument("--min-total-adjusted-fixture-count", type=int, default=300)
    parser.add_argument("--min-total-adjusted-prediction-count", type=int, default=900)
    parser.add_argument("--min-total-competition-count", type=int, default=2)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions:
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionOptions(
        max_selected_candidate_count=args.max_selected_candidate_count,
        min_selected_candidate_count=args.min_selected_candidate_count,
        min_candidate_adjusted_fixture_count=args.min_candidate_adjusted_fixture_count,
        min_candidate_adjusted_prediction_count=(
            args.min_candidate_adjusted_prediction_count
        ),
        min_total_adjusted_fixture_count=args.min_total_adjusted_fixture_count,
        min_total_adjusted_prediction_count=args.min_total_adjusted_prediction_count,
        min_total_competition_count=args.min_total_competition_count,
    )
