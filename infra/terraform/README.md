# speech-bridge — Infrastructure as Code (Terraform)

Deploy speech-bridge to **AWS, Azure, GCP, or Oracle Cloud** with one
self-contained Terraform module per cloud. Every piece is **optional**: create
a resource or bring your own, pick a runtime shape, and cap spend with a
two-tier budget + kill switch.

```
infra/terraform/
├── modules/
│   ├── aws/     App Runner or EC2 · ECR · Secrets Manager · Budgets + Budget Actions
│   ├── azure/   Container Apps or VM · ACR · Key Vault · Consumption Budget + Action Group
│   ├── gcp/     Cloud Run or GCE · Artifact Registry · Secret Manager · Billing Budget + Pub/Sub
│   └── oci/     Container Instances or VM · OCIR · Vault · Budget + ONS
├── envs/        *.example.tfvars per cloud
└── scripts/     build_and_push.sh (image build + registry push helper)
```

## Quickstart

```bash
# 1. Build & push the image (or set image_uri to an existing one)
./infra/terraform/scripts/build_and_push.sh gcp us-central1-docker.pkg.dev/my-proj/speech-bridge

# 2. Configure
cd infra/terraform/modules/gcp
cp ../../envs/gcp.example.tfvars gcp.tfvars   # then edit

# 3. Deploy
terraform init
terraform apply -var-file=gcp.tfvars
```

`terraform output service_url` (or `service_fqdn` / `vm_public_ip`) prints the
endpoint. Each module authenticates with your normal cloud CLI/session — no
credentials live in Terraform.

## Everything is optional

Each module exposes `create_*` flags and `existing_*` passthroughs so it slots
into an account that already has networking/registries/secrets, or builds them
from nothing:

| Concern | Create it | Bring your own |
|---|---|---|
| Compute | `runtime = "serverless" \| "vm"` | `runtime = "none"` (budgets/secrets only) |
| Network | `create_network = true` | `existing_subnet_id(s) = [...]` |
| Registry | `create_registry = true` | `image_uri = "<registry>/speech-bridge:latest"` |
| Secrets | `create_secrets = true` + `secrets = {...}` | plaintext `app_env`, or point `SECRETS_PREFIX` at existing secrets |
| Resource group (Azure) | `create_resource_group = true` | `create_resource_group = false` + existing `resource_group_name` |
| Budget | `enable_budget = true` | `enable_budget = false` |
| Kill switch | `enable_hard_cap = true` | `enable_hard_cap = false` |

The `runtime = "none"` mode is useful to attach **only** budgets/alerts to an
account whose workload is already running elsewhere.

## Runtime shapes

`runtime` picks the compute per deployment:

| Cloud | `serverless` | `vm` |
|---|---|---|
| AWS | App Runner | EC2 (Docker via user-data) |
| Azure | Container Apps (scale-to-zero) | Linux VM |
| GCP | Cloud Run v2 (scale-to-zero) | GCE (Container-Optimized OS) |
| OCI | Container Instances | Compute VM |

Serverless is the default and gives the strongest cost story (scale-to-zero on
Cloud Run / Container Apps; App Runner keeps ≥1 provisioned instance). The `vm`
path suits **local GPU whisper** (`STT_ENGINE=local` with a GPU instance type).

## Cost controls — two-tier budget + kill switch

Spend is bounded by three independent layers:

1. **Architectural caps (always on).** `max_instances`/`max_replicas`,
   per-instance `max_concurrency`, and fixed instance sizes bound the burn rate
   regardless of budgets. A single Container Instance / VM is inherently capped.
2. **Regular budget → alerts.** `monthly_budget` with `alert_thresholds`
   (50/80/100%) emails `alert_emails`. Informational; nothing is stopped.
3. **Grace budget → kill switch.** `hard_cap_amount` (defaults to
   `monthly_budget` when null) is the hard ceiling. On breach the module takes
   real action — see the honest per-cloud matrix below.

```
spend ──►  50% ─── 80% ─── 100% (monthly_budget)  ·········  hard_cap_amount
           └────── email alerts ──────┘                       └── KILL SWITCH ──┘
```

Set `hard_cap_amount` a little above `monthly_budget` to get a warning buffer
before the switch trips; leave it `null` to trip exactly at the regular budget.

### Per-cloud enforcement (be honest about the limits)

| Cloud | Kill-switch mechanism | Native hard stop? |
|---|---|---|
| **AWS** | Native **Budget Action**. `vm`: SSM `STOP_EC2_INSTANCES` (real stop). serverless/none: `APPLY_IAM_POLICY` deny attached to `killswitch_role_arn` — point the app's AWS creds at that role to revoke paid-API access. | ✅ EC2 · ⚠️ App Runner base keeps billing until paused |
| **GCP** | Billing budget → **Pub/Sub** topic → deploy the kill-switch function (`scale_zero` sets Cloud Run max=0, or `disable_billing` detaches billing). | ✅ with the function (incl. nuclear disable-billing) |
| **Azure** | Consumption budget → **Action Group** (email + optional `killswitch_webhook_uri`). Point the webhook at an Automation runbook/Function that scales the Container App to 0. | ⚠️ automation only (no native stop) |
| **OCI** | Budget alert + **ONS topic**. Subscribe a Function that stops the Container Instance/VM via an Events rule. | ⚠️ automation only (advisory budgets) |

AWS and GCP can fully self-enforce; Azure and OCI notify + trigger automation
you wire to the provided webhook/topic. In all four, the architectural caps
(layer 1) remain a guaranteed ceiling even if the automation is not deployed.

## Secrets

With `create_secrets = true` the module stores `secrets = { NAME = value }` in
the cloud's secret manager. Run the app with `SECRETS_BACKEND=<cloud>` and
`SECRETS_PREFIX` set (see each `*.example.tfvars`) so it resolves credentials at
startup instead of reading plaintext env vars. Secret names mirror the app's
setting names (`OPENAI_API_KEY`, `AZURE_SPEECH_KEY`, `API_KEYS`, …).

## Remote state

Each `versions.tf` ships a commented backend block (S3+DynamoDB / azurerm /
GCS / OCI Object Storage). Uncomment and fill it in for team use; the default is
local state.

## Verifying the modules

```bash
make tf-fmt          # formatting (offline)
make tf-validate     # terraform validate per module (needs provider download)
make tf-plan-aws     # plan (needs cloud credentials + a *.tfvars)
```

> The CI pipeline runs `fmt -check` + `validate` + `tflint`. A full `plan`
> requires real cloud credentials and provider registry access, so it is run
> manually / in the gated deploy workflow, not in PR CI.
