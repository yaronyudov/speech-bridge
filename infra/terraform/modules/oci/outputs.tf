output "container_instance_id" {
  description = "Container Instance OCID (serverless runtime)."
  value       = local.deploy_serverless ? oci_container_instances_container_instance.this[0].id : null
}

output "vm_public_ip" {
  description = "Compute VM public IP (vm runtime)."
  value       = local.deploy_vm ? oci_core_instance.vm[0].public_ip : null
}

output "subnet_id" {
  description = "Subnet used by the compute resource."
  value       = local.subnet_id
}

output "killswitch_topic_id" {
  description = "ONS topic OCID for the grace-budget kill switch (wire a Function to it)."
  value       = var.enable_hard_cap ? oci_ons_notification_topic.killswitch[0].id : null
}
