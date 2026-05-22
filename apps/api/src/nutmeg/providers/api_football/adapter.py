from __future__ import annotations

from collections.abc import Mapping
from json import loads
from os import getenv
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, SecretStr


class ApiFootballAdapterError(RuntimeError):
    """Raised when API-Football cannot be queried safely."""


class ApiFootballHttpError(ApiFootballAdapterError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class ApiFootballPlanLimitError(ApiFootballAdapterError):
    def __init__(self, errors: Mapping[str, object]) -> None:
        self.errors = dict(errors)
        super().__init__("API-Football plan does not allow this request")


class ApiFootballConfig(BaseModel):
    api_key: SecretStr | None = None
    api_key_env_var: str = "API_FOOTBALL_API_KEY"
    base_url: str = "https://v3.football.api-sports.io"
    timeout_seconds: int = Field(default=10, gt=0)

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        return getenv(self.api_key_env_var)


class ApiFootballTransport(Protocol):
    def get_json(self, path: str, query: dict[str, object]) -> object:
        """Return parsed JSON for tests or controlled local fixtures."""


class ApiFootballAdapter:
    provider_name = "api-football"

    def __init__(
        self,
        config: ApiFootballConfig | None = None,
        *,
        transport: ApiFootballTransport | None = None,
    ) -> None:
        self.config = config or ApiFootballConfig()
        self.transport = transport

    def fetch_leagues(
        self,
        *,
        country: str | None = None,
        season: str | None = None,
        search: str | None = None,
        current: bool | None = None,
    ) -> list[dict[str, object]]:
        query: dict[str, object] = {}
        if country:
            query["country"] = country
        if season:
            query["season"] = season
        if search:
            query["search"] = search
        if current is not None:
            query["current"] = "true" if current else "false"
        payload = self._get_json("/leagues", query)
        return _response_list(payload)

    def fetch_fixtures(self, *, league_id: str, season: str) -> list[dict[str, object]]:
        payload = self._get_json(
            "/fixtures",
            {
                "league": league_id,
                "season": season,
            },
        )
        return _response_list(payload)

    def _get_json(
        self,
        path: str,
        query: Mapping[str, object] | None = None,
    ) -> object:
        api_key = self.config.resolved_api_key
        if not api_key:
            raise ApiFootballAdapterError("API-Football key is required for this request")
        request_query = dict(query or {})

        if self.transport is not None:
            return self.transport.get_json(path, request_query)

        request = Request(
            _url(self.config.base_url, path, request_query),
            headers={
                "Accept": "application/json",
                "x-apisports-key": api_key,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ApiFootballHttpError(exc.code, f"API-Football HTTP {exc.code}") from exc
        except URLError as exc:
            raise ApiFootballAdapterError("API-Football request failed") from exc


def _url(base_url: str, path: str, query: Mapping[str, object]) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    encoded_query = urlencode(query)
    return f"{normalized_base}{normalized_path}?{encoded_query}" if encoded_query else (
        f"{normalized_base}{normalized_path}"
    )


def _response_list(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise ApiFootballAdapterError("API-Football response must be an object")
    errors = payload.get("errors")
    if isinstance(errors, dict) and errors:
        if _contains_plan_limit_error(errors):
            raise ApiFootballPlanLimitError(errors)
        raise ApiFootballAdapterError("API-Football response contains errors")
    if isinstance(errors, list) and errors:
        raise ApiFootballAdapterError("API-Football response contains errors")
    value = payload.get("response")
    if not isinstance(value, list):
        raise ApiFootballAdapterError("API-Football response missing response list")
    return [dict(item) for item in value if isinstance(item, dict)]


def _contains_plan_limit_error(errors: Mapping[str, object]) -> bool:
    return any("plan" in str(key).lower() for key in errors) or any(
        "free plan" in str(value).lower() or "free plans" in str(value).lower()
        for value in errors.values()
    )
