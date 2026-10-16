# Sourced by every script: loads deploy/env.sh and offers helpers.
set -euo pipefail
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
if [[ ! -f "${DEPLOY_DIR}/env.sh" ]]; then
  echo "deploy/env.sh missing: cp deploy/env.example.sh deploy/env.sh and fill it" >&2; exit 1
fi
# shellcheck disable=SC1091
source "${DEPLOY_DIR}/env.sh"
for v in PROJECT_ID REGION SERVICE_ACCOUNT AR_REPO; do
  [[ -n "${!v:-}" ]] || { echo "env var $v is empty" >&2; exit 1; }
done
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
API_IMAGE="${IMAGE_BASE}/panda-api:${IMAGE_TAG:-latest}"
WEB_IMAGE="${IMAGE_BASE}/panda-web:${IMAGE_TAG:-latest}"
require_set() { for v in "$@"; do [[ -n "${!v:-}" && "${!v}" != REPLACE* ]] || { echo "set $v in deploy/env.sh" >&2; exit 1; }; done; }
