// BFF: proxies the AG-UI event stream to the query gateway and forwards the caller's Authorization header.
import { GATEWAY, forwardHeaders, unreachable } from "@/lib/gateway";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${GATEWAY}/api/chat`, {
      method: "POST", headers: forwardHeaders(req, { "content-type": "application/json", accept: "text/event-stream" }), body: await req.text(), signal: req.signal,
    });
  } catch { return unreachable(); }
  const ok = upstream.ok;  // 401/429/422 come back as JSON and must not be labelled as an event stream
  return new Response(upstream.body, {
    status: upstream.status,
    headers: ok
      ? { "content-type": "text/event-stream", "cache-control": "no-cache, no-transform", "x-accel-buffering": "no" }
      : { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
