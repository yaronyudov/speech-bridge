#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build the speech-bridge image and push it to a cloud registry.
# Run from the repo root. Requires docker + the target cloud's CLI logged in.
#
#   ./infra/terraform/scripts/build_and_push.sh aws  <ecr-repo-url>
#   ./infra/terraform/scripts/build_and_push.sh gcp  <region-docker.pkg.dev/proj/repo>
#   ./infra/terraform/scripts/build_and_push.sh azure <acr-login-server>
#   ./infra/terraform/scripts/build_and_push.sh oci  <region.ocir.io/namespace>
#
# The registry URLs are printed as Terraform outputs (ecr_repository_url,
# artifact_registry_repo, acr_login_server, ...) after `terraform apply`.
# ---------------------------------------------------------------------------
set -euo pipefail

CLOUD="${1:-}"
REGISTRY="${2:-}"
IMAGE_NAME="${IMAGE_NAME:-speech-bridge}"
TAG="${TAG:-latest}"

if [[ -z "$CLOUD" || -z "$REGISTRY" ]]; then
  grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

case "$CLOUD" in
  aws)
    REGION="${AWS_REGION:-us-east-1}"
    aws ecr get-login-password --region "$REGION" \
      | docker login --username AWS --password-stdin "${REGISTRY%%/*}"
    IMAGE="${REGISTRY}:${TAG}"
    ;;
  gcp)
    gcloud auth configure-docker "${REGISTRY%%/*}" --quiet
    IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
    ;;
  azure)
    az acr login --name "${REGISTRY%%.*}"
    IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
    ;;
  oci)
    # Expects `docker login <region>.ocir.io` to have been run already.
    IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
    ;;
  *)
    echo "Unknown cloud '$CLOUD' (expected: aws|gcp|azure|oci)" >&2
    exit 1
    ;;
esac

echo "Building ${IMAGE} ..."
docker build -t "$IMAGE" .
echo "Pushing ${IMAGE} ..."
docker push "$IMAGE"
echo "Done. Set image_uri = \"${IMAGE}\" (or rely on create_registry)."
