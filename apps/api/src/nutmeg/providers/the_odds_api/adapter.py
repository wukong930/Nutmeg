from __future__ import annotations

from collections.abc import Mapping
from json import loads
from os import getenv
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, SecretStr


class TheOddsApiAdapterError(RuntimeError):
    """Raised when The Odds API cannot be queried safely."""


class TheOddsApiHttpError(TheOddsApiAdapterError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class TheOddsApiConfig(BaseModel):
    api_key: SecretStr | None = None
    api_key_env_var: str = "THE_ODDS_API_KEY"
    base_url: str = "https://api.the-odds-api.com/v4"
    timeout_seconds: int = Field(default=10, gt=0)

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        return getenv(self.api_key_env_var)


class TheOddsApiTransport(Protocol):
    def get_json(self, path: str, query: dict[str, object]) -> object:
        """Return parsed JSON for a fake or real transport."""


class TheOddsApiAdapter:
    provider_name = "the-odds-api"

    def __init__(
        self,
        config: TheOddsApiConfig | None = None,
        *,
        transport: TheOddsApiTransport | None = None,
    ) -> None:
        self.config = config or TheOddsApiConfig()
        self.transport = transport

    def fetch_sports(self, *, include_all: bool = False) -> list[dict[str, object]]:
        payload = self._get_json("/sports", {"all": str(include_all).lower()})
        if not isinstance(payload, list):
            raise TheOddsApiAdapterError("The Odds API sports response must be a list")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def fetch_sport_odds(
        self,
        *,
        sport_key: str,
        regions: str,
        markets: str = "h2h,spreads",
        odds_format: str = "decimal",
        date_format: str = "iso",
        event_ids: str | None = None,
        bookmakers: str | None = None,
    ) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/sports/{sport_key}/odds",
            _compact_query(
                {
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": odds_format,
                    "dateFormat": date_format,
                    "eventIds": event_ids,
                    "bookmakers": bookmakers,
                }
            ),
        )
        if not isinstance(payload, list):
            raise TheOddsApiAdapterError("The Odds API odds response must be a list")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def fetch_sport_events(
        self,
        *,
        sport_key: str,
        date_format: str = "iso",
        event_ids: str | None = None,
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
    ) -> list[dict[str, object]]:
        payload = self._get_json(
            f"/sports/{sport_key}/events",
            _compact_query(
                {
                    "dateFormat": date_format,
                    "eventIds": event_ids,
                    "commenceTimeFrom": commence_time_from,
                    "commenceTimeTo": commence_time_to,
                }
            ),
        )
        if not isinstance(payload, list):
            raise TheOddsApiAdapterError("The Odds API events response must be a list")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def fetch_event_odds(
        self,
        *,
        sport_key: str,
        event_id: str,
        regions: str,
        markets: str = "h2h,spreads",
        odds_format: str = "decimal",
        date_format: str = "iso",
        bookmakers: str | None = None,
    ) -> dict[str, object]:
        payload = self._get_json(
            f"/sports/{sport_key}/events/{event_id}/odds",
            _compact_query(
                {
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": odds_format,
                    "dateFormat": date_format,
                    "bookmakers": bookmakers,
                }
            ),
        )
        if not isinstance(payload, dict):
            raise TheOddsApiAdapterError("The Odds API event odds response must be an object")
        return payload

    def _get_json(self, path: str, query: Mapping[str, object] | None = None) -> object:
        request_query = dict(query or {})
        api_key = self.config.resolved_api_key
        if not api_key:
            raise TheOddsApiAdapterError("The Odds API key is required for this request")
        request_query["apiKey"] = api_key

        if self.transport is not None:
            safe_query = dict(request_query)
            safe_query["apiKey"] = "__redacted__"
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
            raise TheOddsApiHttpError(exc.code, f"The Odds API HTTP {exc.code}") from exc
        except URLError as exc:
            raise TheOddsApiAdapterError("The Odds API request failed") from exc


def _url(base_url: str, path: str, query: Mapping[str, object]) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}?{urlencode(query)}"


def _compact_query(values: Mapping[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}
