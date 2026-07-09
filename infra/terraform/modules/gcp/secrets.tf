# Optional Secret Manager secrets. Secret ids match the app setting names, so
# run the app with SECRETS_BACKEND=gcp and SECRETS_PREFIX="projects/<project>".

resource "google_secret_manager_secret" "this" {
  for_each  = var.create_secrets ? var.secrets : {}
  secret_id = each.key
  labels    = local.common_labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "this" {
  for_each    = var.create_secrets ? var.secrets : {}
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = each.value
}
