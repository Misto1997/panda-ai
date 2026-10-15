"""Typed, validated models for the files under `semantic/`. Invalid files fail at startup."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import CheckKind, DocKind, Direction, HypothesisTest, Movement, Scope, TimeGrain, ValueFormat


class MetricSpec(BaseModel):
    kind: Literal["metric"]
    id: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    table: str
    expr: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    unit: str = ""
    format: ValueFormat = ValueFormat.NUMBER
    direction: Direction = Direction.NEUTRAL
    dimensions: list[str] = Field(default_factory=list)
    time_grains: list[TimeGrain] = Field(default_factory=list)

    @model_validator(mode="after")
    def _expr_or_ratio(self) -> "MetricSpec":
        if bool(self.expr) == bool(self.numerator and self.denominator):
            raise ValueError(f"metric '{self.id}' needs either expr, or numerator and denominator")
        return self

    @property
    def is_ratio(self) -> bool:
        return self.numerator is not None


class DimensionSpec(BaseModel):
    kind: Literal["dimension"]
    id: str
    title: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    column: str
    tables: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    parent: str | None = None
    children: str | None = None
    hierarchy: dict[str, dict[str, str]] = Field(default_factory=dict)  # value -> {ancestor dimension: value}


class TableSpec(BaseModel):
    kind: Literal["table"]
    id: str
    title: str
    description: str = ""
    raw: str
    rollup: str
    time_column: str
    rollup_dimensions: list[str] = Field(default_factory=list)
    anchor: bool = False  # the table whose latest date defines "today"


class GlossaryTerm(BaseModel):
    term: str
    full_form: str
    definition: str


class GlossarySpec(BaseModel):
    kind: Literal["glossary"]
    id: str
    title: str
    terms: list[GlossaryTerm]


class HypothesisSpec(BaseModel):
    id: str
    claim: str
    test: HypothesisTest
    metric: str | None = None
    other_metric: str | None = None  # DIVERGENCE: the metric expected to stay stable
    dimension: str | None = None     # MIX_SHIFT: dimension whose shares are compared
    scope: Scope = Scope.OVERALL
    direction: Movement = Movement.ANY
    threshold: float
    stable_threshold: float = 0.05

    @model_validator(mode="after")
    def _required_fields(self) -> "HypothesisSpec":
        need = {HypothesisTest.METRIC_SHIFT: ["metric"], HypothesisTest.DIVERGENCE: ["metric", "other_metric"],
                HypothesisTest.MIX_SHIFT: ["metric", "dimension"], HypothesisTest.CONCENTRATION: []}[self.test]
        missing = [f for f in need if getattr(self, f) is None]
        if missing:
            raise ValueError(f"hypothesis '{self.id}' ({self.test}) is missing {missing}")
        return self


class DecompositionSpec(BaseModel):
    formula: str
    components: list[str]


class RcaTreeSpec(BaseModel):
    kind: Literal["rca_tree"]
    id: str
    title: str
    root_metric: str
    policy: str
    preflight: list[str] = Field(default_factory=list)
    decomposition: DecompositionSpec | None = None
    drill_dimensions: list[str] = Field(default_factory=list)     # jointly drilled (cells)
    marginal_dimensions: list[str] = Field(default_factory=list)  # reported one dimension at a time
    hypotheses: list[HypothesisSpec] = Field(default_factory=list)


class CheckSpec(BaseModel):
    kind: Literal["rca_check"]
    id: str
    title: str
    check: CheckKind
    description: str
    metric: str | None = None
    threshold: float | None = None


class PolicyRule(BaseModel):
    value: float
    reason: str


class PolicySpec(BaseModel):
    kind: Literal["rca_policy"]
    id: str
    title: str
    rules: dict[str, PolicyRule]

    def value(self, name: str) -> float:
        return self.rules[name].value


class Doc(BaseModel):
    """One searchable chunk of the semantic layer."""
    id: str
    kind: DocKind
    title: str
    text: str
    related: list[str] = Field(default_factory=list)  # ids pulled in with this doc (e.g. a metric's dimensions)
