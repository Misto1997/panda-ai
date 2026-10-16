import type { Meta } from "./types";

export type SuggestionGroup = { title: string; items: string[] };

/** Shown when /api/meta fails or returns no suggestions. */
export const STATIC_SUGGESTIONS: SuggestionGroup[] = [
  { title: "Ask", items: ["Net GMV by zone for the last 7 days", "Daily visits for the last 14 days", "Average selling price by business unit last month"] },
  { title: "Investigate", items: ["Why did visits drop in the last 14 days?", "Why did Net GMV drop last week?"] },
  { title: "Learn", items: ["What is BU visits?", "How is conversion defined?"] },
];

export const CAPABILITIES = [
  { title: "Ask", hint: "Metrics, trends and breakdowns", q: "Net GMV by zone for the last 7 days" },
  { title: "Investigate", hint: "Find out why a metric moved", q: "Why did visits drop in the last 14 days?" },
  { title: "Learn", hint: "Definitions from the governed layer", q: "What is BU visits?" },
];

export function groupSuggestions(meta: Meta | null): SuggestionGroup[] {
  const list = (meta?.suggestions ?? []).filter((s) => typeof s === "string" && s.trim());
  if (list.length === 0) return STATIC_SUGGESTIONS;
  const groups: Record<string, string[]> = { Ask: [], Investigate: [], Learn: [] };
  for (const s of list) {
    const k = /^(why|what caused|root cause)/i.test(s) ? "Investigate" : /^(what is|what's|define|explain|how is)/i.test(s) ? "Learn" : "Ask";
    groups[k].push(s);
  }
  return Object.entries(groups).filter(([, items]) => items.length).map(([title, items]) => ({ title, items }));
}
