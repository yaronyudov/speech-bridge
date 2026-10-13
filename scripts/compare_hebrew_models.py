#!/usr/bin/env python3
# ruff: noqa: E402
"""Ivrit-AI & Whisper Hebrew Models Benchmark & Test Client.

Tests and benchmarks candidate models for Hebrew speech recognition:
1. ivrit-ai/whisper-large-v3-turbo-ct2  (Turbo: 4 dec layers, SOTA Hebrew, fast CPU)
2. ivrit-ai/whisper-large-v3-ct2        (Large-v3: 32 dec layers, maximum vocabulary capacity)
3. ivrit-ai/faster-whisper-v2-d4        (Distilled v2-d4: Hebrew fine-tuned distillation)
4. Systran/faster-whisper-large-v3      (OpenAI Large-v3: generic multilingual)
5. Systran/faster-whisper-small         (OpenAI Small: generic multilingual)

Modes:
- Benchmark: Run comparison on an audio file (e.g., transcript_voice_org.wav)
- Live Stream: Speak into microphone and see live RTL streaming
- Record & Test: Record N seconds from microphone and benchmark
"""

import argparse
import concurrent.futures
import os
import shutil
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_PY = ROOT_DIR / ".venv" / "bin" / "python"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if sys.executable != str(VENV_PY) and VENV_PY.exists():
    os.execv(str(VENV_PY), [str(VENV_PY), __file__] + sys.argv[1:])

import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None
import soundfile as sf
from faster_whisper import WhisperModel

MODELS = {
    "turbo": {
        "id": "ivrit-ai/whisper-large-v3-turbo-ct2",
        "name": "Ivrit-AI Large-v3-Turbo",
        "type": "Hebrew SOTA (Fine-tuned)",
        "size": "~1.6 GB",
        "desc": "4 decoder layers — SOTA Hebrew accuracy, 6.6x faster than real-time on CPU",
    },
    "large-v3": {
        "id": "ivrit-ai/whisper-large-v3-ct2",
        "name": "Ivrit-AI Large-v3",
        "type": "Hebrew SOTA (Fine-tuned)",
        "size": "~3.1 GB",
        "desc": "32 decoder layers — Full capacity Hebrew acoustic & language model",
    },
    "v2-d4": {
        "id": "ivrit-ai/faster-whisper-v2-d4",
        "name": "Ivrit-AI Distilled v2-d4",
        "type": "Hebrew (Distilled v2)",
        "size": "~3.0 GB",
        "desc": "Distilled 4 decoder layers of Hebrew Whisper v2",
    },
    "generic-large": {
        "id": "Systran/faster-whisper-large-v3",
        "name": "OpenAI Whisper Large-v3",
        "type": "Generic Multilingual",
        "size": "~3.1 GB",
        "desc": "OpenAI Large-v3 multilingual base (not specialized on Israeli Hebrew)",
    },
    "generic-small": {
        "id": "Systran/faster-whisper-small",
        "name": "OpenAI Whisper Small",
        "type": "Generic Multilingual",
        "size": "~460 MB",
        "desc": "OpenAI Small — fast on CPU, but prone to Hebrew hallucinations",
    },
}

PROMPT_HE = "תמלול שיחה ופגישה בעברית תקנית."


def format_hebrew_line(
    text: str, tag: str = "", right_align: bool = True, bidi_reverse: bool = True
) -> str:
    """Format Hebrew text for terminal display with automatic Right-To-Left layout."""
    if not text:
        return ""
    disp = text
    if bidi_reverse:
        try:
            from bidi.algorithm import get_display

            disp = get_display(text)
        except ImportError:
            pass
    if not right_align:
        return f"{tag} {disp}" if tag else disp

    cols = shutil.get_terminal_size((80, 24)).columns
    if tag:
        pad = cols - len(tag) - len(disp) - 2
        if pad > 0:
            return f"{tag}{' ' * pad}{disp}"
        return f"{tag} {disp}"
    return disp.rjust(cols)


def load_model(model_key: str, threads: int = 8) -> tuple[WhisperModel, float]:
    info = MODELS[model_key]
    print(f"\n📦 Loading [{model_key}]: {info['name']} ({info['size']})...")
    t0 = time.time()
    model = WhisperModel(
        info["id"],
        device="cpu",
        compute_type="int8",
        cpu_threads=threads,
    )
    load_time = time.time() - t0
    print(f"   ✅ Loaded in {load_time:.2f}s ({threads} CPU threads)")
    return model, load_time


def benchmark_batch(model: WhisperModel, audio: np.ndarray, sr: int) -> dict:
    t0 = time.time()
    segs, _ = model.transcribe(
        audio,
        language="he",
        beam_size=1,
        initial_prompt=PROMPT_HE,
        vad_filter=True,
    )
    transcript = " ".join(s.text.strip() for s in segs)
    elapsed = time.time() - t0
    audio_dur = len(audio) / sr
    rtf = elapsed / audio_dur if audio_dur > 0 else 0.0
    return {
        "text": transcript,
        "elapsed": elapsed,
        "duration": audio_dur,
        "rtf": rtf,
    }


def simulate_streaming(
    model: WhisperModel,
    audio: np.ndarray,
    sr: int,
    chunk_sec: float = 3.0,
    right_align: bool = True,
    bidi_reverse: bool = True,
) -> float:
    print(f"\n⚡ Simulated Real-Time Streaming (chunk: {chunk_sec:.1f}s, RTL layout):")
    print("-" * 80)
    step_samples = int(chunk_sec * sr)
    accum = np.array([], dtype=np.float32)
    latencies = []

    for i in range(0, len(audio), step_samples):
        chunk = audio[i : i + step_samples]
        accum = np.concatenate([accum, chunk])
        curr_time = (i + len(chunk)) / sr

        t0 = time.time()
        segs, _ = model.transcribe(
            accum,
            language="he",
            beam_size=1,
            initial_prompt=PROMPT_HE,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        texts = [s.text.strip() for s in segs if s.text.strip()]
        dt = (time.time() - t0) * 1000
        latencies.append(dt)

        preview = " ".join(texts)
        if preview:
            tag = f"[{curr_time:4.1f}s | {dt:4.0f}ms]"
            formatted = format_hebrew_line(
                preview, tag=tag, right_align=right_align, bidi_reverse=bidi_reverse
            )
            print(formatted)

        if any(preview.rstrip().endswith(p) for p in (".", "?", "!")) or len(
            accum
        ) > int(8.0 * sr):
            accum = np.array([], dtype=np.float32)

    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print("-" * 80)
    print(f"   • Average Chunk Latency: {avg_lat:.0f} ms")
    return avg_lat


def run_benchmark_matrix(
    audio: np.ndarray,
    sr: int,
    model_keys: list[str],
    run_stream_sim: bool = False,
    right_align: bool = True,
    bidi_reverse: bool = True,
):
    audio_dur = len(audio) / sr
    print("=" * 82)
    print(
        f"🇮🇱 Hebrew Models Side-by-Side Benchmark (Audio: {audio_dur:.2f}s, ~{int(audio_dur / 60)}m{int(audio_dur % 60)}s)"
    )
    print("=" * 82)

    results = {}
    for key in model_keys:
        m, load_time = load_model(key)
        avg_chunk_lat = None
        if run_stream_sim:
            avg_chunk_lat = simulate_streaming(
                m, audio, sr, right_align=right_align, bidi_reverse=bidi_reverse
            )
        batch_res = benchmark_batch(m, audio, sr)
        batch_res["load_time"] = load_time
        batch_res["avg_chunk_lat"] = avg_chunk_lat
        results[key] = batch_res
        del m  # immediately free memory to prevent RAM pressure

    print("\n" + "=" * 82)
    print("📊 BENCHMARK COMPARISON MATRIX (Sorted by Speed & Accuracy)")
    print("=" * 82)
    header = f"{'Model Key':<14} {'Model Name':<25} {'Size':<9} {'Batch':<10} {'Speed':<12} {'RTF':<8}"
    if run_stream_sim:
        header += f" {'Latency':<10}"
    print(header)
    print("-" * 82)

    for key in model_keys:
        r = results[key]
        info = MODELS[key]
        speedup = f"{1 / r['rtf']:.1f}x real-time" if r["rtf"] > 0 else "N/A"
        elapsed_str = f"{r['elapsed']:.2f}s"
        rtf_str = f"{r['rtf']:.2f}x"
        row = f"{key:<14} {info['name'][:24]:<25} {info['size']:<9} {elapsed_str:<10} {speedup:<12} {rtf_str:<8}"
        if run_stream_sim:
            lat_str = (
                f"{r['avg_chunk_lat']:.0f} ms" if r.get("avg_chunk_lat") else " --"
            )
            row += f" {lat_str:<10}"
        print(row)
    print("-" * 82)

    print("\n" + "=" * 82)
    print("📝 HEBREW TRANSCRIPT RESULTS (Right-To-Left Terminal View):")
    print("=" * 82)
    for key in model_keys:
        info = MODELS[key]
        r = results[key]
        print(f"\n🔹 [{key}] {info['name']} — {info['type']} ({r['elapsed']:.2f}s):")
        print("   " + "-" * 76)
        formatted = format_hebrew_line(
            r["text"], right_align=right_align, bidi_reverse=bidi_reverse
        )
        print(formatted)
    print("\n" + "=" * 82)


def record_microphone(seconds: int = 10, sr: int = 16000) -> np.ndarray:
    if sd is None:
        raise RuntimeError(
            "sounddevice or PortAudio library is not available on this system."
        )
    print(f"\n🎙️  Recording {seconds} seconds from microphone...")
    print("   🗣️  Speak now in Hebrew...")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32")
    for sec in range(seconds, 0, -1):
        print(f"\r   ⏳ {sec}s remaining...", end="", flush=True)
        time.sleep(1.0)
    sd.wait()
    print("\r   ✅ Recording complete!              ")
    return audio.flatten()


def compute_rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2))) * 32767


def rms_bars(rms: float) -> str:
    bars = "  ▂▃▄▅▆▇█"
    bar_idx = min(len(bars) - 1, int(rms / 45))
    return bars[bar_idx] * 4


def live_mic_loop(
    model_key: str,
    right_align: bool = True,
    bidi_reverse: bool = True,
    english_tags: bool = False,
):
    if sd is None:
        raise RuntimeError(
            "sounddevice or PortAudio library is not available on this system."
        )
    m, _ = load_model(model_key)
    sr = 16000
    accum = np.array([], dtype=np.float32)

    print("\n" + "=" * 65)
    print(f"🎤 Live Mic Streaming with [{MODELS[model_key]['name']}]")
    print("🗣️  Speak into your microphone in Hebrew. Press Ctrl+C to exit.")
    print("=" * 65 + "\n")

    audio_queue = []

    def callback(indata, frames, time_info, status):
        audio_queue.append(indata.copy())

    # Format labels inside brackets
    lbl_live = "LIVE"
    if english_tags:
        lbl_final = "FINAL"
        lbl_listen = "Listening..."
    else:
        try:
            from bidi.algorithm import get_display

            lbl_final = get_display("סופי") if bidi_reverse else "סופי"
            lbl_listen = (
                get_display("מקשיב לקול...") if bidi_reverse else "מקשיב לקול..."
            )
        except ImportError:
            lbl_final, lbl_listen = "סופי", "מקשיב לקול..."

    stream = sd.InputStream(
        samplerate=sr, channels=1, dtype="float32", callback=callback, blocksize=1600
    )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = None

    current_text = ""
    last_dt = 0.0
    last_infer_time = 0.0
    silence_frames = 0
    consecutive_empty = 0

    def run_whisper_task(audio_data: np.ndarray):
        t0 = time.time()
        segs, _ = m.transcribe(
            audio_data,
            language="he",
            beam_size=1,
            initial_prompt=PROMPT_HE,
            vad_filter=False,
        )
        dt = (time.time() - t0) * 1000
        text = " ".join(s.text.strip() for s in segs)
        return text, dt

    with stream:
        try:
            while True:
                time.sleep(0.05)  # 20 FPS refresh rate for continuous live UI

                # Ingest captured audio
                if audio_queue:
                    new_data = np.concatenate(audio_queue).flatten()
                    audio_queue.clear()
                    accum = np.concatenate([accum, new_data])

                recent_chunk = (
                    accum[-int(0.2 * sr) :] if len(accum) >= int(0.2 * sr) else accum
                )
                rms = compute_rms(recent_chunk)
                meter = rms_bars(rms)

                # Silence tracking
                if rms < 100:
                    silence_frames += 1
                else:
                    silence_frames = 0

                now = time.time()

                # Check if background inference completed
                if future is not None and future.done():
                    try:
                        text, dt = future.result()
                        last_dt = dt
                        if text:
                            current_text = text
                            consecutive_empty = 0
                        else:
                            consecutive_empty += 1
                    except Exception:
                        pass
                    future = None

                # Trigger new inference if idle and we have enough speech (>= 0.6s)
                if (
                    future is None
                    and len(accum) >= int(0.6 * sr)
                    and (now - last_infer_time >= 0.38)
                ):
                    last_infer_time = now
                    future = executor.submit(run_whisper_task, accum.copy())

                # Sentence boundary check: punctuation, long pause, or large buffer
                is_sentence_end = current_text and (
                    any(current_text.rstrip().endswith(p) for p in (".", "?", "!"))
                    or (silence_frames >= 14 and len(current_text) > 3)
                    or len(accum) > int(7.0 * sr)
                )

                if is_sentence_end:
                    final_tag = f"[{lbl_final} {last_dt:.0f}ms | RMS:{int(rms):3d}]"
                    print(
                        f"\r\033[K{format_hebrew_line(current_text, tag=final_tag, right_align=right_align, bidi_reverse=bidi_reverse)}"
                    )
                    current_text = ""
                    accum = accum[-int(0.4 * sr) :]
                    silence_frames = 0
                    consecutive_empty = 0
                    continue

                # Buffer trimming when silent for > 1.5s and no active text
                if silence_frames >= 22 and not current_text:
                    if len(accum) > int(0.4 * sr):
                        accum = accum[-int(0.4 * sr) :]

                # RENDER CONTINUOUS LIVE STATUS LINE (NEVER STOPS, ALWAYS ANIMATED)
                if current_text:
                    live_tag = f"[🔴 {lbl_live} | MIC {meter} | RMS:{int(rms):3d} | {last_dt:.0f}ms]"
                    disp_body = current_text
                else:
                    live_tag = f"[🔴 {lbl_live} | MIC {meter} | RMS:{int(rms):3d}]"
                    disp_body = lbl_listen

                line = format_hebrew_line(
                    disp_body,
                    tag=live_tag,
                    right_align=right_align,
                    bidi_reverse=bidi_reverse if current_text else False,
                )
                print(f"\r\033[K{line}", end="", flush=True)

        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            executor.shutdown(wait=False)


def main():
    parser = argparse.ArgumentParser(
        description="Ivrit-AI & Whisper Hebrew Models Benchmark & Test Client"
    )
    parser.add_argument(
        "--model",
        choices=[
            "all",
            "ivrit",
            "both",
            "turbo",
            "large-v3",
            "v2-d4",
            "generic-large",
            "generic-small",
        ],
        default="all",
        help="Which model(s) to run: 'all' (all 5 models), 'ivrit' (all 3 Ivrit-AI models), 'both' (turbo + large-v3), or a specific model key (default: all)",
    )
    parser.add_argument(
        "--file",
        default="transcript_voice_org.wav",
        help="WAV file to benchmark against (default: transcript_voice_org.wav)",
    )
    parser.add_argument(
        "--record",
        type=int,
        default=0,
        help="Record N seconds from microphone before benchmarking",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live microphone streaming test directly with selected model",
    )
    parser.add_argument(
        "--stream-sim",
        action="store_true",
        help="Also simulate 3-second streaming chunks on every benchmarked model",
    )
    parser.add_argument(
        "--ltr",
        action="store_true",
        help="Disable automatic Right-To-Left right-alignment (force Left-to-Right left-margin output)",
    )
    parser.add_argument(
        "--en-tags",
        action="store_true",
        help="Use English bracket tags ([LIVE], [FINAL]) instead of Hebrew tags",
    )
    parser.add_argument(
        "--no-bidi",
        action="store_true",
        help="Disable automatic visual BiDi character reordering (only if terminal already reorders RTL natively)",
    )
    args = parser.parse_args()

    right_align = not args.ltr
    bidi_reverse = not args.no_bidi

    if args.live:
        model_key = "turbo" if args.model in ("all", "ivrit", "both") else args.model
        live_mic_loop(
            model_key,
            right_align=right_align,
            bidi_reverse=bidi_reverse,
            english_tags=args.en_tags,
        )
        return

    if args.record > 0:
        audio = record_microphone(args.record)
        sr = 16000
    else:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            sys.exit(1)
        audio, sr = sf.read(str(file_path))
        audio = audio.astype(np.float32)
        if len(audio.shape) > 1:
            audio = audio[:, 0]

    # Resolve target models
    if args.model == "all":
        target_keys = ["turbo", "large-v3", "v2-d4", "generic-large", "generic-small"]
    elif args.model == "ivrit":
        target_keys = ["turbo", "large-v3", "v2-d4"]
    elif args.model == "both":
        target_keys = ["turbo", "large-v3"]
    else:
        target_keys = [args.model]

    run_benchmark_matrix(
        audio,
        sr,
        target_keys,
        run_stream_sim=args.stream_sim,
        right_align=right_align,
        bidi_reverse=bidi_reverse,
    )


if __name__ == "__main__":
    main()
