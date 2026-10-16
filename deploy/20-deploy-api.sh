#!/usr/bin/env bash
# Deploy the API to Cloud Run with Direct VPC egress (to reach the AlloyDB private IP). Public invoker; Firebase auth is enforced in the app.
source "$(dirname "$0")/lib.sh"
require_set DB_HOST DATABASE_URL FIREBASE_PROJECT_ID
source "${DEPLOY_DIR}/api_env.sh"
gcloud run deploy "${API_SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --image "${API_IMAGE}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --network "${VPC_NETWORK}" --subnet "${VPC_SUBNET}" --vpc-egress private-ranges-only \
  --min-instances 0 --max-instances 2 --concurrency 20 --timeout 3600 \
  --cpu 1 --memory 1Gi --cpu-boost \
  --set-env-vars "${API_ENV}" \
  --set-secrets "PGPASSWORD=${DB_PASSWORD_SECRET}:latest" \
  --allow-unauthenticated
URL="$(gcloud run services describe "${API_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "API: ${URL}"
