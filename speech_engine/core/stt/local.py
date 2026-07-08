"""Local STT engine built on faster-whisper.

* The ``WhisperModel`` is loaded exactly once per process (thread-safe
  lazy singleton) and only when the STT subsystem is enabled — the model
  is instantiated on first use, which ``main.py`` triggers at startup
  via :meth:`LocalSTTEngine.warmup` when ``ENABLE_STT`` is true.
* Batch transcription runs the (blocking) model in a worker thread.
* Live streaming keeps a rolling PCM buffer per connection: every
  ``STT_STREAM_INFER_INTERVAL_SECONDS`` of new audio the whole buffer is
  re-decoded with whisper's built-in VAD filter and the hypothesis is
  emitted as a *partial*; trailing silence or a full buffer commits the
  segment as *final* and resets the window.
"""

import asyncio
import logging
import threading
from typing import Any, AsyncGenerator, Optional

from speech_engine.config import Settings, get_settings
from speech_engine.core.audio import (
    STREAM_BYTES_PER_SECOND,
    is_silence,
    pcm16_to_float32,
)
from speech_engine.core.constants import normalize_language
from speech_engine.core.exceptions import (
    ConfigurationError,
    SpeechEngineError,
    TranscriptionError,
)
from speech_engine.core.stt.base import (
    MSG_AUDIO,
    MSG_DISCONNECT,
    MSG_FLUSH,
    MSG_STOP,
    RESULT_FINAL,
    RESULT_PARTIAL,
    BaseSTTEngine,
    STTStreamResult,
    receive_stream_message,
)

logger = logging.getLogger(__name__)


class LocalSTTEngine(BaseSTTEngine):
    """faster-whisper batch transcription + rolling-window live streaming."""

    name = "local"

    # Process-wide model singleton (models are large; never load twice).
    _model: Optional[Any] = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._settings: Settings = get_settings()

    # ------------------------------------------------------------------ #
    # Model lifecycle
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_device(settings: Settings) -> str:
        if settings.STT_LOCAL_DEVICE != "auto":
            return settings.STT_LOCAL_DEVICE
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            # torch is optional; fall back to ctranslate2's own CUDA probe.
            try:
                import ctranslate2

                return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                return "cpu"

    def warmup(self) -> None:
        """Eagerly load the model (called from the FastAPI lifespan)."""
        self._get_model()

    def _get_model(self) -> Any:
        cls = type(self)
        if cls._model is None:
            with cls._model_lock:
                if cls._model is None:
                    try:
                        from faster_whisper import WhisperModel
                    except ImportError as exc:
                        raise ConfigurationError(
                            "STT_ENGINE=local requires the 'faster-whisper' "
                            "package: pip install faster-whisper"
                        ) from exc

                    settings = self._settings
                    device = self._detect_device(settings)
                    compute_type = settings.STT_LOCAL_COMPUTE_TYPE
                    if compute_type == "auto":
                        compute_type = "float16" if device == "cuda" else "int8"

                    logger.info(
                        "Loading faster-whisper model '%s' (device=%s, compute_type=%s)",
                        settings.STT_LOCAL_MODEL_SIZE,
                        device,
                        compute_type,
                    )
                    cls._model = WhisperModel(
                        settings.STT_LOCAL_MODEL_SIZE,
                        device=device,
                        compute_type=compute_type,
                    )
                    logger.info("faster-whisper model loaded")
        return cls._model

    # ------------------------------------------------------------------ #
    # Batch
    # ------------------------------------------------------------------ #
    async def transcribe(
        self, audio_file_path: str, language: Optional[str] = None
    ) -> str:
        lang = normalize_language(language)
        try:
            return await asyncio.to_thread(
                self._transcribe_source, audio_file_path, lang
            )
        except SpeechEngineError:
            raise
        except Exception as exc:
            raise TranscriptionError(f"Local transcription failed: {exc}") from exc

    def _transcribe_source(self, source: Any, lang: Optional[str]) -> str:
        """Blocking transcription of a file path or a float32 waveform."""
        model = self._get_model()
        segments, _info = model.transcribe(
            source,
            language=lang,  # None -> whisper auto-detect
            beam_size=self._settings.STT_LOCAL_BEAM_SIZE,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _transcribe_pcm(self, pcm: bytes, lang: Optional[str]) -> str:
        return self._transcribe_source(pcm16_to_float32(pcm), lang)

    # ------------------------------------------------------------------ #
    # Live streaming (rolling buffer + VAD-filtered incremental decode)
    # ------------------------------------------------------------------ #
    async def transcribe_stream(
        self, websocket: Any, language: Optional[str] = None
    ) -> AsyncGenerator[STTStreamResult, None]:
        lang = normalize_language(language)
        settings = self._settings

        min_new_bytes = int(
            settings.STT_STREAM_INFER_INTERVAL_SECONDS * STREAM_BYTES_PER_SECOND
        )
        max_segment_bytes = int(
            settings.STT_STREAM_MAX_SEGMENT_SECONDS * STREAM_BYTES_PER_SECOND
        )
        tail_bytes = int(
            settings.STT_STREAM_TRAILING_SILENCE_SECONDS * STREAM_BYTES_PER_SECOND
        )

        buffer = bytearray()
        pending_bytes = 0  # new audio since the last inference pass
        last_partial = ""

        logger.debug("Local live-STT session opened (language=%s)", lang)
        try:
            while True:
                kind, data = await receive_stream_message(websocket)

                if kind == MSG_AUDIO:
                    buffer.extend(data)
                    pending_bytes += len(data)
                    if pending_bytes < min_new_bytes:
                        continue
                    pending_bytes = 0

                    text = await asyncio.to_thread(
                        self._transcribe_pcm, bytes(buffer), lang
                    )
                    segment_full = len(buffer) >= max_segment_bytes
                    trailing_quiet = len(buffer) >= tail_bytes and is_silence(
                        bytes(buffer[-tail_bytes:]),
                        settings.STT_STREAM_SILENCE_RMS_THRESHOLD,
                    )
                    if segment_full or trailing_quiet:
                        buffer.clear()
                        last_partial = ""
                        if text:
                            yield STTStreamResult(RESULT_FINAL, text)
                    elif text and text != last_partial:
                        last_partial = text
                        yield STTStreamResult(RESULT_PARTIAL, text)

                elif kind in (MSG_STOP, MSG_FLUSH):
                    if buffer:
                        text = await asyncio.to_thread(
                            self._transcribe_pcm, bytes(buffer), lang
                        )
                        buffer.clear()
                        last_partial = ""
                        if text:
                            yield STTStreamResult(RESULT_FINAL, text)
                    if kind == MSG_STOP:
                        return

                elif kind == MSG_DISCONNECT:
                    # Client is gone: nobody can receive a flush; just exit.
                    return
        finally:
            buffer.clear()
            logger.debug("Local live-STT session closed")
