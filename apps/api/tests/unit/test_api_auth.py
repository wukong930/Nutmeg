from __future__ import annotations

import pytest
from fastapi import HTTPException

from nutmeg.api.auth import require_admin_token
from nutmeg.config import Settings


def test_require_admin_token_rejects_unconfigured_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(Settings(admin_api_token=None), "provided")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "admin token is not configured"


def test_require_admin_token_rejects_missing_or_invalid_token() -> None:
    settings = Settings(admin_api_token="secret")

    with pytest.raises(HTTPException) as missing_exc:
        require_admin_token(settings, None)
    with pytest.raises(HTTPException) as invalid_exc:
        require_admin_token(settings, "wrong")

    assert missing_exc.value.status_code == 403
    assert invalid_exc.value.status_code == 403
    assert missing_exc.value.detail == "admin token required"
    assert invalid_exc.value.detail == "admin token required"


def test_require_admin_token_accepts_matching_token() -> None:
    require_admin_token(Settings(admin_api_token="secret"), "secret")
