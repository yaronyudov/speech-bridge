output "service_url" {
  description = "Cloud Run service URL (serverless runtime)."
  value       = local.deploy_serverless ? google_cloud_run_v2_service.this[0].uri : null
}

output "vm_name" {
  description = "GCE instance name (vm runtime)."
  value       = local.deploy_vm ? google_compute_instance.vm[0].name : null
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository path (when create_registry = true)."
  value       = var.create_registry ? "${var.region}-docker.pkg.dev/${var.project}/${var.name}" : null
}

output "image_uri" {
  description = "Resolved image URI used by the compute resources."
  value       = local.image_uri
}

output "killswitch_topic" {
  description = "Pub/Sub topic the grace budget publishes to (deploy the function against it)."
  value       = var.enable_hard_cap ? google_pubsub_topic.killswitch[0].id : null
}

output "killswitch_mode" {
  description = "Configured kill-switch behaviour — pass as the MODE argument to scripts/deploy_gcp_killswitch.sh."
  value       = var.hard_cap_mode
}
