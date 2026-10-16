import json

import pytest
from fastapi.testclient import TestClient

from app.core.enums import CustomEventName, EventType
from app.main import create_app


@pytest.fixture(scope="module")
def client(container):
    with TestClient(create_app(container)) as c:
        yield c


def ask(client, question, **kw):
    """Parses the AG-UI stream; returns (events, panda.result payload)."""
    r = client.post("/api/chat", json={"question": question, **kw})
    events = []
    for block in r.text.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        assert block.startswith("data: ") and "\nevent:" not in block  # AG-UI: data lines only
        events.append(json.loads(block[6:]))
    result = next((e["value"] for e in events if e["type"] == EventType.CUSTOM and e["name"] == CustomEventName.RESULT), None)
    return events, result


def test_stream_contract_and_cache_layers(client):
    client.post("/api/admin/cache/clear")
    events, result = ask(client, "Net GMV by zone last 7 days", runId="run-1")
    types = [e["type"] for e in events]
    assert types[0] == "RUN_STARTED" and events[0]["runId"] == "run-1" and "threadId" in events[0]
    assert types[-1] == "RUN_FINISHED" and events[-1]["outcome"] == {"type": "success"}
    started = [e["stepName"] for e in events if e["type"] == "STEP_STARTED"]
    assert started == [e["stepName"] for e in events if e["type"] == "STEP_FINISHED"] and started
    assert any(e["type"] == "CUSTOM" and e["name"] == "panda.step" and "node" in e["value"] for e in events)
    text = [e for e in events if e["type"].startswith("TEXT_MESSAGE")]
    assert [e["type"] for e in (text[0], text[-1])] == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_END"]
    assert "".join(e["delta"] for e in text if e["type"] == "TEXT_MESSAGE_CONTENT") == result["text"]
    surface = next(e for e in events if e["type"] == "ACTIVITY_SNAPSHOT")
    assert surface["activityType"] == "a2ui-surface" and "createSurface" in surface["content"][0]
    assert result["type"] == "answer" and result["meta"]["cache"] == "miss" and len(result["table"]["rows"]) == 4
    _, again = ask(client, "revenue split by zone past 7 days")  # different words, same resolved intent
    assert again["meta"]["cache"] == "hit"
    _, bypass = ask(client, "Net GMV by zone last 7 days", bypass_cache=True)
    assert bypass["meta"]["cache"] == "off"


def test_a2ui_catalog_served(client):
    cat = client.get("/api/a2ui/catalog").json()
    assert "VegaLiteChart" in cat["components"] and cat["catalogId"]


def test_follow_up_uses_thread_memory(client):
    _, first = ask(client, "Net GMV by zone last 7 days", thread_id="t-follow")
    _, second = ask(client, "and by marketplace?", thread_id="t-follow")
    assert second["table"]["columns"][0] == "marketplace" and first["table"]["columns"][0] == "zone"


def test_user_facing_errors_become_error_results(client):
    _, result = ask(client, "show me widgets")
    assert result["type"] == "error" and "No metric" in result["text"]


def test_rca_over_http(client):
    events, result = ask(client, "Why did Net GMV drop in the last 14 days?")
    components = next(e for e in events if e["type"] == "ACTIVITY_SNAPSHOT")["content"][1]["updateComponents"]["components"]
    assert {"HypothesisList", "SegmentBars", "DecompositionTable"} <= {c["component"] for c in components}
    assert result["type"] == "rca" and result["rca"]["drill"]["cells"][0]["segment"]["zone"] == "South"


def test_validation_health_and_request_id(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1500}).status_code == 422
    assert client.get("/health").json() == {"status": "ok"} and client.get("/ready").json()["status"] == "ready"
    assert client.get("/api/meta").json()["tables"]["fact_sales"] > 1_000_000
    assert client.get("/health", headers={"X-Request-Id": "abc123"}).headers["X-Request-Id"] == "abc123"


def test_run_error_is_generic_and_typed(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret detail")
        yield  # generator, like the real runner
    monkeypatch.setattr(client.app.state.container.runner, "stream", boom)
    r = client.post("/api/chat", json={"question": "anything"})
    err = json.loads(r.text.strip().split("\n\n")[-1][6:])
    assert err["type"] == "RUN_ERROR" and "secret" not in err["message"]
