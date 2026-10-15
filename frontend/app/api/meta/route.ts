const GATEWAY = process.env.GATEWAY_URL ?? "http://localhost:8000";
export const dynamic = "force-dynamic";

export async function GET() {
  const r = await fetch(`${GATEWAY}/api/meta`, { cache: "no-store" });
  return new Response(r.body, { status: r.status, headers: { "content-type": "application/json" } });
}
