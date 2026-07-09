# Optional Secrets Manager entries. Names are prefixed with "<name>/" so they
# match SECRETS_PREFIX="<name>/" when the app runs with SECRETS_BACKEND=aws.

resource "aws_secretsmanager_secret" "this" {
  for_each = var.create_secrets ? var.secrets : {}
  name     = "${var.name}/${each.key}"
  tags     = local.common_tags
}

resource "aws_secretsmanager_secret_version" "this" {
  for_each      = var.create_secrets ? var.secrets : {}
  secret_id     = aws_secretsmanager_secret.this[each.key].id
  secret_string = each.value
}
