terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0"
    }
  }

  # Optional remote state — uncomment to use an azurerm backend.
  # backend "azurerm" {
  #   resource_group_name  = "tfstate-rg"
  #   storage_account_name = "mytfstate"
  #   container_name       = "tfstate"
  #   key                  = "speech-bridge.tfstate"
  # }
}

# azurerm v4 requires a subscription: set ARM_SUBSCRIPTION_ID in the
# environment (or add subscription_id here) before plan/apply.
provider "azurerm" {
  features {}
}
