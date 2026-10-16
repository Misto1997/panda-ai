"""Caller identity. AUTH_MODE=dev returns a fixed local user; firebase verifies a Firebase ID token (Google sign-in)
with google-auth: no secrets, only the public project id as audience."""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings
from app.core.enums import AuthMode
from app.core.errors import AuthenticationError, ConfigurationError
from app.core.logging import get_logger

log = get_logger("security.auth")
FIREBASE_ISSUER = "https://securetoken.google.com/{project}"
CACHE_TTL_S = 300
DEV_USER_EMAIL = "dev@localhost"


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, Any]:
        """Returns decoded claims or raises ValueError for any invalid token."""


class FirebaseTokenVerifier:
    def __init__(self, project_id: str) -> None:
        from google.auth.transport import requests as google_requests

        self._project, self._request = project_id, google_requests.Request()

    def verify(self, token: str) -> Mapping[str, Any]:
        from google.auth.exceptions import GoogleAuthError
        from google.oauth2 import id_token

        try:
            claims = id_token.verify_firebase_token(token, self._request, audience=self._project)
        except GoogleAuthError as e:  # transport failures while fetching certs
            raise ValueError(f"token verification failed: {e}") from e
        if claims.get("iss") != FIREBASE_ISSUER.format(project=self._project):
            raise ValueError("wrong token issuer")
        return claims


class Authenticator:
    def __init__(self, mode: AuthMode, verifier: TokenVerifier | None = None, clock: Callable[[], float] = time.time) -> None:
        if mode == AuthMode.FIREBASE and verifier is None:
            raise ConfigurationError("AUTH_MODE=firebase needs a token verifier (set FIREBASE_PROJECT_ID)")
        self._mode, self._verifier, self._clock = mode, verifier, clock
        self._cache: dict[str, tuple[AuthUser, float]] = {}

    @classmethod
    def from_settings(cls, s: Settings) -> "Authenticator":
        if s.auth_mode == AuthMode.DEV:
            return cls(AuthMode.DEV)
        if not s.firebase_project_id:
            raise ConfigurationError("AUTH_MODE=firebase needs FIREBASE_PROJECT_ID")
        return cls(AuthMode.FIREBASE, FirebaseTokenVerifier(s.firebase_project_id))

    def authenticate(self, authorization: str | None) -> AuthUser:
        if self._mode == AuthMode.DEV:
            return AuthUser("dev-user", DEV_USER_EMAIL)
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Sign in to continue.")
        token = token.strip()
        now = self._clock()
        if (hit := self._cache.get(token)) and hit[1] > now:
            return hit[0]
        try:
            claims = self._verifier.verify(token)
        except ValueError as e:
            log.info("rejected token: %s", e)
            raise AuthenticationError("Your session is invalid or expired. Sign in again.") from e
        uid = claims.get("user_id") or claims.get("sub")
        if not uid:
            raise AuthenticationError("Your session is invalid or expired. Sign in again.")
        user = AuthUser(str(uid), str(claims.get("email") or uid))
        if len(self._cache) > 1000:
            self._cache.clear()
        self._cache[token] = (user, min(float(claims.get("exp", now)), now + CACHE_TTL_S))
        return user
