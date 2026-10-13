"""Smoke and CLI tests for scripts in the scripts/ directory."""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"


def test_download_model_help():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "download_model.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (
        "Download HuggingFace / faster-whisper models" in result.stdout
        or "usage:" in result.stdout.lower()
    )


def test_generate_test_wav_help():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "generate_test_wav.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_record_and_benchmark_help():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "record_and_benchmark.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "benchmark" in result.stdout.lower()


def test_test_latency_help():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "test_latency.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "latency" in result.stdout.lower()


def test_compare_hebrew_models_help():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "compare_hebrew_models.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_test_latency_synthetic_audio_generation():
    from scripts.test_latency import generate_audio, generate_synthetic_pcm

    raw_pcm = generate_synthetic_pcm(duration_seconds=0.5, sample_rate=16000)
    assert len(raw_pcm) == int(0.5 * 16000 * 2)

    audio = generate_audio("בדיקה", force_synthetic=True)
    assert len(audio) > 0
