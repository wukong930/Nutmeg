"""Domain models for the Nutmeg V2 skeleton."""

from nutmeg.domain.accuracy import (
    ActualMatchResult,
    BacktestRunSchema,
    CalibrationBucket,
    CalibrationBucketKey,
    DateWindow,
    ModelComparisonStub,
    ModelVersionMetrics,
    PredictionEvaluation,
)
from nutmeg.domain.competition import CompetitionConfig, ModelCompetitionConfig
from nutmeg.domain.market import (
    AsianHandicapProbabilities,
    CNHandicapProbabilities,
    CorrectScoreProbability,
    OneXTwoProbabilities,
)
from nutmeg.domain.modeling import GoalLambdaEstimate, PoissonBaselineInput
from nutmeg.domain.parlay import AtomicBet, ParlayEvaluation, ParlayLegSelection
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.score_grid import ScoreGridTailMetrics, ScoreProbability, ScoreProbabilityGrid
from nutmeg.domain.settlement import (
    AsianHandicapSettlement,
    HandicapOneXTwoOutcome,
    OneXTwoOutcome,
)

__all__ = [
    "AsianHandicapProbabilities",
    "AsianHandicapSettlement",
    "AtomicBet",
    "ActualMatchResult",
    "BacktestRunSchema",
    "CNHandicapProbabilities",
    "CalibrationBucket",
    "CalibrationBucketKey",
    "CompetitionConfig",
    "CorrectScoreProbability",
    "DateWindow",
    "GoalLambdaEstimate",
    "HandicapOneXTwoOutcome",
    "ModelComparisonStub",
    "ModelCompetitionConfig",
    "ModelVersionMetrics",
    "OneXTwoOutcome",
    "OneXTwoProbabilities",
    "ParlayEvaluation",
    "ParlayLegSelection",
    "PoissonBaselineInput",
    "PredictionEvaluation",
    "PredictionSnapshot",
    "ScoreGridTailMetrics",
    "ScoreProbability",
    "ScoreProbabilityGrid",
]
