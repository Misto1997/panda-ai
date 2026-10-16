"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import AnswerActions from "@/components/AnswerActions";
import A2uiSurface from "@/components/a2ui/A2uiSurface";
import { buildSurfaces, renderable } from "@/components/a2ui/surface";
import { useAuth } from "@/components/AuthProvider";
import { AskContext } from "@/components/blocks";
import EmptyState from "@/components/EmptyState";
import { MenuIcon, SendIcon } from "@/components/icons";
import Markdown from "@/components/Markdown";
import ResultView from "@/components/ResultView";
import Sidebar from "@/components/Sidebar";
import Stepper, { stageLabel } from "@/components/Stepper";
import { fetchRatings } from "@/lib/feedback";
import { quotaText } from "@/lib/quota";
import { ApiError, streamRun } from "@/lib/sse";
import { A2UI_SURFACE, type A2uiMessage, type AgUiEvent, type Me, type Meta, type Rating, type StoredTurn, type ThreadSummary, type Turn } from "@/lib/types";

const WAKE_AFTER_MS = 3000;
const META_REFRESH_MS = 60_000;
const SIDEBAR_KEY = "panda.sidebar.collapsed";
const FEATURES = [
  ["Ask in plain English", "Metrics, trends and breakdowns without writing a query."],
  ["Investigate why metrics move", "A root-cause runbook walks the numbers for you."],
  ["Governed SQL on BigQuery", "Generated SQL is validated against the semantic layer before it runs."],
];

/** Live steps: a node shows as running until its finished records arrive (which replace the placeholder); skipped nodes just vanish. */
function mergeStep(steps: Turn["steps"], s: Turn["steps"][number]): Turn["steps"] {
  if (s.status === "running") return steps.some((x) => x.status === "running" && x.node === s.node) ? steps : [...steps, s];
  const rest = steps.filter((x) => !(x.status === "running" && x.node === s.node));
  return s.status === "skipped" ? rest : [...rest, s];
}

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
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadsLoaded, setThreadsLoaded] = useState(false);
  const [activeId, setActiveId] = useState<string>();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [ratings, setRatings] = useState<Record<number, Rating>>({});
  const thread = useRef<string | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);
  const quota = quotaText(me);
  const ready = !auth.loading && (!auth.enabled || Boolean(auth.email));

  useEffect(() => { try { setCollapsed(localStorage.getItem(SIDEBAR_KEY) === "1"); } catch { /* storage unavailable */ } }, []);
  const toggleSidebar = () => {
    if (window.matchMedia("(max-width: 860px)").matches) { setMobileOpen((v) => !v); return; }
    setCollapsed((c) => { try { localStorage.setItem(SIDEBAR_KEY, c ? "0" : "1"); } catch { /* ignore */ } return !c; });
  };

  const setThread = (id?: string) => { thread.current = id; setActiveId(id); };
  const resetConversation = () => { openSeq.current++; setThread(undefined); setTurns([]); setNotice(undefined); setRatings({}); };
  const refreshMeta = async () => {
    try {
      const r = await fetch("/api/meta", { headers: await auth.authHeaders() });
      if (r.ok) { const m = await r.json(); if (m && typeof m === "object") setMeta(m); } // a failed refresh keeps existing meta
    } catch { /* sidebar facts are optional */ }
  };
  const refreshMe = async () => {
    if (!auth.enabled) return;
    try {
      const r = await fetch("/api/me", { headers: await auth.authHeaders() });
      if (r.ok) setMe(await r.json()); // 404 on older gateways: tolerated
    } catch { /* optional */ }
  };
  const refreshThreads = async () => {
    try {
      const r = await fetch("/api/threads", { headers: await auth.authHeaders() });
      if (r.ok) { const b = await r.json(); if (Array.isArray(b?.threads)) setThreads(b.threads); } // 404 on older gateways: tolerated
    } catch { /* history is optional */ } finally { setThreadsLoaded(true); }
  };

  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => setMetaWaiting(true), WAKE_AFTER_MS); // cold start: first request after idle is slow
    refreshMeta().finally(() => { clearTimeout(timer); setMetaWaiting(false); });
    refreshMe();
    refreshThreads();
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, auth.email]);
  // Live runtime numbers: refresh on an interval while the tab is visible, and when the tab or window regains focus.
  const metaRefresher = useRef(refreshMeta);
  metaRefresher.current = refreshMeta;
  useEffect(() => {
    if (!ready) return;
    const tick = () => { if (document.visibilityState === "visible") void metaRefresher.current(); };
    const timer = setInterval(tick, META_REFRESH_MS);
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); window.removeEventListener("focus", tick); document.removeEventListener("visibilitychange", tick); };
  }, [ready, auth.email]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  const openSeq = useRef(0);
  async function openThread(id: string) {
    if (busy) return;
    const seq = ++openSeq.current; // only the latest click may apply its result
    setMobileOpen(false); setNotice(undefined);
    try {
      const r = await fetch(`/api/threads/${encodeURIComponent(id)}`, { headers: await auth.authHeaders() });
      if (!r.ok) throw new Error(String(r.status));
      const b = await r.json() as { turns: StoredTurn[] };
      const restored = await fetchRatings(id, await auth.authHeaders());
      if (seq !== openSeq.current) return;
      const base = Date.now();
      setRatings(restored);
      setTurns(b.turns.map((t, i) => ({
        id: base + i, question: t.question, steps: [], text: t.response?.text ?? "", result: t.response,
        surface: t.surface ?? undefined, done: true,
      })));
      setThread(id);
    } catch {
      setNotice("Could not open that chat. Please try again.");
      void refreshThreads();
    }
  }

  async function deleteThread(id: string) {
    if (!window.confirm("Delete this chat?")) return;
    try {
      const r = await fetch(`/api/threads/${encodeURIComponent(id)}`, { method: "DELETE", headers: await auth.authHeaders() });
      if (!r.ok && r.status !== 404) throw new Error(String(r.status));
      if (thread.current === id) resetConversation();
    } catch { setNotice("Could not delete that chat. Please try again."); }
    void refreshThreads();
  }

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    const id = Date.now();
    setBusy(true); setQ(""); setNotice(undefined);
    setTurns((t) => [...t, { id, question, steps: [], text: "", done: false }]);
    const patch = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));
    const onEvent = (e: AgUiEvent) => {
      switch (e.type) {
        case "RUN_STARTED": setThread(e.threadId); break;
        case "TEXT_MESSAGE_START": patch((t) => ({ ...t, text: "" })); break; // an upgraded answer replaces the first one
        case "TEXT_MESSAGE_CONTENT": patch((t) => ({ ...t, text: t.text + e.delta })); break;
        case "ACTIVITY_SNAPSHOT":
          if (e.activityType === A2UI_SURFACE && Array.isArray(e.content)) patch((t) => ({ ...t, surface: e.content as A2uiMessage[] }));
          break;
        case "CUSTOM":
          if (e.name === "panda.step") patch((t) => ({ ...t, steps: mergeStep(t.steps, e.value as Turn["steps"][number]) }));
          else if (e.name === "panda.result") patch((t) => ({ ...t, result: e.value as Turn["result"] }));
          break;
        case "RUN_ERROR": patch((t) => ({ ...t, error: e.message })); break;
        default: break; // STEP_*, TEXT_MESSAGE_END, RUN_FINISHED need no UI state
      }
    };
    try {
      for await (const e of streamRun({ question, thread_id: thread.current, force_raw: forceRaw, bypass_cache: bypass }, await auth.authHeaders())) onEvent(e);
    } catch (e) {
      patch((t) => ({ ...t, error: e instanceof ApiError ? e.message : "Could not reach PANDA AI. Please try again." }));
    } finally {
      patch((t) => ({ ...t, done: true })); setBusy(false); refreshMeta(); refreshMe();
      void refreshThreads(); setTimeout(() => void refreshThreads(), 1500); // the server writes history just after the stream ends
    }
  }

  const signOut = () => { resetConversation(); setThreads([]); setThreadsLoaded(false); setMe(null); void auth.signOut(); };

  if (auth.enabled && auth.loading) return <div className="signin"><div className="logo">🐼</div><p className="muted">Loading…</p></div>;
  if (auth.enabled && !auth.email) {
    return (
      <div className="signin">
        <div className="logo" style={{ fontSize: 56 }}>🐼</div>
        <h1>PANDA AI</h1>
        <p className="tagline">Ask questions about your business data in plain English. PANDA AI writes the SQL, checks it against governed metrics, runs it on BigQuery and explains what it finds.</p>
        <ul className="features">{FEATURES.map(([t, d]) => <li key={t}><b>{t}</b><span>{d}</span></li>)}</ul>
        <button onClick={auth.signIn}>Sign in with Google</button>
        {auth.error && <div className="err">{auth.error}</div>}
        <div className="notice">Synthetic Acme Retail demo data</div>
      </div>
    );
  }

  return (
    <div className={`shell${collapsed ? " rail" : ""}`}>
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onToggle={toggleSidebar} onCloseMobile={() => setMobileOpen(false)}
        threads={threads} threadsLoaded={threadsLoaded} activeId={activeId} busy={busy}
        onNew={() => { resetConversation(); setMobileOpen(false); }} onOpen={openThread} onDelete={deleteThread}
        forceRaw={forceRaw} setForceRaw={setForceRaw} bypass={bypass} setBypass={setBypass} meta={meta} />
      <main>
        <div className="topbar">
          <button className="icon-btn menu" onClick={toggleSidebar} aria-label="Open sidebar"><MenuIcon /></button>
          <span className="spacer" />
          {auth.enabled && <>
            {quota && <span>{quota}</span>}
            <span>{auth.email}</span><button className="ghost" onClick={signOut}>Sign out</button></>}
        </div>
        {metaWaiting && <div className="banner wake">Waking up PANDA AI (first request after idle can take ~10-15 s)</div>}
        {notice && <div className="banner err-banner" role="alert">{notice}</div>}
        <div className="feed">
          {turns.length === 0 && <EmptyState meta={meta} busy={busy} ask={ask} />}
          <AskContext.Provider value={{ ask, disabled: busy }}>
          {turns.map((t, ti) => {
            const turnIndex = turns.slice(0, ti).filter((x) => !x.error && x.result?.type !== "error").length; // failed runs are not stored in the thread
            const answerText = t.result?.text ?? t.text;
            const rateable = t.done && !t.error && t.result?.type !== "error" && Boolean(activeId) && Boolean(answerText);
            const narrating = !t.done && t.steps.some((s) => s.status === "running" && s.node === "narrate");
            return (
              <div key={t.id} className="turn">
                <div className="q">{t.question}</div>
                {!t.done && <Stepper steps={t.steps} startedAt={t.id} />}
                {t.done && t.steps.length > 0 && !t.error && (
                  <details className="trace"><summary>{t.steps.filter((s) => !s.status).length} steps · {t.steps.reduce((a, s) => a + s.ms, 0).toFixed(0)} ms</summary>
                    {t.steps.map((s, i) => <div key={i}><b>{stageLabel(s.node)}</b> {s.detail} <span className="muted">{s.ms} ms</span></div>)}</details>)}
                <div key={t.result?.meta?.narrated ? "narrated" : "standard"} className="answer-wrap"><TurnBody t={t} /></div>
                {narrating && <div className="hint" role="status">Writing insights…</div>}
                {t.error && <div className="result error">{t.error}</div>}
                {rateable && activeId && <AnswerActions key={`${activeId}:${turnIndex}`} threadId={activeId} turn={turnIndex} question={t.question} text={answerText} table={t.result?.table}
                  rating={ratings[turnIndex]} onRated={(r) => { if (thread.current === activeId) setRatings((cur) => ({ ...cur, [turnIndex]: r })); }} />}
              </div>);
          })}
          </AskContext.Provider>
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Ask a question" placeholder="Ask about Net GMV, visits, ASP… or “why did Net GMV drop?”" autoFocus />
          <button disabled={busy || !q.trim()} aria-label="Send question" title="Send"><SendIcon /></button>
        </form>
        <div className="notice">Synthetic Acme Retail demo data</div>
      </main>
    </div>
  );
}
