#!/usr/bin/env python3
# ruff: noqa: E402
"""Interactive Microphone Voice Recording & Hebrew Model Benchmark.

Allows the user to speak their own voice freely into the microphone:
1. Press Enter to start recording.
2. Speak naturally in Hebrew for as long as desired.
3. Press Enter to finish recording.
4. Automatically runs the 5-model benchmark suite on the recording and displays
   side-by-side results with Right-to-Left formatting.
"""

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

import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None
import soundfile as sf


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return

    sr = 16000
    output_path = ROOT_DIR / "my_voice.wav"

    print("=" * 70)
    print("🎙️  HEBREW VOICE BENCHMARK: DELIVER YOUR OWN VOICE")
    print("=" * 70)
    print("This will record your voice, save it as a clean 16 kHz WAV, and")
    print("benchmark all candidate models against what you said.\n")

    input("👉 Press [ENTER] to START recording...")
    print("\n" + "-" * 70)
    print("🔴 RECORDING... Speak now into your microphone in Hebrew!")
    print("👉 When you are finished speaking, press [ENTER] to STOP...")
    print("-" * 70)

    audio_chunks = []

    def callback(indata, frames, time_info, status):
        audio_chunks.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sr, channels=1, dtype="float32", callback=callback
    )
    t0 = time.time()
    with stream:
        try:
            input()
        except KeyboardInterrupt:
            pass

    dur = time.time() - t0
    print(f"\n⏹️  Recording stopped ({dur:.1f}s recorded).")

    if not audio_chunks:
        print("❌ No audio captured from microphone. Check microphone permissions.")
        sys.exit(1)

    audio = np.concatenate(audio_chunks).flatten()
    sf.write(str(output_path), audio, sr)
    print(
        f"💾 Saved to: {output_path.name} ({len(audio) / sr:.2f}s, {output_path.stat().st_size:,} bytes)"
    )

    print("\n" + "=" * 70)
    print("🚀 BENCHMARKING ALL MODELS ON YOUR VOICE...")
    print("=" * 70)

    cmd = [
        str(VENV_PY),
        str(DIR / "compare_hebrew_models.py"),
        "--model",
        "all",
        "--file",
        str(output_path),
    ]
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
