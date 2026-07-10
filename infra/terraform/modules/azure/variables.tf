# ---------------------------------------------------------------------------
# speech-bridge — Azure module inputs. Every sub-resource is optional; runtime
# selects Container Apps (serverless), a Linux VM, or none.
# ---------------------------------------------------------------------------

variable "name" {
  description = "Name prefix for all created resources."
  type        = string
  default     = "speech-bridge"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "tags" {
  description = "Tags applied to resources (cost allocation)."
  type        = map(string)
  default     = {}
}

# ------------------------------------------------------------ resource group
variable "create_resource_group" {
  description = "Create the resource group. If false, resource_group_name must exist."
  type        = bool
  default     = true
}

variable "resource_group_name" {
  description = "Resource group name (created or existing)."
  type        = string
  default     = "speech-bridge-rg"
}

# ----------------------------------------------------------------- compute --
variable "runtime" {
  description = "Compute shape: 'serverless' (Container Apps), 'vm', or 'none'."
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
  description = "Container App vCPU (e.g. 0.5, 1.0, 2.0)."
  type        = number
  default     = 1.0
}

variable "memory" {
  description = "Container App memory (e.g. '2Gi')."
  type        = string
  default     = "2Gi"
}

variable "min_instances" {
  description = "Minimum replicas. 0 = scale to zero (cost cap)."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum replicas (architectural cost cap)."
  type        = number
  default     = 3
}

variable "vm_size" {
  description = "VM size when runtime = 'vm'."
  type        = string
  default     = "Standard_D2s_v5"
}

variable "vm_admin_username" {
  type    = string
  default = "azureuser"
}

variable "vm_ssh_public_key" {
  description = "SSH public key for the VM admin user (required for vm runtime)."
  type        = string
  default     = ""
}

variable "app_env" {
  description = "Non-secret environment variables for the app."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------- registry --
variable "create_registry" {
  description = "Create an Azure Container Registry."
  type        = bool
  default     = false
}

# ----------------------------------------------------------------- secrets --
variable "create_secrets" {
  description = "Create a Key Vault and store app credentials in it."
  type        = bool
  default     = false
}

variable "secrets" {
  description = "Map of secret name -> value (only when create_secrets = true)."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# ------------------------------------------------------------------ budget --
variable "enable_budget" {
  description = "Create the monthly consumption budget + alerts."
  type        = bool
  default     = true
}

variable "monthly_budget" {
  description = "Regular monthly budget (USD/your billing currency). Drives alerts."
  type        = number
  default     = 50
}

variable "alert_thresholds" {
  description = "Percentages of the regular budget that trigger alerts."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "alert_emails" {
  description = "Emails that receive budget alerts."
  type        = list(string)
  default     = []
}

variable "budget_start_date" {
  description = "Budget start (must be first of a month, RFC3339). Set to a recent month."
  type        = string
  default     = "2026-01-01T00:00:00Z"
}

variable "budget_end_date" {
  description = "Budget end (RFC3339)."
  type        = string
  default     = "2030-01-01T00:00:00Z"
}

variable "enable_hard_cap" {
  description = "Create the grace budget wired to a kill-switch action group."
  type        = bool
  default     = true
}

variable "hard_cap_amount" {
  description = "Grace budget that triggers the kill switch. Null => monthly_budget."
  type        = number
  default     = null
}

variable "killswitch_webhook_uri" {
  description = "Optional webhook (Automation runbook / Function) the kill switch calls to scale to zero."
  type        = string
  default     = ""
}
