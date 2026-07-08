"""Text-to-Speech HTTP endpoints."""

import logging
import os
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from speech_engine.config import get_settings
from speech_engine.core.constants import require_language
from speech_engine.core.exceptions import SpeechEngineError
from speech_engine.core.tts.factory import get_tts_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Text-to-Speech"])


class SynthesisRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Plain text to synthesize.",
        examples=["hello world"],
    )
    language: str = Field(
        ..., description="Language of the text: en, he, or ar.", examples=["en"]
    )


def _delete_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


@router.post(
    "/synthesize",
    summary="Synthesize speech from text",
    response_class=FileResponse,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}},
)
async def synthesize_speech(payload: SynthesisRequest) -> FileResponse:
    """Run the configured TTS engine and stream the audio file back.

    The generated file is deleted after the response is sent
    (``BackgroundTasks`` attached to the ``FileResponse``).
    """
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text must not be blank.")
    lang = require_language(payload.language)  # raises 400 via global handler

    engine = get_tts_engine()
    output_dir = get_settings().resolve_temp_dir()
    output_path = output_dir / f"tts_{uuid4().hex}.{engine.file_extension}"

    logger.info(
        "Synthesizing %d chars (language=%s, engine=%s)",
        len(payload.text),
        lang,
        engine.name,
    )
    try:
        result_path = await engine.synthesize(
            payload.text, lang, str(output_path)
        )
    except SpeechEngineError:
        _delete_file(str(output_path))
        raise

    cleanup = BackgroundTasks()
    cleanup.add_task(_delete_file, result_path)
    return FileResponse(
        result_path,
        media_type=engine.media_type,
        filename=f"speech_{lang}.{engine.file_extension}",
        background=cleanup,
    )
