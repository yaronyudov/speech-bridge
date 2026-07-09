# Optional VPC. Created only when create_network = true (mainly for the VM
# runtime); otherwise the module uses existing_subnet_ids or the default VPC.

resource "aws_vpc" "this" {
  count                = var.create_network ? 1 : 0
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.common_tags, { Name = "${var.name}-vpc" })
}

resource "aws_internet_gateway" "this" {
  count  = var.create_network ? 1 : 0
  vpc_id = aws_vpc.this[0].id
  tags   = merge(local.common_tags, { Name = "${var.name}-igw" })
}

resource "aws_subnet" "public" {
  count                   = var.create_network ? 1 : 0
  vpc_id                  = aws_vpc.this[0].id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 0)
  map_public_ip_on_launch = true
  tags                    = merge(local.common_tags, { Name = "${var.name}-public" })
}

resource "aws_route_table" "public" {
  count  = var.create_network ? 1 : 0
  vpc_id = aws_vpc.this[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }

  tags = merge(local.common_tags, { Name = "${var.name}-public-rt" })
}

resource "aws_route_table_association" "public" {
  count          = var.create_network ? 1 : 0
  subnet_id      = aws_subnet.public[0].id
  route_table_id = aws_route_table.public[0].id
}

# Look up the VPC of a caller-supplied subnet (BYO-network path).
data "aws_subnet" "selected" {
  count = !var.create_network && length(var.existing_subnet_ids) > 0 ? 1 : 0
  id    = var.existing_subnet_ids[0]
}

locals {
  # Subnet ids the VM runtime should launch into.
  subnet_ids = var.create_network ? [aws_subnet.public[0].id] : var.existing_subnet_ids

  # VPC that the VM security group belongs to (null => account default VPC).
  vpc_id = var.create_network ? aws_vpc.this[0].id : (
    length(var.existing_subnet_ids) > 0 ? data.aws_subnet.selected[0].vpc_id : null
  )
}
