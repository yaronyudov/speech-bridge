# Optional VCN + public subnet. Created only when create_network = true.

resource "oci_core_vcn" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name}-vcn"
  freeform_tags  = local.common_tags
}

resource "oci_core_internet_gateway" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this[0].id
  display_name   = "${var.name}-igw"
  enabled        = true
}

resource "oci_core_route_table" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this[0].id
  display_name   = "${var.name}-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.this[0].id
  }
}

resource "oci_core_security_list" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this[0].id
  display_name   = "${var.name}-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"

    tcp_options {
      min = var.container_port
      max = var.container_port
    }
  }
}

resource "oci_core_subnet" "this" {
  count             = var.create_network ? 1 : 0
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.this[0].id
  cidr_block        = cidrsubnet(var.vcn_cidr, 8, 0)
  display_name      = "${var.name}-subnet"
  route_table_id    = oci_core_route_table.this[0].id
  security_list_ids = [oci_core_security_list.this[0].id]
  freeform_tags     = local.common_tags
}
