#!/usr/bin/env bash
# Keep Artifact Registry small: keep the 3 most recent versions of every image, delete anything older than 7 days.
# Default is a DRY RUN that only reports what would be deleted. Apply with:  deploy/90-cleanup.sh --apply
# Flags follow `gcloud artifacts repositories set-cleanup-policies` (UNVERIFIED against current docs: check `gcloud artifacts repositories set-cleanup-policies --help`).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
POLICY="$(mktemp)"
cat > "${POLICY}" <<'JSON'
[
  {"name": "keep-recent-3", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}},
  {"name": "delete-older-than-7d", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "7d"}}
]
JSON
MODE="--dry-run"; [[ "${1:-}" == "--apply" ]] && MODE="--no-dry-run"
gcloud artifacts repositories set-cleanup-policies "${AR_REPO}" --project="${PROJECT_ID}" --location="${REGION}" --policy="${POLICY}" ${MODE}
rm -f "${POLICY}"
echo "Cloud Run keeps old revisions (no cost while idle). Remove unused ones with:  gcloud run revisions list --service=panda-api --region=${REGION}  then  gcloud run revisions delete <name> --region=${REGION}"
