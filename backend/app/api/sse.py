from __future__ import annotations

import json

from app.core.enums import EventType


class SseEncoder:
    """Server-Sent Events wire format (https://html.spec.whatwg.org/multipage/server-sent-events.html)."""

    @staticmethod
    def event(event: EventType, data: dict) -> str:
        return f"event: {event.value}\ndata: {json.dumps(data, default=str)}\n\n"

    @staticmethod
    def heartbeat() -> str:
        return ": keep-alive\n\n"  # comment line; keeps proxies and load balancers from closing an idle stream
