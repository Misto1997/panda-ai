#!/usr/bin/env bash
# Smoke test of the deployed services. Optional: SMOKE_ID_TOKEN=<Firebase ID token> to include a real chat turn.
source "$(dirname "$0")/lib.sh"
API_URL="$(gcloud run services describe "${API_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
FAILS=0
check() {  # name, ok(0/1)
  if [[ "$2" == 0 ]]; then echo "PASS  $1"; else echo "FAIL  $1"; FAILS=$((FAILS + 1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' --max-time "${3:-60}" "${@:4}" "$1" | grep -q "^$2$"; }  # returns non-zero on any failure; callers must use it inside `if` (errexit-safe)

if code "${API_URL}/health" 200; then check "api /health" 0; else check "api /health" 1; fi
if code "${API_URL}/ready" 200 90; then check "api /ready (engine reachable; first call may cold-start)" 0; else check "api /ready (engine reachable; first call may cold-start)" 1; fi
if code "${API_URL}/api/meta" 200 90; then check "api /api/meta" 0; else check "api /api/meta" 1; fi
if code "${WEB_URL}/" 200; then check "web /" 0; else check "web /" 1; fi
if code "${API_URL}/api/chat" 401 30 -X POST -H 'content-type: application/json' -d '{"question":"hi"}'; then check "api /api/chat rejects anonymous (401)" 0; else check "api /api/chat rejects anonymous (401)" 1; fi

if [[ -n "${SMOKE_ID_TOKEN:-}" ]]; then
  OUT="$(curl -s --max-time 120 -N -X POST "${API_URL}/api/chat" -H "Authorization: Bearer ${SMOKE_ID_TOKEN}" \
         -H 'content-type: application/json' -d '{"question":"Net GMV by zone for the last 7 days"}' || true)"
  if grep -q 'RUN_FINISHED' <<<"${OUT}"; then check "api /api/chat SSE turn finishes (RUN_FINISHED)" 0; else check "api /api/chat SSE turn finishes (RUN_FINISHED)" 1; fi
  if grep -q 'RUN_ERROR' <<<"${OUT}"; then check "chat turn had no RUN_ERROR" 1; else check "chat turn had no RUN_ERROR" 0; fi
else
  echo "SKIP  authenticated chat turn (export SMOKE_ID_TOKEN to enable)"
fi
[[ "${FAILS}" == 0 ]] && echo "ALL PASSED" || { echo "${FAILS} FAILED"; exit 1; }
