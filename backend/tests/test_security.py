from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.enums import AuthMode
from app.core.errors import AuthenticationError, QuotaExceededError, RateLimitedError
from app.main import create_app
from app.security.auth import Authenticator, AuthUser
from app.security.limits import IpRateLimiter
from app.security.quota import MemoryUsageStore, QuotaService
from app.security.service import Security


class FakeVerifier:
    def verify(self, token):
        if token != "good":
            raise ValueError("bad")
        return {"user_id": "u1", "email": "a@b.c", "exp": 9e12}


def test_authenticator_firebase_modes():
    auth = Authenticator(AuthMode.FIREBASE, FakeVerifier())
    assert auth.authenticate("Bearer good") == AuthUser("u1", "a@b.c")
    for header in (None, "", "Bearer", "Basic good", "Bearer nope"):
        with pytest.raises(AuthenticationError):
            auth.authenticate(header)
    assert Authenticator(AuthMode.DEV).authenticate(None).uid == "dev-user"


def test_quota_user_and_global_limits_are_atomic():
    day = date(2026, 10, 1)
    q = QuotaService(MemoryUsageStore(), user_limit=2, global_limit=3, today=lambda: day)
    a, b = AuthUser("a", "a"), AuthUser("b", "b")
    assert q.consume(a) == 1 and q.consume(a) == 0
    with pytest.raises(QuotaExceededError) as e:
        q.consume(a)
    assert e.value.details == {"remaining": 0}
    assert q.consume(b) == 0  # global total is now 3, b used 1 of 2
    with pytest.raises(QuotaExceededError):
        q.consume(b)
    assert q.remaining(b) == 0 and q.remaining(AuthUser("c", "c")) == 0  # global cap hit: nobody can ask
    nxt = QuotaService(q._store, 2, 3, today=lambda: date(2026, 10, 2))
    assert nxt.remaining(a) == 2


def test_ip_rate_limiter_refills():
    now = [0.0]
    lim = IpRateLimiter(rate_per_minute=60, burst=2, clock=lambda: now[0])
    lim.check("1.1.1.1"), lim.check("1.1.1.1")
    with pytest.raises(RateLimitedError):
        lim.check("1.1.1.1")
    lim.check("2.2.2.2")
    now[0] = 1.0
    lim.check("1.1.1.1")


def _client(container, **sec):
    base = container.security
    container_sec = Security(sec.get("authenticator", base.authenticator), sec.get("quota", base.quota), sec.get("limiter", base.limiter))
    swapped = type(container)(**{**container.__dict__, "security": container_sec})
    return TestClient(create_app(swapped))


def test_http_auth_quota_and_no_llm_call_on_rejection(container):
    calls = []
    orig = container.runner.stream
    container.runner.stream = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
    quota = QuotaService(MemoryUsageStore(), 1, 10)
    try:
        with _client(container, authenticator=Authenticator(AuthMode.FIREBASE, FakeVerifier()), quota=quota) as c:
            body = {"question": "Net GMV by zone last 7 days"}
            r = c.post("/api/chat", json=body)
            assert r.status_code == 401 and r.json()["code"] == "unauthenticated" and not calls
            ok = {"Authorization": "Bearer good"}
            assert c.get("/api/me", headers=ok).json() == {"email": "a@b.c", "remaining_today": 1, "daily_limit": 1}
            assert c.post("/api/chat", json={"question": ""}, headers=ok).status_code == 422  # invalid body costs nothing
            assert c.post("/api/chat", json=body, headers=ok).status_code == 200 and len(calls) == 1
            r = c.post("/api/chat", json=body, headers=ok)
            assert r.status_code == 429 and r.json()["code"] == "quota_exceeded" and r.json()["remaining"] == 0 and len(calls) == 1
    finally:
        container.runner.stream = orig


def test_oversized_body_rejected(container):
    with _client(container) as c:
        r = c.post("/api/chat", content=b"x" * 40_000, headers={"content-type": "application/json"})
        assert r.status_code == 413 and r.json()["code"] == "request_too_large"


def test_ddl_scripts_are_split_into_single_statements():
    """Regression: the pool prepares every statement, and Postgres rejects multi-command prepared statements."""
    from app.core.db import execute_script
    from app.search.pgvector import DDL, INDEX_DDL
    from app.core.enums import VectorIndexKind

    class Recorder:
        def __init__(self): self.sql = []
        def execute(self, statement): self.sql.append(statement)

    conn = Recorder()
    execute_script(conn, DDL.format(dim=768))
    execute_script(conn, INDEX_DDL[VectorIndexKind.SCANN])
    assert len(conn.sql) == 5 and all(";" not in stmt for stmt in conn.sql)
