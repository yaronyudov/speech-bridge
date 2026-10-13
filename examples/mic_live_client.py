#!/usr/bin/env python3
"""Live microphone → speech-bridge transcription client.

Captures audio from the default microphone and streams it to the
speech-bridge WebSocket endpoint for real-time transcription. Silent
chunks are filtered client-side, and a freshness-aware drain ensures
the transcription stays live even during network hiccups.

The server expects PCM 16-bit, 16 kHz, mono — sounddevice captures
directly in that format, so no conversion is needed.

Usage:
    python examples/mic_live_client.py --language he -o transcript.txt
    python examples/mic_live_client.py --language he --reconcile -o transcript.txt
    python examples/mic_live_client.py --language ar \
        --url ws://my-server:8000/api/v1/live-transcribe

Requires:
    pip install sounddevice websockets numpy
"""

import argparse
import asyncio
import io
import json
import shutil
import sys
import wave
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None
import websockets

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # bytes (int16)
CHANNELS = 1
CHUNK_MS = 100
FRAMES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000  # 1600 samples
BYTES_PER_CHUNK = FRAMES_PER_CHUNK * SAMPLE_WIDTH  # 3200 bytes


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


def format_terminal_line(tag: str, text: str, is_rtl: bool) -> str:
    """Format terminal output line. If language is RTL, applies BiDi shaping and pushes text to the right margin."""
    if not is_rtl:
        return f"{tag} {text}" if text else tag
    disp = text
    try:
        from bidi.algorithm import get_display

        disp = get_display(text)
    except ImportError:
        pass
    cols = shutil.get_terminal_size((80, 24)).columns
    pad = cols - len(tag) - len(disp) - 2
    if pad > 0:
        return f"{tag}{' ' * pad}{disp}"
    return f"{disp}  {tag}".rjust(cols)


async def receive_results(
    ws: Any,
    output_path: str | None = None,
    state: dict[str, Any] | None = None,
    language: str = "en",
) -> None:
    out_file = None
    is_he = language in ("he", "iw")
    is_rtl = language in ("he", "iw", "ar")
    try:
        from bidi.algorithm import get_display

        tag_partial = f"[{get_display('מתמלל')}" if is_he else "[partial"
        tag_final = f"[{get_display('סופי')}" if is_he else "[final"
    except ImportError:
        tag_partial = "[מתמלל" if is_he else "[partial"
        tag_final = "[סופי" if is_he else "[final"
    rlm = "\u200f" if is_rtl else ""

    if output_path:
        out_file = open(output_path, "a", encoding="utf-8")
        label = "תמליל נשמר ב:" if is_he else "Live transcripts saving to:"
        print(f"[file] {label} {output_path}")
    try:
        async for message in ws:
            data = json.loads(message)
            kind = data.get("type")
            lat_str = f" ({int(data['latency_ms'])}ms)" if "latency_ms" in data else ""
            if kind == "partial":
                if state is not None:
                    state["has_partial"] = True
                tag = f"{tag_partial}{lat_str}]"
                line = format_terminal_line(tag, data.get("text", ""), is_rtl)
                print(f"\r\033[K{line}", end="", flush=True)
            elif kind == "final":
                if state is not None:
                    state["has_partial"] = False
                text = data.get("text", "").strip()
                tag = f"{tag_final}{lat_str}]"
                line = format_terminal_line(tag, text, is_rtl)
                print(f"\r\033[K{line}")
                if out_file and text:
                    out_file.write(f"{rlm}{text}\n")
                    out_file.flush()
            elif kind == "error":
                print(f"\n[error]   {data.get('message')}", file=sys.stderr)
    except websockets.ConnectionClosed:
        pass
    finally:
        if out_file:
            out_file.close()


async def reconcile(
    url: str,
    wav_data: bytes,
    language: str,
    api_key: str | None,
    output_path: str | None = None,
) -> None:
    import httpx

    is_he = language == "he"
    rec_msg = (
        "\n--- סנכרון סופי: שולח את כל ההקלטה לדיוק מקסימלי ---"
        if is_he
        else "\n--- Reconciliation: sending full recording to batch endpoint ---"
    )
    print(rec_msg)
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        timeout = httpx.Timeout(300.0, connect=30.0, read=300.0, write=300.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers=headers,
                params={"language": language},
                files={"audio": ("recording.wav", wav_data, "audio/wav")},
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("text", "")
                tag = "[תמלול סופי]" if is_he else "[reconciled]"
                is_rtl = language in ("he", "iw", "ar")
                print(format_terminal_line(tag, text, is_rtl))
                if output_path and text:
                    rlm = "\u200f" if is_rtl else ""
                    header = (
                        "\n--- תמלול מלא מדויק (Reconciled) ---\n"
                        if is_he
                        else "\n--- Reconciled Full Transcript ---\n"
                    )
                    with open(output_path, "a", encoding="utf-8") as f:
                        f.write(f"{header}{rlm}{text}\n")
            else:
                print(
                    f"[reconcile error] {resp.status_code}: {resp.text}",
                    file=sys.stderr,
                )
    except httpx.TimeoutException:
        print(
            "[reconcile] Timed out waiting for batch reconciliation (audio was still saved to file).",
            file=sys.stderr,
        )
    except Exception as exc:
        print(
            f"[reconcile warning] Reconciliation request failed: {exc}", file=sys.stderr
        )


def resolve_audio_output_path(
    output_path: str | None,
    audio_output: str | None,
    no_save_audio: bool,
) -> Path | None:
    if no_save_audio:
        return None
    if audio_output:
        return Path(audio_output)
    if output_path:
        p = Path(output_path)
        return p.parent / f"{p.stem}_voice_org.wav"
    return None


async def stream_microphone(args: argparse.Namespace) -> None:
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"\n[audio] {status}", file=sys.stderr)
        loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(indata))

    audio_save_path = resolve_audio_output_path(
        args.output,
        args.audio_output,
        args.no_save_audio,
    )

    silence_threshold = args.silence_threshold
    flush_chunks = max(1, int(args.flush_after_silence * 1000 / CHUNK_MS))
    max_lag_chunks = max(1, int(args.max_lag * 1000 / CHUNK_MS))
    keep_chunks = max(1, int(1.0 * 1000 / CHUNK_MS))  # keep ~1s on drop

    recording_buf = (
        bytearray() if (args.reconcile or audio_save_path is not None) else None
    )
    consecutive_silent = 0
    flush_sent = False
    stats_dropped = 0

    connect_url = f"{args.url}?language={args.language}"
    if args.api_key:
        connect_url += f"&api_key={args.api_key}"

    print(f"Connecting to {args.url} (language={args.language}) ...")
    if args.output:
        print(f"📄 Transcription text output: {args.output}")
    if audio_save_path:
        print(f"🎙️  Original voice audio output: {audio_save_path}")
    print("Speak into your microphone. Press Ctrl+C to stop.\n")

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=FRAMES_PER_CHUNK,
        dtype="int16",
        channels=CHANNELS,
        callback=audio_callback,
    )

    state: dict[str, Any] = {"has_partial": False}
    last_meter_time = 0.0

    try:
        async with websockets.connect(connect_url, ping_interval=None) as ws:
            receiver = asyncio.create_task(
                receive_results(ws, args.output, state, language=args.language)
            )
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

                        rms = pcm16_rms(pcm_chunk)

                        # Dynamic microphone audio meter (gives live visual proof that mic is hearing sound)
                        now = loop.time()
                        if now - last_meter_time > 0.15:
                            last_meter_time = now
                            if not state.get("has_partial", False):
                                bars = "  ▂▃▄▅▆▇█"
                                bar_idx = min(len(bars) - 1, int(rms / 40))
                                meter = bars[bar_idx] * 4
                                if args.language in ("he", "iw"):
                                    line = format_terminal_line(
                                        f"[מיק {meter}]",
                                        f"מקשיב (עוצמה: {int(rms)})...",
                                        True,
                                    )
                                    print(f"\r\033[K{line}", end="", flush=True)
                                else:
                                    print(
                                        f"\r\033[K[mic {meter}] Listening (RMS: {int(rms)})...",
                                        end="",
                                        flush=True,
                                    )

                        # Silence detection:
                        # When silence_threshold is 0 (default), all audio is streamed to the server.
                        # A threshold of 120 is used purely to trigger flush after natural pauses.
                        is_quiet = rms < (
                            silence_threshold if silence_threshold > 0 else 120
                        )
                        if is_quiet:
                            consecutive_silent += 1
                            if consecutive_silent >= flush_chunks and not flush_sent:
                                await ws.send(json.dumps({"event": "flush"}))
                                flush_sent = True
                            if silence_threshold > 0:
                                continue
                        else:
                            consecutive_silent = 0
                            flush_sent = False

                        await ws.send(pcm_chunk)

            except (
                KeyboardInterrupt,
                asyncio.CancelledError,
                websockets.exceptions.ConnectionClosed,
            ):
                pass
            finally:
                stream.stop()
                stream.close()
                try:
                    await ws.send(json.dumps({"event": "stop"}))
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(receiver, timeout=5.0)
                except (TimeoutError, asyncio.CancelledError, Exception):
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
                    if audio_save_path is not None:
                        audio_save_path.parent.mkdir(parents=True, exist_ok=True)
                        audio_save_path.write_bytes(wav_data)
                        print(
                            f"[audio] Saved original voice recording ({len(wav_data):,} bytes) to: {audio_save_path}"
                        )
                    if args.reconcile:
                        try:
                            await reconcile(
                                args.reconcile_url,
                                wav_data,
                                args.language,
                                args.api_key,
                                args.output,
                            )
                        except (KeyboardInterrupt, asyncio.CancelledError):
                            print("\n[reconcile] Reconciliation skipped by user.")
    except (ConnectionRefusedError, OSError, websockets.exceptions.InvalidURI) as err:
        print(
            f"\n❌ Could not connect to server at {args.url}: {err}\n"
            f"💡 Make sure the speech-bridge server is running first with: ./start_server.sh\n",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream microphone audio to speech-bridge for live transcription."
    )
    parser.add_argument(
        "--language",
        choices=["en", "he", "ar"],
        required=True,
        help="Transcription language.",
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/api/v1/live-transcribe",
        help="WebSocket endpoint URL.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key when the server has ENABLE_AUTH=true.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="File path to save the transcription to (e.g., transcript.txt).",
    )
    parser.add_argument(
        "--audio-output",
        default=None,
        help="File path to save original voice recording (defaults to {output_stem}_voice_org.wav).",
    )
    parser.add_argument(
        "--no-save-audio",
        action="store_true",
        help="Disable saving the original voice recording.",
    )
    parser.add_argument(
        "--silence-threshold",
        type=int,
        default=0,
        help="int16 RMS below which a chunk is treated as silence (default: 0 = stream all audio, recommended).",
    )
    parser.add_argument(
        "--flush-after-silence",
        type=float,
        default=1.5,
        help="Seconds of silence before flushing the server buffer (default: 1.5).",
    )
    parser.add_argument(
        "--max-lag",
        type=float,
        default=2.0,
        help="Max seconds of audio backlog before dropping old chunks (default: 2.0).",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Record all audio and send to batch endpoint at session end "
        "for a complete transcript.",
    )
    parser.add_argument(
        "--reconcile-url",
        default="http://localhost:8000/api/v1/transcribe",
        help="Batch STT endpoint for reconciliation.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(stream_microphone(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopped.")


if __name__ == "__main__":
    main()
