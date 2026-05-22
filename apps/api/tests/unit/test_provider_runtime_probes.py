from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.providers.api_football.adapter import (
    ApiFootballHttpError,
    ApiFootballPlanLimitError,
)
from nutmeg.providers.football_data_org.adapter import FootballDataOrgHttpError
from nutmeg.providers.live_probes import build_provider_runtime_probe_response
from nutmeg.providers.the_odds_api.adapter import TheOddsApiHttpError


def test_provider_runtime_probes_report_key_presence_without_secrets() -> None:
    response = build_provider_runtime_probe_response(
        Settings(
            football_data_api_key="football-secret",
            the_odds_api_key="odds-secret",
            sportmonks_api_key="sportmonks-secret",
            api_football_api_key="api-football-secret",
        ),
        generated_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
    )

    payload = response.model_dump_json()
    assert "football-secret" not in payload
    assert "odds-secret" not in payload
    assert "sportmonks-secret" not in payload
    assert "api-football-secret" not in payload
    assert response.live_probe is False

    records = {item.provider_name: item for item in response.items}
    assert records["football-data.org"].status == "key_configured"
    assert records["football-data.org"].safe_to_call_real_provider is True
    assert records["the-odds-api"].status == "key_configured"
    assert records["sportmonks"].status == "key_configured"
    assert records["api-football"].status == "key_configured"
    assert records["api-football"].safe_to_call_real_provider is True


def test_provider_runtime_probes_live_mode_uses_supported_provider_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.FootballDataOrgAdapter.fetch_competition_teams",
        lambda self, competition_id, *, season=None: [{"id": 57}, {"id": 64}],
    )
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.TheOddsApiAdapter.fetch_sports",
        lambda self, *, include_all=False: [
            {"key": "soccer_epl"},
            {"key": "basketball_nba"},
        ],
    )
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.SportMonksAdapter.fetch_competitions",
        lambda self: [{"id": 8}, {"id": 271}],
    )
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.ApiFootballAdapter.fetch_leagues",
        lambda self, **kwargs: [{"league": {"id": 39}}],
    )

    response = build_provider_runtime_probe_response(
        Settings(
            football_data_api_key="football-secret",
            the_odds_api_key="odds-secret",
            sportmonks_api_key="sportmonks-secret",
            api_football_api_key="api-football-secret",
        ),
        live=True,
        generated_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
    )

    records = {item.provider_name: item for item in response.items}
    assert records["football-data.org"].status == "ok"
    assert records["football-data.org"].observed_count == 2
    assert records["the-odds-api"].status == "ok"
    assert records["the-odds-api"].metadata["soccer_epl_available"] is True
    assert records["sportmonks"].status == "ok"
    assert records["sportmonks"].observed_count == 2
    assert records["api-football"].status == "ok"
    assert records["api-football"].observed_count == 1


def test_provider_runtime_probes_classify_live_http_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_football_limited(
        self: object,
        competition_id: str,
        *,
        season: str | None = None,
    ) -> list[dict[str, object]]:
        _ = (self, competition_id, season)
        raise FootballDataOrgHttpError(403, "forbidden")

    def raise_odds_auth(
        self: object,
        *,
        include_all: bool = False,
    ) -> list[dict[str, object]]:
        _ = (self, include_all)
        raise TheOddsApiHttpError(401, "unauthorized")

    def raise_api_football_rate_limited(
        self: object,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        _ = (self, kwargs)
        raise ApiFootballHttpError(429, "rate limited")

    monkeypatch.setattr(
        "nutmeg.providers.live_probes.FootballDataOrgAdapter.fetch_competition_teams",
        raise_football_limited,
    )
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.TheOddsApiAdapter.fetch_sports",
        raise_odds_auth,
    )
    monkeypatch.setattr(
        "nutmeg.providers.live_probes.ApiFootballAdapter.fetch_leagues",
        raise_api_football_rate_limited,
    )

    response = build_provider_runtime_probe_response(
        Settings(
            football_data_api_key="football-secret",
            the_odds_api_key="odds-secret",
            api_football_api_key="api-football-secret",
        ),
        live=True,
        generated_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
    )

    records = {item.provider_name: item for item in response.items}
    assert records["football-data.org"].status == "limited"
    assert records["football-data.org"].metadata["http_status_code"] == 403
    assert records["the-odds-api"].status == "auth_failed"
    assert records["the-odds-api"].metadata["http_status_code"] == 401
    assert records["api-football"].status == "rate_limited"
    assert records["api-football"].metadata["http_status_code"] == 429
    assert records["sportmonks"].status == "not_configured"


def test_provider_runtime_probes_classify_api_football_plan_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_api_football_plan_limited(
        self: object,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        _ = (self, kwargs)
        raise ApiFootballPlanLimitError(
            {"plan": "Free plans do not have access to this season."}
        )

    monkeypatch.setattr(
        "nutmeg.providers.live_probes.ApiFootballAdapter.fetch_leagues",
        raise_api_football_plan_limited,
    )

    response = build_provider_runtime_probe_response(
        Settings(api_football_api_key="api-football-secret"),
        live=True,
        generated_at_utc=datetime(2026, 5, 7, tzinfo=UTC),
    )

    records = {item.provider_name: item for item in response.items}
    assert records["api-football"].status == "limited"
    assert records["api-football"].metadata["provider_errors"] == {
        "plan": "Free plans do not have access to this season."
    }
