"""Result of an RCA investigation. JSON-serialised straight into the chat payload."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import HypothesisStatus, HypothesisTest, ValueFormat


class PeriodValue(BaseModel):
    start: str
    end: str  # inclusive last day
    value: float | None


class CheckOutcome(BaseModel):
    id: str
    title: str
    fired: bool
    detail: str


class ComponentContribution(BaseModel):
    component: str
    title: str
    format: ValueFormat
    baseline: float
    current: float
    rel: float | None
    contribution: float


class SegmentContribution(BaseModel):
    segment: dict[str, str]
    baseline: float | None
    current: float | None
    rel: float | None
    contribution: float
    share_of_change: float | None


class DrillReport(BaseModel):
    dims: list[str]
    total_change: float
    cells: list[SegmentContribution]
    marginals: dict[str, SegmentContribution] = Field(default_factory=dict)  # best single segment per dimension


class HypothesisOutcome(BaseModel):
    id: str
    claim: str
    test: HypothesisTest
    status: HypothesisStatus
    evidence: str


class RcaReport(BaseModel):
    metric: str
    title: str
    format: ValueFormat
    tree: str | None
    current: PeriodValue
    baseline: PeriodValue
    rel: float | None
    material: bool
    checks: list[CheckOutcome]
    decomposition: list[ComponentContribution]
    drill_metric: str
    drill: DrillReport
    hypotheses: list[HypothesisOutcome]
    queries_run: int
    sql_sample: list[str]
