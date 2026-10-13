"""Edge-case and error-handling tests for all TTS engines (local and remote)."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from speech_engine.core.exceptions import (
    ConfigurationError,
    RemoteServiceError,
    SynthesisError,
    UnsupportedLanguageError,
)
from speech_engine.core.tts.local import (
    CoquiTTSEngine,
    EdgeTTSEngine,
    _verify_output_file,
)
from speech_engine.core.tts.remote import AWSTTSEngine, AzureTTSEngine, OpenAITTSEngine


def test_verify_output_file_missing_or_empty(tmp_path):
    missing = tmp_path / "missing.mp3"
    with pytest.raises(SynthesisError) as exc:
        _verify_output_file(str(missing))
    assert "no audio output" in str(exc.value)

    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(SynthesisError) as exc:
        _verify_output_file(str(empty))
    assert "no audio output" in str(exc.value)


@pytest.mark.asyncio
async def test_edge_tts_missing_package(monkeypatch, tmp_path):
    engine = EdgeTTSEngine()
    out = tmp_path / "out.mp3"
    with patch.dict(sys.modules, {"edge_tts": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.synthesize("test", "en", str(out))
        assert "requires the 'edge-tts' package" in str(exc.value)


@pytest.mark.asyncio
async def test_edge_tts_synthesis_failure(monkeypatch, tmp_path):
    engine = EdgeTTSEngine()
    out = tmp_path / "out.mp3"

    mock_edge = MagicMock()
    mock_comm = MagicMock()
    mock_comm.save = AsyncMock(side_effect=RuntimeError("connection error"))
    mock_edge.Communicate.return_value = mock_comm

    monkeypatch.setitem(sys.modules, "edge_tts", mock_edge)
    with pytest.raises(SynthesisError) as exc:
        await engine.synthesize("test", "he", str(out))
    assert "edge-tts synthesis failed" in str(exc.value)


@pytest.mark.asyncio
async def test_coqui_tts_rejects_hebrew():
    engine = CoquiTTSEngine()
    with pytest.raises(UnsupportedLanguageError) as exc:
        await engine.synthesize("שלום", "he", "out.wav")
    assert "Coqui XTTS v2 does not support Hebrew" in str(exc.value)


@pytest.mark.asyncio
async def test_coqui_tts_missing_package(monkeypatch, tmp_path):
    engine = CoquiTTSEngine()
    CoquiTTSEngine._tts = None
    out = tmp_path / "out.wav"
    with patch.dict(sys.modules, {"TTS": None, "TTS.api": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.synthesize("test", "en", str(out))
        assert "requires the 'TTS' package" in str(exc.value)


def test_azure_tts_missing_configuration(configure_env):
    configure_env(AZURE_SPEECH_KEY="", AZURE_SPEECH_REGION="")
    with pytest.raises(ConfigurationError) as exc:
        AzureTTSEngine()
    assert "requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION" in str(exc.value)


@pytest.mark.asyncio
async def test_azure_tts_missing_sdk(configure_env, tmp_path):
    configure_env(AZURE_SPEECH_KEY="key", AZURE_SPEECH_REGION="eastus")
    engine = AzureTTSEngine()
    out = tmp_path / "out.mp3"
    with patch.dict(sys.modules, {"azure.cognitiveservices.speech": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.synthesize("hello", "en", str(out))
        assert "requires the 'azure-cognitiveservices-speech' package" in str(exc.value)


@pytest.mark.asyncio
async def test_azure_tts_synthesis_cancellation(monkeypatch, configure_env, tmp_path):
    configure_env(AZURE_SPEECH_KEY="key", AZURE_SPEECH_REGION="eastus")
    engine = AzureTTSEngine()
    out = tmp_path / "out.mp3"

    mock_sdk = MagicMock()
    mock_result = MagicMock()
    mock_result.reason = mock_sdk.ResultReason.Canceled
    mock_result.cancellation_details.error_details = "Auth failure"

    mock_synth = MagicMock()
    mock_async = MagicMock()
    mock_async.get.return_value = mock_result
    mock_synth.speak_text_async.return_value = mock_async
    mock_sdk.SpeechSynthesizer.return_value = mock_synth

    monkeypatch.setitem(sys.modules, "azure.cognitiveservices.speech", mock_sdk)
    monkeypatch.setitem(
        sys.modules, "azure.cognitiveservices", MagicMock(speech=mock_sdk)
    )

    with pytest.raises(RemoteServiceError) as exc:
        await engine.synthesize("hello", "en", str(out))
    assert "Azure TTS failed: Auth failure" in str(exc.value)


def test_openai_tts_missing_configuration(configure_env):
    configure_env(OPENAI_API_KEY="")
    with pytest.raises(ConfigurationError) as exc:
        OpenAITTSEngine()
    assert "requires OPENAI_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_tts_missing_sdk(configure_env, tmp_path):
    configure_env(OPENAI_API_KEY="sk-123")
    engine = OpenAITTSEngine()
    out = tmp_path / "out.mp3"
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.synthesize("test", "en", str(out))
        assert "requires the 'openai' package" in str(exc.value)


@pytest.mark.asyncio
async def test_aws_polly_rejects_hebrew():
    engine = AWSTTSEngine()
    with pytest.raises(UnsupportedLanguageError) as exc:
        await engine.synthesize("שלום", "he", "out.mp3")
    assert "Amazon Polly has no voice for 'he'" in str(exc.value)


@pytest.mark.asyncio
async def test_aws_polly_missing_sdk(tmp_path):
    engine = AWSTTSEngine()
    out = tmp_path / "out.mp3"
    with patch.dict(sys.modules, {"boto3": None}):
        with pytest.raises(ConfigurationError) as exc:
            await engine.synthesize("hello", "en", str(out))
        assert "requires the 'boto3' package" in str(exc.value)


@pytest.mark.asyncio
async def test_aws_polly_synthesis_success(monkeypatch, tmp_path):
    engine = AWSTTSEngine()
    out = tmp_path / "out.mp3"

    mock_boto = MagicMock()
    mock_client = MagicMock()
    mock_resp = {"AudioStream": MagicMock(read=lambda: b"polly-mp3-bytes")}
    mock_client.synthesize_speech.return_value = mock_resp
    mock_boto.client.return_value = mock_client

    monkeypatch.setitem(sys.modules, "boto3", mock_boto)

    res = await engine.synthesize("hello", "en", str(out))
    assert res == str(out)
    assert out.read_bytes() == b"polly-mp3-bytes"
