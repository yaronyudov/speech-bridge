"""TTS Factory: returns the configured engine (Strategy) as a singleton.

``TTS_ENGINE`` selects the provider; when it is ``local``,
``TTS_LOCAL_BACKEND`` further selects edge-tts (default) or Coqui XTTS.
"""

import threading

from speech_engine.config import get_settings
from speech_engine.core.exceptions import ConfigurationError
from speech_engine.core.tts.base import BaseTTSEngine
from speech_engine.core.tts.local import CoquiTTSEngine, EdgeTTSEngine
from speech_engine.core.tts.remote import (
    AWSTTSEngine,
    AzureTTSEngine,
    OpenAITTSEngine,
)

_instance: BaseTTSEngine | None = None
_lock = threading.Lock()


def _create_engine() -> BaseTTSEngine:
    settings = get_settings()
    if not settings.ENABLE_TTS:
        raise ConfigurationError("The TTS subsystem is disabled (ENABLE_TTS=false).")
    if settings.TTS_ENGINE == "local":
        if settings.TTS_LOCAL_BACKEND == "coqui":
            return CoquiTTSEngine()
        return EdgeTTSEngine()
    if settings.TTS_ENGINE == "azure":
        return AzureTTSEngine()
    if settings.TTS_ENGINE == "openai":
        return OpenAITTSEngine()
    if settings.TTS_ENGINE == "aws":
        return AWSTTSEngine()
    raise ConfigurationError(
        f"Unknown TTS_ENGINE '{settings.TTS_ENGINE}'. "
        "Valid options: ['local', 'azure', 'openai', 'aws']"
    )


def get_tts_engine() -> BaseTTSEngine:
    """Return the process-wide TTS engine selected by ``TTS_ENGINE``."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = _create_engine()
    return _instance


def reset_tts_engine() -> None:
    """Drop the cached engine (used by tests / config reloads)."""
    global _instance
    with _lock:
        _instance = None
