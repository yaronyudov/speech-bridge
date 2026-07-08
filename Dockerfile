FROM python:3.11-slim

# ffmpeg      — pydub decoding of compressed uploads (mp3/m4a/webm)
# libsndfile1 — soundfile
# libasound2 / libssl / ca-certificates — Azure Speech SDK runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libasound2 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY speech_engine/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY speech_engine ./speech_engine

EXPOSE 8000

# Single worker: the faster-whisper model is a per-process singleton.
CMD ["uvicorn", "speech_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
