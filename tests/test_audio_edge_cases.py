"""Edge-case tests for speech_engine.core.audio utilities."""

import io
import os
import wave
from unittest.mock import patch

import numpy as np
import pytest

from speech_engine.core import audio
from speech_engine.core.exceptions import AudioProcessingError


def test_pcm16_to_float32_edge_cases():
    # Empty bytes
    empty = audio.pcm16_to_float32(b"")
    assert empty.size == 0
    assert empty.dtype == np.float32

    # Single odd byte
    odd = audio.pcm16_to_float32(b"\x00")
    assert odd.size == 0

    # Extremes: min int16 (-32768) and max int16 (32767)
    samples = np.array([-32768, 32767], dtype=np.int16)
    converted = audio.pcm16_to_float32(samples.tobytes())
    assert np.isclose(converted[0], -1.0)
    assert np.isclose(converted[1], 32767.0 / 32768.0)


def test_pcm16_rms_edge_cases():
    # Empty bytes
    assert audio.pcm16_rms(b"") == 0.0

    # Single odd byte (gets truncated to empty)
    assert audio.pcm16_rms(b"\x55") == 0.0

    # Three bytes (truncated to 2 bytes = 1 sample)
    one_sample = np.array([1000], dtype=np.int16).tobytes() + b"\xff"
    assert np.isclose(audio.pcm16_rms(one_sample), 1000.0)

    # Constant amplitude
    const_arr = np.full(100, 500, dtype=np.int16)
    assert np.isclose(audio.pcm16_rms(const_arr.tobytes()), 500.0)


def test_is_silence():
    loud = np.full(100, 1000, dtype=np.int16).tobytes()
    quiet = np.full(100, 50, dtype=np.int16).tobytes()

    assert not audio.is_silence(loud, rms_threshold=200)
    assert audio.is_silence(quiet, rms_threshold=200)
    assert audio.is_silence(b"", rms_threshold=1)


def test_wrap_pcm16_as_wav_custom_parameters():
    pcm = np.zeros(800, dtype=np.int16).tobytes()
    wav_bytes = audio.wrap_pcm16_as_wav(pcm, sample_rate=8000, channels=1)

    with wave.open(io.BytesIO(wav_bytes)) as w:
        assert w.getframerate() == 8000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getnframes() == 800


def test_load_audio_as_pcm16_soundfile_resample(tmp_path):
    # Create a 44.1kHz stereo audio file
    duration_s = 0.1
    sr = 44100
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    sine = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    stereo = np.column_stack([sine, sine])

    import soundfile as sf

    test_wav = tmp_path / "stereo_44k.wav"
    sf.write(str(test_wav), stereo, sr)

    pcm = audio.load_audio_as_pcm16(str(test_wav), target_rate=16000)
    assert len(pcm) > 0
    # Expected samples = duration * 16000 = 1600 samples = 3200 bytes
    samples_count = len(pcm) // 2
    assert abs(samples_count - 1600) <= 2


def test_load_audio_as_pcm16_fallback_pydub(tmp_path):
    # Mock soundfile to fail and pydub to succeed
    test_file = tmp_path / "mock.mp3"
    test_file.write_bytes(b"dummy")

    with patch(
        "speech_engine.core.audio._load_with_soundfile", side_effect=Exception("no sf")
    ):
        with patch(
            "speech_engine.core.audio._load_with_pydub", return_value=b"\x00\x00" * 100
        ):
            res = audio.load_audio_as_pcm16(str(test_file))
            assert len(res) == 200


def test_load_audio_as_pcm16_unreadable_raises_error(tmp_path):
    corrupt_file = tmp_path / "corrupt.raw"
    corrupt_file.write_bytes(b"not an audio format")

    with pytest.raises(AudioProcessingError) as exc_info:
        audio.load_audio_as_pcm16(str(corrupt_file))
    assert "Could not decode audio file" in str(exc_info.value)


def test_ensure_wav_pcm16_converts_non_matching(tmp_path):
    # Non-standard WAV: 8000 Hz
    pcm = np.zeros(800, dtype=np.int16).tobytes()
    wav_bytes = audio.wrap_pcm16_as_wav(pcm, sample_rate=8000)
    test_file = tmp_path / "rate_8k.wav"
    test_file.write_bytes(wav_bytes)

    out_path, is_temp = audio.ensure_wav_pcm16(str(test_file), target_rate=16000)
    try:
        assert is_temp is True
        assert os.path.exists(out_path)
        with wave.open(out_path, "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1
    finally:
        if is_temp and os.path.exists(out_path):
            os.unlink(out_path)


def test_ensure_wav_pcm16_cleanup_on_failure(tmp_path):
    bad_file = tmp_path / "bad.dat"
    bad_file.write_bytes(b"garbage")

    with patch(
        "speech_engine.core.audio.load_audio_as_pcm16",
        side_effect=AudioProcessingError("fail"),
    ):
        with pytest.raises(AudioProcessingError):
            audio.ensure_wav_pcm16(str(bad_file))
