#!/usr/bin/env bash
# Nightly roll-forward of the synthetic dataset so "yesterday" is really yesterday. A Cloud Scheduler job triggers a Cloud Run Job that regenerates
# the synthetic data to end yesterday (UTC), reloads BigQuery and clears the cache. It stops by itself after N days and can be paused/deleted any time.
#
#   deploy/45-nightly-refresh.sh create [DAYS]   create/update the job and the schedule (default 30 days; the job no-ops after that)
#   deploy/45-nightly-refresh.sh run             run it once now
#   deploy/45-nightly-refresh.sh pause|resume    pause or resume the schedule
#   deploy/45-nightly-refresh.sh extend DAYS     move the stop date to today + DAYS
#   deploy/45-nightly-refresh.sh status          show the schedule, the stop date and recent executions
#   deploy/45-nightly-refresh.sh delete          remove the schedule (and the job): the data simply stays at its last refresh
# Flags are UNVERIFIED against current gcloud docs: check `gcloud scheduler jobs create http --help` if one errors.
source "$(dirname "$0")/lib.sh"
require_set DB_HOST
source "${DEPLOY_DIR}/api_env.sh"
JOB="panda-bootstrap-refresh"
SCHEDULER_JOB="panda-nightly-refresh"
SCHEDULE="${REFRESH_CRON:-30 0 * * *}"   # 00:30 UTC = 06:00 IST: right after midnight UTC, so the data always ends on the true "yesterday"
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run"

stop_date() { date -u -v+"$1"d +%F 2>/dev/null || date -u -d "+$1 days" +%F; }   # macOS then GNU date

deploy_job() {  # $1 = stop date
  gcloud run jobs deploy "${JOB}" --project "${PROJECT_ID}" --region "${REGION}" --image "${API_IMAGE}" \
    --service-account "${SERVICE_ACCOUNT}" \
    --network "${VPC_NETWORK}" --subnet "${VPC_SUBNET}" --vpc-egress private-ranges-only \
    --memory "${JOB_MEMORY:-16Gi}" --cpu 2 --max-retries 1 --task-timeout 3600s \
    --command python --args="-m,app.bootstrap,refresh,--rows,${BOOTSTRAP_ROWS:-20000000},--until,$1" \
    --set-env-vars "${API_ENV}" --set-secrets "PGPASSWORD=${DB_PASSWORD_SECRET}:latest"
}

case "${1:-}" in
  create)
    UNTIL="$(stop_date "${2:-30}")"
    deploy_job "${UNTIL}"
    gcloud run jobs add-iam-policy-binding "${JOB}" --project "${PROJECT_ID}" --region "${REGION}" \
      --member "serviceAccount:${SERVICE_ACCOUNT}" --role roles/run.invoker >/dev/null
    COMMON=(--project "${PROJECT_ID}" --location "${REGION}" --schedule "${SCHEDULE}" --time-zone "Etc/UTC" --uri "${RUN_URI}" --http-method POST
            --oauth-service-account-email "${SERVICE_ACCOUNT}" --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform")
    gcloud scheduler jobs create http "${SCHEDULER_JOB}" "${COMMON[@]}" 2>/dev/null || gcloud scheduler jobs update http "${SCHEDULER_JOB}" "${COMMON[@]}"
    echo "Nightly refresh scheduled (${SCHEDULE} UTC) and will stop by itself after ${UNTIL}."
    echo "Stop any time: deploy/45-nightly-refresh.sh pause   (or: delete)" ;;
  run)    gcloud scheduler jobs run "${SCHEDULER_JOB}" --project "${PROJECT_ID}" --location "${REGION}" ;;
  pause)  gcloud scheduler jobs pause "${SCHEDULER_JOB}" --project "${PROJECT_ID}" --location "${REGION}" ;;
  resume) gcloud scheduler jobs resume "${SCHEDULER_JOB}" --project "${PROJECT_ID}" --location "${REGION}" ;;
  extend) deploy_job "$(stop_date "${2:?usage: extend DAYS}")" && echo "stop date moved to $(stop_date "$2")" ;;
  status)
    gcloud scheduler jobs describe "${SCHEDULER_JOB}" --project "${PROJECT_ID}" --location "${REGION}" --format='value(state,schedule,lastAttemptTime,status.code)' || true
    gcloud run jobs describe "${JOB}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(spec.template.spec.template.spec.containers[0].args)' || true
    gcloud run jobs executions list --job "${JOB}" --project "${PROJECT_ID}" --region "${REGION}" --limit 5 ;;
  delete)
    gcloud scheduler jobs delete "${SCHEDULER_JOB}" --project "${PROJECT_ID}" --location "${REGION}" --quiet || true
    gcloud run jobs delete "${JOB}" --project "${PROJECT_ID}" --region "${REGION}" --quiet || true
    echo "Nightly refresh removed. The data stays as of the last successful run." ;;
  *) echo "usage: $0 create [DAYS] | run | pause | resume | extend DAYS | status | delete" >&2; exit 1 ;;
esac
