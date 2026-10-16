"""Wire contracts shared by the agents and the HTTP layer. The frontend mirrors these in frontend/lib/types.ts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CacheStatus, ResponseType


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: str | None = Field(default=None, alias="runId", max_length=64, pattern=r"^[A-Za-z0-9_-]+$")  # AG-UI run id, optional
    question: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    force_raw: bool = False
    bypass_cache: bool = False


class StepEvent(BaseModel):
    node: str
    step: str
    detail: str
    ms: float = 0
    cache: CacheStatus | None = None


class TablePayload(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    formats: dict[str, str]
    titles: dict[str, str]
    truncated: bool = False


class ResultMeta(BaseModel):
    route: str
    engine: str | None = None
    llm: str | None = None
    sources: dict[str, str] | None = None
    elapsed_ms: float | None = None
    cache: CacheStatus | None = None
    ir_source: str | None = None
    period: str | None = None
    rows: int | None = None
    docs: list[str] = Field(default_factory=list)
    search_backend: str | None = None
    tree: str | None = None
    queries: int | None = None
    total_ms: float | None = None
    bytes_processed: int | None = None   # engine-reported scan size (BigQuery)
    path: str | None = None              # how the SQL was produced: text_to_sql | ir_fallback | cache
    narrated: bool | None = None         # True when the model-written text replaced the standard summary
    sql_attempts: int | None = None      # generation + repair attempts


class ChatResult(BaseModel):
    type: ResponseType
    text: str
    meta: ResultMeta
    table: TablePayload | None = None
    chart: dict | None = None
    sql: str | None = None
    rca: dict | None = None

    def to_state(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def error(cls, text: str, route: str) -> "ChatResult":
        return cls(type=ResponseType.ERROR, text=text, meta=ResultMeta(route=route))
