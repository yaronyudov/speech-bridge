# ---------------------------------------------------------------------------
# Two-tier billing budget.
#   * Regular budget -> email alerts at var.alert_thresholds.
#   * Grace budget   -> publishes to a Pub/Sub topic (enforcement.tf) that a
#     kill-switch function consumes when var.enable_hard_cap = true.
# Requires var.billing_account.
# ---------------------------------------------------------------------------

resource "google_monitoring_notification_channel" "email" {
  for_each     = var.enable_budget ? toset(var.alert_emails) : []
  display_name = "speech-bridge budget alert (${each.value})"
  type         = "email"

  labels = {
    email_address = each.value
  }
}

resource "google_billing_budget" "regular" {
  count           = var.enable_budget && var.billing_account != "" ? 1 : 0
  billing_account = var.billing_account
  display_name    = "${var.name}-monthly"

  budget_filter {
    projects = ["projects/${var.project}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget)
    }
  }

  dynamic "threshold_rules" {
    for_each = var.alert_thresholds
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [
      for c in google_monitoring_notification_channel.email : c.id
    ]
    disable_default_iam_recipients = true
  }
}

resource "google_billing_budget" "hard_cap" {
  count           = var.enable_hard_cap && var.billing_account != "" ? 1 : 0
  billing_account = var.billing_account
  display_name    = "${var.name}-hard-cap"

  budget_filter {
    projects = ["projects/${var.project}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(local.hard_cap_amount)
    }
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  # Fire the kill-switch topic; the function acts when spend >= grace budget.
  all_updates_rule {
    pubsub_topic = google_pubsub_topic.killswitch[0].id
  }
}
