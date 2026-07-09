terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.20"
    }
  }

  # Optional remote state — uncomment to use a GCS backend.
  # backend "gcs" {
  #   bucket = "my-tfstate-bucket"
  #   prefix = "speech-bridge/gcp"
  # }
}

provider "google" {
  project = var.project
  region  = var.region
}
