#!/usr/bin/env bash
# Starts speech-bridge local FastAPI server using the dedicated .venv

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting speech-bridge local engine on http://0.0.0.0:8000 ..."
exec "$DIR/.venv/bin/uvicorn" speech_engine.main:app --host 0.0.0.0 --port 8000 "$@"
