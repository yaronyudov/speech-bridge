# Optional ECR repository. When create_registry = false, pass image_uri.

resource "aws_ecr_repository" "this" {
  count                = var.create_registry ? 1 : 0
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# Keep only the 10 most recent images to bound storage cost.
resource "aws_ecr_lifecycle_policy" "this" {
  count      = var.create_registry ? 1 : 0
  repository = aws_ecr_repository.this[0].name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire all but the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
