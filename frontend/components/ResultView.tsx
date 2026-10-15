"use client";
import { useState } from "react";
import Chart from "./Chart";
import Markdown from "./Markdown";
import { fmt, pct } from "@/lib/format";
import type { Rca, Result } from "@/lib/types";

function Chips({ meta }: { meta: Result["meta"] }) {
  const chips: [string, string, string?][] = [];
  if (meta.engine) chips.push(["engine", meta.engine]);
  if (meta.sources) chips.push(["source", Object.values(meta.sources).join(", "), String(Object.values(meta.sources)[0]).startsWith("agg_") ? "good" : "warn"]);
  if (meta.elapsed_ms !== undefined) chips.push(["query", `${meta.elapsed_ms} ms`]);
  if (meta.cache && meta.cache !== "off") chips.push(["cache", meta.cache, meta.cache === "hit" ? "good" : ""]);
  if (meta.queries) chips.push(["queries", String(meta.queries)]);
  if (meta.total_ms !== undefined) chips.push(["total", `${meta.total_ms} ms`]);
  if (meta.llm) chips.push(["llm", meta.llm]);
  return (
    <div className="chips">
      {chips.map(([k, v, tone]) => <span key={k} className={`chip ${tone ?? ""}`}><b>{k}</b> {v}</span>)}
    </div>
  );
}

function DataTable({ t }: { t: NonNullable<Result["table"]> }) {
  return (
    <div className="tablewrap">
      <table>
        <thead><tr>{t.columns.map((c) => <th key={c}>{t.titles[c] ?? c}</th>)}</tr></thead>
        <tbody>
          {t.rows.slice(0, 100).map((r, i) => (
            <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{fmt(v, t.formats[t.columns[j]])}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {t.rows.length > 100 && <div className="muted">Showing 100 of {t.rows.length} rows</div>}
    </div>
  );
}

function RcaPanel({ r }: { r: Rca }) {
  const seg = (s: Record<string, string>) => Object.entries(s).map(([k, v]) => `${k}=${v}`).join(", ");
  return (
    <div className="rca">
      {r.checks.some((c) => c.fired) && <div className="warn-box">{r.checks.filter((c) => c.fired).map((c) => `${c.title}: ${c.detail}`).join(" · ")}</div>}
      <h4>Decomposition <span className="muted">{r.title} split into its multiplicative drivers (exact log-ratio attribution)</span></h4>
      <table><thead><tr><th>Driver</th><th>Baseline</th><th>Current</th><th>Change</th><th>Contribution</th></tr></thead>
        <tbody>{r.decomposition.map((d) => (
          <tr key={d.component}><td>{d.component}</td><td className="num">{fmt(d.baseline, d.component.includes("rate") ? "percent" : d.component === "aov" ? "currency" : "number")}</td>
            <td className="num">{fmt(d.current, d.component.includes("rate") ? "percent" : d.component === "aov" ? "currency" : "number")}</td>
            <td className={`num ${d.rel && d.rel < 0 ? "neg" : "pos"}`}>{pct(d.rel)}</td><td className="num">{fmt(d.contribution, r.format)}</td></tr>))}</tbody></table>
      <h4>Where it happened <span className="muted">top segments by share of the change in {r.drill_metric}</span></h4>
      {r.drill.cells.map((c, i) => (
        <div key={i} className="bar-row">
          <span className="bar-label">{seg(c.segment)}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, Math.abs((c.share_of_change ?? 0) * 100))}%` }} /></div>
          <span className="bar-val">{c.share_of_change === null ? "" : `${(c.share_of_change * 100).toFixed(0)}%`} · {pct(c.rel)}</span>
        </div>))}
      <h4>Hypotheses tested</h4>
      {r.hypotheses.map((h) => (
        <div key={h.id} className="hyp"><span className={`badge ${h.status}`}>{h.status}</span> <b>{h.claim}</b><div className="muted">{h.evidence}</div></div>))}
      <div className="muted">Runbook {r.tree} · {r.queries_run} governed queries · baseline {r.baseline.start}..{r.baseline.end}</div>
    </div>
  );
}

export default function ResultView({ result }: { result: Result }) {
  const [sql, setSql] = useState(false);
  return (
    <div className={`result ${result.type}`}>
      <div className="answer"><Markdown text={result.text} /></div>
      {result.chart && <Chart spec={result.chart} />}
      {result.rca && <RcaPanel r={result.rca} />}
      {result.table && result.table.rows.length > 1 && <DataTable t={result.table} />}
      {result.sql && <button className="link" onClick={() => setSql(!sql)}>{sql ? "Hide" : "Show"} SQL</button>}
      {sql && <pre className="sql">{result.sql}</pre>}
      <Chips meta={result.meta} />
    </div>
  );
}
