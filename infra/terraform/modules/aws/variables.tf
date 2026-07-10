# ---------------------------------------------------------------------------
# speech-bridge — AWS module inputs.
#
# Design principle: every piece is OPTIONAL. Toggle each sub-resource with a
# `create_*` flag; when false, pass an existing id/uri instead. `runtime`
# selects the compute shape (or "none" to provision only budgets/secrets).
# ---------------------------------------------------------------------------

variable "name" {
  description = "Name prefix for all created resources."
  type        = string
  default     = "speech-bridge"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Tags applied to every resource (used for cost allocation)."
  type        = map(string)
  default     = {}
}

# ----------------------------------------------------------------- compute --
variable "runtime" {
  description = "Compute shape: 'serverless' (App Runner), 'vm' (EC2), or 'none'."
  type        = string
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "vm", "none"], var.runtime)
    error_message = "runtime must be one of: serverless, vm, none."
  }
}

variable "image_uri" {
  description = "Container image URI to deploy. Required unless create_registry builds one you push to."
  type        = string
  default     = ""
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "vCPU for the App Runner service (e.g. '1 vCPU', '2 vCPU')."
  type        = string
  default     = "1 vCPU"
}

variable "memory" {
  description = "Memory for the App Runner service (e.g. '2 GB', '4 GB')."
  type        = string
  default     = "2 GB"
}

variable "min_instances" {
  description = "Minimum instances. 0 enables scale-to-zero (cost cap)."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Hard ceiling on instances (architectural cost cap)."
  type        = number
  default     = 2
}

variable "max_concurrency" {
  description = "Max concurrent requests per instance."
  type        = number
  default     = 40
}

variable "vm_instance_type" {
  description = "EC2 instance type when runtime = 'vm'."
  type        = string
  default     = "t3.large"
}

variable "app_env" {
  description = "Non-secret environment variables passed to the app (e.g. ENABLE_STT)."
  type        = map(string)
  default     = {}
}

# ----------------------------------------------------------------- network --
variable "create_network" {
  description = "Create a VPC/subnets. If false, supply existing_subnet_ids for VM runtime."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR for the created VPC (when create_network = true)."
  type        = string
  default     = "10.40.0.0/16"
}

variable "existing_subnet_ids" {
  description = "Existing subnet ids to use when create_network = false (VM runtime)."
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------- registry --
variable "create_registry" {
  description = "Create an ECR repository to push the image to."
  type        = bool
  default     = false
}

# ----------------------------------------------------------------- secrets --
variable "create_secrets" {
  description = "Create Secrets Manager entries for the app credentials below."
  type        = bool
  default     = false
}

variable "secrets" {
  description = "Map of secret name -> value to store (only when create_secrets = true)."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# ------------------------------------------------------------------ budget --
variable "enable_budget" {
  description = "Create the monthly budget + alert notifications."
  type        = bool
  default     = true
}

variable "monthly_budget" {
  description = "Regular monthly budget in USD. Drives alert notifications."
  type        = number
  default     = 50
}

variable "alert_thresholds" {
  description = "Percentages of the regular budget that trigger alert emails."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "alert_emails" {
  description = "Email addresses that receive budget alerts."
  type        = list(string)
  default     = []
}

variable "enable_hard_cap" {
  description = "Enable the grace-tier kill switch (stops the service when hit)."
  type        = bool
  default     = true
}

variable "hard_cap_amount" {
  description = "Grace budget (USD) that triggers the kill switch. Null => equals monthly_budget."
  type        = number
  default     = null
}
