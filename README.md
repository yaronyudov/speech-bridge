# speech-bridge

A highly modular, configuration-driven FastAPI service for hybrid **Speech-to-Text (STT)** and **Text-to-Speech (TTS)**. Supports batch processing, real-time WebSocket streaming, and native **English, Hebrew, and Arabic** localization with seamless switching between **Local** models and multi-cloud endpoints (**AWS, Azure, OpenAI**).

- **Partial modes** — run STT-only, TTS-only, or both (`ENABLE_STT` / `ENABLE_TTS`); disabled subsystems mount no routes and load no models.
- **Strategy + Factory architecture** — engines are interchangeable strategies behind `BaseSTTEngine` / `BaseTTSEngine`; factories pick the implementation from config at startup.
- **Live low-latency STT** — WebSocket streaming with partial/final results for local (faster-whisper rolling-buffer + VAD) and remote (Azure push streams, Amazon Transcribe Streaming) setups.

> **New here? Start with the step-by-step guide: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — zero to a working service, locally or on AWS/Azure/GCP/OCI.  
> 🇮🇱 **Looking for Hebrew STT/TTS? See [docs/HEBREW_GUIDE.md](docs/HEBREW_GUIDE.md)** for optimal Ivrit-AI model selection, live microphone setup, and troubleshooting.

---

## Contents

- [Quickstart](#quickstart)
- [Architecture](#architecture)
- [Configuration reference](#configuration-reference)
- [Engine matrix](#engine-matrix)
- [Language & voice mappings](#language--voice-mappings)
- [API reference](#api-reference)
  - [`GET /health`](#get-health)
  - [`POST /api/v1/transcribe`](#post-apiv1transcribe--batch-stt)
  - [`WebSocket /api/v1/live-transcribe`](#websocket-apiv1live-transcribe--live-stt)
  - [`POST /api/v1/synthesize`](#post-apiv1synthesize--tts)
- [Example clients](#example-clients)
- [Partial modes](#partial-modes)
- [Security](#security)
- [Observability](#observability)
- [Deployment (Terraform)](#deployment-terraform)
- [Docker](#docker)
- [Extending: adding a new engine](#extending-adding-a-new-engine)
- [Error handling](#error-handling)
- [Performance notes](#performance-notes)
- [Troubleshooting](#troubleshooting)

---

## Quickstart

Requirements: **Python 3.11+**; `ffmpeg` recommended (decoding compressed uploads such as mp3/m4a/webm).

```bash
git clone <this repo> && cd speech-bridge

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r speech_engine/requirements.txt

# Configure (defaults work out of the box: local faster-whisper + edge-tts)
cp .env.example .env

# Run
uvicorn speech_engine.main:app --host 0.0.0.0 --port 8000
# or: python -m speech_engine.main
```

Interactive API docs: **http://localhost:8000/docs**

Smoke test:

```bash
curl http://localhost:8000/health

# TTS (Hebrew, via zero-cost edge-tts by default)
curl -X POST http://localhost:8000/api/v1/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "שלום עולם", "language": "he"}' \
     --output hello.mp3

# STT
curl -X POST "http://localhost:8000/api/v1/transcribe?language=en" \
     -F "audio=@hello.wav"
```

> **First STT request note:** with `STT_ENGINE=local` the faster-whisper model (default `large-v3`, ~3 GB) is downloaded and loaded **once at startup**, not per request. Use `STT_LOCAL_MODEL_SIZE=tiny` or `small` for a fast first run.

## Architecture

**Design patterns:** every engine is a **Strategy** implementing a shared abstract interface; a **Factory** (`core/stt/factory.py`, `core/tts/factory.py`) instantiates the strategy selected by config exactly once per process and hands out the singleton.

```text
speech_engine/
├── main.py                # FastAPI entry point; conditional router mounting; lifespan warmup
├── config.py              # pydantic-settings manager (.env / config.yaml / env vars)
├── requirements.txt
├── api/
│   ├── routes_stt.py      # POST /api/v1/transcribe        (batch STT)
│   ├── routes_tts.py      # POST /api/v1/synthesize        (TTS)
│   └── ws_stt.py          # WS   /api/v1/live-transcribe   (live STT)
└── core/
    ├── constants.py       # language codes & per-provider voice/locale mappings
    ├── exceptions.py      # error hierarchy w/ HTTP + WebSocket close codes
    ├── audio.py           # PCM chunk ops, decoding, resampling, WAV wrapping
    ├── stt/
    │   ├── base.py        # BaseSTTEngine ABC (batch + streaming) + WS frame plumbing
    │   ├── factory.py     # local | azure | openai | aws  → singleton
    │   ├── local.py       # faster-whisper batch + rolling-buffer live streaming
    │   └── remote.py      # Azure Speech, OpenAI Whisper API, Amazon Transcribe Streaming
    └── tts/
        ├── base.py        # BaseTTSEngine ABC
        ├── factory.py     # local | azure | openai | aws  → singleton
        ├── local.py       # edge-tts (default) + Coqui XTTS v2 offline adapter
        └── remote.py      # Azure Neural TTS, OpenAI TTS, Amazon Polly
```

**Interfaces:**

```python
class BaseSTTEngine(ABC):
    async def transcribe(
        self, audio_file_path: str, language: str | None = None
    ) -> str: ...
    async def transcribe_stream(
        self, websocket, language: str | None = None
    ) -> AsyncGenerator[STTStreamResult, None]: ...  # yields partial/final increments


class BaseTTSEngine(ABC):
    async def synthesize(
        self, text: str, language: str, output_file_path: str
    ) -> str: ...
```

**Request flow (live STT):** client WebSocket → `ws_stt.py` (language negotiation, error frames) → `engine.transcribe_stream(websocket)` reads binary PCM frames, feeds the engine-specific pipeline (rolling whisper buffer / Azure `PushAudioInputStream` / Transcribe event stream), and yields `partial`/`final` results, which the route serializes back as JSON.

## Configuration reference

Settings resolve with priority: **process env vars → `.env` → `config.yaml` → defaults**. Templates: [`.env.example`](.env.example), [`config.yaml.example`](config.yaml.example).

| Variable | Default | Description |
|---|---|---|
| `ENABLE_STT` | `true` | Mount STT routes & load STT engine/model |
| `ENABLE_TTS` | `true` | Mount TTS route & init TTS engine |
| `STT_ENGINE` | `local` | `local` \| `azure` \| `openai` \| `aws` |
| `TTS_ENGINE` | `local` | `local` \| `azure` \| `openai` \| `aws` |
| `STT_LOCAL_MODEL_SIZE` | `large-v3` | faster-whisper model (`tiny`…`large-v3` or HF repo id) |
| `STT_LOCAL_DEVICE` | `auto` | `auto` \| `cuda` \| `cpu` (`auto` = CUDA when available) |
| `STT_LOCAL_COMPUTE_TYPE` | `auto` | `auto` = `float16` on GPU, `int8` on CPU |
| `STT_LOCAL_BEAM_SIZE` | `5` | Whisper beam size (batch transcription) |
| `STT_STREAM_INFER_INTERVAL_SECONDS` | `1.5` | New audio required between local live inference passes |
| `STT_STREAM_BEAM_SIZE` | `1` | Beam size for live streaming passes (1 = greedy search, 3-4x faster on CPU) |
| `STT_STREAM_MIN_CONTEXT_SECONDS` | `0.0` | Minimum audio context required before first inference (prevents broken syllables) |
| `STT_STREAM_MAX_SEGMENT_SECONDS` | `12.0` | Force-finalize a live segment at this length |
| `STT_STREAM_SILENCE_RMS_THRESHOLD` | `300` | int16 RMS below which audio counts as silence |
| `STT_STREAM_TRAILING_SILENCE_SECONDS` | `0.6` | Trailing silence that finalizes a segment |
| `STT_STREAM_OPENAI_FLUSH_SECONDS` | `3.0` | Pseudo-streaming flush interval (OpenAI live adapter) |
| `TTS_LOCAL_BACKEND` | `edge` | `edge` (zero-cost neural voices) \| `coqui` (offline XTTS v2) |
| `TTS_COQUI_MODEL_NAME` | `tts_models/multilingual/multi-dataset/xtts_v2` | Coqui model id |
| `TTS_COQUI_SPEAKER` | `Ana Florence` | XTTS built-in speaker |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | — | Azure Speech Services credentials |
| `OPENAI_API_KEY` | — | OpenAI credentials |
| `OPENAI_STT_MODEL` | `whisper-1` | OpenAI transcription model |
| `OPENAI_TTS_MODEL` / `OPENAI_TTS_VOICE` | `tts-1` / `alloy` | OpenAI TTS model & voice |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | — / — / `us-east-1` | AWS credentials (any boto3 credential-chain source also works) |
| `AWS_POLLY_ENGINE` | `neural` | `neural` \| `standard` |
| `ENABLE_AUTH` | `false` | Require an `X-API-Key` header on all `/api/v1` routes + live WS |
| `API_KEYS` | — | Comma-separated accepted keys (e.g. `k1,k2`) |
| `API_KEY_HEADER` | `X-API-Key` | Header carrying the API key |
| `ENABLE_RATE_LIMIT` / `RATE_LIMIT` | `true` / `60/minute` | Shared REST+WS rate limit |
| `MAX_UPLOAD_BYTES` | `26214400` | Max `/transcribe` upload (413 over cap) |
| `MAX_TEXT_CHARS` | `5000` | Max `/synthesize` text length |
| `MAX_WS_SESSION_SECONDS` / `MAX_WS_BYTES` | `300` / `104857600` | Live-session time & audio caps |
| `CORS_ALLOW_ORIGINS` | — | Comma-separated origins or `*` (empty disables CORS) |
| `SECRETS_BACKEND` | `none` | `none` \| `aws` \| `azure` \| `gcp` \| `oci` |
| `SECRETS_PREFIX` | — | Secret-store locator (see [Secrets](#secrets-from-a-cloud-manager)) |
| `ENABLE_METRICS` | `true` | Expose Prometheus `/metrics` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP endpoint to enable tracing (empty = off) |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `TEMP_DIR` | system temp | Working dir for uploads & synthesized files |

## Engine matrix

| Capability | `local` | `azure` | `openai` | `aws` |
|---|---|---|---|---|
| **Batch STT** | faster-whisper | Speech SDK continuous recognition | Whisper API | Transcribe Streaming (file pumped through — no S3 needed) |
| **Live STT** | rolling buffer + whisper VAD | `PushAudioInputStream` + `SpeechRecognizer` (true streaming) | buffered pseudo-streaming (rolling flush to Whisper API)¹ | Transcribe Streaming SDK (true streaming) |
| **TTS** | edge-tts (default) / Coqui XTTS v2 | Neural TTS | OpenAI TTS | Amazon Polly |
| **Credentials** | none² | `AZURE_SPEECH_*` | `OPENAI_API_KEY` | `AWS_*` |

¹ The OpenAI Whisper HTTP API has no public streaming transport; the adapter re-sends the rolling buffer every `STT_STREAM_OPENAI_FLUSH_SECONDS`, so partials lag Azure/AWS. Prefer `azure`/`aws`/`local` for real-time use.
² edge-tts needs outbound internet but no API key; Coqui XTTS and faster-whisper are fully offline after the model download.

## Language & voice mappings

Canonical codes accepted everywhere: `en`, `he`, `ar` (regional tags like `he-IL` and the legacy `iw` are normalized). Anything else → HTTP 400 / WS close 4400.

| | `en` | `he` | `ar` |
|---|---|---|---|
| Whisper (local & OpenAI) | `en` | `he` | `ar` |
| Azure STT locale | `en-US` | `he-IL` | `ar-SA` |
| Amazon Transcribe | `en-US` | `he-IL` | `ar-SA` |
| Azure / edge-tts voice | `en-US-JennyNeural` | `he-IL-HilaNeural` | `ar-SA-ZariyahNeural` |
| Amazon Polly voice | `Joanna` (neural) | ⚠️ **not available**¹ | `Hala` (`ar-AE`, neural)² |
| OpenAI TTS | multilingual voice (`alloy`) — speaks the language of the input text | | |
| Coqui XTTS v2 | `en` | ⚠️ **not available**¹ | `ar` |

¹ Amazon Polly and Coqui XTTS v2 have no Hebrew voice — requesting `he` there returns a clear 400 pointing at `azure`/`local(edge)` instead.
² Modern Standard Arabic alternative: `Zeina` (`arb`, standard engine) — see `POLLY_VOICES` in `core/constants.py`.

## API reference

All routes are mounted under `/api/v1`. OpenAPI/Swagger UI at `/docs`.

### `GET /health`

Always available. Returns service status, active engines, and supported languages:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "stt": {"enabled": true, "engine": "local"},
  "tts": {"enabled": true, "engine": "local"},
  "supported_languages": ["en", "he", "ar"]
}
```

### `POST /api/v1/transcribe` — batch STT

*Mounted only when `ENABLE_STT=true`.*

- **Input:** `multipart/form-data` with an `audio` file field; optional `language` query parameter (`en`|`he`|`ar`, omit for auto-detect on local/openai engines).
- **Accepted formats:** wav/flac/ogg natively; mp3/m4a/webm/etc. with ffmpeg installed (remote engines that accept compressed audio get the file as-is).
- **Behavior:** upload is saved to a temp file, transcribed, and the temp file is always deleted.

```bash
curl -X POST "http://localhost:8000/api/v1/transcribe?language=he" \
     -F "audio=@meeting.wav"
```

```json
{"text": "שלום, מה שלומך?"}
```

Errors: `400` unsupported language / undecodable or empty audio · `502` remote provider failure · `500` engine failure.

### `WebSocket /api/v1/live-transcribe` — live STT

*Mounted only when `ENABLE_STT=true`.*

**Connect:** `ws://host:8000/api/v1/live-transcribe?language=he`
— or omit the query parameter and send a first **text** frame: `{"language": "he"}` (15 s handshake timeout). Language is **required** for live sessions.

**Send:** continuous **binary** frames of raw PCM — **16-bit little-endian, 16 kHz, mono** (100–250 ms per frame recommended). Convert anything with:

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 out.wav   # then stream out.wav's data chunk
```

**Optional text control frames:**

| Frame | Effect |
|---|---|
| `{"event": "flush"}` | Force-finalize the current segment now |
| `{"event": "stop"}` | Flush, emit the last `final`, close the socket (code 1000) |

**Receive:** JSON frames

```json
{"type": "partial", "text": "hello wor"}
{"type": "final",   "text": "Hello world."}
{"type": "error",   "message": "..."}        // then the socket closes
```

`partial` = evolving hypothesis for the current segment (may change); `final` = committed segment text. Segments finalize on trailing silence, on `STT_STREAM_MAX_SEGMENT_SECONDS` (local/openai), or per the provider's endpointing (azure/aws).

**Close codes:** `1000` normal · `4400` client error (unsupported/missing language, bad handshake) · `1011` internal/remote failure. Abrupt client disconnects are detected and all buffers / remote push-streams are released immediately.

### `POST /api/v1/synthesize` — TTS

*Mounted only when `ENABLE_TTS=true`.*

- **Input:** `{"text": "hello world", "language": "en"}` (text ≤ 5000 chars).
- **Output:** the audio file itself (`audio/mpeg` for edge/azure/openai/polly, `audio/wav` for coqui) via `FileResponse`; the server-side file is deleted after the response by a background task.

```bash
curl -X POST http://localhost:8000/api/v1/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "مرحبا بالعالم", "language": "ar"}' \
     --output hello_ar.mp3
```

Errors: `400` unsupported language / blank text (incl. Polly+`he`, Coqui+`he`) · `502` remote provider failure · `500` synthesis failure.

## Example clients

Runnable reference clients live in [`examples/`](examples/):

```bash
pip install requests websockets

# Batch STT / TTS
python examples/batch_client.py transcribe meeting.wav --language he
python examples/batch_client.py synthesize "hello world" --language en --out hi.mp3

# Live STT: streams a 16 kHz mono WAV at real-time pace, prints partial/final
python examples/live_client.py meeting_16k.wav --language he

# Live microphone STT: real-time microphone streaming with RMS audio meter & BiDi display
python examples/mic_live_client.py --language he -o transcript.txt
```

`live_client.py` and `mic_live_client.py` provide reference implementations of the WebSocket protocol above (pacing, `stop` control frame, result handling, RMS metering) — a browser client would do the same with `AudioWorklet`-captured PCM.

## Partial modes

| Mode | Config | Effect |
|---|---|---|
| STT + TTS (default) | `ENABLE_STT=true ENABLE_TTS=true` | All routes mounted |
| STT-only | `ENABLE_TTS=false` | `/synthesize` not mounted (404); no TTS engine initialized |
| TTS-only | `ENABLE_STT=false` | `/transcribe` + `/live-transcribe` not mounted; **the whisper model is never loaded** (saves RAM/VRAM) |

The `/health` endpoint always reports which subsystems are live.

## Security

All optional and off/relaxed by default for local dev; enable for production
(see [`SECURITY.md`](SECURITY.md)).

- **Authentication** — set `ENABLE_AUTH=true` + `API_KEYS=k1,k2`. Clients send
  `X-API-Key: k1` on REST calls and on the live WS handshake (or `?api_key=k1`).
  Missing/invalid → `401` (WS close `4401`). Keys are compared in constant time.
- **Rate limiting** — `RATE_LIMIT` (e.g. `60/minute`) is enforced across REST
  and WebSocket, keyed by API key (or client IP). Over-limit → `429` (WS `4429`).
- **Request caps** — `MAX_UPLOAD_BYTES` (413), `MAX_TEXT_CHARS`, and
  `MAX_WS_SESSION_SECONDS` / `MAX_WS_BYTES` (WS `4413`) bound each request/session
  and cap the cost of the paid remote APIs.
- **CORS** — `CORS_ALLOW_ORIGINS` (disabled by default).

### Secrets from a cloud manager

Instead of plaintext env credentials, set `SECRETS_BACKEND` to `aws`/`azure`/
`gcp`/`oci` and `SECRETS_PREFIX` to the store locator; matching secrets
(`OPENAI_API_KEY`, `AZURE_SPEECH_KEY`, `API_KEYS`, …) are fetched at startup.

| Backend | `SECRETS_PREFIX` | Requires |
|---|---|---|
| `aws` | secret name prefix, e.g. `speech-bridge/` | `boto3` |
| `gcp` | `projects/<project-id>` | `google-cloud-secret-manager` |
| `azure` | Key Vault URL | `azure-keyvault-secrets` + `azure-identity` |
| `oci` | Vault OCID | `oci` |

## Observability

- **`/metrics`** — Prometheus metrics (request counts, latency histograms) when
  `ENABLE_METRICS=true`.
- **`/health`** (liveness, always 200) and **`/ready`** (readiness, 503 until the
  model has warmed up) — wire them to your load balancer's probes.
- **Tracing** — set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OpenTelemetry
  FastAPI instrumentation.

## Deployment (Terraform)

Production infrastructure for **AWS, Azure, GCP, and Oracle Cloud** lives in
[`infra/terraform/`](infra/terraform/) — one self-contained, fully optional
module per cloud (serverless containers or VM, create-or-BYO network/registry/
secrets).

```bash
cd infra/terraform/modules/gcp
cp ../../envs/gcp.example.tfvars gcp.tfvars   # edit
terraform init && terraform apply -var-file=gcp.tfvars
```

### Cost controls — budget must not be exceeded

Spend is bounded by three layers (details in the [IaC README](infra/terraform/README.md)):

1. **Architectural caps (always on)** — `max_instances`/replicas + concurrency
   bound the burn rate no matter what.
2. **Regular budget → alerts** — `monthly_budget` emails at 50/80/100%.
3. **Grace budget → kill switch** — `hard_cap_amount` (defaults to the regular
   budget) triggers real enforcement: AWS Budget Actions (SSM stop / deny
   policy), GCP Pub/Sub → scale-to-zero or disable-billing, Azure/OCI automation.

```
spend ─► 50% ── 80% ── 100% (monthly_budget) ····· hard_cap_amount
         └──── email alerts ────┘                   └── KILL SWITCH ──┘
```

See [`docs/PRODUCTION.md`](docs/PRODUCTION.md) for the full production checklist
and roadmap.

## Docker

```bash
docker build -t speech-bridge .
docker run --rm -p 8000:8000 --env-file .env speech-bridge

# GPU (requires nvidia-container-toolkit; install torch/CUDA-enabled ctranslate2 in the image as needed)
docker run --rm -p 8000:8000 --gpus all --env-file .env speech-bridge
```

The image runs a **single uvicorn worker** on purpose: the whisper model is a per-process singleton — scale horizontally with more containers, not workers.

## Extending: adding a new engine

1. Implement the strategy — subclass `BaseSTTEngine` (implement `transcribe` + `transcribe_stream`; use `receive_stream_message()` from `core/stt/base.py` for uniform WebSocket frame/disconnect handling) or `BaseTTSEngine` (implement `synthesize`; set `file_extension` / `media_type`).
2. Add language/voice mappings to `core/constants.py`.
3. Register the class in the relevant factory (`_ENGINE_REGISTRY` in `core/stt/factory.py`, or `_create_engine()` in `core/tts/factory.py`).
4. Extend the `STT_ENGINE`/`TTS_ENGINE` `Literal` in `config.py`, add any credentials as new settings, and document them in `.env.example`.

Keep SDK imports lazy (inside methods) so deployments only need the packages for engines they enable, and raise `ConfigurationError` with an actionable message when credentials or packages are missing.

## Error handling

Domain errors derive from `SpeechEngineError` (`core/exceptions.py`), each carrying an HTTP status and a WebSocket close code; a global FastAPI handler maps them to `{"detail": "..."}` responses and the WS route to error frames:

| Exception | HTTP | WS close | Meaning |
|---|---|---|---|
| `UnsupportedLanguageError` | 400 | 4400 | Language outside {en, he, ar} or unsupported by the engine |
| `AudioProcessingError` | 400 | 4400 | Audio could not be decoded/converted |
| `AuthError` | 401 | 4401 | Missing or invalid API key (when `ENABLE_AUTH=true`) |
| `RequestTooLargeError` | 413 | 4413 | Upload / text / WS session exceeded a configured cap |
| `RateLimitError` | 429 | 4429 | Client exceeded `RATE_LIMIT` |
| `ConfigurationError` | 500 | 1011 | Missing credentials / package / disabled subsystem |
| `TranscriptionError` / `SynthesisError` | 500 | 1011 | Engine failure |
| `RemoteServiceError` | 502 | 1011 | Provider timeout / auth / transport failure |

Remote failures (timeouts, auth errors) are caught, logged via the standard `logging` module, and streams are shut down gracefully — push streams and buffers are released in `finally` blocks on client disconnect.

## Performance notes

- **Live STT on CPU:** `large-v3` re-decodes the rolling window every ~1.5 s — heavy on CPU. For real-time CPU use set `STT_LOCAL_MODEL_SIZE=small` (or `medium`), or use `STT_ENGINE=azure`/`aws` for true server-side streaming.
- **GPU:** auto-detected (`torch.cuda.is_available()`, ctranslate2 fallback) with `float16` compute; CPU falls back to `int8`.
- **Latency levers:** `STT_STREAM_INFER_INTERVAL_SECONDS` (partial cadence), `STT_STREAM_TRAILING_SILENCE_SECONDS` / `STT_STREAM_SILENCE_RMS_THRESHOLD` (segment endpointing), frame size (100 ms recommended).
- **Memory:** TTS-only deployments (`ENABLE_STT=false`) never load whisper. Model singletons are process-wide — one worker per container.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not decode audio file ... ensure ffmpeg is installed` | `apt-get install ffmpeg` / `brew install ffmpeg` (needed for mp3/m4a/webm uploads) |
| First startup very slow with `STT_ENGINE=local` | The whisper model is downloading; pick a smaller `STT_LOCAL_MODEL_SIZE` |
| `STT_ENGINE=azure requires AZURE_SPEECH_KEY...` (HTTP 500 at startup) | Fill the provider credentials in `.env`; the app fails fast by design |
| WS closes immediately with 4400 | Missing/unsupported `language` — pass `?language=en\|he\|ar` or the initial JSON frame |
| Live partials are garbage/empty | Verify the stream is raw PCM **16-bit / 16 kHz / mono** (no WAV header per frame; a leading 44-byte header is harmless) |
| `Amazon Polly has no voice for 'he'` | Expected — Polly lacks Hebrew; use `TTS_ENGINE=azure` or `local` |
| GPU not used | Install CUDA-enabled ctranslate2/cuDNN (and optionally torch); check startup log line `device=cuda` |
| 404 on `/transcribe` or `/synthesize` | That subsystem is disabled via `ENABLE_STT`/`ENABLE_TTS` — check `/health` |

## License

[MIT](LICENSE)
