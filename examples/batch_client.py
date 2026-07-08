#!/usr/bin/env python3
"""Example client for the batch HTTP endpoints.

Usage:
    # Transcribe an audio file (language optional: en | he | ar)
    python examples/batch_client.py transcribe path/to/audio.wav --language he

    # Synthesize speech into an mp3
    python examples/batch_client.py synthesize "שלום עולם" --language he --out hello.mp3

Requires:
    pip install requests
"""

import argparse
import sys

import requests

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


def transcribe(base_url: str, audio_path: str, language: str | None) -> None:
    params = {"language": language} if language else {}
    with open(audio_path, "rb") as audio_file:
        response = requests.post(
            f"{base_url}/transcribe",
            params=params,
            files={"audio": (audio_path, audio_file)},
            timeout=600,
        )
    if response.status_code != 200:
        sys.exit(f"Error {response.status_code}: {response.text}")
    print(response.json()["text"])


def synthesize(base_url: str, text: str, language: str, out_path: str) -> None:
    response = requests.post(
        f"{base_url}/synthesize",
        json={"text": text, "language": language},
        timeout=600,
    )
    if response.status_code != 200:
        sys.exit(f"Error {response.status_code}: {response.text}")
    with open(out_path, "wb") as out:
        out.write(response.content)
    print(f"Wrote {len(response.content)} bytes to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_stt = subparsers.add_parser("transcribe", help="Batch speech-to-text")
    p_stt.add_argument("audio", help="Path to an audio file")
    p_stt.add_argument("--language", choices=["en", "he", "ar"], default=None)

    p_tts = subparsers.add_parser("synthesize", help="Text-to-speech")
    p_tts.add_argument("text", help="Text to speak")
    p_tts.add_argument("--language", choices=["en", "he", "ar"], required=True)
    p_tts.add_argument("--out", default="speech.mp3", help="Output audio path")

    args = parser.parse_args()
    if args.command == "transcribe":
        transcribe(args.base_url, args.audio, args.language)
    else:
        synthesize(args.base_url, args.text, args.language, args.out)


if __name__ == "__main__":
    main()
