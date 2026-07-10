# ---------------------------------------------------------------------------
# Two-tier consumption budget (resource-group scoped).
#   * Regular budget -> "Actual" alerts at var.alert_thresholds to emails.
#   * Grace budget   -> a "Forecasted"+"Actual" alert at 100 % of the grace
#     amount wired to the kill-switch action group (enforcement.tf).
# Azure has no native hard-stop; the action group's webhook drives a runbook /
# Function that scales the Container App to zero (see enforcement.tf + README).
# ---------------------------------------------------------------------------

# NOTE: azurerm requires at least one notification block on a budget, so the
# regular (alerts-only) budget is skipped when no alert emails are configured.
resource "azurerm_consumption_budget_resource_group" "regular" {
  count             = var.enable_budget && length(var.alert_emails) > 0 ? 1 : 0
  name              = "${var.name}-monthly"
  resource_group_id = local.rg_id
  amount            = var.monthly_budget
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
    end_date   = var.budget_end_date
  }

  dynamic "notification" {
    for_each = length(var.alert_emails) > 0 ? var.alert_thresholds : []
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
    }
  }
}

resource "azurerm_consumption_budget_resource_group" "hard_cap" {
  count             = var.enable_hard_cap ? 1 : 0
  name              = "${var.name}-hard-cap"
  resource_group_id = local.rg_id
  amount            = local.hard_cap_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
    end_date   = var.budget_end_date
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = var.alert_emails
    contact_groups = [azurerm_monitor_action_group.killswitch[0].id]
  }
}
