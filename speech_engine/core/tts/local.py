"""Local TTS engines.

* :class:`EdgeTTSEngine` (default) — Microsoft Edge neural voices via
  ``edge-tts``: zero-cost, no API keys, excellent Hebrew and Arabic.
  Requires outbound internet but no credentials.
* :class:`CoquiTTSEngine` — fully offline Coqui XTTS v2 adapter for
  air-gapped deployments (heavy model download on first use; XTTS v2
  supports English and Arabic but **not Hebrew**).

Select via ``TTS_LOCAL_BACKEND`` ("edge" | "coqui").
"""

import asyncio
import logging
import os
import threading
from typing import Any, Optional

from speech_engine.config import Settings, get_settings
from speech_engine.core.constants import (
    COQUI_XTTS_LANGUAGES,
    EDGE_TTS_VOICES,
    LANGUAGE_NAMES,
    require_language,
)
from speech_engine.core.exceptions import (
    ConfigurationError,
    SpeechEngineError,
    SynthesisError,
    UnsupportedLanguageError,
)
from speech_engine.core.tts.base import BaseTTSEngine

logger = logging.getLogger(__name__)


def _verify_output_file(path: str) -> str:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise SynthesisError("TTS produced no audio output.")
    return path


class EdgeTTSEngine(BaseTTSEngine):
    """edge-tts adapter — high-quality neural voices without API keys."""

    name = "local-edge"
    file_extension = "mp3"
    media_type = "audio/mpeg"

    async def synthesize(
        self, text: str, language: str, output_file_path: str
    ) -> str:
        lang = require_language(language)
        voice = EDGE_TTS_VOICES[lang]
        try:
            import edge_tts
        except ImportError as exc:
            raise ConfigurationError(
                "TTS_ENGINE=local (edge backend) requires the 'edge-tts' "
                "package: pip install edge-tts"
            ) from exc

        try:
            communicate = edge_tts.Communicate(text=text, voice=voice)
            await communicate.save(output_file_path)
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("edge-tts synthesis failed: %s", exc)
            raise SynthesisError(f"edge-tts synthesis failed: {exc}") from exc
        return _verify_output_file(output_file_path)


class CoquiTTSEngine(BaseTTSEngine):
    """Coqui XTTS v2 adapter — fully offline local generation."""

    name = "local-coqui"
    file_extension = "wav"
    media_type = "audio/wav"

    # XTTS models are large — share one instance per process.
    _tts: Optional[Any] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._settings: Settings = get_settings()

    def _get_tts(self) -> Any:
        cls = type(self)
        if cls._tts is None:
            with cls._lock:
                if cls._tts is None:
                    try:
                        from TTS.api import TTS
                    except ImportError as exc:
                        raise ConfigurationError(
                            "TTS_LOCAL_BACKEND=coqui requires the 'TTS' "
                            "package: pip install TTS"
                        ) from exc
                    device = "cpu"
                    try:
                        import torch

                        if torch.cuda.is_available():
                            device = "cuda"
                    except ImportError:
                        pass
                    logger.info(
                        "Loading Coqui model '%s' on %s",
                        self._settings.TTS_COQUI_MODEL_NAME,
                        device,
                    )
                    cls._tts = TTS(self._settings.TTS_COQUI_MODEL_NAME).to(device)
        return cls._tts

    async def synthesize(
        self, text: str, language: str, output_file_path: str
    ) -> str:
        lang = require_language(language)
        coqui_lang = COQUI_XTTS_LANGUAGES.get(lang)
        if coqui_lang is None:
            raise UnsupportedLanguageError(
                f"Coqui XTTS v2 does not support {LANGUAGE_NAMES[lang]} "
                f"('{lang}'). Use TTS_LOCAL_BACKEND=edge or TTS_ENGINE=azure "
                "for Hebrew."
            )
        try:
            await asyncio.to_thread(
                self._synthesize_blocking, text, coqui_lang, output_file_path
            )
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("Coqui synthesis failed: %s", exc)
            raise SynthesisError(f"Coqui synthesis failed: {exc}") from exc
        return _verify_output_file(output_file_path)

    def _synthesize_blocking(
        self, text: str, coqui_lang: str, output_file_path: str
    ) -> None:
        tts = self._get_tts()
        tts.tts_to_file(
            text=text,
            language=coqui_lang,
            speaker=self._settings.TTS_COQUI_SPEAKER,
            file_path=output_file_path,
        )
