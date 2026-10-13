"""API route and WebSocket edge cases, Prometheus metrics, and CORS."""

import json

import numpy as np
from fastapi.testclient import TestClient


def _build_app():
    import importlib

    import speech_engine.main as main

    return importlib.reload(main).app


def _client(configure_env, **env):
    configure_env(**env)
    return TestClient(_build_app())


def test_docs_and_openapi(configure_env, stub_edge_tts):
    with _client(configure_env, ENABLE_STT="false") as client:
        r = client.get("/docs")
        assert r.status_code == 200
        assert "Swagger UI" in r.text or "swagger" in r.text.lower()


def test_metrics_endpoint_toggle(configure_env, stub_edge_tts):
    # Enabled
    with _client(configure_env, ENABLE_STT="false", ENABLE_METRICS="true") as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert (
            "speech_bridge" in r.text or "python_gc" in r.text or "process_" in r.text
        )

    # Disabled
    with _client(configure_env, ENABLE_STT="false", ENABLE_METRICS="false") as client:
        r = client.get("/metrics")
        assert r.status_code == 404


def test_cors_middleware(configure_env, stub_edge_tts):
    with _client(
        configure_env, ENABLE_STT="false", CORS_ALLOW_ORIGINS="http://example.com"
    ) as client:
        r = client.get("/health", headers={"Origin": "http://example.com"})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "http://example.com"


def test_synthesize_empty_or_whitespace_text(configure_env, stub_edge_tts):
    with _client(configure_env, ENABLE_STT="false") as client:
        # Empty string fails pydantic min_length
        r1 = client.post("/api/v1/synthesize", json={"text": "", "language": "en"})
        assert r1.status_code == 422

        # Whitespace-only string fails route validation
        r2 = client.post("/api/v1/synthesize", json={"text": "   ", "language": "en"})
        assert r2.status_code == 400
        assert "Text must not be blank" in r2.text


def test_synthesize_invalid_payload(configure_env, stub_edge_tts):
    with _client(configure_env, ENABLE_STT="false") as client:
        # Missing text
        r = client.post("/api/v1/synthesize", json={"language": "en"})
        assert r.status_code == 422


def test_transcribe_upload_cap(configure_env, stub_whisper, tone_wav):
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
        MAX_UPLOAD_BYTES="10",
    ) as client:
        r = client.post(
            "/api/v1/transcribe?language=en",
            files={"audio": ("big.wav", tone_wav, "audio/wav")},
        )
        assert r.status_code == 413


def test_transcribe_empty_file_returns_400(configure_env, stub_whisper):
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
    ) as client:
        r = client.post(
            "/api/v1/transcribe?language=en",
            files={"audio": ("empty.wav", b"", "audio/wav")},
        )
        assert r.status_code == 400
        assert "Uploaded audio file is empty" in r.text


def test_live_stream_language_negotiation_frame(configure_env, stub_whisper):
    loud = (np.sin(np.linspace(0, 400, 8000)) * 9000).astype(np.int16).tobytes()
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
        STT_STREAM_INFER_INTERVAL_SECONDS="0.25",
    ) as client:
        # No ?language= query param, send JSON frame with language
        with client.websocket_connect("/api/v1/live-transcribe") as ws:
            ws.send_text(json.dumps({"language": "he"}))
            ws.send_bytes(loud)
            frame = ws.receive_json()
            assert frame["type"] == "partial"
            ws.send_text(json.dumps({"event": "stop"}))


def test_live_stream_binary_before_language_error(configure_env, stub_whisper):
    loud = (np.sin(np.linspace(0, 400, 8000)) * 9000).astype(np.int16).tobytes()
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
    ) as client:
        # Send binary audio without declaring language first
        with client.websocket_connect("/api/v1/live-transcribe") as ws:
            ws.send_bytes(loud)
            frame = ws.receive_json()
            assert frame["type"] == "error"
            assert "The first frame must declare the language" in frame["message"]
            closed = ws.receive()
            assert closed["type"] == "websocket.close" and closed["code"] == 4400
