"""FastAPI entry point.

Routers are mounted **conditionally**: the STT endpoints (HTTP + WebSocket)
exist only when ``ENABLE_STT`` is true, and the TTS endpoint only when
``ENABLE_TTS`` is true — disabled subsystems load no models, hold no
memory, and return 404 for their routes.

Run with:
    uvicorn speech_engine.main:app --host 0.0.0.0 --port 8000
or:
    python -m speech_engine.main
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from speech_engine import __version__
from speech_engine.config import get_settings
from speech_engine.core.exceptions import SpeechEngineError

settings = get_settings()

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("speech_engine")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting speech-bridge v%s (STT: %s, TTS: %s)",
        __version__,
        f"enabled/{settings.STT_ENGINE}" if settings.ENABLE_STT else "disabled",
        f"enabled/{settings.TTS_ENGINE}" if settings.ENABLE_TTS else "disabled",
    )
    if not settings.ENABLE_STT and not settings.ENABLE_TTS:
        logger.warning(
            "Both ENABLE_STT and ENABLE_TTS are false — "
            "only /health is being served."
        )

    if settings.ENABLE_STT:
        # Fail fast on bad credentials/config, and pre-load the local
        # whisper model exactly once so the first request is not slow.
        from speech_engine.core.stt.factory import get_stt_engine

        engine = get_stt_engine()
        if hasattr(engine, "warmup"):
            logger.info("Warming up STT engine '%s'...", engine.name)
            await asyncio.to_thread(engine.warmup)
        logger.info("STT engine ready: %s", engine.name)

    if settings.ENABLE_TTS:
        from speech_engine.core.tts.factory import get_tts_engine

        engine = get_tts_engine()
        logger.info("TTS engine ready: %s", engine.name)

    yield
    logger.info("speech-bridge shutting down")


app = FastAPI(
    title="speech-bridge",
    description=(
        "Modular STT/TTS backend for English, Hebrew, and Arabic with "
        "switchable local (faster-whisper / edge-tts) and remote "
        "(Azure / OpenAI / AWS) engines, batch endpoints, and real-time "
        "WebSocket transcription."
    ),
    version=__version__,
    lifespan=lifespan,
)


@app.exception_handler(SpeechEngineError)
async def speech_engine_error_handler(
    request: Request, exc: SpeechEngineError
) -> JSONResponse:
    logger.error("%s: %s", type(exc).__name__, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# --------------------------------------------------------------------------- #
# Conditional mounting — disabled subsystems expose no routes at all.
# --------------------------------------------------------------------------- #
if settings.ENABLE_STT:
    from speech_engine.api import routes_stt, ws_stt

    app.include_router(routes_stt.router, prefix="/api/v1")
    app.include_router(ws_stt.router, prefix="/api/v1")

if settings.ENABLE_TTS:
    from speech_engine.api import routes_tts

    app.include_router(routes_tts.router, prefix="/api/v1")


@app.get("/health", tags=["Health"], summary="Service health & active engines")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "stt": {
            "enabled": settings.ENABLE_STT,
            "engine": settings.STT_ENGINE if settings.ENABLE_STT else None,
        },
        "tts": {
            "enabled": settings.ENABLE_TTS,
            "engine": settings.TTS_ENGINE if settings.ENABLE_TTS else None,
        },
        "supported_languages": ["en", "he", "ar"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "speech_engine.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
