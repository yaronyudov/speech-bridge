# ---------------------------------------------------------------------------
# Compute — Azure Container Apps (serverless) or a Linux VM.
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "this" {
  count               = local.deploy_serverless ? 1 : 0
  name                = "${var.name}-env"
  resource_group_name = local.rg_name
  location            = local.rg_location
  tags                = local.common_tags
}

resource "azurerm_container_app" "this" {
  count                        = local.deploy_serverless ? 1 : 0
  name                         = var.name
  resource_group_name          = local.rg_name
  container_app_environment_id = azurerm_container_app_environment.this[0].id
  revision_mode                = "Single"
  tags                         = local.common_tags

  template {
    min_replicas = var.min_instances # 0 => scale to zero
    max_replicas = var.max_instances # architectural cost cap

    container {
      name   = var.name
      image  = local.image_uri
      cpu    = var.cpu
      memory = var.memory

      dynamic "env" {
        for_each = var.app_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = var.container_port

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# -------------------------------------------------------------------- VM ---
resource "azurerm_virtual_network" "vm" {
  count               = local.deploy_vm ? 1 : 0
  name                = "${var.name}-vnet"
  resource_group_name = local.rg_name
  location            = local.rg_location
  address_space       = ["10.42.0.0/16"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "vm" {
  count                = local.deploy_vm ? 1 : 0
  name                 = "${var.name}-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vm[0].name
  address_prefixes     = ["10.42.1.0/24"]
}

resource "azurerm_public_ip" "vm" {
  count               = local.deploy_vm ? 1 : 0
  name                = "${var.name}-pip"
  resource_group_name = local.rg_name
  location            = local.rg_location
  allocation_method   = "Static"
  tags                = local.common_tags
}

resource "azurerm_network_security_group" "vm" {
  count               = local.deploy_vm ? 1 : 0
  name                = "${var.name}-nsg"
  resource_group_name = local.rg_name
  location            = local.rg_location
  tags                = local.common_tags

  security_rule {
    name                       = "app"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.container_port)
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "vm" {
  count               = local.deploy_vm ? 1 : 0
  name                = "${var.name}-nic"
  resource_group_name = local.rg_name
  location            = local.rg_location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vm[0].id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vm[0].id
  }
}

resource "azurerm_network_interface_security_group_association" "vm" {
  count                     = local.deploy_vm ? 1 : 0
  network_interface_id      = azurerm_network_interface.vm[0].id
  network_security_group_id = azurerm_network_security_group.vm[0].id
}

resource "azurerm_linux_virtual_machine" "vm" {
  count                 = local.deploy_vm ? 1 : 0
  name                  = "${var.name}-vm"
  resource_group_name   = local.rg_name
  location              = local.rg_location
  size                  = var.vm_size
  admin_username        = var.vm_admin_username
  network_interface_ids = [azurerm_network_interface.vm[0].id]
  tags                  = local.common_tags

  admin_ssh_key {
    username   = var.vm_admin_username
    public_key = var.vm_ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    set -euo pipefail
    curl -fsSL https://get.docker.com | sh
    docker run -d --restart always -p ${var.container_port}:8000 \
      ${join(" ", [for k, v in var.app_env : "-e ${k}='${v}'"])} \
      ${local.image_uri}
  EOF
  )
}
