from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Tags every log line of a request with an id and returns it, so one chat turn can be traced end to end."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get(HEADER, "")[:32] or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER] = rid
        return response
