// AG-UI client: POST the run, read `data: <json>` SSE lines, yield typed events.
import type { AgUiEvent } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public remaining?: number) { super(message); }
}

/** Turns a non-2xx gateway response ({code,message} JSON, 401/429 contract) into an ApiError with a friendly message. */
export async function toApiError(res: Response): Promise<ApiError> {
  let body: { code?: string; message?: string; remaining?: number; detail?: unknown } = {};
  try { body = await res.json(); } catch { /* non-JSON body */ }
  const code = body.code ?? `http_${res.status}`;
  const friendly =
    res.status === 401 ? "Please sign in to use PANDA AI." :
    res.status === 429 ? "You have reached today's question limit. Please try again tomorrow." :
    body.message ?? (typeof body.detail === "string" ? body.detail : `Request failed (${res.status}).`);
  return new ApiError(res.status, code, friendly, body.remaining);
}

export async function* readAgUi(res: Response): AsyncGenerator<AgUiEvent> {
  if (!res.ok || !res.body) throw await toApiError(res);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
      if (!data) continue; // comment-only block (heartbeat)
      try { yield JSON.parse(data) as AgUiEvent; } catch { /* ignore a malformed frame rather than abort the run */ }
    }
  }
}

export type RunInput = { question: string; thread_id?: string; runId?: string; force_raw?: boolean; bypass_cache?: boolean };

export async function* streamRun(input: RunInput, headers: Record<string, string> = {}, signal?: AbortSignal): AsyncGenerator<AgUiEvent> {
  const res = await fetch("/api/chat", {
    method: "POST", signal, body: JSON.stringify(input),
    headers: { "content-type": "application/json", accept: "text/event-stream", ...headers },
  });
  yield* readAgUi(res);
}
