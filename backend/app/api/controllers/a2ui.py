from __future__ import annotations

from fastapi import APIRouter

from app.presentation.a2ui import load_catalog


class A2uiController:
    """GET /api/a2ui/catalog: the custom A2UI component catalog the answer surfaces are built against."""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/api/a2ui", tags=["a2ui"])
        self.router.add_api_route("/catalog", self.catalog, methods=["GET"])

    def catalog(self) -> dict:
        return load_catalog()
