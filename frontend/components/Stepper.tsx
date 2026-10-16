"use client";
import { useEffect, useState } from "react";
import type { Turn } from "@/lib/types";

export const STAGE_LABEL: Record<string, string> = {
  route: "Understanding your question", plan: "Writing SQL", execute: "Running on BigQuery", respond: "Preparing the answer",
  rca: "Investigating the root cause", narrate: "Writing insights", discover: "Looking up definitions", help: "Preparing help", meta: "Checking the previous answer",
};
export const stageLabel = (node: string) => STAGE_LABEL[node] ?? "Working";

/** Live progress of one running turn: finished stages with a check, running ones with a spinner, elapsed seconds on top. */
export default function Stepper({ steps, startedAt }: { steps: Turn["steps"]; startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);
  const secs = Math.max(0, Math.floor((now - startedAt) / 1000));
  return (
    <div className="stepper" role="status" aria-live="polite">
      <div className="stepper-head">Working<span className="muted"> · {secs}s</span></div>
      <ol>
        {steps.length === 0 && <li className="running"><span className="spin" />Starting…</li>}
        {steps.map((s, i) => s.status === "running"
          ? <li key={i} className="running"><span className="spin" />{stageLabel(s.node)}…</li>
          : <li key={i} className="finished"><span className="tick" aria-hidden>✓</span>{stageLabel(s.node)}{s.detail && <span className="muted"> · {s.detail.slice(0, 70)}</span>}</li>)}
      </ol>
    </div>
  );
}
