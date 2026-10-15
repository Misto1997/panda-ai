// BFF: proxies the SSE stream to the query gateway. Phase 2 adds Google session -> signed JWT here.
const GATEWAY = process.env.GATEWAY_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const upstream = await fetch(`${GATEWAY}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "text/event-stream", "cache-control": "no-cache, no-transform", "x-accel-buffering": "no" },
  });
}
