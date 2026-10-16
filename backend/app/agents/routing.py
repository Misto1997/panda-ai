"""Deterministic intent routing. The common cases need no model call (a call is seconds, and each one is exposed to quota stalls);
the model router only sees questions these rules cannot place."""
from __future__ import annotations

import re

from app.core.enums import Route
from app.llm.base import Vocabulary

HELP = re.compile(r"^\s*(hi|hello|hey|help|thanks|thank you|good (morning|afternoon|evening))\b[\s!.,?]*$"
                  r"|\b(what can you do|how do i use|how does this work|what do you do|who are you)\b")
RCA = re.compile(r"\b(why|root[ -]cause|what caused|what happened|what drove|what'?s driving|reasons? for|investigate|"
                 r"explain the (drop|decline|dip|fall|increase|rise|spike|change))\b")
DISCOVER_START = re.compile(r"^\s*(what is|what'?s|what are|what does|define|definition of|meaning of|explain|how is|how are|which metrics|what metrics|"
                            r"what dimensions|list( the| all)?( available)? (metrics|dimensions)|show( me)?( the)?( available)? (metrics|dimensions))\b")
OFF_TOPIC = re.compile(r"\b(poem|poetry|joke|riddle|song|lyrics|recipe|horoscope|weather|movie|cricket score|football|translate|bitcoin|crypto|"
                       r"capital of|write (me )?(a |an |some )?(code|script|essay|story|email|program))\b")
INJECTION = re.compile(r"\b(ignore (all |your |the )?(previous|prior|above) |system prompt|jailbreak|pretend (to be|you are)|act as)\b")
SQL_CUE = re.compile(r"\b(show|give|display|print|share|see|view)\b.*\b(sql|quer(y|ies))\b|\bwhat(\'s| is| was) the (sql|query)\b|\b(sql|quer(y|ies)) (you|did you|was|were) (used|ran|run|fired|generated|wrote)\b")
RANGE_CUE = re.compile(r"\b(till|until|up ?to|through|upto) (when|what date|which date|how long|what day)\b|\bhow (far back|recent|fresh|up[- ]to[- ]date|old)\b|"
                       r"\bdata (is |are )?(available |loaded )?(till|until|through|upto|up to)\b|\b(latest|earliest|first available|last available|most recent) (date|day)s?\b|"
                       r"\b(data|dataset) (range|coverage|freshness|history|window)\b|\bwhen (was|is) (the )?data (last )?(updated|refreshed|loaded)\b|"
                       r"\bwhat (dates|period|time ?frame|date range) (do you have|is available|are available|does the data cover|is covered)\b|\bhow (much|many days of) (history|data)\b|"
                       r"\b(from|since) when\b.*\bdata\b|\bdata\b.*\b(from|since) when\b")
HOW_CUE = re.compile(r"\b(which|what) (filters?|period|date range|dates?|tables?|source|data source) (did|was|were|are|do) (you|this|that|it)\b|"
                     r"\bhow (did|do) you (get|calculate|compute|derive|arrive|work (this|that) out)\b|\bwhere (did|does) (this|that|the) (number|data|figure|value)s? come from\b")
FOLLOW_UP = re.compile(r"\b(it|that|this|those|these|them|there|again)\b|^\s*why\s*[?!. ]*$")  # a bare "why" or a pronoun refers to the previous turn
DATA_TOKENS = re.compile(r"\b(by|per|each|last|past|previous|yesterday|today|this (week|month|quarter)|trend|top|bottom|compare|versus|vs|daily|weekly|"
                         r"monthly|how many|how much|total|average|number of|count|breakdown|split|between|during|for the)\b")


def meta_kind(q: str) -> str | None:
    """'sql' | 'range' | 'how' for questions about the previous answer or the data coverage, else None. `q` is lower-cased."""
    if RANGE_CUE.search(q):
        return "range"
    if HOW_CUE.search(q):
        return "how"
    if SQL_CUE.search(q):
        return "sql"
    return None


class RuleRouter:
    def __init__(self, vocabulary: Vocabulary) -> None:
        names = {n.lower().replace("_", " ") for t in (*vocabulary.metrics, *vocabulary.dimensions) for n in t.names}
        values = {v.lower() for t in vocabulary.dimensions for v in t.values}
        self._names = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")s?\b") if names else None
        self._values = re.compile(r"\b(" + "|".join(sorted(map(re.escape, values), key=len, reverse=True)) + r")\b") if values else None

    def route(self, question: str, has_context: bool = False) -> Route | None:
        """None means 'ambiguous': let the model decide. `has_context` is True when an earlier turn left a query to follow up on."""
        q = " ".join(question.lower().split())
        if HELP.search(q):
            return Route.HELP
        value_mentioned = bool(self._values and self._values.search(q))
        name_mentioned = bool(self._names and self._names.search(q))
        kind = meta_kind(q)
        about_data = bool(re.search(r"\bdata(set)?\b", q))
        if kind and ((value_mentioned or name_mentioned) is False or (kind == "range" and about_data)):
            return Route.META  # "show me the sql", "till when do you have data": answered from saved facts, no query, no model
        if INJECTION.search(q) or (OFF_TOPIC.search(q) and not (value_mentioned or name_mentioned)):  # instruction tampering is refused even next to a metric name
            return Route.OFF_TOPIC
        if RCA.search(q):
            # "why ..." needs something to explain: a known metric/dimension, or a previous turn. Otherwise let the model decide.
            return Route.RCA if (value_mentioned or name_mentioned or (has_context and FOLLOW_UP.search(q))) else None
        if DISCOVER_START.search(q) and not DATA_TOKENS.search(q) and not value_mentioned:
            return Route.DISCOVER
        if DATA_TOKENS.search(q) or value_mentioned or name_mentioned:
            return Route.QNA
        return None
