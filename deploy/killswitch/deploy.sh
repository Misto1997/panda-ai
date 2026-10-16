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
gcloud functions deploy panda-killswitch \
  --gen2 --project "${PROJECT_ID}" --region "${REGION}" \
  --runtime python312 --source "${DEPLOY_DIR}/killswitch" --entry-point on_budget_alert \
  --trigger-topic "${TOPIC}" --service-account "${KS_SA}" \
  --memory 256Mi --max-instances 1 \
  --set-env-vars "^##^KILL_SERVICES=${API_SERVICE},${WEB_SERVICE}##KILL_PROJECT=${PROJECT_ID}##KILL_REGION=${REGION}"
