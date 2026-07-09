# Example variables for the OCI module. Copy to oci.tfvars and edit.
#   cd infra/terraform/modules/oci
#   terraform init
#   terraform apply -var-file=../../envs/oci.tfvars

name                = "speech-bridge"
compartment_ocid    = "ocid1.compartment.oc1..aaaa..."
region              = "us-ashburn-1"
availability_domain = "Uocm:US-ASHBURN-AD-1"

# ---- Compute: "serverless" (Container Instances) | "vm" | "none" ----
runtime   = "serverless"
image_uri = "iad.ocir.io/mynamespace/speech-bridge:latest"

ocpus         = 1
memory_in_gbs = 4

# ---- Network: create a VCN+subnet, or bring your own ----
create_network     = true
existing_subnet_id = ""

app_env = {
  ENABLE_STT      = "true"
  ENABLE_TTS      = "true"
  ENABLE_AUTH     = "true"
  SECRETS_BACKEND = "oci"
  SECRETS_PREFIX  = "ocid1.vault.oc1..aaaa..." # your Vault OCID
}

# ---- Two-tier budget ----
enable_budget    = true
monthly_budget   = 50
alert_thresholds = [50, 80, 100]
alert_emails     = ["ops@example.com"]
enable_hard_cap  = true
hard_cap_amount  = 60
