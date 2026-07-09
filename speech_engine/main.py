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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    app.state.ready = False
    logger.info(
        "Starting speech-bridge v%s (STT: %s, TTS: %s)",
        __version__,
        f"enabled/{settings.STT_ENGINE}" if settings.ENABLE_STT else "disabled",
        f"enabled/{settings.TTS_ENGINE}" if settings.ENABLE_TTS else "disabled",
    )
    if not settings.ENABLE_STT and not settings.ENABLE_TTS:
        logger.warning(
            "Both ENABLE_STT and ENABLE_TTS are false — only /health is being served."
        )

    # Resolve credentials from a cloud secret manager, if configured, before
    # any engine reads them (no-op when SECRETS_BACKEND=none).
    from speech_engine.core.secrets import apply_secret_overrides

    await asyncio.to_thread(apply_secret_overrides, settings)

    if settings.ENABLE_STT:
        # Fail fast on bad credentials/config, and pre-load the local
        # whisper model exactly once so the first request is not slow.
        from speech_engine.core.stt.factory import get_stt_engine

        stt_engine = get_stt_engine()
        if hasattr(stt_engine, "warmup"):
            logger.info("Warming up STT engine '%s'...", stt_engine.name)
            await asyncio.to_thread(stt_engine.warmup)
        logger.info("STT engine ready: %s", stt_engine.name)

    if settings.ENABLE_TTS:
        from speech_engine.core.tts.factory import get_tts_engine

        tts_engine = get_tts_engine()
        logger.info("TTS engine ready: %s", tts_engine.name)

    app.state.ready = True
    yield
    app.state.ready = False
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
# Cross-cutting middleware & instrumentation (all optional / config-gated).
# --------------------------------------------------------------------------- #
if settings.CORS_ALLOW_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if settings.ENABLE_METRICS:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )
        logger.info("Prometheus metrics exposed at /metrics")
    except ImportError:
        logger.warning(
            "ENABLE_METRICS is true but 'prometheus-fastapi-instrumentator' "
            "is not installed; /metrics is disabled."
        )

if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info(
            "OpenTelemetry tracing enabled (exporter=%s)",
            settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )
    except ImportError:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry packages "
            "are not installed; tracing is disabled."
        )


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


@app.get("/health", tags=["Health"], summary="Liveness probe & active engines")
async def health() -> dict:
    """Liveness: the process is up. Always returns 200 while serving."""
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


@app.get("/ready", tags=["Health"], summary="Readiness probe")
async def ready() -> JSONResponse:
    """Readiness: engines constructed and (for local STT) model loaded.

    Returns 503 until startup completes so load balancers hold traffic
    until the ~3 GB whisper model has finished warming up.
    """
    is_ready = bool(getattr(app.state, "ready", False))
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "starting"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "speech_engine.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
