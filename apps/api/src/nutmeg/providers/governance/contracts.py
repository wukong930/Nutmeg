from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

ProviderCapability = Literal[
    "competitions",
    "seasons",
    "fixtures",
    "fixture_detail",
    "results",
    "odds",
    "lineups",
    "injuries",
    "team_stats",
]

ProviderAuthorizationStatus = Literal[
    "active",
    "pending_review",
    "research_only",
    "blocked",
    "expired",
]

ProviderEntityType = Literal["competition", "team", "player", "fixture", "season"]


class ProviderAdapter(Protocol):
    provider_name: str

    def fetch_competitions(self) -> list[dict[str, object]]: ...

    def fetch_seasons(self, competition_id: str) -> list[dict[str, object]]: ...

    def fetch_fixtures(self, competition_id: str, season: str) -> list[dict[str, object]]: ...

    def fetch_fixture_detail(self, fixture_id: str) -> dict[str, object]: ...

    def fetch_odds(self, fixture_id: str) -> list[dict[str, object]]: ...

    def fetch_lineups(self, fixture_id: str) -> list[dict[str, object]]: ...

    def fetch_injuries(self, team_id: str) -> list[dict[str, object]]: ...

    def fetch_team_stats(self, fixture_id: str) -> list[dict[str, object]]: ...


class ProviderAuthorizationRecord(BaseModel):
    provider_name: str
    status: ProviderAuthorizationStatus
    capabilities: tuple[ProviderCapability, ...] = Field(default_factory=tuple)
    terms_checked_at_utc: datetime | None = None
    commercial_use_allowed: bool = False
    retention_allowed: bool = False
    allowed_use: str = "research_and_development"
    rate_limit: str | None = None
    historical_data_allowed: bool = False
    redistribution_allowed: bool = False
    terms_url: str | None = None
    last_reviewed_at: datetime | None = None
    next_review_due_at: datetime | None = None
    owner: str = "nutmeg-ops"
    api_key_env_var: str | None = None
    notes: str = ""

    @field_validator("api_key_env_var")
    @classmethod
    def validate_api_key_reference(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.isidentifier() or value.upper() != value:
            raise ValueError("api_key_env_var must be an uppercase environment variable name")
        forbidden_fragments = ("SECRET", "TOKEN_VALUE", "PASSWORD_VALUE", "KEY_VALUE")
        if any(fragment in value for fragment in forbidden_fragments):
            raise ValueError("api_key_env_var must reference a variable name, not a secret value")
        return value

    @property
    def is_usable_for_production(self) -> bool:
        return (
            self.status == "active"
            and self.commercial_use_allowed
            and self.retention_allowed
        )

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


class ProviderEntityMapping(BaseModel):
    provider: str
    entity_type: ProviderEntityType
    provider_entity_id: str
    canonical_entity_id: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ProviderRegistry:
    def __init__(self, authorizations: Sequence[ProviderAuthorizationRecord] = ()) -> None:
        self._authorizations = {
            authorization.provider_name: authorization for authorization in authorizations
        }
        self._adapters: dict[str, ProviderAdapter] = {}

    def register_adapter(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.provider_name] = adapter

    def authorization_for(self, provider_name: str) -> ProviderAuthorizationRecord | None:
        return self._authorizations.get(provider_name)

    def adapter_for(
        self,
        provider_name: str,
        *,
        required_capability: ProviderCapability | None = None,
    ) -> ProviderAdapter:
        authorization = self.authorization_for(provider_name)
        if authorization is None:
            raise ValueError(f"provider authorization missing: {provider_name}")
        if not authorization.is_usable_for_production:
            raise ValueError(f"provider is not production-authorized: {provider_name}")
        if required_capability is not None and not authorization.supports(required_capability):
            raise ValueError(
                f"provider {provider_name} does not support {required_capability}"
            )
        try:
            return self._adapters[provider_name]
        except KeyError as exc:
            raise ValueError(f"provider adapter missing: {provider_name}") from exc

    def list_authorizations(self) -> list[ProviderAuthorizationRecord]:
        return sorted(
            self._authorizations.values(),
            key=lambda authorization: authorization.provider_name,
        )
