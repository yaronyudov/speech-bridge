# ---------------------------------------------------------------------------
# Compute — OCI Container Instances (serverless) or a Compute VM.
# A Container Instance is a single fixed-size unit (no autoscaling), so its
# shape (ocpus/memory) is itself the architectural cost cap.
# ---------------------------------------------------------------------------

resource "oci_container_instances_container_instance" "this" {
  count               = local.deploy_serverless ? 1 : 0
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = var.name
  shape               = var.container_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_in_gbs
  }

  containers {
    display_name = var.name
    image_url    = var.image_uri

    environment_variables = var.app_env
  }

  vnics {
    subnet_id             = local.subnet_id
    is_public_ip_assigned = true
  }
}

# -------------------------------------------------------------------- VM ---
resource "oci_core_instance" "vm" {
  count               = local.deploy_vm ? 1 : 0
  compartment_id      = var.compartment_ocid
  availability_domain = var.availability_domain
  display_name        = "${var.name}-vm"
  shape               = var.vm_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_in_gbs
  }

  create_vnic_details {
    subnet_id        = local.subnet_id
    assign_public_ip = true
  }

  source_details {
    source_type = "image"
    source_id   = var.vm_image_ocid
  }

  metadata = {
    ssh_authorized_keys = var.vm_ssh_public_key
    user_data = base64encode(<<-EOF
      #!/bin/bash
      set -euo pipefail
      curl -fsSL https://get.docker.com | sh
      systemctl enable --now docker
      docker run -d --restart always -p ${var.container_port}:8000 \
        ${join(" ", [for k, v in var.app_env : "-e ${k}='${v}'"])} \
        ${var.image_uri}
    EOF
    )
  }
}
