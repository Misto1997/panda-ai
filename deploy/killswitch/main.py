"""Budget kill-switch: on a budget notification at or above 100% of the budget, remove public (allUsers) invoker access from
the Cloud Run services listed in KILL_SERVICES. Spend stops growing because nobody can reach the app; fix and redeploy to restore.

Budget notification payload (Pub/Sub message data, JSON): costAmount, budgetAmount, alertThresholdExceeded (optional), ...
Entry point: on_budget_alert (CloudEvent, Pub/Sub trigger)."""
from __future__ import annotations

import base64
import json
import logging
import os

log = logging.getLogger("killswitch")
PUBLIC_MEMBER = "allUsers"
INVOKER_ROLE = "roles/run.invoker"


def should_kill(payload: dict) -> bool:
    cost, budget = payload.get("costAmount"), payload.get("budgetAmount")
    if cost is not None and budget:
        return float(cost) >= float(budget)
    return float(payload.get("alertThresholdExceeded", 0)) >= 1.0


def revoke_public_access(client, resource: str) -> bool:
    """Removes allUsers from roles/run.invoker. `client` needs get_iam_policy(resource) and set_iam_policy(resource, policy)
    with a policy exposing .bindings[].role / .members (a protobuf Policy or a compatible fake). Returns True if changed."""
    policy = client.get_iam_policy(resource)
    changed = False
    for binding in policy.bindings:
        if binding.role == INVOKER_ROLE and PUBLIC_MEMBER in binding.members:
            binding.members.remove(PUBLIC_MEMBER)
            changed = True
    if changed:
        client.set_iam_policy(resource, policy)
    return changed


def kill(client, project: str, region: str, services: list[str]) -> list[str]:
    done = []
    for name in services:
        resource = f"projects/{project}/locations/{region}/services/{name}"
        if revoke_public_access(client, resource):
            done.append(name)
            log.warning("revoked public access: %s", resource)
    return done


class _RunIamClient:
    """Thin adapter over google-cloud-run's ServicesClient (UNVERIFIED against the live API: signature of the IAM calls)."""

    def __init__(self) -> None:
        from google.cloud import run_v2
        self._c = run_v2.ServicesClient()

    def get_iam_policy(self, resource: str):
        from google.iam.v1 import iam_policy_pb2
        return self._c.get_iam_policy(request=iam_policy_pb2.GetIamPolicyRequest(resource=resource))

    def set_iam_policy(self, resource: str, policy) -> None:
        from google.iam.v1 import iam_policy_pb2
        self._c.set_iam_policy(request=iam_policy_pb2.SetIamPolicyRequest(resource=resource, policy=policy))


def handle(event_data: dict, client, project: str, region: str, services: list[str]) -> list[str]:
    payload = json.loads(base64.b64decode(event_data["message"]["data"]).decode())
    if not should_kill(payload):
        log.info("budget notification below 100%%: no action (%s)", payload.get("alertThresholdExceeded"))
        return []
    return kill(client, project, region, services)


try:  # functions-framework is only present in the deployed function
    import functions_framework

    @functions_framework.cloud_event
    def on_budget_alert(cloud_event) -> None:
        services = [s.strip() for s in os.environ["KILL_SERVICES"].split(",") if s.strip()]
        handle(cloud_event.data, _RunIamClient(), os.environ["KILL_PROJECT"], os.environ["KILL_REGION"], services)
except ImportError:  # unit tests import the pure functions above
    pass
