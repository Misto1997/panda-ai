#!/usr/bin/env bash
# Build both images with Cloud Build and push them to Artifact Registry. Run from anywhere.
source "$(dirname "$0")/lib.sh"
require_set FIREBASE_API_KEY FIREBASE_AUTH_DOMAIN FIREBASE_PROJECT_ID FIREBASE_APP_ID
cd "${REPO_ROOT}"
gcloud builds submit --project "${PROJECT_ID}" --region "${REGION}" --config deploy/cloudbuild-api.yaml \
  --substitutions="_IMAGE=${IMAGE_BASE}/panda-api,_TAG=${IMAGE_TAG:-latest}" .
gcloud builds submit --project "${PROJECT_ID}" --region "${REGION}" --config deploy/cloudbuild-web.yaml \
  --substitutions="_IMAGE=${IMAGE_BASE}/panda-web,_TAG=${IMAGE_TAG:-latest},_FB_API_KEY=${FIREBASE_API_KEY},_FB_AUTH_DOMAIN=${FIREBASE_AUTH_DOMAIN},_FB_PROJECT_ID=${FIREBASE_PROJECT_ID},_FB_APP_ID=${FIREBASE_APP_ID}" .
