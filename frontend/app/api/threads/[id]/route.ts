// Passthrough to GET / DELETE /api/threads/{id}. The id is URL-encoded; the gateway validates it.
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";
type Ctx = { params: Promise<{ id: string }> };

async function forward(req: Request, ctx: Ctx, method: "GET" | "DELETE") {
  try {
    const { id } = await ctx.params;
    const r = await fetch(`${GATEWAY}/api/threads/${encodeURIComponent(id)}`, { method, cache: "no-store", signal: req.signal, headers: forwardHeaders(req) });
    if (r.status === 204) return new Response(null, { status: 204 });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch { return unreachable(); }
}

export const GET = (req: Request, ctx: Ctx) => forward(req, ctx, "GET");
export const DELETE = (req: Request, ctx: Ctx) => forward(req, ctx, "DELETE");
