"use client";
// Thumbs up / thumbs down / copy under a finished answer. Feedback errors are inline and never touch the answer itself.
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthProvider";
import { CheckIcon, CopyIcon, ThumbDownIcon, ThumbUpIcon } from "./icons";
import { copyText } from "@/lib/clipboard";
import { DOWN_REASONS, MAX_COMMENT, UP_REASONS, postFeedback } from "@/lib/feedback";
import type { Rating, Table } from "@/lib/types";

const MAX_COPY_ROWS = 100;
const cell = (v: string | number | null) => String(v ?? "").replace(/[\t\r\n]+/g, " ");

export function answerClipboard(text: string, table?: Table): string {
  if (!table || !table.rows?.length) return text;
  const head = table.columns.map((c) => cell(table.titles?.[c] ?? c)).join("\t");
  const rows = table.rows.slice(0, MAX_COPY_ROWS).map((r) => r.map(cell).join("\t"));
  return `${text}\n\n${[head, ...rows].join("\n")}`;
}

type Props = { threadId: string; turn: number; question: string; text: string; table?: Table; rating?: Rating; onRated: (r: Rating) => void };

export default function AnswerActions({ threadId, turn, question, text, table, rating, onRated }: Props) {
  const auth = useAuth();
  const [panel, setPanel] = useState<"up" | "down" | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [thanks, setThanks] = useState(false);
  const [error, setError] = useState<string>();
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function send(r: Rating, why: string[], note?: string) {
    if (busy) return false;
    setBusy(true); setError(undefined);
    const ok = await postFeedback({ thread_id: threadId, turn, question, rating: r, reasons: why.slice(0, 5), ...(note?.trim() ? { comment: note.trim().slice(0, MAX_COMMENT) } : {}) }, await auth.authHeaders());
    setBusy(false);
    if (!ok) { setError("Could not send feedback. Please try again."); return false; }
    onRated(r); setThanks(true);
    return true;
  }

  async function up() {
    if (busy || rating === "up") return;
    setPanel(null); setThanks(false);
    if (await send("up", [])) setPanel("up");
  }
  const down = () => { if (busy) return; setThanks(false); setError(undefined); setReasons([]); setComment(""); setPanel("down"); };
  async function pickUpReason(reason: string) {
    if (await send("up", [reason])) setPanel(null);
  }
  async function submitDown() { if (await send("down", reasons, comment)) setPanel(null); }
  const toggle = (r: string) => setReasons((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : cur.length >= 5 ? cur : [...cur, r]));

  async function copy() {
    setCopied((await copyText(answerClipboard(text, table))) ? "ok" : "fail");
    clearTimeout(timer.current); timer.current = setTimeout(() => setCopied(null), 1800);
  }

  return (
    <div className="actions">
      <div className="actions-row">
        <button type="button" className={`act${rating === "up" ? " on up" : ""}`} onClick={up} disabled={busy} aria-pressed={rating === "up"} aria-label="Good answer" title="Good answer"><ThumbUpIcon filled={rating === "up"} /></button>
        <button type="button" className={`act${rating === "down" ? " on down" : ""}`} onClick={down} disabled={busy} aria-pressed={rating === "down"} aria-label="Bad answer" title="Bad answer"><ThumbDownIcon filled={rating === "down"} /></button>
        <button type="button" className="act" onClick={copy} aria-label="Copy answer" title="Copy answer">{copied === "ok" ? <CheckIcon /> : <CopyIcon />}</button>
        <span className="act-status" role="status" aria-live="polite">{copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : thanks && !panel ? "Thanks for the feedback" : ""}</span>
      </div>
      {panel === "up" && (
        <div className="fb-panel" role="group" aria-label="What worked?">
          <span className="muted">Thanks! What worked? (optional)</span>
          <div className="pill-row">{UP_REASONS.map((r) => <button key={r} type="button" className="reason" disabled={busy} onClick={() => pickUpReason(r)}>{r}</button>)}</div>
        </div>)}
      {panel === "down" && (
        <div className="fb-panel" role="group" aria-label="Tell us what went wrong">
          <span className="muted">What went wrong?</span>
          <div className="pill-row">{DOWN_REASONS.map((r) => <button key={r} type="button" className={`reason${reasons.includes(r) ? " sel" : ""}`} aria-pressed={reasons.includes(r)} onClick={() => toggle(r)}>{r}</button>)}</div>
          <textarea value={comment} maxLength={MAX_COMMENT} onChange={(e) => setComment(e.target.value)} placeholder="Anything else? (optional)" aria-label="Feedback comment" rows={2} />
          <div className="fb-foot"><span className="muted">{comment.length}/{MAX_COMMENT}</span><span className="spacer" />
            <button type="button" className="ghost-btn" onClick={() => setPanel(null)} disabled={busy}>Cancel</button>
            <button type="button" className="primary-btn" onClick={submitDown} disabled={busy}>{busy ? "Sending…" : "Submit"}</button></div>
        </div>)}
      {error && <div className="fb-error" role="alert">{error}</div>}
    </div>
  );
}
