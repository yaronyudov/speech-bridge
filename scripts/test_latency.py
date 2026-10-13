#!/usr/bin/env python3
# ruff: noqa: E402
"""Automated live-transcription latency benchmark.

Synthesizes a short Hebrew speech clip and streams it in real-time chunks
(16 kHz PCM, 100ms chunks) over the WebSocket, printing live updates and
measuring exact latency for partial and final results.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
ROOT_DIR = DIR.parent
VENV_PY = ROOT_DIR / ".venv" / "bin" / "python"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if sys.executable != str(VENV_PY) and VENV_PY.exists():
    os.execv(str(VENV_PY), [str(VENV_PY), __file__] + sys.argv[1:])

import websockets


async def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return

    test_phrase = (
        "שלום לכולם, אנחנו בודקים כעת את מהירות התמלול והדיוק של המערכת בעברית."
    )
    print("=" * 65)
    print("⚡ Hebrew Live Transcription & Latency Test")
    print(f'🗣️  Phrase: "{test_phrase}"')
    print("=" * 65)

    # 1. Generate clean audio using macOS Carmit voice
    aiff_path = DIR / "benchmark_speech.aiff"
    wav_path = DIR / "benchmark_speech.wav"
    try:
        subprocess.run(
            ["say", "-v", "Carmit", test_phrase, "-o", str(aiff_path)], check=True
        )
        subprocess.run(
            [
                "afconvert",
                "-f",
                "WAVE",
                "-d",
                "LEI16@16000",
                "-c",
                "1",
                str(aiff_path),
                str(wav_path),
            ],
            check=True,
        )

        with open(wav_path, "rb") as f:
            # Skip 44-byte WAV header to get raw PCM 16-bit
            pcm_data = f.read()[44:]
    finally:
        aiff_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)

    total_seconds = len(pcm_data) / (16000 * 2)
    print(f"🎵 Audio duration: {total_seconds:.2f} seconds")
    print(
        "🔌 Connecting to ws://localhost:8000/api/v1/live-transcribe (language=he)...\n"
    )

    chunk_size = 1600 * 2  # 100ms at 16kHz 16-bit mono = 3200 bytes
    latencies = []

    async with websockets.connect(
        "ws://localhost:8000/api/v1/live-transcribe?language=he", ping_interval=None
    ) as ws:

        async def receiver():
            async for msg in ws:
                data = json.loads(msg)
                kind = data.get("type")
                lat = data.get("latency_ms")
                if lat is not None:
                    latencies.append(lat)
                lat_str = f" [latency: {int(lat)}ms]" if lat is not None else ""

                if kind == "partial":
                    print(f"⏳ [partial{lat_str}] {data.get('text', '')}")
                elif kind == "final":
                    print(f"✅ [final  {lat_str}]   {data.get('text', '')}")

        rec_task = asyncio.create_task(receiver())

        # Stream audio in real-time (100ms sleep between chunks)
        print("🎙️  Streaming audio in real-time (100ms intervals)...")
        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i : i + chunk_size]
            await ws.send(chunk)
            await asyncio.sleep(0.1)

        # Send flush to finalize
        await ws.send(json.dumps({"event": "flush"}))
        for _ in range(60):
            if latencies:
                await asyncio.sleep(0.5)
                break
            await asyncio.sleep(0.1)
        await ws.send(json.dumps({"event": "stop"}))
        try:
            await asyncio.wait_for(rec_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    print("\n" + "=" * 65)
    print("📊 Latency Benchmark Results:")
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        print(f"   • Passes recorded:   {len(latencies)}")
        print(f"   • Average latency:   {avg_lat:.0f} ms")
        print(f"   • Fastest latency:   {min_lat:.0f} ms")
        print(f"   • Peak latency:      {max_lat:.0f} ms")
    else:
        print("   No inference latency events recorded.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
