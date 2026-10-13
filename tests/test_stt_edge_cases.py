"""Edge-case tests for STT engines (Local faster-whisper, Azure, OpenAI, AWS)."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from speech_engine.config import Settings
from speech_engine.core.exceptions import (
    ConfigurationError,
    TranscriptionError,
)
from speech_engine.core.stt.base import (
    MSG_AUDIO,
    MSG_FLUSH,
    MSG_STOP,
    RESULT_FINAL,
)
from speech_engine.core.stt.local import LocalSTTEngine
from speech_engine.core.stt.remote import AWSSTTEngine, AzureSTTEngine, OpenAISTTEngine


def test_local_stt_detect_device_auto():
    engine = LocalSTTEngine()
    settings_cpu = Settings(STT_LOCAL_DEVICE="cpu")
    assert engine._detect_device(settings_cpu) == "cpu"

    settings_cuda = Settings(STT_LOCAL_DEVICE="cuda")
    assert engine._detect_device(settings_cuda) == "cuda"


def test_local_stt_missing_package():
    LocalSTTEngine._model = None
    engine = LocalSTTEngine()
    with patch.dict(sys.modules, {"faster_whisper": None}):
        with pytest.raises(ConfigurationError) as exc:
            engine._get_model()
        assert "requires the 'faster-whisper' package" in str(exc.value)


@pytest.mark.asyncio
async def test_local_stt_transcribe_exception_handling():
    engine = LocalSTTEngine()
    with patch.object(
        engine, "_transcribe_source", side_effect=RuntimeError("CUDA out of memory")
    ):
        with pytest.raises(TranscriptionError) as exc:
            await engine.transcribe("test.wav", "en")
        assert "Local transcription failed" in str(exc.value)


def test_local_stt_transcribe_pcm_empty():
    engine = LocalSTTEngine()
    assert engine._transcribe_pcm(b"", "en") == ""


def test_local_stt_transcribe_pcm_beam_size():
    engine = LocalSTTEngine()
    with patch.object(engine, "_transcribe_source", return_value="test") as mock_source:
        engine._transcribe_pcm(b"\x00\x00" * 1600, "en")
        mock_source.assert_called_once()
        assert (
            mock_source.call_args.kwargs.get("beam_size")
            == engine._settings.STT_STREAM_BEAM_SIZE
        )


@pytest.mark.asyncio
async def test_local_stt_stream_events():
    engine = LocalSTTEngine()
    # Stub _transcribe_pcm
    engine._transcribe_pcm = MagicMock(return_value="שלום.")

    # Mock websocket yielding AUDIO, then FLUSH, then STOP
    audio_frame = np.full(8000, 5000, dtype=np.int16).tobytes()

    messages = [
        (MSG_AUDIO, audio_frame),
        (MSG_FLUSH, b""),
        (MSG_STOP, b""),
    ]
    idx = 0

    class FakeWS:
        async def receive(self):
            nonlocal idx
            if idx < len(messages):
                msg_type, payload = messages[idx]
                idx += 1
                if msg_type == MSG_AUDIO:
                    return {"type": "websocket.receive", "bytes": payload}
                elif msg_type == MSG_FLUSH:
                    return {"type": "websocket.receive", "text": '{"event": "flush"}'}
                elif msg_type == MSG_STOP:
                    return {"type": "websocket.receive", "text": '{"event": "stop"}'}
            return {"type": "websocket.disconnect"}

    results = []
    async for res in engine.transcribe_stream(FakeWS(), language="he"):
        results.append(res)

    assert len(results) >= 1
    assert any(r.type == RESULT_FINAL for r in results)


@pytest.mark.asyncio
async def test_local_stt_stream_disconnect():
    engine = LocalSTTEngine()
    engine._transcribe_pcm = MagicMock(return_value="word")

    class DisconnectWS:
        async def receive(self):
            return {"type": "websocket.disconnect"}

    results = []
    async for res in engine.transcribe_stream(DisconnectWS(), language="en"):
        results.append(res)

    # Should exit cleanly without raising
    assert len(results) == 0


def test_azure_stt_missing_config(configure_env):
    configure_env(AZURE_SPEECH_KEY="", AZURE_SPEECH_REGION="")
    with pytest.raises(ConfigurationError) as exc:
        AzureSTTEngine()
    assert "requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION" in str(exc.value)


@pytest.mark.asyncio
async def test_azure_stt_missing_sdk(configure_env):
    configure_env(AZURE_SPEECH_KEY="k", AZURE_SPEECH_REGION="reg")
    engine = AzureSTTEngine()
    with patch.dict(sys.modules, {"azure.cognitiveservices.speech": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.transcribe("file.wav", "en")
        assert "requires the 'azure-cognitiveservices-speech' package" in str(exc.value)


def test_openai_stt_missing_config(configure_env):
    configure_env(OPENAI_API_KEY="")
    with pytest.raises(ConfigurationError) as exc:
        OpenAISTTEngine()
    assert "requires OPENAI_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_stt_missing_sdk(configure_env, tmp_path):
    configure_env(OPENAI_API_KEY="sk-fake")
    engine = OpenAISTTEngine()
    f = tmp_path / "dummy.wav"
    f.write_bytes(b"dummy audio")
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.transcribe(str(f), "en")
        assert "requires the 'openai' package" in str(exc.value)


@pytest.mark.asyncio
async def test_aws_stt_missing_sdk():
    engine = AWSSTTEngine()
    with patch.dict(sys.modules, {"amazon_transcribe": None}):
        with pytest.raises(ConfigurationError) as exc:
            ws = MagicMock()
            async for _ in engine.transcribe_stream(ws, "en"):
                pass
        assert "requires the 'amazon-transcribe' package" in str(exc.value)
