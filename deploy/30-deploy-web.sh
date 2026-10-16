#!/usr/bin/env bash
# Deploy the web UI (Next.js + BFF) to Cloud Run. GATEWAY_URL points at the API service.
source "$(dirname "$0")/lib.sh"
API_URL="$(gcloud run services describe "${API_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
gcloud run deploy "${WEB_SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --image "${WEB_IMAGE}" \
  --min-instances 0 --max-instances 2 --concurrency 40 --timeout 3600 \
  --cpu 1 --memory 512Mi --cpu-boost \
  --set-env-vars "GATEWAY_URL=${API_URL}" \
  --allow-unauthenticated
WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "WEB: ${WEB_URL}"
echo "Add ${WEB_URL#https://} to Firebase Auth > Settings > Authorized domains."
