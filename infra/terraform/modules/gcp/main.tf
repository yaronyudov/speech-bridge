# speech-bridge — GCP module composition root (shared locals only).

locals {
  common_labels = merge(
    { project = var.name, managed-by = "terraform" },
    var.labels,
  )

  hard_cap_amount = coalesce(var.hard_cap_amount, var.monthly_budget)

  deploy_serverless = var.runtime == "serverless"
  deploy_vm         = var.runtime == "vm"

  image_uri = var.create_registry ? "${var.region}-docker.pkg.dev/${var.project}/${var.name}/${var.name}:latest" : var.image_uri
}
