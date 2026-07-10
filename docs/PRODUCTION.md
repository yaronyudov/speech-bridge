# Production readiness

This document is the operator's checklist plus the forward roadmap. It reflects
a "make it production-grade from every POV" review of speech-bridge.

## What's already in place

| Area | Capability |
|---|---|
| **Deploy** | Terraform for AWS/Azure/GCP/OCI; serverless or VM; everything optional |
| **Cost control** | Two-tier budget + kill switch; architectural instance/concurrency caps |
| **AuthN/Z** | API-key auth (REST + WS); constant-time comparison |
| **Abuse/cost guards** | Rate limiting; upload/text/WS size & time caps |
| **Secrets** | Cloud secret-manager resolution (AWS/Azure/GCP/OCI) or env |
| **Observability** | Prometheus `/metrics`, `/health` + `/ready`, optional OTEL traces |
| **Container** | Multi-stage, non-root, `HEALTHCHECK`, model-cache volume |
| **CI/CD** | Lint, format, type-check, tests, image build + Trivy scan, TF validate; gated deploy |
| **Docs** | README, IaC guide, CONTRIBUTING, SECURITY, CHANGELOG |
| **Tests** | Offline pytest suite across config, audio, engines, API, streaming |

## Pre-launch checklist

- [ ] `ENABLE_AUTH=true` with rotated `API_KEYS`; TLS terminated at the edge.
- [ ] `SECRETS_BACKEND` set; no plaintext credentials in env/`config.yaml`.
- [ ] Budget + `enable_hard_cap` deployed; alert emails verified; kill-switch
      automation (GCP function / Azure runbook / OCI function) wired where the
      cloud needs it.
- [ ] `RATE_LIMIT` and request caps tuned to expected traffic.
- [ ] Readiness probe (`/ready`) wired to the load balancer; liveness to
      `/health`. Model-cache volume mounted so cold starts don't re-download.
- [ ] `/metrics` scraped; alerts on error rate, latency, saturation.
- [ ] Log aggregation configured; `LOG_LEVEL` appropriate.
- [ ] Right-sized instances; `max_instances`/replicas set; scale-to-zero where
      acceptable.
- [ ] Image scanned (Trivy) and base image patched.

## Roadmap — "master product guy" ideas (not yet built)

Prioritized backlog to take the service further. None are required to run
today; they're where the product goes next.

### Reliability & scale
- **Multi-region + failover** with health-based routing; region-aware model
  caches.
- **Autoscaling on queue depth / concurrency** rather than CPU alone; a warm
  model pool or pre-baked model image to eliminate cold-start latency.
- **Blue-green / canary deploys** with automated rollback on SLO regression.
- **SLOs + error budgets** (latency, availability, WER) with alerting.

### Product features
- **Speaker diarization** and **word-level timestamps** for STT.
- **Translation pipeline** (he/ar ↔ en) chaining STT → MT → TTS.
- **Streaming TTS** (chunked audio out) for low-latency playback.
- **Audio result caching** keyed by content hash to skip repeat synthesis/
  transcription and cut provider cost.
- **Batch/async jobs API** for large files with webhooks on completion.
- **SSML support** and per-request voice/speed/pitch selection.

### Multi-tenancy & billing
- **Per-tenant API keys, quotas, and usage metering**; usage-based billing
  export.
- **Cost-per-request dashboards** and a consistent **resource-tagging strategy**
  for cloud cost allocation.
- **Admin/usage dashboard UI**.

### Security & compliance
- **WAF + DDoS protection** and an API gateway / CDN in front.
- **Data-retention & PII policy**, audit logging, and **GDPR** controls
  (right-to-erasure, data residency).
- **OAuth2 / JWT / mTLS** auth options beyond API keys; secret rotation.

### Quality & delivery
- **Load & soak testing** in CI (k6/Locust) with performance budgets.
- **Contract tests** against each cloud provider's STT/TTS SDK.
- **gRPC interface** option alongside REST/WebSocket.
- **Helm chart** for Kubernetes deployments in addition to the serverless/VM
  Terraform paths.
