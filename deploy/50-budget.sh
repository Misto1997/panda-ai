#!/usr/bin/env bash
# Budget with alerts at 50/90/100% publishing to Pub/Sub, then deploys the kill-switch that cuts public access at 100%.
source "$(dirname "$0")/lib.sh"
require_set BILLING_ACCOUNT_ID BUDGET_AMOUNT
TOPIC="${BUDGET_TOPIC:-panda-budget-alerts}"
gcloud pubsub topics describe "${TOPIC}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud pubsub topics create "${TOPIC}" --project "${PROJECT_ID}"

# The budget publisher (Cloud Billing) needs no extra grant for budget notifications on a topic in your project.
gcloud billing budgets create \
  --billing-account="${BILLING_ACCOUNT_ID}" \
  --display-name="panda-ai monthly budget" \
  --budget-amount="${BUDGET_AMOUNT}" \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
  --notifications-rule-pubsub-topic="projects/${PROJECT_ID}/topics/${TOPIC}" \
  --filter-projects="projects/${PROJECT_ID}"

"${DEPLOY_DIR}/killswitch/deploy.sh"
echo "Budget created. Re-running this script creates a second budget: delete the old one in Billing > Budgets first."
