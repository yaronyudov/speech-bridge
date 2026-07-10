# ---------------------------------------------------------------------------
# Grace-tier kill switch.
#
# The grace budget (budget.tf) publishes to this Pub/Sub topic. A Cloud
# Function consumes it and, depending on var.hard_cap_mode:
#   * scale_zero      -> sets the Cloud Run service max instances to 0
#     (stops serving new requests; safest — reversible).
#   * disable_billing -> detaches the billing account from the project
#     (nuclear; stops ALL project spend). Requires the function's service
#     account to have Billing Account Administrator.
#
# Terraform provisions the topic here. Deploy the ready-made function with:
#   infra/terraform/scripts/deploy_gcp_killswitch.sh
# (kept out of Terraform so the base plan needs no function source bucket).
# The var.max_instances cap on Cloud Run remains the always-on guard.
# ---------------------------------------------------------------------------

resource "google_pubsub_topic" "killswitch" {
  count  = var.enable_hard_cap ? 1 : 0
  name   = "${var.name}-killswitch"
  labels = local.common_labels
}

# The Google-managed billing-budget service account must be allowed to
# publish, or grace-budget notifications never reach the topic.
resource "google_pubsub_topic_iam_member" "budget_publisher" {
  count  = var.enable_hard_cap ? 1 : 0
  topic  = google_pubsub_topic.killswitch[0].id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:billing-budget-alert@system.gserviceaccount.com"
}
