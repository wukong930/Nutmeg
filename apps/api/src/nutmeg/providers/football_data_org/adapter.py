from __future__ import annotations

from collections.abc import Mapping
from json import loads
from os import getenv
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, SecretStr


class FootballDataOrgAdapterError(RuntimeError):
    """Raised when football-data.org cannot be queried safely."""


class FootballDataOrgHttpError(FootballDataOrgAdapterError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class ProviderCapabilityNotSupported(FootballDataOrgAdapterError):
    """Raised for Nutmeg provider capabilities absent from football-data.org."""


class FootballDataOrgConfig(BaseModel):
    api_token: SecretStr | None = None
    api_token_env_var: str = "FOOTBALL_DATA_API_KEY"
    base_url: str = "https://api.football-data.org/v4"
    timeout_seconds: int = Field(default=10, gt=0)

    @property
    def resolved_api_token(self) -> str | None:
        if self.api_token is not None:
            return self.api_token.get_secret_value()
        return getenv(self.api_token_env_var)


class FootballDataTransport(Protocol):
    def get_json(
        self,
        path: str,
        query: dict[str, object],
        require_token: bool,
    ) -> dict[str, object]: ...


class FootballDataOrgAdapter:
    provider_name = "football-data.org"

    def __init__(
        self,
        config: FootballDataOrgConfig | None = None,
        *,
        transport: FootballDataTransport | None = None,
    ) -> None:
        self.config = config or FootballDataOrgConfig()
        self.transport = transport

    def fetch_competitions(self) -> list[dict[str, object]]:
        payload = self._get_json("/competitions", require_token=False)
        return _list_payload(payload, "competitions")

    def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]:
        payload = self._get_json(f"/competitions/{competition_id}")
        seasons: list[dict[str, object]] = []
        current_season = payload.get("currentSeason")
        if isinstance(current_season, dict):
            seasons.append(dict(current_season))
        return seasons

    def fetch_fixtures(self, competition_id: str, season: str) -> list[dict[str, object]]:
        payload = self.fetch_competition_matches(competition_id, season=season)
        return _list_payload(payload, "matches")

    def fetch_competition_matches(
        self,
        competition_id: str,
        *,
        season: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        matchday: int | None = None,
    ) -> dict[str, object]:
        query = _compact_query(
            {
                "season": season,
                "dateFrom": date_from,
                "dateTo": date_to,
                "status": status,
                "matchday": matchday,
            }
        )
        return self._get_json(f"/competitions/{competition_id}/matches", query=query)

    def fetch_fixture_detail(self, fixture_id: str) -> dict[str, object]:
        return self._get_json(f"/matches/{fixture_id}")

    def fetch_competition_teams(
        self,
        competition_id: str,
        *,
        season: str | None = None,
    ) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/competitions/{competition_id}/teams",
            query=_compact_query({"season": season}),
        )
        return _list_payload(payload, "teams")

    def fetch_odds(self, fixture_id: str) -> list[dict[str, object]]:
        raise ProviderCapabilityNotSupported("football-data.org does not expose odds")

    def fetch_lineups(self, fixture_id: str) -> list[dict[str, object]]:
        raise ProviderCapabilityNotSupported("football-data.org does not expose lineups")

    def fetch_injuries(self, team_id: str) -> list[dict[str, object]]:
        raise ProviderCapabilityNotSupported("football-data.org does not expose injuries")

    def fetch_team_stats(self, fixture_id: str) -> list[dict[str, object]]:
        raise ProviderCapabilityNotSupported("football-data.org does not expose team stats")

    def _get_json(
        self,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        require_token: bool = True,
    ) -> dict[str, object]:
        if self.transport is not None:
            payload = self.transport.get_json(path, dict(query or {}), require_token)
            if not isinstance(payload, dict):
                raise FootballDataOrgAdapterError("transport returned non-object JSON")
            return payload

        token = self.config.resolved_api_token
        if require_token and not token:
            raise FootballDataOrgAdapterError(
                "football-data.org API token is required for this request"
            )

        request = Request(
            _url(self.config.base_url, path, query),
            headers=_headers(token),
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload = loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise FootballDataOrgHttpError(exc.code, f"football-data.org HTTP {exc.code}") from exc
        except URLError as exc:
            raise FootballDataOrgAdapterError("football-data.org request failed") from exc

        if not isinstance(payload, dict):
            raise FootballDataOrgAdapterError("football-data.org returned non-object JSON")
        return payload


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    return headers


def _url(base_url: str, path: str, query: Mapping[str, object] | None) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    if not query:
        return f"{normalized_base}{normalized_path}"
    return f"{normalized_base}{normalized_path}?{urlencode(query)}"


def _compact_query(values: Mapping[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _list_payload(payload: Mapping[str, Any], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise FootballDataOrgAdapterError(f"football-data.org response missing {key}")
    return [dict(item) for item in value if isinstance(item, dict)]
