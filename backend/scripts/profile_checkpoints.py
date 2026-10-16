"""How much conversation state does each turn persist? Runs turns on one thread with the in-memory checkpointer and measures the
serialised bytes LangGraph would write to Postgres (checkpoints + blobs + writes).   python scripts/profile_checkpoints.py"""
from __future__ import annotations

import uuid

from app.container import build_container
from app.core.config import get_settings

QUESTIONS = ["Net GMV by zone for the last 7 days", "and by marketplace?", "Daily visits by marketplace last 14 days",
             "Net GMV by city daily last 90 days", "Why did Net GMV drop in the last 14 days?", "what about visits?"]


def size_of(saver) -> dict[str, int]:
    def blob(x):
        return sum(len(p) for p in x if isinstance(p, (bytes, bytearray)))
    storage = sum(blob(v[0:1]) + blob(v[1:2]) if isinstance(v, tuple) else 0 for ns in saver.storage.values() for cps in ns.values() for v in cps.values())
    blobs = sum(blob(v) for v in saver.blobs.values())
    writes = sum(blob(w) for per in saver.writes.values() for w in per.values())
    return {"checkpoints": storage, "blobs": blobs, "writes": writes}


def main() -> None:
    c = build_container(get_settings().model_copy(update={"log_level": "WARNING"}))
    saver = c.runner._graph.checkpointer
    thread, prev = f"prof-{uuid.uuid4().hex[:6]}", 0
    print(f"{'turn':>4s} {'checkpoint rows':>16s} {'total KB':>9s} {'added KB':>9s}  question")
    for i, q in enumerate(QUESTIONS, 1):
        rows = None
        for u in c.runner.stream(q, thread, {"force_raw": False, "bypass_cache": True}):
            if u.response and u.response.get("table"):
                rows = len(u.response["table"]["rows"])
        s = size_of(saver)
        total = sum(s.values())
        n_cp = sum(len(cps) for ns in saver.storage.values() for cps in ns.values())
        print(f"{i:4d} {n_cp:16d} {total / 1024:9.1f} {(total - prev) / 1024:9.1f}  {q} (result rows: {rows})")
        prev = total
    print("\nkeys persisted in the final state:", sorted(k for k in c.runner._graph.get_state({'configurable': {'thread_id': thread}}).values))
    c.close()


if __name__ == "__main__":
    main()
