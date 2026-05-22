from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.replacement_probability_preserving_promotion_review import (
    HistoricalReplacementProbabilityPreservingPromotionReviewReport,
    load_historical_replacement_probability_preserving_promotion_review_report,
)

type RecommendationStrategyPromotionGateStatus = Literal[
    "ready",
    "watchlist",
    "blocked",
]
type RecommendationStrategyPromotionGateCheckStatus = Literal[
    "passed",
    "failed",
]


class RecommendationStrategyPromotionGateOptions(BaseModel):
    gate_id: str = "v3_1_recommendation_strategy_promotion_gate"
    strategy_key: str = "probability_preserving_replacement"
    min_promotion_review_count: int = Field(default=1, ge=1)
    min_ready_promotion_review_count: int = Field(default=1, ge=0)
    min_total_final_answer_count: int = Field(default=30, ge=1)
    min_total_changed_final_answer_count: int = Field(default=1, ge=0)
    min_total_final_answer_hit_delta_count: int = 0
    min_total_profit_loss_delta: float = 0.0
    min_minimum_roi_delta: float | None = 0.0
    max_total_harm_count_vs_original: int = Field(default=0, ge=0)
    max_total_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_total_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_minimum_active_surface_count: int = Field(default=1, ge=0)
    max_total_failed_surface_count: int = Field(default=0, ge=0)
    min_minimum_active_competition_fold_count: int = Field(default=1, ge=0)
    min_minimum_active_season_fold_count: int = Field(default=1, ge=0)
    min_minimum_active_rolling_fold_count: int = Field(default=1, ge=0)
    max_total_failed_fold_count: int = Field(default=0, ge=0)
    require_all_reviews_ready: bool = True
    require_no_review_blockers: bool = True
    require_no_production_allowed: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_dry_run_only_review_profile: bool = True
    require_source_chain_complete: bool = True
    require_unique_selected_candidate: bool = True


class RecommendationStrategyPromotionGateCheck(BaseModel):
    name: str
    status: RecommendationStrategyPromotionGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class RecommendationStrategyPromotionGateEvidence(BaseModel):
    source_path: str | None = None
    report_key: str
    status: str
    promotion_review_allowed: bool
    production_recommendation_allowed: bool
    production_recommendation_changed: bool
    public_response_changed: bool
    dry_run_only_review_profile: bool
    selected_candidate_key: str | None = None
    source_runtime_dry_run_report_key: str
    source_grid_report_key: str | None = None
    source_surface_replay_report_key: str | None = None
    source_admission_report_key: str | None = None
    generated_runtime_shadow_replay_report_key: str | None = None
    candidate_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    profit_loss_delta: float
    roi_delta: float | None = None
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(ge=0)
    profit_loss_harm_count_vs_original: int = Field(ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    active_surface_count: int = Field(ge=0)
    failed_surface_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    blocker_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warning_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class RecommendationStrategyPromotionGateReport(BaseModel):
    gate_key: str
    status: RecommendationStrategyPromotionGateStatus
    strategy_gate_ready: bool
    strategy_key: str
    gate_id: str
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    evidence_count: int = Field(ge=0)
    ready_evidence_count: int = Field(ge=0)
    watchlist_evidence_count: int = Field(ge=0)
    blocked_evidence_count: int = Field(ge=0)
    selected_candidate_keys: list[str] = Field(default_factory=list)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    total_final_answer_count: int = Field(ge=0)
    total_changed_final_answer_count: int = Field(ge=0)
    total_final_answer_hit_delta_count: int
    total_profit_loss_delta: float
    minimum_roi_delta: float | None = None
    total_harm_count_vs_original: int = Field(ge=0)
    total_final_hit_harm_count_vs_original: int = Field(ge=0)
    total_profit_loss_harm_count_vs_original: int = Field(ge=0)
    minimum_active_surface_count: int = Field(ge=0)
    total_failed_surface_count: int = Field(ge=0)
    minimum_active_competition_fold_count: int = Field(ge=0)
    minimum_active_season_fold_count: int = Field(ge=0)
    minimum_active_rolling_fold_count: int = Field(ge=0)
    total_failed_fold_count: int = Field(ge=0)
    evidence: list[RecommendationStrategyPromotionGateEvidence] = Field(
        default_factory=list
    )
    checks: list[RecommendationStrategyPromotionGateCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_recommendation_strategy_promotion_gate_report(
    promotion_review_reports: Sequence[
        HistoricalReplacementProbabilityPreservingPromotionReviewReport
    ],
    *,
    source_paths: Sequence[Path | str | None] | None = None,
    options: RecommendationStrategyPromotionGateOptions | None = None,
) -> RecommendationStrategyPromotionGateReport:
    resolved_options = options or RecommendationStrategyPromotionGateOptions()
    evidence = _evidence_items(promotion_review_reports, source_paths=source_paths)
    metrics = _metrics(evidence)
    checks = _checks(evidence, metrics=metrics, options=resolved_options)
    failed_check_names = [check.name for check in checks if check.status == "failed"]
    status = _status(evidence, failed_check_names)
    strategy_gate_ready = status == "ready"
    warnings = _warnings(evidence, failed_check_names)
    summary: dict[str, object] = {
        "calculation_basis": "recommendation_strategy_promotion_gate_v3_1",
        "status": status,
        "strategy_gate_ready": strategy_gate_ready,
        "strategy_key": resolved_options.strategy_key,
        "gate_id": resolved_options.gate_id,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "evidence_count": metrics.evidence_count,
        "ready_evidence_count": metrics.ready_evidence_count,
        "watchlist_evidence_count": metrics.watchlist_evidence_count,
        "blocked_evidence_count": metrics.blocked_evidence_count,
        "selected_candidate_keys": metrics.selected_candidate_keys,
        "allowed_competition_ids": metrics.allowed_competition_ids,
        "total_final_answer_count": metrics.total_final_answer_count,
        "total_changed_final_answer_count": metrics.total_changed_final_answer_count,
        "total_final_answer_hit_delta_count": (
            metrics.total_final_answer_hit_delta_count
        ),
        "total_profit_loss_delta": metrics.total_profit_loss_delta,
        "minimum_roi_delta": metrics.minimum_roi_delta,
        "total_harm_count_vs_original": metrics.total_harm_count_vs_original,
        "total_final_hit_harm_count_vs_original": (
            metrics.total_final_hit_harm_count_vs_original
        ),
        "total_profit_loss_harm_count_vs_original": (
            metrics.total_profit_loss_harm_count_vs_original
        ),
        "minimum_active_surface_count": metrics.minimum_active_surface_count,
        "total_failed_surface_count": metrics.total_failed_surface_count,
        "minimum_active_competition_fold_count": (
            metrics.minimum_active_competition_fold_count
        ),
        "minimum_active_season_fold_count": (
            metrics.minimum_active_season_fold_count
        ),
        "minimum_active_rolling_fold_count": (
            metrics.minimum_active_rolling_fold_count
        ),
        "total_failed_fold_count": metrics.total_failed_fold_count,
        "blockers": failed_check_names,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    gate_key = _gate_key(summary, evidence, checks)
    return RecommendationStrategyPromotionGateReport(
        gate_key=gate_key,
        status=status,
        strategy_gate_ready=strategy_gate_ready,
        strategy_key=resolved_options.strategy_key,
        gate_id=resolved_options.gate_id,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        evidence_count=metrics.evidence_count,
        ready_evidence_count=metrics.ready_evidence_count,
        watchlist_evidence_count=metrics.watchlist_evidence_count,
        blocked_evidence_count=metrics.blocked_evidence_count,
        selected_candidate_keys=metrics.selected_candidate_keys,
        allowed_competition_ids=metrics.allowed_competition_ids,
        total_final_answer_count=metrics.total_final_answer_count,
        total_changed_final_answer_count=metrics.total_changed_final_answer_count,
        total_final_answer_hit_delta_count=metrics.total_final_answer_hit_delta_count,
        total_profit_loss_delta=metrics.total_profit_loss_delta,
        minimum_roi_delta=metrics.minimum_roi_delta,
        total_harm_count_vs_original=metrics.total_harm_count_vs_original,
        total_final_hit_harm_count_vs_original=(
            metrics.total_final_hit_harm_count_vs_original
        ),
        total_profit_loss_harm_count_vs_original=(
            metrics.total_profit_loss_harm_count_vs_original
        ),
        minimum_active_surface_count=metrics.minimum_active_surface_count,
        total_failed_surface_count=metrics.total_failed_surface_count,
        minimum_active_competition_fold_count=(
            metrics.minimum_active_competition_fold_count
        ),
        minimum_active_season_fold_count=metrics.minimum_active_season_fold_count,
        minimum_active_rolling_fold_count=metrics.minimum_active_rolling_fold_count,
        total_failed_fold_count=metrics.total_failed_fold_count,
        evidence=evidence,
        checks=checks,
        blockers=failed_check_names,
        warnings=warnings,
        summary_json={**summary, "gate_key": gate_key},
    )


def load_recommendation_strategy_promotion_gate_report(
    path: Path | str,
) -> RecommendationStrategyPromotionGateReport:
    return RecommendationStrategyPromotionGateReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    reports = [
        load_historical_replacement_probability_preserving_promotion_review_report(
            path
        )
        for path in args.promotion_review_report
    ]
    report = build_recommendation_strategy_promotion_gate_report(
        reports,
        source_paths=args.promotion_review_report,
        options=_options_from_args(args),
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


class _GateMetrics(BaseModel):
    evidence_count: int = Field(ge=0)
    ready_evidence_count: int = Field(ge=0)
    watchlist_evidence_count: int = Field(ge=0)
    blocked_evidence_count: int = Field(ge=0)
    selected_candidate_keys: list[str] = Field(default_factory=list)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    total_final_answer_count: int = Field(ge=0)
    total_changed_final_answer_count: int = Field(ge=0)
    total_final_answer_hit_delta_count: int
    total_profit_loss_delta: float
    minimum_roi_delta: float | None = None
    total_harm_count_vs_original: int = Field(ge=0)
    total_final_hit_harm_count_vs_original: int = Field(ge=0)
    total_profit_loss_harm_count_vs_original: int = Field(ge=0)
    minimum_active_surface_count: int = Field(ge=0)
    total_failed_surface_count: int = Field(ge=0)
    minimum_active_competition_fold_count: int = Field(ge=0)
    minimum_active_season_fold_count: int = Field(ge=0)
    minimum_active_rolling_fold_count: int = Field(ge=0)
    total_failed_fold_count: int = Field(ge=0)


def _evidence_items(
    reports: Sequence[HistoricalReplacementProbabilityPreservingPromotionReviewReport],
    *,
    source_paths: Sequence[Path | str | None] | None,
) -> list[RecommendationStrategyPromotionGateEvidence]:
    paths = list(source_paths or [])
    return [
        _evidence_item(report, source_path=paths[index] if index < len(paths) else None)
        for index, report in enumerate(reports)
    ]


def _evidence_item(
    report: HistoricalReplacementProbabilityPreservingPromotionReviewReport,
    *,
    source_path: Path | str | None,
) -> RecommendationStrategyPromotionGateEvidence:
    return RecommendationStrategyPromotionGateEvidence(
        source_path=str(source_path) if source_path is not None else None,
        report_key=report.report_key,
        status=report.status,
        promotion_review_allowed=report.promotion_review_allowed,
        production_recommendation_allowed=report.production_recommendation_allowed,
        production_recommendation_changed=report.production_recommendation_changed,
        public_response_changed=report.public_response_changed,
        dry_run_only_review_profile=bool(report.review_profile_json.get("dry_run_only")),
        selected_candidate_key=report.selected_candidate_key,
        source_runtime_dry_run_report_key=report.source_runtime_dry_run_report_key,
        source_grid_report_key=report.source_grid_report_key,
        source_surface_replay_report_key=report.source_surface_replay_report_key,
        source_admission_report_key=report.source_admission_report_key,
        generated_runtime_shadow_replay_report_key=(
            report.generated_runtime_shadow_replay_report_key
        ),
        candidate_rule_count=report.candidate_rule_count,
        allowed_competition_ids=sorted(set(report.allowed_competition_ids)),
        final_answer_count=report.final_answer_count,
        changed_final_answer_count=report.changed_final_answer_count,
        final_answer_hit_delta_count=report.final_answer_hit_delta_count,
        profit_loss_delta=report.profit_loss_delta,
        roi_delta=report.roi_delta,
        harm_count_vs_original=report.harm_count_vs_original,
        final_hit_harm_count_vs_original=report.final_hit_harm_count_vs_original,
        profit_loss_harm_count_vs_original=report.profit_loss_harm_count_vs_original,
        average_hit_probability_delta_vs_original=(
            report.average_hit_probability_delta_vs_original
        ),
        active_surface_count=report.active_surface_count,
        failed_surface_count=report.failed_surface_count,
        active_competition_fold_count=report.active_competition_fold_count,
        active_season_fold_count=report.active_season_fold_count,
        active_rolling_fold_count=report.active_rolling_fold_count,
        failed_fold_count=report.failed_fold_count,
        blocker_count=len(report.blockers),
        blockers=list(report.blockers),
        warning_count=len(report.warnings),
        warnings=list(report.warnings),
    )


def _metrics(
    evidence: Sequence[RecommendationStrategyPromotionGateEvidence],
) -> _GateMetrics:
    return _GateMetrics(
        evidence_count=len(evidence),
        ready_evidence_count=sum(1 for item in evidence if item.status == "promotion_review_ready"),
        watchlist_evidence_count=sum(
            1 for item in evidence if item.status == "promotion_review_watchlist"
        ),
        blocked_evidence_count=sum(1 for item in evidence if item.status == "blocked"),
        selected_candidate_keys=_unique(
            item.selected_candidate_key for item in evidence if item.selected_candidate_key
        ),
        allowed_competition_ids=_unique(
            competition_id
            for item in evidence
            for competition_id in item.allowed_competition_ids
        ),
        total_final_answer_count=sum(item.final_answer_count for item in evidence),
        total_changed_final_answer_count=sum(
            item.changed_final_answer_count for item in evidence
        ),
        total_final_answer_hit_delta_count=sum(
            item.final_answer_hit_delta_count for item in evidence
        ),
        total_profit_loss_delta=sum(item.profit_loss_delta for item in evidence),
        minimum_roi_delta=_minimum(
            item.roi_delta for item in evidence if item.roi_delta is not None
        ),
        total_harm_count_vs_original=sum(
            item.harm_count_vs_original for item in evidence
        ),
        total_final_hit_harm_count_vs_original=sum(
            item.final_hit_harm_count_vs_original for item in evidence
        ),
        total_profit_loss_harm_count_vs_original=sum(
            item.profit_loss_harm_count_vs_original for item in evidence
        ),
        minimum_active_surface_count=_minimum_int(
            item.active_surface_count for item in evidence
        ),
        total_failed_surface_count=sum(item.failed_surface_count for item in evidence),
        minimum_active_competition_fold_count=_minimum_int(
            item.active_competition_fold_count for item in evidence
        ),
        minimum_active_season_fold_count=_minimum_int(
            item.active_season_fold_count for item in evidence
        ),
        minimum_active_rolling_fold_count=_minimum_int(
            item.active_rolling_fold_count for item in evidence
        ),
        total_failed_fold_count=sum(item.failed_fold_count for item in evidence),
    )


def _checks(
    evidence: Sequence[RecommendationStrategyPromotionGateEvidence],
    *,
    metrics: _GateMetrics,
    options: RecommendationStrategyPromotionGateOptions,
) -> list[RecommendationStrategyPromotionGateCheck]:
    return [
        _minimum_check(
            name="promotion_review_count",
            actual=metrics.evidence_count,
            threshold=options.min_promotion_review_count,
            detail="strategy gate must include enough promotion review evidence",
        ),
        _minimum_check(
            name="ready_promotion_review_count",
            actual=metrics.ready_evidence_count,
            threshold=options.min_ready_promotion_review_count,
            detail="strategy gate must include enough ready promotion reviews",
        ),
        _boolean_check(
            name="all_reviews_ready",
            actual=metrics.ready_evidence_count == metrics.evidence_count,
            expected=True,
            enabled=options.require_all_reviews_ready,
            detail="all required promotion reviews should be ready",
        ),
        _maximum_check(
            name="blocked_promotion_review_count",
            actual=metrics.blocked_evidence_count,
            threshold=0,
            detail="blocked promotion reviews cannot enter a strategy gate",
        ),
        _maximum_check(
            name="promotion_review_blocker_count",
            actual=sum(item.blocker_count for item in evidence),
            threshold=0,
            enabled=options.require_no_review_blockers,
            detail="source promotion reviews should not carry blockers",
        ),
        _boolean_check(
            name="production_recommendation_allowed_false",
            actual=not any(item.production_recommendation_allowed for item in evidence),
            expected=True,
            enabled=options.require_no_production_allowed,
            detail="strategy gate must not allow production recommendations",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not any(item.production_recommendation_changed for item in evidence),
            expected=True,
            enabled=options.require_no_production_change,
            detail="strategy gate evidence must not have changed production recommendations",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=not any(item.public_response_changed for item in evidence),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="strategy gate evidence must not have changed public responses",
        ),
        _boolean_check(
            name="dry_run_only_review_profile",
            actual=all(item.dry_run_only_review_profile for item in evidence),
            expected=True,
            enabled=options.require_dry_run_only_review_profile,
            detail="strategy gate source profiles should remain dry-run only",
        ),
        _minimum_check(
            name="total_final_answer_count",
            actual=metrics.total_final_answer_count,
            threshold=options.min_total_final_answer_count,
            detail="combined evidence should cover enough final answers",
        ),
        _minimum_check(
            name="total_changed_final_answer_count",
            actual=metrics.total_changed_final_answer_count,
            threshold=options.min_total_changed_final_answer_count,
            detail="combined evidence should affect enough final answers",
        ),
        _minimum_check(
            name="total_final_answer_hit_delta_count",
            actual=metrics.total_final_answer_hit_delta_count,
            threshold=options.min_total_final_answer_hit_delta_count,
            detail="combined final-answer hit count should not regress",
        ),
        _minimum_check(
            name="total_profit_loss_delta",
            actual=metrics.total_profit_loss_delta,
            threshold=options.min_total_profit_loss_delta,
            detail="combined P/L should not regress",
        ),
        _optional_minimum_check(
            name="minimum_roi_delta",
            actual=metrics.minimum_roi_delta,
            threshold=options.min_minimum_roi_delta,
            detail="minimum ROI delta across evidence should not regress",
        ),
        _maximum_check(
            name="total_harm_count_vs_original",
            actual=metrics.total_harm_count_vs_original,
            threshold=options.max_total_harm_count_vs_original,
            detail="combined evidence should not harm original final answers",
        ),
        _maximum_check(
            name="total_final_hit_harm_count_vs_original",
            actual=metrics.total_final_hit_harm_count_vs_original,
            threshold=options.max_total_final_hit_harm_count_vs_original,
            detail="combined evidence should not turn original hits into misses",
        ),
        _maximum_check(
            name="total_profit_loss_harm_count_vs_original",
            actual=metrics.total_profit_loss_harm_count_vs_original,
            threshold=options.max_total_profit_loss_harm_count_vs_original,
            detail="combined evidence should not reduce original final-answer P/L",
        ),
        _minimum_check(
            name="minimum_active_surface_count",
            actual=metrics.minimum_active_surface_count,
            threshold=options.min_minimum_active_surface_count,
            detail="each evidence item should cover enough active surfaces",
        ),
        _maximum_check(
            name="total_failed_surface_count",
            actual=metrics.total_failed_surface_count,
            threshold=options.max_total_failed_surface_count,
            detail="combined evidence should not include failed surfaces",
        ),
        _minimum_check(
            name="minimum_active_competition_fold_count",
            actual=metrics.minimum_active_competition_fold_count,
            threshold=options.min_minimum_active_competition_fold_count,
            detail="each evidence item should cover enough competition folds",
        ),
        _minimum_check(
            name="minimum_active_season_fold_count",
            actual=metrics.minimum_active_season_fold_count,
            threshold=options.min_minimum_active_season_fold_count,
            detail="each evidence item should cover enough season folds",
        ),
        _minimum_check(
            name="minimum_active_rolling_fold_count",
            actual=metrics.minimum_active_rolling_fold_count,
            threshold=options.min_minimum_active_rolling_fold_count,
            detail="each evidence item should cover enough rolling folds",
        ),
        _maximum_check(
            name="total_failed_fold_count",
            actual=metrics.total_failed_fold_count,
            threshold=options.max_total_failed_fold_count,
            detail="combined evidence should not include failed folds",
        ),
        _boolean_check(
            name="source_chain_complete",
            actual=all(_source_chain_complete(item) for item in evidence),
            expected=True,
            enabled=options.require_source_chain_complete,
            detail="each evidence item must preserve grid/surface/admission/runtime chain",
        ),
        _boolean_check(
            name="unique_selected_candidate",
            actual=len(metrics.selected_candidate_keys) <= 1,
            expected=True,
            enabled=options.require_unique_selected_candidate,
            detail="strategy gate should keep selected candidate lineage explicit",
        ),
    ]


def _status(
    evidence: Sequence[RecommendationStrategyPromotionGateEvidence],
    failed_check_names: Sequence[str],
) -> RecommendationStrategyPromotionGateStatus:
    if not evidence or any(item.status == "blocked" for item in evidence):
        return "blocked"
    blocking_failures = {
        "promotion_review_count",
        "blocked_promotion_review_count",
        "production_recommendation_allowed_false",
        "no_production_recommendation_change",
        "no_public_response_change",
    }
    if any(name in blocking_failures for name in failed_check_names):
        return "blocked"
    if failed_check_names:
        return "watchlist"
    return "ready"


def _warnings(
    evidence: Sequence[RecommendationStrategyPromotionGateEvidence],
    failed_check_names: Sequence[str],
) -> list[str]:
    return [
        warning
        for warning in [
            *(warning for item in evidence for warning in item.warnings),
            *(
                f"recommendation_strategy_promotion_gate:failed_check:{name}"
                for name in failed_check_names
            ),
        ]
    ]


def _source_chain_complete(
    item: RecommendationStrategyPromotionGateEvidence,
) -> bool:
    return all(
        [
            item.source_runtime_dry_run_report_key,
            item.source_grid_report_key,
            item.source_surface_replay_report_key,
            item.source_admission_report_key,
            item.generated_runtime_shadow_replay_report_key,
        ]
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> RecommendationStrategyPromotionGateCheck:
    if not enabled:
        return RecommendationStrategyPromotionGateCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyPromotionGateCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> RecommendationStrategyPromotionGateCheck:
    return RecommendationStrategyPromotionGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> RecommendationStrategyPromotionGateCheck:
    if threshold is None:
        return RecommendationStrategyPromotionGateCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=None,
            detail=f"{detail} (disabled)",
        )
    if actual is None:
        return RecommendationStrategyPromotionGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return _minimum_check(
        name=name,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
    enabled: bool = True,
) -> RecommendationStrategyPromotionGateCheck:
    if not enabled:
        return RecommendationStrategyPromotionGateCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=threshold,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyPromotionGateCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _minimum(values: Iterable[float]) -> float | None:
    resolved = list(values)
    if not resolved:
        return None
    return min(resolved)


def _minimum_int(values: Iterable[int]) -> int:
    resolved = list(values)
    if not resolved:
        return 0
    return min(resolved)


def _unique(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Aggregate governed promotion review artifacts into a strategy-level "
            "quality gate without changing production recommendations."
        )
    )
    parser.add_argument(
        "--promotion-review-report",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument("--gate-id", default="v3_1_recommendation_strategy_promotion_gate")
    parser.add_argument("--strategy-key", default="probability_preserving_replacement")
    parser.add_argument("--min-promotion-review-count", type=int, default=1)
    parser.add_argument("--min-ready-promotion-review-count", type=int, default=1)
    parser.add_argument("--min-total-final-answer-count", type=int, default=30)
    parser.add_argument("--min-total-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-total-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-total-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-minimum-roi-delta", type=float, default=0.0)
    parser.add_argument("--allow-missing-roi-delta", action="store_true")
    parser.add_argument("--max-total-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-total-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-total-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument("--min-minimum-active-surface-count", type=int, default=1)
    parser.add_argument("--max-total-failed-surface-count", type=int, default=0)
    parser.add_argument(
        "--min-minimum-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument("--min-minimum-active-season-fold-count", type=int, default=1)
    parser.add_argument("--min-minimum-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--max-total-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-partial-review", action="store_true")
    parser.add_argument("--allow-review-blockers", action="store_true")
    parser.add_argument("--allow-production-recommendation", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-non-dry-run-review-profile", action="store_true")
    parser.add_argument("--allow-incomplete-source-chain", action="store_true")
    parser.add_argument("--allow-multiple-candidates", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationStrategyPromotionGateOptions:
    return RecommendationStrategyPromotionGateOptions(
        gate_id=args.gate_id,
        strategy_key=args.strategy_key,
        min_promotion_review_count=args.min_promotion_review_count,
        min_ready_promotion_review_count=args.min_ready_promotion_review_count,
        min_total_final_answer_count=args.min_total_final_answer_count,
        min_total_changed_final_answer_count=args.min_total_changed_final_answer_count,
        min_total_final_answer_hit_delta_count=(
            args.min_total_final_answer_hit_delta_count
        ),
        min_total_profit_loss_delta=args.min_total_profit_loss_delta,
        min_minimum_roi_delta=(
            None if args.allow_missing_roi_delta else args.min_minimum_roi_delta
        ),
        max_total_harm_count_vs_original=args.max_total_harm_count_vs_original,
        max_total_final_hit_harm_count_vs_original=(
            args.max_total_final_hit_harm_count_vs_original
        ),
        max_total_profit_loss_harm_count_vs_original=(
            args.max_total_profit_loss_harm_count_vs_original
        ),
        min_minimum_active_surface_count=args.min_minimum_active_surface_count,
        max_total_failed_surface_count=args.max_total_failed_surface_count,
        min_minimum_active_competition_fold_count=(
            args.min_minimum_active_competition_fold_count
        ),
        min_minimum_active_season_fold_count=args.min_minimum_active_season_fold_count,
        min_minimum_active_rolling_fold_count=(
            args.min_minimum_active_rolling_fold_count
        ),
        max_total_failed_fold_count=args.max_total_failed_fold_count,
        require_all_reviews_ready=not args.allow_partial_review,
        require_no_review_blockers=not args.allow_review_blockers,
        require_no_production_allowed=not args.allow_production_recommendation,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        require_dry_run_only_review_profile=not args.allow_non_dry_run_review_profile,
        require_source_chain_complete=not args.allow_incomplete_source_chain,
        require_unique_selected_candidate=not args.allow_multiple_candidates,
    )


def _gate_key(
    summary: Mapping[str, object],
    evidence: Sequence[RecommendationStrategyPromotionGateEvidence],
    checks: Sequence[RecommendationStrategyPromotionGateCheck],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "checks": [check.model_dump(mode="json") for check in checks],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"recommendation_strategy_promotion_gate:{digest}"
