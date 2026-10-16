"use client";
// Plain renderer of the `panda.result` payload. Used when the A2UI surface is absent or fails to render.
import Chart from "./Chart";
import Markdown from "./Markdown";
import { Callouts, Chips, DataTable, DecompositionTable, HypothesisList, SegmentBars, SqlBlock, SuggestionChips, VerdictHeader, type ChipItem, type Verdict } from "./blocks";
import { fmt, pct } from "@/lib/format";
import type { Rca, Result } from "@/lib/types";

const DIM_ORDER = ["marketplace", "zone", "region", "state", "city", "business_unit"];
const pctOf = (v: number | null) => (v === null ? "" : `${(v * 100).toFixed(0)}%`);

function metaChips(meta: Result["meta"]): ChipItem[] {
  const c: ChipItem[] = [];
  if (meta.engine) c.push({ label: "engine", value: meta.engine });
  if (meta.sources) c.push({ label: "source", value: Object.values(meta.sources).join(", "), tone: String(Object.values(meta.sources)[0]).startsWith("agg_") ? "good" : "warn" });
  if (meta.elapsed_ms !== undefined) c.push({ label: "query", value: `${meta.elapsed_ms} ms` });
  if (meta.cache && meta.cache !== "off") c.push({ label: "cache", value: meta.cache, tone: meta.cache === "hit" ? "good" : "" });
  if (meta.bytes_processed !== undefined) c.push({ label: "scanned", value: `${(meta.bytes_processed / 1e6).toFixed(1)} MB` });
  if (meta.path) c.push({ label: "path", value: meta.path });
  if (meta.sql_attempts) c.push({ label: "sql attempts", value: String(meta.sql_attempts) });
  if (meta.queries) c.push({ label: "queries", value: String(meta.queries) });
  if (meta.total_ms !== undefined) c.push({ label: "total", value: `${meta.total_ms} ms` });
  if (meta.llm) c.push({ label: "llm", value: meta.llm });
  return c;
}

const dayBefore = (iso: string) => { const d = new Date(`${iso}T00:00:00Z`); return Number.isNaN(d.getTime()) ? iso : new Date(d.getTime() - 864e5).toISOString().slice(0, 10); };
const span = (p: Rca["current"]) => (p?.start && p?.end ? `${p.start} to ${dayBefore(p.end)}` : "");

const toneOf = (rel: number | null | undefined, dir?: string) =>
  !rel || (dir !== "up_is_good" && dir !== "down_is_good") ? "neutral" : (rel > 0) === (dir === "up_is_good") ? "good" : "bad";

function verdictOf(r: Rca): Verdict {
  return {
    title: r.title, delta: r.rel === null || r.rel === undefined ? "n/a" : pct(r.rel), tone: toneOf(r.rel, r.direction),
    current: { label: "Current", value: fmt(r.current?.value, r.format), range: span(r.current) }, baseline: { label: "Baseline", value: fmt(r.baseline?.value, r.format), range: span(r.baseline) },
    material: r.material,
  };
}

export default function ResultView({ result }: { result: Result }) {
  const r = result.rca;
  const seg = (s: Record<string, string>) => Object.entries(s).map(([k, v]) => `${k}=${v}`).join(", ");
  return (
    <div className={`result ${result.type}`}>
      {!r && <div className="answer"><Markdown text={result.text} /></div>}
      {result.chart && <Chart spec={result.chart} />}
      {r && (
        <div className="rca">
          <VerdictHeader verdict={verdictOf(r)} />
          <Callouts items={r.checks.filter((c) => c.fired).map((c) => ({ label: c.title, value: c.detail }))} />
          {r.decomposition.length > 0 && <DecompositionTable rows={r.decomposition} title={r.title} format={r.format} />}
          <SegmentBars metric={r.drill_metric} cells={r.drill.cells.map((c) => ({ label: seg(c.segment), share: c.share_of_change, rel: c.rel }))} />
          {Object.keys(r.drill.marginals).length > 0 && (
            <Chips chips={Object.entries(r.drill.marginals).sort(([a], [b]) => DIM_ORDER.indexOf(a) - DIM_ORDER.indexOf(b))
              .map(([dim, m]) => ({ label: dim.replace("_", " "), value: `${m.segment[dim]} · ${pctOf(m.share_of_change)}` }))} />)}
          <HypothesisList items={r.hypotheses} />
          <h4 className="section-heading">Analyst summary</h4>
          <div className="answer"><Markdown text={result.text} /></div>
          <div className="muted">Runbook {r.tree} · {r.queries_run} governed queries · baseline {r.baseline.start}..{r.baseline.end}</div>
        </div>)}
      {result.meta.suggestions && result.meta.suggestions.length > 0 && <SuggestionChips items={result.meta.suggestions} />}
      {result.table && result.table.rows.length > 1 && <DataTable t={result.table} />}
      {result.sql && <SqlBlock sql={result.sql} />}
      <Chips chips={metaChips(result.meta)} />
    </div>
  );
}
