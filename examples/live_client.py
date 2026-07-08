#!/usr/bin/env python3
"""Example client for the live-transcription WebSocket.

Streams a WAV file to /api/v1/live-transcribe at real-time pace and
prints partial results in place and final results on their own lines.

The server expects PCM 16-bit, 16 kHz, mono. Convert any audio with:
    ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 input_16k.wav

Usage:
    python examples/live_client.py input_16k.wav --language he
    python examples/live_client.py input_16k.wav --language en \
        --url ws://localhost:8000/api/v1/live-transcribe

Requires:
    pip install websockets
"""

import argparse
import asyncio
import json
import sys
import wave

import websockets

CHUNK_MS = 100  # send 100 ms of audio per frame


async def receive_results(ws) -> None:
    try:
        async for message in ws:
            data = json.loads(message)
            kind = data.get("type")
            if kind == "partial":
                print(f"\r[partial] {data['text']}", end="", flush=True)
            elif kind == "final":
                print(f"\r[final]   {data['text']}")
            elif kind == "error":
                print(f"\n[error]   {data.get('message')}", file=sys.stderr)
    except websockets.ConnectionClosed:
        pass


async def stream_file(url: str, audio_path: str, language: str) -> None:
    with wave.open(audio_path, "rb") as wav_file:
        if (
            wav_file.getframerate() != 16000
            or wav_file.getnchannels() != 1
            or wav_file.getsampwidth() != 2
        ):
            sys.exit(
                "Audio must be 16 kHz, mono, 16-bit PCM WAV. Convert with:\n"
                f"  ffmpeg -i {audio_path} -ar 16000 -ac 1 -sample_fmt s16 out.wav"
            )
        frames_per_chunk = wav_file.getframerate() * CHUNK_MS // 1000

        async with websockets.connect(f"{url}?language={language}") as ws:
            receiver = asyncio.create_task(receive_results(ws))
            while chunk := wav_file.readframes(frames_per_chunk):
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_MS / 1000)  # real-time pacing
            await ws.send(json.dumps({"event": "stop"}))
            await receiver  # server sends the final result, then closes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", help="16 kHz mono 16-bit PCM WAV file")
    parser.add_argument("--language", choices=["en", "he", "ar"], required=True)
    parser.add_argument(
        "--url", default="ws://localhost:8000/api/v1/live-transcribe"
    )
    args = parser.parse_args()
    asyncio.run(stream_file(args.url, args.audio, args.language))


if __name__ == "__main__":
    main()
