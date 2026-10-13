"""Shared pytest fixtures.

The whole suite runs without any heavy ML models or network access: the
local whisper engine's model layer is stubbed, and (for TTS) edge-tts is
replaced with a tiny writer. Engine selection, routing, config, auth,
rate limiting, and the streaming state machine are all exercised for real.
"""

import numpy as np
import pytest


def _reset_singletons() -> None:
    from speech_engine.config import get_settings
    from speech_engine.core.security import reset_rate_limiter
    from speech_engine.core.stt.factory import reset_stt_engine
    from speech_engine.core.tts.factory import reset_tts_engine

    get_settings.cache_clear()
    reset_stt_engine()
    reset_tts_engine()
    reset_rate_limiter()


@pytest.fixture(autouse=True)
def isolate_test_env(monkeypatch):
    """Isolate tests from local .env files and set test defaults."""
    monkeypatch.setenv("TESTING", "1")


@pytest.fixture
def configure_env(monkeypatch):
    """Return a helper that sets env vars and resets cached singletons."""
    monkeypatch.setenv("TESTING", "1")

    def _apply(**env: str):
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        _reset_singletons()

    yield _apply
    _reset_singletons()


@pytest.fixture
def stub_whisper(monkeypatch):
    """Replace the faster-whisper model with a deterministic stub.

    Returns a list that records the language of each transcription call.
    Transcripts encode the audio length so streaming assertions can observe
    the rolling buffer growing and resetting.
    """
    from speech_engine.core.stt.local import LocalSTTEngine

    calls: list = []

    def fake_source(self, source, lang, *args, **kwargs):
        calls.append(lang)
        if isinstance(source, np.ndarray):
            return f"heard {source.shape[0] // 1600} tenths" if source.size else ""
        return f"file:{lang}"

    monkeypatch.setattr(LocalSTTEngine, "warmup", lambda self: None)
    monkeypatch.setattr(LocalSTTEngine, "_transcribe_source", fake_source)
    return calls


@pytest.fixture
def stub_edge_tts(monkeypatch):
    """Replace edge-tts synthesis with a local file writer (no network)."""
    from speech_engine.core.constants import require_language
    from speech_engine.core.tts.local import EdgeTTSEngine

    async def fake_synthesize(self, text, language, output_file_path):
        require_language(language)  # keep language validation behaviour
        with open(output_file_path, "wb") as out:
            out.write(b"ID3fake-audio-bytes")
        return output_file_path

    monkeypatch.setattr(EdgeTTSEngine, "synthesize", fake_synthesize)


@pytest.fixture
def tone_wav():
    """A 1-second 16 kHz mono PCM WAV as bytes."""
    from speech_engine.core.audio import wrap_pcm16_as_wav

    samples = (np.sin(np.linspace(0, 800, 16000)) * 9000).astype(np.int16)
    return wrap_pcm16_as_wav(samples.tobytes())


@pytest.fixture(autouse=True)
def _clean_singletons():
    _reset_singletons()
    yield
    _reset_singletons()
