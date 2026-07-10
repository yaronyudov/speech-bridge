# ---------------------------------------------------------------------------
# Two-tier budget.
#   * Regular budget -> alert rules at var.alert_thresholds (email recipients).
#   * Grace          -> a 100 %-of-grace alert rule + an ONS topic
#     (enforcement.tf) operators wire a stop Function to.
# NOTE: OCI budgets target a compartment and live in the tenancy's home
# region. Budget alert rules can only email; hard enforcement is via the ONS
# topic + a Function (see enforcement.tf + README).
# ---------------------------------------------------------------------------

resource "oci_budget_budget" "this" {
  count          = var.enable_budget ? 1 : 0
  compartment_id = var.compartment_ocid # tenancy OCID for a tenancy-wide budget
  amount         = var.monthly_budget
  reset_period   = "MONTHLY"
  target_type    = "COMPARTMENT"
  targets        = [var.compartment_ocid]
  display_name   = "${var.name}-monthly"
  freeform_tags  = local.common_tags
}

resource "oci_budget_alert_rule" "alerts" {
  for_each  = var.enable_budget && length(var.alert_emails) > 0 ? toset([for t in var.alert_thresholds : tostring(t)]) : []
  budget_id = oci_budget_budget.this[0].id
  threshold = tonumber(each.value)
  type      = "ACTUAL"

  threshold_type = "PERCENTAGE"
  recipients     = join(",", var.alert_emails)
  message        = "speech-bridge budget alert: ${each.value}% of the monthly budget reached."
}

resource "oci_budget_alert_rule" "hard_cap" {
  count     = var.enable_hard_cap && var.enable_budget ? 1 : 0
  budget_id = oci_budget_budget.this[0].id
  # Grace threshold expressed as a percentage of the regular budget.
  threshold      = local.hard_cap_amount / var.monthly_budget * 100
  type           = "ACTUAL"
  threshold_type = "PERCENTAGE"
  recipients     = join(",", var.alert_emails)
  message        = "speech-bridge KILL SWITCH: grace budget reached — stopping the workload."
}
