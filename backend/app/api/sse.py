from __future__ import annotations

import json

from app.schemas.agui import AgUiEvent


class AgUiEncoder:
    """AG-UI over Server-Sent Events: one `data: <json>` line per event, no `event:` field (the JSON carries `type`)."""

    @staticmethod
    def encode(event: AgUiEvent) -> str:
        return f"data: {json.dumps(event.to_wire(), default=str, separators=(',', ':'))}\n\n"

    @staticmethod
    def heartbeat() -> str:
        return ": keep-alive\n\n"  # SSE comment; keeps proxies and load balancers from closing an idle stream
