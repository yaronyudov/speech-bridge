# ---------------------------------------------------------------------------
# speech-bridge — AWS module composition root.
# Sub-resources live in network.tf / registry.tf / secrets.tf / compute.tf /
# budget.tf / enforcement.tf. This file only holds shared locals.
# ---------------------------------------------------------------------------

locals {
  common_tags = merge(
    {
      "project"    = var.name
      "managed-by" = "terraform"
    },
    var.tags,
  )

  # Grace/kill-switch amount defaults to the regular budget when unset.
  hard_cap_amount = coalesce(var.hard_cap_amount, var.monthly_budget)

  deploy_serverless = var.runtime == "serverless"
  deploy_vm         = var.runtime == "vm"

  # Prefer a created ECR repo URL, else the caller-provided image URI.
  image_uri = var.create_registry ? "${aws_ecr_repository.this[0].repository_url}:latest" : var.image_uri
}
