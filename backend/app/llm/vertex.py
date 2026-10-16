"""Shared client options: Google AI Studio (API key) or Vertex AI (project + location, Application Default Credentials)."""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError


def client_options(settings: Settings, location: str = "") -> dict:
    if not settings.google_genai_use_vertexai:
        return {}
    if not settings.google_cloud_project:
        raise ConfigurationError("GOOGLE_GENAI_USE_VERTEXAI=true needs GOOGLE_CLOUD_PROJECT")
    return {"vertexai": True, "project": settings.google_cloud_project, "location": location or settings.google_cloud_location}
