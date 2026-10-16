"""Golden benchmark: runs each question through the full graph and compares the result set with an independently written
ground-truth SQL against the PHYSICAL tables (raw facts, so rollups are checked too).

    python -m app.bench [--file F] [--category C] [--cache] [--json OUT] [-v]

Prints accuracy per category, latency and the path taken (text_to_sql / ir_fallback / cache). With LLM_PROVIDER=mock, items marked
`xfail_mock` in the golden file are expected to fail and are reported separately instead of as regressions."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from app.container import Container, build_container
from app.core.config import ROOT, get_settings
from app.core.enums import LlmProvider, ResponseType

GOLDEN = ROOT / "backend" / "tests" / "golden" / "golden.yaml"
REL_TOL, ABS_TOL = 1e-6, 1e-9
SORT_DIGITS = 4  # significant digits used only to order rows before comparing with the real tolerance


@dataclass
class Outcome:
    id: str
    category: str
    passed: bool
    path: str | None
    latency_ms: float
    detail: str = ""
    expected_fail: str | None = None  # reason, when the item is known not to pass on this LLM


def _cell(value):
    if value is None:
        return (2, 0, "")
    if isinstance(value, bool):
        return (1, 0, str(value))
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    return (1, 0, str(value))


def _row(row: list) -> list[tuple]:
    return sorted((_cell(v) for v in row), key=lambda c: (c[0], c[1], c[2]))


def _sort_key(row: list[tuple]):
    return [(c[0], float(f"{c[1]:.{SORT_DIGITS}g}"), c[2]) for c in row]


def compare_rows(actual: list[list], expected: list[list]) -> tuple[bool, str]:
    """Order- and column-name-insensitive comparison of two result sets with a numeric tolerance."""
    if len(actual) != len(expected):
        return False, f"row count {len(actual)} != expected {len(expected)}"
    a, e = sorted((_row(r) for r in actual), key=_sort_key), sorted((_row(r) for r in expected), key=_sort_key)
    for i, (ra, re_) in enumerate(zip(a, e)):
        if len(ra) != len(re_):
            return False, f"column count {len(ra)} != expected {len(re_)}"
        for ca, ce in zip(ra, re_):
            same_number = ca[0] == ce[0] == 0 and math.isclose(ca[1], ce[1], rel_tol=REL_TOL, abs_tol=ABS_TOL)
            if not (same_number or (ca[0] != 0 and ca == ce)):
                return False, f"row {i}: got {ca[1] if ca[0] == 0 else ca[2]!r}, expected {ce[1] if ce[0] == 0 else ce[2]!r}"
    return True, ""


def load_items(path: Path = GOLDEN) -> dict:
    return yaml.safe_load(path.read_text())


ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CALENDAR = re.compile(r"\b(week|month|mtd|quarter|year)\b", re.I)  # calendar-aligned periods do not survive a shift by N days


def _shift(text: str, days: int) -> str:
    return ISO_DATE.sub(lambda m: str(date.fromisoformat(m.group()) + timedelta(days=days)), text)


def rebase(item: dict, days: int) -> dict | None:
    """Moves a golden item to a data window that ends `days` later (the nightly roll-forward). Items whose period is calendar-aligned
    (last week, this month...) cannot be shifted faithfully and return None."""
    if any(CALENDAR.search(t) for t in item["turns"]):
        return None
    return {**item, "turns": [_shift(t, days) for t in item["turns"]], "sql": _shift(item["sql"], days)}


def run_item(container: Container, item: dict, use_cache: bool) -> Outcome:
    thread, final, latency = f"bench-{item['id']}", None, 0.0
    for question in item["turns"]:
        started = time.perf_counter()
        for update in container.runner.stream(question, thread, {"bypass_cache": not use_cache}):
            final = update.response or final
        latency = (time.perf_counter() - started) * 1000
    reason = item.get("xfail_mock") if container.llm.name == LlmProvider.MOCK.value else None
    path = (final or {}).get("meta", {}).get("path")
    if not final or final["type"] != ResponseType.ANSWER:
        return Outcome(item["id"], item["category"], False, path, latency, f"no answer: {(final or {}).get('text', 'no result')[:120]}", reason)
    expected = container.engine.run(item["sql"], container.settings.query_timeout_s)
    ok, detail = compare_rows(final["table"]["rows"], expected.rows)
    return Outcome(item["id"], item["category"], ok, path, latency, detail, reason)


def run_bench(container: Container, categories: set[str] | None = None, use_cache: bool = False, path: Path = GOLDEN,
              follow_anchor: bool = False) -> list[Outcome]:
    """`follow_anchor` is for a deployment whose data rolls forward: golden dates are shifted to the live data window and calendar-aligned items are skipped."""
    golden = load_items(path)
    delta = (container.query_service.anchor - date.fromisoformat(golden["anchor"])).days
    if delta and not follow_anchor:
        raise SystemExit(f"dataset anchor {container.query_service.anchor} != golden anchor {golden['anchor']}: regenerate data with `make data` (or pass --follow-anchor)")
    items = [i for i in golden["items"] if not categories or i["category"] in categories]
    if follow_anchor:
        items = [r for r in (rebase(i, delta) for i in items) if r]
    return [run_item(container, i, use_cache) for i in items]


def summarize(outcomes: list[Outcome]) -> dict:
    by_cat: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        by_cat[o.category].append(o)
    lat = sorted(o.latency_ms for o in outcomes) or [0.0]
    return {
        "total": len(outcomes), "passed": sum(o.passed for o in outcomes),
        "unexpected_failures": [o.id for o in outcomes if not o.passed and not o.expected_fail],
        "unexpected_passes": [o.id for o in outcomes if o.passed and o.expected_fail],
        "by_category": {c: {"passed": sum(o.passed for o in os), "total": len(os), "expected_fail": sum(1 for o in os if o.expected_fail)}
                        for c, os in by_cat.items()},
        "paths": dict(Counter(o.path or "none" for o in outcomes)),
        "latency_ms": {"p50": round(statistics.median(lat), 1), "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1)},
    }


def render(outcomes: list[Outcome], summary: dict, verbose: bool) -> str:
    lines = [f"{'category':20s}{'pass':>6s}{'total':>7s}{'acc':>8s}  expected-fail"]
    for cat, s in summary["by_category"].items():
        lines.append(f"{cat:20s}{s['passed']:>6d}{s['total']:>7d}{s['passed'] / s['total']:>8.0%}  {s['expected_fail'] or ''}")
    lines.append(f"{'ALL':20s}{summary['passed']:>6d}{summary['total']:>7d}{summary['passed'] / max(1, summary['total']):>8.0%}")
    lines.append(f"paths: {summary['paths']}   latency p50={summary['latency_ms']['p50']} ms p95={summary['latency_ms']['p95']} ms")
    for o in outcomes:
        if verbose or (not o.passed and not o.expected_fail):
            mark = "ok  " if o.passed else ("xfail" if o.expected_fail else "FAIL")
            lines.append(f"  {mark:5s} {o.id:14s} {o.path or '-':12s} {o.latency_ms:8.1f} ms  {o.detail or o.expected_fail or ''}")
    if summary["unexpected_passes"]:
        lines.append(f"unexpected passes (remove their xfail_mock): {summary['unexpected_passes']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the golden question benchmark through the full PANDA graph")
    ap.add_argument("--file", type=Path, default=GOLDEN)
    ap.add_argument("--category", action="append", help="only this category (repeatable)")
    ap.add_argument("--cache", action="store_true", help="allow the semantic cache (default: bypass, so latency is real)")
    ap.add_argument("--follow-anchor", action="store_true", help="shift golden dates to the live data window (data that rolls forward nightly); skips calendar-aligned items")
    ap.add_argument("--json", type=Path, help="write outcomes and summary as JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    container = build_container(get_settings().model_copy(update={"log_level": "WARNING"}))
    try:
        outcomes = run_bench(container, set(args.category or []), args.cache, args.file, args.follow_anchor)
        summary = summarize(outcomes)
        print(f"llm={container.llm.name} engine={container.engine.name} anchor={container.query_service.anchor}")
        print(render(outcomes, summary, args.verbose))
        if args.json:
            args.json.write_text(json.dumps({"summary": summary, "outcomes": [asdict(o) for o in outcomes]}, indent=2))
    finally:
        container.close()
    sys.exit(1 if summary["unexpected_failures"] else 0)


if __name__ == "__main__":
    main()
