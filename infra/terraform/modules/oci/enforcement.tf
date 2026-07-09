# ---------------------------------------------------------------------------
# Grace-tier kill switch (OCI budgets are advisory / email-only natively).
#
# This creates a Notifications (ONS) topic + email subscriptions for the
# operators. For automated enforcement, subscribe an OCI Function to this
# topic that stops the Container Instance / Compute VM, and trigger it from
# the grace budget alert via an Events rule (see the module README). The
# single fixed-size Container Instance is itself the architectural cost cap.
# ---------------------------------------------------------------------------

resource "oci_ons_notification_topic" "killswitch" {
  count          = var.enable_hard_cap ? 1 : 0
  compartment_id = var.compartment_ocid
  name           = "${var.name}-killswitch"
  description    = "speech-bridge grace-budget kill-switch notifications"
  freeform_tags  = local.common_tags
}

resource "oci_ons_subscription" "email" {
  for_each       = var.enable_hard_cap ? toset(var.alert_emails) : []
  compartment_id = var.compartment_ocid
  topic_id       = oci_ons_notification_topic.killswitch[0].id
  protocol       = "EMAIL"
  endpoint       = each.value
}
