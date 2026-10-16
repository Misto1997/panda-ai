"""Exception hierarchy. `user_facing` errors are safe to show to end users verbatim;
anything else is logged and replaced by a generic message at the API boundary."""
from __future__ import annotations


class PandaError(Exception):
    code = "internal_error"
    user_facing = False
    http_status: int | None = None  # overrides the default 400 (user facing) / 500 mapping at the API boundary

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


class DatabaseUnavailableError(PandaError):
    code = "database_unavailable"
    http_status = 503


class QueryTooExpensiveError(EngineError):
    """The engine refused a query because it would scan more than the configured byte cap."""
    code = "query_too_expensive"
    user_facing = True


class LlmBudgetExceededError(PandaError):
    code = "llm_budget_exceeded"
    user_facing = True


class AuthenticationError(PandaError):
    code = "unauthenticated"
    user_facing = True
    http_status = 401


class QuotaExceededError(PandaError):
    code = "quota_exceeded"
    user_facing = True
    http_status = 429


class RateLimitedError(PandaError):
    code = "rate_limited"
    user_facing = True
    http_status = 429


class RequestTooLargeError(PandaError):
    code = "request_too_large"
    user_facing = True
    http_status = 413
