#!/usr/bin/env bash
# Runner for Ivrit-AI Hebrew Model Comparison & Testing
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"

exec "$ROOT_DIR/.venv/bin/python" "$DIR/compare_hebrew_models.py" "$@"
