"""Closed vocabularies used across layers. Strings that cross a module boundary live here."""
from enum import StrEnum


class Route(StrEnum):
    QNA = "qna"
    RCA = "rca"
    DISCOVER = "discover"
    HELP = "help"


class NodeName(StrEnum):
    ROUTE = "route"
    PLAN = "plan"
    EXECUTE = "execute"
    RESPOND = "respond"
    RCA = "rca"
    DISCOVER = "discover"
    HELP = "help"


class ResponseType(StrEnum):
    ANSWER = "answer"
    RCA = "rca"
    INFO = "info"
    ERROR = "error"


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    STEP = "step"
    RESULT = "result"
    ERROR = "error"
    RUN_FINISHED = "run_finished"


class CacheStatus(StrEnum):
    HIT = "hit"
    MISS = "miss"
    OFF = "off"


class TimeGrain(StrEnum):
    NONE = "none"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class QueryMode(StrEnum):
    AUTO = "auto"  # rollup when possible
    RAW = "raw"    # force raw fact tables


class ValueFormat(StrEnum):
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"
    DATE = "date"


class Direction(StrEnum):
    UP_IS_GOOD = "up_is_good"
    DOWN_IS_GOOD = "down_is_good"
    NEUTRAL = "neutral"


class Movement(StrEnum):
    UP = "up"
    DOWN = "down"
    ANY = "any"


class LlmProvider(StrEnum):
    MOCK = "mock"
    GEMINI = "gemini"


class ModelTier(StrEnum):
    FAST = "fast"            # routing, planning, short answers
    REASONING = "reasoning"  # RCA narrative


class LlmTask(StrEnum):
    """Used by the offline mock to know which behaviour to emulate."""
    ANSWER = "answer"
    RCA_NARRATIVE = "rca_narrative"
    DISCOVER = "discover"


class EngineKind(StrEnum):
    DUCKDB = "duckdb"
    BIGQUERY = "bigquery"


class DocKind(StrEnum):
    METRIC = "metric"
    DIMENSION = "dimension"
    GLOSSARY = "glossary"
    RCA_TREE = "rca_tree"
    RCA_CHECK = "rca_check"


class HypothesisTest(StrEnum):
    METRIC_SHIFT = "metric_shift"    # a metric moved by more than a threshold
    DIVERGENCE = "divergence"        # metric moved while another stayed stable
    CONCENTRATION = "concentration"  # one segment explains most of the change
    MIX_SHIFT = "mix_shift"          # segment shares of a metric changed


class HypothesisStatus(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class Scope(StrEnum):
    OVERALL = "overall"
    TOP_CELL = "top_cell"  # restrict to the segment with the largest contribution


class CheckKind(StrEnum):
    FRESHNESS = "freshness"
    METRIC_SHIFT = "metric_shift"


class PromptId(StrEnum):
    ROUTE = "route"
    PLAN = "plan"
    ANSWER = "answer"
    RCA_REQUEST = "rca_request"
    RCA_NARRATIVE = "rca_narrative"
    DISCOVER = "discover"
