"""Structured outputs the LLM must produce for each decision point."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import Confidence


class RcaRequest(BaseModel):
    metric: str = Field(description="Metric id whose movement should be explained")
    time_expr: str = Field(default="last_14_days", description="Period to explain, same grammar as QueryIR.time_expr")


class SqlDraft(BaseModel):
    """Structured output of SQL generation and repair. An empty `sql` means the question cannot be answered; `rationale` says why."""
    sql: str = Field(description="One SELECT over the logical tables, or an empty string if the question cannot be answered")
    rationale: str = Field(default="", description="Short reasoning: which metrics, tables and period were used (or why none apply)")
    confidence: Confidence = Field(default=Confidence.MEDIUM, description="low, medium or high")
