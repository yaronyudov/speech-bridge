terraform {
  required_version = ">= 1.5"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.30"
    }
  }

  # Optional remote state — uncomment to use an OCI Object Storage backend
  # (S3-compatible). See the OCI docs for generating an access key.
  # backend "s3" {
  #   bucket                      = "my-tfstate"
  #   key                         = "speech-bridge/oci.tfstate"
  #   region                      = "us-ashburn-1"
  #   endpoints                   = { s3 = "https://<namespace>.compat.objectstorage.us-ashburn-1.oraclecloud.com" }
  #   skip_region_validation      = true
  #   skip_credentials_validation = true
  #   skip_requesting_account_id  = true
  #   skip_s3_checksum            = true
  #   use_path_style              = true
  # }
}

provider "oci" {
  region = var.region
}
