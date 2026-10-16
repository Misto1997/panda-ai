"""Bundle of the access-control collaborators, built once by the Container."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.core.db import PgPool
from app.security.auth import Authenticator, AuthUser
from app.security.limits import IpRateLimiter, client_ip
from app.security.quota import MemoryUsageStore, PgUsageStore, QuotaService


@dataclass
class Security:
    authenticator: Authenticator
    quota: QuotaService
    limiter: IpRateLimiter


def build_security(settings: Settings, pool: PgPool | None) -> Security:
    store = PgUsageStore(pool) if pool else MemoryUsageStore()
    return Security(
        Authenticator.from_settings(settings),
        QuotaService(store, settings.daily_user_query_limit, settings.daily_global_query_limit),
        IpRateLimiter(settings.ip_rate_per_minute, settings.ip_rate_burst))


def _security(request: Request) -> Security:
    return request.app.state.container.security


def authenticated_user(request: Request) -> AuthUser:
    """FastAPI dependency: per-IP rate limit, then identity. Raises 429 / 401 as PandaErrors. Never touches quota or the LLM."""
    sec = _security(request)
    sec.limiter.check(client_ip(request.headers, request.client.host if request.client else None))
    return sec.authenticator.authenticate(request.headers.get("authorization"))


def current_user(request: Request) -> AuthUser:
    """FastAPI dependency for read-only endpoints (no IP bucket charge)."""
    return _security(request).authenticator.authenticate(request.headers.get("authorization"))
