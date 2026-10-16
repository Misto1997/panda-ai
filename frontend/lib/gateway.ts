// Shared by the BFF route handlers: gateway address and Authorization forwarding.
export const GATEWAY = process.env.GATEWAY_URL ?? "http://localhost:8000";

export function forwardHeaders(req: Request, extra: Record<string, string> = {}): Record<string, string> {
  const h = { ...extra };
  const auth = req.headers.get("authorization");
  if (auth) h.authorization = auth; // the gateway verifies the Firebase ID token
  const xff = req.headers.get("x-forwarded-for");
  if (xff) h["x-forwarded-for"] = xff; // the browser's address as seen by Google's front end, so the API's per-IP limit is per user, not per web service
  return h;
}

export const unreachable = () =>
  Response.json({ code: "gateway_unreachable", message: "PANDA AI backend is not reachable right now." }, { status: 502 });
