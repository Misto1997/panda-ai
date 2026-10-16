"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import A2uiSurface from "@/components/a2ui/A2uiSurface";
import { buildSurfaces, renderable } from "@/components/a2ui/surface";
import { useAuth } from "@/components/AuthProvider";
import Markdown from "@/components/Markdown";
import ResultView from "@/components/ResultView";
import { ApiError, streamRun } from "@/lib/sse";
import { A2UI_SURFACE, type A2uiMessage, type AgUiEvent, type Me, type Meta, type Turn } from "@/lib/types";

const WAKE_AFTER_MS = 3000;

function TurnBody({ t }: { t: Turn }) {
  const surface = useMemo(() => {
    const all = Object.values(buildSurfaces(t.surface ?? []));
    return all.find(renderable);
  }, [t.surface]);
  if (surface) return <A2uiSurface surface={surface} />;
  if (t.result) return <ResultView result={t.result} />; // no (usable) A2UI surface: plain rendering of panda.result
  if (t.text && !t.error) return <div className="streaming-text"><Markdown text={t.text} /></div>;
  return null;
}

export default function Home() {
  const auth = useAuth();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaWaiting, setMetaWaiting] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [forceRaw, setForceRaw] = useState(false);
  const [bypass, setBypass] = useState(false);
  const thread = useRef<string | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);
  const ready = !auth.loading && (!auth.enabled || Boolean(auth.email));

  const refreshMeta = async () => {
    try {
      const r = await fetch("/api/meta", { headers: await auth.authHeaders() });
      if (r.ok) setMeta(await r.json());
    } catch { /* sidebar facts are optional */ }
  };
  const refreshMe = async () => {
    if (!auth.enabled) return;
    try {
      const r = await fetch("/api/me", { headers: await auth.authHeaders() });
      if (r.ok) setMe(await r.json()); // 404 on older gateways: tolerated
    } catch { /* optional */ }
  };

  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => setMetaWaiting(true), WAKE_AFTER_MS); // cold start: first request after idle is slow
    refreshMeta().finally(() => { clearTimeout(timer); setMetaWaiting(false); });
    refreshMe();
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, auth.email]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const id = Date.now();
    setBusy(true); setQ("");
    setTurns((t) => [...t, { id, question, steps: [], text: "", done: false }]);
    const patch = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));
    const onEvent = (e: AgUiEvent) => {
      switch (e.type) {
        case "RUN_STARTED": thread.current = e.threadId; break;
        case "TEXT_MESSAGE_CONTENT": patch((t) => ({ ...t, text: t.text + e.delta })); break;
        case "ACTIVITY_SNAPSHOT":
          if (e.activityType === A2UI_SURFACE && Array.isArray(e.content)) patch((t) => ({ ...t, surface: e.content as A2uiMessage[] }));
          break;
        case "CUSTOM":
          if (e.name === "panda.step") patch((t) => ({ ...t, steps: [...t.steps, e.value as Turn["steps"][number]] }));
          else if (e.name === "panda.result") patch((t) => ({ ...t, result: e.value as Turn["result"] }));
          break;
        case "RUN_ERROR": patch((t) => ({ ...t, error: e.message })); break;
        default: break; // STEP_*, TEXT_MESSAGE_START/END, RUN_FINISHED need no UI state
      }
    };
    try {
      for await (const e of streamRun({ question, thread_id: thread.current, force_raw: forceRaw, bypass_cache: bypass }, await auth.authHeaders())) onEvent(e);
    } catch (e) {
      patch((t) => ({ ...t, error: e instanceof ApiError ? e.message : "Could not reach PANDA AI. Please try again." }));
    } finally {
      patch((t) => ({ ...t, done: true })); setBusy(false); refreshMeta(); refreshMe();
    }
  }

  if (auth.enabled && auth.loading) return <div className="signin"><div className="logo">🐼</div><p className="muted">Loading…</p></div>;
  if (auth.enabled && !auth.email) {
    return (
      <div className="signin">
        <div className="logo" style={{ fontSize: 56 }}>🐼</div>
        <h1>PANDA AI</h1>
        <p className="muted">Prompt-driven Analytics &amp; Natural Data Access</p>
        <button onClick={auth.signIn}>Sign in with Google</button>
        {auth.error && <div className="err">{auth.error}</div>}
        <div className="notice">Synthetic Acme Retail demo data</div>
      </div>
    );
  }

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="logo">🐼</span><div><h1>PANDA AI</h1><p>Prompt-driven Analytics &amp; Natural Data Access</p></div></div>
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
            <div><b>Profile</b> {meta.profile} ({meta.app_env})</div><div><b>LLM</b> {meta.llm}</div><div><b>Engine</b> {meta.engine}</div><div><b>Search</b> {meta.search}</div>
            <div><b>Data through</b> {meta.anchor}</div>
            <div><b>Raw rows</b> {meta.tables.fact_sales.toLocaleString()}</div>
            <div><b>Rollup rows</b> {meta.tables.agg_sales_daily.toLocaleString()}</div>
            <div><b>Cache</b> {meta.cache.plan_hits + meta.cache.result_hits} hits / {meta.cache.plan_misses + meta.cache.result_misses} misses</div>
          </div>)}
      </aside>
      <main>
        {auth.enabled && (
          <div className="topbar">
            {me?.remaining_today !== undefined && me.daily_limit !== undefined && <span>{me.remaining_today} / {me.daily_limit} questions left today</span>}
            <span>{auth.email}</span><button onClick={auth.signOut}>Sign out</button>
          </div>)}
        {metaWaiting && <div className="banner wake">Waking up PANDA AI (first request after idle can take ~10-15 s)</div>}
        <div className="feed">
          {turns.length === 0 && (
            <div className="hero"><h2>Ask your data in plain English.</h2>
              <p>Answers come from governed metrics, never free-form SQL. Ask <i>why</i> a metric moved and PANDA AI walks a root-cause runbook.</p></div>)}
          {turns.map((t) => (
            <div key={t.id} className="turn">
              <div className="q">{t.question}</div>
              {!t.done && <div className="steps">{t.steps.map((s, i) => <span key={i} className="step">✓ {s.step} <i>{s.detail.slice(0, 70)}</i></span>)}<span className="dots">thinking…</span></div>}
              {t.done && t.steps.length > 0 && !t.error && (
                <details className="trace"><summary>{t.steps.length} steps · {t.steps.reduce((a, s) => a + s.ms, 0).toFixed(0)} ms</summary>
                  {t.steps.map((s, i) => <div key={i}><b>{s.step}</b> {s.detail} <span className="muted">{s.ms} ms</span></div>)}</details>)}
              <TurnBody t={t} />
              {t.error && <div className="result error">{t.error}</div>}
            </div>))}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about Net GMV, visits, ASP… or “why did Net GMV drop?”" autoFocus />
          <button disabled={busy || !q.trim()}>Ask</button>
        </form>
        <div className="notice">Synthetic Acme Retail demo data</div>
      </main>
    </div>
  );
}
