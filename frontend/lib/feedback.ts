import type { Rating } from "./types";

export const UP_REASONS = ["Correct", "Useful", "Clear"];
export const DOWN_REASONS = ["Wrong answer", "Wrong data", "Wrong period", "Too slow", "Bad chart", "Missed my question", "Other"];
export const MAX_COMMENT = 240;

export type FeedbackBody = { thread_id: string; turn: number; question: string; rating: Rating; reasons: string[]; comment?: string };

export async function postFeedback(body: FeedbackBody, headers: Record<string, string>): Promise<boolean> {
  try {
    const r = await fetch("/api/feedback", { method: "POST", headers: { ...headers, "content-type": "application/json" }, body: JSON.stringify(body) });
    return r.ok;
  } catch { return false; }
}

export async function fetchRatings(threadId: string, headers: Record<string, string>): Promise<Record<number, Rating>> {
  try {
    const r = await fetch(`/api/threads/${encodeURIComponent(threadId)}/feedback`, { headers });
    if (!r.ok) return {};
    const b = await r.json();
    const out: Record<number, Rating> = {};
    for (const [k, v] of Object.entries(b?.ratings ?? {})) if ((v === "up" || v === "down") && Number.isInteger(Number(k))) out[Number(k)] = v;
    return out;
  } catch { return {}; }
}
