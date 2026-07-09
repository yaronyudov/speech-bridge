"""API authentication and rate limiting.

* **Auth** — when ``ENABLE_AUTH`` is true, requests must carry a valid key
  in the ``X-API-Key`` header (``API_KEY_HEADER``); WebSocket clients may
  also pass ``?api_key=``. Keys are compared in constant time. Disabled by
  default so local development is frictionless.
* **Rate limiting** — a process-wide moving-window limiter (the ``limits``
  library) keyed by API key, falling back to client IP. The same limiter
  backs both the REST dependency and the WebSocket handshake so a single
  ``RATE_LIMIT`` applies uniformly. Degrades to a no-op (with a startup
  warning) if ``limits`` is not installed.

Both features are optional and add no latency when disabled.
"""

import hmac
import logging
from collections.abc import Callable

from fastapi import Depends, Request, WebSocket
from fastapi.security import APIKeyHeader

from speech_engine.config import Settings, get_settings
from speech_engine.core.exceptions import AuthError, RateLimitError

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def _validate_api_key(header_value: str | None, settings: Settings) -> None:
    """Validate an API key or raise :class:`AuthError`. No-op when disabled."""
    if not settings.ENABLE_AUTH:
        return
    if not settings.API_KEYS:
        # Auth requested but no keys configured -> fail closed.
        raise AuthError(
            "Authentication is enabled but no API keys are configured (set API_KEYS)."
        )
    if not header_value or not any(
        hmac.compare_digest(header_value, key) for key in settings.API_KEYS
    ):
        raise AuthError("Invalid or missing API key.")


_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Depends(_api_key_scheme),
) -> None:
    """REST dependency enforcing API-key auth when enabled."""
    _validate_api_key(api_key, get_settings())


def authorize_websocket(websocket: WebSocket) -> None:
    """Enforce API-key auth for a WebSocket handshake when enabled."""
    settings = get_settings()
    key = websocket.headers.get(settings.API_KEY_HEADER) or (
        websocket.query_params.get("api_key")
    )
    _validate_api_key(key, settings)


def _identity_from_headers(key: str | None, host: str | None) -> str:
    if key:
        return f"key:{key}"
    return f"ip:{host}" if host else "ip:unknown"


# --------------------------------------------------------------------------- #
# Rate limiting (limits — moving window, in-process)
# --------------------------------------------------------------------------- #
_rate_limiter = None  # limits.strategies.MovingWindowRateLimiter | None
_rate_limit_item = None  # limits.RateLimitItem | None
_rate_limit_ready = False


def _ensure_rate_limiter() -> bool:
    """Lazily build the shared limiter. Returns False when unavailable."""
    global _rate_limiter, _rate_limit_item, _rate_limit_ready
    if _rate_limit_ready:
        return _rate_limiter is not None

    _rate_limit_ready = True
    settings = get_settings()
    if not settings.ENABLE_RATE_LIMIT or not settings.RATE_LIMIT:
        return False
    try:
        from limits import parse
        from limits.storage import MemoryStorage
        from limits.strategies import MovingWindowRateLimiter
    except ImportError:
        logger.warning(
            "ENABLE_RATE_LIMIT is true but the 'limits' package is not "
            "installed; rate limiting is disabled."
        )
        return False

    _rate_limit_item = parse(settings.RATE_LIMIT)
    _rate_limiter = MovingWindowRateLimiter(MemoryStorage())
    logger.info("Rate limiting enabled: %s", settings.RATE_LIMIT)
    return True


def _enforce_rate_limit(identity: str) -> None:
    if not _ensure_rate_limiter():
        return
    assert _rate_limiter is not None and _rate_limit_item is not None
    if not _rate_limiter.hit(_rate_limit_item, identity):
        raise RateLimitError(f"Rate limit exceeded ({get_settings().RATE_LIMIT}).")


async def rate_limit(request: Request) -> None:
    """REST dependency enforcing the configured rate limit."""
    settings = get_settings()
    key = request.headers.get(settings.API_KEY_HEADER)
    client = request.client
    _enforce_rate_limit(_identity_from_headers(key, client.host if client else None))


def check_ws_rate_limit(websocket: WebSocket) -> None:
    """Enforce the rate limit for a WebSocket handshake."""
    settings = get_settings()
    key = websocket.headers.get(settings.API_KEY_HEADER)
    client = websocket.client
    _enforce_rate_limit(_identity_from_headers(key, client.host if client else None))


def reset_rate_limiter() -> None:
    """Drop cached limiter state (used by tests)."""
    global _rate_limiter, _rate_limit_item, _rate_limit_ready
    _rate_limiter = None
    _rate_limit_item = None
    _rate_limit_ready = False


def security_dependencies() -> list[Callable]:
    """Dependencies applied to every protected REST route."""
    return [Depends(require_api_key), Depends(rate_limit)]
