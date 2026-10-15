"""Structured outputs the LLM must produce for each decision point."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import Route


class RouteDecision(BaseModel):
    route: Route
    reasoning: str = ""


class RcaRequest(BaseModel):
    metric: str = Field(description="Metric id whose movement should be explained")
    time_expr: str = Field(default="last_14_days", description="Period to explain, same grammar as QueryIR.time_expr")
