# speech-bridge — OCI module composition root (shared locals only).

locals {
  common_tags = merge(
    { project = var.name, managed-by = "terraform" },
    var.freeform_tags,
  )

  hard_cap_amount = coalesce(var.hard_cap_amount, var.monthly_budget)

  deploy_serverless = var.runtime == "serverless"
  deploy_vm         = var.runtime == "vm"

  subnet_id = var.create_network ? oci_core_subnet.this[0].id : var.existing_subnet_id
}
