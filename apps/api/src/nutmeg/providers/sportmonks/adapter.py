from __future__ import annotations

from collections.abc import Mapping
from json import loads
from os import getenv
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, SecretStr


class SportMonksAdapterError(RuntimeError):
    """Raised when SportMonks cannot be queried safely."""


class SportMonksHttpError(SportMonksAdapterError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class SportMonksConfig(BaseModel):
    api_token: SecretStr | None = None
    api_token_env_var: str = "SPORTMONKS_API_KEY"
    base_url: str = "https://api.sportmonks.com/v3"
    timeout_seconds: int = Field(default=10, gt=0)

    @property
    def resolved_api_token(self) -> str | None:
        if self.api_token is not None:
            return self.api_token.get_secret_value()
        return getenv(self.api_token_env_var)


class SportMonksTransport(Protocol):
    def get_json(self, path: str, query: dict[str, object]) -> object:
        """Return parsed JSON for tests or controlled local fixtures."""


class SportMonksAdapter:
    provider_name = "sportmonks"

    def __init__(
        self,
        config: SportMonksConfig | None = None,
        *,
        transport: SportMonksTransport | None = None,
    ) -> None:
        self.config = config or SportMonksConfig()
        self.transport = transport

    def fetch_competitions(
        self,
        *,
        include_country: bool = False,
    ) -> list[dict[str, object]]:
        query = {"include": "country"} if include_country else None
        payload = self._get_json("/football/leagues", query)
        return _list_payload(payload, "data")

    def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/football/leagues/{competition_id}",
            {"include": "seasons"},
        )
        league = _object_payload(payload, "data")
        seasons = league.get("seasons")
        if isinstance(seasons, dict):
            return _list_payload(seasons, "data")
        if isinstance(seasons, list):
            return [dict(item) for item in seasons if isinstance(item, dict)]
        return []

    def fetch_fixtures(self, competition_id: str, season: str) -> list[dict[str, object]]:
        payload = self._get_json(
            "/football/fixtures",
            {
                "include": "participants",
                "filters": f"fixtureLeagues:{competition_id};fixtureSeasons:{season}",
            },
        )
        return _list_payload(payload, "data")

    def fetch_fixture_detail(self, fixture_id: str) -> dict[str, object]:
        payload = self._get_json(f"/football/fixtures/{fixture_id}")
        return _object_payload(payload, "data")

    def fetch_odds(self, fixture_id: str) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/football/fixtures/{fixture_id}",
            {"include": "odds"},
        )
        fixture = _object_payload(payload, "data")
        odds = fixture.get("odds")
        if isinstance(odds, dict):
            return _list_payload(odds, "data")
        if isinstance(odds, list):
            return [dict(item) for item in odds if isinstance(item, dict)]
        return []

    def fetch_lineups(self, fixture_id: str) -> list[dict[str, object]]:
        payload = self.fetch_lineups_payload(fixture_id)
        return _list_payload(payload, "data")

    def fetch_lineups_payload(self, fixture_id: str) -> dict[str, object]:
        return _response_object(self._get_json(f"/football/fixtures/{fixture_id}/lineups"))

    def fetch_injuries(self, team_id: str) -> list[dict[str, object]]:
        payload = self.fetch_injuries_payload(team_id)
        return _list_payload(payload, "data")

    def fetch_injuries_payload(self, team_id: str) -> dict[str, object]:
        return _response_object(
            self._get_json(
                "/football/injuries",
                {"filters": f"injuryTeam:{team_id}"},
            )
        )

    def fetch_team_stats(self, fixture_id: str) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/football/fixtures/{fixture_id}",
            {"include": "statistics"},
        )
        fixture = _object_payload(payload, "data")
        statistics = fixture.get("statistics")
        if isinstance(statistics, dict):
            return _list_payload(statistics, "data")
        if isinstance(statistics, list):
            return [dict(item) for item in statistics if isinstance(item, dict)]
        return []

    def _get_json(
        self,
        path: str,
        query: Mapping[str, object] | None = None,
    ) -> object:
        request_query = dict(query or {})
        api_token = self.config.resolved_api_token
        if not api_token:
            raise SportMonksAdapterError("SportMonks API token is required for this request")
        request_query["api_token"] = api_token

        if self.transport is not None:
            safe_query = dict(request_query)
            safe_query["api_token"] = "__redacted__"
            return self.transport.get_json(path, safe_query)

        request = Request(
            _url(self.config.base_url, path, request_query),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise SportMonksHttpError(exc.code, f"SportMonks HTTP {exc.code}") from exc
        except URLError as exc:
            raise SportMonksAdapterError("SportMonks request failed") from exc


def _url(base_url: str, path: str, query: Mapping[str, object]) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}?{urlencode(query)}"


def _list_payload(payload: object, key: str) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise SportMonksAdapterError("SportMonks response must be an object")
    value = payload.get(key)
    if not isinstance(value, list):
        raise SportMonksAdapterError(f"SportMonks response missing {key} list")
    return [dict(item) for item in value if isinstance(item, dict)]


def _object_payload(payload: object, key: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise SportMonksAdapterError("SportMonks response must be an object")
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SportMonksAdapterError(f"SportMonks response missing {key} object")
    return dict(value)


def _response_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise SportMonksAdapterError("SportMonks response must be an object")
    return dict(payload)
