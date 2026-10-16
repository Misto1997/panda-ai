"use client";
import { CAPABILITIES, groupSuggestions } from "@/lib/suggestions";
import type { Meta } from "@/lib/types";

const FLOW = ["Question", "Governed SQL", "BigQuery", "Answer + chart"];

export default function EmptyState({ meta, busy, ask }: { meta: Meta | null; busy: boolean; ask: (q: string) => void }) {
  return (
    <div className="hero">
      <h2>Ask your data anything.</h2>
      <p className="lead">PANDA AI writes SQL over governed Acme Retail metrics with Gemini, validates it, runs it on BigQuery and explains the result.</p>
      <div className="cards">
        {CAPABILITIES.map((c) => (
          <button key={c.title} className="cap-card" onClick={() => ask(c.q)} disabled={busy}>
            <b>{c.title}</b><span className="cap-hint">{c.hint}</span><span className="cap-q">{c.q}</span>
          </button>))}
      </div>
      <div className="groups">
        {groupSuggestions(meta).map((g) => (
          <div key={g.title} className="group"><h4>{g.title}</h4>
            <div className="chip-row">{g.items.map((s) => <button key={s} className="example" onClick={() => ask(s)} disabled={busy}>{s}</button>)}</div></div>))}
      </div>
      <ol className="flow" aria-label="How it works">{FLOW.map((f, i) => <li key={f}>{f}{i < FLOW.length - 1 && <span className="arrow" aria-hidden>→</span>}</li>)}</ol>
      <div className="data-badge">Synthetic Acme Retail data{meta?.anchor ? `, through ${meta.anchor}` : ""}</div>
    </div>
  );
}
