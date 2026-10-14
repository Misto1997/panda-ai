"""Rule-based stand-in for the LLM: offline demo fallback and deterministic test double.
Understands the metric/dimension vocabulary passed in `hints`."""
from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from app.fmt import fmt

T = TypeVar("T", bound=BaseModel)

RCA_WORDS = r"\b(why|root cause|reason|investigate|rca|what happened|what caused|explain the (drop|decline|dip|fall))\b|\b(drop|dropped|decline|declined|fell|fall|dip|dipped|decrease|decreased)\b"
DISCOVER = r"\b(what is|what's|define|definition|meaning|what does|which metrics|what metrics|available|glossary|how is .* (calculated|computed))\b"
HELP = r"^(hi|hello|hey|help)\b|what can you do|how do i use"
DATA_WORDS = r"\b(by|per|last|yesterday|trend|top|compare|show|total|how many|how much)\b"


def _find(names: list[str], q: str) -> bool:
    return any(re.search(rf"\b{re.escape(n.lower())}s?\b", q) for n in names if n)


class MockLLM:
    name = "mock"

    def structured(self, schema: type[T], system: str, user: str, hints: dict | None = None) -> T:
        h, q = hints or {}, (hints or {}).get("question", user).lower()
        n = schema.__name__
        if n == "RouteDecision":
            if re.search(HELP, q):
                r = "help"
            elif re.search(RCA_WORDS, q):
                r = "rca"
            elif re.search(DISCOVER, q) and not re.search(DATA_WORDS, q):
                r = "discover"
            else:
                r = "qna"
            return schema(route=r, reasoning="keyword router (mock)")
        metric = self._metrics(q, h)
        if n == "RcaRequest":
            last = (h.get("last_ir") or {}).get("metrics", [])
            return schema(metric=(metric[0] if metric else (last[0] if last else "gmv")), time_expr=self._time(q) or "last_14_days")
        if n == "QueryIR":
            last = h.get("last_ir")
            dims, filters = [], []
            for d in h["catalog"]["dimensions"]:
                matched_val = [v for v in d["values"] if re.search(rf"\b{re.escape(v.lower())}\b", q)]
                if matched_val:
                    filters.append({"dim": d["id"], "values": matched_val, "negate": False})
                elif re.search(rf"\b(by|per|across|each|breakdown by|split by|for every)\s+(the\s+)?({'|'.join(map(re.escape, [x.lower() for x in d['names']]))})\b", q):
                    dims.append(d["id"])
            grain = "day" if re.search(r"\b(daily|per day|trend|over time|by day|each day)\b", q) else \
                    "week" if re.search(r"\b(weekly|by week|per week)\b", q) else \
                    "month" if re.search(r"\b(monthly|by month|per month)\b", q) else "none"
            follow = bool(last) and not metric
            time_expr = self._time(q) or (last["time_expr"] if follow else "last_30_days")
            if follow:
                metric = last["metrics"]
                dims = dims or (last["dimensions"] if not re.search(r"\b(overall|total)\b", q) else [])
                filters = filters or last["filters"]
                grain = grain if grain != "none" else last.get("grain", "none")
            top = re.search(r"\btop\s+(\d+)\b", q)
            ir = {"metrics": metric, "dimensions": dims, "filters": filters, "time_expr": time_expr, "grain": grain,
                  "order_by": metric[0] if metric and dims else None, "order_desc": not re.search(r"\b(bottom|lowest|worst)\b", q),
                  "limit": int(top.group(1)) if top else None}
            return schema(**ir)
        raise NotImplementedError(n)

    @staticmethod
    def _metrics(q: str, h: dict) -> list[str]:
        found = []
        for m in sorted(h["catalog"]["metrics"], key=lambda m: -max(len(x) for x in m["names"])):
            for nme in m["names"]:
                mt = re.search(rf"\b{re.escape(nme.lower())}s?\b", q)
                if mt and not any(mt.start() >= a and mt.end() <= b for _, (a, b) in found):
                    found.append((m["id"], mt.span()))
                    break
        return [m for m, _ in sorted(found, key=lambda x: x[1][0])]

    @staticmethod
    def _time(q: str) -> str | None:
        if m := re.search(r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", q):
            return f"last_{m.group(1)}_days"
        if m := re.search(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", q):
            return f"last_{int(m.group(1)) * 7}_days"
        for pat, v in [(r"\byesterday\b", "yesterday"), (r"\blast week\b|\bprevious week\b", "last_week"), (r"\bthis week\b", "this_week"),
                       (r"\blast month\b", "last_month"), (r"\bthis month\b", "this_month"), (r"\bmtd\b|month to date", "mtd"),
                       (r"\b(past|last) week\b", "last_7_days"), (r"\ball time\b|\bever\b", "all_time"),
                       (r"\blast quarter\b|\b90 days\b", "last_90_days")]:
            if re.search(pat, q):
                return v
        return None

    def text(self, system: str, user: str, hints: dict | None = None, pro: bool = False) -> str:
        h = hints or {}
        task = h.get("task")
        if task == "answer":
            return self._answer(h)
        if task == "rca":
            return self._rca(h["facts"])
        if task == "discover":
            docs = h["docs"][:4]
            return "Here is what the semantic layer says:\n" + "\n".join(f"- **{d['title']}**: {d['text'][:220]}" for d in docs)
        return ""

    @staticmethod
    def _answer(h: dict) -> str:
        cols, rows, cat = h["columns"], h["rows"], h["formats"]
        if not rows:
            return "No data matched that question for the selected period."
        mcols = [c for c in cols if c in cat]
        if len(rows) == 1:
            return "For the selected period: " + ", ".join(f"**{h['titles'][c]}** is {fmt(rows[0][cols.index(c)], cat[c])}" for c in mcols) + "."
        c0 = mcols[0]
        i = cols.index(c0)
        top = max(rows, key=lambda r: r[i] or 0)
        low = min(rows, key=lambda r: r[i] or 0)
        label = lambda r: " / ".join(str(r[j]) for j, c in enumerate(cols) if c not in cat)
        return (f"{len(rows)} rows. Highest **{h['titles'][c0]}**: {label(top)} ({fmt(top[i], cat[c0])}); "
                f"lowest: {label(low)} ({fmt(low[i], cat[c0])}).")

    @staticmethod
    def _rca(f: dict) -> str:
        fm = f["format"]
        direction = "fell" if (f["rel"] or 0) < 0 else "rose"
        lines = [f"**{f['title']} {direction} {abs(f['rel'] or 0):.1%}** ({fmt(f['baseline']['value'], fm)} to {fmt(f['current']['value'], fm)}) "
                 f"comparing {f['current']['start']}..{f['current']['end']} with the previous {f['baseline']['start']}..{f['baseline']['end']}."]
        if f["decomposition"]:
            d = f["decomposition"][0]
            lines.append(f"Largest driver: **{d['component']}** ({d['rel']:+.1%}), contributing {fmt(d['contribution'], fm)} of the change.")
        cells = f["drill"]["cells"]
        if cells and cells[0]["share_of_change"] is not None:
            c = cells[0]
            seg = ", ".join(f"{k}={v}" for k, v in c["segment"].items())
            lines.append(f"The movement is concentrated in **{seg}**, which explains {c['share_of_change']:.0%} of the change.")
        for hyp in f["hypotheses"]:
            if hyp["status"] == "confirmed":
                lines.append(f"Confirmed hypothesis: {hyp['claim']}. {hyp['evidence']}.")
        for c in f["checks"]:
            if c["fired"]:
                lines.append(f"Caution: {c['title']} fired ({c['detail']}).")
        if not f["material"]:
            lines.append("The overall movement is below the materiality threshold.")
        return "\n\n".join(lines)
