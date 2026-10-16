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

_SQL_RULES = (
    "You write ONE read-only SQL query that answers a business question from a governed analytics warehouse.\n"
    "Return JSON {sql, rationale, confidence}. If the question cannot be answered with the schema and metrics below, "
    "return an empty sql and explain why in rationale.\n"
    "Logical tables (write SQL against these only; physical rollup/raw tables are chosen for you):\n$schema\n"
    "Rules:\n"
    "- Use only the logical tables and columns listed. Never use SELECT *, table functions, files or other schemas.\n"
    "- Measure columns are additive and must appear only inside SUM(). Never AVG, MIN, MAX or COUNT a measure; never COUNT(*). "
    "Count orders with SUM(orders).\n"
    "- Ratio metrics are a ratio of sums: SUM(a) / NULLIF(SUM(b), 0). Never average a ratio. Follow the governed metric definitions below exactly.\n"
    "- Alias every metric with its metric id (for example SUM(net_gmv) AS net_gmv) and keep dimension column names unchanged.\n"
    "- Filter time with explicit half-open date predicates: order_date >= DATE 'YYYY-MM-DD' AND order_date < DATE 'YYYY-MM-DD' "
    "(visit_date for traffic and bu_traffic). Time series: DATE_TRUNC('day'|'week'|'month', <time column>) AS date.\n"
    "- Dimension values are case-sensitive strings from the lists below. Values of a dimension are filters, not columns.\n"
    "- To combine metrics from different tables, aggregate each in its own CTE and join the CTEs on the shared dimension columns "
    "(qualify columns with the CTE name). Visits are not split by business unit.\n"
    "- Period-over-period: one CTE per period, join on the dimensions. Top-N: ORDER BY the metric DESC LIMIT N. Default period: last 30 days.\n"
    "- If the question is a follow-up, start from the previous SQL and change only what the user asks.\n"
    "Data is available through $anchor (the latest full day). Named periods as half-open [start, end):\n$periods\n"
    "Governed context for this question:\n$context\n"
    "Examples (valid for this schema):\n$examples\n"
    "Previous SQL (null if none): $last_sql\n"
    "Previous intent (null if none): $last_intent")

PROMPTS_SQL = [
    PromptTemplate(id=PromptId.SQL_GENERATE, owner=NodeName.PLAN, system=_SQL_RULES),
    PromptTemplate(
        id=PromptId.SQL_REPAIR, owner=NodeName.PLAN,
        system=_SQL_RULES + "\nYour previous attempt was rejected. Fix exactly the problem reported and return the corrected JSON.",
        user="Question: $question\nRejected SQL:\n$sql\nProblem:\n$error"),
]


PROMPTS = PromptRegistry([*PROMPTS_SQL,
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
        user="Question: $question\nColumns: $columns\nValue formats (a percent value is a fraction: 0.034 means 3.4%): $formats\nRows (max 15): $rows"),
    PromptTemplate(
        id=PromptId.RCA_REQUEST, owner=NodeName.RCA,
        system=("Pick the metric whose movement the user wants explained and the period to analyse.\n"
                "Use ONLY one of these metric ids: $metric_ids.\n"
                "time_expr must be one of: $time_grammar. Default is last_14_days.\n$context")),
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
