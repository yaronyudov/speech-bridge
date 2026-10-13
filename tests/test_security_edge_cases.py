"""Tests for authentication and rate limiting security layer."""

from unittest.mock import MagicMock

import pytest

from speech_engine.config import Settings
from speech_engine.core.exceptions import AuthError, RateLimitError
from speech_engine.core.security import (
    _enforce_rate_limit,
    _identity_from_headers,
    _validate_api_key,
    authorize_websocket,
    check_ws_rate_limit,
    rate_limit,
    require_api_key,
    reset_rate_limiter,
    security_dependencies,
)


def test_validate_api_key_disabled():
    settings = Settings(ENABLE_AUTH=False)
    # Should not raise even with None or empty
    _validate_api_key(None, settings)
    _validate_api_key("bad-key", settings)


def test_validate_api_key_fail_closed_when_no_keys_configured():
    settings = Settings(ENABLE_AUTH=True, API_KEYS=[])
    with pytest.raises(AuthError) as exc_info:
        _validate_api_key("any-key", settings)
    assert "no API keys are configured" in str(exc_info.value)


def test_validate_api_key_success_and_failure():
    settings = Settings(ENABLE_AUTH=True, API_KEYS=["secret-key-1", "secret-key-2"])

    # Valid keys
    _validate_api_key("secret-key-1", settings)
    _validate_api_key("secret-key-2", settings)

    # Invalid / missing keys
    with pytest.raises(AuthError):
        _validate_api_key("wrong-key", settings)

    with pytest.raises(AuthError):
        _validate_api_key(None, settings)

    with pytest.raises(AuthError):
        _validate_api_key("", settings)


def test_authorize_websocket(configure_env):
    configure_env(ENABLE_AUTH="true", API_KEYS="valid-ws-key")

    # Header match
    ws_with_header = MagicMock()
    ws_with_header.headers = {"X-API-Key": "valid-ws-key"}
    ws_with_header.query_params = {}
    authorize_websocket(ws_with_header)

    # Query param match
    ws_with_query = MagicMock()
    ws_with_query.headers = {}
    ws_with_query.query_params = {"api_key": "valid-ws-key"}
    authorize_websocket(ws_with_query)

    # Neither match -> raises AuthError
    ws_bad = MagicMock()
    ws_bad.headers = {}
    ws_bad.query_params = {"api_key": "bad"}
    with pytest.raises(AuthError):
        authorize_websocket(ws_bad)


def test_identity_from_headers():
    assert _identity_from_headers("my-key", "127.0.0.1") == "key:my-key"
    assert _identity_from_headers(None, "192.168.1.1") == "ip:192.168.1.1"
    assert _identity_from_headers(None, None) == "ip:unknown"


@pytest.mark.asyncio
async def test_require_api_key_dependency(configure_env):
    configure_env(ENABLE_AUTH="true", API_KEYS="my-token")

    await require_api_key(api_key="my-token")

    with pytest.raises(AuthError):
        await require_api_key(api_key="wrong")


def test_rate_limiting_enforcement(configure_env):
    configure_env(ENABLE_RATE_LIMIT="true", RATE_LIMIT="3/minute")
    reset_rate_limiter()

    identity = "test-user-123"
    _enforce_rate_limit(identity)
    _enforce_rate_limit(identity)
    _enforce_rate_limit(identity)

    # 4th hit exceeds 3/minute limit
    with pytest.raises(RateLimitError):
        _enforce_rate_limit(identity)


@pytest.mark.asyncio
async def test_rate_limit_request_dependency(configure_env):
    configure_env(ENABLE_RATE_LIMIT="true", RATE_LIMIT="2/minute")
    reset_rate_limiter()

    req = MagicMock()
    req.headers = {"X-API-Key": "key-abc"}
    req.client.host = "10.0.0.1"

    await rate_limit(req)
    await rate_limit(req)

    with pytest.raises(RateLimitError):
        await rate_limit(req)


def test_check_ws_rate_limit(configure_env):
    configure_env(ENABLE_RATE_LIMIT="true", RATE_LIMIT="1/minute")
    reset_rate_limiter()

    ws = MagicMock()
    ws.headers = {}
    ws.client.host = "10.0.0.5"

    check_ws_rate_limit(ws)
    with pytest.raises(RateLimitError):
        check_ws_rate_limit(ws)


def test_security_dependencies_list():
    deps = security_dependencies()
    assert len(deps) == 2
