"""Remote STT engines: Azure Speech, OpenAI Whisper API, Amazon Transcribe.

Batch
-----
* **Azure** — Speech SDK continuous recognition over a WAV file.
* **OpenAI** — ``AsyncOpenAI().audio.transcriptions`` (Whisper API); the
  file is uploaded as-is (the API accepts wav/mp3/m4a/webm/...).
* **AWS** — the file is decoded to PCM and pushed through the Amazon
  Transcribe *streaming* API, which avoids the S3-bucket round-trip the
  Transcribe batch API would require.

Live streaming
--------------
* **Azure** — ``PushAudioInputStream`` + ``SpeechRecognizer`` continuous
  recognition; SDK callbacks are bridged onto the event loop with
  ``loop.call_soon_threadsafe`` and an ``asyncio.Queue``.
* **AWS** — Amazon Transcribe Streaming SDK (``amazon-transcribe``),
  full-duplex: one task pumps WebSocket audio into the input stream
  while the transcript event stream is consumed concurrently.
* **OpenAI** — the Whisper API has no public streaming transport, so a
  buffered rolling-window adapter periodically flushes the accumulated
  PCM to the batch API and emits partial/final results (higher latency
  than Azure/AWS; documented in the README).

All SDK imports are lazy so a deployment only needs the packages for the
engines it actually enables.
"""

import asyncio
import io
import logging
import os
import threading
from typing import Any, AsyncGenerator, Optional, Tuple

from speech_engine.config import Settings, get_settings
from speech_engine.core.audio import (
    STREAM_BYTES_PER_SECOND,
    STREAM_SAMPLE_RATE,
    ensure_wav_pcm16,
    load_audio_as_pcm16,
    wrap_pcm16_as_wav,
)
from speech_engine.core.constants import (
    AWS_TRANSCRIBE_LANGUAGES,
    AZURE_STT_LOCALES,
    DEFAULT_LANGUAGE,
    normalize_language,
)
from speech_engine.core.exceptions import (
    ConfigurationError,
    RemoteServiceError,
    SpeechEngineError,
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

_BATCH_RECOGNITION_TIMEOUT_SECONDS = 300


# =========================================================================== #
# Azure Speech Services
# =========================================================================== #
class AzureSTTEngine(BaseSTTEngine):
    """Azure Cognitive Services Speech-to-Text (batch + real-time)."""

    name = "azure"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.AZURE_SPEECH_KEY or not settings.AZURE_SPEECH_REGION:
            raise ConfigurationError(
                "STT_ENGINE=azure requires AZURE_SPEECH_KEY and "
                "AZURE_SPEECH_REGION to be configured."
            )
        self._settings = settings

    @staticmethod
    def _sdk() -> Any:
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as exc:
            raise ConfigurationError(
                "STT_ENGINE=azure requires the "
                "'azure-cognitiveservices-speech' package."
            ) from exc
        return speechsdk

    def _speech_config(self, speechsdk: Any, lang: str) -> Any:
        config = speechsdk.SpeechConfig(
            subscription=self._settings.AZURE_SPEECH_KEY,
            region=self._settings.AZURE_SPEECH_REGION,
        )
        config.speech_recognition_language = AZURE_STT_LOCALES[lang]
        return config

    # ---------------------------- batch ------------------------------- #
    async def transcribe(
        self, audio_file_path: str, language: Optional[str] = None
    ) -> str:
        lang = normalize_language(language) or DEFAULT_LANGUAGE
        return await asyncio.to_thread(
            self._transcribe_blocking, audio_file_path, lang
        )

    def _transcribe_blocking(self, audio_file_path: str, lang: str) -> str:
        speechsdk = self._sdk()
        # The Speech SDK needs plain PCM WAV without extra codecs installed.
        wav_path, is_temporary = ensure_wav_pcm16(audio_file_path)
        recognizer = None
        try:
            audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=self._speech_config(speechsdk, lang),
                audio_config=audio_config,
            )

            pieces = []
            errors = []
            done = threading.Event()

            def on_recognized(evt: Any) -> None:
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    pieces.append(evt.result.text)

            def on_canceled(evt: Any) -> None:
                if evt.reason == speechsdk.CancellationReason.Error:
                    errors.append(evt.error_details)
                done.set()

            recognizer.recognized.connect(on_recognized)
            recognizer.canceled.connect(on_canceled)
            recognizer.session_stopped.connect(lambda evt: done.set())

            recognizer.start_continuous_recognition()
            finished = done.wait(timeout=_BATCH_RECOGNITION_TIMEOUT_SECONDS)
            recognizer.stop_continuous_recognition()

            if not finished:
                raise RemoteServiceError("Azure speech recognition timed out.")
            if errors:
                raise RemoteServiceError(
                    f"Azure speech recognition failed: {errors[0]}"
                )
            return " ".join(piece.strip() for piece in pieces if piece).strip()
        finally:
            if is_temporary:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

    # --------------------------- streaming ----------------------------- #
    async def transcribe_stream(
        self, websocket: Any, language: Optional[str] = None
    ) -> AsyncGenerator[STTStreamResult, None]:
        speechsdk = self._sdk()
        lang = normalize_language(language) or DEFAULT_LANGUAGE
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()

        def emit(kind: str, payload: Optional[str]) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (kind, payload))

        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=STREAM_SAMPLE_RATE, bits_per_sample=16, channels=1
        )
        push_stream = speechsdk.audio.PushAudioInputStream(
            stream_format=stream_format
        )
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=self._speech_config(speechsdk, lang),
            audio_config=speechsdk.audio.AudioConfig(stream=push_stream),
        )

        def on_recognizing(evt: Any) -> None:
            if evt.result.text:
                emit(RESULT_PARTIAL, evt.result.text)

        def on_recognized(evt: Any) -> None:
            if (
                evt.result.reason == speechsdk.ResultReason.RecognizedSpeech
                and evt.result.text
            ):
                emit(RESULT_FINAL, evt.result.text)

        def on_canceled(evt: Any) -> None:
            if getattr(evt, "reason", None) == speechsdk.CancellationReason.Error:
                emit("error", getattr(evt, "error_details", "unknown error"))
            else:  # EndOfStream / CancelledByUser terminate the session
                emit("done", None)

        recognizer.recognizing.connect(on_recognizing)
        recognizer.recognized.connect(on_recognized)
        recognizer.canceled.connect(on_canceled)
        recognizer.session_stopped.connect(lambda evt: emit("done", None))
        recognizer.start_continuous_recognition_async()

        async def pump_audio() -> None:
            """Forward WebSocket binary frames into the Azure push stream."""
            try:
                while True:
                    kind, data = await receive_stream_message(websocket)
                    if kind == MSG_AUDIO:
                        push_stream.write(bytes(data))
                    elif kind in (MSG_STOP, MSG_DISCONNECT):
                        break
            finally:
                # Closing the push stream flushes Azure's final results and
                # ends the session (-> "done" via session_stopped/canceled).
                try:
                    push_stream.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

        pump_task = asyncio.create_task(pump_audio())
        try:
            while True:
                kind, payload = await events.get()
                if kind == "done":
                    break
                if kind == "error":
                    raise RemoteServiceError(
                        f"Azure speech recognition failed: {payload}"
                    )
                yield STTStreamResult(kind, payload or "")
        finally:
            pump_task.cancel()
            try:
                push_stream.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                recognizer.stop_continuous_recognition_async()
            except Exception:  # noqa: BLE001
                pass


# =========================================================================== #
# OpenAI Whisper API
# =========================================================================== #
class OpenAISTTEngine(BaseSTTEngine):
    """OpenAI Whisper API batch STT + buffered pseudo-streaming adapter."""

    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise ConfigurationError(
                "STT_ENGINE=openai requires OPENAI_API_KEY to be configured."
            )
        self._settings = settings
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise ConfigurationError(
                    "STT_ENGINE=openai requires the 'openai' package."
                ) from exc
            self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)
        return self._client

    async def _request_transcription(
        self, file_payload: Any, lang: Optional[str]
    ) -> str:
        client = self._get_client()
        kwargs = {"model": self._settings.OPENAI_STT_MODEL, "file": file_payload}
        if lang:
            kwargs["language"] = lang
        try:
            result = await client.audio.transcriptions.create(**kwargs)
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("OpenAI transcription request failed: %s", exc)
            raise RemoteServiceError(f"OpenAI transcription failed: {exc}") from exc
        return (getattr(result, "text", "") or "").strip()

    # ---------------------------- batch ------------------------------- #
    async def transcribe(
        self, audio_file_path: str, language: Optional[str] = None
    ) -> str:
        lang = normalize_language(language)
        with open(audio_file_path, "rb") as audio_file:
            return await self._request_transcription(audio_file, lang)

    # --------------------------- streaming ----------------------------- #
    async def transcribe_stream(
        self, websocket: Any, language: Optional[str] = None
    ) -> AsyncGenerator[STTStreamResult, None]:
        lang = normalize_language(language)
        settings = self._settings

        flush_bytes = int(
            settings.STT_STREAM_OPENAI_FLUSH_SECONDS * STREAM_BYTES_PER_SECOND
        )
        max_segment_bytes = int(
            settings.STT_STREAM_MAX_SEGMENT_SECONDS * STREAM_BYTES_PER_SECOND
        )

        buffer = bytearray()
        pending_bytes = 0
        last_partial = ""

        async def transcribe_buffer() -> str:
            wav_bytes = wrap_pcm16_as_wav(bytes(buffer))
            payload = ("chunk.wav", io.BytesIO(wav_bytes), "audio/wav")
            return await self._request_transcription(payload, lang)

        while True:
            kind, data = await receive_stream_message(websocket)

            if kind == MSG_AUDIO:
                buffer.extend(data)
                pending_bytes += len(data)
                if pending_bytes < flush_bytes:
                    continue
                pending_bytes = 0

                text = await transcribe_buffer()
                if len(buffer) >= max_segment_bytes:
                    buffer.clear()
                    last_partial = ""
                    if text:
                        yield STTStreamResult(RESULT_FINAL, text)
                elif text and text != last_partial:
                    last_partial = text
                    yield STTStreamResult(RESULT_PARTIAL, text)

            elif kind in (MSG_STOP, MSG_FLUSH):
                if buffer:
                    text = await transcribe_buffer()
                    buffer.clear()
                    last_partial = ""
                    if text:
                        yield STTStreamResult(RESULT_FINAL, text)
                if kind == MSG_STOP:
                    return

            elif kind == MSG_DISCONNECT:
                return


# =========================================================================== #
# AWS — Amazon Transcribe Streaming
# =========================================================================== #
class AWSSTTEngine(BaseSTTEngine):
    """Amazon Transcribe streaming SDK for both batch and live STT."""

    name = "aws"

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        # Export credentials so the AWS SDK credential chain resolves them
        # even when they were provided only via .env / config.yaml.
        if settings.AWS_ACCESS_KEY_ID:
            os.environ.setdefault("AWS_ACCESS_KEY_ID", settings.AWS_ACCESS_KEY_ID)
        if settings.AWS_SECRET_ACCESS_KEY:
            os.environ.setdefault(
                "AWS_SECRET_ACCESS_KEY", settings.AWS_SECRET_ACCESS_KEY
            )
        os.environ.setdefault("AWS_DEFAULT_REGION", settings.AWS_REGION)

    def _create_client(self) -> Any:
        try:
            from amazon_transcribe.client import TranscribeStreamingClient
        except ImportError as exc:
            raise ConfigurationError(
                "STT_ENGINE=aws requires the 'amazon-transcribe' package."
            ) from exc
        return TranscribeStreamingClient(region=self._settings.AWS_REGION)

    async def _start_stream(self, lang: str) -> Any:
        client = self._create_client()
        try:
            return await client.start_stream_transcription(
                language_code=AWS_TRANSCRIBE_LANGUAGES[lang],
                media_sample_rate_hz=STREAM_SAMPLE_RATE,
                media_encoding="pcm",
            )
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("Failed to open Amazon Transcribe stream: %s", exc)
            raise RemoteServiceError(
                f"Could not start Amazon Transcribe stream: {exc}"
            ) from exc

    @staticmethod
    def _iter_results(event: Any) -> list:
        transcript = getattr(event, "transcript", None)
        return list(getattr(transcript, "results", None) or [])

    # ---------------------------- batch ------------------------------- #
    async def transcribe(
        self, audio_file_path: str, language: Optional[str] = None
    ) -> str:
        lang = normalize_language(language) or DEFAULT_LANGUAGE
        pcm = await asyncio.to_thread(load_audio_as_pcm16, audio_file_path)
        stream = await self._start_stream(lang)
        finals: list = []

        async def feed_audio() -> None:
            chunk_size = 1024 * 16
            for offset in range(0, len(pcm), chunk_size):
                await stream.input_stream.send_audio_event(
                    audio_chunk=pcm[offset : offset + chunk_size]
                )
            await stream.input_stream.end_stream()

        async def collect_results() -> None:
            async for event in stream.output_stream:
                for result in self._iter_results(event):
                    if not result.is_partial and result.alternatives:
                        finals.append(result.alternatives[0].transcript)

        try:
            await asyncio.gather(feed_audio(), collect_results())
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("Amazon Transcribe batch request failed: %s", exc)
            raise RemoteServiceError(
                f"Amazon Transcribe transcription failed: {exc}"
            ) from exc
        return " ".join(text.strip() for text in finals if text).strip()

    # --------------------------- streaming ----------------------------- #
    async def transcribe_stream(
        self, websocket: Any, language: Optional[str] = None
    ) -> AsyncGenerator[STTStreamResult, None]:
        lang = normalize_language(language) or DEFAULT_LANGUAGE
        stream = await self._start_stream(lang)
        events: asyncio.Queue = asyncio.Queue()

        async def pump_in() -> None:
            """WebSocket -> Transcribe input stream."""
            try:
                while True:
                    kind, data = await receive_stream_message(websocket)
                    if kind == MSG_AUDIO:
                        await stream.input_stream.send_audio_event(
                            audio_chunk=bytes(data)
                        )
                    elif kind in (MSG_STOP, MSG_DISCONNECT):
                        break
            finally:
                try:
                    await stream.input_stream.end_stream()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass

        async def pump_out() -> None:
            """Transcribe output stream -> local queue."""
            try:
                async for event in stream.output_stream:
                    for result in self._iter_results(event):
                        if not result.alternatives:
                            continue
                        text = result.alternatives[0].transcript
                        if not text:
                            continue
                        await events.put(
                            (
                                RESULT_PARTIAL if result.is_partial else RESULT_FINAL,
                                text,
                            )
                        )
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                await events.put(("error", str(exc)))
            finally:
                await events.put(("done", None))

        in_task = asyncio.create_task(pump_in())
        out_task = asyncio.create_task(pump_out())
        try:
            while True:
                kind, payload = await events.get()
                if kind == "done":
                    break
                if kind == "error":
                    raise RemoteServiceError(
                        f"Amazon Transcribe streaming failed: {payload}"
                    )
                yield STTStreamResult(kind, payload or "")
        finally:
            for task in (in_task, out_task):
                if not task.done():
                    task.cancel()
