# Getting started — from zero to a working speech-bridge

This guide takes **anyone** — no prior knowledge of this repo — from an empty
machine to a running STT/TTS service, locally or in the cloud. Follow it top to
bottom, or jump to the path you need:

- [1. What you're getting](#1-what-youre-getting)
- [2. Prerequisites](#2-prerequisites)
- [3. Run it locally (Python) — 5 minutes](#3-run-it-locally-python--5-minutes)
- [4. Run it with Docker](#4-run-it-with-docker)
- [5. Make your first requests](#5-make-your-first-requests)
- [6. Live (real-time) transcription](#6-live-real-time-transcription)
- [7. Choose your engines](#7-choose-your-engines)
- [8. Turn on production security](#8-turn-on-production-security)
- [9. Develop & contribute](#9-develop--contribute)
- [10. Deploy to a cloud](#10-deploy-to-a-cloud)
- [11. Troubleshooting](#11-troubleshooting)
- [12. Command cheat-sheet](#12-command-cheat-sheet)

---

## 1. What you're getting

A FastAPI service with three endpoints (plus health/metrics):

| Endpoint | What it does |
|---|---|
| `POST /api/v1/transcribe` | Audio file in → text out (batch STT) |
| `WS /api/v1/live-transcribe` | Stream microphone/PCM audio in → live partial/final text out |
| `POST /api/v1/synthesize` | Text in → audio file out (TTS) |

Languages: **English (`en`), Hebrew (`he`), Arabic (`ar`)**. Engines are
switchable by config: fully **local** (faster-whisper + edge-tts, no API keys)
or **remote** (OpenAI / Azure / AWS).

## 2. Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| **Python 3.11+** | running from source | `python3 --version` |
| **ffmpeg** | decoding mp3/m4a/webm uploads (wav/flac work without it) | `ffmpeg -version` |
| **Docker** | container path (§4) and cloud image builds (§10) | `docker --version` |
| **Terraform ≥ 1.5** | cloud deployment (§10) only | `terraform version` |
| A cloud CLI (`aws` / `az` / `gcloud` / `oci`) | only the cloud you deploy to | — |

Install ffmpeg: `sudo apt-get install ffmpeg` (Debian/Ubuntu) · `brew install ffmpeg` (macOS).

## 3. Run it locally (Python) — 5 minutes

```bash
# 1. Clone and enter the repo
git clone https://github.com/yaronyudov/speech-bridge.git
cd speech-bridge

# 2. Create a virtualenv and install dependencies
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r speech_engine/requirements.txt

# 3. Configure — defaults work out of the box (local engines, no keys)
cp .env.example .env

# 4. IMPORTANT for a first run: pick a small whisper model.
#    The default large-v3 downloads ~3 GB; "small" is ~460 MB and fast on CPU.
echo "STT_LOCAL_MODEL_SIZE=small" >> .env

# 5. Start the server
uvicorn speech_engine.main:app --host 0.0.0.0 --port 8000
```

You should see `STT engine ready: local` / `TTS engine ready: local-edge` in
the log. Verify:

```bash
curl http://localhost:8000/health     # {"status":"ok",...}
curl http://localhost:8000/ready      # 200 once the model finished loading
```

Interactive API docs (try requests from the browser): **http://localhost:8000/docs**

> **STT-only or TTS-only?** Set `ENABLE_TTS=false` or `ENABLE_STT=false` in
> `.env`. A TTS-only instance never loads the whisper model at all.

## 4. Run it with Docker

No Python needed on the host:

```bash
cp .env.example .env                       # optional — defaults work
docker compose up --build
```

That builds the hardened image (non-root, ffmpeg included) and mounts a
`model-cache` volume so the whisper model downloads **once**, not on every
restart. Same verification as §3.

Without compose:

```bash
docker build -t speech-bridge .
docker run --rm -p 8000:8000 --env-file .env -v model-cache:/models speech-bridge
```

GPU: install the NVIDIA container toolkit, add `--gpus all`, and use
CUDA-enabled ctranslate2/torch in the image.

## 5. Make your first requests

**Text-to-speech** (works immediately — edge-tts needs no keys, just internet):

```bash
curl -X POST http://localhost:8000/api/v1/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "hello world", "language": "en"}' --output hello.mp3

# Hebrew and Arabic work the same way:
curl -X POST http://localhost:8000/api/v1/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "שלום עולם", "language": "he"}' --output shalom.mp3
```

**Speech-to-text** (upload any wav/mp3/m4a; omit `language` to auto-detect):

```bash
curl -X POST "http://localhost:8000/api/v1/transcribe?language=en" \
     -F "audio=@hello.mp3"
# -> {"text": "Hello world."}
```

Or use the bundled clients:

```bash
pip install requests websockets
python examples/batch_client.py synthesize "hello world" --language en --out hi.mp3
python examples/batch_client.py transcribe hi.mp3 --language en
```

## 6. Live (real-time) transcription

The WebSocket expects raw **PCM 16-bit, 16 kHz, mono** binary frames
(~100 ms each) and streams JSON back:

```json
{"type": "partial", "text": "hello wor"}     // hypothesis, may change
{"type": "final",   "text": "Hello world."}  // committed segment
```

Try it with any audio file:

```bash
# 1. Convert to the expected format
ffmpeg -i speech.mp3 -ar 16000 -ac 1 -sample_fmt s16 speech_16k.wav

# 2. Stream it at real-time pace and watch live results
python examples/live_client.py speech_16k.wav --language en
```

Protocol details (control frames `{"event":"stop"}` / `{"event":"flush"}`,
close codes, browser notes): see the [README API reference](../README.md#websocket-apiv1live-transcribe--live-stt).
`examples/live_client.py` is a complete reference implementation.

> **Live STT on CPU?** Use `STT_LOCAL_MODEL_SIZE=small` (or `medium`), or a
> remote engine (`STT_ENGINE=azure` / `aws`) for true server-side streaming.

## 7. Choose your engines

Set in `.env` (or `config.yaml`, or real env vars — env wins):

### Recipe A — 100% free, no API keys (default)
```ini
STT_ENGINE=local          # faster-whisper on your CPU/GPU
TTS_ENGINE=local          # edge-tts neural voices
```

### Recipe B — OpenAI for everything (no local model download)
```ini
STT_ENGINE=openai
TTS_ENGINE=openai
OPENAI_API_KEY=sk-...
```

### Recipe C — Azure (best live-streaming latency + Hebrew TTS)
```ini
STT_ENGINE=azure
TTS_ENGINE=azure
AZURE_SPEECH_KEY=...          # Azure portal -> Speech service -> Keys
AZURE_SPEECH_REGION=eastus
```

### Recipe D — AWS
```ini
STT_ENGINE=aws                # Amazon Transcribe streaming
TTS_ENGINE=aws                # Amazon Polly — NOTE: no Hebrew voice
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

Mix and match freely (e.g. local STT + Azure TTS). Restart the server after
changing engines. Caveats: Polly and Coqui XTTS have **no Hebrew** voice —
requests for `he` on those return a clear 400 pointing you to alternatives.

## 8. Turn on production security

Everything is relaxed for local dev. Before exposing the service:

```ini
# .env
ENABLE_AUTH=true
API_KEYS=your-strong-key-1,your-strong-key-2
RATE_LIMIT=60/minute
```

Clients then authenticate with a header (REST) or query param (WebSocket):

```bash
curl -H "X-API-Key: your-strong-key-1" -X POST ...
python examples/batch_client.py --api-key your-strong-key-1 transcribe a.wav
python examples/live_client.py a.wav --language en --api-key your-strong-key-1
```

Also review: request caps (`MAX_UPLOAD_BYTES`, `MAX_WS_SESSION_SECONDS`, …),
`CORS_ALLOW_ORIGINS` for browser clients, TLS termination at your load
balancer, and a secrets manager instead of plaintext keys
(`SECRETS_BACKEND` — see the [README](../README.md#secrets-from-a-cloud-manager)).
Full checklist: [`SECURITY.md`](../SECURITY.md) and [`docs/PRODUCTION.md`](PRODUCTION.md).

## 9. Develop & contribute

```bash
make install        # runtime + dev deps (pytest, ruff, mypy, pre-commit)
make run            # uvicorn with autoreload
make test           # pytest — fully offline, models are stubbed
make check          # lint + typecheck + tests (what CI runs)
pre-commit install  # optional: auto-format on commit
```

Project map (where to change what):

```
speech_engine/config.py            all settings (pydantic-settings)
speech_engine/api/                 HTTP + WebSocket routes
speech_engine/core/stt/            STT engines: base.py (interface), local.py, remote.py, factory.py
speech_engine/core/tts/            TTS engines (same shape)
speech_engine/core/constants.py    language codes & per-provider voice maps
tests/                             offline pytest suite (stubs in conftest.py)
infra/terraform/                   cloud deployment modules
```

Adding a new engine = subclass `BaseSTTEngine`/`BaseTTSEngine` → register in
the factory → add voice/locale mappings → extend the config `Literal`. Details:
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## 10. Deploy to a cloud

One Terraform module per cloud; each is self-contained and **everything is
optional** (bring your own network/registry/secrets or let the module create
them). Full reference: [`infra/terraform/README.md`](../infra/terraform/README.md).

The flow is identical on every cloud:

```
authenticate CLI  →  build & push image  →  fill in tfvars  →  terraform apply  →  test the URL
```

### 10.1 AWS (App Runner, ~10 minutes)

```bash
# 0. Authenticate
aws configure                     # or SSO / env vars

# 1. Configure
cd infra/terraform/modules/aws
cp ../../envs/aws.example.tfvars aws.tfvars
$EDITOR aws.tfvars                # set alert_emails, budget, app_env, secrets

# 2. Create the registry (and everything else) — first apply also creates ECR
terraform init
terraform apply -var-file=aws.tfvars      # note the ecr_repository_url output

# 3. Build & push the image into it
cd ../../../..                            # repo root
./infra/terraform/scripts/build_and_push.sh aws <ecr_repository_url>

# 4. Re-apply so App Runner picks up the pushed image
cd infra/terraform/modules/aws
terraform apply -var-file=aws.tfvars

# 5. Test
curl "$(terraform output -raw service_url)/health"
```

Kill switch: **already active** — the grace budget stops the EC2 instance
(vm runtime) or attaches a deny policy to the app's role (serverless).

### 10.2 GCP (Cloud Run)

```bash
gcloud auth login && gcloud config set project <PROJECT>
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
    secretmanager.googleapis.com billingbudgets.googleapis.com

cd infra/terraform/modules/gcp
cp ../../envs/gcp.example.tfvars gcp.tfvars && $EDITOR gcp.tfvars
terraform init && terraform apply -var-file=gcp.tfvars

cd ../../../..
./infra/terraform/scripts/build_and_push.sh gcp \
    <region>-docker.pkg.dev/<PROJECT>/speech-bridge
cd infra/terraform/modules/gcp && terraform apply -var-file=gcp.tfvars

curl "$(terraform output -raw service_url)/health"

# Kill switch (recommended): deploy the budget-triggered function
../../scripts/deploy_gcp_killswitch.sh <PROJECT> <region> \
    speech-bridge speech-bridge-killswitch scale_zero
```

### 10.3 Azure (Container Apps)

```bash
az login

cd infra/terraform/modules/azure
cp ../../envs/azure.example.tfvars azure.tfvars && $EDITOR azure.tfvars
terraform init && terraform apply -var-file=azure.tfvars

cd ../../../..
./infra/terraform/scripts/build_and_push.sh azure <acr_login_server>
cd infra/terraform/modules/azure && terraform apply -var-file=azure.tfvars

curl "https://$(terraform output -raw service_fqdn)/health"
```

Kill switch: point `killswitch_webhook_uri` at an Automation runbook that
scales to zero — sample body in the
[IaC README](../infra/terraform/README.md#wiring-the-kill-switch-automation).

### 10.4 Oracle Cloud (Container Instances)

```bash
oci setup config                              # one-time CLI setup
docker login <region>.ocir.io                 # OCIR: user = <namespace>/<user>, password = auth token

cd infra/terraform/modules/oci
cp ../../envs/oci.example.tfvars oci.tfvars && $EDITOR oci.tfvars   # compartment OCID, AD, image_uri
terraform init && terraform apply -var-file=oci.tfvars

curl "http://$(terraform output -raw vm_public_ip 2>/dev/null || echo '<container-instance-ip>'):8000/health"
```

Kill switch: subscribe an OCI Function to the `killswitch_topic_id` output
(guidance in the IaC README).

### 10.5 Understand your cost protection (all clouds)

Three layers, configured in your tfvars:

1. `max_instances` / instance size — **hard architectural ceiling**, always on.
2. `monthly_budget` + `alert_emails` — **email alerts** at 50/80/100%.
3. `enable_hard_cap` + `hard_cap_amount` — the **kill switch** (defaults to the
   regular budget amount when unset).

Confirm the alert-subscription emails, and test the kill-switch automation once
before trusting it (budgets evaluate spend a few times per day — enforcement is
not instantaneous).

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| First start hangs / slow | The whisper model is downloading. Use `STT_LOCAL_MODEL_SIZE=small` (§3 step 4) |
| `Could not decode audio file … ensure ffmpeg is installed` | Install ffmpeg (§2) — needed for mp3/m4a/webm uploads |
| `401 Invalid or missing API key` | Auth is on: send `X-API-Key` header / `--api-key` / `?api_key=` (WS) |
| `429 Rate limit exceeded` | Raise `RATE_LIMIT` or slow down |
| `413` on upload / WS closes 4413 | Raise `MAX_UPLOAD_BYTES` / `MAX_WS_BYTES` / `MAX_WS_SESSION_SECONDS` |
| WS closes 4400 immediately | Missing/unsupported `language` — pass `?language=en\|he\|ar` |
| Live partials are garbage | Stream must be raw PCM 16-bit / 16 kHz / mono (§6 step 1) |
| `Amazon Polly has no voice for 'he'` | Expected — use `TTS_ENGINE=azure` or `local` for Hebrew |
| 404 on `/transcribe` or `/synthesize` | That subsystem is disabled — check `/health` |
| `/ready` returns 503 | Normal during startup; wait for the model warm-up to finish |
| Cloud deploy: image pull fails | Push the image first (§10 step 3) and check `image_uri` |

## 12. Command cheat-sheet

```bash
# Local
uvicorn speech_engine.main:app --port 8000    # run from source
docker compose up --build                     # run in Docker
make run / make test / make check             # dev loop

# Smoke test
curl localhost:8000/health && curl localhost:8000/ready

# Clients
python examples/batch_client.py transcribe audio.wav --language he
python examples/batch_client.py synthesize "hello" --language en --out hi.mp3
python examples/live_client.py audio_16k.wav --language en

# Cloud (any of aws|gcp|azure|oci)
cd infra/terraform/modules/<cloud>
cp ../../envs/<cloud>.example.tfvars <cloud>.tfvars   # edit, then:
terraform init && terraform apply -var-file=<cloud>.tfvars
```
