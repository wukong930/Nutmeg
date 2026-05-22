from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type CompetitionProfileProposalStatus = Literal[
    "production_ready",
    "shadow_only",
    "blocked",
    "no_candidates",
]


class CompetitionProfileProposalOptions(BaseModel):
    profile_version: str = "v3_1_competition_profile_proposal"
    min_historical_final_hit_sample_size: int = Field(default=30, ge=1)
    require_production_admission: bool = True


class CompetitionProfileProposal(BaseModel):
    competition_id: str = Field(min_length=1)
    scenario_key: str = Field(min_length=1)
    final_answer_score_adjustments: dict[str, float] = Field(default_factory=dict)
    min_historical_final_hit_sample_size: int = Field(ge=1)
    source_report_key: str | None = None
    admission_report_key: str | None = None
    production_recommendation_allowed: bool
    training_pool_allowed: bool
    shadow_allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    evidence_json: dict[str, object] = Field(default_factory=dict)


class CompetitionProfileProposalReport(BaseModel):
    report_key: str
    status: CompetitionProfileProposalStatus
    production_recommendation_allowed: bool
    training_pool_allowed: bool
    shadow_allowed: bool
    proposal_count: int = Field(ge=0)
    profile_evidence_report_key: str | None = None
    admission_report_key: str | None = None
    admission_decision: str | None = None
    proposals: list[CompetitionProfileProposal] = Field(default_factory=list)
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_competition_profile_proposal_report(
    *,
    profile_evidence_report: Mapping[str, object],
    admission_gate_report: Mapping[str, object] | None = None,
    options: CompetitionProfileProposalOptions | None = None,
) -> CompetitionProfileProposalReport:
    resolved_options = options or CompetitionProfileProposalOptions()
    evidence_summary = _summary(profile_evidence_report)
    admission_summary = _summary(admission_gate_report or {})
    profile_evidence_report_key = _string(profile_evidence_report.get("report_key")) or _string(
        evidence_summary.get("report_key")
    )
    admission_report_key = _string((admission_gate_report or {}).get("report_key")) or _string(
        admission_summary.get("report_key")
    )
    admission_decision = _string((admission_gate_report or {}).get("decision")) or _string(
        admission_summary.get("decision")
    )
    production_allowed = _bool(
        (admission_gate_report or {}).get("production_recommendation_allowed"),
        fallback=_bool(admission_summary.get("production_recommendation_allowed")),
    )
    training_allowed = _bool(
        (admission_gate_report or {}).get("training_pool_allowed"),
        fallback=_bool(admission_summary.get("training_pool_allowed")),
    )
    shadow_allowed = _bool(
        (admission_gate_report or {}).get("shadow_allowed"),
        fallback=_bool(admission_summary.get("shadow_allowed")),
    )
    if admission_gate_report is None:
        shadow_allowed = False

    accepted_decisions = [
        item
        for item in _mapping_list(profile_evidence_report.get("decisions"))
        if item.get("status") == "candidate_accepted"
    ]
    default_allowed = (
        production_allowed
        if resolved_options.require_production_admission
        else production_allowed or shadow_allowed
    )
    proposals = [
        _proposal_from_decision(
            decision,
            profile_evidence_report_key=profile_evidence_report_key,
            admission_report_key=admission_report_key,
            production_allowed=default_allowed,
            raw_production_allowed=production_allowed,
            training_allowed=training_allowed,
            shadow_allowed=shadow_allowed,
            min_historical_final_hit_sample_size=(
                resolved_options.min_historical_final_hit_sample_size
            ),
        )
        for decision in accepted_decisions
    ]
    warnings = _proposal_warnings(
        proposals=proposals,
        admission_gate_report=admission_gate_report,
        production_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
    )
    status = _proposal_status(
        proposals=proposals,
        production_allowed=default_allowed,
        shadow_allowed=shadow_allowed,
    )
    proposal_profile_set = _proposal_profile_set_json(
        proposals,
        options=resolved_options,
        status=status,
        production_allowed=default_allowed,
        admission_decision=admission_decision,
        profile_evidence_report_key=profile_evidence_report_key,
        admission_report_key=admission_report_key,
    )
    summary: dict[str, object] = {
        "calculation_basis": "competition_profile_proposal_v3_1",
        "status": status,
        "profile_version": resolved_options.profile_version,
        "profile_evidence_report_key": profile_evidence_report_key,
        "admission_report_key": admission_report_key,
        "admission_decision": admission_decision,
        "production_recommendation_allowed": default_allowed,
        "training_pool_allowed": training_allowed and default_allowed,
        "shadow_allowed": shadow_allowed,
        "proposal_count": len(proposals),
        "accepted_profile_evidence_count": len(accepted_decisions),
        "accepted_profile_adjustments": evidence_summary.get(
            "accepted_profile_adjustments",
            {},
        ),
        "min_historical_final_hit_sample_size": (
            resolved_options.min_historical_final_hit_sample_size
        ),
        "require_production_admission": resolved_options.require_production_admission,
        "warnings": warnings,
    }
    report_key = _report_key(summary, proposals=proposals)
    return CompetitionProfileProposalReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=default_allowed,
        training_pool_allowed=training_allowed and default_allowed,
        shadow_allowed=shadow_allowed,
        proposal_count=len(proposals),
        profile_evidence_report_key=profile_evidence_report_key,
        admission_report_key=admission_report_key,
        admission_decision=admission_decision,
        proposals=proposals,
        proposal_profile_set_json=proposal_profile_set,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_competition_profile_proposal_report(
        profile_evidence_report=_load_json(args.profile_evidence_report),
        admission_gate_report=(
            _load_json(args.admission_gate_report)
            if args.admission_gate_report is not None
            else None
        ),
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
    if report.status != "production_ready" and not args.no_fail_process:
        raise SystemExit(1)


def _proposal_from_decision(
    decision: Mapping[str, object],
    *,
    profile_evidence_report_key: str | None,
    admission_report_key: str | None,
    production_allowed: bool,
    raw_production_allowed: bool,
    training_allowed: bool,
    shadow_allowed: bool,
    min_historical_final_hit_sample_size: int,
) -> CompetitionProfileProposal:
    competition_id = _required_string(decision.get("competition_id"), "competition_id")
    scenario_key = _required_string(
        decision.get("recommended_scenario_key"),
        "recommended_scenario_key",
    )
    suggested_score_adjustment = _float(decision.get("suggested_score_adjustment"))
    selected_metric = _mapping(decision.get("selected_metric"))
    baseline_metric = _mapping(decision.get("baseline_metric"))
    sample_size = _int(
        selected_metric.get("sample_size"),
        fallback=_int(baseline_metric.get("sample_size")),
    )
    reason_codes = [
        *_string_list(decision.get("reason_codes")),
        "competition_profile_proposal:evidence_candidate_accepted",
    ]
    if production_allowed:
        reason_codes.append("competition_profile_proposal:default_recommendation_allowed")
    elif raw_production_allowed:
        reason_codes.append("competition_profile_proposal:production_admission_ignored")
    elif shadow_allowed:
        reason_codes.append("competition_profile_proposal:shadow_only_admission")
    else:
        reason_codes.append("competition_profile_proposal:admission_blocked")
    return CompetitionProfileProposal(
        competition_id=competition_id,
        scenario_key=scenario_key,
        final_answer_score_adjustments={scenario_key: suggested_score_adjustment},
        min_historical_final_hit_sample_size=max(
            min_historical_final_hit_sample_size,
            sample_size,
        ),
        source_report_key=profile_evidence_report_key,
        admission_report_key=admission_report_key,
        production_recommendation_allowed=production_allowed,
        training_pool_allowed=training_allowed and production_allowed,
        shadow_allowed=shadow_allowed,
        reason_codes=reason_codes,
        evidence_json={
            "hit_count_delta": decision.get("hit_count_delta"),
            "roi_delta": decision.get("roi_delta"),
            "profit_loss_delta": decision.get("profit_loss_delta"),
            "baseline_metric": baseline_metric,
            "selected_metric": selected_metric,
        },
    )


def _proposal_warnings(
    *,
    proposals: Sequence[CompetitionProfileProposal],
    admission_gate_report: Mapping[str, object] | None,
    production_allowed: bool,
    shadow_allowed: bool,
) -> list[str]:
    warnings: list[str] = []
    if not proposals:
        warnings.append("competition_profile_proposal:no_accepted_profile_candidates")
    if admission_gate_report is None:
        warnings.append("competition_profile_proposal:missing_admission_gate_report")
    elif not production_allowed and shadow_allowed:
        warnings.append("competition_profile_proposal:admission_shadow_only")
    elif not production_allowed and not shadow_allowed:
        warnings.append("competition_profile_proposal:admission_blocked")
    return warnings


def _proposal_status(
    *,
    proposals: Sequence[CompetitionProfileProposal],
    production_allowed: bool,
    shadow_allowed: bool,
) -> CompetitionProfileProposalStatus:
    if not proposals:
        return "no_candidates"
    if production_allowed:
        return "production_ready"
    if shadow_allowed:
        return "shadow_only"
    return "blocked"


def _proposal_profile_set_json(
    proposals: Sequence[CompetitionProfileProposal],
    *,
    options: CompetitionProfileProposalOptions,
    status: CompetitionProfileProposalStatus,
    production_allowed: bool,
    admission_decision: str | None,
    profile_evidence_report_key: str | None,
    admission_report_key: str | None,
) -> dict[str, object]:
    return {
        "profile_version": options.profile_version,
        "calculation_basis": "competition_profile_proposal_v3_1",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "admission_decision": admission_decision,
        "profiles": [
            {
                "competition_id": proposal.competition_id,
                "final_answer_score_adjustments": (proposal.final_answer_score_adjustments),
                "min_historical_final_hit_sample_size": (
                    proposal.min_historical_final_hit_sample_size
                ),
                "source_report_key": proposal.source_report_key,
                "notes": [
                    "Generated from competition profile evidence.",
                    (
                        "Do not copy to the default profile config unless "
                        "production_recommendation_allowed is true."
                    ),
                ],
            }
            for proposal in proposals
        ],
        "notes": [
            "Profile proposals are internal governance artifacts.",
            "They do not place bets and do not guarantee outcomes.",
            f"profile_evidence_report_key={profile_evidence_report_key}",
            f"admission_report_key={admission_report_key}",
        ],
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Convert accepted competition profile evidence into a governed proposal artifact."
        )
    )
    parser.add_argument("--profile-evidence-report", type=Path, required=True)
    parser.add_argument("--admission-gate-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--profile-version",
        default="v3_1_competition_profile_proposal",
    )
    parser.add_argument("--min-historical-final-hit-sample-size", type=int, default=30)
    parser.add_argument("--allow-without-production-admission", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> CompetitionProfileProposalOptions:
    return CompetitionProfileProposalOptions(
        profile_version=args.profile_version,
        min_historical_final_hit_sample_size=(args.min_historical_final_hit_sample_size),
        require_production_admission=not args.allow_without_production_admission,
    )


def _load_json(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _report_key(
    summary: Mapping[str, object],
    *,
    proposals: Sequence[CompetitionProfileProposal],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "proposals": [proposal.model_dump(mode="json") for proposal in proposals],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"competition_profile_proposal:{digest}"


def _summary(report: Mapping[str, object]) -> dict[str, object]:
    raw_summary = report.get("summary_json")
    if isinstance(raw_summary, dict):
        return dict(raw_summary)
    return {}


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _required_string(value: object, field_name: str) -> str:
    result = _string(value)
    if result is None:
        raise ValueError(f"missing required profile proposal field: {field_name}")
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _bool(value: object, *, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return fallback


def _float(value: object, *, fallback: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value)
    return fallback
