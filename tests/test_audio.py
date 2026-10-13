"""Audio helpers: PCM conversion, silence detection, WAV wrapping."""

import io
import wave

import numpy as np

from speech_engine.core import audio


def test_pcm16_to_float32_range():
    samples = np.array([0, 16384, -16384, 32767], dtype=np.int16)
    out = audio.pcm16_to_float32(samples.tobytes())
    assert out.dtype == np.float32
    assert abs(out[1] - 0.5) < 1e-3
    assert abs(out[2] + 0.5) < 1e-3


def test_pcm16_to_float32_handles_odd_byte():
    # A split frame (odd byte count) must not raise.
    out = audio.pcm16_to_float32(b"\x01\x02\x03")
    assert out.shape[0] == 1


def test_silence_detection():
    loud = (np.sin(np.linspace(0, 400, 16000)) * 9000).astype(np.int16).tobytes()
    quiet = b"\x00\x00" * 16000
    assert not audio.is_silence(loud, 300)
    assert audio.is_silence(quiet, 300)
    assert audio.pcm16_rms(b"") == 0.0


def test_wrap_pcm16_as_wav_roundtrip():
    pcm = (np.sin(np.linspace(0, 800, 16000)) * 8000).astype(np.int16).tobytes()
    wav_bytes = audio.wrap_pcm16_as_wav(pcm)
    with wave.open(io.BytesIO(wav_bytes)) as w:
        assert w.getframerate() == audio.STREAM_SAMPLE_RATE
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.readframes(w.getnframes()) == pcm


def test_ensure_wav_passthrough(tmp_path):
    pcm = (np.zeros(1600)).astype(np.int16).tobytes()
    path = tmp_path / "a.wav"
    path.write_bytes(audio.wrap_pcm16_as_wav(pcm))
    out_path, is_temp = audio.ensure_wav_pcm16(str(path))
    assert out_path == str(path)
    assert is_temp is False


def test_pcm16_rms_calculation():
    # Square wave: alternate between 1000 and -1000 -> RMS is 1000.0
    samples = np.array([1000, -1000] * 500, dtype=np.int16)
    rms = audio.pcm16_rms(samples.tobytes())
    assert abs(rms - 1000.0) < 1e-2
