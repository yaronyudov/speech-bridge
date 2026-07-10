# Optional Secrets Manager entries. Names are prefixed with "<name>/" so they
# match SECRETS_PREFIX="<name>/" when the app runs with SECRETS_BACKEND=aws.
#
# var.secrets is sensitive, and Terraform forbids for_each over sensitive
# values. The KEYS are just setting names (OPENAI_API_KEY, ...), so iterate
# those with nonsensitive(); the VALUES stay sensitive via var.secrets[key].

locals {
  secret_names = var.create_secrets ? nonsensitive(toset(keys(var.secrets))) : toset([])
}

resource "aws_secretsmanager_secret" "this" {
  for_each = local.secret_names
  name     = "${var.name}/${each.key}"
  tags     = local.common_tags
}

resource "aws_secretsmanager_secret_version" "this" {
  for_each      = local.secret_names
  secret_id     = aws_secretsmanager_secret.this[each.key].id
  secret_string = var.secrets[each.key]
}
