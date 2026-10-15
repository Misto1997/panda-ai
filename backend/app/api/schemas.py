from pydantic import BaseModel


class MetricInfo(BaseModel):
    id: str
    title: str
    description: str


class RuntimeInfo(BaseModel):
    llm: str
    engine: str
    search: str
    anchor: str
    tables: dict[str, int]
    metrics: list[MetricInfo]
    suggestions: list[str]
    cache: dict[str, int]


class HealthStatus(BaseModel):
    status: str
