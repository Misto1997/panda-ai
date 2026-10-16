#!/usr/bin/env bash
# Stop / start the AlloyDB instance to save cost when idle:  deploy/alloydb.sh stop|start|status
# UNVERIFIED: --activation-policy=NEVER|ALWAYS is documented for `gcloud alloydb instances update`; confirm the current behaviour
# (stopped instances still bill for storage; startup takes minutes) at https://cloud.google.com/alloydb/docs/instance-stop-start
source "$(dirname "$0")/lib.sh"
ARGS=(--project "${PROJECT_ID}" --region "${REGION}" --cluster "${ALLOYDB_CLUSTER}")
case "${1:-}" in
  stop)   gcloud alloydb instances update "${ALLOYDB_INSTANCE}" "${ARGS[@]}" --activation-policy=NEVER ;;
  start)  gcloud alloydb instances update "${ALLOYDB_INSTANCE}" "${ARGS[@]}" --activation-policy=ALWAYS ;;
  status) gcloud alloydb instances describe "${ALLOYDB_INSTANCE}" "${ARGS[@]}" --format='value(state,activationPolicy)' ;;
  *) echo "usage: $0 stop|start|status" >&2; exit 1 ;;
esac
