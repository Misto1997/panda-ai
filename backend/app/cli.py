"""Run one turn in the terminal with a live trace.   python -m app.cli "why did net gmv drop?" --debug"""
from __future__ import annotations

import argparse
import json
import uuid

from app.container import build_container
from app.core.config import get_settings


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask PANDA a question from the terminal")
    ap.add_argument("question")
    ap.add_argument("--thread", default=uuid.uuid4().hex[:8])
    ap.add_argument("--raw", action="store_true", help="force raw table scan")
    ap.add_argument("--no-cache", action="store_true", help="bypass the semantic cache")
    ap.add_argument("--debug", action="store_true", help="DEBUG logs plus SQL and model payloads")
    ap.add_argument("--json", action="store_true", help="print the full result payload")
    args = ap.parse_args()

    settings = get_settings().model_copy(update={"trace_payloads": args.debug, "log_level": "DEBUG" if args.debug else "WARNING"})
    container = build_container(settings)
    try:
        final = None
        for update in container.runner.stream(args.question, args.thread, {"force_raw": args.raw, "bypass_cache": args.no_cache}):
            for s in update.steps:
                print(f"  [{s['node']:8s}] {s['step']:9s} {s['ms']:>7.1f} ms  {s['detail']}")
            final = update.response or final
        if not final:
            raise SystemExit("no result produced")
        print(f"\n[{final['type']}] {final['text']}\n")
        print("meta:", json.dumps(final.get("meta", {}), default=str))
        if args.json:
            print(json.dumps(final, indent=2, default=str))
    finally:
        container.close()


if __name__ == "__main__":
    main()
