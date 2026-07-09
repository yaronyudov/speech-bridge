# ---------------------------------------------------------------------------
# Grace-tier kill switch (Azure has no native budget hard-stop).
#
# The grace budget triggers this action group, which:
#   * emails the operators, and
#   * (optional) calls var.killswitch_webhook_uri — point this at an Azure
#     Automation runbook or Function that scales the Container App to 0
#     replicas / deallocates the VM. A sample runbook is described in the
#     module README.
#
# The var.max_instances replica cap remains the always-on architectural guard.
# ---------------------------------------------------------------------------

resource "azurerm_monitor_action_group" "killswitch" {
  count               = var.enable_hard_cap ? 1 : 0
  name                = "${var.name}-killswitch"
  resource_group_name = local.rg_name
  short_name          = substr(replace(var.name, "-", ""), 0, 12)
  tags                = local.common_tags

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name          = "email-${email_receiver.key}"
      email_address = email_receiver.value
    }
  }

  dynamic "webhook_receiver" {
    for_each = var.killswitch_webhook_uri != "" ? [var.killswitch_webhook_uri] : []
    content {
      name        = "killswitch-webhook"
      service_uri = webhook_receiver.value
    }
  }
}
