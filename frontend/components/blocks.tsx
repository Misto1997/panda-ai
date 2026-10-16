"use client";
// Presentational blocks shared by the A2UI catalog components and the plain ResultView fallback.
import { useState } from "react";
import { fmt, pct } from "@/lib/format";
import type { Table } from "@/lib/types";

export type ChipItem = { label: string; value: string; tone?: string };
export type DecompRow = { component: string; title: string; format: string; baseline: number; current: number; rel: number | null; contribution: number };
export type SegCell = { label: string; share: number | null; rel: number | null };
export type Hyp = { id: string; claim: string; status: string; evidence: string };
export type Kpi = { label: string; value: string; delta?: number | null; caption?: string; tone?: string };

export function Chips({ chips }: { chips: ChipItem[] }) {
  return <div className="chips">{chips.map((c, i) => <span key={`${c.label}${i}`} className={`chip ${c.tone ?? ""}`}><b>{c.label}</b> {c.value}</span>)}</div>;
}

export function KpiRow({ items }: { items: Kpi[] }) {
  return (
    <div className="kpis">
      {items.map((k, i) => (
        <div key={i} className="kpi">
          <div className="kpi-label">{k.label}</div>
          <div className="kpi-value">{k.value}{k.delta !== undefined && k.delta !== null && <span className={`kpi-delta ${k.delta < 0 ? "neg" : "pos"}`}>{pct(k.delta)}</span>}</div>
          {k.caption && <div className="muted">{k.caption}</div>}
        </div>))}
    </div>
  );
}

export function DataTable({ t }: { t: Table }) {
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

export function DecompositionTable({ rows, title, format }: { rows: DecompRow[]; title?: string; format?: string }) {
  return (
    <>
      <h4>Decomposition <span className="muted">{title} split into its multiplicative drivers (exact log-ratio attribution)</span></h4>
      <table><thead><tr><th>Driver</th><th>Baseline</th><th>Current</th><th>Change</th><th>Contribution</th></tr></thead>
        <tbody>{rows.map((d) => (
          <tr key={d.component}><td>{d.title}</td><td className="num">{fmt(d.baseline, d.format)}</td><td className="num">{fmt(d.current, d.format)}</td>
            <td className={`num ${d.rel && d.rel < 0 ? "neg" : "pos"}`}>{pct(d.rel)}</td><td className="num">{fmt(d.contribution, format)}</td></tr>))}</tbody></table>
    </>
  );
}

export function SegmentBars({ cells, metric }: { cells: SegCell[]; metric?: string }) {
  return (
    <>
      <h4>Where it happened <span className="muted">top segments by share of the change in {(metric ?? "").replaceAll("_", " ")}</span></h4>
      {cells.map((c, i) => (
        <div key={i} className="bar-row">
          <span className="bar-label">{c.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, Math.abs((c.share ?? 0) * 100))}%` }} /></div>
          <span className="bar-val">{c.share === null ? "" : `${(c.share * 100).toFixed(0)}%`} · {pct(c.rel)}</span>
        </div>))}
    </>
  );
}

export function HypothesisList({ items }: { items: Hyp[] }) {
  return (
    <>
      <h4>Hypotheses tested</h4>
      {items.map((h) => <div key={h.id} className="hyp"><span className={`badge ${h.status}`}>{h.status}</span> <b>{h.claim}</b><div className="muted">{h.evidence}</div></div>)}
    </>
  );
}

export function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="link" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"} SQL</button>
      {open && <pre className="sql">{sql}</pre>}
    </>
  );
}
