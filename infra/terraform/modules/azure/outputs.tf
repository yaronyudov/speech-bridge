output "service_fqdn" {
  description = "Container App public FQDN (serverless runtime)."
  value       = local.deploy_serverless ? azurerm_container_app.this[0].ingress[0].fqdn : null
}

output "vm_public_ip" {
  description = "VM public IP (vm runtime)."
  value       = local.deploy_vm ? azurerm_public_ip.vm[0].ip_address : null
}

output "acr_login_server" {
  description = "ACR login server (when create_registry = true)."
  value       = var.create_registry ? azurerm_container_registry.this[0].login_server : null
}

output "image_uri" {
  description = "Resolved image URI used by the compute resources."
  value       = local.image_uri
}

output "key_vault_uri" {
  description = "Key Vault URI to use as SECRETS_PREFIX (when create_secrets = true)."
  value       = var.create_secrets ? azurerm_key_vault.this[0].vault_uri : null
}
