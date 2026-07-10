#!/usr/bin/env python3
"""Live microphone → speech-bridge transcription client.

Captures audio from the default microphone and streams it to the
speech-bridge WebSocket endpoint for real-time transcription. Silent
chunks are filtered client-side, and a freshness-aware drain ensures
the transcription stays live even during network hiccups.

The server expects PCM 16-bit, 16 kHz, mono — sounddevice captures
directly in that format, so no conversion is needed.

Usage:
    python examples/mic_live_client.py --language en
    python examples/mic_live_client.py --language he --reconcile
    python examples/mic_live_client.py --language ar \
        --url ws://my-server:8000/api/v1/live-transcribe

Requires:
    pip install sounddevice websockets numpy
"""

import argparse
import asyncio
import io
import json
import sys
import wave
from collections import deque

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes (int16)
CHANNELS = 1
CHUNK_MS = 100
FRAMES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000  # 1600 samples
BYTES_PER_CHUNK = FRAMES_PER_CHUNK * SAMPLE_WIDTH   # 3200 bytes


def pcm16_rms(pcm: bytes) -> float:
    if len(pcm) % 2:
        pcm = pcm[:-1]
    if not pcm:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples**2)))


def wrap_pcm16_as_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


async def receive_results(ws: websockets.WebSocketClientProtocol) -> None:
    try:
        async for message in ws:
            data = json.loads(message)
            kind = data.get("type")
            if kind == "partial":
                print(f"\r\033[K[partial] {data['text']}", end="", flush=True)
            elif kind == "final":
                print(f"\r\033[K[final]   {data['text']}")
            elif kind == "error":
                print(f"\n[error]   {data.get('message')}", file=sys.stderr)
    except websockets.ConnectionClosed:
        pass


async def reconcile(
    url: str,
    wav_data: bytes,
    language: str,
    api_key: str | None,
) -> None:
    import httpx

    print("\n--- Reconciliation: sending full recording to batch endpoint ---")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            headers=headers,
            params={"language": language},
            files={"file": ("recording.wav", wav_data, "audio/wav")},
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"[reconciled] {result.get('text', '')}")
        else:
            print(
                f"[reconcile error] {resp.status_code}: {resp.text}",
                file=sys.stderr,
            )


async def stream_microphone(args: argparse.Namespace) -> None:
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"\n[audio] {status}", file=sys.stderr)
        loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(indata))

    silence_threshold = args.silence_threshold
    flush_chunks = max(1, int(args.flush_after_silence * 1000 / CHUNK_MS))
    max_lag_chunks = max(1, int(args.max_lag * 1000 / CHUNK_MS))
    keep_chunks = max(1, int(1.0 * 1000 / CHUNK_MS))  # keep ~1s on drop

    recording_buf = bytearray() if args.reconcile else None
    consecutive_silent = 0
    flush_sent = False
    stats_dropped = 0

    connect_url = f"{args.url}?language={args.language}"
    if args.api_key:
        connect_url += f"&api_key={args.api_key}"

    print(f"Connecting to {args.url} (language={args.language}) ...")
    print("Speak into your microphone. Press Ctrl+C to stop.\n")

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=FRAMES_PER_CHUNK,
        dtype="int16",
        channels=CHANNELS,
        callback=audio_callback,
    )

    async with websockets.connect(connect_url) as ws:
        receiver = asyncio.create_task(receive_results(ws))
        stream.start()
        try:
            while True:
                chunk = await audio_queue.get()

                pending: deque[bytes] = deque()
                pending.append(chunk)
                while not audio_queue.empty():
                    try:
                        pending.append(audio_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if len(pending) > max_lag_chunks:
                    dropped = len(pending) - keep_chunks
                    stats_dropped += dropped
                    if recording_buf is not None:
                        for c in list(pending)[:dropped]:
                            recording_buf.extend(c)
                    fresh = deque(list(pending)[-keep_chunks:])
                    pending = fresh

                for pcm_chunk in pending:
                    if recording_buf is not None:
                        recording_buf.extend(pcm_chunk)

                    if pcm16_rms(pcm_chunk) < silence_threshold:
                        consecutive_silent += 1
                        if consecutive_silent >= flush_chunks and not flush_sent:
                            await ws.send(json.dumps({"event": "flush"}))
                            flush_sent = True
                        continue

                    consecutive_silent = 0
                    flush_sent = False
                    await ws.send(pcm_chunk)

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            stream.stop()
            stream.close()
            try:
                await ws.send(json.dumps({"event": "stop"}))
            except websockets.ConnectionClosed:
                pass

            try:
                await asyncio.wait_for(receiver, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                receiver.cancel()

            print()
            if stats_dropped:
                dropped_sec = stats_dropped * CHUNK_MS / 1000
                print(
                    f"[info] Dropped {dropped_sec:.1f}s of stale audio "
                    f"to maintain liveness."
                )

            if recording_buf is not None and len(recording_buf) > 0:
                wav_data = wrap_pcm16_as_wav(bytes(recording_buf))
                await reconcile(
                    args.reconcile_url,
                    wav_data,
                    args.language,
                    args.api_key,
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream microphone audio to speech-bridge for live transcription."
    )
    parser.add_argument(
        "--language", choices=["en", "he", "ar"], required=True,
        help="Transcription language.",
    )
    parser.add_argument(
        "--url", default="ws://localhost:8000/api/v1/live-transcribe",
        help="WebSocket endpoint URL.",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key when the server has ENABLE_AUTH=true.",
    )
    parser.add_argument(
        "--silence-threshold", type=int, default=300,
        help="int16 RMS below which a chunk is treated as silence (default: 300).",
    )
    parser.add_argument(
        "--flush-after-silence", type=float, default=0.5,
        help="Seconds of silence before flushing the server buffer (default: 0.5).",
    )
    parser.add_argument(
        "--max-lag", type=float, default=2.0,
        help="Max seconds of audio backlog before dropping old chunks (default: 2.0).",
    )
    parser.add_argument(
        "--reconcile", action="store_true",
        help="Record all audio and send to batch endpoint at session end "
             "for a complete transcript.",
    )
    parser.add_argument(
        "--reconcile-url", default="http://localhost:8000/api/v1/transcribe",
        help="Batch STT endpoint for reconciliation.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(stream_microphone(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
