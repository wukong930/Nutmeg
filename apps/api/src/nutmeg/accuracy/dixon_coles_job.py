from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.accuracy.calibration_evidence import (
    CalibrationEvidenceReport,
    PostgresCalibrationEvidenceRepository,
)
from nutmeg.accuracy.dixon_coles_backtest import (
    compare_dixon_coles_training_report_to_baseline,
    persist_dixon_coles_training_backtest,
)
from nutmeg.accuracy.dixon_coles_calibration import (
    DixonColesValidationCalibrationReport,
    build_dixon_coles_validation_calibration_report,
)
from nutmeg.accuracy.postgres_write_repository import PostgresAccuracyWriteRepository
from nutmeg.accuracy.promotion_evidence import (
    ModelPromotionEvidenceBundle,
    PostgresPromotionEvidenceRepository,
)
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.accuracy import ModelVersionMetrics
from nutmeg.model_governance import (
    ModelPromotionInput,
    ModelPromotionReview,
    ModelRollbackPlan,
    ModelRollbackSignal,
    PostgresModelPromotionReviewRepository,
    evaluate_model_promotion,
    evaluate_model_rollback,
)
from nutmeg.modeling.dixon_coles_training import (
    DixonColesTrainingConfig,
    DixonColesTrainingMatch,
    DixonColesTrainingReport,
    build_dixon_coles_training_report,
)

LIST_DIXON_COLES_TRAINING_MATCHES_QUERY = """
SELECT
  f.fixture_id,
  f.competition_id,
  f.kickoff_time_utc,
  f.home_team_id,
  f.away_team_id,
  r.home_goals,
  r.away_goals
FROM fixtures f
JOIN results r
  ON r.fixture_id = f.fixture_id
WHERE f.status = 'finished'
  AND f.kickoff_time_utc < %(as_of_time_utc)s
  AND COALESCE(r.settled_at, f.kickoff_time_utc) <= %(as_of_time_utc)s
  AND (%(competition_id)s::text IS NULL OR f.competition_id = %(competition_id)s::text)
  AND r.home_goals IS NOT NULL
  AND r.away_goals IS NOT NULL
ORDER BY f.kickoff_time_utc ASC, f.fixture_id ASC
LIMIT %(limit)s
"""

UPSERT_DIXON_COLES_JOB_MODEL_VERSION_QUERY = """
INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  feature_version,
  calibration_version,
  metrics_json,
  params_json,
  activated_at
) VALUES (
  %(model_version)s,
  %(model_family)s,
  %(status)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(metrics_json)s::jsonb,
  %(params_json)s::jsonb,
  %(activated_at)s
)
ON CONFLICT (model_version) DO UPDATE SET
  model_family = EXCLUDED.model_family,
  status = EXCLUDED.status,
  feature_version = EXCLUDED.feature_version,
  calibration_version = EXCLUDED.calibration_version,
  metrics_json = model_versions.metrics_json || EXCLUDED.metrics_json,
  params_json = model_versions.params_json || EXCLUDED.params_json
RETURNING model_version
"""

UPSERT_DIXON_COLES_JOB_BASELINE_MODEL_VERSION_QUERY = """
INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  feature_version,
  calibration_version,
  metrics_json,
  params_json,
  activated_at
) VALUES (
  %(model_version)s,
  %(model_family)s,
  %(status)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(metrics_json)s::jsonb,
  %(params_json)s::jsonb,
  %(activated_at)s
)
ON CONFLICT (model_version) DO UPDATE SET
  metrics_json = model_versions.metrics_json || EXCLUDED.metrics_json,
  params_json = model_versions.params_json || EXCLUDED.params_json
RETURNING model_version
"""


class DixonColesTrainingDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read historical result rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute write statements with RETURNING."""


class DixonColesTrainingBacktestJobOptions(BaseModel):
    as_of_time_utc: datetime
    competition_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=2_000, ge=1, le=20_000)
    train_window_days: int = Field(default=365, ge=31, le=3_650)
    validation_window_days: int = Field(default=90, ge=1, le=365)
    time_decay_xi: float = Field(default=0.0065, ge=0.0, le=1.0)
    rho_candidates: tuple[float, ...] = (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10)
    max_goals: int = Field(default=8, ge=1, le=20)
    min_training_matches: int = Field(default=4, ge=1)
    candidate_model_version: str = Field(default="dc-v1.5-candidate", min_length=1)
    candidate_feature_version: str = Field(default="features-m1.2.0", min_length=1)
    candidate_calibration_version: str = Field(
        default="calibration-m1.0.0",
        min_length=1,
    )
    baseline_model_version: str = Field(default="poisson-m1.1.0", min_length=1)
    baseline_log_loss: float = Field(default=1.0, ge=0.0)
    baseline_brier_score: float = Field(default=0.25, ge=0.0)
    baseline_ece: float | None = Field(default=None, ge=0.0)
    baseline_sample_size: int | None = Field(default=None, ge=0)
    baseline_calibration_market_type: str = Field(default="1x2", min_length=1)
    candidate_brier_score: float | None = Field(default=None, ge=0.0)
    candidate_ece: float | None = Field(default=None, ge=0.0)
    promotion_minimum_sample_size: int = Field(default=300, ge=1)
    promotion_evidence_top_k: int = Field(default=20, ge=1, le=500)
    promotion_evidence_handicap_market_types: tuple[str, ...] = (
        "cn_handicap_1x2",
        "european_handicap_1x2",
        "asian_handicap",
    )
    core_market_improvement: bool | None = None
    upset_precision_at_k_delta: float | None = None
    handicap_performance_delta: float | None = None
    parlay_simulation_delta: float | None = None
    low_sample_competition_drift: bool = False
    previous_stable_model_version: str | None = Field(default=None, min_length=1)
    report_uri: str | None = Field(default=None, min_length=1)
    dry_run: bool = True

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)

    def training_config(self) -> DixonColesTrainingConfig:
        return DixonColesTrainingConfig(
            as_of_time_utc=self.normalized_as_of_time_utc,
            model_version=self.candidate_model_version,
            feature_version=self.candidate_feature_version,
            calibration_version=self.candidate_calibration_version,
            train_window_days=self.train_window_days,
            validation_window_days=self.validation_window_days,
            time_decay_xi=self.time_decay_xi,
            rho_candidates=self.rho_candidates,
            max_goals=self.max_goals,
            min_training_matches=self.min_training_matches,
        )

    def baseline_metrics(self, validation_sample_size: int) -> ModelVersionMetrics:
        sample_size = (
            self.baseline_sample_size
            if self.baseline_sample_size is not None
            else validation_sample_size
        )
        return ModelVersionMetrics(
            model_version=self.baseline_model_version,
            sample_size=sample_size,
            log_loss=self.baseline_log_loss,
            brier_score=self.baseline_brier_score,
            ece=self.baseline_ece,
            metrics_json={
                "source": "dixon_coles_training_backtest_job",
                "metric_basis": "baseline_supplied_by_operator",
            },
        )


class DixonColesTrainingBacktestJobResult(BaseModel):
    report: DixonColesTrainingReport
    dry_run: bool
    fixture_count: int = Field(ge=0)
    backtest_run_id: int | None = Field(default=None, gt=0)
    model_comparison_report_id: int | None = Field(default=None, gt=0)
    model_promotion_review_id: int | None = Field(default=None, gt=0)
    model_comparison_decision: str
    model_promotion_decision: str
    model_promotion_next_status: str
    model_promotion_reasons: list[str] = Field(default_factory=list)
    rollback_should_rollback: bool = False
    warnings: list[str] = Field(default_factory=list)
    candidate_model_version: str
    baseline_model_version: str
    selected_rho: float
    train_sample_size: int = Field(ge=0)
    validation_sample_size: int = Field(ge=0)
    candidate_brier_score: float | None = Field(default=None, ge=0.0)
    candidate_ece: float | None = Field(default=None, ge=0.0)
    baseline_ece: float | None = Field(default=None, ge=0.0)
    baseline_calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    promotion_evidence_json: dict[str, object] = Field(default_factory=dict)
    report_uri: str | None = None


class DixonColesPromotionArtifacts(BaseModel):
    review: ModelPromotionReview
    rollback_plan: ModelRollbackPlan
    metrics_json: dict[str, object]


def list_dixon_coles_training_matches(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    as_of_time_utc: datetime,
    competition_id: str | None = None,
    limit: int = 2_000,
) -> list[DixonColesTrainingMatch]:
    rows = database.fetch_all(
        LIST_DIXON_COLES_TRAINING_MATCHES_QUERY,
        {
            "as_of_time_utc": _aware_utc(as_of_time_utc),
            "competition_id": competition_id,
            "limit": max(1, min(limit, 20_000)),
        },
    )
    return [_training_match_from_row(row) for row in rows]


def run_dixon_coles_training_backtest_job(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    options: DixonColesTrainingBacktestJobOptions,
) -> DixonColesTrainingBacktestJobResult:
    matches = list_dixon_coles_training_matches(
        database,
        as_of_time_utc=options.normalized_as_of_time_utc,
        competition_id=options.competition_id,
        limit=options.limit,
    )
    report = build_dixon_coles_training_report(
        matches,
        config=options.training_config(),
    )
    calibration_report = build_dixon_coles_validation_calibration_report(
        matches,
        report=report,
        max_goals=options.max_goals,
    )
    candidate_brier_score = (
        options.candidate_brier_score
        if options.candidate_brier_score is not None
        else calibration_report.brier_score
    )
    candidate_ece = (
        options.candidate_ece
        if options.candidate_ece is not None
        else calibration_report.expected_calibration_error
    )
    candidate_metric_payload = _candidate_metric_payload(
        options=options,
        calibration_report=calibration_report,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
    )
    baseline_calibration_evidence = _baseline_calibration_evidence_report(
        database,
        options=options,
    )
    baseline_metrics = _baseline_metrics_with_calibration_evidence(
        options,
        validation_sample_size=report.validation_sample_size,
        baseline_calibration_evidence=baseline_calibration_evidence,
    )
    promotion_evidence = _model_promotion_evidence_bundle(
        database,
        report=report,
        options=options,
    )
    upset_precision_at_k_delta = _effective_upset_precision_delta(
        options,
        promotion_evidence,
    )
    handicap_performance_delta = _effective_handicap_performance_delta(
        options,
        promotion_evidence,
    )
    parlay_simulation_delta = _effective_parlay_simulation_delta(
        options,
        promotion_evidence,
    )
    comparison = compare_dixon_coles_training_report_to_baseline(
        report,
        baseline_metrics=baseline_metrics,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
    )
    promotion_artifacts = build_dixon_coles_promotion_artifacts(
        report,
        baseline_metrics=baseline_metrics,
        options=options,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
        calibration_report=calibration_report,
        upset_precision_at_k_delta=upset_precision_at_k_delta,
        handicap_performance_delta=handicap_performance_delta,
        parlay_simulation_delta=parlay_simulation_delta,
        promotion_evidence_json=promotion_evidence.metrics_json,
    )
    backtest_run_id: int | None = None
    comparison_report_id: int | None = None
    promotion_review_id: int | None = None

    if not options.dry_run:
        _upsert_job_model_versions(
            database,
            report=report,
            baseline_metrics=baseline_metrics,
            options=options,
            candidate_metric_payload=candidate_metric_payload,
        )
        stored = persist_dixon_coles_training_backtest(
            PostgresAccuracyWriteRepository(database),
            report=report,
            baseline_metrics=baseline_metrics,
            candidate_brier_score=candidate_brier_score,
            candidate_ece=candidate_ece,
            extra_metrics_json=candidate_metric_payload,
            calibration_json=calibration_report.calibration_json,
            report_uri=options.report_uri,
        )
        backtest_run_id = stored.backtest_run.backtest_run_id
        comparison_report_id = stored.model_comparison_report.comparison_report_id
        comparison = stored.model_comparison_report.comparison
        stored_promotion = PostgresModelPromotionReviewRepository(database).save_review(
            review=promotion_artifacts.review,
            sample_size=report.validation_sample_size,
            metrics_json=promotion_artifacts.metrics_json,
            rollback_plan=promotion_artifacts.rollback_plan,
        )
        promotion_review_id = stored_promotion.model_promotion_review_id

    return DixonColesTrainingBacktestJobResult(
        report=report,
        dry_run=options.dry_run,
        fixture_count=len(matches),
        backtest_run_id=backtest_run_id,
        model_comparison_report_id=comparison_report_id,
        model_promotion_review_id=promotion_review_id,
        model_comparison_decision=comparison.decision_stub,
        model_promotion_decision=promotion_artifacts.review.decision,
        model_promotion_next_status=promotion_artifacts.review.next_status,
        model_promotion_reasons=promotion_artifacts.review.reasons,
        rollback_should_rollback=promotion_artifacts.rollback_plan.should_rollback,
        warnings=list(
            dict.fromkeys(
                report.warnings + comparison.reasons + promotion_artifacts.review.reasons
            )
        ),
        candidate_model_version=report.model_version,
        baseline_model_version=baseline_metrics.model_version,
        selected_rho=report.selected_rho,
        train_sample_size=report.train_sample_size,
        validation_sample_size=report.validation_sample_size,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
        baseline_ece=baseline_metrics.ece,
        baseline_calibration_evidence_json=_baseline_calibration_evidence_json(
            baseline_calibration_evidence
        ),
        calibration_evidence_json=calibration_report.calibration_json,
        promotion_evidence_json=promotion_evidence.model_dump(mode="json"),
        report_uri=options.report_uri,
    )


def build_dixon_coles_promotion_artifacts(
    report: DixonColesTrainingReport,
    *,
    baseline_metrics: ModelVersionMetrics,
    options: DixonColesTrainingBacktestJobOptions,
    candidate_brier_score: float | None = None,
    candidate_ece: float | None = None,
    calibration_report: DixonColesValidationCalibrationReport | None = None,
    upset_precision_at_k_delta: float | None = None,
    handicap_performance_delta: float | None = None,
    parlay_simulation_delta: float | None = None,
    promotion_evidence_json: dict[str, object] | None = None,
) -> DixonColesPromotionArtifacts:
    candidate_log_loss = report.validation_negative_weighted_log_likelihood
    log_loss_delta = candidate_log_loss - baseline_metrics.log_loss
    brier_delta = (
        candidate_brier_score - baseline_metrics.brier_score
        if candidate_brier_score is not None
        else 1.0
    )
    calibration_error_delta = (
        candidate_ece - baseline_metrics.ece
        if candidate_ece is not None and baseline_metrics.ece is not None
        else 1.0
    )
    core_market_improvement = (
        options.core_market_improvement
        if options.core_market_improvement is not None
        else log_loss_delta < 0 or brier_delta < 0
    )
    upset_delta = upset_precision_at_k_delta if upset_precision_at_k_delta is not None else 0.0
    handicap_delta = (
        handicap_performance_delta
        if handicap_performance_delta is not None
        else 0.0
    )
    review = evaluate_model_promotion(
        ModelPromotionInput(
            candidate_model_version=report.model_version,
            baseline_model_version=baseline_metrics.model_version,
            sample_size=report.validation_sample_size,
            overall_log_loss_delta=log_loss_delta,
            overall_brier_delta=brier_delta,
            calibration_error_delta=calibration_error_delta,
            core_market_improvement=core_market_improvement,
            upset_precision_at_k_delta=upset_delta,
            handicap_performance_delta=handicap_delta,
            parlay_simulation_delta=parlay_simulation_delta,
            low_sample_competition_drift=options.low_sample_competition_drift,
        ),
        minimum_sample_size=options.promotion_minimum_sample_size,
    )
    blocking_reasons = _promotion_evidence_blockers(
        baseline_metrics=baseline_metrics,
        options=options,
        candidate_brier_score=candidate_brier_score,
        candidate_ece=candidate_ece,
        upset_precision_at_k_delta=upset_precision_at_k_delta,
        handicap_performance_delta=handicap_performance_delta,
    )
    if blocking_reasons:
        review = ModelPromotionReview(
            candidate_model_version=review.candidate_model_version,
            baseline_model_version=review.baseline_model_version,
            decision="keep_experiment",
            next_status="experiment",
            reasons=list(dict.fromkeys(review.reasons + blocking_reasons)),
        )

    rollback_plan = evaluate_model_rollback(
        ModelRollbackSignal(
            active_model_version=baseline_metrics.model_version,
            previous_stable_model_version=(
                options.previous_stable_model_version or baseline_metrics.model_version
            ),
        )
    )
    return DixonColesPromotionArtifacts(
        review=review,
        rollback_plan=rollback_plan,
        metrics_json={
            "source": "dixon_coles_training_backtest_job",
            "candidate_model_version": report.model_version,
            "baseline_model_version": baseline_metrics.model_version,
            "sample_size": report.validation_sample_size,
            "overall_log_loss_delta": log_loss_delta,
            "overall_brier_delta": brier_delta,
            "calibration_error_delta": calibration_error_delta,
            "core_market_improvement": core_market_improvement,
            "upset_precision_at_k_delta": upset_delta,
            "handicap_performance_delta": handicap_delta,
            "parlay_simulation_delta": parlay_simulation_delta,
            "promotion_evidence_json": promotion_evidence_json or {},
            "low_sample_competition_drift": options.low_sample_competition_drift,
            "selected_rho": report.selected_rho,
            "candidate_brier_score": candidate_brier_score,
            "candidate_ece": candidate_ece,
            "candidate_brier_score_source": (
                "operator_supplied"
                if options.candidate_brier_score is not None
                else "dixon_coles_validation_1x2"
            ),
            "candidate_ece_source": (
                "operator_supplied"
                if options.candidate_ece is not None
                else "dixon_coles_validation_1x2"
            ),
            "validation_calibration_sample_size": (
                calibration_report.sample_size if calibration_report is not None else None
            ),
            "validation_calibration_observation_count": (
                calibration_report.observation_count
                if calibration_report is not None
                else None
            ),
            "baseline_log_loss": baseline_metrics.log_loss,
            "baseline_brier_score": baseline_metrics.brier_score,
            "baseline_ece": baseline_metrics.ece,
        },
    )


def _upsert_job_model_versions(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    report: DixonColesTrainingReport,
    baseline_metrics: ModelVersionMetrics,
    options: DixonColesTrainingBacktestJobOptions,
    candidate_metric_payload: dict[str, object],
) -> None:
    _required_row(
        database.fetch_one(
            UPSERT_DIXON_COLES_JOB_MODEL_VERSION_QUERY,
            {
                "model_version": report.model_version,
                "model_family": "dixon_coles",
                "status": "candidate",
                "feature_version": options.candidate_feature_version,
                "calibration_version": options.candidate_calibration_version,
                "metrics_json": _json({**report.metrics_json, **candidate_metric_payload}),
                "params_json": _json(
                    {
                        "selected_rho": report.selected_rho,
                        "time_decay_xi": report.time_decay_xi,
                        "fitted_parameters": report.fitted_parameters.model_dump(
                            mode="json"
                        ),
                    }
                ),
                "activated_at": None,
            },
        )
    )
    _required_row(
        database.fetch_one(
            UPSERT_DIXON_COLES_JOB_BASELINE_MODEL_VERSION_QUERY,
            {
                "model_version": baseline_metrics.model_version,
                "model_family": _baseline_model_family(baseline_metrics.model_version),
                "status": "baseline",
                "feature_version": None,
                "calibration_version": None,
                "metrics_json": _json(baseline_metrics.model_dump(mode="json")),
                "params_json": _json({"source": "operator_supplied_baseline"}),
                "activated_at": None,
            },
        )
    )


def _training_match_from_row(row: DatabaseRow) -> DixonColesTrainingMatch:
    return DixonColesTrainingMatch(
        fixture_id=str(row["fixture_id"]),
        competition_id=str(row["competition_id"]),
        kickoff_time_utc=_aware_utc(row["kickoff_time_utc"]),
        home_team_id=str(row["home_team_id"]),
        away_team_id=str(row["away_team_id"]),
        home_goals=_int(row["home_goals"]),
        away_goals=_int(row["away_goals"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _baseline_model_family(model_version: str) -> str:
    if model_version.startswith("poisson"):
        return "poisson"
    if model_version.startswith("dc") or "dixon" in model_version:
        return "dixon_coles"
    return "baseline"


def _promotion_evidence_blockers(
    *,
    baseline_metrics: ModelVersionMetrics,
    options: DixonColesTrainingBacktestJobOptions,
    candidate_brier_score: float | None,
    candidate_ece: float | None,
    upset_precision_at_k_delta: float | None,
    handicap_performance_delta: float | None,
) -> list[str]:
    reasons: list[str] = []
    if candidate_brier_score is None:
        reasons.append("candidate_brier_unavailable")
    if candidate_ece is None:
        reasons.append("candidate_calibration_unavailable")
    if baseline_metrics.ece is None:
        reasons.append("baseline_calibration_unavailable")
    if upset_precision_at_k_delta is None:
        reasons.append("upset_precision_evidence_unavailable")
    if handicap_performance_delta is None:
        reasons.append("handicap_performance_evidence_unavailable")
    return reasons


def _baseline_calibration_evidence_report(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    options: DixonColesTrainingBacktestJobOptions,
) -> CalibrationEvidenceReport | None:
    if options.baseline_ece is not None:
        return None
    return PostgresCalibrationEvidenceRepository(database).get_model_ece(
        model_version=options.baseline_model_version,
        market_type=options.baseline_calibration_market_type,
        competition_id=options.competition_id,
    )


def _baseline_metrics_with_calibration_evidence(
    options: DixonColesTrainingBacktestJobOptions,
    *,
    validation_sample_size: int,
    baseline_calibration_evidence: CalibrationEvidenceReport | None,
) -> ModelVersionMetrics:
    baseline_metrics = options.baseline_metrics(validation_sample_size)
    if options.baseline_ece is not None or baseline_calibration_evidence is None:
        return baseline_metrics
    return baseline_metrics.model_copy(
        update={
            "ece": baseline_calibration_evidence.expected_calibration_error,
            "metrics_json": {
                **baseline_metrics.metrics_json,
                **baseline_calibration_evidence.metrics_json,
            },
        }
    )


def _baseline_calibration_evidence_json(
    baseline_calibration_evidence: CalibrationEvidenceReport | None,
) -> dict[str, object]:
    if baseline_calibration_evidence is None:
        return {}
    return {
        **baseline_calibration_evidence.model_dump(mode="json"),
        **baseline_calibration_evidence.metrics_json,
    }


def _model_promotion_evidence_bundle(
    database: DixonColesTrainingDatabaseExecutor,
    *,
    report: DixonColesTrainingReport,
    options: DixonColesTrainingBacktestJobOptions,
) -> ModelPromotionEvidenceBundle:
    repository = PostgresPromotionEvidenceRepository(database)
    candidate_upset = repository.get_upset_precision_at_k(
        model_version=report.model_version,
        top_k=options.promotion_evidence_top_k,
        competition_id=options.competition_id,
    )
    baseline_upset = repository.get_upset_precision_at_k(
        model_version=options.baseline_model_version,
        top_k=options.promotion_evidence_top_k,
        competition_id=options.competition_id,
    )
    candidate_handicap = repository.get_handicap_performance(
        model_version=report.model_version,
        market_types=options.promotion_evidence_handicap_market_types,
        competition_id=options.competition_id,
    )
    baseline_handicap = repository.get_handicap_performance(
        model_version=options.baseline_model_version,
        market_types=options.promotion_evidence_handicap_market_types,
        competition_id=options.competition_id,
    )
    return ModelPromotionEvidenceBundle(
        model_version=report.model_version,
        candidate_upset_precision=candidate_upset,
        baseline_upset_precision=baseline_upset,
        candidate_handicap_performance=candidate_handicap,
        baseline_handicap_performance=baseline_handicap,
        candidate_parlay_simulation=repository.get_parlay_simulation(
            model_version=report.model_version,
            competition_id=options.competition_id,
        ),
        baseline_parlay_simulation=repository.get_parlay_simulation(
            model_version=options.baseline_model_version,
            competition_id=options.competition_id,
        ),
    )


def _effective_upset_precision_delta(
    options: DixonColesTrainingBacktestJobOptions,
    promotion_evidence: ModelPromotionEvidenceBundle,
) -> float | None:
    if options.upset_precision_at_k_delta is not None:
        return options.upset_precision_at_k_delta
    candidate = promotion_evidence.candidate_upset_precision
    baseline = promotion_evidence.baseline_upset_precision
    if (
        candidate is None
        or baseline is None
        or candidate.precision_at_k is None
        or baseline.precision_at_k is None
    ):
        return None
    return candidate.precision_at_k - baseline.precision_at_k


def _effective_handicap_performance_delta(
    options: DixonColesTrainingBacktestJobOptions,
    promotion_evidence: ModelPromotionEvidenceBundle,
) -> float | None:
    if options.handicap_performance_delta is not None:
        return options.handicap_performance_delta
    candidate = promotion_evidence.candidate_handicap_performance
    baseline = promotion_evidence.baseline_handicap_performance
    if (
        candidate is None
        or baseline is None
        or candidate.accuracy is None
        or baseline.accuracy is None
    ):
        return None
    return candidate.accuracy - baseline.accuracy


def _effective_parlay_simulation_delta(
    options: DixonColesTrainingBacktestJobOptions,
    promotion_evidence: ModelPromotionEvidenceBundle,
) -> float | None:
    if options.parlay_simulation_delta is not None:
        return options.parlay_simulation_delta
    candidate = promotion_evidence.candidate_parlay_simulation
    baseline = promotion_evidence.baseline_parlay_simulation
    if candidate is None or baseline is None or candidate.roi is None or baseline.roi is None:
        return None
    return candidate.roi - baseline.roi


def _candidate_metric_payload(
    *,
    options: DixonColesTrainingBacktestJobOptions,
    calibration_report: DixonColesValidationCalibrationReport,
    candidate_brier_score: float | None,
    candidate_ece: float | None,
) -> dict[str, object]:
    return {
        **calibration_report.metrics_json,
        "candidate_brier_score": candidate_brier_score,
        "candidate_ece": candidate_ece,
        "candidate_brier_score_source": (
            "operator_supplied"
            if options.candidate_brier_score is not None
            else "dixon_coles_validation_1x2"
        ),
        "candidate_ece_source": (
            "operator_supplied"
            if options.candidate_ece is not None
            else "dixon_coles_validation_1x2"
        ),
    }


def _aware_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _json(value: Mapping[str, object] | Sequence[object] | object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"))
