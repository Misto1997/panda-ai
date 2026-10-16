"""Black-box probe of a running PANDA AI (local or deployed): runs demo questions of every kind over the AG-UI stream and reports
latency (total, time to first event, per step), dead gaps the user would stare at, cache effect, payload size, multi-turn growth in one
thread versus fresh threads, and concurrency. Needs only `httpx` (a dev dependency).

  # local backend (AUTH_MODE=dev)
  python scripts/probe.py --api http://localhost:8000
  # deployed (Firebase auth): copy the ID token from DevTools > Network > any /api/chat request > Authorization: Bearer <token>
  ID_TOKEN=eyJ... python scripts/probe.py --api https://panda-api-....run.app --web https://panda-web-....run.app --rounds 2 --out probe.json

Each turn costs one quota unit. Admin accounts (ADMIN_EMAILS) are exempt from the per-user cap. Quick run: --quick (about 12 turns).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

try:
    import httpx
except ImportError:
    sys.exit("this script needs httpx: pip3 install httpx")

GAP_S = 2.0  # a silent stretch longer than this is 'dead time' on the UI

HELP = [("help", "hello")]
DISCOVER = [("discover", "What is BU visits?"), ("discover", "How is net realization rate defined?")]
QNA = [("qna", "Net GMV by zone for the last 7 days"), ("qna", "Daily visits by marketplace last 14 days"),
       ("qna", "Net units by state for Acme Express last 30 days"), ("qna", "ASP by business unit last 14 days"),
       ("qna_city", "Net GMV by city for Acme Mall last 7 days"), ("qna_ratio", "Conversion rate by marketplace and zone last 14 days"),
       ("qna_multi", "Net GMV and visits by marketplace last 7 days")]
RCA = [("rca", "Why did Net GMV drop in the last 14 days?"), ("rca", "Why did visits drop in the last 14 days?"),
       ("rca", "Why did ASP drop in the last 14 days?"), ("rca", "Why did conversion rate change in the last 14 days?")]
MULTI_TURN = ["Net GMV by zone for the last 7 days", "and by marketplace?", "only Acme Express", "now as a daily trend",
              "Why did it drop in the last 14 days?", "what about visits?"]
FRESH_SESSION_QS = ["Net GMV by zone for the last 7 days", "Daily visits by marketplace last 14 days", "Why did visits drop in the last 14 days?"]


def headers(token: str) -> dict:
    return {"content-type": "application/json", **({"authorization": f"Bearer {token}"} if token else {})}


def run_turn(api: str, token: str, question: str, thread: str | None, bypass_cache: bool = False, force_raw: bool = False,
             timeout: float = 240.0) -> dict:
    """One chat turn; returns timings (seconds since the request was sent) and the facts the report needs."""
    body = {"question": question, "bypass_cache": bypass_cache, "force_raw": force_raw}
    if thread:
        body["thread_id"] = thread
    out: dict = {"question": question, "thread": thread, "events": [], "steps": [], "error": None, "http": None}
    t0 = time.perf_counter()
    last = t0
    gaps: list[tuple[float, str]] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=30)) as client, \
                client.stream("POST", f"{api.rstrip('/')}/api/chat", json=body, headers=headers(token)) as r:
            out["http"] = r.status_code
            out["request_id"] = r.headers.get("x-request-id")
            out["ttfb"] = time.perf_counter() - t0
            if r.status_code != 200:
                out["error"] = r.read().decode()[:300]
                out["total"] = time.perf_counter() - t0
                return out
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                now = time.perf_counter()
                event = json.loads(line[6:])
                etype, t = event.get("type"), now - t0
                if now - last > GAP_S:
                    gaps.append((round(now - last, 1), etype))
                last = now
                out["events"].append((round(t, 2), etype))
                if etype == "CUSTOM" and event.get("name") == "panda.step":
                    v = event["value"]
                    out["steps"].append({"node": v["node"], "step": v["step"], "ms": v["ms"], "cache": v.get("cache"), "arrived": round(t, 2)})
                elif etype == "CUSTOM" and event.get("name") == "panda.result":
                    res = event["value"]
                    out["result_bytes"] = len(line)
                    out["type"], out["meta"] = res.get("type"), res.get("meta", {})
                    out["rows"] = len((res.get("table") or {}).get("rows", []))
                    out["text_chars"] = len(res.get("text", ""))
                elif etype == "TEXT_MESSAGE_START":
                    out["t_text"] = round(t, 2)
                elif etype == "ACTIVITY_SNAPSHOT":
                    out["t_surface"] = round(t, 2)
                elif etype == "RUN_ERROR":
                    out["error"] = event.get("message")
                elif etype == "RUN_FINISHED":
                    out["t_finished"] = round(t, 2)
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["total"] = time.perf_counter() - t0
    out["gaps"] = gaps
    out["first_event"] = out["events"][0][0] if out["events"] else None
    out["first_step"] = out["steps"][0]["arrived"] if out["steps"] else None
    return out


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


def line(r: dict) -> str:
    m = r.get("meta") or {}
    flag = "ERR " if r.get("error") else "ok  "
    return (f"{flag}{r['total']:6.1f}s first-step={r.get('first_step') or 0:5.1f}s gaps={len(r.get('gaps', []))} "
            f"path={m.get('path') or m.get('route') or '-':11s} cache={m.get('cache') or '-':4s} sql_try={m.get('sql_attempts') or '-'} "
            f"rows={r.get('rows', '-')} payload={r.get('result_bytes', 0) // 1024}KB  {r['question'][:58]}"
            + (f"   !! {r['error'][:90]}" if r.get("error") else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True, help="gateway base URL")
    ap.add_argument("--web", help="web base URL (checks the UI and the BFF)")
    ap.add_argument("--token", default=os.environ.get("ID_TOKEN", ""), help="Firebase ID token (or env ID_TOKEN); empty for AUTH_MODE=dev")
    ap.add_argument("--rounds", type=int, default=2, help="repeat the single-turn catalogue (round 2 shows the cache effect)")
    ap.add_argument("--quick", action="store_true", help="one question per kind, one round, shorter multi-turn")
    ap.add_argument("--concurrency", type=int, default=4, help="parallel fresh sessions (0 = skip)")
    ap.add_argument("--out", help="write the full JSON report here")
    args = ap.parse_args()

    report: dict = {"api": args.api, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "turns": []}
    print(f"== PANDA AI probe: {args.api}")

    # ---- cold start / readiness ----
    for path in ("/health", "/ready", "/api/meta"):
        t = time.perf_counter()
        try:
            r = httpx.get(args.api.rstrip("/") + path, headers=headers(args.token), timeout=120)
            print(f"GET {path:10s} {r.status_code} {time.perf_counter() - t:5.2f}s")
            if path == "/api/meta" and r.status_code == 200:
                meta = r.json()
                print(f"  profile={meta.get('profile')} llm={meta.get('llm')} engine={meta.get('engine')} search={meta.get('search')} data_through={meta.get('anchor')}")
        except httpx.HTTPError as e:
            print(f"GET {path} failed: {e}")
    if args.web:
        for path in ("/", "/api/meta"):
            t = time.perf_counter()
            try:
                r = httpx.get(args.web.rstrip("/") + path, headers=headers(args.token) if path != "/" else {}, timeout=120)
                print(f"WEB {path:10s} {r.status_code} {time.perf_counter() - t:5.2f}s {len(r.content) // 1024}KB")
            except httpx.HTTPError as e:
                print(f"WEB {path} failed: {e}")

    # ---- single-turn catalogue (fresh thread each) ----
    catalogue = HELP + DISCOVER[:1] + QNA[:2] + RCA[:1] if args.quick else HELP + DISCOVER + QNA + RCA
    rounds = 1 if args.quick else args.rounds
    for rnd in range(1, rounds + 1):
        print(f"\n-- round {rnd}: single turns, fresh thread each")
        for kind, q in catalogue:
            r = run_turn(args.api, args.token, q, uuid.uuid4().hex[:12])
            r.update(kind=kind, round=rnd, scenario="single")
            report["turns"].append(r)
            print(line(r))

    # ---- same session, multi turn ----
    qs = MULTI_TURN[:4] if args.quick else MULTI_TURN
    print("\n-- same session, multi turn (watch latency as the thread grows)")
    thread = "probe-" + uuid.uuid4().hex[:8]
    for i, q in enumerate(qs, 1):
        r = run_turn(args.api, args.token, q, thread, bypass_cache=True)  # bypass cache: isolates thread-growth from caching
        r.update(kind="multi_turn", turn=i, scenario="same_session")
        report["turns"].append(r)
        print(f"t{i} " + line(r))

    # ---- different sessions, same questions ----
    print("\n-- different sessions, same questions (cache should carry across sessions)")
    for q in FRESH_SESSION_QS[: 2 if args.quick else 3]:
        for s in (1, 2):
            r = run_turn(args.api, args.token, q, uuid.uuid4().hex[:12])
            r.update(kind="fresh_session", session=s, scenario="fresh_sessions")
            report["turns"].append(r)
            print(f"s{s} " + line(r))

    # ---- concurrency ----
    if args.concurrency:
        print(f"\n-- {args.concurrency} concurrent fresh sessions (cache bypassed)")
        t0 = time.perf_counter()
        with ThreadPoolExecutor(args.concurrency) as pool:
            results = list(pool.map(lambda i: run_turn(args.api, args.token, QNA[i % len(QNA)][1], uuid.uuid4().hex[:12], bypass_cache=True),
                                    range(args.concurrency)))
        for r in results:
            r.update(kind="concurrent", scenario="concurrency")
            report["turns"].append(r)
            print(line(r))
        print(f"wall clock for all: {time.perf_counter() - t0:.1f}s")

    summarize(report)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=1, default=str)
        print(f"\nfull report written to {args.out}")
    return 1 if any(t.get("error") for t in report["turns"]) else 0


def summarize(report: dict) -> None:
    turns = [t for t in report["turns"] if not t.get("error")]
    print("\n== SUMMARY (successful turns)")
    by_kind: dict[str, list[dict]] = {}
    for t in turns:
        by_kind.setdefault(t.get("kind", "?"), []).append(t)
    print(f"{'kind':14s} {'n':>3s} {'p50':>7s} {'p95':>7s} {'max':>7s}   {'first-step p50':>14s}")
    for kind, ts in sorted(by_kind.items()):
        tot = [t["total"] for t in ts]
        fs = [t["first_step"] for t in ts if t.get("first_step") is not None]
        print(f"{kind:14s} {len(ts):3d} {statistics.median(tot):6.1f}s {pct(tot, .95):6.1f}s {max(tot):6.1f}s   {statistics.median(fs) if fs else 0:13.1f}s")

    steps: dict[str, list[float]] = {}
    for t in turns:
        for s in t["steps"]:
            steps.setdefault(f"{s['node']}/{s['step']}", []).append(s["ms"] / 1000)
    if steps:
        print("\nserver-side time per step (seconds, where the latency is):")
        for name, v in sorted(steps.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            print(f"  {name:22s} n={len(v):3d} avg={sum(v) / len(v):6.2f} p95={pct(v, .95):6.2f} max={max(v):6.2f}")

    errors = [t for t in report["turns"] if t.get("error")]
    gaps = [(g, t["question"]) for t in turns for g, _ in t.get("gaps", [])]
    print(f"\nerrors: {len(errors)} / {len(report['turns'])} turns")
    for t in errors[:5]:
        print(f"  {t['question'][:60]}: {t['error'][:140]}")
    print(f"dead gaps > {GAP_S:.0f}s between events (UI shows no progress): {len(gaps)}; longest {max((g for g, _ in gaps), default=0):.1f}s")

    mt = sorted((t for t in turns if t.get("scenario") == "same_session"), key=lambda t: t["turn"])
    if len(mt) >= 3:
        print(f"same-session latency by turn: {[round(t['total'], 1) for t in mt]}  (a rising trend means thread state is slowing turns)")
    pay = [t.get("result_bytes", 0) / 1024 for t in turns]
    print(f"result payload: p50 {pct(pay, .5):.0f}KB p95 {pct(pay, .95):.0f}KB max {max(pay, default=0):.0f}KB")

    r1 = {t["question"]: t["total"] for t in turns if t.get("round") == 1 and t.get("scenario") == "single"}
    r2 = {t["question"]: t["total"] for t in turns if t.get("round") == 2 and t.get("scenario") == "single"}
    common = [q for q in r1 if q in r2]
    if common:
        print(f"cache effect (round 2 vs round 1): median {statistics.median(r1[q] for q in common):.1f}s -> {statistics.median(r2[q] for q in common):.1f}s")

    llm_slow = [n for n in ("route/route", "plan/plan", "respond/respond", "rca/rca") if steps.get(n) and sum(steps[n]) / len(steps[n]) > 3]
    print("\nhints:")
    if llm_slow:
        print(f"  - slow model-bound steps (avg > 3s): {', '.join(llm_slow)}")
    if steps.get("execute/execute") and sum(steps["execute/execute"]) / len(steps["execute/execute"]) > 3:
        print("  - warehouse step averages > 3s: check bytes scanned and BigQuery job latency")
    if any(t["kind"] == "rca" and t["total"] > 25 for t in turns if t.get("kind")):
        print("  - RCA > 25s: it runs a few dozen sequential warehouse queries; parallelise them")
    if gaps:
        print("  - the UI is silent for stretches: emit a 'started' event before each node, not only after it")
    if max(pay, default=0) > 200:
        print("  - payloads > 200KB: results and chart data are duplicated; trim")


if __name__ == "__main__":
    sys.exit(main())
