"use client";
// Presentational blocks shared by the A2UI catalog components and the plain ResultView fallback.
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { copyText } from "@/lib/clipboard";
import { fmt, pct } from "@/lib/format";
import { formatSql } from "@/lib/sql";
import type { Table } from "@/lib/types";
import { AlertIcon, CheckIcon, ChevronIcon, CopyIcon } from "./icons";

/** Lets answer blocks (suggestion chips) ask a follow-up question; `disabled` while a turn is running. */
export const AskContext = createContext<{ ask?: (q: string) => void; disabled: boolean }>({ disabled: true });

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
          <span className="bar-label ellipsis" title={c.label}>{c.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, Math.abs((c.share ?? 0) * 100))}%` }} /></div>
          <span className="bar-val">{c.share === null ? "" : `${(c.share * 100).toFixed(0)}%`} · {pct(c.rel)}</span>
        </div>))}
    </>
  );
}

export function HypothesisList({ items }: { items: Hyp[] }) {
  const rank = (h: Hyp) => (h.status === "confirmed" ? 0 : h.status === "rejected" ? 2 : 1);
  const sorted = [...items].sort((a, b) => rank(a) - rank(b));
  const active = sorted.filter((h) => h.status !== "rejected"), ruledOut = sorted.filter((h) => h.status === "rejected");
  const card = (h: Hyp) => (
    <div key={h.id} className={`hyp-card ${h.status}`}>
      <div><span className={`badge ${h.status}`}>{h.status}</span><span className="hyp-claim">{h.claim}</span></div>
      {h.evidence && <div className="muted">{h.evidence}</div>}
    </div>);
  return (
    <>
      <h4>Hypotheses tested</h4>
      {items.length === 0 && <div className="muted">No hypotheses were tested.</div>}
      <div className="hyp-list">{active.map(card)}</div>
      {ruledOut.length > 0 && <details className="ruled-out"><summary>Ruled out ({ruledOut.length})</summary><div className="hyp-list">{ruledOut.map(card)}</div></details>}
    </>
  );
}

export type Verdict = {
  title?: string; delta?: string; tone?: string; material?: boolean; materialLabel?: string;
  current?: { label?: string; value?: string; range?: string }; baseline?: { label?: string; value?: string; range?: string };
};

export function VerdictHeader({ verdict: v }: { verdict: Verdict }) {
  const side = (s: Verdict["current"], cls: string) => s && (
    <div className={`verdict-side ${cls}`}><div className="kpi-label">{s.label}</div><div className="verdict-value">{s.value ?? "n/a"}</div>{s.range && <div className="muted">{s.range}</div>}</div>);
  return (
    <div className="verdict">
      <div className="verdict-top">
        <span className="verdict-title ellipsis" title={v.title}>{v.title}</span>
        {v.delta && <span className={`pill ${v.tone ?? "neutral"}`}>{v.delta}</span>}
        <span className={`pill ${v.material ? "material" : "muted-pill"}`}>{v.materialLabel ?? (v.material ? "Material change" : "Below threshold")}</span>
      </div>
      <div className="verdict-compare">{side(v.current, "cur")}<span className="vs" aria-hidden>vs</span>{side(v.baseline, "base")}</div>
    </div>
  );
}

export function BulletList({ title, items }: { title?: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="findings">
      {title && <h4>{title}</h4>}
      <ul>{items.map((t, i) => <li key={i}>{inlineMd(t)}</li>)}</ul>
    </div>
  );
}

function inlineMd(s: string) {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>));
}

export function Callouts({ items }: { items: ChipItem[] }) {
  if (!items.length) return null;
  return (
    <div className="callouts">
      {items.map((c, i) => <div key={i} className="callout" role="note"><AlertIcon /><div><b>{c.label}</b>{c.value && <div>{c.value}</div>}</div></div>)}
    </div>
  );
}

export const Heading = ({ text }: { text: string }) => <h4 className="section-heading">{text}</h4>;

export function SuggestionChips({ items }: { items: string[] }) {
  const { ask, disabled } = useContext(AskContext);
  if (!items.length) return null;
  return (
    <div className="suggest-row" role="group" aria-label="Suggested questions">
      {items.map((q) => <button key={q} type="button" className="example" onClick={() => ask?.(q)} disabled={disabled || !ask} title={q}>{q}</button>)}
    </div>
  );
}

export function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    setCopied((await copyText(sql)) ? "ok" : "fail");
    clearTimeout(timer.current); timer.current = setTimeout(() => setCopied(null), 1800);
  };
  const tokens = open ? formatSql(sql) : [];
  return (
    <div className={`sqlcard${open ? " open" : ""}`}>
      <div className="sqlcard-head">
        <button type="button" className="sqlcard-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? "Collapse generated SQL" : "Expand generated SQL"}>
          <span className="chev"><ChevronIcon /></span><span className="sqlcard-tag">SQL</span><span>Generated SQL</span>
        </button>
        <button type="button" className="copy-btn" onClick={copy} aria-label="Copy SQL">
          {copied === "ok" ? <><CheckIcon /> Copied</> : copied === "fail" ? "Copy failed" : <><CopyIcon /> Copy</>}
        </button>
      </div>
      {open && <pre className="sql-code" tabIndex={0} aria-label="Generated SQL"><code>{tokens.map((t, i) => (t.kind === "txt" ? t.text : <span key={i} className={`sql-${t.kind}`}>{t.text}</span>))}</code></pre>}
    </div>
  );
}
