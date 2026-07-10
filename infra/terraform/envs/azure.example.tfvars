# Example variables for the Azure module. Copy to azure.tfvars and edit.
#   cd infra/terraform/modules/azure
#   terraform init
#   terraform apply -var-file=../../envs/azure.tfvars

name     = "speech-bridge"
location = "eastus"

create_resource_group = true
resource_group_name   = "speech-bridge-rg"

# ---- Compute: "serverless" (Container Apps) | "vm" | "none" ----
runtime         = "serverless"
image_uri       = "" # e.g. speechbridgeacr.azurecr.io/speech-bridge:latest
create_registry = true

min_instances = 0
max_instances = 3

app_env = {
  ENABLE_STT      = "true"
  ENABLE_TTS      = "true"
  ENABLE_AUTH     = "true"
  SECRETS_BACKEND = "azure"
  SECRETS_PREFIX  = "https://speech-bridge-kv.vault.azure.net/"
}

# ---- Optional Key Vault secrets (SECRETS_BACKEND=azure) ----
create_secrets = true
secrets = {
  OPENAI_API_KEY = "sk-..."
  API_KEYS       = "prod-key-1,prod-key-2"
}

# ---- Two-tier budget ----
enable_budget     = true
monthly_budget    = 50
alert_thresholds  = [50, 80, 100]
alert_emails      = ["ops@example.com"]
budget_start_date = "2026-07-01T00:00:00Z" # first of a recent month
enable_hard_cap   = true
hard_cap_amount   = 60
# Point this at an Automation runbook / Function webhook to scale to zero:
killswitch_webhook_uri = ""
