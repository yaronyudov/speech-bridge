# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Multi-stage build for speech-bridge.
#   * builder stage compiles wheels into a venv
#   * final stage is slim, runs as a non-root user, ships a HEALTHCHECK,
#     and keeps the whisper model cache on a volume so the ~3 GB model is
#     downloaded once and survives container restarts.
# ---------------------------------------------------------------------------

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY speech_engine/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# --------------------------------------------------------------------------- #
FROM python:3.11-slim AS runtime

# ffmpeg      — pydub decoding of compressed uploads (mp3/m4a/webm)
# libsndfile1 — soundfile
# libasound2 / libssl / ca-certificates — Azure Speech SDK runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libasound2 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Persist model downloads on the /models volume (see docker-compose).
    HF_HOME=/models \
    XDG_CACHE_HOME=/models \
    HUGGINGFACE_HUB_CACHE=/models/huggingface

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY speech_engine ./speech_engine

RUN mkdir -p /models && chown -R appuser:appuser /models /app
VOLUME ["/models"]

USER appuser
EXPOSE 8000

# Liveness via the /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single worker: the faster-whisper model is a per-process singleton.
CMD ["uvicorn", "speech_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
