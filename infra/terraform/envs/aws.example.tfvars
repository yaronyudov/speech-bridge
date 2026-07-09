# Example variables for the AWS module. Copy to aws.tfvars and edit.
#   cd infra/terraform/modules/aws
#   terraform init
#   terraform apply -var-file=../../envs/aws.tfvars

name   = "speech-bridge"
region = "us-east-1"

# ---- Compute: "serverless" (App Runner) | "vm" (EC2) | "none" ----
runtime         = "serverless"
image_uri       = "" # e.g. 1234567890.dkr.ecr.us-east-1.amazonaws.com/speech-bridge:latest
create_registry = true

min_instances   = 0
max_instances   = 2
max_concurrency = 40

# Non-secret app config (mirrors .env). Credentials should come from secrets.
app_env = {
  ENABLE_STT      = "true"
  ENABLE_TTS      = "true"
  STT_ENGINE      = "openai"
  TTS_ENGINE      = "openai"
  ENABLE_AUTH     = "true"
  SECRETS_BACKEND = "aws"
  SECRETS_PREFIX  = "speech-bridge/"
}

# ---- Optional Secrets Manager entries (SECRETS_BACKEND=aws) ----
create_secrets = true
secrets = {
  OPENAI_API_KEY = "sk-..."
  API_KEYS       = "prod-key-1,prod-key-2"
}

# ---- Two-tier budget ----
enable_budget    = true
monthly_budget   = 50 # regular budget -> alerts
alert_thresholds = [50, 80, 100]
alert_emails     = ["ops@example.com"]
enable_hard_cap  = true
hard_cap_amount  = 60 # grace/kill-switch (null => equals monthly_budget)
