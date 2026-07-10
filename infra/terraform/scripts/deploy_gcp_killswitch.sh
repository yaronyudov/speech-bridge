#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploy the GCP budget kill-switch Cloud Function.
#
# The Terraform GCP module wires the grace budget to a Pub/Sub topic
# (terraform output: killswitch_topic). This script deploys a Gen2 Cloud
# Function subscribed to that topic which, once actual spend reaches the
# grace budget, either:
#   scale_zero      -> sets the Cloud Run service's max instances to 0
#   disable_billing -> detaches the billing account from the project (nuclear)
#
# Usage:
#   ./deploy_gcp_killswitch.sh <PROJECT> <REGION> <RUN_SERVICE> <TOPIC_NAME> [scale_zero|disable_billing]
# Example:
#   ./deploy_gcp_killswitch.sh my-proj us-central1 speech-bridge speech-bridge-killswitch scale_zero
#
# Requires: gcloud CLI authenticated with permission to deploy functions.
# For disable_billing, grant the function's service account the
# "Billing Account Administrator" role on the billing account.
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT="${1:?project id required}"
REGION="${2:?region required}"
RUN_SERVICE="${3:?cloud run service name required}"
TOPIC="${4:?pub/sub topic name required}"
MODE="${5:-scale_zero}"

SRC_DIR="$(mktemp -d)"
trap 'rm -rf "$SRC_DIR"' EXIT

cat > "$SRC_DIR/main.py" <<'PY'
"""Budget kill switch: scale Cloud Run to zero / detach billing."""

import base64
import json
import logging
import os

import functions_framework

logging.basicConfig(level=logging.INFO)
MODE = os.environ.get("KILLSWITCH_MODE", "scale_zero")
PROJECT = os.environ["KILLSWITCH_PROJECT"]
REGION = os.environ.get("KILLSWITCH_REGION", "")
RUN_SERVICE = os.environ.get("KILLSWITCH_RUN_SERVICE", "")


@functions_framework.cloud_event
def on_budget_event(cloud_event):
    payload = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    cost = float(payload.get("costAmount", 0))
    budget = float(payload.get("budgetAmount", 0))
    logging.info("Budget event: cost=%s budget=%s mode=%s", cost, budget, MODE)
    if budget <= 0 or cost < budget:
        return  # only act at/over 100% of the grace budget

    if MODE == "disable_billing":
        from googleapiclient import discovery

        billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
        billing.projects().updateBillingInfo(
            name=f"projects/{PROJECT}", body={"billingAccountName": ""}
        ).execute()
        logging.warning("BILLING DISABLED for project %s", PROJECT)
    else:
        from google.cloud import run_v2

        client = run_v2.ServicesClient()
        name = f"projects/{PROJECT}/locations/{REGION}/services/{RUN_SERVICE}"
        service = client.get_service(name=name)
        service.template.scaling.max_instance_count = 0
        service.template.scaling.min_instance_count = 0
        client.update_service(service=service).result()
        logging.warning("SCALED %s TO ZERO (grace budget reached)", name)
PY

cat > "$SRC_DIR/requirements.txt" <<'REQ'
functions-framework>=3.5
google-cloud-run>=0.10
google-api-python-client>=2.120
REQ

gcloud functions deploy "${RUN_SERVICE}-killswitch" \
  --project "$PROJECT" \
  --region "$REGION" \
  --gen2 \
  --runtime python311 \
  --source "$SRC_DIR" \
  --entry-point on_budget_event \
  --trigger-topic "$TOPIC" \
  --set-env-vars "KILLSWITCH_MODE=${MODE},KILLSWITCH_PROJECT=${PROJECT},KILLSWITCH_REGION=${REGION},KILLSWITCH_RUN_SERVICE=${RUN_SERVICE}"

echo "Kill-switch function deployed (mode: ${MODE})."
echo "Grant its service account 'roles/run.admin' on the project" \
     "(and Billing Account Administrator for disable_billing mode)."
