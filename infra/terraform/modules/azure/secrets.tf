# Optional Key Vault + secrets. Secret names replace '_' with '-' (Key Vault
# naming); the app's SECRETS_BACKEND=azure resolver applies the same mapping.

data "azurerm_client_config" "current" {
  count = var.create_secrets ? 1 : 0
}

resource "azurerm_key_vault" "this" {
  count                     = var.create_secrets ? 1 : 0
  name                      = replace("${var.name}-kv", "_", "-")
  resource_group_name       = local.rg_name
  location                  = local.rg_location
  tenant_id                 = data.azurerm_client_config.current[0].tenant_id
  sku_name                  = "standard"
  enable_rbac_authorization = true
  tags                      = local.common_tags
}

resource "azurerm_key_vault_secret" "this" {
  for_each     = var.create_secrets ? var.secrets : {}
  name         = replace(each.key, "_", "-")
  value        = each.value
  key_vault_id = azurerm_key_vault.this[0].id
}
