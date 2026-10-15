"use client";
import { useEffect, useRef, useState } from "react";
import ResultView from "@/components/ResultView";
import { readSSE } from "@/lib/sse";
import type { Meta, Turn } from "@/lib/types";

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [forceRaw, setForceRaw] = useState(false);
  const [bypass, setBypass] = useState(false);
  const thread = useRef<string | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);

  const refreshMeta = () => fetch("/api/meta").then((r) => r.json()).then(setMeta).catch(() => {});
  useEffect(() => { refreshMeta(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const id = Date.now();
    setBusy(true); setQ("");
    setTurns((t) => [...t, { id, question, steps: [], done: false }]);
    const patch = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, thread_id: thread.current, force_raw: forceRaw, bypass_cache: bypass }) });
      for await (const { event, data } of readSSE(res)) {
        if (event === "run_started") thread.current = data.thread_id;
        else if (event === "step") patch((t) => ({ ...t, steps: [...t.steps, data] }));
        else if (event === "result") patch((t) => ({ ...t, result: data }));
        else if (event === "error") patch((t) => ({ ...t, error: data.message }));
      }
    } catch (e) {
      patch((t) => ({ ...t, error: String(e) }));
    } finally {
      patch((t) => ({ ...t, done: true })); setBusy(false); refreshMeta();
    }
  }

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="logo">🐼</span><div><h1>PANDA</h1><p>Prompt-driven Analytics &amp; Natural Data Access</p></div></div>
        <h3>Try asking</h3>
        {(meta?.suggestions ?? []).map((s) => <button key={s} className="suggest" onClick={() => ask(s)} disabled={busy}>{s}</button>)}
        <h3>Demo controls</h3>
        <label title="Query the raw fact table instead of the pre-aggregated daily rollup, to compare query time">
          <input type="checkbox" checked={forceRaw} onChange={(e) => setForceRaw(e.target.checked)} /> Force raw table scan <span className="muted">(skip rollup)</span></label>
        <label title="Ignore cached intents and results for this question, to compare latency with and without the cache">
          <input type="checkbox" checked={bypass} onChange={(e) => setBypass(e.target.checked)} /> Bypass semantic cache</label>
        <button className="link" onClick={() => { thread.current = undefined; setTurns([]); }}>New conversation</button>
        {meta && (
          <div className="status">
            <h3>Runtime</h3>
            <div><b>LLM</b> {meta.llm}</div><div><b>Engine</b> {meta.engine}</div><div><b>Search</b> {meta.search}</div>
            <div><b>Data through</b> {meta.anchor}</div>
            <div><b>Raw rows</b> {meta.tables.fact_sales.toLocaleString()}</div>
            <div><b>Rollup rows</b> {meta.tables.agg_sales_daily.toLocaleString()}</div>
            <div><b>Cache</b> {meta.cache.plan_hits + meta.cache.result_hits} hits / {meta.cache.plan_misses + meta.cache.result_misses} misses</div>
          </div>)}
      </aside>
      <main>
        <div className="feed">
          {turns.length === 0 && (
            <div className="hero"><h2>Ask your data in plain English.</h2>
              <p>Answers come from governed metrics, never free-form SQL. Ask <i>why</i> a metric moved and PANDA walks a root-cause runbook.</p></div>)}
          {turns.map((t) => (
            <div key={t.id} className="turn">
              <div className="q">{t.question}</div>
              {!t.done && <div className="steps">{t.steps.map((s, i) => <span key={i} className="step">✓ {s.step} <i>{s.detail.slice(0, 70)}</i></span>)}<span className="dots">thinking…</span></div>}
              {t.done && t.steps.length > 0 && !t.error && (
                <details className="trace"><summary>{t.steps.length} steps · {t.steps.reduce((a, s) => a + s.ms, 0).toFixed(0)} ms</summary>
                  {t.steps.map((s, i) => <div key={i}><b>{s.step}</b> {s.detail} <span className="muted">{s.ms} ms</span></div>)}</details>)}
              {t.result && <ResultView result={t.result} />}
              {t.error && <div className="result error">{t.error}</div>}
            </div>))}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about Net GMV, visits, ASP… or “why did Net GMV drop?”" autoFocus />
          <button disabled={busy || !q.trim()}>Ask</button>
        </form>
      </main>
    </div>
  );
}
