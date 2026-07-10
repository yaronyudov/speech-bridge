"""STT Factory: returns the configured engine (Strategy) as a singleton.

The concrete class is chosen from ``STT_ENGINE`` and instantiated once
per process; every request and WebSocket session shares the instance
(engines hold no per-request state — streaming state lives inside each
``transcribe_stream`` generator).
"""

import threading

from speech_engine.config import get_settings
from speech_engine.core.exceptions import ConfigurationError
from speech_engine.core.stt.base import BaseSTTEngine
from speech_engine.core.stt.local import LocalSTTEngine
from speech_engine.core.stt.remote import (
    AWSSTTEngine,
    AzureSTTEngine,
    OpenAISTTEngine,
)

_ENGINE_REGISTRY: dict[str, type[BaseSTTEngine]] = {
    "local": LocalSTTEngine,
    "azure": AzureSTTEngine,
    "openai": OpenAISTTEngine,
    "aws": AWSSTTEngine,
}

_instance: BaseSTTEngine | None = None
_lock = threading.Lock()


def get_stt_engine() -> BaseSTTEngine:
    """Return the process-wide STT engine selected by ``STT_ENGINE``.

    Raises:
        ConfigurationError: when STT is disabled or misconfigured.
    """
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                settings = get_settings()
                if not settings.ENABLE_STT:
                    raise ConfigurationError(
                        "The STT subsystem is disabled (ENABLE_STT=false)."
                    )
                engine_cls = _ENGINE_REGISTRY.get(settings.STT_ENGINE)
                if engine_cls is None:
                    raise ConfigurationError(
                        f"Unknown STT_ENGINE '{settings.STT_ENGINE}'. "
                        f"Valid options: {sorted(_ENGINE_REGISTRY)}"
                    )
                _instance = engine_cls()
    return _instance


def reset_stt_engine() -> None:
    """Drop the cached engine (used by tests / config reloads)."""
    global _instance
    with _lock:
        _instance = None
