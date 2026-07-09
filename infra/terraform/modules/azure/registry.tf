# Optional Azure Container Registry.

resource "azurerm_container_registry" "this" {
  count               = var.create_registry ? 1 : 0
  name                = replace("${var.name}acr", "-", "")
  resource_group_name = local.rg_name
  location            = local.rg_location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.common_tags
}
