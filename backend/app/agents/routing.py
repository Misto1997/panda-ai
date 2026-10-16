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
DATA_TOKENS = re.compile(r"\b(by|per|each|last|past|previous|yesterday|today|this (week|month|quarter)|trend|top|bottom|compare|versus|vs|daily|weekly|"
                         r"monthly|how many|how much|total|average|number of|count|breakdown|split|between|during|for the)\b")


class RuleRouter:
    def __init__(self, vocabulary: Vocabulary) -> None:
        names = {n.lower().replace("_", " ") for t in (*vocabulary.metrics, *vocabulary.dimensions) for n in t.names}
        values = {v.lower() for t in vocabulary.dimensions for v in t.values}
        self._names = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")s?\b") if names else None
        self._values = re.compile(r"\b(" + "|".join(sorted(map(re.escape, values), key=len, reverse=True)) + r")\b") if values else None

    def route(self, question: str) -> Route | None:
        """None means 'ambiguous': let the model decide."""
        q = " ".join(question.lower().split())
        if HELP.search(q):
            return Route.HELP
        if RCA.search(q):
            return Route.RCA
        value_mentioned = bool(self._values and self._values.search(q))
        if DISCOVER_START.search(q) and not DATA_TOKENS.search(q) and not value_mentioned:
            return Route.DISCOVER
        if DATA_TOKENS.search(q) or value_mentioned or (self._names and self._names.search(q)):
            return Route.QNA
        return None
