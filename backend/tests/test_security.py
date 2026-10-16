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
            assert c.get("/api/me", headers=ok).json() == {"email": "a@b.c", "remaining_today": 1, "daily_limit": 1, "admin": False}
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


def test_admin_endpoints_are_restricted_in_firebase_mode():
    from types import SimpleNamespace

    from app.core.enums import AuthMode
    from app.core.errors import ForbiddenError
    from app.security.auth import AuthUser
    from app.security.service import admin_user

    def request(mode, email, admins):
        settings = SimpleNamespace(auth_mode=mode, admin_email_list=[a for a in admins])
        security = SimpleNamespace(authenticator=SimpleNamespace(authenticate=lambda header: AuthUser("u", email)))
        container = SimpleNamespace(settings=settings, security=security)
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)), headers={})

    assert admin_user(request(AuthMode.DEV, "dev@localhost", [])).email == "dev@localhost"
    assert admin_user(request(AuthMode.FIREBASE, "Boss@Example.com", ["boss@example.com"])).email == "Boss@Example.com"
    import pytest
    with pytest.raises(ForbiddenError):
        admin_user(request(AuthMode.FIREBASE, "random@example.com", ["boss@example.com"]))


def test_embedding_rate_limit_is_retried_with_backoff_and_never_fans_out(monkeypatch):

    from app.core.errors import LlmError
    from app.llm import embeddings as emb

    sleeps = []
    monkeypatch.setattr(emb.time, "sleep", sleeps.append)

    class Flaky:
        def __init__(self, fail_times): self.fail, self.calls = fail_times, 0
        def embed_documents(self, texts):
            self.calls += 1
            if self.calls <= self.fail:
                raise RuntimeError("429 Resource exhausted, please try again later.")
            return [[1.0, 0.0] for _ in texts]

    e = emb.GeminiEmbedder.__new__(emb.GeminiEmbedder)
    e._client = Flaky(2)
    assert e.embed(["a", "b"]).shape == (2, 2) and sleeps[:2] == [4.0, 8.0]      # two 429s, then success after backoff

    e._client = Flaky(99)  # permanently limited: fail loudly after bounded retries, one call per attempt (no burst of single calls)
    with pytest.raises(LlmError):
        e.embed(["a", "b", "c"])
    assert e._client.calls == emb.GeminiEmbedder.INDEX_ATTEMPTS


def test_admins_are_exempt_from_the_per_user_cap_but_not_the_global_one():
    import pytest
    from app.core.errors import QuotaExceededError
    from app.security.auth import AuthUser
    from app.security.quota import MemoryUsageStore, QuotaService

    quota = QuotaService(MemoryUsageStore(), user_limit=2, global_limit=5, exempt_emails=frozenset({"Boss@example.com"}))
    boss, other = AuthUser("b", "boss@example.com"), AuthUser("o", "other@example.com")
    for _ in range(4):
        quota.consume(boss)                      # well past the per-user cap of 2
    quota.consume(other)
    with pytest.raises(QuotaExceededError):
        quota.consume(boss)                      # the global cap of 5 still applies


def test_admin_is_exempt_and_reported():
    q = QuotaService(MemoryUsageStore(), 2, 10, exempt_emails=frozenset({"Boss@x.io"}))
    admin, user = AuthUser("a", "boss@x.io"), AuthUser("u", "u@x.io")
    assert q.is_exempt(admin) and not q.is_exempt(user) and not q.is_exempt(AuthUser("n", ""))
    for _ in range(5):
        q.consume(admin)
    assert q.remaining(admin) == 5 and q.remaining(user) == 2  # admin: what is left is the shared pool
