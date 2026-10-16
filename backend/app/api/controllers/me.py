from __future__ import annotations

from fastapi import APIRouter, Depends

from app.container import Container
from app.security.auth import AuthUser
from app.security.service import current_user


class MeController:
    """GET /api/me: who the caller is and how many questions they have left today."""

    def __init__(self, container: Container) -> None:
        self._quota = container.security.quota
        self.router = APIRouter(prefix="/api", tags=["me"])
        self.router.add_api_route("/me", self.me, methods=["GET"])

    def me(self, user: AuthUser = Depends(current_user)) -> dict:
        return {"email": user.email, "remaining_today": self._quota.remaining(user), "daily_limit": self._quota.user_limit}
