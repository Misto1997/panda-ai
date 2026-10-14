"""Deterministic RCA tree walker. Numbers come from governed queries and exact attribution maths;
the LLM only narrates the resulting facts."""
from __future__ import annotations

import math
from datetime import date, timedelta
from itertools import product

from app.engine import get_engine
from app.query.compiler import compile_ir
from app.query.ir import Filter, QueryIR
from app.query.timeutil import previous_period, resolve
from app.semantic.catalog import Catalog

Seg = tuple[str, ...]


def _rel(new: float, old: float) -> float | None:
    return None if not old else (new - old) / abs(old)


class Walker:
    def __init__(self, cat: Catalog, anchor: date) -> None:
        self.cat, self.anchor, self.eng = cat, anchor, get_engine()
        self.queries: list[str] = []

    def seg(self, metric: str, dims: list[str], period: tuple[date, date], filters: list[Filter] | None = None) -> dict[Seg, tuple[float, float | None]]:
        """segment -> (numerator-or-value, denominator-or-None)"""
        s, e = period
        ir = QueryIR(metrics=[metric], dimensions=dims, filters=filters or [], time_expr=f"{s}..{e - timedelta(days=1)}")
        c = compile_ir(ir, self.cat, self.anchor, select_parts=True)
        self.queries.append(c.sql)
        r = self.eng.run(c.sql)
        m, idx = self.cat.metrics[metric], {n: i for i, n in enumerate(r.columns)}
        out: dict[Seg, tuple[float, float | None]] = {}
        for row in r.rows:
            key = tuple(str(row[idx[d]]) for d in dims)
            if m.is_ratio:
                out[key] = (row[idx[f"{metric}__num"]] or 0.0, row[idx[f"{metric}__den"]] or 0.0)
            else:
                out[key] = (row[idx[metric]] or 0.0, None)
        return out

    def value(self, metric: str, period, filters=None) -> float:
        n, d = self.seg(metric, [], period, filters).get((), (0.0, None))
        return n / d if d else (0.0 if d == 0 else n)

    # ---- steps ----
    def checks(self, ids: list[str], cur, base) -> list[dict]:
        out = []
        for cid in ids:
            c = self.cat.checks[cid]
            if c["check"] == "freshness":
                latest = self.eng.anchor()
                fired = latest < cur[1] - timedelta(days=1)
                out.append({"id": cid, "title": c["title"], "fired": fired, "detail": f"latest loaded date {latest}"})
            elif c["check"] == "metric_shift":
                rel = _rel(self.value(c["metric"], cur), self.value(c["metric"], base))
                out.append({"id": cid, "title": c["title"], "fired": rel is not None and rel <= c["threshold"],
                            "detail": f"{c['metric']} changed {rel:+.1%}" if rel is not None else "no baseline"})
        return out

    def decompose(self, tree: dict, cur, base) -> list[dict]:
        comps = tree["decomposition"]["components"]
        g1, g0 = self.value(tree["root_metric"], cur), self.value(tree["root_metric"], base)
        if not (g1 > 0 and g0 > 0) or g1 == g0:
            return []
        scale = (g1 - g0) / math.log(g1 / g0)  # logarithmic mean: contributions sum exactly to the delta
        rows = []
        for c in comps:
            v1, v0 = self.value(c, cur), self.value(c, base)
            rows.append({"component": c, "baseline": v0, "current": v1, "rel": _rel(v1, v0),
                         "contribution": scale * math.log(v1 / v0) if v1 > 0 and v0 > 0 else 0.0})
        return sorted(rows, key=lambda r: -abs(r["contribution"]))

    def drill(self, metric: str, dims: list[str], cur, base, top_k: int, min_share: float) -> dict:
        """Exact contribution-to-delta per segment: sums use value deltas, ratios use num_i/DEN deltas."""
        m = self.cat.metrics[metric]
        dims = [d for d in dims if d in m.dimensions]
        s1, s0 = self.seg(metric, dims, cur), self.seg(metric, dims, base)
        if m.is_ratio:
            D1, D0 = sum(v[1] for v in s1.values()), sum(v[1] for v in s0.values())
            contrib = lambda k: (s1.get(k, (0, 0))[0] / D1 if D1 else 0) - (s0.get(k, (0, 0))[0] / D0 if D0 else 0)
            val = lambda s, k: (s[k][0] / s[k][1]) if k in s and s[k][1] else None
            tot0 = sum(v[0] for v in s0.values()) / D0 if D0 else 0
        else:
            contrib = lambda k: s1.get(k, (0, 0))[0] - s0.get(k, (0, 0))[0]
            val = lambda s, k: s[k][0] if k in s else None
            tot0 = sum(v[0] for v in s0.values())
        keys = set(s1) | set(s0)
        total = sum(contrib(k) for k in keys)
        cells = []
        for k in keys:
            c = contrib(k)
            share0 = (s0[k][1] / sum(v[1] for v in s0.values()) if m.is_ratio else s0[k][0] / tot0) if k in s0 and tot0 else 0
            if share0 < min_share and abs(c) < abs(total) * 0.1:
                continue
            cells.append({"segment": dict(zip(dims, k)), "baseline": val(s0, k), "current": val(s1, k),
                          "rel": _rel(val(s1, k) or 0, val(s0, k) or 0) if val(s0, k) else None,
                          "contribution": c, "share_of_change": (c / total) if total else None})
        cells.sort(key=lambda r: -abs(r["contribution"]))
        marginals = {}
        for d in dims:
            ms1, ms0 = self.seg(metric, [d], cur), self.seg(metric, [d], base)
            best = None
            for k in set(ms1) | set(ms0):
                if m.is_ratio:
                    D1m, D0m = sum(v[1] for v in ms1.values()), sum(v[1] for v in ms0.values())
                    c = (ms1.get(k, (0, 0))[0] / D1m if D1m else 0) - (ms0.get(k, (0, 0))[0] / D0m if D0m else 0)
                else:
                    c = ms1.get(k, (0, 0))[0] - ms0.get(k, (0, 0))[0]
                if best is None or abs(c) > abs(best[1]):
                    best = (k[0], c)
            if best:
                marginals[d] = {"segment": best[0], "contribution": best[1], "share_of_change": best[1] / total if total else None}
        return {"dims": dims, "total_change": total, "cells": cells[:top_k], "marginals": marginals}

    def hypotheses(self, tree: dict, cur, base, top_cell: dict | None) -> list[dict]:
        out = []
        for h in tree.get("hypotheses", []):
            res = {"id": h["id"], "claim": h["claim"], "status": "inconclusive", "evidence": ""}
            if h["test"] == "metric_shift":
                rel = _rel(self.value(h["metric"], cur), self.value(h["metric"], base))
                res["status"] = "confirmed" if rel is not None and abs(rel) > h["threshold"] else "rejected"
                res["evidence"] = f"{h['metric']} changed {rel:+.1%} overall (threshold {h['threshold']:.0%})" if rel is not None else "no baseline"
            elif h["test"] == "funnel_walk" and top_cell:
                vol, *rates = h["funnel"]
                dims = [d for d in top_cell["segment"] if d in self.cat.metrics[rates[0]].dimensions]
                flt = [Filter(dim=d, values=[top_cell["segment"][d]]) for d in dims]
                steps = []
                for mid in [vol, *rates]:
                    v1, v0 = self.value(mid, cur, flt), self.value(mid, base, flt)
                    steps.append({"metric": mid, "baseline": v0, "current": v1, "rel": _rel(v1, v0)})
                worst = min(steps[1:], key=lambda s: s["rel"] if s["rel"] is not None else 0)
                stable = steps[0]["rel"] is not None and abs(steps[0]["rel"]) < 0.10
                confirmed = worst["rel"] is not None and worst["rel"] < -h["threshold"]
                seg_txt = ", ".join(f"{k}={v}" for k, v in top_cell["segment"].items())
                res.update(status="confirmed" if confirmed else "rejected", steps=steps,
                           evidence=(f"In {seg_txt}: {worst['metric']} {worst['rel']:+.1%} "
                                     f"({worst['baseline']:.2%} to {worst['current']:.2%}); {steps[0]['metric']} {steps[0]['rel']:+.1%}"
                                     + (" (stable, so not a traffic issue)" if stable and confirmed else "")))
            out.append(res)
        return out


def run_rca(cat: Catalog, anchor: date, metric: str, time_expr: str) -> dict:
    tree = cat.tree_for(metric)
    policy = cat.policies[(tree or {}).get("policy", "rca_policy_default")]["rules"]
    cur = resolve(time_expr, anchor)
    base = previous_period(*cur)
    w = Walker(cat, anchor)
    m = cat.metrics[metric]
    v1, v0 = w.value(metric, cur), w.value(metric, base)
    rel = _rel(v1, v0)
    facts: dict = {"metric": metric, "title": m.title, "format": m.format, "tree": tree["id"] if tree else None,
                   "current": {"start": str(cur[0]), "end": str(cur[1] - timedelta(days=1)), "value": v1},
                   "baseline": {"start": str(base[0]), "end": str(base[1] - timedelta(days=1)), "value": v0},
                   "rel": rel, "material": rel is not None and abs(rel) >= policy["materiality"]["value"]}
    facts["checks"] = w.checks(tree["preflight"], cur, base) if tree else []
    facts["decomposition"] = w.decompose(tree, cur, base) if tree and "decomposition" in tree else []
    driver = facts["decomposition"][0]["component"] if facts["decomposition"] else metric
    dims = (tree or {}).get("drill_dimensions", m.dimensions)
    facts["drill_metric"] = driver
    facts["drill"] = w.drill(driver, dims, cur, base, policy["top_k_drivers"]["value"], policy["min_segment_share"]["value"])
    top = facts["drill"]["cells"][0] if facts["drill"]["cells"] else None
    facts["hypotheses"] = w.hypotheses(tree, cur, base, top) if tree else []
    facts["queries_run"] = len(w.queries)
    facts["sql_sample"] = w.queries[:3]
    return facts
