#!/usr/bin/env bash
# Interactive runner: Record your own voice and benchmark all Hebrew models
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"

exec "$ROOT_DIR/.venv/bin/python" "$DIR/record_and_benchmark.py" "$@"
