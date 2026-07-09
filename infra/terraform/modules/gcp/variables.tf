# ---------------------------------------------------------------------------
# speech-bridge — GCP module inputs. Every sub-resource is optional; runtime
# selects Cloud Run (serverless), a GCE VM, or none.
# ---------------------------------------------------------------------------

variable "name" {
  description = "Name prefix for all created resources."
  type        = string
  default     = "speech-bridge"
}

variable "project" {
  description = "GCP project id."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone (VM runtime)."
  type        = string
  default     = "us-central1-a"
}

variable "labels" {
  description = "Labels applied to resources (cost allocation)."
  type        = map(string)
  default     = {}
}

# ----------------------------------------------------------------- compute --
variable "runtime" {
  description = "Compute shape: 'serverless' (Cloud Run), 'vm' (GCE), or 'none'."
  type        = string
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "vm", "none"], var.runtime)
    error_message = "runtime must be one of: serverless, vm, none."
  }
}

variable "image_uri" {
  description = "Container image URI. Required unless create_registry is used."
  type        = string
  default     = ""
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "cpu" {
  description = "Cloud Run CPU limit (e.g. '1', '2')."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Cloud Run memory limit (e.g. '2Gi')."
  type        = string
  default     = "2Gi"
}

variable "min_instances" {
  description = "Minimum Cloud Run instances. 0 = scale to zero (cost cap)."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum instances (architectural cost cap)."
  type        = number
  default     = 3
}

variable "max_concurrency" {
  description = "Max concurrent requests per Cloud Run instance."
  type        = number
  default     = 40
}

variable "vm_machine_type" {
  description = "GCE machine type when runtime = 'vm'."
  type        = string
  default     = "e2-standard-2"
}

variable "allow_unauthenticated" {
  description = "Allow public (unauthenticated) access to the Cloud Run service."
  type        = bool
  default     = true
}

variable "app_env" {
  description = "Non-secret environment variables for the app."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------- registry --
variable "create_registry" {
  description = "Create an Artifact Registry Docker repository."
  type        = bool
  default     = false
}

# ----------------------------------------------------------------- secrets --
variable "create_secrets" {
  description = "Create Secret Manager secrets for app credentials."
  type        = bool
  default     = false
}

variable "secrets" {
  description = "Map of secret id -> value (only when create_secrets = true)."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# ------------------------------------------------------------------ budget --
variable "billing_account" {
  description = "Billing account id (required for budgets, e.g. 000000-AAAAAA-BBBBBB)."
  type        = string
  default     = ""
}

variable "enable_budget" {
  description = "Create the monthly billing budget + alerts."
  type        = bool
  default     = true
}

variable "monthly_budget" {
  description = "Regular monthly budget (USD). Drives alerts."
  type        = number
  default     = 50
}

variable "alert_thresholds" {
  description = "Budget fractions (0-1) that trigger alerts."
  type        = list(number)
  default     = [0.5, 0.8, 1.0]
}

variable "alert_emails" {
  description = "Emails that receive budget alerts."
  type        = list(string)
  default     = []
}

variable "enable_hard_cap" {
  description = "Create the grace budget + Pub/Sub kill-switch trigger."
  type        = bool
  default     = true
}

variable "hard_cap_amount" {
  description = "Grace budget (USD) that triggers the kill switch. Null => monthly_budget."
  type        = number
  default     = null
}

variable "hard_cap_mode" {
  description = "Kill-switch behaviour: 'scale_zero' (recommended) or 'disable_billing'."
  type        = string
  default     = "scale_zero"

  validation {
    condition     = contains(["scale_zero", "disable_billing"], var.hard_cap_mode)
    error_message = "hard_cap_mode must be 'scale_zero' or 'disable_billing'."
  }
}
