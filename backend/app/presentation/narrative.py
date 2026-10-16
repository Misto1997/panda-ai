"""Deterministic text summaries. Used by the offline mock and as the fallback when the LLM is unavailable,
so a result is never lost because the narration call failed."""
from __future__ import annotations

from app.presentation.formatting import format_value


def answer_summary(columns: list[str], rows: list[list], formats: dict[str, str], titles: dict[str, str]) -> str:
    if not rows:
        return "No data matched that question for the selected period."
    metric_cols = [c for c in columns if c in formats]
    if not metric_cols:
        return f"{len(rows)} row(s) returned."
    if len(rows) == 1:
        return "For the selected period: " + ", ".join(
            f"**{titles[c]}** is {format_value(rows[0][columns.index(c)], formats[c])}" for c in metric_cols) + "."
    first = metric_cols[0]
    i = columns.index(first)
    top, low = max(rows, key=lambda r: r[i] or 0), min(rows, key=lambda r: r[i] or 0)
    label = lambda r: " / ".join(str(r[j]) for j, c in enumerate(columns) if c not in formats)
    return (f"{len(rows)} rows. Highest **{titles[first]}**: {label(top)} ({format_value(top[i], formats[first])}); "
            f"lowest: {label(low)} ({format_value(low[i], formats[first])}).")


def rca_summary(f: dict) -> str:
    fmt = f["format"]
    if f["rel"] is None:
        return (f"There is no comparable data for {f['title']}: the analysed period " f"({f['current']['start']}..{f['current']['end']}) or its baseline "
                f"({f['baseline']['start']}..{f['baseline']['end']}) has no rows.")
    verb = "fell" if (f["rel"] or 0) < 0 else "rose"
    head = (f"**{f['title']} {verb} {abs(f['rel'] or 0):.1%}** ({format_value(f['baseline']['value'], fmt)} to {format_value(f['current']['value'], fmt)}), "
            f"comparing {f['current']['start']}..{f['current']['end']} with {f['baseline']['start']}..{f['baseline']['end']}.")
    bullets = []
    if f["decomposition"]:
        d = f["decomposition"][0]
        bullets.append(f"Largest driver: **{d['title']}** ({d['rel']:+.1%}), contributing {format_value(d['contribution'], fmt)} of the change.")
    cells = f["drill"]["cells"]
    if cells and cells[0]["share_of_change"] is not None:
        c = cells[0]
        bullets.append(f"Concentrated in **{', '.join(f'{k}={v}' for k, v in c['segment'].items())}**, which explains {c['share_of_change']:.0%} of the change.")
    confirmed = [h for h in f["hypotheses"] if h["status"] == "confirmed"]
    bullets += [f"Confirmed: **{h['claim']}** ({h['evidence']})." for h in confirmed]
    bullets += [f"Caution: {c['title']} fired ({c['detail']})." for c in f["checks"] if c["fired"]]
    if not confirmed:
        bullets.append("No hypothesis was confirmed, so the cause is not established.")
    if not f["material"]:
        bullets.append("The overall movement is below the materiality threshold.")
    return head + "\n\n" + "\n".join(f"- {b}" for b in bullets)
