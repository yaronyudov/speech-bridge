# Optional Key Vault + secrets. Secret names replace '_' with '-' (Key Vault
# naming); the app's SECRETS_BACKEND=azure resolver applies the same mapping.

data "azurerm_client_config" "current" {
  count = var.create_secrets ? 1 : 0
}

# var.secrets is sensitive; for_each over sensitive values is forbidden, so
# iterate the (non-sensitive) key names and look up values per key.
locals {
  secret_names = var.create_secrets ? nonsensitive(toset(keys(var.secrets))) : toset([])
}

resource "azurerm_key_vault" "this" {
  count                      = var.create_secrets ? 1 : 0
  name                       = replace("${var.name}-kv", "_", "-")
  resource_group_name        = local.rg_name
  location                   = local.rg_location
  tenant_id                  = data.azurerm_client_config.current[0].tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  tags                       = local.common_tags
}

resource "azurerm_key_vault_secret" "this" {
  for_each     = local.secret_names
  name         = replace(each.key, "_", "-")
  value        = var.secrets[each.key]
  key_vault_id = azurerm_key_vault.this[0].id
}
