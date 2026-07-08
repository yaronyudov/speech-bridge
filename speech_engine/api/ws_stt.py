"""Live/streaming Speech-to-Text over WebSockets.

Protocol (see README for the full contract):

* Connect to ``/api/v1/live-transcribe?language=he`` — or omit the query
  parameter and send an initial text frame ``{"language": "he"}``.
* Send continuous **binary** frames of raw PCM audio
  (16-bit little-endian, 16 kHz, mono).
* Optional text control frames: ``{"event": "flush"}`` finalizes the
  current segment, ``{"event": "stop"}`` flushes and ends the session.
* Receive JSON frames: ``{"type": "partial"|"final", "text": "..."}``;
  on failure an error frame ``{"type": "error", "message": "..."}`` is
  sent and the socket is closed (4400 = client error, 1011 = internal).
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from speech_engine.core.constants import require_language
from speech_engine.core.exceptions import SpeechEngineError
from speech_engine.core.stt.factory import get_stt_engine

logger = logging.getLogger(__name__)

router = APIRouter()

_HANDSHAKE_TIMEOUT_SECONDS = 15.0


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass  # already closed / disconnected


async def _send_error_and_close(
    websocket: WebSocket, message: str, code: int
) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
    except (RuntimeError, WebSocketDisconnect):
        return
    await _safe_close(websocket, code)


async def _negotiate_language(
    websocket: WebSocket, query_language: Optional[str]
) -> Optional[str]:
    """Resolve the session language from the query string or the first
    text frame. Returns the raw client value (validated by the caller),
    or None when the client disconnected / never declared a language."""
    if query_language is not None:
        return query_language

    try:
        message = await asyncio.wait_for(
            websocket.receive(), timeout=_HANDSHAKE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        await _send_error_and_close(
            websocket,
            "No language declared. Connect with ?language=<en|he|ar> or send "
            'an initial text frame {"language": "<en|he|ar>"}.',
            4400,
        )
        return None
    except WebSocketDisconnect:
        return None

    if message.get("type") == "websocket.disconnect":
        return None

    text = message.get("text")
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "language" in parsed:
                return str(parsed["language"])
        except ValueError:
            return text.strip()  # bare "he" is accepted too

    await _send_error_and_close(
        websocket,
        "The first frame must declare the language, e.g. "
        '{"language": "he"} (binary audio arrived first).',
        4400,
    )
    return None


@router.websocket("/live-transcribe")
async def live_transcribe(
    websocket: WebSocket,
    language: Optional[str] = Query(
        default=None, description="Session language: en, he, or ar."
    ),
) -> None:
    """Real-time transcription: binary PCM in, JSON partial/final out."""
    await websocket.accept()

    raw_language = await _negotiate_language(websocket, language)
    if raw_language is None:
        return

    try:
        lang = require_language(raw_language)
    except SpeechEngineError as exc:
        await _send_error_and_close(websocket, str(exc), exc.ws_close_code)
        return

    try:
        engine = get_stt_engine()
    except SpeechEngineError as exc:
        logger.error("Could not create STT engine for live session: %s", exc)
        await _send_error_and_close(websocket, str(exc), exc.ws_close_code)
        return

    client = websocket.client
    logger.info(
        "Live transcription session started (client=%s, engine=%s, language=%s)",
        f"{client.host}:{client.port}" if client else "unknown",
        engine.name,
        lang,
    )
    try:
        async for result in engine.transcribe_stream(websocket, lang):
            await websocket.send_json({"type": result.type, "text": result.text})
        # Engine finished cleanly (client sent "stop" or disconnected).
        await _safe_close(websocket, 1000)
    except WebSocketDisconnect:
        logger.info("Live transcription client disconnected")
    except SpeechEngineError as exc:
        logger.error("Live transcription failed: %s", exc)
        await _send_error_and_close(websocket, str(exc), exc.ws_close_code)
    except RuntimeError:
        # send after an abrupt disconnect — nothing left to clean up
        logger.info("Live transcription connection dropped mid-send")
    except Exception:
        logger.exception("Unexpected error in live transcription session")
        await _send_error_and_close(websocket, "Internal server error.", 1011)
    finally:
        logger.info("Live transcription session closed (language=%s)", lang)
