# ---------------------------------------------------------------------------
# Grace-tier kill switch (native AWS Budget Actions — no Lambda required).
#
#   * VM runtime  -> RUN_SSM_DOCUMENTS "STOP_EC2_INSTANCES": a real hard stop
#     of the instance when the grace budget is reached.
#   * otherwise   -> APPLY_IAM_POLICY attaches a deny policy to a managed role
#     (killswitch_target). Point your app's AWS credentials at that role and
#     its access to the paid STT/TTS APIs is revoked at the grace threshold.
#     (App Runner base provisioning keeps billing until paused — see README;
#     var.max_instances remains the always-on architectural cap.)
#
# Everything here is created only when var.enable_hard_cap = true.
# ---------------------------------------------------------------------------

locals {
  killswitch_enabled = var.enable_hard_cap
  killswitch_iam     = var.enable_hard_cap && !local.deploy_vm
}

# Grace budget whose breach triggers the action below.
resource "aws_budgets_budget" "hard_cap" {
  count        = local.killswitch_enabled ? 1 : 0
  name         = "${var.name}-hard-cap"
  budget_type  = "COST"
  limit_amount = tostring(local.hard_cap_amount)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = length(var.alert_emails) > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.alert_emails
    }
  }
}

# Role AWS Budgets assumes to execute the action.
data "aws_iam_policy_document" "budgets_assume" {
  count = local.killswitch_enabled ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "budgets_exec" {
  count              = local.killswitch_enabled ? 1 : 0
  name               = "${var.name}-budgets-exec"
  assume_role_policy = data.aws_iam_policy_document.budgets_assume[0].json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "budgets_exec" {
  count = local.killswitch_enabled ? 1 : 0
  name  = "${var.name}-budgets-exec"
  role  = aws_iam_role.budgets_exec[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SsmStop"
        Effect = "Allow"
        Action = [
          "ssm:StartAutomationExecution",
          "ssm:GetAutomationExecution",
          "ec2:StopInstances",
          "ec2:DescribeInstances",
          "iam:PassRole",
        ]
        Resource = "*"
      },
      {
        Sid    = "IamAttach"
        Effect = "Allow"
        Action = [
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
        ]
        Resource = "*"
      },
    ]
  })
}

# Deny policy + target role (non-VM runtimes).
resource "aws_iam_policy" "deny" {
  count       = local.killswitch_iam ? 1 : 0
  name        = "${var.name}-killswitch-deny"
  description = "Revokes access to paid speech APIs when the grace budget is hit."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Deny"
      Action = [
        "transcribe:*",
        "polly:*",
        "bedrock:*",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role" "killswitch_target" {
  count = local.killswitch_iam ? 1 : 0
  name  = "${var.name}-app"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
    }]
  })
  tags = local.common_tags
}

resource "aws_budgets_budget_action" "killswitch" {
  count              = local.killswitch_enabled ? 1 : 0
  budget_name        = aws_budgets_budget.hard_cap[0].name
  action_type        = local.deploy_vm ? "RUN_SSM_DOCUMENTS" : "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budgets_exec[0].arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    dynamic "iam_action_definition" {
      for_each = local.killswitch_iam ? [1] : []
      content {
        policy_arn = aws_iam_policy.deny[0].arn
        roles      = [aws_iam_role.killswitch_target[0].name]
      }
    }

    dynamic "ssm_action_definition" {
      for_each = local.deploy_vm ? [1] : []
      content {
        action_sub_type = "STOP_EC2_INSTANCES"
        region          = var.region
        instance_ids    = [aws_instance.vm[0].id]
      }
    }
  }

  subscriber {
    address           = length(var.alert_emails) > 0 ? var.alert_emails[0] : "ops@example.com"
    subscription_type = "EMAIL"
  }
}
