from __future__ import annotations

import re
import time
from datetime import date
from dataclasses import dataclass

from app.agents.base import AgentNode, NodeOutput
from app.agents.contracts import SqlDraft
from app.agents.deps import NodeDependencies
from app.agents.state import TurnState
from app.core.enums import CacheStatus, DocKind, IrSource, LlmTask, NodeName, PromptId, QueryMode, QueryPath
from app.core.errors import GuardViolationError, LlmError, LlmUnavailableError, PandaError, QueryValidationError
from app.llm.base import LlmContext
from app.prompts.context import SqlPromptContext
from app.query.ir import QueryIR
from app.query.period import extract_time_expr
from app.query.service import PreparedSql

CONTEXT_DOC_KINDS = {DocKind.METRIC, DocKind.DIMENSION, DocKind.GLOSSARY}
CONTEXT_DOCS = 8
EXAMPLE_DOCS = 4
EXAMPLE_PREFIX = "example:"
ALL_TIME_START = date(2000, 1, 1)  # the normaliser's stand-in when a query has no date range
COMPARISON = re.compile(r"\b(vs|versus|compare|compared|comparison|previous|prior|than|growth|change|wow|mom|dod|yoy|against)\b")
DECLINED = "That question cannot be answered with the available metrics. Ask about Net GMV, orders, ASP, visits or conversion."


@dataclass
class _Generated:
    prepared: PreparedSql
    draft: SqlDraft
    attempts: int
    bytes_processed: int | None


class SqlPlannerNode(AgentNode):
    """Retrieve governed context -> LLM writes SQL over logical tables -> guard -> engine dry-run -> repair (bounded).
    If generation still fails, falls back to a QueryIR filled by the LLM and compiled by code. Plan-layer cache skips the LLM."""
    name = NodeName.PLAN

    def __init__(self, deps: NodeDependencies) -> None:
        super().__init__(deps)
        svc = deps.query_service
        self._svc = svc
        self._prompt_ctx = SqlPromptContext(deps.catalog, svc.schema, svc.resolver)

    def run(self, state: TurnState) -> NodeOutput:
        started, question = time.perf_counter(), state["question"]
        options = state.get("options", {})
        use_cache = not options.get("bypass_cache")
        mode = QueryMode.RAW if options.get("force_raw") else QueryMode.AUTO
        last_sql, last_ir = state.get("last_sql"), state.get("last_ir")
        key = self.deps.cache.plan_key(question, f"{self._anchor()}|{last_sql or ''}")  # plans hold explicit dates: never reuse them across data refreshes

        if use_cache and (hit := self.deps.cache.get_plan(key)) and (out := self._from_cache(hit, mode, started)):
            return out

        docs, examples = self._retrieve(question, last_ir)
        doc_ids = [d.id for d in docs]
        steps = [self.step(f"{self.deps.search.backend_name}: {', '.join(doc_ids[:6])} +{len(examples)} examples", name="retrieve")]
        generated, attempts = self._generate(question, docs, examples, last_sql, last_ir, mode) if self.deps.settings.text_to_sql else (None, 0)

        if generated:
            intent = generated.prepared.intent
            ir = intent.ir.model_dump(mode="json") if intent.ir else None
            update = {"sql": generated.prepared.logical_sql, "ir": ir, "ir_source": IrSource.SQL.value, "docs": doc_ids,
                      "path": QueryPath.TEXT_TO_SQL.value, "sql_attempts": generated.attempts,
                      "rationale": generated.draft.rationale, "confidence": generated.draft.confidence.value,
                      "bytes_processed": generated.bytes_processed}
            if use_cache:
                self.deps.cache.put_plan(key, {"sql": update["sql"], "ir": ir, "docs": doc_ids, "rationale": update["rationale"],
                                               "confidence": update["confidence"]})
            steps.append(self.step(f"sql ok after {generated.attempts} attempt(s): {intent.describe()}", started, name="plan"))
            return NodeOutput(update, steps)

        ir = self._ir_fallback(question, docs, last_ir)
        update = {"sql": None, "ir": ir.model_dump(mode="json"), "ir_source": IrSource.LLM.value, "docs": doc_ids,
                  "path": QueryPath.IR_FALLBACK.value, "sql_attempts": attempts}
        if use_cache and ir.metrics:  # never cache a failed plan
            self.deps.cache.put_plan(key, {"sql": None, "ir": update["ir"], "docs": doc_ids})
        steps.append(self.step(f"ir fallback: metrics={ir.metrics} dims={ir.dimensions} time={ir.time_expr}", started, name="plan"))
        return NodeOutput(update, steps)

    def _anchor(self) -> str:
        try:
            return str(self._svc.anchor)
        except PandaError:
            return ""

    def _check_period(self, question: str, prepared: PreparedSql) -> None:
        """The model must not invent dates: if the question names a period, the SQL has to cover exactly that period."""
        if not self.deps.settings.enforce_time_guard or COMPARISON.search(question.lower()) or prepared.intent.period is None:
            return
        expr = extract_time_expr(question)
        if expr is None:
            return
        want = self._svc.resolver.resolve(expr)
        got = prepared.intent.period
        if got.start == ALL_TIME_START and expr != "all_time":
            return  # the normaliser found no date predicate it understands (for example `= DATE '...'`): nothing reliable to compare
        if got != want:
            raise GuardViolationError(
                f"Period mismatch: the question asks for '{expr}', which is {want.start} to {want.last_day} inclusive, i.e. "
                f">= DATE '{want.start}' AND < DATE '{want.end}'. Your SQL covers {got.start} to {got.last_day}. "
                f"Use the dates from the named-period list; data ends {self._svc.anchor}.")

    # ---- cache ----
    def _from_cache(self, hit: dict, mode: QueryMode, started: float) -> NodeOutput | None:
        if hit.get("sql"):
            try:  # the semantic layer or guard may have changed since the entry was written
                self._svc.prepare_sql(hit["sql"], mode)
            except GuardViolationError:
                return None
        update = {"sql": hit.get("sql"), "ir": hit.get("ir"), "docs": hit.get("docs", []), "ir_source": IrSource.CACHE.value,
                  "path": QueryPath.CACHE.value, "sql_attempts": 0, "rationale": hit.get("rationale"), "confidence": hit.get("confidence")}
        return NodeOutput(update, [self.step("plan from semantic cache (LLM skipped)", started, name="plan", cache=CacheStatus.HIT)])

    # ---- retrieval ----
    def _retrieve(self, question: str, last_ir: dict | None):
        query = f"{question} {' '.join((last_ir or {}).get('metrics', []))}".strip()  # follow-ups borrow the previous metrics
        docs = self.deps.search.search(query, CONTEXT_DOCS, CONTEXT_DOC_KINDS)
        examples = [d.id.removeprefix(EXAMPLE_PREFIX) for d in self.deps.search.search(question, EXAMPLE_DOCS, {DocKind.EXAMPLE})]
        return docs, examples

    # ---- text-to-sql ----
    def _generate(self, question, docs, examples, last_sql, last_ir, mode: QueryMode) -> tuple[_Generated | None, int]:
        """Returns the accepted SQL (or None) and the number of model calls spent. The turn-wide LLM budget caps runaway loops."""
        variables = self._prompt_ctx.variables(docs, examples, last_sql, last_ir)
        prompt = self.deps.prompts.render(PromptId.SQL_GENERATE, question=question, **variables)
        task, error, previous = LlmTask.SQL_GENERATE, None, None
        max_attempts = 1 + self.deps.settings.sql_max_repairs
        for attempt in range(1, max_attempts + 1):
            ctx = LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=last_ir, task=task,
                             payload={"sql": previous, "error": error}, render_sql=self._render)
            try:
                draft = self.deps.llm.structured(SqlDraft, prompt, ctx)
            except LlmUnavailableError:
                raise  # the model service itself is failing: a fallback call would fail the same way, tell the user
            except LlmError as e:  # unparseable model output: the deterministic IR fallback may still answer
                self.log.warning("sql generation output unusable: %s", e)
                return None, attempt - 1
            if not draft.sql.strip():  # the model declined: not a failure to repair
                raise QueryValidationError(draft.rationale or DECLINED)
            try:
                prepared = self._svc.prepare_sql(draft.sql, mode)
                self._check_period(question, prepared)
                info = self._svc.dry_run(prepared)
                if not info.ok:
                    raise GuardViolationError(f"The engine rejected the query: {info.error}")
                return _Generated(prepared, draft, attempt, info.bytes_processed), attempt
            except GuardViolationError as e:
                error, previous = e.message, draft.sql
                self.log.info("sql attempt %d rejected: %s", attempt, error)
            task = LlmTask.SQL_REPAIR
            prompt = self.deps.prompts.render(PromptId.SQL_REPAIR, question=question, sql=draft.sql, error=error, **variables)
        return None, max_attempts

    def _render(self, ir: dict) -> str:
        return self._svc.renderer.render(QueryIR.model_validate(ir))

    # ---- deterministic fallback ----
    def _ir_fallback(self, question: str, docs, last_ir: dict | None) -> QueryIR:
        context = "\n".join(f"[{d.kind.value}] {d.id}: {d.text}" for d in docs)
        prompt = self.deps.prompts.render(PromptId.PLAN, question=question, context=context, last_intent=last_ir)
        return self.deps.llm.structured(QueryIR, prompt, LlmContext(question=question, vocabulary=self.deps.vocabulary, last_intent=last_ir))
