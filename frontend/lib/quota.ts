import type { Me } from "./types";

const clamp = (n: unknown): number | undefined => (typeof n === "number" && Number.isFinite(n) ? Math.max(0, Math.floor(n)) : undefined);

/** Top-bar quota text; tolerates older gateways that omit fields. Returns undefined when nothing sensible can be shown. */
export function quotaText(me: Me | null): string | undefined {
  if (!me) return undefined;
  const left = clamp(me.remaining_today);
  if (me.admin) return left === undefined ? "Admin" : `Admin · ${left} questions left today (shared pool)`;
  const limit = clamp(me.daily_limit);
  return left !== undefined && limit !== undefined ? `${Math.min(left, limit)} / ${limit} questions left today` : undefined;
}
