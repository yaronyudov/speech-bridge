"""End-to-end API tests via TestClient with whisper/edge-tts stubbed.

Covers conditional router mounting, batch STT, TTS, the live-streaming
state machine, and the security layer (auth, rate limiting, upload caps).
"""

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


def test_conditional_mounting_stt_only(configure_env, stub_whisper):
    with _client(
        configure_env,
        ENABLE_STT="true",
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
    ) as client:
        paths = set(client.get("/openapi.json").json()["paths"])
        assert "/api/v1/transcribe" in paths
        assert "/api/v1/synthesize" not in paths
        assert client.post("/api/v1/synthesize", json={}).status_code == 404


def test_health_and_ready(configure_env, stub_whisper):
    with _client(configure_env, STT_LOCAL_MODEL_SIZE="tiny") as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").status_code == 200  # ready after startup


def test_batch_transcribe(configure_env, stub_whisper, tone_wav):
    with _client(
        configure_env, ENABLE_TTS="false", STT_LOCAL_MODEL_SIZE="tiny"
    ) as client:
        r = client.post(
            "/api/v1/transcribe?language=he",
            files={"audio": ("a.wav", tone_wav, "audio/wav")},
        )
        assert r.status_code == 200
        assert r.json() == {"text": "file:he"}


def test_batch_rejects_unsupported_language(configure_env, stub_whisper, tone_wav):
    with _client(configure_env, STT_LOCAL_MODEL_SIZE="tiny") as client:
        r = client.post(
            "/api/v1/transcribe?language=fr",
            files={"audio": ("a.wav", tone_wav, "audio/wav")},
        )
        assert r.status_code == 400


def test_batch_empty_upload(configure_env, stub_whisper):
    with _client(configure_env, STT_LOCAL_MODEL_SIZE="tiny") as client:
        r = client.post(
            "/api/v1/transcribe",
            files={"audio": ("a.wav", b"", "audio/wav")},
        )
        assert r.status_code == 400


def test_upload_size_cap(configure_env, stub_whisper, tone_wav):
    with _client(
        configure_env, STT_LOCAL_MODEL_SIZE="tiny", MAX_UPLOAD_BYTES="1024"
    ) as client:
        r = client.post(
            "/api/v1/transcribe",
            files={"audio": ("a.wav", tone_wav, "audio/wav")},
        )
        assert r.status_code == 413


def test_synthesize(configure_env, stub_edge_tts):
    with _client(configure_env, ENABLE_STT="false") as client:
        r = client.post("/api/v1/synthesize", json={"text": "hi", "language": "en"})
        assert r.status_code == 200
        assert r.content.startswith(b"ID3")


def test_synthesize_rejects_unsupported_language(configure_env, stub_edge_tts):
    with _client(configure_env, ENABLE_STT="false") as client:
        r = client.post("/api/v1/synthesize", json={"text": "hi", "language": "fr"})
        assert r.status_code == 400


def test_auth_enforced(configure_env, stub_edge_tts):
    with _client(
        configure_env, ENABLE_STT="false", ENABLE_AUTH="true", API_KEYS="good-key"
    ) as client:
        assert (
            client.post(
                "/api/v1/synthesize", json={"text": "hi", "language": "en"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/synthesize",
                headers={"X-API-Key": "bad"},
                json={"text": "hi", "language": "en"},
            ).status_code
            == 401
        )
        ok = client.post(
            "/api/v1/synthesize",
            headers={"X-API-Key": "good-key"},
            json={"text": "hi", "language": "en"},
        )
        assert ok.status_code == 200


def test_rate_limit(configure_env, stub_edge_tts):
    with _client(
        configure_env,
        ENABLE_STT="false",
        ENABLE_RATE_LIMIT="true",
        RATE_LIMIT="2/minute",
    ) as client:
        codes = [
            client.post(
                "/api/v1/synthesize", json={"text": "hi", "language": "en"}
            ).status_code
            for _ in range(5)
        ]
        assert codes.count(200) == 2
        assert 429 in codes


def test_live_stream_partial_then_final(configure_env, stub_whisper):
    loud = (np.sin(np.linspace(0, 400, 8000)) * 9000).astype(np.int16).tobytes()
    quiet = b"\x00" * 16000
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
        STT_STREAM_INFER_INTERVAL_SECONDS="0.25",
        STT_STREAM_TRAILING_SILENCE_SECONDS="0.4",
    ) as client:
        with client.websocket_connect("/api/v1/live-transcribe?language=he") as ws:
            ws.send_bytes(loud)
            p1 = ws.receive_json()
            assert p1["type"] == "partial" and p1["text"]
            ws.send_bytes(loud)
            p2 = ws.receive_json()
            assert p2["type"] == "partial" and p2["text"] != p1["text"]
            ws.send_bytes(quiet)
            f1 = ws.receive_json()
            assert f1["type"] == "final"
            ws.send_text(json.dumps({"event": "stop"}))
            closed = ws.receive()
            assert closed["type"] == "websocket.close" and closed["code"] == 1000


def test_live_stream_rejects_unsupported_language(configure_env, stub_whisper):
    with _client(
        configure_env, ENABLE_TTS="false", STT_LOCAL_MODEL_SIZE="tiny"
    ) as client:
        with client.websocket_connect("/api/v1/live-transcribe?language=fr") as ws:
            assert ws.receive_json()["type"] == "error"
            closed = ws.receive()
            assert closed["type"] == "websocket.close" and closed["code"] == 4400


def test_live_stream_auth(configure_env, stub_whisper):
    with _client(
        configure_env,
        ENABLE_TTS="false",
        STT_LOCAL_MODEL_SIZE="tiny",
        ENABLE_AUTH="true",
        API_KEYS="k",
    ) as client:
        with client.websocket_connect("/api/v1/live-transcribe?language=en") as ws:
            assert ws.receive_json()["type"] == "error"
            closed = ws.receive()
            assert closed["type"] == "websocket.close" and closed["code"] == 4401
