# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Multi-cloud Terraform IaC** (`infra/terraform/`) for AWS, Azure, GCP, and
  Oracle Cloud. One self-contained module per cloud; every sub-resource
  (network, registry, secrets, compute, budget) is optional via `create_*`
  flags with bring-your-own passthroughs. `runtime` selects serverless
  containers, an always-on VM, or `none` (budgets/secrets only).
- **Two-tier budget + kill switch** per cloud: a regular budget drives
  50/80/100% alert notifications; an optional grace budget (defaulting to the
  regular amount) triggers real enforcement — AWS Budget Actions, GCP
  Pub/Sub-triggered scale-to-zero/disable-billing, Azure action groups, OCI
  notifications — backed by always-on architectural caps (max instances,
  concurrency).
- **API authentication** (`ENABLE_AUTH`, `API_KEYS`, `X-API-Key`) for REST and
  the live-transcribe WebSocket handshake.
- **Rate limiting** (`ENABLE_RATE_LIMIT`, `RATE_LIMIT`) shared across REST and
  WebSocket, plus request caps (`MAX_UPLOAD_BYTES`, `MAX_WS_BYTES`,
  `MAX_WS_SESSION_SECONDS`) as cost guards.
- **Cloud secrets resolution** (`SECRETS_BACKEND`, `SECRETS_PREFIX`) for AWS
  Secrets Manager, Azure Key Vault, GCP Secret Manager, and OCI Vault.
- **Observability**: Prometheus `/metrics`, a `/ready` readiness probe split
  from `/health`, and optional OpenTelemetry tracing
  (`OTEL_EXPORTER_OTLP_ENDPOINT`). Optional CORS via `CORS_ALLOW_ORIGINS`.
- **Container hardening**: multi-stage, non-root Dockerfile with a `HEALTHCHECK`
  and a `/models` cache volume; `docker-compose.yml` and a `Makefile`.
- **CI/CD**: GitHub Actions for lint/format/type-check/test, Docker build +
  Trivy scan, and `terraform fmt`/`validate`/`tflint`; a gated manual deploy
  workflow; a PR template.
- **Test suite** (`tests/`): offline pytest coverage of config, constants,
  audio, factories, WebSocket plumbing, and the full API (auth, rate limiting,
  upload caps, streaming) with whisper/edge-tts stubbed.
- Docs: `infra/terraform/README.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `docs/PRODUCTION.md`, `docs/GETTING_STARTED.md` (step-by-step build / dev /
  deploy guide), and expanded root README (deployment + cost controls).
- `.dockerignore`; `--api-key` support in both example clients; the GCP
  kill-switch function deploy script
  (`infra/terraform/scripts/deploy_gcp_killswitch.sh`).

### Fixed
- `MAX_TEXT_CHARS` is now actually enforced on `/synthesize` (413); it was
  previously a dead setting shadowed by a hardcoded schema limit.
- Live-session time/size cap violations are now surfaced to the client as an
  error frame + close 4413 on the Azure and AWS streaming engines too (they
  previously died silently inside the audio pump task).
- `OTEL_SERVICE_NAME` / `OTEL_EXPORTER_OTLP_ENDPOINT` from `.env`/`config.yaml`
  are exported to the process environment so the OpenTelemetry SDK sees them.
- AWS App Runner now attaches the kill-switch IAM role
  (`instance_role_arn`), making the grace-budget deny policy effective without
  manual wiring.
- GCP: granted the Google billing-budget service account publish rights on the
  kill-switch Pub/Sub topic (notifications never arrived without it).
- Azure: the alerts budget is skipped when no alert emails are configured
  (azurerm rejects a budget with zero notifications).
- `docker compose up` no longer fails when `.env` is absent.

## [1.0.0]

### Added
- Initial speech-bridge service: batch STT (`/api/v1/transcribe`), live
  WebSocket STT (`/api/v1/live-transcribe`), and TTS (`/api/v1/synthesize`)
  for English, Hebrew, and Arabic.
- Local (faster-whisper, edge-tts / Coqui) and remote (Azure, OpenAI, AWS)
  engines behind Strategy/Factory abstractions, switchable by config.
- Partial modes via `ENABLE_STT` / `ENABLE_TTS` with conditional route
  mounting; pydantic-settings configuration; example clients; Dockerfile.
