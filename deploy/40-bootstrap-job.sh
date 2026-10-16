#!/usr/bin/env bash
# Cloud Run Jobs that run the one-off bootstrap steps with the API image. Usage: 40-bootstrap-job.sh [data|index|warm|all]  (default: all)
source "$(dirname "$0")/lib.sh"
require_set DB_HOST
source "${DEPLOY_DIR}/api_env.sh"
STEP="${1:-all}"

deploy_job() {  # name, python args
  local name="panda-bootstrap-$1"; shift
  gcloud run jobs deploy "${name}" \
    --project "${PROJECT_ID}" --region "${REGION}" --image "${API_IMAGE}" \
    --service-account "${SERVICE_ACCOUNT}" \
    --network "${VPC_NETWORK}" --subnet "${VPC_SUBNET}" --vpc-egress private-ranges-only \
    --memory "${JOB_MEMORY:-16Gi}" --cpu 2 --max-retries 0 --task-timeout 3600s \
    --command python --args="$1" \
    --set-env-vars "${API_ENV}" \
    --set-secrets "PGPASSWORD=${DB_PASSWORD_SECRET}:latest"
  gcloud run jobs execute "${name}" --project "${PROJECT_ID}" --region "${REGION}" --wait
}

case "${STEP}" in
  data)  deploy_job data  "-m,app.bootstrap,data,--rows,${BOOTSTRAP_ROWS:-20000000}" ;;
  index) deploy_job index "-m,app.bootstrap,index" ;;
  warm)  deploy_job warm  "-m,app.bootstrap,warm" ;;
  diagnose) deploy_job diagnose "-m,app.bootstrap,diagnose,--llm" ;;
  all)   "$0" data && "$0" index && "$0" warm ;;
  *) echo "usage: $0 [data|index|warm|diagnose|all]" >&2; exit 1 ;;
esac
