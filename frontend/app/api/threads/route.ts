// Passthrough to GET /api/threads (the signed-in user's chat history list).
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const r = await fetch(`${GATEWAY}/api/threads`, { cache: "no-store", signal: req.signal, headers: forwardHeaders(req) });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch { return unreachable(); }
}
