import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client(container):
    with TestClient(create_app(container)) as c:
        yield c


def ask(client, question, **kw):
    r = client.post("/api/chat", json={"question": question, **kw})
    events = []
    for block in r.text.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        lines = block.split("\n")
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events, next((d for e, d in events if e == "result"), None)


def test_stream_contract_and_cache_layers(client):
    client.post("/api/admin/cache/clear")
    events, result = ask(client, "Net GMV by zone last 7 days")
    names = [e for e, _ in events]
    assert names[0] == "run_started" and names[-1] == "run_finished" and "step" in names
    assert result["type"] == "answer" and result["meta"]["cache"] == "miss" and len(result["table"]["rows"]) == 4
    _, again = ask(client, "revenue split by zone past 7 days")  # different words, same resolved intent
    assert again["meta"]["cache"] == "hit"
    _, bypass = ask(client, "Net GMV by zone last 7 days", bypass_cache=True)
    assert bypass["meta"]["cache"] == "off"


def test_follow_up_uses_thread_memory(client):
    _, first = ask(client, "Net GMV by zone last 7 days", thread_id="t-follow")
    _, second = ask(client, "and by marketplace?", thread_id="t-follow")
    assert second["table"]["columns"][0] == "marketplace" and first["table"]["columns"][0] == "zone"


def test_user_facing_errors_become_error_results(client):
    _, result = ask(client, "show me widgets")
    assert result["type"] == "error" and "No metric" in result["text"]


def test_rca_over_http(client):
    _, result = ask(client, "Why did Net GMV drop in the last 14 days?")
    assert result["type"] == "rca" and result["rca"]["drill"]["cells"][0]["segment"]["zone"] == "South"


def test_validation_health_and_request_id(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1500}).status_code == 422
    assert client.get("/health").json() == {"status": "ok"} and client.get("/ready").json()["status"] == "ready"
    assert client.get("/api/meta").json()["tables"]["fact_sales"] > 1_000_000
    assert client.get("/health", headers={"X-Request-Id": "abc123"}).headers["X-Request-Id"] == "abc123"
