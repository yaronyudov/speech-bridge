# ---------------------------------------------------------------------------
# Compute — Cloud Run v2 (serverless) or a GCE VM, selected by var.runtime.
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "this" {
  count    = local.deploy_serverless ? 1 : 0
  name     = var.name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = local.common_labels

  template {
    scaling {
      min_instance_count = var.min_instances # 0 => scale to zero
      max_instance_count = var.max_instances # architectural cost cap
    }

    max_instance_request_concurrency = var.max_concurrency

    containers {
      image = local.image_uri

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }

      dynamic "env" {
        for_each = var.app_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = local.deploy_serverless && var.allow_unauthenticated ? 1 : 0
  name     = google_cloud_run_v2_service.this[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# -------------------------------------------------------------------- GCE --
resource "google_compute_instance" "vm" {
  count        = local.deploy_vm ? 1 : 0
  name         = "${var.name}-vm"
  machine_type = var.vm_machine_type
  zone         = var.zone
  labels       = local.common_labels
  tags         = ["speech-bridge"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }

  network_interface {
    network = "default"
    access_config {} # ephemeral public IP
  }

  metadata = {
    # Container-Optimized OS runs the image via docker on boot.
    startup-script = <<-EOF
      #!/bin/bash
      docker run -d --restart always -p ${var.container_port}:8000 \
        ${join(" ", [for k, v in var.app_env : "-e ${k}='${v}'"])} \
        ${local.image_uri}
    EOF
  }
}

resource "google_compute_firewall" "vm" {
  count   = local.deploy_vm ? 1 : 0
  name    = "${var.name}-allow-app"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = [tostring(var.container_port)]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["speech-bridge"]
}
