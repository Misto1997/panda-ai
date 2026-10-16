#!/usr/bin/env bash
# Put a free Firebase Hosting address (https://<site>.web.app) in front of the Cloud Run web service.
#   HOSTING_SITE=panda-ai deploy/70-hosting.sh        (needs: npm i -g firebase-tools, firebase login)
# Cost: the .web.app address and Hosting are free at demo volume; the project must be on the Blaze plan (billing is linked already).
# CAVEAT: Hosting proxies to Cloud Run with a request time limit (about 60 s, UNVERIFIED) and may buffer: confirm streaming with
#   make probe API=<api url> WEB=https://<site>.web.app ARGS="--via-web --quick"
# Afterwards add <site>.web.app and <site>.firebaseapp.com to Firebase Authentication > Settings > Authorized domains.
source "$(dirname "$0")/lib.sh"
SITE="${HOSTING_SITE:-panda-ai}"
command -v firebase >/dev/null || { echo "install the Firebase CLI first: npm i -g firebase-tools && firebase login" >&2; exit 1; }
WORK="$(mktemp -d)"; cp -R "${DEPLOY_DIR}/firebase-hosting/public" "${WORK}/public"
cat > "${WORK}/firebase.json" <<JSON
{ "hosting": { "site": "${SITE}", "public": "public", "ignore": ["firebase.json", "**/.*"],
  "rewrites": [ { "source": "**", "run": { "serviceId": "${WEB_SERVICE}", "region": "${REGION}" } } ] } }
JSON
firebase hosting:sites:create "${SITE}" --project "${PROJECT_ID}" 2>/dev/null || echo "site ${SITE} exists (or the id is taken: choose another HOSTING_SITE)"
(cd "${WORK}" && firebase deploy --only hosting --project "${PROJECT_ID}")
echo "Live at https://${SITE}.web.app"
