// Passthrough to GET /api/me ({email, remaining_today, daily_limit}). Older gateways return 404; the UI tolerates it.
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const r = await fetch(`${GATEWAY}/api/me`, { cache: "no-store", headers: forwardHeaders(req) });
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch { return unreachable(); }
}
