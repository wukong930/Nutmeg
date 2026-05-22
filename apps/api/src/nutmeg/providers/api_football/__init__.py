from nutmeg.providers.api_football.adapter import (
    ApiFootballAdapter,
    ApiFootballAdapterError,
    ApiFootballConfig,
    ApiFootballHttpError,
    ApiFootballPlanLimitError,
)
from nutmeg.providers.api_football.discovery import (
    ApiFootballCompetitionDiscoveryCandidate,
    ApiFootballCompetitionDiscoveryResult,
    ApiFootballSeasonDiscoveryCandidate,
    discover_api_football_competition_season,
)

__all__ = [
    "ApiFootballAdapter",
    "ApiFootballAdapterError",
    "ApiFootballCompetitionDiscoveryCandidate",
    "ApiFootballCompetitionDiscoveryResult",
    "ApiFootballConfig",
    "ApiFootballHttpError",
    "ApiFootballPlanLimitError",
    "ApiFootballSeasonDiscoveryCandidate",
    "discover_api_football_competition_season",
]
