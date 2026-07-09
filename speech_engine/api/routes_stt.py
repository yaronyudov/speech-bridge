"""Batch Speech-to-Text HTTP endpoints."""

import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from speech_engine.config import get_settings
from speech_engine.core.constants import normalize_language
from speech_engine.core.exceptions import RequestTooLargeError
from speech_engine.core.security import security_dependencies
from speech_engine.core.stt.factory import get_stt_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Speech-to-Text"], dependencies=security_dependencies())

_UPLOAD_CHUNK_SIZE = 1024 * 1024
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,8}$")


class TranscriptionResponse(BaseModel):
    text: str


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix
    return suffix if _SAFE_SUFFIX.match(suffix) else ".bin"


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe an uploaded audio file",
)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file (wav/mp3/m4a/...)"),
    language: str | None = Query(
        default=None,
        description="Language of the audio: en, he, or ar. "
        "Omit for auto-detection (supported by local/openai engines).",
    ),
) -> TranscriptionResponse:
    """Save the upload to a temp file, run the configured STT engine,
    delete the temp file, and return ``{"text": "..."}``."""
    settings = get_settings()
    lang = normalize_language(language)  # raises 400 via the global handler

    temp_dir = settings.resolve_temp_dir()
    temp_path = temp_dir / f"stt_{uuid4().hex}{_safe_suffix(audio.filename)}"
    max_bytes = settings.MAX_UPLOAD_BYTES

    try:
        received = 0
        with open(temp_path, "wb") as out:
            while chunk := await audio.read(_UPLOAD_CHUNK_SIZE):
                received += len(chunk)
                if max_bytes and received > max_bytes:
                    raise RequestTooLargeError(
                        f"Uploaded audio exceeds the maximum size of {max_bytes} bytes."
                    )
                out.write(chunk)
        if received == 0:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

        engine = get_stt_engine()
        logger.info(
            "Transcribing '%s' (%d bytes, language=%s, engine=%s)",
            audio.filename,
            received,
            lang or "auto",
            engine.name,
        )
        text = await engine.transcribe(str(temp_path), lang)
        return TranscriptionResponse(text=text)
    finally:
        temp_path.unlink(missing_ok=True)
