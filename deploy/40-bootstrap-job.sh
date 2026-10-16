#!/usr/bin/env bash
# Cloud Run Jobs that run the one-off bootstrap steps with the API image. Usage: 40-bootstrap-job.sh [data|index|warm|accuracy|all]  (default: all; accuracy is never part of all)
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
  local status=0
  gcloud run jobs execute "${name}" --project "${PROJECT_ID}" --region "${REGION}" --wait || status=$?
  show_logs "${name}"
  return "${status}"
}

show_logs() {  # print what the latest execution of the job wrote (Cloud Run Jobs only log to Cloud Logging)
  local name="$1" exec
  exec="$(gcloud run jobs executions list --job "${name}" --project "${PROJECT_ID}" --region "${REGION}" --limit 1 --format='value(name)' 2>/dev/null || true)"
  [[ -n "${exec}" ]] || { echo "(could not find the execution; see Cloud Run > Jobs > ${name} > Logs)"; return 0; }
  echo "---- logs of ${exec} ----"
  sleep 8  # log ingestion lag
  gcloud logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${name}\" AND labels.\"run.googleapis.com/execution_name\"=\"${exec}\"" \
    --project "${PROJECT_ID}" --order asc --limit 200 --freshness 1h --format='value(textPayload)' | grep -v '^$' || true
  echo "---- end of logs (full history: Cloud Run > Jobs > ${name} > Logs) ----"
}

case "${STEP}" in
  data)  deploy_job data  "-m,app.bootstrap,data,--rows,${BOOTSTRAP_ROWS:-20000000}" ;;
  index) deploy_job index "-m,app.bootstrap,index" ;;
  warm)  deploy_job warm  "-m,app.bootstrap,warm" ;;
  diagnose) deploy_job diagnose "-m,app.bootstrap,diagnose,--llm" ;;
  accuracy) deploy_job accuracy "-m,app.bootstrap,accuracy" ;;
  all)   "$0" data && "$0" index && "$0" warm ;;
  *) echo "usage: $0 [data|index|warm|diagnose|accuracy|all]" >&2; exit 1 ;;
esac
