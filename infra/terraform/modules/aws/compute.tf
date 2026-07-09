# ---------------------------------------------------------------------------
# Compute — selected by var.runtime:
#   serverless -> AWS App Runner (managed, request-based autoscaling)
#   vm         -> single EC2 instance running the container via Docker
#   none       -> nothing (budgets/secrets only)
# ---------------------------------------------------------------------------

# ------------------------------------------------------------- App Runner --
data "aws_iam_policy_document" "apprunner_assume" {
  count = local.deploy_serverless ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_ecr" {
  count              = local.deploy_serverless ? 1 : 0
  name               = "${var.name}-apprunner-ecr"
  assume_role_policy = data.aws_iam_policy_document.apprunner_assume[0].json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr" {
  count      = local.deploy_serverless ? 1 : 0
  role       = aws_iam_role.apprunner_ecr[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_apprunner_auto_scaling_configuration_version" "this" {
  count                           = local.deploy_serverless ? 1 : 0
  auto_scaling_configuration_name = substr(replace(var.name, "/[^a-zA-Z0-9-]/", "-"), 0, 32)
  max_concurrency                 = var.max_concurrency
  min_size                        = max(var.min_instances, 1) # App Runner keeps >= 1 provisioned
  max_size                        = var.max_instances         # architectural cost cap
  tags                            = local.common_tags
}

resource "aws_apprunner_service" "this" {
  count        = local.deploy_serverless ? 1 : 0
  service_name = var.name

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.this[0].arn

  source_configuration {
    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr[0].arn
    }

    image_repository {
      image_identifier      = local.image_uri
      image_repository_type = "ECR"

      image_configuration {
        port                          = tostring(var.container_port)
        runtime_environment_variables = merge(var.app_env, { PORT = tostring(var.container_port) })
      }
    }
  }

  instance_configuration {
    cpu    = var.cpu
    memory = var.memory
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/health"
  }

  tags = local.common_tags
}

# -------------------------------------------------------------------- EC2 --
data "aws_ami" "al2023" {
  count       = local.deploy_vm ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_security_group" "vm" {
  count       = local.deploy_vm ? 1 : 0
  name        = "${var.name}-vm"
  description = "speech-bridge VM ingress"
  vpc_id      = local.vpc_id

  ingress {
    description = "app port"
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_iam_role" "vm" {
  count = local.deploy_vm ? 1 : 0
  name  = "${var.name}-vm"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "vm_ssm" {
  count      = local.deploy_vm ? 1 : 0
  role       = aws_iam_role.vm[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "vm_ecr" {
  count      = local.deploy_vm ? 1 : 0
  role       = aws_iam_role.vm[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "vm" {
  count = local.deploy_vm ? 1 : 0
  name  = "${var.name}-vm"
  role  = aws_iam_role.vm[0].name
}

resource "aws_instance" "vm" {
  count                       = local.deploy_vm ? 1 : 0
  ami                         = data.aws_ami.al2023[0].id
  instance_type               = var.vm_instance_type
  subnet_id                   = length(local.subnet_ids) > 0 ? local.subnet_ids[0] : null
  vpc_security_group_ids      = [aws_security_group.vm[0].id]
  iam_instance_profile        = aws_iam_instance_profile.vm[0].name
  associate_public_ip_address = true

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    dnf install -y docker
    systemctl enable --now docker
    ${join("\n", [for k, v in var.app_env : "export ${k}='${v}'"])}
    docker run -d --restart always -p ${var.container_port}:8000 \
      ${join(" ", [for k, v in var.app_env : "-e ${k}='${v}'"])} \
      ${local.image_uri}
  EOF

  tags = merge(local.common_tags, { Name = "${var.name}-vm" })
}
