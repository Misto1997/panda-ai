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
    last = max(i for i, e in enumerate(text) if e["type"] == "TEXT_MESSAGE_START")  # data first, an upgraded message may follow it
    assert "".join(e["delta"] for e in text[last:] if e["type"] == "TEXT_MESSAGE_CONTENT") == result["text"]
    results = [e for e in events if e["type"] == "CUSTOM" and e["name"] == "panda.result"]
    assert len(results) == 2 and results[-1]["value"]["meta"]["narrated"] is True and "narrated" not in results[0]["value"]["meta"]  # progressive answer
    assert any(e["type"] == "CUSTOM" and e["name"] == "panda.step" and e["value"].get("status") == "running" for e in events)  # live progress
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


# ---- chat history (memory store; the Postgres store is not covered here, it needs a real database) ----
def test_history_store_caps_and_title():
    from datetime import datetime, timedelta, timezone

    from app.history.store import MAX_THREADS, MAX_TURNS, MemoryHistoryStore, make_title

    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    store = MemoryHistoryStore(clock=lambda: now[0])
    assert len(make_title("x" * 200)) == 60
    for i in range(MAX_TURNS + 5):
        store.record("u", "t", f"q{i}", {"type": "answer", "text": str(i)})
    assert [t["question"] for t in store.get_thread("u", "t")["turns"]][0] == "q5"
    for i in range(MAX_THREADS + 3):
        now[0] += timedelta(seconds=1)
        store.record("u", f"th{i}", "q", {"type": "answer"})
    assert len(store.list_threads("u")) == MAX_THREADS and store.get_thread("u", "t") is None  # oldest dropped
    now[0] += timedelta(days=31)
    store.record("v", "x", "q", {"type": "answer"})
    assert store.list_threads("u") == []  # retention purge


def test_history_endpoints_and_isolation(container):
    import time

    from app.history import MemoryHistoryStore
    from app.security.auth import AuthUser
    from app.security.service import authenticated_user, current_user

    store = MemoryHistoryStore()
    old, container.history = container.history, store
    try:
        app = create_app(container)
        app.dependency_overrides[current_user] = app.dependency_overrides[authenticated_user] = lambda: AuthUser("alice", "a@x")
        with TestClient(app) as c:
            r = c.post("/api/chat", json={"question": "net gmv by zone last 7 days", "thread_id": "abc"})
            assert r.status_code == 200
            for _ in range(50):  # the write is fire-and-forget
                if store.list_threads("alice"):
                    break
                time.sleep(0.05)
            listed = c.get("/api/threads").json()["threads"]
            assert [t["id"] for t in listed] == ["abc"] and listed[0]["turns"] == 1 and listed[0]["title"].startswith("net gmv")
            turn = c.get("/api/threads/abc").json()["turns"][0]
            assert turn["question"].startswith("net gmv") and turn["response"]["type"] in ("answer", "rca", "info")
            assert c.get("/api/threads/bad.id").status_code == 422
            app.dependency_overrides[current_user] = lambda: AuthUser("bob", "b@x")
            assert c.get("/api/threads").json()["threads"] == []
            assert c.get("/api/threads/abc").status_code == 404
            c.delete("/api/threads/abc")
            assert store.get_thread("alice", "abc") is not None  # bob cannot delete alice's chat
            app.dependency_overrides[current_user] = lambda: AuthUser("alice", "a@x")
            assert c.delete("/api/threads/abc").status_code == 204 and c.get("/api/threads/abc").status_code == 404
    finally:
        container.history = old
