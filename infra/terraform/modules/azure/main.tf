# speech-bridge — Azure module composition root.

resource "azurerm_resource_group" "this" {
  count    = var.create_resource_group ? 1 : 0
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

data "azurerm_resource_group" "existing" {
  count = var.create_resource_group ? 0 : 1
  name  = var.resource_group_name
}

locals {
  common_tags = merge(
    { project = var.name, managed-by = "terraform" },
    var.tags,
  )

  hard_cap_amount = coalesce(var.hard_cap_amount, var.monthly_budget)

  deploy_serverless = var.runtime == "serverless"
  deploy_vm         = var.runtime == "vm"

  rg_name     = var.create_resource_group ? azurerm_resource_group.this[0].name : data.azurerm_resource_group.existing[0].name
  rg_id       = var.create_resource_group ? azurerm_resource_group.this[0].id : data.azurerm_resource_group.existing[0].id
  rg_location = var.create_resource_group ? azurerm_resource_group.this[0].location : data.azurerm_resource_group.existing[0].location

  image_uri = var.create_registry ? "${azurerm_container_registry.this[0].login_server}/${var.name}:latest" : var.image_uri
}
