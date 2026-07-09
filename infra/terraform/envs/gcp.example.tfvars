# Example variables for the GCP module. Copy to gcp.tfvars and edit.
#   cd infra/terraform/modules/gcp
#   terraform init
#   terraform apply -var-file=../../envs/gcp.tfvars

name    = "speech-bridge"
project = "my-gcp-project"
region  = "us-central1"
zone    = "us-central1-a"

# ---- Compute: "serverless" (Cloud Run) | "vm" (GCE) | "none" ----
runtime               = "serverless"
image_uri             = "" # e.g. us-central1-docker.pkg.dev/my-gcp-project/speech-bridge/speech-bridge:latest
create_registry       = true
allow_unauthenticated = true

min_instances   = 0
max_instances   = 3
max_concurrency = 40

app_env = {
  ENABLE_STT      = "true"
  ENABLE_TTS      = "true"
  ENABLE_AUTH     = "true"
  SECRETS_BACKEND = "gcp"
  SECRETS_PREFIX  = "projects/my-gcp-project"
}

# ---- Optional Secret Manager secrets (SECRETS_BACKEND=gcp) ----
create_secrets = true
secrets = {
  OPENAI_API_KEY = "sk-..."
  API_KEYS       = "prod-key-1,prod-key-2"
}

# ---- Two-tier budget (requires the billing account id) ----
billing_account  = "000000-AAAAAA-BBBBBB"
enable_budget    = true
monthly_budget   = 50
alert_thresholds = [0.5, 0.8, 1.0] # fractions for GCP
alert_emails     = ["ops@example.com"]
enable_hard_cap  = true
hard_cap_amount  = 60
hard_cap_mode    = "scale_zero" # or "disable_billing"
