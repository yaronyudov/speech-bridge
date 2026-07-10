"""Abstract Base Class for STT engines (batch + streaming) and shared
WebSocket message plumbing used by every streaming implementation."""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from starlette.websockets import WebSocketDisconnect

# Result "type" values emitted while streaming.
RESULT_PARTIAL = "partial"
RESULT_FINAL = "final"

# Message kinds produced by receive_stream_message().
MSG_AUDIO = "audio"  # binary PCM chunk
MSG_STOP = "stop"  # client asked to finish the session
MSG_FLUSH = "flush"  # client asked to finalize the current segment
MSG_DISCONNECT = "disconnect"  # transport closed
MSG_NOOP = "noop"  # unrecognized / ignorable frame


@dataclass(frozen=True)
class STTStreamResult:
    """A single live-transcription increment.

    ``type`` is ``"partial"`` (hypothesis may still change) or ``"final"``
    (segment committed). Serialized on the wire as
    ``{"type": "partial"|"final", "text": "..."}``.
    """

    type: str
    text: str


class BaseSTTEngine(ABC):
    """Strategy interface every STT engine (local or remote) implements."""

    name: str = "base"

    @abstractmethod
    async def transcribe(
        self, audio_file_path: str, language: str | None = None
    ) -> str:
        """Transcribe a complete audio file and return the full text.

        Args:
            audio_file_path: Path to an audio file on local disk.
            language: Canonical language code (``en``/``he``/``ar``) or
                ``None`` for auto-detection where the engine supports it.
        """
        raise NotImplementedError

    @abstractmethod
    async def transcribe_stream(
        self, websocket: Any, language: str | None = None
    ) -> AsyncGenerator[STTStreamResult, None]:
        """Consume binary PCM chunks (16 kHz / 16-bit / mono) from an open
        WebSocket and yield intermediate (*partial*) and committed (*final*)
        transcription results as they become available.

        Implementations MUST return promptly when the client disconnects
        and MUST release any remote push-streams / local buffers on exit.
        """
        raise NotImplementedError
        yield STTStreamResult(RESULT_FINAL, "")  # pragma: no cover


async def receive_stream_message(websocket: Any) -> tuple[str, bytes]:
    """Read one frame from a Starlette WebSocket and classify it.

    Returns ``(kind, payload)`` where kind is one of the ``MSG_*``
    constants and payload is the audio bytes for ``MSG_AUDIO`` (empty
    ``b""`` for every other kind). Binary frames are audio; text frames
    are treated as JSON control messages (``{"event": "stop"}`` /
    ``{"event": "flush"}``) or the bare strings ``"stop"`` / ``"flush"``.
    Transport errors and disconnect frames are normalized to
    ``MSG_DISCONNECT`` so engine loops can clean up without
    special-casing exceptions.
    """
    try:
        message = await websocket.receive()
    except (WebSocketDisconnect, RuntimeError):
        return MSG_DISCONNECT, b""

    if message.get("type") == "websocket.disconnect":
        return MSG_DISCONNECT, b""

    data = message.get("bytes")
    if data:
        return MSG_AUDIO, data

    text = message.get("text")
    if text:
        event = text.strip().lower()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                event = str(payload.get("event", "")).strip().lower()
        except ValueError:
            pass
        if event in {"stop", "eof", "end", "close"}:
            return MSG_STOP, b""
        if event == "flush":
            return MSG_FLUSH, b""

    return MSG_NOOP, b""
