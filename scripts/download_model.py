#!/usr/bin/env python3
"""CLI utility to download and cache Whisper models with live progress bars."""

import argparse
import os
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
ROOT_DIR = DIR.parent
venv_python = ROOT_DIR / ".venv" / "bin" / "python"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if sys.executable != str(venv_python) and venv_python.exists():
    os.execv(str(venv_python), [str(venv_python), __file__] + sys.argv[1:])

try:
    import huggingface_hub
    from faster_whisper.utils import _MODELS
except ImportError:
    print(
        "Error: Required dependencies not found. Run with ./.venv/bin/python",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and cache a faster-whisper model with a live progress bar."
    )
    parser.add_argument(
        "model",
        nargs="?",
        default="large-v3",
        help="Model size/name: tiny, base, small, medium, large-v3 (default: large-v3)",
    )
    args = parser.parse_args()

    repo_id = _MODELS.get(args.model, args.model)
    print("==================================================")
    print(f"📥 Downloading Whisper model: {args.model}")
    print(f"📦 Hugging Face Repository:  {repo_id}")
    print("==================================================\n")

    allow_patterns = [
        "config.json",
        "preprocessor_config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.*",
    ]

    path = huggingface_hub.snapshot_download(
        repo_id,
        allow_patterns=allow_patterns,
    )

    print("\n==================================================")
    print("✅ Download complete!")
    print(f"📁 Local cache path: {path}")
    print("==================================================")


if __name__ == "__main__":
    main()
