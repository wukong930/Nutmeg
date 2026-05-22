from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
)


class HistoricalReplacementRerankerDiagnosticOptions(BaseModel):
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    max_report_items: int = Field(default=50, ge=1, le=500)
    probability_gap_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    decimal_odds_gap_threshold: float = Field(default=0.10, ge=0.0)
    model_edge_gap_threshold: float = Field(default=0.01, ge=0.0)
    score_gap_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    risk_gap_threshold: float = Field(default=0.02, ge=0.0, le=1.0)


class HistoricalReplacementRerankerDiagnosticItem(BaseModel):
    item_key: str
    competition_id: str
    slice_id: str
    selected_fixture_id: str
    selected_outcome: str
    model_top_replacement_fixture_id: str
    model_top_replacement_outcome: str
    model_top_replacement_rank: int = Field(ge=1)
    actual_best_replacement_fixture_id: str
    actual_best_replacement_outcome: str
    actual_best_replacement_rank: int = Field(ge=1)
    rank_gap: int
    profit_loss_gap: float
    actual_return_gap: float
    replacement_probability_gap: float
    replacement_decimal_odds_gap: float | None = None
    replacement_model_edge_gap: float
    replacement_score_gap: float
    replacement_quality_score_gap: float
    simulated_hit_probability_gap: float
    simulated_risk_score_gap: float
    bias_tags: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementRerankerCompetitionSummary(BaseModel):
    competition_id: str
    item_count: int = Field(ge=0)
    average_rank_gap: float | None = None
    average_profit_loss_gap: float | None = None
    average_probability_gap: float | None = None
    average_decimal_odds_gap: float | None = None
    average_model_edge_gap: float | None = None
    average_score_gap: float | None = None
    average_quality_score_gap: float | None = None
    bias_counts: dict[str, int] = Field(default_factory=dict)


class HistoricalReplacementRerankerDiagnosticReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    evaluated_item_count: int = Field(ge=0)
    rank_gap_item_count: int = Field(ge=0)
    average_rank_gap: float | None = None
    average_profit_loss_gap: float | None = None
    average_probability_gap: float | None = None
    average_decimal_odds_gap: float | None = None
    average_model_edge_gap: float | None = None
    average_score_gap: float | None = None
    average_quality_score_gap: float | None = None
    average_hit_probability_gap: float | None = None
    average_risk_score_gap: float | None = None
    bias_counts: dict[str, int] = Field(default_factory=dict)
    competition_summaries: list[HistoricalReplacementRerankerCompetitionSummary] = (
        Field(default_factory=list)
    )
    items: list[HistoricalReplacementRerankerDiagnosticItem] = Field(default_factory=list)
    top_profit_gap_items: list[HistoricalReplacementRerankerDiagnosticItem] = (
        Field(default_factory=list)
    )
    top_rank_gap_items: list[HistoricalReplacementRerankerDiagnosticItem] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_reranker_diagnostic_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementRerankerDiagnosticOptions | None = None,
) -> HistoricalReplacementRerankerDiagnosticReport:
    resolved_options = options or HistoricalReplacementRerankerDiagnosticOptions()
    warnings = list(audit_report.warnings)
    items = [
        item
        for audit_item in audit_report.items
        if (
            item := _diagnostic_item_for_audit_item(
                audit_item,
                options=resolved_options,
            )
        )
        is not None
    ]
    items = sorted(
        items,
        key=lambda item: (
            item.profit_loss_gap,
            item.rank_gap,
            item.actual_best_replacement_rank,
            item.item_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_items]
    bias_counts = _bias_counts(items)
    competition_summaries = _competition_summaries(items)
    summary: dict[str, object] = {
        "calculation_basis": "historical_replacement_reranker_diagnostics_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "source_item_count": len(audit_report.items),
        "evaluated_item_count": len(items),
        "rank_gap_item_count": sum(1 for item in items if item.rank_gap > 0),
        "average_rank_gap": _average(item.rank_gap for item in items),
        "average_profit_loss_gap": _average(item.profit_loss_gap for item in items),
        "average_probability_gap": _average(
            item.replacement_probability_gap for item in items
        ),
        "average_decimal_odds_gap": _average(
            item.replacement_decimal_odds_gap for item in items
        ),
        "average_model_edge_gap": _average(
            item.replacement_model_edge_gap for item in items
        ),
        "average_score_gap": _average(item.replacement_score_gap for item in items),
        "average_quality_score_gap": _average(
            item.replacement_quality_score_gap for item in items
        ),
        "average_hit_probability_gap": _average(
            item.simulated_hit_probability_gap for item in items
        ),
        "average_risk_score_gap": _average(
            item.simulated_risk_score_gap for item in items
        ),
        "bias_counts": bias_counts,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, items)
    return HistoricalReplacementRerankerDiagnosticReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        evaluated_item_count=len(items),
        rank_gap_item_count=sum(1 for item in items if item.rank_gap > 0),
        average_rank_gap=_average(item.rank_gap for item in items),
        average_profit_loss_gap=_average(item.profit_loss_gap for item in items),
        average_probability_gap=_average(
            item.replacement_probability_gap for item in items
        ),
        average_decimal_odds_gap=_average(
            item.replacement_decimal_odds_gap for item in items
        ),
        average_model_edge_gap=_average(
            item.replacement_model_edge_gap for item in items
        ),
        average_score_gap=_average(item.replacement_score_gap for item in items),
        average_quality_score_gap=_average(
            item.replacement_quality_score_gap for item in items
        ),
        average_hit_probability_gap=_average(
            item.simulated_hit_probability_gap for item in items
        ),
        average_risk_score_gap=_average(item.simulated_risk_score_gap for item in items),
        bias_counts=bias_counts,
        competition_summaries=competition_summaries,
        items=items,
        top_profit_gap_items=_top_profit_gap_items(items),
        top_rank_gap_items=_top_rank_gap_items(items),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_replacement_reranker_diagnostic_report(
        audit_report,
        options=_options_from_args(args),
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


def load_historical_candidate_marginal_audit_report(
    path: Path | str,
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _diagnostic_item_for_audit_item(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    options: HistoricalReplacementRerankerDiagnosticOptions,
) -> HistoricalReplacementRerankerDiagnosticItem | None:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        return None
    if actual_best.profit_loss_delta <= options.min_actual_best_profit_loss_delta:
        return None
    profit_loss_gap = actual_best.profit_loss_delta - model_top.profit_loss_delta
    if profit_loss_gap <= options.min_profit_loss_gap:
        return None
    decimal_odds_gap = (
        actual_best.replacement_decimal_odds - model_top.replacement_decimal_odds
        if actual_best.replacement_decimal_odds is not None
        and model_top.replacement_decimal_odds is not None
        else None
    )
    probability_gap = (
        actual_best.replacement_probability - model_top.replacement_probability
    )
    model_edge_gap = (
        actual_best.replacement_model_edge - model_top.replacement_model_edge
    )
    score_gap = actual_best.replacement_score - model_top.replacement_score
    quality_score_gap = (
        actual_best.replacement_quality_score - model_top.replacement_quality_score
    )
    hit_probability_gap = (
        actual_best.simulated_hit_probability - model_top.simulated_hit_probability
    )
    risk_score_gap = actual_best.simulated_risk_score - model_top.simulated_risk_score
    rank_gap = actual_best.replacement_rank - model_top.replacement_rank
    bias_tags = _bias_tags(
        probability_gap=probability_gap,
        decimal_odds_gap=decimal_odds_gap,
        model_edge_gap=model_edge_gap,
        score_gap=score_gap,
        quality_score_gap=quality_score_gap,
        hit_probability_gap=hit_probability_gap,
        risk_score_gap=risk_score_gap,
        rank_gap=rank_gap,
        options=options,
    )
    return HistoricalReplacementRerankerDiagnosticItem(
        item_key=audit_item.item_key,
        competition_id=audit_item.competition_id,
        slice_id=audit_item.slice_id,
        selected_fixture_id=audit_item.selected_fixture_id,
        selected_outcome=audit_item.selected_outcome,
        model_top_replacement_fixture_id=model_top.replacement_fixture_id,
        model_top_replacement_outcome=model_top.replacement_outcome,
        model_top_replacement_rank=model_top.replacement_rank,
        actual_best_replacement_fixture_id=actual_best.replacement_fixture_id,
        actual_best_replacement_outcome=actual_best.replacement_outcome,
        actual_best_replacement_rank=actual_best.replacement_rank,
        rank_gap=rank_gap,
        profit_loss_gap=profit_loss_gap,
        actual_return_gap=actual_best.actual_return_delta - model_top.actual_return_delta,
        replacement_probability_gap=probability_gap,
        replacement_decimal_odds_gap=decimal_odds_gap,
        replacement_model_edge_gap=model_edge_gap,
        replacement_score_gap=score_gap,
        replacement_quality_score_gap=quality_score_gap,
        simulated_hit_probability_gap=hit_probability_gap,
        simulated_risk_score_gap=risk_score_gap,
        bias_tags=bias_tags,
        summary_json={
            "selected_probability": audit_item.selected_probability,
            "selected_decimal_odds": audit_item.selected_decimal_odds,
            "selected_model_edge": audit_item.selected_model_edge,
            "selected_score": audit_item.selected_score,
            "model_top_profit_loss_delta": model_top.profit_loss_delta,
            "actual_best_profit_loss_delta": actual_best.profit_loss_delta,
            "model_top_replacement_quality_score": model_top.replacement_quality_score,
            "actual_best_replacement_quality_score": (
                actual_best.replacement_quality_score
            ),
        },
    )


def _bias_tags(
    *,
    probability_gap: float,
    decimal_odds_gap: float | None,
    model_edge_gap: float,
    score_gap: float,
    quality_score_gap: float,
    hit_probability_gap: float,
    risk_score_gap: float,
    rank_gap: int,
    options: HistoricalReplacementRerankerDiagnosticOptions,
) -> list[str]:
    tags: list[str] = []
    if rank_gap > 0:
        tags.append("actual_best_ranked_below_model_top")
    if probability_gap <= -options.probability_gap_threshold:
        tags.append("actual_best_lower_probability")
    if probability_gap >= options.probability_gap_threshold:
        tags.append("actual_best_higher_probability")
    if (
        decimal_odds_gap is not None
        and decimal_odds_gap >= options.decimal_odds_gap_threshold
    ):
        tags.append("actual_best_higher_odds")
    if (
        decimal_odds_gap is not None
        and decimal_odds_gap <= -options.decimal_odds_gap_threshold
    ):
        tags.append("actual_best_lower_odds")
    if model_edge_gap >= options.model_edge_gap_threshold:
        tags.append("actual_best_better_model_edge")
    if model_edge_gap <= -options.model_edge_gap_threshold:
        tags.append("actual_best_worse_model_edge")
    if score_gap <= -options.score_gap_threshold:
        tags.append("actual_best_lower_candidate_score")
    if quality_score_gap <= -options.score_gap_threshold:
        tags.append("actual_best_lower_replacement_quality")
    if hit_probability_gap <= -options.probability_gap_threshold:
        tags.append("actual_best_lower_simulated_hit_probability")
    if risk_score_gap >= options.risk_gap_threshold:
        tags.append("actual_best_higher_risk")
    return tags


def _competition_summaries(
    items: Sequence[HistoricalReplacementRerankerDiagnosticItem],
) -> list[HistoricalReplacementRerankerCompetitionSummary]:
    summaries: list[HistoricalReplacementRerankerCompetitionSummary] = []
    for competition_id in sorted({item.competition_id for item in items}):
        competition_items = [
            item for item in items if item.competition_id == competition_id
        ]
        summaries.append(
            HistoricalReplacementRerankerCompetitionSummary(
                competition_id=competition_id,
                item_count=len(competition_items),
                average_rank_gap=_average(item.rank_gap for item in competition_items),
                average_profit_loss_gap=_average(
                    item.profit_loss_gap for item in competition_items
                ),
                average_probability_gap=_average(
                    item.replacement_probability_gap for item in competition_items
                ),
                average_decimal_odds_gap=_average(
                    item.replacement_decimal_odds_gap for item in competition_items
                ),
                average_model_edge_gap=_average(
                    item.replacement_model_edge_gap for item in competition_items
                ),
                average_score_gap=_average(
                    item.replacement_score_gap for item in competition_items
                ),
                average_quality_score_gap=_average(
                    item.replacement_quality_score_gap
                    for item in competition_items
                ),
                bias_counts=_bias_counts(competition_items),
            )
        )
    return summaries


def _bias_counts(
    items: Sequence[HistoricalReplacementRerankerDiagnosticItem],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in items:
        counter.update(item.bias_tags)
    return dict(sorted(counter.items()))


def _top_profit_gap_items(
    items: Sequence[HistoricalReplacementRerankerDiagnosticItem],
) -> list[HistoricalReplacementRerankerDiagnosticItem]:
    return sorted(
        items,
        key=lambda item: (item.profit_loss_gap, item.rank_gap, item.item_key),
        reverse=True,
    )[:10]


def _top_rank_gap_items(
    items: Sequence[HistoricalReplacementRerankerDiagnosticItem],
) -> list[HistoricalReplacementRerankerDiagnosticItem]:
    return sorted(
        items,
        key=lambda item: (item.rank_gap, item.profit_loss_gap, item.item_key),
        reverse=True,
    )[:10]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Diagnose model-top versus hindsight-best replacement ranking gaps."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--max-report-items", type=int, default=50)
    parser.add_argument("--probability-gap-threshold", type=float, default=0.02)
    parser.add_argument("--decimal-odds-gap-threshold", type=float, default=0.10)
    parser.add_argument("--model-edge-gap-threshold", type=float, default=0.01)
    parser.add_argument("--score-gap-threshold", type=float, default=0.02)
    parser.add_argument("--risk-gap-threshold", type=float, default=0.02)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerDiagnosticOptions:
    return HistoricalReplacementRerankerDiagnosticOptions(
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        max_report_items=args.max_report_items,
        probability_gap_threshold=args.probability_gap_threshold,
        decimal_odds_gap_threshold=args.decimal_odds_gap_threshold,
        model_edge_gap_threshold=args.model_edge_gap_threshold,
        score_gap_threshold=args.score_gap_threshold,
        risk_gap_threshold=args.risk_gap_threshold,
    )


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _report_key(
    summary: dict[str, object],
    items: Sequence[HistoricalReplacementRerankerDiagnosticItem],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "items": [item.item_key for item in items],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_reranker_diagnostics:{digest}"
