import base64
import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("killswitch_main", Path(__file__).resolve().parents[2] / "deploy" / "killswitch" / "main.py")
ks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ks)


@dataclass
class Binding:
    role: str
    members: list = field(default_factory=list)


@dataclass
class Policy:
    bindings: list


class FakeClient:
    def __init__(self):
        self.policies, self.set_calls = {}, []

    def get_iam_policy(self, resource):
        return self.policies.setdefault(resource, Policy([Binding("roles/run.invoker", ["allUsers", "user:a@b.c"]), Binding("roles/run.admin", ["user:x"])]))

    def set_iam_policy(self, resource, policy):
        self.set_calls.append(resource)


def _event(cost, budget):
    return {"message": {"data": base64.b64encode(json.dumps({"costAmount": cost, "budgetAmount": budget}).encode()).decode()}}


def test_below_budget_does_nothing():
    c = FakeClient()
    assert ks.handle(_event(40, 100), c, "p", "r", ["api", "web"]) == [] and not c.set_calls


def test_at_budget_removes_only_allusers_invoker():
    c = FakeClient()
    assert ks.handle(_event(100, 100), c, "p", "r", ["api", "web"]) == ["api", "web"]
    policy = c.policies["projects/p/locations/r/services/api"]
    assert policy.bindings[0].members == ["user:a@b.c"] and policy.bindings[1].members == ["user:x"]
    assert ks.handle(_event(120, 100), c, "p", "r", ["api"]) == []  # already private: idempotent, no second write
    assert len(c.set_calls) == 2


def test_threshold_fraction_fallback():
    assert ks.should_kill({"alertThresholdExceeded": 1.0}) and not ks.should_kill({"alertThresholdExceeded": 0.9})
