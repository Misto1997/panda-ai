#!/usr/bin/env bash
# Deploys the budget kill-switch (Pub/Sub-triggered function) and grants it rights on the two services only.
source "$(dirname "$0")/../lib.sh"
TOPIC="${BUDGET_TOPIC:-panda-budget-alerts}"
KS_SA_NAME="panda-killswitch"
KS_SA="${KS_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "${KS_SA}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${KS_SA_NAME}" --display-name="PANDA budget kill-switch"
for svc in "${API_SERVICE}" "${WEB_SERVICE}"; do
  # run.admin on the service is needed to change its IAM policy (roles/run.invoker alone cannot).
  gcloud run services add-iam-policy-binding "${svc}" --project "${PROJECT_ID}" --region "${REGION}" \
    --member="serviceAccount:${KS_SA}" --role=roles/run.admin --quiet >/dev/null
done
# Gen2 functions are Cloud Run services fed by an Eventarc Pub/Sub trigger. The trigger SA delivers events, so it needs
# eventarc.eventReceiver (project) and run.invoker on the function's Cloud Run service. Using the kill-switch SA for both runtime and
# trigger keeps one identity. Build-side roles are granted in 00-setup.sh.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${KS_SA}" \
  --role=roles/eventarc.eventReceiver --condition=None --quiet >/dev/null
gcloud functions deploy panda-killswitch \
  --gen2 --project "${PROJECT_ID}" --region "${REGION}" \
  --runtime python312 --source "${DEPLOY_DIR}/killswitch" --entry-point on_budget_alert \
  --trigger-topic "${TOPIC}" --service-account "${KS_SA}" --trigger-service-account "${KS_SA}" \
  --memory 256Mi --max-instances 1 \
  --set-env-vars "^##^KILL_SERVICES=${API_SERVICE},${WEB_SERVICE}##KILL_PROJECT=${PROJECT_ID}##KILL_REGION=${REGION}"
# run.invoker for the trigger SA on the function's underlying Cloud Run service (gcloud usually adds it; explicit and idempotent here).
# UNVERIFIED: assumes the Cloud Run service name equals the function name (true for gen2 as of last check).
gcloud run services add-iam-policy-binding panda-killswitch --project "${PROJECT_ID}" --region "${REGION}" \
  --member="serviceAccount:${KS_SA}" --role=roles/run.invoker --quiet >/dev/null
