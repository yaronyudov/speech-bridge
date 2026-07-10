# Optional Artifact Registry Docker repository.

resource "google_artifact_registry_repository" "this" {
  count         = var.create_registry ? 1 : 0
  location      = var.region
  repository_id = var.name
  format        = "DOCKER"
  description   = "speech-bridge container images"
  labels        = local.common_labels
}
