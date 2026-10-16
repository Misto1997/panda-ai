// Passthrough to POST /api/feedback (thumbs up/down on an answer).
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const r = await fetch(`${GATEWAY}/api/feedback`, {
      method: "POST", cache: "no-store", signal: req.signal, body: await req.text(),
      headers: forwardHeaders(req, { "content-type": "application/json" }),
    });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch { return unreachable(); }
}
