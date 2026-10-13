#!/usr/bin/env python3
# ruff: noqa: E402
"""Automated live-transcription latency benchmark.

Synthesizes a short Hebrew speech clip and streams it in real-time chunks
(16 kHz PCM, 100ms chunks) over the WebSocket, printing live updates and
measuring exact latency for partial and final results.
"""

import argparse
import asyncio
import json
import math
import os
import shutil
import struct
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


def generate_synthetic_pcm(
    duration_seconds: float = 3.0,
    sample_rate: int = 16000,
    freq: float = 440.0,
) -> bytes:
    """Generate 16-bit mono PCM test tone audio in memory."""
    total_samples = int(duration_seconds * sample_rate)
    samples = []
    for i in range(total_samples):
        # Sine wave with gentle envelope to avoid clicks
        env = min(1.0, i / 800.0, (total_samples - i) / 800.0)
        val = int(32767 * 0.25 * env * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.append(val)
    return struct.pack(f"<{len(samples)}h", *samples)


def generate_audio(phrase: str, force_synthetic: bool = False) -> bytes:
    """Generate audio bytes (16 kHz 16-bit mono raw PCM)."""
    if not force_synthetic and shutil.which("say") and shutil.which("afconvert"):
        aiff_path = DIR / "benchmark_speech.aiff"
        wav_path = DIR / "benchmark_speech.wav"
        try:
            subprocess.run(
                ["say", "-v", "Carmit", phrase, "-o", str(aiff_path)],
                check=True,
                capture_output=True,
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
                capture_output=True,
            )
            with open(wav_path, "rb") as f:
                return f.read()[44:]
        except Exception:
            pass
        finally:
            aiff_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)

    return generate_synthetic_pcm(duration_seconds=3.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/api/v1/live-transcribe?language=he",
        help="WebSocket transcription endpoint URL",
    )
    parser.add_argument(
        "--phrase",
        default="שלום לכולם, אנחנו בודקים כעת את מהירות התמלול והדיוק של המערכת בעברית.",
        help="Hebrew test phrase to synthesize",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Force using synthetic tone audio instead of macOS Carmit voice",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    print("=" * 65)
    print("⚡ Hebrew Live Transcription & Latency Test")
    print(f'🗣️  Phrase: "{args.phrase}"')
    print("=" * 65)

    pcm_data = generate_audio(args.phrase, force_synthetic=args.synthetic)
    total_seconds = len(pcm_data) / (16000 * 2)
    print(f"🎵 Audio duration: {total_seconds:.2f} seconds")
    print(f"🔌 Connecting to {args.url}...\n")

    chunk_size = 1600 * 2  # 100ms at 16kHz 16-bit mono = 3200 bytes
    latencies = []

    try:
        async with websockets.connect(args.url, ping_interval=None) as ws:

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
    except (OSError, websockets.exceptions.WebSocketException) as e:
        print(f"⚠️  Could not connect to WebSocket at {args.url}: {e}")
        print("   Make sure the speech-bridge server is running (./start_server.sh).")
        return

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
