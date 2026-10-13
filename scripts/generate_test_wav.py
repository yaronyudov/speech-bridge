#!/usr/bin/env python3
# ruff: noqa: E402
"""Generate a new 16 kHz Mono Hebrew WAV file for STT testing and benchmarking.

Supports two generation methods:
1. Synthetic Neural Speech: Generates realistic Hebrew meeting conversation audio using Edge Neural TTS or macOS Carmit.
2. Microphone Recording: Records N seconds from your physical microphone.

Usage:
    # 1. Generate default realistic Hebrew meeting conversation:
    ./generate_test_wav.py --output new_meeting.wav

    # 2. Generate with custom Hebrew text:
    ./generate_test_wav.py --text "שלום, זוהי בדיקה חדשה של מערכת התמלול בעברית." --output custom.wav

    # 3. Record 15 seconds from your microphone:
    ./generate_test_wav.py --record 15 --output my_speech.wav

    # 4. Generate AND immediately run the multi-model benchmark on it:
    ./generate_test_wav.py --run-tests
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent
ROOT_DIR = DIR.parent
VENV_PY = ROOT_DIR / ".venv" / "bin" / "python"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if sys.executable != str(VENV_PY) and VENV_PY.exists():
    os.execv(str(VENV_PY), [str(VENV_PY), __file__] + sys.argv[1:])

import sounddevice as sd
import soundfile as sf

DEFAULT_MEETING_SCRIPT = (
    "שלום לכולם, בוקר טוב. בואו נתחיל את ישיבת הצוות השבועית.\n"
    "הנושא הראשון הוא שדרוג התשתיות ושיפור הביצועים של המערכת.\n"
    "ראינו שיפור משמעותי בזמני התגובה, אך עדיין יש לבדוק את יציבות השרתים תחת עומס.\n"
    "מי יכול לעדכן לגבי בדיקות האיכות שתוכננו להיום?\n"
    "חשוב לוודא שהכל תקין לפני שמעלים את הגרסה החדשה לפרודקשן.\n"
    "תודה רבה לכולם, נמשיך לעדכון הבא."
)


async def synthesize_edge_tts(text: str, voice: str = "he-IL-AvriNeural") -> bytes:
    import edge_tts

    comm = edge_tts.Communicate(text, voice)
    mp3_chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3_chunks.append(chunk["data"])
    return b"".join(mp3_chunks)


def convert_mp3_to_16k_wav(mp3_bytes: bytes, output_path: Path):
    tmp_mp3 = output_path.with_suffix(".tmp.mp3")
    tmp_mp3.write_bytes(mp3_bytes)
    try:
        cmd = [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            str(tmp_mp3),
            str(output_path),
        ]
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    finally:
        tmp_mp3.unlink(missing_ok=True)


def record_from_microphone(seconds: int, output_path: Path, sr: int = 16000):
    print(f"\n🎙️  Recording {seconds} seconds from microphone to {output_path.name}...")
    print("🗣️  Speak into the microphone now in Hebrew...")
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32")
    for sec in range(seconds, 0, -1):
        print(f"\r   ⏳ {sec}s remaining...", end="", flush=True)
        time.sleep(1.0)
    sd.wait()
    print("\r   ✅ Recording complete!              ")
    sf.write(str(output_path), audio.flatten(), sr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Hebrew WAV audio for STT benchmarking"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="test_meeting_voice.wav",
        help="Output WAV path (default: test_meeting_voice.wav)",
    )
    parser.add_argument("--text", default=None, help="Custom Hebrew text to synthesize")
    parser.add_argument(
        "--voice",
        default="he-IL-AvriNeural",
        choices=["he-IL-AvriNeural", "he-IL-HilaNeural"],
        help="Edge TTS voice (default: he-IL-AvriNeural)",
    )
    parser.add_argument(
        "--record",
        type=int,
        default=0,
        help="Record N seconds from microphone instead of synthesizing",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Immediately run the full Hebrew models benchmark on the generated file",
    )
    args = parser.parse_args()

    out_file = Path(args.output).resolve()

    if args.record > 0:
        record_from_microphone(args.record, out_file)
    else:
        text = args.text.strip() if args.text else DEFAULT_MEETING_SCRIPT
        print("=" * 70)
        print("🔊 Synthesizing Realistic Hebrew Speech with Neural TTS...")
        print(f"🎙️  Voice: {args.voice}")
        print("📝 Script:")
        for line in text.splitlines():
            if line.strip():
                print(f"   {line.strip()}")
        print("=" * 70)

        t0 = time.time()
        mp3_data = asyncio.run(synthesize_edge_tts(text, voice=args.voice))
        convert_mp3_to_16k_wav(mp3_data, out_file)
        print(f"✅ Generated {out_file.name} in {time.time() - t0:.2f}s")

    # Inspect WAV
    data, sr = sf.read(str(out_file))
    dur = len(data) / sr
    print(
        f"🎵 Audio specs: {dur:.2f} seconds | {sr} Hz | 16-bit Mono WAV | {out_file.stat().st_size:,} bytes"
    )

    if args.run_tests:
        print("\n🚀 Launching Side-by-Side Model Benchmark on the new file...\n")
        cmd = [
            str(VENV_PY),
            str(DIR / "compare_hebrew_models.py"),
            "--model",
            "all",
            "--file",
            str(out_file),
        ]
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
