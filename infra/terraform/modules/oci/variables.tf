# ---------------------------------------------------------------------------
# speech-bridge — OCI module inputs. Every sub-resource is optional; runtime
# selects Container Instances (serverless), a Compute VM, or none.
# ---------------------------------------------------------------------------

variable "name" {
  description = "Name prefix for all created resources."
  type        = string
  default     = "speech-bridge"
}

variable "compartment_ocid" {
  description = "Compartment OCID that owns the resources and the budget."
  type        = string
}

variable "region" {
  description = "OCI region identifier (e.g. us-ashburn-1)."
  type        = string
  default     = "us-ashburn-1"
}

variable "availability_domain" {
  description = "Availability domain name (e.g. 'Uocm:US-ASHBURN-AD-1')."
  type        = string
  default     = ""
}

variable "freeform_tags" {
  description = "Freeform tags applied to resources (cost allocation)."
  type        = map(string)
  default     = {}
}

# ----------------------------------------------------------------- compute --
variable "runtime" {
  description = "Compute shape: 'serverless' (Container Instances), 'vm', or 'none'."
  type        = string
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "vm", "none"], var.runtime)
    error_message = "runtime must be one of: serverless, vm, none."
  }
}

variable "image_uri" {
  description = "Container image URI (e.g. <region>.ocir.io/<ns>/speech-bridge:latest)."
  type        = string
  default     = ""
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "ocpus" {
  description = "OCPUs for the flexible shape."
  type        = number
  default     = 1
}

variable "memory_in_gbs" {
  description = "Memory (GB) for the flexible shape."
  type        = number
  default     = 4
}

variable "container_shape" {
  description = "Container Instance shape."
  type        = string
  default     = "CI.Standard.E4.Flex"
}

variable "vm_shape" {
  description = "Compute VM shape (vm runtime)."
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "vm_image_ocid" {
  description = "OS image OCID for the Compute VM (vm runtime)."
  type        = string
  default     = ""
}

variable "vm_ssh_public_key" {
  description = "SSH public key for the Compute VM (vm runtime)."
  type        = string
  default     = ""
}

variable "app_env" {
  description = "Non-secret environment variables for the app."
  type        = map(string)
  default     = {}
}

# ----------------------------------------------------------------- network --
variable "create_network" {
  description = "Create a VCN + public subnet. If false, supply existing_subnet_id."
  type        = bool
  default     = true
}

variable "existing_subnet_id" {
  description = "Existing subnet OCID when create_network = false."
  type        = string
  default     = ""
}

variable "vcn_cidr" {
  type    = string
  default = "10.44.0.0/16"
}

# ------------------------------------------------------------------ budget --
variable "enable_budget" {
  description = "Create the monthly budget + alert rules."
  type        = bool
  default     = true
}

variable "monthly_budget" {
  description = "Regular monthly budget (USD). Drives alerts."
  type        = number
  default     = 50
}

variable "alert_thresholds" {
  description = "Percentages of the regular budget that trigger alerts."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "alert_emails" {
  description = "Emails that receive budget alerts / kill-switch notifications."
  type        = list(string)
  default     = []
}

variable "enable_hard_cap" {
  description = "Create the grace alert rule + ONS topic for the kill switch."
  type        = bool
  default     = true
}

variable "hard_cap_amount" {
  description = "Grace budget that triggers the kill switch. Null => monthly_budget."
  type        = number
  default     = null
}
