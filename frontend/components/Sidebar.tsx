"use client";
import { useState } from "react";
import { ChevronIcon, CloseIcon, PlusIcon, SidebarIcon, SlidersIcon } from "./icons";
import type { Meta, ThreadSummary } from "@/lib/types";

export function relativeTime(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (!Number.isFinite(s)) return "";
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

type Props = {
  collapsed: boolean; mobileOpen: boolean; onToggle: () => void; onCloseMobile: () => void;
  threads: ThreadSummary[]; threadsLoaded: boolean; activeId?: string; busy: boolean;
  onNew: () => void; onOpen: (id: string) => void; onDelete: (id: string) => void;
  forceRaw: boolean; setForceRaw: (v: boolean) => void; bypass: boolean; setBypass: (v: boolean) => void;
  meta: Meta | null;
};

export default function Sidebar(p: Props) {
  const [demoOpen, setDemoOpen] = useState(false);
  const cls = `sidebar${p.collapsed ? " collapsed" : ""}${p.mobileOpen ? " open" : ""}`;
  const hits = p.meta ? p.meta.cache.plan_hits + p.meta.cache.result_hits : 0;
  const misses = p.meta ? p.meta.cache.plan_misses + p.meta.cache.result_misses : 0;
  return (
    <>
      {p.mobileOpen && <div className="scrim" onClick={p.onCloseMobile} />}
      <aside className={cls} aria-label="Chats">
        <div className="side-head">
          <span className="brand-mark" aria-hidden>🐼</span>
          <span className="brand-name">PANDA AI</span>
          <button className="icon-btn" onClick={p.onToggle} aria-label={p.collapsed ? "Expand sidebar" : "Collapse sidebar"} title={p.collapsed ? "Expand sidebar" : "Collapse sidebar"}><SidebarIcon /></button>
        </div>
        <button className="new-chat" onClick={p.onNew} disabled={p.busy} aria-label="New chat" title="New chat"><PlusIcon /><span className="label">New chat</span></button>

        <div className="side-body">
          <h3>Chats</h3>
          {p.threads.length === 0
            ? <p className="empty-list">{p.threadsLoaded ? "Your chats will appear here" : "Loading…"}</p>
            : <ul className="chat-list">{p.threads.map((t) => (
              <li key={t.id} className={t.id === p.activeId ? "active" : ""}>
                <button className="chat-item" onClick={() => p.onOpen(t.id)} disabled={p.busy} title={t.title} aria-current={t.id === p.activeId ? "true" : undefined}>
                  <span className="chat-title">{t.title}</span><span className="chat-time">{relativeTime(t.updated_at)}</span>
                </button>
                <button className="icon-btn del" onClick={() => p.onDelete(t.id)} aria-label={`Delete chat: ${t.title}`} title="Delete chat"><CloseIcon /></button>
              </li>))}</ul>}
        </div>

        <div className="side-foot">
          <div className="demo">
            <button className="foot-btn" onClick={() => setDemoOpen((v) => !v)} aria-expanded={demoOpen} aria-label="Demo controls" title="Demo controls"><SlidersIcon /><span className="label">Demo</span></button>
            {demoOpen && (
              <div className="popover" role="group" aria-label="Demo controls">
                <label title="Query the raw fact table instead of the pre-aggregated daily rollup, to compare query time">
                  <input type="checkbox" checked={p.forceRaw} onChange={(e) => p.setForceRaw(e.target.checked)} /> Force raw table scan <span className="muted">(skip rollup)</span></label>
                <label title="Ignore cached intents and results for this question, to compare latency with and without the cache">
                  <input type="checkbox" checked={p.bypass} onChange={(e) => p.setBypass(e.target.checked)} /> Bypass semantic cache</label>
              </div>)}
          </div>
          {p.meta && (
            <details className="runtime">
              <summary><span>Runtime</span><ChevronIcon /></summary>
              <dl>
                <dt>Profile</dt><dd>{p.meta.profile} ({p.meta.app_env})</dd>
                <dt>LLM</dt><dd>{p.meta.llm}</dd>
                <dt>Engine</dt><dd>{p.meta.engine}</dd>
                <dt>Search</dt><dd>{p.meta.search}</dd>
                <dt>Data through</dt><dd>{p.meta.anchor}</dd>
                <dt>Cache</dt><dd>{hits} hits / {misses} misses</dd>
              </dl>
            </details>)}
        </div>
      </aside>
    </>
  );
}
