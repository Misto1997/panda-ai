"""The single register of every prompt in the system. Each prompt names the agent node that owns it.
Placeholders use $name; a missing variable raises instead of silently sending a broken prompt."""
from __future__ import annotations

from dataclasses import dataclass
from string import Template

from app.core.enums import NodeName, PromptId
from app.core.errors import LlmError
from app.llm.base import Prompt


@dataclass(frozen=True)
class PromptTemplate:
    id: PromptId
    owner: NodeName
    system: str
    user: str = "$question"

    def render(self, **variables: object) -> Prompt:
        try:
            return Prompt(Template(self.system).substitute(variables), Template(self.user).substitute(variables))
        except KeyError as e:
            raise LlmError(f"prompt '{self.id}' is missing variable {e}") from e


class PromptRegistry:
    def __init__(self, templates: list[PromptTemplate]) -> None:
        self._by_id = {t.id: t for t in templates}
        if len(self._by_id) != len(templates):
            raise ValueError("duplicate prompt id")

    def get(self, prompt_id: PromptId) -> PromptTemplate:
        return self._by_id[prompt_id]

    def render(self, prompt_id: PromptId, **variables: object) -> Prompt:
        return self.get(prompt_id).render(**variables)

    def all(self) -> list[PromptTemplate]:
        return list(self._by_id.values())


PROMPTS = PromptRegistry([
    PromptTemplate(
        id=PromptId.ROUTE, owner=NodeName.ROUTE,
        system=("Classify the user's analytics request into exactly one route.\n"
                "qna: a data question answerable with metrics (values, trends, breakdowns, comparisons).\n"
                "rca: asks WHY a metric moved or what caused a change.\n"
                "discover: asks what a metric or term means, or what metrics/dimensions exist.\n"
                "help: greetings or questions about how to use the product.")),
    PromptTemplate(
        id=PromptId.PLAN, owner=NodeName.PLAN,
        system=("You translate business questions into a structured query intent (QueryIR) for an analytics semantic layer.\n"
                "Rules:\n"
                "- Use ONLY metric and dimension ids that appear in the context. Never invent ids.\n"
                "- Values of a dimension (for example a zone, state, marketplace or business unit name) become filters, not dimensions.\n"
                "- 'by X' or 'per X' means group by X. Set grain only for trends over time.\n"
                "- If the question is a follow-up, modify the previous intent instead of starting over.\n"
                "- Default time_expr is last_30_days. Do not write SQL.\n"
                "Semantic layer context:\n$context\n"
                "Previous intent (may be null): $last_intent")),
    PromptTemplate(
        id=PromptId.ANSWER, owner=NodeName.RESPOND,
        system="You are a data analyst. Answer in 1-3 sentences using only the numbers provided. Bold the key figures. Do not invent numbers.",
        user="Question: $question\nColumns: $columns\nRows (max 15): $rows"),
    PromptTemplate(
        id=PromptId.RCA_REQUEST, owner=NodeName.RCA,
        system=("Pick the metric whose movement the user wants explained and the period to analyse.\n"
                "Use only metric ids from the context. Default period is last_14_days.\n$context")),
    PromptTemplate(
        id=PromptId.RCA_NARRATIVE, owner=NodeName.RCA,
        system=("You are a senior analyst writing a root-cause summary for an executive. Use 4-6 sentences.\n"
                "State the movement, the main driver and segment, each confirmed hypothesis with its evidence, your confidence, "
                "and one recommended next step. Use ONLY facts from the JSON. Do not speculate beyond confirmed hypotheses. "
                "If no hypothesis is confirmed, say the cause is not established."),
        user="Facts JSON:\n$facts"),
    PromptTemplate(
        id=PromptId.DISCOVER, owner=NodeName.DISCOVER,
        system="Answer using only the semantic layer context. Be concise and cite metric ids in backticks. If the context does not cover it, say so.",
        user="Question: $question\nContext:\n$context"),
])
