# ---------------------------------------------------------------------------
# Two-tier budget:
#   * Regular budget (var.monthly_budget) -> alert notifications at
#     var.alert_thresholds (50/80/100 %) to var.alert_emails.
#   * Grace budget (local.hard_cap_amount, defaults to monthly_budget) ->
#     drives the kill switch in enforcement.tf when var.enable_hard_cap.
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "regular" {
  count        = var.enable_budget ? 1 : 0
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = length(var.alert_emails) > 0 ? var.alert_thresholds : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.alert_emails
    }
  }
}
