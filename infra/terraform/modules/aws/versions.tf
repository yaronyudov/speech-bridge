terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40"
    }
  }

  # Optional remote state — uncomment and fill in to use an S3 backend.
  # backend "s3" {
  #   bucket         = "my-tfstate-bucket"
  #   key            = "speech-bridge/aws.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "my-tfstate-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
}
