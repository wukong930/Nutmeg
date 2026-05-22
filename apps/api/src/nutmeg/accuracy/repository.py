from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nutmeg.accuracy.summary import AccuracyEvaluationEvent, build_accuracy_summary
from nutmeg.api.schemas import AccuracySummaryResponse
from nutmeg.domain.accuracy import ModelComparisonStub


class AccuracyRepository(Protocol):
    def list_evaluation_events(self) -> list[AccuracyEvaluationEvent]:
        """Return post-match evaluation events used by Accuracy Summary."""

    def list_model_comparisons(
        self,
        events: list[AccuracyEvaluationEvent],
    ) -> list[ModelComparisonStub]:
        """Return candidate-vs-baseline model comparison reports."""


class AccuracySummaryService:
    def __init__(
        self,
        repository: AccuracyRepository,
        *,
        active_model_version: str,
    ) -> None:
        self.repository = repository
        self.active_model_version = active_model_version

    def build_summary(
        self,
        *,
        model_version: str,
        competition_id: str,
        market: str,
        window: str,
        generated_at_utc: datetime,
    ) -> AccuracySummaryResponse:
        events = self.repository.list_evaluation_events()
        return build_accuracy_summary(
            events,
            model_version=model_version,
            competition_id=competition_id,
            market=market,
            window=window,
            generated_at_utc=generated_at_utc,
            active_model_version=self.active_model_version,
            model_comparisons=self.repository.list_model_comparisons(events),
        )
