# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's **Report a vulnerability**
(Security → Advisories) rather than opening a public issue. We aim to
acknowledge reports within a few business days.

## Hardening checklist for operators

speech-bridge ships secure-by-default building blocks, but production
deployments should enable them:

- **Authentication** — set `ENABLE_AUTH=true` and provide `API_KEYS`. Without
  it, the API is open. Keys are compared in constant time.
- **Rate limiting** — `ENABLE_RATE_LIMIT=true` with a sensible `RATE_LIMIT`
  bounds abuse and the cost of the paid remote STT/TTS APIs.
- **Request caps** — `MAX_UPLOAD_BYTES`, `MAX_TEXT_CHARS`, `MAX_WS_BYTES`, and
  `MAX_WS_SESSION_SECONDS` bound resource use per request/session.
- **Secrets** — prefer `SECRETS_BACKEND` (AWS Secrets Manager / Azure Key
  Vault / GCP Secret Manager / OCI Vault) over plaintext env vars. Never commit
  `.env`, `config.yaml`, or `*.tfvars` (all git-ignored).
- **Transport** — terminate TLS at your load balancer / ingress; the app
  serves plain HTTP inside the trust boundary.
- **CORS** — set `CORS_ALLOW_ORIGINS` explicitly for browser clients; it is
  disabled (no cross-origin) by default.
- **Container** — the image runs as a non-root user; keep it updated and scan
  it (CI runs Trivy).
- **Cost controls** — deploy the Terraform two-tier budget + kill switch so a
  runaway workload cannot exceed budget (see `infra/terraform/README.md`).

## Data handling

Uploaded audio and synthesized files are written to a temp directory and
deleted immediately after each request (uploads in a `finally` block;
synthesized files via `BackgroundTasks`). No audio or transcripts are persisted
by the service. When using remote engines, audio/text is sent to the configured
provider (OpenAI / Azure / AWS) subject to their data policies.

## Supported versions

The latest release on the default branch receives security fixes.
