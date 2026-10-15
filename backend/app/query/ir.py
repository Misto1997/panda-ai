from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import TimeGrain


class Filter(BaseModel):
    dim: str
    values: list[str]
    negate: bool = False


class QueryIR(BaseModel):
    """Structured intent. The LLM only ever fills this; SQL is compiled from it by code."""
    metrics: list[str] = Field(description="Metric ids from the semantic layer")
    dimensions: list[str] = Field(default_factory=list, description="Dimension ids to group by")
    filters: list[Filter] = Field(default_factory=list)
    time_expr: str = Field(default="last_30_days", description=(
        "One of: today, yesterday, last_7_days, last_14_days, last_30_days, last_90_days, this_week, last_week, "
        "this_month, last_month, mtd, all_time, last_n_days:N, or an explicit range YYYY-MM-DD..YYYY-MM-DD"))
    grain: TimeGrain = Field(default=TimeGrain.NONE, description="Time series grain; none = single aggregate")
    order_by: str | None = Field(default=None, description="Metric id to sort by")
    order_desc: bool = True
    limit: int | None = Field(default=None, ge=1, le=500)
