# Optional Secret Manager secrets. Secret ids match the app setting names, so
# run the app with SECRETS_BACKEND=gcp and SECRETS_PREFIX="projects/<project>".
#
# var.secrets is sensitive; for_each over sensitive values is forbidden, so
# iterate the (non-sensitive) key names and look up values per key.

locals {
  secret_names = var.create_secrets ? nonsensitive(toset(keys(var.secrets))) : toset([])
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secret_names
  secret_id = each.key
  labels    = local.common_labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "this" {
  for_each    = local.secret_names
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = var.secrets[each.key]
}
