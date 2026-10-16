#!/usr/bin/env bash
# One-time project setup: APIs, Artifact Registry, secrets, service account roles. Safe to re-run.
source "$(dirname "$0")/lib.sh"
gcloud config set project "${PROJECT_ID}"

echo "== enable APIs"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com \
  aiplatform.googleapis.com bigquery.googleapis.com alloydb.googleapis.com servicenetworking.googleapis.com \
  compute.googleapis.com identitytoolkit.googleapis.com pubsub.googleapis.com billingbudgets.googleapis.com \
  cloudfunctions.googleapis.com eventarc.googleapis.com logging.googleapis.com

echo "== Artifact Registry repo ${AR_REPO}"
gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${AR_REPO}" --repository-format=docker --location="${REGION}" --description="PANDA images"

echo "== service account ${SERVICE_ACCOUNT}"
gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" --display-name="PANDA API"

grant() { gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${SERVICE_ACCOUNT}" --role="$1" --condition=None --quiet >/dev/null; echo "  + $1"; }
grant roles/aiplatform.user
grant roles/bigquery.jobUser
grant roles/logging.logWriter
grant roles/alloydb.client        # only needed for the AlloyDB connector/IAM auth; harmless for password auth over private IP

echo "== BigQuery: dataEditor on dataset ${BQ_DATASET} (bootstrap job loads tables; the API only reads)"
bq --project_id="${PROJECT_ID}" show --format=none "${BQ_DATASET}" >/dev/null 2>&1 || \
  bq --project_id="${PROJECT_ID}" --location="${BQ_LOCATION:-asia-southeast1}" mk --dataset "${PROJECT_ID}:${BQ_DATASET}"
tmp="$(mktemp)"; bq --project_id="${PROJECT_ID}" show --format=prettyjson "${PROJECT_ID}:${BQ_DATASET}" > "${tmp}"
python3 - "${tmp}" "${SERVICE_ACCOUNT}" <<'PY'
import json, sys
path, sa = sys.argv[1:]
ds = json.load(open(path))
access = ds.setdefault("access", [])
entry = {"role": "WRITER", "userByEmail": sa}
if entry not in access:
    access.append(entry)
json.dump({"access": access}, open(path, "w"))
PY
bq --project_id="${PROJECT_ID}" update --source "${tmp}" "${PROJECT_ID}:${BQ_DATASET}" >/dev/null && rm -f "${tmp}"
echo "  + dataset WRITER (dataEditor equivalent) for ${SERVICE_ACCOUNT}"

echo "== Secret Manager: ${DB_PASSWORD_SECRET} (value prompted, never passed as an argument)"
if ! gcloud secrets describe "${DB_PASSWORD_SECRET}" >/dev/null 2>&1; then
  gcloud secrets create "${DB_PASSWORD_SECRET}" --replication-policy=automatic
fi
read -r -s -p "AlloyDB password for user ${DB_USER:-panda_app} (Enter to keep existing version): " DB_PW; echo
if [[ -n "${DB_PW}" ]]; then
  printf '%s' "${DB_PW}" | gcloud secrets versions add "${DB_PASSWORD_SECRET}" --data-file=-
fi
unset DB_PW
gcloud secrets add-iam-policy-binding "${DB_PASSWORD_SECRET}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/secretmanager.secretAccessor --quiet >/dev/null

echo "== Cloud Build permissions (builds run as the Compute Engine default service account on new projects; verify in the console)"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${BUILD_SA}" --role="${role}" --condition=None --quiet >/dev/null
done
# Gen2 Cloud Functions (kill-switch) build with this account too. Docs say it needs cloudbuild.builds.builder (includes Artifact Registry
# and Storage access) plus logging.logWriter. UNVERIFIED: the exact builder account depends on org policy / project age; check the console
# (Cloud Build > Settings) or pass --build-service-account to gcloud functions deploy if builds fail with permission errors.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${BUILD_SA}" --role=roles/cloudbuild.builds.builder --condition=None --quiet >/dev/null
echo "  + roles/cloudbuild.builds.builder (gen2 function builds)"
# Eventarc/Pub/Sub trigger delivery: the kill-switch SA gets roles/eventarc.eventReceiver in killswitch/deploy.sh (it creates that SA).
# UNVERIFIED: projects created before April 2021 also need the Pub/Sub service agent to hold roles/iam.serviceAccountTokenCreator.
echo "done."
