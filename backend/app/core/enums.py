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
    """AG-UI event types (https://docs.ag-ui.com/concepts/events). Wire values are SCREAMING_SNAKE."""
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    ACTIVITY_SNAPSHOT = "ACTIVITY_SNAPSHOT"
    CUSTOM = "CUSTOM"


class CustomEventName(StrEnum):
    """Names of AG-UI CUSTOM events emitted by the gateway."""
    STEP = "panda.step"      # one trace step: node, step, detail, ms, cache
    RESULT = "panda.result"  # the full ChatResult payload


class ActivityType(StrEnum):
    A2UI_SURFACE = "a2ui-surface"  # content = list of A2UI messages


class MessageRole(StrEnum):
    ASSISTANT = "assistant"


class RunOutcome(StrEnum):
    SUCCESS = "success"


class ErrorCode(StrEnum):
    INTERNAL = "internal_error"
    EMPTY_RESULT = "empty_result"


class A2uiMessage(StrEnum):
    """Top-level keys of A2UI v0.9 server-to-client messages."""
    CREATE_SURFACE = "createSurface"
    UPDATE_COMPONENTS = "updateComponents"
    UPDATE_DATA_MODEL = "updateDataModel"
    DELETE_SURFACE = "deleteSurface"


class A2uiComponent(StrEnum):
    """Components of the PANDA A2UI catalog (presentation/a2ui_catalog.json)."""
    COLUMN = "Column"
    TEXT = "Text"
    KPI_ROW = "KpiRow"
    VEGA_LITE_CHART = "VegaLiteChart"
    DATA_TABLE = "DataTable"
    HYPOTHESIS_LIST = "HypothesisList"
    DECOMPOSITION_TABLE = "DecompositionTable"
    SEGMENT_BARS = "SegmentBars"
    CHIP_ROW = "ChipRow"
    SQL_BLOCK = "SqlBlock"


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
    SQL_GENERATE = "sql_generate"
    SQL_REPAIR = "sql_repair"


class EngineKind(StrEnum):
    DUCKDB = "duckdb"
    BIGQUERY = "bigquery"


class DocKind(StrEnum):
    METRIC = "metric"
    DIMENSION = "dimension"
    GLOSSARY = "glossary"
    RCA_TREE = "rca_tree"
    RCA_CHECK = "rca_check"
    EXAMPLE = "example"


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
    SQL_GENERATE = "sql_generate"
    SQL_REPAIR = "sql_repair"


class QueryPath(StrEnum):
    """How the executed SQL was produced."""
    TEXT_TO_SQL = "text_to_sql"  # LLM-written logical SQL, guarded and rewritten
    IR_FALLBACK = "ir_fallback"  # generation failed after repairs; QueryIR compiled deterministically
    CACHE = "cache"              # plan layer hit: no LLM call


class IrSource(StrEnum):
    """Where the turn's QueryIR came from."""
    SQL = "sql"      # normalised from generated SQL
    LLM = "llm"      # filled by the LLM (fallback path)
    CACHE = "cache"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuthMode(StrEnum):
    DEV = "dev"            # fixed local user, no token needed
    FIREBASE = "firebase"  # Firebase ID token required on every chat turn


class VectorIndexKind(StrEnum):
    NONE = "none"  # exact scan; right for a few dozen documents
    HNSW = "hnsw"  # pgvector (Cloud SQL and AlloyDB)
    SCANN = "scann"  # AlloyDB only (alloydb_scann extension)


class BootstrapStep(StrEnum):
    DATA = "data"
    INDEX = "index"
    WARM = "warm"


class CacheLayer(StrEnum):
    PLAN = "plan"      # normalised question -> generated SQL + intent
    RESULT = "result"  # canonical intent -> result set
