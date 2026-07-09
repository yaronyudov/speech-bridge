output "service_url" {
  description = "Public URL of the App Runner service (serverless runtime)."
  value       = local.deploy_serverless ? "https://${aws_apprunner_service.this[0].service_url}" : null
}

output "vm_public_ip" {
  description = "Public IP of the EC2 instance (vm runtime)."
  value       = local.deploy_vm ? aws_instance.vm[0].public_ip : null
}

output "ecr_repository_url" {
  description = "ECR repository URL to push images to (when create_registry = true)."
  value       = var.create_registry ? aws_ecr_repository.this[0].repository_url : null
}

output "image_uri" {
  description = "Resolved image URI used by the compute resources."
  value       = local.image_uri
}

output "killswitch_role_arn" {
  description = "Attach your app's AWS credentials to this role so the grace-tier kill switch can revoke paid-API access."
  value       = local.killswitch_iam ? aws_iam_role.killswitch_target[0].arn : null
}

output "secret_arns" {
  description = "ARNs of any Secrets Manager entries created by the module."
  value       = { for k, s in aws_secretsmanager_secret.this : k => s.arn }
}
