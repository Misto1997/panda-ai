// Passthrough to GET /api/threads/{id}/feedback ({ratings: {"0": "up"}}), used to restore thumbs when an old chat is opened.
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, ctx: Ctx) {
  try {
    const { id } = await ctx.params;
    const r = await fetch(`${GATEWAY}/api/threads/${encodeURIComponent(id)}/feedback`, { cache: "no-store", signal: req.signal, headers: forwardHeaders(req) });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch { return unreachable(); }
}
