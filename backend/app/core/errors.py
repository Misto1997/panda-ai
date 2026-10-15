"""Exception hierarchy. `user_facing` errors are safe to show to end users verbatim;
anything else is logged and replaced by a generic message at the API boundary."""
from __future__ import annotations


class PandaError(Exception):
    code = "internal_error"
    user_facing = False

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class QueryValidationError(PandaError):
    """The question cannot be answered with the governed semantic layer (unknown metric, invalid slice...)."""
    code = "invalid_query"
    user_facing = True


class GuardViolationError(PandaError):
    code = "guard_violation"
    user_facing = True


class EngineError(PandaError):
    code = "engine_error"


class QueryTimeoutError(EngineError):
    code = "query_timeout"
    user_facing = True


class LlmError(PandaError):
    code = "llm_error"


class CatalogError(PandaError):
    """Semantic layer files are invalid. Raised at startup so bad files never reach users."""
    code = "catalog_error"


class ConfigurationError(PandaError):
    code = "configuration_error"


class UnsupportedTimeExpressionError(QueryValidationError):
    code = "unsupported_time_expression"
