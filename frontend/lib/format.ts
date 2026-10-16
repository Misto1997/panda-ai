export function fmt(v: unknown, kind?: string): string {
  if (v === null || v === undefined) return "n/a";
  if (typeof v !== "number") return String(v);
  const a = Math.abs(v), sign = v < 0 ? "-" : "";
  if (kind === "percent") return `${(v * 100).toFixed(2)}%`;
  const short = a >= 1e9 ? `${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(2)}M` : a >= 1e4 ? `${(a / 1e3).toFixed(1)}K` : a.toLocaleString(undefined, { maximumFractionDigits: kind === "currency" ? 2 : 0 });
  return kind === "currency" ? `${sign}$${short}` : `${sign}${short}`;
}
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`);
