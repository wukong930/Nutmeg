from __future__ import annotations

from hmac import compare_digest

from fastapi import HTTPException

from nutmeg.config import Settings


def require_admin_token(settings: Settings, provided_token: str | None) -> None:
    if not settings.admin_api_token:
        raise HTTPException(status_code=403, detail="admin token is not configured")
    if provided_token is None or not compare_digest(provided_token, settings.admin_api_token):
        raise HTTPException(status_code=403, detail="admin token required")
